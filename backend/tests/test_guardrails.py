"""Guardas por cliente: cada playbook cumple el esquema, el agente nunca envía sus frases prohibidas y ningún precio al
contado del catálogo baja del mínimo negociable que autorizó el cliente."""
import json
from datetime import datetime
from pathlib import Path

import pytest

from bot.engines import guardas, pipeline
from bot.nlu_normalizer import SemanticNormalizer
from tests.test_motores_catalogo import CASA, _libres

CARPETA = Path(__file__).resolve().parent.parent / "playbooks"
PLAYBOOKS = sorted(p.name for p in CARPETA.glob("playbook_*.json"))
ESQUEMA = json.loads((CARPETA / "schema.json").read_text(encoding="utf-8"))
NLU = SemanticNormalizer(usar_llm=False)

CATALOGOS = {   # catálogo de demostración de cada playbook (en producción vive en catalog_items)
    "playbook_sague_realestate.json": [dict(CASA, list_price=135000, cash_price=130000)],
    "playbook_us_realestate.json": [dict(CASA, id="mr1", name_en="Townhome B", list_price=485000, cash_price=470000, annual_rate_pct=6.75, max_term_years=30)],
    "playbook_us_medspa_clinic.json": [{"id": "dn1", "name_en": "Full-Arch Implants", "name_es": "Implantes", "keywords": ["implant", "implante", "pkg"],
                                        "list_price": 18500, "cash_price": 16900, "currency": "USD", "min_down_payment_pct": 10,
                                        "recommended_down_payment_pct": 20, "annual_rate_pct": 9.9, "max_term_years": 3,
                                        "value_comparison_en": "Avg. Miami price is $23,900 per arch", "media": []}],
}
TURNOS = ["ola q tal cuanto sale al cntado?", "ta salado tngo 25 mil nomas", "sigue caro", "muy caro, último precio?",
          "hm for the unit? ngl sounds steep", "only got 25k down, payment plans?", "can i tour tmrw after work round 6?", "2"]


def _cargar(nombre):
    return json.loads((CARPETA / nombre).read_text(encoding="utf-8"))


@pytest.mark.parametrize("nombre", PLAYBOOKS)
def test_playbook_cumple_esquema(nombre):
    pb = _cargar(nombre)
    for clave in ESQUEMA["required"]:
        assert clave in pb, f"{nombre}: falta '{clave}'"
    for clave in ESQUEMA["properties"]["negocio"]["required"]:
        assert pb["negocio"].get(clave), f"{nombre}: falta negocio.{clave}"
    assert pb["industria"] in ESQUEMA["properties"]["industria"]["enum"]
    assert pb["frases_prohibidas"] and all(isinstance(f, str) and f.strip() for f in pb["frases_prohibidas"])
    assert all(isinstance(v, bool) for v in (pb.get("interruptores") or {}).values())


@pytest.mark.parametrize("nombre", PLAYBOOKS)
def test_precio_contado_nunca_bajo_el_minimo(nombre):
    minimo = _cargar(nombre)["precio_minimo_negociable"]
    for item in CATALOGOS[nombre]:
        assert (item.get("cash_price") or item["list_price"]) >= minimo, f"{item.get('name_es')}: contado bajo el mínimo autorizado"


@pytest.mark.parametrize("nombre", PLAYBOOKS)
def test_el_agente_nunca_envia_frases_prohibidas(nombre):
    pb = _cargar(nombre)
    estado = {"stage": "new", "sent_media_ids": []}
    tenant = {"name": pb["negocio"]["nombre"], "bot_name": pb["negocio"]["bot"], "advisor_name": pb["negocio"]["asesor"]}
    ultimo = ""
    for texto in TURNOS:
        r = pipeline.run(NLU.normalize(texto, items=CATALOGOS[nombre], idioma_anterior=estado.get("preferred_language")),
                         estado, CATALOGOS[nombre], tenant, _libres, datetime(2026, 11, 16, 10))
        final, _ = guardas.aplicar(r.texto or "ok", pb["frases_prohibidas"], ultimo)
        for frase in pb["frases_prohibidas"]:
            assert frase.lower() not in final.lower(), f"{nombre}: el agente dijo '{frase}' ante '{texto}'"
        estado.update(r.cambios)
        ultimo = final


def test_guarda_quita_la_oracion_prohibida():
    texto, halladas = guardas.quitar_prohibidas("La casa está lista. Es un remate total. Te espero el sábado.", ["remate"])
    assert halladas == ["remate"] and "remate" not in texto and "Te espero el sábado." in texto


def test_anti_repeticion():
    previo = "Es normal comparar 🙂 A US$645/m² estás 22% bajo el promedio.\n\nCon US$25,000 de inicial..."
    nuevo = "Es normal comparar 🙂 A US$645/m² estás 22% bajo el promedio.\n\nRevisé la agenda real: 1️⃣ Mañana · 7:00 p. m."
    assert guardas.sin_repetir(nuevo, previo) == "Revisé la agenda real: 1️⃣ Mañana · 7:00 p. m."
    assert guardas.sin_repetir(previo, previo) == previo   # si todo se repetía, no se queda callado
