# Trabajar con Claude desde el celular

Objetivo: pedirle a Claude desde la app del celular "arregla X / mejora Y" y que lo haga de punta a punta
(código → pruebas → despliegue → verificación) sin que tengas que estar en la computadora.

## Cómo queda armado

```
Tú (app de Claude en el celular)
  └─ sesión de Claude con el repositorio sague-bot
        ├─ edita el código y corre las pruebas
        ├─ sube el cambio a GitHub (rama main)
        │     └─ GitHub Actions "Desplegar a Cloud Run": pruebas → deploy → verifica que responde y que no hay errores
        ├─ lee los registros del bot  → GitHub Actions "Ver registros"
        ├─ vuelve a la versión anterior → GitHub Actions "Revertir versión"
        └─ consulta / corrige la base de datos → conector de Supabase
```

## Configuración (una sola vez)

| Paso | Quién | Qué |
|---|---|---|
| 1 | Tú | Crear cuenta en GitHub (si no tienes) y un repositorio **privado y vacío** llamado `sague-bot` |
| 2 | Tú | Conectar GitHub en Claude: claude.ai → Configuración → Conectores → GitHub, y dar acceso al repo `sague-bot` |
| 3 | Claude | Subir todo el código de la carpeta al repo, con los flujos de `plantillas_config/workflows/` en `.github/workflows/` |
| 4 | Tú (Cloud Shell) | Subir `scripts/conectar_github_gcp.sh` y ejecutar `bash conectar_github_gcp.sh TU_USUARIO/sague-bot` |
| 5 | Tú o Claude | En GitHub → Settings → Secrets and variables → Actions → **Variables**: `GCP_WIF_PROVIDER` y `GCP_SERVICE_ACCOUNT` (los imprime el paso 4) |
| 6 | Tú | En GitHub → Settings → Environments → crear `produccion`. Opcional: "Required reviewers" = tú → cada despliegue espera tu aprobación con un toque |
| 7 | Tú | Conectar **Supabase** en claude.ai → Configuración → Conectores |
| 8 | Tú | Instalar la app **GitHub** en el celular (para aprobar despliegues y ver el estado) |

No se guarda ninguna clave de Google en GitHub: la conexión usa Workload Identity Federation y solo funciona desde el repo `sague-bot`.

## Uso diario desde el celular

1. Abre la app de Claude → **Code** → nueva sesión con el repositorio `sague-bot`.
2. Escribe lo que necesitas: *"el bot respondió mal a este cliente: …, corrígelo"*, *"revisa por qué no respondió hoy"*, *"cambia el precio al contado a US$128,000"*.
3. Claude corrige, agrega una prueba con el caso, corre todas las pruebas y sube el cambio.
4. Si activaste la aprobación (paso 6), te llega un aviso de GitHub: **Approve and deploy**.
5. Claude revisa los registros del despliegue y te confirma, o revierte si algo salió mal.

## Lo que todavía necesita tu intervención

- **Meta** (tokens, verificaciones de cuenta, plantillas de WhatsApp, anuncios): no hay conector; se hace desde Meta Business o con el navegador de la app de escritorio.
- **Variables de entorno / secretos** de Cloud Run: se cambian en la consola (o se agrega un flujo para eso más adelante).
- Cualquier cambio en la cuenta de Google Cloud fuera del servicio `sague-bot`.
