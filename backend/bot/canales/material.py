"""Envío de fichas, renders y fotos solicitados en una respuesta."""
from bot.canales.alertas import alertar_asesor
from bot.canales.whatsapp import send_wa_media
from bot.config import URL_FICHA_TECNICA, URL_FOTOS_CASA, URL_RENDER_GRIS, URL_RENDER_MADERA
from bot.conversacion.recursos import renders_cocina_catalogo
from bot.estado import MEDIA_ERROR


_TXT_COCINA = {
    "gris": "Opción 1: Cocina Línea Moderna en Gris Grafito con iluminación LED cálida integrada (render de referencia del diseño a instalar).",
    "madera": "Opción 2: Cocina Línea Cálida en Madera Rovere y acabado Taupe (render de referencia del diseño a instalar).",
}


def _enviar_render_cocina(to_phone, estilo):
    """Render de cocina: primero el archivo fijo; si WhatsApp lo rechaza, uno equivalente del bucket. (nombre, ok, url)"""
    url = URL_RENDER_GRIS if estilo == "gris" else URL_RENDER_MADERA
    if send_wa_media(to_phone, url, "image", _TXT_COCINA[estilo]):
        return url.split("?")[0].rsplit("/", 1)[-1], True, url
    for alt in renders_cocina_catalogo(estilo):
        if alt != url and send_wa_media(to_phone, alt, "image", _TXT_COCINA[estilo]):
            print(f"Render de cocina {estilo}: falló {url}, se envió {alt}")
            return alt.rsplit("/", 1)[-1], True, alt
    return url.split("?")[0].rsplit("/", 1)[-1], False, url


def send_requested_wa_media(to_phone, parsed):
    envios = []
    fotos_auto = parsed.get("recursos") or []  # [(url, tipo, leyenda)] elegidos por conversacion/recursos.py
    # Orden: planos -> render de cocina -> fotos (la bienvenida dice "te comparto los planos y el render de ese diseño")
    docs = [x for x in fotos_auto if x[1] == "document"]
    envios.extend(docs)
    if parsed.get("enviar_ficha_tecnica"):
        envios.append((URL_FICHA_TECNICA, "document",
                       "Ficha técnica y planos de los 3 niveles (200 m² construidos sobre 80 m² de terreno). "
                       "Las 2 casas tienen el 1er y 2do piso con acabados; el 3er piso se entrega en casco (sin tarrajear)."))
    resultado = [(u.split("?")[0].rsplit("/", 1)[-1], send_wa_media(to_phone, u, tipo, cap), u) for u, tipo, cap in envios]
    if parsed.get("enviar_renders_cocina"):
        pref = (parsed.get("estilo_render_preferido") or "ambos").lower()
        for estilo in ("gris", "madera"):
            if pref in [estilo, "ambos"]:
                resultado.append(_enviar_render_cocina(to_phone, estilo))
    resto = [x for x in fotos_auto if x[1] != "document"]
    if parsed.get("enviar_fotos_casa"):
        for i, u in enumerate(URL_FOTOS_CASA[:6]):
            resto.append((u, "image", "Casa de estreno en Urb. Santa Teresa, Lambayeque 🏡" if i == 0 else ""))
    resultado += [(u.split("?")[0].rsplit("/", 1)[-1], send_wa_media(to_phone, u, tipo, cap), u) for u, tipo, cap in resto]
    fallidos = [n for n, ok, _ in resultado if not ok]
    if fallidos:
        print(f"No se enviaron {len(fallidos)} de {len(resultado)} archivos a {to_phone}: {fallidos}")
    if not fallidos and not parsed.get("_alerta_fotos"):
        return  # todo salió bien: no molestar al asesor
    # Alerta al asesor cada vez que hay que enviar imágenes (para que verifique o adjunte fotos a mano). Al cliente no se le dice nada.
    try:
        estado = ", ".join(f"{n} {'✅' if ok else '❌ (' + MEDIA_ERROR.get(u, 'sin detalle') + ')'}" for n, ok, u in resultado) or "ninguno"
        pide = parsed.get("_msg_cliente", "")
        aviso = (("🚨 URGENTE – NO SE ENVIARON LAS IMÁGENES\n" if fallidos else "")
                 + f"📸 SAGUE: {parsed.get('_nombre') or 'Un cliente'} (+{to_phone}) "
                 + ("pidió FOTOS de la casa" if parsed.get("_alerta_fotos") else "debía recibir imágenes")
                 + (f" (\"{pide[:120]}\")" if pide else "") + f".\nEnvío automático: {estado}."
                 + ("\n👉 Adjúntale por WhatsApp fotos reales de la casa." if parsed.get("_alerta_fotos") else "")
                 + ("\n👉 Envíaselas tú manualmente lo antes posible." if fallidos else ""))
        alertar_asesor(aviso)
    except Exception:
        pass
