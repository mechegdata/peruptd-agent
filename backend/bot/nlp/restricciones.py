"""Detecta restricciones de horario del cliente ('trabajo hasta las 5', 'después de las 4', 'en la noche').

Una restricción NO es un horario propuesto: 'trabajo hasta las 5 pm' significa que a las 5 pm NO puede.
"""
import re

from bot.utils.texto import limpiar_texto


_HORA_RX = r"(\d{1,2})(?:[:.](\d{2}))?\s*(a\.?\s?m|p\.?\s?m|hrs?|h)?\.?(?![a-z0-9])"
_TRABAJO_RX = (r"(?:trabajo|laboro|estoy (?:en el trabajo|trabajando|en la oficina|ocupad[oa])|"
               r"tengo (?:trabajo|clases?|turno)|estudio|ocupad[oa])")
_SALGO_RX = r"(?:salgo|saldria|me desocupo|me libero|estoy libre|quedo libre|llego|estaria libre)"
_REGLAS = [
    # (regex, tipo, efecto)  efecto: 'desde_mas_1' = libre una hora después; 'desde' = libre desde; 'hasta' = antes de esa hora
    (rf"\b{_TRABAJO_RX}\b[^.,;]{{0,25}}?\bhasta (?:las?|la) {_HORA_RX}", "trabajo", "desde_mas_1"),
    (rf"\b{_SALGO_RX}\b[^.,;]{{0,25}}?\b(?:a|como a|tipo|desde) (?:las?|la) {_HORA_RX}", "trabajo", "desde_mas_1"),
    (rf"\b(?:despues de|luego de|a partir de|pasadas|desde) (?:las?|la) {_HORA_RX}", "general", "desde"),
    (rf"\b(?:antes de|maximo a|hasta antes de) (?:las?|la) {_HORA_RX}", "general", "hasta"),
]


def _a_24h(h, mi, ampm):
    h = int(h)
    mi = int(mi or 0)
    ampm = (ampm or "").replace(".", "").replace(" ", "")
    if ampm.startswith("p") and h < 12:
        h += 12
    elif ampm.startswith("a") and h == 12:
        h = 0
    elif not ampm.startswith("a") and 1 <= h <= 8:
        h += 12  # en contexto de horarios de trabajo/visitas, 'las 5' = 5 p. m.
    return h, mi


def detectar_restriccion_horaria(texto):
    """Devuelve {'tipo', 'desde', 'hasta', 'hora_txt', 'hora_raw'} (horas 0-23; desde/hasta/hora_raw pueden ser None) o None."""
    t = " " + limpiar_texto(texto) + " "
    for rx, tipo, efecto in _REGLAS:
        m = re.search(rx, t)
        if not m:
            continue
        h, mi = _a_24h(m.group(1), m.group(2), m.group(3))
        if not 0 <= h <= 23:
            continue
        hora_txt = f"{h % 12 or 12}{':%02d' % mi if mi else ''} {'a. m.' if h < 12 else 'p. m.'}"
        if efecto == "hasta":
            return {"tipo": tipo, "desde": None, "hasta": h, "hora_txt": hora_txt, "hora_raw": h}
        desde = h + (1 if efecto == "desde_mas_1" else 0) + (1 if mi and efecto == "desde" else 0)
        return {"tipo": tipo, "desde": desde, "hasta": None, "hora_txt": hora_txt, "hora_raw": h}
    if re.search(r"\b(trabajo|laboro|estoy en la oficina)\b[^.;?]{0,15}\b(de lunes a viernes|toda la semana|entre semana|"
                 r"todo el dia|en el dia|de dia|en horario de oficina|mananas? y tardes?)\b|\b(entre semana|de lunes a viernes) trabajo\b", t):
        return {"tipo": "trabajo", "desde": None, "hasta": None, "hora_txt": "", "hora_raw": None}
    t = re.sub(r"\bbuenas? noches\b", " ", t)
    if re.search(r"\b(en la noche|por la noche|de noche|en las noches|por las noches|a la noche)\b", t):
        return {"tipo": "noche", "desde": 19, "hasta": None, "hora_txt": "la noche"}
    if re.search(r"\b(hora de(l)? almuerzo|hora de refrigerio|mi refrigerio|mi almuerzo)\b", t):
        return {"tipo": "almuerzo", "desde": 12, "hasta": 14, "hora_txt": "tu hora de almuerzo"}
    return None


def cumple_restriccion(dt, restr, duracion_min=60):
    """True si el horario dt respeta la restricción. La restricción de 'trabajo' no aplica sábados ni domingos."""
    if not restr:
        return True
    if restr["tipo"] == "trabajo" and dt.weekday() >= 5:
        return True
    if restr.get("desde") is not None and dt.hour < restr["desde"]:
        return False
    if restr.get("hasta") is not None and (dt.hour * 60 + dt.minute + duracion_min) > restr["hasta"] * 60:
        return False
    return True
