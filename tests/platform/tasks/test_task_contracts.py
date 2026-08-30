from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from src.schemas.platform import (
    AttemptOutcome,
    PriorityClass,
    ResourceRef,
    ResourceType,
    StorageBackend,
    StorageNamespace,
    StorageRef,
    TaskAttemptRecord,
    TaskCheckpointRecord,
    TaskRecord,
    TaskState,
    TaskStateEventRecord,
    generate_resource_id,
)


NOW = datetime(2026, 8, 30, 10, 0, tzinfo=timezone.utc)
TASK_ID = generate_resource_id(ResourceType.TASK, timestamp_ms=1_777_100_000_000, random_bits=101)
ATTEMPT_ID = generate_resource_id(ResourceType.ATTEMPT, timestamp_ms=1_777_100_000_000, random_bits=102)
CHECKPOINT_ID = generate_resource_id(ResourceType.CHECKPOINT, timestamp_ms=1_777_100_000_000, random_bits=103)
ARTIFACT_ID = generate_resource_id(ResourceType.ARTIFACT, timestamp_ms=1_777_100_000_000, random_bits=104)


def _task(**updates: object) -> TaskRecord:
    values = dict(
        task_id=TASK_ID,
        task_type="artifact_orphan_dry_run",
        task_schema_version="1.0.0",
        task_state=TaskState.QUEUED,
        priority_class=PriorityClass.P5_PREVIEW_AND_MAINTENANCE,
        priority_value=100,
        idempotency_key="idem-001",
        task_key="artifact_orphan_dry_run:default",
        canonical_request_hash="sha256:" + "1" * 64,
        requested_by="owner:test",
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
        terminal_at=None,
        failure_code=None,
    )
    values.update(updates)
    return TaskRecord(**values)


def test_task_contract_keeps_phase_out_of_task_state_and_validates_terminal_fields() -> None:
    task = _task()
    assert task.task_state is TaskState.QUEUED
    assert "attempt_phase" not in task.model_dump()

    with pytest.raises(ValidationError, match="FAILED requires failure_code"):
        _task(task_state=TaskState.FAILED, terminal_at=NOW)
    with pytest.raises(ValidationError, match="terminal task requires terminal_at"):
        _task(task_state=TaskState.SUCCEEDED)
    with pytest.raises(ValidationError, match="result_artifact_id only applies"):
        _task(result_artifact_id=ARTIFACT_ID)


def test_blocked_task_requires_deterministic_reason_and_unblock_condition() -> None:
    blocked = _task(
        task_state=TaskState.BLOCKED,
        queued_at=None,
        blocked_reason_code="STORAGE_PRESSURE",
        unblock_condition="free_bytes>=1073741824",
    )
    assert blocked.blocked_reason_code == "STORAGE_PRESSURE"

    with pytest.raises(ValidationError, match="BLOCKED requires"):
        _task(task_state=TaskState.BLOCKED, queued_at=None)


def test_attempt_record_stores_only_hashed_lease_and_separates_phase_from_state() -> None:
    attempt = TaskAttemptRecord(
        attempt_id=ATTEMPT_ID,
        task_id=TASK_ID,
        attempt_number=1,
        attempt_phase="SCANNING",
        phase_progress=0.25,
        worker_id="worker-1",
        worker_capabilities=("artifact_orphan_dry_run",),
        lease_token_hash="sha256:" + "2" * 64,
        leased_at=NOW,
        lease_expires_at=NOW + timedelta(minutes=1),
        heartbeat_at=NOW,
        started_at=NOW,
        finished_at=None,
        checkpoint_ref=None,
        resource_usage={"cpu_seconds": 0.1},
        attempt_outcome=None,
        failure_code=None,
        retryable=None,
        diagnostic_artifact_refs=(),
    )
    assert attempt.attempt_phase == "SCANNING"
    assert "lease_token" not in attempt.model_dump()

    with pytest.raises(ValidationError, match="finished attempt requires"):
        TaskAttemptRecord.model_validate(
            {**attempt.model_dump(mode="python"), "attempt_outcome": AttemptOutcome.FAILED}
        )


def test_checkpoint_contract_binds_storage_hash_and_versions() -> None:
    storage_ref = StorageRef(
        storage_backend=StorageBackend.LOCAL_FS,
        storage_namespace=StorageNamespace.APP,
        relative_path="checkpoints/task/payload.json",
        content_hash="sha256:" + "3" * 64,
        media_type="application/json",
        size_bytes=2,
    )
    checkpoint = TaskCheckpointRecord(
        checkpoint_id=CHECKPOINT_ID,
        task_id=TASK_ID,
        attempt_id=ATTEMPT_ID,
        phase="SCANNING",
        sequence=1,
        resume_token_hash="sha256:" + "4" * 64,
        input_hash="sha256:" + "5" * 64,
        handler_version="artifact_orphan_dry_run@1.0.0",
        storage_ref=storage_ref,
        checkpoint_hash=storage_ref.content_hash,
        created_at=NOW,
        expires_at=NOW + timedelta(days=1),
    )
    assert checkpoint.checkpoint_hash == storage_ref.content_hash

    with pytest.raises(ValidationError, match="checkpoint_hash must match storage_ref"):
        TaskCheckpointRecord.model_validate(
            {**checkpoint.model_dump(mode="python"), "checkpoint_hash": "sha256:" + "6" * 64}
        )


def test_state_event_uses_task_and_attempt_resource_ids() -> None:
    event = TaskStateEventRecord(
        task_id=TASK_ID,
        event_sequence=2,
        previous_task_state=TaskState.LEASED,
        next_task_state=TaskState.RUNNING,
        reason_code="WORKER_STARTED",
        actor_ref="worker:worker-1",
        event_at=NOW,
        attempt_id=ATTEMPT_ID,
    )
    assert event.next_task_state is TaskState.RUNNING

    wrong = ResourceRef(resource_type=ResourceType.ARTIFACT, resource_id=ARTIFACT_ID)
    with pytest.raises(ValidationError):
        _task(input_refs=(wrong,), created_from_task_id=ARTIFACT_ID)
