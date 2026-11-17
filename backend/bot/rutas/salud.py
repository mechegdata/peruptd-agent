"""Health check."""
from flask import Blueprint


bp = Blueprint("salud", __name__)


@bp.route("/", methods=["GET"])
def home():
    return "SAGUE Constructora Agente Omnicanal Activo!", 200
