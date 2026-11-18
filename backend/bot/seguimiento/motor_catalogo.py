"""Seguimiento automático para tenants en modo 'catalogo' (cualquier industria, ES/EN). Misma lógica de tiempos que el
motor de SAGUE (recordatorio, pregunta al asesor a los 75 min, protocolo de 14 días, no asistió, rescate de 24 h),
pero los textos salen de bot/seguimiento/plantillas.py (playbook del tenant) y los adjuntos del catálogo
(catalog_media por trigger_moment, sin repetir). El motor de SAGUE (motor.py + mensajes.py) no cambia."""
import json
import re
from datetime import timedelta, timezone

from bot import catalogo, tenant
from bot.canales.alertas import alertar_asesor
from bot.canales.whatsapp import send_wa_media, send_wa_text
from bot.config import HORARIO_PRUDENTE, LIMA_TZ, SEG_HORAS_MIN, VENTANA_WA_HORAS
from bot.crm import etapa_comercial, sincronizar_seguro, telefono_visible
from bot.datos.leads import safe_upsert_lead
from bot.engines import agenda, finanzas, multimedia
from bot.engines.textos import campo, dinero, nombre as nombre_item
from bot.agente import libres_en_horario
from bot.nlp.patrones import DESPEDIDA_RE, POSTERGAR_RE
from bot.seguimiento import plantillas
from bot.seguimiento.envio import _guardar_historial, enviar_seguimiento
from bot.utils.fechas import _ahora, _proxima_hora_prudente, _ts
from bot.utils.texto import _primer_nombre, limpiar_texto

TOQUES = [("post_45m", None), ("post_48h", timedelta(hours=48)), ("post_dia5", timedelta(days=5)),
          ("post_dia10", timedelta(days=10)), ("post_dia14", timedelta(days=14))]
TIPO_WA = {"image": "image", "pdf": "document", "video": "video"}


def en_silencio(t, ahora):
    """True dentro de la ventana de silencio del tenant (p. ej. 20:30 – 08:30, cruza la medianoche)."""
    ini, fin = str(t.get("quiet_hours_start") or "20:30")[:5], str(t.get("quiet_hours_end") or "08:30")[:5]
    hhmm = ahora.astimezone(LIMA_TZ).strftime("%H:%M")
    return (hhmm >= ini or hhmm < fin) if ini > fin else (ini <= hhmm < fin)


def _horarios(meta, idioma):
    """3 horarios reales libres; quedan guardados como offered_slots para que el cliente responda 1, 2 o 3."""
    libres = agenda.proponer({}, libres_en_horario, _ahora().astimezone(LIMA_TZ))
    meta["offered_slots"] = [s.isoformat() for s in libres]
    hoy = _ahora().astimezone(LIMA_TZ).date()
    return "\n".join(f"{agenda.NUMEROS[i]} {agenda.etiqueta(s, idioma, hoy)}" for i, s in enumerate(libres))


def _variables(lead, meta, t, item, idioma):
    nom = _primer_nombre(lead.get("nombre") or "")
    v = {"coma": f", {nom}" if nom else "", "nombre": lead.get("nombre") or nom or "", "empresa": t.get("name", ""),
         "asesor": t.get("advisor_name") or "", "direccion": (item or {}).get("location_address") or t.get("address") or "",
         "mapa": (item or {}).get("google_maps_url") or "", "telefono": re.sub(r"\D", "", telefono_visible(lead.get("telefono") or lead.get("sender_id"))),
         "evento": plantillas.playbooks.valor(f"agenda.nombre_evento_{idioma}", "visit" if idioma == "en" else "visita"),
         "pago": meta.get("payment_method") or "sin dato"}
    if item:
        mon = item.get("currency") or "USD"
        v.update(producto=nombre_item(item, idioma), bono=campo(item, "promo_bonus", idioma).rstrip("."), valor=campo(item, "value_comparison", idioma).rstrip("."))
        if meta.get("stated_budget"):
            v["presupuesto"] = dinero(float(meta["stated_budget"]), idioma, mon)
        calc = (finanzas.evaluar(item, meta.get("stated_budget"), meta.get("payment_method") or "FINANCING", idioma) or {}).get("calculo") or {}
        if calc.get("cuota"):
            v["cuota"] = dinero(calc["cuota"], idioma, mon) + ("/mes" if idioma == "es" else "/mo")
            v.setdefault("presupuesto", dinero(calc.get("inicial") or 0, idioma, mon))
    return v


def _enviar_media(lead, meta, item, clave):
    if not item or clave not in plantillas.MEDIA_POR_TOQUE:
        return
    destino = lead.get("telefono") or lead.get("sender_id")
    idioma = meta.get("preferred_language") or "es"
    enviados = list(meta.get("sent_media_ids") or [])
    for m in multimedia.elegir(item, plantillas.MEDIA_POR_TOQUE[clave], enviados, maximo=1):
        if send_wa_media(destino, m.get("file_url"), TIPO_WA.get(m.get("media_type"), "document"), m.get(f"caption_{idioma}") or ""):
            enviados.append(str(m["id"]))
    meta["sent_media_ids"] = enviados


def _post_visita(lead, meta, t, item, idioma, v, cita, ahora):
    pv = meta.get("post_visita") or {}
    if pv.get("cita") != meta.get("fecha_cita"):
        pv = {"cita": meta.get("fecha_cita"), "enviados": []}
    base_45 = _ts(meta.get("ts_visita_confirmada")) or cita
    ult_cli = _ts(meta.get("ts_ultimo_cliente"))
    conversando = bool(ult_cli and ahora - ult_cli < timedelta(hours=12) and ult_cli > cita)
    accion = None
    for clave, desfase in TOQUES:
        cuando = base_45 + timedelta(minutes=45) if desfase is None else cita + desfase
        if clave in pv["enviados"] or ahora < cuando:
            continue
        if conversando and clave != "post_45m":
            break
        if not plantillas.activo(clave) or (clave != "post_dia14" and ahora > cuando + timedelta(days=3)):
            pv["enviados"].append(clave)
            continue
        llave = clave
        if clave == "post_48h":
            llave = "post_48h_contado" if meta.get("payment_method") == "CASH" else "post_48h_financiado"
        if clave == "post_dia5":
            v["horarios"] = _horarios(meta, idioma)
        estado = enviar_seguimiento(lead, meta, plantillas.texto(llave, idioma, v), clave, [v["coma"].strip(", ") or "hola"])
        if estado == "enviado":
            _enviar_media(lead, meta, item, clave)
        if clave == "post_dia10":
            alertar_asesor(plantillas.texto("alerta_dia10", t.get("default_language") or "es", v), t.get("owner_whatsapp"))
        if clave == "post_dia14":
            meta["etapa"] = "cerrado"
        pv["enviados"].append(clave)
        accion = f"post-visita {clave} ({estado})"
        break
    meta["post_visita"] = pv
    return accion


def _rescate(lead, meta, item, idioma, v, ahora):
    ult_cli, ult_bot, ult_manual = _ts(meta.get("ts_ultimo_cliente")), _ts(meta.get("ts_ultimo_bot")), _ts(meta.get("ts_ultimo_manual"))
    if not (ult_cli and ult_bot and ult_bot >= ult_cli) or meta.get("rescate_24h_para") == meta.get("ts_ultimo_cliente") \
            or meta.get("etapa") == "cerrado" or (ult_manual and ult_manual > ult_cli) or not plantillas.activo("rescate"):
        return None
    ultimo_txt = limpiar_texto(meta.get("ultimo_texto_cliente") or "")
    if POSTERGAR_RE.search(ultimo_txt) or DESPEDIDA_RE.match(ultimo_txt):
        meta["rescate_24h_para"] = meta.get("ts_ultimo_cliente")
        return None
    local = ult_cli.astimezone(LIMA_TZ)
    objetivo = local + timedelta(hours=max(SEG_HORAS_MIN, 6)) if local.hour < 12 else local.replace(hour=9, minute=0, second=0, microsecond=0) + timedelta(days=1)
    objetivo = _proxima_hora_prudente(objetivo)
    limite = ult_cli + timedelta(hours=VENTANA_WA_HORAS)
    if objetivo > limite:
        objetivo = _proxima_hora_prudente(ult_cli + timedelta(hours=SEG_HORAS_MIN))
    if ahora >= limite:
        meta["rescate_24h_para"] = meta.get("ts_ultimo_cliente")
        return None
    if not objetivo <= ahora:
        return None
    pendientes = [s for s in (_ts(x) for x in meta.get("offered_slots") or []) if s and s > ahora + timedelta(hours=2)]
    if pendientes:
        hoy = ahora.astimezone(LIMA_TZ).date()
        v["horarios"] = "\n".join(f"{agenda.NUMEROS[i]} {agenda.etiqueta(s.astimezone(LIMA_TZ), idioma, hoy)}" for i, s in enumerate(pendientes[:3]))
        clave = "rescate_horarios"
    else:
        v["horarios"] = _horarios(meta, idioma)
        clave = "rescate_objecion" if meta.get("price_objection_count") and v.get("valor") else \
            "rescate_presupuesto" if v.get("cuota") and meta.get("stated_budget") else "rescate_general"
    texto = plantillas.texto(clave, idioma, v)
    destino = lead.get("telefono") or lead.get("sender_id")
    accion = None
    if send_wa_text(destino, texto):
        _guardar_historial(destino, texto)
        _enviar_media(lead, meta, item, "rescate")
        meta["ts_ultimo_bot"] = ahora.astimezone(timezone.utc).isoformat()
        accion = f"rescate 24h ({clave})"
    meta["rescate_24h_para"] = meta.get("ts_ultimo_cliente")
    return accion


def procesar(lead):
    """Como motor._procesar_lead_seguimiento: como máximo UNA acción por cliente en cada pasada del cron."""
    try:
        meta = json.loads(lead.get("interes") or "{}")
    except Exception:
        return None
    if meta.get("no_interesado") or meta.get("seguimiento_pausado") or etapa_comercial(meta) in ("won", "lost"):
        return None
    if not re.fullmatch(r"\d{10,15}", re.sub(r"\D", "", telefono_visible(lead.get("telefono") or lead.get("sender_id")))):
        return None
    original = json.dumps(meta, sort_keys=True)
    t = tenant.actual()
    if re.sub(r"\D", "", telefono_visible(lead.get("sender_id"))) == re.sub(r"\D", "", str(t.get("owner_whatsapp") or "x")):
        return None
    if en_silencio(t, _ahora()):
        return None                     # horario de silencio nocturno del cliente (configurable en el CRM web)
    idioma = meta.get("preferred_language") or t.get("default_language") or "es"
    items = catalogo.items()
    item = next((i for i in items if str(i.get("id")) == str(meta.get("interested_catalog_item_id"))), items[0] if items else None)
    v = _variables(lead, meta, t, item, idioma)
    ahora = _ahora()
    cita = _ts(meta.get("fecha_cita")) if meta.get("cita_agendada") else None
    accion = None
    if cita and cita > ahora and meta.get("recordatorio_para") != meta.get("fecha_cita"):
        creada = _ts(meta.get("ts_cita_creada")) or ahora - timedelta(days=1)
        local = cita.astimezone(LIMA_TZ)
        dia_antes = local.date() == ahora.date() + timedelta(days=1) and ahora.strftime("%H:%M") >= "18:00"
        mismo_dia = (local.date() == ahora.date() and cita - ahora >= timedelta(hours=2) and cita - creada >= timedelta(hours=8)
                     and ahora.strftime("%H:%M") >= HORARIO_PRUDENTE[0])
        if (dia_antes and cita - creada >= timedelta(hours=12)) or mismo_dia:
            v.update(cuando=("tomorrow" if dia_antes else "today") if idioma == "en" else ("mañana" if dia_antes else "hoy"),
                     fecha=agenda.etiqueta(local, idioma, local.date() - timedelta(days=7)))
            estado = enviar_seguimiento(lead, meta, plantillas.texto("recordatorio", idioma, v), "recordatorio", [v["coma"].strip(", ") or "hola"])
            meta.update(recordatorio_para=meta.get("fecha_cita"), etapa="confirmar_asistencia")
            accion = f"recordatorio ({estado})"
    elif cita and ahora >= cita + timedelta(minutes=75):
        estado_v = meta.get("visita_estado")
        v["fecha"] = agenda.etiqueta(cita.astimezone(LIMA_TZ), t.get("default_language") or "es", cita.astimezone(LIMA_TZ).date() - timedelta(days=7))
        if not estado_v:
            if not meta.get("pregunta_owner_visita") or (ahora - _ts(meta["pregunta_owner_visita"]) > timedelta(hours=24) and not meta.get("pregunta_owner_visita_2")):
                if meta.get("pregunta_owner_visita"):
                    meta["pregunta_owner_visita_2"] = ahora.isoformat()
                meta["pregunta_owner_visita"] = meta.get("pregunta_owner_visita") or ahora.isoformat()
                alertar_asesor(plantillas.texto("pregunta_asesor", t.get("default_language") or "es", v), t.get("owner_whatsapp"))
                accion = "pregunta al asesor si hubo visita"
        elif estado_v == "realizada":
            accion = _post_visita(lead, meta, t, item, idioma, v, cita, ahora)
        elif estado_v == "no_asistio" and not meta.get("rescate_no_asistio") and plantillas.activo("no_asistio"):
            meta["cita_agendada"] = False
            v["horarios"] = _horarios(meta, idioma)
            estado = enviar_seguimiento(lead, meta, plantillas.texto("no_asistio", idioma, v), "no_asistio", [v["coma"].strip(", ") or "hola"])
            if estado == "enviado":
                _enviar_media(lead, meta, item, "no_asistio")
            meta["rescate_no_asistio"] = True
            accion = f"rescate no asistió ({estado})"
    elif not (cita and cita > ahora) and meta.get("visita_estado") != "realizada":
        accion = _rescate(lead, meta, item, idioma, v, ahora)
    if accion or json.dumps(meta, sort_keys=True) != original:
        safe_upsert_lead(lead.get("sender_id"), lead.get("canal") or "whatsapp", lead.get("nombre"), lead.get("telefono"), meta, "")
        if accion:
            sincronizar_seguro(lead.get("sender_id"))
    return accion
