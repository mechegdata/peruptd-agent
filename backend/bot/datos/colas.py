"""Colas persistentes en Supabase (migración 002): fragmentos de mensajes por agrupar y tareas diferidas (Lead Ads 90 s).
Todo lo que vive aquí sobrevive a un reinicio de Cloud Run: lo que quede pendiente lo termina /cron.
Si algo falla, cada función devuelve un valor que hace que el llamador siga con el comportamiento en memoria."""
from datetime import datetime, timedelta, timezone

from bot.config import TENANT_ID
from bot.datos import persistencia

T_LOTES = "debounce_batches"
T_TAREAS = "scheduled_jobs"


def _iso(segundos=0):
    return (datetime.now(timezone.utc) + timedelta(seconds=segundos)).isoformat()


# ---------------- Agrupación de mensajes ----------------

def encolar_fragmento(sender, texto, canal, perfil, espera_seg):
    """Guarda el fragmento y devuelve su id (o None si no hay persistencia: se usa la memoria)."""
    if not persistencia.disponible():
        return None
    try:
        r = persistencia.cliente().table(T_LOTES).insert({
            "tenant_id": TENANT_ID, "lead_phone": str(sender), "canal": canal, "combined_text": texto,
            "perfil": perfil or None, "execute_at": _iso(espera_seg), "status": "pending"}).execute()
        return (r.data or [{}])[0].get("id")
    except Exception as e:
        persistencia.desactivar(e)
        return None


def reclamar_lote(sender, mi_id, texto_propio):
    """Tras la espera: si llegó otro fragmento después, responde ese (None). Si no, toma todo lo pendiente del cliente
    y devuelve el texto unido. Ante un error devuelve el propio texto (mejor responder que callar)."""
    sb = persistencia.cliente()
    try:
        despues = sb.table(T_LOTES).select("id").eq("tenant_id", TENANT_ID).eq("lead_phone", str(sender)) \
            .eq("status", "pending").gt("id", mi_id).limit(1).execute()
        if despues.data:
            return None
        tomadas = sb.table(T_LOTES).update({"status": "tomado"}).eq("tenant_id", TENANT_ID) \
            .eq("lead_phone", str(sender)).eq("status", "pending").lte("id", mi_id).execute()
    except Exception as e:
        print("Error reclamando el lote de mensajes (se responde solo este mensaje):", e)
        return texto_propio
    filas = sorted(tomadas.data or [], key=lambda f: f.get("id") or 0)
    if not filas:
        return None  # ya lo respondió /cron u otra instancia
    return "\n".join(f.get("combined_text") or "" for f in filas)


def lotes_vencidos(gracia_seg=30, limite=50):
    """Lotes cuya petición murió esperando (reinicio): [(sender, texto, perfil, canal)], ya marcados como tomados."""
    if not persistencia.disponible():
        return []
    sb = persistencia.cliente()
    try:
        filas = sb.table(T_LOTES).select("id,lead_phone").eq("tenant_id", TENANT_ID).eq("status", "pending") \
            .lt("execute_at", _iso(-gracia_seg)).order("id").limit(limite).execute().data or []
    except Exception as e:
        persistencia.desactivar(e)
        return []
    ultimos = {}
    for f in filas:
        ultimos[f["lead_phone"]] = max(ultimos.get(f["lead_phone"], 0), f["id"])
    lotes = []
    for sender, ultimo in ultimos.items():
        try:
            tomadas = sb.table(T_LOTES).update({"status": "tomado"}).eq("tenant_id", TENANT_ID).eq("lead_phone", sender) \
                .eq("status", "pending").lte("id", ultimo).execute().data or []
        except Exception as e:
            print(f"Error tomando el lote vencido de {sender}:", e)
            continue
        if tomadas:
            tomadas.sort(key=lambda f: f.get("id") or 0)
            lotes.append((sender, "\n".join(f.get("combined_text") or "" for f in tomadas),
                          tomadas[-1].get("perfil") or "", tomadas[-1].get("canal") or "whatsapp"))
    return lotes


# ---------------- Tareas diferidas ----------------

def programar_tarea(tipo, clave, payload, espera_seg):
    """Registra la tarea (cancela otra pendiente igual). Devuelve su id, o None sin persistencia."""
    if not persistencia.disponible():
        return None
    try:
        cancelar_tareas(tipo, clave)
        r = persistencia.cliente().table(T_TAREAS).insert({
            "tenant_id": TENANT_ID, "tipo": tipo, "clave": str(clave), "payload": payload,
            "execute_at": _iso(espera_seg), "status": "pending"}).execute()
        return (r.data or [{}])[0].get("id")
    except Exception as e:
        persistencia.desactivar(e)
        return None


def reclamar_tarea(tarea_id):
    """True si a quien llama le toca ejecutarla (pending -> tomado es atómico). Sin id o ante un error: True."""
    if tarea_id is None:
        return True
    try:
        r = persistencia.cliente().table(T_TAREAS).update({"status": "tomado"}).eq("id", tarea_id) \
            .eq("status", "pending").execute()
        return bool(r.data)
    except Exception as e:
        print("Error reclamando tarea (se ejecuta igual):", e)
        return True


def cancelar_tareas(tipo, clave):
    if not persistencia.disponible():
        return
    try:
        persistencia.cliente().table(T_TAREAS).update({"status": "cancelado"}).eq("tenant_id", TENANT_ID) \
            .eq("tipo", tipo).eq("clave", str(clave)).eq("status", "pending").execute()
    except Exception as e:
        print("Error cancelando tarea:", e)


def tareas_vencidas(tipo, gracia_seg=60, limite=20):
    """Tareas que su timer no llegó a ejecutar (reinicio). Devuelve las filas ya tomadas por esta llamada."""
    if not persistencia.disponible():
        return []
    try:
        filas = persistencia.cliente().table(T_TAREAS).select("*").eq("tenant_id", TENANT_ID).eq("tipo", tipo) \
            .eq("status", "pending").lt("execute_at", _iso(-gracia_seg)).order("id").limit(limite).execute().data or []
    except Exception as e:
        persistencia.desactivar(e)
        return []
    return [f for f in filas if reclamar_tarea(f.get("id"))]


def limpiar_antiguos(dias=7):
    """Borra registros viejos para que las tablas no crezcan sin fin (lo llama /cron)."""
    if not persistencia.disponible():
        return
    limite = _iso(-dias * 86400)
    sb = persistencia.cliente()
    for tabla, campo, filtro in (("processed_webhooks", "created_at", None), (T_LOTES, "created_at", "tomado"),
                                 (T_TAREAS, "created_at", None)):
        try:
            q = sb.table(tabla).delete().lt(campo, limite)
            if filtro:
                q = q.eq("status", filtro)
            q.execute()
        except Exception as e:
            print(f"No se pudo limpiar {tabla}:", e)
