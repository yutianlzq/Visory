from __future__ import annotations

from datetime import datetime
from typing import Any, Annotated, Literal

from pydantic import AwareDatetime, Field

from .base import PlatformContractModel


PLATFORM_API_SCHEMA_VERSION = "1.0.0"
REQUEST_ID_PATTERN = r"^req_[0-9a-f]{32}$"
RequestID = Annotated[str, Field(pattern=REQUEST_ID_PATTERN)]


class PlatformResponseMeta(PlatformContractModel):
    """C-010 metadata shared by all successful platform responses."""

    request_id: RequestID
    schema_version: Literal[PLATFORM_API_SCHEMA_VERSION]
    generated_at: AwareDatetime
    data_snapshot_id: str | None
    warnings: tuple[str, ...]


class PlatformPage(PlatformContractModel):
    """Opaque cursor metadata for C-010 list responses."""

    cursor: str | None
    next_cursor: str | None
    limit: Annotated[int, Field(ge=1, le=1000)]
    has_more: bool


class PlatformAPIError(PlatformContractModel):
    """Stable public error fields required by C-010."""

    code: Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9_]{2,63}$")]
    message: Annotated[str, Field(min_length=1, max_length=200)]
    details: dict[str, Any]
    retryable: bool
    request_id: RequestID


_SUCCESS_EXAMPLE = {
    "data": {"resource_id": "example"},
    "meta": {
        "request_id": "req_0123456789abcdef0123456789abcdef",
        "schema_version": PLATFORM_API_SCHEMA_VERSION,
        "generated_at": "2026-08-27T12:00:00+08:00",
        "data_snapshot_id": None,
        "warnings": [],
    },
}
_LIST_EXAMPLE = {
    **_SUCCESS_EXAMPLE,
    "data": [{"resource_id": "example"}],
    "page": {
        "cursor": None,
        "next_cursor": None,
        "limit": 50,
        "has_more": False,
    },
}
_ERROR_EXAMPLE = {
    "error": {
        "code": "RESOURCE_NOT_FOUND",
        "message": "资源不存在",
        "details": {},
        "retryable": False,
        "request_id": "req_0123456789abcdef0123456789abcdef",
    }
}


class PlatformSuccessEnvelope(PlatformContractModel):
    """C-010 object success response."""

    data: dict[str, Any]
    meta: PlatformResponseMeta

    model_config = PlatformContractModel.model_config | {"json_schema_extra": {"examples": [_SUCCESS_EXAMPLE]}}


class PlatformListEnvelope(PlatformContractModel):
    """C-010 list success response with opaque cursor metadata."""

    data: list[dict[str, Any]]
    meta: PlatformResponseMeta
    page: PlatformPage

    model_config = PlatformContractModel.model_config | {"json_schema_extra": {"examples": [_LIST_EXAMPLE]}}


class PlatformErrorEnvelope(PlatformContractModel):
    """C-010 error response."""

    error: PlatformAPIError

    model_config = PlatformContractModel.model_config | {"json_schema_extra": {"examples": [_ERROR_EXAMPLE]}}


def response_meta(
    *,
    request_id: str,
    generated_at: datetime,
    data_snapshot_id: str | None,
    warnings: tuple[str, ...] = (),
) -> PlatformResponseMeta:
    """Build validated response metadata from an already resolved request ID."""

    return PlatformResponseMeta(
        request_id=request_id,
        schema_version=PLATFORM_API_SCHEMA_VERSION,
        generated_at=generated_at,
        data_snapshot_id=data_snapshot_id,
        warnings=warnings,
    )
