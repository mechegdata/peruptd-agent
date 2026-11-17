"""Precio al contado, presupuesto del cliente y "¿solo tienen esas casas?": respuestas honestas (aprendido de chats reales).

- Al contado: US$130,000 (PRECIO_CONTADO_USD), negociable en la visita con el propietario.
- Si el presupuesto no alcanza, se dice con transparencia y se ofrece el camino real: usarlo como inicial + crédito hipotecario.
- Si el monto no dice moneda ("100.000"), se pregunta si son soles o dólares (en Perú puede ser cualquiera).
"""
import re

from bot.config import PLAZO_REFERENCIAL_ANIOS, PRECIO_CONTADO_USD, PRECIO_LISTA_USD, PROPIETARIO_TXT, TASA_REFERENCIAL_TEA
from bot.conversacion.base import _resp
from bot.conversacion.cierres import cierre_contextual
from bot.conversacion.precio import _soles
from bot.integraciones.tipo_cambio import tipo_cambio_referencial
from bot.nlp.numeros import numero_en_palabras
from bot.utils.texto import _usd, limpiar_texto

_SOLES_RX = r"\b(soles|sol|s/|s/\.|lucas|nuevos soles)\b|s/"
_DOLARES_RX = r"\$|\b(dolares|dolar|usd|us\$|verdes)\b"
_PRESUPUESTO_RX = (r"\b(tengo|tenemos|cuento con|contamos con|dispongo|disponemos|mi presupuesto|nuestro presupuesto|presupuesto de|"
                   r"me alcanza|nos alcanza|llego a|llegamos a|puedo adquirir|podria adquirir|puedo comprar|podria comprar|puedo|"
                   r"con \d+|hasta \d+|maximo|tope)\b")
OTRAS_OPCIONES_RX = (r"\b(m?as economic\w*|casas? economicas|economicas|m?as barat\w*|otras? casas?|otras? opcion\w*|otros? (proyectos?|inmuebles?|modelos?)|"
                     r"de un (solo )?piso|un solo piso|de 1 piso|un piso|casas? de (1er|primer|1|uno) piso|mas pequen\w*|mas chic\w*|"
                     r"(venden|tienen|hay|ofrecen|busco|buscaba|quiero|quisiera)\b[^.?]{0,15}\b(departamentos?|depas?|terrenos?|lotes?)|"
                     r"solo (tienen|hay|venden) (esas|estas|esa|esta)|no venden|tienen otr\w*|hay otr\w*)\b")
# 'Cuatrocientos mil ochocientos' / '120 mil' a secas: un monto suelto (en respuesta al precio) también es un presupuesto
_SOLO_MONTO_RX = r"^(?:(?:mas o menos|como|unos|unas|tengo|hasta|maximo|solo|y|de|s/|\$|soles|dolares|mil|k|[\d.,\s]+|[a-z]*cient[oa]s|cien|ciento|" \
                 r"un|uno|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|veinte|veinti\w+|treinta|cuarenta|cincuenta|sesenta|setenta|ochenta|noventa|quinient[oa]s)\s*)+$"


def tc():
    return tipo_cambio_referencial() or 3.45


def linea_contado(mayuscula=True):
    """'Al contado el precio es US$130,000 (...) y lo puedes negociar en la visita con el propietario.'"""
    return (f"{'A' if mayuscula else 'a'}l contado el precio es *{_usd(PRECIO_CONTADO_USD)}* (aprox. {_soles(PRECIO_CONTADO_USD * tc())}) y lo puedes "
            f"negociar directamente en la visita con {PROPIETARIO_TXT}.")


def leer_monto(t):
    """'100.000', '100 mil', '120k', 'S/ 400,000', '$110,000', 'cuatrocientos mil' -> (monto, 'usd' | 'pen' | None)."""
    m = re.search(r"(?<![\d:])(\d{1,3})(?:[.,]?\s?(\d{3}))?(?:[.,]?\s?(\d{3}))?\s*(mil|k|lucas)?(?![\d:])", t.replace("$", " $ "))
    if not m or not (m.group(2) or m.group(4)):
        monto = numero_en_palabras(t)
        if not monto:
            return None, None
    elif m.group(3):
        monto = int(m.group(1) + m.group(2) + m.group(3))
    elif m.group(2):
        monto = int(m.group(1) + m.group(2))
    else:
        monto = int(m.group(1)) * 1000
    if not 5000 <= monto <= 5000000:
        return None, None
    moneda = "pen" if re.search(_SOLES_RX, t) else ("usd" if re.search(_DOLARES_RX, t) else None)
    if moneda is None and monto >= 200000:
        moneda = "pen"  # más de 200 mil "a secas" en Perú son soles (en dólares superaría el precio)
    return monto, moneda


def es_presupuesto(t, meta=None):
    monto, _ = leer_monto(t)
    if not monto or re.search(r"\b(inicial|cuota|mensual|al mes|sueldo|gano|m2|metros|area)\b", t):
        return False
    ya_hablo_precio = bool({"precio", "moneda", "contado", "otras_opciones", "objecion_precio"} & set((meta or {}).get("ya_explicado") or []))
    return bool(re.search(_PRESUPUESTO_RX, t)) or (ya_hablo_precio and bool(re.fullmatch(_SOLO_MONTO_RX, t.strip())))


def _cuota(prestamo):
    i = (1 + TASA_REFERENCIAL_TEA / 100) ** (1 / 12) - 1
    n = PLAZO_REFERENCIAL_ANIOS * 12
    return prestamo * i / (1 - (1 + i) ** -n)


def respuesta_tope_usd(usd, nombre_corto, meta, texto_monto=None):
    """Respuesta honesta según cuánto puede invertir (en US$)."""
    coma = f", {nombre_corto}" if nombre_corto else ""
    meta["presupuesto_tope"] = int(usd)
    meta["etapa"] = ""
    monto_txt = texto_monto or _usd(usd)
    if usd >= PRECIO_CONTADO_USD:
        txt = (f"¡Perfecto{coma}! 😊 Con {monto_txt} sí llegamos: {linea_contado(False)} Y si separas la 1ra unidad, además aplicas "
               "al Bono Especial de Lanzamiento.")
    elif usd >= PRECIO_CONTADO_USD * 0.92:
        txt = (f"¡Gracias por la confianza{coma}! 😊 Con {monto_txt} estamos cerca: {linea_contado(False)} "
               "Vale la pena que lo conversen en persona.")
    elif usd >= PRECIO_CONTADO_USD * 0.80:
        txt = (f"Gracias por contarme{coma} 😊. Con {monto_txt} estamos algo por debajo: {linea_contado(False)} "
               f"La diferencia (aprox. {_usd(PRECIO_CONTADO_USD - usd)}) se podría completar con un crédito hipotecario pequeño, "
               "y lo mejor es que lo conversen en persona.")
    else:
        prestamo = PRECIO_LISTA_USD - usd
        if usd >= PRECIO_LISTA_USD * 0.10:
            meta["etapa"] = "ofrecio_asesor"
            txt = (f"Te soy sincero{coma}: con {monto_txt} no llegaríamos al precio de la casa, que al contado está en "
                   f"*{_usd(PRECIO_CONTADO_USD)}* 😊\n\nPero sí hay un camino: usar ese monto como *cuota inicial* y financiar el resto con "
                   f"crédito hipotecario. Con {monto_txt} de inicial, el banco te prestaría aprox. *{_usd(prestamo)}* y la cuota "
                   f"quedaría alrededor de *{_usd(_cuota(prestamo))} al mes* (referencial a {PLAZO_REFERENCIAL_ANIOS} años; tu banco define "
                   "la tasa exacta).\n\n¿Quieres que nuestro asesor hipotecario aliado te evalúe *sin costo* y te diga cuánto te "
                   "financian? Respóndeme *sí* y le paso tus datos.")
            return txt
        meta["etapa"] = "ofrecio_asesor"
        return (f"Te soy sincero{coma}: con {monto_txt} todavía no llegaríamos, ni siquiera para la cuota inicial con banco, que pide "
                f"desde el 10% (aprox. {_usd(PRECIO_LISTA_USD * 0.10)}) 😊. Si quieres, nuestro asesor hipotecario aliado te evalúa "
                "*sin costo* y te dice qué opciones tienes. ¿Le paso tus datos? Respóndeme *sí*.")
    return txt + "\n\n" + cierre_contextual(meta, nombre_corto)


def respuesta_monto(monto, moneda, nombre_corto, meta):
    """Convierte y responde; si no se sabe la moneda, la pregunta."""
    coma = f", {nombre_corto}" if nombre_corto else ""
    if moneda is None:
        meta["monto_pendiente"] = monto
        meta["etapa"] = "pregunto_moneda_monto"
        r = _resp(f"Para responderte exacto{coma}: ¿esos {monto:,} son en *soles* o en *dólares*? 😊")
        r["_sin_control_repeticion"] = True
        return r
    meta.pop("monto_pendiente", None)
    if moneda == "pen":
        usd = round(monto / tc(), -2)
        texto = f"{_soles(monto)} (aprox. {_usd(usd)})"
    else:
        usd, texto = monto, _usd(monto)
    meta["_alerta_asesor"] = f"💵 Indicó un presupuesto de {texto}"
    r = _resp(respuesta_tope_usd(usd, nombre_corto, meta, texto))
    r["_sin_control_repeticion"] = True
    return r


MUY_GRANDE_RX = r"\b(muy|demasiado|bien|bastante|algo) (grandes?|amplias?|espaciosas?)\b|\b(es|son) (muy )?grandes?\b|\bmucho espacio\b"


def responder_muy_grande(nombre_corto, meta):
    """'Es que muy grande': objeción de tamaño. Se entiende, se aclara cómo se vive la casa y se pregunta qué busca."""
    coma = f", {nombre_corto}" if nombre_corto else ""
    meta["ya_explicado"] = list(set((meta.get("ya_explicado") or []) + ["otras_opciones"]))
    meta["etapa"] = "pregunto_presupuesto"
    return (f"Te entiendo{coma} 😊, son casas amplias: 200 m² en 3 pisos. Por ahora solo tenemos estas 2, así que te cuento cómo se "
            "viven: el 1er piso es la zona social (cochera, sala-comedor, cocina y jardín), el 2do son los 3 dormitorios y el 3ro es "
            "terraza, terma y lavandería, y se entrega en casco (sin tarrajear) para que lo termines a tu gusto; el día a día se hace en los 2 primeros pisos.\n\n"
            "¿Qué tamaño o presupuesto tienes en mente? Dímelo con confianza y te digo con transparencia si te puede encajar.")


def responder_otras_opciones(t, nombre_corto, meta):
    """'¿Hay más económicas?', '¿De un solo piso no venden?', '¿solo tienen esas?'."""
    coma = f", {nombre_corto}" if nombre_corto else ""
    ya = meta.get("ya_explicado") or []
    meta["ya_explicado"] = list(set(ya + ["otras_opciones"]))
    if "otras_opciones" in ya:
        txt = f"Así es{coma}, por ahora solo tenemos estas 2 casas 😊. {linea_contado()}"
    else:
        txt = (f"Te cuento{coma}: por el momento solo tenemos a la venta estas *2 casas de 3 pisos* en Urb. Santa Teresa "
               "(no tenemos casas de un piso, departamentos ni terrenos) 😊.\n\n"
               f"Lo bueno es que el precio es negociable: {linea_contado(False)} Y con crédito hipotecario se puede empezar desde el 10% de inicial.")
    meta["etapa"] = "pregunto_presupuesto"
    return txt + "\n\n¿Qué presupuesto manejas? Dímelo con confianza y te digo con total transparencia si te puede encajar."


def responder_precio_contado(t, nombre_corto, meta):
    """'¿Cuánto es el precio total al contado?', '¿precio final?', '¿cuánto en soles al contado?'."""
    coma = f", {nombre_corto}" if nombre_corto else ""
    meta["ya_explicado"] = list(set((meta.get("ya_explicado") or []) + ["contado"]))
    return (f"¡Claro{coma}! 😊 El valor de lista es {_usd(PRECIO_LISTA_USD)}, pero {linea_contado(False)}\n\n"
            "Y como es la 1ra unidad, también puedes elegir recibirla con los reposteros de cocina instalados en el diseño que prefieras.\n\n"
            + cierre_contextual(meta, nombre_corto))


def responder_medio_millon(t, nombre_corto, meta):
    """'Casi es precio el de medio millón' (lo está pensando en soles)."""
    coma = f", {nombre_corto}" if nombre_corto else ""
    return (f"Así es{coma}, en soles el valor de lista equivale a unos {_soles(PRECIO_LISTA_USD * tc())}. Pero "
            f"{linea_contado(False)}\n\n¿Qué presupuesto manejas? Así te digo con transparencia si te puede encajar 😊")


def responder_presupuesto(user_text, nombre_corto, meta):
    """Despacha lo de este módulo. None si no aplica."""
    t = limpiar_texto(user_text)
    if meta.get("etapa") == "pregunto_moneda_monto" and meta.get("monto_pendiente"):
        moneda = "pen" if re.search(_SOLES_RX, t) else ("usd" if re.search(_DOLARES_RX, t) else None)
        if moneda:
            return respuesta_monto(int(meta["monto_pendiente"]), moneda, nombre_corto, meta)
    if es_presupuesto(t, meta) or (meta.get("etapa") == "pregunto_presupuesto" and leer_monto(t)[0]):
        monto, moneda = leer_monto(t)
        return respuesta_monto(monto, moneda, nombre_corto, meta)
    if re.search(MUY_GRANDE_RX, t):
        return _resp(responder_muy_grande(nombre_corto, meta))
    if re.search(OTRAS_OPCIONES_RX, t):
        return _resp(responder_otras_opciones(t, nombre_corto, meta))
    if re.search(r"\b(medio millon|medio palo|500 mil|quinientos mil|casi un millon)\b", t):
        return _resp(responder_medio_millon(t, nombre_corto, meta))
    if re.search(r"\b(contado|precio final|ultimo precio|precio total|cuanto (seria|sale|es) (al|en) contado)\b", t) and \
            re.search(r"\b(cuanto|precio|valor|costo|sale|seria|final)\b", t):
        return _resp(responder_precio_contado(t, nombre_corto, meta))
    return None
