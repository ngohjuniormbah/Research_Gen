import json

from httpx import AsyncClient


async def _make_review(client: AsyncClient, headers: dict) -> str:
    payload = {
        "topic": "attention mechanisms",
        "records": [
            {"title": "Transformers", "abstract": "Attention is all you need", "year": 2017},
            {"title": "BERT", "abstract": "Bidirectional encoders", "year": 2018},
        ],
    }
    resp = await client.post("/api/v1/reviews", headers=headers, json=payload)
    assert resp.status_code == 202
    job = resp.json()
    assert job["status"] == "succeeded"
    return job["result"]["review_id"]


async def test_review_stores_csl_json(client: AsyncClient, auth_headers: dict) -> None:
    review_id = await _make_review(client, auth_headers)
    resp = await client.get(f"/api/v1/reviews/{review_id}", headers=auth_headers)
    body = resp.json()
    assert isinstance(body["csl_json"], list)
    assert len(body["csl_json"]) == 2
    assert body["csl_json"][0]["type"] == "article-journal"


async def test_preview_returns_sanitized_html(client: AsyncClient, auth_headers: dict) -> None:
    review_id = await _make_review(client, auth_headers)
    resp = await client.get(
        f"/api/v1/reviews/{review_id}/preview?format=html", headers=auth_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["format"] == "html"
    assert "<h1>" in body["html"]
    assert "<script>" not in body["html"]


async def test_export_md_inline(client: AsyncClient, auth_headers: dict) -> None:
    review_id = await _make_review(client, auth_headers)
    resp = await client.get(
        f"/api/v1/reviews/{review_id}/export?format=md", headers=auth_headers
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/markdown")
    assert "Literature Review" in resp.text
    assert "attachment" in resp.headers["content-disposition"]


async def test_export_docx_inline(client: AsyncClient, auth_headers: dict) -> None:
    review_id = await _make_review(client, auth_headers)
    resp = await client.get(
        f"/api/v1/reviews/{review_id}/export?format=docx", headers=auth_headers
    )
    assert resp.status_code == 200
    assert "wordprocessingml" in resp.headers["content-type"]
    assert len(resp.content) > 0


async def test_export_pdf_async_then_download(client: AsyncClient, auth_headers: dict) -> None:
    review_id = await _make_review(client, auth_headers)
    resp = await client.get(
        f"/api/v1/reviews/{review_id}/export?format=pdf", headers=auth_headers
    )
    assert resp.status_code == 202
    job = json.loads(resp.content)
    assert job["kind"] == "export_review"
    assert job["status"] == "succeeded"
    download_url = job["result"]["download_url"]
    assert download_url.startswith("/api/v1/reviews/exports/")

    # The signed URL needs no API key.
    got = await client.get(download_url)
    assert got.status_code == 200
    assert got.content.startswith(b"%PDF")
    assert "attachment" in got.headers["content-disposition"]


async def test_export_bad_format_rejected(client: AsyncClient, auth_headers: dict) -> None:
    review_id = await _make_review(client, auth_headers)
    resp = await client.get(
        f"/api/v1/reviews/{review_id}/export?format=exe", headers=auth_headers
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "validation_error"


async def test_download_bad_token_rejected(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/reviews/exports/not-a-valid-token")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthorized"


async def test_preview_requires_auth(client: AsyncClient) -> None:
    import uuid

    resp = await client.get(f"/api/v1/reviews/{uuid.uuid4()}/preview")
    assert resp.status_code == 401
