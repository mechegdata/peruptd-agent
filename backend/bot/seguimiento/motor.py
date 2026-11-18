"""Motor de seguimiento automático (lo invoca Cloud Scheduler vía /cron)."""
import json
import re
from datetime import datetime, timedelta, timezone

from bot import tenant
from bot.canales.alertas import alertar_asesor
from bot.canales.material import send_requested_wa_media
from bot.canales.whatsapp import send_wa_text
from bot.config import HORARIO_PRUDENTE, LIMA_TZ, MAPS_URL, OWNER_WA, PRECIO_LISTA_USD, SEGUIMIENTO_ACTIVO, SEG_HORAS_MIN, VENTANA_WA_HORAS
from bot.conversacion.recursos import elegir_fotos
from bot.conversacion.slots import _dos_horarios
from bot.crm import sincronizar_seguro
from bot.datos.leads import safe_upsert_lead
from bot.db import supabase
from bot.nlp.financiamiento import resumen_financiero
from bot.nlp.patrones import DESPEDIDA_RE, POSTERGAR_RE
from bot.seguimiento import motor_catalogo
from bot.seguimiento.envio import _guardar_historial, enviar_seguimiento
from bot.seguimiento.mensajes import _texto_rescate_24h, _toque_post_visita
from bot.utils.fechas import DIAS_ES, _ahora, _en_horario_prudente, _proxima_hora_prudente, _ts, a_las, format_fecha_es
from bot.utils.telefono import normalize_pe_phone
from bot.utils.texto import _primer_nombre, _usd, limpiar_texto


def _procesar_lead_seguimiento(lead):
    """Decide y ejecuta como máximo UNA acción de seguimiento para este cliente. Devuelve una descripción o None."""
    if tenant.modo_catalogo():
        return motor_catalogo.procesar(lead)  # cualquier industria, ES/EN, textos del playbook (SAGUE sigue abajo)
    try:
        meta = json.loads(lead.get("interes") or "{}")
    except Exception:
        return None
    if meta.get("no_interesado") or meta.get("seguimiento_pausado") or meta.get("vendido"):
        return None
    phone = lead.get("telefono") or lead.get("sender_id")
    nombre = lead.get("nombre") or ""
    if not phone or not re.fullmatch(r"\d{10,15}", str(phone)) or normalize_pe_phone(phone) == normalize_pe_phone(OWNER_WA):
        return None
    ahora = _ahora()
    accion = None
    cita = _ts(meta.get("fecha_cita")) if meta.get("cita_agendada") else None

    # ---- 1) Recordatorio de la visita ----
    if cita and cita > ahora and meta.get("recordatorio_para") != meta.get("fecha_cita"):
        creada = _ts(meta.get("ts_cita_creada")) or ahora - timedelta(days=1)
        cita_l = cita.astimezone(LIMA_TZ)
        dia_antes = cita_l.date() == ahora.date() + timedelta(days=1) and ahora.strftime("%H:%M") >= "18:00"
        mismo_dia = (cita_l.date() == ahora.date() and cita - ahora >= timedelta(hours=2)
                     and cita - creada >= timedelta(hours=8) and ahora.strftime("%H:%M") >= HORARIO_PRUDENTE[0])
        if (dia_antes and cita - creada >= timedelta(hours=12)) or mismo_dia:
            cuando = "mañana" if dia_antes else "hoy"
            nom = _primer_nombre(nombre)
            texto = (f"¡Hola{', ' + nom if nom else ''}! 😊 Te recuerdo tu visita a las casas de Urb. Santa Teresa *{cuando} "
                     f"{DIAS_ES[cita_l.weekday()]} {cita_l.day} {a_las(cita_l)}*\n📍 Frente a la loza deportiva (5 de Febrero y Andrés Lastres): {MAPS_URL}\n\n"
                     "¿Nos confirmas tu asistencia? Si se te complica, dime y la reprogramamos sin problema.")
            estado = enviar_seguimiento(lead, meta, texto, "recordatorio", [nom or "hola", format_fecha_es(cita_l)])
            meta["recordatorio_para"] = meta.get("fecha_cita")
            meta["etapa"] = "confirmar_asistencia"
            accion = f"recordatorio ({estado})"

    # ---- 2) Después de la visita ----
    elif cita and ahora >= cita + timedelta(minutes=75):
        estado_v = meta.get("visita_estado")
        if not estado_v:
            if not meta.get("pregunta_owner_visita") or (ahora - _ts(meta["pregunta_owner_visita"]) > timedelta(hours=24)
                                                         and not meta.get("pregunta_owner_visita_2")):
                if meta.get("pregunta_owner_visita"):
                    meta["pregunta_owner_visita_2"] = ahora.isoformat()
                meta["pregunta_owner_visita"] = meta.get("pregunta_owner_visita") or ahora.isoformat()
                alertar_asesor(f"❓ SAGUE: ¿Se realizó la visita de {nombre} (+{phone}) del {format_fecha_es(cita.astimezone(LIMA_TZ))}?\n"
                               f"Respóndeme con uno de estos mensajes:\n• *vino {phone}*\n• *no vino {phone}*\n"
                               "Con eso activo el seguimiento post-visita (o el rescate si no vino).")
                accion = "pregunta al asesor si hubo visita"
        elif estado_v == "realizada":
            pv = meta.get("post_visita") or {}
            if pv.get("cita") != meta.get("fecha_cita"):
                pv = {"cita": meta.get("fecha_cita"), "enviados": []}
            base_t1 = _ts(meta.get("ts_visita_confirmada")) or cita
            calendario = [("t1", base_t1 + timedelta(minutes=45)), ("t2", cita + timedelta(hours=48)),
                          ("t3", cita + timedelta(days=5)), ("t4", cita + timedelta(days=10)), ("t5", cita + timedelta(days=14))]
            ult_cli = _ts(meta.get("ts_ultimo_cliente"))
            conversando = bool(ult_cli and ahora - ult_cli < timedelta(hours=12) and ult_cli > cita)
            for clave, cuando in calendario:
                if clave in pv["enviados"] or ahora < cuando:
                    continue
                if conversando and clave != "t1":
                    break  # está hablando con el bot: no interrumpir con el protocolo
                if clave != "t5" and ahora > cuando + timedelta(days=3):
                    pv["enviados"].append(clave)  # se pasó su momento (p. ej. asesor confirmó tarde): saltarlo
                    continue
                plantilla, texto, media = _toque_post_visita(clave, meta, nombre)
                estado = enviar_seguimiento(lead, meta, texto, plantilla, [_primer_nombre(nombre) or "hola"], media)
                pv["enviados"].append(clave)
                if clave == "t4":
                    alertar_asesor(f"📞 SAGUE: Día 10 post-visita de {nombre} (+{phone}). Buen momento para llamarle y negociar "
                                   f"(margen entre {_usd(PRECIO_LISTA_USD)} y tu precio piso). Pago: {resumen_financiero(meta)}.")
                accion = f"post-visita {clave} ({estado})"
                break
            meta["post_visita"] = pv
        elif estado_v == "no_asistio" and not meta.get("rescate_no_asistio"):
            nom = _primer_nombre(nombre)
            meta["cita_agendada"] = False
            texto = (f"¡Hola{', ' + nom if nom else ''}! 😊 Te esperábamos en Santa Teresa, ¿todo bien? Si se te complicó, no te preocupes: "
                     "te reprogramo la visita. " + _dos_horarios(meta))
            fotos = elegir_fotos("no_asistio", meta)
            estado = enviar_seguimiento(lead, meta, texto, "no_asistio", [nom or "hola"], {"recursos": fotos} if fotos else None)
            meta["rescate_no_asistio"] = True
            accion = f"rescate no asistió ({estado})"

    # ---- 3) Rescate dentro de las 24 h gratis (sin cita futura) ----
    elif not (cita and cita > ahora) and meta.get("visita_estado") != "realizada":
        ult_cli = _ts(meta.get("ts_ultimo_cliente"))
        ult_bot = _ts(meta.get("ts_ultimo_bot"))
        ult_manual = _ts(meta.get("ts_ultimo_manual"))
        if ult_cli and ult_bot and ult_bot >= ult_cli and meta.get("rescate_24h_para") != meta.get("ts_ultimo_cliente") \
                and meta.get("etapa") != "cerrado" and not (ult_manual and ult_manual > ult_cli):
            ultimo_txt = limpiar_texto(meta.get("ultimo_texto_cliente") or "")
            if POSTERGAR_RE.search(ultimo_txt) or DESPEDIDA_RE.match(ultimo_txt):
                meta["rescate_24h_para"] = meta.get("ts_ultimo_cliente")  # "te aviso" / "gracias": respetar su espacio
            else:
                l = ult_cli.astimezone(LIMA_TZ)
                objetivo = l + timedelta(hours=max(SEG_HORAS_MIN, 6)) if l.hour < 12 else \
                    l.replace(hour=9, minute=0, second=0, microsecond=0) + timedelta(days=1)
                objetivo = _proxima_hora_prudente(objetivo)
                limite = ult_cli + timedelta(hours=VENTANA_WA_HORAS)
                if objetivo > limite:
                    objetivo = _proxima_hora_prudente(ult_cli + timedelta(hours=SEG_HORAS_MIN))
                if objetivo <= ahora < limite:
                    texto = _texto_rescate_24h(meta, nombre)
                    if send_wa_text(phone, texto):
                        _guardar_historial(phone, texto)
                        fotos = elegir_fotos("rescate", meta)  # 1 foto que aún no vio (sala amoblada, terraza...)
                        if fotos:
                            send_requested_wa_media(phone, {"recursos": fotos, "_nombre": nombre})
                        meta["ts_ultimo_bot"] = ahora.astimezone(timezone.utc).isoformat()
                        accion = "rescate 24h (gratis)"
                    meta["rescate_24h_para"] = meta.get("ts_ultimo_cliente")
                elif ahora >= limite:
                    meta["rescate_24h_para"] = meta.get("ts_ultimo_cliente")  # se cerró la ventana sin horario prudente

    if accion or meta != json.loads(lead.get("interes") or "{}"):
        safe_upsert_lead(lead.get("sender_id"), lead.get("canal") or "whatsapp", nombre, phone, meta, "")
        if accion:
            sincronizar_seguro(lead.get("sender_id"))  # p. ej. etapa de negociación (día 10) en Salesforce
    return accion


def ejecutar_seguimientos():
    if not SEGUIMIENTO_ACTIVO:
        return {"activo": False}
    ahora = _ahora()
    if not _en_horario_prudente(ahora):
        return {"horario_silencioso": True, "hora": ahora.strftime("%H:%M")}
    if not supabase:
        return {"error": "sin supabase"}
    desde = (datetime.now(timezone.utc) - timedelta(days=16)).isoformat()
    try:
        leads = supabase.table("leads").select("*").gte("updated_at", desde).execute().data or []
    except Exception as e:
        print("Error leyendo leads para seguimiento:", e)
        return {"error": str(e)}
    hechos = []
    for lead in leads:
        if (lead.get("canal") or "whatsapp") != "whatsapp":
            continue
        try:
            a = _procesar_lead_seguimiento(lead)
            if a:
                hechos.append({"cliente": lead.get("nombre"), "telefono": lead.get("telefono"), "accion": a})
        except Exception as e:
            print(f"Error en seguimiento de {lead.get('sender_id')}:", e)
    if hechos:
        print("[SEGUIMIENTO]", json.dumps(hechos, ensure_ascii=False))
    return {"revisados": len(leads), "acciones": hechos}
