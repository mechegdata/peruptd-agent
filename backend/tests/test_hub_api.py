"""API del AI Sales Hub (modo en vivo): clave obligatoria, catálogo editable, Kanban, acciones del asesor y chat simulado."""
import json
from unittest import mock

import pytest

from bot.rutas import hub_api
from tests.test_agente_extremo import mundo  # noqa: F401  (fixture: agente con todo simulado)


@pytest.fixture
def cliente():
    from bot.app import app
    with mock.patch.object(hub_api, "HUB_API_KEY", "k-123"):
        yield app.test_client()


H = {"X-Hub-Key": "k-123"}


def test_sin_clave_o_clave_mala_es_403(cliente):
    assert cliente.get("/api/hub/estado").status_code == 403
    assert cliente.get("/api/hub/estado", headers={"X-Hub-Key": "otra"}).status_code == 403
    with mock.patch.object(hub_api, "HUB_API_KEY", ""):
        assert cliente.get("/api/hub/estado", headers={"X-Hub-Key": ""}).status_code == 403


def test_cors_solo_para_origen_permitido(cliente):
    with mock.patch.object(hub_api, "HUB_CORS_ORIGINS", ["https://hub.peruptd.com"]):
        r = cliente.options("/api/hub/estado", headers={"Origin": "https://hub.peruptd.com"})
        assert r.status_code in (200, 204) and r.headers["Access-Control-Allow-Origin"] == "https://hub.peruptd.com"
        r = cliente.options("/api/hub/estado", headers={"Origin": "https://malo.example"})
        assert "Access-Control-Allow-Origin" not in r.headers


def test_editar_catalogo_solo_campos_permitidos(cliente):
    tabla = mock.Mock()
    tabla.update.return_value.eq.return_value.eq.return_value.execute.return_value.data = [{"id": "x", "cash_price": 125000}]
    sb = mock.Mock(table=mock.Mock(return_value=tabla))
    with mock.patch.object(hub_api, "supabase", sb), mock.patch.object(hub_api.tenant, "actual", return_value={"id": "demo"}):
        r = cliente.patch("/api/hub/catalogo/x", headers=H, json={"cash_price": 125000, "tenant_id": "otro", "id": "hack"})
    assert r.status_code == 200
    enviado = tabla.update.call_args[0][0]
    assert enviado["cash_price"] == 125000 and "tenant_id" not in enviado and "id" not in enviado


def test_chat_simulado_no_sale_por_whatsapp(cliente, mundo):  # noqa: F811
    with mock.patch.object(hub_api.tenant, "modo_catalogo", return_value=True), mock.patch.object(hub_api, "sincronizar_seguro"), \
         mock.patch.object(hub_api, "get_lead_by_sender_or_phone", lambda s, t=None: mundo["leads"].get(s)), \
         mock.patch.object(hub_api, "atender_turno", wraps=hub_api.atender_turno):
        # el mundo simulado captura send_wa_text del agente; aquí lo hacemos pasar por la bandeja real del Hub
        from bot import agente
        from bot.canales import whatsapp
        with mock.patch.object(agente, "send_wa_text", whatsapp.send_wa_text), mock.patch.object(agente, "send_wa_media", whatsapp.send_wa_media):
            r = cliente.post("/api/hub/chat", headers=H, json={"sender_id": "hub:+19995550001", "texto": "ta salado tngo 25 mil nomas"})
    d = r.get_json()
    assert r.status_code == 200 and "US$" in d["reply"] and d["nlu"]["entities"]["budget_amount"] == 25000
    assert d["media"] and d["media"][0]["file_url"].startswith("https://cdn/") and d["alertas"]
    assert d["lead"]["stage"] == "qualified" and mundo["textos"] == []          # nada salió a un canal real


def test_chat_exige_sender_simulado(cliente):
    assert cliente.post("/api/hub/chat", headers=H, json={"sender_id": "51999", "texto": "hola"}).status_code == 400


def test_accion_del_asesor_y_kanban(cliente):
    meta = {"cita_agendada": True, "fecha_cita": "2026-11-10T18:00:00-05:00", "visita_estado": "realizada", "preferred_language": "en"}
    filas = [{"sender_id": "hub:+19995550001", "nombre": "Jess", "canal": "whatsapp", "interes": json.dumps(meta)}]
    sb = mock.Mock()
    sb.table.return_value.select.return_value.order.return_value.limit.return_value.execute.return_value.data = filas
    with mock.patch.object(hub_api, "supabase", sb):
        k = cliente.get("/api/hub/leads", headers=H).get_json()
    assert k[0]["stage"] == "visited" and k[0]["lang"] == "en"
    with mock.patch.object(hub_api, "procesar_comando_asesor", return_value="✅ Listo") as cmd, mock.patch.object(hub_api, "sincronizar_seguro"):
        r = cliente.post("/api/hub/leads/hub:+19995550001/accion", headers=H, json={"accion": "vino"})
    assert r.get_json()["ok"] and cmd.call_args[0][0] == "vino 19995550001"
    assert cliente.post("/api/hub/leads/x/accion", headers=H, json={"accion": "borrar todo"}).status_code == 400
