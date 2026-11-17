"""Interfaz común de los adaptadores de CRM. Cada adaptador hace dos cosas:
  1. Catálogo (CRM -> Supabase): listar_productos() devuelve items normalizados (mismas claves que catalog_items, más
     'media': [{file_url|descargar, media_type, trigger_moment, caption_es/en}]); bot/catalogo/sincronizar.py los guarda.
  2. Lead y citas (bot -> CRM): sincronizar_lead(), registrar_cita(), marcar_asistencia(), registrar_nota().
Todos los métodos devuelven None ante un error (y lo registran): el CRM nunca detiene la conversación."""
import os
import re
import time

import requests

TRIGGERS = ("FIRST_INFO", "SPECS_PDF", "OPTION_RENDER", "PRICE_OBJECTION", "LOCATION_FACADE", "POST_VISIT_45M", "RESCUE_24H", "VIDEO_TOUR")


def tipo_por_nombre(nombre, mime=""):
    n = (nombre or "").lower()
    if n.endswith(".pdf") or "pdf" in mime:
        return "pdf"
    if re.search(r"\.(mp4|mov|m4v|webm)$", n) or mime.startswith("video"):
        return "video"
    return "image"


def trigger_por_nombre(nombre, tipo):
    """Convención para el cliente: el archivo se llama '[PRICE_OBJECTION] Cochera.jpg'. Sin etiqueta, se deduce del tipo."""
    m = re.search(r"\[(\w+)\]", nombre or "")
    if m and m.group(1).upper() in TRIGGERS:
        return m.group(1).upper()
    return {"pdf": "SPECS_PDF", "video": "VIDEO_TOUR"}.get(tipo, "FIRST_INFO")


def leyenda(nombre):
    return re.sub(r"\[\w+\]\s*", "", re.sub(r"\.\w{2,4}$", "", nombre or "")).strip()


def solo_digitos(tel):
    return re.sub(r"\D", "", re.sub(r"^(sms|twa):", "", str(tel or "")))


class AdaptadorCRM:
    nombre = "base"

    def __init__(self, credenciales=None, campos=None, http=None):
        self.cred = credenciales or {}
        self.campos = campos or {}          # mapeo de campos propios (playbook: crm.field_map)
        self.http = http or requests.Session()
        self._token = {"valor": None, "ts": 0.0}

    # ---- utilidades ----
    def secreto(self, clave, defecto=""):
        """tenants.crm_credentials_json guarda referencias, no claves: {"api_token_env": "HUBSPOT_TOKEN_ACME"}.
        Se acepta el valor directo solo para pruebas locales."""
        ref = self.cred.get(f"{clave}_env")
        return (os.environ.get(ref, "") if ref else self.cred.get(clave)) or defecto

    def _ok(self, r, que):
        if r is None or r.status_code >= 300:
            print(f"{self.nombre}: falló {que}: HTTP {getattr(r, 'status_code', '?')} {getattr(r, 'text', '')[:250]}")
            return False
        return True

    def _seguro(self, fn, *a, **k):
        try:
            return fn(*a, **k)
        except Exception as e:
            print(f"{self.nombre}: error en {getattr(fn, '__name__', 'llamada')}:", str(e)[:250])
            return None

    def token_vigente(self, segundos=3000):
        return self._token["valor"] if self._token["valor"] and time.time() - self._token["ts"] < segundos else None

    # ---- catálogo ----
    def listar_productos(self):
        return []

    # ---- lead y citas ----
    def sincronizar_lead(self, ficha):
        """ficha: dict con nombre, telefono, email, etapa, etapa_crm, pago, presupuesto, objeciones, idioma, canal,
        producto, producto_crm_id, descripcion, crm_id (si ya existe). Devuelve el Id del registro en el CRM."""
        return None

    def registrar_cita(self, crm_id, inicio, minutos, asunto, descripcion="", ubicacion="", cita_id=None):
        return None

    def marcar_asistencia(self, cita_id, asistio, nota=""):
        return None

    def registrar_nota(self, crm_id, asunto, cuerpo):
        return None
