"""Request-context + access-log middleware.

Assigns a request_id (honoring an inbound X-Request-ID), binds it into structlog's
contextvars, times the request, and emits one structured access log per request with
method / path / status / latency_ms / key_prefix."""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable

import structlog
from starlette.requests import Request
from starlette.responses import Response

from ..core.logging import get_logger


async def request_context_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    request.state.request_id = request_id
    # key_prefix is filled in by the auth dependency once the caller is known.
    request.state.key_prefix = None

    structlog.contextvars.bind_contextvars(request_id=request_id)
    start = time.perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        response.headers["x-request-id"] = request_id
        return response
    finally:
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        get_logger().info(
            "access",
            method=request.method,
            path=request.url.path,
            status=status_code,
            latency_ms=latency_ms,
            key_prefix=getattr(request.state, "key_prefix", None),
        )
        structlog.contextvars.clear_contextvars()
