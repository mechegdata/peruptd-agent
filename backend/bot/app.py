"""Crea la aplicación Flask y registra todas las rutas (Blueprints)."""
from flask import Flask

from bot.rutas import catalogo, cron, diagnostico, hub_api, salesforce, salud, twilio, webhook


def create_app():
    app = Flask(__name__)
    for modulo in (webhook, cron, diagnostico, salud, salesforce, twilio, catalogo, hub_api):
        app.register_blueprint(modulo.bp)
    return app


app = create_app()
