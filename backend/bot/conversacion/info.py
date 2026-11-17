"""Respuestas informativas por tema (ubicación, área, precio, etc.)."""
import re

from bot.config import MAPS_URL, PRECIO_LISTA_USD
from bot.conversacion.base import _resp
from bot.conversacion.cierres import cierre_info
from bot.conversacion.precio import gancho_m2
from bot.conversacion.presupuesto import linea_contado
from bot.utils.texto import _usd, limpiar_texto


INFO_TEMAS = {
    "general": r"\b(info|informacion|informes?|detalles?|mas datos|datos|caracteristicas|me interesa\w*|interesad\w*|quisiera saber|"
               r"quiero saber|cuentame|de que se trata|sobre (la|las|esta|estas|esa|esas) casas?|disponible\w*)\b",
    "precio": r"\b(precios?|cuanto (cuesta|cuestan|vale|valen|esta|estan|sale|salen|es)|costos?|valor|cuanto)\b",
    "area": r"\b(area|areas|metraje|metros|m2|mide|miden|medidas|tamano|terreno|construid\w*|dimensiones)\b",
    "ubicacion": r"\b(ubicacion|ubicad\w*|donde (queda|quedan|esta|estan|es|son)|direccion|como (llego|llegar|ir)|mapa|lugar|zona|sector|referencias? para llegar)\b",
    "distribucion": r"\b(distribucion|distribuid\w*|cuantos (pisos|cuartos|dormitorios|banos|habitaciones|niveles)|habitaciones|dormitorios|cuartos|"
                    r"banos|ambientes|que tiene|que incluye|cochera|terraza|jardin|pisos)\b",
    "entrega": r"\b(entrega\w*|cuando (la |las )?entregan|esta lista|estan listas|en planos|preventa|terminad\w*|para mudarse|estreno)\b",
}


def temas_info(user_text):
    t = limpiar_texto(user_text)
    temas = [k for k, rx in INFO_TEMAS.items() if re.search(rx, t)]
    if "precio" in temas and re.search(r"\binicial\b|\bcuota", t) and not re.search(r"\bprecio", t):
        temas.remove("precio")  # "cuánto de inicial" lo responde la FAQ
    if "general" in temas and len(temas) > 1:
        temas.remove("general")
    return temas


def responder_info(user_text, nombre_corto, meta=None, primer_contacto=False, cerrar=True):
    """Información, detalles, precio, área, ubicación/dirección, distribución, entrega y sus combinaciones (Casos 2, 4, 5, 6, 9, 12)."""
    meta = meta if meta is not None else {}
    temas = temas_info(user_text)
    if not temas:
        return None
    nom = f", {nombre_corto}" if nombre_corto else ""
    elogio = re.search(r"\b(excelente|buen\w* (diseno|acabado|trabajo|construccion|casa)|bonit\w*|linda\w*|hermos\w*|me gusta\w*|que buena|se ve bien|espectacular)\b",
                       limpiar_texto(user_text))
    if primer_contacto:
        saludo = f"¡Hola{nom}! Un gusto saludarte de parte de SAGUE Constructora 🏡. "
    elif elogio:
        saludo = f"¡Muchas gracias{nom}, nos alegra que te guste! 😊 Te detallo: "
    else:
        saludo = f"¡Con gusto te detallo{nom}! 😊 "
    b = {
        "precio": (f"💰 *Precio:* valor de lista de *{_usd(PRECIO_LISTA_USD)} USD*. Con 200 m² construidos te sale a solo *$675 por m²*, "
                   "cuando un departamento de 90 m² en Chiclayo (sin cochera, jardín ni terraza) está entre $950 y $1,150 por m². "
                   + linea_contado()),
        "area": "📐 *Área:* 80 m² de terreno y *200 m² construidos* en 3 pisos independientes.",
        "distribucion": ("🏠 *Distribución:*\n• *1er piso:* cochera privada cerrada, sala-comedor amplia, baño de visitas, cocina integrada con barra y patio con jardín interior.\n"
                         "• *2do piso:* 3 habitaciones amplias: la principal con su baño propio y 2 secundarias que comparten un baño completo.\n"
                         "• *3er piso (en casco):* construido y techado, con la terraza (vista a la loza deportiva), la estructura de la jardinera, "
                         "la terma y la zona de lavandería, pero sin tarrajeo, cerámica ni baranda: lo terminas a tu gusto. "
                         "Según el plano, ahí puedes ampliar más adelante una habitación con su baño."),
        "ubicacion": ("📍 *Ubicación:* Urb. Santa Teresa, Lambayeque — calles 5 de Febrero y Andrés Lastres, *frente a la loza deportiva*. "
                      "A 1 min de la Av. Ramón Castilla, 2 min de la Plaza de Armas y Metro, 5 min de la UNPRG y a 7 cuadras del Hospital Belén.\n"
                      f"Mapa: {MAPS_URL}"),
        "entrega": "🔑 *Entrega inmediata* con título independizado en SUNARP y libre de cargas. Las 2 casas tienen el 1er y 2do piso con acabados y el 3ro en casco (construido y techado, sin tarrajear) para que lo termines a tu gusto.",
        "general": ("Son *2 casas de estreno* en Urb. Santa Teresa (Lambayeque), frente a la loza deportiva y a 1 min de la Av. Ramón Castilla: "
                    "*80 m² de terreno y 200 m² construidos* en 3 pisos (cochera, jardín interior, 3 habitaciones, 3 baños y terraza; el 1er y 2do piso con acabados y el 3ro en casco, sin tarrajear). "
                    f"Valor de lista *{_usd(PRECIO_LISTA_USD)} USD* (solo $675/m²), entrega inmediata con título en SUNARP, y la 1ra unidad que se separe "
                    "incluye los reposteros de cocina instalados a tu gusto."),
    }
    orden = ["general", "precio", "area", "distribucion", "entrega", "ubicacion"]
    if "precio" in temas and "precio" in (meta.get("ya_explicado") or []):
        # ya se le dio el precio completo: no repetir el bloque, recordarlo en corto
        b["precio"] = f"💰 Como te comentaba: valor de lista *{_usd(PRECIO_LISTA_USD)}*. " + linea_contado()
    if "precio" in temas or "general" in temas:
        meta["gancho_m2_n"] = int(meta.get("gancho_m2_n") or 0) + 1  # ya se mostró el precio por m²
        meta["ya_explicado"] = list(set((meta.get("ya_explicado") or []) + ["precio"]))
    elif "area" in temas and not meta.get("gancho_m2_n"):
        b["area"] += " " + gancho_m2(meta, "area")  # quien pregunta metros, está comparando: momento ideal para el $/m²
    cuerpo = "\n\n".join(b[k] for k in orden if k in temas)
    r = _resp("")
    r["_sin_control_repeticion"] = True
    if "distribucion" in temas:
        r["_momento_fotos"] = "distribucion"
    elif "precio" in temas or "general" in temas:
        r["_momento_fotos"] = "primer_vistazo"
    elif temas == ["ubicacion"]:
        r["_momento_fotos"] = "ubicacion"
    if "distribucion" in temas:
        r["enviar_ficha_tecnica"] = True
        cuerpo += "\n\nTe comparto también los planos de los 3 pisos 📄."
    r["reply_text"] = saludo + cuerpo + ("\n\n" + cierre_info(meta, nombre_corto, temas) if cerrar else "")
    return r
