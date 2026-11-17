"""Frases de cierre contextual según lo que se sabe del cliente."""
from datetime import datetime

from bot.config import LIMA_TZ
from bot.conversacion.slots import _slots_a_texto
from bot.integraciones.calendario import get_free_slots
from bot.utils.fechas import DIAS_ES, a_las, format_fecha_es


def _cierre_con_horarios(meta, nombre_corto):
    libres = get_free_slots(n=2)
    if not libres:
        return "¿Qué día te acomoda para visitarnos y ver los 3 pisos en persona? 🏡"
    # Si ya le pasamos estos mismos horarios, no repetir la lista completa: recordarlos en una línea, como un asesor
    if meta is not None and meta.get("etapa") == "ofrecio_horarios" and (meta.get("slots_ofrecidos") or [])[:2] == [s.isoformat() for s in libres]:
        if len(libres) == 2 and libres[0].date() == libres[1].date():
            d = libres[0]
            rel = (d.date() - datetime.now(LIMA_TZ).date()).days
            dia_txt = ("hoy " if rel == 0 else "mañana " if rel == 1 else "el ") + f"{DIAS_ES[d.weekday()]} {d.day}"
            opciones = f"{dia_txt} {a_las(libres[0])} o {a_las(libres[1])}"
        else:
            opciones = " o el ".join(format_fecha_es(s, relativo=True) for s in libres)
        n = int(meta.get("n_cierres") or 0)
        meta["n_cierres"] = n + 1
        frases = [
            f"Cuando gustes te reservo la visita para que lo veas en persona: ¿te acomoda {opciones}, o prefieres otro día? 🏡",
            f"Y si quieres verlo en persona, sigo teniendo libre {opciones} 😊",
            f"¿Te separo alguno de esos horarios ({opciones}) o te queda mejor otro día?",
        ]
        return frases[n % len(frases)]
    if meta is not None:
        meta["etapa"] = "ofrecio_horarios"
        meta["slots_ofrecidos"] = [s.isoformat() for s in libres]
    return ("¿Te parece si coordinamos tu visita para que veas los 3 pisos en persona? Tengo libre:\n"
            f"{_slots_a_texto(libres)}\nRespóndeme con el número y te la registro 🏡")


def cierre_contextual(meta, nombre_corto):
    """Cierra cada respuesta con el SIGUIENTE paso real de esa conversación (no repite lo ya resuelto)."""
    meta = meta if meta is not None else {}
    ahora = datetime.now(LIMA_TZ)
    try:
        if meta.get("cita_agendada") and meta.get("fecha_cita"):
            f = datetime.fromisoformat(meta["fecha_cita"])
            if f > ahora:
                return f"Todo esto lo vemos con calma en tu visita del *{format_fecha_es(f, relativo=True)}* 😊. ¿Tienes alguna otra duda?"
        if meta.get("slot_propuesto"):
            f = datetime.fromisoformat(meta["slot_propuesto"])
            if f > ahora:
                meta["etapa"] = "confirmar_horario"
                return f"¿Te confirmo la visita del *{format_fecha_es(f, relativo=True)}* para verlo en persona? Respóndeme *sí* y la registro."
    except Exception:
        pass
    return _cierre_con_horarios(meta, nombre_corto)


def cierre_info(meta, nombre_corto, temas):
    """Caso 5: tras pedir información general, una pregunta de filtro financiero (solo si aún no se sabe); si no, el siguiente paso."""
    sabe_fin = any(meta.get(k) is not None for k in ["fin_modalidad", "fin_inicial", "fin_credito_aprobado"])
    if temas == ["general"] and not sabe_fin and int(meta.get("veces_pregunta_fin") or 0) == 0 and not meta.get("cita_agendada"):
        meta["pregunta_fin_pendiente"] = True
        return "¿La estás buscando para comprar al contado o con crédito hipotecario? Así te oriento mejor y coordinamos tu visita 😊"
    return cierre_contextual(meta, nombre_corto)
