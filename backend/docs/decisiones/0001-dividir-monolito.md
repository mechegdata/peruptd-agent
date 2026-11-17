# ADR-0001: Dividir main.py en módulos atómicos sin cambiar la lógica

- **Fecha:** 2026-10-25
- **Estado:** aceptada

## Contexto
Todo el bot vivía en un `main.py` de ~3.375 líneas editado en Cloud Shell. Era difícil de navegar, de revisar y de pasar como contexto a un chat de IA, y bloqueaba el camino a un producto multi-cliente.

## Decisión
Separar el archivo en el paquete `bot/` (40 módulos, uno por responsabilidad) copiando cada función **tal cual**, generando los imports y pasando las rutas a Blueprints de Flask. `main.py` queda como punto de entrada (`main:app`), por lo que el comando de despliegue no cambia. El original se guarda en `legacy/main_monolito.py` como referencia.

Se verificó que la versión modular produce exactamente las mismas respuestas y las mismas llamadas a APIs que el original en ~600 casos de prueba (parser de fechas, financiamiento, FAQ, material, info, despedida, respaldo, motor de agenda, orquestador completo, webhook, seguimientos y comandos del asesor).

## Alternativas consideradas
- Reescribir desde cero con arquitectura multi-tenant — demasiado riesgo con el bot en producción.
- Dejar el monolito — impide crecer y ordenar.

## Consecuencias
- Cada módulo cabe en el contexto de un chat; los errores se localizan rápido.
- Quedan funciones largas heredadas (`motor_agenda`, `process_conversation`, `build_Contextual_fallback`): se dividirán al tocarlas.
- `legacy/main_monolito.py` se puede borrar cuando la versión modular lleve unas semanas estable en producción.
