"""Webhook de Twilio (SMS y WhatsApp vía Twilio): POST /webhook/twilio.
Normaliza el mensaje al mismo formato que WhatsApp Cloud API y lo pasa por la misma fila de motores. Responde enseguida
con un TwiML vacío (Twilio corta a los 15 s) y atiende el mensaje en segundo plano: en Cloud Run ese servicio debe tener
la CPU siempre asignada (--no-cpu-throttling). Si el contenedor se reinicia, /cron termina el lote pendiente."""
import threading

from flask import Blueprint, Response, request

from bot.atencion import atender_mensaje_wa
from bot.canales import twilio_adapter
from bot.config import AGRUPAR_MENSAJES_SEG_SMS, TWILIO_EXIGIR_FIRMA, TWILIO_URL_PUBLICA
from bot.datos.idempotencia import ya_procesado

bp = Blueprint("twilio", __name__)
VACIO = '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'


@bp.route("/webhook/twilio", methods=["POST"])
def desde_twilio():
    form = request.form.to_dict()
    url = TWILIO_URL_PUBLICA or request.url
    if TWILIO_EXIGIR_FIRMA and not twilio_adapter.firma_valida(url, form, request.headers.get("X-Twilio-Signature", "")):
        return "Firma de Twilio inválida", 403
    m = twilio_adapter.normalizar_entrante(form)
    if not m["sender_id"] or ya_procesado(m["msg_id"], "twilio"):
        return Response(VACIO, mimetype="text/xml")
    threading.Thread(target=atender_mensaje_wa, daemon=True,
                     args=(m["sender_id"], m["texto"], m["perfil"], m["tipo"]),
                     kwargs={"canal": "whatsapp", "espera_base": AGRUPAR_MENSAJES_SEG_SMS, "canal_origen": m["canal_origen"]}).start()
    return Response(VACIO, mimetype="text/xml")
