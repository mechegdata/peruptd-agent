-- 000 · Esquema base para un proyecto de Supabase NUEVO del PeruPTD Native CRM (varios clientes en la misma base).
-- No correr en la base de SAGUE: ahí las tablas ya existen. Orden: 000 -> 002 -> 003 -> 005 (-> 004 si quieres demos).
-- tenant_id toma por defecto la cabecera x-tenant-id que envía cada despliegue del bot (bot/db.py con MULTI_TENANT=true),
-- así cada insert queda marcado con su cliente aunque el código no lo escriba explícitamente.

create or replace function tenant_de_la_peticion() returns text language sql stable as $$
  select coalesce(nullif(current_setting('request.headers', true)::json ->> 'x-tenant-id', ''), 'sague')
$$;

create table if not exists leads (
  id              bigserial primary key,
  tenant_id       text not null default tenant_de_la_peticion(),
  sender_id       text not null,
  canal           text not null default 'whatsapp',
  nombre          text,
  telefono        text,
  interes         text,                       -- estado del bot (JSON en texto)
  ultimo_mensaje  text,
  cita_agendada   boolean default false,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now(),
  unique (tenant_id, sender_id)
);
create index if not exists leads_tenant_updated_idx on leads (tenant_id, updated_at desc);
create index if not exists leads_tenant_tel_idx on leads (tenant_id, telefono);

create table if not exists mensajes (
  id          bigserial primary key,
  tenant_id   text not null default tenant_de_la_peticion(),
  sender_id   text not null,
  canal       text,
  rol         text not null check (rol in ('user', 'assistant')),
  contenido   text,
  motor       text,                           -- qué motor respondió (Catálogo · Presupuesto · Agenda ...)
  created_at  timestamptz not null default now()
);
create index if not exists mensajes_tenant_sender_idx on mensajes (tenant_id, sender_id, created_at desc);

alter table leads    enable row level security;
alter table mensajes enable row level security;
