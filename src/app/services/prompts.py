"""Prompt templates that steer the model toward a STRUCTURED literature review with
inline numbered citations that map back to the provided sources."""

from __future__ import annotations

SYSTEM_PROMPT = (
    "You are a meticulous research assistant that writes structured academic "
    "literature reviews. You only use the numbered sources provided. Every claim that "
    "draws on a source must carry an inline citation marker like [1] or [2] referring "
    "to that source's number. Never invent sources or citation numbers beyond those "
    "given. Write in Markdown using '## ' section headings and finish with a "
    "'## References' section listing each cited source by its number."
)

REVIEW_INSTRUCTIONS = (
    "Write a structured literature review on the topic below using ONLY the numbered "
    "sources. Include these sections: Introduction, Key Themes, Synthesis, and "
    "Conclusion, followed by References. Use inline [n] citations throughout.\n\n"
    "Topic: {topic}\n\n"
    "Sources:\n{sources}\n"
)

# Map-reduce: summarize one chunk of sources into a compact, citation-preserving digest.
MAP_INSTRUCTIONS = (
    "Summarize the following numbered sources into concise bullet points. Preserve each "
    "source's number so citations stay valid. Keep it factual and brief.\n\n"
    "Topic: {topic}\n\nSources:\n{sources}\n"
)


def render_review_prompt(topic: str, sources_block: str) -> str:
    return REVIEW_INSTRUCTIONS.format(topic=topic, sources=sources_block)


def render_map_prompt(topic: str, sources_block: str) -> str:
    return MAP_INSTRUCTIONS.format(topic=topic, sources=sources_block)
