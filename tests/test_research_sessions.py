import json

from httpx import AsyncClient


async def _create(
    client: AsyncClient, auth_headers: dict, title: str, state: dict | None = None
) -> dict:
    r = await client.post(
        "/api/v1/sessions", headers=auth_headers,
        json={"title": title, "state": state or {}},
    )
    assert r.status_code == 201, r.text
    return r.json()


async def test_session_crud_and_reopen(client: AsyncClient, auth_headers: dict) -> None:
    state = {
        "prompt": "malaria ML",
        "model": "fake",
        "sources": [{"title": "CNN", "orkg_id": "R1"}],
        "orkg_query": "malaria detection",
        "outputs": [{"review_id": "x", "content_md": "..."}],
    }
    created = await _create(client, auth_headers, "Malaria review", state)
    sid = created["id"]
    assert created["state"]["prompt"] == "malaria ML"

    # reopen: full state comes back
    got = await client.get(f"/api/v1/sessions/{sid}", headers=auth_headers)
    assert got.status_code == 200
    assert got.json()["state"]["orkg_query"] == "malaria detection"

    # list summary carries derived counts, not the full state
    lst = await client.get("/api/v1/sessions", headers=auth_headers)
    assert lst.status_code == 200
    row = next(r for r in lst.json() if r["id"] == sid)
    assert row["sources"] == 1 and row["outputs"] == 1 and "state" not in row


async def test_session_update_star_archive_rename(client: AsyncClient, auth_headers: dict) -> None:
    sid = (await _create(client, auth_headers, "old"))["id"]

    p = await client.patch(
        f"/api/v1/sessions/{sid}", headers=auth_headers,
        json={"title": "new", "starred": True, "archived": True},
    )
    assert p.status_code == 200
    body = p.json()
    assert body["title"] == "new" and body["starred"] and body["archived"]

    # archived hidden by default, shown with include_archived
    default_list = await client.get("/api/v1/sessions", headers=auth_headers)
    assert all(r["id"] != sid for r in default_list.json())
    with_arch = await client.get(
        "/api/v1/sessions", headers=auth_headers, params={"include_archived": True}
    )
    assert any(r["id"] == sid for r in with_arch.json())


async def test_session_search_and_delete(client: AsyncClient, auth_headers: dict) -> None:
    a = (await _create(client, auth_headers, "graph neural networks"))["id"]
    await _create(client, auth_headers, "malaria detection")

    hits = await client.get("/api/v1/sessions", headers=auth_headers, params={"q": "malaria"})
    titles = [r["title"].lower() for r in hits.json()]
    assert titles and all("malaria" in t for t in titles)

    d = await client.delete(f"/api/v1/sessions/{a}", headers=auth_headers)
    assert d.status_code == 204
    assert (await client.get(f"/api/v1/sessions/{a}", headers=auth_headers)).status_code == 404


async def test_session_chat_grounded_and_persisted(client: AsyncClient, auth_headers: dict) -> None:
    state = {
        "prompt": "malaria ML",
        "outputs": [{
            "content_md": "## Synthesis\nCNN reaches 96% accuracy [1].",
            "structured": {
                "sources": [{"title": "CNN for malaria", "doi": "10.1/x", "year": 2021}],
            },
        }],
    }
    sid = (await _create(client, auth_headers, "Malaria", state))["id"]

    tokens: list[str] = []
    done = False
    async with client.stream(
        "POST", f"/api/v1/sessions/{sid}/chat", headers=auth_headers,
        json={"message": "Which method is reported and what accuracy?"},
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
                done = True
            elif evt["type"] == "error":
                raise AssertionError(evt["message"])
    assert tokens and done

    # the chat turn is persisted into the session's Working Memory
    got = await client.get(f"/api/v1/sessions/{sid}", headers=auth_headers)
    chat = got.json()["state"]["chat"]
    assert chat[0]["role"] == "user" and chat[1]["role"] == "assistant"
    assert "".join(tokens).strip() == chat[1]["text"].strip()


async def test_sessions_require_auth(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/sessions")).status_code == 401
    assert (await client.post("/api/v1/sessions", json={"title": "x"})).status_code == 401
    assert (await client.post("/api/v1/sessions/00000000-0000-0000-0000-000000000000/chat",
                              json={"message": "x"})).status_code == 401
