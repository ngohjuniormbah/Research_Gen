"""LLM orchestration for review generation: assemble context, call the provider, and
parse the model's Markdown into a structured review (sections + citations + sources).

Pure service layer — no FastAPI, no DB. The worker/job layer wraps this."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from ..schemas.source_record import SourceRecord
from .context import build_context
from .llm.base import ChatMessage, LLMProvider
from .prompts import SYSTEM_PROMPT, render_map_prompt, render_review_prompt

_HEADING_RE = re.compile(r"^#{1,3}\s+(.*)$", re.MULTILINE)
_CITATION_RE = re.compile(r"\[(\d+)\]")
# Chunk size for the map step, in sources per chunk.
_MAP_CHUNK = 10


@dataclass
class ReviewResult:
    content_md: str
    structured: dict[str, Any]
    provider: str
    model: str
    sources: list[SourceRecord] = field(default_factory=list)


def _parse_sections(markdown: str) -> list[dict[str, str]]:
    matches = list(_HEADING_RE.finditer(markdown))
    if not matches:
        return [{"heading": "Body", "content": markdown.strip()}]
    sections = []
    for i, match in enumerate(matches):
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(markdown)
        heading = match.group(1).strip()
        content = markdown[start:end].strip()
        # Skip the top-level title (h1) when it has no body of its own.
        if i == 0 and not content and match.group(0).startswith("# "):
            continue
        sections.append({"heading": heading, "content": content})
    return sections


def _extract_citations(
    markdown: str, sources: list[SourceRecord]
) -> list[dict[str, Any]]:
    seen: dict[int, dict[str, Any]] = {}
    for match in _CITATION_RE.finditer(markdown):
        num = int(match.group(1))
        if num in seen:
            continue
        title = sources[num - 1].title if 1 <= num <= len(sources) else ""
        seen[num] = {"marker": f"[{num}]", "source_index": num, "title": title}
    return [seen[k] for k in sorted(seen)]


def _sources_manifest(sources: list[SourceRecord]) -> list[dict[str, Any]]:
    return [
        {
            "index": i + 1,
            "title": s.title,
            "authors": s.authors,
            "year": s.year,
            "venue": s.venue,
            "doi": s.doi,
        }
        for i, s in enumerate(sources)
    ]


async def _map_reduce_sources(
    provider: LLMProvider, topic: str, sources: list[SourceRecord], token_budget: int
) -> str:
    """Compress an oversized corpus into a smaller, citation-preserving digest by
    summarizing it in chunks (the "map"), then return the concatenated digest that the
    final "reduce" review pass consumes."""
    digests: list[str] = []
    for start in range(0, len(sources), _MAP_CHUNK):
        chunk = sources[start : start + _MAP_CHUNK]
        bundle = build_context(chunk, token_budget)
        # Renumber the digest markers to absolute source positions.
        def _renumber(match: re.Match[str], offset: int = start) -> str:
            return f"[{int(match.group(1)) + offset}]"

        block = re.sub(r"\[(\d+)\]", _renumber, bundle.sources_block)
        prompt = render_map_prompt(topic, block)
        digests.append(
            await provider.generate(
                [
                    ChatMessage(role="system", content=SYSTEM_PROMPT),
                    ChatMessage(role="user", content=prompt),
                ],
                max_tokens=512,
            )
        )
    return "\n\n".join(digests)


async def generate_review_content(
    *,
    provider: LLMProvider,
    topic: str,
    records: list[SourceRecord],
    token_budget: int = 8000,
    max_tokens: int = 1500,
) -> ReviewResult:
    bundle = build_context(records, token_budget)
    used_sources = bundle.sources

    if bundle.strategy == "map-reduce" and bundle.dropped > 0:
        # Corpus overflowed even after compression: summarize everything first, then
        # write the review over the digest so no source is silently dropped.
        digest = await _map_reduce_sources(provider, topic, records, token_budget)
        sources_block = digest
        used_sources = records
    else:
        sources_block = bundle.sources_block

    user_prompt = render_review_prompt(topic, sources_block)
    messages: list[ChatMessage] = [
        ChatMessage(role="system", content=SYSTEM_PROMPT),
        ChatMessage(role="user", content=user_prompt),
    ]
    content = await provider.generate(messages, max_tokens=max_tokens)

    structured = {
        "sections": _parse_sections(content),
        "citations": _extract_citations(content, used_sources),
        "sources": _sources_manifest(used_sources),
        "strategy": bundle.strategy,
        "provider": provider.key,
        "model": provider.model,
    }
    return ReviewResult(
        content_md=content,
        structured=structured,
        provider=provider.key,
        model=provider.model,
        sources=used_sources,
    )
