"""Operación diaria del PeruPTD Native CRM (todo filtrado por el tenant de la sesión):
  GET  /app  (y /hub)                          -> la web (login + CRM); /app?demo=1 = demo para videos
  GET  /api/hub/estado                         -> datos del cliente
  GET  /api/hub/leads                          -> Kanban: Capturado · Calificado · Visita agendada · Seguimiento 14 días · Cierre/Alerta
  GET  /api/hub/leads/<sender_id>/mensajes     -> conversación con el motor que respondió cada mensaje
  POST /api/hub/leads/<sender_id>/comando      -> {"comando": "vino"|"no vino"|"pausa"|"activar"|"vendido"|"estado"}
                                                  o {"mensaje": "..."}: lo envía al cliente y pausa el bot 2 h
  POST /api/hub/chat                           -> turno del agente real con un cliente simulado 'hub:+1999…' (nada sale)
CORS solo para HUB_CORS_ORIGINS. Login, catálogo y playbook viven en hub_auth / hub_catalogo / hub_config."""
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from flask import Blueprint, jsonify, request, send_file

from bot import catalogo, tenant
from bot.agente import atender_turno
from bot.asesor import procesar_comando_asesor
from bot.canales import hub_bandeja
from bot.canales.whatsapp import send_wa_text
from bot.config import HUB_CORS_ORIGINS, PAUSA_BOT_TRAS_HUMANO_MIN
from bot.crm import etapa_comercial, sincronizar_seguro, telefono_visible
from bot.datos.leads import get_lead_by_sender_or_phone, tabla
from bot.db import supabase
from bot.handoff import guardar_mensaje_manual
from bot.hub.sesion import requiere_sesion

bp = Blueprint("hub_api", __name__)
HUB_HTML = Path(__file__).resolve().parent.parent / "static" / "hub.html"
COMANDOS = {"vino", "no vino", "pausa", "activar", "vendido", "estado"}
COLUMNA = {"new": "capturado", "qualified": "calificado", "booked": "visita_agendada", "no_show": "visita_agendada",
           "visited": "seguimiento_14d", "negotiation": "seguimiento_14d", "won": "cierre_alerta", "lost": "cierre_alerta"}


@bp.after_request
def _cors(resp):
    origen = request.headers.get("Origin")
    if origen and origen in HUB_CORS_ORIGINS and request.path.startswith("/api/hub"):
        resp.headers.update({"Access-Control-Allow-Origin": origen, "Access-Control-Allow-Credentials": "true", "Vary": "Origin",
                             "Access-Control-Allow-Headers": "Content-Type, X-Hub-Key, X-Tenant-Id, X-PTD-CSRF",
                             "Access-Control-Allow-Methods": "GET, POST, PUT, PATCH, DELETE, OPTIONS"})
    return resp


@bp.route("/api/hub/<path:_resto>", methods=["OPTIONS"])
def _preflight(_resto):
    return "", 204


@bp.route("/app")
@bp.route("/hub")
def web():
    if not HUB_HTML.exists():
        return "Hub no compilado: corre python hub/build.py", 404
    resp = send_file(HUB_HTML, mimetype="text/html")
    resp.headers.update({"X-Frame-Options": "DENY", "Referrer-Policy": "same-origin", "X-Content-Type-Options": "nosniff"})
    return resp


@bp.route("/api/hub/estado")
@requiere_sesion()
def estado():
    t = tenant.actual()
    return jsonify({"tenant": t.get("id"), "name": t.get("name"), "industry": t.get("industry"), "crm_type": t.get("crm_type"),
                    "pipeline_mode": t.get("pipeline_mode"), "default_language": t.get("default_language"),
                    "bot_name": t.get("bot_name"), "advisor_name": t.get("advisor_name"), "address": t.get("address"),
                    "catalog_items": len(catalogo.items())})


def ficha_kanban(lead):
    meta = json.loads(lead.get("interes") or "{}")
    etapa = etapa_comercial(meta)
    dia = None
    if meta.get("visita_estado") == "realizada" and meta.get("fecha_cita"):
        try:
            dia = (datetime.now(timezone.utc) - datetime.fromisoformat(meta["fecha_cita"])).days
        except ValueError:
            pass
    obj = int(meta.get("price_objection_count") or meta.get("objecion_precio_n") or 0)
    alerta = None
    if obj >= 3:
        alerta = "objecion_3"
    elif etapa == "negotiation" or (dia is not None and dia >= 10):
        alerta = "dia_10_llamar"
    elif meta.get("pregunta_owner_visita") and not meta.get("visita_estado"):
        alerta = "confirmar_asistencia"
    columna = "cierre_alerta" if alerta in ("objecion_3", "dia_10_llamar") else COLUMNA.get(etapa, "capturado")
    return {"sender_id": lead.get("sender_id"), "nombre": lead.get("nombre") or telefono_visible(lead.get("sender_id")),
            "telefono": telefono_visible(lead.get("telefono") or lead.get("sender_id")), "stage": etapa, "columna": columna,
            "alerta": alerta, "lang": meta.get("preferred_language") or "es", "channel": meta.get("canal_origen") or lead.get("canal"),
            "pay": meta.get("payment_method"), "budget": meta.get("stated_budget") or meta.get("presupuesto_tope"), "obj": obj, "day": dia,
            "appointment": meta.get("fecha_cita") if meta.get("cita_agendada") else None, "producto": meta.get("producto_nombre"),
            "followup": (meta.get("post_visita") or {}).get("enviados") or [], "noshow": meta.get("visita_estado") == "no_asistio",
            "paused": bool(meta.get("seguimiento_pausado")), "ultimo_mensaje": lead.get("ultimo_mensaje"), "updated_at": lead.get("updated_at")}


@bp.route("/api/hub/leads")
@requiere_sesion()
def leads():
    if not supabase:
        return jsonify([])
    limite = max(1, min(int(request.args.get("limit", 100)), 300))
    filas = tabla("leads").select("*").order("updated_at", desc=True).limit(limite).execute().data or []
    return jsonify([ficha_kanban(f) for f in filas])


def _lead_o_404(sender_id):
    lead = get_lead_by_sender_or_phone(sender_id)      # filtrado por tenant (MULTI_TENANT)
    return lead or None


@bp.route("/api/hub/leads/<path:sender_id>/mensajes")
@requiere_sesion()
def mensajes(sender_id):
    if not _lead_o_404(sender_id):
        return jsonify({"error": "lead no encontrado"}), 404
    filas = tabla("mensajes").select("rol,contenido,canal,motor,created_at").eq("sender_id", sender_id) \
        .order("created_at", desc=True).limit(150).execute().data or []
    salida = []
    for f in reversed(filas):
        canal = f.get("canal") or ""
        origen = "cliente" if f.get("rol") == "user" else "asesor" if canal.endswith("_manual") else \
            "seguimiento" if "seguimiento" in canal else "bot"
        salida.append({"origen": origen, "texto": f.get("contenido"), "motor": f.get("motor"), "canal": canal, "fecha": f.get("created_at")})
    return jsonify(salida)


@bp.route("/api/hub/leads/<path:sender_id>/comando", methods=["POST"])
@requiere_sesion()
def comando(sender_id):
    lead = _lead_o_404(sender_id)
    if not lead:
        return jsonify({"error": "lead no encontrado"}), 404
    datos = request.get_json(silent=True) or {}
    mensaje = str(datos.get("mensaje") or "").strip()
    if mensaje:
        if len(mensaje) > 1500:
            return jsonify({"error": "mensaje demasiado largo (máx. 1500)"}), 400
        if not send_wa_text(sender_id, mensaje):
            return jsonify({"error": "no se pudo enviar (¿pasaron las 24 h de WhatsApp?)"}), 502
        guardar_mensaje_manual(sender_id, "web", mensaje)      # historial + pausa automática del bot
        return jsonify({"ok": True, "pausa_min": PAUSA_BOT_TRAS_HUMANO_MIN})
    nombre = str(datos.get("comando") or "").lower().strip()
    if nombre not in COMANDOS:
        return jsonify({"error": f"comando no válido: {nombre}"}), 400
    resp = procesar_comando_asesor(f"{nombre} {re.sub(r'[^0-9]', '', telefono_visible(sender_id))}")
    sincronizar_seguro(sender_id)
    lead = _lead_o_404(sender_id) or lead
    return jsonify({"ok": bool(resp) and not str(resp).startswith("No encontré"), "resultado": resp, "lead": ficha_kanban(lead)})


@bp.route("/api/hub/chat", methods=["POST"])
@requiere_sesion()
def chat():
    datos = request.get_json(silent=True) or {}
    sender = str(datos.get("sender_id") or "")
    texto = str(datos.get("texto") or "").strip()[:2000]
    if not hub_bandeja.es_simulado(sender) or not texto:
        return jsonify({"error": "sender_id debe empezar con 'hub:' y texto no puede ir vacío"}), 400
    if not tenant.modo_catalogo():
        return jsonify({"error": "el tenant está en modo sague_legacy: el chat de prueba usa el motor de catálogo"}), 409
    hub_bandeja.vaciar(sender)
    res = atender_turno(sender, texto, datos.get("perfil") or "", datos.get("canal_origen") or "Hub")
    sincronizar_seguro(sender)
    salida = hub_bandeja.vaciar(sender)
    por_url = {str(m.get("file_url")): m for m in res.media}
    lead = get_lead_by_sender_or_phone(sender) or {}
    return jsonify({
        "reply": "\n\n".join(s["contenido"] for s in salida if s["tipo"] == "texto"),
        "media": [{**{k: v for k, v in por_url.get(s["contenido"], {}).items() if k != "descargar"}, "file_url": s["contenido"]}
                  for s in salida if s["tipo"] == "media"],
        "alertas": [s["contenido"] for s in salida if s["tipo"] == "alerta"],
        "nlu": res.nlu.model_dump() if getattr(res, "nlu", None) else None,
        "traza": res.traza, "slots": [s.isoformat() for s in res.slots],
        "lead": ficha_kanban(lead) if lead else None,
    })
