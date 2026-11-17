"""Ofrecer, elegir y recuperar horarios de visita."""
import re
from datetime import datetime, timedelta

from bot.config import LIMA_TZ
from bot.integraciones.calendario import _slot_valido_por_horario, get_free_slots
from bot.nlp.parser_fechas import parse_fecha_hora_es
from bot.utils.fechas import format_fecha_es


def _slots_a_texto(slots):
    emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣"]
    return "\n".join(f"{emojis[i]} {format_fecha_es(s, relativo=True)}" for i, s in enumerate(slots))


def elegir_slot_ofrecido(t, ofrecidos_iso, fh):
    try:
        ofrecidos = [datetime.fromisoformat(s) for s in ofrecidos_iso]
    except Exception:
        return None
    if not ofrecidos:
        return None
    idx = None
    m = re.match(r"^(?:la |el |opcion |numero |nro |la opcion |el numero )?([1-9])\b", t)
    if m and len(t) <= 30:
        idx = int(m.group(1)) - 1
    elif re.search(r"\b(primer[oa]?|1r[oa])\b", t):
        idx = 0
    elif re.search(r"\b(segund[oa]|2d[oa])\b", t):
        idx = 1
    elif re.search(r"\b(tercer[oa]?|3r[oa])\b", t):
        idx = 2
    elif re.search(r"\bultim[oa]\b", t):
        idx = len(ofrecidos) - 1
    if idx is not None and 0 <= idx < len(ofrecidos):
        return ofrecidos[idx]
    if fh.get("hora") is not None:
        coinc = [s for s in ofrecidos if s.hour == fh["hora"] and s.minute == fh["minuto"]
                 and (fh.get("fecha") is None or s.date() == fh["fecha"])]
        if len(coinc) == 1:
            return coinc[0]
    if fh.get("fecha") is not None and fh.get("hora") is None:
        coinc = [s for s in ofrecidos if s.date() == fh["fecha"]
                 and (fh.get("turno") is None or (fh["turno"] == "manana") == (s.hour < 13))]
        if len(coinc) == 1:
            return coinc[0]
    return None


def horarios_en(dias_semana, horas, n=3, desde_hora=None, por_dia=2, dias_busqueda=14):
    """Horarios concretos libres ('sábado 10:00', 'lunes 18:30') en los días y horas indicados, verificados en Calendar."""
    from bot.integraciones.calendario import verificar_slot
    hoy = datetime.now(LIMA_TZ)
    libres = []
    for i in range(dias_busqueda):
        d = (hoy + timedelta(days=i)).date()
        if d.weekday() not in dias_semana:
            continue
        del_dia = 0
        for hh, mm in horas:
            if desde_hora is not None and hh < desde_hora:
                continue
            dt = datetime(d.year, d.month, d.day, hh, mm, tzinfo=LIMA_TZ)
            if dt > hoy + timedelta(hours=2) and verificar_slot(dt)[0] in ["libre", "sin_verificar"]:
                libres.append(dt)
                del_dia += 1
            if del_dia >= por_dia or len(libres) >= n:
                break
        if len(libres) >= n:
            break
    return libres


def construir_slot(fh):
    if fh.get("hora") is None:
        return None
    if fh.get("fecha"):
        f = fh["fecha"]
        return datetime(f.year, f.month, f.day, fh["hora"], fh["minuto"], tzinfo=LIMA_TZ)
    hoy = datetime.now(LIMA_TZ)
    dt = hoy.replace(hour=fh["hora"], minute=fh["minuto"], second=0, microsecond=0)
    if not _slot_valido_por_horario(dt, estricto=False)[0]:
        dt = dt + timedelta(days=1)
    return dt


def recuperar_slot_de_historial(historial_usuario):
    """Si el cliente propuso día y hora en mensajes anteriores (y no quedó guardado), lo recupera."""
    for msg in reversed(historial_usuario[-6:]):
        fh = parse_fecha_hora_es(msg)
        if fh.get("hora") is not None and fh.get("fecha") is not None:
            dt = construir_slot(fh)
            if dt and dt > datetime.now(LIMA_TZ):
                return dt
    return None


def _dos_horarios(meta, preferir=None):
    """Dos horarios libres reales para cerrar el seguimiento; guarda el estado para que '1'/'2' funcione."""
    libres = preferir or get_free_slots(n=2)
    if not libres:
        return "¿Qué día te acomodaría para venir a verlas? 🏡"
    meta["etapa"] = "ofrecio_horarios"
    meta["slots_ofrecidos"] = [s.isoformat() for s in libres]
    return "Tengo libre:\n" + _slots_a_texto(libres) + "\nRespóndeme con el número y te la reservo 🏡"
