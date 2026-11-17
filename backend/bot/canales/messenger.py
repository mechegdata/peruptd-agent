"""Envío de mensajes privados por Messenger / Instagram."""
import requests

from bot.config import GRAPH_URL, META_TOKEN


def send_meta_dm(recipient_id, text):
    if not recipient_id or not text:
        return False
    r = requests.post(
        f"{GRAPH_URL}/me/messages",
        params={"access_token": META_TOKEN},
        json={"recipient": {"id": recipient_id}, "message": {"text": text}},
        timeout=15
    )
    return r.status_code == 200
