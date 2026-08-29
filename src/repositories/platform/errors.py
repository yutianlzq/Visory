from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class PlatformDatabaseError(Exception):
    """Stable, public-safe PostgreSQL infrastructure error."""

    def __init__(
        self,
        *,
        error_code: str,
        public_message: str,
        retryable: bool,
        details: Mapping[str, Any] | None = None,
        cause: BaseException | None = None,
    ) -> None:
        super().__init__(public_message)
        self.error_code = error_code
        self.public_message = public_message
        self.retryable = retryable
        self.details = dict(details or {})
        self.cause = cause
        if cause is not None:
            self.__cause__ = cause

    def __str__(self) -> str:
        return f"{self.error_code}: {self.public_message}"


class DatabaseConfigurationError(PlatformDatabaseError):
    """Non-retryable PostgreSQL configuration failure."""


class DatabaseSecretError(PlatformDatabaseError):
    """Non-retryable secret-file validation failure."""
