# Contexto automático del código

> ⚠️ Archivo GENERADO por `scripts/generar_contexto.py`. No lo edites a mano: se sobrescribe en cada commit.
> Para contexto humano (decisiones, negocio, arquitectura) ver `CLAUDE.md` y `docs/`.

**Módulos:** 95 · **Líneas totales:** 9795 · **Límites:** archivo ≤ 300 líneas, función ≤ 60 líneas

## 1. Mapa de módulos

| Módulo | Líneas | Responsabilidad |
|---|---:|---|
| `main.py` | 7 | Punto de entrada para Cloud Run (gunicorn main:app). La lógica vive en el paquete bot/. |
| `bot/agente.py` | 128 | Turno completo del agente para tenants en modo 'catalogo': |
| `bot/agrupador.py` | 53 | Junta los mensajes que el cliente manda seguidos ('De un piso noms' / 'Quiero' / 'No me alcanza para más') |
| `bot/app.py` | 18 | Crea la aplicación Flask y registra todas las rutas (Blueprints). |
| `bot/asesor.py` | 56 | Comandos del asesor por WhatsApp (vino / no vino / pausa / vendido / estado). |
| `bot/atencion.py` | 103 | Atiende un mensaje entrante de WhatsApp de punta a punta (nunca deja sin respuesta). |
| `bot/canales/alertas.py` | 47 | Alertas al asesor humano (OWNER_WA) con respaldo por plantilla. |
| `bot/canales/hub_bandeja.py` | 24 | Bandeja de prueba del AI Sales Hub: los clientes simulados del Hub usan sender_id 'hub:+1999...'. Lo que el agente |
| `bot/canales/material.py` | 65 | Envío de fichas, renders y fotos solicitados en una respuesta. |
| `bot/canales/messenger.py` | 16 | Envío de mensajes privados por Messenger / Instagram. |
| `bot/canales/twilio_adapter.py` | 90 | Adaptador Twilio (SMS y WhatsApp vía Twilio) para EE. UU. / Canadá. |
| `bot/canales/whatsapp.py` | 179 | WhatsApp Cloud API: envío de texto, media (con subida y compresión) y plantillas. |
| `bot/catalogo/sincronizar.py` | 60 | CRM -> Supabase: copia productos, precios y archivos del CRM del cliente a catalog_items / catalog_media. |
| `bot/config.py` | 243 | Configuración: todas las variables de entorno y constantes del negocio. |
| `bot/conversacion/agenda.py` | 464 ⚠️ | Motor de agenda determinístico (máquina de estados de agendamiento). Corre antes que la IA. |
| `bot/conversacion/agenda_humana.py` | 283 | Agenda 'humana': entiende restricciones y preferencias ('trabajo hasta las 5', 'fin de semana', 'a eso de las 4.30'). |
| `bot/conversacion/base.py` | 9 | Helpers compartidos por los motores de respuesta. |
| `bot/conversacion/cierres.py` | 63 | Frases de cierre contextual según lo que se sabe del cliente. |
| `bot/conversacion/cortesia.py` | 124 | Cortesía conversacional: 'le estaré comunicando la hora', '👍', 'ok'. Un asesor no insiste ni responde un pulgar con una lista. |
| `bot/conversacion/despedida.py` | 51 | Cierre amable de conversación ('no, gracias', 'eso es todo'). |
| `bot/conversacion/faq.py` | 206 | Respuestas determinísticas a preguntas frecuentes de compra. |
| `bot/conversacion/formulario.py` | 76 | Primer mensaje a leads que llenaron el formulario de Meta. |
| `bot/conversacion/info.py` | 90 | Respuestas informativas por tema (ubicación, área, precio, etc.). |
| `bot/conversacion/material.py` | 198 | Respuestas cuando el cliente pide planos, renders, fotos o video. |
| `bot/conversacion/objeciones.py` | 87 | Objeciones de precio ('está muy caro', 'se me pasa del presupuesto') y descuento cuando compra con crédito. |
| `bot/conversacion/orquestador.py` | 434 ⚠️ | Orquestador: decide qué motor responde cada mensaje y persiste el resultado. |
| `bot/conversacion/post_agenda.py` | 84 | Después de agendar: con quién viene, desde dónde, movilidad y punto de encuentro (aprendido del chat real de Eloisa). |
| `bot/conversacion/precio.py` | 68 | Precio: moneda y tipo de cambio, el gancho del precio por m² y la respuesta a un tope de presupuesto. |
| `bot/conversacion/presupuesto.py` | 195 | Precio al contado, presupuesto del cliente y "¿solo tienen esas casas?": respuestas honestas (aprendido de chats reales). |
| `bot/conversacion/recursos.py` | 251 | Qué material mandar en cada momento (fotos reales, renders amoblados, videos y fichas por casa) y cómo rotularlo. |
| `bot/conversacion/respaldo.py` | 217 | Motor de respaldo cuando Gemini no responde. |
| `bot/conversacion/slots.py` | 105 | Ofrecer, elegir y recuperar horarios de visita. |
| `bot/crm.py` | 143 | Ficha viva del lead -> columnas de la tabla leads (siempre) -> CRM del cliente (si está activo). |
| `bot/crm_adapters/base.py` | 89 | Interfaz común de los adaptadores de CRM. Cada adaptador hace dos cosas: |
| `bot/crm_adapters/hubspot.py` | 96 | HubSpotCRMAdapter (API v3 con token de Private App): catálogo desde crm/v3/objects/products; el lead se escribe como |
| `bot/crm_adapters/mapeo.py` | 104 | Mapeo flexible de objetos y campos del CRM externo de cada cliente (tenants.crm_field_mapping_json). |
| `bot/crm_adapters/nativo.py` | 20 | PeruPTD Native CRM: el CRM es la propia base de Supabase (tablas leads, catalog_items, catalog_media) que muestra el |
| `bot/crm_adapters/pipedrive.py` | 82 | PipedriveCRMAdapter (API v1 con api_token): catálogo desde /products; lead = Person + Deal; cita = Activity de tipo |
| `bot/crm_adapters/salesforce.py` | 102 | SalesforceCRMAdapter: catálogo desde Product2 + PricebookEntry + archivos (ContentDocumentLink / ContentVersion) y |
| `bot/crm_adapters/zoho.py` | 83 | ZohoCRMAdapter (API v6, OAuth con refresh token): catálogo desde Products; lead en Leads (upsert por teléfono); |
| `bot/datos/colas.py` | 149 | Colas persistentes en Supabase (migración 002): fragmentos de mensajes por agrupar y tareas diferidas (Lead Ads 90 s). |
| `bot/datos/idempotencia.py` | 26 | Deduplicación de avisos de Meta y Twilio: memoria del proceso + tabla processed_webhooks (sobrevive reinicios |
| `bot/datos/leads.py` | 118 | Lectura y upsert de leads en Supabase (tabla leads, campo interes = JSON en texto). |
| `bot/datos/persistencia.py` | 28 | ¿Están disponibles las tablas persistentes de OmniAgent (migración 002)? Si fallan, el bot vuelve a la memoria del |
| `bot/datos/recursos.py` | 186 | Catálogo de material por casa leyendo el bucket 'recursos' de Supabase Storage, con los nombres que tengan. |
| `bot/db.py` | 21 | Cliente de Supabase (None si faltan credenciales). |
| `bot/engines/agenda.py` | 72 | Motor de agenda: 3 horarios reales libres que respetan lo que dijo el cliente (día, hora, "salgo del trabajo a |
| `bot/engines/calificacion.py` | 34 | Motor de calificación por producto: según catalog_items.qualification_mode (credito_inicial, seguro_medico, |
| `bot/engines/finanzas.py` | 64 | Motor de presupuesto y financiamiento (reglas del documento PeruPTD): |
| `bot/engines/guardas.py` | 36 | Guardas finales de la respuesta (Capa 3): frases prohibidas del playbook y anti-repetición (>= 80 % de similitud |
| `bot/engines/multimedia.py` | 18 | Motor multimedia: elige hasta 2 archivos del catálogo según el momento de la conversación (trigger_moment), sin |
| `bot/engines/objeciones.py` | 23 | Motor de objeción "Está caro" / "Too expensive" en 3 niveles. |
| `bot/engines/pipeline.py` | 139 | Fila de motores (Capa 2) + redactor bilingüe (Capa 3) para tenants en modo 'catalogo'. |
| `bot/engines/textos.py` | 19 | Utilidades de redacción bilingüe (Capa 3). |
| `bot/estado.py` | 13 | Estado en memoria del proceso (cachés y deduplicación). OJO: se pierde al reiniciar y no se comparte entre instancias. |
| `bot/handoff.py` | 63 | Detección de intervención humana (mensajes manuales del asesor) y pausa del bot. |
| `bot/hub/sesion.py` | 110 | Sesiones del PeruPTD Native CRM (/app). |
| `bot/ia/gemini.py` | 125 | Llamada a Gemini (AI Studio / Vertex express) con lista de modelos y presupuesto de tiempo. |
| `bot/ia/prompt.py` | 124 | System prompt del asesor comercial (datos del proyecto y casuísticas). |
| `bot/integraciones/calendario.py` | 221 | Google Calendar: disponibilidad (freebusy), slots libres, crear y reprogramar visitas. |
| `bot/integraciones/salesforce_sync.py` | 189 | Conector de Salesforce (REST API): autenticación OAuth 2.0 (Client Credentials o JWT Bearer), Lead, Event, Task e |
| `bot/integraciones/tipo_cambio.py` | 51 | Tipo de cambio referencial PEN/USD: se actualiza solo desde el BCRP (interbancario venta) y, si falla, usa el número fijo. |
| `bot/leadgen.py` | 102 | Seguimiento diferido (90 s) a leads de formularios Lead Ads. La espera queda registrada en Supabase (scheduled_jobs): |
| `bot/nlp/dias.py` | 73 | Qué días puede el cliente, dicho de mil formas: 'no puedo entre semana', 'solo los sábados', 'de lunes a viernes trabajo', |
| `bot/nlp/financiamiento.py` | 126 | Detección y resumen de la modalidad de compra (contado / crédito / inicial). |
| `bot/nlp/formulario.py` | 29 | Lectura del texto de formularios Lead Ads de Meta que llegan por chat. |
| `bot/nlp/numeros.py` | 40 | Montos escritos en palabras ('cuatrocientos mil ochocientos', 'ciento veinte mil') -> número. |
| `bot/nlp/parser_fechas.py` | 108 | Interpreta fechas y horas escritas en español ('el sábado a las 4 pm'). |
| `bot/nlp/patrones.py` | 123 | Expresiones regulares de intención (visita, material, afirmación, negación, despedida, etc.). |
| `bot/nlp/restricciones.py` | 72 | Detecta restricciones de horario del cliente ('trabajo hasta las 5', 'después de las 4', 'en la noche'). |
| `bot/nlu/lexico.py` | 203 | Normalizador determinístico ES/EN (respaldo del NLU con IA y base de las pruebas). Usa bot/nlu/lexicon.json, el |
| `bot/nlu_normalizer.py` | 140 | Capa 1 · Intérprete semántico bilingüe (ES / EN / Spanglish). |
| `bot/playbooks.py` | 66 | Playbook del cliente (tenant): datos del negocio, reglas, frases prohibidas, interruptores del protocolo y mapeo a |
| `bot/rutas/catalogo.py` | 15 | POST /catalogo/sincronizar: copia el catálogo del CRM del cliente a Supabase (productos, precios y archivos). |
| `bot/rutas/cron.py` | 47 | Endpoint protegido que ejecuta los seguimientos (y termina lo que un reinicio dejó a medias). |
| `bot/rutas/diagnostico.py` | 66 | Endpoint de diagnóstico del envío de media. |
| `bot/rutas/hub_api.py` | 177 | Operación diaria del PeruPTD Native CRM (todo filtrado por el tenant de la sesión): |
| `bot/rutas/hub_auth.py` | 40 | Login del PeruPTD Native CRM: POST /api/hub/login, POST /api/hub/logout, GET /api/hub/me. |
| `bot/rutas/hub_catalogo.py` | 237 | Catálogo del PeruPTD Native CRM (siempre del tenant de la sesión): |
| `bot/rutas/hub_config.py` | 119 | Ajustes del cliente desde el CRM web: |
| `bot/rutas/salesforce.py` | 39 | Salesforce -> bot. Un Flow (o Outbound Message) avisa cuando el asesor cambia la cita o escribe al cliente desde |
| `bot/rutas/salud.py` | 10 | Health check. |
| `bot/rutas/twilio.py` | 30 | Webhook de Twilio (SMS y WhatsApp vía Twilio): POST /webhook/twilio. |
| `bot/rutas/webhook.py` | 224 | Webhook de Meta: WhatsApp, Messenger, Instagram, comentarios y Lead Ads. |
| `bot/seguimiento/envio.py` | 59 | Envío de seguimientos respetando la ventana de 24 h (texto libre / plantilla / manual). |
| `bot/seguimiento/mensajes.py` | 136 | Textos de rescate 24 h y del protocolo post-visita de 14 días. |
| `bot/seguimiento/motor.py` | 175 | Motor de seguimiento automático (lo invoca Cloud Scheduler vía /cron). |
| `bot/seguimiento/motor_catalogo.py` | 213 | Seguimiento automático para tenants en modo 'catalogo' (cualquier industria, ES/EN). Misma lógica de tiempos que el |
| `bot/seguimiento/plantillas.py` | 91 | Plantillas de seguimiento por tenant e idioma (modo 'catalogo'): recordatorio, protocolo post-visita de 14 días |
| `bot/seguimiento/plantillas_industria.py` | 145 | Plantillas por defecto por industria (ES/EN) para el seguimiento de 14 días y el rescate de 24 h. |
| `bot/tenant.py` | 71 | Empresa (tenant) de la petición actual. |
| `bot/utils/fechas.py` | 67 | Formato de fechas/horas en español y utilidades de zona horaria (Lima). |
| `bot/utils/firma_meta.py` | 15 | Verificación de la firma X-Hub-Signature-256 que Meta pone en cada aviso del webhook. |
| `bot/utils/telefono.py` | 49 | Normalización y extracción de teléfonos (Perú +51 e internacionales). |
| `bot/utils/texto.py` | 46 | Normalización de texto (tildes, minúsculas) y formatos simples. |

## 2. Rutas HTTP

| Ruta | Métodos | Función | Archivo |
|---|---|---|---|
| `/catalogo/sincronizar` | POST | `sincronizar_catalogo` | `bot/rutas/catalogo.py` |
| `/cron/seguimiento` | GET,POST | `cron_seguimiento` | `bot/rutas/cron.py` |
| `/cron` | GET,POST | `cron_seguimiento` | `bot/rutas/cron.py` |
| `/reloj` | GET,POST | `cron_seguimiento` | `bot/rutas/cron.py` |
| `/diagnostico/media` | GET | `diagnostico_media` | `bot/rutas/diagnostico.py` |
| `/diagnostico/material` | GET | `diagnostico_material` | `bot/rutas/diagnostico.py` |
| `/api/hub/<path:_resto>` | OPTIONS | `_preflight` | `bot/rutas/hub_api.py` |
| `/app` | GET | `web` | `bot/rutas/hub_api.py` |
| `/hub` | GET | `web` | `bot/rutas/hub_api.py` |
| `/api/hub/estado` | GET | `estado` | `bot/rutas/hub_api.py` |
| `/api/hub/leads` | GET | `leads` | `bot/rutas/hub_api.py` |
| `/api/hub/leads/<path:sender_id>/mensajes` | GET | `mensajes` | `bot/rutas/hub_api.py` |
| `/api/hub/leads/<path:sender_id>/comando` | POST | `comando` | `bot/rutas/hub_api.py` |
| `/api/hub/chat` | POST | `chat` | `bot/rutas/hub_api.py` |
| `/api/hub/login` | POST | `login` | `bot/rutas/hub_auth.py` |
| `/api/hub/logout` | POST | `logout` | `bot/rutas/hub_auth.py` |
| `/api/hub/me` | GET | `me` | `bot/rutas/hub_auth.py` |
| `/api/hub/catalogo` | GET | `listar` | `bot/rutas/hub_catalogo.py` |
| `/api/hub/catalogo` | POST | `crear` | `bot/rutas/hub_catalogo.py` |
| `/api/hub/catalogo/<item_id>` | PUT,PATCH | `editar` | `bot/rutas/hub_catalogo.py` |
| `/api/hub/catalogo/<item_id>` | DELETE | `borrar` | `bot/rutas/hub_catalogo.py` |
| `/api/hub/catalogo/<item_id>/media` | POST | `subir_media` | `bot/rutas/hub_catalogo.py` |
| `/api/hub/catalogo/<item_id>/media/<media_id>` | DELETE | `borrar_media` | `bot/rutas/hub_catalogo.py` |
| `/api/hub/catalogo/sincronizar` | POST | `sincronizar_crm` | `bot/rutas/hub_catalogo.py` |
| `/api/hub/playbook` | GET | `ver` | `bot/rutas/hub_config.py` |
| `/api/hub/playbook` | PUT | `guardar` | `bot/rutas/hub_config.py` |
| `/webhook/salesforce` | POST | `desde_salesforce` | `bot/rutas/salesforce.py` |
| `/` | GET | `home` | `bot/rutas/salud.py` |
| `/webhook/twilio` | POST | `desde_twilio` | `bot/rutas/twilio.py` |
| `/webhook` | GET | `verify` | `bot/rutas/webhook.py` |
| `/webhook` | POST | `webhook` | `bot/rutas/webhook.py` |

## 3. Funciones por módulo

### `bot.agente`
_Depende de:_ `bot`, `bot.canales`, `bot.canales.alertas`, `bot.canales.whatsapp`, `bot.config`, `bot.crm`, `bot.datos.leads`, `bot.db`, `bot.engines`, `bot.engines.textos`, `bot.integraciones.calendario`, `bot.nlu_normalizer`

- `_alertar()` (6 líneas) — Alerta al asesor por WhatsApp; en el Hub (cliente simulado) queda en la bandeja para mostrarla en pantalla.
- `libres_en_horario()` (9 líneas) — Horarios libres del calendario dentro del horario de visitas del cliente (playbook agenda.horario_visitas).
- `_historial()` (8 líneas)
- `_guardar_mensajes()` (10 líneas)
- `_reservar()` (19 líneas) — Crea el evento en el calendario. Devuelve (texto, cambios_meta).
- `atender_turno()` (40 líneas) — Responde un lote de mensajes ya agrupado. Devuelve el ResultadoTurno (para pruebas y registros).

### `bot.agrupador`
_Depende de:_ `bot.config`, `bot.datos`, `bot.estado`, `bot.utils.texto`

- `segundos_de_espera()` (8 líneas) — WhatsApp no avisa si el cliente sigue escribiendo: se espera más tras un saludo suelto o un mensaje cortado.
- `esperar_y_agrupar()` (10 líneas) — Devuelve el texto combinado si a esta llamada le toca responder, o None si llegó otro mensaje después (ese responde).
- `_agrupar_en_memoria()` (13 líneas)

### `bot.app`
_Depende de:_ `bot.config`, `bot.rutas`

- `create_app()` (6 líneas)

### `bot.asesor`
_Depende de:_ `bot.config`, `bot.crm`, `bot.datos.leads`, `bot.nlp.financiamiento`, `bot.nlp.patrones`, `bot.utils.fechas`, `bot.utils.telefono`, `bot.utils.texto`

- `procesar_comando_asesor()` (41 líneas)

### `bot.atencion`
_Depende de:_ `bot`, `bot.agente`, `bot.agrupador`, `bot.asesor`, `bot.canales.alertas`, `bot.canales.material`, `bot.canales.whatsapp`, `bot.config`, `bot.conversacion.orquestador`, `bot.crm`, `bot.db`, `bot.estado`, `bot.handoff`, `bot.utils.telefono`

- `_sin_texto()` (13 líneas) — Audio / imagen / archivo sin texto. A una imagen se responde una sola vez cada 30 min (luego solo se avisa al asesor).
- `_guardar_sin_responder()` (3 líneas)
- `_responder()` (21 líneas) — Arma y envía la respuesta a un texto ya agrupado.
- `_fallo()` (8 líneas)
- `atender_mensaje_wa()` (23 líneas) — Procesa un mensaje entrante. Nunca deja al cliente sin respuesta: ante cualquier error responde algo y avisa al dueño.
- `responder_lote_pendiente()` (6 líneas) — Para /cron: un lote de mensajes cuya petición murió esperando (reinicio de Cloud Run). Se responde igual.

### `bot.canales.alertas`
_Depende de:_ `bot.canales.whatsapp`, `bot.config`, `bot.estado`, `bot.utils.telefono`

- `alertar_asesor()` (36 líneas) — Envía una alerta al asesor (OWNER_WA, o el WhatsApp del asesor del tenant si se indica). Si el mensaje libre falla (por la ventana de 24 h de WhatsApp),

### `bot.canales.hub_bandeja`

- `es_simulado()` (2 líneas)
- `guardar()` (6 líneas)
- `vaciar()` (3 líneas)

### `bot.canales.material`
_Depende de:_ `bot.canales.alertas`, `bot.canales.whatsapp`, `bot.config`, `bot.conversacion.recursos`, `bot.estado`

- `_enviar_render_cocina()` (10 líneas) — Render de cocina: primero el archivo fijo; si WhatsApp lo rechaza, uno equivalente del bucket. (nombre, ok, url)
- `send_requested_wa_media()` (39 líneas)

### `bot.canales.messenger`
_Depende de:_ `bot.config`

- `send_meta_dm()` (10 líneas)

### `bot.canales.twilio_adapter`
_Depende de:_ `bot.config`

- `es_destino_twilio()` (2 líneas)
- `sin_ventana_24h()` (2 líneas)
- `sender_id()` (6 líneas) — 'whatsapp:+1512...' -> 'twa:+1512...' ; '+1512...' -> 'sms:+1512...'
- `_para_twilio()` (3 líneas)
- `texto_sms()` (3 líneas) — El SMS no interpreta *negritas* de WhatsApp.
- `_enviar()` (15 líneas)
- `enviar_texto()` (5 líneas)
- `enviar_media()` (5 líneas) — MMS / WhatsApp con archivo (URL pública). En SMS, si el operador no soporta MMS, Twilio envía el enlace.
- `firma_valida()` (7 líneas) — X-Twilio-Signature = Base64(HMAC-SHA1(auth_token, url + parámetros POST ordenados concatenados)).
- `normalizar_entrante()` (7 líneas) — Formulario de Twilio -> datos con la misma forma que un mensaje de WhatsApp Cloud API.

### `bot.canales.whatsapp`
_Depende de:_ `bot.canales`, `bot.config`, `bot.estado`, `bot.utils.telefono`

- `send_wa_text()` (26 líneas)
- `_tipo_media_por_url()` (9 líneas)
- `subir_media_wa()` (50 líneas) — Descarga el archivo y lo sube a WhatsApp (devuelve media_id). Así los errores (archivo pesado, URL caída)
- `send_wa_media()` (37 líneas)
- `send_wa_template()` (26 líneas)
- `extraer_texto_wa()` (10 líneas)

### `bot.catalogo.sincronizar`
_Depende de:_ `bot`, `bot.config`, `bot.crm_adapters`, `bot.tenant`

- `_subir()` (9 líneas)
- `sincronizar()` (31 líneas) — Devuelve un resumen {'items': n, 'media': n, 'errores': [...]}.

### `bot.config`

- `_url_media()` (11 líneas) — Toma la URL de las variables de entorno solo si es un link real (http/https).
- `_url_opcional()` (3 líneas)

### `bot.conversacion.agenda`
_Depende de:_ `bot.canales.alertas`, `bot.canales.whatsapp`, `bot.config`, `bot.conversacion.agenda_humana`, `bot.conversacion.base`, `bot.conversacion.cierres`, `bot.conversacion.post_agenda`, `bot.conversacion.presupuesto`, `bot.conversacion.slots`, `bot.integraciones.calendario`, `bot.nlp.dias`, `bot.nlp.financiamiento`, `bot.nlp.parser_fechas`, `bot.nlp.patrones`, `bot.nlp.restricciones`, `bot.utils.fechas`, `bot.utils.texto`

- `motor_agenda()` (439 líneas ⚠️) — Devuelve una respuesta (dict) si el mensaje es de agendamiento; None para dejarlo a Gemini/fallback.

### `bot.conversacion.agenda_humana`
_Depende de:_ `bot.config`, `bot.conversacion.base`, `bot.conversacion.slots`, `bot.integraciones.calendario`, `bot.nlp.dias`, `bot.nlp.restricciones`, `bot.utils.fechas`, `bot.utils.texto`

- `slots_vigentes()` (14 líneas) — Horarios ya ofrecidos que siguen en el futuro (para no cambiarle la lista al cliente).
- `_pie()` (6 líneas)
- `_fin_de_semana()` (3 líneas) — Los horarios libres más próximos del fin de semana, según el calendario.
- `_hora_txt()` (2 líneas)
- `_por_trabajo()` (16 líneas) — 'Trabajo hasta las 5' / 'de lunes a viernes trabajo' / 'en la noche': como el asesor —
- `_encabezado_general()` (6 líneas)
- `_con_restriccion()` (19 líneas)
- `agenda_por_preferencias()` (26 líneas) — Respuesta con horarios que respetan lo que dijo el cliente, o None para seguir el flujo normal.
- `completar_fecha_por_contexto()` (29 líneas) — 'A eso de las 4.30' después de ofrecer el sábado => sábado 4:30. Si se ofrecieron varios días, pregunta cuál.
- `_intro()` (15 líneas) — Saludo largo solo la 1ra vez; si ya tiene cita, se habla de CAMBIARLA (no de una visita nueva).
- `ofrecer_por_dia()` (38 líneas) — 'Mejor el domingo', '¿el domingo 1 no tienes?', '¿para la tarde?' (sobre el día que se venía hablando).
- `_ya_ofrecidos()` (6 líneas)
- `inferir_hora_suelta()` (13 líneas) — 'Plan de 5?' (por 'para las 5'), '5?', 'de 4' con una lista de horarios a la vista: es una hora, no una opción ni otra cosa.
- `proponer_si_pregunta()` (10 líneas) — '¿y a las 4?' es una PREGUNTA: se confirma que está libre y se pide el 'sí' (no se agenda de golpe). None si no está libre.
- `ofrecer_mas_tarde()` (23 líneas) — '¿Más tarde no podría ser?' con horarios a la vista = pide una hora MÁS TARDE ese mismo día (no es un rechazo).

### `bot.conversacion.base`

- `_resp()` (6 líneas)

### `bot.conversacion.cierres`
_Depende de:_ `bot.config`, `bot.conversacion.slots`, `bot.integraciones.calendario`, `bot.utils.fechas`

- `_cierre_con_horarios()` (26 líneas)
- `cierre_contextual()` (17 líneas) — Cierra cada respuesta con el SIGUIENTE paso real de esa conversación (no repite lo ya resuelto).
- `cierre_info()` (7 líneas) — Caso 5: tras pedir información general, una pregunta de filtro financiero (solo si aún no se sabe); si no, el siguiente paso.

### `bot.conversacion.cortesia`
_Depende de:_ `bot.conversacion.agenda_humana`, `bot.conversacion.base`, `bot.conversacion.recursos`, `bot.nlp.parser_fechas`, `bot.nlp.patrones`, `bot.utils.texto`

- `es_acuse()` (7 líneas) — True si el mensaje es solo un emoji o un 'ok/listo/ya' sin más contenido.
- `_silencio()` (5 líneas)
- `_postergacion()` (30 líneas)
- `_acuse()` (18 líneas)
- `_saludo()` (10 líneas) — 'Buenos días' de alguien que ya conversó antes: saludar y preguntar, sin lanzar horarios.
- `responder_cortesia()` (18 líneas) — Postergaciones y acuses. None si el mensaje tiene contenido para otros motores (fecha, hora, pregunta).

### `bot.conversacion.despedida`
_Depende de:_ `bot.canales.alertas`, `bot.config`, `bot.conversacion.base`, `bot.nlp.patrones`, `bot.utils.fechas`, `bot.utils.texto`

- `responder_despedida()` (39 líneas) — Si el cliente se despide o ya no tiene dudas, se despide amablemente (sin volver a preguntar nada).

### `bot.conversacion.faq`
_Depende de:_ `bot.config`, `bot.conversacion.cierres`, `bot.conversacion.objeciones`, `bot.conversacion.presupuesto`, `bot.nlp.financiamiento`, `bot.utils.texto`

- `responder_faq()` (195 líneas ⚠️) — Respuestas fijas a las preguntas frecuentes de compra (crédito y contado). Usan el estado del cliente para no repetir.

### `bot.conversacion.formulario`
_Depende de:_ `bot.config`, `bot.conversacion.cierres`, `bot.conversacion.material`, `bot.nlp.financiamiento`, `bot.utils.texto`

- `marcar_bienvenida()` (3 líneas)
- `bienvenida_reciente()` (7 líneas) — True si ya se le mandó la bienvenida del formulario hace menos de 'dias' (Meta a veces avisa 2 veces del mismo formulario:
- `texto_formulario()` (51 líneas) — Respuesta a un lead del formulario de Meta según lo que marcó (pago, estilo de cocina y presupuesto).

### `bot.conversacion.info`
_Depende de:_ `bot.config`, `bot.conversacion.base`, `bot.conversacion.cierres`, `bot.conversacion.precio`, `bot.conversacion.presupuesto`, `bot.utils.texto`

- `temas_info()` (8 líneas)
- `responder_info()` (57 líneas) — Información, detalles, precio, área, ubicación/dirección, distribución, entrega y sus combinaciones (Casos 2, 4, 5, 6, 9, 12).

### `bot.conversacion.material`
_Depende de:_ `bot.config`, `bot.conversacion.base`, `bot.conversacion.cierres`, `bot.conversacion.recursos`, `bot.nlp.patrones`, `bot.utils.texto`

- `_estilo_de_texto()` (7 líneas)
- `_respuesta_muebles()` (9 líneas) — '¿Viene amoblada?' / '¿cómo se ve con muebles?'.
- `_partes_galeria()` (36 líneas) — 'Mándame fotos': mezcla de las 2 casas, fotos reales y renders; luego ofrece el video (o los planos), sin listar horarios.
- `responder_oferta_video()` (26 líneas) — Respuesta a '¿Te gustaría ver el recorrido en video?': 'sí' / 'ok' / '👍' -> videos; 'no' -> sigue la conversación.
- `_partes_video()` (11 líneas) — Videos por casa desde el catálogo (p. ej. 'envíame las dos casas en video para mostrarle a mi familia').
- `responder_material()` (84 líneas ⚠️) — Pedidos de fotos, planos, renders, video, la opción '1' del menú, o la elección de un estilo de cocina.

### `bot.conversacion.objeciones`
_Depende de:_ `bot.config`, `bot.conversacion.cierres`, `bot.conversacion.precio`, `bot.conversacion.presupuesto`, `bot.nlp.financiamiento`, `bot.nlp.patrones`, `bot.utils.texto`

- `es_objecion_precio()` (2 líneas)
- `_primera_objecion()` (17 líneas)
- `_segunda_objecion()` (6 líneas)
- `_tercera_objecion()` (6 líneas)
- `responder_objecion_precio()` (11 líneas)
- `responder_descuento_credito()` (10 líneas) — '¿Hay descuento?' de alguien que NO compra al contado (al contado lo responde la FAQ).
- `responder_precio()` (11 líneas) — Despacha moneda / objeción de precio / descuento con crédito. None si el mensaje no es de esto.

### `bot.conversacion.orquestador`
_Depende de:_ `bot.canales.alertas`, `bot.canales.whatsapp`, `bot.config`, `bot.conversacion.agenda`, `bot.conversacion.base`, `bot.conversacion.cierres`, `bot.conversacion.cortesia`, `bot.conversacion.despedida`, `bot.conversacion.faq`, `bot.conversacion.formulario`, `bot.conversacion.info`, `bot.conversacion.material`, `bot.conversacion.objeciones`, `bot.conversacion.post_agenda`, `bot.conversacion.recursos`, `bot.conversacion.respaldo`, `bot.conversacion.slots`, `bot.datos`, `bot.datos.leads`, `bot.db`, `bot.estado`, `bot.ia.gemini`, `bot.ia.prompt`, `bot.integraciones.calendario`, `bot.nlp.financiamiento`, `bot.nlp.formulario`, `bot.nlp.parser_fechas`, `bot.nlp.patrones`, `bot.utils.fechas`, `bot.utils.telefono`, `bot.utils.texto`

- `process_conversation()` (274 líneas ⚠️)
- `_es_repeticion()` (5 líneas)
- `_reintento_de_meta()` (9 líneas) — El mismo mensaje largo otra vez, ya respondido, en pocos minutos = Meta reenvió el webhook (otra instancia no lo conoce).
- `_finalizar_conversacion()` (101 líneas ⚠️)

### `bot.conversacion.post_agenda`
_Depende de:_ `bot.config`, `bot.conversacion.base`, `bot.nlp.patrones`, `bot.utils.texto`

- `_ack_propia()` (6 líneas)
- `_respuesta_acompanantes()` (26 líneas)
- `_respuesta_movilidad()` (11 líneas)
- `responder_post_agenda()` (14 líneas) — Respuestas sobre acompañantes, movilidad y punto de encuentro cuando ya hay cita. None si no aplica.

### `bot.conversacion.precio`
_Depende de:_ `bot.config`, `bot.conversacion.cierres`, `bot.integraciones.tipo_cambio`, `bot.nlp.patrones`, `bot.utils.texto`

- `precio_m2()` (2 líneas)
- `_soles()` (2 líneas)
- `gancho_m2()` (12 líneas) — Una línea con el argumento del precio por m² (cuenta cuántas veces se usó para no repetirlo de más).
- `es_pregunta_moneda()` (2 líneas)
- `techo_soles()` (3 líneas) — 487,500 -> 'S/ 490,000' (el múltiplo de 5 mil inmediatamente superior), para decir 'por debajo de…'.
- `responder_moneda()` (26 líneas) — '¿El precio es en soles o en dólares?', '¿a qué tipo de cambio?', '¿puedo pagar en soles?'.

### `bot.conversacion.presupuesto`
_Depende de:_ `bot.config`, `bot.conversacion.base`, `bot.conversacion.cierres`, `bot.conversacion.precio`, `bot.integraciones.tipo_cambio`, `bot.nlp.numeros`, `bot.utils.texto`

- `tc()` (2 líneas)
- `linea_contado()` (4 líneas) — 'Al contado el precio es US$130,000 (...) y lo puedes negociar en la visita con el propietario.'
- `leer_monto()` (19 líneas) — '100.000', '100 mil', '120k', 'S/ 400,000', '$110,000', 'cuatrocientos mil' -> (monto, 'usd' | 'pen' | None).
- `es_presupuesto()` (6 líneas)
- `_cuota()` (4 líneas)
- `respuesta_tope_usd()` (32 líneas) — Respuesta honesta según cuánto puede invertir (en US$).
- `respuesta_monto()` (19 líneas) — Convierte y responde; si no se sabe la moneda, la pregunta.
- `responder_muy_grande()` (9 líneas) — 'Es que muy grande': objeción de tamaño. Se entiende, se aclara cómo se vive la casa y se pregunta qué busca.
- `responder_otras_opciones()` (13 líneas) — '¿Hay más económicas?', '¿De un solo piso no venden?', '¿solo tienen esas?'.
- `responder_precio_contado()` (7 líneas) — '¿Cuánto es el precio total al contado?', '¿precio final?', '¿cuánto en soles al contado?'.
- `responder_medio_millon()` (5 líneas) — 'Casi es precio el de medio millón' (lo está pensando en soles).
- `responder_presupuesto()` (20 líneas) — Despacha lo de este módulo. None si no aplica.

### `bot.conversacion.recursos`
_Depende de:_ `bot.config`, `bot.datos.recursos`, `bot.utils.texto`

- `catalogo()` (7 líneas)
- `hay_fotos()` (2 líneas)
- `hay_videos()` (2 líneas)
- `unidad_del_texto()` (8 líneas) — 'casa 2', 'la segunda casa' -> 'casa_2'; 'las dos casas' / nada -> None (todas).
- `_nombre_propio()` (6 líneas) — True si el nombre del archivo es más específico que el ambiente ('cuarto niños' vs 'dormitorio').
- `leyenda()` (24 líneas)
- `_clave()` (2 líneas)
- `_por_unidad()` (2 líneas)
- `hay_renders()` (2 líneas)
- `_tipo_ambiente()` (2 líneas)
- `_elegir()` (11 líneas) — Una por ambiente; no repite archivo NI otra versión del mismo tipo+ambiente (2 renders de sala = la misma idea).
- `_ordenar_variado()` (8 líneas) — Primero un archivo por cada (ambiente, tipo) distinto, luego el resto: así la galería no repite 3 salas seguidas.
- `elegir_galeria()` (15 líneas) — Cuando pide fotos: mezcla las 2 casas (y lo común), fotos reales y renders amoblados, sin repetir lo ya enviado.
- `resumen_galeria()` (6 líneas) — Qué hay para describirlo en el texto: casas con fotos, si hay renders, si hay videos.
- `fichas_por_casa()` (2 líneas)
- `elegir_fotos()` (12 líneas) — [(url, 'image', leyenda)] para ese momento, sin repetir lo ya enviado (salvo que las pida). Registra lo enviado.
- `renders_cocina_catalogo()` (5 líneas) — URLs del bucket con el render de cocina de ese estilo ('gris' / 'madera'), por si el archivo fijo (cocina_1/2.jpg) falla.
- `material_de_tipo()` (5 líneas) — Videos o fichas del catálogo: [(url, tipo_whatsapp, leyenda)] (tipo_whatsapp se deduce del archivo al enviar).
- `_recien_agendado()` (6 líneas)
- `asignar_media()` (26 líneas) — Al final de cada respuesta: agrega a parsed['recursos'] el material del momento (solo WhatsApp).

### `bot.conversacion.respaldo`
_Depende de:_ `bot.config`, `bot.conversacion.faq`, `bot.conversacion.slots`, `bot.integraciones.calendario`, `bot.nlp.patrones`, `bot.utils.fechas`, `bot.utils.texto`

- `build_Contextual_fallback()` (205 líneas ⚠️)

### `bot.conversacion.slots`
_Depende de:_ `bot.config`, `bot.integraciones.calendario`, `bot.nlp.parser_fechas`, `bot.utils.fechas`

- `_slots_a_texto()` (3 líneas)
- `elegir_slot_ofrecido()` (32 líneas)
- `horarios_en()` (22 líneas) — Horarios concretos libres ('sábado 10:00', 'lunes 18:30') en los días y horas indicados, verificados en Calendar.
- `construir_slot()` (11 líneas)
- `recuperar_slot_de_historial()` (9 líneas) — Si el cliente propuso día y hora en mensajes anteriores (y no quedó guardado), lo recupera.
- `_dos_horarios()` (8 líneas) — Dos horarios libres reales para cerrar el seguimiento; guarda el estado para que '1'/'2' funcione.

### `bot.crm`
_Depende de:_ `bot`, `bot.config`, `bot.crm_adapters`, `bot.datos.leads`, `bot.db`, `bot.nlp.financiamiento`

- `etapa_comercial()` (20 líneas) — new | qualified | booked | visited | negotiation | no_show | won | lost
- `telefono_visible()` (3 líneas) — Los clientes de Twilio se guardan como 'sms:+1512…' / 'twa:+1512…': al CRM va solo el número.
- `ficha()` (16 líneas)
- `escribir_columnas()` (17 líneas) — Columnas consultables de la ficha viva (migración 003). Si aún no existen, no pasa nada.
- `_firma()` (2 líneas)
- `_resumen_chat()` (8 líneas)
- `sincronizar_lead()` (34 líneas)
- `sincronizar_seguro()` (9 líneas) — Punto de entrada para el resto del bot: nunca lanza errores.

### `bot.crm_adapters.base`

- `tipo_por_nombre()` (7 líneas)
- `trigger_por_nombre()` (6 líneas) — Convención para el cliente: el archivo se llama '[PRICE_OBJECTION] Cochera.jpg'. Sin etiqueta, se deduce del tipo.
- `leyenda()` (2 líneas)
- `solo_digitos()` (2 líneas)

### `bot.crm_adapters.mapeo`

- `_mezclar()` (7 líneas)
- `efectivo()` (10 líneas) — Mapeo final del tenant: estándar del CRM <- crm_field_map (formato antiguo) <- crm_field_mapping_json.
- `para_adaptador()` (9 líneas) — Lo que reciben los adaptadores en self.campos: el mapeo completo + los atajos 'catalogo' (solo campos propios,
- `validar()` (35 líneas) — (mapeo_limpio, error). Solo nombres de API válidos (sin espacios ni SOQL/SQL): evita inyección en las consultas.

### `bot.datos.colas`
_Depende de:_ `bot.config`, `bot.datos`

- `_iso()` (2 líneas)
- `encolar_fragmento()` (12 líneas) — Guarda el fragmento y devuelve su id (o None si no hay persistencia: se usa la memoria).
- `reclamar_lote()` (18 líneas) — Tras la espera: si llegó otro fragmento después, responde ese (None). Si no, toma todo lo pendiente del cliente
- `lotes_vencidos()` (27 líneas) — Lotes cuya petición murió esperando (reinicio): [(sender, texto, perfil, canal)], ya marcados como tomados.
- `programar_tarea()` (13 líneas) — Registra la tarea (cancela otra pendiente igual). Devuelve su id, o None sin persistencia.
- `reclamar_tarea()` (11 líneas) — True si a quien llama le toca ejecutarla (pending -> tomado es atómico). Sin id o ante un error: True.
- `cancelar_tareas()` (8 líneas)
- `tareas_vencidas()` (11 líneas) — Tareas que su timer no llegó a ejecutar (reinicio). Devuelve las filas ya tomadas por esta llamada.
- `limpiar_antiguos()` (15 líneas) — Borra registros viejos para que las tablas no crezcan sin fin (lo llama /cron).

### `bot.datos.idempotencia`
_Depende de:_ `bot.config`, `bot.datos`, `bot.estado`

- `ya_procesado()` (19 líneas) — True si este id ya se atendió. Si es nuevo, lo marca como atendido y devuelve False.

### `bot.datos.leads`
_Depende de:_ `bot`, `bot.config`, `bot.db`, `bot.utils.telefono`

- `tabla()` (3 líneas) — Consulta sobre leads / mensajes filtrada por el tenant actual cuando hay varios clientes en el mismo Supabase.
- `con_tenant()` (10 líneas) — Agrega tenant_id a las filas a insertar (solo con MULTI_TENANT). Sin el esquema nuevo, quita las columnas que
- `migrar_id_legado()` (14 líneas) — Si el cliente llega con BSUID ("PE.148…") y antes se guardó sin prefijo ("148…"), pasa su lead e historial al ID nuevo.
- `get_lead_by_sender_or_phone()` (14 líneas)
- `safe_upsert_lead()` (37 líneas)

### `bot.datos.persistencia`
_Depende de:_ `bot`, `bot.config`

- `disponible()` (2 líneas)
- `cliente()` (2 líneas)
- `es_duplicado()` (4 líneas) — Choque de PRIMARY KEY / UNIQUE en Postgres (código 23505): ese id ya estaba registrado.
- `desactivar()` (4 líneas)

### `bot.datos.recursos`
_Depende de:_ `bot.config`, `bot.db`

- `_norm()` (4 líneas)
- `_unidad()` (6 líneas)
- `_tipo()` (8 líneas)
- `_ambiente()` (6 líneas)
- `nombre_legible()` (6 líneas) — 'segundo-piso_2.jpg' -> 'Segundo piso'.
- `_url_publica()` (2 líneas)
- `_clasificar()` (22 líneas)
- `_recorrer()` (20 líneas)
- `_desde_bucket()` (9 líneas)
- `_desde_tabla()` (6 líneas)
- `listar_recursos()` (21 líneas) — Material disponible (bucket + tabla opcional). [] si no hay Supabase.
- `resumen_catalogo()` (11 líneas) — Para /diagnostico/material: lo que el bot ve en el bucket, cómo lo entendió y los problemas encontrados.

### `bot.db`
_Depende de:_ `bot.config`

- `_crear()` (10 líneas)

### `bot.engines.agenda`
_Depende de:_ `bot.engines.textos`

- `_minutos()` (3 líneas)
- `dia_objetivo()` (9 líneas)
- `etiqueta()` (9 líneas)
- `proponer()` (21 líneas) — entidades: NormalizedTurn.entities (dict). buscar_libres: get_free_slots(n, dia=None, filtro=None, excluir=None).
- `texto_opciones()` (10 líneas)

### `bot.engines.calificacion`
_Depende de:_ `bot.engines.textos`

- `_calificado()` (5 líneas)
- `siguiente_pregunta()` (10 líneas)

### `bot.engines.finanzas`
_Depende de:_ `bot.engines.textos`

- `cuota_mensual()` (6 líneas)
- `evaluar()` (46 líneas) — Devuelve {'regla', 'texto', 'calculo'} o None si no hay nada que calcular.

### `bot.engines.guardas`
_Depende de:_ `bot.nlu.lexico`

- `quitar_prohibidas()` (8 líneas) — Elimina la oración que contiene una frase prohibida. Devuelve (texto, [frases encontradas]).
- `similitud()` (2 líneas)
- `sin_repetir()` (7 líneas) — Si un párrafo ya se dijo tal cual en el último mensaje, se omite (salvo que no quede nada).
- `aplicar()` (3 líneas)

### `bot.engines.multimedia`

- `elegir()` (13 líneas)

### `bot.engines.objeciones`
_Depende de:_ `bot.engines.textos`

- `responder()` (16 líneas)

### `bot.engines.pipeline`
_Depende de:_ `bot.engines`, `bot.engines.textos`

- `_item()` (3 líneas)
- `run()` (108 líneas ⚠️)

### `bot.engines.textos`

- `L()` (2 líneas)
- `dinero()` (3 líneas)
- `campo()` (3 líneas) — item['promo_bonus_es'] / item['promo_bonus_en'] con respaldo al otro idioma.
- `nombre()` (2 líneas)

### `bot.handoff`
_Depende de:_ `bot.config`, `bot.datos.idempotencia`, `bot.datos.leads`, `bot.db`, `bot.estado`, `bot.utils.texto`

- `guardar_mensaje_manual()` (29 líneas) — Guarda en el historial lo que el asesor humano escribió a mano, para que el bot lo tenga en cuenta.
- `humano_atendiendo()` (19 líneas) — True si el asesor escribió a mano hace poco (memoria o lo guardado en el lead) o pausó el chat con 'pausa 51…'.

### `bot.hub.sesion`
_Depende de:_ `bot`, `bot.config`

- `_serializador()` (4 líneas)
- `hash_password()` (2 líneas)
- `_bloqueado()` (6 líneas)
- `_fallo()` (3 líneas)
- `autenticar()` (21 líneas) — Devuelve (usuario, error). Mismo mensaje si el correo no existe o la clave es incorrecta.
- `crear_token()` (2 líneas)
- `leer_token()` (5 líneas)
- `_usuario_de_la_peticion()` (7 líneas)
- `requiere_sesion()` (17 líneas) — Decorador para rutas del CRM. rol='admin' limita a administradores del cliente.

### `bot.ia.gemini`
_Depende de:_ `bot.config`, `bot.estado`

- `extract_json_from_llm()` (14 líneas)
- `_gemini_endpoints()` (9 líneas)
- `call_gemini_api()` (51 líneas)
- `pedir_json()` (26 líneas) — Llamada corta que devuelve un dict (o None). La usa el NLU de la Capa 1: un solo modelo rápido y poco tiempo,

### `bot.ia.prompt`
_Depende de:_ `bot.config`

- `_regla_apertura()` (11 líneas) — Línea del prompt sobre la fecha desde la que se agendan visitas; vacía si no hay fecha o ya pasó.
- `build_system_prompt()` (105 líneas ⚠️)

### `bot.integraciones.calendario`
_Depende de:_ `bot.config`, `bot.estado`, `bot.utils.fechas`

- `get_calendar_service()` (3 líneas)
- `_parse_rfc3339()` (2 líneas)
- `get_busy_intervals()` (15 líneas) — Intervalos ocupados reales del calendario (freebusy respeta eventos marcados como 'Disponible').
- `primer_dia_visitas()` (7 líneas) — Fecha desde la que se agendan visitas (VISITAS_DESDE), o None si no hay restricción o ya pasó.
- `fecha_apertura_txt()` (5 líneas) — 'domingo 15 de noviembre' (para los mensajes).
- `_slot_valido_por_horario()` (17 líneas) — Valida anticipación mínima y, si estricto, día y franja de visitas sugeridas. Devuelve (ok, motivo).
- `_choca()` (3 líneas)
- `verificar_slot()` (9 líneas) — Devuelve (estado, motivo): estado = 'libre' | 'ocupado' | 'invalido' | 'sin_verificar'.
- `get_free_slots()` (50 líneas) — Horarios libres más próximos. Sin 'dia': máximo 2 por día (el 1ro libre de la mañana y el 1ro de la tarde)
- `_repartir()` (6 líneas) — De un mismo día, uno de la mañana, uno del mediodía y uno de la tarde (así el cliente elige), luego el resto.
- `get_calendar_availability_text()` (24 líneas)
- `create_calendar_event()` (24 líneas) — Crea el evento verificando antes que el horario siga libre. Devuelve (ok, detalle, event_id).
- `update_calendar_event()` (20 líneas) — Reprograma una visita ya agendada. Devuelve (ok, detalle).

### `bot.integraciones.salesforce_sync`
_Depende de:_ `bot.config`

- `configurado()` (2 líneas)
- `_assertion_jwt()` (7 líneas) — JWT firmado con la llave privada del certificado de la Connected App (usa google-auth, ya instalado).
- `_pedir_token()` (10 líneas)
- `_token()` (5 líneas)
- `_api()` (9 líneas) — Llamada autenticada a /services/data/<versión><ruta>. Renueva el token una vez si vence (401).
- `_ok()` (5 líneas)
- `soql_texto()` (3 líneas) — Escapa un valor para ponerlo entre comillas simples en SOQL.
- `consultar()` (7 líneas)
- `_guardar()` (13 líneas) — POST (nuevo) o PATCH (existente). Si la org no tiene los campos propios (__c), reintenta sin ellos.
- `buscar_lead_por_telefono()` (11 líneas)
- `upsert_lead_from_chat()` (15 líneas) — Crea o actualiza el Lead (busca por teléfono si no se conoce su Id). Devuelve el Id o None.
- `create_salesforce_event()` (16 líneas) — Event nativo vinculado al Lead y al asesor (OwnerId). Con event_id lo reprograma. Devuelve el Id o None.
- `update_event_attendance()` (16 líneas) — status = 'Attended' | 'No_Show'. Marca el asunto ([ATTENDED]/[NO-SHOW]) y, si existe, el campo propio.
- `log_chat_summary_note()` (11 líneas) — Resumen de la conversación como Task completada en la línea de tiempo del Lead.
- `fetch_active_inventory()` (11 líneas) — Propiedades / tratamientos / servicios activos leídos de Salesforce, con caché de 5 minutos.

### `bot.integraciones.tipo_cambio`
_Depende de:_ `bot.config`

- `_consultar_bcrp()` (14 líneas)
- `tipo_cambio_referencial()` (19 líneas) — S/ por US$ para dar montos aproximados en soles. Con TIPO_CAMBIO_AUTO (por defecto) usa el BCRP del día;

### `bot.leadgen`
_Depende de:_ `bot.canales.material`, `bot.canales.messenger`, `bot.canales.whatsapp`, `bot.config`, `bot.conversacion.formulario`, `bot.conversacion.recursos`, `bot.crm`, `bot.datos`, `bot.datos.leads`, `bot.db`, `bot.estado`

- `_escribio_hace_poco()` (5 líneas)
- `delayed_leadgen_whatsapp()` (43 líneas)
- `schedule_form_followup()` (16 líneas)
- `_ejecutar_si_le_toca()` (4 líneas) — El timer en memoria solo envía si la tarea sigue pendiente (no la tomó /cron ni otra instancia).
- `ejecutar_leadads_vencidos()` (7 líneas) — Para /cron: saludos de Lead Ads cuyo timer se perdió en un reinicio.

### `bot.nlp.dias`
_Depende de:_ `bot.nlp.patrones`, `bot.utils.texto`

- `_dia()` (2 líneas)
- `_negado()` (5 líneas) — 'no puedo entre semana' / 'entre semana no' / 'entre semana trabajo' / 'menos el lunes'.
- `_dia_negado()` (4 líneas) — Negación pegada al día: 'no puedo el lunes', 'menos el lunes', 'el lunes no', 'los sábados trabajo'.
- `preferencia_dias()` (27 líneas) — Devuelve (dias_permitidos: set | None, dias_negados: set). None = no dijo nada de días.
- `describir_dias()` (10 líneas) — {5, 6} -> 'el fin de semana'; {1, 3} -> 'el martes o el jueves'.

### `bot.nlp.financiamiento`
_Depende de:_ `bot.config`, `bot.nlp.patrones`, `bot.utils.texto`

- `detectar_financiamiento()` (32 líneas) — Lee por cláusulas para entender cosas como 'no tengo crédito aprobado pero sí tengo inicial'.
- `estado_financiero()` (16 líneas) — True = calificado (contado / inicial / crédito aprobado), False = sin inicial ni crédito, None = no sabemos.
- `resumen_financiero()` (18 líneas)
- `pregunta_por_financiamiento()` (3 líneas) — True si alguna pregunta (¿...?) del texto le consulta al cliente por su inicial / crédito / contado.
- `quitar_preguntas_financiamiento()` (4 líneas)
- `inferir_estado_de_historial()` (28 líneas) — Reconstruye lo que el cliente YA dijo sobre cómo pagará (contado / crédito / inicial) leyendo todo el historial,
- `cuota_referencial()` (5 líneas)

### `bot.nlp.formulario`
_Depende de:_ `bot.utils.telefono`

- `parse_lead_form_text()` (23 líneas)

### `bot.nlp.numeros`

- `numero_en_palabras()` (22 líneas) — Primer número escrito en letras dentro del texto (ya limpio, sin tildes). None si no hay ninguno de 1,000 o más.

### `bot.nlp.parser_fechas`
_Depende de:_ `bot.config`, `bot.nlp.patrones`, `bot.utils.texto`

- `parse_fecha_hora_es()` (99 líneas ⚠️) — Entiende 'el martes a las 3 pm', 'mañana 10am', 'sábado por la tarde', '28 de octubre 15:00', 'hoy a las 4 y media'.

### `bot.nlp.restricciones`
_Depende de:_ `bot.utils.texto`

- `_a_24h()` (11 líneas)
- `detectar_restriccion_horaria()` (24 líneas) — Devuelve {'tipo', 'desde', 'hasta', 'hora_txt', 'hora_raw'} (horas 0-23; desde/hasta/hora_raw pueden ser None) o None.
- `cumple_restriccion()` (11 líneas) — True si el horario dt respeta la restricción. La restricción de 'trabajo' no aplica sábados ni domingos.

### `bot.nlu.lexico`

- `sin_tildes()` (2 líneas)
- `_fmt()` (2 líneas)
- `detectar_idioma()` (14 líneas)
- `extraer_presupuesto()` (20 líneas)
- `extraer_hora()` (19 líneas)
- `fecha_relativa()` (7 líneas)
- `expandir()` (21 líneas)
- `_item_mencionado()` (6 líneas)
- `normalizar()` (64 líneas ⚠️) — Devuelve un dict con la forma de NormalizedTurn (ver bot/nlu_normalizer.py).

### `bot.nlu_normalizer`
_Depende de:_ `bot.config`, `bot.nlu`

- `_catalogo_txt()` (2 líneas)

### `bot.playbooks`
_Depende de:_ `bot`, `bot.config`

- `de_archivo()` (3 líneas) — Lee un playbook de la carpeta playbooks/ (para pruebas y demos).
- `_de_bd()` (10 líneas)
- `actual()` (14 líneas) — Playbook vigente del tenant (dict; vacío si no hay ninguno).
- `valor()` (8 líneas) — valor('protocolo_post_visita.enable_72h_arras_bonus', True) -> lo que diga el playbook, o el defecto.
- `interruptor()` (3 líneas) — Compromisos comerciales que se encienden o apagan sin tocar código (sección 'interruptores').
- `limpiar_cache()` (2 líneas)

### `bot.rutas.catalogo`
_Depende de:_ `bot.catalogo.sincronizar`, `bot.config`

- `sincronizar_catalogo()` (5 líneas)

### `bot.rutas.cron`
_Depende de:_ `bot.atencion`, `bot.config`, `bot.datos`, `bot.leadgen`, `bot.seguimiento.motor`

- `procesar_pendientes()` (16 líneas) — Mensajes agrupados y saludos de Lead Ads que quedaron en las colas persistentes porque el contenedor se reinició.
- `cron_seguimiento()` (13 líneas)

### `bot.rutas.diagnostico`
_Depende de:_ `bot.canales.whatsapp`, `bot.config`, `bot.datos.recursos`, `bot.estado`, `bot.utils.telefono`

- `diagnostico_media()` (43 líneas) — Prueba paso a paso el envío de la ficha y los renders. Uso en el navegador:
- `diagnostico_material()` (7 líneas) — Muestra qué fotos, renders, videos y fichas encontró el bot en el bucket. Uso en el navegador:

### `bot.rutas.hub_api`
_Depende de:_ `bot`, `bot.agente`, `bot.asesor`, `bot.canales`, `bot.canales.whatsapp`, `bot.config`, `bot.crm`, `bot.datos.leads`, `bot.db`, `bot.handoff`, `bot.hub.sesion`

- `_cors()` (8 líneas)
- `_preflight()` (3 líneas)
- `web()` (8 líneas)
- `estado()` (8 líneas)
- `ficha_kanban()` (25 líneas)
- `leads()` (8 líneas)
- `_lead_o_404()` (3 líneas)
- `mensajes()` (14 líneas)
- `comando()` (22 líneas)
- `chat()` (25 líneas)

### `bot.rutas.hub_auth`
_Depende de:_ `bot`, `bot.config`, `bot.hub`

- `login()` (16 líneas)
- `logout()` (5 líneas)
- `me()` (5 líneas)

### `bot.rutas.hub_catalogo`
_Depende de:_ `bot`, `bot.catalogo.sincronizar`, `bot.config`, `bot.db`, `bot.hub.sesion`

- `_error()` (2 líneas)
- `validar()` (54 líneas) — Devuelve (fila_limpia, error). Solo pasan campos conocidos; nunca tenant_id/id del cliente.
- `_item()` (5 líneas)
- `listar()` (10 líneas)
- `crear()` (10 líneas)
- `editar()` (14 líneas)
- `borrar()` (10 líneas)
- `_ruta_en_bucket()` (3 líneas)
- `_borrar_archivos()` (7 líneas)
- `subir_media()` (29 líneas)
- `_firma_valida()` (13 líneas) — Revisa los primeros bytes: evita subir un HTML/ejecutable con extensión de imagen al bucket público.
- `borrar_media()` (14 líneas)
- `sincronizar_crm()` (6 líneas)

### `bot.rutas.hub_config`
_Depende de:_ `bot`, `bot.crm_adapters`, `bot.db`, `bot.hub.sesion`, `bot.seguimiento`

- `_vista()` (13 líneas)
- `ver()` (4 líneas)
- `validar()` (44 líneas) — (cambios_tenant, cambios_playbook, error)
- `_poner()` (8 líneas)
- `guardar()` (18 líneas)

### `bot.rutas.salesforce`
_Depende de:_ `bot.asesor`, `bot.config`, `bot.handoff`

- `desde_salesforce()` (18 líneas)

### `bot.rutas.salud`

- `home()` (3 líneas)

### `bot.rutas.twilio`
_Depende de:_ `bot.atencion`, `bot.canales`, `bot.config`, `bot.datos.idempotencia`

- `desde_twilio()` (13 líneas)

### `bot.rutas.webhook`
_Depende de:_ `bot.atencion`, `bot.canales.messenger`, `bot.canales.whatsapp`, `bot.config`, `bot.conversacion.orquestador`, `bot.datos.idempotencia`, `bot.datos.leads`, `bot.handoff`, `bot.leadgen`, `bot.nlp.formulario`, `bot.utils.firma_meta`, `bot.utils.telefono`

- `verify()` (5 líneas)
- `exigir_firma_de_meta()` (17 líneas) — Rechaza los POST al webhook que no estén firmados por Meta (si META_APP_SECRET está configurado).
- `webhook()` (174 líneas ⚠️)

### `bot.seguimiento.envio`
_Depende de:_ `bot.canales.alertas`, `bot.canales.material`, `bot.canales.twilio_adapter`, `bot.canales.whatsapp`, `bot.config`, `bot.datos.leads`, `bot.db`, `bot.utils.fechas`, `bot.utils.telefono`

- `_guardar_historial()` (6 líneas)
- `enviar_seguimiento()` (35 líneas) — Dentro de 24 h: mensaje libre (gratis). Fuera: plantilla aprobada si existe. Si no, le pasa el texto al asesor para que lo envíe.

### `bot.seguimiento.mensajes`
_Depende de:_ `bot.config`, `bot.conversacion.precio`, `bot.conversacion.presupuesto`, `bot.conversacion.recursos`, `bot.conversacion.slots`, `bot.integraciones.calendario`, `bot.nlp.financiamiento`, `bot.utils.fechas`, `bot.utils.texto`

- `_recordar_horarios()` (18 líneas) — '¿Lograste revisar si alguno de los horarios del viernes por la tarde te acomoda?' (lo que escribiría el asesor).
- `_texto_rescate_24h()` (63 líneas ⚠️) — El mensaje de rescate según en qué quedó la conversación (dejó en visto).
- `_toque_post_visita()` (37 líneas)

### `bot.seguimiento.motor`
_Depende de:_ `bot`, `bot.canales.alertas`, `bot.canales.material`, `bot.canales.whatsapp`, `bot.config`, `bot.conversacion.recursos`, `bot.conversacion.slots`, `bot.crm`, `bot.datos.leads`, `bot.db`, `bot.nlp.financiamiento`, `bot.nlp.patrones`, `bot.seguimiento`, `bot.seguimiento.envio`, `bot.seguimiento.mensajes`, `bot.utils.fechas`, `bot.utils.telefono`, `bot.utils.texto`

- `_procesar_lead_seguimiento()` (121 líneas ⚠️) — Decide y ejecuta como máximo UNA acción de seguimiento para este cliente. Devuelve una descripción o None.
- `ejecutar_seguimientos()` (27 líneas)

### `bot.seguimiento.motor_catalogo`
_Depende de:_ `bot`, `bot.agente`, `bot.canales.alertas`, `bot.canales.whatsapp`, `bot.config`, `bot.crm`, `bot.datos.leads`, `bot.engines`, `bot.engines.textos`, `bot.nlp.patrones`, `bot.seguimiento`, `bot.seguimiento.envio`, `bot.utils.fechas`, `bot.utils.texto`

- `en_silencio()` (5 líneas) — True dentro de la ventana de silencio del tenant (p. ej. 20:30 – 08:30, cruza la medianoche).
- `_horarios()` (6 líneas) — 3 horarios reales libres; quedan guardados como offered_slots para que el cliente responda 1, 2 o 3.
- `_variables()` (17 líneas)
- `_enviar_media()` (10 líneas)
- `_post_visita()` (34 líneas)
- `_rescate()` (39 líneas)
- `procesar()` (62 líneas ⚠️) — Como motor._procesar_lead_seguimiento: como máximo UNA acción por cliente en cada pasada del cron.

### `bot.seguimiento.plantillas`
_Depende de:_ `bot`, `bot.seguimiento`

- `activo()` (3 líneas) — Toque encendido? (playbook interruptores.seguimiento_post_dia5 = false lo apaga).
- `texto_crudo()` (6 líneas) — La plantilla sin rellenar que se usaría hoy para este tenant (lo que muestra y edita /app).
- `texto()` (4 líneas)

### `bot.seguimiento.plantillas_industria`

- `familia()` (2 líneas)
- `buscar()` (3 líneas)

### `bot.tenant`
_Depende de:_ `bot`, `bot.config`

- `tid()` (2 líneas)
- `usar()` (7 líneas)
- `fijar()` (3 líneas) — Para la web: fija el tenant de esta petición (Flask corre cada petición en su propio contexto).
- `_por_defecto()` (7 líneas)
- `actual()` (15 líneas)
- `modo_catalogo()` (2 líneas)
- `limpiar_cache()` (5 líneas)

### `bot.utils.fechas`
_Depende de:_ `bot.config`

- `format_hora_es()` (4 líneas)
- `a_las()` (2 líneas)
- `format_fecha_es()` (9 líneas)
- `_ahora()` (2 líneas)
- `_ts()` (8 líneas)
- `_en_horario_prudente()` (3 líneas)
- `_proxima_hora_prudente()` (8 líneas) — Si dt cae en horario de silencio, lo mueve al inicio del horario prudente siguiente.

### `bot.utils.firma_meta`

- `firma_valida()` (10 líneas) — True si `cabecera` ("sha256=<hex>") es el HMAC-SHA256 de `cuerpo` (bytes) con alguno de los `secretos`.

### `bot.utils.telefono`

- `es_bsuid()` (2 líneas)
- `id_legado()` (3 líneas) — Hasta nov-2026 el bot guardaba el BSUID sin el prefijo ("1000000000000001"). Sirve para recuperar el historial.
- `destino_wa()` (5 líneas) — Campo de destinatario para la Cloud API: {"to": teléfono} o {"recipient": BSUID}.
- `normalize_pe_phone()` (15 líneas)
- `extract_phone_from_text()` (7 líneas)

### `bot.utils.texto`

- `sin_tildes()` (3 líneas)
- `limpiar_texto()` (4 líneas)
- `_usd()` (2 líneas)
- `_orden_nombre()` (5 líneas)
- `nombre_valido()` (7 líneas) — El nombre de perfil de WhatsApp puede ser '.', '😊' o '~Brayan': se limpian símbolos y solo se usa si tiene al menos 2 letras.
- `_primer_nombre()` (3 líneas)

## 4. Tablas de Supabase usadas

- **`catalog_items`** ← `bot/catalogo/sincronizar.py`, `bot/rutas/hub_catalogo.py`
- **`catalog_media`** ← `bot/catalogo/sincronizar.py`, `bot/rutas/hub_catalogo.py`
- **`hub_users`** ← `bot/hub/sesion.py`
- **`leads`** ← `bot/datos/leads.py`
- **`mensajes`** ← `bot/atencion.py`, `bot/conversacion/orquestador.py`, `bot/leadgen.py`
- **`processed_webhooks`** ← `bot/datos/idempotencia.py`
- **`recursos_media`** ← `bot/datos/recursos.py`
- **`tenant_playbooks`** ← `bot/playbooks.py`, `bot/rutas/hub_config.py`
- **`tenants`** ← `bot/rutas/hub_config.py`, `bot/tenant.py`

## 5. Estado del lead (`leads.interes`, JSON)

Claves que el código lee o escribe en el diccionario de estado del lead (variables `meta*`):

`_alerta_asesor`, `_con_historial`, `_momento_fotos`, `acompanantes`, `asesor_solicitado`, `asistencia_confirmada`, `aviso_apertura`, `aviso_cambio_cita`, `bienvenida_ts`, `canal_origen`, `cita_agendada`, `crm_asistencia`, `crm_cita_fecha`, `crm_cita_id`, `crm_firma`, `crm_id`, `dia_contexto`, `en_presupuesto`, `estilo_cocina`, `etapa`, `evento_id`, `fecha_cita`, `fin_credito_aprobado`, `fin_inicial`, `fin_modalidad`, `forma_pago`, `fotos_enviadas`, `gancho_m2_n`, `hora_pendiente`, `interested_catalog_item_id`, `material_enviado`, `monto_pendiente`, `movilidad`, `n_cierres`, `no_interesado`, `objecion_precio_n`, `offered_slots`, `payment_method`, `post_visita`, `preferred_language`, `pregunta_fin_pendiente`, `pregunta_owner_visita`, `pregunta_owner_visita_2`, `presupuesto_tope`, `price_objection_count`, `producto_crm_id`, `producto_nombre`, `rechazos_horario`, `recordatorio_para`, `recordo_horarios`, `rescate_24h_para`, `rescate_contado`, `rescate_no_asistio`, `restriccion_horaria`, `saludo_visita`, `seguimiento_pausado`, `sent_media_ids`, `sf_lead_id`, `slot_propuesto`, `slots_ofrecidos`, `stage`, `stated_budget`, `ts_cita_creada`, `ts_postergo`, `ts_ultimo_bot`, `ts_ultimo_cliente`, `ts_ultimo_manual`, `ts_visita_confirmada`, `ultimo_material`, `ultimo_texto_cliente`, `veces_pregunta_fin`, `vendido`, `ventana_noche_desde`, `videos_enviados`, `visita_estado`, `vive_lejos`, `wsp_iniciado`, `ya_explicado`

## 6. Contrato de respuesta de los motores (`parsed`)

Claves del diccionario que devuelven los motores de respuesta / Gemini:

`_alerta_fotos`, `_galeria`, `_msg_cliente`, `_no_responder`, `_nombre`, `_pide_video`, `_sin_cierre`, `_sin_control_repeticion`, `_unidad`, `agendar_visita_iso`, `enviar_ficha_tecnica`, `enviar_fotos_casa`, `enviar_renders_cocina`, `estilo_render_preferido`, `ignorar_comentario`, `private_reply`, `recursos`, `reply_text`

## 7. Variables de entorno

| Variable | Valor por defecto en código | Archivo |
|---|---|---|
| `AGRUPAR_MENSAJES_SEG` | 6 | `bot/config.py` |
| `AGRUPAR_MENSAJES_SEG_SMS` | 4 | `bot/config.py` |
| `ALERTA_TEMPLATE` | — | `bot/config.py` |
| `AREA_CONSTRUIDA_M2` | 200 | `bot/config.py` |
| `ASESOR_HIPOTECARIO_WA` | — | `bot/config.py` |
| `ASESOR_NOMBRE` | — | `bot/tenant.py` |
| `BOT_NOMBRE` | Ava | `bot/tenant.py` |
| `CALENDAR_ID` | calendar@example.com | `bot/config.py` |
| `CARPETA_MATERIAL` | santa-teresa | `bot/config.py` |
| `COLAS_PERSISTENTES` | true | `bot/config.py` |
| `CRM_SYNC_ACTIVO` | — | `bot/config.py` |
| `CRM_TIPO` | peruptd_native | `bot/tenant.py` |
| `CRON_KEY` | — | `bot/config.py` |
| `DIAS_ATENCION` | 0,1,2,3,4,5,6 | `bot/config.py` |
| `DURACION_VISITA_MIN` | 60 | `bot/config.py` |
| `ENTREGA_TXT` | entrega inmediata con título en SUNARP (2 pisos terminados y… | `bot/config.py` |
| `ESTADO_3ER_PISO_TXT` | El 3er piso se entrega *en casco*: está construido y techado… | `bot/config.py` |
| `ESTADO_CASAS_CORTO` | los 2 primeros pisos con acabados y el 3er piso en casco (co… | `bot/config.py` |
| `EXIGIR_FILTRO_FINANCIERO` | true | `bot/config.py` |
| `FB_PAGE_ID` | 100000000000000 | `bot/config.py` |
| `FIRMA_META_EXIGIR` | false | `bot/config.py` |
| `GASTOS_TEXTO` | Los gastos de notaría, inscripción en SUNARP e impuestos que… | `bot/config.py` |
| `GEMINI_API_KEY` | — | `bot/config.py` |
| `GEMINI_ENDPOINT` | auto | `bot/ia/gemini.py` |
| `GEMINI_MODELS` | gemini-3.8-flash,gemini-3.6-flash,gemini-3.5-flash-lite | `bot/config.py` |
| `GEMINI_PRESUPUESTO_SEG` | 15 | `bot/config.py` |
| `GEMINI_TIMEOUT_MODELO_SEG` | 8 | `bot/config.py` |
| `GRAPH_API_VERSION` | v21.0 | `bot/config.py` |
| `HORARIO_NOCHE_HASTA_TXT` | hasta las 8 o 9 p. m. | `bot/config.py` |
| `HORARIO_PRUDENTE_DESDE` | 08:30 | `bot/config.py` |
| `HORARIO_PRUDENTE_HASTA` | 20:30 | `bot/config.py` |
| `HORA_FIN_VISITAS` | 18 | `bot/config.py` |
| `HORA_INICIO_NOCHE` | 18 | `bot/config.py` |
| `HORA_INICIO_VISITAS` | 9 | `bot/config.py` |
| `HUB_API_KEY` | — | `bot/config.py` |
| `HUB_COOKIE_SEGURA` | true | `bot/config.py` |
| `HUB_CORS_ORIGINS` | — | `bot/config.py` |
| `HUB_SESION_HORAS` | 12 | `bot/config.py` |
| `HUB_SESSION_SECRET` | — | `bot/config.py` |
| `IG_ACCOUNT_ID` | — | `bot/config.py` |
| `LEADAD_ESPERA_SEG` | 90 | `bot/config.py` |
| `MAPS_URL` | https://maps.app.goo.gl/dQp7Sj5MFXGJxzMq8 | `bot/config.py` |
| `MAX_SUBIDA_MB` | 25 | `bot/config.py` |
| `META_ACCESS_TOKEN` | — | `bot/config.py` |
| `META_APP_SECRET` | — | `bot/config.py` |
| `MIN_ANTICIPACION_HORAS` | 2 | `bot/config.py` |
| `MOVILIDAD_DESDE` | Chiclayo | `bot/config.py` |
| `MULTI_TENANT` | false | `bot/config.py` |
| `NLU_LLM_ACTIVO` | true | `bot/config.py` |
| `NLU_PRESUPUESTO_SEG` | 2.0 | `bot/config.py` |
| `NOMBRES_SIEMPRE_RENDER` | — | `bot/config.py` |
| `OFRECE_MOVILIDAD` | false | `bot/config.py` |
| `OWNER_WA` | 51900000000 | `bot/config.py` |
| `PAUSA_BOT_TRAS_HUMANO_MIN` | 120 | `bot/config.py` |
| `PIPELINE_MODE` | sague_legacy | `bot/tenant.py` |
| `PLAYBOOK_ARCHIVO` | playbook_sague_realestate.json | `bot/config.py` |
| `PLAZO_REFERENCIAL_ANIOS` | 25 | `bot/config.py` |
| `PORT` | 8080 | `main.py` |
| `PRECIO_CONTADO_USD` | 130000 | `bot/config.py` |
| `PRECIO_LISTA_USD` | 135000 | `bot/config.py` |
| `PRECIO_M2_DEPA_MAX` | 1150 | `bot/config.py` |
| `PRECIO_M2_DEPA_MIN` | 950 | `bot/config.py` |
| `PRECIO_REF_CON_BONO_USD` | 128000 | `bot/config.py` |
| `PROCESAR_EN_SEGUNDO_PLANO` | false | `bot/config.py` |
| `PROPIETARIO_TXT` | el Ing. Henry Guevara, propietario de la constructora | `bot/config.py` |
| `RESTRINGIR_HORARIO_PROPUESTO` | false | `bot/config.py` |
| `SALESFORCE_ACTIVO` | false | `bot/config.py` |
| `SEGUIMIENTO_ACTIVO` | true | `bot/config.py` |
| `SEGUIMIENTO_HORAS_MIN` | 4 | `bot/config.py` |
| `SEPARACION_TEXTO` | un monto de separación que se descuenta del precio final (el… | `bot/config.py` |
| `SF_API_VERSION` | v62.0 | `bot/config.py` |
| `SF_CLIENT_ID` | — | `bot/config.py` |
| `SF_CLIENT_SECRET` | — | `bot/config.py` |
| `SF_JWT_AUDIENCE` | https://login.salesforce.com | `bot/config.py` |
| `SF_JWT_LLAVE_PRIVADA` | — | `bot/config.py` |
| `SF_JWT_USUARIO` | — | `bot/config.py` |
| `SF_LOGIN_URL` | — | `bot/config.py` |
| `SF_OWNER_ID` | — | `bot/config.py` |
| `SF_WEBHOOK_SECRETO` | — | `bot/config.py` |
| `SUPABASE_KEY` | — | `bot/config.py` |
| `SUPABASE_URL` | https://example-project.supabase.co | `bot/config.py` |
| `TASA_REFERENCIAL_TEA` | 9 | `bot/config.py` |
| `TENANT_ID` | sague | `bot/config.py` |
| `TENANT_NOMBRE` | SAGUE Constructora | `bot/tenant.py` |
| `TIPO_CAMBIO_AUTO` | true | `bot/config.py` |
| `TIPO_CAMBIO_REFERENCIAL` | 3.45 | `bot/config.py` |
| `TIPO_CAMBIO_TEXTO` | el tipo de cambio del día de la firma en notaría (o el que a… | `bot/config.py` |
| `TPL_BANCO_LEGAL` | — | `bot/config.py` |
| `TPL_CIERRE` | — | `bot/config.py` |
| `TPL_NO_ASISTIO` | — | `bot/config.py` |
| `TPL_POST_VISITA` | — | `bot/config.py` |
| `TPL_PROPUESTA` | — | `bot/config.py` |
| `TPL_RECORDATORIO` | — | `bot/config.py` |
| `TPL_SEGUNDA_VISITA` | — | `bot/config.py` |
| `TWILIO_ACCOUNT_SID` | — | `bot/config.py` |
| `TWILIO_AUTH_TOKEN` | — | `bot/config.py` |
| `TWILIO_EXIGIR_FIRMA` | true | `bot/config.py` |
| `TWILIO_SMS_FROM` | — | `bot/config.py` |
| `TWILIO_URL_PUBLICA` | — | `bot/config.py` |
| `TWILIO_WA_FROM` | — | `bot/config.py` |
| `URL_FOTOS_CASA` | — | `bot/config.py` |
| `URL_FOTO_BANO` | — | `bot/config.py` |
| `URL_FOTO_COCHERA` | — | `bot/config.py` |
| `URL_FOTO_COCINA` | — | `bot/config.py` |
| `URL_FOTO_DORMITORIO` | — | `bot/config.py` |
| `URL_FOTO_FACHADA` | — | `bot/config.py` |
| `URL_FOTO_JARDIN` | — | `bot/config.py` |
| `URL_FOTO_SALA` | — | `bot/config.py` |
| `URL_FOTO_TERRAZA` | — | `bot/config.py` |
| `URL_VIDEO_RECORRIDO` | — | `bot/config.py` |
| `VERIFY_TOKEN` | (secreto) | `bot/config.py` |
| `VISITAS_DESDE` | — | `bot/config.py` |
| `WA_ACCESS_TOKEN` | — | `bot/config.py` |
| `WA_PHONE_ID` | 100000000000000 | `bot/config.py` |

## 8. Deuda técnica detectada automáticamente

- Archivo `bot/conversacion/agenda.py` tiene 464 líneas (> 300). Dividir por responsabilidad.
- Función `bot.conversacion.agenda.motor_agenda()` tiene 439 líneas (> 60).
- Función `bot.conversacion.faq.responder_faq()` tiene 195 líneas (> 60).
- Función `bot.conversacion.material.responder_material()` tiene 84 líneas (> 60).
- Archivo `bot/conversacion/orquestador.py` tiene 434 líneas (> 300). Dividir por responsabilidad.
- Función `bot.conversacion.orquestador.process_conversation()` tiene 274 líneas (> 60).
- Función `bot.conversacion.orquestador._finalizar_conversacion()` tiene 101 líneas (> 60).
- Función `bot.conversacion.respaldo.build_Contextual_fallback()` tiene 205 líneas (> 60).
- Función `bot.engines.pipeline.run()` tiene 108 líneas (> 60).
- Función `bot.ia.prompt.build_system_prompt()` tiene 105 líneas (> 60).
- Función `bot.nlp.parser_fechas.parse_fecha_hora_es()` tiene 99 líneas (> 60).
- Función `bot.nlu.lexico.normalizar()` tiene 64 líneas (> 60).
- Función `bot.rutas.webhook.webhook()` tiene 174 líneas (> 60).
- Función `bot.seguimiento.mensajes._texto_rescate_24h()` tiene 63 líneas (> 60).
- Función `bot.seguimiento.motor._procesar_lead_seguimiento()` tiene 121 líneas (> 60).
- Función `bot.seguimiento.motor_catalogo.procesar()` tiene 62 líneas (> 60).
