"""Chats reales del 27-28 de octubre: bienvenida duplicada, 'más tarde', vive lejos, montos en letras, plazo, seguimientos."""
import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

os.environ.pop("SUPABASE_KEY", None)
os.environ.pop("GEMINI_API_KEY", None)
os.environ["TIPO_CAMBIO_AUTO"] = "false"  # sin red en las pruebas: tipo de cambio fijo de respaldo (3.45)
os.environ["VISITAS_DESDE"] = ""  # sin fecha de apertura en las pruebas (se prueba aparte con mock)

import bot.integraciones.calendario as cal  # noqa: E402
from bot.config import LIMA_TZ  # noqa: E402
from bot.conversacion.faq import responder_faq  # noqa: E402


class ChatsReales28Oct(unittest.TestCase):
    def setUp(self):
        self.p = mock.patch.object(cal, "get_busy_intervals", lambda a, b: [])
        self.p.start()

    def tearDown(self):
        self.p.stop()

    def test_soles_por_debajo_del_techo(self):
        r = responder_faq("Son soles o dolares", "Asencio", {})
        self.assertIn("por debajo de los S/ 450,000", r)  # US$130,000 x 3.45 = S/ 448,500
        self.assertNotIn("480,000", r)
        r2 = responder_faq("Y cuanto cuesta en soles", "Asencio", {"ya_explicado": ["moneda"]})
        self.assertTrue(r2.startswith("En soles"))

    def test_monto_en_letras(self):
        from bot.conversacion.presupuesto import leer_monto
        self.assertEqual(leer_monto("cuatrocientos mil ochocientos"), (400800, "pen"))
        r = responder_faq("Cuatrocientos mil ochocientos", "", {"ya_explicado": ["moneda"]})
        self.assertIn("S/ 400,800", r)
        self.assertNotIn("sí llegamos", r)

    def test_terreno_no_es_otras_opciones(self):
        self.assertNotIn("solo tenemos", responder_faq("Cuantos m2 es el terreno", "", {}) or "")
        self.assertIn("solo tenemos", responder_faq("no venden terrenos?", "", {}))

    def test_plazo_y_solo_contado(self):
        meta = {}
        self.assertIn("5 hasta 25 años", responder_faq("En cuantos años es para pagar", "", meta))
        self.assertEqual(meta["etapa"], "ofrecio_asesor")
        self.assertIn("Puede ser al contado o con crédito", responder_faq("Osea el pago es al contado", "", {}))

    def test_vive_lejos_no_recibe_horarios(self):
        from bot.conversacion.cortesia import responder_cortesia
        meta = {"etapa": "ofrecio_horarios"}
        with mock.patch("bot.conversacion.cortesia.hay_videos", return_value=True):
            r = responder_cortesia("Yo estoy en Jaen  cuando voy los visito", meta, "José")
        self.assertIn("desde Jaen", r["reply_text"])
        self.assertNotIn("1️⃣", r["reply_text"])
        self.assertEqual(meta["etapa"], "ofrecio_video")

    def test_saludo_de_quien_ya_converso(self):
        from bot.conversacion.cortesia import responder_cortesia
        r = responder_cortesia("Buenos dias", {"_con_historial": True}, "Jorge")
        self.assertIn("¿En qué te puedo ayudar hoy?", r["reply_text"])

    def test_nombre_de_perfil(self):
        from bot.utils.texto import nombre_valido
        self.assertEqual(nombre_valido("~Brayanvillar"), "Brayanvillar")
        self.assertEqual(nombre_valido("Chonate Alcoser Jorge").split()[0], "Jorge")

    def test_bienvenida_no_se_duplica(self):
        from bot.conversacion.formulario import bienvenida_reciente, marcar_bienvenida
        meta = {}
        self.assertFalse(bienvenida_reciente(meta))
        marcar_bienvenida(meta)
        self.assertTrue(bienvenida_reciente(meta))

    def test_reintento_de_meta(self):
        from bot.conversacion.orquestador import _reintento_de_meta
        ahora = datetime.now(timezone.utc)
        texto = "¡Hola! Completé el formulario y me gustaría obtener más información"
        meta = {"ultimo_texto_cliente": texto, "ts_ultimo_cliente": (ahora - timedelta(minutes=2)).isoformat(),
                "ts_ultimo_bot": (ahora - timedelta(minutes=1)).isoformat()}
        self.assertTrue(_reintento_de_meta(meta, texto))
        self.assertFalse(_reintento_de_meta(dict(meta, ultimo_texto_cliente="1"), "1"))

    def test_mas_tarde_ofrece_horas_despues(self):
        from bot.conversacion import agenda_humana as ah
        dia = (datetime.now(LIMA_TZ) + timedelta(days=2)).replace(hour=9, minute=0, second=0, microsecond=0)
        meta = {"etapa": "ofrecio_horarios", "slots_ofrecidos": [dia.isoformat(), dia.replace(hour=13).isoformat()]}
        ofrecidos = {}

        def ofrecer(slots, enc, pie=""):
            ofrecidos["slots"] = slots
            return {"reply_text": enc}
        r = ah.ofrecer_mas_tarde("mas tarde no podria ser", "¿Más tarde no podría ser?", meta, ofrecer, "")
        self.assertTrue(r and all(s.hour > 13 and s.date() == dia.date() for s in ofrecidos["slots"]))
        self.assertIsNone(ah.ofrecer_mas_tarde("mas tarde no podria ser", "Más tarde no podría ser", meta, ofrecer, ""))

    def test_seguimiento_recuerda_los_horarios_pedidos(self):
        from bot.seguimiento.mensajes import _texto_rescate_24h
        vie = (datetime.now(LIMA_TZ) + timedelta(days=3)).replace(hour=13, minute=0, second=0, microsecond=0)
        meta = {"etapa": "ofrecio_horarios", "fin_credito_aprobado": True,
                "slots_ofrecidos": [vie.isoformat(), vie.replace(hour=14).isoformat(), vie.replace(hour=15).isoformat()]}
        txt = _texto_rescate_24h(meta, "María")
        self.assertIn("¿Lograste revisar si alguno de los horarios", txt)
        self.assertIn("por la tarde", txt)
        self.assertNotIn("banco", txt)


    def test_saludo_suelto_espera_mas(self):
        from bot.agrupador import segundos_de_espera
        self.assertGreater(segundos_de_espera("Buenos días"), segundos_de_espera("Donde están ubicados exactamente"))
        self.assertEqual(segundos_de_espera("1"), segundos_de_espera("Donde están ubicados exactamente"))

    def test_carpeta_manda(self):
        from bot.datos.recursos import _clasificar
        tipo = lambda r: _clasificar(r, {"name": r.rsplit("/", 1)[1], "metadata": {"size": 1}}, [])["tipo"]
        self.assertEqual(tipo("santa-teresa/casa-1/fotos/sala.jpg"), "foto_real")
        self.assertEqual(tipo("santa-teresa/comun/renders/sala-1.jpg"), "render_amoblado")
        self.assertEqual(tipo("santa-teresa/casa-2/fichas/ficha.jpg"), "ficha")

    def test_render_cocina_en_comun_renders(self):
        from bot.config import URL_RENDER_GRIS, URL_RENDER_MADERA
        if not os.environ.get("URL_RENDER_GRIS"):
            self.assertTrue(URL_RENDER_GRIS.endswith("santa-teresa/comun/renders/cocina_2.jpg"))
            self.assertTrue(URL_RENDER_MADERA.endswith("santa-teresa/comun/renders/cocina_1.jpg"))

    def test_tipo_cambio_del_bcrp(self):
        import bot.integraciones.tipo_cambio as tcm
        with mock.patch.object(tcm, "TIPO_CAMBIO_AUTO", True), mock.patch.object(tcm, "_consultar_bcrp", return_value=3.4510):
            tcm._CACHE.update(ts=0.0, valor=None, ultimo_bueno=None)
            self.assertEqual(tcm.tipo_cambio_referencial(), 3.45)
        with mock.patch.object(tcm, "TIPO_CAMBIO_AUTO", True), mock.patch.object(tcm, "_consultar_bcrp", side_effect=OSError("caido")):
            tcm._CACHE["ts"] = 0.0
            self.assertEqual(tcm.tipo_cambio_referencial(), 3.45)  # usa el último valor bueno
        tcm._CACHE.update(ts=0.0, valor=None, ultimo_bueno=None)


if __name__ == "__main__":
    unittest.main()
