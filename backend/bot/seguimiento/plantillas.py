"""Plantillas de seguimiento por tenant e idioma (modo 'catalogo'): recordatorio, protocolo post-visita de 14 días
(45 min, 48 h, día 5, día 10, día 14), no asistió y rescate de 24 h.

Fuente, en orden: playbook["seguimiento"][idioma][clave] (editable desde /app > Ajustes) -> plantilla de la industria
del tenant (plantillas_industria: inmobiliaria, salud/clínicas, B2B) -> DEFECTO[idioma][clave] (textos neutros). Cada toque se puede apagar con playbook["interruptores"]["seguimiento_<clave>"] = false.
Variables disponibles en los textos: {coma} (", Ana" o vacío), {nombre}, {empresa}, {asesor}, {producto}, {direccion},
{mapa}, {evento}, {cuando}, {fecha}, {bono}, {valor}, {horarios}, {presupuesto}, {cuota}.
SAGUE (modo 'sague_legacy') sigue usando bot/seguimiento/mensajes.py sin cambios."""
from bot import playbooks, tenant
from bot.seguimiento import plantillas_industria

CLAVES_POST_VISITA = ("post_45m", "post_48h", "post_dia5", "post_dia10", "post_dia14")

# Medios del catálogo que acompañan cada toque (catalog_media.trigger_moment)
MEDIA_POR_TOQUE = {"post_45m": ["POST_VISIT_45M|OPTION_RENDER|SPECS_PDF"], "post_dia5": ["OPTION_RENDER|PROOF_RESULTS|VIDEO_TOUR"],
                   "post_dia10": ["PROOF_RESULTS"], "no_asistio": ["LOCATION_MAP|LOCATION_FACADE"],
                   "rescate": ["RESCUE_24H|PROOF_RESULTS|OPTION_RENDER|VIDEO_TOUR"]}

DEFECTO = {
    "es": {
        "recordatorio": "¡Hola{coma}! 😊 Te recuerdo tu {evento} *{cuando} {fecha}* con {empresa}.\n📍 {direccion} {mapa}\n\n"
                        "¿Nos confirmas tu asistencia? Si se te complica, dime y la reprogramamos sin problema.",
        "pregunta_asesor": "❓ {empresa}: ¿se realizó la {evento} de {nombre} ({telefono}) del {fecha}?\nRespóndeme:\n• *vino {telefono}*\n"
                           "• *no vino {telefono}*\nCon eso activo el seguimiento post-visita (o el rescate si no vino).",
        "post_45m": "¡Gracias por tu tiempo hoy{coma}! 🙌 Te dejo el resumen de *{producto}* para que lo revises con calma (y con tu familia o equipo). "
                    "Cualquier duda que te haya quedado, me escribes por aquí 😊",
        "post_48h_contado": "¡Hola{coma}! 😊 ¿Te ayudo con algún documento para avanzar con *{producto}*? Si quieres, te envío la información "
                            "formal para que la revises con calma.",
        "post_48h_financiado": "¡Hola{coma}! 😊 ¿Pudiste revisar las opciones de pago? Con {presupuesto} la cuota quedaría en {cuota}. "
                               "Si quieres, {asesor} te arma el plan exacto sin compromiso.",
        "post_dia5": "¡Hola{coma}! 😊 ¿Te quedó alguna duda sobre *{producto}*? Si te sirve, coordinamos una segunda {evento} corta "
                     "para revisar los detalles en persona:\n{horarios}",
        "post_dia10": "¡Hola{coma}! 😊 Si *{producto}* es lo que buscas, este es un buen momento para avanzar: {bono}. ¿Lo conversamos?",
        "alerta_dia10": "📞 {empresa}: día 10 post-visita de {nombre} ({telefono}). Buen momento para llamarle y negociar. Pago: {pago}.",
        "post_dia14": "Hola{coma}, para no ser invasivos con tus tiempos, quería confirmar si por ahora prefieres pausar lo de *{producto}*. "
                      "Así cierro tu ficha de este mes y libero el beneficio para otra persona en evaluación. Quedo atento 😊",
        "no_asistio": "¡Hola{coma}! 😊 Te esperábamos para tu {evento}, ¿todo bien? Si se te complicó, no te preocupes, la reprogramamos:\n{horarios}",
        "rescate_horarios": "¡Hola{coma}! 😊 ¿Lograste ver si alguno de estos horarios te acomoda?\n{horarios}\nRespóndeme con el número y te la registro.",
        "rescate_objecion": "¡Hola{coma}! 😊 Me quedé pensando en lo del precio: {valor}. Lo mejor es que lo veas en persona, sin compromiso:\n{horarios}",
        "rescate_presupuesto": "¡Hola{coma}! 😊 Revisé tu caso: con {presupuesto} la cuota quedaría en {cuota}. ¿Quieres que lo veamos juntos?\n{horarios}",
        "rescate_general": "¡Hola{coma}! 😊 Te escribo por si te quedó alguna duda sobre *{producto}*. {bono}. Lo mejor es verlo en persona:\n{horarios}",
    },
    "en": {
        "recordatorio": "Hi{coma}! 😊 Quick reminder of your {evento} *{cuando} {fecha}* with {empresa}.\n📍 {direccion} {mapa}\n\n"
                        "Can you confirm you're coming? If something came up, just tell me and we'll reschedule.",
        "pregunta_asesor": "❓ {empresa}: did {nombre} ({telefono}) show up to the {evento} on {fecha}?\nReply:\n• *vino {telefono}* (attended)\n"
                           "• *no vino {telefono}* (no-show)\nThat starts the post-visit follow-up (or the no-show rescue).",
        "post_45m": "Thanks for your time today{coma}! 🙌 Here's a recap of the *{producto}* to look over at home (or with your team). "
                    "Any question at all, just text me here 😊",
        "post_48h_contado": "Hi{coma}! 😊 Can I help with any paperwork to move forward with the *{producto}*? Happy to send the formal details.",
        "post_48h_financiado": "Hi{coma}! 😊 Did you get a chance to look at the payment options? With {presupuesto} the monthly payment would be "
                               "about {cuota}. {asesor} can put together your exact plan, no strings attached.",
        "post_dia5": "Hi{coma}! 😊 Any questions left about the *{producto}*? If it helps, we can set up a short second {evento} to go over the details:\n{horarios}",
        "post_dia10": "Hi{coma}! 😊 If the *{producto}* is what you're looking for, now is a great time to move forward: {bono}. Want to talk it over?",
        "alerta_dia10": "📞 {empresa}: day 10 after the visit for {nombre} ({telefono}). Good time to call and negotiate. Payment: {pago}.",
        "post_dia14": "Hi{coma}, I don't want to crowd your inbox — should I pause things on the *{producto}* for now? That way I can close "
                      "your file this month and release the offer to someone else. Totally fine either way 😊",
        "no_asistio": "Hi{coma}! 😊 We missed you at your {evento} — everything OK? No worries at all, let's find another time:\n{horarios}",
        "rescate_horarios": "Hi{coma}! 😊 Did any of these times work for you?\n{horarios}\nJust reply with the number and I'll book it.",
        "rescate_objecion": "Hi{coma}! 😊 I was thinking about the price question: {valor}. Best way to judge is in person, zero commitment:\n{horarios}",
        "rescate_presupuesto": "Hi{coma}! 😊 I ran your numbers: with {presupuesto} the monthly payment would be about {cuota}. Want to go over it together?\n{horarios}",
        "rescate_general": "Hi{coma}! 😊 Just checking in in case you had any questions about the *{producto}*. {bono}. Best way to see it is in person:\n{horarios}",
    },
}


class _Seguro(dict):
    def __missing__(self, clave):
        return ""


def activo(clave):
    """Toque encendido? (playbook interruptores.seguimiento_post_dia5 = false lo apaga)."""
    return playbooks.interruptor(f"seguimiento_{clave}", True)


CLAVES_EDITABLES = tuple(k for k in DEFECTO["es"] if k != "pregunta_asesor")


def texto_crudo(clave, idioma):
    """La plantilla sin rellenar que se usaría hoy para este tenant (lo que muestra y edita /app)."""
    idioma = idioma if idioma in DEFECTO else "es"
    return (playbooks.valor(f"seguimiento.{idioma}.{clave}")
            or plantillas_industria.buscar(tenant.actual().get("industry"), idioma, clave)
            or DEFECTO[idioma].get(clave) or DEFECTO["es"].get(clave, ""))


def texto(clave, idioma, variables):
    plantilla = texto_crudo(clave, idioma)
    limpio = plantilla.format_map(_Seguro({k: ("" if v is None else v) for k, v in variables.items()}))
    return "\n".join(l.rstrip() for l in limpio.split("\n")).replace(" .", ".").replace("  ", " ").strip()
