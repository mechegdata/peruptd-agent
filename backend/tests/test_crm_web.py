"""PeruPTD Native CRM (/app): login, aislamiento por tenant, Kanban, conversación, comandos, catálogo, archivos y playbook."""
import json
from unittest import mock

import pytest

from bot import db, tenant
from bot.datos import leads as leads_mod
from bot.hub import sesion
from bot.rutas import hub_api, hub_auth, hub_catalogo, hub_config
from fake_supabase import FakeSupabase
from tests.test_agente_extremo import mundo  # noqa: F401

SECRETO = "s" * 40
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64
CSRF = {"X-PTD-CSRF": "1"}


def _meta(**k):
    return json.dumps(k)


@pytest.fixture
def sb():
    f = FakeSupabase({
        "tenants": [{"id": "demo-dental", "name": "BrightSmile", "industry": "dental", "pipeline_mode": "catalogo", "crm_type": "peruptd_native",
                     "default_language": "en", "owner_whatsapp": "13055550000"},
                    {"id": "demo-b2b", "name": "Northline", "industry": "b2b", "pipeline_mode": "catalogo", "crm_type": "salesforce"}],
        "hub_users": [{"id": "u1", "tenant_id": "demo-dental", "email": "ana@smile.com", "password_hash": sesion.hash_password("clave-segura-1"),
                       "rol": "admin", "activo": True},
                      {"id": "u2", "tenant_id": "demo-dental", "email": "leo@smile.com", "password_hash": sesion.hash_password("clave-segura-2"),
                       "rol": "asesor", "activo": True},
                      {"id": "u3", "tenant_id": "demo-b2b", "email": "max@north.com", "password_hash": sesion.hash_password("clave-segura-3"),
                       "rol": "admin", "activo": True}],
        "leads": [{"tenant_id": "demo-dental", "sender_id": "twa:+13055551234", "nombre": "Jess", "canal": "whatsapp", "updated_at": "2026-11-16",
                   "interes": _meta(cita_agendada=True, fecha_cita="2026-11-01T10:00:00-05:00", visita_estado="realizada", preferred_language="en")},
                  {"tenant_id": "demo-dental", "sender_id": "51999000111", "nombre": "Rosa", "canal": "whatsapp", "updated_at": "2026-11-15",
                   "interes": _meta(stage="qualified", price_objection_count=3)},
                  {"tenant_id": "demo-dental", "sender_id": "51999000222", "nombre": "Nuevo", "canal": "messenger", "updated_at": "2026-11-14",
                   "interes": "{}"},
                  {"tenant_id": "demo-b2b", "sender_id": "51888000999", "nombre": "Otro cliente", "canal": "whatsapp", "updated_at": "2026-11-17",
                   "interes": "{}"}],
        "mensajes": [{"tenant_id": "demo-dental", "sender_id": "51999000111", "rol": "user", "contenido": "too expensive", "canal": "whatsapp", "created_at": "1"},
                     {"tenant_id": "demo-dental", "sender_id": "51999000111", "rol": "assistant", "contenido": "I hear you…", "canal": "whatsapp",
                      "motor": "NLU · Objeciones 3/3", "created_at": "2"},
                     {"tenant_id": "demo-dental", "sender_id": "51999000111", "rol": "assistant", "contenido": "Hi Rosa, Dr. Kim here", "canal": "web_manual",
                      "motor": "Asesor (manual)", "created_at": "3"},
                     {"tenant_id": "demo-b2b", "sender_id": "51888000999", "rol": "user", "contenido": "secreto de otro", "canal": "whatsapp", "created_at": "1"}],
        "catalog_items": [{"id": "11111111-1111-1111-1111-111111111111", "tenant_id": "demo-dental", "name_es": "Implantes", "list_price": 18500,
                           "sort_order": 0},
                          {"id": "22222222-2222-2222-2222-222222222222", "tenant_id": "demo-b2b", "name_es": "Plan Premium", "list_price": 1200,
                           "sort_order": 0}],
        "catalog_media": [], "tenant_playbooks": [],
    })
    parches = [mock.patch.object(m, "supabase", f) for m in (db, leads_mod, hub_api, hub_catalogo, hub_config)]
    parches += [mock.patch.object(leads_mod, "MULTI_TENANT", True), mock.patch.object(sesion, "HUB_SESSION_SECRET", SECRETO),
                mock.patch.object(sesion, "HUB_API_KEY", "k-123"), mock.patch.object(hub_auth, "HUB_COOKIE_SEGURA", False),
                mock.patch("bot.handoff.supabase", f), mock.patch("bot.playbooks.db.supabase", f)]
    for p in parches:
        p.start()
    tenant.limpiar_cache()
    sesion._INTENTOS.clear()
    from bot import playbooks
    playbooks.limpiar_cache()
    yield f
    for p in reversed(parches):
        p.stop()
    tenant.limpiar_cache()
    playbooks.limpiar_cache()


@pytest.fixture
def web(sb):
    from bot.app import app
    return app.test_client()


def entrar(web, email="ana@smile.com", clave="clave-segura-1"):
    r = web.post("/api/hub/login", json={"email": email, "password": clave})
    assert r.status_code == 200, r.get_json()
    return r


# ---------- Login y sesión ----------
def test_login_cookie_httponly_y_me(web):
    r = entrar(web)
    cookie = r.headers["Set-Cookie"]
    assert "ptd_session=" in cookie and "HttpOnly" in cookie and "SameSite=Lax" in cookie
    assert "clave" not in r.get_data(as_text=True) and "password_hash" not in r.get_data(as_text=True)
    assert web.get("/api/hub/me").get_json()["usuario"] == {"email": "ana@smile.com", "nombre": "ana@smile.com", "rol": "admin", "tenant_id": "demo-dental"}
    web.post("/api/hub/logout")
    assert web.get("/api/hub/me").status_code == 401


def test_login_falla_igual_y_bloquea_tras_5_intentos(web):
    a = web.post("/api/hub/login", json={"email": "nadie@x.com", "password": "x"}).get_json()
    b = web.post("/api/hub/login", json={"email": "ana@smile.com", "password": "mala"}).get_json()
    assert a == b == {"error": "correo o contraseña incorrectos"}
    for _ in range(4):
        web.post("/api/hub/login", json={"email": "ana@smile.com", "password": "mala"})
    r = web.post("/api/hub/login", json={"email": "ana@smile.com", "password": "clave-segura-1"})
    assert r.status_code == 401 and "demasiados intentos" in r.get_json()["error"]


def test_token_alterado_o_sin_sesion_es_401(web):
    assert web.get("/api/hub/leads").status_code == 401
    web.set_cookie("ptd_session", "falso.token.123")
    assert web.get("/api/hub/leads").status_code == 401


def test_cambios_con_cookie_exigen_csrf(web):
    entrar(web)
    assert web.post("/api/hub/leads/51999000111/comando", json={"comando": "pausa"}).status_code == 403


def test_app_sirve_la_web_con_cabeceras_seguras(web):
    r = web.get("/app")
    assert r.status_code in (200, 404)
    if r.status_code == 200:
        assert r.headers["X-Frame-Options"] == "DENY"


# ---------- Aislamiento por tenant ----------
def test_cada_cliente_ve_solo_sus_leads_y_mensajes(web):
    entrar(web)
    ids = {l["sender_id"] for l in web.get("/api/hub/leads").get_json()}
    assert ids == {"twa:+13055551234", "51999000111", "51999000222"}
    assert web.get("/api/hub/leads/51888000999/mensajes").status_code == 404        # lead de otro tenant
    entrar(web, "max@north.com", "clave-segura-3")
    assert [l["sender_id"] for l in web.get("/api/hub/leads").get_json()] == ["51888000999"]
    assert [c["name_es"] for c in web.get("/api/hub/catalogo").get_json()] == ["Plan Premium"]


def test_no_se_puede_editar_producto_de_otro_tenant(web):
    entrar(web, "max@north.com", "clave-segura-3")
    r = web.put("/api/hub/catalogo/11111111-1111-1111-1111-111111111111", headers=CSRF, json={"list_price": 1})
    assert r.status_code == 404


def test_tenant_no_se_hereda_entre_peticiones(web):
    entrar(web)
    web.get("/api/hub/leads")
    assert tenant.tid() == hub_api.tenant.tid() and tenant._ACTUAL.get() is None


# ---------- Kanban, conversación y comandos ----------
def test_kanban_cinco_columnas_y_alertas(web):
    entrar(web)
    por_id = {l["sender_id"]: l for l in web.get("/api/hub/leads").get_json()}
    assert por_id["51999000222"]["columna"] == "capturado"
    assert por_id["51999000111"]["columna"] == "cierre_alerta" and por_id["51999000111"]["alerta"] == "objecion_3"
    assert por_id["twa:+13055551234"]["columna"] == "cierre_alerta" and por_id["twa:+13055551234"]["alerta"] == "dia_10_llamar"
    assert por_id["twa:+13055551234"]["telefono"] == "+13055551234"


def test_conversacion_con_motor_y_origen(web):
    entrar(web)
    m = web.get("/api/hub/leads/51999000111/mensajes").get_json()
    assert [x["origen"] for x in m] == ["cliente", "bot", "asesor"]
    assert m[1]["motor"] == "NLU · Objeciones 3/3" and m[2]["motor"] == "Asesor (manual)"


def test_mensaje_manual_se_envia_y_pausa_el_bot(web, sb):
    entrar(web, "leo@smile.com", "clave-segura-2")
    with mock.patch.object(hub_api, "send_wa_text", return_value=True) as envio, mock.patch("bot.handoff.ya_procesado", return_value=False), \
         mock.patch("bot.handoff.safe_upsert_lead") as up:
        r = web.post("/api/hub/leads/51999000222/comando", headers=CSRF, json={"mensaje": "Hola, soy la Dra. Kim 😊"})
    assert r.status_code == 200 and r.get_json()["pausa_min"] > 0
    assert envio.call_args[0] == ("51999000222", "Hola, soy la Dra. Kim 😊")
    nuevo = [x for x in sb.tablas["mensajes"] if x["contenido"].startswith("Hola, soy")][0]
    assert nuevo["tenant_id"] == "demo-dental" and nuevo["motor"] == "Asesor (manual)" and nuevo["canal"] == "web_manual"
    assert "ts_ultimo_manual" in up.call_args[0][4]


def test_comandos_validos(web):
    entrar(web, "leo@smile.com", "clave-segura-2")
    with mock.patch.object(hub_api, "procesar_comando_asesor", return_value="✅ Listo") as cmd, mock.patch.object(hub_api, "sincronizar_seguro"):
        r = web.post("/api/hub/leads/twa:+13055551234/comando", headers=CSRF, json={"comando": "vino"})
    assert r.get_json()["ok"] and cmd.call_args[0][0] == "vino 13055551234"
    assert web.post("/api/hub/leads/51999000111/comando", headers=CSRF, json={"comando": "borrar todo"}).status_code == 400


# ---------- Catálogo ----------
def test_crear_editar_borrar_producto(web, sb):
    entrar(web)
    r = web.post("/api/hub/catalogo", headers=CSRF, json={
        "name_es": "Alineadores", "name_en": "Aligners", "list_price": 4800, "cash_price": 4200, "qualification_mode": "seguro_medico",
        "filter_questions": [{"es": "¿Tienes seguro dental?", "en": "Do you have dental insurance?"}], "conditions_es": "Mayores de 16",
        "keywords": "aligners, invisalign", "tenant_id": "demo-b2b", "id": "hack"})
    assert r.status_code == 201
    item = r.get_json()
    assert item["tenant_id"] == "demo-dental" and item["id"] != "hack" and item["keywords"] == ["aligners", "invisalign"]
    r = web.put(f"/api/hub/catalogo/{item['id']}", headers=CSRF, json={"cash_price": 3999, "qualification_mode": "b2b"})
    assert r.status_code == 200 and r.get_json()["cash_price"] == 3999
    assert web.delete(f"/api/hub/catalogo/{item['id']}", headers=CSRF).status_code == 200
    assert not [i for i in sb.tablas["catalog_items"] if i["id"] == item["id"]]


@pytest.mark.parametrize("datos,error", [({"name_es": "X"}, "list_price"), ({"name_es": "X", "list_price": 10, "cash_price": 20}, "contado"),
                                         ({"name_es": "X", "list_price": 10, "qualification_mode": "magia"}, "qualification_mode"),
                                         ({"name_es": "X", "list_price": "diez"}, "número")])
def test_validacion_de_producto(web, datos, error):
    entrar(web)
    r = web.post("/api/hub/catalogo", headers=CSRF, json=datos)
    assert r.status_code == 400 and error in r.get_json()["error"]


def test_asesor_no_edita_catalogo(web):
    entrar(web, "leo@smile.com", "clave-segura-2")
    assert web.post("/api/hub/catalogo", headers=CSRF, json={"name_es": "X", "list_price": 1}).status_code == 403


def test_subir_archivo_con_rol(web, sb):
    import io
    entrar(web)
    item = "11111111-1111-1111-1111-111111111111"
    r = web.post(f"/api/hub/catalogo/{item}/media", headers=CSRF, content_type="multipart/form-data",
                 data={"role": "PROOF_RESULTS", "caption_en": "Before & after", "file": (io.BytesIO(PNG), "caso.png", "image/png")})
    assert r.status_code == 201, r.get_json()
    m = r.get_json()
    assert m["trigger_moment"] == "PROOF_RESULTS" and m["media_type"] == "image" and m["tenant_id"] == "demo-dental"
    assert "/object/public/catalogo/demo-dental/" in m["file_url"] and len(sb.archivos) == 1
    assert web.get("/api/hub/catalogo").get_json()[0]["media"][0]["id"] == m["id"]
    assert web.delete(f"/api/hub/catalogo/{item}/media/{m['id']}", headers=CSRF).status_code == 200 and not sb.archivos


@pytest.mark.parametrize("rol,archivo,mime,error", [("HACK", PNG, "image/png", "role"), ("FIRST_INFO", b"<html>", "image/png", "contenido"),
                                                    ("SPECS_PDF", b"%PDF-1.4", "text/html", "formato")])
def test_subida_rechaza_rol_tipo_o_contenido_falso(web, rol, archivo, mime, error):
    import io
    entrar(web)
    r = web.post("/api/hub/catalogo/11111111-1111-1111-1111-111111111111/media", headers=CSRF, content_type="multipart/form-data",
                 data={"role": rol, "file": (io.BytesIO(archivo), "x", mime)})
    assert r.status_code == 400 and error in r.get_json()["error"]


# ---------- Playbook / ajustes ----------
def test_playbook_guarda_owner_horarios_silencio_y_frases(web, sb):
    entrar(web)
    r = web.put("/api/hub/playbook", headers=CSRF, json={
        "owner_whatsapp": "+1 (305) 555-9999", "visiting_hours": {"inicio": "10:00", "fin": "17:00", "dias": ["lun", "mie", "vie"]},
        "quiet_hours": {"start": "21:00", "end": "08:00"}, "forbidden_phrases": "remate\ngarantizado",
        "seguimiento": {"en": {"post_dia5": "Custom day 5 for {producto}"}}})
    assert r.status_code == 200, r.get_json()
    v = r.get_json()
    assert v["owner_whatsapp"] == "13055559999" and v["quiet_hours"] == {"start": "21:00", "end": "08:00"}
    assert v["visiting_hours"]["dias"] == ["lun", "mie", "vie"] and v["forbidden_phrases"] == ["remate", "garantizado"]
    assert v["seguimiento"]["en"]["post_dia5"] == "Custom day 5 for {producto}"
    assert "evaluation" in v["seguimiento"]["en"]["rescate_general"]          # plantilla de salud por defecto
    pb = sb.tablas["tenant_playbooks"][0]
    assert pb["tenant_id"] == "demo-dental" and pb["playbook"]["agenda"]["horario_visitas"]["inicio"] == "10:00"


@pytest.mark.parametrize("datos,error", [({"owner_whatsapp": "123"}, "owner_whatsapp"), ({"quiet_hours": {"start": "25:00", "end": "08:00"}}, "quiet_hours"),
                                         ({"visiting_hours": {"inicio": "18:00", "fin": "09:00", "dias": ["lun"]}}, "visiting_hours"),
                                         ({"seguimiento": {"es": {"inyectar": "x"}}}, "clave desconocida"),
                                         ({"crm_field_mapping": {"catalog": {"object": "Product2; DELETE"}}}, "no válido")])
def test_playbook_valida(web, datos, error):
    entrar(web)
    r = web.put("/api/hub/playbook", headers=CSRF, json=datos)
    assert r.status_code == 400 and error in r.get_json()["error"]


def test_mapeo_crm_se_guarda_y_se_ve_efectivo(web, sb):
    entrar(web, "max@north.com", "clave-segura-3")
    r = web.put("/api/hub/playbook", headers=CSRF, json={"crm_field_mapping": {
        "catalog": {"object": "Property__c", "fields": {"name_es": "Name", "list_price": "Price__c", "cash_price": "Cash__c"}},
        "lead": {"fields": {"presupuesto": "Budget__c", "pago": "Payment_Method__c"}}}})
    assert r.status_code == 200, r.get_json()
    m = r.get_json()["crm_field_mapping"]
    assert m["catalog"]["object"] == "Property__c" and m["catalog"]["active_field"] == "IsActive" and m["lead"]["object"] == "Lead"
    assert m["lead"]["fields"]["presupuesto"] == "Budget__c"


# ---------- Acceso de máquina y chat simulado ----------
def test_api_key_exige_tenant(web):
    assert web.get("/api/hub/leads", headers={"X-Hub-Key": "k-123"}).status_code == 401
    assert web.get("/api/hub/leads", headers={"X-Hub-Key": "otra", "X-Tenant-Id": "demo-dental"}).status_code == 401
    assert len(web.get("/api/hub/leads", headers={"X-Hub-Key": "k-123", "X-Tenant-Id": "demo-dental"}).get_json()) == 3


def test_chat_simulado_no_sale_por_whatsapp(web, mundo):  # noqa: F811
    H = {"X-Hub-Key": "k-123", "X-Tenant-Id": "demo-dental"}
    with mock.patch.object(hub_api.tenant, "modo_catalogo", return_value=True), mock.patch.object(hub_api, "sincronizar_seguro"), \
         mock.patch.object(hub_api, "get_lead_by_sender_or_phone", lambda s, t=None: mundo["leads"].get(s)):
        from bot import agente
        from bot.canales import whatsapp
        with mock.patch.object(agente, "send_wa_text", whatsapp.send_wa_text), mock.patch.object(agente, "send_wa_media", whatsapp.send_wa_media):
            r = web.post("/api/hub/chat", headers=H, json={"sender_id": "hub:+19995550001", "texto": "ta salado tngo 25 mil nomas"})
    d = r.get_json()
    assert r.status_code == 200 and "US$" in d["reply"] and d["nlu"]["entities"]["budget_amount"] == 25000
    assert d["media"] and d["alertas"] and d["lead"]["stage"] == "qualified" and mundo["textos"] == []
    assert web.post("/api/hub/chat", headers=H, json={"sender_id": "51999", "texto": "hola"}).status_code == 400


def test_cors_solo_para_origen_permitido(web):
    with mock.patch.object(hub_api, "HUB_CORS_ORIGINS", ["https://hub.peruptd.com"]):
        r = web.options("/api/hub/leads", headers={"Origin": "https://hub.peruptd.com"})
        assert r.headers["Access-Control-Allow-Origin"] == "https://hub.peruptd.com" and r.headers["Access-Control-Allow-Credentials"] == "true"
        assert "Access-Control-Allow-Origin" not in web.options("/api/hub/leads", headers={"Origin": "https://malo.example"}).headers
