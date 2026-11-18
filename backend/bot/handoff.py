"""Detección de intervención humana (mensajes manuales del asesor) y pausa del bot."""
import json
import time
from datetime import datetime, timezone

from bot.config import PAUSA_BOT_TRAS_HUMANO_MIN
from bot.datos.leads import get_lead_by_sender_or_phone, safe_upsert_lead, tabla
from bot.db import supabase
from bot.datos.idempotencia import ya_procesado
from bot.estado import HUMANO_ACTIVO
from bot.utils.texto import limpiar_texto


def guardar_mensaje_manual(cliente_id, canal, texto, msg_id=None):
    """Guarda en el historial lo que el asesor humano escribió a mano, para que el bot lo tenga en cuenta.
    Los mensajes que envió el propio bot ya están guardados, así que se ignoran si coinciden."""
    if not supabase or not cliente_id or not texto:
        return
    if ya_procesado(msg_id, f"{canal}_eco"):
        return
    try:
        res = tabla("mensajes").select("rol,contenido,created_at").eq("sender_id", cliente_id) \
            .order("created_at", desc=True).limit(6).execute()
        for prev in res.data or []:
            if prev.get("rol") == "assistant" and limpiar_texto(prev.get("contenido"))[:300] == limpiar_texto(texto)[:300]:
                return  # es el eco de un mensaje del bot
        tabla("mensajes").insert([
            {"sender_id": cliente_id, "canal": f"{canal}_manual", "rol": "assistant", "contenido": texto, "motor": "Asesor (manual)"}
        ]).execute()
        print(f"Mensaje manual del asesor guardado para {cliente_id}: {texto[:80]!r}")
        try:
            lead_m = get_lead_by_sender_or_phone(cliente_id, cliente_id)
            if lead_m:
                meta_m = json.loads(lead_m.get("interes") or "{}")
                meta_m["ts_ultimo_manual"] = datetime.now(timezone.utc).isoformat()
                safe_upsert_lead(lead_m.get("sender_id"), lead_m.get("canal") or canal, lead_m.get("nombre"), lead_m.get("telefono"), meta_m, "")
        except Exception:
            pass
        if PAUSA_BOT_TRAS_HUMANO_MIN > 0:
            HUMANO_ACTIVO[cliente_id] = time.time()
    except Exception as e:
        print("Error guardando mensaje manual:", e)


def humano_atendiendo(cliente_id):
    """True si el asesor escribió a mano hace poco (memoria o lo guardado en el lead) o pausó el chat con 'pausa 51…'."""
    ts = HUMANO_ACTIVO.get(cliente_id)
    if ts and PAUSA_BOT_TRAS_HUMANO_MIN > 0 and time.time() - ts < PAUSA_BOT_TRAS_HUMANO_MIN * 60:
        return True
    try:
        lead = get_lead_by_sender_or_phone(cliente_id, cliente_id)
        meta = json.loads(lead.get("interes") or "{}") if lead else {}
    except Exception:
        return False
    if meta.get("seguimiento_pausado"):
        return True  # el asesor escribió "pausa 51…": ni seguimientos ni respuestas automáticas
    try:
        manual = datetime.fromisoformat(meta.get("ts_ultimo_manual") or "")
    except ValueError:
        return False
    if manual.tzinfo is None:
        manual = manual.replace(tzinfo=timezone.utc)
    return PAUSA_BOT_TRAS_HUMANO_MIN > 0 and (datetime.now(timezone.utc) - manual).total_seconds() < PAUSA_BOT_TRAS_HUMANO_MIN * 60
