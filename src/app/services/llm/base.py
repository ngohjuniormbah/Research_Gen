from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol, TypedDict, runtime_checkable


class ChatMessage(TypedDict):
    role: str  # "system" | "user" | "assistant"
    content: str


@runtime_checkable
class LLMProvider(Protocol):
    """The one interface the pipeline talks to. Backed by an OpenAI-compatible client
    for real models and by the deterministic fake provider in tests."""

    key: str
    model: str

    async def generate(
        self, messages: list[ChatMessage], *, max_tokens: int = 1024, temperature: float = 0.2
    ) -> str: ...

    def stream(
        self, messages: list[ChatMessage], *, max_tokens: int = 1024, temperature: float = 0.2
    ) -> AsyncIterator[str]: ...
