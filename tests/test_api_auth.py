from httpx import AsyncClient


async def test_create_and_use_api_key(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/api-keys", json={"email": "a@example.com", "name": "mine"}
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["api_key"].startswith("lrk_")
    key = body["api_key"]

    listed = await client.get("/api/v1/auth/api-keys", headers={"X-API-Key": key})
    assert listed.status_code == 200
    assert len(listed.json()) == 1


async def test_missing_key_rejected(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/auth/api-keys")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthorized"


async def test_invalid_key_rejected(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/auth/api-keys", headers={"X-API-Key": "lrk_nope"})
    assert resp.status_code == 401


async def test_revoked_key_rejected(client: AsyncClient) -> None:
    created = await client.post(
        "/api/v1/auth/api-keys", json={"email": "b@example.com"}
    )
    body = created.json()
    key, key_id = body["api_key"], body["id"]
    headers = {"X-API-Key": key}

    revoke = await client.delete(f"/api/v1/auth/api-keys/{key_id}", headers=headers)
    assert revoke.status_code == 204

    after = await client.get("/api/v1/auth/api-keys", headers=headers)
    assert after.status_code == 401


async def test_readyz_checks_db(client: AsyncClient) -> None:
    resp = await client.get("/readyz")
    assert resp.status_code == 200
    assert resp.json()["database"] == "ok"
