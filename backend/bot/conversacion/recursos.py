"""Qué material mandar en cada momento (fotos reales, renders amoblados, videos y fichas por casa) y cómo rotularlo.

Fuente: tabla recursos_media (bot/datos/recursos.py). Respaldo: variables URL_FOTO_* (fotos reales, 'ambas' casas).
Regla: cada render amoblado lleva la aclaración de que los muebles son referenciales. Nunca se repite un archivo.
Cada imagen/video cuenta como un mensaje facturable de WhatsApp: máximo 2 por momento (más solo si el cliente lo pide).
"""
import re
from datetime import datetime, timedelta, timezone

from bot.config import FOTOS_CASA
from bot.datos.recursos import listar_recursos
from bot.utils.texto import limpiar_texto

LEYENDAS = {
    "fachada": "Fachada, frente a la loza deportiva en Urb. Santa Teresa 🏡",
    "sala": "Sala-comedor del 1er piso 🛋️",
    "cocina": "Cocina integrada con barra de porcelanato 🍳",
    "dormitorio": "Dormitorio amplio e iluminado 🛏️",
    "bano": "Baño completo con acabados de estreno 🚿",
    "terraza": "Terraza del 3er piso con vista a la loza deportiva (se entrega en casco, sin tarrajeo ni baranda) 🏗️",
    "cochera": "Cochera privada cerrada 🚗",
    "jardin": "Patio con jardín interior en el 1er piso 🌿",
}
LEYENDAS_MOMENTO = {
    ("objecion", "terraza"): "Esto es lo que un departamento no te da: terraza propia en el 3er piso (en casco, para terminarla a tu gusto) 🔥",
    ("objecion", "cochera"): "...ni cochera privada cerrada 🚗",
    ("objecion", "jardin"): "...ni un jardín interior propio 🌿",
    ("agendado", "fachada"): "Así es la fachada, para que la reconozcas al llegar 📍",
}
AVISO_RENDER = "Muebles agregados como referencia: la casa se entrega sin muebles."
# La cocina en render NO lleva el aviso de muebles: muestra cómo queda con los reposteros instalados (es lo que se entrega con el bono)
TXT_COCINA_RENDER = "Así queda la cocina con los reposteros instalados 🍳 (render del diseño de cocina)"
RENDER_TXT = {  # los renders amoblados venden la emoción: así se vería viviendo ahí
    "sala": "Así se vería la sala-comedor amoblada 🛋️",
    "comedor": "Así se vería el comedor amoblado 🍽️",
    "dormitorio": "Así se vería el dormitorio principal amoblado 🛏️",
    "terraza": "Así podría quedar la terraza una vez terminada 🔥 (render: hoy el 3er piso se entrega en casco, sin tarrajear)",
    "cocina": "Así se vería la cocina en uso 🍳",
}
# momento: (ambientes en orden de prioridad, máximo, solo renders amoblados)
MOMENTOS = {
    "primer_vistazo": (["fachada", "sala"], 2, False),           # pidió info o precio
    "planos": (["sala", "dormitorio", "cocina"], 1, True),      # los planos son fríos: 1 render que los haga vivir
    "distribucion": (["dormitorio", "sala"], 2, False),
    "objecion": (["cochera", "jardin"], 2, False),    # 'está caro': lo que un depa no tiene
    "amoblada": (["sala", "dormitorio", "cocina"], 3, True),   # '¿viene amoblada?', '¿cómo se ve por dentro?'
    "compartir_familia": (["sala", "dormitorio"], 2, True),    # 'lo converso con mi esposo'
    "ubicacion": (["fachada"], 1, False),
    "agendado": (["fachada"], 1, False),
    "rescate": (["sala", "dormitorio", "fachada"], 1, False),
    "no_asistio": (["sala", "dormitorio"], 1, True),
    "post_visita": (["sala", "dormitorio"], 2, True),            # 45 min después: para mostrarla en casa a la familia
    "segunda_visita": (["sala", "dormitorio"], 1, False),
    "pide_fotos": (["fachada", "sala", "cocina", "dormitorio", "bano", "terraza", "cochera", "jardin"], 6, False),
}
REPITE_SI_NO_HAY_NUEVAS = {"pide_fotos", "amoblada", "compartir_familia", "post_visita"}
PREFIERE_RENDER = {"sala", "comedor", "dormitorio", "terraza"}  # un ambiente vacío luce mejor amoblado (con su aclaración)
UNIDAD_TXT = {"casa_1": "Casa 1", "casa_2": "Casa 2"}


def catalogo():
    filas = list(listar_recursos())
    ya = {(f.get("ambiente"), f.get("tipo")) for f in filas}
    for amb, url in FOTOS_CASA.items():
        if url and (amb, "foto_real") not in ya:
            filas.append({"unidad": "ambas", "tipo": "foto_real", "ambiente": amb, "url": url, "leyenda": ""})
    return filas


def hay_fotos():
    return any(f.get("tipo") in ("foto_real", "render_amoblado") for f in catalogo())


def hay_videos():
    return any(f.get("tipo") == "video" for f in catalogo())


def unidad_del_texto(texto):
    """'casa 2', 'la segunda casa' -> 'casa_2'; 'las dos casas' / nada -> None (todas)."""
    t = limpiar_texto(texto)
    if re.search(r"\b(casa\s*(1|uno)|primera casa|casa numero 1)\b", t):
        return "casa_1"
    if re.search(r"\b(casa\s*(2|dos)\b(?! casas)|segunda casa|casa numero 2)", t) and not re.search(r"\blas dos casas\b", t):
        return "casa_2"
    return None


def _nombre_propio(fila):
    """True si el nombre del archivo es más específico que el ambiente ('cuarto niños' vs 'dormitorio')."""
    nombre = limpiar_texto(fila.get("nombre") or "")
    if not nombre or fila.get("leyenda"):
        return False
    return nombre not in {fila.get("ambiente"), "sala comedor", "frontis", "patio", "habitacion", "cuarto", "bano"}


def leyenda(fila, momento=""):
    amb = fila.get("ambiente") or ""
    unidad = UNIDAD_TXT.get(fila.get("unidad"), "")
    if fila.get("tipo") == "video":
        base = fila.get("leyenda") or f"🎥 Recorrido en video{' de la ' + unidad if unidad else ''}"
        return base
    if fila.get("tipo") == "ficha":
        return fila.get("leyenda") or f"📄 Ficha técnica y planos{' de la ' + unidad if unidad else ''} (200 m² construidos en 3 pisos)"
    es_render = fila.get("tipo") == "render_amoblado"
    if es_render and amb == "cocina":
        nombre = fila.get("nombre") if _nombre_propio(fila) else ""
        base = f"{nombre}: {TXT_COCINA_RENDER[0].lower()}{TXT_COCINA_RENDER[1:]}" if nombre else TXT_COCINA_RENDER
        return f"🎨 {unidad + ' · ' if unidad else ''}{base}"
    if _nombre_propio(fila):  # 'Cuarto niños', 'Baño visitas', 'Segundo piso': el nombre del archivo dice más que el genérico
        base = f"{unidad} · {fila['nombre']}" if unidad else fila["nombre"]
        return f"🎨 {base}\n({AVISO_RENDER})" if es_render else f"📸 {base} (foto real)"
    base = (fila.get("leyenda") or LEYENDAS_MOMENTO.get((momento, amb))
            or (RENDER_TXT.get(amb) if es_render else None) or LEYENDAS.get(amb)
            or fila.get("nombre") or "Casa de estreno en Urb. Santa Teresa 🏡")  # ambiente no reconocido: se usa el nombre del archivo
    if unidad:
        base = f"{unidad} · {base}"
    if es_render:
        return f"🎨 {base}\n({AVISO_RENDER})"
    return f"📸 {base} (foto real)"


def _clave(fila):
    return fila.get("url")


def _por_unidad(filas, unidad):
    return [f for f in filas if not unidad or f.get("unidad") in (unidad, "ambas")]


def hay_renders():
    return any(f.get("tipo") == "render_amoblado" for f in catalogo())


def _tipo_ambiente(fila):
    return f"{fila.get('tipo')}:{fila.get('ambiente')}"


def _elegir(filas, ambientes, maximo, enviadas):
    """Una por ambiente; no repite archivo NI otra versión del mismo tipo+ambiente (2 renders de sala = la misma idea)."""
    elegidas = []
    for amb in ambientes:
        opciones = [f for f in filas if f.get("ambiente") == amb and _clave(f) not in enviadas and _tipo_ambiente(f) not in enviadas]
        opciones.sort(key=lambda f: (f.get("tipo") != ("render_amoblado" if amb in PREFIERE_RENDER else "foto_real")))
        if opciones:
            elegidas.append(opciones[0])
        if len(elegidas) >= maximo:
            break
    return elegidas


def _ordenar_variado(filas):
    """Primero un archivo por cada (ambiente, tipo) distinto, luego el resto: así la galería no repite 3 salas seguidas."""
    vistos, primero, despues = set(), [], []
    for f in filas:
        clave = (f.get("ambiente"), f.get("tipo"))
        (despues if clave in vistos and f.get("ambiente") != "otro" else primero).append(f)
        vistos.add(clave)
    return primero + despues


def elegir_galeria(meta, unidad=None, maximo=8):
    """Cuando pide fotos: mezcla las 2 casas (y lo común), fotos reales y renders amoblados, sin repetir lo ya enviado.
    Devuelve ([(url, 'image', leyenda)], cuántas quedan por enviar)."""
    filas = _por_unidad([f for f in catalogo() if f.get("tipo") in ("foto_real", "render_amoblado")], unidad)
    enviadas = set(meta.get("fotos_enviadas") or [])
    nuevas = [f for f in filas if _clave(f) not in enviadas] or filas  # si ya vio todas, se reenvían
    grupos = [_ordenar_variado([f for f in nuevas if f.get("unidad") == u]) for u in ("casa_1", "casa_2", "ambas")]
    elegidas = []
    while len(elegidas) < maximo and any(grupos):
        for g in grupos:  # una de cada casa por turno
            if g and len(elegidas) < maximo:
                elegidas.append(g.pop(0))
    meta["fotos_enviadas"] = sorted(enviadas | {_clave(f) for f in elegidas} | {_tipo_ambiente(f) for f in elegidas})
    quedan = sum(len(g) for g in grupos)
    return [(f["url"], "image", leyenda(f, "pide_fotos")) for f in elegidas], quedan


def resumen_galeria(unidad=None):
    """Qué hay para describirlo en el texto: casas con fotos, si hay renders, si hay videos."""
    filas = _por_unidad(catalogo(), unidad)
    fotos = [f for f in filas if f.get("tipo") in ("foto_real", "render_amoblado")]
    return {"casas": sorted({f.get("unidad") for f in fotos} - {"ambas"}), "renders": any(f.get("tipo") == "render_amoblado" for f in fotos),
            "videos": any(f.get("tipo") == "video" for f in filas), "fichas": any(f.get("tipo") == "ficha" for f in filas)}


def fichas_por_casa():
    return len({f.get("unidad") for f in catalogo() if f.get("tipo") == "ficha"} - {"ambas"}) > 1


def elegir_fotos(momento, meta, unidad=None):
    """[(url, 'image', leyenda)] para ese momento, sin repetir lo ya enviado (salvo que las pida). Registra lo enviado."""
    ambientes, maximo, solo_render = MOMENTOS.get(momento, ([], 0, False))
    tipos = ("render_amoblado",) if solo_render else ("foto_real", "render_amoblado")
    filas = _por_unidad([f for f in catalogo() if f.get("tipo") in tipos], unidad)
    enviadas = set(meta.get("fotos_enviadas") or [])
    elegidas = _elegir(filas, ambientes, maximo, enviadas)
    if not elegidas and momento in REPITE_SI_NO_HAY_NUEVAS:
        elegidas = _elegir(filas, ambientes, maximo, set())  # tiene sentido mostrarlas otra vez (p. ej. para la familia)
    if elegidas:
        meta["fotos_enviadas"] = sorted(enviadas | {_clave(f) for f in elegidas} | {_tipo_ambiente(f) for f in elegidas})
    return [(f["url"], "image", leyenda(f, momento)) for f in elegidas]


def renders_cocina_catalogo(estilo):
    """URLs del bucket con el render de cocina de ese estilo ('gris' / 'madera'), por si el archivo fijo (cocina_1/2.jpg) falla."""
    claves = {"gris": r"gris|grafito|led|modern|cocina[ _-]?2", "madera": r"madera|rovere|taupe|calid|cocina[ _-]?1"}[estilo]
    filas = [f for f in catalogo() if f.get("ambiente") == "cocina" and f.get("tipo") in ("render_amoblado", "foto_real")]
    return [f["url"] for f in filas if re.search(claves, limpiar_texto(f.get("origen") or f.get("url") or ""))]


def material_de_tipo(tipo, unidad=None):
    """Videos o fichas del catálogo: [(url, tipo_whatsapp, leyenda)] (tipo_whatsapp se deduce del archivo al enviar)."""
    filas = _por_unidad([f for f in catalogo() if f.get("tipo") == tipo], unidad)
    wa = "video" if tipo == "video" else "document"
    return [(f["url"], wa, leyenda(f)) for f in filas]


def _recien_agendado(meta):
    try:
        creada = datetime.fromisoformat(meta.get("ts_cita_creada") or "")
        return meta.get("etapa") in ["agendado", "pregunto_acompanantes"] and datetime.now(timezone.utc) - creada < timedelta(minutes=2)
    except ValueError:
        return False


def asignar_media(parsed, meta, canal):
    """Al final de cada respuesta: agrega a parsed['recursos'] el material del momento (solo WhatsApp)."""
    momento = parsed.pop("_momento_fotos", None) or meta.pop("_momento_fotos", None)
    meta.pop("_momento_fotos", None)
    if canal != "whatsapp":
        return
    unidad = parsed.get("_unidad")
    extra = []
    if parsed.get("_galeria"):
        fotos, _ = elegir_galeria(meta, unidad)
        extra += fotos
    if parsed.get("_pide_video"):
        extra += material_de_tipo("video", unidad)
        meta["videos_enviados"] = True
    if parsed.get("enviar_ficha_tecnica"):
        fichas = material_de_tipo("ficha", unidad)
        if fichas:  # fichas por casa en el catálogo reemplazan a la ficha única (URL_FICHA_TECNICA)
            parsed["enviar_ficha_tecnica"] = False
            extra += fichas
    texto = parsed.get("reply_text") or ""
    if not momento and _recien_agendado(meta) and ("quedó registrada" in texto or "Cita confirmada" in texto):
        momento = "agendado"
    if momento:
        extra += elegir_fotos(momento, meta, unidad)
    if extra:
        parsed["recursos"] = (parsed.get("recursos") or []) + extra
