"""Pruebas de humo: la app arranca y las funciones puras clave se comportan como se espera.
Corren sin credenciales (Supabase y Gemini quedan desactivados)."""
import os

os.environ.pop("SUPABASE_KEY", None)
os.environ.pop("GEMINI_API_KEY", None)
os.environ["TIPO_CAMBIO_AUTO"] = "false"  # sin red en las pruebas: tipo de cambio fijo de respaldo (3.45)
os.environ["VISITAS_DESDE"] = ""  # sin fecha de apertura en las pruebas (se prueba aparte con mock)

from bot.app import app  # noqa: E402
from bot.nlp.parser_fechas import parse_fecha_hora_es  # noqa: E402
from bot.utils.telefono import normalize_pe_phone  # noqa: E402


def test_rutas_registradas():
    rutas = {r.rule for r in app.url_map.iter_rules()}
    assert {"/", "/webhook", "/cron", "/cron/seguimiento", "/reloj", "/diagnostico/media"} <= rutas


def test_health():
    assert app.test_client().get("/").status_code == 200


def test_verificacion_webhook_rechaza_token_incorrecto():
    r = app.test_client().get("/webhook?hub.mode=subscribe&hub.verify_token=malo&hub.challenge=1")
    assert r.status_code == 403


def test_normaliza_telefono_peru():
    assert normalize_pe_phone("987 654 321") == "51987654321"
    assert normalize_pe_phone("+51 987654321") == "51987654321"
    assert normalize_pe_phone("123") is None


def test_parser_fecha_detecta_hora():
    fh = parse_fecha_hora_es("el sábado a las 4 pm")
    assert fh.get("hora") is not None
