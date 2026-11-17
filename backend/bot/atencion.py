"""Atiende un mensaje entrante de WhatsApp de punta a punta (nunca deja sin respuesta)."""
import time

from bot.agrupador import esperar_y_agrupar
from bot.asesor import procesar_comando_asesor
from bot.canales.alertas import alertar_asesor
from bot.canales.material import send_requested_wa_media
from bot.canales.whatsapp import send_wa_text
from bot.config import OWNER_WA
from bot import tenant
from bot.agente import atender_turno
from bot.conversacion.orquestador import process_conversation
from bot.crm import sincronizar_seguro
from bot.db import supabase
from bot.estado import IMAGEN_RESPONDIDA
from bot.handoff import humano_atendiendo
from bot.utils.telefono import normalize_pe_phone


def _sin_texto(s, tipo):
    """Audio / imagen / archivo sin texto. A una imagen se responde una sola vez cada 30 min (luego solo se avisa al asesor)."""
    if tipo in ["audio", "voice"]:
        send_wa_text(s, "¡Gracias por tu mensaje! 😊 Por aquí no logro escuchar audios; ¿me lo escribes, por favor? "
                        "Así te respondo al toque (precio, planos, financiamiento o tu visita a las casas de Urb. Santa Teresa).")
        return
    if tipo not in ["image", "video", "document"] or humano_atendiendo(s):
        return  # stickers y reacciones no necesitan respuesta
    alertar_asesor(f"📷 SAGUE: +{s} envió {'una imagen' if tipo == 'image' else 'un archivo'} sin texto. Revísalo en el chat por si necesita algo.")
    if time.time() - IMAGEN_RESPONDIDA.get(s, 0) < 1800:
        return  # ya se le respondió hace poco: no repetir "¡Recibido!"
    IMAGEN_RESPONDIDA[s] = time.time()
    send_wa_text(s, "¡Recibido! 😊 Cuéntame por escrito en qué te ayudo: planos, precio, financiamiento o agendar tu visita.")


def _guardar_sin_responder(s, t):
    if supabase:
        supabase.table("mensajes").insert([{"sender_id": s, "canal": "whatsapp", "rol": "user", "contenido": t}]).execute()


def _responder(s, t, wa_profile_name, canal_origen=None):
    """Arma y envía la respuesta a un texto ya agrupado."""
    if humano_atendiendo(s):
        _guardar_sin_responder(s, t)
        return
    if tenant.modo_catalogo():
        atender_turno(s, t, wa_profile_name, canal_origen)  # motor nuevo: NLU bilingüe + catálogo + motores
        sincronizar_seguro(s)
        return
    parsed_ans, _, _, _ = process_conversation(s, "whatsapp", t, sender_name=wa_profile_name)
    if (parsed_ans or {}).get("_no_responder"):
        return  # p. ej. un 👍 a "quedo atento": un asesor humano no contestaría
    reply = (parsed_ans or {}).get("reply_text", "")
    if not reply:
        raise ValueError("respuesta vacía")
    if not send_wa_text(s, reply):
        print(f"Falló el envío de WhatsApp a {s}")
        alertar_asesor(f"⚠️ SAGUE: no se pudo enviar la respuesta a +{s}. Su mensaje: \"{t[:200]}\". Respóndele manualmente.")
        return
    send_requested_wa_media(s, parsed_ans)
    sincronizar_seguro(s)  # Salesforce (si está activo): después de responder, para no demorar al cliente


def _fallo(s, t, e):
    import traceback
    traceback.print_exc()
    try:
        send_wa_text(s, "¡Gracias por escribirnos! 😊 En unos minutos te responde el asesor encargado de las casas de Urb. Santa Teresa.")
        alertar_asesor(f"⚠️ Error del bot SAGUE con +{s} ({e.__class__.__name__}: {str(e)[:150]}). Mensaje: \"{(t or '')[:200]}\". Respóndele manualmente.")
    except Exception:
        pass


def atender_mensaje_wa(s, t, wa_profile_name, tipo, canal="whatsapp", espera_base=None, canal_origen=None):
    """Procesa un mensaje entrante. Nunca deja al cliente sin respuesta: ante cualquier error responde algo y avisa al dueño.
    canal/espera_base: Twilio (SMS) usa la misma fila de motores con una espera de agrupación más corta."""
    try:
        if not t:
            _sin_texto(s, tipo)
            return
        if normalize_pe_phone(s) == normalize_pe_phone(OWNER_WA):
            resp_cmd = procesar_comando_asesor(t)
            if resp_cmd:
                send_wa_text(s, resp_cmd)
                return
        if humano_atendiendo(s):
            # El asesor está conversando a mano: solo se guarda el mensaje del cliente para el historial
            _guardar_sin_responder(s, t)
            print(f"Bot en pausa para {s}: lo está atendiendo el asesor.")
            return
        t = esperar_y_agrupar(s, t, canal=canal, perfil=wa_profile_name, base=espera_base)
        if t is None:
            return
        _responder(s, t, wa_profile_name, canal_origen)
    except Exception as e:
        _fallo(s, t, e)


def responder_lote_pendiente(s, t, wa_profile_name):
    """Para /cron: un lote de mensajes cuya petición murió esperando (reinicio de Cloud Run). Se responde igual."""
    try:
        _responder(s, t, wa_profile_name)
    except Exception as e:
        _fallo(s, t, e)
