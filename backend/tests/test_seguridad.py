"""Seguridad del webhook: firma X-Hub-Signature-256 de Meta y versión única de la Graph API."""
import hashlib
import hmac
import json
import pathlib
import unittest
from unittest import mock

import simulador  # noqa: F401  (prepara el entorno antes de importar bot)

from bot.utils.firma_meta import firma_valida  # noqa: E402

SECRETO = "secreto-de-prueba"


def _firma(cuerpo, secreto=SECRETO):
    return "sha256=" + hmac.new(secreto.encode(), cuerpo, hashlib.sha256).hexdigest()


class FirmaMeta(unittest.TestCase):
    def test_firma_correcta_e_incorrecta(self):
        cuerpo = b'{"object":"page"}'
        self.assertTrue(firma_valida(cuerpo, _firma(cuerpo), [SECRETO]))
        self.assertTrue(firma_valida(cuerpo, _firma(cuerpo), ["otro", SECRETO]))
        self.assertFalse(firma_valida(cuerpo, _firma(cuerpo, "otro"), [SECRETO]))
        self.assertFalse(firma_valida(cuerpo, "", [SECRETO]))
        self.assertFalse(firma_valida(cuerpo + b" ", _firma(cuerpo), [SECRETO]))

    def _post(self, secretos, exigir, firma):
        import bot.rutas.webhook as wh
        from bot.app import app
        cuerpo = json.dumps({"object": "otro"}).encode()
        cab = {"Content-Type": "application/json"}
        if firma:
            cab["X-Hub-Signature-256"] = _firma(cuerpo, firma)
        with mock.patch.object(wh, "META_APP_SECRETS", secretos), mock.patch.object(wh, "FIRMA_META_EXIGIR", exigir):
            return app.test_client().post("/webhook", data=cuerpo, headers=cab).status_code

    def test_sin_secreto_no_cambia_nada(self):
        self.assertNotEqual(self._post([], False, None), 403)

    def test_modo_observacion_deja_pasar(self):
        self.assertNotEqual(self._post([SECRETO], False, "falsa"), 403)

    def test_exigir_rechaza_falsa_y_acepta_buena(self):
        self.assertEqual(self._post([SECRETO], True, "falsa"), 403)
        self.assertEqual(self._post([SECRETO], True, None), 403)
        self.assertNotEqual(self._post([SECRETO], True, SECRETO), 403)

    def test_verificacion_get_no_exige_firma(self):
        import bot.rutas.webhook as wh
        from bot.app import app
        with mock.patch.object(wh, "META_APP_SECRETS", [SECRETO]), mock.patch.object(wh, "FIRMA_META_EXIGIR", True):
            r = app.test_client().get("/webhook?hub.mode=subscribe&hub.verify_token=x&hub.challenge=1")
        self.assertNotEqual(r.status_code, 500)


class GraphApiCentralizada(unittest.TestCase):
    def test_version_solo_en_config(self):
        for f in pathlib.Path("bot").rglob("*.py"):
            if f.name != "config.py":
                self.assertNotIn("graph.facebook.com/v", f.read_text(encoding="utf-8"), f"{f}: usa GRAPH_URL de bot/config.py")


class CronProtegido(unittest.TestCase):
    def _get(self, clave_cfg, url, cab=None):
        import bot.rutas.cron as cron
        from bot.app import app
        with mock.patch.object(cron, "CRON_KEY", clave_cfg), mock.patch.object(cron, "ejecutar_seguimientos", lambda: {}):
            return app.test_client().get(url, headers=cab or {}).status_code

    def test_clave_en_cabecera_aunque_la_url_traiga_otra(self):
        self.assertEqual(self._get("k1", "/cron?key=vieja", {"X-Cron-Key": "k1"}), 200)

    def test_sin_clave_correcta_no_entra(self):
        self.assertEqual(self._get("k1", "/cron?key=vieja", {"User-Agent": "Google-Cloud-Scheduler"}), 403)

    def test_sin_cron_key_sigue_como_antes(self):
        self.assertEqual(self._get("", "/cron", {"User-Agent": "Google-Cloud-Scheduler"}), 200)
