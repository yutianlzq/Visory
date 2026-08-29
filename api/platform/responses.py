from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

from fastapi import Request

from api.platform.request_id import get_transport_request_id
from src.schemas.platform.api import (
    PlatformListEnvelope,
    PlatformPage,
    PlatformSuccessEnvelope,
    response_meta,
)


def _json_object(value: Mapping[str, Any]) -> dict[str, Any]:
    return dict(value)


def build_success_envelope(
    *,
    request: Request,
    data: Mapping[str, Any],
    data_snapshot_id: str | None,
    warnings: Sequence[str] = (),
    generated_at: datetime | None = None,
) -> PlatformSuccessEnvelope:
    request_id = get_transport_request_id(request)
    return PlatformSuccessEnvelope(
        data=_json_object(data),
        meta=response_meta(
            request_id=request_id,
            generated_at=generated_at or datetime.now(timezone.utc),
            data_snapshot_id=data_snapshot_id,
            warnings=tuple(warnings),
        ),
    )


def build_list_envelope(
    *,
    request: Request,
    data: Sequence[Mapping[str, Any]],
    cursor: str | None,
    next_cursor: str | None,
    limit: int,
    has_more: bool,
    data_snapshot_id: str | None,
    warnings: Sequence[str] = (),
    generated_at: datetime | None = None,
) -> PlatformListEnvelope:
    request_id = get_transport_request_id(request)
    return PlatformListEnvelope(
        data=[_json_object(item) for item in data],
        meta=response_meta(
            request_id=request_id,
            generated_at=generated_at or datetime.now(timezone.utc),
            data_snapshot_id=data_snapshot_id,
            warnings=tuple(warnings),
        ),
        page=PlatformPage(
            cursor=cursor,
            next_cursor=next_cursor,
            limit=limit,
            has_more=has_more,
        ),
    )
