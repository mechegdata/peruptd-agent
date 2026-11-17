"""Conector de Salesforce (REST API): autenticación OAuth 2.0 (Client Credentials o JWT Bearer), Lead, Event, Task e
inventario. Ninguna función lanza errores: ante cualquier fallo registra el motivo y devuelve None, para que el bot
siga respondiendo al cliente aunque Salesforce no esté disponible."""
import re
import threading
import time

import requests

from bot.config import (SF_API_VERSION, SF_CLIENT_ID, SF_CLIENT_SECRET, SF_JWT_AUDIENCE, SF_JWT_LLAVE_PRIVADA, SF_JWT_USUARIO,
                        SF_LOGIN_URL, SF_OWNER_ID)

_TOKEN = {"access_token": None, "instance_url": None, "ts": 0.0}
_LOCK = threading.Lock()
_SIN_CAMPOS_PROPIOS = {}          # objeto -> hasta cuándo no enviar campos __c (no existen en la org)
_CACHE_INVENTARIO = {}            # soql -> (ts, registros)
TOKEN_VIGENCIA_SEG = 50 * 60
INVENTARIO_CACHE_SEG = 5 * 60


def configurado():
    return bool(SF_LOGIN_URL and SF_CLIENT_ID and (SF_CLIENT_SECRET or (SF_JWT_USUARIO and SF_JWT_LLAVE_PRIVADA)))


def _assertion_jwt():
    """JWT firmado con la llave privada del certificado de la Connected App (usa google-auth, ya instalado)."""
    from google.auth import crypt, jwt
    firmante = crypt.RSASigner.from_string(SF_JWT_LLAVE_PRIVADA)
    datos = {"iss": SF_CLIENT_ID, "sub": SF_JWT_USUARIO, "aud": SF_JWT_AUDIENCE, "exp": int(time.time()) + 180}
    token = jwt.encode(firmante, datos)
    return token.decode() if isinstance(token, bytes) else token


def _pedir_token():
    if SF_JWT_USUARIO and SF_JWT_LLAVE_PRIVADA:
        datos = {"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": _assertion_jwt()}
    else:
        datos = {"grant_type": "client_credentials", "client_id": SF_CLIENT_ID, "client_secret": SF_CLIENT_SECRET}
    r = requests.post(f"{SF_LOGIN_URL.rstrip('/')}/services/oauth2/token", data=datos, timeout=15)
    if r.status_code != 200:
        raise RuntimeError(f"OAuth de Salesforce rechazado: HTTP {r.status_code} {r.text[:200]}")
    j = r.json()
    _TOKEN.update(access_token=j["access_token"], instance_url=j.get("instance_url") or SF_LOGIN_URL, ts=time.time())


def _token(forzar=False):
    with _LOCK:
        if forzar or not _TOKEN["access_token"] or time.time() - _TOKEN["ts"] > TOKEN_VIGENCIA_SEG:
            _pedir_token()
        return _TOKEN["access_token"], _TOKEN["instance_url"].rstrip("/")


def _api(metodo, ruta, **kw):
    """Llamada autenticada a /services/data/<versión><ruta>. Renueva el token una vez si vence (401)."""
    for intento in (0, 1):
        token, base = _token(forzar=intento == 1)
        r = requests.request(metodo, f"{base}/services/data/{SF_API_VERSION}{ruta}",
                             headers={"Authorization": f"Bearer {token}"}, timeout=20, **kw)
        if r.status_code != 401:
            return r
    return r


def _ok(r, que):
    if r.status_code >= 300:
        print(f"Salesforce rechazó {que}: HTTP {r.status_code} {r.text[:300]}")
        return False
    return True


def soql_texto(valor):
    """Escapa un valor para ponerlo entre comillas simples en SOQL."""
    return str(valor or "").replace("\\", "\\\\").replace("'", "\\'")


def consultar(soql):
    try:
        r = _api("GET", "/query", params={"q": soql})
        return r.json().get("records", []) if _ok(r, "la consulta SOQL") else []
    except Exception as e:
        print("Error consultando Salesforce:", e)
        return []


def _guardar(objeto, registro_id, campos):
    """POST (nuevo) o PATCH (existente). Si la org no tiene los campos propios (__c), reintenta sin ellos."""
    if time.time() < _SIN_CAMPOS_PROPIOS.get(objeto, 0):
        campos = {k: v for k, v in campos.items() if not k.endswith("__c")}
    ruta = f"/sobjects/{objeto}/{registro_id}" if registro_id else f"/sobjects/{objeto}"
    r = _api("PATCH" if registro_id else "POST", ruta, json=campos)
    if r.status_code == 400 and "INVALID_FIELD" in r.text and any(k.endswith("__c") for k in campos):
        print(f"⚠️ La org no tiene algunos campos propios de {objeto} ({r.text[:160]}). Se envían solo los estándar 1 h.")
        _SIN_CAMPOS_PROPIOS[objeto] = time.time() + 3600
        r = _api("PATCH" if registro_id else "POST", ruta, json={k: v for k, v in campos.items() if not k.endswith("__c")})
    if not _ok(r, f"{'la actualización' if registro_id else 'la creación'} de {objeto}"):
        return None
    return registro_id or r.json().get("id")


def buscar_lead_por_telefono(telefono):
    digitos = re.sub(r"\D", "", str(telefono or ""))
    if len(digitos) < 7:
        return None
    try:
        r = _api("GET", "/search", params={"q": f"FIND {{{digitos[-10:]}}} IN PHONE FIELDS RETURNING Lead(Id WHERE IsConverted = false ORDER BY LastModifiedDate DESC LIMIT 1)"})
        encontrados = r.json().get("searchRecords", []) if _ok(r, "la búsqueda por teléfono") else []
        return encontrados[0]["Id"] if encontrados else None
    except Exception as e:
        print("Error buscando el Lead en Salesforce:", e)
        return None


def upsert_lead_from_chat(nombre, telefono, campos=None, lead_id=None, empresa="Individual"):
    """Crea o actualiza el Lead (busca por teléfono si no se conoce su Id). Devuelve el Id o None."""
    try:
        lead_id = lead_id or buscar_lead_por_telefono(telefono)
        partes = (nombre or "").strip().split(" ", 1)
        datos = {"Phone": telefono, "MobilePhone": telefono, **(campos or {})}
        if not lead_id:
            datos.update({"FirstName": partes[0] if len(partes) > 1 else None,
                          "LastName": (partes[1] if len(partes) > 1 else partes[0]) or "Interesado", "Company": empresa})
            if SF_OWNER_ID:
                datos["OwnerId"] = SF_OWNER_ID
        return _guardar("Lead", lead_id, {k: v for k, v in datos.items() if v is not None})
    except Exception as e:
        print("Error sincronizando el Lead con Salesforce:", e)
        return None


def create_salesforce_event(who_id, inicio, minutos, asunto, descripcion="", ubicacion="", event_id=None):
    """Event nativo vinculado al Lead y al asesor (OwnerId). Con event_id lo reprograma. Devuelve el Id o None."""
    try:
        fin = inicio.timestamp() + minutos * 60
        datos = {"Subject": asunto[:255], "StartDateTime": inicio.isoformat(),
                 "EndDateTime": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(fin)),
                 "Description": descripcion[:32000], "Location": ubicacion[:255] or None}
        if not event_id:
            datos.update({"WhoId": who_id, "IsReminderSet": True,
                          "ReminderDateTime": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(inicio.timestamp() - 86400))})
            if SF_OWNER_ID:
                datos["OwnerId"] = SF_OWNER_ID
        return _guardar("Event", event_id, {k: v for k, v in datos.items() if v is not None})
    except Exception as e:
        print("Error creando el Event en Salesforce:", e)
        return None


def update_event_attendance(event_id, status, nota="", campo_asistencia=None):
    """status = 'Attended' | 'No_Show'. Marca el asunto ([ATTENDED]/[NO-SHOW]) y, si existe, el campo propio."""
    try:
        r = _api("GET", f"/sobjects/Event/{event_id}", params={"fields": "Subject,Description"})
        if not _ok(r, "la lectura del Event"):
            return None
        ev = r.json()
        asunto = re.sub(r"^\[(ATTENDED|NO-SHOW)\]\s*", "", ev.get("Subject") or "")
        datos = {"Subject": f"[{'ATTENDED' if status == 'Attended' else 'NO-SHOW'}] {asunto}"[:255],
                 "Description": ((ev.get("Description") or "") + (f"\n\n{nota}" if nota else ""))[:32000]}
        if campo_asistencia:
            datos[campo_asistencia] = status
        return _guardar("Event", event_id, datos)
    except Exception as e:
        print("Error actualizando la asistencia en Salesforce:", e)
        return None


def log_chat_summary_note(who_id, asunto, cuerpo):
    """Resumen de la conversación como Task completada en la línea de tiempo del Lead."""
    try:
        datos = {"WhoId": who_id, "Subject": asunto[:255], "Description": cuerpo[:32000], "Status": "Completed",
                 "ActivityDate": time.strftime("%Y-%m-%d"), "TaskSubtype": "Task"}
        if SF_OWNER_ID:
            datos["OwnerId"] = SF_OWNER_ID
        return _guardar("Task", None, datos)
    except Exception as e:
        print("Error registrando el resumen en Salesforce:", e)
        return None


def fetch_active_inventory(soql):
    """Propiedades / tratamientos / servicios activos leídos de Salesforce, con caché de 5 minutos."""
    if not soql:
        return []
    ts, registros = _CACHE_INVENTARIO.get(soql, (0, None))
    if registros is not None and time.time() - ts < INVENTARIO_CACHE_SEG:
        return registros
    registros = consultar(soql)
    if registros:
        _CACHE_INVENTARIO[soql] = (time.time(), registros)
    return registros or (_CACHE_INVENTARIO.get(soql, (0, []))[1] or [])
