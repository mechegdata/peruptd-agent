# CLAUDE.md — Chatbot inmobiliario

Contexto para cualquier chat o agente que trabaje en este repo. Léelo completo antes de proponer cambios.

## Qué es

Asesor comercial automático para inmobiliarias que atiende **WhatsApp Business** (y Messenger, Instagram, comentarios y formularios Lead Ads de Meta). Su objetivo es **conseguir visitas presenciales calificadas**: responde dudas, pregunta cómo comprará el cliente (contado / crédito hipotecario con inicial), ofrece horarios libres reales de Google Calendar, agenda, recuerda la cita y hace el seguimiento post-visita de 14 días.

- **Cliente actual (único, en producción):** SAGUE Constructora — 2 casas contiguas (NO gemelas, mismo estado) en Urb. Santa Teresa, Lambayeque, Perú (lista US$135.000, contado US$130.000; 200 m² construidos en 3 pisos; entrega inmediata con título SUNARP).
- **Estado real (nov-2026):** 1er y 2do piso CON acabados; 3er piso EN CASCO (construido y techado, terraza y estructura de jardinera, terma; sin tarrajeo, cerámica ni baranda). Visitas solo desde el 15-nov-2026 (`VISITAS_DESDE`). Nunca escribir "100% terminadas", "lista para mudarte" ni "gemelas" (hay una prueba que lo impide).
- **Objetivo del dueño:** convertirlo en un **producto SaaS** para otras inmobiliarias (ver `docs/PRODUCTO_SAAS.md`).
- **Idioma:** todo en español (código, comentarios, docs, mensajes al cliente). Zona horaria `America/Lima`.

## Stack

Python 3 · Flask (Blueprints) · Google Cloud Run (`sague-bot`, `us-central1`) · Supabase (tablas `leads` y `mensajes`, bucket `recursos`) · Gemini (REST, cascada de modelos) · WhatsApp Cloud API / Graph API v21.0 · Google Calendar (cuenta de servicio) · Cloud Scheduler → `/cron`.

## Mapa del código

```
main.py                    entrada (gunicorn main:app) — no poner lógica aquí
bot/app.py                 crea Flask y registra Blueprints
bot/config.py              TODAS las variables de entorno y constantes
bot/estado.py              estado en memoria (dedupe, cachés) — se pierde al reiniciar
bot/rutas/                 webhook, cron, diagnostico, salud
bot/atencion.py            atiende un mensaje de WhatsApp de punta a punta
bot/conversacion/          orquestador + motores: despedida, formulario, faq, material, info, agenda, respaldo
bot/ia/                    prompt del asesor + cliente Gemini
bot/nlp/                   regex de intención, parser de fechas en español, financiamiento, formularios
bot/integraciones/         Google Calendar
bot/canales/               WhatsApp, Messenger, alertas al asesor, envío de material
bot/datos/                 acceso a Supabase (leads)
bot/seguimiento/           recordatorios, rescate 24 h, protocolo post-visita
bot/asesor.py, handoff.py, leadgen.py
legacy/main_monolito.py    versión anterior en un solo archivo (solo referencia, no se importa)
```

El detalle (cada función, rutas, tablas, claves del estado del lead, variables y deuda) está en **`docs/CONTEXTO_AUTO.md`**, que se regenera solo. El orden de decisión de los motores y las etapas están en **`docs/FLUJO_CONVERSACION.md`**.

## Reglas para trabajar aquí

1. **El bot está en producción con clientes reales.** No cambies comportamiento sin decirlo explícitamente; si refactorizas, la respuesta debe ser idéntica.
2. **Límites:** archivo ≤ 300 líneas, función ≤ 60 líneas, un archivo = una responsabilidad. No agrandes las funciones heredadas largas (`motor_agenda`, `process_conversation`, `build_Contextual_fallback`): extrae sub-funciones al tocarlas. Ver `docs/CONVENCIONES.md`.
3. **Dónde va cada cosa:** variables de entorno → `bot/config.py`; regex → `bot/nlp/patrones.py`; tablas → `bot/datos/`; APIs externas → `bot/integraciones/` o `bot/canales/`; rutas → `bot/rutas/` + registrar en `bot/app.py`.
4. **Dependencias en una sola dirección:** `rutas → atencion → conversacion → (ia, nlp, integraciones, canales, datos) → (utils, config, estado, db)`. Nada de imports circulares.
5. **Nunca** pongas tokens, keys ni teléfonos reales nuevos en el código ni en docs. Secretos solo por variables de entorno (objetivo: Secret Manager).
6. Después de cambiar código: `python scripts/generar_contexto.py` (lo hacen solos el hook de git y el de Claude Code), `pytest -q`, y una línea en `CHANGELOG.md`. Si es una decisión de arquitectura, un ADR en `docs/decisiones/`.
7. Cuando el usuario pida algo para "otros clientes", diséñalo **multi-tenant** (config por cliente en BD), no lo amarres a SAGUE.

## Cosas que muerden (aprendidas)

- **Ventana de 24 h de WhatsApp:** fuera de ella solo se pueden enviar plantillas aprobadas (`TPL_*`, `ALERTA_TEMPLATE`, `bienvenida_santa_teresa`). Por eso `enviar_seguimiento` cae a plantilla o a "envío manual por el asesor".
- **`OWNER_WA` no puede ser el número del bot** (WhatsApp no deja enviarse a sí mismo): las alertas no llegarían.
- **Cloud Run limita la CPU fuera de una petición:** `threading.Timer` y `PROCESAR_EN_SEGUNDO_PLANO=true` solo son fiables con CPU siempre asignada.
- **Deduplicación en memoria:** con varias instancias o tras un reinicio, Meta puede reentregar un mensaje y el bot responde dos veces.
- **El webhook no valida la firma de Meta todavía** (pendiente crítico en `docs/ROADMAP.md`).
- **Graph API v21.0** expira el 21-ene-2027: está escrita a mano en ~22 llamadas; centralizar antes de migrar.
- **Desde el 1-oct-2026** Meta cobra los mensajes de servicio por encima de 1.000 al mes por número: cada respuesta del bot cuesta.
- `leads.interes` es **JSON guardado como texto**; siempre `json.loads` / `json.dumps(ensure_ascii=False)` y mezclar con lo previo (`safe_upsert_lead` ya lo hace).
- Datos del proyecto que el bot **nunca** debe cambiar: 200 m² construidos (no 216), "frente a la loza deportiva", sin la palabra "remate" ni "preventa", sin crédito directo.
- **Clientes con usuario de WhatsApp (BSUID `PE.123…`)**: se responden con `recipient`, no `to` (`bot/utils/telefono.py`). Nunca normalizar un BSUID a dígitos.
- **Despliegue (desde 11-nov-2026): automático.** Cada push a `main` corre las pruebas y despliega a Cloud Run con GitHub Actions (`.github/workflows/desplegar.yml`, Workload Identity, sin claves). Los cambios solo de `docs/` o `*.md` no despliegan. Logs: flujo `registros`; volver atrás: flujo `revertir`. Desde la nube de Claude no se llega a las APIs de Google, pero sí se pueden ver los resultados de los jobs (`gh api .../commits/<sha>/check-runs`). El camino manual viejo (`scripts/generar_main_unico.py` + Cloud Shell) queda solo de emergencia; ver `docs/INCIDENTE_2026-11-08.md`.
- Imágenes de más de 5 MB se comprimen antes de subirlas a WhatsApp (`subir_media_wa`).

## Comandos

```bash
sh scripts/instalar_hooks.sh                 # una vez: hook de git + copia .claude/settings.json y CI desde plantillas_config/
python scripts/generar_contexto.py           # regenerar docs/CONTEXTO_AUTO.md y .env.example
python scripts/generar_contexto.py --check   # CI: falla si están desactualizados
pytest -q                                    # pruebas de humo
git push origin main                         # despliega solo (pruebas → Cloud Run)
```

## Prioridades actuales

Ver `docs/ROADMAP.md`. Lo primero: seguridad del webhook y secretos → cola (Cloud Tasks) e idempotencia → multi-tenant.


## PeruPTD Agent (motor nuevo, modo `catalogo`)
Ver README.md de la raíz del proyecto. Mapa rápido:
- `bot/nlu_normalizer.py` + `bot/nlu/` (léxico ES/EN en `lexicon.json`, compartido con `../hub`): Capa 1.
- `bot/engines/`: motores puros (sin red) + `guardas.py`. `bot/agente.py`: turno completo con envío, calendario y estado.
- `bot/tenant.py`, `bot/catalogo/` (lectura + sincronización desde el CRM), `bot/crm.py`, `bot/crm_adapters/`.
- `bot/canales/twilio_adapter.py` + `bot/rutas/twilio.py`: SMS/WhatsApp de Twilio (sender_id con prefijo `sms:` / `twa:`).
- `bot/datos/colas.py`, `idempotencia.py`: dedupe y debounce persistentes (migración 002).
- Regla: los motores nunca inventan cifras; todo precio sale de `catalog_items`. El LLM solo clasifica (Capa 1), no redacta.
