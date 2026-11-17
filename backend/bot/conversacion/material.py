"""Respuestas cuando el cliente pide planos, renders, fotos o video."""
import re

from bot.config import URL_FOTOS_CASA, URL_VIDEO_RECORRIDO
from bot.conversacion.base import _resp
from bot.conversacion.cierres import cierre_contextual
from bot.conversacion.recursos import (UNIDAD_TXT, elegir_galeria, fichas_por_casa, hay_fotos, hay_renders, hay_videos, resumen_galeria,
                                       unidad_del_texto)
from bot.nlp.patrones import AFIRMA_RE, NIEGA_RE
from bot.utils.texto import limpiar_texto


def _estilo_de_texto(t):
    t = limpiar_texto(t)
    if re.search(r"\b(madera|rovere|taupe|calida|beige)\b", t):
        return "madera"
    if re.search(r"\b(gris|grafito|led|moderna)\b", t):
        return "gris"
    return None


ESTILOS_TXT = {"madera": "Línea Cálida en Madera Rovere y acabado Taupe", "gris": "Línea Moderna en Gris Grafito con iluminación LED cálida"}


def _respuesta_muebles(coma, meta, nombre_corto, cerrar):
    """'¿Viene amoblada?' / '¿cómo se ve con muebles?'."""
    r = _resp(f"La casa se entrega sin muebles{coma}, lista para que la decores a tu gusto (y en la 1ra unidad, con los reposteros de "
              "cocina instalados por el Bono Especial)."
              + (" Para que te imagines, te comparto cómo se vería amoblada 👇" if hay_renders() else "")
              + ("\n\n" + cierre_contextual(meta, nombre_corto) if cerrar else ""))
    r["_sin_control_repeticion"] = True
    r["_momento_fotos"] = "amoblada"
    return r


def _partes_galeria(r, partes, coma, meta):
    """'Mándame fotos': mezcla de las 2 casas, fotos reales y renders; luego ofrece el video (o los planos), sin listar horarios."""
    unidad = r.get("_unidad")
    previas = set(meta.get("fotos_enviadas") or [])
    ya_vio = bool(previas)
    fotos, quedan = elegir_galeria(meta, unidad)
    repetidas = bool(fotos) and all(u in previas for u, _, _ in fotos)
    meta["ultimo_material"] = "fotos"
    r["recursos"] = fotos
    info = resumen_galeria(unidad)
    if unidad:
        de_que = f" de la {UNIDAD_TXT[unidad]}"
    elif len(info["casas"]) == 2:
        de_que = " de las 2 casas (una al lado de la otra)"
    else:
        de_que = ""
    texto = f"¡Claro que sí{coma}! 📸 Te comparto fotos{de_que}."
    if repetidas:
        texto = f"¡Claro{coma}! 📸 Estas son las fotos{de_que}."
    elif ya_vio:
        texto = f"¡Claro{coma}! 📸 Aquí van más fotos{de_que if unidad else ''}."
    elif info["renders"]:
        texto += " Las que dicen *render* tienen muebles de referencia para que te imagines los ambientes (la casa se entrega sin muebles)."
    partes.append(texto)
    if quedan:
        partes.append(f"Tengo {quedan} más; si quieres, te las sigo enviando 😊")
    elif ya_vio and not repetidas:
        partes.append("Con estas ya viste todas las que tengo 😊")
    if info["videos"] and not meta.get("videos_enviados"):
        meta["etapa"] = "ofrecio_video"
        partes.append("¿Te gustaría ver también el recorrido en video" + ("" if unidad else " de cada casa") + "? 🎥")
        r["_sin_cierre"] = True
    elif not meta.get("material_enviado"):
        meta["etapa"] = "ofrecio_material"
        partes.append("¿Te paso también los planos de los 3 pisos? 📄")
        r["_sin_cierre"] = True


def responder_oferta_video(user_text, meta, nombre_corto):
    """Respuesta a '¿Te gustaría ver el recorrido en video?': 'sí' / 'ok' / '👍' -> videos; 'no' -> sigue la conversación."""
    if meta.get("etapa") != "ofrecio_video":
        return None
    t = limpiar_texto(user_text)
    coma = f", {nombre_corto}" if nombre_corto else ""
    solo_emoji = bool(user_text.strip()) and not re.search(r"[0-9A-Za-zÁÉÍÓÚáéíóúÑñ]", user_text)
    if AFIRMA_RE.match(t) or solo_emoji or re.search(r"\b(si|claro|dale|porfa|por favor|me gustaria|quiero|mandal\w*|envial\w*)\b", t):
        meta["etapa"] = ""
        meta["ultimo_material"] = "videos"
        if meta.get("vive_lejos"):  # vive en otra ciudad: no se le lanzan horarios, se le espera
            meta["etapa"] = "espera_cliente"
            cierre = f"Cuando sepas qué día vienes desde {meta['vive_lejos']}, me escribes y te reservo la visita 😊"
        else:
            cierre = cierre_contextual(meta, nombre_corto)
        r = _resp(f"¡Aquí van{coma}! 🎥 Así las ves con calma, o con tu familia.\n\n" + cierre)
        r["_pide_video"] = True
        r["_sin_control_repeticion"] = True
        return r
    if NIEGA_RE.match(t) and len(t) <= 30:
        meta["etapa"] = ""
        r = _resp(f"¡Perfecto{coma}! 😊 " + cierre_contextual(meta, nombre_corto))
        r["_sin_control_repeticion"] = True
        return r
    meta["etapa"] = ""
    return None  # cambió de tema: lo atienden los demás motores


def _partes_video(r, partes, coma, tambien_fotos):
    """Videos por casa desde el catálogo (p. ej. 'envíame las dos casas en video para mostrarle a mi familia')."""
    r["_pide_video"] = True
    if tambien_fotos:
        r["_momento_fotos"] = "pide_fotos"
    if r.get("_unidad"):
        partes.append(f"¡Claro que sí{coma}, con todo gusto! 🎥 Te comparto el video de la {UNIDAD_TXT[r['_unidad']]} para que lo veas con calma.")
    else:
        partes.append(f"¡Claro que sí{coma}, con todo gusto! 🎥 Son 2 casas, una al lado de la otra, y cada una tiene sus propios "
                      "detalles, así que te comparto el video de cada una por separado para que las veas con tu familia.")
    partes.append("En persona se aprecian mucho mejor los 200 m², la iluminación y la vista a la loza deportiva 😊")


def responder_material(user_text, nombre_corto, meta=None, ultimo_bot="", cerrar=True):
    """Pedidos de fotos, planos, renders, video, la opción '1' del menú, o la elección de un estilo de cocina."""
    t = limpiar_texto(user_text)
    meta = meta if meta is not None else {}
    coma = f", {nombre_corto}" if nombre_corto else ""
    menu_material = bool(re.search(r"1️⃣[^\n]*(plano|ficha|cocina|dise)", ultimo_bot or "", re.I))
    lista_horarios = bool(re.search(r"1️⃣[^\n]*(a\. m\.|p\. m\.)", ultimo_bot or ""))
    es_opcion_1 = t in ["1", "1️⃣", "uno", "opcion 1", "la 1", "el 1", "la uno", "la primera"] and (menu_material or not lista_horarios)

    # Eligió un estilo de cocina ("me gusta la gris", "prefiero la de madera")
    if re.search(r"\b(me gusta\w*|prefiero|elijo|escojo|me quedo con|me encanta\w*|mejor la|la de)\b", t) and _estilo_de_texto(t) \
            and not re.search(r"\b(envi\w*|manda\w*|pasa\w*|foto\w*)\b", t):
        estilo = _estilo_de_texto(t)
        meta["estilo_cocina"] = ESTILOS_TXT[estilo]
        r = _resp(f"¡Excelente elección{coma}! 😍 La {ESTILOS_TXT[estilo]} queda espectacular con el porcelanato de la cocina. "
                  "Si separas la 1ra unidad, te la entregamos instalada en ese diseño como parte del Bono Especial de Lanzamiento."
                  + ("\n\n" + cierre_contextual(meta, nombre_corto) if cerrar else ""))
        r["_sin_control_repeticion"] = True
        return r

    if re.search(r"\b(amoblad\w*|amueblad\w*|con muebles|(viene|vienen|entregan|incluye\w*) (con )?(los )?muebles)\b", t):
        return _respuesta_muebles(coma, meta, nombre_corto, cerrar)

    pide_fotos = re.search(r"\b(fotos?|fotitos?|fotografias?|imagen\w*|como es por dentro|por dentro|interiores?|de referencia)\b", t)
    pide_planos = es_opcion_1 or re.search(r"\b(planos?|ficha\w*|pdf|brochure|catalogo)\b", t)
    pide_cocina = es_opcion_1 or re.search(r"\b(render\w*|cocinas?|reposteros?|disenos? de (la )?cocina|estilos? de (la )?cocina)\b", t)
    pide_video = re.search(r"\b(video\w*|recorrido virtual|tour)\b", t)
    if not (pide_fotos or pide_planos or pide_cocina or pide_video):
        # "¿y de la casa 2?" justo después de mandarle fotos o videos = lo mismo, pero de esa casa
        if unidad_del_texto(user_text) and meta.get("ultimo_material") in ("fotos", "videos") and len(t) <= 40:
            pide_fotos = meta["ultimo_material"] == "fotos"
            pide_video = meta["ultimo_material"] == "videos"
        else:
            return None
    r = _resp("")
    r["_sin_control_repeticion"] = True
    r["_unidad"] = unidad_del_texto(user_text)
    partes = []
    if pide_video and hay_videos():
        meta["ultimo_material"] = "videos"
        _partes_video(r, partes, coma, bool(pide_fotos))
    elif (pide_fotos or pide_video) and hay_fotos():
        _partes_galeria(r, partes, coma, meta)
    elif pide_fotos or pide_video:
        con_fotos = hay_fotos()
        r["enviar_fotos_casa"] = bool(URL_FOTOS_CASA) and not con_fotos
        r["enviar_ficha_tecnica"] = True
        r["enviar_renders_cocina"] = True
        if con_fotos:
            r["_momento_fotos"] = "pide_fotos"
        else:
            r["_alerta_fotos"] = True  # no hay fotos cargadas: avisar al asesor para que adjunte fotos reales
        partes.append(f"¡Claro{coma}! 📸 Te comparto por aquí "
                      + ("fotos de la casa, " if (URL_FOTOS_CASA or con_fotos) else "")
                      + "los planos de distribución de los 3 pisos y los 2 diseños de cocina que puedes elegir "
                        "(Opción 1: Gris Grafito con LED; Opción 2: Madera Rovere con Taupe).")
        if pide_video and URL_VIDEO_RECORRIDO:
            partes.append(f"Aquí puedes ver el recorrido en video: {URL_VIDEO_RECORRIDO}")
        partes.append("Las 2 casas tienen el 1er y 2do piso con acabados y el 3ro en casco (sin tarrajear). "
                      "En persona se aprecian mucho mejor los 200 m², la iluminación y la vista a la loza deportiva 😊")
    else:
        r["enviar_ficha_tecnica"] = bool(pide_planos)
        r["enviar_renders_cocina"] = bool(pide_cocina)
        r["_momento_fotos"] = "planos"  # 1 render amoblado que le dé vida a los planos
        if pide_planos and pide_cocina:
            partes.append(f"¡Claro{coma}! 📄 Te comparto los planos de distribución de los 3 pisos (200 m² construidos sobre 80 m² de terreno) "
                          "y los 2 diseños de cocina equipada:\n👉 Opción 1: Línea Moderna en Gris Grafito con iluminación LED cálida.\n"
                          "👉 Opción 2: Línea Cálida en Madera Rovere y acabado Taupe.\n"
                          "El 1er y 2do piso tienen acabados y el 3ro se entrega en casco (sin tarrajear).")
        elif pide_planos and fichas_por_casa() and not r["_unidad"]:
            partes.append(f"¡Claro{coma}! 📄 Te comparto la ficha con los planos de cada casa (200 m² construidos sobre 80 m² de terreno, "
                          "en 3 pisos). El 1er y 2do piso tienen acabados y el 3ro se entrega en casco (sin tarrajear).")
        elif pide_planos:
            partes.append(f"¡Claro{coma}! 📄 Te comparto los planos de distribución de los 3 pisos (200 m² construidos sobre 80 m² de terreno). "
                          "El 1er y 2do piso tienen acabados y el 3ro se entrega en casco (sin tarrajear).")
        else:
            partes.append(f"¡Claro{coma}! Estos son los 2 diseños de cocina que puedes elegir (reposteros altos y bajos instalados):\n"
                          "👉 Opción 1: Línea Moderna en Gris Grafito con iluminación LED cálida.\n"
                          "👉 Opción 2: Línea Cálida en Madera Rovere y acabado Taupe.")
        if pide_cocina and (not meta.get("estilo_cocina") or "Por elegir" in str(meta.get("estilo_cocina"))):
            partes.append("Cuando los veas, cuéntame cuál te gusta más 😊")
    meta["material_enviado"] = True
    r["reply_text"] = "\n\n".join(partes) + ("\n\n" + cierre_contextual(meta, nombre_corto) if cerrar else "")
    return r
