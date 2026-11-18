"""Sesiones del PeruPTD Native CRM (/app).
- Usuarios en hub_users (migración 005), contraseña con hash de werkzeug (scrypt). Nunca se guarda ni registra en claro.
- La sesión es una cookie HttpOnly firmada (itsdangerous) con {uid, tenant_id, rol}, válida HUB_SESION_HORAS.
- Cambios de estado (POST/PUT/PATCH/DELETE) con cookie exigen la cabecera X-PTD-CSRF: un sitio ajeno no puede enviarla
  sin pasar por CORS, así que no puede operar el CRM con la sesión del usuario.
- Acceso de máquina (scripts, automatizaciones): cabecera X-Hub-Key = HUB_API_KEY + X-Tenant-Id.
- Toda ruta protegida fija el tenant de la petición (bot.tenant.fijar): catálogo, playbook, leads y mensajes quedan
  filtrados por ese cliente."""
import hmac
import threading
import time
from datetime import datetime, timezone
from functools import wraps

from flask import g, jsonify, request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.security import check_password_hash, generate_password_hash

from bot import db, tenant
from bot.config import HUB_API_KEY, HUB_SESION_HORAS, HUB_SESSION_SECRET

COOKIE = "ptd_session"
_INTENTOS = {}                 # clave -> [timestamps] (límite de intentos de login)
_LOCK = threading.Lock()
MAX_INTENTOS, VENTANA_SEG = 5, 15 * 60


def _serializador():
    if not HUB_SESSION_SECRET or len(HUB_SESSION_SECRET) < 32:
        raise RuntimeError("HUB_SESSION_SECRET falta o es corto (mínimo 32 caracteres)")
    return URLSafeTimedSerializer(HUB_SESSION_SECRET, salt="ptd-hub-sesion")


def hash_password(clave):
    return generate_password_hash(clave)


def _bloqueado(clave):
    ahora = time.time()
    with _LOCK:
        recientes = [t for t in _INTENTOS.get(clave, []) if ahora - t < VENTANA_SEG]
        _INTENTOS[clave] = recientes
        return len(recientes) >= MAX_INTENTOS


def _fallo(clave):
    with _LOCK:
        _INTENTOS.setdefault(clave, []).append(time.time())


def autenticar(email, password, ip=""):
    """Devuelve (usuario, error). Mismo mensaje si el correo no existe o la clave es incorrecta."""
    email = (email or "").strip().lower()
    claves = (f"e:{email}", f"i:{ip}")
    if any(_bloqueado(c) for c in claves):
        return None, "demasiados intentos, espera 15 minutos"
    if not db.supabase or not email or not password:
        return None, "correo o contraseña incorrectos"
    fila = (db.supabase.table("hub_users").select("*").eq("email", email).limit(1).execute().data or [None])[0]
    # se compara siempre contra un hash para no revelar por el tiempo de respuesta si el correo existe
    ok = check_password_hash(fila["password_hash"] if fila else hash_password("x" * 12), password)
    if not fila or not ok or not fila.get("activo", True):
        for c in claves:
            _fallo(c)
        return None, "correo o contraseña incorrectos"
    try:
        db.supabase.table("hub_users").update({"last_login": datetime.now(timezone.utc).isoformat()}).eq("id", fila["id"]).execute()
    except Exception:
        pass
    return {"uid": fila["id"], "tenant_id": fila["tenant_id"], "rol": fila.get("rol") or "asesor",
            "email": fila["email"], "nombre": fila.get("nombre") or fila["email"]}, None


def crear_token(usuario):
    return _serializador().dumps({k: usuario[k] for k in ("uid", "tenant_id", "rol", "email", "nombre")})


def leer_token(token):
    try:
        return _serializador().loads(token, max_age=HUB_SESION_HORAS * 3600)
    except (BadSignature, SignatureExpired, RuntimeError):
        return None


def _usuario_de_la_peticion():
    clave = request.headers.get("X-Hub-Key", "")
    if clave and HUB_API_KEY and hmac.compare_digest(clave, HUB_API_KEY):
        t = request.headers.get("X-Tenant-Id", "").strip()
        return ({"uid": "api", "tenant_id": t, "rol": "admin", "email": "api", "nombre": "API"}, False) if t else (None, False)
    datos = leer_token(request.cookies.get(COOKIE, ""))
    return (datos, True) if datos else (None, False)


def requiere_sesion(rol=None):
    """Decorador para rutas del CRM. rol='admin' limita a administradores del cliente."""
    def deco(fn):
        @wraps(fn)
        def envoltura(*a, **k):
            usuario, por_cookie = _usuario_de_la_peticion()
            if not usuario:
                return jsonify({"error": "sesión requerida"}), 401
            if por_cookie and request.method not in ("GET", "HEAD", "OPTIONS") and request.headers.get("X-PTD-CSRF") != "1":
                return jsonify({"error": "falta la cabecera X-PTD-CSRF"}), 403
            if rol == "admin" and usuario.get("rol") != "admin":
                return jsonify({"error": "solo un administrador puede hacer esto"}), 403
            g.usuario = usuario
            with tenant.usar(usuario["tenant_id"]):      # se restaura al terminar: un hilo reutilizado no hereda el tenant
                return fn(*a, **k)
        return envoltura
    return deco
