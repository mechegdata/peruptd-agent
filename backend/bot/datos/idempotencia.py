"""Deduplicación de avisos de Meta y Twilio: memoria del proceso + tabla processed_webhooks (sobrevive reinicios
y varias instancias de Cloud Run). Si Meta reentrega un mensaje tras un reinicio, el bot no responde dos veces."""
from bot.config import TENANT_ID
from bot.datos import persistencia
from bot.estado import PROCESSED_IDS


def ya_procesado(msg_id, canal=""):
    """True si este id ya se atendió. Si es nuevo, lo marca como atendido y devuelve False."""
    if not msg_id:
        return False
    msg_id = str(msg_id)
    if msg_id in PROCESSED_IDS:
        return True
    PROCESSED_IDS.add(msg_id)
    if not persistencia.disponible():
        return False
    try:
        persistencia.cliente().table("processed_webhooks").insert(
            {"message_id": msg_id, "tenant_id": TENANT_ID, "canal": canal or None}).execute()
    except Exception as e:
        if persistencia.es_duplicado(e):
            print(f"Aviso repetido ({canal or 'meta'} {msg_id[:40]}): ya se atendió antes (reinicio u otra instancia).")
            return True
        persistencia.desactivar(e)
    return False
