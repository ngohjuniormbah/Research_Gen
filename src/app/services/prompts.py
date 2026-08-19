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
    "Answer the user's request below using ONLY the numbered sources. If the request is a "
    "literature review, include Introduction, Key Themes, Synthesis, and Conclusion, then "
    "References. If it asks for a comparison table, produce a Markdown table comparing the "
    "sources plus a short discussion. Otherwise, respond directly to what is asked. Use "
    "inline [n] citations throughout and finish with a '## References' section.\n\n"
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
