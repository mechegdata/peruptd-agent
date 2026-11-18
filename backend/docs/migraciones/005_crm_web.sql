-- 005 · PeruPTD Native CRM web (/app): usuarios por cliente, catálogo con modo de calificación y preguntas filtro,
-- nuevos roles de archivo y mapeo flexible de campos para CRMs externos. Idempotente.

-- 1) Usuarios del portal (cada uno ve solo su tenant). Contraseña con hash (werkzeug scrypt/pbkdf2), nunca en claro.
create table if not exists hub_users (
  id             uuid primary key default gen_random_uuid(),
  tenant_id      text not null references tenants(id) on delete cascade,
  email          text not null unique,
  nombre         text,
  password_hash  text not null,
  rol            text not null default 'asesor' check (rol in ('admin', 'asesor')),
  activo         boolean not null default true,
  last_login     timestamptz,
  created_at     timestamptz not null default now()
);
alter table hub_users enable row level security;

-- 2) Catálogo: cómo se califica a quien pregunta por este producto
alter table catalog_items add column if not exists qualification_mode text not null default 'credito_inicial';
alter table catalog_items drop constraint if exists catalog_items_qualification_mode_check;
alter table catalog_items add constraint catalog_items_qualification_mode_check
  check (qualification_mode in ('credito_inicial', 'seguro_medico', 'elegibilidad', 'b2b'));
alter table catalog_items add column if not exists filter_questions jsonb not null default '[]'::jsonb;  -- [{"es": "...", "en": "..."}]
alter table catalog_items add column if not exists conditions_es text;
alter table catalog_items add column if not exists conditions_en text;

-- 3) Roles de archivo: se suman PROOF_RESULTS (resultados / antes y después / casos) y LOCATION_MAP (mapa / fachada)
alter table catalog_media drop constraint if exists catalog_media_trigger_moment_check;
alter table catalog_media add constraint catalog_media_trigger_moment_check
  check (trigger_moment in ('FIRST_INFO', 'SPECS_PDF', 'OPTION_RENDER', 'PRICE_OBJECTION', 'PROOF_RESULTS', 'LOCATION_FACADE',
                            'LOCATION_MAP', 'POST_VISIT_45M', 'RESCUE_24H', 'VIDEO_TOUR'));

-- 4) Mapeo flexible para CRMs externos (objetos y campos de cada cliente). Vacío = objetos estándar (bot/crm_adapters/mapeo.py)
alter table tenants add column if not exists crm_field_mapping_json jsonb not null default '{}'::jsonb;

-- 5) Historial: qué motor respondió cada mensaje (la base 000 ya la trae)
alter table mensajes add column if not exists motor text;
