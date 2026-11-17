# Roadmap: mejoras y funcionalidades nuevas

Prioridad: 🔴 hacer ya · 🟠 próximo trimestre · 🟢 cuando haya clientes pagando.
Marca con `[x]` al completar y registra el cambio en `CHANGELOG.md`.

## A. Mejoras técnicas (ver detalle en ARQUITECTURA.md)

- [ ] 🔴 Validar firma `X-Hub-Signature-256` del webhook
- [ ] 🔴 Secret Manager; quitar defaults de secretos; `/cron` con OIDC; desactivar `/diagnostico` en producción
- [ ] 🔴 Constante `GRAPH_API_VERSION` y migrar desde v21.0 (expira 21-ene-2027)
- [ ] 🔴 Repo en GitHub + Cloud Build + entorno de staging con número de prueba
- [ ] 🟠 Cloud Tasks: ack inmediato al webhook, tareas diferidas (reemplazar `threading.Timer`)
- [ ] 🟠 Idempotencia en Postgres (`mensajes.external_id` único) y estado fuera de memoria
- [ ] 🟠 `leads.interes` → `jsonb` y columnas reales (`etapa`, `score`, `asesor_id`)
- [ ] 🟠 Gemini por Vertex AI sin API key, salida estructurada, modelos verificados
- [ ] 🟠 Logs estructurados + Error Reporting + alertas de errores
- [ ] 🟠 Dividir `motor_agenda()` (412 líneas) y `process_conversation()` (249 líneas)
- [ ] 🟠 Suite de regresión: conversaciones reales anonimizadas → respuesta esperada (correr antes de cada deploy)
- [ ] 🟢 Multi-tenant (ver PRODUCTO_SAAS.md)
- [ ] 🟢 Function calling en lugar de regex para la agenda

## B. Funcionalidades nuevas para el chatbot

### Conversación
- [ ] 🔴 **Notas de voz**: transcribir audios con Gemini y responder como si fuera texto (hoy se pide escribir).
- [ ] 🟠 **Botones y listas interactivas de WhatsApp** para elegir horario, estilo de cocina o modalidad de pago (menos errores que "responde 1").
- [ ] 🟠 **WhatsApp Flows**: formulario nativo de precalificación (modalidad, inicial, presupuesto, plazo) dentro del chat.
- [ ] 🟠 **Mensaje de ubicación nativo** (pin de mapa) además del link.
- [ ] 🟠 **Leer imágenes**: si el cliente manda captura de un anuncio o de otra propiedad, identificar qué busca.
- [ ] 🟢 **Multi-idioma** (inglés para peruanos en el extranjero).
- [ ] 🟢 **Guardrails**: negarse a temas ajenos (política de Meta) y no inventar precios (siempre desde BD).

### Ventas
- [ ] 🔴 **Lead scoring automático** (caliente / tibio / frío) según financiamiento, presupuesto, urgencia y respuesta.
- [ ] 🔴 **Resumen IA para el asesor** al agendar: quién es, qué quiere, objeciones, cómo pagará.
- [ ] 🟠 **Catálogo multi-inmueble** con búsqueda por presupuesto, zona y dormitorios (clave para inmobiliarias con muchas unidades).
- [ ] 🟠 **Simulador hipotecario** con tasas por banco y Mivivienda / Techo Propio cuando aplique; derivación al sectorista aliado.
- [ ] 🟠 **Proforma PDF personalizada** (precio, bono, cuota referencial) generada y enviada por el bot.
- [ ] 🟠 **Confirmación de visita con botones** ("Confirmo" / "Reprogramar") y reprogramación sin asesor.
- [ ] 🟠 **Encuesta post-visita** de 1 pregunta (¿qué te faltó para decidir?) → alimenta objeciones.
- [ ] 🟢 **Asignación round-robin** entre asesores con calendarios separados.
- [ ] 🟢 **Campañas de reactivación** con plantillas de marketing a leads con opt-in (nuevo proyecto, bajada de precio).

### Panel y datos
- [ ] 🟠 **Inbox web** con toma de control humana (reemplaza los comandos por WhatsApp), notas y etiquetas.
- [ ] 🟠 **Pipeline tipo Kanban** (nuevo → calificado → cita → visitó → negociación → vendido).
- [ ] 🟠 **Reportes del embudo** por campaña: leads → calificados → citas → asistencias → cierres; costo por cita.
- [ ] 🟠 **Atribución de anuncios Click-to-WhatsApp** (el webhook trae `referral` con el anuncio de origen).
- [ ] 🟢 **Integraciones**: exportar a Google Sheets, HubSpot / Kommo; leads de portales (Urbania, Adondevivir) por correo → bot.
- [ ] 🟢 **Derecho al olvido**: borrar datos del lead a pedido (Ley 29733).
