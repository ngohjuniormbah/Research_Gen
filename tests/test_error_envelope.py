from httpx import AsyncClient


async def _assert_envelope(payload: dict) -> None:
    assert "error" in payload
    err = payload["error"]
    for field in ("code", "message", "details", "request_id"):
        assert field in err, f"missing {field}"


async def test_401_envelope(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/auth/api-keys")
    assert resp.status_code == 401
    await _assert_envelope(resp.json())
    assert resp.json()["error"]["code"] == "unauthorized"
    # request_id echoed in header too.
    assert resp.headers.get("x-request-id")


async def test_404_unknown_route_envelope(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/does-not-exist")
    assert resp.status_code == 404
    await _assert_envelope(resp.json())
    assert resp.json()["error"]["code"] == "not_found"


async def test_422_validation_envelope_has_field_details(
    client: AsyncClient, auth_headers: dict
) -> None:
    # Missing required 'topic'.
    resp = await client.post("/api/v1/reviews", headers=auth_headers, json={})
    assert resp.status_code == 422
    body = resp.json()
    await _assert_envelope(body)
    assert body["error"]["code"] == "validation_error"
    assert isinstance(body["error"]["details"], list)
    assert body["error"]["details"], "expected field-level details"


async def test_request_id_is_stable_and_echoed(client: AsyncClient) -> None:
    resp = await client.get("/healthz", headers={"x-request-id": "trace-123"})
    assert resp.headers["x-request-id"] == "trace-123"


async def test_not_found_review_envelope(client: AsyncClient, auth_headers: dict) -> None:
    import uuid

    resp = await client.get(f"/api/v1/reviews/{uuid.uuid4()}", headers=auth_headers)
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"
