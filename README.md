# PeruPTD Autonomous AI Sales Agent & Multi-CRM Hub

Multi-industry, bilingual (ES/EN), and multi-CRM product built on top of the production-proven engine from SAGUE Constructora.
**SAGUE in production remains untouched**: this is a separate project. SAGUE will be onboarded as the first tenant in `sague_legacy` mode.

```
peruptd-agent/
├── backend/   Python (Flask + Supabase + Gemini + Google Calendar) — copy of the SAGUE engine + new modules
└── hub/       PeruPTD AI Sales Hub + Native CRM web app (vanilla JS, no npm): src/ → build.py → dist/index.html
```

## Architecture (3 Layers)

```
WhatsApp Cloud API ─┐                                                    ┌─> WhatsApp / SMS (text + max. 2 files)
Twilio SMS / WA ────┼─> dedupe (processed_webhooks) ─> debounce 15 s ───┤
Messenger / IG ─────┘    (debounce_batches; /cron finishes orphan jobs)  │
                                                                         │
 Layer 1  bot/nlu_normalizer.py   SemanticNormalizer → NormalizedTurn (pydantic)
          ES/EN lexicon (bot/nlu/lexicon.json, ~1 ms) + strict JSON Gemini Flash (optional, time-budgeted)
 Layer 2  bot/engines/            catalog · budget (8% / 20% / min down payment + annuity) · 1-2-3 objections
                                  · scheduling (live calendar, respects "leaving work at 6") · stage-based media
 Layer 3  bot/engines/guardas.py  playbook forbidden phrases + anti-repetition ≥ 80%
          bot/agente.py           sends, books, updates live lead record, alerts human advisor
 CRM      bot/crm.py + bot/crm_adapters/   PeruPTD Native · Salesforce · HubSpot · Pipedrive · Zoho
```

All SAGUE production features are preserved: 90 s response to Lead Ads, 2 h automatic pause when the advisor replies (echo), 24 h rescue, commands
`vino / no vino / pausa / activar / vendido / estado`, 14-day follow-up protocol, and quiet hours.

**Per-tenant mode** (`tenants.pipeline_mode`): `catalogo` = new engine (NLU + catalog); `sague_legacy` = original engine.
Without a `tenants` table, the deployment starts in `sague_legacy` (`PIPELINE_MODE` environment variable).

## In-CRM Catalog

The agent always reads `catalog_items` + `catalog_media` in Supabase (5 min cache). Each CRM feeds them via
`POST /catalogo/sincronizar` (Cloud Scheduler or CRM webhook):

| CRM | Catalog | Lead / Appointment / Note |
|---|---|---|
| PeruPTD Native | edited in the web app at `/app` | `leads` columns |
| Salesforce | Product2 · PricebookEntry · ContentVersion (copied to the `catalogo` bucket) | Lead · Event · Task |
| HubSpot | crm/v3/objects/products | Contact + Deal · Meeting · Note |
| Pipedrive | /products | Person + Deal · Activity · Note |
| Zoho | Products | Leads (upsert by phone) · Events · Notes |

File naming convention for clients: `[PRICE_OBJECTION] Cochera.jpg`, `[SPECS_PDF] Planos.pdf`. If untagged:
image → FIRST_INFO, PDF → SPECS_PDF, video → VIDEO_TOUR.
Credentials: `tenants.crm_credentials_json` stores **references** to environment variables/secrets (`{"token_env": "HUBSPOT_TOKEN_ACME"}`), never raw keys.

## Activation (Order)

1. Supabase (new project): run, in order, `backend/docs/migraciones/000_base_peruptd.sql`, `002_omniagent.sql`,
   `003_tenants_catalogo.sql`, (demos) `004_demo_catalogos.sql` and `005_crm_web.sql`. Create the public bucket `catalogo`.
   `SUPABASE_KEY` must be the *service_role* key. Several clients in one database: `MULTI_TENANT=true`.
   CRM users: `python scripts/crear_usuario.py --tenant demo-dental --email ana@clinic.com --rol admin`
   (the password is typed in the console; only its hash is stored).
2. Cloud Run (new service, separate from SAGUE): `TENANT_ID`, `PIPELINE_MODE=catalogo`, standard Meta/Gemini/Calendar keys.
   If using Twilio: `--no-cpu-throttling`, `TWILIO_*`, and set the Twilio webhook to `https://<service>/webhook/twilio`.
3. External CRM: `CRM_SYNC_ACTIVO=true` + credentials; Salesforce uses `SF_*` (Connected App, Client Credentials, or JWT).
4. Web CRM: `HUB_SESSION_SECRET` (32+ chars, in Secret Manager) and, if the web app lives on another domain, `HUB_CORS_ORIGINS`.
5. Cloud Scheduler: `/cron` every 5-10 min (follow-ups + orphan queues) and `/catalogo/sincronizar` every hour.

All environment variables are listed in `backend/.env.example` (generated with `python scripts/generar_contexto.py`).

## Per-tenant follow-up (`catalogo` mode)

`bot/seguimiento/motor_catalogo.py` + `plantillas.py`: reminder, rep check-in (75 min), 14-day protocol
(`post_45m`, `post_48h_contado` / `post_48h_financiado`, `post_dia5`, `post_dia10` + rep alert, `post_dia14`),
no-show and 24 h rescue (`rescate_horarios`, `rescate_objecion`, `rescate_presupuesto`, `rescate_general`).
Text lookup order: `playbook.seguimiento.{es,en}` (editable in `/app` → Settings) → industry template
(`plantillas_industria.py`: real estate, health/clinics, B2B; ES and EN) → neutral default. Every touch can be turned off with
`interruptores.seguimiento_<key> = false`; attachments come from the catalog, never repeated. SAGUE (`sague_legacy`) is unchanged.

## PeruPTD Native CRM (`/app`)

One page served by Flask + Supabase (no npm, no Next.js). Two modes:
- `https://<service>/app` → **production**: login (`hub_users`, scrypt password hashes, signed HttpOnly cookie,
  5 attempts / 15 min, `X-PTD-CSRF` header on every write). Each user only sees their own `tenant_id`.
- `/app?demo=1`, the standalone file or the hosted demo → **demo** with scripted scenarios and the AI Brain X-Ray, for videos.

| Tab | What it does | Endpoint |
|---|---|---|
| Pipeline | 5-column Kanban (Captured · Qualified · Visit booked · 14-day follow-up · Close/Alert) | `GET /api/hub/leads` |
| | Conversation, tagged with the engine that produced each reply | `GET /api/hub/leads/<id>/mensajes` |
| | attended / no-show / pause / resume / won, and manual messages (pause the bot for 2 h) | `POST /api/hub/leads/<id>/comando` |
| Catalog | Create / edit / delete products: list & cash price, qualification mode (financing, medical insurance, eligibility, B2B), filter questions, conditions | `GET/POST/PUT/DELETE /api/hub/catalogo` |
| | Upload photos, PDFs and videos to the `catalogo` bucket with a role (FIRST_INFO, SPECS_PDF, PRICE_OBJECTION, PROOF_RESULTS, VIDEO_TOUR, LOCATION_MAP) | `POST /api/hub/catalogo/<item_id>/media` |
| Settings | Owner WhatsApp, visiting hours, night quiet window, forbidden phrases, follow-up texts ES/EN, CRM mapping | `GET/PUT /api/hub/playbook` |

Only `admin` users change the catalog and settings; `asesor` users work the pipeline. Uploads are checked by MIME type and by
file signature and stored under `catalogo/<tenant>/<product>/…`. Machine access: `X-Hub-Key` + `X-Tenant-Id`.

### Flexible mapping for external CRMs (`tenants.crm_field_mapping_json`)

Empty = standard objects (Salesforce `Product2` + standard price book and `Lead`; HubSpot `products`/`contacts`;
Pipedrive `products`/`persons`; Zoho `Products`/`Leads`). Only list what differs; no code changes:

```json
{"catalog": {"object": "Property__c", "active_field": "Listed__c",
             "fields": {"name_es": "Name", "list_price": "Price__c", "cash_price": "Cash_Price__c"}},
 "lead": {"fields": {"presupuesto": "Initial_Budget__c", "pago": "Payment_Method__c"}},
 "event_attendance": "Attendance__c"}
```

Edited in `/app` → Settings; only valid API names are accepted (prevents SOQL/SQL injection).

## AI Sales Hub: live API mode

- Standalone file or hosted demo → built-in demo data.
- Served by the backend at `GET /hub` → reuses the `/app` session if there is one; otherwise asks for `HUB_API_KEY` + tenant.
- Reads and writes the catalog, the Kanban and lead commands, and chats with the real agent through a simulated
  `hub:+1999…` customer (nothing goes out over WhatsApp/SMS and no real calendar event is created).
- `python hub/build.py` builds `hub/dist/index.html` and `backend/bot/static/hub.html`.

## Tests

`cd backend && python -m pytest -q` → 181 tests (79 original SAGUE tests + NLU, engines, queues, CRM adapters and mapping,
Twilio, full agent turn, playbook guardrails, follow-up templates, and the web CRM with an in-memory Supabase).

## Pending (Next Phase)

- **Password reset** for the web CRM: today it is reset with `scripts/crear_usuario.py` (no "forgot password" email).
- **Leads in a custom Salesforce object**: the catalog can already come from any object; leads are always written to `Lead`
  (with configurable fields).
- **Live end-to-end CRM testing**: adapters are tested with mocked HTTP; live testing against a real account for each CRM is pending.
- **Multi-org Salesforce**: the adapter currently uses deployment-level `SF_*` credentials (one org per service).
- **WhatsApp templates** outside the 24 h window (Meta and Twilio Content API): currently the rep is alerted to send manually.
- **Live Gemini NLU**: tested with mocked responses; real latency benchmarking is needed with the project key (`NLU_PRESUPUESTO_SEG`).
