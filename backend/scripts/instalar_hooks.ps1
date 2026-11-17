# Ejecutar UNA vez después de clonar (PowerShell en Windows), desde la carpeta del proyecto:
#   powershell -ExecutionPolicy Bypass -File scripts\instalar_hooks.ps1
Set-Location (Join-Path $PSScriptRoot "..")
git config core.hooksPath .githooks
New-Item -ItemType Directory -Force -Path ".claude", ".github\workflows" | Out-Null
if (-not (Test-Path ".claude\settings.json")) { Copy-Item "plantillas_config\claude_settings.json" ".claude\settings.json" }
if (-not (Test-Path ".github\workflows\ci.yml")) { Copy-Item "plantillas_config\github_ci.yml" ".github\workflows\ci.yml" }
Write-Host "Listo: hook de git, hook de Claude Code (.claude\settings.json) y CI (.github\workflows\ci.yml)."
