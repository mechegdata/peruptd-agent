"""Seguimiento diferido (90 s) a leads de formularios Lead Ads. La espera queda registrada en Supabase (scheduled_jobs):
si el contenedor se reinicia antes de los 90 s, /cron envía el saludo en su siguiente pasada (sin duplicarlo)."""
import json
from datetime import datetime, timedelta, timezone
import threading

from bot.canales.material import send_requested_wa_media
from bot.canales.messenger import send_meta_dm
from bot.canales.whatsapp import send_wa_template, send_wa_text
from bot.config import LEADAD_ESPERA_SEG, OWNER_WA
from bot.conversacion.formulario import bienvenida_reciente, marcar_bienvenida, texto_formulario
from bot.conversacion.recursos import material_de_tipo
from bot.crm import sincronizar_seguro
from bot.datos import colas
from bot.datos.leads import get_lead_by_sender_or_phone, safe_upsert_lead
from bot.db import supabase
from bot.estado import PENDING_FORM_TIMERS


def _escribio_hace_poco(meta, minutos=30):
    try:
        return datetime.now(timezone.utc) - datetime.fromisoformat(meta.get("ts_ultimo_cliente") or "") < timedelta(minutes=minutos)
    except ValueError:
        return False


def delayed_leadgen_whatsapp(phone_norm, nombre, cocina, pago, presupuesto, psid_messenger=None):
    try:
        lead = get_lead_by_sender_or_phone(phone_norm, phone_norm)
        meta = {}
        if lead.get("interes"):
            try:
                meta = json.loads(lead["interes"])
            except Exception:
                pass
        if bienvenida_reciente(meta) or _escribio_hace_poco(meta):
            return  # ya recibió la bienvenida o está conversando por WhatsApp: no duplicarla

        msg_wa, flags = texto_formulario(nombre, cocina, pago, presupuesto, meta)
        ok = send_wa_text(phone_norm, msg_wa)
        if not ok:
            ok = send_wa_template(phone_norm, nombre, cocina, pago)

        if ok:
            marcar_bienvenida(meta)
            flags = dict(flags, recursos=material_de_tipo("ficha"))  # fichas por casa + render de la cocina elegida (sin la sala)
            if flags["recursos"]:
                flags["enviar_ficha_tecnica"] = False
            safe_upsert_lead(phone_norm, "whatsapp", nombre, phone_norm, meta, "[Formulario enviado a WhatsApp]")
            if supabase:
                try:
                    supabase.table("mensajes").insert([{"sender_id": phone_norm, "canal": "whatsapp", "rol": "assistant", "contenido": msg_wa}]).execute()
                except Exception:
                    pass
            send_requested_wa_media(phone_norm, dict(flags, _nombre=nombre, _msg_cliente="[Formulario]"))
        else:
            if psid_messenger:
                send_meta_dm(
                    psid_messenger,
                    f"¡Hola, {nombre}! Intentamos enviarte los planos y el render de tu cocina {cocina} al número +{phone_norm} de tu registro, "
                    "pero no nos permitió abrir WhatsApp (a veces Facebook carga un número antiguo). "
                    "¿Me confirmas por aquí tu número actual de WhatsApp o nos escribes directo tocando aquí?: https://wa.me/51986339051"
                )
            send_wa_text(
                OWNER_WA,
                f"Alerta Lead Formulario SAGUE: {nombre} (+{phone_norm}) llenó el formulario ({pago} | {cocina}), pero el envío automático a WhatsApp rebotó. Escríbele o llámalo."
            )
    except Exception as e:
        print("Error en delayed_leadgen_whatsapp:", e)


def schedule_form_followup(phone_norm, nombre, cocina, pago, presupuesto, psid_messenger=None):
    if not phone_norm:
        return
    sincronizar_seguro(phone_norm)  # el Lead aparece en Salesforce apenas llega el formulario (si está activo)
    if phone_norm in PENDING_FORM_TIMERS:
        try:
            PENDING_FORM_TIMERS[phone_norm].cancel()
        except Exception:
            pass
    payload = {"phone_norm": phone_norm, "nombre": nombre, "cocina": cocina, "pago": pago, "presupuesto": presupuesto,
               "psid_messenger": psid_messenger}
    tarea_id = colas.programar_tarea("lead_ad", phone_norm, payload, LEADAD_ESPERA_SEG)
    timer = threading.Timer(LEADAD_ESPERA_SEG, _ejecutar_si_le_toca, args=(tarea_id, payload))
    timer.daemon = True
    PENDING_FORM_TIMERS[phone_norm] = timer
    timer.start()


def _ejecutar_si_le_toca(tarea_id, payload):
    """El timer en memoria solo envía si la tarea sigue pendiente (no la tomó /cron ni otra instancia)."""
    if colas.reclamar_tarea(tarea_id):
        delayed_leadgen_whatsapp(**payload)


def ejecutar_leadads_vencidos():
    """Para /cron: saludos de Lead Ads cuyo timer se perdió en un reinicio."""
    hechos = 0
    for fila in colas.tareas_vencidas("lead_ad", gracia_seg=60):
        delayed_leadgen_whatsapp(**(fila.get("payload") or {}))
        hechos += 1
    return hechos
