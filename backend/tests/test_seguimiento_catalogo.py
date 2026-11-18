"""Seguimiento en modo 'catalogo': plantillas del playbook (ES/EN), interruptores y flujos con la hora congelada.
SAGUE ('sague_legacy') sigue por su motor original."""
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import pytest

from bot import playbooks
from bot.seguimiento import motor, motor_catalogo, plantillas
from tests.test_agente_extremo import ITEM

CARPETA = Path(__file__).resolve().parent.parent / "playbooks"
AHORA = datetime(2026, 11, 20, 15, 0, tzinfo=timezone.utc)   # 10:00 en Lima: horario prudente
VARS = {"coma": ", Ana", "nombre": "Ana", "empresa": "X", "asesor": "Y", "producto": "Casa A", "direccion": "Calle 1", "mapa": "m",
        "evento": "visita", "cuando": "mañana", "fecha": "Sáb 21 nov · 10:00 a. m.", "bono": "bono", "valor": "valor",
        "horarios": "1️⃣ a\n2️⃣ b", "presupuesto": "US$25,000", "cuota": "US$983/mes", "telefono": "51999", "pago": "CASH"}
ITEM_SEG = dict(ITEM, media=ITEM["media"] + [{"id": "aaaaaaaa-0000-0000-0000-000000000009", "trigger_moment": "POST_VISIT_45M",
                                              "media_type": "pdf", "file_url": "https://cdn/resumen.pdf", "caption_es": "Resumen"}])


@pytest.mark.parametrize("nombre", sorted(p.name for p in CARPETA.glob("playbook_*.json")))
def test_plantillas_del_playbook_usan_solo_variables_conocidas(nombre):
    seg = json.loads((CARPETA / nombre).read_text(encoding="utf-8")).get("seguimiento") or {}
    for idioma, textos in seg.items():
        assert idioma in ("es", "en")
        for clave, texto in textos.items():
            assert clave in plantillas.DEFECTO["es"], f"{nombre}: clave desconocida {clave}"
            for var in re.findall(r"\{(\w+)\}", texto):
                assert var in VARS, f"{nombre} {idioma}.{clave}: variable {{{var}}} no existe"


def test_defectos_completos_y_sin_llaves_sueltas():
    assert set(plantillas.DEFECTO["es"]) == set(plantillas.DEFECTO["en"])
    with mock.patch.object(playbooks, "actual", return_value={}):
        for idioma in ("es", "en"):
            for clave in plantillas.DEFECTO[idioma]:
                t = plantillas.texto(clave, idioma, VARS)
                assert t and "{" not in t, (idioma, clave)
        assert plantillas.texto("post_dia10", "fr", VARS).startswith("¡Hola, Ana!")       # idioma desconocido -> ES


def test_playbook_manda_y_falta_usa_defecto():
    pb = {"seguimiento": {"en": {"post_45m": "Custom {producto}"}}, "interruptores": {"seguimiento_post_dia5": False}}
    with mock.patch.object(playbooks, "actual", return_value=pb):
        assert plantillas.texto("post_45m", "en", VARS) == "Custom Casa A"
        assert plantillas.texto("post_dia14", "en", VARS).startswith("Hi, Ana,")
        assert not plantillas.activo("post_dia5") and plantillas.activo("post_dia10")


@pytest.fixture
def entorno():
    enviados, medias, alertas, guardados = [], [], [], {}
    pb = json.loads((CARPETA / "playbook_us_realestate.json").read_text(encoding="utf-8"))
    tenant = {"name": "Maple Ridge Residences", "advisor_name": "Daniel", "default_language": "en", "pipeline_mode": "catalogo", "owner_whatsapp": "15550000000"}

    def libres(n=3, dia=None, filtro=None, excluir=None):
        base = (AHORA + timedelta(days=1)).astimezone(motor_catalogo.LIMA_TZ)
        return [base.replace(hour=h, minute=0, second=0, microsecond=0) for h in (10, 11, 16)][:n]
    parches = [mock.patch.object(motor_catalogo, "_ahora", return_value=AHORA), mock.patch("bot.seguimiento.envio._ahora", return_value=AHORA),
               mock.patch.object(motor_catalogo.tenant, "actual", return_value=tenant), mock.patch.object(playbooks, "actual", return_value=pb),
               mock.patch.object(motor_catalogo.catalogo, "items", return_value=[ITEM_SEG]),
               mock.patch.object(motor_catalogo, "send_wa_text", lambda d, t: enviados.append((d, t)) or True),
               mock.patch("bot.seguimiento.envio.send_wa_text", lambda d, t: enviados.append((d, t)) or True),
               mock.patch.object(motor_catalogo, "send_wa_media", lambda d, u, ti, c: medias.append(u) or True),
               mock.patch.object(motor_catalogo, "alertar_asesor", lambda t, d=None: alertas.append(t)), mock.patch("bot.seguimiento.envio.alertar_asesor", alertas.append),
               mock.patch.object(motor_catalogo, "libres_en_horario", libres), mock.patch.object(motor_catalogo, "en_silencio", return_value=False), mock.patch.object(motor_catalogo, "sincronizar_seguro"),
               mock.patch.object(motor_catalogo, "safe_upsert_lead", lambda s, c, n, t, meta, u: guardados.update({s: meta})),
               mock.patch("bot.seguimiento.envio.supabase", None), mock.patch.object(motor_catalogo, "_guardar_historial")]
    for p in parches:
        p.start()
    yield {"enviados": enviados, "medias": medias, "alertas": alertas, "guardados": guardados}
    for p in reversed(parches):
        p.stop()


def _lead(sender, **meta):
    base = {"preferred_language": "en", "interested_catalog_item_id": ITEM_SEG["id"], "ts_ultimo_cliente": (AHORA - timedelta(hours=1)).isoformat()}
    return {"sender_id": sender, "telefono": sender, "nombre": "Jessica Miller", "canal": "whatsapp", "interes": json.dumps({**base, **meta})}


def test_protocolo_post_visita_en_ingles_con_media_del_catalogo(entorno):
    cita = AHORA - timedelta(hours=2)
    lead = _lead("sms:+15125550148", cita_agendada=True, fecha_cita=cita.isoformat(), visita_estado="realizada",
                 ts_visita_confirmada=(AHORA - timedelta(minutes=50)).isoformat())
    assert motor_catalogo.procesar(lead) == "post-visita post_45m (enviado)"
    destino, texto = entorno["enviados"][-1]
    assert destino == "sms:+15125550148" and texto.startswith("Thanks for touring Maple Ridge today, Jessica!")
    assert entorno["medias"] == ["https://cdn/resumen.pdf"]
    meta = entorno["guardados"]["sms:+15125550148"]
    assert meta["post_visita"]["enviados"] == ["post_45m"] and "aaaaaaaa-0000-0000-0000-000000000009" in meta["sent_media_ids"]


def test_dia10_alerta_al_asesor_y_dia14_cierra(entorno):
    cita = AHORA - timedelta(days=10, hours=1)
    pv = {"cita": cita.isoformat(), "enviados": ["post_45m", "post_48h", "post_dia5"]}
    lead = _lead("15125550148", cita_agendada=True, fecha_cita=cita.isoformat(), visita_estado="realizada", post_visita=pv,
                 ts_ultimo_cliente=(AHORA - timedelta(days=9)).isoformat())
    assert motor_catalogo.procesar(lead).startswith("post-visita post_dia10")
    assert any("day 10 after the visit for Jessica Miller" in a for a in entorno["alertas"])
    pv["enviados"].append("post_dia10")
    lead = _lead("15125550148", cita_agendada=True, fecha_cita=(AHORA - timedelta(days=14, hours=1)).isoformat(), visita_estado="realizada",
                 post_visita=dict(pv, cita=(AHORA - timedelta(days=14, hours=1)).isoformat()), ts_ultimo_cliente=(AHORA - timedelta(days=13)).isoformat())
    motor_catalogo.procesar(lead)


def test_no_asistio_ofrece_horarios_que_se_pueden_elegir(entorno):
    cita = AHORA - timedelta(hours=3)
    motor_catalogo.procesar(_lead("15125550149", cita_agendada=True, fecha_cita=cita.isoformat(), visita_estado="no_asistio"))
    assert "We missed you" in entorno["enviados"][-1][1] and "1️⃣" in entorno["enviados"][-1][1]
    meta = entorno["guardados"]["15125550149"]
    assert len(meta["offered_slots"]) == 3 and meta["cita_agendada"] is False and meta["rescate_no_asistio"]


def test_rescate_24h_por_objecion_en_espanol(entorno):
    ult = AHORA - timedelta(hours=8)
    lead = _lead("51999888777", preferred_language="es", price_objection_count=1, ts_ultimo_cliente=ult.isoformat(),
                 ts_ultimo_bot=(ult + timedelta(minutes=1)).isoformat(), ultimo_texto_cliente="ta caro")
    assert motor_catalogo.procesar(lead) == "rescate 24h (rescate_objecion)"
    assert entorno["enviados"][-1][1].startswith("¡Hola, Jessica! 😊 Me quedé pensando en lo del precio")


def test_interruptor_apagado_salta_el_toque(entorno):
    cita = AHORA - timedelta(days=5, hours=1)
    with mock.patch.object(plantillas, "activo", lambda clave: clave != "post_dia5"):
        r = motor_catalogo.procesar(_lead("15125550150", cita_agendada=True, fecha_cita=cita.isoformat(), visita_estado="realizada",
                                          post_visita={"cita": cita.isoformat(), "enviados": ["post_45m", "post_48h"]},
                                          ts_ultimo_cliente=(AHORA - timedelta(days=4)).isoformat()))
    assert r is None and "post_dia5" in entorno["guardados"]["15125550150"]["post_visita"]["enviados"]


def test_sague_legacy_no_usa_el_motor_nuevo():
    with mock.patch.object(motor.tenant, "modo_catalogo", return_value=False), \
         mock.patch.object(motor.motor_catalogo, "procesar") as nuevo:
        motor._procesar_lead_seguimiento({"sender_id": "51", "interes": json.dumps({"no_interesado": True})})
    nuevo.assert_not_called()


@pytest.mark.parametrize("industria,idioma,palabra", [("realestate", "es", "planos"), ("realestate", "en", "floor plans"),
                                                     ("dental", "es", "evaluación"), ("medspa", "en", "consultation"),
                                                     ("b2b", "es", "propuesta"), ("b2b", "en", "proposal")])
def test_plantillas_por_industria(industria, idioma, palabra):
    from bot.seguimiento import plantillas_industria
    with mock.patch.object(playbooks, "actual", return_value={}), \
         mock.patch.object(plantillas.tenant, "actual", return_value={"industry": industria}):
        t = plantillas.texto("post_45m", idioma, VARS)
        assert palabra in t and "{" not in t
        for clave in plantillas.CLAVES_EDITABLES:
            assert "{" not in plantillas.texto(clave, idioma, VARS), clave
    for fam in plantillas_industria.POR_INDUSTRIA.values():
        for idi, textos in fam.items():
            for clave, texto in textos.items():
                assert clave in plantillas.DEFECTO["es"]
                assert set(re.findall(r"\{(\w+)\}", texto)) <= set(VARS) | {"pago", "telefono"}, (idi, clave)


def test_playbook_manda_sobre_la_industria_y_otra_industria_usa_neutro():
    with mock.patch.object(playbooks, "actual", return_value={"seguimiento": {"es": {"post_45m": "Propio {producto}"}}}), \
         mock.patch.object(plantillas.tenant, "actual", return_value={"industry": "dental"}):
        assert plantillas.texto("post_45m", "es", VARS) == "Propio Casa A"
    with mock.patch.object(playbooks, "actual", return_value={}), mock.patch.object(plantillas.tenant, "actual", return_value={"industry": "autos"}):
        assert plantillas.texto_crudo("post_45m", "es") == plantillas.DEFECTO["es"]["post_45m"]
