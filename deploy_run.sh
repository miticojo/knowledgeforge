#!/bin/bash
set -e

: "${PROJECT_ID:?PROJECT_ID env var is required (your GCP project for Cloud Run)}"
: "${SPANNER_PROJECT:?SPANNER_PROJECT env var is required (GCP project that hosts the Spanner instance)}"
: "${SPANNER_INSTANCE:?SPANNER_INSTANCE env var is required}"
: "${SPANNER_DATABASE:?SPANNER_DATABASE env var is required}"
REGION="${REGION:-europe-west1}"

echo "=========================================================="
echo "🚀 INIZIO DEPLOY SU CLOUD RUN "
echo "📦 Progetto: $PROJECT_ID"
echo "🌍 Regione: $REGION"
echo "=========================================================="

echo ""
echo "[1/2] 🐍 Deploy Backend FastAPI (kb-agent)..."
gcloud run deploy kb-agent \
  --project $PROJECT_ID \
  --source ./kb-agent \
  --region $REGION \
  --allow-unauthenticated \
  --set-env-vars="ENABLE_MODEL_ARMOR=true,MODEL_ARMOR_TEMPLATE_ID=projects/$PROJECT_ID/locations/$REGION/templates/kb-shield,GOOGLE_CLOUD_LOCATION=$REGION,VERTEX_AI_LOCATION=$REGION,GOOGLE_GENAI_USE_VERTEXAI=1,GOOGLE_CLOUD_PROJECT=$PROJECT_ID,SPANNER_PROJECT=$SPANNER_PROJECT,SPANNER_INSTANCE=$SPANNER_INSTANCE,SPANNER_DATABASE=$SPANNER_DATABASE,RECONCILIATION_THRESHOLD=0.15,ENV=production"

BACKEND_URL=$(gcloud run services describe kb-agent --project $PROJECT_ID --region $REGION --format 'value(status.url)')
echo "✅ Backend deployato con successo! URL: $BACKEND_URL"

echo ""
echo "[2/2] ⚛️ Deploy Frontend Next.js (kb-frontend)..."
gcloud run deploy kb-frontend \
  --project $PROJECT_ID \
  --source ./kb-frontend \
  --region $REGION \
  --allow-unauthenticated \
  --set-env-vars="BACKEND_URL=$BACKEND_URL"

FRONTEND_URL=$(gcloud run services describe kb-frontend --project $PROJECT_ID --region $REGION --format 'value(status.url)')
echo "✅ Frontend deployato con successo! URL: $FRONTEND_URL"

echo "=========================================================="
echo "🎉 DEPLOY COMPLETATO"
echo "🌐 Visita l'interfaccia dell'Agente su: $FRONTEND_URL"
echo "=========================================================="
