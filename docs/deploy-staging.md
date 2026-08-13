# Deploy to Staging (Railway)

This deploys the **same Docker image** twice — once as the web API, once as the arq
worker — plus managed Postgres and Redis. File storage uses the local disk of the web
service by default (set S3/MinIO vars to use object storage).

## Architecture on Railway

```
┌─────────────┐   enqueue    ┌──────────────┐
│  web (API)  │ ───────────► │ worker (arq) │
│ uvicorn     │   Redis      │ generation + │
│ app.main    │ ◄─────────── │ pdf export   │
└──────┬──────┘   results    └──────┬───────┘
       │                            │
       ▼                            ▼
   Postgres  ◄───────────────────  (shared)
   Redis     ◄───────────────────  (shared)
```

Both services run `Dockerfile` (multi-stage). The command differs:
- **web**: `uvicorn app.main:app --host 0.0.0.0 --port 8000`
- **worker**: `arq app.worker.settings.WorkerSettings`

## Prerequisites

- A [Railway](https://railway.app) account and the CLI: `npm i -g @railway/cli`
- `railway login`

## 1. Create the project + managed datastores

```bash
railway init                      # create a project
railway add --database postgres   # provisions DATABASE_URL
railway add --database redis       # provisions REDIS_URL
```

Railway injects `DATABASE_URL` / `REDIS_URL`. **Convert the Postgres URL to the async
driver** the app expects (`postgresql+asyncpg://…`). Set it explicitly (see below).

## 2. Create the two services

Create **web** and **worker** services from this repo (both build the Dockerfile):

```bash
railway service create web
railway service create worker
# set the worker's start command:
railway variables --service worker --set 'RAILWAY_RUN_COMMAND=arq app.worker.settings.WorkerSettings'
```

(Or set the start command in each service's Settings → Deploy.)

## 3. Required environment variables

Set these on **both** services (values shared where noted). Generate real secrets — never
reuse the dev defaults.

| Variable | Notes |
| --- | --- |
| `ENVIRONMENT` | `staging` |
| `DATABASE_URL` | `postgresql+asyncpg://…` (async driver) |
| `REDIS_URL` | from the Redis plugin |
| `JOBS_EAGER` | `false` (web enqueues, worker runs) |
| `CORS_ORIGINS` | `["https://<your-frontend-domain>"]` — lock it down |
| `FERNET_KEY` | `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `EXPORT_URL_SECRET` | long random string (e.g. `openssl rand -hex 32`) |
| `EXPORT_RENDERER` | `pandoc` (the image ships pandoc + WeasyPrint) |
| `SENTRY_DSN` | optional; leave empty to disable |
| `RATE_LIMIT_PER_MINUTE` / `MAX_CONCURRENT_GENERATIONS` / `SPARQL_RATE_LIMIT_PER_MINUTE` | tune as needed |

Example (CLI):

```bash
FERNET=$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
for SVC in web worker; do
  railway variables --service $SVC \
    --set "ENVIRONMENT=staging" \
    --set "JOBS_EAGER=false" \
    --set "CORS_ORIGINS=[\"https://app.example.com\"]" \
    --set "FERNET_KEY=$FERNET" \
    --set "EXPORT_URL_SECRET=$(openssl rand -hex 32)" \
    --set "EXPORT_RENDERER=pandoc"
  # DATABASE_URL/REDIS_URL: reference the plugin values, ensuring the asyncpg driver.
done
```

## 4. Deploy

```bash
railway up --service web
railway up --service worker
```

## 5. Run migrations (every deploy that changes the schema)

```bash
railway run --service web alembic upgrade head
```

## 6. Seed test API keys (staging only)

```bash
railway run --service web python scripts/seed.py 3
# prints:
#   EMAIL                         API_KEY
#   seed1@example.com             lrk_....
#   ...
```

Copy the printed keys — they are shown once. Hand them to the frontend team for testing.

## 7. Smoke test

```bash
BASE=https://<your-app>.up.railway.app
curl -s $BASE/healthz          # {"status":"ok"}
curl -s $BASE/readyz           # {"status":"ready","database":"ok"}
```

Then run the "Getting started in 10 minutes" flow in
[`api-contract.md`](./api-contract.md).

## CI-driven deploy (optional)

`.github/workflows/ci.yml` contains a `deploy-staging` job that is **disabled by default**.
To enable it:
1. Add repository secret `RAILWAY_TOKEN` (a project token from Railway).
2. Add repository variable `ENABLE_RAILWAY_DEPLOY=true`.
It then runs on pushes to `main` after tests + image build pass, deploys both services, and
runs migrations. Leave it disabled until the project + secrets exist.
