"""Cierre amable de conversación ('no, gracias', 'eso es todo')."""
import re
from datetime import datetime

from bot.canales.alertas import alertar_asesor
from bot.config import LIMA_TZ
from bot.conversacion.base import _resp
from bot.nlp.patrones import DESPEDIDA_RE, NO_INTERESADO_RE, PREGUNTA_OTRA_DUDA_RE
from bot.utils.fechas import format_fecha_es
from bot.utils.texto import limpiar_texto


def responder_despedida(user_text, meta, nombre_cliente, ultimo_bot=""):
    """Si el cliente se despide o ya no tiene dudas, se despide amablemente (sin volver a preguntar nada)."""
    t = limpiar_texto(user_text)
    if NO_INTERESADO_RE.search(t):
        nom = nombre_cliente.split()[0] if nombre_cliente not in ["Interesado", "Cliente", ""] else ""
        meta.update({"no_interesado": True, "etapa": "cerrado"})
        alertar_asesor(f"🚫 SAGUE: {nombre_cliente} indicó que ya no le interesa (\"{(user_text or '')[:120]}\"). Detuve sus seguimientos.")
        r = _resp(f"Entendido{', ' + nom if nom else ''}, muchas gracias por avisarnos 😊. No te enviaremos más mensajes. "
                  "Si en algún momento te interesa una casa en Lambayeque, aquí estaremos para ayudarte. ¡Éxitos!")
        r["_sin_control_repeticion"] = True
        return r
    t = re.sub(r"[^\w\s,]", " ", t).strip()
    t = re.sub(r"\s+", " ", t)
    solo_emoji_ok = bool(re.fullmatch(r"[\s👍🙏😊🙌👌☺️🤝❤️👏✅]+", user_text or ""))
    if solo_emoji_ok and (PREGUNTA_OTRA_DUDA_RE.search(ultimo_bot or "") or meta.get("etapa") in ["agendado", "cerrado", "pregunto_acompanantes", "ofrecio_movilidad"]):
        t = "gracias"
    if not t or len(t) > 80 or "?" in (user_text or ""):
        return None
    se_despide = bool(DESPEDIDA_RE.match(t))
    no_simple = bool(re.match(r"^(no+|nop|nope|ninguna|ninguno|nada|no ninguna|no nada|todo ok|todo bien|estoy bien asi|asi esta bien)$", t))
    sin_pendientes = meta.get("etapa") in [None, "", "pregunto_dia", "cerrado", "agendado", "pregunto_acompanantes", "ofrecio_movilidad"]
    if not se_despide and not (no_simple and (PREGUNTA_OTRA_DUDA_RE.search(ultimo_bot or "") or sin_pendientes)):
        return None
    nom = nombre_cliente.split()[0] if nombre_cliente not in ["Interesado", "Cliente", ""] else ""
    coma = f", {nom}" if nom else ""
    h = datetime.now(LIMA_TZ).hour
    buen = "un excelente día" if h < 12 else ("una excelente tarde" if h < 19 else "una excelente noche")
    if meta.get("etapa") == "cerrado":
        txt = f"¡Con gusto{coma}! 🙌"
    elif meta.get("cita_agendada") and meta.get("fecha_cita") and datetime.fromisoformat(meta["fecha_cita"]) > datetime.now(LIMA_TZ):
        txt = (f"¡Gracias a ti{coma}! 😊 Te esperamos el *{format_fecha_es(datetime.fromisoformat(meta['fecha_cita']), relativo=True)}* "
               f"en Urb. Santa Teresa. Cualquier cosa, aquí estoy para ayudarte. ¡Que tengas {buen}!")
    else:
        txt = (f"¡Gracias a ti{coma}! 😊 Fue un gusto atenderte. Quedo a tu disposición por aquí para cualquier consulta "
               f"o cuando quieras conocer las casas de Urb. Santa Teresa. ¡Que tengas {buen}!")
    meta.update({"etapa": "cerrado", "pregunta_fin_pendiente": False, "rechazos_horario": 0})
    r = _resp(txt)
    r["_sin_control_repeticion"] = True
    return r
