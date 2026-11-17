"""Motor de agenda determinístico (máquina de estados de agendamiento). Corre antes que la IA."""
import re
from datetime import datetime, timezone

from bot.canales.alertas import alertar_asesor
from bot.canales.whatsapp import send_wa_text
from bot.config import ASESOR_HIPOTECARIO_WA, EXIGIR_FILTRO_FINANCIERO, LIMA_TZ, MAPS_URL, OWNER_WA
from bot.conversacion.agenda_humana import (agenda_por_preferencias, completar_fecha_por_contexto, inferir_hora_suelta, ofrecer_mas_tarde,
                                            ofrecer_por_dia,
                                            proponer_si_pregunta, slots_vigentes)
from bot.conversacion.base import _resp
from bot.conversacion.cierres import cierre_contextual
from bot.conversacion.post_agenda import PREGUNTA_ACOMPANANTES
from bot.conversacion.presupuesto import responder_presupuesto
from bot.conversacion.slots import _slots_a_texto, construir_slot, elegir_slot_ofrecido, recuperar_slot_de_historial
from bot.integraciones.calendario import create_calendar_event, fecha_apertura_txt, get_free_slots, primer_dia_visitas, update_calendar_event, verificar_slot
from bot.nlp.dias import preferencia_dias
from bot.nlp.restricciones import detectar_restriccion_horaria
from bot.nlp.financiamiento import detectar_financiamiento, estado_financiero, resumen_financiero
from bot.nlp.parser_fechas import parse_fecha_hora_es
from bot.nlp.patrones import AFIRMA_RE, MATERIAL_RE, NIEGA_RE, POSTERGAR_RE, PREGUNTA_INFO_RE, RECHAZO_RE, VISITA_FUERTE_RE, VISITA_RE
from bot.utils.fechas import DIAS_ES, format_fecha_es
from bot.utils.texto import _usd, limpiar_texto


def motor_agenda(user_text, meta, nombre_cliente, telefono, canal, historial_usuario=None):
    """Devuelve una respuesta (dict) si el mensaje es de agendamiento; None para dejarlo a Gemini/fallback.
    Modifica 'meta' con el nuevo estado de la conversación."""
    if canal not in ["whatsapp", "facebook", "instagram"]:
        return None
    t = limpiar_texto(user_text)
    if not t:
        return None
    nom = nombre_cliente.split()[0] if nombre_cliente not in ["Interesado", "Cliente", ""] else ""
    coma_nom = f", {nom}" if nom else ""
    etapa = meta.get("etapa") or ""
    fh = parse_fecha_hora_es(user_text)
    inferir_hora_suelta(t, fh, meta)  # "Plan de 5?" / "5?" con la lista del día a la vista = esa hora
    fin = detectar_financiamiento(user_text)
    afirma = bool(AFIRMA_RE.match(t)) and len(t) <= 80 and not t.startswith("si no")
    niega = bool(NIEGA_RE.match(t)) and len(t) <= 60
    # "ninguno", "no puedo", "otro día"... cuando le ofrecimos horarios
    rechaza = bool(RECHAZO_RE.search(t)) and etapa in ["ofrecio_horarios", "confirmar_horario", "agendado", "pregunto_acompanantes", "ofrecio_movilidad", "pregunto_dia", "ofrecio_material",
                                                        "confirmar_asistencia"]
    # "no puedo entre semana", "solo los sábados", "el fin de semana no", "martes o jueves", "menos el lunes"...
    pref_dias, dias_negados = preferencia_dias(user_text)
    recurrente = bool(re.search(r"\b(solo|los (lunes|martes|miercoles|jueves|viernes|sabados|domingos)|sabados|domingos)\b", t))
    if pref_dias and len(pref_dias) == 1 and fh["fecha"] is not None and fh["fecha"].weekday() in pref_dias and not recurrente:
        pref_dias = None  # "el martes por la tarde" es un día puntual (lo maneja la fecha), no una preferencia
    if fh["fecha"] is not None and (fh["fecha"].weekday() in dias_negados or (pref_dias and (len(pref_dias) > 1 or recurrente))):
        fh["fecha"] = None  # "no puedo el lunes" / "martes o jueves" / "solo los sábados" no son una cita en ese día puntual

    fin_pendiente = bool(meta.get("pregunta_fin_pendiente"))
    # Respuestas cortas ("sí" / "no todavía") a la pregunta de inicial o crédito
    if all(v is None for v in fin.values()) and fin_pendiente and etapa not in ["confirmar_horario", "ofrecio_asesor", "ofrecio_material"] and not rechaza:
        if niega:
            fin = {"modalidad": None, "inicial": False, "credito_aprobado": False}
        elif afirma and etapa == "pregunto_financiamiento":
            fin = {"modalidad": None, "inicial": True, "credito_aprobado": None}
    hay_fin = any(v is not None for v in fin.values())
    if fin["modalidad"]:
        meta["fin_modalidad"] = fin["modalidad"]
    if fin["inicial"] is not None:
        meta["fin_inicial"] = fin["inicial"]
    if fin["credito_aprobado"] is not None:
        meta["fin_credito_aprobado"] = fin["credito_aprobado"]
    calif = estado_financiero(meta)
    if calif is not None:
        meta["pregunta_fin_pendiente"] = False

    if POSTERGAR_RE.search(t) and not hay_fin:
        return None

    # Preguntas informativas ("¿con banco cómo sería?", "¿cuánto de inicial?") las responde FAQ/Gemini, no el agendador
    es_pregunta_info = ("?" in (user_text or "") or bool(PREGUNTA_INFO_RE.search(t))) and fh["hora"] is None and fh["fecha"] is None
    turno_en_flujo = bool(fh["turno"]) and (etapa in ["ofrecio_horarios", "pregunto_dia", "confirmar_horario"] or bool(meta.get("cita_agendada")))
    if es_pregunta_info and not turno_en_flujo and not rechaza and not pref_dias and not VISITA_RE.search(t) and not detectar_restriccion_horaria(user_text) and not (etapa == "ofrecio_horarios" and elegir_slot_ofrecido(t, meta.get("slots_ofrecidos") or [], fh)):
        return None

    intencion_visita = bool(VISITA_RE.search(t)) or (t in ["2", "2️⃣", "dos", "opcion 2"] and etapa in ["", "agendado"])
    # "puedo el martes", "el sábado en la mañana", "mejor el jueves": hablar de un día ya es hablar de la visita
    if fh["fecha"] is not None and (fh["turno"] or re.search(r"\b(puedo|podria|podemos|me queda|me acomoda|prefiero|mejor|seria)\b", t)):
        intencion_visita = True
    if MATERIAL_RE.search(t) and not VISITA_FUERTE_RE.search(t):
        intencion_visita = False
    en_flujo = etapa in ["ofrecio_horarios", "pregunto_financiamiento", "confirmar_horario", "pregunto_dia"]

    slot_pend = None
    if meta.get("slot_propuesto"):
        try:
            slot_pend = datetime.fromisoformat(meta["slot_propuesto"])
        except Exception:
            slot_pend = None
    if slot_pend is None and (hay_fin or afirma) and historial_usuario and not meta.get("cita_agendada"):
        slot_pend = recuperar_slot_de_historial(historial_usuario)

    # ---------- helpers de respuesta ----------
    def ofrecer(slots, encabezado, pie=""):
        if not slots:
            meta["etapa"] = "pregunto_dia"
            return _resp(
                f"{encabezado}\n\nEn este momento no veo espacios libres en la agenda de los próximos días 😕. "
                "¿Qué día y hora te acomodaría? Me adapto a tu horario y lo coordino directamente con el ingeniero."
            )
        if primer_dia_visitas() and not meta.get("aviso_apertura") and "desde el" not in encabezado:
            meta["aviso_apertura"] = True
            pie = (f"📅 Estamos agendando las visitas desde el {fecha_apertura_txt()}, cuando terminemos los últimos detalles."
                   + (f"\n\n{pie}" if pie else ""))
        nuevos = [s.isoformat() for s in slots]
        distintos = nuevos != (meta.get("slots_ofrecidos") or [])
        meta["etapa"] = "ofrecio_horarios"
        meta["slots_ofrecidos"] = nuevos
        txt = (
            f"{encabezado}\n\n{_slots_a_texto(slots)}\n\n"
            "Respóndeme con el número (o dime otro día y hora) y te la dejo registrada al toque."
        )
        if pie:
            txt += f"\n\n{pie}"
        r = _resp(txt)
        if distintos:
            r["_sin_control_repeticion"] = True  # horarios nuevos (p. ej. "en la mañana" de ese día): no es una repetición aunque el texto se parezca
        return r

    def alternativas(slot, motivo):
        alt = get_free_slots(n=3, dia=slot.date()) if motivo != "dia" else []
        if not alt:
            alt = get_free_slots(n=3)
        if motivo == "ocupado":
            enc = f"Uy{coma_nom}, el {format_fecha_es(slot, relativo=True)} ya está tomado 😕. Estos son los horarios libres más cercanos:"
        elif motivo == "pasado":
            enc = f"Ese horario ya no llego a coordinarlo con el ingeniero{coma_nom} 😅. Estos son los horarios libres más próximos:"
        elif motivo == "dia":
            enc = f"Ese día no tenemos atención de visitas{coma_nom}. Te propongo estos horarios libres:"
        elif motivo == "apertura":
            meta["aviso_apertura"] = True
            enc = (f"Te cuento{coma_nom}: estamos dando los últimos detalles a las casas (pasamanos y barandas), así que las visitas "
                   f"las estamos agendando desde el {fecha_apertura_txt()} 😊. Estos son los primeros horarios libres:")
        else:
            enc = f"Ese horario no lo tengo disponible{coma_nom} 😕. Estos son los horarios libres más cercanos a lo que me pides:"
        return ofrecer(alt, enc)

    def reservar(slot):
        notas = f"Pago: {resumen_financiero(meta)} | Cocina: {meta.get('estilo_cocina', 'Por elegir')} | Canal: {canal}"
        ok, det, ev_id = create_calendar_event(nombre_cliente, telefono or "sin número", slot.isoformat(), notas)
        if ok:
            meta.update({
                "cita_agendada": True, "fecha_cita": slot.isoformat(), "evento_id": ev_id or "",
                "ts_cita_creada": datetime.now(timezone.utc).isoformat(), "recordatorio_para": "", "visita_estado": "",
                "pregunta_owner_visita": "", "pregunta_owner_visita_2": "", "rescate_no_asistio": False,
                "etapa": "agendado", "slot_propuesto": "", "slots_ofrecidos": [], "pregunta_fin_pendiente": False,
                "dia_contexto": "", "rechazos_horario": 0
            })
            meta["etapa"] = "pregunto_acompanantes"  # como el asesor: "¿será una visita familiar?"
            extra = ""
            if meta.get("fin_modalidad") == "contado":
                extra = "Si deseas, antes de la visita te enviamos la Copia Literal de SUNARP para que tu abogado la revise. "
            elif calif is False:
                extra = ("Ese día también te orientamos con el crédito y, si gustas, te contactamos sin costo con nuestro "
                         "asesor hipotecario aliado para que sepas cuánto te financia el banco. ")
            elif meta.get("fin_inicial") is True and meta.get("fin_credito_aprobado") is not True:
                extra = ("Como ya cuentas con tu inicial, en la visita te entregamos la Copia Literal y HR/PU de SUNARP "
                         "para que tu banco te evalúe el crédito rápido. ")
            try:
                alertar_asesor(f"📅 Nueva visita SAGUE: {nombre_cliente} (+{telefono or 's/n'}) el {det} | Pago: {resumen_financiero(meta)} | Canal: {canal}")
            except Exception:
                pass
            return _resp(
                f"¡Listo{coma_nom}! ✅ Tu visita guiada quedó registrada para el *{det}*\n\n"
                f"📍 Urb. Santa Teresa, Lambayeque (calles 5 de Febrero y Andrés Lastres, frente a la loza deportiva, "
                f"a 1 min de la Av. Ramón Castilla): {MAPS_URL}\n\n"
                "Ese día te mostramos los 3 pisos, los 2 diseños de cocina y te explicamos en obra el Bono Especial de la 1ra Unidad. "
                f"{extra}Si surge algún cambio, me escribes por aquí y lo reprogramamos 😊\n\n{PREGUNTA_ACOMPANANTES}"
            )
        if det in ["ocupado", "invalido"]:
            return alternativas(slot, "ocupado" if det == "ocupado" else "horario")
        # Error técnico de Calendar: no perder al cliente
        meta["slot_propuesto"] = slot.isoformat()
        meta["etapa"] = "confirmacion_manual"
        try:
            alertar_asesor(f"⚠️ SAGUE: {nombre_cliente} (+{telefono or 's/n'}) pidió visita el {format_fecha_es(slot)}, "
                                   f"pero Calendar falló ({det[:120]}). Regístrala y confírmale manualmente.")
        except Exception:
            pass
        return _resp(
            f"¡Perfecto{coma_nom}! Tomé nota de tu visita para el *{format_fecha_es(slot, relativo=True)}* 🙌. "
            "En unos minutos el ingeniero encargado te confirma por aquí el registro."
        )

    def manejar_slot(slot, confirmado=False):
        # Reprogramación de una cita ya agendada
        if meta.get("cita_agendada") and meta.get("evento_id"):
            ok, det = update_calendar_event(meta["evento_id"], slot.isoformat())
            if ok:
                meta.update({"fecha_cita": slot.isoformat(), "etapa": "agendado", "slot_propuesto": "", "slots_ofrecidos": [],
                             "recordatorio_para": "", "ts_cita_creada": datetime.now(timezone.utc).isoformat()})
                try:
                    alertar_asesor(f"🔁 Visita reprogramada: {nombre_cliente} (+{telefono or 's/n'}) ahora el {det}")
                except Exception:
                    pass
                return _resp(f"¡Hecho{coma_nom}! 🔁 Reprogramé tu visita para el *{det}*\nTe esperamos en Urb. Santa Teresa: {MAPS_URL}")
            if det in ["ocupado", "invalido"]:
                return alternativas(slot, "ocupado" if det == "ocupado" else "horario")
            # Falla técnica de Calendar: NO crear otra cita (quedarían dos); el asesor la mueve a mano
            meta.update({"slot_propuesto": slot.isoformat(), "etapa": "confirmacion_manual"})
            try:
                alertar_asesor(f"⚠️ SAGUE: {nombre_cliente} (+{telefono or 's/n'}) quiere MOVER su visita al {format_fecha_es(slot)}, "
                               f"pero Calendar falló ({str(det)[:100]}). Muévela a mano y confírmale.")
            except Exception:
                pass
            return _resp(f"¡Perfecto{coma_nom}! Tomé nota del cambio de tu visita al *{format_fecha_es(slot, relativo=True)}* 🙌. "
                         "En unos minutos te confirmo por aquí.")
        estado, motivo = verificar_slot(slot)
        if estado == "invalido":
            return alternativas(slot, motivo)
        if estado == "ocupado":
            return alternativas(slot, "ocupado")
        meta["slot_propuesto"] = slot.isoformat()
        meta["slots_ofrecidos"] = []
        fecha_txt = format_fecha_es(slot, relativo=True)
        if not confirmado and calif is None and EXIGIR_FILTRO_FINANCIERO:
            meta["etapa"] = "pregunto_financiamiento"
            meta["pregunta_fin_pendiente"] = True
            ctx = "Como lo evalúas con crédito hipotecario, una" if meta.get("fin_modalidad") == "credito" else "Una"
            return _resp(
                f"¡Claro que sí{coma_nom}! El *{fecha_txt}* está libre ✅ y te lo dejo separado.\n\n"
                f"{ctx} consulta rápida para confirmártelo con el ingeniero: ¿ya cuentas con tu cuota inicial "
                "(desde el 10%, aprox. $13,500 USD) o con un crédito preaprobado en tu banco?"
            )
        if not confirmado and calif is False:
            meta["etapa"] = "confirmar_horario"
            return _resp(
                f"Gracias por contarme{coma_nom} 😊. No te preocupes: como las casas ya están construidas y con título en SUNARP, "
                "se compran al contado o con crédito hipotecario, y el banco solo pide desde el 10% de inicial (aprox. $13,500 USD). "
                "Si gustas, te ponemos en contacto sin costo con nuestro asesor hipotecario aliado para que te evalúe y sepas "
                "exactamente cuánto te financian.\n\n"
                f"¿Te mantengo la visita del *{fecha_txt}* para que conozcas las casas y ahí mismo te orientamos con el banco? "
                "Respóndeme *sí* y te la confirmo."
            )
        return reservar(slot)

    # ---------- 0c) Respuesta al recordatorio de visita ----------
    if etapa == "confirmar_asistencia" and (afirma or niega) and not rechaza and fh["hora"] is None and fh["fecha"] is None:
        if afirma:
            meta.update({"etapa": "agendado", "asistencia_confirmada": True})
            try:
                f_c = format_fecha_es(datetime.fromisoformat(meta["fecha_cita"]), relativo=True)
            except Exception:
                f_c = "la fecha acordada"
            alertar_asesor(f"✅ SAGUE: {nombre_cliente} (+{telefono or 's/n'}) CONFIRMÓ su visita del {f_c}.")
            return _resp(f"¡Perfecto{coma_nom}! 🙌 Te esperamos el *{f_c}* en Urb. Santa Teresa, frente a la loza deportiva. "
                         f"Aquí el mapa por si acaso: {MAPS_URL}")
        nom_c = nombre_cliente.split()[0] if nombre_cliente not in ["Interesado", "Cliente", ""] else ""
        return ofrecer(get_free_slots(n=3), f"Sin problema{coma_nom} 😊, la reprogramamos. Estos son los próximos horarios libres:")

    # ---------- 0d) Aceptó que le enviemos la Copia Literal (seguimiento post-visita, compra al contado) ----------
    if etapa == "ofrecio_copia" and (afirma or niega):
        meta["etapa"] = ""
        if afirma:
            alertar_asesor(f"📄 SAGUE: {nombre_cliente} (+{telefono or 's/n'}) pidió la COPIA LITERAL de SUNARP para su abogado. Envíasela hoy.")
            return _resp(f"¡Listo{coma_nom}! 📄 Hoy mismo te hacemos llegar la Copia Literal completa por aquí para que tu abogado la revise. "
                         "Cualquier consulta legal que tenga, con gusto la vemos.")
        return _resp(f"Perfecto{coma_nom} 😊. Cuando la necesites, me avisas y te la enviamos al toque.")

    # ---------- 0b) Nos dijo su tope de presupuesto (lead de formulario con "No está en mi rango") ----------
    if etapa in ("pregunto_presupuesto", "pregunto_moneda_monto"):
        r_pres = responder_presupuesto(user_text, nom, meta)  # honesto: si no alcanza, inicial + crédito; si no dice moneda, pregunta
        if r_pres and fh["hora"] is None:
            return r_pres

    # ---------- 0a) Aceptó que el asesor hipotecario lo contacte ----------
    if etapa == "ofrecio_asesor" and (afirma or niega):
        meta["etapa"] = ""
        if afirma:
            meta["asesor_solicitado"] = True
            aviso = (f"📞 SAGUE: {nombre_cliente} (+{telefono or 's/n'}) pidió evaluación con el asesor hipotecario. "
                     f"Situación: {resumen_financiero(meta)}. Contáctalo hoy.")
            for dest in {OWNER_WA, ASESOR_HIPOTECARIO_WA} - {""}:
                try:
                    send_wa_text(dest, aviso)
                except Exception:
                    pass
            txt = (f"¡Listo{coma_nom}! 🙌 Ya le pasé tus datos a nuestro asesor hipotecario aliado; te escribirá a este número "
                   "para evaluarte sin costo. ")
        else:
            txt = f"Perfecto{coma_nom}, sin problema 😊. "
        nom_c = nombre_cliente.split()[0] if nombre_cliente not in ["Interesado", "Cliente", ""] else ""
        return _resp(txt + "Mientras tanto, lo ideal es que conozcas las casas en persona. " + cierre_contextual(meta, nom_c))

    # ---------- 0) Aceptó que le enviemos planos y renders ----------
    if etapa == "ofrecio_material" and afirma:
        meta["etapa"] = "pregunto_dia"
        r = _resp(
            f"¡Listo{coma_nom}! 📄 Te adjunto los planos de los 3 pisos (el 1er y 2do piso con "
            "acabados y el 3ro en casco, sin tarrajear) y los 2 diseños de cocina: Gris Grafito con LED y Madera Rovere con Taupe. "
            "Cuando quieras conocerlas en persona, dime el día y la hora y te reservo la visita 🏡"
        )
        r["enviar_ficha_tecnica"] = True
        r["enviar_renders_cocina"] = True
        r["_momento_fotos"] = "planos"
        return r
    if etapa == "ofrecio_material" and (niega or rechaza):
        meta["etapa"] = "pregunto_dia"
        return _resp(f"Perfecto{coma_nom}, quedo atento por aquí 😊. Cualquier duda o cuando quieras visitarnos, me escribes y te ayudo al toque.")

    # ---------- 0f) Repite la opción ("2") mientras esperamos lo de la inicial: recordárselo en corto, sin otra lista ----------
    if etapa == "pregunto_financiamiento" and slot_pend is not None and not hay_fin and \
            re.fullmatch(r"(la |el |opcion |numero )?([1-4]|primer[oa]|segund[oa]|tercer[oa])( opcion)?", t):
        return _resp(f"¡Perfecto{coma_nom}, el *{format_fecha_es(slot_pend, relativo=True)}* ya te lo tengo separado! 🙌 Solo me falta un dato "
                     "para confirmarlo con el ingeniero: ¿ya cuentas con tu cuota inicial o con un crédito preaprobado? "
                     "(si es al contado, dime *contado*)")

    r_tarde = ofrecer_mas_tarde(t, user_text, meta, ofrecer, coma_nom) if etapa == "ofrecio_horarios" else None
    if r_tarde:
        return r_tarde
    # ---------- 0e) Restricciones y preferencias humanas ("trabajo hasta las 5", "fin de semana a las 10") ----------
    if intencion_visita or en_flujo or pref_dias or rechaza or meta.get("cita_agendada") or detectar_restriccion_horaria(user_text):
        pide_fin = calif is None and EXIGIR_FILTRO_FINANCIERO and not meta.get("cita_agendada")
        r_pref = agenda_por_preferencias(user_text, fh, pref_dias, meta, ofrecer, coma_nom, pide_fin, rechaza)
        if r_pref:
            return r_pref
    r_fecha = completar_fecha_por_contexto(fh, meta, coma_nom, t)  # "a eso de las 4.30" tras ofrecer el sábado
    if r_fecha:
        return r_fecha

    # ---------- 1) El cliente propone o elige un horario concreto ----------
    slot_nuevo = None
    if etapa in ["ofrecio_horarios", "pregunto_dia"] and meta.get("slots_ofrecidos"):
        slot_nuevo = elegir_slot_ofrecido(t, meta["slots_ofrecidos"], fh)
    # "a las 4" justo después de hablar del sábado => sábado a las 4
    if slot_nuevo is None and fh["hora"] is not None and fh["fecha"] is None and en_flujo and meta.get("dia_contexto"):
        try:
            d_ctx = datetime.fromisoformat(meta["dia_contexto"]).date()
            if d_ctx >= datetime.now(LIMA_TZ).date():
                fh["fecha"] = d_ctx
        except Exception:
            pass
    if slot_nuevo is None and fh["hora"] is not None and (fh["fecha"] is not None or en_flujo or intencion_visita or hay_fin):
        slot_nuevo = construir_slot(fh)
    if slot_nuevo is not None:
        if "?" in (user_text or ""):
            r_preg = proponer_si_pregunta(slot_nuevo, meta, coma_nom)
            if r_preg:
                return r_preg
        return manejar_slot(slot_nuevo)

    # ---------- 1b) No le acomodan los horarios ofrecidos ("ninguno", "no puedo", "otro día") ----------
    if rechaza or (pref_dias and (en_flujo or intencion_visita)):
        rechazos = int(meta.get("rechazos_horario") or 0) + (1 if rechaza else 0)
        meta["rechazos_horario"] = rechazos
        if rechazos >= 4 and not (fh["fecha"] or fh["turno"] or pref_dias):
            meta["etapa"] = "ofrecio_material"
            meta["slots_ofrecidos"] = []
            return _resp(
                f"Entiendo{coma_nom}, sin ningún problema 😊. Cuando tengas un espacio libre me escribes por aquí y te reservo "
                "el horario al instante. Mientras tanto, ¿te envío los planos de los 3 pisos y los 2 diseños de cocina para que los vayas revisando?"
            )
        if rechazos >= 3 and not (fh["fecha"] or fh["turno"] or pref_dias):
            # No insistir con más listas: pasar a conversación abierta y avisar al asesor humano
            meta["etapa"] = "pregunto_dia"
            meta["slots_ofrecidos"] = []
            try:
                alertar_asesor(f"🔔 SAGUE: {nombre_cliente} (+{telefono or 's/n'}) rechazó varios horarios. "
                                       f"Último mensaje: \"{user_text[:150]}\". Conviene llamarle para coordinar.")
            except Exception:
                pass
            return _resp(
                f"Entiendo{coma_nom}, no te preocupes 😊. Cuéntame con calma qué día y a qué hora te quedaría mejor "
                "(me adapto a tu horario, incluso temprano o al final del día) y lo coordino directamente con el ingeniero. Si prefieres, también te puede llamar "
                "el asesor para cuadrarlo en 2 minutos, ¿te parece?"
            )
        vistos = []
        for s in meta.get("slots_ofrecidos") or []:
            try:
                vistos.append(datetime.fromisoformat(s))
            except Exception:
                pass
        if fh["fecha"] is not None:
            slots = get_free_slots(n=3, dia=fh["fecha"], turno=fh["turno"], excluir=[v.isoformat() for v in vistos])
        else:
            slots = get_free_slots(n=3, turno=fh["turno"], dias_semana=pref_dias,
                                   excluir_fechas=None if pref_dias else {v.date() for v in vistos})
            if not slots:
                slots = get_free_slots(n=3, turno=fh["turno"], dias_semana=pref_dias, excluir=[v.isoformat() for v in vistos])
        if meta.get("cita_agendada") and rechaza:
            enc = f"Sin problema{coma_nom}, la reprogramamos 😊. Estas son otras opciones libres:"
        elif pref_dias == {5, 6}:
            enc = f"¡Claro{coma_nom}! Para el fin de semana tengo libres estos horarios:"
        elif pref_dias:
            enc = f"¡Claro{coma_nom}! Entre semana tengo libres estos horarios:"
        else:
            enc = f"Sin problema{coma_nom} 😊 Te busco otras opciones en días distintos:"
        return ofrecer(
            slots, enc,
            "Si ninguno te acomoda, dime el día y la hora que prefieras y me adapto a tu horario."
        )

    # ---------- 2) Esperábamos un "sí" para mantener el horario ----------
    if etapa == "confirmar_horario" and slot_pend is not None:
        if afirma:
            return manejar_slot(slot_pend, confirmado=True)
        if niega or re.search(r"\botro (dia|horario)\b", t):
            return ofrecer(get_free_slots(n=3), f"Sin problema{coma_nom}. Estos son los próximos horarios libres por si te acomoda otro:")
        if hay_fin:
            return manejar_slot(slot_pend)

    # ---------- 3) Respondió sobre su financiamiento y había un horario pendiente ----------
    if slot_pend is not None and hay_fin and not meta.get("cita_agendada"):
        return manejar_slot(slot_pend)

    # ---------- 4) Respondió sobre su financiamiento sin horario pendiente ----------
    if hay_fin and (fin_pendiente or en_flujo or intencion_visita):
        if calif is True:
            previos = slots_vigentes(meta)  # p. ej. los de fin de semana que pidió: no cambiarle la lista
            if previos:
                return ofrecer(previos, f"¡Excelente{coma_nom}! 🙌 Entonces elige el horario que mejor te acomode:")
            return ofrecer(get_free_slots(n=3), f"¡Excelente{coma_nom}! 🙌 Entonces coordinemos tu visita guiada. Estos son los horarios libres más próximos:")
        if calif is False and "sin_inicial" in (meta.get("ya_explicado") or []) and not meta.get("asesor_solicitado"):
            meta["etapa"] = "ofrecio_asesor"
            return _resp(
                f"Perfecto{coma_nom}, entonces con crédito hipotecario 😊. El paso más rápido es que nuestro asesor hipotecario aliado "
                "te evalúe sin costo y te diga cuánto te financia el banco y cuánto necesitarías de inicial. "
                "¿Quieres que te contacte a este número? Respóndeme *sí* y le paso tus datos."
            )
        if calif is False:
            meta["ya_explicado"] = list(set((meta.get("ya_explicado") or []) + ["sin_inicial"]))
            return ofrecer(
                slots_vigentes(meta) or get_free_slots(n=3),
                f"Gracias por contarme{coma_nom} 😊. Como las casas ya están construidas y con título en SUNARP, se compran al contado "
                "o con crédito hipotecario (el banco pide desde el 10% de inicial, aprox. $13,500 USD; no manejamos crédito directo). "
                "Si gustas, te contactamos sin costo con nuestro asesor hipotecario aliado para evaluarte.\n\n"
                "Y si deseas conocer las casas mientras tanto, estos son los horarios libres más próximos:"
            )
        if en_flujo or intencion_visita:
            meta["etapa"] = "pregunto_financiamiento"
            meta["pregunta_fin_pendiente"] = True
            return _resp(
                f"¡Perfecto{coma_nom}! Trabajamos con cualquier banco (BCP, BBVA, Interbank, Scotiabank, BanBif). "
                "¿Ya cuentas con tu cuota inicial (desde el 10%, aprox. $13,500 USD) o con un crédito preaprobado? "
                "Así te separo de inmediato el horario de tu visita."
            )

    # ---------- 5) Quiere visitar / pregunta por un día o turno ----------
    if intencion_visita or (en_flujo and (fh["fecha"] is not None or fh["turno"])):
        if meta.get("cita_agendada") and meta.get("fecha_cita") and not (fh["fecha"] or fh["turno"]):
            try:
                f_cita = datetime.fromisoformat(meta["fecha_cita"])
                if f_cita > datetime.now(LIMA_TZ):
                    return _resp(
                        f"¡Ya tienes tu visita registrada{coma_nom}! ✅ Te esperamos el *{format_fecha_es(f_cita, relativo=True)}* "
                        f"en Urb. Santa Teresa: {MAPS_URL}\n\n¿La mantenemos o prefieres cambiarla a otro día/hora?"
                    )
            except Exception:
                pass
        pie = ""
        if calif is None and EXIGIR_FILTRO_FINANCIERO and not meta.get("cita_agendada"):
            meta["pregunta_fin_pendiente"] = True
            pie = ("Y para registrarte con el ingeniero: ¿la compra la evalúas al contado o con crédito hipotecario "
                   "(el banco pide desde el 10% de inicial)?")
        elif calif is False:
            pie = ("Te recuerdo que la compra es al contado o con crédito hipotecario (desde 10% de inicial); en la visita te "
                   "orientamos y te contactamos sin costo con nuestro asesor hipotecario aliado.")
        return ofrecer_por_dia(fh, meta, ofrecer, coma_nom, pie)

    return None
