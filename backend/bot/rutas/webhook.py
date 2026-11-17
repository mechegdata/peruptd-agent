"""Webhook de Meta: WhatsApp, Messenger, Instagram, comentarios y Lead Ads."""
import json
import threading

from flask import Blueprint, jsonify, request
import requests

from bot.atencion import atender_mensaje_wa
from bot.canales.messenger import send_meta_dm
from bot.canales.whatsapp import extraer_texto_wa
from bot.config import FB_PAGE_ID, FIRMA_META_EXIGIR, GRAPH_URL, IG_ACCOUNT_ID, META_APP_SECRETS, META_TOKEN, PROCESAR_EN_SEGUNDO_PLANO, VERIFY_TOKEN
from bot.conversacion.orquestador import process_conversation
from bot.datos.leads import migrar_id_legado, safe_upsert_lead
from bot.datos.idempotencia import ya_procesado
from bot.handoff import guardar_mensaje_manual
from bot.leadgen import schedule_form_followup
from bot.nlp.formulario import parse_lead_form_text
from bot.utils.firma_meta import firma_valida
from bot.utils.telefono import normalize_pe_phone


bp = Blueprint("webhook", __name__)


@bp.route("/webhook", methods=["GET"])
def verify():
    if request.args.get("hub.mode") == "subscribe" and request.args.get("hub.verify_token") == VERIFY_TOKEN:
        return request.args.get("hub.challenge"), 200
    return "Invalido", 403


@bp.before_request
def exigir_firma_de_meta():
    """Rechaza los POST al webhook que no estén firmados por Meta (si META_APP_SECRET está configurado)."""
    if request.method != "POST" or request.path != "/webhook":
        return None
    if not META_APP_SECRETS:
        print("AVISO: META_APP_SECRET no configurado; el webhook acepta avisos sin verificar la firma de Meta.")
        return None
    if firma_valida(request.get_data(), request.headers.get("X-Hub-Signature-256", ""), META_APP_SECRETS):
        if not FIRMA_META_EXIGIR:
            print("Firma de Meta OK (modo observación).")
        return None
    if not FIRMA_META_EXIGIR:
        print("Firma de Meta NO coincide (modo observación: se deja pasar). Revisa META_APP_SECRET.")
        return None
    print("Webhook RECHAZADO: firma de Meta inválida o ausente.", request.headers.get("User-Agent", "")[:80])
    return "Firma inválida", 403


@bp.route("/webhook", methods=["POST"])
def webhook():
    body = request.get_json(silent=True) or {}
    obj = body.get("object")

    if obj == "whatsapp_business_account":
        for e in body.get("entry", []):
            for c in e.get("changes", []):
                val = c.get("value", {})
                contacts = val.get("contacts", [{}])
                wa_profile_name = contacts[0].get("profile", {}).get("name", "") if contacts else ""
                if c.get("field") == "smb_message_echoes" or val.get("message_echoes"):
                    for eco in val.get("message_echoes") or val.get("messages") or []:
                        destino_eco = eco.get("to") or eco.get("to_user_id")
                        guardar_mensaje_manual(normalize_pe_phone(destino_eco) or destino_eco, "whatsapp", extraer_texto_wa(eco), eco.get("id"))
                    continue
                for st in val.get("statuses", []):
                    if st.get("status") == "failed":
                        print("WhatsApp NO entregó un mensaje:", json.dumps(st.get("errors", st), ensure_ascii=False)[:500])
                pendientes = []  # (remitente, texto, tipo): varios mensajes del mismo cliente en un solo aviso se juntan
                for m in val.get("messages", []):
                    msg_id = m.get("id")
                    if ya_procesado(msg_id, "whatsapp"):
                        continue

                    c0 = contacts[0] if contacts else {}
                    # Si WhatsApp manda el teléfono (wa_id) se usa ese; si el cliente usa "username" solo llega su BSUID.
                    raw_from = c0.get("wa_id") or m.get("from") or m.get("from_user_id") or c0.get("user_id")
                    s = normalize_pe_phone(raw_from) or raw_from
                    migrar_id_legado(s)
                    t = extraer_texto_wa(m)
                    print(f"WA entrante de {raw_from} ({wa_profile_name}) tipo={m.get('type')}: {t[:120]!r}")
                    if not s:
                        print("Mensaje de WhatsApp sin remitente reconocible:", json.dumps(m, ensure_ascii=False)[:500])
                        continue
                    if pendientes and pendientes[-1][0] == s and m.get("type") == "text" and pendientes[-1][2] == "text":
                        pendientes[-1] = (s, pendientes[-1][1] + "\n" + t, "text")
                    else:
                        pendientes.append((s, t, m.get("type")))
                for s, t, tipo in pendientes:
                    if PROCESAR_EN_SEGUNDO_PLANO:
                        threading.Thread(target=atender_mensaje_wa, args=(s, t, wa_profile_name, tipo), daemon=True).start()
                    else:
                        atender_mensaje_wa(s, t, wa_profile_name, tipo)

    elif obj in ["page", "instagram"]:
        canal_base = "instagram" if obj == "instagram" else "facebook"
        for e in body.get("entry", []):
            for m in e.get("messaging", []):
                msg_obj = m.get("message", {})
                if msg_obj.get("is_echo"):
                    destinatario = (m.get("recipient") or {}).get("id")
                    if destinatario and msg_obj.get("text"):
                        guardar_mensaje_manual(destinatario, canal_base, msg_obj.get("text"), msg_obj.get("mid"))
                    continue
                msg_id = msg_obj.get("mid")
                if ya_procesado(msg_id, canal_base):
                    continue

                s = m.get("sender", {}).get("id")
                t = msg_obj.get("text", "")
                if not s or s in [FB_PAGE_ID, IG_ACCOUNT_ID] or not t:
                    continue

                form_data = parse_lead_form_text(t)
                if form_data.get("es_formulario"):
                    f_phone = form_data.get("telefono")
                    f_name = form_data.get("nombre", "Cliente")
                    f_cocina = form_data.get("estilo_cocina", "Gris Grafito con LED")
                    f_pago = form_data.get("forma_pago", "Contado / Crédito Hipotecario")
                    f_presup = form_data.get("en_presupuesto", "Sí")

                    meta_init = {
                        "forma_pago": f_pago,
                        "estilo_cocina": f_cocina,
                        "en_presupuesto": f_presup,
                        "psid_messenger": s,
                    }  # sin 'wsp_iniciado': si ya conversa por WhatsApp, no se debe borrar esa marca (duplicaba la bienvenida)
                    safe_upsert_lead(s, canal_base, f_name, f_phone, meta_init, t)
                    if f_phone:
                        safe_upsert_lead(f_phone, "whatsapp", f_name, f_phone, meta_init, t)
                        schedule_form_followup(f_phone, f_name, f_cocina, f_pago, f_presup, psid_messenger=s)
                    continue

                parsed_ans, _, _, _ = process_conversation(s, canal_base, t)
                send_meta_dm(s, parsed_ans.get("reply_text", ""))

            for c in e.get("changes", []):
                field = c.get("field")
                v = c.get("value", {})

                if field == "leadgen":
                    lead_id = v.get("leadgen_id")
                    if lead_id and not ya_procesado(lead_id, "leadgen"):
                        try:
                            r_lead = requests.get(
                                f"{GRAPH_URL}/{lead_id}",
                                params={"access_token": META_TOKEN},
                                timeout=10
                            ).json()
                            campos = {f.get("name", ""): (f.get("values") or [""])[0] for f in r_lead.get("field_data", [])}
                            f_phone = None
                            f_name = "Cliente"
                            f_cocina = "Línea Moderna Gris Grafito con LED"
                            f_pago = "Contado / Crédito Hipotecario"
                            f_presup = "Sí"
                            for k, val_str in campos.items():
                                kl = k.lower()
                                if "phone" in kl or "telefono" in kl or "celular" in kl:
                                    f_phone = normalize_pe_phone(val_str)
                                elif "name" in kl or "nombre" in kl:
                                    f_name = val_str.strip().title()
                                elif "estilo" in kl or "cocina" in kl:
                                    f_cocina = val_str.strip()
                                elif "compra" in kl or "modalidad" in kl or "pago" in kl:
                                    f_pago = val_str.strip()
                                elif "rango" in kl or "inversi" in kl or "presupuesto" in kl:
                                    f_presup = val_str.strip()
                            if f_phone:
                                meta_init = {
                                    "forma_pago": f_pago,
                                    "estilo_cocina": f_cocina,
                                    "en_presupuesto": f_presup,
                                }  # sin 'wsp_iniciado' (ver arriba)
                                safe_upsert_lead(f_phone, "whatsapp", f_name, f_phone, meta_init, "[Leadgen Form]")
                                schedule_form_followup(f_phone, f_name, f_cocina, f_pago, f_presup)
                        except Exception as e_lg:
                            print("Error procesando leadgen:", e_lg)

                elif field == "feed" and v.get("item") == "comment" and v.get("verb") == "add":
                    cid = v.get("comment_id")
                    s = v.get("from", {}).get("id")
                    autor = v.get("from", {}).get("name", "")
                    t = v.get("message", "")
                    if cid and s and str(s) != str(FB_PAGE_ID) and t and not ya_procesado(cid, "fb_comment"):
                        parsed_ans, _, _, _ = process_conversation(s, "fb_comment", t, sender_name=autor, comment_id=cid)
                        if not parsed_ans.get("ignorar_comentario"):
                            requests.post(
                                f"{GRAPH_URL}/{cid}/comments",
                                params={"access_token": META_TOKEN},
                                json={"message": parsed_ans.get("reply_text", "")},
                                timeout=15
                            )
                            if parsed_ans.get("private_reply"):
                                requests.post(
                                    f"{GRAPH_URL}/{FB_PAGE_ID}/messages",
                                    params={"access_token": META_TOKEN},
                                    json={"recipient": {"comment_id": cid}, "message": {"text": parsed_ans["private_reply"]}},
                                    timeout=15
                                )

                elif field == "comments":
                    cid = v.get("id")
                    s = v.get("from", {}).get("id")
                    autor = v.get("from", {}).get("username", "")
                    t = v.get("text", "")
                    if cid and s and str(s) != str(IG_ACCOUNT_ID) and t and not ya_procesado(cid, "ig_comment"):
                        parsed_ans, _, _, _ = process_conversation(s, "ig_comment", t, sender_name=autor, comment_id=cid)
                        if not parsed_ans.get("ignorar_comentario"):
                            requests.post(
                                f"{GRAPH_URL}/{cid}/replies",
                                params={"access_token": META_TOKEN},
                                json={"message": parsed_ans.get("reply_text", "")},
                                timeout=15
                            )
                            if parsed_ans.get("private_reply"):
                                requests.post(
                                    f"{GRAPH_URL}/me/messages",
                                    params={"access_token": META_TOKEN},
                                    json={"recipient": {"comment_id": cid}, "message": {"text": parsed_ans["private_reply"]}},
                                    timeout=15
                                )

    return jsonify({"status": "ok"}), 200
