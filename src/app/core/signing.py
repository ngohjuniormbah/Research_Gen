"""HMAC-signed, expiring tokens for temporary download URLs. No DB lookup needed to
validate — the token carries its own (signed) payload and expiry."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any


class SignatureError(Exception):
    pass


def _b64e(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64d(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


class TokenSigner:
    def __init__(self, secret: str) -> None:
        self._secret = secret.encode("utf-8")

    def _sign(self, payload_b64: str) -> str:
        digest = hmac.new(self._secret, payload_b64.encode("ascii"), hashlib.sha256).digest()
        return _b64e(digest)

    def sign(self, data: dict[str, Any], *, ttl_s: int) -> str:
        payload = {**data, "exp": int(time.time()) + ttl_s}
        payload_b64 = _b64e(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
        return f"{payload_b64}.{self._sign(payload_b64)}"

    def verify(self, token: str) -> dict[str, Any]:
        try:
            payload_b64, signature = token.split(".", 1)
        except ValueError as exc:
            raise SignatureError("malformed token") from exc
        expected = self._sign(payload_b64)
        if not hmac.compare_digest(expected, signature):
            raise SignatureError("bad signature")
        payload: dict[str, Any] = json.loads(_b64d(payload_b64))
        if int(payload.get("exp", 0)) < int(time.time()):
            raise SignatureError("token expired")
        return payload
