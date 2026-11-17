"""Motor de respaldo cuando Gemini no responde."""
from datetime import datetime

from bot.config import MAPS_URL
from bot.conversacion.faq import responder_faq
from bot.conversacion.slots import _slots_a_texto
from bot.integraciones.calendario import get_free_slots
from bot.nlp.patrones import VISITA_RE
from bot.utils.fechas import format_fecha_es
from bot.utils.texto import limpiar_texto


def build_Contextual_fallback(canal, user_text, nombre_cliente, has_history, meta=None):
    low = (user_text or "").strip().lower()
    saludo_nom = f"¡Hola, {nombre_cliente}!" if nombre_cliente not in ["Interesado", "Cliente", ""] else "¡Hola!"
    nombre_corto = nombre_cliente.split()[0] if nombre_cliente not in ["Interesado", "Cliente", ""] else ""

    faq = responder_faq(user_text, nombre_corto, meta)
    if faq:
        es_comentario = canal in ["fb_comment", "ig_comment"]
        return {
            "reply_text": (f"{saludo_nom} Te enviamos el detalle por mensaje privado 📩. También puedes escribirnos al WhatsApp: "
                           "https://wa.me/51986339051") if es_comentario else faq,
            "private_reply": faq if es_comentario else "",
            "ignorar_comentario": False,
            "enviar_ficha_tecnica": False,
            "enviar_renders_cocina": False,
            "estilo_render_preferido": "ambos",
            "agendar_visita_iso": ""
        }

    # Caso 1: El cliente respondio "1" o pide planos / ficha / diseños de cocina
    if low in ["1", "1️⃣", "uno", "opcion 1", "opción 1"] or any(w in low for w in ["plano", "ficha", "cocina", "render", "repostero", "foto"]):
        txt = (
            f"¡Claro{', ' + nombre_corto if nombre_corto else ''}! 😊 Te comparto los planos arquitectónicos de distribución "
            "de los 3 pisos (200 m² construidos sobre 80 m² de terreno; los 2 primeros pisos tienen acabados y el 3ro "
            "se entrega en casco (construido y techado, sin tarrajear) para que lo termines a tu gusto; entrega inmediata con título en SUNARP) junto con nuestras 2 opciones de cocina equipada:\n"
            "👉 Opción 1: Línea Moderna en Gris Grafito con iluminación LED cálida.\n"
            "👉 Opción 2: Línea Cálida en Madera Rovere y acabado Taupe.\n\n"
            "Cuéntame, ¿cuál de los dos estilos de cocina te gusta más y si estás evaluando la compra al contado o con crédito hipotecario para agendar tu visita guiada?"
        )
        return {
            "reply_text": txt,
            "private_reply": "",
            "ignorar_comentario": False,
            "enviar_ficha_tecnica": True,
            "enviar_renders_cocina": True,
            "estilo_render_preferido": "ambos",
            "agendar_visita_iso": ""
        }

    # Caso 2: El cliente respondio "2" o pide visitar / ir a ver la casa / direccion
    if low in ["2", "2️⃣", "dos", "opcion 2", "opción 2"] or VISITA_RE.search(limpiar_texto(user_text)):
        libres = get_free_slots(n=2)
        turnos = " o el ".join(format_fecha_es(s, relativo=True) for s in libres) if libres else "el día y hora que prefieras"
        txt = (
            f"¡Qué excelente noticia{', ' + nombre_corto if nombre_corto else ''}! Será un gusto recibirte en la Urb. Santa Teresa (Lambayeque), "
            "exactamente frente a la loza deportiva y a 1 min de la Av. Ramón Castilla 🏡.\n\n"
            f"Tengo libre el {turnos}. ¿Cuál te acomoda? "
            "Y para registrarte con el ingeniero: ¿la compra la evalúas al contado o con crédito hipotecario (desde 10% de inicial)?"
        )
        return {
            "reply_text": txt,
            "private_reply": "",
            "ignorar_comentario": False,
            "enviar_ficha_tecnica": False,
            "enviar_renders_cocina": False,
            "estilo_render_preferido": "ambos",
            "agendar_visita_iso": ""
        }

    # Caso 3: Pregunta por cuotas / bancos / credito / inicial / forma de pago
    if any(w in low for w in ["cuota", "banco", "credito", "crédito", "inicial", "hipotecario", "contado", "financiamiento", "pago"]):
        txt = (
            f"Con gusto te detallo{', ' + nombre_corto if nombre_corto else ''}: nuestras 2 casas son de estreno y ya cuentan con título independiente en SUNARP para entrega inmediata. "
            "No manejamos crédito directo, pero puedes adquirirlas al contado o mediante crédito hipotecario con cualquier banco (BCP, BBVA, Interbank, Scotiabank, etc.), "
            "donde el banco solicita desde el 10% de cuota inicial (aprox. $13,500 USD sobre el valor de lista de $135,000 USD, con bono especial en visita para la primera casa).\n\n"
            "¿Ya cuentas con tu inicial disponible o crédito preaprobado para coordinar tu visita guiada esta semana? 😊"
        )
        return {
            "reply_text": txt,
            "private_reply": "",
            "ignorar_comentario": False,
            "enviar_ficha_tecnica": False,
            "enviar_renders_cocina": False,
            "estilo_render_preferido": "ambos",
            "agendar_visita_iso": ""
        }

    # Caso 4: Pregunta por precio / cuanto cuesta / valor
    if any(w in low for w in ["precio", "cuanto", "cuánto", "valor", "costo", "cuesta", "caro", "descuento", "135", "125"]):
        txt = (
            f"El valor de lista de nuestras casas de estreno en Urb. Santa Teresa (Lambayeque) es de $135,000 USD. "
            "Al tener 200 m² construidos en 3 pisos (sobre 80 m² de terreno, frente a loza deportiva), te sale a solo $675 por m² construido, "
            "mucho más ventajoso que un departamento pequeño en Chiclayo (que supera los $1,000/m²).\n\n"
            "Además, para la PRIMERA UNIDAD que se separe otorgamos un Bono Especial de Lanzamiento (incluyendo reposteros de cocina altos y bajos a tu gusto "
            "o aplicando un descuento directo en visita). ¿Te gustaría ver los planos y diseños de cocina (escribe 1) o agendar una visita guiada (escribe 2)?"
        )
        return {
            "reply_text": txt,
            "private_reply": "",
            "ignorar_comentario": False,
            "enviar_ficha_tecnica": False,
            "enviar_renders_cocina": False,
            "estilo_render_preferido": "ambos",
            "agendar_visita_iso": ""
        }

    # Caso 5: Pregunta por ubicacion / donde queda / mapa
    if any(w in low for w in ["ubicacion", "ubicación", "donde", "dónde", "direccion", "dirección", "mapa", "llegar", "lugar"]):
        txt = (
            f"Estamos ubicados en la Urb. Santa Teresa (Lambayeque), en la intersección de las calles 5 de Febrero y Andrés Lastres, "
            f"exactamente frente a la loza deportiva, a 1 min de la Av. Ramón Castilla y a 5 min de la UNPRG 📍: {MAPS_URL}\n\n"
            "Las 2 casas tienen 200 m² construidos en 3 pisos (1er y 2do piso con acabados; 3ro en casco, sin tarrajear) y entrega inmediata con título en SUNARP. "
            "¿Qué día te gustaría visitarnos por la mañana o por la tarde para mostrártelas por dentro?"
        )
        return {
            "reply_text": txt,
            "private_reply": "",
            "ignorar_comentario": False,
            "enviar_ficha_tecnica": False,
            "enviar_renders_cocina": False,
            "estilo_render_preferido": "ambos",
            "agendar_visita_iso": ""
        }

    # Caso 6: Pregunta por distribucion / area / metraje / pisos
    if any(w in low for w in ["distribucion", "distribución", "area", "área", "metraje", "metro", "piso", "habitacion", "dormitorio"]):
        txt = (
            "Cada casa cuenta con 80 m² de terreno y 200 m² construidos distribuidos en 3 pisos independientes (entrega inmediata en SUNARP):\n"
            "• 1er Piso: Cochera privada cerrada, sala-comedor amplia, baño de visitas, cocina equipada con barra y patio con jardín interior.\n"
            "• 2do Piso: 3 habitaciones amplias: la principal con su baño propio y 2 secundarias que comparten un baño completo.\n"
            "• 3er Piso (en casco: construido y techado, sin tarrajeo, cerámica ni baranda): terraza con vista a la loza deportiva, estructura de la jardinera, terma y zona de lavandería, para terminarlo a tu gusto (según plano, se puede ampliar una habitación con su baño).\n\n"
            "Te adjunto los planos detallados por aquí 📄. ¿Te gustaría agendar una visita esta semana para recorrer los 3 niveles en persona?"
        )
        return {
            "reply_text": txt,
            "private_reply": "",
            "ignorar_comentario": False,
            "enviar_ficha_tecnica": True,
            "enviar_renders_cocina": False,
            "estilo_render_preferido": "ambos",
            "agendar_visita_iso": ""
        }

    # Caso 7: Ya hay historial previo (para NUNCA repetir el bloque de bienvenida dos veces)
    if has_history and canal == "whatsapp":
        meta = meta or {}
        if meta.get("etapa") == "ofrecio_horarios" and meta.get("slots_ofrecidos"):
            # Ya tiene la lista: no repetirla (eso se sentía insistente). Pregunta abierta y corta.
            txt = (f"Cuéntame{', ' + nombre_corto if nombre_corto else ''}, ¿te acomoda alguno de los horarios que te pasé o prefieres "
                   "otro día? Y si tienes alguna duda (precio, financiamiento, distribución), con gusto te la resuelvo 😊")
        elif meta.get("cita_agendada") and meta.get("fecha_cita"):
            try:
                f_cita = format_fecha_es(datetime.fromisoformat(meta["fecha_cita"]), relativo=True)
            except Exception:
                f_cita = "la fecha acordada"
            txt = (
                f"¡Gracias{', ' + nombre_corto if nombre_corto else ''}! 😊 Te recuerdo que tu visita guiada está registrada para el *{f_cita}* "
                f"en Urb. Santa Teresa (frente a la loza deportiva): {MAPS_URL}\n\n¿Tienes alguna otra consulta antes de la visita?"
            )
        elif meta.get("etapa") == "espera_cliente":
            txt = f"Aquí estoy para lo que necesites{', ' + nombre_corto if nombre_corto else ''} 😊"
        else:
            libres = get_free_slots(n=3)
            if libres:
                meta["etapa"] = "ofrecio_horarios"
                meta["slots_ofrecidos"] = [s.isoformat() for s in libres]
                txt = (
                    f"¡Gracias{', ' + nombre_corto if nombre_corto else ''}! 😊 Lo mejor para que veas los acabados, recorras los 3 pisos y te expliquemos "
                    "el Bono Especial de la 1ra Unidad es una visita guiada. Estos son los horarios libres más próximos:\n\n"
                    f"{_slots_a_texto(libres)}\n\nRespóndeme con el número (o dime otro día y hora) y te la registro."
                )
            else:
                txt = (
                    f"¡Gracias{', ' + nombre_corto if nombre_corto else ''}! 😊 ¿Qué día y hora te acomodaría para una visita guiada "
                    "y así te muestro los 3 pisos y te explico el Bono Especial de la 1ra Unidad?"
                )
        return {
            "reply_text": txt,
            "private_reply": "",
            "ignorar_comentario": False,
            "enviar_ficha_tecnica": False,
            "enviar_renders_cocina": False,
            "estilo_render_preferido": "ambos",
            "agendar_visita_iso": ""
        }

    # Caso 8: Primer contacto en WhatsApp o Redes
    if canal == "whatsapp":
        txt = (
            f"{saludo_nom} Un gusto saludarte de parte de SAGUE Constructora 🏡. "
            "Nuestras 2 casas de estreno (entrega inmediata e independizadas en SUNARP) "
            "están ubicadas frente a la loza deportiva en la Urb. Santa Teresa (Lambayeque), a 1 min de la Av. Ramón Castilla. "
            "Cuentan con 80 m² de terreno y 200 m² construidos en 3 pisos (cochera privada, jardín interior, 3 habitaciones, 3 baños y terraza; el 3er piso en casco, sin tarrajear). "
            "Su valor de lista es de $135,000 USD ($675/m² construido, con Bono Especial para la 1ra unidad), disponible al contado o con crédito hipotecario, "
            "e incluye los reposteros de cocina instalados a tu gusto.\n\n"
            "Cuéntame, ¿cómo prefieres avanzar?:\n"
            "1️⃣ Recibir por aquí los planos de distribución y los 2 diseños de cocina.\n"
            "2️⃣ Coordinar una visita guiada para recorrerlas en persona."
        )
    else:
        txt = (
            f"{saludo_nom} Gracias por escribir a SAGUE Constructora 🏡. Nuestras 2 casas de estreno (entrega inmediata) "
            "frente a la loza deportiva en Urb. Santa Teresa (Lambayeque) tienen 200 m² construidos en 3 pisos, "
            "título en SUNARP y cocina equipada ($135,000 USD, al contado o crédito hipotecario). "
            "¿Me compartes tu número de WhatsApp por aquí para enviarte el PDF con los planos y renders de cocina, o nos escribes directo al 986 339 051?"
        )
    return {
        "reply_text": txt,
        "private_reply": txt if canal in ["fb_comment", "ig_comment"] else "",
        "ignorar_comentario": False,
        "enviar_ficha_tecnica": False,
        "enviar_renders_cocina": False,
        "estilo_render_preferido": "ambos",
        "agendar_visita_iso": ""
    }
