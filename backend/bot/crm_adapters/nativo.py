"""PeruPTD Native CRM: el CRM es la propia base de Supabase (tablas leads, catalog_items, catalog_media) que muestra el
portal web PeruPTD AI Sales Hub. El catálogo ya vive ahí (no hay nada que sincronizar) y la ficha del lead se escribe en
las columnas de la tabla leads (las escribe bot/crm.py para todos los tenants)."""
from bot.crm_adapters.base import AdaptadorCRM


class PeruPTDNativeCRMAdapter(AdaptadorCRM):
    nombre = "peruptd_native"

    def sincronizar_lead(self, ficha):
        return ficha.get("sender_id")          # el Id del lead es el propio registro de Supabase

    def registrar_cita(self, crm_id, inicio, minutos, asunto, descripcion="", ubicacion="", cita_id=None):
        return cita_id or f"cita:{crm_id}:{inicio.isoformat()}"   # appointment_datetime ya queda en la fila del lead

    def marcar_asistencia(self, cita_id, asistio, nota=""):
        return cita_id

    def registrar_nota(self, crm_id, asunto, cuerpo):
        return crm_id                           # el historial completo ya está en la tabla mensajes
