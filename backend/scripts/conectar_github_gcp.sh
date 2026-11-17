#!/bin/bash
# Conecta GitHub Actions con Google Cloud SIN claves (Workload Identity Federation).
# Ejecutar UNA vez en Cloud Shell:   bash conectar_github_gcp.sh TU_USUARIO_GITHUB/sague-bot
# Crea una cuenta de servicio "github-deployer" que SOLO ese repositorio puede usar.
set -euo pipefail
REPO="${1:?Uso: bash conectar_github_gcp.sh usuario/repositorio}"
PROJECT=sague-bot
gcloud config set project "$PROJECT" >/dev/null
NUM=$(gcloud projects describe "$PROJECT" --format='value(projectNumber)')
SA="github-deployer@${PROJECT}.iam.gserviceaccount.com"

echo "1/5 Activando APIs…"
gcloud services enable iamcredentials.googleapis.com sts.googleapis.com cloudbuild.googleapis.com \
  run.googleapis.com artifactregistry.googleapis.com logging.googleapis.com --quiet

echo "2/5 Cuenta de servicio github-deployer…"
gcloud iam service-accounts describe "$SA" >/dev/null 2>&1 || \
  gcloud iam service-accounts create github-deployer --display-name="GitHub Actions: desplegar sague-bot"

echo "3/5 Permisos (desplegar, leer registros)…"
# Una cuenta recién creada tarda unos segundos en ser visible para IAM: se reintenta hasta 6 veces
for ROL in roles/run.admin roles/iam.serviceAccountUser roles/cloudbuild.builds.editor \
           roles/artifactregistry.writer roles/storage.admin roles/logging.viewer roles/serviceusage.serviceUsageConsumer; do
  for INTENTO in 1 2 3 4 5 6; do
    if gcloud projects add-iam-policy-binding "$PROJECT" --member="serviceAccount:$SA" --role="$ROL" --condition=None --quiet >/dev/null 2>&1; then
      break
    fi
    [ "$INTENTO" = 6 ] && { echo "No se pudo asignar $ROL. Espera 1 minuto y vuelve a ejecutar el script."; exit 1; }
    sleep 10
  done
done

echo "4/5 Conexión segura con GitHub (solo el repo $REPO)…"
gcloud iam workload-identity-pools describe github --location=global >/dev/null 2>&1 || \
  gcloud iam workload-identity-pools create github --location=global --display-name="GitHub"
gcloud iam workload-identity-pools providers describe github --location=global --workload-identity-pool=github >/dev/null 2>&1 || \
  gcloud iam workload-identity-pools providers create-oidc github --location=global --workload-identity-pool=github \
    --display-name="GitHub Actions" --issuer-uri="https://token.actions.githubusercontent.com" \
    --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
    --attribute-condition="assertion.repository=='${REPO}'"
gcloud iam service-accounts add-iam-policy-binding "$SA" --role=roles/iam.workloadIdentityUser \
  --member="principalSet://iam.googleapis.com/projects/${NUM}/locations/global/workloadIdentityPools/github/attribute.repository/${REPO}" --quiet >/dev/null

echo "5/5 Listo. Copia estos 2 valores en GitHub (Settings > Secrets and variables > Actions > Variables):"
echo
echo "  GCP_WIF_PROVIDER    = projects/${NUM}/locations/global/workloadIdentityPools/github/providers/github"
echo "  GCP_SERVICE_ACCOUNT = ${SA}"
