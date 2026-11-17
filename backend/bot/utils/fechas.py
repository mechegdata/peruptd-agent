"""Formato de fechas/horas en español y utilidades de zona horaria (Lima)."""
from datetime import datetime, timedelta, timezone

from bot.config import HORARIO_PRUDENTE, LIMA_TZ


DIAS_ES = {
    0: "lunes", 1: "martes", 2: "miércoles", 3: "jueves",
    4: "viernes", 5: "sábado", 6: "domingo"
}


MESES_ES = {
    1: "enero", 2: "febrero", 3: "marzo", 4: "abril",
    5: "mayo", 6: "junio", 7: "julio", 8: "agosto",
    9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre"
}


def format_hora_es(dt_obj):
    h12 = dt_obj.hour % 12 or 12
    sufijo = "a. m." if dt_obj.hour < 12 else "p. m."
    return f"{h12}:{dt_obj.minute:02d} {sufijo}"


def a_las(dt_obj):
    return ("a la " if dt_obj.hour % 12 == 1 else "a las ") + format_hora_es(dt_obj)


def format_fecha_es(dt_obj, relativo=False):
    dt_obj = dt_obj.astimezone(LIMA_TZ) if dt_obj.tzinfo else dt_obj
    dia_sem = DIAS_ES[dt_obj.weekday()]
    mes = MESES_ES[dt_obj.month]
    sufijo = ""
    if relativo:
        delta = (dt_obj.date() - datetime.now(LIMA_TZ).date()).days
        sufijo = " (hoy)" if delta == 0 else (" (mañana)" if delta == 1 else "")
    return f"{dia_sem} {dt_obj.day} de {mes} {a_las(dt_obj)}{sufijo}"


def _ahora():
    return datetime.now(LIMA_TZ)


def _ts(valor):
    try:
        dt = datetime.fromisoformat(valor) if valor else None
        if dt and dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _en_horario_prudente(dt):
    hm = dt.strftime("%H:%M")
    return HORARIO_PRUDENTE[0] <= hm < HORARIO_PRUDENTE[1]


def _proxima_hora_prudente(dt):
    """Si dt cae en horario de silencio, lo mueve al inicio del horario prudente siguiente."""
    dt = dt.astimezone(LIMA_TZ)
    h, m = [int(x) for x in HORARIO_PRUDENTE[0].split(":")]
    if _en_horario_prudente(dt):
        return dt
    inicio = dt.replace(hour=h, minute=m, second=0, microsecond=0)
    return inicio if dt < inicio else inicio + timedelta(days=1)
