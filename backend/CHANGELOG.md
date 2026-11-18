# Changelog

Formato: [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/). Versiones: `AAAA.MM.N`.

## PeruPTD Agent 0.3.0 — 2026-11-17 · PeruPTD Native CRM
- CRM web en `/app` con login (`hub_users`, migración 005; `bot/hub/sesion.py`: hash scrypt, cookie HttpOnly firmada,
  límite de intentos, CSRF) y aislamiento por `tenant_id` (`MULTI_TENANT`, `tenant.usar`, `datos.leads.tabla`).
  `/app?demo=1` = demo intacta para videos.
- Rutas: `hub_auth` (login/logout/me), `hub_api` (Kanban de 5 columnas, mensajes con motor, comandos + mensaje manual con
  pausa de 2 h), `hub_catalogo` (CRUD, subida de archivos por rol al bucket `catalogo`, sincronizar), `hub_config`
  (`GET/PUT /api/hub/playbook`: dueño, horarios, silencio, frases prohibidas, textos de seguimiento, mapeo CRM).
- Seguimiento: plantillas por industria ES/EN (`plantillas_industria.py`: inmobiliaria, salud/clínicas, B2B).
- Catálogo: `qualification_mode`, `filter_questions`, `conditions_es/en`; roles `PROOF_RESULTS` y `LOCATION_MAP`.
- `crm_adapters/mapeo.py` + `tenants.crm_field_mapping_json`: objetos y campos del CRM externo configurables.
- `scripts/crear_usuario.py`. Pruebas: `test_crm_web.py` (Supabase en memoria), mapeo y plantillas → 181.

## PeruPTD Agent 0.2.0 — 2026-11-17
- Seguimiento multi-industria (modo `catalogo`): `bot/seguimiento/motor_catalogo.py` + `plantillas.py`; textos ES/EN en
  `playbook.seguimiento`, interruptores `seguimiento_<clave>`, adjuntos del catálogo. SAGUE (`sague_legacy`) sin cambios.
- API del AI Sales Hub (`bot/rutas/hub_api.py`, `HUB_API_KEY`, `HUB_CORS_ORIGINS`) y `GET /hub`; bandeja simulada `hub:` para chatear
  con el agente real sin enviar nada por los canales.
- Hub: modo API en vivo (`hub/src/live.js`) con vuelta automática a los datos de demostración.

## PeruPTD Agent 0.1.0 — 2026-11-17 (proyecto nuevo basado en SAGUE)
- Capa 1: `bot/nlu_normalizer.py` (SemanticNormalizer, NormalizedTurn con pydantic) + léxico ES/EN compartido con el AI Sales Hub.
- Capa 2: `bot/engines/` (catálogo, presupuesto 8/20 % + anualidad, objeciones 1-2-3, agenda con "salgo del trabajo", multimedia máx. 2 sin repetir).
- Capa 3: `bot/engines/guardas.py` (frases prohibidas del playbook, anti-repetición 80 %) y `bot/agente.py` (turno completo).
- Multi-tenant: migraciones 002 (colas persistentes), 003 (tenants, catalog_items, catalog_media, ficha viva en leads), 004 (demos).
- Multi-CRM: `bot/crm_adapters/` (Native, Salesforce, HubSpot, Pipedrive, Zoho), `bot/crm.py` genérico, `POST /catalogo/sincronizar`.
- Twilio SMS/WhatsApp: `bot/canales/twilio_adapter.py`, `POST /webhook/twilio`; el SMS no tiene ventana de 24 h.
- Salesforce -> bot: `POST /webhook/salesforce` (vino / no vino / pausa / vendido / mensaje manual).
- Playbooks por cliente (`playbooks/`) y `tests/test_guardrails.py`.

## [Sin publicar]

### Cambiado (17 nov)
- Pasamanos y baranda terminados y primera visita realizada (15-nov): `VISITAS_DESDE` queda vacío por defecto y la IA solo menciona una fecha de apertura si es futura; se quitó "se están terminando pasamanos y barandas".
- "La casa ya está terminada" → "ya está construida" (financiamiento y proceso al contado).
- El resumen general ya no dice que las casas incluyen los reposteros: es solo para la 1ra unidad (Bono de Lanzamiento).

### Seguridad (11 nov)
- El webhook verifica la firma de Meta (`X-Hub-Signature-256`) con `META_APP_SECRET` (Secret Manager). `FIRMA_META_EXIGIR=false` = solo observa; `true` = rechaza avisos falsos. Sin la variable no cambia nada.
- `/cron` acepta la clave tanto en `?key=` como en la cabecera `X-Cron-Key`; `CRON_KEY` pasa a Secret Manager (`scripts/configurar_secretos.sh`).
- Versión de la Graph API centralizada (`GRAPH_API_VERSION`), lista para migrar antes del 21-ene-2027.

### Infraestructura (11 nov)
- Despliegue automático desde GitHub: cada push a `main` corre las pruebas y publica en Cloud Run (GitHub Actions + Workload Identity Federation, sin claves). Flujos manuales `registros` (leer logs) y `revertir` (volver a una revisión anterior).

### Cambiado (8 nov, noche — estado real de las casas)
- **Las casas NO están 100 % terminadas**: el 1er y 2do piso tienen acabados; el 3er piso se entrega **en casco** (construido y techado, con terraza, estructura de la jardinera y terma, sin tarrajeo, cerámica ni baranda). Se corrigieron ~25 mensajes (información, distribución, entrega, planos, objeciones, formulario, respaldo) y las instrucciones de Gemini, que además tiene prohibido inventar detalles de acabados o seguridad. Textos centralizados en `config.py` (`ESTADO_CASAS_CORTO`, `ESTADO_3ER_PISO_TXT`, `ENTREGA_TXT`).
- La terraza ya no se envía sola en mensajes automáticos; su render dice "así podría quedar una vez terminada (hoy en casco)".
- **Visitas desde el 15 de noviembre** (`VISITAS_DESDE=2026-11-15`): se están terminando pasamanos y la baranda del balcón del 2do piso. El bot no ofrece ni acepta horarios antes y lo explica una vez. Al pasar la fecha, la restricción se desactiva sola.
- Prueba que impide volver a escribir "100 % terminadas", "lista para mudarte", "gran terraza" o "gemelas".

### Corregido (8 nov — el bot "no respondía" y respuestas incoherentes)
- **Clientes con "usuario" de WhatsApp (BSUID, p. ej. `PE.1000000000000001`)**: el bot les quitaba el prefijo y respondía como si fuera un teléfono, así que WhatsApp descartaba TODAS las respuestas ("Message undeliverable", código 131026). Afectó a Linn, Eloisa, Elizabeth y otros desde el 25 de oct. Ahora se responde con `recipient` = BSUID y su historial anterior se migra solo al ID nuevo (`migrar_id_legado`).
- **Gemini caído**: los modelos 2.5/2.0/1.5 fueron retirados por Google y Vertex no está habilitado. Modelos nuevos por defecto (`gemini-3.8-flash`, `gemini-3.6-flash`, `gemini-3.5-flash-lite`) y máximo 8 s por modelo (`GEMINI_TIMEOUT_MODELO_SEG`) para que un modelo saturado no consuma todo el tiempo. En Cloud Run: `GEMINI_ENDPOINT=ai_studio`, `PYTHONUNBUFFERED=1` (logs en tiempo real).
- "Si me indica qué día" ya no se entiende como "sí tengo inicial" (el bot le inventó la inicial a Linn).
- "En la mañana está bien" con un día ya elegido ofrece los horarios de la mañana de ese día (antes: "Perdona si no me expliqué bien").
- "Y casa de 1er piso" = quiere una casa de un piso (antes describía el 1er piso). "Es que muy grande": responde a la objeción de tamaño.
- "¿Eso es al contado?": confirma que US$130,000 es el precio al contado. "Mensual, ¿cuánto sería?": da la cuota mensual (antes el precio total).
- Nombres de perfil en minúsculas ("gladis", "cielo") se escriben con mayúscula.
- Si el cliente pregunta "¿dónde la veo?" y la respuesta no trae la ubicación, se agrega el mapa.
- Pruebas: `tests/simulador.py` (conversaciones completas con base de datos en memoria) y `tests/test_chats_08nov.py`.

### Causas externas encontradas (8 nov)
- Messenger, Instagram y comentarios dejaron de responderse desde el ~29 oct por una **verificación de seguridad pendiente en la cuenta de Meta** (resuelta el 8 nov).
- No hubo formularios nuevos desde el 30 oct: revisar la campaña y la verificación de la cuenta publicitaria.
- Las alertas al asesor fallan fuera de la ventana de 24 h (código 131047): falta configurar `ALERTA_TEMPLATE`.

### Corregido (30 oct)
- Tipo de cambio automático: el bot toma el interbancario venta del BCRP (se refresca cada 6 h); si el BCRP no responde usa el último valor bueno y, si nunca respondió, `TIPO_CAMBIO_REFERENCIAL` (ahora 3.45). Los montos en soles, el "por debajo de S/ …" y el prompt de Gemini se calculan con ese valor.
- Bienvenida del formulario: manda solo las fichas de las 2 casas y el render de la cocina que eligió (ya no la sala amoblada). Por Lead Ads también usa las fichas por casa.
- Imágenes que no son lo que dice su extensión (un PNG guardado como .jpg, WEBP, HEIC): se detecta el formato real y se sube bien (o se convierte a JPG); antes WhatsApp podía rechazarlas.
- Ya no se dice "casas gemelas" en ningún mensaje (ni en las instrucciones de Gemini).

### Corregido (chats reales del 27-28 oct)
- Bienvenida del formulario duplicada (Iván, María, Brayan): el aviso de Lead Ads borraba la marca `wsp_iniciado` y a los 90 s se volvía a mandar la bienvenida. Ahora se guarda `bienvenida_ts` y no se repite en 3 días, venga por WhatsApp, por Lead Ads o por un reintento de Meta. Un mismo mensaje largo repetido en menos de 3 min tampoco se responde dos veces.
- Formulario que llega sin respuestas (solo "Completé el formulario"): ya no dice "tu diseño de cocina" ni "con tu modalidad de compra"; ofrece los 2 diseños y pregunta cuál le gusta.
- Nombre de perfil: se limpian símbolos ("~Brayanvillar") y si viene con apellidos primero ("Chonate Alcoser Jorge") se usa el nombre de pila.
- Soles: "por debajo de los S/ 490,000" (aprox. S/ 487,500 al contado), ya no "S/ 480,000". La 2da vez que pregunta en soles va directo al número.
- Montos en letras ("Cuatrocientos mil ochocientos") se entienden; entre 80 % y 92 % del precio al contado: "estamos algo por debajo" + completar con crédito.
- "¿En cuántos años es para pagar?" → lo define el banco (5 a 25 años), cuota referencial y asesor. "O sea, ¿el pago es al contado?" → al contado o con crédito de cualquier banco.
- "¿Cuántos m² es el terreno?" ya no responde "no vendemos terrenos".
- "Estoy en Jaén, cuando voy los visito": sin lista de horarios; le pide avisar un día antes y le ofrece el video.
- "¿Más tarde no podría ser?" (con pregunta): ofrece horas más tarde ese mismo día y la opción de la noche.
- Seguimiento: si quedó con horarios de un día que pidió, pregunta "¿lograste revisar los horarios del viernes por la tarde?" (sin cambiarle la lista ni preguntar por el banco). Si preguntó el precio al contado, retoma eso.
- Renders de cocina: van justo después de los planos; si el archivo fijo (`cocina_1.jpg` / `cocina_2.jpg`) falla, se manda el render de cocina del bucket con "gris/grafito" o "madera/rovere" en el nombre. El asesor solo recibe alerta cuando algo no se envió.
- Fotos vs renders según la carpeta del bucket: `casa-X/fotos` = fotos reales (la sala vacía ya no lleva el aviso de muebles), `comun/renders` = renders con muebles, `fichas` y `videos` por casa.
- Renders de cocina: el archivo por defecto apuntaba a la raíz del bucket, pero `cocina_1.jpg` (madera) y `cocina_2.jpg` (gris) están en `santa-teresa/comun/renders/`; por eso nunca llegaban. Corregido, con respaldo desde el catálogo.
- Mensajes seguidos ("Buenos días" + "¿Dónde están ubicados exactamente?"): una sola respuesta. Tras un saludo suelto o un mensaje que termina en coma, el bot espera ~15 s; si Meta manda los dos en el mismo aviso, se juntan de una. Nombres en mayúsculas ("JUAN CORONEL") se escriben "Juan".

### Despliegue
- `scripts/generar_main_unico.py` genera `dist/main.py`: todo el bot en un solo archivo para subirlo como antes (misma lógica que `bot/`, verificado con las conversaciones de prueba).

### Corregido
- Agenda: "trabajo hasta las 5 pm, ¿puede ser un fin de semana?" ya no agenda una cita a las 5 p. m.; ofrece horarios del fin de semana. Entiende "salgo a las 3", "después de las 4", "antes de las 12", "en la noche", "a la hora de mi almuerzo" y "el fin de semana a las 10" (`bot/nlp/restricciones.py`, `bot/conversacion/agenda_humana.py`).
- Agenda: después de responder "al contado" / "no tengo inicial" se mantienen los horarios que ya se le ofrecieron (antes se cambiaban por otros).

### Cambiado (chats reales del 26-27 oct)
- Precio al contado: *US$130,000* (aprox. S/ 487,500), negociable en la visita con el propietario (`PRECIO_CONTADO_USD`, `PROPIETARIO_TXT`). Aparece en el precio, la moneda, el "precio final al contado", la objeción y el seguimiento.
- Presupuesto honesto (`bot/conversacion/presupuesto.py`): si no dice moneda ("100.000") pregunta si son soles o dólares; si no alcanza, lo dice y ofrece usarlo como inicial + crédito (con cuota referencial). El seguimiento ya no promete "podemos acercarnos a $100,000".
- "¿Hay más económicas?", "¿De un solo piso no venden?": "por el momento solo tenemos estas 2 casas" + pregunta el presupuesto. "Casi medio millón": confirma el precio en soles.
- Varios mensajes seguidos del cliente se juntan y se responden una sola vez (`AGRUPAR_MENSAJES_SEG`, 6 s).
- Si el asesor escribe a mano, el bot se calla 2 horas en ese chat (`PAUSA_BOT_TRAS_HUMANO_MIN=120`, guardado en el lead). "pausa 51…" ahora también detiene las respuestas.
- "Ok" / 👍 sin nada pendiente: no responde. Saludo de alguien que ya escribió antes: saluda y pregunta en qué ayudar (sin lanzar horarios).
- A una imagen sin texto responde una vez cada 30 min (y avisa al asesor). No repite el mismo tipo de foto/render del mismo ambiente.

### Corregido ("Plan de 5?")
- Con una lista de horarios a la vista, un número suelto ("5?", "de 5", "plan de 5" por "para las 5") se entiende como hora de ese día; "la 2" sigue siendo la opción 2.
- "¿Y a las 4?" es una pregunta: responde que está libre y pide el "sí" antes de agendar o mover la cita.
- Si el bot no entiende algo en plena coordinación, pregunta por los horarios en vez de recordar la cita anterior.

### Corregido (revisión de fotos)
- La cocina en render se presenta como "así queda con los reposteros instalados" (sin el aviso de muebles).
- Leyenda de dormitorio sin "baño propio"; los renders dicen "Muebles agregados como referencia".
- Distribución corregida: 2do piso = principal con baño propio + 2 secundarias con baño compartido; 3er piso = terraza y lavandería, con opción (según plano) de ampliar una habitación con baño. Total construido: 3 habitaciones y 3 baños.

### Corregido (chat de prueba "Clara")
- "Mejor para el domingo" dicho un domingo de noche ya no ofrece el lunes: entiende el próximo domingo.
- Si ya tiene cita, habla de cambiarla ("Cambiamos tu visita del lunes 26…") y al elegir, la mueve en Calendar. Si Calendar falla, ya no crea una segunda cita: avisa al asesor.
- Un día puntual se ofrece repartido (mañana, mediodía, tarde) en vez de 9-10-11; "¿para la tarde?" se entiende sobre el día que se venía hablando.
- Si vuelve a preguntar por lo mismo, confirma en una línea en vez de repetir la lista (o caer en "no supe cómo continuar"). El saludo largo solo va la 1ra vez.

### Corregido (prueba real tras desplegar)
- El bot no encontraba el material porque exigía nombres exactos de carpetas. Ahora recorre todo el bucket y deduce casa, tipo (foto real / render / video / ficha) y ambiente de cualquier nombre; usa el nombre del archivo como leyenda cuando es más específico.
- "Mándame fotos" envía una mezcla de las 2 casas y renders amoblados, dice cuántas quedan y pregunta si quiere ver el recorrido en video (un "sí" envía un video por casa). Entiende "¿tienes más?" y "¿y de la casa 2?".

### Agregado (2da revisión)
- Entiende de muchas formas qué días puede el cliente (`bot/nlp/dias.py`). A quien trabaja le dice "entre semana te recibo saliendo del trabajo hasta las 8 o 9 p. m. y el fin de semana claro que sí" con los horarios del fin de semana del calendario.
- Más momentos con renders amoblados: 1er mensaje del formulario, planos, "¿viene amoblada?", "lo converso con mi esposo", post-visita y no asistió.
- El material se sube por carpetas al bucket (sin SQL): `docs/GUIA_SUBIR_MATERIAL.md` y verificación en `/diagnostico/material`.

### Agregado (revisión de chats reales: Henry y Eloisa)
- El bot ya no insiste: entiende "le estaré comunicando la hora / te aviso" (queda atento, sin horarios), no responde un 👍 cuando no hace falta y recuerda la lista de horarios una sola vez (`bot/conversacion/cortesia.py`).
- "La segunda opción" se entiende aunque el último mensaje no haya sido la lista; un nombre de perfil como "." ya no se usa en el saludo.
- "A eso de las 4.30" tras ofrecer un día se agenda ese día (o pregunta cuál).
- Después de agendar pregunta con quién viene y, si `OFRECE_MOVILIDAD=true`, ofrece recogerlos (`bot/conversacion/post_agenda.py`).
- Catálogo de material por casa en Supabase (`recursos_media`): videos y fichas por casa, fotos reales y renders amoblados con aclaración automática "mobiliario de referencia" (`bot/conversacion/recursos.py`, reemplaza a `fotos.py`).
- Respuesta de tipo de cambio con la redacción del asesor: S/ 3.75 referencial y "con el bono quedaría por debajo de S/ 480,000"; ya no ofrece crédito en soles a quien compra al contado.

### Agregado
- Respuesta a "¿soles o dólares?" / "¿a qué tipo de cambio?" con tipo de cambio fijo (`TIPO_CAMBIO_REFERENCIAL`) u opcional del BCRP (`TIPO_CAMBIO_AUTO`).
- Objeción "está muy caro" en 3 niveles (valor por m² + rango de inversión → visita sin compromiso → pasa al propietario), con alerta al asesor en cada nivel.
- Gancho del precio por m² en más momentos: pregunta de área, tope de presupuesto (calcula el $/m² con su monto), descuento con crédito, rescate 24 h y toque post-visita del día 10.
- Fotos etiquetadas de la casa (`URL_FOTO_FACHADA`, `URL_FOTO_SALA`, …) que se envían solas según el momento, sin repetir (hoy en `bot/conversacion/recursos.py`).
- Casos 18-20 en el prompt de Gemini (moneda, objeción de precio, restricciones de horario).

### Cambiado
- El código pasa de un único `main.py` a módulos en `bot/` (misma lógica, ver ADR-0001). El despliegue no cambia.

### Agregado
- Documentación en `docs/`, `CLAUDE.md`, generador automático de contexto, hooks de git y Claude Code, CI y pruebas de humo.
