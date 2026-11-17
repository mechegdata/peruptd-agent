"""Chats reales del 31-oct al 8-nov: clientes con BSUID (WhatsApp usernames), 'en la mañana', 'si me indica',
casa de 1 piso, 'es muy grande', '¿eso es al contado?', 'mensual cuánto', nombres en minúsculas y '¿dónde la veo?'."""
import unittest
from unittest import mock

from simulador import Simulador  # noqa: I100 (prepara el entorno antes de importar bot)

from bot.canales import whatsapp  # noqa: E402
from bot.nlp.patrones import AFIRMA_RE  # noqa: E402
from bot.utils.telefono import destino_wa, es_bsuid, id_legado, normalize_pe_phone  # noqa: E402
from bot.utils.texto import nombre_valido  # noqa: E402

BSUID = "PE.1000000000000001"


class ClientesConBSUID(unittest.TestCase):
    def test_bsuid_no_se_convierte_en_telefono(self):
        self.assertTrue(es_bsuid(BSUID))
        self.assertEqual(normalize_pe_phone(BSUID), BSUID)
        self.assertEqual(id_legado(BSUID), "1000000000000001")
        self.assertFalse(es_bsuid("51900000000"))

    def test_destinatario_correcto(self):
        self.assertEqual(destino_wa(BSUID), {"recipient": BSUID})
        self.assertEqual(destino_wa("900000000"), {"to": "51900000000"})

    def test_envio_a_bsuid_usa_recipient(self):
        class R:
            status_code = 200
            text = "{}"
        with mock.patch.object(whatsapp.requests, "post", return_value=R()) as post:
            whatsapp.send_wa_text(BSUID, "hola")
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload.get("recipient"), BSUID)
        self.assertNotIn("to", payload)

    def test_historial_legado_se_migra(self):
        from bot.datos.leads import migrar_id_legado
        with Simulador() as sim:
            sim.sb.table("leads").insert([{"sender_id": "1000000000000001", "canal": "whatsapp", "interes": '{"etapa": "ofrecio_horarios"}'}]).execute()
            sim.sb.table("mensajes").insert([{"sender_id": "1000000000000001", "rol": "user", "contenido": "hola"}]).execute()
            migrar_id_legado(BSUID)
            self.assertEqual(sim.meta(BSUID).get("etapa"), "ofrecio_horarios")
            self.assertEqual(sim.sb.db["mensajes"][0]["sender_id"], BSUID)


class ChatsReales(unittest.TestCase):
    def test_linn_en_la_manana_del_dia_elegido_y_sin_inventar_inicial(self):
        from datetime import timedelta
        from bot.utils.fechas import _ahora
        hoy = _ahora().date()
        domingo = hoy + timedelta(days=(6 - hoy.weekday()) % 7 or 7)  # el chat real fue con "el domingo 15" (ya pasó)
        if (domingo - hoy).days < 2:
            domingo += timedelta(days=7)
        with Simulador() as sim:
            for m in ["Hola, info de la casa por favorm", "Podemos ir a verlo", "Si me indica que día\nPaa ir con mi esposa",
                      f"El domingo {domingo.day} esta bien."]:
                sim.cliente(BSUID, "Linn Dávila", m)
            r = sim.cliente(BSUID, "Linn Dávila", "En la mañana esta bien")
            self.assertIn(f"domingo {domingo.day} en la mañana", r)
            self.assertNotIn("Perdona", r)
            sim.cliente(BSUID, "Linn Dávila", "10am esta bieb")
            self.assertIsNot(sim.meta(BSUID).get("fin_inicial"), True, "nunca dijo que tenía inicial")

    def test_si_condicional_no_es_afirmacion(self):
        self.assertFalse(AFIRMA_RE.match("si me indica que dia"))
        self.assertFalse(AFIRMA_RE.match("si puede manana"))
        self.assertTrue(AFIRMA_RE.match("si me parece bien"))
        self.assertTrue(AFIRMA_RE.match("si"))

    def test_maritza_casa_de_1er_piso_muy_grande_y_contado(self):
        with Simulador() as sim:
            s, n = "51900000000", "Maritza Diaz Veliz"
            sim.cliente(s, n, "Buenos días. Disculpe quisiera saber el costo y si hay echas como para vivir")
            self.assertIn("solo tenemos", sim.cliente(s, n, "Y casa de 1er piso"))
            r = sim.cliente(s, n, "Esque muy grande")
            self.assertIn("Te entiendo", r)
            self.assertNotIn("1️⃣", r)
            r = sim.cliente(s, n, "Eso es al contado")
            self.assertIn("Así es", r)
            self.assertIn("130,000", r)

    def test_gladis_mensual_es_la_cuota(self):
        with Simulador() as sim:
            s, n = "51976399193", "gladis"
            r1 = sim.cliente(s, n, "Buenas noches me podría brindar información de la casa que tienen en venta en lambayeque")
            self.assertIn("Gladis", r1)
            r = sim.cliente(s, n, "Mensual cuanto seria?")
            self.assertIn("al mes", r)

    def test_nombres_en_minusculas(self):
        self.assertEqual(nombre_valido("cielo"), "Cielo")
        self.assertEqual(nombre_valido("JUAN CORONEL"), "Juan Coronel")

    def test_donde_la_veo_agrega_ubicacion(self):
        from bot.config import MAPS_URL
        with Simulador() as sim:
            s, n = "51979662530", "Eloisa Uceda"
            sim.cliente(s, n, "Hola, quiero visitar las casas")
            r = sim.cliente(s, n, "Quedamos para hoy a las 4.30pm, me confirma?\nY donde la veo?")
            self.assertIn(MAPS_URL, r)


if __name__ == "__main__":
    unittest.main()


class EstadoRealDeLasCasas(unittest.TestCase):
    """8-nov: 1er y 2do piso con acabados; 3er piso en casco. Visitas desde el 15-nov (se terminan pasamanos y barandas)."""

    def test_ningun_mensaje_promete_casas_terminadas(self):
        import pathlib
        import re
        prohibido = re.compile(r"100% (terminad|construid)|lista para mudarte|listas para entrega|ya están terminadas|"
                               r"ideal para parrillas|lista para una parrillada|gran terraza|gemelas|ya est[aá] terminada", re.I)
        for f in pathlib.Path("bot").rglob("*.py"):
            for n, linea in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
                if prohibido.search(linea) and not linea.strip().startswith("#") and "NO son gemelas" not in linea and "NUNCA las llames 'gemelas'" not in linea and "prohibido" not in linea:
                    self.fail(f"{f}:{n} promete más de lo que hay: {linea.strip()[:120]}")

    def test_distribucion_aclara_tercer_piso_en_casco(self):
        with Simulador() as sim:
            r = sim.cliente("51900000001", "Ana", "Cómo es la distribución de los pisos?")
            self.assertIn("casco", r)

    def test_prompt_prohibe_inventar_acabados_del_3er_piso(self):
        from bot.ia.prompt import build_system_prompt
        p = build_system_prompt("whatsapp", "", "")
        self.assertIn("EN CASCO", p)
        self.assertIn("NO inventes", p)

    def test_visitas_solo_desde_la_fecha_de_apertura(self):
        from datetime import date, timedelta
        import bot.conversacion.agenda as agenda
        import bot.conversacion.agenda_humana as ah
        import bot.integraciones.calendario as cal
        apertura = date.today() + timedelta(days=5)
        with Simulador() as sim, mock.patch.object(cal, "primer_dia_visitas", lambda: apertura), \
                mock.patch.object(agenda, "primer_dia_visitas", lambda: apertura), \
                mock.patch.object(ah, "primer_dia_visitas", lambda: apertura):
            r = sim.cliente("51900000002", "Luis", "Quiero visitar las casas, ¿cuándo puedo ir?")
            self.assertIn("Estamos agendando las visitas desde el", r)
            for s in sim.meta("51900000002").get("slots_ofrecidos") or []:
                self.assertGreaterEqual(cal.datetime.fromisoformat(s).date(), apertura)
            r = sim.cliente("51900000002", "Luis", "Mejor mañana a las 10")
            self.assertIn("últimos detalles", r)
            self.assertFalse(sim.eventos, "no debe agendar antes de la apertura")

    def test_prompt_sin_fecha_de_apertura_pasada(self):
        """15-nov: ya se terminaron pasamanos y barandas; la IA no debe seguir diciendo 'visitas desde el 15'."""
        import bot.ia.prompt as pr
        with mock.patch.object(pr, "VISITAS_DESDE", "2026-11-15"), mock.patch("bot.utils.fechas._ahora",
                return_value=__import__("datetime").datetime(2026, 11, 17, 8, 0)):
            p = pr.build_system_prompt("whatsapp", "", "")
        self.assertNotIn("SOLO se agendan desde", p)
        self.assertNotIn("pasamanos", p)
        with mock.patch.object(pr, "VISITAS_DESDE", "2026-11-15"), mock.patch("bot.utils.fechas._ahora",
                return_value=__import__("datetime").datetime(2026, 11, 10, 8, 0)):
            self.assertIn("SOLO se agendan desde el domingo 15", pr.build_system_prompt("whatsapp", "", ""))

    def test_reposteros_solo_primera_unidad(self):
        with Simulador() as sim:
            r = sim.cliente("51900000003", "Rosa", "Hola, quisiera información de las casas")
        self.assertNotIn("incluyen los reposteros", r)
