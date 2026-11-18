"""Cliente de Supabase (None si faltan credenciales).
Con MULTI_TENANT, cada petición lleva la cabecera x-tenant-id del despliegue: el esquema 000 la usa como valor por
defecto de tenant_id, así todo insert del bot queda marcado con su cliente sin tocar cada llamada."""
from supabase import create_client

from bot.config import MULTI_TENANT, SUPABASE_KEY, SUPABASE_URL, TENANT_ID


def _crear():
    if not (SUPABASE_URL and SUPABASE_KEY):
        return None
    if MULTI_TENANT:
        try:
            from supabase import ClientOptions
            return create_client(SUPABASE_URL, SUPABASE_KEY, options=ClientOptions(headers={"x-tenant-id": TENANT_ID}))
        except ImportError:
            pass
    return create_client(SUPABASE_URL, SUPABASE_KEY)


supabase = _crear()
