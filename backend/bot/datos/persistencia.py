"""¿Están disponibles las tablas persistentes de OmniAgent (migración 002)? Si fallan, el bot vuelve a la memoria del
proceso por unos minutos (comportamiento anterior) en vez de dejar de responder."""
import time

from bot import db
from bot.config import COLAS_PERSISTENTES

_APAGADO_HASTA = {"ts": 0.0}


def disponible():
    return COLAS_PERSISTENTES and db.supabase is not None and time.time() >= _APAGADO_HASTA["ts"]


def cliente():
    return db.supabase


def es_duplicado(error):
    """Choque de PRIMARY KEY / UNIQUE en Postgres (código 23505): ese id ya estaba registrado."""
    texto = f"{getattr(error, 'code', '')} {error}".lower()
    return "23505" in texto or "duplicate key" in texto


def desactivar(error, minutos=10):
    _APAGADO_HASTA["ts"] = time.time() + minutos * 60
    print(f"⚠️ COLAS PERSISTENTES DESACTIVADAS {minutos} min (se usa la memoria del proceso). "
          f"¿Corriste docs/migraciones/002_omniagent.sql? Error: {str(error)[:200]}")
