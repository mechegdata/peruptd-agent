"""Motor de agenda: 3 horarios reales libres que respetan lo que dijo el cliente (día, hora, "salgo del trabajo a
las 6"). La búsqueda en el calendario se inyecta (por defecto Google Calendar del bot), así el motor se prueba sin red."""
from datetime import datetime, timedelta

from bot.engines.textos import L

DIAS = {"es": ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"], "en": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]}
MESES = {"es": ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"],
         "en": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]}
NUMEROS = ["1️⃣", "2️⃣", "3️⃣"]


def _minutos(hhmm):
    h, m = map(int, hhmm.split(":"))
    return h * 60 + m


def dia_objetivo(relativo, hoy):
    if relativo == "TODAY":
        return hoy
    if relativo == "TOMORROW":
        return hoy + timedelta(days=1)
    objetivo = {"THIS_SATURDAY": 5, "THIS_SUNDAY": 6, "MONDAY": 0}.get(relativo)
    if objetivo is None:
        return None
    return hoy + timedelta(days=((objetivo - hoy.weekday()) % 7) or 7)


def etiqueta(dt, idioma, hoy):
    hora = dt.strftime("%I:%M %p").lstrip("0") if idioma == "en" else f"{dt.hour % 12 or 12}:{dt.minute:02d} {'p. m.' if dt.hour >= 12 else 'a. m.'}"
    if dt.date() == hoy + timedelta(days=1):
        dia = L(idioma, "Tomorrow", "Mañana")
    elif dt.date() == hoy:
        dia = L(idioma, "Today", "Hoy")
    else:
        dia = f"{DIAS[idioma][dt.weekday()].capitalize()} {dt.day} {MESES[idioma][dt.month - 1]}"
    return f"{dia} · {hora}"


def proponer(entidades, buscar_libres, ahora=None, n=3):
    """entidades: NormalizedTurn.entities (dict). buscar_libres: get_free_slots(n, dia=None, filtro=None, excluir=None)."""
    ahora = ahora or datetime.now()
    minimo = _minutos(entidades["work_end_hour"]) + 30 if entidades.get("work_end_hour") else 0
    pedido = _minutos(entidades["proposed_time"]) if entidades.get("proposed_time") else 0
    dia = dia_objetivo(entidades.get("proposed_date_relative"), ahora.date())

    def ese_dia(dt):
        return dt.hour * 60 + dt.minute >= max(minimo, pedido)

    def otros_dias(dt):
        return dt.hour * 60 + dt.minute >= minimo

    slots = list(buscar_libres(n=2, dia=dia, filtro=ese_dia)) if dia else []
    extra = buscar_libres(n=n, filtro=otros_dias, excluir=[s.isoformat() for s in slots])
    for s in extra:
        if len(slots) >= n:
            break
        if s not in slots:
            slots.append(s)
    return sorted(slots)[:n]


def texto_opciones(slots, entidades, idioma, hoy):
    if not slots:
        return L(idioma, "Let me check the calendar with the team and I'll send you times shortly 🙏",
                 "Déjame revisar la agenda con el equipo y te paso horarios en un momento 🙏")
    nota = ""
    if entidades.get("work_end_hour"):
        nota = L(idioma, f" (you're off at {entidades['work_end_hour']}, so after that)", f" (sales del trabajo a las {entidades['work_end_hour']}, así que después)")
    lineas = "\n".join(f"{NUMEROS[i]} {etiqueta(s, idioma, hoy)}" for i, s in enumerate(slots))
    return L(idioma, f"I checked the live calendar{nota}:\n{lineas}\nReply 1, 2 or 3 👍",
             f"Revisé la agenda real{nota}:\n{lineas}\nResponde 1, 2 o 3 👍")
