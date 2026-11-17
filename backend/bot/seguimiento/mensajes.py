"""Textos de rescate 24 h y del protocolo post-visita de 14 días."""
from datetime import datetime, timedelta

from bot.config import LIMA_TZ, PRECIO_CONTADO_USD, PRECIO_LISTA_USD
from bot.conversacion.recursos import elegir_fotos
from bot.conversacion.precio import gancho_m2, precio_m2
from bot.conversacion.presupuesto import linea_contado
from bot.conversacion.slots import _dos_horarios
from bot.integraciones.calendario import verificar_slot
from bot.nlp.financiamiento import estado_financiero
from bot.utils.fechas import DIAS_ES, _ahora, _ts, format_fecha_es
from bot.utils.texto import _primer_nombre, _usd


def _recordar_horarios(meta, coma):
    """'¿Lograste revisar si alguno de los horarios del viernes por la tarde te acomoda?' (lo que escribiría el asesor)."""
    if meta.get("etapa") != "ofrecio_horarios":
        return None
    limite = _ahora() + timedelta(hours=2)
    slots = [x for x in (_ts(i) for i in meta.get("slots_ofrecidos") or []) if x and x > limite]
    if len(slots) < 2:
        return None
    nums = ["1️⃣", "2️⃣", "3️⃣", "4️⃣"]
    if len({x.date() for x in slots}) == 1:
        d = slots[0]
        turno = " por la tarde" if all(x.hour >= 13 for x in slots) else (" por la mañana" if all(x.hour < 13 for x in slots) else "")
        cuando = f"del {DIAS_ES[d.weekday()]} {d.day}{turno}"
    else:
        cuando = "que te pasé"
    lista = "\n".join(f"{nums[i]} {format_fecha_es(x, relativo=True)}" for i, x in enumerate(slots[:4]))
    return (f"¡Hola{coma}! 😊 ¿Lograste revisar si alguno de los horarios {cuando} te acomoda?\n{lista}\n"
            "Respóndeme con el número y te la registro, o dime otro día y hora 🏡")


def _texto_rescate_24h(meta, nombre):
    """El mensaje de rescate según en qué quedó la conversación (dejó en visto)."""
    nom = _primer_nombre(nombre)
    coma = f", {nom}" if nom else ""
    etapa = meta.get("etapa") or ""
    ahora = _ahora()
    # Propuso un horario y quedó pendiente de confirmar
    sp = _ts(meta.get("slot_propuesto"))
    if sp and sp > ahora + timedelta(hours=2):
        meta["etapa"] = "confirmar_horario"
        return (f"¡Hola{coma}! 😊 Te sigo guardando la visita del *{format_fecha_es(sp, relativo=True)}* en Urb. Santa Teresa. "
                "¿Te la confirmo? Respóndeme *sí* y queda registrada, o dime si prefieres otro horario.")
    # Le ofrecimos horarios (p. ej. los del día que pidió) y no eligió: preguntar por ESOS, sin cambiarle la lista
    r_hor = _recordar_horarios(meta, coma)
    if r_hor:
        return r_hor
    # Preguntó el precio al contado y quedó ahí
    if "contado" in (meta.get("ya_explicado") or []) and not meta.get("rescate_contado"):
        meta["rescate_contado"] = True
        return (f"¡Hola{coma}! 😊 Quedé pendiente con lo del precio: {linea_contado(False)} Lo mejor es que la veas y lo conversen en persona. "
                + _dos_horarios(meta))
    # Le ofrecimos el asesor hipotecario y no respondió
    if etapa == "ofrecio_asesor" and not meta.get("asesor_solicitado"):
        meta["etapa"] = "ofrecio_asesor"
        return (f"¡Hola{coma}! 😊 Quedé pendiente de tu respuesta: ¿quieres que nuestro asesor hipotecario aliado te evalúe *sin costo*? "
                "En 24 h te diría cuánto te financia el banco y cuánto necesitarías de inicial. Respóndeme *sí* y le paso tus datos.")
    # Presupuesto menor al precio (Caso Lisve)
    tope = meta.get("presupuesto_tope")
    if etapa == "pregunto_presupuesto" or (tope and tope < PRECIO_LISTA_USD):
        if not tope:
            meta["etapa"] = "pregunto_presupuesto"
            return (f"¡Hola{coma}! 😊 Te cuento que el precio es negociable: {linea_contado(False)} Y para que lo compares: hoy sale a "
                    f"*{_usd(precio_m2())} por m²*, menos que un depa en Chiclayo. ¿Qué presupuesto manejas? "
                    "Así te confirmo con transparencia si llegamos.")
        if tope >= PRECIO_CONTADO_USD * 0.92:
            return (f"¡Hola{coma}! 😊 Estuve revisando tu caso: con {_usd(tope)} estamos cerca. {linea_contado()} " + _dos_horarios(meta))
        # Presupuesto lejos del precio: NUNCA prometer que se llega; ofrecer el camino real (inicial + crédito)
        meta["etapa"] = "ofrecio_asesor"
        return (f"¡Hola{coma}! 😊 Estuve pensando en tu caso: con {_usd(tope)} podrías usarlo como cuota inicial y financiar el resto con "
                "crédito hipotecario. ¿Quieres que nuestro asesor hipotecario aliado te evalúe *sin costo* y te diga cuánto te financian? "
                "Respóndeme *sí* y le paso tus datos.")
    # Al contado (sin cita)
    if meta.get("fin_modalidad") == "contado":
        return (f"¡Hola{coma}! 😊 Para tu tranquilidad, ¿quieres que te adelantemos la Copia Literal de SUNARP para que verifiques que la casa está "
                "libre de cargas? O, si prefieres, separamos 15 minutos para que veas los acabados y bloquees el Bono de Lanzamiento de la 1ra Unidad. "
                + _dos_horarios(meta))
    # Crédito hipotecario (dejó en visto horarios o la pregunta de inicial)
    if meta.get("fin_modalidad") == "credito" or meta.get("fin_inicial") is not None or meta.get("fin_credito_aprobado") is not None:
        if estado_financiero(meta) is False and not meta.get("asesor_solicitado"):
            meta["etapa"] = "ofrecio_asesor"
            return (f"¡Hola{coma}! 😊 ¿Ya lo vienes viendo con algún banco (BCP, BBVA, Interbank…)? Si quieres, nuestro asesor hipotecario aliado "
                    "te evalúa *sin costo* y te dice exactamente cuánto te financian. Respóndeme *sí* y le paso tus datos.")
        return (f"¡Hola{coma}! 😊 ¿Ya lo vienes viendo con algún banco en particular (BCP, BBVA, Interbank…)? Lo más práctico es que conozcas "
                "los 3 pisos en persona y con la Copia Literal y HR/PU de SUNARP tu sectorista arme la simulación exacta. " + _dos_horarios(meta))
    # Solo pidió info / precio / distribución / cocinas
    if meta.get("material_enviado"):
        if not meta.get("estilo_cocina") or "Por elegir" in str(meta.get("estilo_cocina")):
            return (f"¡Hola{coma}! 😊 ¿Pudiste revisar los planos y los 2 diseños de cocina? ¿Cuál va más contigo: el *Gris Grafito con LED* "
                    "o el *Madera Rovere con Taupe*? En persona se aprecian mucho mejor. " + _dos_horarios(meta))
        return (f"¡Hola{coma}! 😊 ¿Pudiste revisar la distribución de los 200 m² en 3 pisos? Me encantaría mostrarte en persona cómo queda "
                f"la cocina en {meta.get('estilo_cocina')}. " + _dos_horarios(meta))
    return (f"¡Hola{coma}! 😊 Te escribo por si te quedó alguna duda sobre las casas de Urb. Santa Teresa (200 m², 3 pisos, entrega inmediata). "
            + gancho_m2(meta, "seguimiento") + " Lo mejor es que las conozcas en persona. " + _dos_horarios(meta))


def _toque_post_visita(clave, meta, nombre):
    nom = _primer_nombre(nombre)
    coma = f", {nom}" if nom else ""
    if clave == "t1":
        fotos = elegir_fotos("post_visita", meta)  # renders amoblados: para que la imaginen en casa con la familia
        amob = " y cómo se vería amoblada (muebles de referencia), para que la vean con calma en familia" if fotos else ""
        return ("post_visita", f"¡Gracias por visitarnos{coma}! 🏡 Fue un gusto mostrarte las casas de Urb. Santa Teresa. Te comparto el resumen: "
                f"los planos de los 3 pisos, los 2 diseños de cocina{amob}. La casa tiene título independizado en SUNARP, libre de cargas, "
                "y podemos enviarte la Copia Literal cuando la necesites. Cualquier duda que te haya quedado, me escribes por aquí 😊",
                {"enviar_ficha_tecnica": True, "enviar_renders_cocina": True, "recursos": fotos})
    if clave == "t2":
        if meta.get("fin_modalidad") == "contado":
            meta["etapa"] = "ofrecio_copia"
            return ("banco_legal", f"¡Hola{coma}! 😊 ¿Te enviamos la Copia Literal completa de SUNARP para que tu abogado confirme que la casa "
                    "está libre de cargas y gravámenes? Respóndeme *sí* y te la hacemos llegar.", None)
        meta["etapa"] = "ofrecio_asesor"
        return ("banco_legal", f"¡Hola{coma}! 😊 ¿Cómo te fue con el banco? Si tu sectorista aún no revisa tus ingresos con la partida de la casa, "
                "nuestro asesor hipotecario aliado te puede evaluar *sin costo* en 24 h. ¿Quieres que te contacte? Respóndeme *sí*.", None)
    if clave == "t3":
        hoy = _ahora().date()
        sabado = hoy + timedelta(days=(5 - hoy.weekday()) % 7 or 7)
        pref = [datetime(sabado.year, sabado.month, sabado.day, h, 0, tzinfo=LIMA_TZ) for h in (11, 16)]
        pref = [p for p in pref if verificar_slot(p)[0] in ["libre", "sin_verificar"]] or None
        fotos = elegir_fotos("segunda_visita", meta)  # una foto que reavive la emoción (sala amoblada / terraza)
        return ("segunda_visita", f"¡Hola{coma}! 😊 Este fin de semana estaremos en Santa Teresa con el muestrario físico de melamina para definir "
                "los acabados de la 1ra unidad. ¿Tienen 20 minutos para venir a tomar medidas de sus muebles y revisar una propuesta formal de cierre? "
                + _dos_horarios(meta, pref), {"recursos": fotos} if fotos else None)
    if clave == "t4":
        return ("propuesta", f"¡Hola{coma}! 😊 Si la casa les encantó, este es un buen momento para presentarnos su *propuesta formal de compra*: "
                "el Bono de la 1ra Unidad sigue vigente y podemos cerrar condiciones especiales si se firma el contrato de arras en 72 horas. "
                f"Recuerden que hoy sale a *{_usd(precio_m2())} por m²* y, una vez vendida la 1ra, la casa de al lado queda a precio fijo "
                "de lista. ¿Les parece si lo conversamos?", None)
    if clave == "t5":
        meta["etapa"] = "cerrado"
        return ("cierre", f"Hola{coma}, para no ser invasivos con tus tiempos, quería confirmar si por ahora han decidido pausar la compra en "
                "Urb. Santa Teresa, para cerrar tu ficha de este mes y liberar el bono de 1ra unidad a otra familia en evaluación. Quedo atento 😊", None)
    return (None, "", None)
