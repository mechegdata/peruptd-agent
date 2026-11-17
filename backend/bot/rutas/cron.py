"""Endpoint protegido que ejecuta los seguimientos (y termina lo que un reinicio dejó a medias)."""
import time

from flask import Blueprint, jsonify, request

from bot.atencion import responder_lote_pendiente
from bot.config import CRON_KEY, VERIFY_TOKEN
from bot.datos import colas
from bot.leadgen import ejecutar_leadads_vencidos
from bot.seguimiento.motor import ejecutar_seguimientos


bp = Blueprint("cron", __name__)
_ULTIMA_LIMPIEZA = {"ts": 0.0}


def procesar_pendientes():
    """Mensajes agrupados y saludos de Lead Ads que quedaron en las colas persistentes porque el contenedor se reinició.
    Son respuestas a algo que el cliente hizo, así que se envían aunque sea horario silencioso."""
    res = {"lotes": 0, "lead_ads": 0}
    try:
        for sender, texto, perfil, _canal in colas.lotes_vencidos():
            responder_lote_pendiente(sender, texto, perfil)
            res["lotes"] += 1
        res["lead_ads"] = ejecutar_leadads_vencidos()
        if time.time() - _ULTIMA_LIMPIEZA["ts"] > 6 * 3600:
            _ULTIMA_LIMPIEZA["ts"] = time.time()
            colas.limpiar_antiguos()
    except Exception as e:
        print("Error procesando pendientes de las colas:", e)
        res["error"] = str(e)[:200]
    return res


@bp.route("/cron/seguimiento", methods=["GET", "POST"])
@bp.route("/cron", methods=["GET", "POST"])
@bp.route("/reloj", methods=["GET", "POST"])
def cron_seguimiento():
    claves = {request.args.get("key"), request.headers.get("X-Cron-Key")}
    es_scheduler = "Google-Cloud-Scheduler" in (request.headers.get("User-Agent") or "")
    if (CRON_KEY or VERIFY_TOKEN) not in claves and not (es_scheduler and not CRON_KEY):
        return "No autorizado", 403
    pendientes = procesar_pendientes()
    resultado = ejecutar_seguimientos()
    if pendientes.get("lotes") or pendientes.get("lead_ads") or pendientes.get("error"):
        resultado["pendientes"] = pendientes
    return jsonify(resultado), 200
