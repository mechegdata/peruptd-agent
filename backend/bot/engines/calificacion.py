"""Motor de calificación por producto: según catalog_items.qualification_mode (credito_inicial, seguro_medico,
elegibilidad, b2b) y sus preguntas filtro (filter_questions), hace UNA pregunta por turno, solo si la respuesta del
agente no termina ya en otra pregunta, y deja de preguntar cuando el lead ya está calificado."""
from bot.engines.textos import L

POR_DEFECTO = {
    "credito_inicial": [{"es": "Para orientarte mejor: ¿piensas comprar al contado o con crédito? ¿Con cuánto contarías para la inicial?",
                         "en": "So I can guide you: are you paying cash or financing? How much would you put down?"}],
    "seguro_medico": [{"es": "¿Tienes seguro dental o médico (PPO), o prefieres pagar con financiamiento?",
                       "en": "Do you have dental or medical insurance (PPO), or would you rather use a payment plan?"}],
    "elegibilidad": [{"es": "¿Para cuándo lo necesitas? Así te confirmo si calificas.",
                      "en": "When would you need it? That way I can confirm you qualify."}],
    "b2b": [{"es": "¿El presupuesto ya está aprobado o están evaluando opciones? ¿Para cuándo necesitan implementarlo?",
             "en": "Is the budget already approved, or are you still exploring? When do you need it in place?"}],
}


def _calificado(modo, estado, cambios):
    datos = {**estado, **cambios}
    if modo == "elegibilidad":
        return False                     # se hacen todas las preguntas filtro del producto
    return bool(datos.get("payment_method") or datos.get("stated_budget") or datos.get("cita_agendada"))


def siguiente_pregunta(item, estado, cambios, idioma, ya_pregunta=False):
    modo = item.get("qualification_mode") or "credito_inicial"
    preguntas = [p for p in (item.get("filter_questions") or []) if isinstance(p, dict) and (p.get("es") or p.get("en"))] \
        or POR_DEFECTO.get(modo, POR_DEFECTO["credito_inicial"])
    hechas = list(estado.get("preguntas_filtro_hechas") or [])
    if ya_pregunta or _calificado(modo, estado, cambios) or len(hechas) >= len(preguntas):
        return None
    i = len(hechas)
    p = preguntas[i]
    return {"texto": L(idioma, p.get("en") or p.get("es"), p.get("es") or p.get("en")), "hechas": hechas + [i]}
