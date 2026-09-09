import uuid
from httpx import AsyncClient


async def test_evaluate_review_lifecycle(client: AsyncClient, auth_headers: dict) -> None:
    # 1. Create a review
    submit = await client.post(
        "/api/v1/reviews",
        headers=auth_headers,
        json={
            "topic": "Evaluation of Graph Neural Networks",
            "records": [{"title": "GNN Survey", "abstract": "Overview of message passing", "year": 2022}],
        },
    )
    assert submit.status_code == 202
    review_id = submit.json()["result"]["review_id"]

    # 2. Run evaluation
    eval_resp = await client.post(
        f"/api/v1/reviews/{review_id}/evaluate",
        headers=auth_headers,
        json={"provider": "fake", "rubric": "Check for strict mathematical rigor"},
    )
    assert eval_resp.status_code == 200
    res = eval_resp.json()

    assert res["review_id"] == review_id
    assert res["judge_provider"] == "fake"
    assert 1.0 <= res["overall_score"] <= 10.0
    assert res["grounding"]["score"] >= 1
    assert res["citation_accuracy"]["score"] >= 1
    assert res["completeness"]["score"] >= 1
    assert res["academic_rigor"]["score"] >= 1
    assert len(res["critique_summary"]) > 0

    # 3. Confirm evaluation is persisted on the review record
    fetched = await client.get(f"/api/v1/reviews/{review_id}", headers=auth_headers)
    assert fetched.status_code == 200
    persisted_eval = fetched.json()["structured"].get("evaluation")
    assert persisted_eval is not None
    assert persisted_eval["overall_score"] == res["overall_score"]


async def test_evaluate_requires_auth(client: AsyncClient) -> None:
    resp = await client.post(f"/api/v1/reviews/{uuid.uuid4()}/evaluate", json={})
    assert resp.status_code == 401
