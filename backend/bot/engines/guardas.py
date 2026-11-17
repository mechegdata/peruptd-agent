"""Guardas finales de la respuesta (Capa 3): frases prohibidas del playbook y anti-repetición (>= 80 % de similitud
con el último mensaje del agente). Se aplican a todo texto antes de enviarlo."""
import re
from difflib import SequenceMatcher

from bot.nlu.lexico import sin_tildes

UMBRAL_REPETICION = 0.8


def quitar_prohibidas(texto, prohibidas):
    """Elimina la oración que contiene una frase prohibida. Devuelve (texto, [frases encontradas])."""
    encontradas = [p for p in prohibidas or [] if sin_tildes(p) in sin_tildes(texto)]
    if not encontradas:
        return texto, []
    oraciones = re.split(r"(?<=[.!?])\s+|\n", texto)
    limpias = [o for o in oraciones if not any(sin_tildes(p) in sin_tildes(o) for p in encontradas)]
    return "\n".join(o for o in limpias if o.strip()).strip(), encontradas


def similitud(a, b):
    return SequenceMatcher(None, sin_tildes(a or ""), sin_tildes(b or "")).ratio()


def sin_repetir(texto, ultimo_del_agente):
    """Si un párrafo ya se dijo tal cual en el último mensaje, se omite (salvo que no quede nada)."""
    if not ultimo_del_agente:
        return texto
    previos = [p.strip() for p in ultimo_del_agente.split("\n\n")]
    parrafos = [p for p in texto.split("\n\n") if all(similitud(p.strip(), q) < UMBRAL_REPETICION for q in previos)]
    return "\n\n".join(parrafos) if parrafos else texto


def aplicar(texto, prohibidas, ultimo_del_agente):
    texto = sin_repetir(texto, ultimo_del_agente)
    return quitar_prohibidas(texto, prohibidas)
