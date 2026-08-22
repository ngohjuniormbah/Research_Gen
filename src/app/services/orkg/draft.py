"""Build an ORKG submission draft from a generated review.

This produces a structured, human-reviewable draft — it never publishes to ORKG. Actual
write-back must go through the user's connected ORKG account and an explicit approval step
(and only via officially supported ORKG write APIs). Until that path is verified end to
end, the product exports this draft so nothing is silently submitted."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from ...models import Review

DRAFT_NOTE = (
    "Draft only — review and submit through your connected ORKG account. "
    "World Model Of Science never auto-publishes to ORKG."
)


def build_orkg_draft(review: Review) -> dict[str, Any]:
    structured = review.structured or {}
    sources = structured.get("sources") or []
    draft_sources = []
    for s in sources:
        if not isinstance(s, dict):
            continue
        draft_sources.append({
            "index": s.get("index"),
            "title": s.get("title", ""),
            "authors": s.get("authors", []),
            "year": s.get("year"),
            "venue": s.get("venue", ""),
            "doi": s.get("doi", ""),
        })
    return {
        "kind": "orkg_contribution_draft",
        "status": "draft",
        "note": DRAFT_NOTE,
        "title": review.topic,
        "generated_by": {"provider": review.provider, "model": review.model},
        "created_at": datetime.now(UTC).isoformat(),
        "sources": draft_sources,
        "citations": structured.get("citations", []),
        "content_markdown": review.content_md,
        "csl_references": review.csl_json or [],
        "provenance": {
            "system": "world-model-of-science",
            "review_id": str(review.id),
            "strategy": structured.get("strategy"),
        },
    }
