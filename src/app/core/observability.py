"""Sentry wiring. A no-op when SENTRY_DSN is unset, so dev/CI never phone home."""

from __future__ import annotations

from .logging import get_logger


def init_sentry(dsn: str, *, environment: str, traces_sample_rate: float = 0.0) -> bool:
    if not dsn:
        return False
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration
    except ImportError:  # pragma: no cover - sentry is a hard dep, but stay defensive
        get_logger().warning("sentry_unavailable")
        return False

    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        traces_sample_rate=traces_sample_rate,
        integrations=[StarletteIntegration(), FastApiIntegration()],
        # Never let PII (API keys, request bodies) into events by default.
        send_default_pii=False,
    )
    get_logger().info("sentry_initialized", environment=environment)
    return True
