from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock
import sys

from fastapi.testclient import TestClient

from api.platform.request_id import REQUEST_ID_HEADER
from src.schemas.platform import (
    PriorityClass,
    TaskDetails,
    TaskRecord,
    TaskState,
)
from src.services.platform.task_control import TaskControlError

sys.modules.setdefault("litellm", MagicMock())
from api.app import create_app


NOW = datetime(2026, 8, 30, 14, 0, tzinfo=timezone.utc)
TASK_ID = "task_019a7f6d-5c00-7000-8000-000000000001"


def _task(state: TaskState = TaskState.QUEUED) -> TaskRecord:
    terminal = NOW if state in {TaskState.SUCCEEDED, TaskState.DEGRADED, TaskState.FAILED, TaskState.CANCELLED} else None
    return TaskRecord(
        task_id=TASK_ID,
        task_type="artifact_orphan_dry_run",
        task_schema_version="1.0.0",
        task_state=state,
        priority_class=PriorityClass.P5_PREVIEW_AND_MAINTENANCE,
        priority_value=100,
        idempotency_key="api-idempotency",
        task_key="artifact_orphan_dry_run:fixture",
        canonical_request_hash="sha256:" + "1" * 64,
        requested_by="owner:api",
        request_source="platform_api",
        input_refs=(),
        requirements={"worker_kind": "maintenance"},
        active_attempt_id=None,
        blocked_reason_code=None,
        unblock_condition=None,
        max_attempts=3,
        cancel_requested_at=None,
        result_artifact_id=None,
        created_from_task_id=None,
        force_reason=None,
        created_at=NOW,
        queued_at=NOW,
        terminal_at=terminal,
        failure_code="TASK_FAILED" if state is TaskState.FAILED else None,
    )


class FakeTaskService:
    def __init__(self) -> None:
        self.task = _task()
        self.idempotency_key = None

    def create_task(self, request, *, idempotency_key, endpoint="/api/platform/v1/tasks"):
        self.idempotency_key = idempotency_key
        return self.task

    def get_task(self, task_id):
        assert task_id == TASK_ID
        return TaskDetails(task=self.task, attempts=(), state_events=())

    def request_cancel(self, task_id, **kwargs):
        assert task_id == TASK_ID
        self.task = _task(TaskState.CANCELLED)
        return self.task

    def request_retry(self, task_id, **kwargs):
        assert task_id == TASK_ID
        return self.task


def test_task_create_query_cancel_and_retry_use_c010_envelope(tmp_path: Path) -> None:
    app = create_app(static_dir=tmp_path / "missing-static")
    service = FakeTaskService()
    app.state.task_control_service = service
    client = TestClient(app)
    headers = {
        REQUEST_ID_HEADER: "req_0123456789abcdef0123456789abcdef",
        "Idempotency-Key": "command-001",
    }
    created = client.post(
        "/api/platform/v1/tasks",
        headers=headers,
        json={
            "task_type": "artifact_orphan_dry_run",
            "requested_by": "owner:api",
            "requirements": {"worker_kind": "maintenance"},
        },
    )
    assert created.status_code == 200
    assert created.json()["data"]["task_id"] == TASK_ID
    assert created.json()["meta"]["request_id"] == headers[REQUEST_ID_HEADER]
    assert service.idempotency_key == "command-001"

    queried = client.get(f"/api/platform/v1/tasks/{TASK_ID}")
    assert queried.status_code == 200
    assert queried.json()["data"]["attempts"] == []

    cancelled = client.post(f"/api/platform/v1/tasks/{TASK_ID}/cancellations", json={})
    assert cancelled.status_code == 200
    assert cancelled.json()["data"]["task_state"] == "CANCELLED"

    retried = client.post(f"/api/platform/v1/tasks/{TASK_ID}/retries", json={})
    assert retried.status_code == 200


def test_task_api_returns_stable_task_error_and_requires_idempotency_key(tmp_path: Path) -> None:
    class FailingService(FakeTaskService):
        def create_task(self, request, *, idempotency_key, endpoint="/api/platform/v1/tasks"):
            raise TaskControlError(
                "TASK_IDEMPOTENCY_CONFLICT",
                "Idempotency-Key was already used with a different payload.",
                details={"endpoint": endpoint, "secret": "must-not-leak"},
            )

    app = create_app(static_dir=tmp_path / "missing-static")
    app.state.task_control_service = FailingService()
    client = TestClient(app, raise_server_exceptions=False)
    payload = {"task_type": "artifact_orphan_dry_run", "requested_by": "owner:api"}

    missing = client.post("/api/platform/v1/tasks", json=payload)
    assert missing.status_code == 400
    assert missing.json()["error"]["code"] == "TASK_IDEMPOTENCY_KEY_REQUIRED"

    conflict = client.post(
        "/api/platform/v1/tasks",
        headers={"Idempotency-Key": "command-001"},
        json=payload,
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "TASK_IDEMPOTENCY_CONFLICT"
    assert conflict.json()["error"]["retryable"] is False
    assert "must-not-leak" not in conflict.text
