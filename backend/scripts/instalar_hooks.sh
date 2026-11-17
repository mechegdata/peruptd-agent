#!/bin/sh
# Ejecutar UNA vez después de clonar (Git Bash en Windows, terminal en Mac/Linux o Cloud Shell).
# 1) Activa el hook pre-commit que regenera docs/CONTEXTO_AUTO.md y .env.example
# 2) Copia la config del hook de Claude Code y del CI de GitHub a su lugar (.claude/ y .github/)
cd "$(dirname "$0")/.." || exit 1
git config core.hooksPath .githooks
chmod +x .githooks/pre-commit 2>/dev/null
mkdir -p .claude .github/workflows
[ -f .claude/settings.json ] || cp plantillas_config/claude_settings.json .claude/settings.json
[ -f .github/workflows/ci.yml ] || cp plantillas_config/github_ci.yml .github/workflows/ci.yml
echo "Listo: hook de git, hook de Claude Code (.claude/settings.json) y CI (.github/workflows/ci.yml)."
