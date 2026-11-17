"""Capa 1 · NLU bilingüe: jergas, typos, Spanglish y mensajes partidos -> NormalizedTurn validado."""
import time

from bot.nlu_normalizer import NormalizedTurn, SemanticNormalizer

CASA = {"id": "re1", "name_es": "Casa de 3 pisos", "keywords": ["casa", "house", "3br", "3-bedroom", "unit", "ksa"]}
PREMIUM = {"id": "b1", "name_es": "Servicio Premium", "keywords": ["premium", "premiun", "servicio", "plan", "maintenance"]}
IMPLANTE = {"id": "dn1", "name_es": "Implantes All-on-4", "keywords": ["implant", "implants", "implante", "implantes", "pkg", "package"]}
NLU = SemanticNormalizer(usar_llm=False)


def test_jerga_peruana_del_documento():
    t = NLU.normalize("ola hno q tal, a cuanto sale el srvicio premiun al cntado?? ta medio salado ah, tngo 2 lucas nomas, "
                      "se podra ver mñn saliendo de la chamba tipo 6 y media?", items=[PREMIUM])
    assert t.detected_language == "es"
    assert t.primary_intent == "SCHEDULE_AND_PRICE_OBJECTION"
    for i in ("CASH_DISCOUNT", "OBJECTION_EXPENSIVE", "BUDGET_STATEMENT", "SCHEDULE_REQUEST"):
        assert i in t.intents
    e = t.entities
    assert (e.catalog_item_id, e.payment_type, e.budget_amount, e.price_objection) == ("b1", "CASH", 2000, True)
    assert (e.proposed_date_relative, e.proposed_time, e.work_end_hour) == ("TOMORROW", "18:30", "18:00")
    assert "2,000" in t.clean_text and "trabajo" in t.clean_text and "mañana" in t.clean_text
    assert any(s.startswith("hno") for s in t.regional_slang_detected)


def test_sms_ingles_del_documento():
    t = NLU.normalize("yo hm for the full arch pkg? ngl sounds kinda steep, yall do payment plans or nah? free this sat round 4ish",
                      items=[IMPLANTE])
    assert t.detected_language == "en"
    assert t.entities.payment_type == "FINANCING" and t.entities.price_objection
    assert (t.entities.proposed_date_relative, t.entities.proposed_time) == ("THIS_SATURDAY", "16:00")
    assert t.entities.catalog_item_id == "dn1"
    assert "how much" in t.clean_text.lower() and "expensive" in t.clean_text


def test_rafaga_partida_en_4_y_25k():
    t = NLU.normalize("yo\nhm for the 3br unit?\nngl sounds steep, only got 25k down\ncan i tour tmrw after work round 6?", items=[CASA])
    assert t.entities.budget_amount == 25000 and t.entities.catalog_item_id == "re1"
    assert t.entities.proposed_time == "18:00" and t.entities.work_end_hour == "17:30"


def test_eleccion_de_horario():
    assert NLU.normalize("2").entities.selected_slot_index == 2
    assert NLU.normalize("la segunda").entities.selected_slot_index == 2
    assert NLU.normalize("the third one").primary_intent == "SLOT_SELECTION"


def test_cambia_de_idioma_a_mitad_de_chat():
    assert NLU.normalize("cuanto cuesta la casa?", items=[CASA]).detected_language == "es"
    assert NLU.normalize("ok and how much is the down payment?", items=[CASA], idioma_anterior="es").detected_language == "en"


def test_llm_valido_se_combina_y_el_producto_sale_del_catalogo():
    def llm(_prompt, _seg):
        return {"detected_language": "es", "clean_text": "¿Cuánto cuesta la casa al contado?", "primary_intent": "PRICE_INQUIRY",
                "intents": ["PRICE_INQUIRY", "CASH_DISCOUNT", "INVENTADA"],
                "entities": {"service_keyword": "casa", "catalog_item_id": "id-inventado", "payment_type": "CASH"}}
    t = SemanticNormalizer(llamar_llm=llm, usar_llm=True).normalize("cuanto la ksa al cntado", items=[CASA])
    assert t.source == "llm+lexicon"
    assert t.entities.catalog_item_id == "re1"            # nunca el Id que inventó el LLM
    assert "INVENTADA" not in t.intents


def test_llm_invalido_o_caido_usa_el_lexico():
    for llm in (lambda p, s: {"detected_language": "fr", "clean_text": 1}, lambda p, s: (_ for _ in ()).throw(TimeoutError()), lambda p, s: None):
        t = SemanticNormalizer(llamar_llm=llm, usar_llm=True).normalize("ta salado tngo 25 mil", items=[CASA])
        assert t.source == "lexicon" and t.entities.budget_amount == 25000 and t.entities.price_objection


def test_lexico_es_rapido():
    t0 = time.time()
    for _ in range(200):
        NLU.normalize("ola q tal a cuanto sale la ksa al cntado?? ta medio salado ah tngo 25 mil nomas", items=[CASA])
    assert (time.time() - t0) / 200 < 0.02


def test_modelo_rechaza_basura():
    t = NormalizedTurn(detected_language="es", clean_text="x", primary_intent="NOPE", intents=["NOPE"])
    assert t.intents == ["GENERAL_INFO"] and t.primary_intent == "GENERAL_INFO"
