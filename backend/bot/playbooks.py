"""Playbook del cliente (tenant): datos del negocio, reglas, frases prohibidas, interruptores del protocolo y mapeo a
Salesforce. Fuente: tabla tenant_playbooks (si existe la fila del TENANT_ID) o el archivo playbooks/<PLAYBOOK_ARCHIVO>.
Se guarda en caché 5 minutos. Si no hay playbook, valor() devuelve el valor por defecto que pasa cada llamador,
así que el comportamiento de SAGUE no depende de que el playbook exista."""
import json
import time
from pathlib import Path

from bot import db, tenant
from bot.config import PLAYBOOK_ARCHIVO

CARPETA = Path(__file__).resolve().parent.parent / "playbooks"
_CACHE = {}   # tenant_id -> (ts, datos)
CACHE_SEG = 5 * 60


def de_archivo(nombre):
    """Lee un playbook de la carpeta playbooks/ (para pruebas y demos)."""
    return json.loads((CARPETA / nombre).read_text(encoding="utf-8"))


def _de_bd():
    if not db.supabase:
        return None
    try:
        r = db.supabase.table("tenant_playbooks").select("playbook").eq("tenant_id", tenant.tid()).limit(1).execute()
        fila = (r.data or [None])[0]
        pb = (fila or {}).get("playbook")
        return json.loads(pb) if isinstance(pb, str) else pb
    except Exception:
        return None  # la tabla aún no existe (migración 002 pendiente): se usa el archivo


def actual():
    """Playbook vigente del tenant (dict; vacío si no hay ninguno)."""
    ts, guardado = _CACHE.get(tenant.tid(), (0, None))
    if guardado is not None and time.time() - ts < CACHE_SEG:
        return guardado
    datos = _de_bd()
    if not datos:
        try:
            datos = de_archivo(PLAYBOOK_ARCHIVO)
        except Exception as e:
            print(f"Sin playbook ({PLAYBOOK_ARCHIVO}): {e}")
            datos = {}
    _CACHE[tenant.tid()] = (time.time(), datos)
    return datos


def valor(ruta, defecto=None, playbook=None):
    """valor('protocolo_post_visita.enable_72h_arras_bonus', True) -> lo que diga el playbook, o el defecto."""
    nodo = actual() if playbook is None else playbook
    for parte in ruta.split("."):
        if not isinstance(nodo, dict) or parte not in nodo:
            return defecto
        nodo = nodo[parte]
    return nodo


def interruptor(nombre, defecto=True):
    """Compromisos comerciales que se encienden o apagan sin tocar código (sección 'interruptores')."""
    return bool(valor(f"interruptores.{nombre}", defecto))


def limpiar_cache():
    _CACHE.clear()
