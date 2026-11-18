"""Catálogo del PeruPTD Native CRM (siempre del tenant de la sesión):
  GET    /api/hub/catalogo                       -> productos con sus archivos
  POST   /api/hub/catalogo                       -> crear producto
  PUT    /api/hub/catalogo/<item_id>             -> editar (precios, modo de calificación, preguntas filtro, condiciones…)
  DELETE /api/hub/catalogo/<item_id>             -> borrar (y sus archivos)
  POST   /api/hub/catalogo/<item_id>/media       -> subir archivo (multipart: file, role, caption_es, caption_en)
                                                    al bucket público 'catalogo' y registrarlo en catalog_media
  DELETE /api/hub/catalogo/<item_id>/media/<media_id>
  POST   /api/hub/catalogo/sincronizar           -> traer el catálogo del CRM externo del cliente"""
import re
import uuid
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request

from bot import catalogo, tenant
from bot.catalogo.sincronizar import sincronizar
from bot.config import MAX_SUBIDA_MB
from bot.db import supabase
from bot.hub.sesion import requiere_sesion

bp = Blueprint("hub_catalogo", __name__)
BUCKET = "catalogo"
ROLES = ("FIRST_INFO", "SPECS_PDF", "PRICE_OBJECTION", "PROOF_RESULTS", "VIDEO_TOUR", "LOCATION_MAP",
         "OPTION_RENDER", "LOCATION_FACADE", "POST_VISIT_45M", "RESCUE_24H")
MODOS = ("credito_inicial", "seguro_medico", "elegibilidad", "b2b")
ESTADOS = ("available", "last_units", "sold_out")
TIPOS = {"image/jpeg": ("image", "jpg"), "image/png": ("image", "png"), "image/webp": ("image", "webp"),
         "application/pdf": ("pdf", "pdf"), "video/mp4": ("video", "mp4"), "video/quicktime": ("video", "mov")}
TEXTO = ("name_es", "name_en", "category", "currency", "promo_bonus_es", "promo_bonus_en", "value_comparison_es",
         "value_comparison_en", "insurance_es", "insurance_en", "conditions_es", "conditions_en", "location_address",
         "google_maps_url", "external_crm_id")
NUMERO = {"list_price": (0, 1e10), "cash_price": (0, 1e10), "min_down_payment_pct": (0, 100),
          "recommended_down_payment_pct": (0, 100), "annual_rate_pct": (0, 100), "max_term_years": (0, 40), "sort_order": (-1e6, 1e6)}


def _error(msg, codigo=400):
    return jsonify({"error": msg}), codigo


def validar(datos, nuevo):
    """Devuelve (fila_limpia, error). Solo pasan campos conocidos; nunca tenant_id/id del cliente."""
    fila = {}
    for c in TEXTO:
        if c in datos:
            v = datos[c]
            fila[c] = None if v in (None, "") else str(v).strip()[:4000]
    for c, (lo, hi) in NUMERO.items():
        if c in datos and datos[c] not in (None, ""):
            try:
                n = float(datos[c])
            except (TypeError, ValueError):
                return None, f"{c} debe ser un número"
            if not lo <= n <= hi:
                return None, f"{c} fuera de rango ({lo}–{hi})"
            fila[c] = int(n) if c == "sort_order" else n
        elif c in datos and c == "cash_price":
            fila[c] = None
    if "status" in datos:
        if datos["status"] not in ESTADOS:
            return None, f"status debe ser uno de {', '.join(ESTADOS)}"
        fila["status"] = datos["status"]
    if "qualification_mode" in datos:
        if datos["qualification_mode"] not in MODOS:
            return None, f"qualification_mode debe ser uno de {', '.join(MODOS)}"
        fila["qualification_mode"] = datos["qualification_mode"]
    if "keywords" in datos:
        kw = datos["keywords"]
        kw = kw.split(",") if isinstance(kw, str) else kw or []
        fila["keywords"] = [str(k).strip().lower()[:60] for k in kw if str(k).strip()][:30]
    if "filter_questions" in datos:
        preguntas = []
        for p in datos["filter_questions"] or []:
            p = {"es": p, "en": ""} if isinstance(p, str) else p
            es, en = str(p.get("es") or "").strip()[:300], str(p.get("en") or "").strip()[:300]
            if es or en:
                preguntas.append({"es": es or en, "en": en or es})
        fila["filter_questions"] = preguntas[:8]
    if "specs_json" in datos:
        specs = datos["specs_json"] or {}
        if not isinstance(specs, dict) or not all(isinstance(v, dict) for v in specs.values()):
            return None, 'specs_json debe ser {"es": {...}, "en": {...}}'
        fila["specs_json"] = {k: {str(a)[:80]: str(b)[:200] for a, b in v.items()} for k, v in specs.items() if k in ("es", "en")}
    if nuevo:
        if not fila.get("name_es"):
            return None, "name_es es obligatorio"
        if fila.get("list_price") is None:
            return None, "list_price es obligatorio"
    if fila.get("cash_price") and fila.get("list_price") and fila["cash_price"] > fila["list_price"]:
        return None, "el precio contado no puede ser mayor que el de lista"
    if fila.get("min_down_payment_pct") and fila.get("recommended_down_payment_pct") and \
            fila["min_down_payment_pct"] > fila["recommended_down_payment_pct"]:
        return None, "la inicial mínima no puede ser mayor que la recomendada"
    return fila, None


def _item(item_id):
    if not re.fullmatch(r"[0-9a-fA-F-]{36}", item_id or ""):
        return None
    r = supabase.table("catalog_items").select("id").eq("tenant_id", tenant.tid()).eq("id", item_id).limit(1).execute()
    return (r.data or [None])[0]


@bp.route("/api/hub/catalogo")
@requiere_sesion()
def listar():
    if not supabase:
        return jsonify([])
    items = supabase.table("catalog_items").select("*").eq("tenant_id", tenant.tid()).order("sort_order").execute().data or []
    media = supabase.table("catalog_media").select("*").eq("tenant_id", tenant.tid()).order("sort_order").execute().data or []
    for it in items:
        it["media"] = [m for m in media if m["catalog_item_id"] == it["id"]]
    return jsonify(items)


@bp.route("/api/hub/catalogo", methods=["POST"])
@requiere_sesion(rol="admin")
def crear():
    fila, error = validar(request.get_json(silent=True) or {}, nuevo=True)
    if error:
        return _error(error)
    fila["tenant_id"] = tenant.tid()
    nuevo = (supabase.table("catalog_items").insert(fila).execute().data or [{}])[0]
    catalogo.limpiar_cache()
    return jsonify(nuevo), 201


@bp.route("/api/hub/catalogo/<item_id>", methods=["PUT", "PATCH"])
@requiere_sesion(rol="admin")
def editar(item_id):
    if not _item(item_id):
        return _error("producto no encontrado", 404)
    fila, error = validar(request.get_json(silent=True) or {}, nuevo=False)
    if error:
        return _error(error)
    if not fila:
        return _error("nada que guardar")
    fila["updated_at"] = datetime.now(timezone.utc).isoformat()
    r = supabase.table("catalog_items").update(fila).eq("tenant_id", tenant.tid()).eq("id", item_id).execute()
    catalogo.limpiar_cache()
    return jsonify((r.data or [{}])[0])


@bp.route("/api/hub/catalogo/<item_id>", methods=["DELETE"])
@requiere_sesion(rol="admin")
def borrar(item_id):
    if not _item(item_id):
        return _error("producto no encontrado", 404)
    media = supabase.table("catalog_media").select("file_url").eq("tenant_id", tenant.tid()).eq("catalog_item_id", item_id).execute().data or []
    _borrar_archivos([m["file_url"] for m in media])
    supabase.table("catalog_items").delete().eq("tenant_id", tenant.tid()).eq("id", item_id).execute()
    catalogo.limpiar_cache()
    return jsonify({"ok": True})


def _ruta_en_bucket(url):
    marca = f"/object/public/{BUCKET}/"
    return url.split(marca, 1)[1] if marca in (url or "") else None


def _borrar_archivos(urls):
    rutas = [r for r in (_ruta_en_bucket(u) for u in urls) if r and r.startswith(f"{tenant.tid()}/")]
    if rutas:
        try:
            supabase.storage.from_(BUCKET).remove(rutas)
        except Exception as e:
            print("Catálogo: no se pudieron borrar archivos:", e)


@bp.route("/api/hub/catalogo/<item_id>/media", methods=["POST"])
@requiere_sesion(rol="admin")
def subir_media(item_id):
    if not _item(item_id):
        return _error("producto no encontrado", 404)
    archivo = request.files.get("file")
    rol = request.form.get("role") or request.form.get("trigger_moment")
    if rol not in ROLES:
        return _error(f"role debe ser uno de {', '.join(ROLES)}")
    if not archivo or not archivo.filename:
        return _error("falta el archivo (campo 'file')")
    tipo = TIPOS.get((archivo.mimetype or "").lower())
    if not tipo:
        return _error("formato no permitido: JPG, PNG, WEBP, PDF, MP4 o MOV")
    contenido = archivo.read(MAX_SUBIDA_MB * 1024 * 1024 + 1)
    if len(contenido) > MAX_SUBIDA_MB * 1024 * 1024:
        return _error(f"el archivo supera {MAX_SUBIDA_MB} MB", 413)
    if not _firma_valida(contenido, tipo[1]):
        return _error("el contenido no coincide con el tipo de archivo")
    ruta = f"{tenant.tid()}/{item_id}/{rol.lower()}-{uuid.uuid4().hex[:12]}.{tipo[1]}"
    supabase.storage.from_(BUCKET).upload(ruta, contenido, {"content-type": archivo.mimetype, "upsert": "false"})
    url = supabase.storage.from_(BUCKET).get_public_url(ruta)
    fila = {"catalog_item_id": item_id, "tenant_id": tenant.tid(), "file_url": url, "media_type": tipo[0], "trigger_moment": rol,
            "caption_es": (request.form.get("caption_es") or "")[:500] or None,
            "caption_en": (request.form.get("caption_en") or "")[:500] or None,
            "sort_order": int(request.form.get("sort_order") or 0) if (request.form.get("sort_order") or "0").lstrip("-").isdigit() else 0}
    nuevo = (supabase.table("catalog_media").insert(fila).execute().data or [fila])[0]
    catalogo.limpiar_cache()
    return jsonify(nuevo), 201


def _firma_valida(b, ext):
    """Revisa los primeros bytes: evita subir un HTML/ejecutable con extensión de imagen al bucket público."""
    if ext == "jpg":
        return b[:3] == b"\xff\xd8\xff"
    if ext == "png":
        return b[:8] == b"\x89PNG\r\n\x1a\n"
    if ext == "webp":
        return b[:4] == b"RIFF" and b[8:12] == b"WEBP"
    if ext == "pdf":
        return b[:5] == b"%PDF-"
    if ext in ("mp4", "mov"):
        return b[4:8] in (b"ftyp", b"moov", b"wide", b"mdat", b"free")
    return False


@bp.route("/api/hub/catalogo/<item_id>/media/<media_id>", methods=["DELETE"])
@requiere_sesion(rol="admin")
def borrar_media(item_id, media_id):
    if not _item(item_id):
        return _error("producto no encontrado", 404)
    r = supabase.table("catalog_media").select("id,file_url").eq("tenant_id", tenant.tid()).eq("catalog_item_id", item_id) \
        .eq("id", media_id).limit(1).execute()
    fila = (r.data or [None])[0]
    if not fila:
        return _error("archivo no encontrado", 404)
    _borrar_archivos([fila["file_url"]])
    supabase.table("catalog_media").delete().eq("tenant_id", tenant.tid()).eq("id", media_id).execute()
    catalogo.limpiar_cache()
    return jsonify({"ok": True})


@bp.route("/api/hub/catalogo/sincronizar", methods=["POST"])
@requiere_sesion(rol="admin")
def sincronizar_crm():
    if (tenant.actual().get("crm_type") or "peruptd_native") == "peruptd_native":
        return _error("este cliente usa PeruPTD Native CRM: el catálogo se edita aquí mismo", 409)
    return jsonify(sincronizar())
