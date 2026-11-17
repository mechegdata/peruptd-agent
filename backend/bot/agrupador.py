"""Junta los mensajes que el cliente manda seguidos ('De un piso noms' / 'Quiero' / 'No me alcanza para más')
para responder UNA sola vez a todo, como lo haría una persona. Los fragmentos se guardan en Supabase
(debounce_batches) para sobrevivir a un reinicio; sin esa tabla se usa la memoria del proceso (como antes)."""
import re
import threading
import time

from bot.config import AGRUPAR_MENSAJES_SEG
from bot.datos import colas
from bot.estado import BUFFER_MENSAJES
from bot.utils.texto import limpiar_texto

_LOCK = threading.Lock()
# Mensajes que casi siempre vienen seguidos de otro: "Buenos días" -> "¿Dónde están ubicados exactamente?"
_INCOMPLETO_RX = re.compile(r"^(hola+|holi+|ola|alo|buen[oa]s?( (dias|tardes|noches))?|hola,? buen[oa]s?( (dias|tardes|noches))?|"
                            r"saludos|disculpe|disculpa|una consulta|una pregunta|consulta|oiga|senor\w*|senorita|ingeniero|amigo|amiga)$")


def segundos_de_espera(texto, base=None):
    """WhatsApp no avisa si el cliente sigue escribiendo: se espera más tras un saludo suelto o un mensaje cortado."""
    base = AGRUPAR_MENSAJES_SEG if base is None else base
    t = re.sub(r"[^\w\s]", "", limpiar_texto(texto)).strip()
    crudo = (texto or "").strip()
    if _INCOMPLETO_RX.match(t) or crudo.endswith((",", "...", ":")):
        return base * 2.5   # ~15 s
    return base


def esperar_y_agrupar(sender, texto, canal="whatsapp", perfil="", base=None):
    """Devuelve el texto combinado si a esta llamada le toca responder, o None si llegó otro mensaje después (ese responde)."""
    if AGRUPAR_MENSAJES_SEG <= 0:
        return texto
    espera = segundos_de_espera(texto, base)
    mi_id = colas.encolar_fragmento(sender, texto, canal, perfil, espera)
    if mi_id is not None:
        time.sleep(espera)
        return colas.reclamar_lote(sender, mi_id, texto)
    return _agrupar_en_memoria(sender, texto, espera)


def _agrupar_en_memoria(sender, texto, espera):
    with _LOCK:
        buf = BUFFER_MENSAJES.setdefault(sender, {"textos": [], "turno": 0})
        buf["textos"].append(texto)
        buf["turno"] += 1
        mi_turno = buf["turno"]
    time.sleep(espera)
    with _LOCK:
        buf = BUFFER_MENSAJES.get(sender)
        if not buf or buf["turno"] != mi_turno:
            return None  # el cliente siguió escribiendo: responde la llamada del último mensaje
        textos = BUFFER_MENSAJES.pop(sender)["textos"]
    return "\n".join(textos)
