from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import text

from src.artifacts.hashing import compute_bytes_hash
from src.artifacts.namespace import StorageNamespaceResolver
from src.repositories.platform import PostgresDatabase, upgrade_database
from src.schemas.platform import (
    PriorityClass,
    StorageBackend,
    StorageNamespace,
    StorageRef,
    TaskCreateRequest,
    TaskState,
)
from src.services.platform.task_control import TaskControlError, TaskControlService


class MutableClock:
    def __init__(self, value: datetime) -> None:
        self.value = value
        self._lock = threading.Lock()

    def __call__(self) -> datetime:
        with self._lock:
            return self.value

    def advance(self, **delta: int) -> None:
        with self._lock:
            self.value += timedelta(**delta)


NOW = datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc)


def _request(**updates: object) -> TaskCreateRequest:
    values = dict(
        task_type="artifact_orphan_dry_run",
        task_schema_version="1.0.0",
        priority_class=PriorityClass.P5_PREVIEW_AND_MAINTENANCE,
        priority_value=100,
        requested_by="owner:integration",
        request_source="integration_test",
        input_refs=(),
        requirements={"worker_kind": "maintenance"},
        max_attempts=3,
        force=False,
        force_reason=None,
        created_from_task_id=None,
    )
    values.update(updates)
    return TaskCreateRequest(**values)


@pytest.fixture
def task_database(isolated_postgres_database: PostgresDatabase) -> PostgresDatabase:
    upgrade_database(isolated_postgres_database.engine)
    return isolated_postgres_database


def test_idempotent_command_and_concurrent_duplicates_create_one_task(task_database: PostgresDatabase) -> None:
    service = TaskControlService(task_database, clock=lambda: NOW)
    request = _request()
    barrier = threading.Barrier(6)

    def submit() -> str:
        barrier.wait(timeout=10)
        return service.create_task(request, idempotency_key="same-command").task_id

    with ThreadPoolExecutor(max_workers=6) as executor:
        task_ids = list(executor.map(lambda _: submit(), range(6)))

    assert len(set(task_ids)) == 1
    replayed = service.create_task(request, idempotency_key="same-command")
    assert replayed.task_id == task_ids[0]
    with pytest.raises(TaskControlError) as captured:
        service.create_task(_request(priority_value=101), idempotency_key="same-command")
    assert captured.value.error_code == "TASK_IDEMPOTENCY_CONFLICT"

    with task_database.engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM platform_task")).scalar_one() == 1
        assert connection.execute(text("SELECT count(*) FROM task_command_idempotency")).scalar_one() == 1
        assert connection.execute(text("SELECT count(*) FROM task_state_event")).scalar_one() == 2


def test_concurrent_workers_claim_once_and_heartbeat_requires_current_lease(task_database: PostgresDatabase) -> None:
    clock = MutableClock(NOW)
    service = TaskControlService(task_database, clock=clock)
    task = service.create_task(_request(), idempotency_key="claim-once")
    barrier = threading.Barrier(2)

    def claim(worker_id: str):
        barrier.wait(timeout=10)
        return service.lease_next(
            worker_id=worker_id,
            worker_capabilities=("artifact_orphan_dry_run",),
            lease_seconds=30,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        claims = list(executor.map(claim, ("worker-a", "worker-b")))
    leases = [claim for claim in claims if claim is not None]
    assert len(leases) == 1
    lease = leases[0]
    assert lease.task.task_id == task.task_id
    assert lease.attempt.lease_token_hash != lease.lease_token

    running = service.start_attempt(lease.attempt.attempt_id, lease.lease_token)
    previous_expiry = running.lease_expires_at
    clock.advance(seconds=5)
    renewed = service.heartbeat(lease.attempt.attempt_id, lease.lease_token, lease_seconds=30)
    assert renewed.lease_expires_at > previous_expiry

    with pytest.raises(TaskControlError) as captured:
        service.heartbeat(lease.attempt.attempt_id, "wrong-token-value-that-is-long-enough")
    assert captured.value.error_code == "TASK_LEASE_LOST"


def test_lease_expiry_restart_retry_and_old_worker_write_rejection(task_database: PostgresDatabase) -> None:
    clock = MutableClock(NOW)
    service = TaskControlService(task_database, clock=clock)
    task = service.create_task(_request(), idempotency_key="lease-recovery")
    first = service.lease_next(
        worker_id="worker-old",
        worker_capabilities=("artifact_orphan_dry_run",),
        lease_seconds=10,
    )
    assert first is not None
    service.start_attempt(first.attempt.attempt_id, first.lease_token)
    clock.advance(seconds=11)

    restarted = TaskControlService(task_database, clock=clock)
    second = restarted.lease_next(
        worker_id="worker-new",
        worker_capabilities=("artifact_orphan_dry_run",),
        lease_seconds=30,
    )
    assert second is not None
    assert second.task.task_id == task.task_id
    assert second.attempt.attempt_number == 2
    assert second.attempt.attempt_id != first.attempt.attempt_id

    with pytest.raises(TaskControlError) as captured:
        restarted.start_attempt(first.attempt.attempt_id, first.lease_token)
    assert captured.value.error_code == "TASK_LEASE_LOST"
    with task_database.transaction() as session:
        with pytest.raises(TaskControlError) as publish_error:
            restarted.complete_with_artifact_in_session(
                session,
                attempt_id=first.attempt.attempt_id,
                lease_token=first.lease_token,
                artifact_id="artifact_019a7f6d-5c00-7000-8000-000000000099",
            )
    assert publish_error.value.error_code == "TASK_LEASE_LOST"
    details = restarted.get_task(task.task_id)
    assert details.attempts[0].attempt_outcome.value == "LEASE_LOST"
    assert details.task.task_state is TaskState.LEASED


def test_lease_expiry_before_start_respects_max_attempts(task_database: PostgresDatabase) -> None:
    clock = MutableClock(NOW)
    service = TaskControlService(task_database, clock=clock)
    task = service.create_task(
        _request(max_attempts=1, priority_value=99),
        idempotency_key="lease-before-start-exhausted",
    )
    first = service.lease_next(
        worker_id="worker-never-started",
        worker_capabilities=("artifact_orphan_dry_run",),
        lease_seconds=10,
    )
    assert first is not None and first.task.task_id == task.task_id
    clock.advance(seconds=11)

    assert service.lease_next(
        worker_id="worker-after-expiry",
        worker_capabilities=("artifact_orphan_dry_run",),
        lease_seconds=30,
    ) is None
    details = service.get_task(task.task_id)
    assert details.task.task_state is TaskState.FAILED
    assert details.task.failure_code == "TASK_MAX_ATTEMPTS_EXCEEDED"
    assert details.attempts[0].attempt_outcome.value == "LEASE_LOST"
    assert details.attempts[0].retryable is False


def test_retry_cancel_and_blocked_recovery_keep_old_attempts_immutable(task_database: PostgresDatabase) -> None:
    service = TaskControlService(task_database, clock=lambda: NOW)

    retry_task = service.create_task(_request(), idempotency_key="retry-flow")
    first = service.lease_next(worker_id="worker-1", worker_capabilities=("artifact_orphan_dry_run",))
    assert first is not None and first.task.task_id == retry_task.task_id
    service.start_attempt(first.attempt.attempt_id, first.lease_token)
    waiting = service.record_failure(
        first.attempt.attempt_id,
        first.lease_token,
        failure_code="TASK_HANDLER_CRASHED",
        retryable=True,
    )
    assert waiting.task_state is TaskState.RETRY_WAIT
    service.request_retry(retry_task.task_id)
    second = service.lease_next(worker_id="worker-2", worker_capabilities=("artifact_orphan_dry_run",))
    assert second is not None
    assert second.attempt.attempt_number == 2
    assert service.get_task(retry_task.task_id).attempts[0].failure_code == "TASK_HANDLER_CRASHED"

    queued = service.create_task(_request(priority_value=101), idempotency_key="cancel-queued")
    queued_cancelled = service.request_cancel(queued.task_id)
    assert queued_cancelled.task_state is TaskState.CANCELLED
    assert queued_cancelled.cancel_requested_at == NOW

    blocked = service.create_task(_request(priority_value=102), idempotency_key="blocked-flow")
    blocked_state = service.block_task(
        blocked.task_id,
        reason_code="STORAGE_PRESSURE",
        unblock_condition="free_bytes>=1073741824",
        actor_ref="scheduler",
    )
    assert blocked_state.task_state is TaskState.BLOCKED
    assert blocked_state.blocked_reason_code == "STORAGE_PRESSURE"
    assert service.unblock_task(blocked.task_id, actor_ref="scheduler").task_state is TaskState.QUEUED


def test_checkpoint_resume_validates_token_input_version_hash_and_storage(
    task_database: PostgresDatabase,
    tmp_path: Path,
) -> None:
    clock = MutableClock(NOW)
    service = TaskControlService(task_database, clock=clock, runtime_root=tmp_path)
    task = service.create_task(_request(), idempotency_key="checkpoint-flow")
    lease = service.lease_next(worker_id="worker-cp", worker_capabilities=("artifact_orphan_dry_run",))
    assert lease is not None and lease.task.task_id == task.task_id
    service.start_attempt(lease.attempt.attempt_id, lease.lease_token)

    content = b'{"cursor":1}\n'
    content_hash = compute_bytes_hash(content)
    storage_ref = StorageRef(
        storage_backend=StorageBackend.LOCAL_FS,
        storage_namespace=StorageNamespace.APP,
        relative_path="checkpoints/integration/cursor.json",
        content_hash=content_hash,
        media_type="application/json",
        size_bytes=len(content),
    )
    path = StorageNamespaceResolver(tmp_path).resolve(storage_ref)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    input_hash = "sha256:" + "7" * 64

    checkpoint, resume_token = service.save_checkpoint(
        lease.attempt.attempt_id,
        lease.lease_token,
        phase="SCANNING",
        input_hash=input_hash,
        handler_version="artifact_orphan_dry_run@1.0.0",
        storage_ref=storage_ref,
        expires_at=NOW + timedelta(hours=1),
    )
    assert service.validate_checkpoint(
        checkpoint.checkpoint_id,
        resume_token=resume_token,
        input_hash=input_hash,
        handler_version="artifact_orphan_dry_run@1.0.0",
    ) == checkpoint

    for invalid in (
        {"resume_token": "invalid-token-value-that-is-long-enough", "input_hash": input_hash, "handler_version": "artifact_orphan_dry_run@1.0.0"},
        {"resume_token": resume_token, "input_hash": "sha256:" + "8" * 64, "handler_version": "artifact_orphan_dry_run@1.0.0"},
        {"resume_token": resume_token, "input_hash": input_hash, "handler_version": "artifact_orphan_dry_run@2.0.0"},
    ):
        with pytest.raises(TaskControlError, match="TASK_CHECKPOINT_INVALID"):
            service.validate_checkpoint(checkpoint.checkpoint_id, **invalid)

    path.write_bytes(b"tampered")
    with pytest.raises(TaskControlError, match="TASK_CHECKPOINT_INVALID"):
        service.validate_checkpoint(
            checkpoint.checkpoint_id,
            resume_token=resume_token,
            input_hash=input_hash,
            handler_version="artifact_orphan_dry_run@1.0.0",
        )


def test_force_creates_new_task_lineage_and_does_not_overwrite_original(task_database: PostgresDatabase) -> None:
    service = TaskControlService(task_database, clock=lambda: NOW)
    original = service.create_task(_request(), idempotency_key="force-original")
    forced = service.create_task(
        _request(force=True, force_reason="MANUAL_RETRY", created_from_task_id=original.task_id),
        idempotency_key="force-command",
    )
    assert forced.task_id != original.task_id
    assert forced.created_from_task_id == original.task_id
    assert forced.force_reason == "MANUAL_RETRY"
    assert forced.idempotency_key != original.idempotency_key
    assert service.get_task(original.task_id).task.task_state is TaskState.QUEUED
    assert service.get_task(forced.task_id).task.task_state is TaskState.QUEUED


def test_running_cancel_is_cooperative_and_blocked_can_cancel(task_database: PostgresDatabase) -> None:
    service = TaskControlService(task_database, clock=lambda: NOW)
    running_task = service.create_task(_request(priority_value=200), idempotency_key="cancel-running")
    lease = service.lease_next(worker_id="worker-cancel", worker_capabilities=("artifact_orphan_dry_run",))
    assert lease is not None and lease.task.task_id == running_task.task_id
    service.start_attempt(lease.attempt.attempt_id, lease.lease_token)
    requested = service.request_cancel(running_task.task_id)
    assert requested.task_state is TaskState.RUNNING
    assert requested.cancel_requested_at == NOW
    cancelled = service.acknowledge_cancel(lease.attempt.attempt_id, lease.lease_token)
    assert cancelled.task_state is TaskState.CANCELLED
    assert service.get_task(running_task.task_id).attempts[-1].attempt_outcome.value == "CANCELLED"

    blocked_task = service.create_task(_request(priority_value=201), idempotency_key="cancel-blocked")
    service.block_task(
        blocked_task.task_id,
        reason_code="DEPENDENCY_UNAVAILABLE",
        unblock_condition="dependency=healthy",
        actor_ref="scheduler",
    )
    blocked_cancelled = service.request_cancel(blocked_task.task_id)
    assert blocked_cancelled.task_state is TaskState.CANCELLED
    assert blocked_cancelled.cancel_requested_at == NOW


def test_running_block_finishes_attempt_and_unblock_creates_new_attempt(task_database: PostgresDatabase) -> None:
    service = TaskControlService(task_database, clock=lambda: NOW)
    task = service.create_task(_request(priority_value=202), idempotency_key="block-running")
    first = service.lease_next(worker_id="worker-block", worker_capabilities=("artifact_orphan_dry_run",))
    assert first is not None and first.task.task_id == task.task_id
    service.start_attempt(first.attempt.attempt_id, first.lease_token)
    blocked = service.block_task(
        task.task_id,
        attempt_id=first.attempt.attempt_id,
        lease_token=first.lease_token,
        reason_code="DEPENDENCY_UNAVAILABLE",
        unblock_condition="dependency=healthy",
        actor_ref="worker:worker-block",
    )
    assert blocked.task_state is TaskState.BLOCKED
    assert service.get_task(task.task_id).attempts[0].attempt_outcome.value == "BLOCKED"
    service.unblock_task(task.task_id, actor_ref="scheduler")
    second = service.lease_next(worker_id="worker-resume", worker_capabilities=("artifact_orphan_dry_run",))
    assert second is not None and second.task.task_id == task.task_id
    assert second.attempt.attempt_number == 2


def test_nonretryable_or_exhausted_attempt_fails_terminally(task_database: PostgresDatabase) -> None:
    service = TaskControlService(task_database, clock=lambda: NOW)
    task = service.create_task(_request(max_attempts=1, priority_value=203), idempotency_key="max-attempts")
    lease = service.lease_next(worker_id="worker-fail", worker_capabilities=("artifact_orphan_dry_run",))
    assert lease is not None and lease.task.task_id == task.task_id
    service.start_attempt(lease.attempt.attempt_id, lease.lease_token)
    failed = service.record_failure(
        lease.attempt.attempt_id,
        lease.lease_token,
        failure_code="TASK_HANDLER_CRASHED",
        retryable=True,
    )
    assert failed.task_state is TaskState.FAILED
    assert failed.failure_code == "TASK_HANDLER_CRASHED"
    with pytest.raises(TaskControlError, match="TASK_CANCEL_NOT_ALLOWED"):
        service.request_cancel(task.task_id)
