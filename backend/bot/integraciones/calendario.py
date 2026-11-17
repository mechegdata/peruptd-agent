"""Google Calendar: disponibilidad (freebusy), slots libres, crear y reprogramar visitas."""
import time
from datetime import date, datetime, timedelta

from googleapiclient.discovery import build
import google.auth

from bot.config import CALENDAR_ID, DIAS_ATENCION, DURACION_VISITA_MIN, HORA_FIN_VISITAS, HORA_INICIO_VISITAS, LIMA_TZ, MIN_ANTICIPACION_HORAS, RESTRINGIR_HORARIO_PROPUESTO, VISITAS_DESDE
from bot.estado import CALENDAR_CACHE
from bot.utils.fechas import DIAS_ES, format_fecha_es


def get_calendar_service():
    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/calendar"])
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def _parse_rfc3339(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(LIMA_TZ)


def get_busy_intervals(desde, hasta):
    """Intervalos ocupados reales del calendario (freebusy respeta eventos marcados como 'Disponible')."""
    try:
        service = get_calendar_service()
        res = service.freebusy().query(body={
            "timeMin": desde.isoformat(),
            "timeMax": hasta.isoformat(),
            "timeZone": "America/Lima",
            "items": [{"id": CALENDAR_ID}]
        }).execute()
        busy = res.get("calendars", {}).get(CALENDAR_ID, {}).get("busy", [])
        return [(_parse_rfc3339(b["start"]), _parse_rfc3339(b["end"])) for b in busy]
    except Exception as e:
        print("Error consultando freebusy de Calendar:", e)
        return None  # None = no se pudo verificar


def primer_dia_visitas():
    """Fecha desde la que se agendan visitas (VISITAS_DESDE), o None si no hay restricción o ya pasó."""
    try:
        d = date.fromisoformat(VISITAS_DESDE) if VISITAS_DESDE else None
    except ValueError:
        return None
    return d if d and d > datetime.now(LIMA_TZ).date() else None


def fecha_apertura_txt():
    """'domingo 15 de noviembre' (para los mensajes)."""
    from bot.utils.fechas import DIAS_ES, MESES_ES
    d = primer_dia_visitas()
    return f"{DIAS_ES[d.weekday()]} {d.day} de {MESES_ES[d.month]}" if d else ""


def _slot_valido_por_horario(dt_start, ahora=None, estricto=True):
    """Valida anticipación mínima y, si estricto, día y franja de visitas sugeridas. Devuelve (ok, motivo)."""
    ahora = ahora or datetime.now(LIMA_TZ)
    dt_end = dt_start + timedelta(minutes=DURACION_VISITA_MIN)
    if dt_start < ahora + timedelta(hours=MIN_ANTICIPACION_HORAS):
        return False, "pasado"
    if primer_dia_visitas() and dt_start.date() < primer_dia_visitas():
        return False, "apertura"  # aún se están terminando detalles: visitas desde VISITAS_DESDE
    if not estricto:
        return True, ""
    if dt_start.weekday() not in DIAS_ATENCION:
        return False, "dia"
    inicio = dt_start.replace(hour=HORA_INICIO_VISITAS, minute=0, second=0, microsecond=0)
    fin = dt_start.replace(hour=HORA_FIN_VISITAS, minute=0, second=0, microsecond=0)
    if dt_start < inicio or dt_end > fin:
        return False, "horario"
    return True, ""


def _choca(dt_start, busy):
    dt_end = dt_start + timedelta(minutes=DURACION_VISITA_MIN)
    return any(b_ini < dt_end and dt_start < b_fin for b_ini, b_fin in busy)


def verificar_slot(dt_start):
    """Devuelve (estado, motivo): estado = 'libre' | 'ocupado' | 'invalido' | 'sin_verificar'."""
    ok, motivo = _slot_valido_por_horario(dt_start, estricto=RESTRINGIR_HORARIO_PROPUESTO)
    if not ok:
        return "invalido", motivo
    busy = get_busy_intervals(dt_start - timedelta(minutes=1), dt_start + timedelta(minutes=DURACION_VISITA_MIN + 1))
    if busy is None:
        return "sin_verificar", ""
    return ("ocupado", "") if _choca(dt_start, busy) else ("libre", "")


def get_free_slots(n=3, dia=None, turno=None, excluir=None, dias_busqueda=14, dias_semana=None, excluir_fechas=None, filtro=None):
    """
    Horarios libres más próximos. Sin 'dia': máximo 2 por día (el 1ro libre de la mañana y el 1ro de la tarde)
    para dar variedad. Con 'dia' (date): los primeros libres de ese día. turno: 'manana' | 'tarde' | None.
    dias_semana: set de weekday() permitidos (ej. {5, 6} = fin de semana). excluir_fechas: fechas a saltar.
    filtro: función opcional dt -> bool para descartar horarios (p. ej. 'trabajo hasta las 5').
    """
    ahora = datetime.now(LIMA_TZ)
    excluir = set(excluir or [])
    excluir_fechas = set(excluir_fechas or [])
    desde = primer_dia_visitas()
    if dia:
        fechas = [dia] if not desde or dia >= desde else []
    else:
        base = max(ahora.date(), desde) if desde else ahora.date()
        fechas = [base + timedelta(days=i) for i in range(dias_busqueda)]
        fechas = [f for f in fechas if (not dias_semana or f.weekday() in dias_semana) and f not in excluir_fechas]
    if not fechas:
        return []
    rango_ini = datetime(fechas[0].year, fechas[0].month, fechas[0].day, 0, 0, tzinfo=LIMA_TZ)
    rango_fin = datetime(fechas[-1].year, fechas[-1].month, fechas[-1].day, 23, 59, tzinfo=LIMA_TZ)
    busy = get_busy_intervals(rango_ini, rango_fin) or []

    slots = []
    for f in fechas:
        del_dia = []
        for h in range(HORA_INICIO_VISITAS, HORA_FIN_VISITAS):
            dt = datetime(f.year, f.month, f.day, h, 0, tzinfo=LIMA_TZ)
            if turno == "manana" and h >= 13:
                continue
            if turno in ["tarde", "noche"] and h < 13:
                continue
            if dt.isoformat() in excluir or (filtro and not filtro(dt)):
                continue
            ok, _ = _slot_valido_por_horario(dt, ahora)
            if ok and not _choca(dt, busy):
                del_dia.append(dt)
        if dia and not turno:
            slots.extend(_repartir(del_dia, n))
        elif dia:
            slots.extend(del_dia)
        elif turno:
            slots.extend(del_dia[:2])
        else:
            manana = [d for d in del_dia if d.hour < 13][:1]
            tarde = [d for d in del_dia if d.hour >= 13][:1]
            slots.extend(manana + tarde)
        if len(slots) >= n:
            break
    return slots[:n]


def _repartir(horarios, n):
    """De un mismo día, uno de la mañana, uno del mediodía y uno de la tarde (así el cliente elige), luego el resto."""
    tramos = [[h for h in horarios if h.hour < 12], [h for h in horarios if 12 <= h.hour < 15], [h for h in horarios if h.hour >= 15]]
    elegidos = [t[0] for t in tramos if t]
    elegidos += [h for h in horarios if h not in elegidos]
    return sorted(elegidos[:n])


def get_calendar_availability_text():
    now_ts = time.time()
    if now_ts - CALENDAR_CACHE["ts"] < 60 and CALENDAR_CACHE["text"]:
        return CALENDAR_CACHE["text"]
    ahora_pe = datetime.now(LIMA_TZ)
    proximos_dias = []
    for i in range(8):
        d = ahora_pe + timedelta(days=i)
        etiqueta = "HOY" if i == 0 else ("MAÑANA" if i == 1 else DIAS_ES[d.weekday()].upper())
        proximos_dias.append(f"{etiqueta} ({DIAS_ES[d.weekday()]} {d.strftime('%Y-%m-%d')})")
    guia_fechas = (
        f"Fecha y hora actual en Lima: {ahora_pe.strftime('%Y-%m-%d %H:%M')}.\n"
        "Guía exacta de fechas próximas: " + ", ".join(proximos_dias) + ".\n"
        f"Horario de visitas: {HORA_INICIO_VISITAS}:00 a {HORA_FIN_VISITAS}:00 (cada visita dura {DURACION_VISITA_MIN} min).\n"
    )
    libres = get_free_slots(n=6)
    if libres:
        lista = "; ".join(f"{format_fecha_es(s, relativo=True)} [{s.isoformat()}]" for s in libres)
        txt = guia_fechas + "HORARIOS LIBRES MÁS PRÓXIMOS (ofrece SOLO de estos, nunca otros): " + lista
    else:
        txt = guia_fechas + "No se pudo leer la agenda: pide al cliente su día y hora preferidos."
    CALENDAR_CACHE["ts"] = now_ts
    CALENDAR_CACHE["text"] = txt
    return txt


def create_calendar_event(nombre, telefono, iso_dt_str, notas="", titulo=None, ubicacion=None):
    """Crea el evento verificando antes que el horario siga libre. Devuelve (ok, detalle, event_id)."""
    try:
        dt_start = datetime.fromisoformat(iso_dt_str)
        if dt_start.tzinfo is None:
            dt_start = dt_start.replace(tzinfo=LIMA_TZ)
        estado, motivo = verificar_slot(dt_start)
        if estado in ["ocupado", "invalido"]:
            return False, estado, None
        dt_end = dt_start + timedelta(minutes=DURACION_VISITA_MIN)
        service = get_calendar_service()
        body = {
            "summary": titulo or f"Visita Santa Teresa - {nombre}",
            "location": ubicacion or "Urb. Santa Teresa, Lambayeque (Intersección 5 de Febrero y Andrés Lastres, frente a loza deportiva)",
            "description": f"Cliente: {nombre}\nWhatsApp: +{telefono}\nNotas: {notas}",
            "start": {"dateTime": dt_start.isoformat(), "timeZone": "America/Lima"},
            "end": {"dateTime": dt_end.isoformat(), "timeZone": "America/Lima"}
        }
        ev = service.events().insert(calendarId=CALENDAR_ID, body=body).execute()
        CALENDAR_CACHE["ts"] = 0
        return True, format_fecha_es(dt_start, relativo=True), ev.get("id")
    except Exception as e:
        print("Error creando evento en Calendar:", e)
        return False, str(e), None


def update_calendar_event(event_id, iso_dt_str):
    """Reprograma una visita ya agendada. Devuelve (ok, detalle)."""
    try:
        dt_start = datetime.fromisoformat(iso_dt_str)
        if dt_start.tzinfo is None:
            dt_start = dt_start.replace(tzinfo=LIMA_TZ)
        estado, _ = verificar_slot(dt_start)
        if estado in ["ocupado", "invalido"]:
            return False, estado
        dt_end = dt_start + timedelta(minutes=DURACION_VISITA_MIN)
        service = get_calendar_service()
        service.events().patch(calendarId=CALENDAR_ID, eventId=event_id, body={
            "start": {"dateTime": dt_start.isoformat(), "timeZone": "America/Lima"},
            "end": {"dateTime": dt_end.isoformat(), "timeZone": "America/Lima"}
        }).execute()
        CALENDAR_CACHE["ts"] = 0
        return True, format_fecha_es(dt_start, relativo=True)
    except Exception as e:
        print("Error reprogramando evento:", e)
        return False, str(e)
