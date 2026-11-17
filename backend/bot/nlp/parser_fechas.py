"""Interpreta fechas y horas escritas en español ('el sábado a las 4 pm')."""
import re
from datetime import datetime, timedelta

from bot.config import HORA_FIN_VISITAS, LIMA_TZ
from bot.nlp.patrones import DIAS_IDX, MESES_IDX, _AMPM_RX, _DIAS_RX, _MESES_RX
from bot.utils.texto import limpiar_texto


def parse_fecha_hora_es(texto, ahora=None):
    """Entiende 'el martes a las 3 pm', 'mañana 10am', 'sábado por la tarde', '28 de octubre 15:00', 'hoy a las 4 y media'."""
    ahora = ahora or datetime.now(LIMA_TZ)
    hoy = ahora.date()
    t = " " + limpiar_texto(texto) + " "
    res = {"fecha": None, "hora": None, "minuto": 0, "turno": None}

    if re.search(r"\b(?:por|en|de|a|para) la manana\b|\b(?:en|por) las mananas\b|\btemprano\b", t):
        res["turno"] = "manana"
    if re.search(r"\b(?:por|en|de|a|para) la (?:tarde|tardecita)\b|\b(?:en|por) las tardes\b", t):
        res["turno"] = "tarde"
    if re.search(r"\b(?:por|en|de|a|para) la noche\b|\bnoche\b", t):
        res["turno"] = "noche"
    t = re.sub(r"\b(?:por|en|de|a|para) la (?:manana|tarde|tardecita|noche)\b|\b(?:en|por) las (?:mananas|tardes)\b", " ", t)

    # --- Día ---
    dia_semana_hoy = False
    if re.search(r"\bpasado manana\b", t):
        res["fecha"] = hoy + timedelta(days=2)
    elif re.search(r"\bhoy\b", t):
        res["fecha"] = hoy
    elif re.search(r"\bmanana\b", t):
        res["fecha"] = hoy + timedelta(days=1)

    m_dia = re.search(rf"\b(?:(proximo|siguiente)\s+)?({_DIAS_RX})\b", t)
    if m_dia and res["fecha"] is None:
        delta = (DIAS_IDX[m_dia.group(2)] - hoy.weekday()) % 7
        if m_dia.group(1) and delta == 0:
            delta = 7
        dia_semana_hoy = delta == 0
        res["fecha"] = hoy + timedelta(days=delta)

    m_fecha = re.search(rf"\b(\d{{1,2}})\s+de\s+({_MESES_RX})\b", t)
    m_barra = re.search(r"\b(\d{1,2})/(\d{1,2})(?:/\d{2,4})?\b", t)
    m_num = re.search(
        rf"\b(?:(?:el|este|para el)\s+|(?:{_DIAS_RX})\s+)(\d{{1,2}})\b"
        r"(?!\s*(?:%|:|\.\d|a\.?\s?m|p\.?\s?m|h\b|hrs|y media|de la|pisos?|m2|metros|casas?|por ciento))", t
    )
    try:
        if m_fecha:
            d, mes = int(m_fecha.group(1)), MESES_IDX[m_fecha.group(2)]
            f = datetime(hoy.year, mes, d).date()
            res["fecha"] = f if f >= hoy else datetime(hoy.year + 1, mes, d).date()
        elif m_barra:
            d, mes = int(m_barra.group(1)), int(m_barra.group(2))
            f = datetime(hoy.year, mes, d).date()
            res["fecha"] = f if f >= hoy else datetime(hoy.year + 1, mes, d).date()
        elif m_num:
            d = int(m_num.group(1))
            f = datetime(hoy.year, hoy.month, d).date()
            if f < hoy:
                nm = hoy.month % 12 + 1
                f = datetime(hoy.year + (1 if nm == 1 else 0), nm, d).date()
            res["fecha"] = f
    except ValueError:
        pass

    # --- Hora ---
    h, mi, ampm = None, 0, None
    m1 = re.search(rf"\b(\d{{1,2}})[:.](\d{{2}})(?!\d)\s*(?:{_AMPM_RX})?", t)
    m2 = re.search(rf"\b(\d{{1,2}})\s*{_AMPM_RX}", t)
    m3 = re.search(r"\ba\s+las?\s+(\d{1,2})\b(?!\s*%)", t)
    m4 = re.search(r"\b(\d{1,2})\s*(?:hrs?\.?|h)(?![a-z])", t)
    m5 = re.search(r"\blas?\s+(\d{1,2})\b(?!\s*(?:%|casas?|pisos?|unidades|habitaciones|banos|m2|metros|opciones))", t)
    if m1 and int(m1.group(1)) <= 23 and int(m1.group(2)) <= 59:
        h, mi = int(m1.group(1)), int(m1.group(2))
        ampm = m1.group(3)
    elif m2:
        h, ampm = int(m2.group(1)), m2.group(2)
    elif m3:
        h = int(m3.group(1))
    elif m4:
        h = int(m4.group(1))
    elif m5:
        h = int(m5.group(1))
    elif re.search(r"\bmedio ?dia\b", t):
        h = 12
    if h is not None and re.search(rf"\b{h}\s+y\s+media\b", t):
        mi = 30
    if h is not None:
        if ampm:
            if ampm.startswith("p") and h < 12:
                h += 12
            elif ampm.startswith("a") and h == 12:
                h = 0
        elif res["turno"] in ["tarde", "noche"] and h < 12:
            h += 12
        elif res["turno"] != "manana" and 1 <= h <= 7:
            h += 12  # "a las 3" en contexto de visitas = 3 p. m.
        if 0 <= h <= 23:
            res["hora"], res["minuto"] = h, mi

    # "el martes" dicho un martes cuya hora ya pasó => martes siguiente
    if dia_semana_hoy and res["hora"] is not None:
        if datetime(hoy.year, hoy.month, hoy.day, res["hora"], res["minuto"], tzinfo=LIMA_TZ) < ahora:
            res["fecha"] = hoy + timedelta(days=7)
    elif dia_semana_hoy and ahora.hour >= HORA_FIN_VISITAS - 1:
        res["fecha"] = hoy + timedelta(days=7)  # "el domingo" dicho un domingo a las 11 p. m. = el próximo domingo
    return res
