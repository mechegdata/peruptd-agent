"""Estado en memoria del proceso (cachés y deduplicación). OJO: se pierde al reiniciar y no se comparte entre instancias."""


CALENDAR_CACHE = {"ts": 0, "text": ""}
PROCESSED_IDS = set()
PENDING_FORM_TIMERS = {}
ALERTA_ESTADO = {"chequeado": False}
MEDIA_ERROR = {}  # url -> último motivo de fallo
MEDIA_CACHE = {}  # url -> (media_id, timestamp). Los media_id de WhatsApp duran 30 días; se renuevan cada 7.
GEMINI_ESTADO = {"endpoint_ok": None}
HUMANO_ACTIVO = {}
BUFFER_MENSAJES = {}   # sender -> {'textos': [...], 'turno': n} para juntar mensajes seguidos
IMAGEN_RESPONDIDA = {}  # sender -> timestamp de la última respuesta a una imagen/archivo sin texto
