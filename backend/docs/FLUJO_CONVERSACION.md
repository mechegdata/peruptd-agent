# Flujo de una conversación

## 1. Entrada de un mensaje de WhatsApp

```
POST /webhook  (bot/rutas/webhook.py)
  ├─ echoes del asesor (smb_message_echoes) → bot/handoff.py guarda el mensaje manual en el historial
  ├─ dedupe por id en memoria (bot/estado.py: PROCESSED_IDS)
  └─ bot/atencion.py · atender_mensaje_wa()
        ├─ audio / imagen sin texto → respuesta fija
        ├─ si escribe el asesor (OWNER_WA) → bot/asesor.py (comandos)
        ├─ si el asesor está atendiendo (PAUSA_BOT_TRAS_HUMANO_MIN) → solo guarda
        └─ bot/conversacion/orquestador.py · process_conversation()
              → envía la respuesta y luego el material (bot/canales/material.py)
```

## 2. Orden de decisión dentro de `process_conversation()`

| Paso | Motor | Archivo | Cuándo responde |
|---|---|---|---|
| 0a | Cortesía | `conversacion/cortesia.py` | "le estaré comunicando la hora", "👍", "ok" (puede no responder) |
| 0b | Después de agendar | `conversacion/post_agenda.py` | con quién viene, movilidad, "vamos por nuestra cuenta" |
| 0 | Despedida | `conversacion/despedida.py` | "no, gracias", "eso es todo", "no" a "¿otra duda?" |
| 1 | Formulario Lead Ads | `conversacion/formulario.py` | El texto es un formulario de Meta llegado por WhatsApp |
| 2 | FAQ → Material + Info | `conversacion/faq.py`, `material.py`, `info.py` | No hay día/hora en el mensaje, no es elección de horario, no es "sí/no" corto (una objeción de precio nunca cuenta como "no" corto) |
| 2a | ↳ Precio (dentro de la FAQ, va primero) | `conversacion/objeciones.py`, `precio.py` | "¿soles o dólares?", "tipo de cambio", "está muy caro", "¿hay descuento?" (con crédito) |
| 3 | Agenda determinística | `conversacion/agenda.py` | Mensajes de agendamiento, respuestas a horarios ofrecidos, "sí/no" a financiamiento |
| 3a | ↳ Agenda humana (antes de tomar una hora como cita) | `conversacion/agenda_humana.py`, `nlp/restricciones.py` | "trabajo hasta las 5", "salgo a las 3", "después de las 4", "en la noche", "el fin de semana a las 10" |
| 4 | Gemini | `ia/prompt.py` + `ia/gemini.py` | Todo lo demás (historial de 20 mensajes + agenda + estado del lead) |
| 5 | Respaldo | `conversacion/respaldo.py` | Gemini no respondió en `GEMINI_PRESUPUESTO_SEG` |

Post-proceso (solo en la rama de Gemini/respaldo): forzar adjuntos si el texto los promete, "1" ⇒ planos + renders, validar `agendar_visita_iso` contra Calendar, no repetir la pregunta de financiamiento.

Cierre común (`_finalizar_conversacion`): material del momento (`conversacion/recursos.py`), alerta al asesor si un motor la pidió (`meta["_alerta_asesor"]`), anti-repetición (si la respuesta es ≥ 80 % igual a la anterior se reformula y se alerta al asesor), guardar en `mensajes`, upsert del lead y, si vino de Facebook/Instagram con teléfono, saltar a WhatsApp.

## 3. Etapas (`leads.interes.etapa`)

| Etapa | Significa | La fija |
|---|---|---|
| `ofrecio_horarios` | Se ofrecieron horarios numerados (1️⃣ 2️⃣ 3️⃣) | agenda, slots, seguimiento |
| `pregunto_dia` | Se preguntó qué día le acomoda | agenda, anti-repetición |
| `pregunto_financiamiento` | Se preguntó contado / crédito / inicial | agenda, orquestador |
| `confirmar_horario` | El cliente propuso un horario, falta su "sí" | agenda, rescate 24 h |
| `espera_cliente` | El cliente dijo "te aviso / le comunico la hora": no insistir | cortesía |
| `pregunto_acompanantes` | Cita recién creada: se preguntó con quién viene | agenda |
| `ofrecio_movilidad` | Se ofreció recogerlos (si `OFRECE_MOVILIDAD`) | post_agenda |
| `confirmacion_manual` | Calendar no se pudo verificar; confirma el asesor | agenda |
| `agendado` | Cita creada en Calendar | agenda, orquestador |
| `confirmar_asistencia` | Se envió recordatorio | seguimiento |
| `ofrecio_asesor` | Se ofreció asesor hipotecario | agenda, faq, formulario, seguimiento |
| `ofrecio_material` | Se ofreció enviar planos / renders | agenda |
| `ofrecio_copia` | Se ofreció la Copia Literal (contado) | seguimiento post-visita |
| `pregunto_presupuesto` | Presupuesto menor al precio u objeción "está caro": se pidió el tope | formulario, objeciones, rescate 24 h |
| `cerrado` | Se despidió o terminó el protocolo de 14 días | despedida, seguimiento |

La lista completa de claves del estado se regenera sola en `CONTEXTO_AUTO.md` §5.

## 4. Seguimiento automático (`/cron`, cada X minutos por Cloud Scheduler)

`bot/seguimiento/motor.py` revisa leads de WhatsApp actualizados en los últimos 16 días, solo entre 08:30 y 20:30, y hace **máximo una acción por lead**:

1. **Recordatorio** de la visita (día anterior desde las 18:00 o el mismo día con ≥ 2 h).
2. **Post-visita**: pregunta al asesor si vino; si `vino` → toques a los 45 min, 48 h, día 5, 10 y 14; si `no vino` → mensaje para reprogramar.
3. **Rescate 24 h**: si el cliente dejó en visto, un mensaje según en qué quedó (no si dijo "te aviso" o se despidió).

Fuera de la ventana de 24 h: plantilla aprobada si está configurada (`TPL_*`); si no, se le pasa el texto al asesor para que lo envíe a mano.

## 5. Precio: moneda, objeción y gancho del m²

- **Moneda:** el precio está en dólares; se puede pagar en soles al tipo de cambio del día del pago (`TIPO_CAMBIO_TEXTO`). Cifra en soles solo si hay `TIPO_CAMBIO_REFERENCIAL` o `TIPO_CAMBIO_AUTO=true` (BCRP).
- **Objeción "está caro"** (`objecion_precio_n` en el estado): 1ra vez → valor por m² + qué incluye + bono + "¿qué rango manejas?" (etapa `pregunto_presupuesto`); 2da → visita sin compromiso, los números los cierran los propietarios; 3ra → el propietario le escribe. Alerta al asesor en cada nivel. Si dice un monto, se calcula su $/m² ("a $120,000 serían $600 por m²").
- **Gancho $/m²** (`gancho_m2_n`): respuesta de precio/info general, pregunta de área (si aún no lo vio), objeción, tope de presupuesto, descuento con crédito, rescate 24 h genérico y de presupuesto, toque post-visita día 10.

## 6. Material por casa: fotos reales, renders amoblados, videos y fichas (`conversacion/recursos.py`)

**Dónde se guarda:** en las carpetas del bucket `recursos` de Supabase Storage; el bot las lee solo (`bot/datos/recursos.py`, caché de 10 min).
Paso a paso para subir: **`docs/GUIA_SUBIR_MATERIAL.md`**. Para verificar: `/diagnostico/material?key=VERIFY_TOKEN`.
```
recursos/santa-teresa/<comun | casa-1 | casa-2>/<fotos | renders | videos | fichas>/<ambiente>.<ext>
```
El nombre del archivo es el ambiente (`sala.jpg`, `dormitorio-2.jpg`, `recorrido.mp4`). `renders` = cualquier imagen con muebles que no se entregan.
La tabla `recursos_media` (`docs/migraciones/001_recursos_media.sql`) es opcional (leyendas propias); `URL_FOTO_*` queda como respaldo.
Límites de WhatsApp: video MP4 ≤ 16 MB; imagen JPG/PNG ≤ 5 MB (se comprime sola); PDF ≤ 100 MB. Lo que no cumple sale en "avisos" del diagnóstico.

**Rótulos automáticos:** foto real → "📸 … (foto real)"; render → "🎨 … (Render con mobiliario de referencia: la casa se entrega sin muebles.)";
video → "🎥 Recorrido en video de la Casa N"; ficha → "📄 Ficha técnica y planos de la Casa N". Si una fila trae `leyenda`, se usa esa.
Si existen fichas por casa en el catálogo, reemplazan a la ficha única (`URL_FICHA_TECNICA`).

| Momento | Material (máx.) | Por qué |
|---|---|---|
| 1er mensaje a lead de formulario | planos + cocina elegida + 1 render amoblado (sala) | Enamorar desde el inicio (Eloisa se animó al ver los muebles) |
| Pide info general o precio | fachada + sala (render amoblado si hay) (2) | El precio se recibe mejor después de ver la casa |
| Pide planos | ficha(s) + 1 render amoblado no visto | Los planos son fríos |
| Pide distribución | ficha(s) + dormitorio + terraza (2) | Lo que el plano no transmite |
| "¿Viene amoblada?" / "¿cómo se ve por dentro?" | hasta 3 renders amoblados | |
| "Lo converso con mi esposo/familia" | 2 renders amoblados | Para que se la muestre |
| Objeción "está caro" | terraza + cochera / jardín (2) | Lo que un depa no tiene |
| Pide ubicación | fachada (1) | |
| Cita confirmada | fachada (1) | "Para que la reconozcas al llegar" |
| Rescate 24 h | 1 no vista | Reenganchar con algo nuevo |
| 45 min post-visita | planos + cocinas + 2 renders amoblados | Para verla en familia |
| No asistió | 1 render amoblado | Reavivar el interés |
| Día 5 post-visita | 1 (sala / terraza) | Antes de la visita de cierre |
| Pide fotos / videos | hasta 6 fotos / 1 video por casa | |

Nunca se repite un archivo (`fotos_enviadas`), salvo que el cliente lo pida y ya haya visto todo.

## 7. Trato humano (aprendido de chats reales)

- **Pospone** ("le estaré comunicando la hora", "te aviso", "lo converso con mi esposa") → "Quedo atento 😊", etapa `espera_cliente`, sin ofrecer horarios (`conversacion/cortesia.py`).
- **👍 / ok sin contenido** → si hay una lista de horarios vigente, se recuerda **una sola vez** en una línea; en otros casos (espera, cita agendada) **no se responde** (`_no_responder`).
- **"La segunda opción"** se entiende aunque el último mensaje del bot no haya sido la lista.
- **Nombre de perfil inválido** ("." o un emoji) → se saluda sin nombre.
- **Qué días puede**, dicho como sea ("no puedo entre semana", "solo los sábados", "el fin de semana no", "martes o jueves", "menos el lunes") → `bot/nlp/dias.py`.
- **Trabaja** ("hasta las 5", "de lunes a viernes", "en la noche") → "entre semana te recibo saliendo del trabajo, desde las 6 p. m. hasta las 8 o 9 p. m. (dime día y hora), y el fin de semana claro que sí: [horarios del calendario]" (`HORA_INICIO_NOCHE`, `HORARIO_NOCHE_HASTA_TXT`). Luego "a las 7" → "¿qué día de la semana?".
- **Hora suelta tras ofrecer un día** ("a eso de las 4.30") → ese día; si se ofrecieron varios, pregunta cuál.
- **Después de agendar** → "¿vendrás con alguien más?" (`pregunto_acompanantes`) → si `OFRECE_MOVILIDAD=true`, ofrece recojo desde `MOVILIDAD_DESDE` (`ofrecio_movilidad`) → "vamos por nuestra cuenta" = agradece + ubicación. Cada dato le llega al asesor como alerta.

## 8. Ritmo humano y precio (chats reales 26-27 oct)

- **Mensajes seguidos** del cliente se juntan (`bot/agrupador.py`, `AGRUPAR_MENSAJES_SEG`) y se responden una vez.
- **El asesor escribe a mano** → el bot se calla `PAUSA_BOT_TRAS_HUMANO_MIN` (120 min) en ese chat. Requiere que Meta envíe los ecos de la app (campo `smb_message_echoes` del webhook). "pausa 51…" desde `OWNER_WA` lo calla hasta "activar 51…".
- **Precio**: lista US$135,000; al contado US$130,000 negociable en la visita (`PRECIO_CONTADO_USD`). Presupuesto del cliente → `bot/conversacion/presupuesto.py` (honesto; inicial + crédito si no alcanza; pregunta la moneda si no la dice).
- **"¿Solo tienen esas?"** → solo hay estas 2 casas de 3 pisos (sin casas de un piso, departamentos ni terrenos).
