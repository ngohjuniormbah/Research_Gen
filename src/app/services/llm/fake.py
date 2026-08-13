"""Deterministic, offline LLM provider. Same input -> same output, no network, no API
key. Every test and local dev run uses this; it never calls a real model.

It reads the numbered sources embedded in the prompt and emits a structured, cited
Markdown literature review so the downstream parser has real sections and citations
to work with."""

from __future__ import annotations

import re
from collections.abc import AsyncIterator

from .base import ChatMessage

_SOURCE_RE = re.compile(r"^\[(\d+)\]\s*(.+)$", re.MULTILINE)
_TOPIC_RE = re.compile(r"Topic:\s*(.+)", re.IGNORECASE)


class FakeProvider:
    def __init__(self, key: str = "fake", model: str = "fake-1") -> None:
        self.key = key
        self.model = model

    def _render(self, messages: list[ChatMessage]) -> str:
        prompt = "\n\n".join(m["content"] for m in messages)
        topic_match = _TOPIC_RE.search(prompt)
        topic = topic_match.group(1).strip() if topic_match else "the surveyed literature"

        sources = _SOURCE_RE.findall(prompt)
        if not sources:
            sources = [("1", "an unspecified source")]
        markers = [f"[{idx}]" for idx, _ in sources]

        intro_cites = " ".join(markers[:3])
        themes = "\n".join(
            f"- Source {idx} contributes: {title[:120]} {marker}"
            for (idx, title), marker in zip(sources, markers, strict=False)
        )
        refs = "\n".join(f"[{idx}] {title}" for idx, title in sources)

        return (
            f"# Literature Review: {topic}\n\n"
            f"## Introduction\n"
            f"This review synthesizes {len(sources)} sources on {topic}. "
            f"The corpus establishes the problem space and motivates study {intro_cites}.\n\n"
            f"## Key Themes\n"
            f"Several themes recur across the corpus:\n{themes}\n\n"
            f"## Synthesis\n"
            f"Taken together, the sources converge on shared methods while differing in "
            f"scope and evaluation {' '.join(markers)}.\n\n"
            f"## Conclusion\n"
            f"The literature on {topic} is maturing; open questions remain around "
            f"generalization and reproducibility {markers[0]}.\n\n"
            f"## References\n{refs}\n"
        )

    async def generate(
        self, messages: list[ChatMessage], *, max_tokens: int = 1024, temperature: float = 0.2
    ) -> str:
        return self._render(messages)

    async def stream(
        self, messages: list[ChatMessage], *, max_tokens: int = 1024, temperature: float = 0.2
    ) -> AsyncIterator[str]:
        for chunk in self._render(messages).split("\n\n"):
            yield chunk + "\n\n"
