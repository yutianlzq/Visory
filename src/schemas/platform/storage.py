from __future__ import annotations

import re

from pydantic import Field, field_validator

from .base import PlatformContractModel
from .enums import StorageBackend, StorageNamespace


_MEDIA_TYPE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9!#$&^_.+-]*/[a-z0-9][a-z0-9!#$&^_.+-]*$")


class StorageRef(PlatformContractModel):
    storage_backend: StorageBackend
    storage_namespace: StorageNamespace
    relative_path: str
    content_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    media_type: str
    size_bytes: int = Field(ge=0)

    @field_validator("relative_path")
    @classmethod
    def validate_relative_path(cls, value: str) -> str:
        if not value or value.startswith("/") or "\\" in value:
            raise ValueError("relative_path must be a non-empty relative POSIX path")
        if any(ord(character) < 32 for character in value):
            raise ValueError("relative_path cannot contain control characters")
        segments = value.split("/")
        if any(segment in {"", ".", ".."} for segment in segments):
            raise ValueError("relative_path cannot contain empty, dot, or parent segments")
        if any(":" in segment for segment in segments):
            raise ValueError("relative_path cannot contain drive or URI-style path segments")
        return value

    @field_validator("media_type")
    @classmethod
    def validate_media_type(cls, value: str) -> str:
        if not _MEDIA_TYPE_PATTERN.fullmatch(value):
            raise ValueError("media_type must be a canonical MIME media type")
        return value
