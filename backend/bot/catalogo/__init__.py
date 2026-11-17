"""Catálogo dinámico (catalog_items + catalog_media en Supabase). Lo alimenta el CRM del cliente (sincronizar.py) o el
portal web; el agente lo lee aquí con caché de 5 minutos."""
import time

from bot import db
from bot.config import TENANT_ID

_CACHE = {"ts": 0.0, "items": None}
CACHE_SEG = 300


def items(forzar=False):
    if not forzar and _CACHE["items"] is not None and time.time() - _CACHE["ts"] < CACHE_SEG:
        return _CACHE["items"]
    if not db.supabase:
        return _CACHE["items"] or []
    try:
        filas = db.supabase.table("catalog_items").select("*").eq("tenant_id", TENANT_ID).neq("status", "sold_out") \
            .order("sort_order").execute().data or []
        media = db.supabase.table("catalog_media").select("*").eq("tenant_id", TENANT_ID).order("sort_order").execute().data or []
    except Exception as e:
        print("No se pudo leer el catálogo (se usa la última copia):", e)
        return _CACHE["items"] or []
    por_item = {}
    for m in media:
        por_item.setdefault(str(m["catalog_item_id"]), []).append(m)
    for f in filas:
        f["media"] = por_item.get(str(f["id"]), [])
    _CACHE.update(ts=time.time(), items=filas)
    return filas


def limpiar_cache():
    _CACHE.update(ts=0.0, items=None)
