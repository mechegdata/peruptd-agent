# PeruPTD Autonomous AI Sales Agent & Multi-CRM Hub

Producto multi-industria, bilingüe (ES/EN) y multi-CRM construido sobre el motor probado de SAGUE Constructora.
**SAGUE en producción no se toca**: este es un proyecto aparte. SAGUE entrará como primer tenant en modo `sague_legacy`.

```
peruptd-agent/
├── backend/   Python (Flask + Supabase + Gemini + Google Calendar) — copia del motor SAGUE + lo nuevo
└── hub/       PeruPTD AI Sales Hub (demo web para videos y ventas): src/ → build.py → dist/index.html
```

## Arquitectura (3 capas)

```
WhatsApp Cloud API ─┐                                                    ┌─> WhatsApp / SMS (texto + máx. 2 archivos)
Twilio SMS / WA ────┼─> dedupe (processed_webhooks) ─> debounce 15 s ───┤
Messenger / IG ─────┘    (debounce_batches; /cron termina lotes huérfanos)│
                                                                         │
 Capa 1  bot/nlu_normalizer.py   SemanticNormalizer → NormalizedTurn (pydantic)
         léxico ES/EN (bot/nlu/lexicon.json, ~1 ms) + Gemini Flash en JSON estricto (opcional, con presupuesto de tiempo)
 Capa 2  bot/engines/            catálogo · presupuesto (8 % / 20 % / inicial mínima + anualidad) · objeciones 1-2-3
                                 · agenda (calendario real, respeta "salgo del trabajo a las 6") · multimedia por momento
 Capa 3  bot/engines/guardas.py  frases prohibidas del playbook + anti-repetición ≥ 80 %
         bot/agente.py           envía, agenda, guarda la ficha viva, alerta al asesor
 CRM     bot/crm.py + bot/crm_adapters/   PeruPTD Native · Salesforce · HubSpot · Pipedrive · Zoho
```

Se conserva todo lo de SAGUE: 90 s a Lead Ads, pausa de 2 h cuando el asesor escribe (eco), rescate 24 h, comandos
`vino / no vino / pausa / activar / vendido / estado`, protocolo de 14 días y horario silencioso.

**Modo por tenant** (`tenants.pipeline_mode`): `catalogo` = motor nuevo (NLU + catálogo); `sague_legacy` = motor original.
Sin tabla `tenants`, el despliegue arranca en `sague_legacy` (variable `PIPELINE_MODE`).

## Catálogo dentro del CRM

El agente siempre lee `catalog_items` + `catalog_media` en Supabase (caché 5 min). Cada CRM los alimenta con
`POST /catalogo/sincronizar` (Cloud Scheduler o webhook del CRM):

| CRM | Catálogo | Lead / cita / nota |
|---|---|---|
| PeruPTD Native | el portal edita Supabase directo | columnas de `leads` |
| Salesforce | Product2 · PricebookEntry · ContentVersion (se copian al bucket `catalogo`) | Lead · Event · Task |
| HubSpot | crm/v3/objects/products | Contact + Deal · Meeting · Note |
| Pipedrive | /products | Person + Deal · Activity · Note |
| Zoho | Products | Leads (upsert por teléfono) · Events · Notes |

Convención de archivos para el cliente: `[PRICE_OBJECTION] Cochera.jpg`, `[SPECS_PDF] Planos.pdf`. Sin etiqueta:
imagen → FIRST_INFO, PDF → SPECS_PDF, video → VIDEO_TOUR.
Credenciales: `tenants.crm_credentials_json` guarda **referencias** a variables/secretos (`{"token_env": "HUBSPOT_TOKEN_ACME"}`), nunca la clave.

## Activación (orden)

1. Supabase: correr `backend/docs/migraciones/002_omniagent.sql`, `003_tenants_catalogo.sql` y (demos) `004_demo_catalogos.sql`.
   Crear el bucket público `catalogo`. `SUPABASE_KEY` debe ser la clave *service_role*.
2. Cloud Run (servicio nuevo, no el de SAGUE): `TENANT_ID`, `PIPELINE_MODE=catalogo`, claves de Meta/Gemini/Calendar de siempre.
   Si usa Twilio: `--no-cpu-throttling`, `TWILIO_*`, y en Twilio el webhook `https://<servicio>/webhook/twilio`.
3. CRM externo: `CRM_SYNC_ACTIVO=true` + credenciales; Salesforce usa `SF_*` (Connected App, Client Credentials o JWT).
4. Cloud Scheduler: `/cron` cada 5-10 min (seguimientos + colas huérfanas) y `/catalogo/sincronizar` cada hora.

Todas las variables están en `backend/.env.example` (se genera con `python scripts/generar_contexto.py`).

## Seguimiento por tenant (modo `catalogo`)

`bot/seguimiento/motor_catalogo.py` + `plantillas.py`: recordatorio, pregunta al asesor (75 min), protocolo de 14 días
(`post_45m`, `post_48h_contado` / `post_48h_financiado`, `post_dia5`, `post_dia10` + alerta al asesor, `post_dia14`),
no asistió y rescate de 24 h (`rescate_horarios`, `rescate_objecion`, `rescate_presupuesto`, `rescate_general`).
Textos en `playbook.seguimiento.{es,en}` con variables `{coma} {producto} {bono} {valor} {horarios} {cuota}…`; lo que
falte usa un texto neutro por defecto. Cada toque se apaga con `interruptores.seguimiento_<clave> = false`. Los adjuntos
salen del catálogo (`POST_VISIT_45M`, `OPTION_RENDER`, `RESCUE_24H`…), sin repetir. SAGUE (`sague_legacy`) no cambia.

## AI Sales Hub: modo API en vivo

- Sin backend (archivo suelto o el artifact de claude.ai) → datos de demostración, como siempre.
- Servido por el backend en `GET /hub` (mismo dominio) → pide la `HUB_API_KEY` una vez y se conecta.
- En otro dominio → botón **⚙** del Hub (URL + clave) y ese dominio en `HUB_CORS_ORIGINS`.
- Lee y escribe: catálogo (`PATCH` precios/bono/argumento), `POST /api/hub/catalogo/sincronizar`, Kanban (`/api/hub/leads`),
  acciones vino / no vino / pausa / vendido, y chat con el agente real usando un cliente simulado `hub:+1999…`
  (no sale nada por WhatsApp/SMS ni se crea la cita en el calendario real).
- Dentro de claude.ai la página no puede llamar a otros dominios (política del sitio): ahí siempre funciona en modo demo.
- `python hub/build.py` genera `hub/dist/index.html` y `backend/bot/static/hub.html`.

## Pruebas

`cd backend && python -m pytest -q` → 145 pruebas (79 originales de SAGUE + NLU, motores, colas, adaptadores, Twilio,
turno completo del agente y guardas por playbook).

## Pendiente (siguiente fase)

- **Portal web real (Next.js + Supabase)**: hoy el Hub es una demo autocontenida (datos en el navegador). Para construir
  la versión conectada a Supabase hace falta activar la instalación de paquetes (npm) en la configuración de red.
- **Plantillas de WhatsApp aprobadas por Meta** para los toques fuera de la ventana de 24 h en modo `catalogo`: hoy pasan al
  asesor para envío manual (el SMS no tiene ventana y se envía directo).
- **Login del portal**: la API del Hub usa una sola clave (`HUB_API_KEY`); para clientes con varios usuarios falta Supabase Auth.
- **Pruebas en vivo de cada CRM**: los adaptadores están probados con HTTP simulado; falta probarlos contra una cuenta real de cada CRM.
- **Salesforce multi-org**: el adaptador usa las credenciales `SF_*` del despliegue (una org por servicio).
- **Plantillas de WhatsApp vía Twilio** fuera de la ventana de 24 h (Content API): hoy se avisa al asesor para envío manual.
- **NLU con Gemini en vivo**: probado con respuestas simuladas; medir latencia real con la llave del proyecto (`NLU_PRESUPUESTO_SEG`).
