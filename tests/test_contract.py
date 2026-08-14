"""Contract tests: every endpoint's real response must validate against its schema."""

from httpx import AsyncClient

from app.schemas.auth import ApiKeyCreated, ApiKeyInfo
from app.schemas.document import DocumentInfo
from app.schemas.job import JobInfo
from app.schemas.review import PreviewOut, ReviewOut

CSV = b"title,abstract,authors,year,doi\nDeep Learning,A survey.,Smith; Doe,2019,10.1/abc\n"


async def test_auth_contract(client: AsyncClient) -> None:
    created = await client.post("/api/v1/auth/api-keys", json={"email": "c@example.com"})
    model = ApiKeyCreated.model_validate(created.json())
    assert model.api_key.startswith("lrk_")

    listed = await client.get("/api/v1/auth/api-keys", headers={"X-API-Key": model.api_key})
    for item in listed.json():
        ApiKeyInfo.model_validate(item)


async def test_document_contract(client: AsyncClient, auth_headers: dict) -> None:
    up = await client.post(
        "/api/v1/documents", headers=auth_headers,
        files={"file": ("p.csv", CSV, "text/csv")},
    )
    doc = DocumentInfo.model_validate(up.json())
    got = await client.get(f"/api/v1/documents/{doc.id}", headers=auth_headers)
    DocumentInfo.model_validate(got.json())


async def test_review_lifecycle_contract(client: AsyncClient, auth_headers: dict) -> None:
    submit = await client.post(
        "/api/v1/reviews", headers=auth_headers,
        json={"topic": "contract topic", "records": [{"title": "A", "year": 2020}]},
    )
    job = JobInfo.model_validate(submit.json())
    assert job.status == "succeeded"

    polled = await client.get(f"/api/v1/reviews/jobs/{job.id}", headers=auth_headers)
    poll_model = JobInfo.model_validate(polled.json())
    review_id = poll_model.result["review_id"]

    review = await client.get(f"/api/v1/reviews/{review_id}", headers=auth_headers)
    ReviewOut.model_validate(review.json())

    preview = await client.get(
        f"/api/v1/reviews/{review_id}/preview?format=html", headers=auth_headers
    )
    PreviewOut.model_validate(preview.json())


async def test_export_job_contract(client: AsyncClient, auth_headers: dict) -> None:
    import json

    submit = await client.post(
        "/api/v1/reviews", headers=auth_headers,
        json={"topic": "t", "records": [{"title": "A"}]},
    )
    review_id = submit.json()["result"]["review_id"]
    export = await client.get(
        f"/api/v1/reviews/{review_id}/export?format=pdf", headers=auth_headers
    )
    job = JobInfo.model_validate(json.loads(export.content))
    assert job.kind == "export_review"
    assert "download_url" in job.result


async def test_health_contract(client: AsyncClient) -> None:
    assert (await client.get("/healthz")).json() == {"status": "ok"}
    ready = await client.get("/readyz")
    assert ready.json()["status"] == "ready"


async def test_root_landing(client: AsyncClient) -> None:
    resp = await client.get("/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["docs"] == "/docs"


async def test_models_endpoint_lists_providers(client: AsyncClient, auth_headers: dict) -> None:
    resp = await client.get("/api/v1/models", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["default"] == "fake"
    keys = {p["key"] for p in body["providers"]}
    # The registry ships these selectable keys; none expose an api_key.
    assert {"fake", "llama", "gemma", "qwen", "deepseek-v4", "glm"} <= keys
    assert all("api_key" not in p for p in body["providers"])
    # Each entry carries a display label + a location badge for the frontend picker.
    for p in body["providers"]:
        assert p["label"] and p["location"] in ("local", "cloud", "builtin")


async def test_models_requires_auth(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/models")).status_code == 401
