from __future__ import annotations

from fastapi import APIRouter, Header, Request

from api.platform.errors import platform_error
from api.platform.responses import build_success_envelope
from src.services.platform.task_control import TaskControlError
from src.schemas.platform import TaskCancelRequest, TaskCreateRequest, TaskRetryRequest
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


def _task_service(request: Request):
    service = getattr(request.app.state, "task_control_service", None)
    if service is None:
        raise platform_error(503, details={"dependency": "postgresql", "operation": "task_control"})
    return service


def _raise_task_database_error(exc: PlatformDatabaseError) -> None:
    raise platform_error(
        503,
        code=exc.error_code,
        message=exc.public_message,
        retryable=exc.retryable,
        details={key: value for key, value in exc.details.items() if key in {"dependency", "operation"}},
    ) from exc


def _raise_task_error(exc: TaskControlError) -> None:
    allowed = {"endpoint", "task_id", "attempt_id", "from", "to", "dependency", "operation"}
    details = {key: value for key, value in exc.details.items() if key in allowed}
    raise platform_error(
        exc.status_code,
        code=exc.error_code,
        message=exc.public_message,
        retryable=exc.retryable,
        details=details,
    ) from exc


@router.post("/tasks", response_model=PlatformSuccessEnvelope, summary="Create a durable platform task")
def create_task(
    request_body: TaskCreateRequest,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> PlatformSuccessEnvelope:
    service = _task_service(request)
    try:
        if idempotency_key is None:
            raise TaskControlError("TASK_IDEMPOTENCY_KEY_REQUIRED", "Idempotency-Key is required.", status_code=400)
        task = service.create_task(request_body, idempotency_key=idempotency_key)
    except TaskControlError as exc:
        _raise_task_error(exc)
    except PlatformDatabaseError as exc:
        _raise_task_database_error(exc)
    return build_success_envelope(request=request, data=task.model_dump(mode="json"), data_snapshot_id=None, generated_at=task.created_at)


@router.get("/tasks/{task_id}", response_model=PlatformSuccessEnvelope, summary="Get a durable platform task")
def get_task(task_id: str, request: Request) -> PlatformSuccessEnvelope:
    service = _task_service(request)
    try:
        details = service.get_task(task_id)
    except TaskControlError as exc:
        _raise_task_error(exc)
    except PlatformDatabaseError as exc:
        _raise_task_database_error(exc)
    return build_success_envelope(request=request, data=details.model_dump(mode="json"), data_snapshot_id=None, generated_at=details.task.created_at)


@router.post("/tasks/{task_id}/cancellations", response_model=PlatformSuccessEnvelope, summary="Request task cancellation")
def cancel_task(task_id: str, request_body: TaskCancelRequest, request: Request) -> PlatformSuccessEnvelope:
    service = _task_service(request)
    try:
        task = service.request_cancel(task_id, reason_code=request_body.reason_code)
    except TaskControlError as exc:
        _raise_task_error(exc)
    except PlatformDatabaseError as exc:
        _raise_task_database_error(exc)
    return build_success_envelope(request=request, data=task.model_dump(mode="json"), data_snapshot_id=None, generated_at=task.created_at)


@router.post("/tasks/{task_id}/retries", response_model=PlatformSuccessEnvelope, summary="Request task retry")
def retry_task(task_id: str, request_body: TaskRetryRequest, request: Request) -> PlatformSuccessEnvelope:
    service = _task_service(request)
    try:
        task = service.request_retry(task_id, reason_code=request_body.reason_code)
    except TaskControlError as exc:
        _raise_task_error(exc)
    except PlatformDatabaseError as exc:
        _raise_task_database_error(exc)
    return build_success_envelope(request=request, data=task.model_dump(mode="json"), data_snapshot_id=None, generated_at=task.created_at)
