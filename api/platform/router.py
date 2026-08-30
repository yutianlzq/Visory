from __future__ import annotations

import json

from fastapi import APIRouter, Header, Query, Request
from fastapi.responses import StreamingResponse

from api.platform.errors import platform_error
from api.platform.responses import build_list_envelope, build_success_envelope
from src.services.platform.task_control import TaskControlError
from src.schemas.platform import TaskCancelRequest, TaskCreateRequest, TaskDetails, TaskListQuery, TaskRetryRequest
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
