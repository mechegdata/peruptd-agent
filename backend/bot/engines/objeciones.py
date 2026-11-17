"""Motor de objeción "Está caro" / "Too expensive" en 3 niveles.
  1: empatía + argumento de valor del catálogo + multimedia PRICE_OBJECTION + alerta suave al asesor
  2: invitación a ver/evaluar sin compromiso + alerta "buen momento para llamarle"
  3: escala al propietario / ejecutivo senior, deja de insistir y alerta urgente"""
from bot.engines.textos import L, campo, nombre


def responder(item, nivel, idioma, asesor):
    nivel = max(1, min(3, nivel))
    n = nombre(item, idioma)
    if nivel == 1:
        return {"nivel": 1, "trigger": "PRICE_OBJECTION", "urgente": False,
                "alerta": L(idioma, f"Price objection 1/3 handled ({n}) — FYI", f"Objeción de precio 1/3 atendida ({n}) — para tu información"),
                "texto": L(idioma, f"Totally fair to compare 🙂 {campo(item, 'value_comparison', 'en')}.", f"Es normal comparar 🙂 {campo(item, 'value_comparison', 'es')}.")}
    if nivel == 2:
        return {"nivel": 2, "trigger": None, "urgente": False,
                "alerta": L(idioma, f"Price objection 2/3 ({n}) — good time to call this lead", f"Objeción de precio 2/3 ({n}) — buen momento para llamarle"),
                "texto": L(idioma, "No pressure at all — come see it in person, zero commitment. Most people decide once they see it.",
                           "Sin compromiso: ven a verlo en persona. La mayoría decide recién cuando lo ve.")}
    return {"nivel": 3, "trigger": None, "urgente": True,
            "alerta": L(idioma, f"URGENT: price objection 3/3 ({n}) — escalated to {asesor}", f"URGENTE: objeción de precio 3/3 ({n}) — escalado a {asesor}"),
            "texto": L(idioma, f"I understand. I've asked {asesor} to personally review options for you — they'll reach out today.",
                       f"Te entiendo. Le pedí a {asesor} que revise personalmente opciones para ti; te escribe hoy.")}
