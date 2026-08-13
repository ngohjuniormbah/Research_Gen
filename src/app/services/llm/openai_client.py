"""A single OpenAI-compatible chat client. Works against any endpoint that speaks the
`/chat/completions` schema — Ollama locally, or a hosted OpenAI-compatible service.
Selecting a different model is purely config (base_url/model/api_key); no code change."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx

from .base import ChatMessage


class LLMError(Exception):
    pass


class OpenAICompatProvider:
    def __init__(
        self,
        key: str,
        *,
        base_url: str,
        model: str,
        api_key: str = "",
        timeout_s: float = 120.0,
    ) -> None:
        self.key = key
        self.model = model
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout_s

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    def _payload(
        self, messages: list[ChatMessage], max_tokens: int, temperature: float, stream: bool
    ) -> dict:
        return {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": stream,
        }

    async def generate(
        self, messages: list[ChatMessage], *, max_tokens: int = 1024, temperature: float = 0.2
    ) -> str:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                f"{self._base_url}/chat/completions",
                headers=self._headers(),
                json=self._payload(messages, max_tokens, temperature, stream=False),
            )
        if resp.status_code >= 400:
            raise LLMError(f"provider {self.key} returned {resp.status_code}: {resp.text[:500]}")
        data = resp.json()
        try:
            return str(data["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"unexpected response from {self.key}: {exc}") from exc

    async def stream(
        self, messages: list[ChatMessage], *, max_tokens: int = 1024, temperature: float = 0.2
    ) -> AsyncIterator[str]:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            async with client.stream(
                "POST",
                f"{self._base_url}/chat/completions",
                headers=self._headers(),
                json=self._payload(messages, max_tokens, temperature, stream=True),
            ) as resp:
                if resp.status_code >= 400:
                    body = await resp.aread()
                    raise LLMError(
                        f"provider {self.key} returned {resp.status_code}: {body[:500]!r}"
                    )
                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    payload = line[len("data:"):].strip()
                    if payload == "[DONE]":
                        break
                    try:
                        delta = json.loads(payload)["choices"][0]["delta"].get("content")
                    except (json.JSONDecodeError, KeyError, IndexError, TypeError):
                        continue
                    if delta:
                        yield delta
