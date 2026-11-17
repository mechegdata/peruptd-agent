#!/usr/bin/env bash
# Guarda la clave secreta de la app de Meta y una clave nueva para /cron en Secret Manager, se las pasa a Cloud Run
# y activa la verificación de la firma de Meta en el webhook. Se ejecuta UNA vez en Cloud Shell:
#   bash configurar_secretos.sh
# Es seguro volver a ejecutarlo (agrega una versión nueva de cada secreto).
set -euo pipefail

PROJECT=sague-bot
REGION=us-central1
SERVICIO=sague-bot
JOB=sague-reloj

gcloud config set project "$PROJECT" >/dev/null

echo "1/6 Activando Secret Manager…"
gcloud services enable secretmanager.googleapis.com --quiet

guardar_secreto() {  # nombre valor
  if gcloud secrets describe "$1" >/dev/null 2>&1; then
    printf '%s' "$2" | gcloud secrets versions add "$1" --data-file=- >/dev/null
  else
    printf '%s' "$2" | gcloud secrets create "$1" --replication-policy=automatic --data-file=- >/dev/null
  fi
}

echo
echo "2/6 Clave secreta de la app de Meta"
echo "    Meta for Developers → tu app → Configuración de la app → Básica → 'Clave secreta de la app' → Mostrar."
read -rsp "    Pégala aquí (no se verá mientras la pegas) y presiona Enter: " APP_SECRET
echo
[ -n "$APP_SECRET" ] || { echo "No pegaste nada. Vuelve a ejecutar el script."; exit 1; }
guardar_secreto meta-app-secret "$APP_SECRET"
unset APP_SECRET

echo "3/6 Clave nueva para /cron…"
CRON_KEY=$(openssl rand -hex 24)
guardar_secreto cron-key "$CRON_KEY"

echo "4/6 Permiso para que Cloud Run lea los secretos…"
SA=$(gcloud run services describe "$SERVICIO" --region "$REGION" --format='value(spec.template.spec.serviceAccountName)')
if [ -z "$SA" ]; then
  SA="$(gcloud projects describe "$PROJECT" --format='value(projectNumber)')-compute@developer.gserviceaccount.com"
fi
for S in meta-app-secret cron-key; do
  gcloud secrets add-iam-policy-binding "$S" --member="serviceAccount:$SA" \
    --role=roles/secretmanager.secretAccessor --quiet >/dev/null
done

echo "5/6 Cloud Scheduler ($JOB) enviará la clave nueva a /cron…"
UBICACION=""
for L in "$REGION" us-east1 us-west1 southamerica-east1 southamerica-west1; do
  if gcloud scheduler jobs describe "$JOB" --location "$L" >/dev/null 2>&1; then UBICACION=$L; break; fi
done
if [ -n "$UBICACION" ]; then
  gcloud scheduler jobs update http "$JOB" --location "$UBICACION" --update-headers="X-Cron-Key=$CRON_KEY" --quiet >/dev/null
  echo "    Listo ($UBICACION)."
else
  echo "    No encontré el job '$JOB'. /cron seguirá protegido como antes (sin CRON_KEY)."
fi

echo "6/6 Pasando los secretos a Cloud Run (modo observación de la firma)…"
SECRETOS="META_APP_SECRET=meta-app-secret:latest"
[ -n "$UBICACION" ] && SECRETOS="$SECRETOS,CRON_KEY=cron-key:latest"
gcloud run services update "$SERVICIO" --region "$REGION" --update-secrets="$SECRETOS" \
  --update-env-vars=FIRMA_META_EXIGIR=false --quiet
unset CRON_KEY

echo
echo "================================================================"
echo " Ahora escríbele un mensaje al bot por WhatsApp (por ejemplo 'hola')"
echo " desde tu celular y espera su respuesta."
read -rp " Cuando te haya respondido, presiona Enter aquí… " _
echo
sleep 5
REGISTRO=$(gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=$SERVICIO AND textPayload:\"Firma de Meta\"" \
  --freshness=15m --limit=5 --format='value(textPayload)')
echo "$REGISTRO"
if echo "$REGISTRO" | grep -q "Firma de Meta OK"; then
  echo "La firma coincide ✅. Activando el bloqueo de avisos falsos…"
  gcloud run services update "$SERVICIO" --region "$REGION" --update-env-vars=FIRMA_META_EXIGIR=true --quiet
  echo "LISTO: el webhook solo acepta avisos firmados por Meta."
elif echo "$REGISTRO" | grep -q "NO coincide"; then
  echo "La clave NO coincide ❌ (el bot sigue funcionando normal). Revisa que copiaste la"
  echo "'Clave secreta de la app' correcta y vuelve a ejecutar el script."
else
  echo "Todavía no veo registros de la firma. Espera un minuto y vuelve a ejecutar el script."
fi
