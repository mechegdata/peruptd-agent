"""Ajustes del cliente desde el CRM web:
  GET /api/hub/playbook  -> lo que el cliente puede editar
  PUT /api/hub/playbook  -> {"owner_whatsapp", "visiting_hours": {"inicio","fin","dias"}, "quiet_hours": {"start","end"},
                             "forbidden_phrases": [...], "bot_name", "advisor_name", "address", "default_language",
                             "seguimiento": {"es": {...}, "en": {...}}, "crm_field_mapping": {...}}
Los datos del negocio van a tenants; los del guion (horario de visitas, frases prohibidas, textos de seguimiento) a
tenant_playbooks.playbook. El resto del playbook se conserva tal cual."""
import copy
import re
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request

from bot import playbooks, tenant
from bot.crm_adapters import mapeo
from bot.db import supabase
from bot.hub.sesion import requiere_sesion
from bot.seguimiento import plantillas

bp = Blueprint("hub_config", __name__)
HORA = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
DIAS = {"lun", "mar", "mie", "jue", "vie", "sab", "dom"}


def _vista():
    t = tenant.actual()
    pb = playbooks.actual() or {}
    agenda = (pb.get("agenda") or {}).get("horario_visitas") or {}
    return {"owner_whatsapp": t.get("owner_whatsapp") or "", "bot_name": t.get("bot_name"), "advisor_name": t.get("advisor_name"),
            "address": t.get("address"), "default_language": t.get("default_language") or "es", "industry": t.get("industry"),
            "pipeline_mode": t.get("pipeline_mode"), "crm_type": t.get("crm_type") or "peruptd_native",
            "visiting_hours": {"inicio": agenda.get("inicio", "09:00"), "fin": agenda.get("fin", "18:00"),
                               "dias": agenda.get("dias", ["lun", "mar", "mie", "jue", "vie", "sab"])},
            "quiet_hours": {"start": str(t.get("quiet_hours_start") or "20:30")[:5], "end": str(t.get("quiet_hours_end") or "08:30")[:5]},
            "forbidden_phrases": pb.get("frases_prohibidas") or [],
            "seguimiento": {i: {c: plantillas.texto_crudo(c, i) for c in plantillas.CLAVES_EDITABLES} for i in ("es", "en")},
            "crm_field_mapping": mapeo.efectivo(t)}


@bp.route("/api/hub/playbook")
@requiere_sesion()
def ver():
    return jsonify(_vista())


def validar(d):
    """(cambios_tenant, cambios_playbook, error)"""
    ten, pb = {}, {}
    if "owner_whatsapp" in d:
        num = re.sub(r"[^\d]", "", str(d["owner_whatsapp"] or ""))
        if num and not 8 <= len(num) <= 15:
            return None, None, "owner_whatsapp: número con código de país, 8 a 15 dígitos"
        ten["owner_whatsapp"] = num or None
    for c, largo in (("bot_name", 40), ("advisor_name", 60), ("address", 300)):
        if c in d:
            ten[c] = (str(d[c] or "").strip()[:largo]) or None
    if "default_language" in d:
        if d["default_language"] not in ("es", "en"):
            return None, None, "default_language debe ser es o en"
        ten["default_language"] = d["default_language"]
    if "quiet_hours" in d:
        q = d["quiet_hours"] or {}
        if not (HORA.match(str(q.get("start", ""))) and HORA.match(str(q.get("end", "")))):
            return None, None, "quiet_hours: start y end en formato HH:MM"
        ten["quiet_hours_start"], ten["quiet_hours_end"] = q["start"], q["end"]
    if "visiting_hours" in d:
        v = d["visiting_hours"] or {}
        dias = [x for x in (v.get("dias") or []) if x in DIAS]
        if not (HORA.match(str(v.get("inicio", ""))) and HORA.match(str(v.get("fin", "")))) or v["inicio"] >= v["fin"] or not dias:
            return None, None, "visiting_hours: inicio < fin (HH:MM) y al menos un día (lun…dom)"
        pb["agenda.horario_visitas"] = {"inicio": v["inicio"], "fin": v["fin"], "dias": dias}
    if "forbidden_phrases" in d:
        frases = d["forbidden_phrases"]
        frases = frases.split("\n") if isinstance(frases, str) else frases or []
        pb["frases_prohibidas"] = [str(f).strip()[:120] for f in frases if str(f).strip()][:100]
    if "seguimiento" in d:
        for idioma, textos in (d["seguimiento"] or {}).items():
            if idioma not in ("es", "en") or not isinstance(textos, dict):
                return None, None, "seguimiento: {'es': {...}, 'en': {...}}"
            for clave, txt in textos.items():
                if clave not in plantillas.CLAVES_EDITABLES:
                    return None, None, f"seguimiento: clave desconocida {clave}"
                pb[f"seguimiento.{idioma}.{clave}"] = str(txt or "").strip()[:1200] or None
    if "crm_field_mapping" in d:
        m, error = mapeo.validar(d["crm_field_mapping"])
        if error:
            return None, None, error
        ten["crm_field_mapping_json"] = m
    return ten, pb, None


def _poner(dic, ruta, valor):
    partes = ruta.split(".")
    for p in partes[:-1]:
        dic = dic.setdefault(p, {})
    if valor is None:
        dic.pop(partes[-1], None)
    else:
        dic[partes[-1]] = valor


@bp.route("/api/hub/playbook", methods=["PUT"])
@requiere_sesion(rol="admin")
def guardar():
    ten, pb, error = validar(request.get_json(silent=True) or {})
    if error:
        return jsonify({"error": error}), 400
    if ten:
        supabase.table("tenants").update(ten).eq("id", tenant.tid()).execute()
    if pb:
        actual = copy.deepcopy(playbooks.actual() or {})
        for ruta, valor in pb.items():
            _poner(actual, ruta, valor)
        industria = tenant.actual().get("industry") or "general"
        supabase.table("tenant_playbooks").upsert({"tenant_id": tenant.tid(), "industria": industria, "playbook": actual,
                                                   "updated_at": datetime.now(timezone.utc).isoformat()}, on_conflict="tenant_id").execute()
    tenant.limpiar_cache(tenant.tid())
    playbooks.limpiar_cache()
    return jsonify(_vista())
