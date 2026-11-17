"""Orquestador: decide qué motor responde cada mensaje y persiste el resultado."""
import difflib
import json
import re
from datetime import datetime, timedelta, timezone

from bot.canales.alertas import alertar_asesor
from bot.canales.whatsapp import send_wa_media, send_wa_template, send_wa_text
from bot.config import LIMA_TZ, MAPS_URL, OWNER_WA, URL_FICHA_TECNICA, URL_RENDER_GRIS, URL_RENDER_MADERA
from bot.conversacion.agenda import motor_agenda
from bot.conversacion.base import _resp
from bot.conversacion.cierres import cierre_contextual, cierre_info
from bot.conversacion.cortesia import responder_cortesia
from bot.conversacion.post_agenda import responder_post_agenda
from bot.conversacion.despedida import responder_despedida
from bot.conversacion.faq import responder_faq
from bot.conversacion.formulario import bienvenida_reciente, marcar_bienvenida, texto_formulario
from bot.conversacion.recursos import asignar_media
from bot.conversacion.info import responder_info, temas_info
from bot.conversacion.material import responder_material, responder_oferta_video
from bot.conversacion.objeciones import es_objecion_precio
from bot.conversacion.respaldo import build_Contextual_fallback
from bot.conversacion.slots import _slots_a_texto, elegir_slot_ofrecido
from bot.datos.leads import get_lead_by_sender_or_phone, safe_upsert_lead
from bot.db import supabase
from bot.datos import colas
from bot.estado import PENDING_FORM_TIMERS
from bot.ia.gemini import call_gemini_api
from bot.ia.prompt import build_system_prompt
from bot.integraciones.calendario import create_calendar_event, get_calendar_availability_text, get_free_slots, update_calendar_event
from bot.nlp.financiamiento import estado_financiero, inferir_estado_de_historial, pregunta_por_financiamiento, quitar_preguntas_financiamiento, resumen_financiero
from bot.nlp.formulario import parse_lead_form_text
from bot.nlp.parser_fechas import parse_fecha_hora_es
from bot.nlp.patrones import AFIRMA_RE, NIEGA_RE, NO_INTERESADO_RE
from bot.utils.fechas import format_fecha_es
from bot.utils.telefono import extract_phone_from_text, normalize_pe_phone
from bot.utils.texto import limpiar_texto, nombre_valido, sin_tildes


def process_conversation(sender_id, canal, user_text, sender_name="", comment_id=None):
    form_info = parse_lead_form_text(user_text)
    extracted_phone = form_info.get("telefono") or extract_phone_from_text(user_text)
    if canal == "whatsapp":
        extracted_phone = normalize_pe_phone(sender_id)

    if extracted_phone and extracted_phone in PENDING_FORM_TIMERS:
        try:
            PENDING_FORM_TIMERS[extracted_phone].cancel()
            del PENDING_FORM_TIMERS[extracted_phone]
            colas.cancelar_tareas("lead_ad", extracted_phone)  # y la copia persistente (que no la envíe /cron)
        except Exception:
            pass

    lead = get_lead_by_sender_or_phone(sender_id, extracted_phone)
    meta_lead = {}
    if lead.get("interes"):
        try:
            meta_lead = json.loads(lead["interes"])
        except Exception:
            meta_lead = {}

    nombre_cliente = (nombre_valido(form_info.get("nombre")) or nombre_valido(lead.get("nombre"))
                      or nombre_valido(sender_name) or "Interesado")
    if nombre_cliente in ["Interesado", "Cliente", ""]:
        m_nom = re.search(r"(?i)(?:soy|me llamo|mi nombre es|con)\s+([a-záéíóúñA-ZÁÉÍÓÚÑ]+(?:\s+[a-záéíóúñA-ZÁÉÍÓÚÑ]+)?)", user_text)
        if m_nom:
            candidato = m_nom.group(1).strip()
            if sin_tildes(candidato.split()[0]) not in ["el", "la", "un", "una", "banco", "credito", "contado", "visita", "sague", "mi", "mis", "inicial", "gusto", "todo", "mucho", "interes"]:
                nombre_cliente = candidato.title()

    if _reintento_de_meta(meta_lead, user_text):
        print(f"Mensaje repetido de {sender_id} en menos de 3 min (reintento de Meta): no se responde dos veces")
        return {"reply_text": "", "_no_responder": True, "_sin_control_repeticion": True}, extracted_phone, nombre_cliente, meta_lead
    if form_info:
        meta_lead.update(form_info)
    if canal == "whatsapp":
        meta_lead["wsp_iniciado"] = True
    meta_lead["ts_ultimo_cliente"] = datetime.now(timezone.utc).isoformat()
    meta_lead["ultimo_texto_cliente"] = (user_text or "")[:200]
    if NO_INTERESADO_RE.search(limpiar_texto(user_text)):
        meta_lead["no_interesado"] = True

    history_text = ""
    has_history = False
    mensajes_db = []
    if supabase:
        try:
            res = supabase.table("mensajes").select("rol,contenido,created_at").eq("sender_id", sender_id).order("created_at", desc=True).limit(20).execute()
            mensajes_db = list(reversed(res.data)) if res.data else []
            if not mensajes_db and extracted_phone and sender_id != extracted_phone:
                res_p = supabase.table("mensajes").select("rol,contenido,created_at").eq("sender_id", extracted_phone).order("created_at", desc=True).limit(8).execute()
                if res_p.data:
                    mensajes_db = list(reversed(res_p.data))
            if mensajes_db:
                has_history = True
            for m in mensajes_db:
                history_text += f"{m['rol'].upper()}: {m['contenido']}\n"
        except Exception as e:
            print("Error leyendo historial:", e)

    historial_usuario = [m["contenido"] for m in mensajes_db if m.get("rol") == "user" and m.get("contenido")]
    inferir_estado_de_historial(meta_lead, mensajes_db)
    ultimo_bot = next((m["contenido"] for m in reversed(mensajes_db) if m.get("rol") == "assistant" and m.get("contenido")), "")
    # Compatibilidad con conversaciones previas sin estado: si el último mensaje del bot preguntó por inicial/crédito, lo marcamos
    if not meta_lead.get("etapa") and pregunta_por_financiamiento(ultimo_bot):
        meta_lead["pregunta_fin_pendiente"] = True
        meta_lead["etapa"] = "pregunto_financiamiento"

    # 0) Despedida: "no, gracias", "eso es todo", o "no" a "¿tienes alguna otra duda?" => cerrar con amabilidad
    parsed = None
    if not form_info.get("es_formulario") and canal in ["whatsapp", "facebook", "instagram"]:
        # 'le estaré comunicando la hora', '👍', 'ok': no insistir (y a veces, no responder)
        nom_corto = nombre_cliente.split()[0] if nombre_cliente not in ["Interesado", "Cliente", ""] else ""
        meta_lead["_con_historial"] = has_history  # un "buenos días" de quien ya conversó es un saludo, no un 1er contacto
        r_cort = responder_cortesia(user_text, meta_lead, nom_corto)
        meta_lead.pop("_con_historial", None)
        parsed = (r_cort or responder_post_agenda(user_text, meta_lead, nom_corto)
                  or (responder_oferta_video(user_text, meta_lead, nom_corto) if canal == "whatsapp" else None)
                  or responder_despedida(user_text, meta_lead, nombre_cliente, ultimo_bot))
        if parsed:
            return _finalizar_conversacion(parsed, sender_id, canal, user_text, nombre_cliente, extracted_phone, meta_lead, form_info, ultimo_bot)

    nom_c = nombre_cliente.split()[0] if nombre_cliente not in ["Interesado", "Cliente", ""] else ""
    privado = canal in ["whatsapp", "facebook", "instagram"]

    # 1) Mensaje del formulario de Meta que llega por WhatsApp: responder según lo que marcó
    if form_info.get("es_formulario") and canal == "whatsapp":
        if bienvenida_reciente(meta_lead):
            # El mismo formulario llegó otra vez (reintento de Meta o el aviso de Lead Ads): no repetir la bienvenida
            print(f"Formulario repetido de {sender_id}: ya se le dio la bienvenida, no se reenvía")
            if lead:
                safe_upsert_lead(sender_id, canal, nombre_cliente, extracted_phone, meta_lead, user_text)
            return {"reply_text": "", "_no_responder": True, "_sin_control_repeticion": True}, extracted_phone, nombre_cliente, meta_lead
        marcar_bienvenida(meta_lead)
        txt_f, flags_f = texto_formulario(nombre_cliente, form_info.get("estilo_cocina"), form_info.get("forma_pago"),
                                          form_info.get("en_presupuesto"), meta_lead)
        parsed = _resp(txt_f)
        parsed.update(flags_f)
        # 1er mensaje: solo las fichas y el render de la cocina que eligió (lo que el texto promete), sin la sala
        parsed["_sin_control_repeticion"] = True
        return _finalizar_conversacion(parsed, sender_id, canal, user_text, nombre_cliente, extracted_phone, meta_lead, form_info, ultimo_bot)

    # 2) Respuestas de contenido (FAQ de compra, material, información). No se usan si el cliente está dando un día/hora
    #    ni para respuestas cortas ("sí", "no todavía"), que las maneja el motor de agenda.
    fh_check = parse_fecha_hora_es(user_text)
    t_l = limpiar_texto(user_text)
    # Elección de un horario ofrecido aunque el último mensaje del bot no haya sido la lista ("La segunda opción.")
    es_eleccion_horario = bool(meta_lead.get("etapa") in ["ofrecio_horarios", "pregunto_dia"] and meta_lead.get("slots_ofrecidos")
                               and not re.search(r"1️⃣[^\n]*(plano|ficha|cocina|dise)", ultimo_bot or "", re.I)
                               and elegir_slot_ofrecido(t_l, meta_lead.get("slots_ofrecidos") or [], fh_check) is not None)
    corto = len(t_l) <= 25 and bool(AFIRMA_RE.match(t_l) or NIEGA_RE.match(t_l)) and not es_objecion_precio(t_l)
    if privado and not form_info.get("es_formulario") and fh_check.get("hora") is None and fh_check.get("fecha") is None \
            and not es_eleccion_horario and not corto:
        faq = responder_faq(user_text, nom_c, meta_lead)
        if faq:
            parsed = _resp(faq)
        else:
            mat = responder_material(user_text, nom_c, meta_lead, ultimo_bot, cerrar=False) if canal == "whatsapp" else None
            inf = responder_info(user_text, nom_c, meta_lead, primer_contacto=not has_history, cerrar=False)
            if mat and inf:
                parsed = dict(inf)
                for k in ["enviar_fotos_casa", "enviar_ficha_tecnica", "enviar_renders_cocina", "_alerta_fotos", "_pide_video"]:
                    parsed[k] = bool(inf.get(k) or mat.get(k))
                for k in ["_momento_fotos", "_unidad", "recursos", "_sin_cierre"]:
                    if mat.get(k):
                        parsed[k] = mat[k]
                partes_mat = mat["reply_text"].split("\n\n", 1)
                parsed["reply_text"] = inf["reply_text"] + "\n\n" + (partes_mat[1] if len(partes_mat) > 1 else partes_mat[0])
            else:
                parsed = inf or mat
            if parsed and not parsed.get("_sin_cierre"):
                # Un solo cierre al final, según lo que ya se sabe del cliente
                if inf:
                    parsed["reply_text"] += "\n\n" + cierre_info(meta_lead, nom_c, temas_info(user_text))
                else:
                    parsed["reply_text"] += "\n\n" + cierre_contextual(meta_lead, nom_c)

    # 3) Motor de agenda determinístico (no depende de Gemini)
    if not parsed and not form_info.get("es_formulario"):
        try:
            parsed = motor_agenda(user_text, meta_lead, nombre_cliente, extracted_phone, canal, historial_usuario)
        except Exception as e:
            print("Error en motor_agenda:", e)
            parsed = None

    if parsed:
        return _finalizar_conversacion(parsed, sender_id, canal, user_text, nombre_cliente, extracted_phone, meta_lead, form_info, ultimo_bot)

    cal_info = get_calendar_availability_text()
    slot_pend_txt = ""
    if meta_lead.get("slot_propuesto"):
        try:
            slot_pend_txt = format_fecha_es(datetime.fromisoformat(meta_lead["slot_propuesto"]), relativo=True)
        except Exception:
            pass
    fecha_cita_txt = ""
    if meta_lead.get("cita_agendada") and meta_lead.get("fecha_cita"):
        try:
            fecha_cita_txt = " (" + format_fecha_es(datetime.fromisoformat(meta_lead["fecha_cita"]), relativo=True) + ")"
        except Exception:
            pass
    lead_ctx_str = (
        f"- Nombre: {nombre_cliente}\n"
        f"- Teléfono WhatsApp: {extracted_phone or lead.get('telefono') or 'Aún no proporcionado'}\n"
        f"- Modalidad de compra: {resumen_financiero(meta_lead) or meta_lead.get('forma_pago', 'Por consultar')}\n"
        f"- Estilo de cocina elegido: {meta_lead.get('estilo_cocina', 'Por elegir (Gris Grafito LED o Madera Rovere)')}\n"
        f"- Dentro de presupuesto ($135k): {meta_lead.get('en_presupuesto', 'Por confirmar')}\n"
        f"- Horario de visita que el cliente propuso y está pendiente de confirmar: {slot_pend_txt or 'Ninguno'}\n"
        f"- Cita ya agendada previamente: {'Sí' + fecha_cita_txt if meta_lead.get('cita_agendada') else 'No'}"
    )

    sys_prompt = build_system_prompt(canal, cal_info, lead_ctx_str)

    schema_rule = """
INSTRUCCIÓN DE FORMATO DE SALIDA:
Responde ÚNICAMENTE con un objeto JSON válido (sin texto adicional antes ni después y sin comentarios //) con esta estructura exacta:
{
  "reply_text": "Tu respuesta conversacional y persuasiva para el cliente",
  "private_reply": "Mensaje privado DM solo si el canal es comentario público, sino vacío",
  "ignorar_comentario": false,
  "enviar_ficha_tecnica": false,
  "enviar_renders_cocina": false,
  "estilo_render_preferido": "ambos",
  "agendar_visita_iso": ""
}
"""

    full_prompt = (
        f"{sys_prompt}\n\n{schema_rule}\n\n"
        f"HISTORIAL DE CONVERSACIÓN RECIENTE:\n{history_text or '(Primer mensaje de la conversación)'}\n\n"
        f"NUEVO MENSAJE DEL CLIENTE ({canal}):\n{user_text}\n\n"
        "JSON DE RESPUESTA:"
    )

    parsed = call_gemini_api(full_prompt)

    # Si por cualquier motivo la API falla, usamos el motor contextual (NUNCA repite el saludo si puso 1, 2, etc.)
    if not parsed or not parsed.get("reply_text"):
        print("Usando motor de respaldo (Gemini no devolvió respuesta válida).")
        parsed = build_Contextual_fallback(canal, user_text, nombre_cliente, has_history, meta_lead)

    # Si el texto promete adjuntos que no se marcaron para envío, se envían igual (nunca prometer sin enviar)
    if canal == "whatsapp" and re.search(r"(?i)(adjunt|te env[ií]o|aqu[ií] tienes|te comparto)", parsed.get("reply_text", "")):
        rt = parsed.get("reply_text", "").lower()
        if re.search(r"plano|ficha", rt):
            parsed["enviar_ficha_tecnica"] = True
        if re.search(r"render|cocina|dise[ñn]o", rt):
            parsed["enviar_renders_cocina"] = True

    # Asegurar que si el usuario escribio "1" en WhatsApp, SIEMPRE se disparen los planos y renders aunque el LLM olvide marcar el booleano
    low_input = (user_text or "").strip().lower()
    if canal == "whatsapp" and low_input in ["1", "1️⃣", "uno", "opcion 1", "opción 1"]:
        parsed["enviar_ficha_tecnica"] = True
        parsed["enviar_renders_cocina"] = True

    reply_text = parsed.get("reply_text", "").strip()
    iso_cita = (parsed.get("agendar_visita_iso") or "").strip()

    # Si Gemini propone una cita, se valida contra la agenda real antes de confirmarla
    if iso_cita:
        try:
            dt_cita = datetime.fromisoformat(iso_cita)
            if dt_cita.tzinfo is None:
                dt_cita = dt_cita.replace(tzinfo=LIMA_TZ)
        except Exception:
            dt_cita = None
        if dt_cita:
            notas_cal = f"Pago: {resumen_financiero(meta_lead)} | Cocina: {meta_lead.get('estilo_cocina', 'Por elegir')}"
            if meta_lead.get("cita_agendada") and meta_lead.get("evento_id"):
                ok_cal, det_cal = update_calendar_event(meta_lead["evento_id"], dt_cita.isoformat())
                ev_id = meta_lead["evento_id"]
            elif not meta_lead.get("cita_agendada"):
                ok_cal, det_cal, ev_id = create_calendar_event(nombre_cliente, extracted_phone or sender_id, dt_cita.isoformat(), notas_cal)
            else:
                ok_cal, det_cal, ev_id = False, "ya_agendada", None
            if ok_cal:
                meta_lead.update({"cita_agendada": True, "fecha_cita": dt_cita.isoformat(), "evento_id": ev_id or "",
                                  "ts_cita_creada": datetime.now(timezone.utc).isoformat(), "recordatorio_para": "", "visita_estado": "",
                                  "pregunta_owner_visita": "", "pregunta_owner_visita_2": "", "rescate_no_asistio": False,
                                  "etapa": "agendado", "slot_propuesto": "", "slots_ofrecidos": []})
                reply_text += (
                    f"\n\n✅ ¡Cita confirmada en nuestra agenda para el {det_cal}!\n"
                    f"📍 Te esperamos en Urb. Santa Teresa, Lambayeque (frente a la loza deportiva, a 1 min de Av. Ramón Castilla): {MAPS_URL}"
                )
                try:
                    alertar_asesor(f"📅 Nueva visita SAGUE: {nombre_cliente} (+{extracted_phone or 's/n'}) el {det_cal} | Pago: {resumen_financiero(meta_lead)}")
                except Exception:
                    pass
            elif det_cal in ["ocupado", "invalido"]:
                alt = get_free_slots(n=3)
                if alt:
                    meta_lead["etapa"] = "ofrecio_horarios"
                    meta_lead["slots_ofrecidos"] = [s.isoformat() for s in alt]
                    reply_text = (
                        f"Ese horario ya no está disponible en la agenda 😕. Estos son los horarios libres más próximos:\n\n"
                        f"{_slots_a_texto(alt)}\n\nRespóndeme con el número y te la registro al toque."
                    )
            parsed["reply_text"] = reply_text

    # Si la respuesta (Gemini o respaldo) pregunta por la inicial, recordarlo para entender un "sí" / "no todavía"
    # No volver a preguntar por la inicial/crédito si el cliente ya lo contó (en el chat, al bot o al asesor humano)
    ya_respondio = estado_financiero(meta_lead) is not None or (
        int(meta_lead.get("veces_pregunta_fin") or 0) >= 1 and any(meta_lead.get(k) is not None for k in ["fin_modalidad", "fin_inicial", "fin_credito_aprobado"]))
    if pregunta_por_financiamiento(reply_text) and (ya_respondio or meta_lead.get("cita_agendada") or int(meta_lead.get("veces_pregunta_fin") or 0) >= 2):
        nom_c = nombre_cliente.split()[0] if nombre_cliente not in ["Interesado", "Cliente", ""] else ""
        reply_text = quitar_preguntas_financiamiento(reply_text) + "\n\n" + cierre_contextual(meta_lead, nom_c)
    if not meta_lead.get("cita_agendada") and pregunta_por_financiamiento(reply_text):
        meta_lead["pregunta_fin_pendiente"] = True
        if meta_lead.get("etapa") not in ["ofrecio_horarios"]:
            meta_lead["etapa"] = "pregunto_financiamiento"

    parsed["reply_text"] = reply_text
    return _finalizar_conversacion(parsed, sender_id, canal, user_text, nombre_cliente, extracted_phone, meta_lead, form_info, ultimo_bot)


def _es_repeticion(nuevo, anterior):
    if not nuevo or not anterior:
        return False
    a, b = limpiar_texto(nuevo)[:400], limpiar_texto(anterior)[:400]
    return difflib.SequenceMatcher(None, a, b).ratio() >= 0.8


def _reintento_de_meta(meta, texto, minutos=3):
    """El mismo mensaje largo otra vez, ya respondido, en pocos minutos = Meta reenvió el webhook (otra instancia no lo conoce)."""
    if len((texto or "").strip()) < 15 or (meta.get("ultimo_texto_cliente") or "") != (texto or "")[:200]:
        return False
    try:
        cli, bot = datetime.fromisoformat(meta.get("ts_ultimo_cliente") or ""), datetime.fromisoformat(meta.get("ts_ultimo_bot") or "")
    except ValueError:
        return False
    return bot >= cli and datetime.now(timezone.utc) - cli < timedelta(minutes=minutos)


def _finalizar_conversacion(parsed, sender_id, canal, user_text, nombre_cliente, extracted_phone, meta_lead, form_info, ultimo_bot=""):
    reply_text = (parsed.get("reply_text") or "").strip()
    # "¿Me confirma? ¿Y dónde la veo?": si preguntó dónde y la respuesta no trae la ubicación, se agrega (no se deja una pregunta sin responder)
    if reply_text and not parsed.get("_no_responder") and MAPS_URL not in reply_text and \
            re.search(r"\b(donde (es|esta|estan|queda|quedan|la veo|nos vemos|los veo|te veo|lo veo|me espera\w*)|ubicacion|direccion|como llego)\b",
                      limpiar_texto(user_text)):
        reply_text += f"\n\n📍 Te esperamos en Urb. Santa Teresa, Lambayeque (calles 5 de Febrero y Andrés Lastres, frente a la loza deportiva): {MAPS_URL}"
        parsed["reply_text"] = reply_text
    if not parsed.get("_no_responder"):
        meta_lead["ts_ultimo_bot"] = datetime.now(timezone.utc).isoformat()
    parsed["_nombre"] = nombre_cliente
    parsed["_msg_cliente"] = "Formulario de Meta" if form_info.get("es_formulario") else user_text
    if pregunta_por_financiamiento(reply_text):
        meta_lead["veces_pregunta_fin"] = int(meta_lead.get("veces_pregunta_fin") or 0) + 1
    # Un asesor nunca repite el mismo mensaje: si la respuesta es casi igual a la anterior, se reformula y se avisa al asesor humano
    if canal in ["whatsapp", "facebook", "instagram"] and not parsed.get("_sin_control_repeticion") and _es_repeticion(reply_text, ultimo_bot):
        nom = nombre_cliente.split()[0] if nombre_cliente not in ["Interesado", "Cliente", ""] else ""
        coma = f", {nom}" if nom else ""
        if meta_lead.get("etapa") == "ofrecio_horarios" and not meta_lead.get("cita_agendada"):
            # Se mantiene la etapa y los horarios: si luego dice "la segunda opción", se entiende
            reply_text = (
                f"Perdona si no me expliqué bien{coma} 😊. ¿Qué día y a qué hora te quedaría mejor para conocer las casas? "
                "Me adapto a tu horario. "
                "Y si antes tienes alguna duda (precio, financiamiento, distribución), con gusto te la resuelvo."
            )
        else:
            reply_text = (
                f"Cuéntame{coma}, ¿en qué más te puedo ayudar? 😊 Puedo resolverte dudas de precio, distribución, "
                "financiamiento con banco o coordinar tu visita a las casas de Urb. Santa Teresa."
            )
        try:
            alertar_asesor(f"🔔 SAGUE: el bot no supo cómo continuar con {nombre_cliente} (+{extracted_phone or sender_id}). "
                                   f"Mensaje del cliente: \"{user_text[:150]}\". Revisa el chat por si conviene intervenir.")
        except Exception:
            pass
        parsed["reply_text"] = reply_text
    asignar_media(parsed, meta_lead, canal)  # fotos / renders / videos / fichas por casa según el momento
    alerta = meta_lead.pop("_alerta_asesor", None)
    if alerta:
        try:
            alertar_asesor(f"{alerta} — {nombre_cliente} (+{extracted_phone or sender_id}). Mensaje: \"{user_text[:150]}\"")
        except Exception:
            pass
    if supabase:
        try:
            supabase.table("mensajes").insert([
                {"sender_id": sender_id, "canal": canal, "rol": "user", "contenido": user_text},
                {"sender_id": sender_id, "canal": canal, "rol": "assistant", "contenido": reply_text}
            ][:1 if parsed.get("_no_responder") else 2]).execute()
        except Exception as e:
            print("Error guardando mensajes:", e)

    safe_upsert_lead(
        sender_id=sender_id,
        canal=canal,
        nombre=nombre_cliente,
        telefono=extracted_phone,
        interes_dict=meta_lead,
        ultimo_msg=user_text
    )

    if canal in ["facebook", "instagram"] and extracted_phone and not form_info.get("es_formulario"):
        safe_upsert_lead(
            sender_id=extracted_phone,
            canal="whatsapp",
            nombre=nombre_cliente,
            telefono=extracted_phone,
            interes_dict=meta_lead,
            ultimo_msg=f"[Traspaso desde {canal}]: {user_text}"
        )
        msg_salto_wa = (
            f"¡Hola, {nombre_cliente}! Te saluda el equipo de SAGUE Constructora 😊. "
            f"Continuamos por aquí nuestra conversación de {canal.capitalize()} sobre las casas de estreno de 3 pisos (200 m² construidos) "
            f"en Urb. Santa Teresa, Lambayeque (frente a la loza deportiva). "
            "Te adjunto por aquí la ficha técnica con los planos de distribución (1er y 2do piso con acabados y el 3ro en casco, "
            "sin tarrajear; entrega inmediata con título en SUNARP) y los diseños de cocina equipada."
        )
        ok_wa = send_wa_text(extracted_phone, msg_salto_wa)
        if not ok_wa:
            ok_wa = send_wa_template(
                extracted_phone,
                nombre_cliente,
                meta_lead.get("estilo_cocina", "equipada"),
                meta_lead.get("forma_pago", "contado o crédito hipotecario")
            )
        if ok_wa:
            send_wa_media(
                extracted_phone,
                URL_FICHA_TECNICA,
                "document",
                "Planos de distribución de los 3 pisos (200 m² construidos - Entrega Inmediata en Urb. Santa Teresa)."
            )
            send_wa_media(extracted_phone, URL_RENDER_GRIS, "image", "Opción 1: Línea Moderna en Gris Grafito con iluminación LED cálida.")
            send_wa_media(extracted_phone, URL_RENDER_MADERA, "image", "Opción 2: Línea Cálida en Madera Rovere y acabado Taupe.")
        else:
            send_wa_text(
                OWNER_WA,
                f"Alerta SAGUE: {nombre_cliente} dejó su celular +{extracted_phone} en {canal}, pero requiere iniciar chat manual o no tiene WhatsApp activo."
            )

    return parsed, extracted_phone, nombre_cliente, meta_lead
