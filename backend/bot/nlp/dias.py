"""Qué días puede el cliente, dicho de mil formas: 'no puedo entre semana', 'solo los sábados', 'de lunes a viernes trabajo',
'el fin de semana no', 'puedo martes o jueves', 'cualquier día menos el lunes'."""
import re

from bot.nlp.patrones import DIAS_IDX
from bot.utils.texto import limpiar_texto

FIN_DE_SEMANA = {5, 6}
ENTRE_SEMANA = {0, 1, 2, 3, 4}
TODOS = FIN_DE_SEMANA | ENTRE_SEMANA

_NEG = r"(?:no puedo|no podria|no podre|no me (?:da|queda|acomoda|alcanza)|imposible|complicad\w*|dificil|no tengo tiempo|trabajo|estoy ocupad\w*|estudio|no)"
_SEMANA = r"(?:entre semana|en la semana|de lunes a viernes|dias? de semana|dias? utiles|dias? laborables|lunes a viernes)"
_FINDE = r"(?:fin(?:es)? de semana|finde|sabados? (?:y|o) domingos?|domingos? (?:y|o) sabados?)"
_DIA_RX = r"(lunes|martes|miercoles|jueves|viernes|sabados?|domingos?)"


def _dia(nombre):
    return DIAS_IDX[nombre[:-1] if nombre in ("sabados", "domingos") else nombre]


def _negado(t, grupo_rx):
    """'no puedo entre semana' / 'entre semana no' / 'entre semana trabajo' / 'menos el lunes'."""
    return bool(re.search(rf"\b{_NEG}\b[^.,;?]{{0,25}}\b{grupo_rx}", t)
                or re.search(rf"\b{grupo_rx}\b[^.,;?]{{0,12}}\b(?:no|imposible|trabajo|estoy ocupad\w*|es complicado|no puedo)\b", t)
                or re.search(rf"\b(?:menos|excepto|salvo)\s+(?:el |los |la )?{grupo_rx}", t))


def _dia_negado(t, dia):
    """Negación pegada al día: 'no puedo el lunes', 'menos el lunes', 'el lunes no', 'los sábados trabajo'."""
    return bool(re.search(rf"\b(?:no puedo|no podria|no|imposible|menos|excepto|salvo|tampoco)\s+(?:el |los |la |este |ese )?{dia}\b", t)
                or re.search(rf"\b{dia}\s+(?:no|tampoco|imposible|trabajo|no puedo)\b", t))


def preferencia_dias(texto):
    """Devuelve (dias_permitidos: set | None, dias_negados: set). None = no dijo nada de días."""
    t = " " + limpiar_texto(texto) + " "
    negados = set()
    # Grupos (semana / fin de semana)
    if re.search(rf"\b{_SEMANA}\b", t) and _negado(t, _SEMANA):
        negados |= ENTRE_SEMANA
    if re.search(rf"\b{_FINDE}\b", t) and _negado(t, _FINDE):
        negados |= FIN_DE_SEMANA
    # Días sueltos
    positivos = set()
    t_dias = re.sub(rf"\b(?:{_SEMANA}|{_FINDE})\b", " ", t)  # 'de lunes a viernes' no son dos días sueltos
    for m in re.finditer(rf"\b{_DIA_RX}\b", t_dias):
        d = _dia(m.group(1))
        if _dia_negado(t_dias, m.group(1)):
            negados.add(d)
        else:
            positivos.add(d)
    if negados and not positivos:
        return (TODOS - negados) or None, negados
    if positivos - negados:
        return positivos - negados, negados
    if re.search(rf"\b{_FINDE}\b|\bsolo (?:puedo )?(?:los )?(?:sabados|domingos)\b", t):
        return FIN_DE_SEMANA, negados
    if re.search(rf"\b{_SEMANA}\b", t):
        return ENTRE_SEMANA, negados
    return None, negados


def describir_dias(dias):
    """{5, 6} -> 'el fin de semana'; {1, 3} -> 'el martes o el jueves'."""
    if dias == FIN_DE_SEMANA:
        return "el fin de semana"
    if dias == ENTRE_SEMANA:
        return "entre semana"
    nombres = {v: k for k, v in DIAS_IDX.items()}
    nombres[2], nombres[5] = "miércoles", "sábado"
    lista = [f"el {nombres[d]}" for d in sorted(dias)]
    return lista[0] if len(lista) == 1 else ", ".join(lista[:-1]) + " o " + lista[-1]
