"""Respuestas determinísticas a preguntas frecuentes de compra."""
import re

from bot.config import PRECIO_CONTADO_USD, GASTOS_TEXTO, PLAZO_REFERENCIAL_ANIOS, PRECIO_LISTA_USD, SEPARACION_TEXTO, TASA_REFERENCIAL_TEA
from bot.conversacion.cierres import cierre_contextual
from bot.conversacion.objeciones import responder_precio
from bot.conversacion.presupuesto import linea_contado, responder_presupuesto
from bot.nlp.financiamiento import cuota_referencial
from bot.utils.texto import _usd, limpiar_texto


def responder_faq(user_text, nombre_corto, meta=None):
    """Respuestas fijas a las preguntas frecuentes de compra (crédito y contado). Usan el estado del cliente para no repetir."""
    t = limpiar_texto(user_text)
    meta = meta if meta is not None else {}
    coma = f", {nombre_corto}" if nombre_corto else ""
    fin_rx = r"(banco|credito|hipotecari\w*|financ\w*|prestamo)"
    proc_rx = r"(procedimiento|proceso|como seria|como es|como funciona|como hago|pasos|tramite)"
    es_contado = bool(re.search(r"\b(contado|efectivo|cash|fondos propios)\b", t)) or meta.get("fin_modalidad") == "contado"
    sin_aprobacion = meta.get("fin_credito_aprobado") is False or meta.get("fin_inicial") is False
    # Moneda / tipo de cambio, "está muy caro" y descuento con crédito (ver conversacion/objeciones.py)
    r_pres = responder_presupuesto(user_text, nombre_corto, meta)  # contado, presupuesto, "¿solo tienen esas?", "medio millón"
    if r_pres:
        return r_pres["reply_text"]
    # "Mensual, ¿cuánto sería?" va ANTES del precio: pregunta por la cuota, no por el precio total
    if re.search(r"\b(cuota mensual|mensual\w*|al mes|por mes|cuanto pagaria|cuanto saldria|cuanto seria la cuota|cuanto es la cuota|"
                 r"de cuanto (seria|es|son|saldria) (la|las) cuotas?)\b", t):
        return (
            f"Te doy una referencia{coma} (tasa aprox. {TASA_REFERENCIAL_TEA:g}% anual a {PLAZO_REFERENCIAL_ANIOS} años, sobre el precio de lista de {_usd(PRECIO_LISTA_USD)}):\n"
            f"• Con 10% de inicial ({_usd(PRECIO_LISTA_USD * 0.10)}) → aprox. *{_usd(cuota_referencial(0.10))} al mes*\n"
            f"• Con 20% de inicial ({_usd(PRECIO_LISTA_USD * 0.20)}) → aprox. *{_usd(cuota_referencial(0.20))} al mes*\n\n"
            "La cuota exacta la define tu banco según tu evaluación, y con el Bono Especial de la 1ra Unidad el monto baja. "
            "Si quieres, nuestro asesor hipotecario aliado te hace la simulación sin costo.\n\n"
            + cierre_contextual(meta, nombre_corto)
        )
    # "¿Eso es al contado?" (sobre el precio que se le dio): confirmar cuál es el precio al contado
    if re.search(r"^(y |o sea |osea )?(eso|ese|ese precio|el precio|esos|ese monto) (es|seria|son|sera)( el precio)? (al contado|contado|en efectivo)\b", t):
        meta["ya_explicado"] = list(set((meta.get("ya_explicado") or []) + ["contado"]))
        return (f"Así es{coma} 😊 {linea_contado()} El valor de lista ({_usd(PRECIO_LISTA_USD)}) es la referencia si la compras con "
                "crédito hipotecario de cualquier banco (desde 10% de inicial).\n\n¿Cómo lo evaluarías tú: al contado o con crédito?")

    r_precio = responder_precio(user_text, nombre_corto, meta)
    if r_precio:
        return r_precio

    # ---------------- CRÉDITO ----------------
    # "¿En cuántos años es para pagar?" (lo define el banco: nosotros no financiamos directo)
    if re.search(r"\b(cuantos anos|a cuantos anos|en cuanto tiempo|que plazo|el plazo|plazo para pagar|anos para pagar|tiempo para pagar|"
                 r"hasta cuantos anos)\b", t):
        meta["etapa"] = "ofrecio_asesor"
        return (f"Eso lo define el banco con el que saques tu crédito hipotecario{coma} 😊: nosotros no financiamos directamente, pero los "
                "bancos suelen dar *de 5 hasta 25 años* (algunos hasta 30). Como referencia, con 10% de inicial y a "
                f"{PLAZO_REFERENCIAL_ANIOS} años, la cuota sale aprox. *{_usd(cuota_referencial(0.10))} al mes*.\n\n"
                "Si quieres, te apoyamos con nuestro asesor hipotecario aliado: te evalúa *sin costo* y te dice a cuántos años y cuánto "
                "te financian. ¿Le paso tus datos? Respóndeme *sí*.")
    # "O sea, ¿el pago es al contado?" / "¿solo al contado?" (es una PREGUNTA, no que vaya a pagar al contado)
    if re.search(r"\b(o sea|osea|entonces|solo|solamente|nada mas|unicamente)\b[^.]{0,25}\b(al contado|contado|en efectivo)\b", t) \
            and not re.search(r"\b(yo|lo|la|pagaria|pagare|voy a|compraria|tengo)\b", t):
        meta["ya_explicado"] = list(set((meta.get("ya_explicado") or []) + ["financiamiento"]))
        meta["pregunta_fin_pendiente"] = True
        return (f"Puede ser al contado o con crédito hipotecario de cualquier banco{coma} 😊. Nosotros no damos crédito directo, pero con "
                f"banco solo necesitas desde el 10% de inicial (aprox. {_usd(PRECIO_LISTA_USD * 0.10)}) y el resto lo financia el banco; "
                "nuestro asesor hipotecario aliado te puede evaluar sin costo.\n\n¿Cómo lo evaluarías tú: al contado o con crédito?")

    # ¿La evaluación la hacen ustedes o voy al banco?
    if re.search(r"\bevalua\w*|precalifica\w*|calificar\w*|aprobar\w*|aprueben\b", t) and re.search(
            r"\b(ustedes|banco|quien|donde|tengo que|debo|hacen|ir)\b", t):
        meta["etapa"] = "ofrecio_asesor"
        intro = ("Como todavía no tienes tu crédito aprobado, " if sin_aprobacion else "")
        return (
            f"Buena pregunta{coma} 😊. La evaluación crediticia la hace el banco (nosotros no damos crédito directo), "
            f"pero no tienes que hacerlo sola ni ir de banco en banco. {intro}tienes 2 caminos:\n\n"
            "1️⃣ *Con nuestro asesor hipotecario aliado (sin costo):* te contacta, revisa tu perfil y te dice en qué banco te conviene "
            "y cuánto te prestan.\n"
            "2️⃣ *Directo con tu banco:* si ya eres cliente de alguno (BCP, BBVA, Interbank, etc.), pides tu precalificación hipotecaria "
            "con tu sectorista; nosotros te entregamos la Copia Literal y HR/PU de SUNARP de la casa para que avance rápido.\n\n"
            "¿Quieres que el asesor te contacte a este número? Respóndeme *sí* y le paso tus datos."
        )

    # ¿Cuánto de inicial? / inicial adecuada / mínima
    if re.search(r"\binicial\b", t) and re.search(r"\b(cuant\w*|adecuad\w*|recomend\w*|minim\w*|necesit\w*|ideal|porcentaje)\b", t):
        return (
            f"¡Buena pregunta{coma}! 😊 El banco pide como *mínimo el 10%* del valor (aprox. *{_usd(PRECIO_LISTA_USD * 0.10)} USD* "
            f"sobre el precio de lista de {_usd(PRECIO_LISTA_USD)}). Lo que te recomendamos es apuntar a un *20% (aprox. {_usd(PRECIO_LISTA_USD * 0.20)})*: "
            "con más inicial el banco te aprueba más rápido, te da mejor tasa y la cuota mensual baja.\n\n"
            f"Como referencia (tasa aprox. {TASA_REFERENCIAL_TEA:g}% anual a {PLAZO_REFERENCIAL_ANIOS} años; tu banco define la tasa exacta):\n"
            f"• Con 10% de inicial → cuota aprox. *{_usd(cuota_referencial(0.10))} al mes*\n"
            f"• Con 20% de inicial → cuota aprox. *{_usd(cuota_referencial(0.20))} al mes*\n\n"
            "Además, por ser la 1ra unidad aplica el Bono Especial, que baja el precio final (y con eso la inicial y la cuota). "
            "Aparte de la inicial, considera un monto para gastos de notaría, registros y la tasación del banco. "
            "Si gustas, nuestro asesor hipotecario aliado te evalúa sin costo y te dice exacto cuánto te financian.\n\n"
            + cierre_contextual(meta, nombre_corto)
        )

    # ¿Cuánto pagaría al mes? / cuota mensual
    if re.search(r"\b(cuota mensual|al mes|mensualidad|cuanto pagaria|cuanto saldria|cuanto seria la cuota|cuanto es la cuota)\b", t):
        return (
            f"Te doy una referencia{coma} (tasa aprox. {TASA_REFERENCIAL_TEA:g}% anual a {PLAZO_REFERENCIAL_ANIOS} años, sobre el precio de lista de {_usd(PRECIO_LISTA_USD)}):\n"
            f"• Con 10% de inicial ({_usd(PRECIO_LISTA_USD * 0.10)}) → aprox. *{_usd(cuota_referencial(0.10))} al mes*\n"
            f"• Con 20% de inicial ({_usd(PRECIO_LISTA_USD * 0.20)}) → aprox. *{_usd(cuota_referencial(0.20))} al mes*\n\n"
            "La cuota exacta la define tu banco según tu evaluación, y con el Bono Especial de la 1ra Unidad el monto baja. "
            "Si quieres, nuestro asesor hipotecario aliado te hace la simulación sin costo.\n\n"
            + cierre_contextual(meta, nombre_corto)
        )

    # ¿Se puede financiar? / ¿tienen financiamiento? / ¿en cuotas? / ¿crédito directo?
    if re.search(r"\b(financ\w*|cuotas?|facilidades|a plazos|en partes|mensualidades|credito directo|"
                 r"credito hipotecario|hipotecari\w*|aceptan credito|con banco|prestamo)\b", t) and not re.search(r"\binicial\b", t):
        ya = meta.get("ya_explicado") or []
        if "financiamiento" in ya:
            # Ya se le explicó: no repetir el bloque completo, avanzar al siguiente paso
            if meta.get("asesor_solicitado"):
                return (f"Así es{coma}: el financiamiento es con crédito hipotecario de cualquier banco (desde 10% de inicial). "
                        "Nuestro asesor hipotecario ya tiene tus datos para evaluarte sin costo 😊.\n\n" + cierre_contextual(meta, nombre_corto))
            meta["etapa"] = "ofrecio_asesor"
            return (f"Así es{coma}: no damos crédito directo, pero sí puedes financiarla con crédito hipotecario de cualquier banco "
                    f"(desde 10% de inicial, cuota aprox. {_usd(cuota_referencial(0.10))} al mes). Lo más práctico es que nuestro asesor "
                    "hipotecario aliado te evalúe sin costo. ¿Quieres que te contacte a este número? Respóndeme *sí* y le paso tus datos.")
        meta["ya_explicado"] = list(set(ya + ["financiamiento"]))
        if re.search(r"\b(directo|con ustedes|con la constructora|propio)\b", t):
            intro = f"Buena pregunta{coma} 😊. Financiamiento directo con la constructora no manejamos, pero *sí puedes financiarla*: "
        elif meta.get("fin_modalidad") == "contado":
            intro = f"¡Claro{coma}! Aunque me comentaste que lo verías al contado, te cuento cómo funciona con financiamiento: "
        else:
            intro = f"¡Sí, se puede financiar{coma}! 😊 "
        txt = (
            intro + ("" if "directo" in intro else "No manejamos crédito directo con la constructora; ") + "el financiamiento es mediante *crédito hipotecario con cualquier banco* "
            "(BCP, BBVA, Interbank, Scotiabank, BanBif, etc.), y como la casa ya está construida y con título en SUNARP, el trámite es rápido:\n\n"
            f"• *Inicial:* desde el 10% (aprox. {_usd(PRECIO_LISTA_USD * 0.10)} USD); el banco financia hasta el 90% restante.\n"
            f"• *Plazo y cuota:* hasta 25-30 años; como referencia, con 10% de inicial la cuota sale aprox. *{_usd(cuota_referencial(0.10))} al mes* "
            f"(tasa aprox. {TASA_REFERENCIAL_TEA:g}% anual, la exacta la define tu banco).\n"
            "• *Evaluación:* nuestro asesor hipotecario aliado te evalúa sin costo y te dice cuánto te prestan.\n"
            "• *Pasos:* evaluación → separación y entrega de Copia Literal/HR-PU → tasación del banco, firma en notaría, desembolso y llaves.\n\n"
        )
        if meta.get("fin_inicial") is None and meta.get("fin_credito_aprobado") is None and meta.get("fin_modalidad") != "contado" \
                and int(meta.get("veces_pregunta_fin") or 0) == 0:
            meta["pregunta_fin_pendiente"] = True
            meta["etapa"] = meta.get("etapa") if meta.get("etapa") == "ofrecio_horarios" else "pregunto_financiamiento"
            return txt + "Para orientarte mejor: ¿ya tienes algo de inicial ahorrado o algún crédito preaprobado?"
        return txt + cierre_contextual(meta, nombre_corto)

    # ---------------- CONTADO ----------------
    # ¿Cómo es el proceso al contado?
    if es_contado and re.search(proc_rx, t) and not re.search(fin_rx, t):
        return (
            f"¡Claro{coma}! Al contado el proceso es rápido porque la casa ya está construida y con título independizado en SUNARP:\n\n"
            f"1️⃣ *Visita y propuesta:* ves las casas, eliges la unidad y cierras el precio (al contado desde {_usd(PRECIO_CONTADO_USD)}, negociable en la visita).\n"
            "2️⃣ *Revisión legal:* te enviamos la Copia Literal y HR/PU de SUNARP para que tu abogado confirme que está libre de cargas.\n"
            f"3️⃣ *Separación:* firmamos un contrato de arras con {SEPARACION_TEXTO}.\n"
            "4️⃣ *Escritura y llaves:* firmamos la escritura pública en notaría, realizas el pago y te entregamos las llaves de inmediato; "
            "la notaría inscribe la compra a tu nombre en SUNARP.\n\n"
            + cierre_contextual(meta, nombre_corto)
        )

    # ¿Hay descuento por pago al contado? / precio final
    if re.search(r"\b(descuento|rebaja|rebajan|precio final|ultimo precio|negociable|mejor precio|cuanto menos|me lo dejan)\b", t) and es_contado:
        return (
            f"¡Sí{coma}! 😊 {linea_contado()} Trato directo, sin comisión inmobiliaria.\n\n"
            "Además, por ser la 1ra unidad puedes elegir recibirla con los reposteros de cocina instalados en el diseño que prefieras "
            "(Gris Grafito con LED o Madera Rovere). Recuerda que una vez vendida la 1ra casa, la 2da queda a precio fijo de lista.\n\n"
            + cierre_contextual(meta, nombre_corto)
        )

    # Separación / arras
    if re.search(r"\b(separa\w*|arras|apartar|reservar la casa|reservarla|cuanto para separar)\b", t):
        return (
            f"Para asegurar la unidad{coma}, se firma un contrato de arras con {SEPARACION_TEXTO}. "
            "Así la casa queda bloqueada a tu nombre con el Bono de la 1ra Unidad mientras se prepara la escritura.\n\n"
            + cierre_contextual(meta, nombre_corto)
        )

    # Papeles / documentos / cargas
    if re.search(r"\b(papeles|documentos|documentacion|en regla|saneado\w*|copia literal|partida|cargas|gravamen\w*|hipotecad\w*|titulo)\b", t) and not re.search(proc_rx, t):
        return (
            f"Todo está en regla{coma} ✅: cada casa tiene *título independizado en SUNARP, libre de cargas y gravámenes*, lista para transferencia notarial. "
            "Si deseas, te enviamos la Copia Literal y la HR/PU para que tu abogado (o tu banco) las revise antes de separar.\n\n"
            + cierre_contextual(meta, nombre_corto)
        )

    # Gastos notariales / impuestos
    if re.search(r"\b(gastos?|notari\w*|impuesto\w*|alcabala|quien paga)\b", t) and re.search(r"\b(cuanto|quien|cuales|incluye|aparte|adicional\w*|paga\w*|hay)\b", t):
        return f"{GASTOS_TEXTO} 😊. El precio de la casa no incluye comisión inmobiliaria porque el trato es directo con la constructora.\n\n" + cierre_contextual(meta, nombre_corto)

    # Comprar desde el extranjero
    if re.search(r"\b(extranjero|exterior|fuera del pais|vivo en (eeuu|usa|estados unidos|espana|italia|chile|argentina|japon)|desde (eeuu|usa|espana|italia|chile))\b", t):
        return (
            f"¡Claro que sí{coma}! Muchos de nuestros compradores viven fuera 😊. Puedes comprar desde el exterior otorgando un poder por escritura pública "
            "(en el consulado peruano) a un familiar de confianza, o viajar solo para la firma. Mientras tanto, un familiar puede visitar la casa por ti. "
            "Te enviamos la Copia Literal para que tu abogado revise todo a distancia.\n\n"
            + cierre_contextual(meta, nombre_corto)
        )

    # ¿Cómo es el procedimiento con banco? (Caso 16)
    if (re.search(fin_rx, t) and re.search(proc_rx, t)) or re.search(r"\bcomo (seria|es|funciona) con (el )?banco\b", t):
        return (
            f"¡Claro{coma}! El proceso es súper directo porque la casa ya está construida y tiene título independizado en SUNARP (sin cargas ni hipotecas):\n\n"
            "1️⃣ *Inicial y banco:* Trabajamos con cualquier banco (BCP, BBVA, Interbank, Scotiabank, BanBif, etc.). "
            "El banco te pide desde el 10% de cuota inicial y financia hasta el 90% restante.\n"
            "2️⃣ *Separación y documentos:* Acordamos el precio final (con el bono de 1ra unidad), separas la unidad y te entregamos "
            "la Copia Literal y HR/PU de SUNARP para tu sectorista.\n"
            "3️⃣ *Tasación y desembolso:* El perito del banco tasa la casa, firmas la escritura en notaría, el banco nos desembolsa "
            "y te entregamos las llaves de inmediato.\n\n"
            "Si gustas, te contactamos sin costo con nuestro asesor hipotecario aliado para que te evalúe. "
            + cierre_contextual(meta, nombre_corto)
        )
    return None
