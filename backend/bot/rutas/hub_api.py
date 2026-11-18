"""API del AI Sales Hub en modo en vivo (lo que el Hub lee y escribe cuando tiene un backend configurado).
  GET  /hub                                -> el Hub servido por el propio backend (mismo dominio: sin CORS)
  GET  /api/hub/estado                     -> tenant, CRM, idioma, nº de productos
  GET  /api/hub/catalogo                   -> catalog_items + catalog_media
  PATCH /api/hub/catalogo/<id>             -> edita precios / bono / argumento de valor (campos permitidos)
  POST /api/hub/catalogo/sincronizar       -> trae el catálogo desde el CRM del cliente
  GET  /api/hub/leads                      -> embudo (Kanban) con la ficha viva de cada lead
  POST /api/hub/leads/<sender_id>/accion   -> vino | no vino | pausa | activar | vendido | estado
  POST /api/hub/chat                       -> un turno del agente real con un cliente simulado ('hub:+1999…'):
                                              nada sale por WhatsApp/SMS y la cita no va al calendario real.
Todo /api/hub exige la cabecera X-Hub-Key = HUB_API_KEY. Sin HUB_API_KEY configurada, la API responde 403."""
import hmac
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from flask import Blueprint, jsonify, request, send_file

from bot import catalogo, tenant
from bot.agente import atender_turno
from bot.asesor import procesar_comando_asesor
from bot.canales import hub_bandeja
from bot.catalogo.sincronizar import sincronizar
from bot.config import HUB_API_KEY, HUB_CORS_ORIGINS
from bot.crm import etapa_comercial, sincronizar_seguro, telefono_visible
from bot.datos.leads import get_lead_by_sender_or_phone
from bot.db import supabase

bp = Blueprint("hub_api", __name__)
HUB_HTML = Path(__file__).resolve().parent.parent / "static" / "hub.html"
EDITABLES = {"list_price", "cash_price", "min_down_payment_pct", "recommended_down_payment_pct", "annual_rate_pct", "max_term_years",
             "promo_bonus_es", "promo_bonus_en", "value_comparison_es", "value_comparison_en", "status", "name_es", "name_en"}
ACCIONES = {"vino", "no vino", "pausa", "activar", "vendido", "estado"}


@bp.after_request
def _cors(resp):
    origen = request.headers.get("Origin")
    if origen and origen in HUB_CORS_ORIGINS and request.path.startswith("/api/hub"):
        resp.headers.update({"Access-Control-Allow-Origin": origen, "Vary": "Origin",
                             "Access-Control-Allow-Headers": "Content-Type, X-Hub-Key", "Access-Control-Allow-Methods": "GET, POST, PATCH, OPTIONS"})
    return resp


@bp.before_request
def _auth():
    if not request.path.startswith("/api/hub") or request.method == "OPTIONS":
        return None
    if not HUB_API_KEY or not hmac.compare_digest(request.headers.get("X-Hub-Key", ""), HUB_API_KEY):
        return jsonify({"error": "unauthorized"}), 403
    return None


@bp.route("/api/hub/<path:_resto>", methods=["OPTIONS"])
def _preflight(_resto):
    return "", 204


@bp.route("/hub")
def hub():
    if not HUB_HTML.exists():
        return "Hub no compilado: corre python hub/build.py", 404
    return send_file(HUB_HTML, mimetype="text/html")


@bp.route("/api/hub/estado")
def estado():
    t = tenant.actual()
    return jsonify({"tenant": t.get("id"), "name": t.get("name"), "industry": t.get("industry"), "crm_type": t.get("crm_type"),
                    "pipeline_mode": t.get("pipeline_mode"), "default_language": t.get("default_language"),
                    "bot_name": t.get("bot_name"), "advisor_name": t.get("advisor_name"), "address": t.get("address"),
                    "catalog_items": len(catalogo.items())})


@bp.route("/api/hub/catalogo")
def leer_catalogo():
    return jsonify(catalogo.items(forzar=True))


@bp.route("/api/hub/catalogo/<item_id>", methods=["PATCH"])
def editar_catalogo(item_id):
    cambios = {k: v for k, v in (request.get_json(silent=True) or {}).items() if k in EDITABLES}
    if not cambios or not supabase:
        return jsonify({"error": "nada que guardar"}), 400
    cambios["updated_at"] = datetime.now(timezone.utc).isoformat()
    fila = supabase.table("catalog_items").update(cambios).eq("id", item_id).eq("tenant_id", tenant.actual().get("id")).execute().data
    catalogo.limpiar_cache()
    return (jsonify(fila[0]), 200) if fila else (jsonify({"error": "no existe"}), 404)


@bp.route("/api/hub/catalogo/sincronizar", methods=["POST"])
def sincronizar_catalogo():
    return jsonify(sincronizar())


def _ficha_kanban(lead):
    meta = json.loads(lead.get("interes") or "{}")
    dia = None
    if meta.get("visita_estado") == "realizada" and meta.get("fecha_cita"):
        try:
            dia = (datetime.now(timezone.utc) - datetime.fromisoformat(meta["fecha_cita"])).days
        except ValueError:
            pass
    return {"sender_id": lead.get("sender_id"), "nombre": lead.get("nombre") or telefono_visible(lead.get("sender_id")),
            "stage": etapa_comercial(meta), "lang": meta.get("preferred_language") or "es",
            "channel": meta.get("canal_origen") or lead.get("canal"), "pay": meta.get("payment_method"),
            "budget": meta.get("stated_budget") or meta.get("presupuesto_tope"),
            "obj": int(meta.get("price_objection_count") or meta.get("objecion_precio_n") or 0), "day": dia,
            "appointment": meta.get("fecha_cita") if meta.get("cita_agendada") else None,
            "followup": (meta.get("post_visita") or {}).get("enviados") or [], "noshow": meta.get("visita_estado") == "no_asistio",
            "paused": bool(meta.get("seguimiento_pausado")), "updated_at": lead.get("updated_at")}


@bp.route("/api/hub/leads")
def leads():
    if not supabase:
        return jsonify([])
    filas = supabase.table("leads").select("*").order("updated_at", desc=True).limit(min(int(request.args.get("limit", 60)), 200)).execute().data or []
    return jsonify([_ficha_kanban(f) for f in filas])


@bp.route("/api/hub/leads/<sender_id>/accion", methods=["POST"])
def accion(sender_id):
    nombre = str((request.get_json(silent=True) or {}).get("accion") or "").lower().strip()
    if nombre not in ACCIONES:
        return jsonify({"error": f"acción no válida: {nombre}"}), 400
    digitos = re.sub(r"\D", "", telefono_visible(sender_id))
    resp = procesar_comando_asesor(f"{nombre} {digitos}")
    sincronizar_seguro(sender_id)
    return jsonify({"ok": bool(resp) and not str(resp).startswith("No encontré"), "resultado": resp})


@bp.route("/api/hub/chat", methods=["POST"])
def chat():
    datos = request.get_json(silent=True) or {}
    sender = str(datos.get("sender_id") or "")
    texto = str(datos.get("texto") or "").strip()
    if not hub_bandeja.es_simulado(sender) or not texto:
        return jsonify({"error": "sender_id debe empezar con 'hub:' y texto no puede ir vacío"}), 400
    if not tenant.modo_catalogo():
        return jsonify({"error": "el tenant está en modo sague_legacy: el chat del Hub usa el motor de catálogo"}), 409
    hub_bandeja.vaciar(sender)
    res = atender_turno(sender, texto, datos.get("perfil") or "", datos.get("canal_origen") or "Hub")
    sincronizar_seguro(sender)
    salida = hub_bandeja.vaciar(sender)
    media_ids = {str(m.get("file_url")): m for m in res.media}
    lead = get_lead_by_sender_or_phone(sender, sender) or {}
    return jsonify({
        "reply": "\n\n".join(s["contenido"] for s in salida if s["tipo"] == "texto"),
        "media": [{**{k: v for k, v in media_ids.get(s["contenido"], {}).items() if k != "descargar"}, "file_url": s["contenido"]}
                  for s in salida if s["tipo"] == "media"],
        "alertas": [s["contenido"] for s in salida if s["tipo"] == "alerta"],
        "nlu": res.nlu.model_dump() if getattr(res, "nlu", None) else None,
        "traza": res.traza, "slots": [s.isoformat() for s in res.slots],
        "lead": _ficha_kanban(lead) if lead else None,
    })
