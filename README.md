# Literature Review Generator - Backend

Production-oriented FastAPI service that ingests bibliographic sources and generates a
structured, cited literature review via an async job pipeline. Built in steps; each step
runs green before the next lands.

## Step 2 (this drop) — the core pipeline
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
```

## Run with Docker (web + worker + postgres + redis + minio)
```bash
cp .env.example .env
docker compose up --build
docker compose run --rm web alembic upgrade head   # apply migrations
```

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
  services/              business logic (no FastAPI imports)
    auth.py  storage.py  documents.py  context.py  prompts.py  review.py  jobs.py
    ingestion/           csv/xlsx/pdf/json parsers + normalize
    llm/                 provider protocol, fake + OpenAI-compatible client, registry
    orkg/                OIDC client, token store, guarded SPARQL
  api/v1/                health, auth, documents, orkg, reviews (no business logic)
  worker/                arq WorkerSettings + generate_review task + enqueue helper
migrations/              Alembic (async env + initial schema)
tests/                   fake provider only; no live API calls
```

## Roadmap (Step 3)
Pandoc PDF/DOCX export, preview rendering, rate limiting, Sentry/observability, staging
deploy, OpenAPI polish, frontend handoff docs.
