"""Bandeja de prueba del AI Sales Hub: los clientes simulados del Hub usan sender_id 'hub:+1999...'. Lo que el agente
les "envía" queda aquí (no sale por WhatsApp/SMS), y el Hub lo lee en la respuesta de /api/hub/chat."""
import threading

_LOCK = threading.Lock()
_BANDEJA = {}
MAX_POR_CLIENTE = 50


def es_simulado(destino):
    return str(destino or "").startswith("hub:")


def guardar(destino, tipo, contenido, extra=None):
    with _LOCK:
        lista = _BANDEJA.setdefault(str(destino), [])
        lista.append({"tipo": tipo, "contenido": contenido, **(extra or {})})
        del lista[:-MAX_POR_CLIENTE]
    return True


def vaciar(destino):
    with _LOCK:
        return _BANDEJA.pop(str(destino), [])
