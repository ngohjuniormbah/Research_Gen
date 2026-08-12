# Literature Review Generator - Backend

Production-oriented FastAPI service. Built in vertical slices; each slice runs green before the next lands.

## Slice 1 (this drop)
Runnable FastAPI skeleton: request-id middleware, JSON structured logging, health/readiness probes, consistent error envelope, tests, Docker, green CI.

## Requirements
- Python 3.12+
- (Docker optional for the compose stack)

## Run locally
```bash
python -m venv .venv && source .venv/bin/activate
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

## Run with Docker
```bash
cp .env.example .env
docker compose up --build web    # app only
docker compose up --build        # app + postgres + redis
```

## Layout
```
src/app/
  main.py            app factory, middleware, exception handler
  config.py          typed settings (all env vars)
  api/v1/health.py   /healthz, /readyz
  core/logging.py    structlog JSON logging
  core/errors.py     AppError -> error envelope
tests/               async client + health tests
```

## Roadmap
2. DB + Alembic + users/api_keys + auth + rate limiting
3. Storage abstraction + upload + parsers
4. LLM protocol + OpenAI-compatible client + registry + fake provider
5. Jobs + arq worker + async review endpoints
6. ORKG REST + guarded SPARQL
7. Preview + Pandoc exports + citations
8. Hardening + Sentry + OpenAPI freeze
