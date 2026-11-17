"""Adaptador Twilio (SMS y WhatsApp vía Twilio) para EE. UU. / Canadá.
Los clientes que entran por Twilio se identifican con un prefijo en su sender_id: 'sms:+15125550148' (SMS) o
'twa:+15125550148' (WhatsApp de Twilio). send_wa_text / send_wa_media miran ese prefijo y envían por aquí, así que toda
la fila de motores, los seguimientos y las alertas funcionan igual que con WhatsApp Cloud API.
El SMS no tiene ventana de 24 h: los seguimientos se envían directo (Twilio gestiona STOP / opt-out por ley)."""
import base64
import hashlib
import hmac
import re

import requests

from bot.config import TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_SMS_FROM, TWILIO_WA_FROM

PREFIJOS = ("sms:", "twa:")


def es_destino_twilio(destino):
    return str(destino or "").startswith(PREFIJOS)


def sin_ventana_24h(destino):
    return str(destino or "").startswith("sms:")


def sender_id(desde):
    """'whatsapp:+1512...' -> 'twa:+1512...' ; '+1512...' -> 'sms:+1512...'"""
    desde = str(desde or "").strip()
    if desde.startswith("whatsapp:"):
        return "twa:" + desde.split(":", 1)[1]
    return "sms:" + desde


def _para_twilio(destino):
    canal, numero = str(destino).split(":", 1)
    return (f"whatsapp:{numero}", TWILIO_WA_FROM) if canal == "twa" else (numero, TWILIO_SMS_FROM)


def texto_sms(texto):
    """El SMS no interpreta *negritas* de WhatsApp."""
    return re.sub(r"\*([^*\n]+)\*", r"\1", texto or "")


def _enviar(destino, datos):
    if not (TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN):
        print("Twilio no configurado: no se envía a", destino)
        return False
    para, desde = _para_twilio(destino)
    campo_desde = "MessagingServiceSid" if str(desde).startswith("MG") else "From"
    try:
        r = requests.post(f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/Messages.json",
                          auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN), data={"To": para, campo_desde: desde, **datos}, timeout=15)
    except Exception as e:
        print(f"Excepción enviando por Twilio a {para}:", e)
        return False
    if r.status_code >= 300:
        print(f"Twilio rechazó el mensaje a {para}: HTTP {r.status_code} {r.text[:300]}")
    return r.status_code < 300


def enviar_texto(destino, texto):
    if not destino or not texto:
        return False
    cuerpo = texto_sms(texto) if destino.startswith("sms:") else texto
    return _enviar(destino, {"Body": cuerpo[:1600]})


def enviar_media(destino, url, leyenda=""):
    """MMS / WhatsApp con archivo (URL pública). En SMS, si el operador no soporta MMS, Twilio envía el enlace."""
    if not destino or not url:
        return False
    return _enviar(destino, {"MediaUrl": url, "Body": texto_sms(leyenda)[:1600]})


def firma_valida(url, params, firma):
    """X-Twilio-Signature = Base64(HMAC-SHA1(auth_token, url + parámetros POST ordenados concatenados))."""
    if not TWILIO_AUTH_TOKEN or not firma:
        return False
    datos = url + "".join(f"{k}{params[k]}" for k in sorted(params))
    esperado = base64.b64encode(hmac.new(TWILIO_AUTH_TOKEN.encode(), datos.encode(), hashlib.sha1).digest()).decode()
    return hmac.compare_digest(esperado, firma)


def normalizar_entrante(form):
    """Formulario de Twilio -> datos con la misma forma que un mensaje de WhatsApp Cloud API."""
    desde = form.get("From", "")
    n_media = int(form.get("NumMedia") or 0)
    return {"sender_id": sender_id(desde), "texto": (form.get("Body") or "").strip(), "msg_id": form.get("MessageSid") or form.get("SmsSid"),
            "perfil": form.get("ProfileName") or "", "tipo": "text" if (form.get("Body") or "").strip() else ("image" if n_media else "text"),
            "canal_origen": "WhatsApp (Twilio)" if desde.startswith("whatsapp:") else "SMS (Twilio)"}
