"""Crea la aplicación Flask y registra todas las rutas (Blueprints)."""
from flask import Flask

from bot.config import MAX_SUBIDA_MB

from bot.rutas import (catalogo, cron, diagnostico, hub_api, hub_auth, hub_catalogo, hub_config, salesforce, salud, twilio,
                       webhook)


def create_app():
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = (MAX_SUBIDA_MB + 1) * 1024 * 1024     # tope de subidas del catálogo
    for modulo in (webhook, cron, diagnostico, salud, salesforce, twilio, catalogo, hub_api, hub_auth, hub_catalogo, hub_config):
        app.register_blueprint(modulo.bp)
    return app


app = create_app()
