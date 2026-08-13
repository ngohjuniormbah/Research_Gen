# syntax=docker/dockerfile:1
# Multi-stage build. The SAME image runs the web API or the worker — selected by the
# container's command (see docker-compose.yml).

# ----- builder: produce a wheel ------------------------------------------------ #
FROM python:3.12-slim AS builder
ENV PIP_NO_CACHE_DIR=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
RUN pip install --upgrade pip build
COPY pyproject.toml ./
COPY src ./src
RUN python -m build --wheel --outdir /dist

# ----- runtime ----------------------------------------------------------------- #
FROM python:3.12-slim AS runtime
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

# pandoc + WeasyPrint runtime libraries (PDF export engine).
RUN apt-get update && apt-get install -y --no-install-recommends \
        pandoc \
        libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf-2.0-0 libcairo2 libffi8 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=builder /dist /dist
RUN pip install /dist/*.whl weasyprint && rm -rf /dist

# Alembic + migrations + operational scripts for `alembic upgrade head`, seeding, etc.
COPY alembic.ini ./
COPY migrations ./migrations
COPY scripts ./scripts

# Drop root.
RUN useradd --create-home --uid 10001 appuser && mkdir -p /app/data && chown -R appuser /app
USER appuser

EXPOSE 8000
# Default is the web API, honoring an injected $PORT (Railway/Render) with an 8000
# fallback for local/compose. The worker overrides this with:
#   arq app.worker.settings.WorkerSettings
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
