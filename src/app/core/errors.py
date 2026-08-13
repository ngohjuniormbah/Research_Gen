"""Single application error type + a global-handler-friendly envelope.

Every client-facing failure becomes an AppError, which the API layer renders as a
consistent envelope: {"error": {code, message, details, request_id}}. Stack traces are
never sent to clients."""

from __future__ import annotations

from typing import Any


class ErrorCode:
    """Canonical, stable error codes. The frontend switches on these, so treat them as
    an API contract (documented in docs/api-contract.md)."""

    VALIDATION = "validation_error"
    UNAUTHORIZED = "unauthorized"
    FORBIDDEN = "forbidden"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"
    PAYLOAD_TOO_LARGE = "payload_too_large"
    UNSUPPORTED_MEDIA = "unsupported_media_type"
    RATE_LIMITED = "rate_limited"
    UNKNOWN_PROVIDER = "unknown_provider"
    SPARQL_REJECTED = "sparql_rejected"
    ORKG_AUTH_FAILED = "orkg_auth_failed"
    UPSTREAM_UNAVAILABLE = "upstream_unavailable"
    INTERNAL = "internal_error"


class AppError(Exception):
    """The one application error type. Note the (code, message, status) ordering is kept
    from Step 2 for call-site compatibility; ``details`` carries field-level info."""

    def __init__(
        self,
        code: str,
        message: str,
        status: int = 400,
        details: list[Any] | None = None,
        *,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.status = status
        self.details = details or []
        self.headers = headers or {}
        super().__init__(message)

    def envelope(self, request_id: str | None = None) -> dict[str, Any]:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details,
                "request_id": request_id,
            }
        }


# --- convenience constructors (keep call sites terse and consistent) --------- #
def not_found(message: str = "resource not found") -> AppError:
    return AppError(ErrorCode.NOT_FOUND, message, status=404)


def unauthorized(message: str = "authentication required") -> AppError:
    return AppError(ErrorCode.UNAUTHORIZED, message, status=401)


def validation_error(message: str, details: list[Any] | None = None) -> AppError:
    return AppError(ErrorCode.VALIDATION, message, status=422, details=details)


def rate_limited(message: str, retry_after: int) -> AppError:
    return AppError(
        ErrorCode.RATE_LIMITED,
        message,
        status=429,
        details=[{"retry_after": retry_after}],
        headers={"Retry-After": str(retry_after)},
    )
