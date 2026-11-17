"""Catálogo de material por casa leyendo el bucket 'recursos' de Supabase Storage, con los nombres que tengan.

No exige nombres exactos: recorre las carpetas y deduce de la RUTA y el NOMBRE de cada archivo:
- casa:     'casa 1', 'casa-1', 'casa1', 'c1', 'primera' -> casa_1 (igual para la 2); si no dice -> 'ambas'
- tipo:     .mp4 -> video · .pdf / 'ficha' / 'plano' -> ficha · 'render' / 'amoblado' / 'muebles' / '3d' -> render_amoblado · resto -> foto_real
- ambiente: sala, comedor, cocina, dormitorio/habitación/cuarto, baño, terraza/azotea, cochera/garaje, fachada/frontis, jardín/patio...
El nombre del archivo también se usa como leyenda cuando no es un ambiente conocido ('segundo-piso.jpg' -> 'Segundo piso').
"""
import re
import time
import unicodedata
from urllib.parse import quote

from bot.config import CARPETA_MATERIAL, NOMBRES_SIEMPRE_RENDER, SUPABASE_URL, URL_FICHA_TECNICA
from bot.db import supabase

CLIENTE = "sague"
BUCKET = "recursos"
CARPETA_BASE = CARPETA_MATERIAL
PROFUNDIDAD_MAX = 4
VIDEO_MAX_BYTES = 16 * 1024 * 1024   # límite de WhatsApp para videos
EXT_IMAGEN = ("jpg", "jpeg", "png")
EXT_NO_SOPORTADA = {"heic": "JPG", "heif": "JPG", "webp": "JPG", "mov": "MP4", "avi": "MP4", "mkv": "MP4", "gif": "JPG"}
AMBIENTES = [  # (ambiente, palabras que lo identifican en el nombre)
    ("fachada", ["fachada", "frontis", "frente", "exterior", "calle"]),
    ("sala", ["sala", "living", "estar"]),
    ("comedor", ["comedor"]),
    ("cocina", ["cocina", "kitchen", "repostero"]),
    ("dormitorio", ["dormitorio", "habitacion", "cuarto", "recamara", "alcoba", "dorm"]),
    ("bano", ["bano", "banos", "ss hh", "sshh", "servicio higienico"]),
    ("terraza", ["terraza", "azotea", "parrilla", "techo"]),
    ("cochera", ["cochera", "garaje", "garage", "estacionamiento"]),
    ("jardin", ["jardin", "patio", "verde"]),
    ("lavanderia", ["lavanderia", "lavadero"]),
    ("escalera", ["escalera", "escaleras"]),
    ("recorrido", ["recorrido", "tour", "video"]),
    ("planos", ["plano", "planos", "ficha", "distribucion", "lamina"]),
]
CARPETAS_FOTOS_REALES = {"fotos", "fotos reales", "foto real", "reales"}
_CACHE = {"ts": 0.0, "filas": [], "avisos": []}
_TTL = 600  # 10 min: un archivo nuevo se usa como máximo 10 min después de subirlo


def _norm(s):
    s = unicodedata.normalize("NFD", (s or "").lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def _unidad(ruta_n):
    if re.search(r"\b(casa ?(1|01|uno|i)|c ?1|primera( casa)?|unidad ?1)\b", ruta_n):
        return "casa_1"
    if re.search(r"\b(casa ?(2|02|dos|ii)|c ?2|segunda( casa)?|unidad ?2)\b", ruta_n):
        return "casa_2"
    return "ambas"


def _tipo(ruta_n, ext):
    if ext == "mp4":
        return "video"
    if ext == "pdf" or re.search(r"\b(ficha|fichas|plano|planos|lamina|laminas)\b", ruta_n):
        return "ficha"
    if re.search(r"\b(render\w*|amoblad\w*|amueblad\w*|mueble\w*|decorad\w*|3d|referencia\w*|staging|virtual\w*|editad\w*|simulad\w*)\b", ruta_n):
        return "render_amoblado"
    return "foto_real"


def _ambiente(nombre_n, ruta_n):
    for texto in (nombre_n, ruta_n):  # primero el nombre del archivo, luego las carpetas
        for amb, palabras in AMBIENTES:
            if any(re.search(rf"\b{re.escape(p)}", texto) for p in palabras):
                return amb
    return "otro"


def nombre_legible(nombre):
    """'segundo-piso_2.jpg' -> 'Segundo piso'."""
    base = re.sub(r"[_\-.]+", " ", nombre.rsplit(".", 1)[0])
    base = re.sub(r"\b(img|dsc|foto|render|casa ?\d|c\d|\d+)\b", " ", base, flags=re.I)
    base = re.sub(r"\s+", " ", base).strip()
    return base[:1].upper() + base[1:] if base else ""


def _url_publica(ruta):
    return f"{SUPABASE_URL}/storage/v1/object/public/{BUCKET}/{quote(ruta)}"


def _clasificar(ruta, archivo, avisos):
    nombre = archivo.get("name") or ""
    ext = nombre.rsplit(".", 1)[-1].lower() if "." in nombre else ""
    if ext in EXT_NO_SOPORTADA:
        avisos.append(f"{ruta}: formato .{ext} no sirve para WhatsApp, conviértelo a {EXT_NO_SOPORTADA[ext]}")
        return None
    if ext not in EXT_IMAGEN + ("mp4", "pdf"):
        return None
    tam = int((archivo.get("metadata") or {}).get("size") or 0)
    if ext == "mp4" and tam > VIDEO_MAX_BYTES:
        avisos.append(f"{ruta} pesa {tam / 1048576:.0f} MB: WhatsApp acepta videos de hasta 16 MB")
        return None
    ruta_n, nombre_n = _norm(ruta), _norm(nombre.rsplit(".", 1)[0])
    tipo, ambiente = _tipo(ruta_n, ext), _ambiente(nombre_n, ruta_n)
    carpetas = {_norm(c) for c in ruta.split("/")[:-1]}
    if tipo == "render_amoblado" and carpetas & CARPETAS_FOTOS_REALES and not re.search(r"\brender", nombre_n):
        tipo = "foto_real"  # la carpeta 'fotos' manda: son fotos reales (aunque la ruta tenga otra palabra)
    if tipo == "foto_real" and not re.search(r"\breal(es)?\b", ruta_n) and \
            any(re.search(rf"\b{re.escape(_norm(n))}\b", nombre_n) for n in NOMBRES_SIEMPRE_RENDER):
        tipo = "render_amoblado"  # 'sala comedor.jpg' es render aunque no lo diga; 'sala de estar.jpg' es foto real
    return {"unidad": _unidad(ruta_n), "tipo": tipo, "ambiente": ambiente, "url": _url_publica(ruta),
            "leyenda": "", "nombre": nombre_legible(nombre), "origen": ruta}


def _recorrer(store, carpeta, profundidad, avisos, filas):
    try:
        items = store.list(carpeta, {"limit": 1000, "sortBy": {"column": "name", "order": "asc"}}) or []
    except Exception as e:
        avisos.append(f"No se pudo leer la carpeta '{carpeta or '/'}': {str(e)[:100]}")
        return
    for it in items:
        nombre = it.get("name") or ""
        if not nombre or nombre.startswith("."):
            continue
        ruta = f"{carpeta}/{nombre}" if carpeta else nombre
        if it.get("id") is None:  # es carpeta
            if profundidad < PROFUNDIDAD_MAX:
                _recorrer(store, ruta, profundidad + 1, avisos, filas)
            continue
        if not carpeta:
            continue  # archivos sueltos en la raíz = los de siempre (ficha_tecnica.jpg, cocina_1.jpg...), ya se usan por variable
        fila = _clasificar(ruta, it, avisos)
        if fila and fila["url"] != URL_FICHA_TECNICA:
            filas.append(fila)


def _desde_bucket(avisos):
    store = supabase.storage.from_(BUCKET)
    filas = []
    _recorrer(store, CARPETA_BASE, 1, avisos, filas)
    if not filas:  # la carpeta tiene otro nombre: se revisa todo el bucket
        _recorrer(store, "", 0, avisos, filas)
    for i, f in enumerate(filas):
        f["orden"] = i
    return filas


def _desde_tabla():
    try:
        res = (supabase.table("recursos_media").select("*").eq("cliente", CLIENTE).eq("activo", True).order("orden").execute())
        return res.data or []
    except Exception:
        return []  # la tabla es opcional


def listar_recursos():
    """Material disponible (bucket + tabla opcional). [] si no hay Supabase."""
    if not supabase:
        return []
    if _CACHE["ts"] and time.time() - _CACHE["ts"] < _TTL:
        return _CACHE["filas"]
    avisos = []
    try:
        filas = _desde_bucket(avisos)
    except Exception as e:
        avisos.append(f"No se pudo leer el bucket: {str(e)[:150]}")
        filas = []
    urls = {f["url"] for f in filas}
    filas += [f for f in _desde_tabla() if f.get("url") not in urls]
    if not filas:
        avisos.append("No encontré archivos. Si sí los subiste, el bot no tiene permiso para listar el bucket "
                      "(ver docs/GUIA_SUBIR_MATERIAL.md, paso 5).")
    for a in avisos:
        print("⚠️ Material:", a)
    _CACHE.update(ts=time.time(), filas=filas, avisos=avisos)
    return filas


def resumen_catalogo(refrescar=True):
    """Para /diagnostico/material: lo que el bot ve en el bucket, cómo lo entendió y los problemas encontrados."""
    if refrescar:
        _CACHE["ts"] = 0
    filas = listar_recursos()
    conteo = {}
    for f in filas:
        clave = f"{f.get('unidad')} · {f.get('tipo')}"
        conteo[clave] = conteo.get(clave, 0) + 1
    return {"bucket": BUCKET, "total": len(filas), "resumen": conteo, "avisos": _CACHE["avisos"],
            "archivos": [{k: f.get(k) for k in ["origen", "unidad", "tipo", "ambiente", "nombre"]} for f in filas]}
