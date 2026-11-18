"""Turno completo del agente para tenants en modo 'catalogo':
  texto agrupado -> Capa 1 (NLU bilingüe) -> Capa 2 (motores con el catálogo) -> Capa 3 (redacción + guardas)
  -> envío (WhatsApp / SMS) + multimedia -> calendario -> estado del lead -> alertas al asesor.
El estado comercial vive en leads.interes con las mismas claves que usa el resto del bot (cita_agendada, fecha_cita,
evento_id...), así que los comandos del asesor (vino / no vino / pausa), el rescate de 24 h y el protocolo de 14 días
siguen funcionando igual. La sincronización con el CRM la hace bot/crm.py después de responder."""
import json
from datetime import datetime, timezone

from bot import catalogo, playbooks, tenant
from bot.canales import hub_bandeja
from bot.canales.alertas import alertar_asesor
from bot.canales.whatsapp import send_wa_media, send_wa_text
from bot.config import LIMA_TZ
from bot.crm import telefono_visible
from bot.datos.leads import get_lead_by_sender_or_phone, safe_upsert_lead, tabla
from bot.db import supabase
from bot.engines import agenda, guardas, pipeline
from bot.engines.textos import L
from bot.integraciones.calendario import create_calendar_event, get_free_slots
from bot.nlu_normalizer import SemanticNormalizer

NORMALIZADOR = SemanticNormalizer()
TIPO_WA = {"image": "image", "pdf": "document", "video": "video"}


def _alertar(sender_id, texto):
    """Alerta al asesor por WhatsApp; en el Hub (cliente simulado) queda en la bandeja para mostrarla en pantalla."""
    if hub_bandeja.es_simulado(sender_id):
        hub_bandeja.guardar(sender_id, "alerta", texto)
    else:
        alertar_asesor(texto, tenant.actual().get("owner_whatsapp"))


def libres_en_horario(n=3, dia=None, filtro=None, excluir=None):
    """Horarios libres del calendario dentro del horario de visitas del cliente (playbook agenda.horario_visitas)."""
    h = playbooks.valor("agenda.horario_visitas") or {}
    ini, fin, dias = h.get("inicio", "00:00"), h.get("fin", "23:59"), h.get("dias")

    def dentro(dt):
        hhmm = dt.strftime("%H:%M")
        return ini <= hhmm <= fin and (dias is None or dt.weekday() in dias) and (filtro is None or filtro(dt))
    return get_free_slots(n=n, dia=dia, filtro=dentro, excluir=excluir)


def _historial(sender_id, n=8):
    if not supabase:
        return []
    try:
        filas = tabla("mensajes").select("rol,contenido").eq("sender_id", sender_id).order("created_at", desc=True).limit(n).execute().data or []
        return [{"rol": f["rol"], "texto": f["contenido"]} for f in reversed(filas)]
    except Exception:
        return []


def _guardar_mensajes(sender_id, texto_cliente, texto_agente, motores=""):
    if not supabase:
        return
    filas = [{"sender_id": sender_id, "canal": "whatsapp", "rol": "user", "contenido": texto_cliente}]
    if texto_agente:
        filas.append({"sender_id": sender_id, "canal": "whatsapp", "rol": "assistant", "contenido": texto_agente, "motor": motores or None})
    try:
        tabla("mensajes").insert(filas).execute()
    except Exception as e:
        print("No se pudo guardar el historial:", e)


def _reservar(res, lead, meta, idioma, t):
    """Crea el evento en el calendario. Devuelve (texto, cambios_meta)."""
    nombre = lead.get("nombre") or "Cliente"
    evento = playbooks.valor(f"agenda.nombre_evento_{idioma}", L(idioma, "visit", "visita"))
    simulado = hub_bandeja.es_simulado(lead.get("sender_id"))
    ok, detalle, ev_id = (True, "simulado", "hub-demo") if simulado else create_calendar_event(nombre, telefono_visible(lead.get("telefono") or lead.get("sender_id")), res.reservar.isoformat(),
                                               notas=f"PeruPTD AI Sales Agent · idioma {idioma}", titulo=f"{evento.capitalize()} - {nombre}",
                                               ubicacion=t.get("address"))
    if not ok:
        libres = agenda.proponer({}, libres_en_horario, datetime.now(LIMA_TZ))
        return (L(idioma, "That time was just taken 😅 ", "Ese horario se acaba de ocupar 😅 ") + agenda.texto_opciones(libres, {}, idioma, datetime.now(LIMA_TZ).date()),
                {"offered_slots": [s.isoformat() for s in libres], "stage": "qualified"})
    etiqueta = agenda.etiqueta(res.reservar, idioma, datetime.now(LIMA_TZ).date())
    _alertar(lead.get("sender_id"), f"📅 {evento.capitalize()} agendada: {nombre} ({telefono_visible(lead.get('sender_id'))}) — {etiqueta}")
    lugar = t.get("address") or ""
    return (L(idioma, f"Booked! ✅ Your {evento}: {etiqueta}\n📍 {lugar}\nI'll confirm with you 24h before.",
              f"¡Listo! ✅ Agendé tu {evento}: {etiqueta}\n📍 {lugar}\nTe confirmo 24 h antes.").replace("\n📍 \n", "\n"),
            {"cita_agendada": True, "fecha_cita": res.reservar.isoformat(), "evento_id": ev_id or "", "etapa": "agendado",
             "ts_cita_creada": datetime.now(timezone.utc).isoformat()})


def atender_turno(sender_id, texto, perfil="", canal_origen=None):
    """Responde un lote de mensajes ya agrupado. Devuelve el ResultadoTurno (para pruebas y registros)."""
    t = tenant.actual()
    lead = get_lead_by_sender_or_phone(sender_id, sender_id) or {}
    meta = json.loads(lead.get("interes") or "{}")
    items = catalogo.items()
    turno = NORMALIZADOR.normalize(texto, items, _historial(sender_id), meta.get("preferred_language") or t.get("default_language"))
    res = pipeline.run(turno, meta, items, t, buscar_libres=libres_en_horario, ahora=datetime.now(LIMA_TZ))
    idioma = turno.detected_language
    cambios = dict(res.cambios)
    texto_final = res.texto
    if res.reservar:
        texto_final, extra = _reservar(res, {**lead, "sender_id": sender_id}, meta, idioma, t)
        cambios.update(extra)
    ultimo = next((h["texto"] for h in reversed(_historial(sender_id, 4)) if h["rol"] == "assistant"), "")
    texto_final, prohibidas = guardas.aplicar(texto_final, playbooks.valor("frases_prohibidas", []), ultimo)
    if prohibidas:
        print(f"Guardas: se quitaron frases prohibidas {prohibidas}")
    enviado = send_wa_text(sender_id, texto_final)
    enviados = list(meta.get("sent_media_ids") or [])
    for m in res.media:
        if send_wa_media(sender_id, m.get("file_url"), TIPO_WA.get(m.get("media_type"), "document"), m.get(f"caption_{idioma}") or m.get("caption_es") or ""):
            enviados.append(str(m["id"]))
    for alerta, urgente in res.alertas:
        _alertar(sender_id, ("🚨 " if urgente else "ℹ️ ") + f"{lead.get('nombre') or telefono_visible(sender_id)}: {alerta}")
    ahora = datetime.now(timezone.utc).isoformat()
    item = next((i for i in items if str(i.get("id")) == cambios.get("interested_catalog_item_id")), None)
    cambios.update(sent_media_ids=enviados, ts_ultimo_cliente=ahora, ultimo_texto_cliente=texto[:300],
                   nlu_ultimo={"intents": turno.intents, "entities": turno.entities.model_dump(exclude_none=True), "source": turno.source})
    if item:
        cambios.update(producto_nombre=item.get("name_es"), producto_crm_id=item.get("external_crm_id"))
    if canal_origen:
        cambios["canal_origen"] = canal_origen
    if enviado:
        cambios["ts_ultimo_bot"] = ahora
    safe_upsert_lead(sender_id, "whatsapp", lead.get("nombre") or perfil or None, lead.get("telefono"), cambios, texto)
    _guardar_mensajes(sender_id, texto, texto_final if enviado else "", " · ".join(dict.fromkeys(m for m, _ in res.traza)))
    res.texto = texto_final
    res.nlu = turno
    return res
