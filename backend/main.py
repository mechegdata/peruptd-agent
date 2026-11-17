"""Punto de entrada para Cloud Run (gunicorn main:app). La lógica vive en el paquete bot/."""
import os

from bot.app import app

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
