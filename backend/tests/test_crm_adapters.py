"""Adaptadores multi-CRM (con un HTTP falso), sincronización genérica del lead y canal Twilio."""
import base64
import hashlib
import hmac
import json
from datetime import datetime, timezone
from unittest import mock

import pytest

from bot import crm, tenant
from bot.canales import twilio_adapter
from bot.crm_adapters import adaptador
from bot.crm_adapters.base import trigger_por_nombre, tipo_por_nombre


class Resp:
    def __init__(self, data, status=200):
        self._d, self.status_code, self.text, self.content = data, status, json.dumps(data), b"bin"

    def json(self):
        return self._d


class HttpFalso:
    """Responde según (método, fragmento de URL). Guarda cada llamada."""
    def __init__(self, rutas):
        self.rutas, self.llamadas = rutas, []

    def request(self, metodo, url, **kw):
        self.llamadas.append((metodo, url, kw))
        for (m, frag), resp in self.rutas.items():
            if m == metodo and frag in url:
                return resp(kw) if callable(resp) else resp
        return Resp({}, 404)

    def post(self, url, **kw):
        return self.request("POST", url, **kw)


FICHA = {"sender_id": "51999", "nombre": "Lucía Paredes", "telefono": "+51 999 111 222", "etapa": "booked", "pago": "FINANCING",
         "presupuesto": 25000, "objeciones": 1, "idioma": "es", "canal": "WhatsApp", "producto": "Casa A", "descripcion": "x"}


def test_convencion_de_archivos_del_cliente():
    assert trigger_por_nombre("[PRICE_OBJECTION] Cochera", "image") == "PRICE_OBJECTION"
    assert trigger_por_nombre("Planos 3 niveles", tipo_por_nombre("Planos.pdf")) == "SPECS_PDF"
    assert trigger_por_nombre("Recorrido", tipo_por_nombre("tour.mp4")) == "VIDEO_TOUR"


def test_factory_por_tipo():
    assert adaptador({"crm_type": "hubspot"}).nombre == "hubspot"
    assert adaptador({"crm_type": "zoho"}).nombre == "zoho"
    assert adaptador({}).nombre == "peruptd_native"


def test_hubspot_catalogo_y_lead_nuevo():
    http = HttpFalso({
        ("GET", "/objects/products"): Resp({"results": [{"id": "77", "properties": {"name": "Plan Premium", "price": "2400", "cash__c": "2150"}},
                                                        {"id": "78", "properties": {"name": "Sin precio", "price": ""}}]}),
        ("POST", "/contacts/search"): Resp({"results": []}),
        ("POST", "/objects/contacts"): Resp({"id": "C1"}),
        ("POST", "/objects/deals"): Resp({"id": "D1"}),
    })
    hs = adaptador({"crm_type": "hubspot", "crm_credentials_json": {"token": "x"}, "crm_field_map": {"catalogo": {"cash_price": "cash__c"}}}, http)
    assert hs.listar_productos() == [{"external_crm_id": "77", "name_es": "Plan Premium", "list_price": 2400.0, "media": [], "cash_price": "2150"}]
    assert hs.sincronizar_lead(FICHA) == "C1|D1"
    deal = next(kw["json"] for m, u, kw in http.llamadas if m == "POST" and u.endswith("/deals"))
    assert deal["properties"]["dealstage"] == "presentationscheduled" and deal["properties"]["amount"] == 25000


def test_pipedrive_reusa_persona_y_crea_actividad():
    http = HttpFalso({
        ("GET", "/persons/search"): Resp({"data": {"items": [{"item": {"id": 5}}]}}),
        ("PUT", "/persons/5"): Resp({"data": {"id": 5}}),
        ("POST", "/deals"): Resp({"data": {"id": 9}}),
        ("POST", "/activities"): Resp({"data": {"id": 31}}),
    })
    pd = adaptador({"crm_type": "pipedrive", "crm_credentials_json": {"api_token": "t", "dominio": "acme"}, "crm_field_map": {"stage_ids": {"booked": 3}}}, http)
    assert pd.sincronizar_lead(FICHA) == "5|9"
    assert pd.registrar_cita("5|9", datetime(2026, 11, 18, 23, 30, tzinfo=timezone.utc), 60, "Visita") == "31"
    act = next(kw["json"] for m, u, kw in http.llamadas if u.endswith("/activities"))
    assert act["type"] == "meeting" and act["due_time"] == "23:30" and act["deal_id"] == 9
    assert all("acme.pipedrive.com" in u and kw["params"]["api_token"] == "t" for _, u, kw in http.llamadas)


def test_zoho_pide_token_y_hace_upsert_por_telefono():
    http = HttpFalso({
        ("POST", "accounts.zoho.eu/oauth/v2/token"): Resp({"access_token": "AT"}),
        ("POST", "/Leads/upsert"): Resp({"data": [{"details": {"id": "Z1"}}]}),
    })
    zo = adaptador({"crm_type": "zoho", "crm_credentials_json": {"dominio": "eu", "refresh_token": "r", "client_id": "c", "client_secret": "s"}}, http)
    assert zo.sincronizar_lead(FICHA) == "Z1"
    up = next(kw for m, u, kw in http.llamadas if u.endswith("/Leads/upsert"))
    assert up["json"]["duplicate_check_fields"] == ["Phone"] and up["headers"]["Authorization"] == "Zoho-oauthtoken AT"
    assert up["json"]["data"][0]["Lead_Status"] == "Contacted"


def test_crm_caido_no_rompe():
    http = HttpFalso({("POST", "/contacts/search"): Resp({"message": "boom"}, 500), ("POST", "/objects/contacts"): Resp({}, 500)})
    assert adaptador({"crm_type": "hubspot", "crm_credentials_json": {"token": "x"}}, http).sincronizar_lead(FICHA) is None


def test_secretos_por_referencia(monkeypatch):
    monkeypatch.setenv("HS_ACME", "secreto-real")
    assert adaptador({"crm_type": "hubspot", "crm_credentials_json": {"token_env": "HS_ACME"}}).secreto("token") == "secreto-real"


def test_sincronizacion_generica_es_idempotente():
    meta = {"payment_method": "FINANCING", "stated_budget": 25000, "price_objection_count": 1, "preferred_language": "es",
            "cita_agendada": True, "fecha_cita": "2026-11-18T18:30:00-05:00", "visita_estado": "realizada"}
    lead = {"sender_id": "51999", "nombre": "Lucía", "telefono": "51999", "canal": "whatsapp", "interes": json.dumps(meta)}
    adapt = mock.Mock(sincronizar_lead=mock.Mock(return_value="L1"), registrar_cita=mock.Mock(return_value="E1"),
                      registrar_nota=mock.Mock(return_value="N1"), marcar_asistencia=mock.Mock(return_value="E1"))
    guardado = {}

    def upsert(_s, _c, _n, _t, cambios, _u):
        guardado.update(cambios)
        meta.update(cambios)
        lead["interes"] = json.dumps(meta)
    with mock.patch.object(crm, "get_lead_by_sender_or_phone", return_value=lead), mock.patch.object(crm, "safe_upsert_lead", upsert), \
         mock.patch.object(crm, "CRM_SYNC_ACTIVO", True), mock.patch.object(tenant, "actual", return_value={"crm_type": "hubspot"}), \
         mock.patch.object(crm, "supabase", None):
        crm.sincronizar_lead("51999", adapt)
        assert guardado["crm_id"] == "L1" and guardado["crm_cita_id"] == "E1" and guardado["crm_asistencia"] == "realizada"
        assert adapt.sincronizar_lead.call_args[0][0]["etapa"] == "visited"
        crm.sincronizar_lead("51999", adapt)                          # sin cambios: no vuelve a llamar
        assert adapt.sincronizar_lead.call_count == 1 and adapt.registrar_cita.call_count == 1 and adapt.registrar_nota.call_count == 1


# ---------------- Twilio ----------------

def test_twilio_normaliza_sms_y_whatsapp():
    sms = twilio_adapter.normalizar_entrante({"From": "+15125550148", "Body": "hm for the 3br?", "MessageSid": "SM1"})
    assert sms["sender_id"] == "sms:+15125550148" and sms["canal_origen"] == "SMS (Twilio)" and sms["msg_id"] == "SM1"
    wa = twilio_adapter.normalizar_entrante({"From": "whatsapp:+15125550148", "Body": "hi", "ProfileName": "Jess"})
    assert wa["sender_id"] == "twa:+15125550148" and wa["perfil"] == "Jess"
    assert crm.telefono_visible(sms["sender_id"]) == "+15125550148"


def test_twilio_firma():
    params = {"Body": "hola", "From": "+1512"}
    with mock.patch.object(twilio_adapter, "TWILIO_AUTH_TOKEN", "tok"):
        datos = "https://bot.example/webhook/twilio" + "Bodyhola" + "From+1512"
        firma = base64.b64encode(hmac.new(b"tok", datos.encode(), hashlib.sha1).digest()).decode()
        assert twilio_adapter.firma_valida("https://bot.example/webhook/twilio", params, firma)
        assert not twilio_adapter.firma_valida("https://bot.example/webhook/twilio", {**params, "Body": "otro"}, firma)


def test_envio_por_twilio_quita_negritas_y_enruta(monkeypatch):
    from bot.canales import whatsapp
    enviados = []
    monkeypatch.setattr(twilio_adapter, "_enviar", lambda destino, datos: enviados.append((destino, datos)) or True)
    assert whatsapp.send_wa_text("sms:+15125550148", "*Casa A* — $135,000")
    assert whatsapp.send_wa_media("twa:+15125550148", "https://x/f.jpg", "image", "Fachada")
    assert enviados == [("sms:+15125550148", {"Body": "Casa A — $135,000"}), ("twa:+15125550148", {"MediaUrl": "https://x/f.jpg", "Body": "Fachada"})]
    assert twilio_adapter.sin_ventana_24h("sms:+1") and not twilio_adapter.sin_ventana_24h("twa:+1")


@pytest.fixture(autouse=True)
def _sin_cache():
    tenant.limpiar_cache()
    yield
    tenant.limpiar_cache()
