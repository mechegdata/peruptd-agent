"""Alertas al asesor humano (OWNER_WA) con respaldo por plantilla."""
import re

import requests

from bot.canales.whatsapp import send_wa_text
from bot.config import ALERTA_TEMPLATE, GRAPH_URL, OWNER_WA, WA_PHONE_ID, WA_TOKEN
from bot.estado import ALERTA_ESTADO
from bot.utils.telefono import normalize_pe_phone


def alertar_asesor(texto):
    """Envía una alerta al asesor (OWNER_WA). Si el mensaje libre falla (por la ventana de 24 h de WhatsApp),
    intenta con una plantilla aprobada. Todo queda en los logs con la etiqueta [ALERTA]."""
    print(f"[ALERTA] {texto}")
    if not ALERTA_ESTADO["chequeado"]:
        ALERTA_ESTADO["chequeado"] = True
        try:
            info = requests.get(f"{GRAPH_URL}/{WA_PHONE_ID}", params={"fields": "display_phone_number"},
                                headers={"Authorization": f"Bearer {WA_TOKEN}"}, timeout=10).json()
            propio = re.sub(r"\D", "", info.get("display_phone_number", ""))
            if propio and propio == re.sub(r"\D", "", OWNER_WA or ""):
                print("[ALERTA] ⚠️ OWNER_WA es el MISMO número del bot: WhatsApp no permite enviarse mensajes a sí mismo, "
                      "las alertas nunca llegarán. Configura OWNER_WA con el celular personal del asesor.")
        except Exception:
            pass
    if send_wa_text(OWNER_WA, texto):
        return True
    if ALERTA_TEMPLATE:
        try:
            r = requests.post(
                f"{GRAPH_URL}/{WA_PHONE_ID}/messages",
                headers={"Authorization": f"Bearer {WA_TOKEN}"},
                json={"messaging_product": "whatsapp", "to": normalize_pe_phone(OWNER_WA) or OWNER_WA, "type": "template",
                      "template": {"name": ALERTA_TEMPLATE, "language": {"code": "es"},
                                   "components": [{"type": "body", "parameters": [
                                       {"type": "text", "text": re.sub(r"\s+", " ", texto.replace("\n", " | "))[:1000]}]}]}},
                timeout=15)
            if r.status_code == 200:
                return True
            print(f"[ALERTA] La plantilla {ALERTA_TEMPLATE} también falló: HTTP {r.status_code} {r.text[:300]}")
        except Exception as e:
            print("[ALERTA] Error enviando plantilla de alerta:", e)
    print("[ALERTA] ❌ No se pudo avisar al asesor por WhatsApp (revisa OWNER_WA y la ventana de 24 h).")
    return False
