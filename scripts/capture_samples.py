#!/usr/bin/env python
"""Capture real request/response payloads (against the FAKE provider) into docs/samples/.

Deterministic and offline: SQLite + fake LLM + fake renderer + rate limiting disabled.
Run:  python scripts/capture_samples.py
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("JOBS_EAGER", "true")
os.environ.setdefault("LLM_DEFAULT_PROVIDER", "fake")
os.environ.setdefault("EXPORT_RENDERER", "fake")
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite://")

OUT = Path("docs/samples")


async def main() -> None:
    from httpx import ASGITransport, AsyncClient
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import StaticPool

    from app import models  # noqa: F401  (register tables)
    from app.db.base import Base
    from app.db.session import get_session
    from app.main import create_app

    engine = create_async_engine(
        "sqlite+aiosqlite://", poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    app = create_app()

    async def _override():
        async with maker() as s:
            yield s

    app.dependency_overrides[get_session] = _override
    OUT.mkdir(parents=True, exist_ok=True)
    samples: dict[str, object] = {}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost:8000") as c:
        created = await c.post(
            "/api/v1/auth/api-keys", json={"email": "demo@example.com", "name": "demo"}
        )
        samples["01_create_api_key"] = {
            "request": {"method": "POST", "path": "/api/v1/auth/api-keys",
                        "body": {"email": "demo@example.com", "name": "demo"}},
            "response": {"status": created.status_code, "body": created.json()},
        }
        key = created.json()["api_key"]
        h = {"X-API-Key": key}

        csv = (
            b"title,abstract,authors,year,doi\n"
            b"Attention,All you need,Vaswani; Shazeer,2017,10.5555/x\n"
        )
        up = await c.post("/api/v1/documents", headers=h,
                          files={"file": ("papers.csv", csv, "text/csv")})
        samples["02_upload_document"] = {
            "request": {"method": "POST", "path": "/api/v1/documents",
                        "body": "multipart/form-data: file=papers.csv"},
            "response": {"status": up.status_code, "body": up.json()},
        }
        doc_id = up.json()["id"]

        submit = await c.post("/api/v1/reviews", headers=h,
                              json={"topic": "attention mechanisms", "document_ids": [doc_id]})
        samples["03_submit_review"] = {
            "request": {"method": "POST", "path": "/api/v1/reviews",
                        "body": {"topic": "attention mechanisms", "document_ids": [doc_id]}},
            "response": {"status": submit.status_code, "body": submit.json()},
        }
        job_id = submit.json()["id"]

        poll = await c.get(f"/api/v1/reviews/jobs/{job_id}", headers=h)
        samples["04_poll_job"] = {
            "request": {"method": "GET", "path": f"/api/v1/reviews/jobs/{job_id}"},
            "response": {"status": poll.status_code, "body": poll.json()},
        }
        review_id = poll.json()["result"]["review_id"]

        review = await c.get(f"/api/v1/reviews/{review_id}", headers=h)
        samples["05_get_review"] = {
            "request": {"method": "GET", "path": f"/api/v1/reviews/{review_id}"},
            "response": {"status": review.status_code, "body": review.json()},
        }

        preview_path = f"/api/v1/reviews/{review_id}/preview?format=html"
        preview = await c.get(preview_path, headers=h)
        samples["06_preview"] = {
            "request": {"method": "GET", "path": preview_path},
            "response": {"status": preview.status_code, "body": preview.json()},
        }

        export = await c.get(f"/api/v1/reviews/{review_id}/export?format=pdf", headers=h)
        samples["07_export_pdf"] = {
            "request": {"method": "GET", "path": f"/api/v1/reviews/{review_id}/export?format=pdf"},
            "response": {"status": export.status_code, "body": json.loads(export.content)},
        }

    for name, payload in samples.items():
        (OUT / f"{name}.json").write_text(json.dumps(payload, indent=2) + "\n")
    print(f"wrote {len(samples)} sample files to {OUT}/")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
