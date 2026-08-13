"""Prompt/context assembly. Lays the normalized sources out as a numbered block that
fits a token budget, falling back to a map-reduce compression when the corpus is too
large to send verbatim."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..schemas.source_record import SourceRecord

# Rough heuristic: ~4 characters per token. Good enough for budgeting.
_CHARS_PER_TOKEN = 4
_MIN_BLOCK_TOKENS = 40  # floor per source so every kept source stays citable


def estimate_tokens(text: str) -> int:
    return (len(text) + _CHARS_PER_TOKEN - 1) // _CHARS_PER_TOKEN


@dataclass
class ContextBundle:
    sources_block: str
    strategy: str  # "direct" | "map-reduce"
    included: int
    dropped: int
    token_estimate: int
    sources: list[SourceRecord] = field(default_factory=list)


def _format_source(index: int, record: SourceRecord, *, abstract_chars: int | None) -> str:
    authors = ", ".join(record.authors[:8])
    if len(record.authors) > 8:
        authors += " et al."
    header_bits = [record.title or "Untitled"]
    meta = []
    if authors:
        meta.append(authors)
    if record.year:
        meta.append(str(record.year))
    if record.venue:
        meta.append(record.venue)
    if record.doi:
        meta.append(f"doi:{record.doi}")
    header = header_bits[0] + (f". {'; '.join(meta)}" if meta else "")

    body = record.abstract or (record.full_text or "")[:2000]
    if abstract_chars is not None:
        body = body[:abstract_chars]
    body = body.strip()
    block = f"[{index}] {header}"
    if body:
        block += f"\n    {body}"
    return block


def build_context(
    records: list[SourceRecord], token_budget: int
) -> ContextBundle:
    """Assemble a numbered sources block within ``token_budget`` tokens.

    Strategy:
      * "direct" — every source rendered in full fits the budget.
      * "map-reduce" — compress each source (truncate abstracts) so more fit; if the
        corpus still overflows even at the per-source floor, keep as many as fit and
        report the number dropped.
    """
    if not records:
        return ContextBundle(sources_block="", strategy="direct", included=0, dropped=0,
                             token_estimate=0, sources=[])

    direct_blocks = [
        _format_source(i + 1, r, abstract_chars=None) for i, r in enumerate(records)
    ]
    direct_text = "\n\n".join(direct_blocks)
    if estimate_tokens(direct_text) <= token_budget:
        return ContextBundle(
            sources_block=direct_text,
            strategy="direct",
            included=len(records),
            dropped=0,
            token_estimate=estimate_tokens(direct_text),
            sources=list(records),
        )

    # Map-reduce fallback: give each source an equal slice of the budget.
    per_source_tokens = max(_MIN_BLOCK_TOKENS, token_budget // max(1, len(records)))
    abstract_chars = per_source_tokens * _CHARS_PER_TOKEN

    kept: list[SourceRecord] = []
    blocks: list[str] = []
    used = 0
    for record in records:
        block = _format_source(len(kept) + 1, record, abstract_chars=abstract_chars)
        cost = estimate_tokens(block)
        if used + cost > token_budget and kept:
            break
        kept.append(record)
        blocks.append(block)
        used += cost

    return ContextBundle(
        sources_block="\n\n".join(blocks),
        strategy="map-reduce",
        included=len(kept),
        dropped=len(records) - len(kept),
        token_estimate=used,
        sources=kept,
    )
