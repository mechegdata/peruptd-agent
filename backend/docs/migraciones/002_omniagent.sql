-- 002 · OmniAgent: colas persistentes (a prueba de reinicios de Cloud Run) + playbooks multi-cliente.
-- Se puede correr varias veces (todo es "if not exists"). No modifica datos existentes.
-- Mientras estas tablas no existan, el bot sigue funcionando con la memoria del proceso (como antes).

-- 1) Deduplicación persistente: cada id de Meta/Twilio se registra una sola vez (PRIMARY KEY).
--    Si Meta reenvía el aviso tras un reinicio, el insert choca y el bot no responde dos veces.
create table if not exists processed_webhooks (
  message_id  text primary key,
  tenant_id   text not null default 'sague',
  canal       text,
  created_at  timestamptz not null default now()
);
create index if not exists processed_webhooks_created_idx on processed_webhooks (created_at);

-- 2) Agrupación de mensajes cortados ("Hola" / "¿dónde están?"): cada fragmento es una fila. Responde la petición del
--    ÚLTIMO fragmento; si el contenedor muere mientras espera, /cron toma el lote vencido y responde igual.
create table if not exists debounce_batches (
  id             bigserial primary key,
  tenant_id      text not null default 'sague',
  lead_phone     text not null,
  canal          text not null default 'whatsapp',
  combined_text  text not null,                 -- texto del fragmento (se unen con salto de línea al responder)
  perfil         text,                          -- nombre de perfil de WhatsApp
  execute_at     timestamptz not null,          -- cuándo se puede responder (ahora + 6/15 s)
  status         text not null default 'pending',   -- pending | tomado
  created_at     timestamptz not null default now()
);
create index if not exists debounce_pend_idx on debounce_batches (tenant_id, status, execute_at);
create index if not exists debounce_lead_idx on debounce_batches (tenant_id, lead_phone, status);

-- 3) Tareas diferidas (hoy: saludo de Lead Ads a los 90 s). Un timer en memoria la ejecuta a tiempo; si el contenedor
--    se reinicia, /cron la ejecuta en su siguiente pasada. 'pending' -> 'tomado' es atómico (no se duplica el saludo).
create table if not exists scheduled_jobs (
  id          bigserial primary key,
  tenant_id   text not null default 'sague',
  tipo        text not null,                    -- 'lead_ad'
  clave       text not null,                    -- teléfono del lead
  payload     jsonb not null default '{}'::jsonb,
  execute_at  timestamptz not null,
  status      text not null default 'pending',  -- pending | tomado | cancelado
  created_at  timestamptz not null default now()
);
create index if not exists scheduled_jobs_pend_idx on scheduled_jobs (tenant_id, status, execute_at);
create index if not exists scheduled_jobs_clave_idx on scheduled_jobs (tenant_id, tipo, clave, status);

-- 4) Playbooks por cliente (textos, precios, reglas, frases prohibidas, mapeo a Salesforce). Ver playbooks/schema.json.
create table if not exists tenant_playbooks (
  tenant_id   text primary key,
  industria   text not null,
  playbook    jsonb not null,
  updated_at  timestamptz not null default now()
);

-- 5) Multi-cliente en las tablas existentes (columna nueva con valor por defecto: no cambia nada para SAGUE).
alter table leads    add column if not exists tenant_id text not null default 'sague';
alter table mensajes add column if not exists tenant_id text not null default 'sague';

-- Estas tablas solo las usa el bot: sin acceso público. IMPORTANTE: SUPABASE_KEY debe ser la clave *service_role*
-- (la que ignora RLS). Si el bot usa la clave anon, comenta estas 4 líneas; si no, el bot no podrá escribir en
-- estas tablas y seguirá con la memoria del proceso (lo avisa en los registros: "COLAS PERSISTENTES DESACTIVADAS").
alter table processed_webhooks     enable row level security;
alter table debounce_batches enable row level security;
alter table scheduled_jobs         enable row level security;
alter table tenant_playbooks       enable row level security;
