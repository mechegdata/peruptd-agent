"""WhatsApp Cloud API: envío de texto, media (con subida y compresión) y plantillas."""
import time

import requests

from bot.canales import hub_bandeja, twilio_adapter
from bot.config import GRAPH_URL, WA_IMG_MAX_BYTES, WA_PHONE_ID, WA_TOKEN
from bot.estado import MEDIA_CACHE, MEDIA_ERROR
from bot.utils.telefono import destino_wa, normalize_pe_phone


def send_wa_text(to_phone, text):
    if not to_phone or not text:
        return False
    if hub_bandeja.es_simulado(to_phone):
        return hub_bandeja.guardar(to_phone, "texto", text)  # cliente simulado del AI Sales Hub: no sale a ningún canal
    if twilio_adapter.es_destino_twilio(to_phone):
        return twilio_adapter.enviar_texto(to_phone, text)  # cliente de EE. UU./Canadá por SMS o WhatsApp de Twilio
    clean_phone = normalize_pe_phone(to_phone) or str(to_phone).replace("+", "")
    try:
        r = requests.post(
            f"{GRAPH_URL}/{WA_PHONE_ID}/messages",
            headers={"Authorization": f"Bearer {WA_TOKEN}"},
            json={
                "messaging_product": "whatsapp",
                **destino_wa(clean_phone),
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
        real = "image/png" if data[:8] == b"\x89PNG\r\n\x1a\n" else ("image/jpeg" if data[:3] == b"\xff\xd8\xff" else None)
        if tipo == "image" and real and real != mime:
            print(f"{media_url}: dice {mime} pero es {real}; se sube como {real}")
            mime = real  # un PNG guardado como .jpg: WhatsApp lo rechaza si se declara mal el tipo
        if tipo == "image" and not real:
            print(f"{media_url}: no es JPG ni PNG (¿WEBP/HEIC?); se convierte a JPG")
        if tipo == "image" and (len(data) > WA_IMG_MAX_BYTES or not real):
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
            f"{GRAPH_URL}/{WA_PHONE_ID}/media",
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
    if hub_bandeja.es_simulado(to_phone):
        return hub_bandeja.guardar(to_phone, "media", media_url, {"leyenda": caption, "tipo_media": media_type})
    if twilio_adapter.es_destino_twilio(to_phone):
        return twilio_adapter.enviar_media(to_phone, media_url, caption)
    clean_phone = normalize_pe_phone(to_phone) or str(to_phone).replace("+", "")
    # Un .jpg se manda como imagen (antes la ficha .jpg iba como "documento PDF" y WhatsApp la rechazaba)
    media_type, mime = _tipo_media_por_url(media_url, media_type)
    media_id = subir_media_wa(media_url, media_type, mime)
    contenido = {"id": media_id} if media_id else {"link": media_url}
    if caption and media_type in ["image", "document", "video"]:
        contenido["caption"] = caption[:1024]
    if media_type == "document":
        contenido["filename"] = media_url.split("?")[0].rsplit("/", 1)[-1] or "Ficha_Tecnica_Santa_Teresa.pdf"
    payload = {"messaging_product": "whatsapp", **destino_wa(clean_phone), "type": media_type, media_type: contenido}
    try:
        r = requests.post(
            f"{GRAPH_URL}/{WA_PHONE_ID}/messages",
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
        **destino_wa(clean_phone),
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
        f"{GRAPH_URL}/{WA_PHONE_ID}/messages",
        headers={"Authorization": f"Bearer {WA_TOKEN}"},
        json=payload,
        timeout=15
    )
    return r.status_code == 200


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
