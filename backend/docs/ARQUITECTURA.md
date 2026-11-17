# Arquitectura: estado actual, diagnóstico y opciones

> Documento humano (no se genera solo). El detalle módulo por módulo, rutas y variables está en
> [`CONTEXTO_AUTO.md`](CONTEXTO_AUTO.md), que sí se regenera en cada commit.
> Última revisión: 2026-10-25.

## 1. Cómo funciona hoy

```
WhatsApp / Messenger / Instagram / comentarios / Lead Ads
            │  (webhook de Meta, Graph API v21.0)
            ▼
   Cloud Run "sague-bot" (Flask, 1 servicio, us-central1)
            │  procesa el mensaje DENTRO de la petición HTTP
            ├── motores determinísticos (regex): despedida → formulario → FAQ / material / info → agenda
            ├── Gemini (REST, varios modelos en cascada, presupuesto de 15 s) → si falla, motor de respaldo
            ├── Google Calendar (freebusy + crear/reprogramar visitas)
            ├── Supabase: tablas `leads` (estado JSON en texto) y `mensajes` (historial)
            └── WhatsApp Cloud API: responde, envía media, alerta al asesor (OWNER_WA)

Cloud Scheduler "sague-reloj" ──► /cron → recordatorios, rescate 24 h y protocolo post-visita de 14 días
Asesor (OWNER_WA) ──► comandos por WhatsApp: "vino 51…", "no vino 51…", "pausa", "vendido", "estado"
```

**Lo que está bien y conviene conservar**

- **Cloud Run + Supabase (Postgres)** es una base correcta para un SaaS pequeño/mediano: escala a cero, paga por uso y Postgres aguanta multi-cliente sin problema.
- **Diseño híbrido determinístico + IA**: la agenda y las FAQ no dependen del LLM, y existe un motor de respaldo. Esto es más confiable que un bot 100 % LLM.
- **Validación real de la agenda** antes de confirmar una cita (freebusy).
- **Respeto de la ventana de 24 h y horario prudente** en los seguimientos, con plantillas como respaldo.
- **Traspaso a humano**: detección de mensajes manuales del asesor (echoes) y comandos por WhatsApp.

## 2. Diagnóstico (ordenado por prioridad)

### 🔴 Crítico — seguridad y fiabilidad

| # | Problema | Riesgo concreto | Solución |
|---|---|---|---|
| 1 | **El webhook no valida la firma `X-Hub-Signature-256`** de Meta. | Cualquiera que conozca la URL puede inyectar mensajes falsos: el bot responde por WhatsApp (costo), crea eventos en Calendar y escribe en Supabase. | Validar HMAC-SHA256 del cuerpo con el `APP_SECRET` de la app de Meta y rechazar con 403 si no coincide. |
| 2 | **Secretos con valor por defecto en el código** (`VERIFY_TOKEN`, IDs, teléfonos). `/cron` acepta peticiones si el `User-Agent` dice `Google-Cloud-Scheduler` y no hay `CRON_KEY` (el User-Agent se falsifica trivialmente). `/diagnostico/media` se protege con el `VERIFY_TOKEN` por defecto y puede enviar mensajes a cualquier número. | Ejecución del cron o envíos masivos por terceros. | Quitar defaults de secretos; usar **Secret Manager**; proteger `/cron` con **autenticación OIDC** de Cloud Scheduler (o un servicio privado); desactivar `/diagnostico` en producción. |
| 3 | **Se procesa todo dentro de la petición del webhook** (Gemini hasta 15 s + Calendar + varias consultas a Supabase). | Meta reintenta cuando no recibe 200 rápido → respuestas duplicadas. La deduplicación (`PROCESSED_IDS`) vive en memoria: no se comparte entre instancias ni sobrevive a reinicios. | Responder 200 de inmediato y encolar el trabajo (**Cloud Tasks**). Idempotencia en Postgres: tabla de eventos con `wa_message_id` único. |
| 4 | **`threading.Timer` de 90 s** para leads de formularios y estado en memoria (`HUMANO_ACTIVO`, cachés). | En Cloud Run la CPU se limita fuera de las peticiones y las instancias se apagan: seguimientos perdidos en silencio. `PROCESSED_IDS` crece sin límite (fuga de memoria). | Cloud Tasks con `schedule_time` para tareas diferidas; estado en Postgres (o Redis/Memorystore si hace falta). |
| 5 | **Graph API v21.0 escrita a mano en 22 lugares.** | Según el calendario de Meta, v21.0 deja de estar disponible el 21-ene-2027; Meta redirige en silencio a la siguiente versión y los cambios de formato pueden romper cosas sin dar error. | Una sola constante `GRAPH_API_VERSION` en `config.py` y migrar a la versión actual (Meta publicó v26 en julio de 2026). |

### 🟠 Importante — costo, mantenimiento y producto

| # | Problema | Solución |
|---|---|---|
| 6 | **Todo el negocio de SAGUE está escrito en el código** (prompt, regex, textos de FAQ, seguimientos, precios, ubicación) repartido en ~15 módulos. Es el principal bloqueo para venderlo a otras empresas. | Mover datos del negocio a la base de datos por cliente (`tenants`, `proyectos`, `inmuebles`, `faq`, `plantillas`) y que el código sea genérico. Ver [`PRODUCTO_SAAS.md`](PRODUCTO_SAAS.md). |
| 7 | **Modelo de datos**: `leads.interes` es JSON guardado como texto; `mensajes` no guarda el id de WhatsApp ni el cliente (tenant). | Columna `jsonb` (o columnas reales para `etapa`, `cita`, `financiamiento`), `tenant_id` en todas las tablas, **RLS** activado, migraciones versionadas en `supabase/migrations/`. |
| 8 | **La API key de Gemini viaja en la URL** (`?key=`) y la cascada incluye modelos antiguos que pueden estar retirados (cada intento fallido consume parte de los 15 s). | Vertex AI con la cuenta de servicio de Cloud Run (sin key) o header `x-goog-api-key`; un modelo principal y uno de respaldo verificados; **salida estructurada** (`responseSchema`) o **function calling** en vez de "responde solo JSON". |
| 9 | **Lógica de conversación muy basada en regex** (motor de agenda de 412 líneas en una sola función). Funciona, pero cada caso nuevo agrega reglas y es frágil frente a cómo escribe la gente. | Pasar gradualmente a **LLM con herramientas** (`ver_disponibilidad`, `agendar_visita`, `enviar_material`, `derivar_a_humano`) y dejar regex solo para atajos baratos ("1", "2", "sí"). Mantener tests de regresión de conversaciones. |
| 10 | **Sin control de versiones, tests ni CI**; despliegue desde el editor de Cloud Shell. | GitHub privado + Cloud Build (deploy al hacer push a `main`) + entorno de staging. Ya incluido en este repo: CI, pruebas de humo y documentación automática. |
| 11 | **Observabilidad**: `print()` sueltos; sin métricas de embudo. | Logs JSON estructurados (Cloud Logging con `severity`, `tenant_id`, `lead_id`), Error Reporting y una tabla de eventos para medir el embudo. |
| 12 | **Costos de WhatsApp cambiaron**: desde el 1-oct-2026 Meta volvió a cobrar los mensajes de servicio por encima de 1.000 gratis al mes por número, y los mensajes *utility* dentro de la ventana de atención. | Cada respuesta del bot tiene costo variable: inclúyelo en el precio del SaaS (o que cada cliente pague a Meta con su propio método de pago). Medir mensajes por cliente. |
| 13 | **Privacidad (Ley 29733, Perú)**: se guardan nombres, teléfonos e historial sin política de retención; "borren mi número" marca `no_interesado` pero no borra datos. | Aviso de privacidad, base legal/consentimiento, retención (p. ej. 12 meses), endpoint de borrado, contrato de encargo de datos con cada inmobiliaria. |
| 14 | **Audios**: se pide al cliente que escriba. En Perú las notas de voz son muy comunes. | Transcribir con Gemini (acepta audio) y procesar como texto. |

### 🟢 Política de Meta sobre bots de IA

Desde el 15-ene-2026 Meta prohíbe en la API de WhatsApp Business los **chatbots de IA de propósito general** (tipo ChatGPT). Los bots de una empresa para ventas, soporte y citas **siguen permitidos**. Tu bot entra en esta categoría; para no tener problemas, el prompt debe **negarse a temas ajenos** al negocio y derivar a un humano cuando corresponda.

## 3. Arquitectura recomendada (evolución, no reescritura)

```
                ┌───────────── Panel web (Next.js + Supabase Auth) ─────────────┐
                │ onboarding (Embedded Signup), inbox con toma humana, CRM,       │
                │ inventario de inmuebles, FAQ, plantillas, reportes por cliente  │
                └───────────────────────────────┬────────────────────────────────┘
Meta (WA/IG/FB) ──► Cloud Run "ingesta"         │
  firma HMAC ✔     responde 200 en <1 s          │
                   guarda evento (idempotente)   │
                   └─► Cloud Tasks ──► Cloud Run "worker" (este código, multi-tenant)
                                         ├─ carga config del tenant desde Postgres
                                         ├─ atajos determinísticos (1/2/sí/no, horarios)
                                         ├─ LLM con herramientas + RAG (pgvector) por tenant
                                         ├─ Google Calendar por asesor / tenant
                                         └─ WhatsApp Cloud API con el token del tenant
Cloud Scheduler (OIDC) ──► worker /cron  (seguimientos por tenant, vía Cloud Tasks)
Supabase: Postgres (RLS por tenant_id) · Storage (fichas, renders) · pgvector · Auth
Secret Manager: tokens de Meta por tenant, claves · Cloud Logging + Error Reporting
```

Cambios clave respecto a hoy:

1. **Multi-tenant**: un solo despliegue atiende a todos los clientes; el `phone_number_id` del webhook identifica al tenant.
2. **Cola** (Cloud Tasks): ack inmediato a Meta, reintentos controlados, tareas diferidas confiables.
3. **Configuración en base de datos**, no en variables de entorno ni en el prompt.
4. **LLM con function calling + RAG** por cliente: el conocimiento (precios, inmuebles, FAQ) sale de la base de datos, el modelo no lo inventa.
5. **Panel web** para que cada inmobiliaria se configure sola y para que los asesores tomen chats.
6. **Meta Tech Provider + Embedded Signup**: cada inmobiliaria conecta su propio número en minutos y paga sus mensajes a Meta.

## 4. Tablas comparativas

### 4.1 Arquitectura general

| Criterio | A. Actual (monolito Flask en Cloud Run) | **B. Recomendada: Cloud Run modular multi-tenant + Cloud Tasks + Supabase** | C. Todo en Supabase (Edge Functions TS + pgmq + pg_cron) | D. Low-code (n8n + Chatwoot + BSP) | E. Revender una plataforma (Respond.io, WATI, Kommo, Botpress…) |
|---|---|---|---|---|---|
| Trabajo para llegar a SaaS | Alto: todo es de un solo cliente | Medio: se reutiliza el 70-80 % del código actual | Alto: reescribir en TypeScript | Medio: rehacer flujos en nodos | Bajo: configurar, no programar |
| Tiempo hasta el 2.º cliente | Copiar servicio por cliente (no escala) | 4-8 semanas (multi-tenant básico) | 8-12 semanas | 2-4 semanas | Días |
| Costo fijo de infraestructura | Muy bajo | Bajo (Cloud Run escala a cero; Supabase Pro ~US$25/mes; verificar precios vigentes) | Muy bajo (un solo proveedor) | Bajo-medio (VPS para n8n + Chatwoot) | Alto por cliente (licencias por usuario/contacto) |
| Costo marginal por cliente | Un servicio y config por cliente | Casi cero (mensajes de Meta + tokens del LLM) | Casi cero | Bajo | Licencia por cliente: tu margen se reduce |
| Fiabilidad (reintentos, duplicados) | Débil (estado en memoria, proceso síncrono) | Alta (cola, idempotencia en BD) | Alta (pgmq) pero límites de tiempo de las Edge Functions | Media (depende de la configuración de n8n) | Alta (lo resuelve el proveedor) |
| Control de la lógica de ventas (tu diferencial) | Total | Total | Total | Medio | Bajo: limitado a lo que ofrece la plataforma |
| Panel para clientes / inbox humano | No (solo comandos por WhatsApp) | Lo construyes (Next.js) o integras Chatwoot | Lo construyes | Chatwoot incluido | Incluido |
| Dependencia de proveedor | Media (GCP + Supabase) | Media (GCP + Supabase, ambos con salida: Postgres estándar) | Alta en Supabase | Baja (open source) | Muy alta |
| Encaje con lo que ya sabes | Total | Total (Python, GCP, Supabase) | Requiere aprender TS/Deno | Distinto paradigma | Nada técnico |
| Escala esperada | 1 cliente | Decenas o cientos de clientes | Decenas o cientos | Decenas | Ilimitada (pero pagas licencias) |
| **Veredicto** | Punto de partida | ✅ **Mejor equilibrio para tu caso** | Buena si quisieras un solo proveedor y TS | Útil para prototipos o clientes con flujos simples | Útil como plan B o para vender servicios de configuración, no un producto propio |

### 4.2 Acceso a WhatsApp

| Criterio | Cloud API directa (hoy, 1 número) | **Cloud API como Tech Provider + Embedded Signup** | BSP / intermediario (360dialog, Twilio, Gupshup…) |
|---|---|---|---|
| Alta de un nuevo cliente | Manual en Meta Business, compleja | El cliente conecta su número desde tu panel en minutos | Desde el panel del BSP |
| Quién paga los mensajes | Tú | El cliente, con su método de pago en WhatsApp Manager (o tú, si lo configuras) | El BSP te factura (Meta + su margen) |
| Costo extra sobre Meta | Ninguno | Ninguno | Margen o cuota del BSP |
| Requisitos | Una app de Meta | App verificada, verificación de negocio y pasar a Tech Provider; usar Embedded Signup v4 (v2 y v3 se deprecaron el 15-oct-2026) | Contrato con el BSP |
| Control y dependencia | Total | Total | Dependes de su API y de sus precios |
| Recomendación | Solo para tu caso actual | ✅ **Para el SaaS** | Si Meta tarda en aprobarte, como puente temporal |

### 4.3 Modelo de IA

| Criterio | Gemini Flash vía Vertex AI | Claude (Haiku / Sonnet) | OpenAI (modelos mini) | Modelo abierto propio (Llama, Qwen…) |
|---|---|---|---|---|
| Integración con tu stack GCP | ✅ Nativa (cuenta de servicio, sin API key, mismo proyecto de facturación) | API externa (también disponible en Vertex AI Model Garden) | API externa | Requiere GPU y operación propia |
| Function calling / salida estructurada | Sí | Sí | Sí | Variable según modelo |
| Español peruano coloquial | Bueno | Muy bueno | Bueno | Variable |
| Audio (notas de voz) en el mismo modelo | ✅ Sí | No (requiere transcribir aparte) | Con modelos específicos | Requiere otro modelo |
| Costo relativo por conversación | Bajo | Medio (Haiku bajo) | Bajo | Fijo alto (GPU) |
| Recomendación | ✅ **Principal** (ya lo usas) | Buen respaldo o para tareas de calidad (resúmenes al asesor) | Respaldo alternativo | No compensa a esta escala |

Consejo: hacer una capa `bot/ia/` con una interfaz común (`generar(mensajes, herramientas)`) para poder cambiar de proveedor por cliente sin tocar la lógica.

### 4.4 Framework del backend

| Criterio | Flask (actual) | FastAPI | Node.js / TypeScript |
|---|---|---|---|
| Migración | Ninguna | Baja (rutas parecidas) | Reescritura total |
| Validación de datos (webhooks, panel) | Manual | Pydantic integrado | Zod u otra |
| Asíncrono (muchas llamadas HTTP) | Hilos | Nativo (async) | Nativo |
| Documentación de API automática | No | Sí (OpenAPI) | Con librerías |
| Recomendación | Sirve mientras uses cola + workers | ✅ Cuando construyas la API del panel | Solo si el equipo es TS |

## 5. Plan de migración sugerido

1. **Semana 1 — Ordenar y asegurar** (sin cambiar comportamiento): repo en GitHub, deploy por Cloud Build, Secret Manager, firma del webhook, `/cron` con OIDC, versión de Graph API centralizada y actualizada.
2. **Semanas 2-3 — Fiabilidad**: Cloud Tasks (ack inmediato), tabla de idempotencia, reemplazar `threading.Timer`, estado fuera de memoria, logs estructurados.
3. **Semanas 3-6 — Multi-tenant**: tablas `tenants`/`canales`/`proyectos`/`inmuebles`/`faq`, `tenant_id` + RLS, prompt y textos generados desde la BD, SAGUE como primer tenant.
4. **Semanas 6-10 — Producto**: panel web (onboarding, inbox, CRM, reportes), Tech Provider + Embedded Signup, facturación.
5. **Continuo**: pasar el motor de agenda a function calling con tests de regresión de conversaciones.

## Fuentes

- Calendario de versiones de Graph API: <https://developers.facebook.com/docs/graph-api/changelog/versions>
- Precios de WhatsApp Business Platform: <https://developers.facebook.com/documentation/business-messaging/whatsapp/pricing>
- Onboarding como Tech Provider (Embedded Signup): <https://developers.facebook.com/documentation/business-messaging/whatsapp/embedded-signup/onboarding-customers-as-a-tech-provider>
- Política de chatbots de IA en WhatsApp: <https://respond.io/blog/whatsapp-general-purpose-chatbots-ban>
