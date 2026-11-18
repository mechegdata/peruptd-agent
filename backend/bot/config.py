"""Configuración: todas las variables de entorno y constantes del negocio."""
import os
from zoneinfo import ZoneInfo


LIMA_TZ = ZoneInfo("America/Lima")
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "SAGUE2026")
FB_PAGE_ID = os.environ.get("FB_PAGE_ID", "100000000000000")
IG_ACCOUNT_ID = os.environ.get("IG_ACCOUNT_ID", "")
WA_PHONE_ID = os.environ.get("WA_PHONE_ID", "100000000000000")
META_TOKEN = os.environ.get("META_ACCESS_TOKEN")
WA_TOKEN = os.environ.get("WA_ACCESS_TOKEN") or META_TOKEN
# Versión de la Graph API de Meta en un solo lugar (v21.0 deja de funcionar el 21-ene-2027)
GRAPH_API_VERSION = os.environ.get("GRAPH_API_VERSION", "v21.0")
GRAPH_URL = f"https://graph.facebook.com/{GRAPH_API_VERSION}"
# Clave secreta de la app de Meta (Panel de apps → Configuración → Básica). Con ella el webhook comprueba que cada aviso
# viene de verdad de Meta (cabecera X-Hub-Signature-256). Se aceptan varias separadas por coma (varias apps / clientes).
# Vacía = no se valida (solo se avisa en los registros).
META_APP_SECRETS = [x.strip() for x in os.environ.get("META_APP_SECRET", "").split(",") if x.strip()]
# false = modo observación: verifica y lo anota en los registros, pero no rechaza nada (para probar la clave sin riesgo)
FIRMA_META_EXIGIR = os.environ.get("FIRMA_META_EXIGIR", "false").lower() == "true"
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


# Visitas entre semana saliendo del trabajo (el asesor recibe en la noche). El fin de semana se ofrecen los horarios libres del calendario.
HORA_INICIO_NOCHE = int(os.environ.get("HORA_INICIO_NOCHE", "18"))                  # "saliendo del trabajo, desde las 6 p. m."
HORARIO_NOCHE_HASTA_TXT = os.environ.get("HORARIO_NOCHE_HASTA_TXT", "hasta las 8 o 9 p. m.")


# Tiempo máximo total para intentar Gemini (todos los modelos). Si se pasa, responde el motor de respaldo.
GEMINI_PRESUPUESTO_SEG = float(os.environ.get("GEMINI_PRESUPUESTO_SEG", "15"))


# "true" solo si el servidor mantiene CPU fuera del request (p. ej. Cloud Run con CPU siempre asignada)
PROCESAR_EN_SEGUNDO_PLANO = os.environ.get("PROCESAR_EN_SEGUNDO_PLANO", "false").lower() == "true"


# Modelos vigentes en nov-2026 (2.0 y 1.5 ya fueron retirados por Google; 2.5 no está disponible para proyectos nuevos)
GEMINI_MODELS = [m.strip() for m in os.environ.get(
    "GEMINI_MODELS", "gemini-3.8-flash,gemini-3.6-flash,gemini-3.5-flash-lite"
).split(",") if m.strip()]
GEMINI_TIMEOUT_MODELO_SEG = float(os.environ.get("GEMINI_TIMEOUT_MODELO_SEG", "8"))
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
_RENDERS_COMUN = f"{DEFAULT_BUCKET}/{os.environ.get('CARPETA_MATERIAL', 'santa-teresa')}/comun/renders"  # ahí están cocina_1/2.jpg
URL_RENDER_GRIS = _url_media(["URL_RENDER_GRIS", "RENDER_COCINA_1_URL"], f"{_RENDERS_COMUN}/cocina_2.jpg")  # gris = cocina_2.jpg
URL_RENDER_MADERA = _url_media(["URL_RENDER_MADERA", "RENDER_COCINA_2_URL"], f"{_RENDERS_COMUN}/cocina_1.jpg")  # madera = cocina_1.jpg
ALERTA_TEMPLATE = os.environ.get("ALERTA_TEMPLATE", "")  # plantilla aprobada (1 variable) para alertas fuera de las 24 h
WA_IMG_MAX_BYTES = 5 * 1024 * 1024  # límite de WhatsApp para imágenes
PRECIO_LISTA_USD = float(os.environ.get("PRECIO_LISTA_USD", "135000"))
PRECIO_CONTADO_USD = float(os.environ.get("PRECIO_CONTADO_USD", "130000"))   # al contado: desde este monto, negociable en la visita
PROPIETARIO_TXT = os.environ.get("PROPIETARIO_TXT", "el Ing. Henry Guevara, propietario de la constructora")

# --- Estado real de las casas (nov-2026). Fuente ÚNICA de verdad para todos los mensajes: no prometer más de lo que hay ---
# Las 2 casas están igual (NO son gemelas): 1er y 2do piso con acabados; 3er piso EN CASCO (construido y techado, sin tarrajear).
ESTADO_CASAS_CORTO = os.environ.get(
    "ESTADO_CASAS_CORTO", "los 2 primeros pisos con acabados y el 3er piso en casco (construido y techado, sin tarrajear)")
ESTADO_3ER_PISO_TXT = os.environ.get(
    "ESTADO_3ER_PISO_TXT",
    "El 3er piso se entrega *en casco*: está construido y techado, con la terraza y la estructura de la jardinera, pero sin "
    "tarrajeo, cerámica ni baranda (ahí está la terma). Así lo terminas a tu gusto")
ENTREGA_TXT = os.environ.get(
    "ENTREGA_TXT", "entrega inmediata con título en SUNARP (2 pisos terminados y el 3ro en casco, para que lo termines a tu gusto)")
# Las visitas se agendan desde esta fecha (p. ej. mientras se terminan detalles de obra). Vacío o ya pasada = sin restricción.
VISITAS_DESDE = os.environ.get("VISITAS_DESDE", "")
TASA_REFERENCIAL_TEA = float(os.environ.get("TASA_REFERENCIAL_TEA", "9"))   # % anual, solo referencial
PLAZO_REFERENCIAL_ANIOS = int(os.environ.get("PLAZO_REFERENCIAL_ANIOS", "25"))
AREA_CONSTRUIDA_M2 = float(os.environ.get("AREA_CONSTRUIDA_M2", "200"))
PRECIO_M2_DEPA_MIN = float(os.environ.get("PRECIO_M2_DEPA_MIN", "950"))     # comparativo de mercado (depa en Chiclayo)
PRECIO_M2_DEPA_MAX = float(os.environ.get("PRECIO_M2_DEPA_MAX", "1150"))


# --- Moneda y tipo de cambio (el precio de lista está en dólares) ---
# Tipo de cambio para dar montos aproximados en soles. TIPO_CAMBIO_AUTO=true (por defecto): el del BCRP (interbancario venta),
# actualizado solo cada 6 h. TIPO_CAMBIO_REFERENCIAL: respaldo si el BCRP no responde (o el valor fijo si AUTO=false; 0 = no dar soles).
TIPO_CAMBIO_REFERENCIAL = float(os.environ.get("TIPO_CAMBIO_REFERENCIAL", "3.45") or 0)
TIPO_CAMBIO_AUTO = os.environ.get("TIPO_CAMBIO_AUTO", "true").lower() == "true"
TIPO_CAMBIO_TEXTO = os.environ.get(
    "TIPO_CAMBIO_TEXTO",
    "el tipo de cambio del día de la firma en notaría (o el que aplique tu banco al desembolsar, si es con crédito)"
)
PRECIO_REF_CON_BONO_USD = float(os.environ.get("PRECIO_REF_CON_BONO_USD", "128000"))  # referencia para "con el bono quedaría por debajo de…"


# --- Después de agendar: con quién viene y movilidad ---
OFRECE_MOVILIDAD = os.environ.get("OFRECE_MOVILIDAD", "false").lower() == "true"     # la constructora recoge a la familia
MOVILIDAD_DESDE = os.environ.get("MOVILIDAD_DESDE", "Chiclayo")


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
URL_VIDEO_RECORRIDO = os.environ.get("URL_VIDEO_RECORRIDO", "")
URL_FOTOS_CASA = [u.strip() for u in os.environ.get("URL_FOTOS_CASA", "").split(",") if u.strip().lower().startswith(("http://", "https://"))]


def _url_opcional(valor):
    valor = (valor or "").strip()
    return valor if valor.lower().startswith(("http://", "https://")) else ""


# Fotos etiquetadas de la casa: el bot elige cuáles mandar según el momento de la conversación (ver conversacion/recursos.py).
# Lo recomendado es la tabla recursos_media (videos, fichas, fotos y renders por casa); estas variables son el respaldo.
# Vacía = esa foto no se usa. Sube las fotos al bucket 'recursos' de Supabase y pega aquí su link público.
CARPETA_MATERIAL = os.environ.get("CARPETA_MATERIAL", "santa-teresa")   # carpeta dentro del bucket 'recursos' (ver docs/GUIA_SUBIR_MATERIAL.md)
# Nombres de archivo que son renders aunque no digan "render" (opcional). En SAGUE no hace falta: manda la carpeta
# ('fotos' = fotos reales, 'renders' = renders con muebles).
NOMBRES_SIEMPRE_RENDER = [a.strip() for a in os.environ.get("NOMBRES_SIEMPRE_RENDER", "").split(",") if a.strip()]
FOTOS_CASA = {
    "fachada": _url_opcional(os.environ.get("URL_FOTO_FACHADA")),
    "sala": _url_opcional(os.environ.get("URL_FOTO_SALA")),          # sala-comedor amoblada como referencia
    "cocina": _url_opcional(os.environ.get("URL_FOTO_COCINA")),
    "dormitorio": _url_opcional(os.environ.get("URL_FOTO_DORMITORIO")),
    "bano": _url_opcional(os.environ.get("URL_FOTO_BANO")),
    "terraza": _url_opcional(os.environ.get("URL_FOTO_TERRAZA")),
    "cochera": _url_opcional(os.environ.get("URL_FOTO_COCHERA")),
    "jardin": _url_opcional(os.environ.get("URL_FOTO_JARDIN")),
}
# Si el asesor escribe a mano en un chat, el bot se calla ese tiempo en ese chat (0 = nunca se pausa)
PAUSA_BOT_TRAS_HUMANO_MIN = float(os.environ.get("PAUSA_BOT_TRAS_HUMANO_MIN", "120"))
# Varios mensajes seguidos del cliente ("De un piso" / "Quiero" / "No me alcanza") se juntan y se responden UNA vez
AGRUPAR_MENSAJES_SEG = float(os.environ.get("AGRUPAR_MENSAJES_SEG", "6"))


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


# =====================================================================
# OMNIAGENT (multi-cliente, Salesforce, Twilio). Todo apagado por defecto: SAGUE se comporta igual que antes.
# =====================================================================
TENANT_ID = os.environ.get("TENANT_ID", "sague")                     # cliente dueño de este despliegue (tablas nuevas)
PLAYBOOK_ARCHIVO = os.environ.get("PLAYBOOK_ARCHIVO", "playbook_sague_realestate.json")  # respaldo si no está en tenant_playbooks
# Colas persistentes (dedupe, agrupación de mensajes y espera de 90 s de Lead Ads) en Supabase. Si las tablas de
# docs/migraciones/002_omniagent.sql no existen, el bot sigue con la memoria del proceso (comportamiento anterior).
COLAS_PERSISTENTES = os.environ.get("COLAS_PERSISTENTES", "true").lower() == "true"
LEADAD_ESPERA_SEG = float(os.environ.get("LEADAD_ESPERA_SEG", "90"))

# --- Salesforce (REST API). Conectado = SALESFORCE_ACTIVO=true + credenciales de una Connected App / External Client App ---
SALESFORCE_ACTIVO = os.environ.get("SALESFORCE_ACTIVO", "false").lower() == "true"
SF_LOGIN_URL = os.environ.get("SF_LOGIN_URL", "")                      # https://<mi-dominio>.my.salesforce.com
SF_CLIENT_ID = os.environ.get("SF_CLIENT_ID", "")
SF_CLIENT_SECRET = os.environ.get("SF_CLIENT_SECRET", "")              # flujo Client Credentials
SF_JWT_USUARIO = os.environ.get("SF_JWT_USUARIO", "")                  # flujo JWT Bearer (usuario de integración)
SF_JWT_LLAVE_PRIVADA = os.environ.get("SF_JWT_LLAVE_PRIVADA", "").replace("\\n", "\n")
SF_JWT_AUDIENCE = os.environ.get("SF_JWT_AUDIENCE", "https://login.salesforce.com")   # test.salesforce.com en sandbox
SF_API_VERSION = os.environ.get("SF_API_VERSION", "v62.0")
SF_OWNER_ID = os.environ.get("SF_OWNER_ID", "")                        # asesor dueño de Leads y Events (vacío = usuario de la API)
SF_WEBHOOK_SECRETO = os.environ.get("SF_WEBHOOK_SECRETO", "")          # cabecera X-OmniAgent-Key de /webhook/salesforce

# --- Twilio (SMS y WhatsApp para EE. UU./Canadá) ---
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_SMS_FROM = os.environ.get("TWILIO_SMS_FROM", "")               # +1XXXXXXXXXX (o un Messaging Service SID MG...)
TWILIO_WA_FROM = os.environ.get("TWILIO_WA_FROM", "")                 # whatsapp:+1XXXXXXXXXX
TWILIO_URL_PUBLICA = os.environ.get("TWILIO_URL_PUBLICA", "")         # URL exacta configurada en Twilio (para validar la firma)
TWILIO_EXIGIR_FIRMA = os.environ.get("TWILIO_EXIGIR_FIRMA", "true").lower() == "true"
AGRUPAR_MENSAJES_SEG_SMS = float(os.environ.get("AGRUPAR_MENSAJES_SEG_SMS", "4"))  # Twilio corta a los 15 s: espera más corta

# --- Capa 1: intérprete semántico bilingüe (bot/nlu_normalizer.py) ---
NLU_LLM_ACTIVO = os.environ.get("NLU_LLM_ACTIVO", "true").lower() == "true"   # false = solo el léxico determinístico
NLU_PRESUPUESTO_SEG = float(os.environ.get("NLU_PRESUPUESTO_SEG", "2.0"))     # si el LLM tarda más, manda el léxico

# --- CRM del cliente (bot/crm.py + bot/crm_adapters). Con crm_type 'peruptd_native' no hace falta: el CRM es Supabase ---
CRM_SYNC_ACTIVO = os.environ.get("CRM_SYNC_ACTIVO", os.environ.get("SALESFORCE_ACTIVO", "false")).lower() == "true"

# --- AI Sales Hub en modo API en vivo (bot/rutas/hub_api.py). Sin HUB_API_KEY la API del Hub queda apagada ---
HUB_API_KEY = os.environ.get("HUB_API_KEY", "")
HUB_CORS_ORIGINS = [o.strip() for o in os.environ.get("HUB_CORS_ORIGINS", "").split(",") if o.strip()]  # si el Hub se sirve en otro dominio
