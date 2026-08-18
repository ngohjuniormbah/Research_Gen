#!/usr/bin/env bash
# One-shot backend deploy to GCP (Cloud Run + Cloud SQL). Idempotent: safe to re-run.
# Prereqs: `gcloud` installed and `gcloud auth login` done. Run from the repo root.
#
#   PROJECT=my-proj REGION=us-central1 DB_PASSWORD='...' FRONTEND_ORIGIN='https://app...' \
#     bash scripts/deploy_gcp.sh
#
# Optional: OPENAI_API_KEY=sk-... and/or OPENROUTER_API_KEY=sk-or-... to enable real models.
set -euo pipefail

# ---- config (override via env) --------------------------------------------- #
PROJECT="${PROJECT:?set PROJECT=your-gcp-project}"
REGION="${REGION:-us-central1}"
DB_INSTANCE="${DB_INSTANCE:-litreview-db}"
DB_NAME="${DB_NAME:-litreview}"
DB_USER="${DB_USER:-app}"
DB_PASSWORD="${DB_PASSWORD:?set DB_PASSWORD=a-strong-password}"
SERVICE="${SERVICE:-litreview-web}"
FRONTEND_ORIGIN="${FRONTEND_ORIGIN:-*}"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT}/app/litreview-backend:latest"
FERNET_KEY="${FERNET_KEY:-$(python3 -c 'import secrets;print(secrets.token_urlsafe(32))')}"
EXPORT_URL_SECRET="${EXPORT_URL_SECRET:-$(python3 -c 'import secrets;print(secrets.token_urlsafe(32))')}"
OPENAI_API_KEY="${OPENAI_API_KEY:-}"
OPENROUTER_API_KEY="${OPENROUTER_API_KEY:-}"
# ---------------------------------------------------------------------------- #

echo "==> Project $PROJECT / region $REGION"
gcloud config set project "$PROJECT" >/dev/null
# Enabling APIs needs serviceusage admin. If the deployer service account lacks it, the
# project OWNER must enable them once (see docs/gcp-service-account-setup.md). Non-fatal so
# a deploy still proceeds when the APIs are already enabled.
gcloud services enable run.googleapis.com sqladmin.googleapis.com \
  artifactregistry.googleapis.com cloudbuild.googleapis.com >/dev/null 2>&1 \
  || echo "WARN: could not enable APIs from here — ensure the project owner enabled them" \
          "(docs/gcp-service-account-setup.md). Continuing…"

echo "==> Artifact Registry"
gcloud artifacts repositories create app --repository-format=docker \
  --location="$REGION" 2>/dev/null || true

echo "==> Build & push backend image (frontend excluded via .gcloudignore)"
gcloud builds submit --tag "$IMAGE"

echo "==> Cloud SQL (Postgres)"
if ! gcloud sql instances describe "$DB_INSTANCE" >/dev/null 2>&1; then
  gcloud sql instances create "$DB_INSTANCE" --database-version=POSTGRES_16 \
    --tier=db-f1-micro --region="$REGION"
fi
gcloud sql databases create "$DB_NAME" --instance="$DB_INSTANCE" 2>/dev/null || true
gcloud sql users create "$DB_USER" --instance="$DB_INSTANCE" --password="$DB_PASSWORD" 2>/dev/null \
  || gcloud sql users set-password "$DB_USER" --instance="$DB_INSTANCE" --password="$DB_PASSWORD"

CONN="${PROJECT}:${REGION}:${DB_INSTANCE}"
DATABASE_URL="postgresql+asyncpg://${DB_USER}:${DB_PASSWORD}@/${DB_NAME}?host=/cloudsql/${CONN}"

# Build the env-var list with '@' as the delimiter (values contain commas/brackets).
ENVVARS="ENVIRONMENT=production@JOBS_EAGER=true@RATE_LIMIT_ENABLED=false@EXPORT_RENDERER=pandoc"
ENVVARS="${ENVVARS}@FERNET_KEY=${FERNET_KEY}@EXPORT_URL_SECRET=${EXPORT_URL_SECRET}"
ENVVARS="${ENVVARS}@DATABASE_URL=${DATABASE_URL}@CORS_ORIGINS=[\"${FRONTEND_ORIGIN}\"]"
[ -n "$OPENAI_API_KEY" ] && ENVVARS="${ENVVARS}@OPENAI_API_KEY=${OPENAI_API_KEY}@LLM_DEFAULT_PROVIDER=openai"
[ -n "$OPENROUTER_API_KEY" ] && ENVVARS="${ENVVARS}@OPENROUTER_API_KEY=${OPENROUTER_API_KEY}"

echo "==> Deploy to Cloud Run (migrations run on container start)"
gcloud run deploy "$SERVICE" \
  --image="$IMAGE" --region="$REGION" --platform=managed --allow-unauthenticated \
  --add-cloudsql-instances="$CONN" --timeout=300 --memory=1Gi --cpu=1 \
  --set-env-vars="^@^${ENVVARS}"

URL="$(gcloud run services describe "$SERVICE" --region="$REGION" --format='value(status.url)')"
echo
echo "==> Deployed: $URL"
echo "    Health:  curl -s $URL/readyz"
echo "    Smoke:   python scripts/smoke_test.py $URL --provider fake"
