"""Capa 2 · motores conectados al catálogo: reglas de presupuesto, anualidad, objeciones 1-2-3, agenda y multimedia."""
from datetime import datetime, timedelta

from bot.engines import agenda, finanzas, multimedia, pipeline
from bot.nlu_normalizer import SemanticNormalizer

NLU = SemanticNormalizer(usar_llm=False)
CASA = {"id": "re1", "external_crm_id": "01t5g00000Kx3AA", "name_es": "Casa de 3 pisos", "name_en": "3-Story House",
        "keywords": ["casa", "house", "3br", "ksa"], "specs_json": {"es": {"Terreno": "80 m²", "Pisos": "3"}, "en": {"Lot": "861 sqft", "Floors": "3"}},
        "list_price": 135000, "cash_price": 129000, "currency": "USD", "min_down_payment_pct": 10, "recommended_down_payment_pct": 20,
        "annual_rate_pct": 8.9, "max_term_years": 20, "promo_bonus_es": "La 1ra unidad incluye reposteros", "promo_bonus_en": "1st unit includes cabinets",
        "value_comparison_es": "A US$645/m² estás 22% bajo el promedio", "value_comparison_en": "At $645/m² you're 22% below average",
        "media": [{"id": "m1", "trigger_moment": "FIRST_INFO"}, {"id": "m2", "trigger_moment": "FIRST_INFO"},
                  {"id": "m3", "trigger_moment": "SPECS_PDF"}, {"id": "m4", "trigger_moment": "PRICE_OBJECTION"},
                  {"id": "m5", "trigger_moment": "LOCATION_FACADE"}]}
PREMIUM = {"id": "b1", "name_es": "Servicio Premium", "keywords": ["premium", "premiun", "servicio"], "list_price": 2400, "cash_price": 2150,
           "currency": "USD", "min_down_payment_pct": 0, "recommended_down_payment_pct": 0, "annual_rate_pct": 0, "max_term_years": 1,
           "value_comparison_es": "Reduces 32% las paradas", "media": []}
TENANT = {"name": "Santa Teresa Homes", "bot_name": "Ava", "advisor_name": "Henry"}
LUNES = datetime(2026, 11, 16, 10, 0)


def _libres(n=3, dia=None, filtro=None, excluir=None):
    """Calendario falso: libre cada hora de 9 a 20, salvo mañana a las 19:00."""
    base = (dia or (LUNES.date() + timedelta(days=1)))
    out = []
    for d in range(0 if dia else 0, 1 if dia else 4):
        f = base + timedelta(days=d)
        for h in range(9, 21):
            dt = datetime(f.year, f.month, f.day, h)
            if (f == LUNES.date() + timedelta(days=1) and h == 19) or (excluir and dt.isoformat() in excluir):
                continue
            if not filtro or filtro(dt):
                out.append(dt)
    return out[:n]


def test_anualidad():
    assert round(finanzas.cuota_mensual(110000, 8.9, 240)) == 983
    assert finanzas.cuota_mensual(1200, 0, 12) == 100


def test_reglas_de_presupuesto():
    assert finanzas.evaluar(CASA, 130000, "CASH", "es")["regla"] == "cubre_contado"
    assert finanzas.evaluar(CASA, 122000, "CASH", "es")["regla"].startswith("cerca_")          # 5 % abajo
    r = finanzas.evaluar(CASA, 110000, "CASH", "es")
    assert r["regla"].startswith("diferencia_corta") and r["calculo"]["cuota"] == round(19000 / 12)
    r = finanzas.evaluar(CASA, 25000, "FINANCING", "en")
    assert r["calculo"] == {"inicial": 25000, "prestamo": 110000, "cuota": 983, "meses": 240} and "$983/mo" in r["texto"]
    assert finanzas.evaluar(CASA, 5000, None, "es")["calculo"]["inicial_minima"] == 13500
    assert finanzas.evaluar(CASA, None, "FINANCING", "es")["calculo"]["inicial"] == 27000


def test_multimedia_maximo_2_sin_repetir():
    assert [m["id"] for m in multimedia.elegir(CASA, ["PRICE_OBJECTION", "FIRST_INFO", "SPECS_PDF"], [])] == ["m4", "m1"]
    assert [m["id"] for m in multimedia.elegir(CASA, ["FIRST_INFO", "FIRST_INFO"], ["m1"])] == ["m2"]


def test_agenda_respeta_salida_del_trabajo():
    ent = {"proposed_date_relative": "TOMORROW", "proposed_time": "18:30", "work_end_hour": "18:00"}
    slots = agenda.proponer(ent, _libres, LUNES)
    assert len(slots) == 3 and all(s.hour * 60 + s.minute >= 18 * 60 + 30 for s in slots)
    assert datetime(2026, 11, 17, 19) not in slots                                        # ocupado en el calendario
    assert "Mañana" in agenda.texto_opciones(slots, ent, "es", LUNES.date())


def test_conversacion_completa_es_con_jerga():
    estado = {"stage": "new", "sent_media_ids": []}
    t = NLU.normalize("ola q tal\na cuanto sale la ksa al cntado??\nta medio salado ah tngo 25 mil nomas\n"
                      "se podra ver mñn saliendo de la chamba tipo 6 y media?", items=[CASA])
    r = pipeline.run(t, estado, [CASA, PREMIUM], TENANT, _libres, LUNES)
    assert "¡Hola! Soy Ava" in r.texto and "US$129,000" in r.texto and "US$983/mes" in r.texto and "1️⃣" in r.texto
    assert [m["id"] for m in r.media] == ["m4", "m1"]
    assert r.cambios["price_objection_count"] == 1 and r.cambios["stated_budget"] == 25000 and r.cambios["stage"] == "qualified"
    assert r.alertas and not r.alertas[0][1]
    estado.update(r.cambios, sent_media_ids=[m["id"] for m in r.media])
    r2 = pipeline.run(NLU.normalize("2"), estado, [CASA], TENANT, _libres, LUNES)
    assert r2.reservar == datetime.fromisoformat(estado["offered_slots"][1]) and r2.cambios["stage"] == "booked"
    assert [m["id"] for m in r2.media] == ["m5"]


def test_escalera_de_objeciones_hasta_3():
    estado = {"stage": "qualified", "greeted": True, "sent_media_ids": [], "price_objection_count": 0}
    niveles = []
    for _ in range(4):
        r = pipeline.run(NLU.normalize("sigue caro"), estado, [CASA], TENANT, _libres, LUNES)
        estado.update(r.cambios)
        niveles.append((r.cambios["price_objection_count"], r.alertas[0][1]))
    assert niveles == [(1, False), (2, False), (3, True), (3, True)]


def test_b2b_cerca_del_contado_en_ingles():
    t = NLU.normalize("whats the price on the premium plan cash? kinda pricey ngl budget is like 2k", items=[CASA, PREMIUM])
    r = pipeline.run(t, {"stage": "new", "sent_media_ids": []}, [CASA, PREMIUM], TENANT, None, LUNES)
    assert t.detected_language == "en" and "only 7% away" in r.texto and "$2,150" in r.texto


def test_no_interesado_cierra():
    r = pipeline.run(NLU.normalize("ya no me interesa gracias"), {"stage": "qualified"}, [CASA], TENANT, None, LUNES)
    assert r.cambios["stage"] == "lost" and not r.media
