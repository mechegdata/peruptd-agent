"""Turno completo del agente en modo catálogo (WhatsApp y SMS), con Supabase, calendario y envío simulados."""
import json
from datetime import datetime, timedelta
from unittest import mock

import pytest

from bot import agente
from bot.config import LIMA_TZ
from tests.test_motores_catalogo import CASA

ITEM = dict(CASA, id="11111111-2222-3333-4444-555555555555",
            media=[{"id": "aaaaaaaa-0000-0000-0000-000000000001", "trigger_moment": "FIRST_INFO", "media_type": "image", "file_url": "https://cdn/x1.jpg", "caption_es": "Fachada"},
                   {"id": "aaaaaaaa-0000-0000-0000-000000000004", "trigger_moment": "PRICE_OBJECTION", "media_type": "image", "file_url": "https://cdn/x4.jpg", "caption_es": "Cochera"},
                   {"id": "aaaaaaaa-0000-0000-0000-000000000005", "trigger_moment": "LOCATION_FACADE", "media_type": "image", "file_url": "https://cdn/x5.jpg"}])
TENANT = {"id": "demo", "name": "Santa Teresa Homes", "bot_name": "Ava", "advisor_name": "Henry", "address": "Urb. Santa Teresa", "pipeline_mode": "catalogo",
          "default_language": "es", "crm_type": "peruptd_native"}


@pytest.fixture
def mundo():
    leads, textos, medias, alertas, eventos = {}, [], [], [], []
    manana = (datetime.now(LIMA_TZ) + timedelta(days=1)).date()

    def libres(n=3, dia=None, filtro=None, excluir=None):
        dias = [dia] if dia else [manana + timedelta(days=i) for i in range(4)]
        out = [datetime(d.year, d.month, d.day, h, tzinfo=LIMA_TZ) for d in dias for h in range(9, 21)]
        return [d for d in out if (not filtro or filtro(d)) and d.isoformat() not in (excluir or [])][:n]

    def upsert(sender, canal, nombre=None, telefono=None, cambios=None, ultimo=""):
        lead = leads.setdefault(sender, {"sender_id": sender, "canal": canal, "nombre": nombre, "telefono": telefono or sender, "interes": "{}"})
        meta = json.loads(lead["interes"])
        meta.update({k: v for k, v in (cambios or {}).items() if v is not None})
        lead["interes"] = json.dumps(meta)

    parches = [mock.patch.object(agente.catalogo, "items", return_value=[ITEM]), mock.patch.object(agente.tenant, "actual", return_value=TENANT),
               mock.patch.object(agente, "get_lead_by_sender_or_phone", lambda s, t=None: leads.get(s)), mock.patch.object(agente, "safe_upsert_lead", upsert),
               mock.patch.object(agente, "send_wa_text", lambda d, t: textos.append((d, t)) or True),
               mock.patch.object(agente, "send_wa_media", lambda d, u, tipo, c: medias.append((d, u)) or True),
               mock.patch.object(agente, "alertar_asesor", alertas.append), mock.patch.object(agente, "get_free_slots", libres),
               mock.patch.object(agente, "create_calendar_event", lambda *a, **k: eventos.append((a, k)) or (True, "ok", "EV1")),
               mock.patch.object(agente, "supabase", None), mock.patch.object(agente.NORMALIZADOR, "usar_llm", False),
               mock.patch.object(agente.playbooks, "valor", lambda ruta, defecto=None: ["remate"] if ruta == "frases_prohibidas" else defecto)]
    for p in parches:
        p.start()
    yield {"leads": leads, "textos": textos, "medias": medias, "alertas": alertas, "eventos": eventos}
    for p in parches:
        p.stop()


def test_whatsapp_con_jerga_hasta_la_cita(mundo):
    r = agente.atender_turno("51999888777", "ola q tal\na cuanto sale la ksa al cntado??\nta medio salado ah tngo 25 mil nomas\n"
                                            "se podra ver mñn saliendo de la chamba tipo 6 y media?", "Lucía")
    texto = mundo["textos"][-1][1]
    assert "US$129,000" in texto and "US$983/mes" in texto and "1️⃣" in texto
    assert [u for _, u in mundo["medias"]] == ["https://cdn/x4.jpg", "https://cdn/x1.jpg"]
    assert mundo["alertas"] and "1/3" in mundo["alertas"][0]
    meta = json.loads(mundo["leads"]["51999888777"]["interes"])
    assert meta["stage"] == "qualified" and meta["stated_budget"] == 25000 and len(meta["offered_slots"]) == 3
    assert len(meta["sent_media_ids"]) == 2 and meta["nlu_ultimo"]["source"] == "lexicon"
    assert r.cambios["price_objection_count"] == 1

    agente.atender_turno("51999888777", "1", "Lucía")
    meta = json.loads(mundo["leads"]["51999888777"]["interes"])
    assert meta["cita_agendada"] and meta["evento_id"] == "EV1" and meta["fecha_cita"] == meta.get("fecha_cita")
    assert "¡Listo! ✅ Agendé tu visita" in mundo["textos"][-1][1]
    assert mundo["eventos"][0][1]["titulo"].startswith("Visita - ") and mundo["medias"][-1][1] == "https://cdn/x5.jpg"
    assert any("agendada" in a for a in mundo["alertas"])


def test_sms_en_ingles(mundo):
    agente.atender_turno("sms:+15125550148", "yo hm for the 3br unit? ngl sounds steep, only got 25k down", "", "SMS (Twilio)")
    destino, texto = mundo["textos"][-1]
    assert destino == "sms:+15125550148" and "Hi! I'm Ava" in texto and "$983/mo" in texto
    meta = json.loads(mundo["leads"]["sms:+15125550148"]["interes"])
    assert meta["preferred_language"] == "en" and meta["canal_origen"] == "SMS (Twilio)"


def test_no_repite_ni_usa_frases_prohibidas(mundo):
    with mock.patch.object(agente, "_historial", lambda s, n=8: [{"rol": "assistant", "texto": "Es normal comparar 🙂 A US$645/m² estás 22% bajo el promedio."}]):
        agente.atender_turno("51911", "ta caro", "")
    assert "Es normal comparar" not in mundo["textos"][-1][1] or len(mundo["textos"][-1][1].split("\n\n")) == 1
