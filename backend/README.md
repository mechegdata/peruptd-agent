# Chatbot inmobiliario (WhatsApp · Messenger · Instagram)

Asesor comercial automático para inmobiliarias: responde por WhatsApp Business, califica al cliente (contado / crédito), agenda visitas en Google Calendar y hace el seguimiento post-visita. Primer cliente: **SAGUE Constructora** (Proyecto Santa Teresa, Lambayeque).

**Stack:** Python 3 · Flask · Google Cloud Run · Supabase · Gemini · WhatsApp Cloud API · Google Calendar · Cloud Scheduler.

```bash
# Primera vez después de clonar
sh scripts/instalar_hooks.sh   # o: powershell -ExecutionPolicy Bypass -File scripts\instalar_hooks.ps1
pip install -r requirements.txt

# Desplegar
gcloud run deploy sague-bot --source . --project sague-bot --region us-central1 --allow-unauthenticated
```

- Contexto para humanos e IA: [`CLAUDE.md`](CLAUDE.md)
- Documentación: [`docs/`](docs/README.md)
