import json

from httpx import AsyncClient

CSV = (
    "title,abstract,authors,year,journal,doi\n"
    "Deep Learning,A survey.,Smith; Doe,2019,Nature,10.1/abc\n"
    "Transformers,Attention.,Vaswani,2017,NeurIPS,10.2/xyz\n"
)


async def test_upload_document_and_fetch(client: AsyncClient, auth_headers: dict) -> None:
    resp = await client.post(
        "/api/v1/documents",
        headers=auth_headers,
        files={"file": ("papers.csv", CSV.encode(), "text/csv")},
    )
    assert resp.status_code == 201
    doc = resp.json()
    assert doc["kind"] == "csv"
    assert doc["status"] == "parsed"
    assert doc["parsed_meta"]["record_count"] == 2

    got = await client.get(f"/api/v1/documents/{doc['id']}", headers=auth_headers)
    assert got.status_code == 200
    assert got.json()["parsed_meta"]["record_count"] == 2


async def test_upload_requires_auth(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/documents",
        files={"file": ("papers.csv", CSV.encode(), "text/csv")},
    )
    assert resp.status_code == 401


async def test_document_not_found(client: AsyncClient, auth_headers: dict) -> None:
    import uuid

    resp = await client.get(f"/api/v1/documents/{uuid.uuid4()}", headers=auth_headers)
    assert resp.status_code == 404


async def test_review_pipeline_end_to_end(client: AsyncClient, auth_headers: dict) -> None:
    # Inline records path: submit -> 202 job -> poll -> fetch structured review.
    payload = {
        "topic": "attention mechanisms",
        "records": [
            {"title": "Transformers", "abstract": "Attention is all you need", "year": 2017},
            {"title": "BERT", "abstract": "Bidirectional encoders", "year": 2018},
        ],
    }
    resp = await client.post("/api/v1/reviews", headers=auth_headers, json=payload)
    assert resp.status_code == 202
    job = resp.json()
    job_id = job["id"]

    polled = await client.get(f"/api/v1/reviews/jobs/{job_id}", headers=auth_headers)
    assert polled.status_code == 200
    job = polled.json()
    assert job["status"] == "succeeded"
    assert job["progress"] == 100
    review_id = job["result"]["review_id"]

    review = await client.get(f"/api/v1/reviews/{review_id}", headers=auth_headers)
    assert review.status_code == 200
    body = review.json()
    assert body["provider"] == "fake"
    assert "Literature Review" in body["content_md"]
    headings = {s["heading"] for s in body["structured"]["sections"]}
    assert "Introduction" in headings
    assert len(body["structured"]["citations"]) >= 1


async def test_review_from_uploaded_document(client: AsyncClient, auth_headers: dict) -> None:
    upload = await client.post(
        "/api/v1/documents",
        headers=auth_headers,
        files={"file": ("papers.csv", CSV.encode(), "text/csv")},
    )
    doc_id = upload.json()["id"]

    resp = await client.post(
        "/api/v1/reviews",
        headers=auth_headers,
        json={"topic": "deep learning", "document_ids": [doc_id]},
    )
    assert resp.status_code == 202
    job = resp.json()
    assert job["status"] == "succeeded"
    review_id = job["result"]["review_id"]

    review = await client.get(f"/api/v1/reviews/{review_id}", headers=auth_headers)
    assert len(review.json()["structured"]["sources"]) == 2


async def test_review_unknown_provider_rejected(client: AsyncClient, auth_headers: dict) -> None:
    resp = await client.post(
        "/api/v1/reviews",
        headers=auth_headers,
        json={"topic": "x", "provider": "nonexistent", "records": [{"title": "A"}]},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "unknown_provider"


async def test_review_requires_auth(client: AsyncClient) -> None:
    resp = await client.post("/api/v1/reviews", json={"topic": "x"})
    assert resp.status_code == 401


def test_csv_fixture_is_valid_json_free() -> None:
    # Guard: the CSV constant is not accidentally JSON.
    try:
        json.loads(CSV)
        raise AssertionError("CSV should not parse as JSON")
    except json.JSONDecodeError:
        pass
