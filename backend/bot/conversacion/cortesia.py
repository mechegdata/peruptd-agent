"""Cortesía conversacional: 'le estaré comunicando la hora', '👍', 'ok'. Un asesor no insiste ni responde un pulgar con una lista.

Puede devolver una respuesta con '_no_responder': True cuando lo humano es no contestar (p. ej. un 👍 a "quedo atento").
"""
import re
from datetime import datetime, timezone

from bot.conversacion.agenda_humana import slots_vigentes
from bot.conversacion.base import _resp
from bot.conversacion.recursos import hay_renders, hay_videos
from bot.nlp.parser_fechas import parse_fecha_hora_es
from bot.nlp.patrones import ACUSE_RE, LEJOS_RE, POSTERGAR_RE
from bot.utils.texto import limpiar_texto

ETAPAS_EN_PAUSA = ["espera_cliente", "cerrado", "agendado"]
# Etapas en las que el bot hizo una pregunta de sí/no: ahí "ok" es una respuesta, no un simple acuse
ESPERAN_RESPUESTA = ["ofrecio_material", "ofrecio_asesor", "ofrecio_copia", "confirmar_horario", "pregunto_financiamiento",
                     "confirmar_asistencia", "ofrecio_video",
                     "pregunto_acompanantes", "ofrecio_movilidad", "confirmacion_manual"]
_FAMILIA_RX = r"\b(espos[oa]|familia|pareja|herman[oa]|mama|papa|hij[oa]s?|socio|novi[oa]|abogad[oa])\b"


def es_acuse(user_text):
    """True si el mensaje es solo un emoji o un 'ok/listo/ya' sin más contenido."""
    crudo = (user_text or "").strip()
    if crudo and not re.search(r"[0-9A-Za-zÁÉÍÓÚáéíóúÑñ]", crudo):
        return True  # solo emojis / signos
    t = re.sub(r"[^\w\s]", " ", limpiar_texto(crudo))
    return bool(ACUSE_RE.match(re.sub(r"\s+", " ", t).strip()))


def _silencio():
    r = _resp("")
    r["_no_responder"] = True
    r["_sin_control_repeticion"] = True
    return r


def _postergacion(t, meta, coma, original=""):
    meta["etapa"] = "espera_cliente"
    meta["ts_postergo"] = datetime.now(timezone.utc).isoformat()
    meta["slots_ofrecidos"] = []
    fam = re.search(_FAMILIA_RX, t)
    lejos = LEJOS_RE.search(t) and (LEJOS_RE.search((original or "").lower()) or LEJOS_RE.search(t))
    if lejos and not fam:
        lugar = lejos.group(1).split(" cuando")[0].strip().title()
        meta["vive_lejos"] = lugar
        txt = (f"¡Perfecto{coma}! Cuando vengas desde {lugar}, avísame con un día de anticipación y te reservo la visita en el horario que te "
               "acomode (también fines de semana o saliendo del trabajo, en la noche) 😊.")
        if hay_videos() and not meta.get("videos_enviados"):
            meta["etapa"] = "ofrecio_video"
            txt += " Mientras tanto, ¿te mando el video del recorrido para que la conozcas desde allá?"
        r = _resp(txt)
        r["_sin_control_repeticion"] = True
        return r
    if fam and hay_renders():
        txt = (f"¡Claro{coma}! Coméntalo con calma con tu {fam.group(1)} 😊. Para que se la muestres, te dejo cómo se vería "
               "amoblada 👇. Quedo atento a tu mensaje.")
    elif fam:
        txt = (f"¡Claro{coma}! Coméntalo con calma con tu {fam.group(1)} 😊. Si quieres, te reenvío los planos o el video para "
               "que se los muestres. Quedo atento a tu mensaje.")
    else:
        txt = f"¡Perfecto{coma}! Quedo atento a tu mensaje 😊. Cuando tengas el día, me escribes y te lo reservo al toque."
    r = _resp(txt)
    r["_sin_control_repeticion"] = True
    if fam:
        r["_momento_fotos"] = "compartir_familia"
    return r


def _acuse(meta, coma):
    etapa = meta.get("etapa") or ""
    if etapa in ["pregunto_acompanantes", "ofrecio_movilidad", "ofrecio_video"]:
        return None  # 'ok' puede ser la respuesta a la pregunta de movilidad
    if etapa == "ofrecio_horarios" and slots_vigentes(meta):  # va primero: también aplica al reprogramar
        firma = (meta.get("slots_ofrecidos") or [""])[0]
        if meta.get("recordo_horarios") == firma:
            return _silencio()  # ya se le recordó esta misma lista: no insistir
        meta["recordo_horarios"] = firma
        n = len(slots_vigentes(meta))
        nums = ["1️⃣", "2️⃣", "3️⃣", "4️⃣"][:n]
        opciones = (", ".join(nums[:-1]) + " o " + nums[-1]) if n > 1 else "1️⃣"
        r = _resp(f"👌 ¿Te reservo alguno{coma}? Respóndeme {opciones}, o si prefieres me avisas cuando sepas el día.")
        r["_sin_control_repeticion"] = True
        return r
    if etapa in ESPERAN_RESPUESTA:
        return None  # "ok" puede ser el "sí" a lo que se le preguntó: lo resuelve el motor correspondiente
    return _silencio()  # "Ok" sin nada pendiente: un asesor no responde con otra lista de horarios


SALUDO_RE = re.compile(r"^(hola+|holi+|alo|buen[oa]s?( (dias|tardes|noches))?|hola buen[oa]s?( (dias|tardes|noches))?|"
                       r"hola,? (que tal|como esta\w*)|saludos)( (senor\w*|senorita|ingeniero|amigo|amiga))?$")


def _saludo(meta, coma):
    """'Buenos días' de alguien que ya conversó antes: saludar y preguntar, sin lanzar horarios."""
    from datetime import datetime
    from bot.config import LIMA_TZ
    h = datetime.now(LIMA_TZ).hour
    saludo = "¡Buenos días" if h < 12 else ("¡Buenas tardes" if h < 19 else "¡Buenas noches")
    r = _resp(f"{saludo}{coma}! 😊 ¿En qué te puedo ayudar hoy? Te puedo contar del precio, mandarte fotos y videos de las casas "
              "o coordinar una visita.")
    r["_sin_control_repeticion"] = True
    return r


def responder_cortesia(user_text, meta, nombre_corto):
    """Postergaciones y acuses. None si el mensaje tiene contenido para otros motores (fecha, hora, pregunta)."""
    if "?" in (user_text or ""):
        return None
    fh = parse_fecha_hora_es(user_text)
    if fh.get("hora") is not None or fh.get("fecha") is not None:
        return None
    coma = f", {nombre_corto}" if nombre_corto else ""
    t = limpiar_texto(user_text)
    if SALUDO_RE.match(re.sub(r"[^\w\s,]", "", t).strip()) and (meta.get("ts_ultimo_bot") or meta.get("_con_historial")):
        return _saludo(meta, coma)
    if fh.get("turno") and meta.get("etapa") in ("ofrecio_horarios", "pregunto_dia", "confirmar_horario"):
        return None  # "En la mañana está bien" con horarios a la vista: pide ese turno (lo resuelve la agenda), no es un simple "ok"
    if POSTERGAR_RE.search(t) and len(t) <= 160:
        return _postergacion(t, meta, coma, user_text)
    if es_acuse(user_text):
        return _acuse(meta, coma)
    return None
