"""Follow-up chat grounded in a research session's Working Memory.

Answers a user's question using ONLY the session's retrieved/generated context (the
current synthesis and its sources), so the conversation stays evidence-grounded. Pure
service layer — the API wraps it and streams the answer."""

from __future__ import annotations

from typing import Any

from .llm.base import ChatMessage

RESEARCH_CHAT_SYSTEM = (
    "You are a research assistant answering follow-up questions about a specific research "
    "dataset and its synthesis. Use ONLY the provided context. Cite sources by their [n] "
    "marker where possible. If the answer is not supported by the context, say so plainly "
    "instead of inventing facts. Be concise and precise."
)

_MAX_SYNTHESIS_CHARS = 6000
_MAX_SOURCES = 60


def build_context(state: dict[str, Any]) -> str:
    """Assemble a grounded context string from the session's Working-Memory state."""
    state = state or {}
    parts: list[str] = []

    outputs = state.get("outputs") or []
    sources: list[dict[str, Any]] = []
    if outputs:
        latest = outputs[-1] or {}
        content = str(latest.get("content_md") or "").strip()
        if content:
            parts.append("Current synthesis:\n" + content[:_MAX_SYNTHESIS_CHARS])
        sources = (latest.get("structured") or {}).get("sources") or []

    if not sources:
        sources = state.get("orkg_records") or []

    if sources:
        lines = []
        for i, s in enumerate(sources[:_MAX_SOURCES], 1):
            title = str(s.get("title") or s.get("label") or "").strip()
            doi = str(s.get("doi") or "").strip()
            year = s.get("year")
            oid = s.get("orkg_id") or (s.get("source") or {}).get("resource_id")
            bits = [f"[{i}] {title}"]
            if year:
                bits.append(f"({year})")
            if doi:
                bits.append(f"DOI:{doi}")
            if oid:
                bits.append(f"ORKG:{oid}")
            lines.append(" ".join(bits).strip())
        parts.append("Sources:\n" + "\n".join(lines))

    return "\n\n".join(parts) or "(no research context is available yet)"


def build_chat_messages(
    state: dict[str, Any], history: list[dict[str, str]], question: str
) -> list[ChatMessage]:
    context = build_context(state)
    convo = ""
    for turn in history[-10:]:  # keep the last few turns for continuity
        role = turn.get("role", "user")
        text = str(turn.get("text") or "").strip()
        if text:
            convo += f"\n{role.upper()}: {text}"
    user = f"Research context:\n{context}\n"
    if convo:
        user += f"\nConversation so far:{convo}\n"
    user += f"\nQuestion: {question.strip()}"
    return [
        ChatMessage(role="system", content=RESEARCH_CHAT_SYSTEM),
        ChatMessage(role="user", content=user),
    ]
