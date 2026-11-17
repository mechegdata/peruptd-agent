# Despliegue y operación

## Infraestructura actual

| Pieza | Valor |
|---|---|
| Proyecto GCP | `sague-bot` |
| Servicio Cloud Run | `sague-bot` · región `us-central1` · público (`--allow-unauthenticated`, lo necesita el webhook de Meta) |
| Scheduler | `sague-reloj` → `GET /cron` (seguimientos) |
| Base de datos | Supabase (tablas `leads`, `mensajes`; bucket público `recursos` con fichas y renders) |
| Calendar | Calendario del asesor compartido con la cuenta de servicio de Cloud Run |
| Webhook de Meta | `https://<url-cloud-run>/webhook` (WhatsApp, página de Facebook, Instagram, Lead Ads) |

## Desplegar (igual que antes)

La estructura nueva mantiene `main.py` con la variable `app` en la raíz, así que el comando no cambia:

```bash
gcloud run deploy sague-bot --source . --project sague-bot --region us-central1 --allow-unauthenticated
```

> Si en Cloud Shell ya tenías un `requirements.txt` o `Procfile`, conserva el tuyo y compáralo con el de este repo antes de desplegar.
> Las variables de entorno ya configuradas en el servicio se mantienen entre despliegues.

## Antes de desplegar

```bash
python scripts/generar_contexto.py --check   # docs al día
python -m compileall -q bot main.py         # compila
pytest -q                                   # pruebas de humo
```

## Recomendado: deploy automático desde GitHub

1. Subir este repo a GitHub (privado).
2. Cloud Run → servicio → "Configurar implementación continua" → elegir el repo y la rama `main`.
3. Desde entonces: `git push` = deploy. Crear un segundo servicio `sague-bot-staging` (rama `staging`) con un número de prueba de WhatsApp.

## Secretos (pendiente)

Mover `META_ACCESS_TOKEN`, `WA_ACCESS_TOKEN`, `GEMINI_API_KEY`, `SUPABASE_KEY`, `VERIFY_TOKEN`, `CRON_KEY` a **Secret Manager** y montarlos como variables:

```bash
gcloud run services update sague-bot --region us-central1 \
  --update-secrets=META_ACCESS_TOKEN=meta-access-token:latest,GEMINI_API_KEY=gemini-api-key:latest
```

## Diagnóstico rápido

| Síntoma | Dónde mirar |
|---|---|
| No responde | Logs de Cloud Run: buscar `WA entrante`, `Excepcion`, `HTTP 4xx` |
| No llegan imágenes | `GET /diagnostico/media?key=…&to=519…` (desactivar en producción cuando haya Secret Manager) |
| Alertas al asesor no llegan | Log `[ALERTA]`; `OWNER_WA` no puede ser el mismo número del bot; ventana de 24 h |
| Seguimientos no salen | Ejecutar `/cron?key=…` y revisar el JSON `acciones`; horario prudente 08:30-20:30 |
