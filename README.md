# Literature Review Generator - Backend

Production-oriented FastAPI service that ingests bibliographic sources and generates a
structured, cited literature review via an async job pipeline. Built in steps; each step
runs green before the next lands.

> 🚀 **Deploying to Google Cloud? Read [`DEPLOYMENT.md`](DEPLOYMENT.md)** — a detailed,
> bilingual (English / Français) step-by-step guide (backend + database + frontend + keys).
>
> 🚀 **Déploiement sur Google Cloud ? Lisez [`DEPLOYMENT.md`](DEPLOYMENT.md)** — un guide
> détaillé et bilingue (anglais / français), étape par étape.

## Step 3 — production readiness + staging + handoff
- **Preview & export**: `GET /reviews/{id}/preview?format=html` (Markdown → sanitized
  HTML) and `GET /reviews/{id}/export?format=md|docx|pdf` (md/docx inline; pdf is a worker
  job → stored file → signed temporary URL). Renderer is config-driven (pandoc / fake).
- **Citations**: APA bibliography + CSL-JSON stored on each review.
- **Validation**: magic-byte MIME sniffing, upload-size + source-count caps, blank-prompt
  rejection, field-level errors.
- **Unified errors**: one `AppError` + global handlers → consistent
  `{error:{code,message,details,request_id}}`; no stack traces to clients.
- **Observability**: structlog JSON access logs (request_id/latency/key_prefix),
  per-generation token usage, Sentry (no-op without a DSN).
- **Rate limiting** (Redis, per key): general/min, max concurrent generations, stricter
  SPARQL cap → `429` + `Retry-After`. **Security**: locked CORS, Fernet-encrypted ORKG
  tokens, `Idempotency-Key` on `POST /reviews`, `pip-audit` in CI.
- **Handoff**: [`docs/api-contract.md`](docs/api-contract.md),
  [`docs/deploy-staging.md`](docs/deploy-staging.md),
  [`docs/postman_collection.json`](docs/postman_collection.json),
  [`docs/openapi.json`](docs/openapi.json), captured [`docs/samples/`](docs/samples/),
  and `scripts/seed.py` (issue test keys).

## Step 2 — the core pipeline
- Async SQLAlchemy 2.0 + Alembic; Postgres (prod) / SQLite (tests).
- ORM models: `users`, `api_keys`, `jobs` (first-class: queued→running→succeeded/failed,
  progress, input jsonb), `documents`, `reviews`.
- API-key auth (`X-API-Key`): issue / list / revoke + a `require_api_key` dependency.
- File ingestion for **CSV, XLSX, PDF, JSON**, all normalized to a single `SourceRecord`
  `{title, abstract, authors, year, venue, doi, full_text?, raw}`; dedupe + cleaning.
- Storage abstraction (local FS in dev; S3/MinIO-ready interface).
- ORKG integration: OIDC (Keycloak) token store + refresh, REST search, and a **guarded
  SPARQL** client (read-only forms only, auto-`LIMIT`, hard timeout).
- Config-driven LLM registry over one OpenAI-compatible client (`gemma`, `qwen`,
  `deepseek-v4`, `glm` via Ollama/hosted) plus a deterministic `fake` provider for tests.
  Adding a model = one registry entry, zero code change.
- Prompt/context assembly with a map-reduce fallback when sources exceed the token budget.
- Generation as an **async job**: `POST /reviews` → `202 {job_id}` → arq worker →
  structured review (sections + citations + sources) → poll to completion.

## Run locally
```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
uvicorn app.main:app --reload --app-dir src
# -> http://localhost:8000/healthz   http://localhost:8000/docs
```

## Quality gate (what CI runs)
```bash
ruff check .
mypy src
pytest -q
pip-audit
python scripts/export_openapi.py docs/openapi.json   # export the schema artifact
```

## Operational scripts
```bash
python scripts/seed.py 3                 # issue 3 test users + API keys (printed once)
python scripts/export_openapi.py         # -> docs/openapi.json
python scripts/capture_samples.py        # -> docs/samples/*.json (fake provider)
```

## Run with Docker (web + worker + postgres + redis + minio)
```bash
cp .env.example .env
docker compose up --build
docker compose run --rm web alembic upgrade head   # apply migrations
```

## Deploy
- **GCP (production)**: `docs/gcp-monday-runbook.md` — one command deploys the backend
  (`bash scripts/deploy_gcp.sh`), plus frontend build + CORS. Details: `docs/deploy-gcp.md`.
- **Render (staging)**: one-click blueprint — `docs/deploy-render.md`.
- **Frontend**: the React/Vite app in `frontend/` is a separate static deployment; set
  `VITE_API_BASE_URL` to the backend URL and the backend `CORS_ORIGINS` to the frontend URL.

## API tour
```bash
# 1. Issue an API key (bootstrap)
curl -sX POST localhost:8000/api/v1/auth/api-keys -H 'content-type: application/json' \
  -d '{"email":"me@example.com","name":"dev"}'
# -> {"api_key":"lrk_...", ...}   (shown once)

# 2. Upload sources (csv/xlsx/pdf/json)
curl -sX POST localhost:8000/api/v1/documents -H "X-API-Key: $KEY" -F file=@papers.csv

# 3. Generate a review (async)
curl -sX POST localhost:8000/api/v1/reviews -H "X-API-Key: $KEY" \
  -H 'content-type: application/json' \
  -d '{"topic":"graph neural networks","document_ids":["<doc-id>"]}'
# -> 202 {"id":"<job-id>", "status":"queued", ...}

# 4. Poll the job, then fetch the review
curl -s localhost:8000/api/v1/reviews/jobs/<job-id> -H "X-API-Key: $KEY"
curl -s localhost:8000/api/v1/reviews/<review-id>   -H "X-API-Key: $KEY"
```

## Layout
```
src/app/
  config.py              typed settings incl. the LLM registry
  db/                    Base, async engine/session, JSONB variant type
  models/                users, api_keys, jobs, documents, reviews
  schemas/               Pydantic incl. the canonical SourceRecord
  core/                  errors, logging, redis, crypto, signing, observability
  services/              business logic (no FastAPI imports)
    auth  storage  documents  context  prompts  review  jobs  render  citations
    export  exports  ratelimit  idempotency
    ingestion/           csv/xlsx/pdf/json parsers + normalize + magic-byte sniff
    llm/                 provider protocol, fake + OpenAI-compatible client, registry
    orkg/                OIDC client, encrypted token store, guarded SPARQL
  api/v1/                health, auth, documents, orkg, reviews (no business logic)
  api/                   deps, middleware, exception_handlers
  worker/                arq WorkerSettings + generate_review/export tasks + enqueue
migrations/              Alembic (async env + schema migrations)
scripts/                 seed, export_openapi, capture_samples
docs/                    api-contract, deploy-staging, postman collection, openapi, samples
tests/                   fake provider only; no live API/LLM/ORKG calls
```

## Project status
Steps 1 (skeleton), 2 (core pipeline), and 3 (production readiness + staging + handoff)
are complete. See `docs/` for the frontend handoff package.
