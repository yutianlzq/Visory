from __future__ import annotations

from fastapi import APIRouter, Request

from api.platform.errors import platform_error
from api.platform.responses import build_success_envelope
from src.repositories.platform.errors import PlatformDatabaseError
from src.schemas.platform import AssetResolutionRequest, PlatformSuccessEnvelope


router = APIRouter(prefix="/platform/v1", tags=["Platform"])


@router.post(
    "/asset-resolutions",
    response_model=PlatformSuccessEnvelope,
    summary="Resolve an asset identity without guessing",
)
def resolve_asset_identity(request_body: AssetResolutionRequest, request: Request) -> PlatformSuccessEnvelope:
    service = getattr(request.app.state, "asset_resolver_service", None)
    if service is None:
        raise platform_error(503, details={"dependency": "postgresql", "operation": "asset_resolution"})
    try:
        result = service.resolve(request_body)
    except PlatformDatabaseError as exc:
        raise platform_error(
            503,
            details={"dependency": "postgresql", "operation": "asset_resolution"},
        ) from exc
    return build_success_envelope(
        request=request,
        data=result.model_dump(mode="json"),
        data_snapshot_id=None,
        generated_at=result.resolved_at,
    )
