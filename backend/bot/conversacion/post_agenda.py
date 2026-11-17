"""Después de agendar: con quién viene, desde dónde, movilidad y punto de encuentro (aprendido del chat real de Eloisa).

Etapas: 'pregunto_acompanantes' (se pregunta al confirmar la cita) -> 'ofrecio_movilidad' (si OFRECE_MOVILIDAD) -> 'agendado'.
"""
import re

from bot.config import MAPS_URL, MOVILIDAD_DESDE, OFRECE_MOVILIDAD
from bot.conversacion.base import _resp
from bot.nlp.patrones import AFIRMA_RE, NIEGA_RE
from bot.utils.texto import limpiar_texto

PREGUNTA_ACOMPANANTES = "Cuéntame, ¿vendrás con alguien más (familia, pareja)? Así te esperamos con todo listo 😊"
_ACOMP_RX = (r"\b(mi |con mi |con mis )?(espos[oa]|herman[oa]s?|mama|papa|padres|hij[oa]s?|familia|pareja|novi[oa]|"
             r"amig[oa]s?|prim[oa]s?|ti[oa]s?|suegr[oa]s?|socio|abogad[oa]|cuñad[oa])\b")
_SOLO_RX = r"\b(sol[oa]|yo nomas|yo no mas|nadie|solamente yo|solo yo)\b"
_PROPIA_RX = (r"\b(por (nuestra|mi|su) cuenta|de manera independiente|independiente|en (mi|nuestro) (carro|auto|movilidad)|"
              r"vamos solos|llegamos solos|no es necesario|no se preocupe|no te preocupes)\b")
_LOGISTICA_RX = r"\b(donde nos (reunimos|encontramos|vemos)|punto de encuentro|nos reunimos|recoj\w*|recog\w*|movilidad)\b"
_CUANDO_RX = r"\b(dias? antes|tiene que ser ya|ahora o|despues coordinamos|luego coordinamos|mas adelante|con tiempo)\b"


def _ack_propia(coma, meta):
    meta["movilidad"] = "propia"
    meta["etapa"] = "agendado"
    meta["_alerta_asesor"] = "🚗 Irán por su cuenta a la visita"
    return _resp(f"¡Perfecto{coma}, muchas gracias por avisarme! 😊 Te dejo la ubicación exacta por si acaso: {MAPS_URL}\n"
                 "El día de la visita te escribo por aquí para ubicarnos sin problema.")


def _respuesta_acompanantes(t, meta, coma):
    acomp = re.search(_ACOMP_RX, t)
    solo = re.search(_SOLO_RX, t)
    origen = MOVILIDAD_DESDE if re.search(rf"\b{limpiar_texto(MOVILIDAD_DESDE)}\b", t) else ""
    if not (acomp or solo or origen):
        meta["etapa"] = "agendado"
        return None
    if acomp:
        quien = acomp.group(2)
        meta["acompanantes"] = quien
        txt = f"¡Genial que vengas con tu {quien}! 🙌 Así lo ven y lo deciden juntos."
    elif solo:
        meta["acompanantes"] = "solo"
        txt = "¡Perfecto! Te esperamos 😊."
    else:
        txt = "¡Perfecto! 😊"
    meta["_alerta_asesor"] = f"👥 Visita: vendrá con {meta.get('acompanantes', 'por confirmar')}" + (f" desde {origen}" if origen else "")
    if OFRECE_MOVILIDAD and (origen or not re.search(r"\blambayeque\b", t)) and not re.search(_PROPIA_RX, t):
        meta["etapa"] = "ofrecio_movilidad"
        desde = "" if origen else f"Si vienen desde {MOVILIDAD_DESDE}, "
        txt += (f" {desde}La constructora cuenta con movilidad para acompañarlos en el traslado: ¿les gustaría que el ingeniero "
                "los recoja o prefieren llegar por su cuenta? No hay apuro, lo coordinamos antes de la visita.")
    else:
        meta["etapa"] = "agendado"
        txt += f" Un día antes te envío el recordatorio con la ubicación 📍"
    return _resp(txt)


def _respuesta_movilidad(t, user_text, meta, coma):
    if re.search(_PROPIA_RX, t) or (NIEGA_RE.match(t) and len(t) <= 40):
        return _ack_propia(coma, meta)
    if re.search(_CUANDO_RX, t) or AFIRMA_RE.match(t) or re.search(r"\b(seria bien|me parece|si por favor|si gracias|nos recojan)\b", t):
        meta["movilidad"] = "recojo"
        meta["etapa"] = "agendado"
        meta["_alerta_asesor"] = "🚗 Pidió que la recojan para la visita: coordinar punto y hora"
        return _resp(f"¡Listo{coma}! 🚗 No te preocupes, no hay apuro: un día antes de la visita te envío el recordatorio y ahí "
                     "coordinamos el punto y la hora de recojo.")
    meta["etapa"] = "agendado"
    return None


def responder_post_agenda(user_text, meta, nombre_corto):
    """Respuestas sobre acompañantes, movilidad y punto de encuentro cuando ya hay cita. None si no aplica."""
    if not meta.get("cita_agendada"):
        return None
    t = limpiar_texto(user_text)
    coma = f", {nombre_corto}" if nombre_corto else ""
    etapa = meta.get("etapa")
    if etapa == "pregunto_acompanantes":
        return _respuesta_acompanantes(t, meta, coma)
    if etapa == "ofrecio_movilidad":
        return _respuesta_movilidad(t, user_text, meta, coma)
    if re.search(_PROPIA_RX, t) and re.search(_LOGISTICA_RX + r"|\b(vamos|iremos|llegamos)\b", t):
        return _ack_propia(coma, meta)
    return None
