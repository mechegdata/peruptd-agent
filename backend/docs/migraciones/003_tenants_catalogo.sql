-- 003 · PeruPTD Autonomous AI Sales Agent: empresas (tenants), catálogo con multimedia y ficha viva del lead.
-- Requiere 002_omniagent.sql (processed_webhooks, debounce_batches, scheduled_jobs, tenant_playbooks).
-- Idempotente: se puede correr varias veces.

create extension if not exists pgcrypto;

-- 1) Empresas cliente
create table if not exists tenants (
  id                    text primary key,                      -- 'sague', 'brightsmile', ...
  name                  text not null,
  industry              text not null,                         -- realestate | dental | medspa | b2b | ...
  default_language      text not null default 'es' check (default_language in ('es','en')),
  supported_languages   text[] not null default array['es','en'],
  crm_type              text not null default 'peruptd_native'
                        check (crm_type in ('peruptd_native','salesforce','hubspot','pipedrive','zoho')),
  crm_credentials_json  jsonb not null default '{}'::jsonb,     -- SOLO referencias a secretos (Secret Manager), nunca la clave en texto
  owner_whatsapp        text,
  bot_name              text not null default 'Ava',             -- cómo se presenta el agente
  advisor_name          text,                                     -- a quién escala la objeción nivel 3
  address               text,
  crm_field_map         jsonb not null default '{}'::jsonb,       -- {"catalogo": {...}, "lead": {...}} (ver bot/crm_adapters)
  quiet_hours_start     time not null default '20:30',
  quiet_hours_end       time not null default '08:30',
  timezone              text not null default 'America/Lima',
  calendar_id           text,
  bcrp_or_fx_rate       numeric,                               -- tipo de cambio referencial si vende en 2 monedas
  pipeline_mode         text not null default 'catalogo'       -- 'catalogo' (motor nuevo) | 'sague_legacy' (motor original)
                        check (pipeline_mode in ('catalogo','sague_legacy')),
  created_at            timestamptz not null default now()
);

insert into tenants (id, name, industry, default_language, crm_type, pipeline_mode)
values ('sague', 'SAGUE Constructora', 'realestate', 'es', 'peruptd_native', 'sague_legacy')
on conflict (id) do nothing;

-- 2) Catálogo (servicios, productos, tratamientos, propiedades). Bilingüe.
create table if not exists catalog_items (
  id                            uuid primary key default gen_random_uuid(),
  tenant_id                     text not null references tenants(id) on delete cascade,
  external_crm_id               text,                          -- Product2 Id / HubSpot product id / ...
  name_es                       text not null,
  name_en                       text,
  keywords                      text[] not null default '{}',  -- cómo lo llama la gente: 'ksa', 'depa', 'implant pkg'
  category                      text,
  status                        text not null default 'available' check (status in ('available','last_units','sold_out')),
  specs_json                    jsonb not null default '{}'::jsonb,   -- {"es": {"Terreno": "80 m2"}, "en": {"Lot": "861 sqft"}}
  list_price                    numeric not null,
  cash_price                    numeric,
  currency                      text not null default 'USD',
  min_down_payment_pct          numeric not null default 10,
  recommended_down_payment_pct  numeric not null default 20,
  annual_rate_pct               numeric not null default 0,
  max_term_years                numeric not null default 1,
  promo_bonus_es                text,
  promo_bonus_en                text,
  value_comparison_es           text,                          -- argumento contra "está caro"
  value_comparison_en           text,
  insurance_es                  text,                          -- clínicas: qué seguros acepta (lo usa el motor si preguntan)
  insurance_en                  text,
  location_address              text,
  google_maps_url               text,
  sort_order                    int not null default 0,
  updated_at                    timestamptz not null default now(),
  unique (tenant_id, external_crm_id)
);
create index if not exists catalog_items_tenant_idx on catalog_items (tenant_id, status, sort_order);

-- 3) Multimedia por momento de la conversación
create table if not exists catalog_media (
  id               uuid primary key default gen_random_uuid(),
  catalog_item_id  uuid not null references catalog_items(id) on delete cascade,
  tenant_id        text not null references tenants(id) on delete cascade,
  file_url         text not null,                              -- Supabase Storage (bucket 'catalogo') o URL del CRM
  media_type       text not null check (media_type in ('image','pdf','video')),
  trigger_moment   text not null check (trigger_moment in ('FIRST_INFO','SPECS_PDF','OPTION_RENDER','PRICE_OBJECTION',
                                                           'LOCATION_FACADE','POST_VISIT_45M','RESCUE_24H','VIDEO_TOUR')),
  caption_es       text,
  caption_en       text,
  sort_order       int not null default 0
);
create index if not exists catalog_media_item_idx on catalog_media (catalog_item_id, trigger_moment, sort_order);

-- 4) Ficha viva del lead: columnas consultables (el estado detallado sigue en leads.interes, JSON).
alter table leads add column if not exists external_crm_lead_id        text;
alter table leads add column if not exists preferred_language          text;
alter table leads add column if not exists channel_origin              text;
alter table leads add column if not exists interested_catalog_item_id  uuid;
alter table leads add column if not exists stage                       text;
alter table leads add column if not exists payment_method              text;
alter table leads add column if not exists stated_budget               numeric;
alter table leads add column if not exists price_objection_count       int not null default 0;
alter table leads add column if not exists appointment_datetime        timestamptz;
alter table leads add column if not exists appointment_status          text;
alter table leads add column if not exists followup_14d_step           text;
alter table leads add column if not exists sent_media_ids              uuid[] not null default '{}';
alter table leads add column if not exists bot_paused_until            timestamptz;
alter table leads add column if not exists last_client_message_at      timestamptz;
alter table leads add column if not exists last_bot_message_at         timestamptz;
create index if not exists leads_tenant_stage_idx on leads (tenant_id, stage);

alter table tenants        enable row level security;
alter table catalog_items  enable row level security;
alter table catalog_media  enable row level security;
-- El portal web (AI Sales Hub) leerá con la sesión del usuario: agrega políticas por tenant cuando exista el login.
