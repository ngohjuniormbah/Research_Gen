"""Global exception handlers producing one consistent error envelope everywhere.

Registered on the app in main.py. Clients never see stack traces — unexpected errors
are logged (and sent to Sentry) but rendered as a generic internal_error."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from ..core.errors import AppError, ErrorCode
from ..core.logging import get_logger


def _request_id(request: Request) -> str | None:
    rid = getattr(request.state, "request_id", None)
    return rid or request.headers.get("x-request-id")


def _render(error: AppError, request: Request) -> JSONResponse:
    return JSONResponse(
        status_code=error.status,
        content=error.envelope(_request_id(request)),
        headers=error.headers or None,
    )


async def _handle_app_error(request: Request, exc: AppError) -> JSONResponse:
    return _render(exc, request)


async def _handle_validation_error(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    details: list[dict[str, Any]] = []
    for err in exc.errors():
        loc = [str(p) for p in err.get("loc", []) if p not in ("body",)]
        details.append(
            {"field": ".".join(loc) or "body", "message": err.get("msg", ""),
             "type": err.get("type", "")}
        )
    app_error = AppError(
        ErrorCode.VALIDATION, "request validation failed", status=422, details=details
    )
    return _render(app_error, request)


async def _handle_http_exception(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    # Map bare HTTPExceptions (e.g. 404 for unknown routes) into the envelope.
    code = {
        401: ErrorCode.UNAUTHORIZED,
        403: ErrorCode.FORBIDDEN,
        404: ErrorCode.NOT_FOUND,
        405: ErrorCode.NOT_FOUND,
        409: ErrorCode.CONFLICT,
    }.get(exc.status_code, ErrorCode.INTERNAL if exc.status_code >= 500 else "http_error")
    message = exc.detail if isinstance(exc.detail, str) else "request failed"
    app_error = AppError(code, message, status=exc.status_code)
    if isinstance(exc.headers, dict):
        app_error.headers = exc.headers
    return _render(app_error, request)


async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
    get_logger().error("unhandled_exception", error=str(exc), error_type=type(exc).__name__)
    app_error = AppError(
        ErrorCode.INTERNAL, "an internal error occurred", status=500
    )
    return _render(app_error, request)


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _handle_app_error)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, _handle_validation_error)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, _handle_http_exception)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, _handle_unexpected)
