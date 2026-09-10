"""Verification test suite for Steps 1, 2, and 3.

Tests:
  1. Step 1: Export job produces a download URL and downloads without 404.
  2. Step 2: ORKG comparison with 48+ studies resolves all 48 without capping at 15.
  3. Step 3: Context builder ingests all 48 tables under 32,000 tokens without dropping any.
"""

from __future__ import annotations

import json
from typing import Any
from httpx import AsyncClient
import pytest

from app.config import get_settings
from app.schemas.source_record import SourceRecord
from app.services.context import build_context
from app.services.orkg.client import ORKGClient
from app.services.orkg.resolve import resolve_many


# --------------------------------------------------------------------------- #
# 1. Step 1 Test: Export and Download URL Verification                        #
# --------------------------------------------------------------------------- #

async def test_step1_export_download_flow(client: AsyncClient, auth_headers: dict) -> None:
    """Ensure that review generation, export to PDF, and download return HTTP 200 (no 404)."""
    submit = await client.post(
        "/api/v1/reviews",
        headers=auth_headers,
        json={
            "topic": "Graph Neural Networks Verification",
            "records": [{"title": "GNN Test Paper", "abstract": "Test abstract", "year": 2023}],
        },
    )
    assert submit.status_code == 202, submit.text
    review_id = submit.json()["result"]["review_id"]

    export_resp = await client.get(
        f"/api/v1/reviews/{review_id}/export?format=pdf",
        headers=auth_headers,
    )
    assert export_resp.status_code == 202, export_resp.text
    job_info = json.loads(export_resp.content)

    download_url = job_info.get("result", {}).get("download_url")
    assert download_url is not None, "download_url missing from export job result"
    assert download_url.startswith("/api/v1/reviews/exports/")

    api_base = "http://test"
    target_url = download_url if download_url.startswith("http") else f"{api_base}{download_url}"

    download_resp = await client.get(target_url)
    assert download_resp.status_code == 200, f"Expected 200, got {download_resp.status_code}"
    assert len(download_resp.content) > 0
    assert download_resp.content.startswith(b"%PDF")


# --------------------------------------------------------------------------- #
# 2. Step 2 Test: 48+ ORKG Comparison Tables Resolution                       #
# --------------------------------------------------------------------------- #

class Mock48ComparisonClient(ORKGClient):
    """Stub simulating an ORKG comparison resource linking 48 separate contributions."""

    def __init__(self, count: int = 48):
        super().__init__(oidc_url="http://mock", client_id="mock", api_url="http://mock")
        self.count = count

    async def get_resource(self, resource_id: str, *, user_key: str | None = None) -> dict[str, Any]:
        return {
            "id": resource_id,
            "label": f"Malaria Drug Efficacy Benchmark ({self.count} Studies)",
            "classes": ["Comparison"],
        }

    async def get_statements(
        self, subject_id: str, *, user_key: str | None = None, size: int = 1000
    ) -> list[dict[str, Any]]:
        if subject_id == "R_MALARIA_48":
            return [
                {
                    "predicate": {"label": "compareContribution", "id": "P_COMP"},
                    "object": {"id": f"C_{i}", "label": f"Study {i} - Clinical Trial", "_class": "resource"},
                }
                for i in range(1, self.count + 1)
            ]
        if subject_id.startswith("C_"):
            i = subject_id.split("_")[1]
            return [
                {"predicate": {"label": "Method"}, "object": {"label": f"Drug-Regimen-{i}", "_class": "literal"}},
                {"predicate": {"label": "Efficacy"}, "object": {"label": f"9{int(i) % 10}.5%", "_class": "literal"}},
                {"predicate": {"label": "Dataset"}, "object": {"label": f"Cohort-{i}", "_class": "literal"}},
                {"predicate": {"label": "year"}, "object": {"label": str(2020 + (int(i) % 5)), "_class": "literal"}},
                {"predicate": {"label": "doi"}, "object": {"label": f"10.1000/trial_{i}", "_class": "literal"}},
            ]
        return []


async def test_step2_resolve_48_comparison_tables() -> None:
    """Verify that all 48 comparison contributions are resolved and unpacked without cap."""
    client = Mock48ComparisonClient(count=48)
    records, unresolved = await resolve_many("https://orkg.org/comparison/R_MALARIA_48", client=client)

    assert len(unresolved) == 0
    assert len(records) == 49

    master = records[0]
    assert master["resolved"] is True
    assert "Contribution — Study 48 - Clinical Trial" in master["structured"]
    assert "Contribution — Study 1 - Clinical Trial" in master["structured"]

    unpacked_studies = records[1:]
    assert len(unpacked_studies) == 48
    assert unpacked_studies[0]["title"] == "Study 1 - Clinical Trial"
    assert unpacked_studies[-1]["title"] == "Study 48 - Clinical Trial"
    assert "Drug-Regimen-48" in unpacked_studies[-1]["abstract"]


# --------------------------------------------------------------------------- #
# 3. Step 3 Test: Context Window & 48-Table Rendering                         #
# --------------------------------------------------------------------------- #

def test_step3_context_budget_handles_48_tables() -> None:
    """Verify that 48 multi-column tables fit into the 32,000 token budget without dropping."""
    settings = get_settings()
    assert settings.llm_max_context_tokens >= 32000

    records = [
        SourceRecord(
            title=f"Survey Study {i}",
            abstract=f"Comprehensive evaluation of approach {i} across benchmark tasks.",
            year=2021 + (i % 4),
            doi=f"10.5555/study_{i}",
            raw={
                "tables": [
                    {
                        "page": 1,
                        "rows": [
                            ["Architecture", "Dataset", "Metric", "Score"],
                            [f"Model-Variant-{i}", f"Benchmark-{i}", "Accuracy", f"9{i % 10}.8%"],
                            [f"Baseline-{i}", f"Benchmark-{i}", "Accuracy", f"8{i % 10}.1%"],
                        ],
                    }
                ]
            },
        )
        for i in range(1, 49)
    ]

    bundle = build_context(records, token_budget=settings.llm_max_context_tokens)

    assert bundle.strategy == "direct"
    assert bundle.included == 48
    assert bundle.dropped == 0

    for i in range(1, 49):
        assert f"Survey Study {i}" in bundle.sources_block
        assert f"Model-Variant-{i}" in bundle.sources_block
        assert f"Benchmark-{i}" in bundle.sources_block
