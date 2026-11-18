"""Catálogo dinámico (catalog_items + catalog_media en Supabase). Lo alimenta el CRM del cliente (sincronizar.py) o el
portal web; el agente lo lee aquí con caché de 5 minutos."""
import time

from bot import db, tenant

_CACHE = {}   # tenant_id -> (ts, items)
CACHE_SEG = 300


def items(forzar=False, incluir_agotados=False):
    t = tenant.tid()
    clave = (t, incluir_agotados)
    ts, guardado = _CACHE.get(clave, (0, None))
    if not forzar and guardado is not None and time.time() - ts < CACHE_SEG:
        return guardado
    if not db.supabase:
        return guardado or []
    try:
        q = db.supabase.table("catalog_items").select("*").eq("tenant_id", t)
        if not incluir_agotados:
            q = q.neq("status", "sold_out")
        filas = q.order("sort_order").execute().data or []
        media = db.supabase.table("catalog_media").select("*").eq("tenant_id", t).order("sort_order").execute().data or []
    except Exception as e:
        print("No se pudo leer el catálogo (se usa la última copia):", e)
        return guardado or []
    por_item = {}
    for m in media:
        por_item.setdefault(str(m["catalog_item_id"]), []).append(m)
    for f in filas:
        f["media"] = por_item.get(str(f["id"]), [])
    _CACHE[clave] = (time.time(), filas)
    return filas


def limpiar_cache():
    _CACHE.clear()
