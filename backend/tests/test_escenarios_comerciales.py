"""Escenarios comerciales: agenda humana, moneda/tipo de cambio, objeción de precio, gancho $/m² y fotos por momento.
Corren sin credenciales: Calendar se simula con una agenda vacía."""
import os
import unittest
from unittest import mock

os.environ.pop("SUPABASE_KEY", None)
os.environ.pop("GEMINI_API_KEY", None)
os.environ["TIPO_CAMBIO_AUTO"] = "false"  # sin red en las pruebas: tipo de cambio fijo de respaldo (3.45)
os.environ["VISITAS_DESDE"] = ""  # sin fecha de apertura en las pruebas (se prueba aparte con mock)

import bot.integraciones.calendario as cal  # noqa: E402
from bot.conversacion import agenda  # noqa: E402
from bot.conversacion import recursos  # noqa: E402
from bot.conversacion.recursos import elegir_fotos  # noqa: E402
from bot.conversacion.objeciones import es_objecion_precio, responder_precio  # noqa: E402
from bot.conversacion.precio import es_pregunta_moneda  # noqa: E402
from bot.conversacion.presupuesto import leer_monto  # noqa: E402
from bot.nlp.restricciones import detectar_restriccion_horaria  # noqa: E402
from bot.utils.texto import limpiar_texto  # noqa: E402

ELOISA = "Si me gustaría ver la casa , pero trabajo hasta las 5pm, podría concretar la cita para un fin de semana?"


def _evento_falso(nombre, tel, iso, notas=""):
    return True, cal.format_fecha_es(cal.datetime.fromisoformat(iso), relativo=True), "ev-test"


class AgendaHumana(unittest.TestCase):
    def setUp(self):
        self.patches = [
            mock.patch.object(cal, "get_busy_intervals", lambda a, b: []),
            mock.patch.object(agenda, "create_calendar_event", side_effect=_evento_falso),
            mock.patch.object(agenda, "alertar_asesor", lambda *a: None),
        ]
        self.mocks = [p.start() for p in self.patches]

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def _agenda(self, texto, meta=None):
        meta = meta if meta is not None else {"fin_modalidad": "contado"}
        return agenda.motor_agenda(texto, meta, "Eloisa Pérez", "51999", "whatsapp", []), meta

    def test_caso_eloisa_no_agenda_a_las_5_y_ofrece_fin_de_semana(self):
        r, meta = self._agenda(ELOISA)
        self.assertEqual(meta["etapa"], "ofrecio_horarios")
        self.assertFalse(self.mocks[1].called, "no debe crear la cita a las 5 p. m.")
        dias = {cal.datetime.fromisoformat(s).weekday() for s in meta["slots_ofrecidos"]}
        self.assertTrue(dias <= {5, 6})
        self.assertIn("fin de semana", r["reply_text"])

    def test_tras_responder_contado_mantiene_los_horarios_de_fin_de_semana(self):
        _, meta = self._agenda(ELOISA, {})
        ofrecidos = list(meta["slots_ofrecidos"])
        self._agenda("al contado", meta)
        self.assertEqual(meta["slots_ofrecidos"], ofrecidos)

    def test_salgo_a_las_3_ofrece_desde_las_4(self):
        _, meta = self._agenda("quiero visitarla, salgo del trabajo a las 3")
        for s in meta["slots_ofrecidos"]:
            dt = cal.datetime.fromisoformat(s)
            self.assertTrue(dt.weekday() >= 5 or dt.hour >= 16)

    def test_fin_de_semana_a_las_10(self):
        _, meta = self._agenda("puedo ir el fin de semana a las 10?")
        for s in meta["slots_ofrecidos"]:
            dt = cal.datetime.fromisoformat(s)
            self.assertIn(dt.weekday(), {5, 6})
            self.assertEqual(dt.hour, 10)

    def test_hora_concreta_mas_restriccion_agenda_la_hora_concreta(self):
        r, meta = self._agenda("el sábado a las 11 porque trabajo hasta las 5")
        self.assertTrue(meta["cita_agendada"])
        dt = cal.datetime.fromisoformat(meta["fecha_cita"])
        self.assertEqual((dt.weekday(), dt.hour), (5, 11))

    def test_detecta_restricciones(self):
        self.assertEqual(detectar_restriccion_horaria("trabajo hasta las 5pm")["desde"], 18)
        self.assertEqual(detectar_restriccion_horaria("después de las 4")["desde"], 16)
        self.assertEqual(detectar_restriccion_horaria("antes de las 12")["hasta"], 12)
        self.assertEqual(detectar_restriccion_horaria("puedo en la noche")["tipo"], "noche")
        self.assertIsNone(detectar_restriccion_horaria("buenas noches, quiero visitar"))
        self.assertIsNone(detectar_restriccion_horaria("el sábado a las 4 pm"))


class Precio(unittest.TestCase):
    def setUp(self):
        self.p = mock.patch.object(cal, "get_busy_intervals", lambda a, b: [])
        self.p.start()

    def tearDown(self):
        self.p.stop()

    def test_moneda(self):
        for txt in ["¿el precio es en soles o en dólares?", "a qué tipo de cambio?", "puedo pagar en soles?"]:
            self.assertTrue(es_pregunta_moneda(limpiar_texto(txt)), txt)
        self.assertFalse(es_pregunta_moneda(limpiar_texto("tengo 100 mil soles de inicial")))
        r = responder_precio("¿es en soles o dólares?", "Eloisa", {})
        self.assertIn("dólares", r)

    def test_monto_en_soles_con_tipo_de_cambio_fijo(self):
        with mock.patch("bot.conversacion.precio.tipo_cambio_referencial", return_value=3.75):
            r = responder_precio("a qué tipo de cambio?", "", {})
            self.assertIn("S/ 506,250", r)
            self.assertIn("S/ 487,500", r)  # al contado US$130,000
            self.assertEqual(leer_monto(limpiar_texto("tengo 450 mil soles")), (450000, "pen"))

    def test_objecion_detecta_y_excluye(self):
        for txt in ["uy está muy caro", "se me pasa del presupuesto", "sigue siendo mucho para mí", "está fuerte el precio"]:
            self.assertTrue(es_objecion_precio(limpiar_texto(txt)), txt)
        for txt in ["no es caro, me gusta", "no me alcanza el tiempo hoy", "frente a la loza, cara a la calle"]:
            self.assertFalse(es_objecion_precio(limpiar_texto(txt)), txt)

    def test_objecion_escalonada(self):
        meta = {}
        r1 = responder_precio("está muy caro", "Eloisa", meta)
        self.assertIn("$675 por m²", r1)
        self.assertEqual(meta["etapa"], "pregunto_presupuesto")
        r2 = responder_precio("igual es mucho para mi", "Eloisa", meta)
        self.assertIn("sin compromiso", r2)
        r3 = responder_precio("sigue siendo mucho para mi", "Eloisa", meta)
        self.assertIn("propietario", r3)
        self.assertIn("3ra vez", meta["_alerta_asesor"])

    def test_objecion_con_monto_calcula_m2(self):
        meta = {}
        r = responder_precio("muy caro, yo tengo 120 mil", "", meta)
        self.assertIn("¿esos 120,000 son en *soles* o en *dólares*?", r)  # sin moneda: pregunta


class Recursos(unittest.TestCase):
    CAT = [
        {"unidad": "casa_1", "tipo": "video", "ambiente": "recorrido", "url": "https://x/c1.mp4"},
        {"unidad": "casa_2", "tipo": "video", "ambiente": "recorrido", "url": "https://x/c2.mp4"},
        {"unidad": "ambas", "tipo": "foto_real", "ambiente": "fachada", "url": "https://x/f.jpg"},
        {"unidad": "ambas", "tipo": "render_amoblado", "ambiente": "sala", "url": "https://x/s.jpg"},
        {"unidad": "casa_2", "tipo": "foto_real", "ambiente": "terraza", "url": "https://x/t.jpg"},
    ]

    def setUp(self):
        self.p = [mock.patch.object(recursos, "listar_recursos", lambda: self.CAT),
                  mock.patch.dict("bot.conversacion.recursos.FOTOS_CASA", {}, clear=True)]
        for p in self.p:
            p.start()

    def tearDown(self):
        for p in self.p:
            p.stop()

    def test_fotos_por_momento_sin_repetir_y_render_aclarado(self):
        meta = {}
        fotos = elegir_fotos("primer_vistazo", meta)
        self.assertEqual([u for u, _, _ in fotos], ["https://x/f.jpg", "https://x/s.jpg"])
        self.assertIn("foto real", fotos[0][2])
        self.assertIn("Muebles agregados como referencia", fotos[1][2])
        self.assertEqual(elegir_fotos("ubicacion", meta), [])  # la fachada ya la vio
        # La terraza (3er piso en casco) ya no se manda sola en la objeción de precio: no crear expectativas de acabados
        self.assertNotIn("https://x/t.jpg", [u for u, _, _ in elegir_fotos("objecion", meta)])

    def test_videos_por_casa(self):
        vids = recursos.material_de_tipo("video")
        self.assertEqual([c for _, _, c in vids], ["🎥 Recorrido en video de la Casa 1", "🎥 Recorrido en video de la Casa 2"])
        self.assertEqual(len(recursos.material_de_tipo("video", "casa_2")), 1)
        self.assertEqual(recursos.unidad_del_texto("fotos de la casa 2"), "casa_2")
        self.assertIsNone(recursos.unidad_del_texto("las dos casas en video"))

    def test_sin_catalogo_no_manda_nada(self):
        with mock.patch.object(recursos, "listar_recursos", lambda: []):
            self.assertEqual(elegir_fotos("primer_vistazo", {}), [])


class TratoHumano(unittest.TestCase):
    """Casos reales: Henry (bot insistente) y Eloisa (logística después de agendar)."""

    def setUp(self):
        self.p = mock.patch.object(cal, "get_busy_intervals", lambda a, b: [])
        self.p.start()

    def tearDown(self):
        self.p.stop()

    def test_postergacion_no_insiste(self):
        from bot.conversacion.cortesia import responder_cortesia
        meta = {"etapa": "pregunto_dia"}
        r = responder_cortesia("Muy bien. Le estaré comunicando la hora. 👍", meta, "")
        self.assertIn("Quedo atento", r["reply_text"])
        self.assertNotIn("1️⃣", r["reply_text"])
        self.assertTrue(responder_cortesia("👍👍", meta, "")["_no_responder"])

    def test_pulgar_tras_horarios_recuerda_una_sola_vez(self):
        from bot.conversacion.cortesia import responder_cortesia
        slots = [s.isoformat() for s in cal.get_free_slots(n=3)]
        meta = {"etapa": "ofrecio_horarios", "slots_ofrecidos": slots}
        self.assertIn("¿Te reservo alguno?", responder_cortesia("👍", meta, "")["reply_text"])
        self.assertTrue(responder_cortesia("👍", meta, "")["_no_responder"])

    def test_nombre_de_perfil_invalido(self):
        from bot.utils.texto import _primer_nombre, nombre_valido
        self.assertEqual(nombre_valido("."), "")
        self.assertEqual(_primer_nombre("😊"), "")
        self.assertEqual(_primer_nombre("eloisa uceda"), "Eloisa")

    def test_hora_suelta_tras_ofrecer_fin_de_semana_pregunta_el_dia(self):
        from bot.conversacion.agenda_humana import completar_fecha_por_contexto
        sab = [s for s in cal.get_free_slots(n=6, dias_semana={5, 6})]
        meta = {"etapa": "ofrecio_horarios", "slots_ofrecidos": [s.isoformat() for s in sab]}
        fh = {"hora": 16, "minuto": 30, "fecha": None}
        r = completar_fecha_por_contexto(fh, meta, ", Eloisa")
        self.assertIn("¿Para qué día", r["reply_text"])
        fh2 = {"hora": None, "minuto": 0, "fecha": sab[0].date()}
        self.assertIsNone(completar_fecha_por_contexto(fh2, meta, ""))
        self.assertEqual((fh2["hora"], fh2["minuto"]), (16, 30))

    def test_acompanantes_y_movilidad(self):
        from bot.conversacion import post_agenda
        meta = {"cita_agendada": True, "etapa": "pregunto_acompanantes"}
        with mock.patch.object(post_agenda, "OFRECE_MOVILIDAD", True):
            r = post_agenda.responder_post_agenda("Si de Chiclayo a lambayeque, iré con mi hermano", meta, "Eloisa")
            self.assertIn("hermano", r["reply_text"])
            self.assertEqual(meta["etapa"], "ofrecio_movilidad")
            r = post_agenda.responder_post_agenda("coordinamos dos días antes o tiene que ser ya", meta, "Eloisa")
            self.assertIn("no hay apuro", r["reply_text"])
        r = post_agenda.responder_post_agenda("me indican que vamos por nuestra cuenta, coordinamos donde nos reunimos", meta, "")
        self.assertEqual(meta["movilidad"], "propia")


class DiasYMaterial(unittest.TestCase):
    def setUp(self):
        self.p = [mock.patch.object(cal, "get_busy_intervals", lambda a, b: []),
                  mock.patch.object(agenda, "alertar_asesor", lambda *a: None)]
        for p in self.p:
            p.start()

    def tearDown(self):
        for p in self.p:
            p.stop()

    def test_muchas_formas_de_decir_los_dias(self):
        from bot.nlp.dias import preferencia_dias
        casos = {
            "uy no puedo entre semana": {5, 6}, "solo puedo los fines de semana": {5, 6}, "de lunes a viernes trabajo": {5, 6},
            "en la semana no me da el tiempo": {5, 6}, "solo los sábados": {5}, "el fin de semana no puedo": {0, 1, 2, 3, 4},
            "el fin de semana no puedo, mejor entre semana": {0, 1, 2, 3, 4}, "puedo martes o jueves": {1, 3},
            "cualquier día menos el lunes": {1, 2, 3, 4, 5, 6}, "entre semana no, sabado si": {5}, "prefiero de lunes a viernes": {0, 1, 2, 3, 4},
        }
        for txt, esperado in casos.items():
            self.assertEqual(preferencia_dias(txt)[0], esperado, txt)
        self.assertIsNone(preferencia_dias("quiero visitarla")[0])

    def test_trabaja_ventana_de_noche_y_fin_de_semana(self):
        meta = {"fin_modalidad": "contado"}
        r = agenda.motor_agenda("quiero ver la casa pero trabajo hasta las 5", meta, "Eloisa", "519", "whatsapp", [])
        self.assertIn("saliendo del trabajo, desde las 6 p. m. hasta las 8 o 9 p. m.", r["reply_text"])
        self.assertTrue(all(cal.datetime.fromisoformat(x).weekday() >= 5 for x in meta["slots_ofrecidos"]))
        r = agenda.motor_agenda("a las 7", meta, "Eloisa", "519", "whatsapp", [])
        self.assertIn("¿Qué día de la semana", r["reply_text"])


class GaleriaConNombresLibres(unittest.TestCase):
    """El material se sube con cualquier nombre: el bot deduce casa, tipo y ambiente de la ruta."""

    def test_clasifica_nombres_desordenados(self):
        import bot.datos.recursos as rd
        arbol = {"": ["cocina_1.jpg", "Proyecto/"], "Proyecto": ["Casa 1/", "CASA 2/", "Renders con muebles/"],
                 "Proyecto/Casa 1": ["IMG_2034.jpg", "Recorrido casa 1.mp4", "Ficha tecnica.pdf", "terraza.heic"],
                 "Proyecto/CASA 2": ["frontis.jpeg", "baño visitas.jpg"], "Proyecto/Renders con muebles": ["cuarto niños.png"]}

        class Store:
            def list(self, ruta, opts=None):
                return [{"name": n[:-1], "id": None} if n.endswith("/") else {"name": n, "id": "x"} for n in arbol.get(ruta, [])]

        class SB:
            class storage:
                @staticmethod
                def from_(b):
                    return Store()

            def table(self, n):
                raise RuntimeError("sin tabla")

        with mock.patch.object(rd, "supabase", SB()):
            res = rd.resumen_catalogo()
        rd._CACHE["ts"] = 0
        vistos = {(a["unidad"], a["tipo"], a["ambiente"]) for a in res["archivos"]}
        self.assertIn(("casa_1", "video", "recorrido"), vistos)
        self.assertIn(("casa_1", "ficha", "planos"), vistos)
        self.assertIn(("casa_2", "foto_real", "fachada"), vistos)
        self.assertIn(("ambas", "render_amoblado", "dormitorio"), vistos)
        self.assertEqual(len(res["archivos"]), 6)  # el .heic y el archivo suelto de la raíz no entran
        self.assertTrue(any(".heic" in a for a in res["avisos"]))

    def test_galeria_mezcla_casas_y_ofrece_video(self):
        from bot.conversacion.material import responder_material, responder_oferta_video
        cat = [{"unidad": u, "tipo": t, "ambiente": a, "url": f"https://x/{u}{a}{t}", "nombre": ""}
               for u, t, a in [("casa_1", "foto_real", "sala"), ("casa_2", "foto_real", "sala"), ("ambas", "render_amoblado", "sala"),
                               ("casa_1", "video", "recorrido"), ("casa_2", "video", "recorrido")]]
        with mock.patch.object(recursos, "listar_recursos", lambda: cat), mock.patch.dict("bot.conversacion.recursos.FOTOS_CASA", {}, clear=True), \
                mock.patch.object(cal, "get_busy_intervals", lambda a, b: []):
            meta = {}
            r = responder_material("me mandas fotos?", "Ana", meta, cerrar=False)
            self.assertEqual({u.split("/")[-1][:6] for u, _, _ in r["recursos"]}, {"casa_1", "casa_2", "ambass"})
            self.assertIn("recorrido en video", r["reply_text"])
            self.assertEqual(meta["etapa"], "ofrecio_video")
            r2 = responder_oferta_video("sí", meta, "Ana")
            self.assertTrue(r2["_pide_video"])


class CasoClara(unittest.TestCase):
    """'Mejor para el domingo' un domingo 11:38 p. m., '¿el domingo 1 no tienes?', '¿para la tarde?' con una cita ya agendada."""

    def test_domingo_dicho_un_domingo_de_noche_es_el_proximo(self):
        from datetime import datetime
        from bot.config import LIMA_TZ
        from bot.nlp.parser_fechas import parse_fecha_hora_es
        ahora = datetime(2026, 10, 25, 23, 38, tzinfo=LIMA_TZ)  # domingo
        self.assertEqual(parse_fecha_hora_es("Mejor para el domingo porfa", ahora)["fecha"].day, 1)
        self.assertEqual(parse_fecha_hora_es("Para la tarde?", ahora)["turno"], "tarde")
        manana = datetime(2026, 10, 25, 9, 0, tzinfo=LIMA_TZ)
        self.assertEqual(parse_fecha_hora_es("el domingo", manana)["fecha"].day, 25)  # en la mañana sí es hoy

    def test_horarios_repartidos_en_el_dia(self):
        from bot.integraciones.calendario import _repartir
        dia = [cal.datetime(2026, 11, 1, h, 0) for h in range(9, 18)]
        self.assertEqual([x.hour for x in _repartir(dia, 3)], [9, 12, 15])

    def test_reprograma_y_entiende_la_tarde(self):
        from datetime import datetime
        from bot.config import LIMA_TZ
        with mock.patch.object(cal, "get_busy_intervals", lambda a, b: []), mock.patch.object(agenda, "alertar_asesor", lambda *a: None):
            prox = cal.get_free_slots(n=1, dias_semana={6})[0].date()
            cita = datetime(prox.year, prox.month, prox.day, 11, 0, tzinfo=LIMA_TZ) - cal.timedelta(days=1)
            meta = {"fin_modalidad": "contado", "cita_agendada": True, "fecha_cita": cita.isoformat(), "evento_id": "e", "etapa": "agendado"}
            r = agenda.motor_agenda(f"mejor el domingo {prox.day}", meta, "Clara", "519", "whatsapp", [])
            self.assertIn("Cambiamos tu visita", r["reply_text"])
            r = agenda.motor_agenda(f"para el domingo {prox.day} no tienes espacios?", meta, "Clara", "519", "whatsapp", [])
            self.assertIn("¿Cuál te reservo?", r["reply_text"])
            r = agenda.motor_agenda("Para la tarde?", meta, "Clara", "519", "whatsapp", [])
            self.assertIn("en la tarde", r["reply_text"])
            self.assertTrue(all(cal.datetime.fromisoformat(x).hour >= 13 for x in meta["slots_ofrecidos"]))


class LeyendasCorrectas(unittest.TestCase):
    def test_cocina_render_no_dice_muebles_y_dormitorio_sin_bano(self):
        from bot.conversacion.recursos import leyenda
        cocina = leyenda({"unidad": "ambas", "tipo": "render_amoblado", "ambiente": "cocina", "nombre": "Cocina"})
        self.assertIn("reposteros instalados", cocina)
        self.assertNotIn("sin muebles", cocina)
        dorm = leyenda({"unidad": "casa_1", "tipo": "foto_real", "ambiente": "dormitorio", "nombre": "Dormitorio"})
        self.assertNotIn("baño", dorm)
        sala = leyenda({"unidad": "ambas", "tipo": "render_amoblado", "ambiente": "sala", "nombre": "Sala comedor"})
        self.assertIn("Muebles agregados como referencia", sala)


class HoraSuelta(unittest.TestCase):
    def test_plan_de_5_es_una_hora_y_la_2_es_una_opcion(self):
        from bot.conversacion.agenda_humana import inferir_hora_suelta
        meta = {"etapa": "ofrecio_horarios", "slots_ofrecidos": ["2026-11-01T13:00:00-05:00", "2026-11-01T14:00:00-05:00", "2026-11-01T15:00:00-05:00"]}
        for txt, hora in [("plan de 5", 17), ("5", 17), ("para las 10 am", 10), ("la 2", None), ("2", None)]:
            fh = {"hora": None, "minuto": 0, "fecha": None, "turno": None}
            inferir_hora_suelta(txt, fh, meta)
            self.assertEqual(fh["hora"], hora, txt)

    def test_pregunta_por_una_hora_pide_confirmacion(self):
        with mock.patch.object(cal, "get_busy_intervals", lambda a, b: []), mock.patch.object(agenda, "alertar_asesor", lambda *a: None), \
                mock.patch.object(agenda, "create_calendar_event") as crear:
            meta = {"fin_modalidad": "contado"}
            agenda.motor_agenda("quiero visitar el domingo en la tarde", meta, "Ana", "519", "whatsapp", [])
            r = agenda.motor_agenda("y a las 5?", meta, "Ana", "519", "whatsapp", [])
            self.assertIn("está libre", r["reply_text"])
            self.assertEqual(meta["etapa"], "confirmar_horario")
            self.assertFalse(crear.called)


class ChatsReales27Oct(unittest.TestCase):
    """Isidro, Asencio, Ana y la clienta de los 100,000: contado US$130k, presupuesto honesto, 'solo tenemos estas 2'."""

    def setUp(self):
        self.p = mock.patch.object(cal, "get_busy_intervals", lambda a, b: [])
        self.p.start()

    def tearDown(self):
        self.p.stop()

    def test_precio_al_contado(self):
        from bot.conversacion.faq import responder_faq
        r = responder_faq("Es su precio final cuánto sería al contado en soles", "Isidro", {})
        self.assertIn("$130,000", r)
        self.assertIn("S/ 448,500", r)
        self.assertIn("negociar", r)

    def test_solo_tenemos_estas_dos(self):
        from bot.conversacion.faq import responder_faq
        for txt in ["Solo casas en ese precio tiene o hay más económicas", "De un solo piso no venden", "hay casas as economicas"]:
            self.assertIn("solo tenemos", responder_faq(txt, "", {}), txt)

    def test_presupuesto_honesto(self):
        from bot.conversacion.faq import responder_faq
        meta = {"etapa": "pregunto_presupuesto"}
        r = responder_faq("puedo adquirir una casa con 100. 000 o no", "", meta)
        self.assertIn("soles", r)
        r = responder_faq("soles", "", meta)
        self.assertIn("no llegaríamos", r)
        self.assertIn("cuota inicial", r)
        self.assertNotIn("acercarnos", r)

    def test_ok_sin_nada_pendiente_no_responde(self):
        from bot.conversacion.cortesia import responder_cortesia
        self.assertTrue(responder_cortesia("Ok", {"etapa": "pregunto_presupuesto"}, "")["_no_responder"])
        self.assertIsNone(responder_cortesia("ok", {"etapa": "ofrecio_asesor"}, ""))  # ahí "ok" es un sí

    def test_mensajes_seguidos_se_responden_una_vez(self):
        import threading
        import bot.agrupador as ag
        with mock.patch.object(ag, "AGRUPAR_MENSAJES_SEG", 0.3):
            resultados = []
            hilos = [threading.Thread(target=lambda x=x: resultados.append(ag.esperar_y_agrupar("519", x))) for x in ["De un piso", "Quiero"]]
            for h in hilos:
                h.start()
                h.join(0.05)
            for h in hilos:
                h.join()
        self.assertEqual(sorted(r for r in resultados if r), ["De un piso\nQuiero"])


if __name__ == "__main__":
    unittest.main()
