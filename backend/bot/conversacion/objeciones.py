"""Objeciones de precio ('está muy caro', 'se me pasa del presupuesto') y descuento cuando compra con crédito."""
import re

from bot.config import PRECIO_LISTA_USD
from bot.conversacion.cierres import cierre_contextual
from bot.conversacion.precio import es_pregunta_moneda, gancho_m2, precio_m2, responder_moneda
from bot.conversacion.presupuesto import leer_monto, linea_contado, respuesta_monto
from bot.nlp.financiamiento import cuota_referencial
from bot.nlp.patrones import NO_OBJECION_RE, OBJECION_PRECIO_RE
from bot.utils.texto import _usd, limpiar_texto


def es_objecion_precio(t):
    return bool(OBJECION_PRECIO_RE.search(t)) and not NO_OBJECION_RE.search(t)


def _primera_objecion(nombre_corto, meta):
    coma = f", {nombre_corto}" if nombre_corto else ""
    lineas = [
        f"Te entiendo{coma}, es una inversión importante y está muy bien comparar 🙌. Déjame mostrártelo en números:",
        "",
        "• " + gancho_m2(meta),
        "• Por casi lo mismo que un depa pequeño te llevas una *casa independiente de 3 pisos* ya construida y con título "
        "en SUNARP: 2 pisos listos con acabados y el 3ro en casco para terminarlo a tu gusto.",
        "• Y es negociable: " + linea_contado(False),
    ]
    if meta.get("fin_modalidad") == "credito" or meta.get("fin_inicial") is not None:
        lineas.append(f"• Con crédito hipotecario, desde 10% de inicial la cuota referencial es aprox. *{_usd(cuota_referencial(0.10))} al mes*.")
    lineas += ["", "¿Qué rango de inversión tienes en mente? Dímelo con confianza y te digo con total transparencia si podemos llegar 😊"]
    meta["etapa"] = "pregunto_presupuesto"
    meta["_momento_fotos"] = "objecion"
    meta["_alerta_asesor"] = "💬 Objeción de precio (1ra vez): el bot le pidió su rango de inversión"
    return "\n".join(lineas)


def _segunda_objecion(nombre_corto, meta):
    coma = f", {nombre_corto}" if nombre_corto else ""
    meta["_alerta_asesor"] = "🔥 Objeción de precio por 2da vez: buen momento para llamarle y negociar en persona"
    return (f"Lo entiendo{coma} 🙏. Para no darte vueltas por chat: {linea_contado(False)} "
            "Trato directo, sin comisión inmobiliaria. ¿Te animas a verla sin compromiso? Si en persona no te convence, no pasa nada 😊\n\n"
            + cierre_contextual(meta, nombre_corto))


def _tercera_objecion(nombre_corto, meta):
    coma = f", {nombre_corto}" if nombre_corto else ""
    meta["_alerta_asesor"] = "🚨 Objeción de precio por 3ra vez: escríbele o llámale tú (el bot ya no insistirá)"
    meta["etapa"] = ""
    return (f"Te entiendo perfectamente{coma}, y gracias por la sinceridad 🙏. Le voy a pedir al propietario que te escriba "
            "directamente para ver si hay una forma de que la casa te encaje. Sin compromiso, ¿te parece?")


def responder_objecion_precio(t, nombre_corto, meta):
    meta["objecion_precio_n"] = n = int(meta.get("objecion_precio_n") or 0) + 1
    meta["ya_explicado"] = list(set((meta.get("ya_explicado") or []) + ["objecion_precio"]))
    monto, moneda = leer_monto(t)
    if monto:
        return respuesta_monto(monto, moneda, nombre_corto, meta)["reply_text"]
    if n >= 3:
        return _tercera_objecion(nombre_corto, meta)
    if n == 2:
        return _segunda_objecion(nombre_corto, meta)
    return _primera_objecion(nombre_corto, meta)


def responder_descuento_credito(t, nombre_corto, meta):
    """'¿Hay descuento?' de alguien que NO compra al contado (al contado lo responde la FAQ)."""
    coma = f", {nombre_corto}" if nombre_corto else ""
    return (f"¡Sí{coma}! 😊 Solo para la *1ra unidad* que se separe aplica el *Bono Especial de Lanzamiento*, también si compras con "
            "crédito hipotecario. Puedes elegir entre:\n"
            "🅰️ Recibir la casa con los reposteros de cocina instalados en el diseño que prefieras (Gris Grafito con LED o Madera Rovere), o\n"
            "🅱️ Un descuento directo sobre el precio de lista, sin los reposteros.\n\n"
            f"Y ojo que ya de por sí el precio de lista ({_usd(PRECIO_LISTA_USD)}) sale a solo *{_usd(precio_m2())} por m²* construido."
            + "\n\nEl monto final se cierra en la visita con los propietarios (trato directo, sin comisión).\n\n"
            + cierre_contextual(meta, nombre_corto))


def responder_precio(user_text, nombre_corto, meta):
    """Despacha moneda / objeción de precio / descuento con crédito. None si el mensaje no es de esto."""
    t = limpiar_texto(user_text)
    if es_pregunta_moneda(t):
        return responder_moneda(t, nombre_corto, meta)
    if es_objecion_precio(t):
        return responder_objecion_precio(t, nombre_corto, meta)
    es_contado = bool(re.search(r"\b(contado|efectivo|cash)\b", t)) or meta.get("fin_modalidad") == "contado"
    if not es_contado and re.search(r"\b(descuento|rebaja|rebajan|precio final|ultimo precio|negociable|mejor precio|me lo dejan)\b", t):
        return responder_descuento_credito(t, nombre_corto, meta)
    return None
