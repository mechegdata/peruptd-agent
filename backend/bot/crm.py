"""Ficha viva del lead -> columnas de la tabla leads (siempre) -> CRM del cliente (si está activo).
Funciona con los 5 adaptadores (bot/crm_adapters). Lo que se envía al CRM sale del estado que el bot ya guardó en
leads.interes: etapa, forma de pago, presupuesto, objeciones, idioma, producto, cita (y su reprogramación), asistencia
('vino' / 'no vino') y un resumen del chat como nota. Es idempotente: guarda los Ids del CRM y una firma de lo último
enviado en el propio lead, así que si nada cambió no llama a la API. Nunca interrumpe la conversación."""
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone

from bot import playbooks, tenant
from bot.config import CRM_SYNC_ACTIVO, DURACION_VISITA_MIN
from bot.crm_adapters import adaptador
from bot.datos.leads import get_lead_by_sender_or_phone, safe_upsert_lead, tabla
from bot.db import supabase
from bot.nlp.financiamiento import resumen_financiero

UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)


def etapa_comercial(meta):
    """new | qualified | booked | visited | negotiation | no_show | won | lost"""
    if meta.get("vendido") or meta.get("stage") == "won":
        return "won"
    if meta.get("no_interesado") or meta.get("stage") == "lost":
        return "lost"
    if meta.get("visita_estado") == "realizada":
        try:
            if datetime.now(timezone.utc) - datetime.fromisoformat(meta.get("ts_visita_confirmada") or "") >= timedelta(days=10):
                return "negotiation"
        except ValueError:
            pass
        return "visited"
    if meta.get("visita_estado") == "no_asistio":
        return "no_show"
    if meta.get("cita_agendada"):
        return "booked"
    if meta.get("fin_modalidad") or meta.get("presupuesto_tope") or meta.get("payment_method") or meta.get("stated_budget"):
        return "qualified"
    return "new"


def telefono_visible(valor):
    """Los clientes de Twilio se guardan como 'sms:+1512…' / 'twa:+1512…': al CRM va solo el número."""
    return re.sub(r"^(sms|twa):", "", str(valor or ""))


def ficha(lead, meta):
    etapa = etapa_comercial(meta)
    pago = meta.get("payment_method") or ({"contado": "CASH", "credito": "FINANCING"}.get(meta.get("fin_modalidad")))
    return {
        "sender_id": lead.get("sender_id"), "nombre": lead.get("nombre"), "telefono": telefono_visible(lead.get("telefono") or lead.get("sender_id")),
        "etapa": etapa, "etapa_crm": playbooks.valor(f"crm.etapas.{etapa}"), "pago": pago,
        "presupuesto": meta.get("stated_budget") or meta.get("presupuesto_tope"),
        "objeciones": int(meta.get("price_objection_count") or meta.get("objecion_precio_n") or 0),
        "idioma": meta.get("preferred_language") or "es", "canal": meta.get("canal_origen") or lead.get("canal"),
        "producto": meta.get("producto_nombre"), "producto_crm_id": meta.get("producto_crm_id"),
        "empresa": playbooks.valor("crm.empresa_por_defecto", "Individual"),
        "descripcion": (f"Atendido por PeruPTD AI Sales Agent. Etapa: {etapa} | Pago: {pago or resumen_financiero(meta) or 'sin dato'} | "
                        f"Presupuesto: {meta.get('stated_budget') or meta.get('presupuesto_tope') or 'sin dato'} | "
                        f"Objeciones de precio: {meta.get('price_objection_count') or meta.get('objecion_precio_n') or 0}"),
        "crm_id": meta.get("crm_id") or meta.get("sf_lead_id"),
    }


def escribir_columnas(lead, meta):
    """Columnas consultables de la ficha viva (migración 003). Si aún no existen, no pasa nada."""
    if not supabase or not lead.get("sender_id"):
        return
    enviados = [m for m in (meta.get("sent_media_ids") or []) if UUID_RE.match(str(m))]
    datos = {"stage": etapa_comercial(meta), "payment_method": meta.get("payment_method"), "preferred_language": meta.get("preferred_language"),
             "stated_budget": meta.get("stated_budget") or meta.get("presupuesto_tope"), "channel_origin": meta.get("canal_origen") or lead.get("canal"),
             "price_objection_count": int(meta.get("price_objection_count") or meta.get("objecion_precio_n") or 0),
             "appointment_datetime": meta.get("fecha_cita") if meta.get("cita_agendada") else None,
             "appointment_status": meta.get("visita_estado") or ("scheduled" if meta.get("cita_agendada") else None),
             "interested_catalog_item_id": meta.get("interested_catalog_item_id") if UUID_RE.match(str(meta.get("interested_catalog_item_id") or "")) else None,
             "sent_media_ids": enviados, "external_crm_lead_id": meta.get("crm_id") or meta.get("sf_lead_id"),
             "last_client_message_at": meta.get("ts_ultimo_cliente"), "last_bot_message_at": meta.get("ts_ultimo_bot")}
    try:
        tabla("leads").update({k: v for k, v in datos.items() if v is not None}).eq("sender_id", lead["sender_id"]).execute()
    except Exception:
        pass


def _firma(datos):
    return hashlib.sha1(json.dumps(datos, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()[:16]


def _resumen_chat(sender_id, n=20):
    if not supabase:
        return ""
    try:
        filas = tabla("mensajes").select("rol,contenido").eq("sender_id", sender_id).order("created_at", desc=True).limit(n).execute().data or []
        return "\n".join(f"{'Cliente' if f.get('rol') == 'user' else 'Agente'}: {f.get('contenido')}" for f in reversed(filas))
    except Exception:
        return ""


def sincronizar_lead(sender_id, adapt=None):
    lead = get_lead_by_sender_or_phone(sender_id, sender_id)
    if not lead:
        return {}
    meta = json.loads(lead.get("interes") or "{}")
    escribir_columnas(lead, meta)
    t = tenant.actual()
    if t.get("crm_type", "peruptd_native") == "peruptd_native" or not CRM_SYNC_ACTIVO:
        return {}
    adapt = adapt or adaptador(t)
    f, cambios = ficha(lead, meta), {}
    firma = _firma({k: v for k, v in f.items() if k != "crm_id"})
    crm_id = f["crm_id"]
    if firma != meta.get("crm_firma") or not crm_id:
        nuevo = adapt.sincronizar_lead(f)
        if nuevo:
            crm_id = nuevo
            cambios.update(crm_id=nuevo, crm_firma=firma)
    if crm_id and meta.get("cita_agendada") and meta.get("fecha_cita") and meta.get("crm_cita_fecha") != meta["fecha_cita"]:
        asunto = playbooks.valor("crm.asunto_cita", "Visita - {nombre}").replace("{nombre}", lead.get("nombre") or "Cliente")
        cita = adapt.registrar_cita(crm_id, datetime.fromisoformat(meta["fecha_cita"]), DURACION_VISITA_MIN, asunto, f["descripcion"],
                                    t.get("address") or "", cita_id=meta.get("crm_cita_id"))
        if cita:
            if not meta.get("crm_cita_id"):
                adapt.registrar_nota(crm_id, f"Resumen del chat — {asunto}", _resumen_chat(lead.get("sender_id")))
            cambios.update(crm_cita_id=cita, crm_cita_fecha=meta["fecha_cita"])
    estado = meta.get("visita_estado")
    cita_id = cambios.get("crm_cita_id") or meta.get("crm_cita_id")
    if cita_id and estado in ("realizada", "no_asistio") and meta.get("crm_asistencia") != estado:
        if adapt.marcar_asistencia(cita_id, estado == "realizada", f"Asesor: {'vino' if estado == 'realizada' else 'no vino'}"):
            cambios["crm_asistencia"] = estado
    if cambios:
        safe_upsert_lead(lead.get("sender_id"), lead.get("canal") or "whatsapp", lead.get("nombre"), lead.get("telefono"), cambios, "")
    return cambios


def sincronizar_seguro(sender_id):
    """Punto de entrada para el resto del bot: nunca lanza errores."""
    if not sender_id:
        return {}
    try:
        return sincronizar_lead(sender_id)
    except Exception as e:
        print(f"Error sincronizando {sender_id} con el CRM (la conversación sigue normal):", e)
        return {}
