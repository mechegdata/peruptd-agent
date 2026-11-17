# De bot de SAGUE a producto SaaS para inmobiliarias

## 1. Qué hay que separar

Hoy el código mezcla **motor** (genérico) y **negocio de SAGUE** (específico). Para vender el producto, todo lo específico pasa a la base de datos:

| Hoy está en… | Ejemplo | Pasa a |
|---|---|---|
| `bot/ia/prompt.py` | Datos de Santa Teresa, precios, casuísticas 1-17 | `tenants.prompt_base` + `proyectos` + `inmuebles` + `faq` (se arma el prompt en tiempo de ejecución) |
| `bot/conversacion/faq.py`, `info.py`, `material.py`, `respaldo.py` | Textos fijos ("200 m²", "frente a la loza deportiva") | Tabla `faq` / `respuestas` por tenant, con variables (`{precio}`, `{area}`) |
| `bot/seguimiento/mensajes.py` | Protocolo de 14 días | `secuencias` + `pasos_secuencia` configurables por tenant |
| `bot/config.py` | `PRECIO_LISTA_USD`, `MAPS_URL`, `CALENDAR_ID`, `OWNER_WA`, URLs de renders | `tenants` / `proyectos` / `asesores` / Storage |
| Variables de entorno | `WA_PHONE_ID`, `WA_ACCESS_TOKEN` | `canales` (id) + Secret Manager (token por tenant) |
| `bot/nlp/patrones.py` | "cocina gris / madera" | Atributos del inmueble (`opciones_personalizacion`) |

Regla práctica: **si cambiaría al vender a otra inmobiliaria, no debe estar en el código.**

## 2. Esquema de datos propuesto (Postgres / Supabase)

```sql
-- Cada inmobiliaria cliente
create table tenants (
  id uuid primary key default gen_random_uuid(),
  nombre text not null,
  plan text not null default 'basico',
  zona_horaria text not null default 'America/Lima',
  prompt_base text,                 -- tono, reglas, prohibiciones
  config jsonb not null default '{}', -- horarios de visita, anticipación, filtro financiero, etc.
  activo boolean not null default true,
  created_at timestamptz default now()
);

-- Números de WhatsApp / páginas conectadas (el webhook identifica al tenant por phone_number_id)
create table canales (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id),
  tipo text not null check (tipo in ('whatsapp','messenger','instagram')),
  external_id text not null unique, -- phone_number_id / page_id / ig_id
  waba_id text,
  secreto_ref text not null,        -- nombre del secreto en Secret Manager (nunca el token en la BD)
  created_at timestamptz default now()
);

create table asesores (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id),
  nombre text, whatsapp text, calendar_id text, activo boolean default true
);

create table proyectos (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id),
  nombre text not null, ubicacion text, maps_url text, descripcion text,
  argumentos_venta jsonb default '[]'
);

create table inmuebles (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id),
  proyecto_id uuid references proyectos(id),
  codigo text, tipo text, area_terreno_m2 numeric, area_construida_m2 numeric,
  dormitorios int, banos int, precio_lista numeric, precio_minimo numeric, moneda text default 'USD',
  estado text default 'disponible', atributos jsonb default '{}', media jsonb default '[]'
);

create table leads (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id),
  canal_id uuid references canales(id),
  sender_id text not null, telefono text, nombre text,
  etapa text, score int, asesor_id uuid references asesores(id),
  estado jsonb not null default '{}',   -- hoy: leads.interes (texto)
  origen jsonb default '{}',            -- campaña / anuncio CTWA / formulario
  updated_at timestamptz default now(),
  unique (tenant_id, sender_id)
);

create table mensajes (
  id bigserial primary key,
  tenant_id uuid not null references tenants(id),
  lead_id uuid not null references leads(id),
  external_id text,                      -- wamid / mid
  rol text not null check (rol in ('user','assistant','humano','sistema')),
  contenido text, tipo text default 'text',
  created_at timestamptz default now(),
  unique (tenant_id, external_id)        -- idempotencia: no procesar dos veces
);

create table citas (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id),
  lead_id uuid references leads(id), inmueble_id uuid references inmuebles(id),
  asesor_id uuid references asesores(id),
  inicio timestamptz not null, fin timestamptz not null,
  estado text default 'agendada', evento_calendar_id text
);

create table faq (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id),
  pregunta text, respuesta text, embedding vector(768)  -- RAG con pgvector
);

-- Seguridad: cada usuario del panel solo ve su tenant
alter table leads enable row level security;
-- (repetir para todas las tablas y crear políticas por tenant_id según el JWT de Supabase Auth)
```

## 3. Modelo de negocio (puntos a decidir)

| Tema | Opciones | Comentario |
|---|---|---|
| Quién paga a Meta | (a) cada cliente con su tarjeta en WhatsApp Manager · (b) tú y lo repercutes | (a) evita riesgo financiero; desde oct-2026 los mensajes de servicio sobre 1.000/mes tienen costo. |
| Precio | Implementación única + mensualidad por número/proyecto; o por cita agendada / lead calificado | Cobrar por resultado (cita) es atractivo para inmobiliarias y te diferencia. |
| Planes | Básico (FAQ + agenda) · Pro (seguimientos, panel, reportes) · Premium (multi-asesor, integraciones CRM, anuncios) | Activar funciones por `tenants.plan`. |
| Contratos | Términos, SLA, encargo de tratamiento de datos (Ley 29733) | Necesario antes de procesar datos de clientes de terceros. |

## 4. Onboarding de un cliente nuevo (objetivo)

1. La inmobiliaria se registra en el panel → crea su `tenant`.
2. Conecta su WhatsApp con **Embedded Signup v4** (Tech Provider) → se guarda el canal y el token en Secret Manager → se suscribe la app al WABA.
3. Carga proyectos, inmuebles, fotos/fichas, FAQ y horarios de visita; conecta Google Calendar del asesor.
4. Elige plantillas de seguimiento (se envían a aprobación de Meta).
5. Prueba en modo "sandbox" (solo números de prueba) → activa.
