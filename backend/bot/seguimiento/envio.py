"""Envío de seguimientos respetando la ventana de 24 h (texto libre / plantilla / manual)."""
from datetime import timedelta

import requests

from bot.canales.alertas import alertar_asesor
from bot.canales.material import send_requested_wa_media
from bot.canales.twilio_adapter import sin_ventana_24h
from bot.canales.whatsapp import send_wa_text
from bot.config import GRAPH_URL, TPL, VENTANA_WA_HORAS, WA_PHONE_ID, WA_TOKEN
from bot.db import supabase
from bot.utils.fechas import _ahora, _ts
from bot.utils.telefono import destino_wa


def _guardar_historial(phone, texto):
    if supabase:
        try:
            supabase.table("mensajes").insert([{"sender_id": phone, "canal": "whatsapp_seguimiento", "rol": "assistant", "contenido": texto}]).execute()
        except Exception as e:
            print("Error guardando seguimiento en historial:", e)


def enviar_seguimiento(lead, meta, texto, plantilla=None, params=None, media=None):
    """Dentro de 24 h: mensaje libre (gratis). Fuera: plantilla aprobada si existe. Si no, le pasa el texto al asesor para que lo envíe."""
    phone = lead.get("telefono") or lead.get("sender_id")
    nombre = lead.get("nombre") or ""
    ult_cli = _ts(meta.get("ts_ultimo_cliente"))
    dentro_ventana = bool(ult_cli and (_ahora() - ult_cli) < timedelta(hours=VENTANA_WA_HORAS)) or sin_ventana_24h(phone)  # el SMS no tiene ventana
    if dentro_ventana and send_wa_text(phone, texto):
        _guardar_historial(phone, texto)
        if media:
            send_requested_wa_media(phone, dict(media, _nombre=nombre, _msg_cliente="[Seguimiento automático]"))
        return "enviado"
    tpl = TPL.get(plantilla or "", "")
    if tpl:
        try:
            r = requests.post(
                f"{GRAPH_URL}/{WA_PHONE_ID}/messages",
                headers={"Authorization": f"Bearer {WA_TOKEN}"},
                json={"messaging_product": "whatsapp", **destino_wa(phone), "type": "template",
                      "template": {"name": tpl, "language": {"code": "es"},
                                   "components": [{"type": "body", "parameters": [{"type": "text", "text": str(p)[:200]} for p in (params or [])]}]}},
                timeout=15)
            if r.status_code == 200:
                _guardar_historial(phone, f"[Plantilla {tpl}] {texto}")
                return "plantilla"
            print(f"Plantilla {tpl} rechazada: HTTP {r.status_code} {r.text[:300]}")
        except Exception as e:
            print("Error enviando plantilla de seguimiento:", e)
    adjuntos = ""
    if media:
        adjuntos = "\n\n📎 Adjúntale también: " + ", ".join(
            n for n, k in [("los planos (ficha técnica)", "enviar_ficha_tecnica"), ("los 2 renders de cocina", "enviar_renders_cocina"),
                           ("una foto de la casa", "recursos")] if media.get(k))
    alertar_asesor(f"✍️ SEGUIMIENTO PARA ENVIAR A MANO a {nombre} (+{phone}) — ya pasaron las 24 h gratis de WhatsApp. "
                   f"Cópiale este mensaje:\n\n{texto}{adjuntos}")
    return "manual"
