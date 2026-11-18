"""Login del PeruPTD Native CRM: POST /api/hub/login, POST /api/hub/logout, GET /api/hub/me."""
from flask import Blueprint, g, jsonify, make_response, request

from bot import tenant
from bot.config import HUB_COOKIE_SEGURA, HUB_SESION_HORAS
from bot.hub import sesion

bp = Blueprint("hub_auth", __name__)


@bp.route("/api/hub/login", methods=["POST"])
def login():
    datos = request.get_json(silent=True) or {}
    usuario, error = sesion.autenticar(datos.get("email"), datos.get("password"), request.headers.get("X-Forwarded-For", request.remote_addr or ""))
    if not usuario:
        return jsonify({"error": error}), 401
    try:
        token = sesion.crear_token(usuario)
    except RuntimeError as e:
        print("Login: configuración incompleta:", e)
        return jsonify({"error": "el servidor no tiene configurada la sesión (HUB_SESSION_SECRET)"}), 500
    t = tenant.actual(usuario["tenant_id"])
    resp = make_response(jsonify({"usuario": {k: usuario[k] for k in ("email", "nombre", "rol", "tenant_id")}, "tenant": t.get("name")}))
    resp.set_cookie(sesion.COOKIE, token, max_age=HUB_SESION_HORAS * 3600, httponly=True, secure=HUB_COOKIE_SEGURA,
                    samesite="Lax", path="/")
    return resp


@bp.route("/api/hub/logout", methods=["POST"])
def logout():
    resp = make_response(jsonify({"ok": True}))
    resp.delete_cookie(sesion.COOKIE, path="/")
    return resp


@bp.route("/api/hub/me")
@sesion.requiere_sesion()
def me():
    u = g.usuario
    return jsonify({"usuario": {k: u.get(k) for k in ("email", "nombre", "rol", "tenant_id")}})
