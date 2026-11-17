"""Comandos del asesor por WhatsApp (vino / no vino / pausa / vendido / estado)."""
import json
import re
from datetime import datetime, timezone

from bot.config import LIMA_TZ
from bot.crm import sincronizar_seguro
from bot.datos.leads import get_lead_by_sender_or_phone, safe_upsert_lead
from bot.nlp.financiamiento import resumen_financiero
from bot.nlp.patrones import COMANDO_RE
from bot.utils.fechas import _ts, format_fecha_es
from bot.utils.telefono import normalize_pe_phone
from bot.utils.texto import limpiar_texto


def procesar_comando_asesor(texto):
    t = limpiar_texto(texto)
    if t in ["ayuda", "comandos", "menu bot"]:
        return ("🤖 Comandos del bot SAGUE (escríbelos aquí):\n• *vino 519XXXXXXXX* → la visita se realizó (activa el seguimiento post-visita)\n"
                "• *no vino 519XXXXXXXX* → le escribe para reprogramar\n• *pausa 519XXXXXXXX* / *activar 519XXXXXXXX* → el bot deja de responder y de hacer seguimientos a ese cliente (o los reanuda)\n"
                "• *vendido 519XXXXXXXX* → cierra el seguimiento\n• *estado 519XXXXXXXX* → resumen del cliente")
    m = COMANDO_RE.match(t)
    if not m:
        return None
    cmd, num = m.group(1).lower(), normalize_pe_phone(re.sub(r"\s", "", m.group(2)))
    lead = get_lead_by_sender_or_phone(num, num)
    for prefijo in ("sms:+", "twa:+"):  # clientes que escriben por Twilio (EE. UU./Canadá): su ID lleva el canal
        lead = lead or get_lead_by_sender_or_phone(prefijo + num)
    if not lead:
        return f"No encontré al cliente +{num} 🤔"
    meta = json.loads(lead.get("interes") or "{}")
    nombre = lead.get("nombre") or num
    if cmd in ["si vino", "vino", "realizada", "asistio"]:
        meta.update({"visita_estado": "realizada", "ts_visita_confirmada": datetime.now(timezone.utc).isoformat()})
        resp = f"✅ Anotado: {nombre} visitó las casas. En 45 min le envío el agradecimiento con el resumen y luego sigo el protocolo (48 h, día 5, 10 y 14)."
    elif cmd in ["no vino", "no asistio", "falto"]:
        meta["visita_estado"] = "no_asistio"
        resp = f"👍 Anotado: {nombre} no vino. En la próxima revisión le escribo para reprogramar."
    elif cmd in ["pausa", "pausar"]:
        meta["seguimiento_pausado"] = True
        resp = f"⏸️ Pausé los mensajes automáticos a {nombre}. (El bot igual le responde si escribe)."
    elif cmd in ["activar", "reanudar"]:
        meta["seguimiento_pausado"] = False
        resp = f"▶️ Reactivé el seguimiento automático de {nombre}."
    elif cmd in ["vendido", "vendida"]:
        meta.update({"vendido": True, "seguimiento_pausado": True})
        resp = f"🎉 ¡Felicitaciones! Cerré el seguimiento de {nombre}."
    else:
        c = _ts(meta.get("fecha_cita"))
        resp = (f"📋 {nombre} (+{num})\n• Pago: {resumen_financiero(meta) or 'sin dato'}\n• Cocina: {meta.get('estilo_cocina', 'sin elegir')}\n"
                f"• Cita: {format_fecha_es(c.astimezone(LIMA_TZ)) if c and meta.get('cita_agendada') else 'no'}\n"
                f"• Visita: {meta.get('visita_estado') or '—'} | Etapa: {meta.get('etapa') or '—'}\n"
                f"• Seguimiento: {'pausado' if meta.get('seguimiento_pausado') else 'activo'}")
    safe_upsert_lead(lead.get("sender_id"), lead.get("canal") or "whatsapp", lead.get("nombre"), lead.get("telefono"), meta, "")
    sincronizar_seguro(lead.get("sender_id"))  # vino / no vino -> Event en Salesforce (si está activo)
    return resp
