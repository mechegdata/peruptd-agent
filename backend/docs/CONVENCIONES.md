# Convenciones del proyecto

## Tamaño y responsabilidad (archivos "atómicos")

| Regla | Límite | Por qué |
|---|---|---|
| Un archivo = una responsabilidad | Si necesitas "y" para describirlo, divídelo | Fácil de encontrar, de probar y de dar como contexto a la IA |
| Líneas por archivo | ideal 100-200 · máximo **300** | Cabe completo en pantalla y en el contexto de un chat |
| Líneas por función | ideal ≤ 30 · máximo **60** | Una función, una decisión |
| Parámetros por función | ≤ 5 (si no, un `dict`/`dataclass`) | Legibilidad |
| Profundidad de `if` anidados | ≤ 3 | Usar retornos tempranos |

El generador (`scripts/generar_contexto.py`) marca con ⚠️ lo que se pasa del límite en `docs/CONTEXTO_AUTO.md` §8. Hoy hay deuda heredada del monolito (p. ej. `motor_agenda()` con 412 líneas): **no agregues más líneas a esas funciones**; al tocarlas, extrae sub-funciones.

## Dónde va cada cosa

| Si vas a… | Va en |
|---|---|
| Agregar una variable de entorno | `bot/config.py` (y se documenta sola en `.env.example`) |
| Agregar una regex de intención | `bot/nlp/patrones.py` |
| Responder un tipo de pregunta nuevo | un módulo en `bot/conversacion/` y llamarlo desde `orquestador.py` |
| Llamar a una API externa nueva | `bot/integraciones/<servicio>.py` o `bot/canales/<canal>.py` |
| Leer/escribir tablas | `bot/datos/<tabla>.py` (nunca `supabase.table()` fuera de `bot/datos/` en código nuevo) |
| Una ruta HTTP | `bot/rutas/<nombre>.py` con un `Blueprint` y registrarlo en `bot/app.py` |
| Textos del negocio de un cliente | Hoy en el módulo de conversación; objetivo: base de datos (ver `PRODUCTO_SAAS.md`) |

Dependencias permitidas (de arriba hacia abajo, nunca al revés): `rutas → atencion → conversacion → (ia, nlp, integraciones, canales, datos) → (utils, config, estado, db)`.

## Código

- Nombres en español, como el resto del proyecto (`responder_faq`, `enviar_seguimiento`). Las funciones heredadas en inglés (`send_wa_text`) se mantienen.
- Docstring de una línea en cada módulo y en cada función pública (el generador las usa).
- Nada de secretos ni teléfonos reales nuevos como valor por defecto.
- Formato: `ruff format` (o `black`) con línea de 120.

## Git

- Ramas: `main` (producción), `staging`, y `feat/…`, `fix/…`, `docs/…` para cambios.
- Commits con [Conventional Commits](https://www.conventionalcommits.org/es/): `feat: botones para elegir horario`, `fix: duplicados por reintentos de Meta`.
- Cada cambio visible para el cliente → una línea en `CHANGELOG.md`.
- Cada decisión de arquitectura → un ADR en `docs/decisiones/` (copia `0000-plantilla.md`).
