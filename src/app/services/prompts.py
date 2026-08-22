"""Prompt templates that steer the model toward a STRUCTURED literature review with
inline numbered citations that map back to the provided sources."""

from __future__ import annotations

SYSTEM_PROMPT = (
    "You are a meticulous research assistant. Produce exactly what the user asks for — a "
    "literature review, a comparison table, a synthesis, a summary, or another analysis — "
    "using ONLY the numbered sources provided. Every claim that draws on a source must "
    "carry an inline citation marker like [1] or [2] referring to that source's number. "
    "Never invent sources or citation numbers beyond those given. Write in Markdown, using "
    "'## ' section headings and Markdown tables when a table or comparison is requested, "
    "and finish with a '## References' section listing each cited source by its number. If "
    "the provided sources cannot support the request (for example an unreadable or empty "
    "document), say so briefly and clearly instead of inventing content."
)

REVIEW_INSTRUCTIONS = (
    "Answer the user's request below using ONLY the numbered sources. Be thorough, "
    "analytical and scholarly — synthesize and compare across the sources rather than "
    "listing shallow one-line summaries. Discuss methods, datasets, metrics, results, "
    "agreements, contradictions, and gaps where the sources support it.\n"
    "If a source is itself a document that contains SEVERAL comparison tables or studies, "
    "address EACH of them separately (a subsection per table/study), never just the first.\n"
    "For a literature review, use these sections: Introduction, Background, Key Themes, "
    "Methodological Comparison, Results & Findings, Research Gaps, Conclusion. For a "
    "comparison request, produce a Markdown table (Paper | Method | Dataset | Metric | "
    "Result) plus a short discussion. Otherwise respond directly to what is asked.\n"
    "Use inline [n] citations throughout. Finish with a '## References' section that lists "
    "EVERY numbered source with its title, authors, year, and DOI/ORKG id when available. "
    "Do not fabricate bibliographic details — if a field is unknown, omit it.\n\n"
    "User request: {topic}\n{instructions}"
    "Sources:\n{sources}\n"
)

# Map-reduce: summarize one chunk of sources into a compact, citation-preserving digest.
MAP_INSTRUCTIONS = (
    "Summarize the following numbered sources into concise bullet points. Preserve each "
    "source's number so citations stay valid. Keep it factual and brief.\n\n"
    "Topic: {topic}\n\nSources:\n{sources}\n"
)


def render_review_prompt(topic: str, sources_block: str, instructions: str = "") -> str:
    # The optional free-text instruction lets a user steer the review in natural language
    # ("focus on methods since 2020", "keep it under 400 words", etc.).
    instruction_block = (
        f"Additional instructions from the user: {instructions.strip()}\n\n"
        if instructions and instructions.strip()
        else "\n"
    )
    return REVIEW_INSTRUCTIONS.format(
        topic=topic, instructions=instruction_block, sources=sources_block
    )


def render_map_prompt(topic: str, sources_block: str) -> str:
    return MAP_INSTRUCTIONS.format(topic=topic, sources=sources_block)
