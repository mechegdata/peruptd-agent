"""POST /catalogo/sincronizar: copia el catálogo del CRM del cliente a Supabase (productos, precios y archivos).
Protegido con la misma clave del cron. Lo llama Cloud Scheduler (p. ej. cada hora) o un webhook del CRM."""
from flask import Blueprint, jsonify, request

from bot.catalogo.sincronizar import sincronizar
from bot.config import CRON_KEY, VERIFY_TOKEN

bp = Blueprint("catalogo", __name__)


@bp.route("/catalogo/sincronizar", methods=["POST"])
def sincronizar_catalogo():
    if (CRON_KEY or VERIFY_TOKEN) not in {request.args.get("key"), request.headers.get("X-Cron-Key")}:
        return "No autorizado", 403
    return jsonify(sincronizar()), 200
