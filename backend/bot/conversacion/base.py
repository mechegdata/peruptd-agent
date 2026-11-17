"""Helpers compartidos por los motores de respuesta."""


def _resp(texto):
    return {
        "reply_text": texto, "private_reply": "", "ignorar_comentario": False,
        "enviar_ficha_tecnica": False, "enviar_renders_cocina": False,
        "estilo_render_preferido": "ambos", "agendar_visita_iso": "", "_motor_agenda": True
    }
