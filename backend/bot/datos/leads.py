"""Lectura y upsert de leads en Supabase (tabla leads, campo interes = JSON en texto)."""
import json
from datetime import datetime, timezone

from bot.db import supabase
from bot.utils.telefono import id_legado

_MIGRADOS = set()


def migrar_id_legado(sender_id):
    """Si el cliente llega con BSUID ("PE.148…") y antes se guardó sin prefijo ("148…"), pasa su lead e historial al ID nuevo.
    Así el bot no lo trata como un cliente nuevo ni pierde la conversación previa."""
    legado = id_legado(sender_id)
    if not supabase or not legado or sender_id in _MIGRADOS:
        return
    _MIGRADOS.add(sender_id)
    try:
        ya = supabase.table("leads").select("sender_id").eq("sender_id", sender_id).limit(1).execute()
        if not ya.data:
            supabase.table("leads").update({"sender_id": sender_id}).eq("sender_id", legado).execute()
        supabase.table("mensajes").update({"sender_id": sender_id}).eq("sender_id", legado).execute()
    except Exception as e:
        print(f"No se pudo migrar el ID legado {legado} -> {sender_id}:", e)


def get_lead_by_sender_or_phone(sender_id, phone=None):
    if not supabase:
        return {}
    try:
        res = supabase.table("leads").select("*").eq("sender_id", sender_id).limit(1).execute()
        if res.data:
            return res.data[0]
        if phone:
            res_p = supabase.table("leads").select("*").eq("telefono", phone).order("updated_at", desc=True).limit(1).execute()
            if res_p.data:
                return res_p.data[0]
    except Exception:
        pass
    return {}


def safe_upsert_lead(sender_id, canal, nombre=None, telefono=None, interes_dict=None, ultimo_msg=""):
    if not supabase:
        return
    now_iso = datetime.now(timezone.utc).isoformat()
    existing = get_lead_by_sender_or_phone(sender_id, telefono)
    prev_meta = {}
    if existing.get("interes"):
        try:
            prev_meta = json.loads(existing["interes"])
        except Exception:
            prev_meta = {"notas": existing["interes"]}
    if interes_dict:
        prev_meta.update({k: v for k, v in interes_dict.items() if v is not None})

    base_payload = {
        "sender_id": sender_id,
        "canal": canal,
        "nombre": nombre or existing.get("nombre") or "Interesado",
        "telefono": telefono or existing.get("telefono") or (sender_id if canal == "whatsapp" else None),
        "interes": json.dumps(prev_meta, ensure_ascii=False) if prev_meta else existing.get("interes"),
        "ultimo_mensaje": (ultimo_msg or existing.get("ultimo_mensaje") or "")[:500],
        "updated_at": now_iso
    }
    try:
        ext_payload = dict(base_payload)
        if "cita_agendada" in prev_meta:
            ext_payload["cita_agendada"] = bool(prev_meta["cita_agendada"])
        supabase.table("leads").upsert(ext_payload, on_conflict="sender_id").execute()
    except Exception:
        try:
            supabase.table("leads").upsert(base_payload, on_conflict="sender_id").execute()
        except Exception as e:
            print("Supabase lead upsert error:", e)
