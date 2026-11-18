"""Empresa (tenant) de la petición actual.
- El bot (webhooks, cron) atiende al TENANT_ID de su despliegue.
- La web del CRM (/app) atiende a muchos clientes: cada petición fija su tenant con `usar(tenant_id)` según la sesión,
  y catálogo, playbook, leads y mensajes se filtran por ese tenant.
Sin la tabla tenants, o sin fila, se arma desde variables de entorno con pipeline_mode='sague_legacy' (SAGUE no cambia)."""
import contextvars
import os
import time
from contextlib import contextmanager

from bot import db
from bot.config import TENANT_ID

_ACTUAL = contextvars.ContextVar("tenant_actual", default=None)
_CACHE = {}
CACHE_SEG = 300


def tid():
    return _ACTUAL.get() or TENANT_ID


@contextmanager
def usar(tenant_id):
    marca = _ACTUAL.set(tenant_id)
    try:
        yield tenant_id
    finally:
        _ACTUAL.reset(marca)


def fijar(tenant_id):
    """Para la web: fija el tenant de esta petición (Flask corre cada petición en su propio contexto)."""
    _ACTUAL.set(tenant_id)


def _por_defecto(tenant_id):
    return {"id": tenant_id, "name": os.environ.get("TENANT_NOMBRE", "SAGUE Constructora"), "industry": "realestate",
            "default_language": "es", "crm_type": os.environ.get("CRM_TIPO", "peruptd_native"),
            "pipeline_mode": os.environ.get("PIPELINE_MODE", "sague_legacy"), "bot_name": os.environ.get("BOT_NOMBRE", "Ava"),
            "advisor_name": os.environ.get("ASESOR_NOMBRE", ""), "crm_credentials_json": {}, "crm_field_map": {},
            "crm_field_mapping_json": {}, "owner_whatsapp": os.environ.get("OWNER_WA", ""),
            "quiet_hours_start": "20:30", "quiet_hours_end": "08:30"}


def actual(tenant_id=None):
    tenant_id = tenant_id or tid()
    ts, datos = _CACHE.get(tenant_id, (0, None))
    if datos and time.time() - ts < CACHE_SEG:
        return datos
    datos = _por_defecto(tenant_id)
    if db.supabase:
        try:
            fila = (db.supabase.table("tenants").select("*").eq("id", tenant_id).limit(1).execute().data or [None])[0]
            if fila:
                datos.update({k: v for k, v in fila.items() if v is not None})
        except Exception:
            pass  # migración 003 pendiente: valores por defecto
    _CACHE[tenant_id] = (time.time(), datos)
    return datos


def modo_catalogo():
    return actual().get("pipeline_mode") == "catalogo"


def limpiar_cache(tenant_id=None):
    if tenant_id:
        _CACHE.pop(tenant_id, None)
    else:
        _CACHE.clear()
