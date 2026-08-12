from typing import Any


class AppError(Exception):
    """Single application error type -> consistent JSON envelope for the frontend."""

    def __init__(
        self,
        code: str,
        message: str,
        status: int = 400,
        details: list[Any] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.status = status
        self.details = details or []
        super().__init__(message)
