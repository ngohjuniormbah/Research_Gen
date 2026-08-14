# Deploy to GCP

The backend is a standard container that reads all config from env vars, so GCP is a
clean fit. Two paths — start simple, scale later.

## Recommended (simple): Cloud Run web + Cloud SQL

One Cloud Run service runs the API. Generation runs inline (`JOBS_EAGER=true`), so there's
no separate worker to manage. Add the worker later when you need heavy async throughput.

```bash
PROJECT=your-project
REGION=us-central1

# 1. Build & push the image (Artifact Registry or GCR)
gcloud builds submit --tag $REGION-docker.pkg.dev/$PROJECT/app/litreview-backend

# 2. Managed Postgres (Cloud SQL)
gcloud sql instances create litreview-db --database-version=POSTGRES_16 \
  --tier=db-f1-micro --region=$REGION
gcloud sql databases create litreview --instance=litreview-db
gcloud sql users create app --instance=litreview-db --password=STRONGPASS

# 3. Deploy the web service (Cloud Run injects $PORT=8080; the image honors it and runs
#    migrations on start)
gcloud run deploy litreview-web \
  --image=$REGION-docker.pkg.dev/$PROJECT/app/litreview-backend \
  --region=$REGION --allow-unauthenticated \
  --add-cloudsql-instances=$PROJECT:$REGION:litreview-db \
  --set-env-vars=ENVIRONMENT=production,JOBS_EAGER=true,RATE_LIMIT_ENABLED=false \
  --set-env-vars=EXPORT_RENDERER=pandoc \
  --set-env-vars=CORS_ORIGINS='["https://your-frontend"]' \
  --set-env-vars=FERNET_KEY=<random>,EXPORT_URL_SECRET=<random> \
  --set-env-vars=DATABASE_URL='postgresql+asyncpg://app:STRONGPASS@/litreview?host=/cloudsql/'$PROJECT:$REGION:litreview-db
```

Notes:
- **Cloud SQL**: connect over the unix socket the `--add-cloudsql-instances` flag mounts
  (`host=/cloudsql/<conn-name>`), or use a public IP + SSL. The app rewrites
  `postgres://`/`postgresql://` to the async driver automatically.
- **Migrations** run on container start (baked into the image) — no separate step.
- **Redis**: only needed for rate limiting + idempotency. The simple path sets
  `RATE_LIMIT_ENABLED=false`. To enable it, add **Memorystore for Redis** and set
  `REDIS_URL`.
- **Request timeout**: raise Cloud Run's timeout (e.g. `--timeout=300`) so long
  generations with big models finish inside the request.

## Scaled: web (Cloud Run) + worker (GKE) + Memorystore

When you outgrow inline generation:
- Set `JOBS_EAGER=false` and add **Memorystore for Redis** (`REDIS_URL`).
- Run the **web** on Cloud Run as above (same image).
- Run the **worker** as a GKE Deployment (or a GCE VM) using the **same image** with the
  command `arq app.worker.settings.WorkerSettings` and the same env vars. A worker is a
  long-running poller, so it belongs on GKE/GCE, not a request-driven Cloud Run service.

## Why it won't crash on GCP
- The app boots and serves **regardless of model configuration** — providers are created
  lazily and only touched during a generation job.
- A misconfigured/unreachable model does **not** crash the server: that job is marked
  `failed` with an error message and the API keeps serving (covered by
  `tests/test_job_resilience.py`).
- Health/readiness probes (`/healthz`, `/readyz`) let Cloud Run/GKE gate traffic on a
  working DB connection.
