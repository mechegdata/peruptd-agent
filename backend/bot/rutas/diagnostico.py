"""Endpoint de diagnóstico del envío de media."""
from flask import Blueprint, jsonify, request
import requests

from bot.canales.whatsapp import _tipo_media_por_url
from bot.config import FOTOS_CASA, GRAPH_URL, URL_FICHA_TECNICA, URL_FOTOS_CASA, URL_RENDER_GRIS, URL_RENDER_MADERA, VERIFY_TOKEN, WA_PHONE_ID, WA_TOKEN
from bot.datos.recursos import resumen_catalogo
from bot.estado import MEDIA_CACHE
from bot.utils.telefono import destino_wa, normalize_pe_phone


bp = Blueprint("diagnostico", __name__)


@bp.route("/diagnostico/media", methods=["GET"])
def diagnostico_media():
    """Prueba paso a paso el envío de la ficha y los renders. Uso en el navegador:
    https://TU-SERVIDOR/diagnostico/media?key=VERIFY_TOKEN&to=519XXXXXXXX"""
    if request.args.get("key") != VERIFY_TOKEN:
        return "No autorizado", 403
    to = normalize_pe_phone(request.args.get("to", "")) or request.args.get("to", "")
    reporte = {"to": to, "wa_phone_id": WA_PHONE_ID, "token_configurado": bool(WA_TOKEN), "archivos": []}
    for url in [URL_FICHA_TECNICA, URL_RENDER_GRIS, URL_RENDER_MADERA] + URL_FOTOS_CASA + [u for u in FOTOS_CASA.values() if u]:
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
            up = requests.post(f"{GRAPH_URL}/{WA_PHONE_ID}/media",
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
                    r = requests.post(f"{GRAPH_URL}/{WA_PHONE_ID}/messages",
                                      headers={"Authorization": f"Bearer {WA_TOKEN}"},
                                      json={"messaging_product": "whatsapp", **destino_wa(to), "type": tipo,
                                            tipo: dict(contenido, caption=f"Prueba {modo}: {nombre}")}, timeout=20)
                    item[f"envio_{modo}"] = {"http": r.status_code, "respuesta": r.text[:400]}
                except Exception as e:
                    item[f"envio_{modo}"] = {"error": str(e)}
        reporte["archivos"].append(item)
    return jsonify(reporte), 200


@bp.route("/diagnostico/material", methods=["GET"])
def diagnostico_material():
    """Muestra qué fotos, renders, videos y fichas encontró el bot en el bucket. Uso en el navegador:
    https://TU-SERVIDOR/diagnostico/material?key=VERIFY_TOKEN"""
    if request.args.get("key") != VERIFY_TOKEN:
        return "No autorizado", 403
    return jsonify(resumen_catalogo()), 200
