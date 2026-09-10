"""Prompt/context assembly. Lays the normalized sources out as a numbered block that
fits a token budget, preserving all comparison tables and empirical rows."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..schemas.source_record import SourceRecord

# Rough heuristic: ~4 characters per token.
_CHARS_PER_TOKEN = 4
_MIN_BLOCK_TOKENS = 120

# High-capacity thresholds to support 48+ comparison tables without truncation
_DIRECT_PROSE_CHARS = 35000   # Increased from 6,000 to retain complete survey text
_TBL_MAX_ROWS = 150           # Increased from 30 to support long comparison tables
_TBL_MAX_COLS = 30            # Increased from 12 for wide benchmark matrices
_TBL_CELL_CHARS = 120         # Increased from 60 to prevent metric truncation


def _render_tables(record: SourceRecord) -> str:
    """Render EVERY structured table extracted from a source as a text grid."""
    raw = record.raw if isinstance(record.raw, dict) else {}
    tables = raw.get("tables")
    if not isinstance(tables, list) or not tables:
        return ""
    out: list[str] = []
    for n, tbl in enumerate(tables, start=1):
        rows = (tbl or {}).get("rows") if isinstance(tbl, dict) else None
        if not isinstance(rows, list) or not rows:
            continue
        page = (tbl or {}).get("page")
        label = f"Table {n}" + (f" (page {page})" if page else "")
        lines = [label]
        for row in rows[:_TBL_MAX_ROWS]:
            cells = [
                str(c).replace("\n", " ").strip()[:_TBL_CELL_CHARS]
                for c in row[:_TBL_MAX_COLS]
            ]
            lines.append("| " + " | ".join(cells) + " |")
        out.append("\n".join(lines))
    return ("\n\n".join(out)).strip()


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

    tables_block = _render_tables(record)
    prose = (record.abstract or "").strip()
    full = (record.full_text or "").strip()
    if full and full != prose:
        prose = f"{prose}\n{full}" if prose else full

    if abstract_chars is not None:
        prose = prose[: max(0, abstract_chars)]
    else:
        prose = prose[:_DIRECT_PROSE_CHARS]

    block = f"[{index}] {header}"
    if tables_block:
        block += f"\n    [Structured Comparison Tables — Synthesize Every Row]\n{tables_block}"
    if prose.strip():
        block += f"\n    {prose.strip()}"
    return block


def build_context(
    records: list[SourceRecord], token_budget: int
) -> ContextBundle:
    """Assemble a numbered sources block within token_budget tokens."""
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

    # Map-reduce fallback: give each source an equal slice of the expanded budget
    per_source_tokens = max(
        _MIN_BLOCK_TOKENS, token_budget // max(1, len(records)))
    abstract_chars = per_source_tokens * _CHARS_PER_TOKEN

    kept: list[SourceRecord] = []
    blocks: list[str] = []
    used = 0
    for record in records:
        block = _format_source(len(kept) + 1, record,
                               abstract_chars=abstract_chars)
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
