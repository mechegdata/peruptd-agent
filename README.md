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

1. Supabase (proyecto nuevo): correr en orden `backend/docs/migraciones/000_base_peruptd.sql`, `002_omniagent.sql`,
   `003_tenants_catalogo.sql`, (demos) `004_demo_catalogos.sql` y `005_crm_web.sql`. Crear el bucket público `catalogo`.
   `SUPABASE_KEY` debe ser la clave *service_role*. Con varios clientes en la misma base: `MULTI_TENANT=true`.
   Usuarios del CRM web: `python scripts/crear_usuario.py --tenant demo-dental --email ana@clinica.com --rol admin`
   (pide la contraseña por consola; se guarda solo el hash).
2. Cloud Run (servicio nuevo, no el de SAGUE): `TENANT_ID`, `PIPELINE_MODE=catalogo`, claves de Meta/Gemini/Calendar de siempre.
   Si usa Twilio: `--no-cpu-throttling`, `TWILIO_*`, y en Twilio el webhook `https://<servicio>/webhook/twilio`.
3. CRM externo: `CRM_SYNC_ACTIVO=true` + credenciales; Salesforce usa `SF_*` (Connected App, Client Credentials o JWT).
4. CRM web: `HUB_SESSION_SECRET` (32+ caracteres, en Secret Manager) y, si la web vive en otro dominio, `HUB_CORS_ORIGINS`.
5. Cloud Scheduler: `/cron` cada 5-10 min (seguimientos + colas huérfanas) y `/catalogo/sincronizar` cada hora.

Todas las variables están en `backend/.env.example` (se genera con `python scripts/generar_contexto.py`).

## Seguimiento por tenant (modo `catalogo`)

`bot/seguimiento/motor_catalogo.py` + `plantillas.py`: recordatorio, pregunta al asesor (75 min), protocolo de 14 días
(`post_45m`, `post_48h_contado` / `post_48h_financiado`, `post_dia5`, `post_dia10` + alerta al asesor, `post_dia14`),
no asistió y rescate de 24 h (`rescate_horarios`, `rescate_objecion`, `rescate_presupuesto`, `rescate_general`).
Textos, en orden: `playbook.seguimiento.{es,en}` (editables en /app → Ajustes) → plantilla de la industria del tenant
(`plantillas_industria.py`: inmobiliaria, salud/clínicas, B2B; ES y EN) → texto neutro. Variables
`{coma} {producto} {bono} {valor} {horarios} {cuota}…`. Cada toque se apaga con `interruptores.seguimiento_<clave> = false`. Los adjuntos
salen del catálogo (`POST_VISIT_45M`, `OPTION_RENDER`, `RESCUE_24H`…), sin repetir. SAGUE (`sague_legacy`) no cambia.

## PeruPTD Native CRM (`/app`)

Una sola página (Flask + Supabase, sin npm). Doble modo:
- `https://<servicio>/app` → **producción**: login (tabla `hub_users`, contraseña con hash scrypt, cookie HttpOnly firmada,
  5 intentos / 15 min, cabecera `X-PTD-CSRF` en cada cambio). Cada usuario ve solo los datos de su `tenant_id`.
- `/app?demo=1`, el archivo suelto o el artifact → **demo** de siempre (▶, X-Ray, switches) para grabar videos.

| Pestaña | Qué hace | Endpoint |
|---|---|---|
| Pipeline | Kanban de 5 columnas (Capturado · Calificado · Visita agendada · Seguimiento 14 días · Cierre/Alerta) | `GET /api/hub/leads` |
| | Conversación con el motor que respondió cada mensaje | `GET /api/hub/leads/<id>/mensajes` |
| | vino / no vino / pausa / activar / vendido, y mensaje manual (pausa el bot 2 h) | `POST /api/hub/leads/<id>/comando` |
| Catálogo | Crear / editar / borrar productos: precios lista y contado, modo de calificación (Crédito/Inicial, Seguro médico, Elegibilidad, B2B), preguntas filtro, condiciones | `GET/POST/PUT/DELETE /api/hub/catalogo` |
| | Subir fotos, PDF y videos al bucket `catalogo` con su rol (FIRST_INFO, SPECS_PDF, PRICE_OBJECTION, PROOF_RESULTS, VIDEO_TOUR, LOCATION_MAP) | `POST /api/hub/catalogo/<item_id>/media` |
| Ajustes | WhatsApp del dueño, horario de visitas, silencio nocturno, frases prohibidas, textos de seguimiento ES/EN, mapeo de CRM | `GET/PUT /api/hub/playbook` |

Solo `admin` cambia catálogo y ajustes; `asesor` opera el pipeline. Las subidas se validan por tipo y por contenido
(firma del archivo) y van a `catalogo/<tenant>/<producto>/…`. Acceso de máquina: `X-Hub-Key` + `X-Tenant-Id`.

### Mapeo flexible para CRMs externos (`tenants.crm_field_mapping_json`)

Vacío = objetos estándar (Salesforce `Product2` + lista de precios estándar y `Lead`; HubSpot `products`/`contacts`;
Pipedrive `products`/`persons`; Zoho `Products`/`Leads`). Solo se indica lo distinto, sin tocar código:

```json
{"catalog": {"object": "Property__c", "active_field": "Listed__c",
             "fields": {"name_es": "Name", "list_price": "Price__c", "cash_price": "Cash_Price__c"}},
 "lead": {"fields": {"presupuesto": "Initial_Budget__c", "pago": "Payment_Method__c"}},
 "event_attendance": "Attendance__c"}
```

Se edita en /app → Ajustes; solo se aceptan nombres de API válidos. El formato anterior `crm_field_map` se sigue leyendo.

## AI Sales Hub: modo API en vivo

- Sin backend (archivo suelto o el artifact de claude.ai) → datos de demostración, como siempre.
- Servido por el backend en `GET /hub` (mismo dominio) → usa tu sesión de /app si existe; si no, pide `HUB_API_KEY` + tenant.
- En otro dominio → botón **⚙** del Hub (URL + clave) y ese dominio en `HUB_CORS_ORIGINS`.
- Lee y escribe: catálogo (`PATCH` precios/bono/argumento), `POST /api/hub/catalogo/sincronizar`, Kanban (`/api/hub/leads`),
  acciones vino / no vino / pausa / vendido, y chat con el agente real usando un cliente simulado `hub:+1999…`
  (no sale nada por WhatsApp/SMS ni se crea la cita en el calendario real).
- Dentro de claude.ai la página no puede llamar a otros dominios (política del sitio): ahí siempre funciona en modo demo.
- `python hub/build.py` genera `hub/dist/index.html` y `backend/bot/static/hub.html`.

## Pruebas

`cd backend && python -m pytest -q` → 181 pruebas (79 originales de SAGUE + NLU, motores, colas, adaptadores, Twilio,
turno completo del agente y guardas por playbook).

## Pendiente (siguiente fase)

- **Plantillas de WhatsApp aprobadas por Meta** para los toques fuera de la ventana de 24 h en modo `catalogo`: hoy pasan al
  asesor para envío manual (el SMS no tiene ventana y se envía directo).
- **Recuperar contraseña** del CRM web: hoy se restablece con `scripts/crear_usuario.py` (no hay correo de "olvidé mi clave").
- **Lead en objeto propio de Salesforce**: el catálogo ya se lee de cualquier objeto; el lead se escribe siempre en `Lead`
  (con campos configurables).
- **Pruebas en vivo de cada CRM**: los adaptadores están probados con HTTP simulado; falta probarlos contra una cuenta real de cada CRM.
- **Salesforce multi-org**: el adaptador usa las credenciales `SF_*` del despliegue (una org por servicio).
- **Plantillas de WhatsApp vía Twilio** fuera de la ventana de 24 h (Content API): hoy se avisa al asesor para envío manual.
- **NLU con Gemini en vivo**: probado con respuestas simuladas; medir latencia real con la llave del proyecto (`NLU_PRESUPUESTO_SEG`).
