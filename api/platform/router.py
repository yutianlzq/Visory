from __future__ import annotations

import json
from datetime import date

from fastapi import APIRouter, Header, Query, Request
from fastapi.responses import StreamingResponse

from api.platform.errors import platform_error
from api.platform.responses import build_list_envelope, build_success_envelope
from src.services.platform.task_control import TaskControlError
from src.services.platform.provider_registry import ProviderRegistryService
from src.services.platform.data_quality import DataQualityError, DataQualityService
from src.schemas.platform import (
    DataQualityActionRequest,
    DataQualityQuery,
    QualityStatus,
    TaskCancelRequest,
    TaskCreateRequest,
    TaskDetails,
    TaskListQuery,
    TaskRetryRequest,
)
from src.repositories.platform.errors import PlatformDatabaseError
from src.schemas.platform import AssetResolutionRequest, PlatformSuccessEnvelope


router = APIRouter(prefix="/platform/v1", tags=["Platform"])


def _provider_registry_service(request: Request) -> ProviderRegistryService:
    service = getattr(request.app.state, "provider_registry_service", None)
    if service is None:
        raise platform_error(503, details={"dependency": "postgresql", "operation": "provider_registry"})
    return service


def _provider_registry_payload(request: Request) -> dict[str, object]:
    projection = _provider_registry_service(request).settings_projection()
    return projection.model_dump(mode="json")


@router.get("/provider-registry", response_model=PlatformSuccessEnvelope, summary="Read dataset and provider registry")
def get_provider_registry(request: Request) -> PlatformSuccessEnvelope:
    payload = _provider_registry_payload(request)
    return build_success_envelope(request=request, data=payload, data_snapshot_id=None)


@router.get("/providers", response_model=PlatformSuccessEnvelope, summary="List registered providers")
def list_providers(request: Request) -> PlatformSuccessEnvelope:
    payload = _provider_registry_payload(request)
    return build_success_envelope(request=request, data={"providers": payload["providers"]}, data_snapshot_id=None)


@router.get("/datasets", response_model=PlatformSuccessEnvelope, summary="List registered datasets")
def list_datasets(request: Request) -> PlatformSuccessEnvelope:
    payload = _provider_registry_payload(request)
    return build_success_envelope(request=request, data={"datasets": payload["datasets"]}, data_snapshot_id=None)


def _data_quality_service(request: Request) -> DataQualityService:
    service = getattr(request.app.state, "data_quality_service", None)
    if service is None:
        raise platform_error(503, details={"dependency": "postgresql", "operation": "data_quality"})
    return service


def _raise_data_quality_error(exc: DataQualityError) -> None:
    raise platform_error(
        exc.status_code,
        code=exc.error_code,
        message=exc.public_message,
        retryable=exc.retryable,
        details=exc.details,
    ) from exc


def _quality_query(
    *,
    trade_date: date | None,
    snapshot_id: str | None,
    capability: str | None,
    dataset: str | None,
    provider: str | None,
    status: str | None,
) -> DataQualityQuery:
    try:
        return DataQualityQuery.model_validate(
            {
                "trade_date": trade_date,
                "snapshot_id": snapshot_id,
                "capability": capability,
                "dataset": dataset,
                "provider": provider,
                "quality_status": status,
            }
        )
    except ValueError as exc:
        raise platform_error(422, details={"field": "query"}) from exc


@router.get("/data-quality", response_model=PlatformSuccessEnvelope, summary="Read data quality snapshot projection")
def get_data_quality(
    request: Request,
    trade_date: date | None = Query(default=None),
    snapshot_id: str | None = Query(default=None),
    capability: str | None = Query(default=None),
    dataset: str | None = Query(default=None),
    provider: str | None = Query(default=None),
    status: str | None = Query(default=None),
) -> PlatformSuccessEnvelope:
    service = _data_quality_service(request)
    query = _quality_query(
        trade_date=trade_date,
        snapshot_id=snapshot_id,
        capability=capability,
        dataset=dataset,
        provider=provider,
        status=status,
    )
    try:
        projection = service.get_projection(query)
    except DataQualityError as exc:
        _raise_data_quality_error(exc)
    except PlatformDatabaseError as exc:
        _raise_task_database_error(exc)
    return build_success_envelope(
        request=request,
        data=projection.model_dump(mode="json"),
        data_snapshot_id=projection.snapshot_id,
        warnings=projection.warnings,
        generated_at=projection.data_as_of,
    )


@router.get("/data-quality/compare", response_model=PlatformSuccessEnvelope, summary="Compare data quality snapshots")
def compare_data_quality(
    request: Request,
    snapshot_id: str = Query(...),
    base_snapshot_id: str | None = Query(default=None),
) -> PlatformSuccessEnvelope:
    service = _data_quality_service(request)
    try:
        target = DataQualityQuery.model_validate({"snapshot_id": snapshot_id}).snapshot_id
        base = (
            DataQualityQuery.model_validate({"snapshot_id": base_snapshot_id}).snapshot_id
            if base_snapshot_id is not None
            else None
        )
        assert target is not None
        result = service.compare_snapshots(target, base)
    except AssertionError as exc:
        raise platform_error(422, details={"field": "snapshot_id"}) from exc
    except ValueError as exc:
        raise platform_error(422, details={"field": "snapshot_id"}) from exc
    except DataQualityError as exc:
        _raise_data_quality_error(exc)
    except PlatformDatabaseError as exc:
        _raise_task_database_error(exc)
    return build_success_envelope(
        request=request,
        data=result.model_dump(mode="json"),
        data_snapshot_id=result.target_snapshot_id,
    )


@router.post("/data-quality/actions", response_model=PlatformSuccessEnvelope, summary="Create a controlled data quality task")
def create_data_quality_action(
    request_body: DataQualityActionRequest,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> PlatformSuccessEnvelope:
    service = _data_quality_service(request)
    if idempotency_key is None:
        raise platform_error(400, code="TASK_IDEMPOTENCY_KEY_REQUIRED", message="Idempotency-Key is required.")
    if request_body.idempotency_key is not None and request_body.idempotency_key != idempotency_key:
        raise platform_error(409, code="TASK_IDEMPOTENCY_CONFLICT", message="Idempotency-Key conflicts with request body.")
    try:
        result = service.create_action(request_body, idempotency_key=idempotency_key)
    except DataQualityError as exc:
        _raise_data_quality_error(exc)
    except TaskControlError as exc:
        _raise_task_error(exc)
    except PlatformDatabaseError as exc:
        _raise_task_database_error(exc)
    return build_success_envelope(
        request=request,
        data=result.model_dump(mode="json"),
        data_snapshot_id=result.snapshot_id,
    )


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


def _public_task_details(details: TaskDetails) -> dict[str, object]:
    payload = details.model_dump(mode="json")
    for attempt in payload.get("attempts", []):
        if isinstance(attempt, dict):
            attempt.pop("lease_token_hash", None)
    return payload


def _sse_response(events: tuple[object, ...]) -> StreamingResponse:
    def generate():
        for event in events:
            data = event.model_dump(mode="json") if hasattr(event, "model_dump") else event
            encoded = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
            yield f"id: {data['event_id']}\nevent: {data['event_type']}\ndata: {encoded}\n\n"
        yield ": heartbeat\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


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


@router.get("/tasks", response_model=object, summary="List durable platform tasks")
def list_tasks(
    request: Request,
    tab: str | None = Query(default=None),
    task_state: str | None = Query(default=None),
    task_type: str | None = Query(default=None),
    priority_class: str | None = Query(default=None),
    requested_by: str | None = Query(default=None),
    created_from: str | None = Query(default=None),
    created_to: str | None = Query(default=None),
    resource_id: str | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
) -> object:
    service = _task_service(request)
    try:
        query = TaskListQuery.model_validate({
            "tab": tab, "task_state": task_state, "task_type": task_type,
            "priority_class": priority_class, "requested_by": requested_by,
            "created_from": created_from, "created_to": created_to,
            "resource_id": resource_id, "cursor": cursor, "limit": limit,
        })
        tasks, next_cursor, has_more = service.list_tasks(query)
    except TaskControlError as exc:
        _raise_task_error(exc)
    except ValueError as exc:
        raise platform_error(422, details={"field": "query"}) from exc
    return build_list_envelope(
        request=request,
        data=[task.model_dump(mode="json") for task in tasks],
        cursor=cursor,
        next_cursor=next_cursor,
        limit=limit,
        has_more=has_more,
        data_snapshot_id=None,
        generated_at=tasks[0].created_at if tasks else None,
    )


@router.get("/tasks/events", summary="Stream durable task state events")
def stream_task_events(
    request: Request,
    after_event_id: str | None = Query(default=None),
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
) -> StreamingResponse:
    service = _task_service(request)
    try:
        events = service.list_event_records(after_event_id=after_event_id or last_event_id)
    except TaskControlError as exc:
        _raise_task_error(exc)
    return _sse_response(events)


@router.get("/tasks/{task_id}/events", summary="Stream durable task state events for one task")
def stream_task_events_for_task(
    task_id: str,
    request: Request,
    after_event_id: str | None = Query(default=None),
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
) -> StreamingResponse:
    service = _task_service(request)
    try:
        events = service.list_event_records(task_id=task_id, after_event_id=after_event_id or last_event_id)
    except TaskControlError as exc:
        _raise_task_error(exc)
    return _sse_response(events)


@router.get("/tasks/{task_id}", response_model=PlatformSuccessEnvelope, summary="Get a durable platform task")
def get_task(task_id: str, request: Request) -> PlatformSuccessEnvelope:
    service = _task_service(request)
    try:
        details = service.get_task(task_id)
    except TaskControlError as exc:
        _raise_task_error(exc)
    except PlatformDatabaseError as exc:
        _raise_task_database_error(exc)
    return build_success_envelope(request=request, data=_public_task_details(details), data_snapshot_id=None, generated_at=details.task.created_at)


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
