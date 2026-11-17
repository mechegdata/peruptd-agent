"""Empresa (tenant) dueña de este despliegue: fila de la tabla tenants (migración 003), con caché de 5 minutos.
Sin esa tabla o sin fila, se arma desde variables de entorno con pipeline_mode='sague_legacy', así el despliegue de SAGUE
sigue con su motor original sin cambiar nada."""
import os
import time

from bot import db
from bot.config import TENANT_ID

_CACHE = {"ts": 0.0, "datos": None}


def _por_defecto():
    return {"id": TENANT_ID, "name": os.environ.get("TENANT_NOMBRE", "SAGUE Constructora"), "industry": "realestate",
            "default_language": "es", "crm_type": os.environ.get("CRM_TIPO", "peruptd_native"),
            "pipeline_mode": os.environ.get("PIPELINE_MODE", "sague_legacy"), "bot_name": os.environ.get("BOT_NOMBRE", "Ava"),
            "advisor_name": os.environ.get("ASESOR_NOMBRE", ""), "crm_credentials_json": {}, "crm_field_map": {}}


def actual():
    if _CACHE["datos"] and time.time() - _CACHE["ts"] < 300:
        return _CACHE["datos"]
    datos = _por_defecto()
    if db.supabase:
        try:
            fila = (db.supabase.table("tenants").select("*").eq("id", TENANT_ID).limit(1).execute().data or [None])[0]
            if fila:
                datos.update({k: v for k, v in fila.items() if v is not None})
        except Exception:
            pass  # migración 003 pendiente: valores por defecto
    _CACHE.update(ts=time.time(), datos=datos)
    return datos


def modo_catalogo():
    return actual().get("pipeline_mode") == "catalogo"


def limpiar_cache():
    _CACHE.update(ts=0.0, datos=None)
