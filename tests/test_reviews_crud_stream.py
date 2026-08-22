import json

from httpx import AsyncClient

RECORDS = [
    {"title": "Transformers", "abstract": "Attention is all you need", "year": 2017},
    {"title": "BERT", "abstract": "Bidirectional encoders", "year": 2018},
]


async def _make_review(client: AsyncClient, auth_headers: dict, topic: str) -> str:
    r = await client.post(
        "/api/v1/reviews", headers=auth_headers, json={"topic": topic, "records": RECORDS}
    )
    assert r.status_code == 202, r.text
    return r.json()["result"]["review_id"]


async def test_list_and_search_reviews(client: AsyncClient, auth_headers: dict) -> None:
    rid = await _make_review(client, auth_headers, "graph neural networks")
    await _make_review(client, auth_headers, "malaria detection methods")

    lst = await client.get("/api/v1/reviews", headers=auth_headers)
    assert lst.status_code == 200
    items = lst.json()
    assert len(items) >= 2
    assert any(i["id"] == rid for i in items)
    assert all("sections" in i and "content_md" not in i for i in items)  # summary only

    hits = await client.get("/api/v1/reviews", headers=auth_headers, params={"q": "malaria"})
    topics = [i["topic"].lower() for i in hits.json()]
    assert topics and all("malaria" in t for t in topics)


async def test_list_requires_auth(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/reviews")).status_code == 401


async def test_rename_and_delete_review(client: AsyncClient, auth_headers: dict) -> None:
    rid = await _make_review(client, auth_headers, "old title")

    patched = await client.patch(
        f"/api/v1/reviews/{rid}", headers=auth_headers, json={"topic": "new title"}
    )
    assert patched.status_code == 200
    assert patched.json()["topic"] == "new title"

    deleted = await client.delete(f"/api/v1/reviews/{rid}", headers=auth_headers)
    assert deleted.status_code == 204
    assert (await client.get(f"/api/v1/reviews/{rid}", headers=auth_headers)).status_code == 404


async def test_stream_review_sse(client: AsyncClient, auth_headers: dict) -> None:
    tokens: list[str] = []
    done: dict | None = None
    async with client.stream(
        "POST", "/api/v1/reviews/stream", headers=auth_headers,
        json={"topic": "attention mechanisms", "records": RECORDS},
    ) as resp:
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        async for line in resp.aiter_lines():
            if not line.startswith("data:"):
                continue
            evt = json.loads(line[len("data:"):].strip())
            if evt["type"] == "token":
                tokens.append(evt["text"])
            elif evt["type"] == "done":
                done = evt
            elif evt["type"] == "error":
                raise AssertionError(f"stream error: {evt['message']}")

    assert tokens, "expected streamed tokens"
    assert done is not None and done.get("review_id")
    # The streamed text is persisted and fetchable.
    got = await client.get(f"/api/v1/reviews/{done['review_id']}", headers=auth_headers)
    assert got.status_code == 200
    assert "".join(tokens).strip() == got.json()["content_md"].strip()
