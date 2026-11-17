"""Cliente de Supabase (None si faltan credenciales)."""
from supabase import create_client

from bot.config import SUPABASE_KEY, SUPABASE_URL


supabase = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None
