"""Validation and ORKG fallback tests before pushing to GitHub."""

from __future__ import annotations

from typing import Any
from httpx import AsyncClient
import pytest

from app.services.orkg.client import ORKGClient
from app.services.orkg.resolve import resolve_many


async def test_long_prompt_not_rejected(client: AsyncClient, auth_headers: dict) -> None:
    """Verify that prompts longer than 1,000 characters (1,500+ chars) no longer trigger HTTP 422."""
    long_prompt = (
        "Conduct an exhaustive, publication-grade academic literature review and meta-analytic synthesis on "
        "Bone Marrow Involvement in Malaria, focusing on parasite sequestration, gametocyte maturation niches, "
        "and the molecular mechanisms driving severe malarial anemia.\n\n"
        "Mandatory Requirements:\n"
        "1. Synthesize every paper across all attached comparison tables. Do not provide high-level summaries.\n"
        "2. Construct a comprehensive Master Comparison Matrix in Markdown comparing every study across: "
        "Study / Reference [n], Host & Species, Bone Marrow Compartment, Anemia Mechanism & Inflammatory Mediators, "
        "and Key Empirical Findings & Biomarkers.\n"
        "3. Dissect the dichotomy between asexual parasite sequestration (microvascular sinusoidal obstruction) and "
        "immature gametocyte accumulation in extravascular erythroblastic islands.\n"
        "4. Detail the molecular pathways of dyserythropoiesis (e.g. TNF-alpha suppression vs Stem Cell Growth Factor "
        "/ CLEC11A suppression by hemozoin deposits).\n"
        "5. Ground every metric, clinical setting (e.g. pediatric severe anemia in Kenya/Mozambique, adult cerebral malaria), "
        "and finding with precise inline citations [n].\n"
        "6. Conclude with an organized, numbered References section matching every citation.\n"
        + "Detailed methodology and benchmark specification: " * 10
    )
    assert len(long_prompt) > 1500  # Well above the old 1000 char threshold

    resp = await client.post(
        "/api/v1/reviews",
        headers=auth_headers,
        json={
            "topic": long_prompt,
            "records": [{"title": "GNN and Malaria Study", "year": 2022}],
            "max_tokens": 8000,
        },
    )
    assert resp.status_code == 202, f"Failed with {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body["status"] in ("queued", "running", "succeeded")
    review_id = body.get("result", {}).get("review_id")
    assert review_id is not None

    # Verify review was saved in DB without VARCHAR(1000) overflow error
    fetched = await client.get(f"/api/v1/reviews/{review_id}", headers=auth_headers)
    assert fetched.status_code == 200
    assert len(fetched.json()["topic"]) <= 950


class ComparisonFallbackClient(ORKGClient):
    """Simulates ORKG where /resources/ fails with 404, but /comparisons/ succeeds."""

    def __init__(self):
        super().__init__(oidc_url="http://mock", client_id="mock", api_url="http://mock")

    async def get_resource(self, resource_id: str, *, user_key: str | None = None) -> dict[str, Any]:
        if resource_id == "R1587227":
            raise RuntimeError("Resource endpoint returned 404 Not Found")
        return {"id": resource_id, "label": "Normal Resource"}

    async def get_comparison(self, comparison_id: str, *, user_key: str | None = None) -> dict[str, Any]:
        if comparison_id == "R1587227":
            return {
                "id": "R1587227",
                "label": "Bone Marrow Involvement in Malaria: Parasite Sequestration",
                "classes": ["Comparison"],
            }
        raise RuntimeError("Comparison not found")

    async def get_statements(self, subject_id: str, *, user_key: str | None = None, size: int = 1000) -> list[dict[str, Any]]:
        return [
            {
                "predicate": {"label": "compareContribution"},
                "object": {"id": "C101", "label": "Study 1 (Suppression of CLEC11A)", "_class": "resource"},
            }
        ] if subject_id == "R1587227" else [
            {"predicate": {"label": "Anemia mechanism"}, "object": {"label": "Suppression of stem cell growth factor", "_class": "literal"}},
        ]


async def test_orkg_comparison_fallback() -> None:
    """Verify that an ORKG comparison link resolves via /comparisons/ if /resources/ 404s."""
    client = ComparisonFallbackClient()
    records, unresolved = await resolve_many("https://orkg.org/comparisons/R1587227", client=client)

    assert len(unresolved) == 0, f"Unresolved: {unresolved}"
    assert len(records) >= 1
    assert records[0]["resolved"] is True
    assert "Bone Marrow Involvement in Malaria" in records[0]["title"]
    assert records[0]["orkg_id"] == "R1587227"
