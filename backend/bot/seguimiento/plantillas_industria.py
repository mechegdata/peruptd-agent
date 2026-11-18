"""Plantillas por defecto por industria (ES/EN) para el seguimiento de 14 días y el rescate de 24 h.
Orden de búsqueda en plantillas.texto(): playbook del tenant -> esta tabla (según tenants.industry) -> textos neutros.
Lo que no esté aquí cae al texto neutro de plantillas.DEFECTO."""

ALIAS = {"realestate": "inmobiliaria", "real_estate": "inmobiliaria", "inmobiliaria": "inmobiliaria", "construction": "inmobiliaria",
         "dental": "salud", "clinic": "salud", "clinica": "salud", "medspa": "salud", "health": "salud", "salud": "salud",
         "b2b": "b2b", "industrial": "b2b", "saas": "b2b", "services": "b2b"}


def familia(industria):
    return ALIAS.get((industria or "").lower().strip())


POR_INDUSTRIA = {
    "inmobiliaria": {
        "es": {
            "post_45m": "¡Gracias por venir a conocer *{producto}* hoy{coma}! 🏡 Te dejo los planos y la ficha para que los revises en casa "
                        "con tu familia. Cualquier duda de áreas, acabados o pagos, me escribes por aquí 😊",
            "post_48h_contado": "¡Hola{coma}! 😊 Si decides separar *{producto}*, te ayudo con la minuta y los documentos de compra. "
                                "¿Te envío la lista de requisitos?",
            "post_48h_financiado": "¡Hola{coma}! 😊 ¿Pudiste revisar el financiamiento? Con una inicial de {presupuesto} la cuota quedaría "
                                   "en {cuota}. {asesor} puede pre-evaluarte con el banco sin compromiso.",
            "post_dia5": "¡Hola{coma}! 😊 Muchas familias vuelven una segunda vez para ver la luz y la vista a otra hora. "
                         "¿Te gustaría una segunda visita corta?\n{horarios}",
            "post_dia10": "¡Hola{coma}! 😊 Te cuento que quedan pocas unidades como *{producto}*: {bono}. ¿Quieres que te la reserve?",
            "post_dia14": "Hola{coma}, para no ser invasivos, ¿prefieres que pausemos lo de *{producto}* por ahora? Así libero la "
                          "separación para otra familia en evaluación. Quedo atento 😊",
            "no_asistio": "¡Hola{coma}! 😊 Te esperábamos en el proyecto, ¿todo bien? Si se te complicó, reprogramamos tu visita:\n{horarios}",
            "rescate_objecion": "¡Hola{coma}! 😊 Sobre el precio: {valor}. Además el valor por m² de la zona sigue subiendo. "
                                "Lo mejor es verlo en persona:\n{horarios}",
            "rescate_presupuesto": "¡Hola{coma}! 😊 Hice los números: con {presupuesto} de inicial la cuota sería de {cuota}. "
                                   "¿Lo vemos juntos en el proyecto?\n{horarios}",
            "rescate_general": "¡Hola{coma}! 😊 Te escribo por si te quedó alguna duda sobre *{producto}*. {bono}. "
                               "Nada como recorrerlo en persona:\n{horarios}",
        },
        "en": {
            "post_45m": "Thanks for touring the *{producto}* today{coma}! 🏡 Here are the floor plans and spec sheet to review at home "
                        "with your family. Any question about sizes, finishes or payments, just text me 😊",
            "post_48h_contado": "Hi{coma}! 😊 If you decide to reserve the *{producto}*, I can help with the purchase paperwork. "
                                "Want me to send the checklist?",
            "post_48h_financiado": "Hi{coma}! 😊 Did you get to look at financing? With {presupuesto} down, the monthly payment would be "
                                   "about {cuota}. {asesor} can get you pre-qualified, no strings attached.",
            "post_dia5": "Hi{coma}! 😊 A lot of buyers come back a second time to see the light and the view at a different hour. "
                         "Want a quick second visit?\n{horarios}",
            "post_dia10": "Hi{coma}! 😊 Heads-up: only a few units like the *{producto}* are left — {bono}. Want me to hold one for you?",
            "post_dia14": "Hi{coma}, I don't want to crowd you — should we pause the *{producto}* for now? That lets me release the hold "
                          "to another family. Totally fine either way 😊",
            "no_asistio": "Hi{coma}! 😊 We missed you at the property today — everything OK? Let's find another time:\n{horarios}",
            "rescate_objecion": "Hi{coma}! 😊 About the price: {valor}. Plus, price per sq ft in the area keeps climbing. "
                                "Best way to judge is in person:\n{horarios}",
            "rescate_presupuesto": "Hi{coma}! 😊 I ran the numbers: with {presupuesto} down, the monthly payment would be about {cuota}. "
                                   "Want to go over it at the property?\n{horarios}",
            "rescate_general": "Hi{coma}! 😊 Checking in in case you had questions about the *{producto}*. {bono}. "
                               "Nothing beats walking through it:\n{horarios}",
        },
    },
    "salud": {
        "es": {
            "post_45m": "¡Gracias por venir a tu evaluación hoy{coma}! 🦷 Te dejo el resumen del plan de *{producto}* para que lo revises "
                        "con calma. Si te surge cualquier duda sobre el procedimiento o la recuperación, escríbeme 😊",
            "post_48h_contado": "¡Hola{coma}! 😊 ¿Te ayudo a reservar la fecha de tu tratamiento de *{producto}*? Pagando al contado "
                                "aplica el precio especial.",
            "post_48h_financiado": "¡Hola{coma}! 😊 ¿Pudiste revisar el plan de pagos? Con {presupuesto} de inicial la cuota quedaría en "
                                   "{cuota}. También revisamos qué cubre tu seguro, sin compromiso.",
            "post_dia5": "¡Hola{coma}! 😊 ¿Te quedó alguna duda sobre *{producto}*? Si quieres, agendamos una consulta corta con "
                         "{asesor} para resolverla:\n{horarios}",
            "post_dia10": "¡Hola{coma}! 😊 Te cuento que este mes {bono}. Los cupos de agenda para *{producto}* se llenan rápido, "
                          "¿te separo una fecha?",
            "post_dia14": "Hola{coma}, para no insistir de más, ¿prefieres que pausemos tu plan de *{producto}* por ahora? "
                          "Tu evaluación queda guardada para cuando quieras retomarlo 😊",
            "no_asistio": "¡Hola{coma}! 😊 Te esperábamos en tu cita, ¿todo bien? Si se te complicó, la reprogramamos:\n{horarios}",
            "rescate_objecion": "¡Hola{coma}! 😊 Sobre el costo: {valor}. Y puedes pagarlo en cuotas. ¿Te explico en una consulta "
                                "sin costo?\n{horarios}",
            "rescate_presupuesto": "¡Hola{coma}! 😊 Revisé tu caso: con {presupuesto} de inicial la cuota sería de {cuota}. "
                                   "¿Lo vemos en consulta?\n{horarios}",
            "rescate_general": "¡Hola{coma}! 😊 Te escribo por si te quedó alguna duda sobre *{producto}*. {bono}. "
                               "Lo mejor es una evaluación en persona:\n{horarios}",
        },
        "en": {
            "post_45m": "Thanks for coming in for your consultation today{coma}! 🦷 Here's a summary of your *{producto}* plan to review "
                        "at home. Any question about the procedure or recovery, just text me 😊",
            "post_48h_contado": "Hi{coma}! 😊 Want me to lock in a date for your *{producto}* treatment? Paying in full gets the special price.",
            "post_48h_financiado": "Hi{coma}! 😊 Did you get to look at the payment plan? With {presupuesto} down the monthly payment would be "
                                   "about {cuota}. We can also check what your insurance covers, no strings attached.",
            "post_dia5": "Hi{coma}! 😊 Any questions left about the *{producto}*? We can book a quick follow-up with {asesor}:\n{horarios}",
            "post_dia10": "Hi{coma}! 😊 Just so you know, this month {bono}. Treatment slots for the *{producto}* fill up fast — "
                          "want me to hold a date?",
            "post_dia14": "Hi{coma}, I don't want to push — should we pause your *{producto}* plan for now? Your consultation stays on "
                          "file whenever you're ready 😊",
            "no_asistio": "Hi{coma}! 😊 We missed you at your appointment — everything OK? Let's reschedule:\n{horarios}",
            "rescate_objecion": "Hi{coma}! 😊 About the cost: {valor}. And you can split it into monthly payments. Want me to walk you "
                                "through it in a free consult?\n{horarios}",
            "rescate_presupuesto": "Hi{coma}! 😊 I looked at your case: with {presupuesto} down the monthly payment would be about {cuota}. "
                                   "Want to go over it in person?\n{horarios}",
            "rescate_general": "Hi{coma}! 😊 Checking in in case you had questions about the *{producto}*. {bono}. "
                               "Best next step is an in-person evaluation:\n{horarios}",
        },
    },
    "b2b": {
        "es": {
            "post_45m": "¡Gracias por la reunión de hoy{coma}! 🤝 Te dejo la propuesta y la ficha técnica de *{producto}* para que la "
                        "compartas con tu equipo. Si necesitan algo más para decidir, me avisas.",
            "post_48h_contado": "¡Hola{coma}! 😊 ¿Les ayudo con la orden de compra o el alta como proveedor para *{producto}*? "
                                "Les envío lo que su área de compras necesite.",
            "post_48h_financiado": "¡Hola{coma}! 😊 ¿Pudieron revisar el esquema de pagos? Con {presupuesto} el pago mensual quedaría en "
                                   "{cuota}. {asesor} puede ajustar la propuesta al presupuesto de su área.",
            "post_dia5": "¡Hola{coma}! 😊 ¿Surgió alguna pregunta del equipo técnico o de compras sobre *{producto}*? "
                         "Podemos hacer una llamada corta con ellos:\n{horarios}",
            "post_dia10": "¡Hola{coma}! 😊 Si cierran este mes, {bono}. ¿Coordinamos el siguiente paso con quien firma?",
            "post_dia14": "Hola{coma}, para no saturar su bandeja, ¿prefieren que pausemos la propuesta de *{producto}* por ahora? "
                          "La dejo guardada para cuando el presupuesto esté aprobado.",
            "no_asistio": "¡Hola{coma}! 😊 No coincidimos en la reunión de hoy, ¿todo bien? Reprogramemos cuando les acomode:\n{horarios}",
            "rescate_objecion": "¡Hola{coma}! 😊 Sobre la inversión: {valor}. Si les sirve, armamos un caso de ahorro con sus propios "
                                "números:\n{horarios}",
            "rescate_presupuesto": "¡Hola{coma}! 😊 Con un presupuesto de {presupuesto} el pago mensual quedaría en {cuota}. "
                                   "¿Lo revisamos en una llamada?\n{horarios}",
            "rescate_general": "¡Hola{coma}! 😊 Les escribo por si quedó alguna duda sobre *{producto}*. {bono}. "
                               "¿Agendamos una demo corta?\n{horarios}",
        },
        "en": {
            "post_45m": "Thanks for the meeting today{coma}! 🤝 Here's the proposal and spec sheet for the *{producto}* to share with "
                        "your team. If you need anything else to make a decision, just let me know.",
            "post_48h_contado": "Hi{coma}! 😊 Can I help with the PO or vendor onboarding for the *{producto}*? "
                                "Happy to send whatever procurement needs.",
            "post_48h_financiado": "Hi{coma}! 😊 Did you get to review the payment terms? With {presupuesto} the monthly cost would be about "
                                   "{cuota}. {asesor} can tailor the proposal to your budget.",
            "post_dia5": "Hi{coma}! 😊 Did your technical or procurement team have any questions about the *{producto}*? "
                         "Happy to jump on a short call with them:\n{horarios}",
            "post_dia10": "Hi{coma}! 😊 If you sign this month, {bono}. Should we set up the next step with your decision-maker?",
            "post_dia14": "Hi{coma}, I don't want to clutter your inbox — should we pause the *{producto}* proposal for now? "
                          "I'll keep it on file for when the budget is approved.",
            "no_asistio": "Hi{coma}! 😊 Looks like we missed each other at today's meeting — all good? Let's reschedule:\n{horarios}",
            "rescate_objecion": "Hi{coma}! 😊 About the investment: {valor}. If it helps, we can build an ROI case with your own numbers:\n{horarios}",
            "rescate_presupuesto": "Hi{coma}! 😊 With a {presupuesto} budget the monthly cost would be about {cuota}. "
                                   "Want to review it on a call?\n{horarios}",
            "rescate_general": "Hi{coma}! 😊 Checking in in case you had questions about the *{producto}*. {bono}. "
                               "Want a quick demo?\n{horarios}",
        },
    },
}


def buscar(industria, idioma, clave):
    fam = familia(industria)
    return ((POR_INDUSTRIA.get(fam) or {}).get(idioma) or {}).get(clave) if fam else None
