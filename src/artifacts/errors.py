from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class ArtifactError(RuntimeError):
    """Stable, sanitized Artifact boundary error."""

    def __init__(
        self,
        *,
        error_code: str,
        public_message: str,
        retryable: bool = False,
        details: Mapping[str, Any] | None = None,
        cause: BaseException | None = None,
    ) -> None:
        super().__init__(public_message)
        self.error_code = error_code
        self.public_message = public_message
        self.retryable = retryable
        self.details = dict(details or {})
        self.__cause__ = cause

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}(error_code={self.error_code!r}, "
            f"public_message={self.public_message!r}, retryable={self.retryable!r}, "
            f"details={self.details!r})"
        )


class ArtifactStorageError(ArtifactError):
    pass


class ArtifactPublishError(ArtifactError):
    pass


class ArtifactIntegrityError(ArtifactError):
    pass


class ArtifactManifestError(ArtifactError):
    pass
