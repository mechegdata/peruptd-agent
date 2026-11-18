"""Crea (o reactiva) un usuario del PeruPTD Native CRM (/app). La contraseña se pide por consola y se guarda con hash.
Uso:  python scripts/crear_usuario.py --tenant demo-dental --email ana@clinica.com --nombre "Ana" --rol admin"""
import argparse
import getpass
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from bot.db import supabase  # noqa: E402
from bot.hub.sesion import hash_password  # noqa: E402


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--tenant", required=True)
    p.add_argument("--email", required=True)
    p.add_argument("--nombre", default="")
    p.add_argument("--rol", choices=("admin", "asesor"), default="asesor")
    a = p.parse_args()
    if not supabase:
        sys.exit("Falta SUPABASE_URL / SUPABASE_KEY en el entorno.")
    if not (supabase.table("tenants").select("id").eq("id", a.tenant).limit(1).execute().data):
        sys.exit(f"No existe el tenant '{a.tenant}' (migraciones 003/004).")
    clave = getpass.getpass("Contraseña (mín. 10 caracteres): ")
    if len(clave) < 10 or clave != getpass.getpass("Repite la contraseña: "):
        sys.exit("Las contraseñas no coinciden o son muy cortas.")
    supabase.table("hub_users").upsert({"tenant_id": a.tenant, "email": a.email.strip().lower(), "nombre": a.nombre or None,
                                        "rol": a.rol, "activo": True, "password_hash": hash_password(clave)},
                                       on_conflict="email").execute()
    print(f"Listo: {a.email} ({a.rol}) puede entrar a /app y verá solo los datos de '{a.tenant}'.")


if __name__ == "__main__":
    main()
