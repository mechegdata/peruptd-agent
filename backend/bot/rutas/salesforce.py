"""Salesforce -> bot. Un Flow (o Outbound Message) avisa cuando el asesor cambia la cita o escribe al cliente desde
Salesforce, y el bot reacciona igual que con los comandos de WhatsApp del asesor:
  POST /webhook/salesforce   cabecera X-OmniAgent-Key: <SF_WEBHOOK_SECRETO>
  {"telefono": "+1 512 555 0148", "accion": "vino" | "no vino" | "pausa" | "activar" | "vendido" | "estado" | "mensaje_manual",
   "texto": "(solo para mensaje_manual: lo que el asesor le escribió al cliente)"}
También acepta los valores de un picklist de asistencia: "Completed", "Attended", "No-Show", "No_Show"."""
import hmac
import re

from flask import Blueprint, jsonify, request

from bot.asesor import procesar_comando_asesor
from bot.config import SF_WEBHOOK_SECRETO
from bot.handoff import guardar_mensaje_manual

bp = Blueprint("salesforce", __name__)

_EQUIVALENCIAS = {"completed": "vino", "attended": "vino", "asistio": "vino", "no-show": "no vino", "no_show": "no vino",
                  "noshow": "no vino", "closed won": "vendido"}


@bp.route("/webhook/salesforce", methods=["POST"])
def desde_salesforce():
    if not SF_WEBHOOK_SECRETO or not hmac.compare_digest(request.headers.get("X-OmniAgent-Key", ""), SF_WEBHOOK_SECRETO):
        return "No autorizado", 403
    body = request.get_json(silent=True) or {}
    digitos = re.sub(r"\D", "", str(body.get("telefono") or ""))
    accion = str(body.get("accion") or "").strip().lower()
    accion = _EQUIVALENCIAS.get(accion, accion)
    if not digitos or not accion:
        return jsonify({"ok": False, "error": "faltan telefono o accion"}), 400
    if accion == "mensaje_manual":
        destino = str(body.get("sender_id") or digitos)
        guardar_mensaje_manual(destino, "salesforce", str(body.get("texto") or ""))  # pausa el bot 2 h con ese cliente
        return jsonify({"ok": True, "resultado": "bot en pausa para ese cliente"}), 200
    resp = procesar_comando_asesor(f"{accion} {digitos}")
    if resp is None:
        return jsonify({"ok": False, "error": f"acción no reconocida: {accion}"}), 400
    return jsonify({"ok": not resp.startswith("No encontré"), "resultado": resp}), 200
