import io

from httpx import AsyncClient


async def test_empty_file_rejected(client: AsyncClient, auth_headers: dict) -> None:
    resp = await client.post(
        "/api/v1/documents", headers=auth_headers,
        files={"file": ("empty.csv", b"", "text/csv")},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "validation_error"


async def test_oversize_file_rejected(client: AsyncClient, auth_headers: dict) -> None:
    # Default limit is 10MB; send just over a tiny override is hard, so send >10MB.
    big = b"a,b,c\n" + b"1,2,3\n" * 2_000_000  # ~12MB
    resp = await client.post(
        "/api/v1/documents", headers=auth_headers,
        files={"file": ("big.csv", big, "text/csv")},
    )
    assert resp.status_code == 413
    assert resp.json()["error"]["code"] == "payload_too_large"


async def test_magic_bytes_mismatch_marks_failed(client: AsyncClient, auth_headers: dict) -> None:
    # A PDF disguised with a .csv name: sniffing sees %PDF and treats it as PDF (image
    # PDF with no text) -> parse fails, document persisted with status='failed'.
    fake_pdf = b"%PDF-1.4\nno text here\n"
    resp = await client.post(
        "/api/v1/documents", headers=auth_headers,
        files={"file": ("sneaky.csv", fake_pdf, "text/csv")},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["kind"] == "pdf"  # detected by magic bytes, not the .csv extension
    assert body["status"] == "failed"


async def test_zip_non_xlsx_rejected(client: AsyncClient, auth_headers: dict) -> None:
    zip_bytes = b"PK\x03\x04" + b"\x00" * 40
    resp = await client.post(
        "/api/v1/documents", headers=auth_headers,
        files={"file": ("archive.zip", zip_bytes, "application/zip")},
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == "failed"


async def test_blank_topic_rejected(client: AsyncClient, auth_headers: dict) -> None:
    resp = await client.post(
        "/api/v1/reviews", headers=auth_headers,
        json={"topic": "   ", "records": [{"title": "A"}]},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "validation_error"
    # Field-level detail present.
    assert any("topic" in str(d.get("field", "")) for d in resp.json()["error"]["details"])


async def test_unknown_provider_rejected(client: AsyncClient, auth_headers: dict) -> None:
    resp = await client.post(
        "/api/v1/reviews", headers=auth_headers,
        json={"topic": "x", "provider": "ghost", "records": [{"title": "A"}]},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "unknown_provider"


async def test_document_content_actually_parses(client: AsyncClient, auth_headers: dict) -> None:
    # Sanity: a genuine CSV with a matching extension parses fine.
    csv = io.BytesIO(b"title,year\nHello,2020\n").getvalue()
    resp = await client.post(
        "/api/v1/documents", headers=auth_headers,
        files={"file": ("real.csv", csv, "text/csv")},
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == "parsed"
    assert resp.json()["parsed_meta"]["record_count"] == 1
