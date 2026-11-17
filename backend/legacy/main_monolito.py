import os
import re
import json
import time
import threading
import unicodedata
import difflib
import requests
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from flask import Flask, request, jsonify
from supabase import create_client
import google.auth
from googleapiclient.discovery import build

app = Flask(__name__)
LIMA_TZ = ZoneInfo("America/Lima")

VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "SAGUE2026")
FB_PAGE_ID = os.environ.get("FB_PAGE_ID", "100000000000000")
IG_ACCOUNT_ID = os.environ.get("IG_ACCOUNT_ID", "")
WA_PHONE_ID = os.environ.get("WA_PHONE_ID", "100000000000000")
META_TOKEN = os.environ.get("META_ACCESS_TOKEN")
WA_TOKEN = os.environ.get("WA_ACCESS_TOKEN") or META_TOKEN
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://example-project.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
CALENDAR_ID = os.environ.get("CALENDAR_ID", "calendar@example.com")
OWNER_WA = os.environ.get("OWNER_WA", "51900000000")

# --- Configuración de agenda de visitas ---
HORA_INICIO_VISITAS = int(os.environ.get("HORA_INICIO_VISITAS", "9"))    # primera visita 9:00 a. m.
HORA_FIN_VISITAS = int(os.environ.get("HORA_FIN_VISITAS", "18"))         # la visita debe terminar a las 6:00 p. m.
DURACION_VISITA_MIN = int(os.environ.get("DURACION_VISITA_MIN", "60"))
MIN_ANTICIPACION_HORAS = float(os.environ.get("MIN_ANTICIPACION_HORAS", "2"))
DIAS_ATENCION = {int(d) for d in os.environ.get("DIAS_ATENCION", "0,1,2,3,4,5,6").split(",") if d.strip()}  # 0=lunes
# Si es "true", antes de confirmar la cita se pregunta 1 vez si tiene inicial / crédito (Estrategia: agendar a calificados)
# "false" (por defecto): se acepta cualquier hora que proponga el cliente si está libre en Calendar.
# HORA_INICIO/FIN_VISITAS solo definen qué horarios SUGIERE el bot.
RESTRINGIR_HORARIO_PROPUESTO = os.environ.get("RESTRINGIR_HORARIO_PROPUESTO", "false").lower() == "true"
EXIGIR_FILTRO_FINANCIERO = os.environ.get("EXIGIR_FILTRO_FINANCIERO", "true").lower() == "true"
# Tiempo máximo total para intentar Gemini (todos los modelos). Si se pasa, responde el motor de respaldo.
GEMINI_PRESUPUESTO_SEG = float(os.environ.get("GEMINI_PRESUPUESTO_SEG", "15"))
# "true" solo si el servidor mantiene CPU fuera del request (p. ej. Cloud Run con CPU siempre asignada)
PROCESAR_EN_SEGUNDO_PLANO = os.environ.get("PROCESAR_EN_SEGUNDO_PLANO", "false").lower() == "true"
GEMINI_MODELS = [m.strip() for m in os.environ.get(
    "GEMINI_MODELS", "gemini-3.8-flash,gemini-2.5-flash,gemini-2.0-flash,gemini-1.5-flash"
).split(",") if m.strip()]

MAPS_URL = os.environ.get("MAPS_URL", "https://maps.app.goo.gl/dQp7Sj5MFXGJxzMq8")
DEFAULT_BUCKET = f"{SUPABASE_URL}/storage/v1/object/public/recursos"

def _url_media(nombres_env, por_defecto):
    """Toma la URL de las variables de entorno solo si es un link real (http/https).
    Si la variable tiene un texto de ejemplo como 'AQUI_PEGA_EL_LINK...', se ignora y se usa el archivo del bucket."""
    for nombre in nombres_env:
        valor = (os.environ.get(nombre) or "").strip()
        if not valor:
            continue
        if valor.lower().startswith(("http://", "https://")):
            return valor
        print(f"⚠️ La variable {nombre} no es un link válido ({valor[:40]}...). Se usará {por_defecto}")
    return por_defecto


URL_FICHA_TECNICA = _url_media(["URL_FICHA_TECNICA", "PDF_FICHA_URL"], f"{DEFAULT_BUCKET}/ficha_tecnica.jpg")
URL_RENDER_GRIS = _url_media(["URL_RENDER_GRIS", "RENDER_COCINA_1_URL"], f"{DEFAULT_BUCKET}/cocina_2.jpg")  # gris = cocina_2.jpg
URL_RENDER_MADERA = _url_media(["URL_RENDER_MADERA", "RENDER_COCINA_2_URL"], f"{DEFAULT_BUCKET}/cocina_1.jpg")  # madera = cocina_1.jpg

supabase = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None
CALENDAR_CACHE = {"ts": 0, "text": ""}
PROCESSED_IDS = set()
PENDING_FORM_TIMERS = {}

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


def normalize_pe_phone(raw):
    if not raw:
        return None
    digs = re.sub(r"\D", "", str(raw))
    if digs.startswith("00"):
        digs = digs[2:]
    if len(digs) == 9 and digs.startswith("9"):
        return "51" + digs
    if len(digs) == 11 and digs.startswith("519"):
        return digs
    if len(digs) >= 10:
        return digs  # número internacional (cliente en el extranjero): no se modifica
    return None


def extract_phone_from_text(text):
    if not text:
        return None
    m = re.search(r"(?:\+?51)?\s*(9(?:[\s\-]*\d){8})", text)
    if m:
        return normalize_pe_phone(m.group(0))
    return None


def parse_lead_form_text(text):
    if not text:
        return {}
    low = text.lower()
    if "filled out your form" not in low and "completé el formulario" not in low and "cómo planeas realizar la compra" not in low:
        return {}
    info = {"es_formulario": True}
    m_name = re.search(r"(?i)full name:\s*([^\n\r]+)", text)
    if m_name:
        info["nombre"] = m_name.group(1).strip().title()
    m_phone = re.search(r"(?i)phone number:\s*([^\n\r]+)", text)
    if m_phone:
        info["telefono"] = normalize_pe_phone(m_phone.group(1))
    m_pago = re.search(r"(?i)c[oó]mo planeas realizar la compra\?:\s*([^\n\r]+)", text)
    if m_pago:
        info["forma_pago"] = m_pago.group(1).strip()
    m_cocina = re.search(r"(?i)qu[eé] estilo prefieres\?:\s*([^\n\r]+)", text)
    if m_cocina:
        info["estilo_cocina"] = m_cocina.group(1).strip()
    m_presup = re.search(r"(?i)rango de inversi[oó]n\?:\s*([^\n\r]+)", text)
    if m_presup:
        info["en_presupuesto"] = m_presup.group(1).strip()
    return info


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


def _slot_valido_por_horario(dt_start, ahora=None, estricto=True):
    """Valida anticipación mínima y, si estricto, día y franja de visitas sugeridas. Devuelve (ok, motivo)."""
    ahora = ahora or datetime.now(LIMA_TZ)
    dt_end = dt_start + timedelta(minutes=DURACION_VISITA_MIN)
    if dt_start < ahora + timedelta(hours=MIN_ANTICIPACION_HORAS):
        return False, "pasado"
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


def get_free_slots(n=3, dia=None, turno=None, excluir=None, dias_busqueda=14, dias_semana=None, excluir_fechas=None):
    """
    Horarios libres más próximos. Sin 'dia': máximo 2 por día (el 1ro libre de la mañana y el 1ro de la tarde)
    para dar variedad. Con 'dia' (date): los primeros libres de ese día. turno: 'manana' | 'tarde' | None.
    dias_semana: set de weekday() permitidos (ej. {5, 6} = fin de semana). excluir_fechas: fechas a saltar.
    """
    ahora = datetime.now(LIMA_TZ)
    excluir = set(excluir or [])
    excluir_fechas = set(excluir_fechas or [])
    if dia:
        fechas = [dia]
    else:
        fechas = [(ahora + timedelta(days=i)).date() for i in range(dias_busqueda)]
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
            if dt.isoformat() in excluir:
                continue
            ok, _ = _slot_valido_por_horario(dt, ahora)
            if ok and not _choca(dt, busy):
                del_dia.append(dt)
        if dia:
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


def create_calendar_event(nombre, telefono, iso_dt_str, notas=""):
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
            "summary": f"Visita Santa Teresa - {nombre}",
            "location": "Urb. Santa Teresa, Lambayeque (Intersección 5 de Febrero y Andrés Lastres, frente a loza deportiva)",
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


# =====================================================================
# MOTOR DE AGENDA DETERMINÍSTICO
# Se ejecuta ANTES de Gemini para los mensajes de agendamiento, así la
# cita se concreta aunque el LLM falle. Guarda el estado en leads.interes:
#   etapa: ofrecio_horarios | pregunto_financiamiento | confirmar_horario | agendado
#   slot_propuesto, slots_ofrecidos, fin_modalidad, fin_inicial,
#   fin_credito_aprobado, pregunta_fin_pendiente, cita_agendada, fecha_cita, evento_id
# =====================================================================
DIAS_IDX = {"lunes": 0, "martes": 1, "miercoles": 2, "jueves": 3, "viernes": 4, "sabado": 5, "domingo": 6}
MESES_IDX = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12
}
_DIAS_RX = "lunes|martes|miercoles|jueves|viernes|sabado|domingo"
_MESES_RX = "|".join(MESES_IDX.keys())
_AMPM_RX = r"(a\.?\s?m|p\.?\s?m)\.?(?![a-z])"

VISITA_RE = re.compile(
    r"\b(visita\w*|visitar\w*|agend\w*|cita|recorr\w*|horarios?|disponibilidad|conocer\w*|mirar\w*|"
    r"ir a ver\w*|pasar a ver|dar(?:me|nos)? una vuelta|puedo ir|podemos ir|podria ir|quiero ir|queremos ir|"
    r"cuando puedo|cuando podria|a que hora|verlas|verla|"
    r"ver (?:la|las|el|los|esa|esas) (?:casas?|propiedad\w*|inmuebles?|viviendas?|proyecto|unidad\w*))\b"
)
VISITA_FUERTE_RE = re.compile(r"\b(visita\w*|visitar\w*|agend\w*|cita|ir a ver\w*|quiero ir|puedo ir|recorr\w*)\b")
MATERIAL_RE = re.compile(r"\b(plano\w*|ficha\w*|render\w*|fotos?|fotitos?|fotografias?|pdf|imagen\w*|video\w*|distribucion|cocinas?|reposteros?|brochure|catalogo)\b")
POSTERGAR_RE = re.compile(
    r"\b(te|le|les) (confirmo|aviso|escribo|llamo|comento|respondo)\b|\blo (pienso|consulto|converso|voy a pensar|evaluo)\b|"
    r"\b(despues|luego|mas tarde) (te|le)\b"
)
AFIRMA_RE = re.compile(
    r"^(si+|sip|claro|ok+|okey|okay|dale|perfecto|listo|de acuerdo|confirmo|confirmado|va|ya|esta bien|"
    r"me parece bien|excelente|genial|correcto|por supuesto|sale|bueno|mantenla|mantengala|mantenlo|reservala|agendala)\b"
)
NIEGA_RE = re.compile(
    r"^(no+|nop|nope|todavia no|aun no|no todavia|no aun|tampoco|nada aun|aun nada|todavia nada|"
    r"no tengo|todavia|aun)\b"
)
RECHAZO_RE = re.compile(
    r"^(ninguno|ninguna|ningun|ni uno|ni una|tampoco|esos no|esas no|no me (acomoda|queda|conviene|sirve|alcanza)|"
    r"no puedo|no podre|no podria|no estoy|no,? otro|no,? otra|otro dia|otra hora|otro horario|otra fecha)\b|"
    r"\b(ninguno|ninguna) (me|de)\b|\bno me (acomoda|acomodan|quedan?|conviene|convienen|sirven?)\b|"
    r"\b(otro dia|otros dias|otro horario|otros horarios|otra fecha|mas adelante|mas tarde no)\b"
)
PREGUNTA_INFO_RE = re.compile(
    r"\b(como seria|como es|como funciona|como hago|cuanto seria|cuanto es|cuanto deberia|cuanto necesito|cuanto tendria|"
    r"cuanto pagaria|que necesito|cuales son|una consulta|requisitos|procedimiento|proceso|se puede financiar|"
    r"tienen financiamiento|hay financiamiento|dan financiamiento|financian|financiar|facilidades|credito directo|en cuotas|a plazos)\b"
)
NEG_CLAUSULA_RE = re.compile(r"\b(no|sin|ni|tampoco|todavia no|aun no|nada)\b")


def sin_tildes(s):
    s = unicodedata.normalize("NFD", (s or "").lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def limpiar_texto(s):
    t = sin_tildes(s)
    t = re.sub(r"[¿?¡!\"“”]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def parse_fecha_hora_es(texto, ahora=None):
    """Entiende 'el martes a las 3 pm', 'mañana 10am', 'sábado por la tarde', '28 de octubre 15:00', 'hoy a las 4 y media'."""
    ahora = ahora or datetime.now(LIMA_TZ)
    hoy = ahora.date()
    t = " " + limpiar_texto(texto) + " "
    res = {"fecha": None, "hora": None, "minuto": 0, "turno": None}

    if re.search(r"\b(?:por|en|de|a) la manana\b|\btemprano\b", t):
        res["turno"] = "manana"
    if re.search(r"\b(?:por|en|de|a) la tarde\b", t):
        res["turno"] = "tarde"
    if re.search(r"\b(?:por|en|de|a) la noche\b|\bnoche\b", t):
        res["turno"] = "noche"
    t = re.sub(r"\b(?:por|en|de|a) la (?:manana|tarde|noche)\b", " ", t)

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
    return res


def detectar_financiamiento(texto):
    """Lee por cláusulas para entender cosas como 'no tengo crédito aprobado pero sí tengo inicial'."""
    t = limpiar_texto(texto)
    out = {"modalidad": None, "inicial": None, "credito_aprobado": None}
    nada = bool(re.search(r"\b(ni nada|no tengo nada|nada todavia|todavia nada|aun nada|nada aun)\b", t))
    for c in re.split(r"\bpero\b|\baunque\b|,|;|\.|\by\b|\bo sea\b", t):
        c = c.strip()
        if not c:
            continue
        neg = bool(NEG_CLAUSULA_RE.search(c))
        # "¿Cuánto sería una inicial adecuada?" pregunta, no afirma que la tenga
        es_pregunta_c = bool(re.search(r"\b(cuant\w*|como|cual\w*|que|donde|requisitos?)\b", c)) and not re.search(
            r"\b(tengo|tenemos|cuento|contamos|dispongo|disponemos|junte|juntamos|ahorre|ahorramos|aprobaron)\b", c)
        if re.search(r"\b(al contado|contado|efectivo|cash|fondos propios|sin credito|sin banco)\b", c) and not re.search(r"\bno\b.*contado", c):
            if not es_pregunta_c:
                out["modalidad"] = "contado"
            continue
        if es_pregunta_c:
            if re.search(r"\b(credito|hipotecari\w*|banco|prestamo|financiamiento)\b", c) and not neg:
                out["modalidad"] = out["modalidad"] or "credito"
            continue
        if re.search(r"\binicial\b|\b(10|20) ?%|\b(10|20) por ciento|ahorrad|mis ahorros", c):
            out["inicial"] = not neg
        if re.search(r"pre ?aprobad|aprobad|aprobaron|calific", c):
            out["credito_aprobado"] = not neg
            out["modalidad"] = out["modalidad"] or "credito"
        elif re.search(r"\b(credito|hipotecari\w*|banco|prestamo|financiamiento|financiad\w*|mivivienda|techo propio)\b", c) and not neg:
            out["modalidad"] = out["modalidad"] or "credito"
    if nada:
        out["inicial"] = False if out["inicial"] is None else out["inicial"]
        out["credito_aprobado"] = False if out["credito_aprobado"] is None else out["credito_aprobado"]
    return out


def estado_financiero(meta):
    """True = calificado (contado / inicial / crédito aprobado), False = sin inicial ni crédito, None = no sabemos."""
    if meta.get("fin_modalidad") == "contado":
        return True
    if meta.get("fin_inicial") is True or meta.get("fin_credito_aprobado") is True:
        return True
    if meta.get("fin_inicial") is False and meta.get("fin_credito_aprobado") is not True:
        return False
    fp = meta.get("forma_pago")
    if fp and fp not in ["Por consultar", "Contado / Crédito Hipotecario"]:
        d = detectar_financiamiento(fp)
        if d["modalidad"] == "contado" or d["inicial"] is True or d["credito_aprobado"] is True:
            return True
        if d["inicial"] is False:
            return False
    return None


def resumen_financiero(meta):
    calif = estado_financiero(meta)
    if meta.get("fin_modalidad") == "contado":
        return "Contado"
    partes = []
    if meta.get("fin_modalidad") == "credito":
        partes.append("Crédito hipotecario")
    if meta.get("fin_inicial") is True:
        partes.append("con inicial")
    if meta.get("fin_inicial") is False:
        partes.append("SIN inicial (ofrecer asesor hipotecario)")
    if meta.get("fin_credito_aprobado") is True:
        partes.append("crédito preaprobado")
    if meta.get("fin_credito_aprobado") is False:
        partes.append("sin crédito aprobado aún")
    if not partes:
        return meta.get("forma_pago") or ("Por validar" if calif is None else "")
    return ", ".join(partes)


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


def pregunta_por_financiamiento(texto):
    """True si alguna pregunta (¿...?) del texto le consulta al cliente por su inicial / crédito / contado."""
    return any(re.search(r"(?i)inicial|preaprobado|contado o", q) for q in re.findall(r"¿[^?¿]*\?", texto or ""))


def quitar_preguntas_financiamiento(texto):
    t = re.sub(r"¿[^?¿]*(?:inicial|preaprobado|contado o)[^?¿]*\?\s*(?:😊)?", "", texto or "")
    t = re.sub(r"(?i)\b(cuéntame|coméntame)[,:]?\s*$", "", t.strip())
    return re.sub(r"\n{3,}", "\n\n", t).strip()


def inferir_estado_de_historial(meta, mensajes_db):
    """Reconstruye lo que el cliente YA dijo sobre cómo pagará (contado / crédito / inicial) leyendo todo el historial,
    incluidas respuestas cortas ("no todavía") a preguntas del bot o del asesor humano. Solo completa lo que falte."""
    visto = {}
    prev_bot = ""
    for m in mensajes_db or []:
        txt = m.get("contenido") or ""
        if m.get("rol") != "user":
            prev_bot = txt
            continue
        d = detectar_financiamiento(txt)
        tl = limpiar_texto(txt)
        if all(v is None for v in d.values()) and pregunta_por_financiamiento(prev_bot) and len(tl) <= 60:
            if NIEGA_RE.match(tl):
                d = {"modalidad": None, "inicial": False, "credito_aprobado": False}
            elif AFIRMA_RE.match(tl):
                d = {"modalidad": None, "inicial": True, "credito_aprobado": None}
        for k_src, k_meta in (("modalidad", "fin_modalidad"), ("inicial", "fin_inicial"), ("credito_aprobado", "fin_credito_aprobado")):
            if d[k_src] is not None:
                visto[k_meta] = d[k_src]
        if pregunta_por_financiamiento(prev_bot):
            visto["_preguntado"] = True
    for k, v in visto.items():
        if k == "_preguntado":
            if not meta.get("veces_pregunta_fin"):
                meta["veces_pregunta_fin"] = 1
        elif meta.get(k) is None:
            meta[k] = v


DESPEDIDA_RE = re.compile(
    r"^(no+,? (muchas |mil )?gracias|no,? eso (es|seria) todo|no,? nada mas|no,? ninguna|no,? por ahora( no)?|nada mas|eso es todo|eso seria todo|"
    r"seria todo|todo claro|todo bien,? gracias|(ok|okey|okay|ya|listo|perfecto|genial|excelente|bueno|entendido|vale|super)\W*,? (muchas |mil )?gracias|"
    r"(muchas |mil |muchisimas )?gracias+( por (todo|la informacion|la info|su tiempo|tu tiempo|su atencion|tu ayuda))?|"
    r"chao+|chau+|adios|hasta luego|hasta pronto|bendiciones|igualmente|gracias,? igualmente)\W*"
    r"(\s*(muy amable|que tenga\w* (un )?buen\w* (dia|tarde|noche)|bendiciones|saludos|igualmente|👍|🙏|😊))*\W*$"
)
PREGUNTA_OTRA_DUDA_RE = re.compile(r"(?i)(otra|alguna|mas) (duda|pregunta|consulta)|en qu[eé] m[aá]s te puedo ayudar|algo m[aá]s en (lo )?que")


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
    if solo_emoji_ok and (PREGUNTA_OTRA_DUDA_RE.search(ultimo_bot or "") or meta.get("etapa") in ["agendado", "cerrado"]):
        t = "gracias"
    if not t or len(t) > 80 or "?" in (user_text or ""):
        return None
    se_despide = bool(DESPEDIDA_RE.match(t))
    no_simple = bool(re.match(r"^(no+|nop|nope|ninguna|ninguno|nada|no ninguna|no nada|todo ok|todo bien|estoy bien asi|asi esta bien)$", t))
    sin_pendientes = meta.get("etapa") in [None, "", "pregunto_dia", "cerrado", "agendado"]
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


def _resp(texto):
    return {
        "reply_text": texto, "private_reply": "", "ignorar_comentario": False,
        "enviar_ficha_tecnica": False, "enviar_renders_cocina": False,
        "estilo_render_preferido": "ambos", "agendar_visita_iso": "", "_motor_agenda": True
    }


def motor_agenda(user_text, meta, nombre_cliente, telefono, canal, historial_usuario=None):
    """Devuelve una respuesta (dict) si el mensaje es de agendamiento; None para dejarlo a Gemini/fallback.
    Modifica 'meta' con el nuevo estado de la conversación."""
    if canal not in ["whatsapp", "facebook", "instagram"]:
        return None
    t = limpiar_texto(user_text)
    if not t:
        return None
    nom = nombre_cliente.split()[0] if nombre_cliente not in ["Interesado", "Cliente", ""] else ""
    coma_nom = f", {nom}" if nom else ""
    etapa = meta.get("etapa") or ""
    fh = parse_fecha_hora_es(user_text)
    fin = detectar_financiamiento(user_text)
    afirma = bool(AFIRMA_RE.match(t)) and len(t) <= 80 and not t.startswith("si no")
    niega = bool(NIEGA_RE.match(t)) and len(t) <= 60
    # "ninguno", "no puedo", "otro día"... cuando le ofrecimos horarios
    rechaza = bool(RECHAZO_RE.search(t)) and etapa in ["ofrecio_horarios", "confirmar_horario", "agendado", "pregunto_dia", "ofrecio_material",
                                                        "confirmar_asistencia"]
    pref_dias = None
    if re.search(r"\b(fin de semana|fines de semana|finde|sabado o domingo|domingo o sabado)\b", t):
        pref_dias = {5, 6}
    elif re.search(r"\b(entre semana|en la semana|dia de semana|dias de semana|dia util|dias utiles|de lunes a viernes)\b", t):
        pref_dias = {0, 1, 2, 3, 4}

    fin_pendiente = bool(meta.get("pregunta_fin_pendiente"))
    # Respuestas cortas ("sí" / "no todavía") a la pregunta de inicial o crédito
    if all(v is None for v in fin.values()) and fin_pendiente and etapa not in ["confirmar_horario", "ofrecio_asesor", "ofrecio_material"] and not rechaza:
        if niega:
            fin = {"modalidad": None, "inicial": False, "credito_aprobado": False}
        elif afirma and etapa == "pregunto_financiamiento":
            fin = {"modalidad": None, "inicial": True, "credito_aprobado": None}
    hay_fin = any(v is not None for v in fin.values())
    if fin["modalidad"]:
        meta["fin_modalidad"] = fin["modalidad"]
    if fin["inicial"] is not None:
        meta["fin_inicial"] = fin["inicial"]
    if fin["credito_aprobado"] is not None:
        meta["fin_credito_aprobado"] = fin["credito_aprobado"]
    calif = estado_financiero(meta)
    if calif is not None:
        meta["pregunta_fin_pendiente"] = False

    if POSTERGAR_RE.search(t) and not hay_fin:
        return None

    # Preguntas informativas ("¿con banco cómo sería?", "¿cuánto de inicial?") las responde FAQ/Gemini, no el agendador
    es_pregunta_info = ("?" in (user_text or "") or bool(PREGUNTA_INFO_RE.search(t))) and fh["hora"] is None and fh["fecha"] is None
    if es_pregunta_info and not rechaza and not pref_dias and not VISITA_RE.search(t) and not (etapa == "ofrecio_horarios" and elegir_slot_ofrecido(t, meta.get("slots_ofrecidos") or [], fh)):
        return None

    intencion_visita = bool(VISITA_RE.search(t)) or (t in ["2", "2️⃣", "dos", "opcion 2"] and etapa in ["", "agendado"])
    if MATERIAL_RE.search(t) and not VISITA_FUERTE_RE.search(t):
        intencion_visita = False
    en_flujo = etapa in ["ofrecio_horarios", "pregunto_financiamiento", "confirmar_horario", "pregunto_dia"]

    slot_pend = None
    if meta.get("slot_propuesto"):
        try:
            slot_pend = datetime.fromisoformat(meta["slot_propuesto"])
        except Exception:
            slot_pend = None
    if slot_pend is None and (hay_fin or afirma) and historial_usuario and not meta.get("cita_agendada"):
        slot_pend = recuperar_slot_de_historial(historial_usuario)

    # ---------- helpers de respuesta ----------
    def ofrecer(slots, encabezado, pie=""):
        if not slots:
            meta["etapa"] = "pregunto_dia"
            return _resp(
                f"{encabezado}\n\nEn este momento no veo espacios libres en la agenda de los próximos días 😕. "
                "¿Qué día y hora te acomodaría? Me adapto a tu horario y lo coordino directamente con el ingeniero."
            )
        meta["etapa"] = "ofrecio_horarios"
        meta["slots_ofrecidos"] = [s.isoformat() for s in slots]
        txt = (
            f"{encabezado}\n\n{_slots_a_texto(slots)}\n\n"
            "Respóndeme con el número (o dime otro día y hora) y te la dejo registrada al toque."
        )
        if pie:
            txt += f"\n\n{pie}"
        return _resp(txt)

    def alternativas(slot, motivo):
        alt = get_free_slots(n=3, dia=slot.date()) if motivo != "dia" else []
        if not alt:
            alt = get_free_slots(n=3)
        if motivo == "ocupado":
            enc = f"Uy{coma_nom}, el {format_fecha_es(slot, relativo=True)} ya está tomado 😕. Estos son los horarios libres más cercanos:"
        elif motivo == "pasado":
            enc = f"Ese horario ya no llego a coordinarlo con el ingeniero{coma_nom} 😅. Estos son los horarios libres más próximos:"
        elif motivo == "dia":
            enc = f"Ese día no tenemos atención de visitas{coma_nom}. Te propongo estos horarios libres:"
        else:
            enc = f"Ese horario no lo tengo disponible{coma_nom} 😕. Estos son los horarios libres más cercanos a lo que me pides:"
        return ofrecer(alt, enc)

    def reservar(slot):
        notas = f"Pago: {resumen_financiero(meta)} | Cocina: {meta.get('estilo_cocina', 'Por elegir')} | Canal: {canal}"
        ok, det, ev_id = create_calendar_event(nombre_cliente, telefono or "sin número", slot.isoformat(), notas)
        if ok:
            meta.update({
                "cita_agendada": True, "fecha_cita": slot.isoformat(), "evento_id": ev_id or "",
                "ts_cita_creada": datetime.now(timezone.utc).isoformat(), "recordatorio_para": "", "visita_estado": "",
                "pregunta_owner_visita": "", "pregunta_owner_visita_2": "", "rescate_no_asistio": False,
                "etapa": "agendado", "slot_propuesto": "", "slots_ofrecidos": [], "pregunta_fin_pendiente": False,
                "dia_contexto": "", "rechazos_horario": 0
            })
            extra = ""
            if meta.get("fin_modalidad") == "contado":
                extra = "Si deseas, antes de la visita te enviamos la Copia Literal de SUNARP para que tu abogado la revise. "
            elif calif is False:
                extra = ("Ese día también te orientamos con el crédito y, si gustas, te contactamos sin costo con nuestro "
                         "asesor hipotecario aliado para que sepas cuánto te financia el banco. ")
            elif meta.get("fin_inicial") is True and meta.get("fin_credito_aprobado") is not True:
                extra = ("Como ya cuentas con tu inicial, en la visita te entregamos la Copia Literal y HR/PU de SUNARP "
                         "para que tu banco te evalúe el crédito rápido. ")
            try:
                alertar_asesor(f"📅 Nueva visita SAGUE: {nombre_cliente} (+{telefono or 's/n'}) el {det} | Pago: {resumen_financiero(meta)} | Canal: {canal}")
            except Exception:
                pass
            return _resp(
                f"¡Listo{coma_nom}! ✅ Tu visita guiada quedó registrada para el *{det}*\n\n"
                f"📍 Urb. Santa Teresa, Lambayeque (calles 5 de Febrero y Andrés Lastres, frente a la loza deportiva, "
                f"a 1 min de la Av. Ramón Castilla): {MAPS_URL}\n\n"
                "Ese día te mostramos los 3 pisos, los 2 diseños de cocina y te explicamos en obra el Bono Especial de la 1ra Unidad. "
                f"{extra}Si surge algún cambio, me escribes por aquí y lo reprogramamos 😊"
            )
        if det in ["ocupado", "invalido"]:
            return alternativas(slot, "ocupado" if det == "ocupado" else "horario")
        # Error técnico de Calendar: no perder al cliente
        meta["slot_propuesto"] = slot.isoformat()
        meta["etapa"] = "confirmacion_manual"
        try:
            alertar_asesor(f"⚠️ SAGUE: {nombre_cliente} (+{telefono or 's/n'}) pidió visita el {format_fecha_es(slot)}, "
                                   f"pero Calendar falló ({det[:120]}). Regístrala y confírmale manualmente.")
        except Exception:
            pass
        return _resp(
            f"¡Perfecto{coma_nom}! Tomé nota de tu visita para el *{format_fecha_es(slot, relativo=True)}* 🙌. "
            "En unos minutos el ingeniero encargado te confirma por aquí el registro."
        )

    def manejar_slot(slot, confirmado=False):
        # Reprogramación de una cita ya agendada
        if meta.get("cita_agendada") and meta.get("evento_id"):
            ok, det = update_calendar_event(meta["evento_id"], slot.isoformat())
            if ok:
                meta.update({"fecha_cita": slot.isoformat(), "etapa": "agendado", "slot_propuesto": "", "slots_ofrecidos": [],
                             "recordatorio_para": "", "ts_cita_creada": datetime.now(timezone.utc).isoformat()})
                try:
                    alertar_asesor(f"🔁 Visita reprogramada: {nombre_cliente} (+{telefono or 's/n'}) ahora el {det}")
                except Exception:
                    pass
                return _resp(f"¡Hecho{coma_nom}! 🔁 Reprogramé tu visita para el *{det}*\nTe esperamos en Urb. Santa Teresa: {MAPS_URL}")
            if det in ["ocupado", "invalido"]:
                return alternativas(slot, "ocupado" if det == "ocupado" else "horario")
        estado, motivo = verificar_slot(slot)
        if estado == "invalido":
            return alternativas(slot, motivo)
        if estado == "ocupado":
            return alternativas(slot, "ocupado")
        meta["slot_propuesto"] = slot.isoformat()
        meta["slots_ofrecidos"] = []
        fecha_txt = format_fecha_es(slot, relativo=True)
        if not confirmado and calif is None and EXIGIR_FILTRO_FINANCIERO:
            meta["etapa"] = "pregunto_financiamiento"
            meta["pregunta_fin_pendiente"] = True
            ctx = "Como lo evalúas con crédito hipotecario, una" if meta.get("fin_modalidad") == "credito" else "Una"
            return _resp(
                f"¡Claro que sí{coma_nom}! El *{fecha_txt}* está libre ✅ y te lo dejo separado.\n\n"
                f"{ctx} consulta rápida para confirmártelo con el ingeniero: ¿ya cuentas con tu cuota inicial "
                "(desde el 10%, aprox. $13,500 USD) o con un crédito preaprobado en tu banco?"
            )
        if not confirmado and calif is False:
            meta["etapa"] = "confirmar_horario"
            return _resp(
                f"Gracias por contarme{coma_nom} 😊. No te preocupes: como las casas están 100% terminadas y con título en SUNARP, "
                "se compran al contado o con crédito hipotecario, y el banco solo pide desde el 10% de inicial (aprox. $13,500 USD). "
                "Si gustas, te ponemos en contacto sin costo con nuestro asesor hipotecario aliado para que te evalúe y sepas "
                "exactamente cuánto te financian.\n\n"
                f"¿Te mantengo la visita del *{fecha_txt}* para que conozcas las casas y ahí mismo te orientamos con el banco? "
                "Respóndeme *sí* y te la confirmo."
            )
        return reservar(slot)

    # ---------- 0c) Respuesta al recordatorio de visita ----------
    if etapa == "confirmar_asistencia" and (afirma or niega) and not rechaza and fh["hora"] is None and fh["fecha"] is None:
        if afirma:
            meta.update({"etapa": "agendado", "asistencia_confirmada": True})
            try:
                f_c = format_fecha_es(datetime.fromisoformat(meta["fecha_cita"]), relativo=True)
            except Exception:
                f_c = "la fecha acordada"
            alertar_asesor(f"✅ SAGUE: {nombre_cliente} (+{telefono or 's/n'}) CONFIRMÓ su visita del {f_c}.")
            return _resp(f"¡Perfecto{coma_nom}! 🙌 Te esperamos el *{f_c}* en Urb. Santa Teresa, frente a la loza deportiva. "
                         f"Aquí el mapa por si acaso: {MAPS_URL}")
        nom_c = nombre_cliente.split()[0] if nombre_cliente not in ["Interesado", "Cliente", ""] else ""
        return ofrecer(get_free_slots(n=3), f"Sin problema{coma_nom} 😊, la reprogramamos. Estos son los próximos horarios libres:")

    # ---------- 0d) Aceptó que le enviemos la Copia Literal (seguimiento post-visita, compra al contado) ----------
    if etapa == "ofrecio_copia" and (afirma or niega):
        meta["etapa"] = ""
        if afirma:
            alertar_asesor(f"📄 SAGUE: {nombre_cliente} (+{telefono or 's/n'}) pidió la COPIA LITERAL de SUNARP para su abogado. Envíasela hoy.")
            return _resp(f"¡Listo{coma_nom}! 📄 Hoy mismo te hacemos llegar la Copia Literal completa por aquí para que tu abogado la revise. "
                         "Cualquier consulta legal que tenga, con gusto la vemos.")
        return _resp(f"Perfecto{coma_nom} 😊. Cuando la necesites, me avisas y te la enviamos al toque.")

    # ---------- 0b) Nos dijo su tope de presupuesto (lead de formulario con "No está en mi rango") ----------
    if etapa == "pregunto_presupuesto":
        m_monto = re.search(r"(\d{2,3})(?:[.,\s]?(\d{3}))?\s*(mil|k|lucas)?", t.replace("$", " "))
        if m_monto and fh["hora"] is None:
            monto = int(m_monto.group(1) + m_monto.group(2)) if m_monto.group(2) else int(m_monto.group(1)) * 1000
            meta["presupuesto_tope"] = monto
            meta["etapa"] = ""
            try:
                alertar_asesor(f"💵 SAGUE: {nombre_cliente} (+{telefono or 's/n'}) indicó un tope de {_usd(monto)} USD. Pago: {resumen_financiero(meta)}.")
            except Exception:
                pass
            if monto >= PRECIO_LISTA_USD * 0.88:
                intro = (f"¡Gracias por la confianza{coma_nom}! 😊 Con {_usd(monto)} estamos muy cerca: con el Bono Especial de la 1ra Unidad "
                         "y la opción de entregarla sin reposteros, podemos evaluar un ajuste que te encaje. Los números finos los cerramos en la visita "
                         "directamente con los propietarios.")
            else:
                intro = (f"¡Gracias por la confianza{coma_nom}! 😊 Ese monto está algo por debajo del valor de las casas, pero con el Bono Especial "
                         "de la 1ra Unidad y la opción sin reposteros podemos revisar números juntos en la visita, sin compromiso.")
            nom_c = nombre_cliente.split()[0] if nombre_cliente not in ["Interesado", "Cliente", ""] else ""
            return _resp(intro + "\n\n" + cierre_contextual(meta, nom_c))

    # ---------- 0a) Aceptó que el asesor hipotecario lo contacte ----------
    if etapa == "ofrecio_asesor" and (afirma or niega):
        meta["etapa"] = ""
        if afirma:
            meta["asesor_solicitado"] = True
            aviso = (f"📞 SAGUE: {nombre_cliente} (+{telefono or 's/n'}) pidió evaluación con el asesor hipotecario. "
                     f"Situación: {resumen_financiero(meta)}. Contáctalo hoy.")
            for dest in {OWNER_WA, ASESOR_HIPOTECARIO_WA} - {""}:
                try:
                    send_wa_text(dest, aviso)
                except Exception:
                    pass
            txt = (f"¡Listo{coma_nom}! 🙌 Ya le pasé tus datos a nuestro asesor hipotecario aliado; te escribirá a este número "
                   "para evaluarte sin costo. ")
        else:
            txt = f"Perfecto{coma_nom}, sin problema 😊. "
        nom_c = nombre_cliente.split()[0] if nombre_cliente not in ["Interesado", "Cliente", ""] else ""
        return _resp(txt + "Mientras tanto, lo ideal es que conozcas las casas en persona. " + cierre_contextual(meta, nom_c))

    # ---------- 0) Aceptó que le enviemos planos y renders ----------
    if etapa == "ofrecio_material" and afirma:
        meta["etapa"] = "pregunto_dia"
        r = _resp(
            f"¡Listo{coma_nom}! 📄 Te adjunto los planos de los 3 pisos (ambas casas ya están 100% "
            "terminadas) y los 2 diseños de cocina: Gris Grafito con LED y Madera Rovere con Taupe. "
            "Cuando quieras conocerlas en persona, dime el día y la hora y te reservo la visita 🏡"
        )
        r["enviar_ficha_tecnica"] = True
        r["enviar_renders_cocina"] = True
        return r
    if etapa == "ofrecio_material" and (niega or rechaza):
        meta["etapa"] = "pregunto_dia"
        return _resp(f"Perfecto{coma_nom}, quedo atento por aquí 😊. Cualquier duda o cuando quieras visitarnos, me escribes y te ayudo al toque.")

    # ---------- 1) El cliente propone o elige un horario concreto ----------
    slot_nuevo = None
    if etapa == "ofrecio_horarios" and meta.get("slots_ofrecidos"):
        slot_nuevo = elegir_slot_ofrecido(t, meta["slots_ofrecidos"], fh)
    # "a las 4" justo después de hablar del sábado => sábado a las 4
    if slot_nuevo is None and fh["hora"] is not None and fh["fecha"] is None and en_flujo and meta.get("dia_contexto"):
        try:
            d_ctx = datetime.fromisoformat(meta["dia_contexto"]).date()
            if d_ctx >= datetime.now(LIMA_TZ).date():
                fh["fecha"] = d_ctx
        except Exception:
            pass
    if slot_nuevo is None and fh["hora"] is not None and (fh["fecha"] is not None or en_flujo or intencion_visita or hay_fin):
        slot_nuevo = construir_slot(fh)
    if slot_nuevo is not None:
        return manejar_slot(slot_nuevo)

    # ---------- 1b) No le acomodan los horarios ofrecidos ("ninguno", "no puedo", "otro día") ----------
    if rechaza or (pref_dias and (en_flujo or intencion_visita)):
        rechazos = int(meta.get("rechazos_horario") or 0) + (1 if rechaza else 0)
        meta["rechazos_horario"] = rechazos
        if rechazos >= 4 and not (fh["fecha"] or fh["turno"] or pref_dias):
            meta["etapa"] = "ofrecio_material"
            meta["slots_ofrecidos"] = []
            return _resp(
                f"Entiendo{coma_nom}, sin ningún problema 😊. Cuando tengas un espacio libre me escribes por aquí y te reservo "
                "el horario al instante. Mientras tanto, ¿te envío los planos de los 3 pisos y los 2 diseños de cocina para que los vayas revisando?"
            )
        if rechazos >= 3 and not (fh["fecha"] or fh["turno"] or pref_dias):
            # No insistir con más listas: pasar a conversación abierta y avisar al asesor humano
            meta["etapa"] = "pregunto_dia"
            meta["slots_ofrecidos"] = []
            try:
                alertar_asesor(f"🔔 SAGUE: {nombre_cliente} (+{telefono or 's/n'}) rechazó varios horarios. "
                                       f"Último mensaje: \"{user_text[:150]}\". Conviene llamarle para coordinar.")
            except Exception:
                pass
            return _resp(
                f"Entiendo{coma_nom}, no te preocupes 😊. Cuéntame con calma qué día y a qué hora te quedaría mejor "
                "(me adapto a tu horario, incluso temprano o al final del día) y lo coordino directamente con el ingeniero. Si prefieres, también te puede llamar "
                "el asesor para cuadrarlo en 2 minutos, ¿te parece?"
            )
        vistos = []
        for s in meta.get("slots_ofrecidos") or []:
            try:
                vistos.append(datetime.fromisoformat(s))
            except Exception:
                pass
        if fh["fecha"] is not None:
            slots = get_free_slots(n=3, dia=fh["fecha"], turno=fh["turno"], excluir=[v.isoformat() for v in vistos])
        else:
            slots = get_free_slots(n=3, turno=fh["turno"], dias_semana=pref_dias,
                                   excluir_fechas=None if pref_dias else {v.date() for v in vistos})
            if not slots:
                slots = get_free_slots(n=3, turno=fh["turno"], dias_semana=pref_dias, excluir=[v.isoformat() for v in vistos])
        if meta.get("cita_agendada") and rechaza:
            enc = f"Sin problema{coma_nom}, la reprogramamos 😊. Estas son otras opciones libres:"
        elif pref_dias == {5, 6}:
            enc = f"¡Claro{coma_nom}! Para el fin de semana tengo libres estos horarios:"
        elif pref_dias:
            enc = f"¡Claro{coma_nom}! Entre semana tengo libres estos horarios:"
        else:
            enc = f"Sin problema{coma_nom} 😊 Te busco otras opciones en días distintos:"
        return ofrecer(
            slots, enc,
            "Si ninguno te acomoda, dime el día y la hora que prefieras y me adapto a tu horario."
        )

    # ---------- 2) Esperábamos un "sí" para mantener el horario ----------
    if etapa == "confirmar_horario" and slot_pend is not None:
        if afirma:
            return manejar_slot(slot_pend, confirmado=True)
        if niega or re.search(r"\botro (dia|horario)\b", t):
            return ofrecer(get_free_slots(n=3), f"Sin problema{coma_nom}. Estos son los próximos horarios libres por si te acomoda otro:")
        if hay_fin:
            return manejar_slot(slot_pend)

    # ---------- 3) Respondió sobre su financiamiento y había un horario pendiente ----------
    if slot_pend is not None and hay_fin and not meta.get("cita_agendada"):
        return manejar_slot(slot_pend)

    # ---------- 4) Respondió sobre su financiamiento sin horario pendiente ----------
    if hay_fin and (fin_pendiente or en_flujo or intencion_visita):
        if calif is True:
            return ofrecer(get_free_slots(n=3), f"¡Excelente{coma_nom}! 🙌 Entonces coordinemos tu visita guiada. Estos son los horarios libres más próximos:")
        if calif is False and "sin_inicial" in (meta.get("ya_explicado") or []) and not meta.get("asesor_solicitado"):
            meta["etapa"] = "ofrecio_asesor"
            return _resp(
                f"Perfecto{coma_nom}, entonces con crédito hipotecario 😊. El paso más rápido es que nuestro asesor hipotecario aliado "
                "te evalúe sin costo y te diga cuánto te financia el banco y cuánto necesitarías de inicial. "
                "¿Quieres que te contacte a este número? Respóndeme *sí* y le paso tus datos."
            )
        if calif is False:
            meta["ya_explicado"] = list(set((meta.get("ya_explicado") or []) + ["sin_inicial"]))
            return ofrecer(
                get_free_slots(n=3),
                f"Gracias por contarme{coma_nom} 😊. Como las casas están 100% terminadas con título en SUNARP, se compran al contado "
                "o con crédito hipotecario (el banco pide desde el 10% de inicial, aprox. $13,500 USD; no manejamos crédito directo). "
                "Si gustas, te contactamos sin costo con nuestro asesor hipotecario aliado para evaluarte.\n\n"
                "Y si deseas conocer las casas mientras tanto, estos son los horarios libres más próximos:"
            )
        if en_flujo or intencion_visita:
            meta["etapa"] = "pregunto_financiamiento"
            meta["pregunta_fin_pendiente"] = True
            return _resp(
                f"¡Perfecto{coma_nom}! Trabajamos con cualquier banco (BCP, BBVA, Interbank, Scotiabank, BanBif). "
                "¿Ya cuentas con tu cuota inicial (desde el 10%, aprox. $13,500 USD) o con un crédito preaprobado? "
                "Así te separo de inmediato el horario de tu visita."
            )

    # ---------- 5) Quiere visitar / pregunta por un día o turno ----------
    if intencion_visita or (en_flujo and (fh["fecha"] is not None or fh["turno"])):
        if meta.get("cita_agendada") and meta.get("fecha_cita") and not (fh["fecha"] or fh["turno"]):
            try:
                f_cita = datetime.fromisoformat(meta["fecha_cita"])
                if f_cita > datetime.now(LIMA_TZ):
                    return _resp(
                        f"¡Ya tienes tu visita registrada{coma_nom}! ✅ Te esperamos el *{format_fecha_es(f_cita, relativo=True)}* "
                        f"en Urb. Santa Teresa: {MAPS_URL}\n\n¿La mantenemos o prefieres cambiarla a otro día/hora?"
                    )
            except Exception:
                pass
        meta["dia_contexto"] = fh["fecha"].isoformat() if fh["fecha"] is not None else ""
        if fh["fecha"] is not None:
            slots = get_free_slots(n=3, dia=fh["fecha"], turno=fh["turno"])
            enc_base = f"Para el {DIAS_ES[fh['fecha'].weekday()]} {fh['fecha'].day} tengo libres estos horarios:"
            if not slots:
                slots = get_free_slots(n=3, turno=fh["turno"])
                enc_base = "Ese día ya no tengo espacios libres 😕, pero estos son los más cercanos:"
        else:
            slots = get_free_slots(n=3, turno=fh["turno"])
            enc_base = "Estos son los horarios libres más próximos para tu visita guiada:"
        saludo = f"¡Con todo gusto{coma_nom}! 😊 Será un gusto recibirte en Urb. Santa Teresa (frente a la loza deportiva). "
        if calif is None and EXIGIR_FILTRO_FINANCIERO and not meta.get("cita_agendada"):
            meta["pregunta_fin_pendiente"] = True
            return ofrecer(
                slots, saludo + enc_base,
                "Y para registrarte con el ingeniero: ¿la compra la evalúas al contado o con crédito hipotecario "
                "(el banco pide desde el 10% de inicial)?"
            )
        if calif is False:
            return ofrecer(
                slots, saludo + enc_base,
                "Te recuerdo que la compra es al contado o con crédito hipotecario (desde 10% de inicial); en la visita te "
                "orientamos y te contactamos sin costo con nuestro asesor hipotecario aliado."
            )
        return ofrecer(slots, saludo + enc_base)

    return None


ALERTA_TEMPLATE = os.environ.get("ALERTA_TEMPLATE", "")  # plantilla aprobada (1 variable) para alertas fuera de las 24 h
ALERTA_ESTADO = {"chequeado": False}


def alertar_asesor(texto):
    """Envía una alerta al asesor (OWNER_WA). Si el mensaje libre falla (por la ventana de 24 h de WhatsApp),
    intenta con una plantilla aprobada. Todo queda en los logs con la etiqueta [ALERTA]."""
    print(f"[ALERTA] {texto}")
    if not ALERTA_ESTADO["chequeado"]:
        ALERTA_ESTADO["chequeado"] = True
        try:
            info = requests.get(f"https://graph.facebook.com/v21.0/{WA_PHONE_ID}", params={"fields": "display_phone_number"},
                                headers={"Authorization": f"Bearer {WA_TOKEN}"}, timeout=10).json()
            propio = re.sub(r"\D", "", info.get("display_phone_number", ""))
            if propio and propio == re.sub(r"\D", "", OWNER_WA or ""):
                print("[ALERTA] ⚠️ OWNER_WA es el MISMO número del bot: WhatsApp no permite enviarse mensajes a sí mismo, "
                      "las alertas nunca llegarán. Configura OWNER_WA con el celular personal del asesor.")
        except Exception:
            pass
    if send_wa_text(OWNER_WA, texto):
        return True
    if ALERTA_TEMPLATE:
        try:
            r = requests.post(
                f"https://graph.facebook.com/v21.0/{WA_PHONE_ID}/messages",
                headers={"Authorization": f"Bearer {WA_TOKEN}"},
                json={"messaging_product": "whatsapp", "to": normalize_pe_phone(OWNER_WA) or OWNER_WA, "type": "template",
                      "template": {"name": ALERTA_TEMPLATE, "language": {"code": "es"},
                                   "components": [{"type": "body", "parameters": [
                                       {"type": "text", "text": re.sub(r"\s+", " ", texto.replace("\n", " | "))[:1000]}]}]}},
                timeout=15)
            if r.status_code == 200:
                return True
            print(f"[ALERTA] La plantilla {ALERTA_TEMPLATE} también falló: HTTP {r.status_code} {r.text[:300]}")
        except Exception as e:
            print("[ALERTA] Error enviando plantilla de alerta:", e)
    print("[ALERTA] ❌ No se pudo avisar al asesor por WhatsApp (revisa OWNER_WA y la ventana de 24 h).")
    return False


def send_wa_text(to_phone, text):
    if not to_phone or not text:
        return False
    clean_phone = normalize_pe_phone(to_phone) or str(to_phone).replace("+", "")
    try:
        r = requests.post(
            f"https://graph.facebook.com/v21.0/{WA_PHONE_ID}/messages",
            headers={"Authorization": f"Bearer {WA_TOKEN}"},
            json={
                "messaging_product": "whatsapp",
                "to": clean_phone,
                "type": "text",
                "text": {"preview_url": True, "body": text[:4096]}
            },
            timeout=15
        )
    except Exception as e:
        print(f"Excepción enviando WhatsApp a {clean_phone}:", e)
        return False
    if r.status_code != 200:
        print(f"WhatsApp rechazó el mensaje a {clean_phone}: HTTP {r.status_code} {r.text[:300]}")
    return r.status_code == 200


MEDIA_ERROR = {}  # url -> último motivo de fallo
MEDIA_CACHE = {}  # url -> (media_id, timestamp). Los media_id de WhatsApp duran 30 días; se renuevan cada 7.
WA_IMG_MAX_BYTES = 5 * 1024 * 1024  # límite de WhatsApp para imágenes


def _tipo_media_por_url(media_url, media_type):
    ext = media_url.lower().split("?")[0].rsplit(".", 1)[-1]
    if ext in ["jpg", "jpeg", "png", "webp"]:
        return "image", ("image/png" if ext == "png" else "image/jpeg")
    if ext == "pdf":
        return "document", "application/pdf"
    if ext in ["mp4", "3gp"]:
        return "video", "video/mp4"
    return media_type, None


def subir_media_wa(media_url, tipo, mime):
    """Descarga el archivo y lo sube a WhatsApp (devuelve media_id). Así los errores (archivo pesado, URL caída)
    se detectan al instante, y las imágenes de más de 5 MB se comprimen automáticamente."""
    cache = MEDIA_CACHE.get(media_url)
    if cache and time.time() - cache[1] < 7 * 24 * 3600:
        return cache[0]
    try:
        r = requests.get(media_url, timeout=20)
        if r.status_code != 200:
            print(f"No se pudo descargar {media_url}: HTTP {r.status_code}")
            return None
        data = r.content
        mime = mime or r.headers.get("Content-Type", "application/octet-stream").split(";")[0]
        if tipo == "image" and len(data) > WA_IMG_MAX_BYTES:
            try:
                from PIL import Image
                import io
                img = Image.open(io.BytesIO(data)).convert("RGB")
                img.thumbnail((2000, 2000))
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=82, optimize=True)
                print(f"Imagen {media_url} comprimida de {len(data)/1e6:.1f} MB a {buf.tell()/1e6:.1f} MB")
                data, mime = buf.getvalue(), "image/jpeg"
            except Exception as e:
                print(f"Imagen {media_url} pesa {len(data)/1e6:.1f} MB (WhatsApp acepta máx. 5 MB) y no se pudo comprimir: {e}")
                return None
        nombre = media_url.split("?")[0].rsplit("/", 1)[-1]
        up = requests.post(
            f"https://graph.facebook.com/v21.0/{WA_PHONE_ID}/media",
            headers={"Authorization": f"Bearer {WA_TOKEN}"},
            data={"messaging_product": "whatsapp", "type": mime},
            files={"file": (nombre, data, mime)},
            timeout=30
        )
        if up.status_code != 200:
            print(f"WhatsApp rechazó la subida de {nombre}: HTTP {up.status_code} {up.text[:300]}")
            return None
        media_id = up.json().get("id")
        if media_id:
            MEDIA_CACHE[media_url] = (media_id, time.time())
        return media_id
    except Exception as e:
        print(f"Error subiendo media {media_url}:", e)
        return None


def send_wa_media(to_phone, media_url, media_type="document", caption=""):
    if not to_phone or not media_url or "link-a-tu-" in media_url:
        return False
    clean_phone = normalize_pe_phone(to_phone) or str(to_phone).replace("+", "")
    # Un .jpg se manda como imagen (antes la ficha .jpg iba como "documento PDF" y WhatsApp la rechazaba)
    media_type, mime = _tipo_media_por_url(media_url, media_type)
    media_id = subir_media_wa(media_url, media_type, mime)
    contenido = {"id": media_id} if media_id else {"link": media_url}
    if caption and media_type in ["image", "document", "video"]:
        contenido["caption"] = caption[:1024]
    if media_type == "document":
        contenido["filename"] = media_url.split("?")[0].rsplit("/", 1)[-1] or "Ficha_Tecnica_Santa_Teresa.pdf"
    payload = {"messaging_product": "whatsapp", "to": clean_phone, "type": media_type, media_type: contenido}
    try:
        r = requests.post(
            f"https://graph.facebook.com/v21.0/{WA_PHONE_ID}/messages",
            headers={"Authorization": f"Bearer {WA_TOKEN}"},
            json=payload,
            timeout=20
        )
    except Exception as e:
        print(f"Excepción enviando media a {clean_phone}:", e)
        MEDIA_ERROR[media_url] = str(e)[:120]
        return False
    if r.status_code != 200:
        print(f"WhatsApp rechazó el envío de {media_url} a {clean_phone}: HTTP {r.status_code} {r.text[:300]}")
        try:
            MEDIA_ERROR[media_url] = (r.json().get("error") or {}).get("message", "")[:120] or f"HTTP {r.status_code}"
        except Exception:
            MEDIA_ERROR[media_url] = f"HTTP {r.status_code}"
        if media_id:
            MEDIA_CACHE.pop(media_url, None)
    return r.status_code == 200


def send_wa_template(to_phone, nombre, cocina, pago):
    clean_phone = normalize_pe_phone(to_phone) or to_phone.replace("+", "")
    payload = {
        "messaging_product": "whatsapp",
        "to": clean_phone,
        "type": "template",
        "template": {
            "name": "bienvenida_santa_teresa",
            "language": {"code": "es"},
            "components": [{
                "type": "body",
                "parameters": [
                    {"type": "text", "text": nombre or "Hola"},
                    {"type": "text", "text": cocina or "equipada con reposteros"},
                    {"type": "text", "text": pago or "contado o crédito hipotecario"}
                ]
            }]
        }
    }
    r = requests.post(
        f"https://graph.facebook.com/v21.0/{WA_PHONE_ID}/messages",
        headers={"Authorization": f"Bearer {WA_TOKEN}"},
        json=payload,
        timeout=15
    )
    return r.status_code == 200


def send_meta_dm(recipient_id, text):
    if not recipient_id or not text:
        return False
    r = requests.post(
        "https://graph.facebook.com/v21.0/me/messages",
        params={"access_token": META_TOKEN},
        json={"recipient": {"id": recipient_id}, "message": {"text": text}},
        timeout=15
    )
    return r.status_code == 200


def get_lead_by_sender_or_phone(sender_id, phone=None):
    if not supabase:
        return {}
    try:
        res = supabase.table("leads").select("*").eq("sender_id", sender_id).limit(1).execute()
        if res.data:
            return res.data[0]
        if phone:
            res_p = supabase.table("leads").select("*").eq("telefono", phone).order("updated_at", desc=True).limit(1).execute()
            if res_p.data:
                return res_p.data[0]
    except Exception:
        pass
    return {}


def safe_upsert_lead(sender_id, canal, nombre=None, telefono=None, interes_dict=None, ultimo_msg=""):
    if not supabase:
        return
    now_iso = datetime.now(timezone.utc).isoformat()
    existing = get_lead_by_sender_or_phone(sender_id, telefono)
    prev_meta = {}
    if existing.get("interes"):
        try:
            prev_meta = json.loads(existing["interes"])
        except Exception:
            prev_meta = {"notas": existing["interes"]}
    if interes_dict:
        prev_meta.update({k: v for k, v in interes_dict.items() if v is not None})

    base_payload = {
        "sender_id": sender_id,
        "canal": canal,
        "nombre": nombre or existing.get("nombre") or "Interesado",
        "telefono": telefono or existing.get("telefono") or (sender_id if canal == "whatsapp" else None),
        "interes": json.dumps(prev_meta, ensure_ascii=False) if prev_meta else existing.get("interes"),
        "ultimo_mensaje": (ultimo_msg or existing.get("ultimo_mensaje") or "")[:500],
        "updated_at": now_iso
    }
    try:
        ext_payload = dict(base_payload)
        if "cita_agendada" in prev_meta:
            ext_payload["cita_agendada"] = bool(prev_meta["cita_agendada"])
        supabase.table("leads").upsert(ext_payload, on_conflict="sender_id").execute()
    except Exception:
        try:
            supabase.table("leads").upsert(base_payload, on_conflict="sender_id").execute()
        except Exception as e:
            print("Supabase lead upsert error:", e)


PRECIO_LISTA_USD = float(os.environ.get("PRECIO_LISTA_USD", "135000"))
TASA_REFERENCIAL_TEA = float(os.environ.get("TASA_REFERENCIAL_TEA", "9"))   # % anual, solo referencial
PLAZO_REFERENCIAL_ANIOS = int(os.environ.get("PLAZO_REFERENCIAL_ANIOS", "25"))


def cuota_referencial(porc_inicial):
    prestamo = PRECIO_LISTA_USD * (1 - porc_inicial)
    r = (1 + TASA_REFERENCIAL_TEA / 100) ** (1 / 12) - 1
    n = PLAZO_REFERENCIAL_ANIOS * 12
    return prestamo * r / (1 - (1 + r) ** -n)


def _usd(x):
    return f"${x:,.0f}"


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


SEPARACION_TEXTO = os.environ.get(
    "SEPARACION_TEXTO",
    "un monto de separación que se descuenta del precio final (el importe exacto te lo confirmamos en la visita)"
)
GASTOS_TEXTO = os.environ.get(
    "GASTOS_TEXTO",
    "Los gastos de notaría, inscripción en SUNARP e impuestos que correspondan te los detallamos por escrito antes de firmar, "
    "para que no haya sorpresas"
)
ASESOR_HIPOTECARIO_WA = os.environ.get("ASESOR_HIPOTECARIO_WA", "")


def responder_faq(user_text, nombre_corto, meta=None):
    """Respuestas fijas a las preguntas frecuentes de compra (crédito y contado). Usan el estado del cliente para no repetir."""
    t = limpiar_texto(user_text)
    meta = meta if meta is not None else {}
    coma = f", {nombre_corto}" if nombre_corto else ""
    fin_rx = r"(banco|credito|hipotecari\w*|financ\w*|prestamo)"
    proc_rx = r"(procedimiento|proceso|como seria|como es|como funciona|como hago|pasos|tramite)"
    es_contado = bool(re.search(r"\b(contado|efectivo|cash|fondos propios)\b", t)) or meta.get("fin_modalidad") == "contado"
    sin_aprobacion = meta.get("fin_credito_aprobado") is False or meta.get("fin_inicial") is False

    # ---------------- CRÉDITO ----------------
    # ¿La evaluación la hacen ustedes o voy al banco?
    if re.search(r"\bevalua\w*|precalifica\w*|calificar\w*|aprobar\w*|aprueben\b", t) and re.search(
            r"\b(ustedes|banco|quien|donde|tengo que|debo|hacen|ir)\b", t):
        meta["etapa"] = "ofrecio_asesor"
        intro = ("Como todavía no tienes tu crédito aprobado, " if sin_aprobacion else "")
        return (
            f"Buena pregunta{coma} 😊. La evaluación crediticia la hace el banco (nosotros no damos crédito directo), "
            f"pero no tienes que hacerlo sola ni ir de banco en banco. {intro}tienes 2 caminos:\n\n"
            "1️⃣ *Con nuestro asesor hipotecario aliado (sin costo):* te contacta, revisa tu perfil y te dice en qué banco te conviene "
            "y cuánto te prestan.\n"
            "2️⃣ *Directo con tu banco:* si ya eres cliente de alguno (BCP, BBVA, Interbank, etc.), pides tu precalificación hipotecaria "
            "con tu sectorista; nosotros te entregamos la Copia Literal y HR/PU de SUNARP de la casa para que avance rápido.\n\n"
            "¿Quieres que el asesor te contacte a este número? Respóndeme *sí* y le paso tus datos."
        )

    # ¿Cuánto de inicial? / inicial adecuada / mínima
    if re.search(r"\binicial\b", t) and re.search(r"\b(cuant\w*|adecuad\w*|recomend\w*|minim\w*|necesit\w*|ideal|porcentaje)\b", t):
        return (
            f"¡Buena pregunta{coma}! 😊 El banco pide como *mínimo el 10%* del valor (aprox. *{_usd(PRECIO_LISTA_USD * 0.10)} USD* "
            f"sobre el precio de lista de {_usd(PRECIO_LISTA_USD)}). Lo que te recomendamos es apuntar a un *20% (aprox. {_usd(PRECIO_LISTA_USD * 0.20)})*: "
            "con más inicial el banco te aprueba más rápido, te da mejor tasa y la cuota mensual baja.\n\n"
            f"Como referencia (tasa aprox. {TASA_REFERENCIAL_TEA:g}% anual a {PLAZO_REFERENCIAL_ANIOS} años; tu banco define la tasa exacta):\n"
            f"• Con 10% de inicial → cuota aprox. *{_usd(cuota_referencial(0.10))} al mes*\n"
            f"• Con 20% de inicial → cuota aprox. *{_usd(cuota_referencial(0.20))} al mes*\n\n"
            "Además, por ser la 1ra unidad aplica el Bono Especial, que baja el precio final (y con eso la inicial y la cuota). "
            "Aparte de la inicial, considera un monto para gastos de notaría, registros y la tasación del banco. "
            "Si gustas, nuestro asesor hipotecario aliado te evalúa sin costo y te dice exacto cuánto te financian.\n\n"
            + cierre_contextual(meta, nombre_corto)
        )

    # ¿Cuánto pagaría al mes? / cuota mensual
    if re.search(r"\b(cuota mensual|al mes|mensualidad|cuanto pagaria|cuanto saldria|cuanto seria la cuota|cuanto es la cuota)\b", t):
        return (
            f"Te doy una referencia{coma} (tasa aprox. {TASA_REFERENCIAL_TEA:g}% anual a {PLAZO_REFERENCIAL_ANIOS} años, sobre el precio de lista de {_usd(PRECIO_LISTA_USD)}):\n"
            f"• Con 10% de inicial ({_usd(PRECIO_LISTA_USD * 0.10)}) → aprox. *{_usd(cuota_referencial(0.10))} al mes*\n"
            f"• Con 20% de inicial ({_usd(PRECIO_LISTA_USD * 0.20)}) → aprox. *{_usd(cuota_referencial(0.20))} al mes*\n\n"
            "La cuota exacta la define tu banco según tu evaluación, y con el Bono Especial de la 1ra Unidad el monto baja. "
            "Si quieres, nuestro asesor hipotecario aliado te hace la simulación sin costo.\n\n"
            + cierre_contextual(meta, nombre_corto)
        )

    # ¿Se puede financiar? / ¿tienen financiamiento? / ¿en cuotas? / ¿crédito directo?
    if re.search(r"\b(financ\w*|cuotas?|facilidades|a plazos|en partes|mensualidades|credito directo|"
                 r"credito hipotecario|hipotecari\w*|aceptan credito|con banco|prestamo)\b", t) and not re.search(r"\binicial\b", t):
        ya = meta.get("ya_explicado") or []
        if "financiamiento" in ya:
            # Ya se le explicó: no repetir el bloque completo, avanzar al siguiente paso
            if meta.get("asesor_solicitado"):
                return (f"Así es{coma}: el financiamiento es con crédito hipotecario de cualquier banco (desde 10% de inicial). "
                        "Nuestro asesor hipotecario ya tiene tus datos para evaluarte sin costo 😊.\n\n" + cierre_contextual(meta, nombre_corto))
            meta["etapa"] = "ofrecio_asesor"
            return (f"Así es{coma}: no damos crédito directo, pero sí puedes financiarla con crédito hipotecario de cualquier banco "
                    f"(desde 10% de inicial, cuota aprox. {_usd(cuota_referencial(0.10))} al mes). Lo más práctico es que nuestro asesor "
                    "hipotecario aliado te evalúe sin costo. ¿Quieres que te contacte a este número? Respóndeme *sí* y le paso tus datos.")
        meta["ya_explicado"] = list(set(ya + ["financiamiento"]))
        if re.search(r"\b(directo|con ustedes|con la constructora|propio)\b", t):
            intro = f"Buena pregunta{coma} 😊. Financiamiento directo con la constructora no manejamos, pero *sí puedes financiarla*: "
        elif meta.get("fin_modalidad") == "contado":
            intro = f"¡Claro{coma}! Aunque me comentaste que lo verías al contado, te cuento cómo funciona con financiamiento: "
        else:
            intro = f"¡Sí, se puede financiar{coma}! 😊 "
        txt = (
            intro + ("" if "directo" in intro else "No manejamos crédito directo con la constructora; ") + "el financiamiento es mediante *crédito hipotecario con cualquier banco* "
            "(BCP, BBVA, Interbank, Scotiabank, BanBif, etc.), y como la casa ya está terminada y con título en SUNARP, el trámite es rápido:\n\n"
            f"• *Inicial:* desde el 10% (aprox. {_usd(PRECIO_LISTA_USD * 0.10)} USD); el banco financia hasta el 90% restante.\n"
            f"• *Plazo y cuota:* hasta 25-30 años; como referencia, con 10% de inicial la cuota sale aprox. *{_usd(cuota_referencial(0.10))} al mes* "
            f"(tasa aprox. {TASA_REFERENCIAL_TEA:g}% anual, la exacta la define tu banco).\n"
            "• *Evaluación:* nuestro asesor hipotecario aliado te evalúa sin costo y te dice cuánto te prestan.\n"
            "• *Pasos:* evaluación → separación y entrega de Copia Literal/HR-PU → tasación del banco, firma en notaría, desembolso y llaves.\n\n"
        )
        if meta.get("fin_inicial") is None and meta.get("fin_credito_aprobado") is None and meta.get("fin_modalidad") != "contado" \
                and int(meta.get("veces_pregunta_fin") or 0) == 0:
            meta["pregunta_fin_pendiente"] = True
            meta["etapa"] = meta.get("etapa") if meta.get("etapa") == "ofrecio_horarios" else "pregunto_financiamiento"
            return txt + "Para orientarte mejor: ¿ya tienes algo de inicial ahorrado o algún crédito preaprobado?"
        return txt + cierre_contextual(meta, nombre_corto)

    # ---------------- CONTADO ----------------
    # ¿Cómo es el proceso al contado?
    if es_contado and re.search(proc_rx, t) and not re.search(fin_rx, t):
        return (
            f"¡Claro{coma}! Al contado el proceso es rápido porque la casa ya está terminada y con título independizado en SUNARP:\n\n"
            "1️⃣ *Visita y propuesta:* ves las casas, eliges la unidad y cerramos el precio con el Bono de la 1ra Unidad.\n"
            "2️⃣ *Revisión legal:* te enviamos la Copia Literal y HR/PU de SUNARP para que tu abogado confirme que está libre de cargas.\n"
            f"3️⃣ *Separación:* firmamos un contrato de arras con {SEPARACION_TEXTO}.\n"
            "4️⃣ *Escritura y llaves:* firmamos la escritura pública en notaría, realizas el pago y te entregamos las llaves de inmediato; "
            "la notaría inscribe la compra a tu nombre en SUNARP.\n\n"
            + cierre_contextual(meta, nombre_corto)
        )

    # ¿Hay descuento por pago al contado? / precio final
    if re.search(r"\b(descuento|rebaja|rebajan|precio final|ultimo precio|negociable|mejor precio|cuanto menos|me lo dejan)\b", t) and es_contado:
        return (
            f"¡Sí{coma}! 😊 Por ser la 1ra unidad aplica el *Bono Especial de Lanzamiento*, y al contado la negociación es más ágil. "
            "Puedes elegir entre:\n"
            "🅰️ Recibir la casa con los reposteros de cocina altos y bajos instalados en el diseño que prefieras (Gris Grafito con LED o Madera Rovere), o\n"
            "🅱️ Un descuento directo sobre el precio de lista, sin los reposteros.\n\n"
            "El monto final lo cerramos en la visita directamente con los propietarios (trato directo, sin comisión inmobiliaria). "
            "Recuerda que una vez vendida la 1ra casa, la 2da queda a precio fijo de lista.\n\n"
            + cierre_contextual(meta, nombre_corto)
        )

    # Separación / arras
    if re.search(r"\b(separa\w*|arras|apartar|reservar la casa|reservarla|cuanto para separar)\b", t):
        return (
            f"Para asegurar la unidad{coma}, se firma un contrato de arras con {SEPARACION_TEXTO}. "
            "Así la casa queda bloqueada a tu nombre con el Bono de la 1ra Unidad mientras se prepara la escritura.\n\n"
            + cierre_contextual(meta, nombre_corto)
        )

    # Papeles / documentos / cargas
    if re.search(r"\b(papeles|documentos|documentacion|en regla|saneado\w*|copia literal|partida|cargas|gravamen\w*|hipotecad\w*|titulo)\b", t) and not re.search(proc_rx, t):
        return (
            f"Todo está en regla{coma} ✅: cada casa tiene *título independizado en SUNARP, libre de cargas y gravámenes*, lista para transferencia notarial. "
            "Si deseas, te enviamos la Copia Literal y la HR/PU para que tu abogado (o tu banco) las revise antes de separar.\n\n"
            + cierre_contextual(meta, nombre_corto)
        )

    # Gastos notariales / impuestos
    if re.search(r"\b(gastos?|notari\w*|impuesto\w*|alcabala|quien paga)\b", t) and re.search(r"\b(cuanto|quien|cuales|incluye|aparte|adicional\w*|paga\w*|hay)\b", t):
        return f"{GASTOS_TEXTO} 😊. El precio de la casa no incluye comisión inmobiliaria porque el trato es directo con la constructora.\n\n" + cierre_contextual(meta, nombre_corto)

    # Comprar desde el extranjero
    if re.search(r"\b(extranjero|exterior|fuera del pais|vivo en (eeuu|usa|estados unidos|espana|italia|chile|argentina|japon)|desde (eeuu|usa|espana|italia|chile))\b", t):
        return (
            f"¡Claro que sí{coma}! Muchos de nuestros compradores viven fuera 😊. Puedes comprar desde el exterior otorgando un poder por escritura pública "
            "(en el consulado peruano) a un familiar de confianza, o viajar solo para la firma. Mientras tanto, un familiar puede visitar la casa por ti. "
            "Te enviamos la Copia Literal para que tu abogado revise todo a distancia.\n\n"
            + cierre_contextual(meta, nombre_corto)
        )

    # ¿Cómo es el procedimiento con banco? (Caso 16)
    if (re.search(fin_rx, t) and re.search(proc_rx, t)) or re.search(r"\bcomo (seria|es|funciona) con (el )?banco\b", t):
        return (
            f"¡Claro{coma}! El proceso es súper directo porque la casa ya está 100% terminada y tiene título independizado en SUNARP (sin cargas ni hipotecas):\n\n"
            "1️⃣ *Inicial y banco:* Trabajamos con cualquier banco (BCP, BBVA, Interbank, Scotiabank, BanBif, etc.). "
            "El banco te pide desde el 10% de cuota inicial y financia hasta el 90% restante.\n"
            "2️⃣ *Separación y documentos:* Acordamos el precio final (con el bono de 1ra unidad), separas la unidad y te entregamos "
            "la Copia Literal y HR/PU de SUNARP para tu sectorista.\n"
            "3️⃣ *Tasación y desembolso:* El perito del banco tasa la casa, firmas la escritura en notaría, el banco nos desembolsa "
            "y te entregamos las llaves de inmediato.\n\n"
            "Si gustas, te contactamos sin costo con nuestro asesor hipotecario aliado para que te evalúe. "
            + cierre_contextual(meta, nombre_corto)
        )
    return None


URL_VIDEO_RECORRIDO = os.environ.get("URL_VIDEO_RECORRIDO", "")


def _estilo_de_texto(t):
    t = limpiar_texto(t)
    if re.search(r"\b(madera|rovere|taupe|calida|beige)\b", t):
        return "madera"
    if re.search(r"\b(gris|grafito|led|moderna)\b", t):
        return "gris"
    return None


ESTILOS_TXT = {"madera": "Línea Cálida en Madera Rovere y acabado Taupe", "gris": "Línea Moderna en Gris Grafito con iluminación LED cálida"}


def responder_material(user_text, nombre_corto, meta=None, ultimo_bot="", cerrar=True):
    """Pedidos de fotos, planos, renders, video, la opción '1' del menú, o la elección de un estilo de cocina."""
    t = limpiar_texto(user_text)
    meta = meta if meta is not None else {}
    coma = f", {nombre_corto}" if nombre_corto else ""
    menu_material = bool(re.search(r"1️⃣[^\n]*(plano|ficha|cocina|dise)", ultimo_bot or "", re.I))
    lista_horarios = bool(re.search(r"1️⃣[^\n]*(a\. m\.|p\. m\.)", ultimo_bot or ""))
    es_opcion_1 = t in ["1", "1️⃣", "uno", "opcion 1", "la 1", "el 1", "la uno", "la primera"] and (menu_material or not lista_horarios)

    # Eligió un estilo de cocina ("me gusta la gris", "prefiero la de madera")
    if re.search(r"\b(me gusta\w*|prefiero|elijo|escojo|me quedo con|me encanta\w*|mejor la|la de)\b", t) and _estilo_de_texto(t) \
            and not re.search(r"\b(envi\w*|manda\w*|pasa\w*|foto\w*)\b", t):
        estilo = _estilo_de_texto(t)
        meta["estilo_cocina"] = ESTILOS_TXT[estilo]
        r = _resp(f"¡Excelente elección{coma}! 😍 La {ESTILOS_TXT[estilo]} queda espectacular con el porcelanato de la cocina. "
                  "Si separas la 1ra unidad, te la entregamos instalada en ese diseño como parte del Bono Especial de Lanzamiento."
                  + ("\n\n" + cierre_contextual(meta, nombre_corto) if cerrar else ""))
        r["_sin_control_repeticion"] = True
        return r

    pide_fotos = re.search(r"\b(fotos?|fotitos?|fotografias?|imagen\w*|como es por dentro|por dentro|interiores?|de referencia)\b", t)
    pide_planos = es_opcion_1 or re.search(r"\b(planos?|ficha\w*|pdf|brochure|catalogo)\b", t)
    pide_cocina = es_opcion_1 or re.search(r"\b(render\w*|cocinas?|reposteros?|disenos? de (la )?cocina|estilos? de (la )?cocina)\b", t)
    pide_video = re.search(r"\b(video\w*|recorrido virtual|tour)\b", t)
    if not (pide_fotos or pide_planos or pide_cocina or pide_video):
        return None
    r = _resp("")
    r["_sin_control_repeticion"] = True
    partes = []
    if pide_fotos or pide_video:
        r["enviar_fotos_casa"] = bool(URL_FOTOS_CASA)
        r["enviar_ficha_tecnica"] = True
        r["enviar_renders_cocina"] = True
        r["_alerta_fotos"] = True  # avisar al asesor para que adjunte fotos reales
        partes.append(f"¡Claro{coma}! 📸 Te comparto por aquí "
                      + ("fotos de la casa, " if URL_FOTOS_CASA else "")
                      + "los planos de distribución de los 3 pisos y los 2 diseños de cocina que puedes elegir "
                        "(Opción 1: Gris Grafito con LED; Opción 2: Madera Rovere con Taupe).")
        if pide_video and URL_VIDEO_RECORRIDO:
            partes.append(f"Aquí puedes ver el recorrido en video: {URL_VIDEO_RECORRIDO}")
        partes.append("Ambas casas ya están 100% terminadas y listas para entrega inmediata. "
                      "En persona se aprecian mucho mejor los 200 m², la iluminación y la terraza frente a la loza deportiva 😊")
    else:
        r["enviar_ficha_tecnica"] = bool(pide_planos)
        r["enviar_renders_cocina"] = bool(pide_cocina)
        if pide_planos and pide_cocina:
            partes.append(f"¡Claro{coma}! 📄 Te comparto los planos de distribución de los 3 pisos (200 m² construidos sobre 80 m² de terreno) "
                          "y los 2 diseños de cocina equipada:\n👉 Opción 1: Línea Moderna en Gris Grafito con iluminación LED cálida.\n"
                          "👉 Opción 2: Línea Cálida en Madera Rovere y acabado Taupe.\n"
                          "Ambas casas ya están 100% terminadas y listas para entrega inmediata.")
        elif pide_planos:
            partes.append(f"¡Claro{coma}! 📄 Te comparto los planos de distribución de los 3 pisos (200 m² construidos sobre 80 m² de terreno). "
                          "Ambas casas ya están 100% terminadas y listas para entrega inmediata.")
        else:
            partes.append(f"¡Claro{coma}! Estos son los 2 diseños de cocina que puedes elegir (reposteros altos y bajos instalados):\n"
                          "👉 Opción 1: Línea Moderna en Gris Grafito con iluminación LED cálida.\n"
                          "👉 Opción 2: Línea Cálida en Madera Rovere y acabado Taupe.")
        if pide_cocina and (not meta.get("estilo_cocina") or "Por elegir" in str(meta.get("estilo_cocina"))):
            partes.append("Cuando los veas, cuéntame cuál te gusta más 😊")
    meta["material_enviado"] = True
    r["reply_text"] = "\n\n".join(partes) + ("\n\n" + cierre_contextual(meta, nombre_corto) if cerrar else "")
    return r


INFO_TEMAS = {
    "general": r"\b(info|informacion|informes?|detalles?|mas datos|datos|caracteristicas|me interesa\w*|interesad\w*|quisiera saber|"
               r"quiero saber|cuentame|de que se trata|sobre la casa|sobre las casas|disponible\w*)\b",
    "precio": r"\b(precios?|cuanto (cuesta|cuestan|vale|valen|esta|estan|sale|salen|es)|costos?|valor|cuanto)\b",
    "area": r"\b(area|areas|metraje|metros|m2|mide|miden|medidas|tamano|terreno|construid\w*|dimensiones)\b",
    "ubicacion": r"\b(ubicacion|ubicad\w*|donde (queda|quedan|esta|estan|es|son)|direccion|como (llego|llegar|ir)|mapa|lugar|zona|sector|referencias? para llegar)\b",
    "distribucion": r"\b(distribucion|distribuid\w*|cuantos (pisos|cuartos|dormitorios|banos|habitaciones|niveles)|habitaciones|dormitorios|cuartos|"
                    r"banos|ambientes|que tiene|que incluye|cochera|terraza|jardin|pisos)\b",
    "entrega": r"\b(entrega\w*|cuando (la |las )?entregan|esta lista|estan listas|en planos|preventa|terminad\w*|para mudarse|estreno)\b",
}


def temas_info(user_text):
    t = limpiar_texto(user_text)
    temas = [k for k, rx in INFO_TEMAS.items() if re.search(rx, t)]
    if "precio" in temas and re.search(r"\binicial\b|\bcuota", t) and not re.search(r"\bprecio", t):
        temas.remove("precio")  # "cuánto de inicial" lo responde la FAQ
    if "general" in temas and len(temas) > 1:
        temas.remove("general")
    return temas


def responder_info(user_text, nombre_corto, meta=None, primer_contacto=False, cerrar=True):
    """Información, detalles, precio, área, ubicación/dirección, distribución, entrega y sus combinaciones (Casos 2, 4, 5, 6, 9, 12)."""
    meta = meta if meta is not None else {}
    temas = temas_info(user_text)
    if not temas:
        return None
    nom = f", {nombre_corto}" if nombre_corto else ""
    elogio = re.search(r"\b(excelente|buen\w* (diseno|acabado|trabajo|construccion|casa)|bonit\w*|linda\w*|hermos\w*|me gusta\w*|que buena|se ve bien|espectacular)\b",
                       limpiar_texto(user_text))
    if primer_contacto:
        saludo = f"¡Hola{nom}! Un gusto saludarte de parte de SAGUE Constructora 🏡. "
    elif elogio:
        saludo = f"¡Muchas gracias{nom}, nos alegra que te guste! 😊 Te detallo: "
    else:
        saludo = f"¡Con gusto te detallo{nom}! 😊 "
    b = {
        "precio": (f"💰 *Precio:* valor de lista de *{_usd(PRECIO_LISTA_USD)} USD*. Con 200 m² construidos te sale a solo *$675 por m²*, "
                   "cuando un departamento de 90 m² en Chiclayo (sin cochera, jardín ni terraza) está entre $950 y $1,150 por m². "
                   "Además, la 1ra unidad que se separe tiene un *Bono Especial de Lanzamiento* (reposteros de cocina incluidos o descuento directo)."),
        "area": "📐 *Área:* 80 m² de terreno y *200 m² construidos* en 3 pisos independientes.",
        "distribucion": ("🏠 *Distribución:*\n• *1er piso:* cochera privada cerrada, sala-comedor amplia, baño de visitas, cocina integrada con barra y patio con jardín interior.\n"
                         "• *2do piso:* 3 habitaciones amplias y 2 baños completos (la principal con baño propio).\n"
                         "• *3er piso:* gran terraza social para parrillas con vista a la loza deportiva y zona de lavandería."),
        "ubicacion": ("📍 *Ubicación:* Urb. Santa Teresa, Lambayeque — calles 5 de Febrero y Andrés Lastres, *frente a la loza deportiva*. "
                      "A 1 min de la Av. Ramón Castilla, 2 min de la Plaza de Armas y Metro, 5 min de la UNPRG y a 7 cuadras del Hospital Belén.\n"
                      f"Mapa: {MAPS_URL}"),
        "entrega": "🔑 *Entrega inmediata:* ambas casas están 100% terminadas, con título independizado en SUNARP y libres de cargas.",
        "general": ("Son *2 casas gemelas de estreno* en Urb. Santa Teresa (Lambayeque), frente a la loza deportiva y a 1 min de la Av. Ramón Castilla: "
                    "*80 m² de terreno y 200 m² construidos* en 3 pisos (cochera, jardín interior, 3 habitaciones, 3 baños y terraza amplia). "
                    f"Valor de lista *{_usd(PRECIO_LISTA_USD)} USD* (solo $675/m²), entrega inmediata con título en SUNARP, e incluyen los reposteros de cocina "
                    "instalados a tu gusto."),
    }
    orden = ["general", "precio", "area", "distribucion", "entrega", "ubicacion"]
    cuerpo = "\n\n".join(b[k] for k in orden if k in temas)
    r = _resp("")
    r["_sin_control_repeticion"] = True
    if "distribucion" in temas:
        r["enviar_ficha_tecnica"] = True
        cuerpo += "\n\nTe comparto también los planos de los 3 pisos 📄."
    r["reply_text"] = saludo + cuerpo + ("\n\n" + cierre_info(meta, nombre_corto, temas) if cerrar else "")
    return r


def cierre_info(meta, nombre_corto, temas):
    """Caso 5: tras pedir información general, una pregunta de filtro financiero (solo si aún no se sabe); si no, el siguiente paso."""
    sabe_fin = any(meta.get(k) is not None for k in ["fin_modalidad", "fin_inicial", "fin_credito_aprobado"])
    if temas == ["general"] and not sabe_fin and int(meta.get("veces_pregunta_fin") or 0) == 0 and not meta.get("cita_agendada"):
        meta["pregunta_fin_pendiente"] = True
        return "¿La estás buscando para comprar al contado o con crédito hipotecario? Así te oriento mejor y coordinamos tu visita 😊"
    return cierre_contextual(meta, nombre_corto)


def texto_formulario(nombre, cocina, pago, presupuesto, meta):
    """Respuesta a un lead del formulario de Meta según lo que marcó (pago, estilo de cocina y presupuesto)."""
    nom = (nombre or "").split()[0].title() if nombre and nombre not in ["Cliente", "Interesado"] else ""
    coma = f", {nom}" if nom else ""
    d = detectar_financiamiento(pago or "")
    pl = limpiar_texto(pago or "")
    if re.search(r"\b(aun no|todavia no|sin inicial|ni evaluacion|no cuento)\b", pl):
        d["inicial"], d["credito_aprobado"] = False, False
    if re.search(r"pre ?aprobad", pl):
        d["credito_aprobado"], d["modalidad"] = True, "credito"
    for k_src, k_meta in (("modalidad", "fin_modalidad"), ("inicial", "fin_inicial"), ("credito_aprobado", "fin_credito_aprobado")):
        if d[k_src] is not None:
            meta[k_meta] = d[k_src]
    meta["forma_pago"] = pago or meta.get("forma_pago")
    estilo = _estilo_de_texto(cocina or "")
    if estilo:
        meta["estilo_cocina"] = ESTILOS_TXT[estilo]
    estilo_txt = f"la {ESTILOS_TXT[estilo]}" if estilo else "tu diseño de cocina"
    presup_no = limpiar_texto(presupuesto or "").startswith("no")
    calif = estado_financiero(meta)
    flags = {"enviar_ficha_tecnica": True, "enviar_renders_cocina": True, "estilo_render_preferido": estilo or "ambos"}
    intro = (f"¡Hola{coma}! 😊 Te saluda el equipo de SAGUE Constructora. Gracias por completar el formulario de nuestras 2 casas gemelas de estreno "
             "en Urb. Santa Teresa, Lambayeque (200 m² construidos en 3 pisos, frente a la loza deportiva, entrega inmediata con título en SUNARP).\n\n")
    if calif is False:
        meta["etapa"] = "ofrecio_asesor"
        meta["ya_explicado"] = list(set((meta.get("ya_explicado") or []) + ["sin_inicial"]))
        txt = (intro + f"¡Muy buena elección {estilo_txt} para tus reposteros! Te comparto los planos de distribución y el render de ese diseño.\n\n"
               "Vi que aún no cuentas con inicial ni evaluación bancaria. Como las casas ya están terminadas, la compra es al contado o con "
               f"crédito hipotecario de cualquier banco, que pide desde el 10% de inicial (aprox. {_usd(PRECIO_LISTA_USD * 0.10)} USD); no manejamos crédito directo.\n\n"
               "¿Tienes proyectado disponer pronto de esa inicial? Si gustas, nuestro asesor hipotecario aliado te evalúa *sin costo* y te dice cuánto "
               "te financian. Respóndeme *sí* y le paso tus datos.")
    elif presup_no:
        meta["etapa"] = "pregunto_presupuesto"
        txt = (intro + f"¡Muy buena elección {estilo_txt}! Te comparto los planos y el render de ese diseño.\n\n"
               f"Vi que el valor de lista ({_usd(PRECIO_LISTA_USD)}) se escapa un poco de tu rango. Como la 1ra unidad tiene un Bono Especial de Lanzamiento "
               "(e incluso podemos entregarla sin los reposteros y descontar ese monto), cuéntame con total confianza: "
               "¿cuál es el tope aproximado de inversión o crédito que manejas? Así vemos si llegamos a un número que te encaje.")
    else:
        modalidad = ("al contado" if meta.get("fin_modalidad") == "contado" else
                     "con tu crédito preaprobado" if meta.get("fin_credito_aprobado") else
                     "con tu inicial lista" if meta.get("fin_inicial") else "con tu modalidad de compra")
        txt = (intro + f"¡Excelente elección {estilo_txt} para tus reposteros! Te comparto los planos de los 3 pisos y el render de ese diseño.\n\n"
               f"Como compras {modalidad}, tienes *prioridad para el Bono Especial de Lanzamiento de la 1ra Unidad* sobre el valor de lista de {_usd(PRECIO_LISTA_USD)}.\n\n"
               + _cierre_con_horarios(meta, nom))
    return txt, flags


def build_Contextual_fallback(canal, user_text, nombre_cliente, has_history, meta=None):
    low = (user_text or "").strip().lower()
    saludo_nom = f"¡Hola, {nombre_cliente}!" if nombre_cliente not in ["Interesado", "Cliente", ""] else "¡Hola!"
    nombre_corto = nombre_cliente.split()[0] if nombre_cliente not in ["Interesado", "Cliente", ""] else ""

    faq = responder_faq(user_text, nombre_corto, meta)
    if faq:
        es_comentario = canal in ["fb_comment", "ig_comment"]
        return {
            "reply_text": (f"{saludo_nom} Te enviamos el detalle por mensaje privado 📩. También puedes escribirnos al WhatsApp: "
                           "https://wa.me/51986339051") if es_comentario else faq,
            "private_reply": faq if es_comentario else "",
            "ignorar_comentario": False,
            "enviar_ficha_tecnica": False,
            "enviar_renders_cocina": False,
            "estilo_render_preferido": "ambos",
            "agendar_visita_iso": ""
        }

    # Caso 1: El cliente respondio "1" o pide planos / ficha / diseños de cocina
    if low in ["1", "1️⃣", "uno", "opcion 1", "opción 1"] or any(w in low for w in ["plano", "ficha", "cocina", "render", "repostero", "foto"]):
        txt = (
            f"¡Claro{', ' + nombre_corto if nombre_corto else ''}! 😊 Te comparto los planos arquitectónicos de distribución "
            "de los 3 pisos (200 m² construidos sobre 80 m² de terreno; ambas casas ya están 100% construidas "
            "y listas para entrega inmediata, con título en SUNARP) junto con nuestras 2 opciones de cocina equipada:\n"
            "👉 Opción 1: Línea Moderna en Gris Grafito con iluminación LED cálida.\n"
            "👉 Opción 2: Línea Cálida en Madera Rovere y acabado Taupe.\n\n"
            "Cuéntame, ¿cuál de los dos estilos de cocina te gusta más y si estás evaluando la compra al contado o con crédito hipotecario para agendar tu visita guiada?"
        )
        return {
            "reply_text": txt,
            "private_reply": "",
            "ignorar_comentario": False,
            "enviar_ficha_tecnica": True,
            "enviar_renders_cocina": True,
            "estilo_render_preferido": "ambos",
            "agendar_visita_iso": ""
        }

    # Caso 2: El cliente respondio "2" o pide visitar / ir a ver la casa / direccion
    if low in ["2", "2️⃣", "dos", "opcion 2", "opción 2"] or VISITA_RE.search(limpiar_texto(user_text)):
        libres = get_free_slots(n=2)
        turnos = " o el ".join(format_fecha_es(s, relativo=True) for s in libres) if libres else "el día y hora que prefieras"
        txt = (
            f"¡Qué excelente noticia{', ' + nombre_corto if nombre_corto else ''}! Será un gusto recibirte en la Urb. Santa Teresa (Lambayeque), "
            "exactamente frente a la loza deportiva y a 1 min de la Av. Ramón Castilla 🏡.\n\n"
            f"Tengo libre el {turnos}. ¿Cuál te acomoda? "
            "Y para registrarte con el ingeniero: ¿la compra la evalúas al contado o con crédito hipotecario (desde 10% de inicial)?"
        )
        return {
            "reply_text": txt,
            "private_reply": "",
            "ignorar_comentario": False,
            "enviar_ficha_tecnica": False,
            "enviar_renders_cocina": False,
            "estilo_render_preferido": "ambos",
            "agendar_visita_iso": ""
        }

    # Caso 3: Pregunta por cuotas / bancos / credito / inicial / forma de pago
    if any(w in low for w in ["cuota", "banco", "credito", "crédito", "inicial", "hipotecario", "contado", "financiamiento", "pago"]):
        txt = (
            f"Con gusto te detallo{', ' + nombre_corto if nombre_corto else ''}: nuestras 2 casas gemelas son de estreno y ya cuentan con título independiente en SUNARP para entrega inmediata. "
            "No manejamos crédito directo, pero puedes adquirirlas al contado o mediante crédito hipotecario con cualquier banco (BCP, BBVA, Interbank, Scotiabank, etc.), "
            "donde el banco solicita desde el 10% de cuota inicial (aprox. $13,500 USD sobre el valor de lista de $135,000 USD, con bono especial en visita para la primera casa).\n\n"
            "¿Ya cuentas con tu inicial disponible o crédito preaprobado para coordinar tu visita guiada esta semana? 😊"
        )
        return {
            "reply_text": txt,
            "private_reply": "",
            "ignorar_comentario": False,
            "enviar_ficha_tecnica": False,
            "enviar_renders_cocina": False,
            "estilo_render_preferido": "ambos",
            "agendar_visita_iso": ""
        }

    # Caso 4: Pregunta por precio / cuanto cuesta / valor
    if any(w in low for w in ["precio", "cuanto", "cuánto", "valor", "costo", "cuesta", "caro", "descuento", "135", "125"]):
        txt = (
            f"El valor de lista de nuestras casas gemelas de estreno en Urb. Santa Teresa (Lambayeque) es de $135,000 USD. "
            "Al tener 200 m² construidos en 3 pisos (sobre 80 m² de terreno, frente a loza deportiva), te sale a solo $675 por m² construido, "
            "mucho más ventajoso que un departamento pequeño en Chiclayo (que supera los $1,000/m²).\n\n"
            "Además, para la PRIMERA UNIDAD que se separe otorgamos un Bono Especial de Lanzamiento (incluyendo reposteros de cocina altos y bajos a tu gusto "
            "o aplicando un descuento directo en visita). ¿Te gustaría ver los planos y diseños de cocina (escribe 1) o agendar una visita guiada (escribe 2)?"
        )
        return {
            "reply_text": txt,
            "private_reply": "",
            "ignorar_comentario": False,
            "enviar_ficha_tecnica": False,
            "enviar_renders_cocina": False,
            "estilo_render_preferido": "ambos",
            "agendar_visita_iso": ""
        }

    # Caso 5: Pregunta por ubicacion / donde queda / mapa
    if any(w in low for w in ["ubicacion", "ubicación", "donde", "dónde", "direccion", "dirección", "mapa", "llegar", "lugar"]):
        txt = (
            f"Estamos ubicados en la Urb. Santa Teresa (Lambayeque), en la intersección de las calles 5 de Febrero y Andrés Lastres, "
            f"exactamente frente a la loza deportiva, a 1 min de la Av. Ramón Castilla y a 5 min de la UNPRG 📍: {MAPS_URL}\n\n"
            "Ambas casas están 100% terminadas para entrega inmediata (200 m² construidos en 3 pisos, $135,000 USD al contado o con banco). "
            "¿Qué día te gustaría visitarnos por la mañana o por la tarde para mostrártelas por dentro?"
        )
        return {
            "reply_text": txt,
            "private_reply": "",
            "ignorar_comentario": False,
            "enviar_ficha_tecnica": False,
            "enviar_renders_cocina": False,
            "estilo_render_preferido": "ambos",
            "agendar_visita_iso": ""
        }

    # Caso 6: Pregunta por distribucion / area / metraje / pisos
    if any(w in low for w in ["distribucion", "distribución", "area", "área", "metraje", "metro", "piso", "habitacion", "dormitorio"]):
        txt = (
            "Cada casa cuenta con 80 m² de terreno y 200 m² construidos distribuidos en 3 pisos independientes (entrega inmediata en SUNARP):\n"
            "• 1er Piso: Cochera privada cerrada, sala-comedor amplia, baño de visitas, cocina equipada con barra y patio con jardín interior.\n"
            "• 2do Piso: 3 habitaciones amplias y 2 baños completos (principal con baño propio).\n"
            "• 3er Piso: Gran terraza social para parrillas con vista a la loza deportiva y zona de lavandería.\n\n"
            "Te adjunto los planos detallados por aquí 📄. ¿Te gustaría agendar una visita esta semana para recorrer los 3 niveles en persona?"
        )
        return {
            "reply_text": txt,
            "private_reply": "",
            "ignorar_comentario": False,
            "enviar_ficha_tecnica": True,
            "enviar_renders_cocina": False,
            "estilo_render_preferido": "ambos",
            "agendar_visita_iso": ""
        }

    # Caso 7: Ya hay historial previo (para NUNCA repetir el bloque de bienvenida dos veces)
    if has_history and canal == "whatsapp":
        meta = meta or {}
        if meta.get("cita_agendada") and meta.get("fecha_cita"):
            try:
                f_cita = format_fecha_es(datetime.fromisoformat(meta["fecha_cita"]), relativo=True)
            except Exception:
                f_cita = "la fecha acordada"
            txt = (
                f"¡Gracias{', ' + nombre_corto if nombre_corto else ''}! 😊 Te recuerdo que tu visita guiada está registrada para el *{f_cita}* "
                f"en Urb. Santa Teresa (frente a la loza deportiva): {MAPS_URL}\n\n¿Tienes alguna otra consulta antes de la visita?"
            )
        else:
            libres = get_free_slots(n=3)
            if libres:
                meta["etapa"] = "ofrecio_horarios"
                meta["slots_ofrecidos"] = [s.isoformat() for s in libres]
                txt = (
                    f"¡Gracias{', ' + nombre_corto if nombre_corto else ''}! 😊 Lo mejor para que veas los acabados, los 3 pisos y te expliquemos "
                    "el Bono Especial de la 1ra Unidad es una visita guiada. Estos son los horarios libres más próximos:\n\n"
                    f"{_slots_a_texto(libres)}\n\nRespóndeme con el número (o dime otro día y hora) y te la registro."
                )
            else:
                txt = (
                    f"¡Gracias{', ' + nombre_corto if nombre_corto else ''}! 😊 ¿Qué día y hora te acomodaría para una visita guiada "
                    "y así te muestro los 3 pisos y te explico el Bono Especial de la 1ra Unidad?"
                )
        return {
            "reply_text": txt,
            "private_reply": "",
            "ignorar_comentario": False,
            "enviar_ficha_tecnica": False,
            "enviar_renders_cocina": False,
            "estilo_render_preferido": "ambos",
            "agendar_visita_iso": ""
        }

    # Caso 8: Primer contacto en WhatsApp o Redes
    if canal == "whatsapp":
        txt = (
            f"{saludo_nom} Un gusto saludarte de parte de SAGUE Constructora 🏡. "
            "Nuestras 2 casas gemelas de estreno (entrega inmediata e independizadas en SUNARP) "
            "están ubicadas frente a la loza deportiva en la Urb. Santa Teresa (Lambayeque), a 1 min de la Av. Ramón Castilla. "
            "Cuentan con 80 m² de terreno y 200 m² construidos en 3 pisos (cochera privada, jardín interior, 3 habitaciones, 3 baños y amplia terraza). "
            "Su valor de lista es de $135,000 USD ($675/m² construido, con Bono Especial para la 1ra unidad), disponible al contado o con crédito hipotecario, "
            "e incluye los reposteros de cocina instalados a tu gusto.\n\n"
            "Cuéntame, ¿cómo prefieres avanzar?:\n"
            "1️⃣ Recibir por aquí los planos de distribución y los 2 diseños de cocina.\n"
            "2️⃣ Coordinar una visita guiada para recorrerlas en persona."
        )
    else:
        txt = (
            f"{saludo_nom} Gracias por escribir a SAGUE Constructora 🏡. Nuestras 2 casas gemelas de estreno (entrega inmediata) "
            "frente a la loza deportiva en Urb. Santa Teresa (Lambayeque) tienen 200 m² construidos en 3 pisos, "
            "título en SUNARP y cocina equipada ($135,000 USD, al contado o crédito hipotecario). "
            "¿Me compartes tu número de WhatsApp por aquí para enviarte el PDF con los planos y renders de cocina, o nos escribes directo al 986 339 051?"
        )
    return {
        "reply_text": txt,
        "private_reply": txt if canal in ["fb_comment", "ig_comment"] else "",
        "ignorar_comentario": False,
        "enviar_ficha_tecnica": False,
        "enviar_renders_cocina": False,
        "estilo_render_preferido": "ambos",
        "agendar_visita_iso": ""
    }


def build_system_prompt(canal, cal_info, lead_info):
    if canal == "whatsapp":
        regla_canal = (
            "CANAL ACTUAL: WHATSAPP. El cliente YA te escribe desde su WhatsApp. "
            "PROHIBIDO pedirle su número de WhatsApp. "
            "PROHIBIDO repetir el mensaje de bienvenida o volver a ofrecer las opciones 1 y 2 si ya están en el historial. "
            "ATENCIÓN A RESPUESTAS CORTAS: Si en el historial le diste las opciones 1 y 2 y el cliente responde '1' (o pide planos/diseños), "
            "NO repitas la bienvenida: pon 'enviar_ficha_tecnica': true y 'enviar_renders_cocina': true, explícale en 'reply_text' que le acabas de adjuntar "
            "los planos de los 3 pisos (ya están 100% terminadas para entrega inmediata) y los 2 renders de cocina "
            "(Opción 1: Gris Grafito con LED y Opción 2: Madera Rovere con Taupe), y pregúntale cuál de los dos diseños le gusta más y si evalúa comprar al contado o con banco para agendar visita. "
            "Si el cliente responde '2' (o pide visitar), valida su interés y pregúntale qué modalidad de compra maneja (contado o crédito hipotecario con 10% de inicial) y qué día/hora prefiere visitarnos."
        )
    elif canal in ["facebook", "instagram"]:
        regla_canal = (
            f"CANAL ACTUAL: CHAT PRIVADO DE {canal.upper()}. "
            "Resuelve su consulta con los datos exactos (nunca lo mandes en frío a un link sin responderle primero) "
            "y PÍDELE SU NÚMERO DE WHATSAPP para enviarle ahora mismo el PDF con los planos de los 3 pisos, "
            "los 2 renders de cocina y coordinar su visita guiada (o indícale el WhatsApp directo 986 339 051)."
        )
    else:
        regla_canal = (
            f"CANAL ACTUAL: COMENTARIO PÚBLICO EN {canal.upper()}. "
            "Debes generar dos textos: "
            "1) 'reply_text': Respuesta pública breve, cálida y variada (máximo 220 caracteres) saludando al usuario por su nombre, "
            "diciéndole que le enviaste los detalles completos por mensaje privado y dejando el WhatsApp 986 339 051 (https://wa.me/51986339051). "
            "Si el comentario es una objeción (ej. dice que no hay jardín o que es cara), rebátela con mucha elegancia en público "
            "(aclarando que tiene jardín interior + gran terraza en 3er piso, y que son 200 m² construidos a solo $675/m² con título SUNARP). "
            "Si es un insulto, ataque o queja municipal ajena, marca 'ignorar_comentario': true. "
            "2) 'private_reply': Mensaje privado (DM) completo y cálido respondiendo exactamente lo que preguntó en su comentario "
            "y pidiéndole su número de WhatsApp o invitándolo a agendar visita."
        )

    return f"""Eres el asesor comercial senior de SAGUE Constructora e Inmobiliaria en Lambayeque, Perú.
Tu objetivo principal es lograr que el cliente AGENDE UNA VISITA PRESENCIAL a nuestras 2 casas gemelas en Urb. Santa Teresa, aplicando hospitalidad ejecutiva, ingeniería de valor y sentido de urgencia.

DATOS OFICIALES E INALTERABLES DEL PROYECTO SANTA TERESA:
- Propiedad: 2 únicas casas gemelas contiguas de estreno (100% construidas y terminadas, listas para ENTREGA INMEDIATA). Trato directo con la constructora propietaria (SAGUE Constructora), cero comisión inmobiliaria y con garantía estructural post-venta.
- Ubicación exacta: Urb. Santa Teresa, Lambayeque (intersección de las calles 5 de Febrero y Andrés Lastres, no es esquina), EXACTAMENTE FRENTE A LA LOZA DEPORTIVA (PROHIBIDO decir solo 'frente a parque'), a 1 minuto de la Av. Ramón Castilla, a 2 min del mercado/Plaza de Armas/Metro, a 5 min de la UNPRG, a 6 cuadras de la Panamericana Norte y a espaldas (7 cuadras) del Hospital Belén.
- Link de Google Maps: {MAPS_URL}
- Área exacta: 80 m² de terreno y 200 m² construidos distribuidos en 3 pisos independientes (NUNCA digas 216 m²):
  * 1er Piso: Cochera privada cerrada, sala-comedor amplia e iluminada, baño social de visitas, cocina integrada con barra de porcelanato y patio con jardín interior.
  * 2do Piso: 3 habitaciones amplias e iluminadas y 2 baños completos (dormitorio principal con baño propio incorporado).
  * 3er Piso: Gran terraza social amplia para parrillas con vista a la loza deportiva y zona de lavandería.
- Situación legal: Documentación 100% en regla, título independizado en SUNARP (libre de cargas y gravámenes), lista para transferencia notarial.

ESTRATEGIA COMERCIAL Y DE PRECIOS (INGENIERÍA DE VALOR):
1. Precio de Lista: $135,000 USD. PROHIBIDO usar la palabra 'REMATE' y PROHIBIDO decir $140,000.
2. Argumento de Ingeniería de Valor ($675/m² vs Departamentos): $135,000 USD entre 200 m² construidos equivale a solo $675 USD por m² construido, mientras que un departamento pequeño en Chiclayo de 90 m² (sin cochera propia, sin jardín y sin terraza privada) cuesta entre $95,000 y $115,000 USD ($950 a $1,150/m²). Por casi el mismo presupuesto de un departamento pequeño en Chiclayo, el comprador se lleva una casa independiente de 3 pisos y 200 m² en Lambayeque.
3. Regla de Escasez de la Unidad 1 y Doble Opción de Cierre:
   Tenemos solo 2 casas gemelas disponibles. Únicamente para la PRIMERA UNIDAD que se separe otorgamos el Bono Especial de Lanzamiento (una vez vendida la primera casa, la segunda se vende estrictamente al precio fijo de $135,000 USD):
   - Opción A (Equipamiento incluido): Entregamos la casa con los reposteros altos y bajos de cocina en melamina RH instalados a su gusto, eligiendo entre nuestros 2 renders oficiales:
     * Opción 1: Línea Moderna en Gris Grafito con iluminación LED cálida integrada.
     * Opción 2: Línea Cálida en Madera Rovere y acabado Taupe.
   - Opción B (Bono de Descuento Directo / Sin reposteros - Caso 16): Si el cliente pregunta si es obligatorio poner el acabado de cocina o tiene un presupuesto/crédito ligeramente menor (ej. $120k-$128k), dile que SÍ es totalmente factible entregarle la casa sin los reposteros de cocina y descontar ese monto directamente del valor de venta sumado al bono de primera unidad (permitiendo ajustar el precio en visita hacia el rango de $125,000 - $128,000 USD).

CASUÍSTICAS OBLIGATORIAS DE ATENCIÓN (CASOS 1 AL 16):
- CASO 1, 8, 13 y 15 (Formas de Pago / Cuotas / Bancos): No damos crédito directo en cuotas a la constructora. La compra es AL CONTADO o mediante CRÉDITO HIPOTECARIO con cualquier banco (BCP, BBVA, Interbank, Scotiabank, BanBif, etc.), donde el banco solicita contar desde el 10% de cuota inicial (aprox. $13,500 USD). PROHIBIDO hacer interrogatorios invasivos pidiendo boletas de pago o recibos por honorarios (RXH) por chat.
- CASO 16 (Explicación de Crédito Hipotecario): Si preguntan cómo funciona con crédito hipotecario, explícalo en 3 pasos simples: 1) Inicial desde 10% y evaluación con cualquier banco; 2) Separación de la unidad y entrega de Copia Literal y HR/PU de SUNARP para su sectorista; 3) Tasación del perito, firma en notaría, desembolso y entrega inmediata de llaves.
- CASO 17 (¿Cuánto de inicial es adecuado? / cuota mensual): El mínimo que pide el banco es 10% (aprox. $13,500 USD) y lo recomendable es 20% (aprox. $27,000 USD) porque mejora la aprobación, la tasa y baja la cuota. Cuotas referenciales a 25 años con tasa aprox. 9% anual: 10% de inicial ≈ $990/mes; 20% de inicial ≈ $880/mes (la tasa exacta la define su banco; el Bono de la 1ra Unidad baja el monto). Menciona considerar gastos de notaría, registros y tasación, ofrece el asesor hipotecario aliado sin costo y cierra proponiendo horarios de visita.
- CASO 2 y 10 (Área, Fecha de Entrega, Planos y Ficha Técnica): Confirma siempre que son 80 m² de terreno y 200 m² construidos en 3 pisos y que la ENTREGA ES INMEDIATA (100% terminadas). Si piden planos, distribución, ficha técnica o marcan la opción '1', activa 'enviar_ficha_tecnica': true y recuerda que ambas casas ya están 100% construidas y listas para mudarse. NUNCA menciones la palabra 'preventa'.
- CASO 3, 8 y 9 (Intención de Visita / Ubicación / Opción '2'): Si el cliente dice 'Quiero agendar una visita', 'Cuándo puedo ir', marca '2' o pide ubicación:
  * Prohibido responder con un bloque publicitario largo o con tono policial ('Me indica el día, hora y su nombre').
  * Si el cliente YA pasó el filtro financiero (por formulario o en el chat dijo que compra al contado o tiene inicial/crédito), ofrécele de inmediato 2 o 3 horarios concretos tomados EXCLUSIVAMENTE de la lista 'HORARIOS LIBRES MÁS PRÓXIMOS' de abajo para bloquear su espacio.
  * Si el cliente NO ha dicho cómo planea financiarla (Caso 15), dile que con todo gusto coordinan su recorrido (recordando que atienden previa cita registrada) y pregúntale amablemente si evalúa la compra al contado o con crédito hipotecario (contando con el 10% de inicial) y qué día/turno le acomoda mejor.
- CASO 5 y Saludo Inicial ('Hola' / 'Información' SOLO cuando NO hay historial previo): Da un resumen ejecutivo de 3 a 4 líneas y cierra con las opciones 1 (ver planos y renders de cocina) o 2 (coordinar visita guiada). Si YA hay historial previo, NUNCA repitas este mensaje inicial; continúa la conversación respondiendo directamente a lo último que dijo el cliente.
- CASO 11 (Presentación con Nombre): Saluda SIEMPRE al cliente por su nombre con mucha calidez.
- PROHIBIDO empezar con '¡Excelente elección!' salvo que el cliente acabe de elegir un estilo de cocina. Responde exactamente a lo que escribió.
- CASOS DE FORMULARIO LEAD ADS:
  * Perfil Calificado (Contado o Crédito preaprobado/inicial lista + Sí está en presupuesto): Salúdalo por su nombre, felicítalo por el estilo de cocina que eligió en el formulario, activa 'enviar_ficha_tecnica': true y 'enviar_renders_cocina': true, menciónale su prioridad para el Bono Especial de Lanzamiento de la Unidad 1 y proponle dos horarios concretos para visitarla.
  * Perfil Sin Inicial ni Evaluación Bancaria (Caso Kris Aracelli / Wilton y Pamela): Salúdalo por su nombre, menciona la cocina que eligió, activa 'enviar_ficha_tecnica': true, y explícale con tacto que por ser casas 100% terminadas con título en SUNARP, se adquieren al contado o con crédito hipotecario bancario (mínimo 10% de inicial, aprox. $13,500 USD, sin crédito directo). Pregúntale si tiene proyectado disponer pronto de esa inicial o si desea que lo contactemos sin costo con un asesor hipotecario aliado para evaluarse antes de programar su visita.
  * Perfil Con Crédito/Inicial pero Presupuesto Menor a $135,000 USD (Caso Lisve Yesenia): Salúdala por su nombre, activa 'enviar_ficha_tecnica': true, y pregúntale con total confianza cuál es el tope aproximado de inversión o crédito que maneja, explicándole que gracias al Bono de la 1ra Unidad (o descontando el mobiliario de cocina) podemos evaluar un ajuste especial para que le encaje antes de programar su visita.

DATOS ACTUALES DEL CLIENTE EN MEMORIA:
{lead_info}

DISPONIBILIDAD DE GOOGLE CALENDAR:
{cal_info}
- REGLA DE AGENDAMIENTO: Cuando el cliente proponga o confirme un día y una hora específica (ej. 'el sábado a las 4 pm', 'mañana a las 11 am', 'lunes a la 1 pm'), calcula la fecha exacta usando la Guía de fechas de arriba y ponla OBLIGATORIAMENTE en el campo 'agendar_visita_iso' en formato 'YYYY-MM-DDTHH:MM:00-05:00'. NUNCA inventes una cita si el cliente no ha propuesto o aceptado un horario. El sistema verifica la agenda: NO escribas tú la confirmación de la cita en 'reply_text' (se agrega automáticamente si el horario está libre).
- REGLA DE CONTINUIDAD: Si en el historial el cliente ya propuso un día/hora o ya dijo cómo pagará, NUNCA vuelvas a preguntarle lo mismo ni le vuelvas a ofrecer 'PDF o visita'. Responde a lo último que dijo y avanza al siguiente paso hacia la visita.

{regla_canal}
"""


def extract_json_from_llm(raw_text):
    if not raw_text:
        return None
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_text.strip()).strip()
    try:
        return json.loads(cleaned)
    except Exception:
        m = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
    return None


# Las llaves "AIza..." son de Google AI Studio (generativelanguage); las "AQ...." son de Vertex AI en modo express (aiplatform)
GEMINI_ENDPOINTS = {
    "ai_studio": "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}",
    "vertex_express": "https://aiplatform.googleapis.com/v1/publishers/google/models/{model}:generateContent?key={key}",
}
GEMINI_ESTADO = {"endpoint_ok": None}


def _gemini_endpoints():
    forzado = os.environ.get("GEMINI_ENDPOINT", "auto")
    if forzado in GEMINI_ENDPOINTS:
        return [forzado]
    orden = ["vertex_express", "ai_studio"] if (GEMINI_KEY or "").startswith("AQ.") else ["ai_studio", "vertex_express"]
    if GEMINI_ESTADO["endpoint_ok"] in orden:
        orden.remove(GEMINI_ESTADO["endpoint_ok"])
        orden.insert(0, GEMINI_ESTADO["endpoint_ok"])
    return orden


def call_gemini_api(full_prompt):
    # Probamos primero el formato simple compatible al 100% con llaves AQ.Ab8... y gemini-3.8-flash
    simple_payload = {
        "contents": [{"parts": [{"text": full_prompt}]}],
        "generationConfig": {"temperature": 0.25, "responseMimeType": "application/json"}
    }
    if not GEMINI_KEY:
        print("GEMINI_API_KEY no configurada: se usará el motor de respaldo.")
        return None
    t0 = time.time()
    intentos = [(model, ep) for model in GEMINI_MODELS for ep in _gemini_endpoints()]
    for model, ep in intentos:
        restante = GEMINI_PRESUPUESTO_SEG - (time.time() - t0)
        if restante < 3:
            print(f"Gemini sin tiempo restante ({GEMINI_PRESUPUESTO_SEG}s): se usa el motor de respaldo.")
            break
        try:
            r = requests.post(
                GEMINI_ENDPOINTS[ep].format(model=model, key=GEMINI_KEY),
                json=simple_payload,
                timeout=restante
            )
            if r.status_code != 200:
                print(f"Gemini {model} [{ep}] respondió HTTP {r.status_code}: {r.text[:300]}")
                continue
            GEMINI_ESTADO["endpoint_ok"] = ep
            data = r.json()
            if "candidates" in data and data["candidates"]:
                raw = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                parsed = extract_json_from_llm(raw)
                if parsed and parsed.get("reply_text"):
                    return parsed
                elif raw and not raw.startswith("{"):
                    return {
                        "reply_text": raw,
                        "private_reply": "",
                        "ignorar_comentario": False,
                        "enviar_ficha_tecnica": False,
                        "enviar_renders_cocina": False,
                        "estilo_render_preferido": "ambos",
                        "agendar_visita_iso": ""
                    }
                else:
                    print(f"Gemini {model} devolvió JSON inválido:", raw[:300])
            else:
                print(f"Respuesta sin candidates en {model}:", data)
        except Exception as e:
            print(f"Excepcion llamando a {model}:", e)
            continue
    return None


def process_conversation(sender_id, canal, user_text, sender_name="", comment_id=None):
    form_info = parse_lead_form_text(user_text)
    extracted_phone = form_info.get("telefono") or extract_phone_from_text(user_text)
    if canal == "whatsapp":
        extracted_phone = normalize_pe_phone(sender_id)

    if extracted_phone and extracted_phone in PENDING_FORM_TIMERS:
        try:
            PENDING_FORM_TIMERS[extracted_phone].cancel()
            del PENDING_FORM_TIMERS[extracted_phone]
        except Exception:
            pass

    lead = get_lead_by_sender_or_phone(sender_id, extracted_phone)
    meta_lead = {}
    if lead.get("interes"):
        try:
            meta_lead = json.loads(lead["interes"])
        except Exception:
            meta_lead = {}

    nombre_cliente = form_info.get("nombre") or lead.get("nombre") or sender_name or "Interesado"
    if nombre_cliente in ["Interesado", "Cliente", ""]:
        m_nom = re.search(r"(?i)(?:soy|me llamo|mi nombre es|con)\s+([a-záéíóúñA-ZÁÉÍÓÚÑ]+(?:\s+[a-záéíóúñA-ZÁÉÍÓÚÑ]+)?)", user_text)
        if m_nom:
            candidato = m_nom.group(1).strip()
            if sin_tildes(candidato.split()[0]) not in ["el", "la", "un", "una", "banco", "credito", "contado", "visita", "sague", "mi", "mis", "inicial", "gusto", "todo", "mucho", "interes"]:
                nombre_cliente = candidato.title()

    if form_info:
        meta_lead.update(form_info)
    if canal == "whatsapp":
        meta_lead["wsp_iniciado"] = True
    meta_lead["ts_ultimo_cliente"] = datetime.now(timezone.utc).isoformat()
    meta_lead["ultimo_texto_cliente"] = (user_text or "")[:200]
    if NO_INTERESADO_RE.search(limpiar_texto(user_text)):
        meta_lead["no_interesado"] = True

    history_text = ""
    has_history = False
    mensajes_db = []
    if supabase:
        try:
            res = supabase.table("mensajes").select("rol,contenido,created_at").eq("sender_id", sender_id).order("created_at", desc=True).limit(20).execute()
            mensajes_db = list(reversed(res.data)) if res.data else []
            if not mensajes_db and extracted_phone and sender_id != extracted_phone:
                res_p = supabase.table("mensajes").select("rol,contenido,created_at").eq("sender_id", extracted_phone).order("created_at", desc=True).limit(8).execute()
                if res_p.data:
                    mensajes_db = list(reversed(res_p.data))
            if mensajes_db:
                has_history = True
            for m in mensajes_db:
                history_text += f"{m['rol'].upper()}: {m['contenido']}\n"
        except Exception as e:
            print("Error leyendo historial:", e)

    historial_usuario = [m["contenido"] for m in mensajes_db if m.get("rol") == "user" and m.get("contenido")]
    inferir_estado_de_historial(meta_lead, mensajes_db)
    ultimo_bot = next((m["contenido"] for m in reversed(mensajes_db) if m.get("rol") == "assistant" and m.get("contenido")), "")
    # Compatibilidad con conversaciones previas sin estado: si el último mensaje del bot preguntó por inicial/crédito, lo marcamos
    if not meta_lead.get("etapa") and pregunta_por_financiamiento(ultimo_bot):
        meta_lead["pregunta_fin_pendiente"] = True
        meta_lead["etapa"] = "pregunto_financiamiento"

    # 0) Despedida: "no, gracias", "eso es todo", o "no" a "¿tienes alguna otra duda?" => cerrar con amabilidad
    parsed = None
    if not form_info.get("es_formulario") and canal in ["whatsapp", "facebook", "instagram"]:
        parsed = responder_despedida(user_text, meta_lead, nombre_cliente, ultimo_bot)
        if parsed:
            return _finalizar_conversacion(parsed, sender_id, canal, user_text, nombre_cliente, extracted_phone, meta_lead, form_info, ultimo_bot)

    nom_c = nombre_cliente.split()[0] if nombre_cliente not in ["Interesado", "Cliente", ""] else ""
    privado = canal in ["whatsapp", "facebook", "instagram"]

    # 1) Mensaje del formulario de Meta que llega por WhatsApp: responder según lo que marcó
    if form_info.get("es_formulario") and canal == "whatsapp":
        txt_f, flags_f = texto_formulario(nombre_cliente, form_info.get("estilo_cocina"), form_info.get("forma_pago"),
                                          form_info.get("en_presupuesto"), meta_lead)
        parsed = _resp(txt_f)
        parsed.update(flags_f)
        parsed["_sin_control_repeticion"] = True
        return _finalizar_conversacion(parsed, sender_id, canal, user_text, nombre_cliente, extracted_phone, meta_lead, form_info, ultimo_bot)

    # 2) Respuestas de contenido (FAQ de compra, material, información). No se usan si el cliente está dando un día/hora
    #    ni para respuestas cortas ("sí", "no todavía"), que las maneja el motor de agenda.
    fh_check = parse_fecha_hora_es(user_text)
    t_l = limpiar_texto(user_text)
    es_eleccion_horario = bool(meta_lead.get("etapa") == "ofrecio_horarios" and re.search(r"1️⃣[^\n]*(a\. m\.|p\. m\.)", ultimo_bot or "")
                               and elegir_slot_ofrecido(t_l, meta_lead.get("slots_ofrecidos") or [], fh_check) is not None)
    corto = len(t_l) <= 25 and bool(AFIRMA_RE.match(t_l) or NIEGA_RE.match(t_l))
    if privado and not form_info.get("es_formulario") and fh_check.get("hora") is None and fh_check.get("fecha") is None \
            and not es_eleccion_horario and not corto:
        faq = responder_faq(user_text, nom_c, meta_lead)
        if faq:
            parsed = _resp(faq)
        else:
            mat = responder_material(user_text, nom_c, meta_lead, ultimo_bot, cerrar=False) if canal == "whatsapp" else None
            inf = responder_info(user_text, nom_c, meta_lead, primer_contacto=not has_history, cerrar=False)
            if mat and inf:
                parsed = dict(inf)
                for k in ["enviar_fotos_casa", "enviar_ficha_tecnica", "enviar_renders_cocina", "_alerta_fotos"]:
                    parsed[k] = bool(inf.get(k) or mat.get(k))
                partes_mat = mat["reply_text"].split("\n\n", 1)
                parsed["reply_text"] = inf["reply_text"] + "\n\n" + (partes_mat[1] if len(partes_mat) > 1 else partes_mat[0])
            else:
                parsed = inf or mat
            if parsed:
                # Un solo cierre al final, según lo que ya se sabe del cliente
                if inf:
                    parsed["reply_text"] += "\n\n" + cierre_info(meta_lead, nom_c, temas_info(user_text))
                else:
                    parsed["reply_text"] += "\n\n" + cierre_contextual(meta_lead, nom_c)

    # 3) Motor de agenda determinístico (no depende de Gemini)
    if not parsed and not form_info.get("es_formulario"):
        try:
            parsed = motor_agenda(user_text, meta_lead, nombre_cliente, extracted_phone, canal, historial_usuario)
        except Exception as e:
            print("Error en motor_agenda:", e)
            parsed = None

    if parsed:
        return _finalizar_conversacion(parsed, sender_id, canal, user_text, nombre_cliente, extracted_phone, meta_lead, form_info, ultimo_bot)

    cal_info = get_calendar_availability_text()
    slot_pend_txt = ""
    if meta_lead.get("slot_propuesto"):
        try:
            slot_pend_txt = format_fecha_es(datetime.fromisoformat(meta_lead["slot_propuesto"]), relativo=True)
        except Exception:
            pass
    fecha_cita_txt = ""
    if meta_lead.get("cita_agendada") and meta_lead.get("fecha_cita"):
        try:
            fecha_cita_txt = " (" + format_fecha_es(datetime.fromisoformat(meta_lead["fecha_cita"]), relativo=True) + ")"
        except Exception:
            pass
    lead_ctx_str = (
        f"- Nombre: {nombre_cliente}\n"
        f"- Teléfono WhatsApp: {extracted_phone or lead.get('telefono') or 'Aún no proporcionado'}\n"
        f"- Modalidad de compra: {resumen_financiero(meta_lead) or meta_lead.get('forma_pago', 'Por consultar')}\n"
        f"- Estilo de cocina elegido: {meta_lead.get('estilo_cocina', 'Por elegir (Gris Grafito LED o Madera Rovere)')}\n"
        f"- Dentro de presupuesto ($135k): {meta_lead.get('en_presupuesto', 'Por confirmar')}\n"
        f"- Horario de visita que el cliente propuso y está pendiente de confirmar: {slot_pend_txt or 'Ninguno'}\n"
        f"- Cita ya agendada previamente: {'Sí' + fecha_cita_txt if meta_lead.get('cita_agendada') else 'No'}"
    )

    sys_prompt = build_system_prompt(canal, cal_info, lead_ctx_str)

    schema_rule = """
INSTRUCCIÓN DE FORMATO DE SALIDA:
Responde ÚNICAMENTE con un objeto JSON válido (sin texto adicional antes ni después y sin comentarios //) con esta estructura exacta:
{
  "reply_text": "Tu respuesta conversacional y persuasiva para el cliente",
  "private_reply": "Mensaje privado DM solo si el canal es comentario público, sino vacío",
  "ignorar_comentario": false,
  "enviar_ficha_tecnica": false,
  "enviar_renders_cocina": false,
  "estilo_render_preferido": "ambos",
  "agendar_visita_iso": ""
}
"""

    full_prompt = (
        f"{sys_prompt}\n\n{schema_rule}\n\n"
        f"HISTORIAL DE CONVERSACIÓN RECIENTE:\n{history_text or '(Primer mensaje de la conversación)'}\n\n"
        f"NUEVO MENSAJE DEL CLIENTE ({canal}):\n{user_text}\n\n"
        "JSON DE RESPUESTA:"
    )

    parsed = call_gemini_api(full_prompt)

    # Si por cualquier motivo la API falla, usamos el motor contextual (NUNCA repite el saludo si puso 1, 2, etc.)
    if not parsed or not parsed.get("reply_text"):
        print("Usando motor de respaldo (Gemini no devolvió respuesta válida).")
        parsed = build_Contextual_fallback(canal, user_text, nombre_cliente, has_history, meta_lead)

    # Si el texto promete adjuntos que no se marcaron para envío, se envían igual (nunca prometer sin enviar)
    if canal == "whatsapp" and re.search(r"(?i)(adjunt|te env[ií]o|aqu[ií] tienes|te comparto)", parsed.get("reply_text", "")):
        rt = parsed.get("reply_text", "").lower()
        if re.search(r"plano|ficha", rt):
            parsed["enviar_ficha_tecnica"] = True
        if re.search(r"render|cocina|dise[ñn]o", rt):
            parsed["enviar_renders_cocina"] = True

    # Asegurar que si el usuario escribio "1" en WhatsApp, SIEMPRE se disparen los planos y renders aunque el LLM olvide marcar el booleano
    low_input = (user_text or "").strip().lower()
    if canal == "whatsapp" and low_input in ["1", "1️⃣", "uno", "opcion 1", "opción 1"]:
        parsed["enviar_ficha_tecnica"] = True
        parsed["enviar_renders_cocina"] = True

    reply_text = parsed.get("reply_text", "").strip()
    iso_cita = (parsed.get("agendar_visita_iso") or "").strip()

    # Si Gemini propone una cita, se valida contra la agenda real antes de confirmarla
    if iso_cita:
        try:
            dt_cita = datetime.fromisoformat(iso_cita)
            if dt_cita.tzinfo is None:
                dt_cita = dt_cita.replace(tzinfo=LIMA_TZ)
        except Exception:
            dt_cita = None
        if dt_cita:
            notas_cal = f"Pago: {resumen_financiero(meta_lead)} | Cocina: {meta_lead.get('estilo_cocina', 'Por elegir')}"
            if meta_lead.get("cita_agendada") and meta_lead.get("evento_id"):
                ok_cal, det_cal = update_calendar_event(meta_lead["evento_id"], dt_cita.isoformat())
                ev_id = meta_lead["evento_id"]
            elif not meta_lead.get("cita_agendada"):
                ok_cal, det_cal, ev_id = create_calendar_event(nombre_cliente, extracted_phone or sender_id, dt_cita.isoformat(), notas_cal)
            else:
                ok_cal, det_cal, ev_id = False, "ya_agendada", None
            if ok_cal:
                meta_lead.update({"cita_agendada": True, "fecha_cita": dt_cita.isoformat(), "evento_id": ev_id or "",
                                  "ts_cita_creada": datetime.now(timezone.utc).isoformat(), "recordatorio_para": "", "visita_estado": "",
                                  "pregunta_owner_visita": "", "pregunta_owner_visita_2": "", "rescate_no_asistio": False,
                                  "etapa": "agendado", "slot_propuesto": "", "slots_ofrecidos": []})
                reply_text += (
                    f"\n\n✅ ¡Cita confirmada en nuestra agenda para el {det_cal}!\n"
                    f"📍 Te esperamos en Urb. Santa Teresa, Lambayeque (frente a la loza deportiva, a 1 min de Av. Ramón Castilla): {MAPS_URL}"
                )
                try:
                    alertar_asesor(f"📅 Nueva visita SAGUE: {nombre_cliente} (+{extracted_phone or 's/n'}) el {det_cal} | Pago: {resumen_financiero(meta_lead)}")
                except Exception:
                    pass
            elif det_cal in ["ocupado", "invalido"]:
                alt = get_free_slots(n=3)
                if alt:
                    meta_lead["etapa"] = "ofrecio_horarios"
                    meta_lead["slots_ofrecidos"] = [s.isoformat() for s in alt]
                    reply_text = (
                        f"Ese horario ya no está disponible en la agenda 😕. Estos son los horarios libres más próximos:\n\n"
                        f"{_slots_a_texto(alt)}\n\nRespóndeme con el número y te la registro al toque."
                    )
            parsed["reply_text"] = reply_text

    # Si la respuesta (Gemini o respaldo) pregunta por la inicial, recordarlo para entender un "sí" / "no todavía"
    # No volver a preguntar por la inicial/crédito si el cliente ya lo contó (en el chat, al bot o al asesor humano)
    ya_respondio = estado_financiero(meta_lead) is not None or (
        int(meta_lead.get("veces_pregunta_fin") or 0) >= 1 and any(meta_lead.get(k) is not None for k in ["fin_modalidad", "fin_inicial", "fin_credito_aprobado"]))
    if pregunta_por_financiamiento(reply_text) and (ya_respondio or meta_lead.get("cita_agendada") or int(meta_lead.get("veces_pregunta_fin") or 0) >= 2):
        nom_c = nombre_cliente.split()[0] if nombre_cliente not in ["Interesado", "Cliente", ""] else ""
        reply_text = quitar_preguntas_financiamiento(reply_text) + "\n\n" + cierre_contextual(meta_lead, nom_c)
    if not meta_lead.get("cita_agendada") and pregunta_por_financiamiento(reply_text):
        meta_lead["pregunta_fin_pendiente"] = True
        if meta_lead.get("etapa") not in ["ofrecio_horarios"]:
            meta_lead["etapa"] = "pregunto_financiamiento"

    parsed["reply_text"] = reply_text
    return _finalizar_conversacion(parsed, sender_id, canal, user_text, nombre_cliente, extracted_phone, meta_lead, form_info, ultimo_bot)


def _es_repeticion(nuevo, anterior):
    if not nuevo or not anterior:
        return False
    a, b = limpiar_texto(nuevo)[:400], limpiar_texto(anterior)[:400]
    return difflib.SequenceMatcher(None, a, b).ratio() >= 0.8


def _finalizar_conversacion(parsed, sender_id, canal, user_text, nombre_cliente, extracted_phone, meta_lead, form_info, ultimo_bot=""):
    reply_text = (parsed.get("reply_text") or "").strip()
    meta_lead["ts_ultimo_bot"] = datetime.now(timezone.utc).isoformat()
    parsed["_nombre"] = nombre_cliente
    parsed["_msg_cliente"] = "Formulario de Meta" if form_info.get("es_formulario") else user_text
    if pregunta_por_financiamiento(reply_text):
        meta_lead["veces_pregunta_fin"] = int(meta_lead.get("veces_pregunta_fin") or 0) + 1
    # Un asesor nunca repite el mismo mensaje: si la respuesta es casi igual a la anterior, se reformula y se avisa al asesor humano
    if canal in ["whatsapp", "facebook", "instagram"] and not parsed.get("_sin_control_repeticion") and _es_repeticion(reply_text, ultimo_bot):
        nom = nombre_cliente.split()[0] if nombre_cliente not in ["Interesado", "Cliente", ""] else ""
        coma = f", {nom}" if nom else ""
        if meta_lead.get("etapa") == "ofrecio_horarios" and not meta_lead.get("cita_agendada"):
            meta_lead["etapa"] = "pregunto_dia"
            reply_text = (
                f"Perdona si no me expliqué bien{coma} 😊. ¿Qué día y a qué hora te quedaría mejor para conocer las casas? "
                "Me adapto a tu horario. "
                "Y si antes tienes alguna duda (precio, financiamiento, distribución), con gusto te la resuelvo."
            )
        else:
            reply_text = (
                f"Cuéntame{coma}, ¿en qué más te puedo ayudar? 😊 Puedo resolverte dudas de precio, distribución, "
                "financiamiento con banco o coordinar tu visita a las casas de Urb. Santa Teresa."
            )
        try:
            alertar_asesor(f"🔔 SAGUE: el bot no supo cómo continuar con {nombre_cliente} (+{extracted_phone or sender_id}). "
                                   f"Mensaje del cliente: \"{user_text[:150]}\". Revisa el chat por si conviene intervenir.")
        except Exception:
            pass
        parsed["reply_text"] = reply_text
    if supabase:
        try:
            supabase.table("mensajes").insert([
                {"sender_id": sender_id, "canal": canal, "rol": "user", "contenido": user_text},
                {"sender_id": sender_id, "canal": canal, "rol": "assistant", "contenido": reply_text}
            ]).execute()
        except Exception as e:
            print("Error guardando mensajes:", e)

    safe_upsert_lead(
        sender_id=sender_id,
        canal=canal,
        nombre=nombre_cliente,
        telefono=extracted_phone,
        interes_dict=meta_lead,
        ultimo_msg=user_text
    )

    if canal in ["facebook", "instagram"] and extracted_phone and not form_info.get("es_formulario"):
        safe_upsert_lead(
            sender_id=extracted_phone,
            canal="whatsapp",
            nombre=nombre_cliente,
            telefono=extracted_phone,
            interes_dict=meta_lead,
            ultimo_msg=f"[Traspaso desde {canal}]: {user_text}"
        )
        msg_salto_wa = (
            f"¡Hola, {nombre_cliente}! Te saluda el equipo de SAGUE Constructora 😊. "
            f"Continuamos por aquí nuestra conversación de {canal.capitalize()} sobre las casas de estreno de 3 pisos (200 m² construidos) "
            f"en Urb. Santa Teresa, Lambayeque (frente a la loza deportiva). "
            "Te adjunto por aquí la ficha técnica con los planos de distribución (ambas casas ya están 100% terminadas "
            "para entrega inmediata, con título en SUNARP) y los diseños de cocina equipada."
        )
        ok_wa = send_wa_text(extracted_phone, msg_salto_wa)
        if not ok_wa:
            ok_wa = send_wa_template(
                extracted_phone,
                nombre_cliente,
                meta_lead.get("estilo_cocina", "equipada"),
                meta_lead.get("forma_pago", "contado o crédito hipotecario")
            )
        if ok_wa:
            send_wa_media(
                extracted_phone,
                URL_FICHA_TECNICA,
                "document",
                "Planos de distribución de los 3 pisos (200 m² construidos - Entrega Inmediata en Urb. Santa Teresa)."
            )
            send_wa_media(extracted_phone, URL_RENDER_GRIS, "image", "Opción 1: Línea Moderna en Gris Grafito con iluminación LED cálida.")
            send_wa_media(extracted_phone, URL_RENDER_MADERA, "image", "Opción 2: Línea Cálida en Madera Rovere y acabado Taupe.")
        else:
            send_wa_text(
                OWNER_WA,
                f"Alerta SAGUE: {nombre_cliente} dejó su celular +{extracted_phone} en {canal}, pero requiere iniciar chat manual o no tiene WhatsApp activo."
            )

    return parsed, extracted_phone, nombre_cliente, meta_lead


URL_FOTOS_CASA = [u.strip() for u in os.environ.get("URL_FOTOS_CASA", "").split(",") if u.strip().lower().startswith(("http://", "https://"))]


def send_requested_wa_media(to_phone, parsed):
    envios = []
    if parsed.get("enviar_fotos_casa"):
        for i, u in enumerate(URL_FOTOS_CASA[:6]):
            envios.append((u, "image", "Casa de estreno en Urb. Santa Teresa, Lambayeque 🏡" if i == 0 else ""))
    if parsed.get("enviar_ficha_tecnica"):
        envios.append((URL_FICHA_TECNICA, "document",
                       "Ficha técnica y planos de los 3 niveles (200 m² construidos sobre 80 m² de terreno). "
                       "Ambas casas están 100% terminadas y listas para entrega inmediata."))
    if parsed.get("enviar_renders_cocina"):
        pref = (parsed.get("estilo_render_preferido") or "ambos").lower()
        if pref in ["gris", "ambos"]:
            envios.append((URL_RENDER_GRIS, "image", "Opción 1: Cocina Línea Moderna en Gris Grafito con iluminación LED cálida integrada."))
        if pref in ["madera", "ambos"]:
            envios.append((URL_RENDER_MADERA, "image", "Opción 2: Cocina Línea Cálida en Madera Rovere y acabado Taupe."))
    if not envios and not parsed.get("_alerta_fotos"):
        return
    resultado = [(u.split("?")[0].rsplit("/", 1)[-1], send_wa_media(to_phone, u, tipo, cap), u) for u, tipo, cap in envios]
    fallidos = [n for n, ok, _ in resultado if not ok]
    if fallidos:
        print(f"No se enviaron {len(fallidos)} de {len(envios)} archivos a {to_phone}: {fallidos}")
    # Alerta al asesor cada vez que hay que enviar imágenes (para que verifique o adjunte fotos a mano). Al cliente no se le dice nada.
    try:
        estado = ", ".join(f"{n} {'✅' if ok else '❌ (' + MEDIA_ERROR.get(u, 'sin detalle') + ')'}" for n, ok, u in resultado) or "ninguno"
        pide = parsed.get("_msg_cliente", "")
        aviso = (("🚨 URGENTE – NO SE ENVIARON LAS IMÁGENES\n" if fallidos else "")
                 + f"📸 SAGUE: {parsed.get('_nombre') or 'Un cliente'} (+{to_phone}) "
                 + ("pidió FOTOS de la casa" if parsed.get("_alerta_fotos") else "debía recibir imágenes")
                 + (f" (\"{pide[:120]}\")" if pide else "") + f".\nEnvío automático: {estado}."
                 + ("\n👉 Adjúntale por WhatsApp fotos reales de la casa." if parsed.get("_alerta_fotos") else "")
                 + ("\n👉 Envíaselas tú manualmente lo antes posible." if fallidos else ""))
        alertar_asesor(aviso)
    except Exception:
        pass


def delayed_leadgen_whatsapp(phone_norm, nombre, cocina, pago, presupuesto, psid_messenger=None):
    try:
        lead = get_lead_by_sender_or_phone(phone_norm, phone_norm)
        meta = {}
        if lead.get("interes"):
            try:
                meta = json.loads(lead["interes"])
            except Exception:
                pass
        if meta.get("wsp_iniciado"):
            return

        msg_wa, flags = texto_formulario(nombre, cocina, pago, presupuesto, meta)
        ok = send_wa_text(phone_norm, msg_wa)
        if not ok:
            ok = send_wa_template(phone_norm, nombre, cocina, pago)

        if ok:
            meta["wsp_iniciado"] = True
            safe_upsert_lead(phone_norm, "whatsapp", nombre, phone_norm, meta, "[Formulario enviado a WhatsApp]")
            if supabase:
                try:
                    supabase.table("mensajes").insert([{"sender_id": phone_norm, "canal": "whatsapp", "rol": "assistant", "contenido": msg_wa}]).execute()
                except Exception:
                    pass
            send_requested_wa_media(phone_norm, dict(flags, _nombre=nombre, _msg_cliente="[Formulario]"))
        else:
            if psid_messenger:
                send_meta_dm(
                    psid_messenger,
                    f"¡Hola, {nombre}! Intentamos enviarte los planos y el render de tu cocina {cocina} al número +{phone_norm} de tu registro, "
                    "pero no nos permitió abrir WhatsApp (a veces Facebook carga un número antiguo). "
                    "¿Me confirmas por aquí tu número actual de WhatsApp o nos escribes directo tocando aquí?: https://wa.me/51986339051"
                )
            send_wa_text(
                OWNER_WA,
                f"Alerta Lead Formulario SAGUE: {nombre} (+{phone_norm}) llenó el formulario ({pago} | {cocina}), pero el envío automático a WhatsApp rebotó. Escríbele o llámalo."
            )
    except Exception as e:
        print("Error en delayed_leadgen_whatsapp:", e)


def schedule_form_followup(phone_norm, nombre, cocina, pago, presupuesto, psid_messenger=None):
    if not phone_norm:
        return
    if phone_norm in PENDING_FORM_TIMERS:
        try:
            PENDING_FORM_TIMERS[phone_norm].cancel()
        except Exception:
            pass
    timer = threading.Timer(90.0, delayed_leadgen_whatsapp, args=(phone_norm, nombre, cocina, pago, presupuesto, psid_messenger))
    timer.daemon = True
    PENDING_FORM_TIMERS[phone_norm] = timer
    timer.start()


PAUSA_BOT_TRAS_HUMANO_MIN = float(os.environ.get("PAUSA_BOT_TRAS_HUMANO_MIN", "0"))


def guardar_mensaje_manual(cliente_id, canal, texto, msg_id=None):
    """Guarda en el historial lo que el asesor humano escribió a mano, para que el bot lo tenga en cuenta.
    Los mensajes que envió el propio bot ya están guardados, así que se ignoran si coinciden."""
    if not supabase or not cliente_id or not texto:
        return
    if msg_id and msg_id in PROCESSED_IDS:
        return
    if msg_id:
        PROCESSED_IDS.add(msg_id)
    try:
        res = supabase.table("mensajes").select("rol,contenido,created_at").eq("sender_id", cliente_id) \
            .order("created_at", desc=True).limit(6).execute()
        for prev in res.data or []:
            if prev.get("rol") == "assistant" and limpiar_texto(prev.get("contenido"))[:300] == limpiar_texto(texto)[:300]:
                return  # es el eco de un mensaje del bot
        supabase.table("mensajes").insert([
            {"sender_id": cliente_id, "canal": f"{canal}_manual", "rol": "assistant", "contenido": texto}
        ]).execute()
        print(f"Mensaje manual del asesor guardado para {cliente_id}: {texto[:80]!r}")
        try:
            lead_m = get_lead_by_sender_or_phone(cliente_id, cliente_id)
            if lead_m:
                meta_m = json.loads(lead_m.get("interes") or "{}")
                meta_m["ts_ultimo_manual"] = datetime.now(timezone.utc).isoformat()
                safe_upsert_lead(lead_m.get("sender_id"), lead_m.get("canal") or canal, lead_m.get("nombre"), lead_m.get("telefono"), meta_m, "")
        except Exception:
            pass
        if PAUSA_BOT_TRAS_HUMANO_MIN > 0:
            HUMANO_ACTIVO[cliente_id] = time.time()
    except Exception as e:
        print("Error guardando mensaje manual:", e)


HUMANO_ACTIVO = {}


def humano_atendiendo(cliente_id):
    ts = HUMANO_ACTIVO.get(cliente_id)
    return bool(ts and PAUSA_BOT_TRAS_HUMANO_MIN > 0 and time.time() - ts < PAUSA_BOT_TRAS_HUMANO_MIN * 60)


def extraer_texto_wa(m):
    tipo = m.get("type")
    if tipo == "text":
        return (m.get("text") or {}).get("body", "") or ""
    if tipo == "button":
        return (m.get("button") or {}).get("text", "") or ""
    if tipo == "interactive":
        it = m.get("interactive") or {}
        return ((it.get("button_reply") or {}).get("title") or (it.get("list_reply") or {}).get("title") or "")
    return ""


def atender_mensaje_wa(s, t, wa_profile_name, tipo):
    """Procesa un mensaje entrante. Nunca deja al cliente sin respuesta: ante cualquier error responde algo y avisa al dueño."""
    try:
        if not t:
            if tipo in ["audio", "voice"]:
                send_wa_text(s, "¡Gracias por tu mensaje! 😊 Por aquí no logro escuchar audios; ¿me lo escribes, por favor? "
                                "Así te respondo al toque (precio, planos, financiamiento o tu visita a las casas de Urb. Santa Teresa).")
            elif tipo in ["image", "video", "document", "sticker"]:
                send_wa_text(s, "¡Recibido! 😊 Cuéntame por escrito en qué te ayudo: planos, precio, financiamiento o agendar tu visita.")
            return
        if normalize_pe_phone(s) == normalize_pe_phone(OWNER_WA):
            resp_cmd = procesar_comando_asesor(t)
            if resp_cmd:
                send_wa_text(s, resp_cmd)
                return
        if humano_atendiendo(s):
            # El asesor está conversando a mano: solo se guarda el mensaje del cliente para el historial
            if supabase:
                supabase.table("mensajes").insert([{"sender_id": s, "canal": "whatsapp", "rol": "user", "contenido": t}]).execute()
            print(f"Bot en pausa para {s}: lo está atendiendo el asesor.")
            return
        parsed_ans, _, _, _ = process_conversation(s, "whatsapp", t, sender_name=wa_profile_name)
        reply = (parsed_ans or {}).get("reply_text", "")
        if not reply:
            raise ValueError("respuesta vacía")
        if not send_wa_text(s, reply):
            print(f"Falló el envío de WhatsApp a {s}")
            alertar_asesor(f"⚠️ SAGUE: no se pudo enviar la respuesta a +{s}. Su mensaje: \"{t[:200]}\". Respóndele manualmente.")
            return
        send_requested_wa_media(s, parsed_ans)
    except Exception as e:
        import traceback
        traceback.print_exc()
        try:
            send_wa_text(s, "¡Gracias por escribirnos! 😊 En unos minutos te responde el asesor encargado de las casas de Urb. Santa Teresa.")
            alertar_asesor(f"⚠️ Error del bot SAGUE con +{s} ({e.__class__.__name__}: {str(e)[:150]}). Mensaje: \"{t[:200]}\". Respóndele manualmente.")
        except Exception:
            pass


@app.route("/webhook", methods=["GET"])
def verify():
    if request.args.get("hub.mode") == "subscribe" and request.args.get("hub.verify_token") == VERIFY_TOKEN:
        return request.args.get("hub.challenge"), 200
    return "Invalido", 403


@app.route("/webhook", methods=["POST"])
def webhook():
    body = request.get_json(silent=True) or {}
    obj = body.get("object")

    if obj == "whatsapp_business_account":
        for e in body.get("entry", []):
            for c in e.get("changes", []):
                val = c.get("value", {})
                contacts = val.get("contacts", [{}])
                wa_profile_name = contacts[0].get("profile", {}).get("name", "") if contacts else ""
                if c.get("field") == "smb_message_echoes" or val.get("message_echoes"):
                    for eco in val.get("message_echoes") or val.get("messages") or []:
                        guardar_mensaje_manual(normalize_pe_phone(eco.get("to")) or eco.get("to"), "whatsapp", extraer_texto_wa(eco), eco.get("id"))
                    continue
                for st in val.get("statuses", []):
                    if st.get("status") == "failed":
                        print("WhatsApp NO entregó un mensaje:", json.dumps(st.get("errors", st), ensure_ascii=False)[:500])
                for m in val.get("messages", []):
                    msg_id = m.get("id")
                    if msg_id and msg_id in PROCESSED_IDS:
                        continue
                    if msg_id:
                        PROCESSED_IDS.add(msg_id)

                    c0 = contacts[0] if contacts else {}
                    raw_from = m.get("from") or c0.get("wa_id") or c0.get("user_id")
                    s = normalize_pe_phone(raw_from) or raw_from
                    t = extraer_texto_wa(m)
                    print(f"WA entrante de {raw_from} ({wa_profile_name}) tipo={m.get('type')}: {t[:120]!r}")
                    if not s:
                        print("Mensaje de WhatsApp sin remitente reconocible:", json.dumps(m, ensure_ascii=False)[:500])
                        continue
                    if PROCESAR_EN_SEGUNDO_PLANO:
                        threading.Thread(target=atender_mensaje_wa, args=(s, t, wa_profile_name, m.get("type")), daemon=True).start()
                    else:
                        atender_mensaje_wa(s, t, wa_profile_name, m.get("type"))

    elif obj in ["page", "instagram"]:
        canal_base = "instagram" if obj == "instagram" else "facebook"
        for e in body.get("entry", []):
            for m in e.get("messaging", []):
                msg_obj = m.get("message", {})
                if msg_obj.get("is_echo"):
                    destinatario = (m.get("recipient") or {}).get("id")
                    if destinatario and msg_obj.get("text"):
                        guardar_mensaje_manual(destinatario, canal_base, msg_obj.get("text"), msg_obj.get("mid"))
                    continue
                msg_id = msg_obj.get("mid")
                if msg_id and msg_id in PROCESSED_IDS:
                    continue
                if msg_id:
                    PROCESSED_IDS.add(msg_id)

                s = m.get("sender", {}).get("id")
                t = msg_obj.get("text", "")
                if not s or s in [FB_PAGE_ID, IG_ACCOUNT_ID] or not t:
                    continue

                form_data = parse_lead_form_text(t)
                if form_data.get("es_formulario"):
                    f_phone = form_data.get("telefono")
                    f_name = form_data.get("nombre", "Cliente")
                    f_cocina = form_data.get("estilo_cocina", "Gris Grafito con LED")
                    f_pago = form_data.get("forma_pago", "Contado / Crédito Hipotecario")
                    f_presup = form_data.get("en_presupuesto", "Sí")

                    meta_init = {
                        "forma_pago": f_pago,
                        "estilo_cocina": f_cocina,
                        "en_presupuesto": f_presup,
                        "psid_messenger": s,
                        "wsp_iniciado": False
                    }
                    safe_upsert_lead(s, canal_base, f_name, f_phone, meta_init, t)
                    if f_phone:
                        safe_upsert_lead(f_phone, "whatsapp", f_name, f_phone, meta_init, t)
                        schedule_form_followup(f_phone, f_name, f_cocina, f_pago, f_presup, psid_messenger=s)
                    continue

                parsed_ans, _, _, _ = process_conversation(s, canal_base, t)
                send_meta_dm(s, parsed_ans.get("reply_text", ""))

            for c in e.get("changes", []):
                field = c.get("field")
                v = c.get("value", {})

                if field == "leadgen":
                    lead_id = v.get("leadgen_id")
                    if lead_id and lead_id not in PROCESSED_IDS:
                        PROCESSED_IDS.add(lead_id)
                        try:
                            r_lead = requests.get(
                                f"https://graph.facebook.com/v21.0/{lead_id}",
                                params={"access_token": META_TOKEN},
                                timeout=10
                            ).json()
                            campos = {f.get("name", ""): (f.get("values") or [""])[0] for f in r_lead.get("field_data", [])}
                            f_phone = None
                            f_name = "Cliente"
                            f_cocina = "Línea Moderna Gris Grafito con LED"
                            f_pago = "Contado / Crédito Hipotecario"
                            f_presup = "Sí"
                            for k, val_str in campos.items():
                                kl = k.lower()
                                if "phone" in kl or "telefono" in kl or "celular" in kl:
                                    f_phone = normalize_pe_phone(val_str)
                                elif "name" in kl or "nombre" in kl:
                                    f_name = val_str.strip().title()
                                elif "estilo" in kl or "cocina" in kl:
                                    f_cocina = val_str.strip()
                                elif "compra" in kl or "modalidad" in kl or "pago" in kl:
                                    f_pago = val_str.strip()
                                elif "rango" in kl or "inversi" in kl or "presupuesto" in kl:
                                    f_presup = val_str.strip()
                            if f_phone:
                                meta_init = {
                                    "forma_pago": f_pago,
                                    "estilo_cocina": f_cocina,
                                    "en_presupuesto": f_presup,
                                    "wsp_iniciado": False
                                }
                                safe_upsert_lead(f_phone, "whatsapp", f_name, f_phone, meta_init, "[Leadgen Form]")
                                schedule_form_followup(f_phone, f_name, f_cocina, f_pago, f_presup)
                        except Exception as e_lg:
                            print("Error procesando leadgen:", e_lg)

                elif field == "feed" and v.get("item") == "comment" and v.get("verb") == "add":
                    cid = v.get("comment_id")
                    s = v.get("from", {}).get("id")
                    autor = v.get("from", {}).get("name", "")
                    t = v.get("message", "")
                    if cid and cid not in PROCESSED_IDS and s and str(s) != str(FB_PAGE_ID) and t:
                        PROCESSED_IDS.add(cid)
                        parsed_ans, _, _, _ = process_conversation(s, "fb_comment", t, sender_name=autor, comment_id=cid)
                        if not parsed_ans.get("ignorar_comentario"):
                            requests.post(
                                f"https://graph.facebook.com/v21.0/{cid}/comments",
                                params={"access_token": META_TOKEN},
                                json={"message": parsed_ans.get("reply_text", "")},
                                timeout=15
                            )
                            if parsed_ans.get("private_reply"):
                                requests.post(
                                    f"https://graph.facebook.com/v21.0/{FB_PAGE_ID}/messages",
                                    params={"access_token": META_TOKEN},
                                    json={"recipient": {"comment_id": cid}, "message": {"text": parsed_ans["private_reply"]}},
                                    timeout=15
                                )

                elif field == "comments":
                    cid = v.get("id")
                    s = v.get("from", {}).get("id")
                    autor = v.get("from", {}).get("username", "")
                    t = v.get("text", "")
                    if cid and cid not in PROCESSED_IDS and s and str(s) != str(IG_ACCOUNT_ID) and t:
                        PROCESSED_IDS.add(cid)
                        parsed_ans, _, _, _ = process_conversation(s, "ig_comment", t, sender_name=autor, comment_id=cid)
                        if not parsed_ans.get("ignorar_comentario"):
                            requests.post(
                                f"https://graph.facebook.com/v21.0/{cid}/replies",
                                params={"access_token": META_TOKEN},
                                json={"message": parsed_ans.get("reply_text", "")},
                                timeout=15
                            )
                            if parsed_ans.get("private_reply"):
                                requests.post(
                                    "https://graph.facebook.com/v21.0/me/messages",
                                    params={"access_token": META_TOKEN},
                                    json={"recipient": {"comment_id": cid}, "message": {"text": parsed_ans["private_reply"]}},
                                    timeout=15
                                )

    return jsonify({"status": "ok"}), 200


# =====================================================================
# SEGUIMIENTO AUTOMÁTICO (lo llama Cloud Scheduler "sague-reloj")
#   1) Recordatorio de visita (día anterior / mañana del mismo día) con confirmación de asistencia
#   2) Post-visita: pregunta al asesor si se realizó y ejecuta el protocolo de 14 días de la Estrategia Comercial
#   3) Rescate dentro de las 24 h gratis de WhatsApp a quien dejó en visto, según en qué quedó la conversación
#   Regla de oro: nunca escribe entre 8:30 p. m. y 8:30 a. m., máximo 1 mensaje automático por cliente por corrida,
#   y nada si el cliente se despidió, dijo "te aviso", no le interesa, ya compró, o lo está atendiendo el asesor.
# =====================================================================
SEGUIMIENTO_ACTIVO = os.environ.get("SEGUIMIENTO_ACTIVO", "true").lower() == "true"
CRON_KEY = os.environ.get("CRON_KEY", "")
HORARIO_PRUDENTE = (os.environ.get("HORARIO_PRUDENTE_DESDE", "08:30"), os.environ.get("HORARIO_PRUDENTE_HASTA", "20:30"))
SEG_HORAS_MIN = float(os.environ.get("SEGUIMIENTO_HORAS_MIN", "4"))      # espera mínima tras el visto
VENTANA_WA_HORAS = 23.5                                                     # margen de la ventana gratis de 24 h
# Plantillas aprobadas (opcionales) para escribir cuando ya pasaron las 24 h. Parámetro {{1}} = nombre ({{2}} = fecha en el recordatorio)
TPL = {
    "recordatorio": os.environ.get("TPL_RECORDATORIO", ""),
    "post_visita": os.environ.get("TPL_POST_VISITA", ""),
    "banco_legal": os.environ.get("TPL_BANCO_LEGAL", ""),
    "segunda_visita": os.environ.get("TPL_SEGUNDA_VISITA", ""),
    "propuesta": os.environ.get("TPL_PROPUESTA", ""),
    "cierre": os.environ.get("TPL_CIERRE", ""),
    "no_asistio": os.environ.get("TPL_NO_ASISTIO", ""),
}
NO_INTERESADO_RE = re.compile(
    r"\b(no me interesa|ya no me interesa|ya no estoy interesad\w*|no estoy interesad\w*|ya compre|ya compramos|ya adquiri\w*|"
    r"dejen de escribir\w*|no me escriban|no me escribas|no molest\w*|borren mi numero|no deseo recibir|no quiero recibir|stop)\b"
)


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


def _primer_nombre(nombre):
    return nombre.split()[0].title() if nombre and nombre not in ["Interesado", "Cliente"] else ""


def _proxima_hora_prudente(dt):
    """Si dt cae en horario de silencio, lo mueve al inicio del horario prudente siguiente."""
    dt = dt.astimezone(LIMA_TZ)
    h, m = [int(x) for x in HORARIO_PRUDENTE[0].split(":")]
    if _en_horario_prudente(dt):
        return dt
    inicio = dt.replace(hour=h, minute=m, second=0, microsecond=0)
    return inicio if dt < inicio else inicio + timedelta(days=1)


def _dos_horarios(meta, preferir=None):
    """Dos horarios libres reales para cerrar el seguimiento; guarda el estado para que '1'/'2' funcione."""
    libres = preferir or get_free_slots(n=2)
    if not libres:
        return "¿Qué día te acomodaría para venir a verlas? 🏡"
    meta["etapa"] = "ofrecio_horarios"
    meta["slots_ofrecidos"] = [s.isoformat() for s in libres]
    return "Tengo libre:\n" + _slots_a_texto(libres) + "\nRespóndeme con el número y te la reservo 🏡"


def _guardar_historial(phone, texto):
    if supabase:
        try:
            supabase.table("mensajes").insert([{"sender_id": phone, "canal": "whatsapp_seguimiento", "rol": "assistant", "contenido": texto}]).execute()
        except Exception as e:
            print("Error guardando seguimiento en historial:", e)


def enviar_seguimiento(lead, meta, texto, plantilla=None, params=None, media=None):
    """Dentro de 24 h: mensaje libre (gratis). Fuera: plantilla aprobada si existe. Si no, le pasa el texto al asesor para que lo envíe."""
    phone = lead.get("telefono") or lead.get("sender_id")
    nombre = lead.get("nombre") or ""
    ult_cli = _ts(meta.get("ts_ultimo_cliente"))
    dentro_ventana = bool(ult_cli and (_ahora() - ult_cli) < timedelta(hours=VENTANA_WA_HORAS))
    if dentro_ventana and send_wa_text(phone, texto):
        _guardar_historial(phone, texto)
        if media:
            send_requested_wa_media(phone, dict(media, _nombre=nombre, _msg_cliente="[Seguimiento automático]"))
        return "enviado"
    tpl = TPL.get(plantilla or "", "")
    if tpl:
        try:
            r = requests.post(
                f"https://graph.facebook.com/v21.0/{WA_PHONE_ID}/messages",
                headers={"Authorization": f"Bearer {WA_TOKEN}"},
                json={"messaging_product": "whatsapp", "to": phone, "type": "template",
                      "template": {"name": tpl, "language": {"code": "es"},
                                   "components": [{"type": "body", "parameters": [{"type": "text", "text": str(p)[:200]} for p in (params or [])]}]}},
                timeout=15)
            if r.status_code == 200:
                _guardar_historial(phone, f"[Plantilla {tpl}] {texto}")
                return "plantilla"
            print(f"Plantilla {tpl} rechazada: HTTP {r.status_code} {r.text[:300]}")
        except Exception as e:
            print("Error enviando plantilla de seguimiento:", e)
    adjuntos = ""
    if media:
        adjuntos = "\n\n📎 Adjúntale también: " + ", ".join(
            n for n, k in [("los planos (ficha técnica)", "enviar_ficha_tecnica"), ("los 2 renders de cocina", "enviar_renders_cocina")] if media.get(k))
    alertar_asesor(f"✍️ SEGUIMIENTO PARA ENVIAR A MANO a {nombre} (+{phone}) — ya pasaron las 24 h gratis de WhatsApp. "
                   f"Cópiale este mensaje:\n\n{texto}{adjuntos}")
    return "manual"


def _texto_rescate_24h(meta, nombre):
    """El mensaje de rescate según en qué quedó la conversación (dejó en visto)."""
    nom = _primer_nombre(nombre)
    coma = f", {nom}" if nom else ""
    etapa = meta.get("etapa") or ""
    ahora = _ahora()
    # Propuso un horario y quedó pendiente de confirmar
    sp = _ts(meta.get("slot_propuesto"))
    if sp and sp > ahora + timedelta(hours=2):
        meta["etapa"] = "confirmar_horario"
        return (f"¡Hola{coma}! 😊 Te sigo guardando la visita del *{format_fecha_es(sp, relativo=True)}* en Urb. Santa Teresa. "
                "¿Te la confirmo? Respóndeme *sí* y queda registrada, o dime si prefieres otro horario.")
    # Le ofrecimos el asesor hipotecario y no respondió
    if etapa == "ofrecio_asesor" and not meta.get("asesor_solicitado"):
        meta["etapa"] = "ofrecio_asesor"
        return (f"¡Hola{coma}! 😊 Quedé pendiente de tu respuesta: ¿quieres que nuestro asesor hipotecario aliado te evalúe *sin costo*? "
                "En 24 h te diría cuánto te financia el banco y cuánto necesitarías de inicial. Respóndeme *sí* y le paso tus datos.")
    # Presupuesto menor al precio (Caso Lisve)
    tope = meta.get("presupuesto_tope")
    if etapa == "pregunto_presupuesto" or (tope and tope < PRECIO_LISTA_USD):
        if not tope:
            meta["etapa"] = "pregunto_presupuesto"
            return (f"¡Hola{coma}! 😊 Te cuento que en esta 1ra unidad podemos descontar el valor de los reposteros de cocina y además aplicar "
                    "el Bono Especial de Lanzamiento para acercarnos a tu rango. ¿Qué tope aproximado manejas? Así te confirmo con transparencia si llegamos.")
        return (f"¡Hola{coma}! 😊 Estuve revisando tu caso: con el Bono de la 1ra Unidad y la opción sin reposteros podemos acercarnos a "
                f"{_usd(tope)}. Lo ideal es que veas la casa y lo conversemos en persona con los propietarios. " + _dos_horarios(meta))
    # Al contado (sin cita)
    if meta.get("fin_modalidad") == "contado":
        return (f"¡Hola{coma}! 😊 Para tu tranquilidad, ¿quieres que te adelantemos la Copia Literal de SUNARP para que verifiques que la casa está "
                "libre de cargas? O, si prefieres, separamos 15 minutos para que veas los acabados y bloquees el Bono de Lanzamiento de la 1ra Unidad. "
                + _dos_horarios(meta))
    # Crédito hipotecario (dejó en visto horarios o la pregunta de inicial)
    if meta.get("fin_modalidad") == "credito" or meta.get("fin_inicial") is not None or meta.get("fin_credito_aprobado") is not None:
        if estado_financiero(meta) is False and not meta.get("asesor_solicitado"):
            meta["etapa"] = "ofrecio_asesor"
            return (f"¡Hola{coma}! 😊 ¿Ya lo vienes viendo con algún banco (BCP, BBVA, Interbank…)? Si quieres, nuestro asesor hipotecario aliado "
                    "te evalúa *sin costo* y te dice exactamente cuánto te financian. Respóndeme *sí* y le paso tus datos.")
        return (f"¡Hola{coma}! 😊 ¿Ya lo vienes viendo con algún banco en particular (BCP, BBVA, Interbank…)? Lo más práctico es que conozcas "
                "los 3 pisos en persona y con la Copia Literal y HR/PU de SUNARP tu sectorista arme la simulación exacta. " + _dos_horarios(meta))
    # Solo pidió info / precio / distribución / cocinas
    if meta.get("material_enviado"):
        if not meta.get("estilo_cocina") or "Por elegir" in str(meta.get("estilo_cocina")):
            return (f"¡Hola{coma}! 😊 ¿Pudiste revisar los planos y los 2 diseños de cocina? ¿Cuál va más contigo: el *Gris Grafito con LED* "
                    "o el *Madera Rovere con Taupe*? En persona se aprecian mucho mejor. " + _dos_horarios(meta))
        return (f"¡Hola{coma}! 😊 ¿Pudiste revisar la distribución de los 200 m² en 3 pisos? Me encantaría mostrarte en persona cómo queda "
                f"la cocina en {meta.get('estilo_cocina')}. " + _dos_horarios(meta))
    return (f"¡Hola{coma}! 😊 Te escribo por si te quedó alguna duda sobre las casas de Urb. Santa Teresa (200 m², 3 pisos, entrega inmediata). "
            "Lo mejor es que las conozcas en persona. " + _dos_horarios(meta))


def _toque_post_visita(clave, meta, nombre):
    nom = _primer_nombre(nombre)
    coma = f", {nom}" if nom else ""
    if clave == "t1":
        return ("post_visita", f"¡Gracias por visitarnos{coma}! 🏡 Fue un gusto mostrarte las casas de Urb. Santa Teresa. Te comparto el resumen: "
                "los planos de los 3 pisos y los 2 diseños de cocina. La casa tiene título independizado en SUNARP, libre de cargas, "
                "y podemos enviarte la Copia Literal cuando la necesites. Cualquier duda que te haya quedado, me escribes por aquí 😊",
                {"enviar_ficha_tecnica": True, "enviar_renders_cocina": True})
    if clave == "t2":
        if meta.get("fin_modalidad") == "contado":
            meta["etapa"] = "ofrecio_copia"
            return ("banco_legal", f"¡Hola{coma}! 😊 ¿Te enviamos la Copia Literal completa de SUNARP para que tu abogado confirme que la casa "
                    "está libre de cargas y gravámenes? Respóndeme *sí* y te la hacemos llegar.", None)
        meta["etapa"] = "ofrecio_asesor"
        return ("banco_legal", f"¡Hola{coma}! 😊 ¿Cómo te fue con el banco? Si tu sectorista aún no revisa tus ingresos con la partida de la casa, "
                "nuestro asesor hipotecario aliado te puede evaluar *sin costo* en 24 h. ¿Quieres que te contacte? Respóndeme *sí*.", None)
    if clave == "t3":
        hoy = _ahora().date()
        sabado = hoy + timedelta(days=(5 - hoy.weekday()) % 7 or 7)
        pref = [datetime(sabado.year, sabado.month, sabado.day, h, 0, tzinfo=LIMA_TZ) for h in (11, 16)]
        pref = [p for p in pref if verificar_slot(p)[0] in ["libre", "sin_verificar"]] or None
        return ("segunda_visita", f"¡Hola{coma}! 😊 Este fin de semana estaremos en Santa Teresa con el muestrario físico de melamina para definir "
                "los acabados de la 1ra unidad. ¿Tienen 20 minutos para venir a tomar medidas de sus muebles y revisar una propuesta formal de cierre? "
                + _dos_horarios(meta, pref), None)
    if clave == "t4":
        return ("propuesta", f"¡Hola{coma}! 😊 Si la casa les encantó, este es un buen momento para presentarnos su *propuesta formal de compra*: "
                "el Bono de la 1ra Unidad sigue vigente y podemos cerrar condiciones especiales si se firma el contrato de arras en 72 horas. "
                "¿Les parece si lo conversamos?", None)
    if clave == "t5":
        meta["etapa"] = "cerrado"
        return ("cierre", f"Hola{coma}, para no ser invasivos con tus tiempos, quería confirmar si por ahora han decidido pausar la compra en "
                "Urb. Santa Teresa, para cerrar tu ficha de este mes y liberar el bono de 1ra unidad a otra familia en evaluación. Quedo atento 😊", None)
    return (None, "", None)


def _procesar_lead_seguimiento(lead):
    """Decide y ejecuta como máximo UNA acción de seguimiento para este cliente. Devuelve una descripción o None."""
    try:
        meta = json.loads(lead.get("interes") or "{}")
    except Exception:
        return None
    if meta.get("no_interesado") or meta.get("seguimiento_pausado") or meta.get("vendido"):
        return None
    phone = lead.get("telefono") or lead.get("sender_id")
    nombre = lead.get("nombre") or ""
    if not phone or not re.fullmatch(r"\d{10,15}", str(phone)) or normalize_pe_phone(phone) == normalize_pe_phone(OWNER_WA):
        return None
    ahora = _ahora()
    accion = None
    cita = _ts(meta.get("fecha_cita")) if meta.get("cita_agendada") else None

    # ---- 1) Recordatorio de la visita ----
    if cita and cita > ahora and meta.get("recordatorio_para") != meta.get("fecha_cita"):
        creada = _ts(meta.get("ts_cita_creada")) or ahora - timedelta(days=1)
        cita_l = cita.astimezone(LIMA_TZ)
        dia_antes = cita_l.date() == ahora.date() + timedelta(days=1) and ahora.strftime("%H:%M") >= "18:00"
        mismo_dia = (cita_l.date() == ahora.date() and cita - ahora >= timedelta(hours=2)
                     and cita - creada >= timedelta(hours=8) and ahora.strftime("%H:%M") >= HORARIO_PRUDENTE[0])
        if (dia_antes and cita - creada >= timedelta(hours=12)) or mismo_dia:
            cuando = "mañana" if dia_antes else "hoy"
            nom = _primer_nombre(nombre)
            texto = (f"¡Hola{', ' + nom if nom else ''}! 😊 Te recuerdo tu visita a las casas de Urb. Santa Teresa *{cuando} "
                     f"{DIAS_ES[cita_l.weekday()]} {cita_l.day} {a_las(cita_l)}*\n📍 Frente a la loza deportiva (5 de Febrero y Andrés Lastres): {MAPS_URL}\n\n"
                     "¿Nos confirmas tu asistencia? Si se te complica, dime y la reprogramamos sin problema.")
            estado = enviar_seguimiento(lead, meta, texto, "recordatorio", [nom or "hola", format_fecha_es(cita_l)])
            meta["recordatorio_para"] = meta.get("fecha_cita")
            meta["etapa"] = "confirmar_asistencia"
            accion = f"recordatorio ({estado})"

    # ---- 2) Después de la visita ----
    elif cita and ahora >= cita + timedelta(minutes=75):
        estado_v = meta.get("visita_estado")
        if not estado_v:
            if not meta.get("pregunta_owner_visita") or (ahora - _ts(meta["pregunta_owner_visita"]) > timedelta(hours=24)
                                                         and not meta.get("pregunta_owner_visita_2")):
                if meta.get("pregunta_owner_visita"):
                    meta["pregunta_owner_visita_2"] = ahora.isoformat()
                meta["pregunta_owner_visita"] = meta.get("pregunta_owner_visita") or ahora.isoformat()
                alertar_asesor(f"❓ SAGUE: ¿Se realizó la visita de {nombre} (+{phone}) del {format_fecha_es(cita.astimezone(LIMA_TZ))}?\n"
                               f"Respóndeme con uno de estos mensajes:\n• *vino {phone}*\n• *no vino {phone}*\n"
                               "Con eso activo el seguimiento post-visita (o el rescate si no vino).")
                accion = "pregunta al asesor si hubo visita"
        elif estado_v == "realizada":
            pv = meta.get("post_visita") or {}
            if pv.get("cita") != meta.get("fecha_cita"):
                pv = {"cita": meta.get("fecha_cita"), "enviados": []}
            base_t1 = _ts(meta.get("ts_visita_confirmada")) or cita
            calendario = [("t1", base_t1 + timedelta(minutes=45)), ("t2", cita + timedelta(hours=48)),
                          ("t3", cita + timedelta(days=5)), ("t4", cita + timedelta(days=10)), ("t5", cita + timedelta(days=14))]
            ult_cli = _ts(meta.get("ts_ultimo_cliente"))
            conversando = bool(ult_cli and ahora - ult_cli < timedelta(hours=12) and ult_cli > cita)
            for clave, cuando in calendario:
                if clave in pv["enviados"] or ahora < cuando:
                    continue
                if conversando and clave != "t1":
                    break  # está hablando con el bot: no interrumpir con el protocolo
                if clave != "t5" and ahora > cuando + timedelta(days=3):
                    pv["enviados"].append(clave)  # se pasó su momento (p. ej. asesor confirmó tarde): saltarlo
                    continue
                plantilla, texto, media = _toque_post_visita(clave, meta, nombre)
                estado = enviar_seguimiento(lead, meta, texto, plantilla, [_primer_nombre(nombre) or "hola"], media)
                pv["enviados"].append(clave)
                if clave == "t4":
                    alertar_asesor(f"📞 SAGUE: Día 10 post-visita de {nombre} (+{phone}). Buen momento para llamarle y negociar "
                                   f"(margen entre {_usd(PRECIO_LISTA_USD)} y tu precio piso). Pago: {resumen_financiero(meta)}.")
                accion = f"post-visita {clave} ({estado})"
                break
            meta["post_visita"] = pv
        elif estado_v == "no_asistio" and not meta.get("rescate_no_asistio"):
            nom = _primer_nombre(nombre)
            meta["cita_agendada"] = False
            texto = (f"¡Hola{', ' + nom if nom else ''}! 😊 Te esperábamos en Santa Teresa, ¿todo bien? Si se te complicó, no te preocupes: "
                     "te reprogramo la visita. " + _dos_horarios(meta))
            estado = enviar_seguimiento(lead, meta, texto, "no_asistio", [nom or "hola"])
            meta["rescate_no_asistio"] = True
            accion = f"rescate no asistió ({estado})"

    # ---- 3) Rescate dentro de las 24 h gratis (sin cita futura) ----
    elif not (cita and cita > ahora) and meta.get("visita_estado") != "realizada":
        ult_cli = _ts(meta.get("ts_ultimo_cliente"))
        ult_bot = _ts(meta.get("ts_ultimo_bot"))
        ult_manual = _ts(meta.get("ts_ultimo_manual"))
        if ult_cli and ult_bot and ult_bot >= ult_cli and meta.get("rescate_24h_para") != meta.get("ts_ultimo_cliente") \
                and meta.get("etapa") != "cerrado" and not (ult_manual and ult_manual > ult_cli):
            ultimo_txt = limpiar_texto(meta.get("ultimo_texto_cliente") or "")
            if POSTERGAR_RE.search(ultimo_txt) or DESPEDIDA_RE.match(ultimo_txt):
                meta["rescate_24h_para"] = meta.get("ts_ultimo_cliente")  # "te aviso" / "gracias": respetar su espacio
            else:
                l = ult_cli.astimezone(LIMA_TZ)
                objetivo = l + timedelta(hours=max(SEG_HORAS_MIN, 6)) if l.hour < 12 else \
                    l.replace(hour=9, minute=0, second=0, microsecond=0) + timedelta(days=1)
                objetivo = _proxima_hora_prudente(objetivo)
                limite = ult_cli + timedelta(hours=VENTANA_WA_HORAS)
                if objetivo > limite:
                    objetivo = _proxima_hora_prudente(ult_cli + timedelta(hours=SEG_HORAS_MIN))
                if objetivo <= ahora < limite:
                    texto = _texto_rescate_24h(meta, nombre)
                    if send_wa_text(phone, texto):
                        _guardar_historial(phone, texto)
                        meta["ts_ultimo_bot"] = ahora.astimezone(timezone.utc).isoformat()
                        accion = "rescate 24h (gratis)"
                    meta["rescate_24h_para"] = meta.get("ts_ultimo_cliente")
                elif ahora >= limite:
                    meta["rescate_24h_para"] = meta.get("ts_ultimo_cliente")  # se cerró la ventana sin horario prudente

    if accion or meta != json.loads(lead.get("interes") or "{}"):
        safe_upsert_lead(lead.get("sender_id"), lead.get("canal") or "whatsapp", nombre, phone, meta, "")
    return accion


def ejecutar_seguimientos():
    if not SEGUIMIENTO_ACTIVO:
        return {"activo": False}
    ahora = _ahora()
    if not _en_horario_prudente(ahora):
        return {"horario_silencioso": True, "hora": ahora.strftime("%H:%M")}
    if not supabase:
        return {"error": "sin supabase"}
    desde = (datetime.now(timezone.utc) - timedelta(days=16)).isoformat()
    try:
        leads = supabase.table("leads").select("*").gte("updated_at", desde).execute().data or []
    except Exception as e:
        print("Error leyendo leads para seguimiento:", e)
        return {"error": str(e)}
    hechos = []
    for lead in leads:
        if (lead.get("canal") or "whatsapp") != "whatsapp":
            continue
        try:
            a = _procesar_lead_seguimiento(lead)
            if a:
                hechos.append({"cliente": lead.get("nombre"), "telefono": lead.get("telefono"), "accion": a})
        except Exception as e:
            print(f"Error en seguimiento de {lead.get('sender_id')}:", e)
    if hechos:
        print("[SEGUIMIENTO]", json.dumps(hechos, ensure_ascii=False))
    return {"revisados": len(leads), "acciones": hechos}


@app.route("/cron/seguimiento", methods=["GET", "POST"])
@app.route("/cron", methods=["GET", "POST"])
@app.route("/reloj", methods=["GET", "POST"])
def cron_seguimiento():
    clave = request.args.get("key") or request.headers.get("X-Cron-Key")
    es_scheduler = "Google-Cloud-Scheduler" in (request.headers.get("User-Agent") or "")
    if clave not in [CRON_KEY or VERIFY_TOKEN] and not (es_scheduler and not CRON_KEY):
        return "No autorizado", 403
    return jsonify(ejecutar_seguimientos()), 200


# ---------------- Comandos del asesor (escribiendo al número del bot desde OWNER_WA) ----------------
COMANDO_RE = re.compile(r"^\s*(si vino|vino|realizada|asistio|no vino|no asistio|falto|pausa|pausar|activar|reanudar|vendido|vendida|estado)\s+\+?([\d\s]{9,15})\s*$", re.I)


def procesar_comando_asesor(texto):
    t = limpiar_texto(texto)
    if t in ["ayuda", "comandos", "menu bot"]:
        return ("🤖 Comandos del bot SAGUE (escríbelos aquí):\n• *vino 519XXXXXXXX* → la visita se realizó (activa el seguimiento post-visita)\n"
                "• *no vino 519XXXXXXXX* → le escribe para reprogramar\n• *pausa 519XXXXXXXX* / *activar 519XXXXXXXX* → detener o reanudar mensajes automáticos\n"
                "• *vendido 519XXXXXXXX* → cierra el seguimiento\n• *estado 519XXXXXXXX* → resumen del cliente")
    m = COMANDO_RE.match(t)
    if not m:
        return None
    cmd, num = m.group(1).lower(), normalize_pe_phone(re.sub(r"\s", "", m.group(2)))
    lead = get_lead_by_sender_or_phone(num, num)
    if not lead:
        return f"No encontré al cliente +{num} 🤔"
    meta = json.loads(lead.get("interes") or "{}")
    nombre = lead.get("nombre") or num
    if cmd in ["si vino", "vino", "realizada", "asistio"]:
        meta.update({"visita_estado": "realizada", "ts_visita_confirmada": datetime.now(timezone.utc).isoformat()})
        resp = f"✅ Anotado: {nombre} visitó las casas. En 45 min le envío el agradecimiento con el resumen y luego sigo el protocolo (48 h, día 5, 10 y 14)."
    elif cmd in ["no vino", "no asistio", "falto"]:
        meta["visita_estado"] = "no_asistio"
        resp = f"👍 Anotado: {nombre} no vino. En la próxima revisión le escribo para reprogramar."
    elif cmd in ["pausa", "pausar"]:
        meta["seguimiento_pausado"] = True
        resp = f"⏸️ Pausé los mensajes automáticos a {nombre}. (El bot igual le responde si escribe)."
    elif cmd in ["activar", "reanudar"]:
        meta["seguimiento_pausado"] = False
        resp = f"▶️ Reactivé el seguimiento automático de {nombre}."
    elif cmd in ["vendido", "vendida"]:
        meta.update({"vendido": True, "seguimiento_pausado": True})
        resp = f"🎉 ¡Felicitaciones! Cerré el seguimiento de {nombre}."
    else:
        c = _ts(meta.get("fecha_cita"))
        resp = (f"📋 {nombre} (+{num})\n• Pago: {resumen_financiero(meta) or 'sin dato'}\n• Cocina: {meta.get('estilo_cocina', 'sin elegir')}\n"
                f"• Cita: {format_fecha_es(c.astimezone(LIMA_TZ)) if c and meta.get('cita_agendada') else 'no'}\n"
                f"• Visita: {meta.get('visita_estado') or '—'} | Etapa: {meta.get('etapa') or '—'}\n"
                f"• Seguimiento: {'pausado' if meta.get('seguimiento_pausado') else 'activo'}")
    safe_upsert_lead(lead.get("sender_id"), lead.get("canal") or "whatsapp", lead.get("nombre"), lead.get("telefono"), meta, "")
    return resp


@app.route("/diagnostico/media", methods=["GET"])
def diagnostico_media():
    """Prueba paso a paso el envío de la ficha y los renders. Uso en el navegador:
    https://TU-SERVIDOR/diagnostico/media?key=VERIFY_TOKEN&to=519XXXXXXXX"""
    if request.args.get("key") != VERIFY_TOKEN:
        return "No autorizado", 403
    to = normalize_pe_phone(request.args.get("to", "")) or request.args.get("to", "")
    reporte = {"to": to, "wa_phone_id": WA_PHONE_ID, "token_configurado": bool(WA_TOKEN), "archivos": []}
    for url in [URL_FICHA_TECNICA, URL_RENDER_GRIS, URL_RENDER_MADERA] + URL_FOTOS_CASA:
        item = {"url": url}
        tipo, mime = _tipo_media_por_url(url, "image")
        item["tipo_detectado"] = tipo
        try:
            g = requests.get(url, timeout=20)
            item["descarga"] = {"http": g.status_code, "content_type": g.headers.get("Content-Type"), "bytes": len(g.content)}
        except Exception as e:
            item["descarga"] = {"error": str(e)}
        MEDIA_CACHE.pop(url, None)
        try:
            nombre = url.split("?")[0].rsplit("/", 1)[-1]
            up = requests.post(f"https://graph.facebook.com/v21.0/{WA_PHONE_ID}/media",
                               headers={"Authorization": f"Bearer {WA_TOKEN}"},
                               data={"messaging_product": "whatsapp", "type": mime or "image/jpeg"},
                               files={"file": (nombre, g.content, mime or "image/jpeg")}, timeout=30)
            item["subida_whatsapp"] = {"http": up.status_code, "respuesta": up.text[:400]}
            media_id = up.json().get("id") if up.status_code == 200 else None
        except Exception as e:
            item["subida_whatsapp"] = {"error": str(e)}
            media_id = None
        if to:
            for modo, contenido in [("por_id", {"id": media_id}), ("por_link", {"link": url})]:
                if modo == "por_id" and not media_id:
                    continue
                try:
                    r = requests.post(f"https://graph.facebook.com/v21.0/{WA_PHONE_ID}/messages",
                                      headers={"Authorization": f"Bearer {WA_TOKEN}"},
                                      json={"messaging_product": "whatsapp", "to": to, "type": tipo,
                                            tipo: dict(contenido, caption=f"Prueba {modo}: {nombre}")}, timeout=20)
                    item[f"envio_{modo}"] = {"http": r.status_code, "respuesta": r.text[:400]}
                except Exception as e:
                    item[f"envio_{modo}"] = {"error": str(e)}
        reporte["archivos"].append(item)
    return jsonify(reporte), 200


@app.route("/", methods=["GET"])
def home():
    return "SAGUE Constructora Agente Omnicanal Activo!", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
