from __future__ import annotations

import hashlib
import hmac
import secrets
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from src.artifacts.hashing import compute_bytes_hash
from src.artifacts.namespace import StorageNamespaceResolver
from src.core.platform.task_state_machine import InvalidTaskTransition, validate_task_transition
from src.repositories.platform.database import PostgresDatabase
from src.repositories.platform.task import TaskControlRepository
from src.schemas.platform import (
    AttemptOutcome,
    ResourceType,
    StorageRef,
    TaskAttemptRecord,
    TaskCheckpointRecord,
    TaskCreateRequest,
    TaskDetails,
    TaskEventRecord,
    TaskLease,
    TaskListQuery,
    TaskRecord,
    TaskState,
    TaskStateEventRecord,
    compute_content_hash,
    generate_resource_id,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _secret_hash(value: str) -> str:
    return f"sha256:{hashlib.sha256(value.encode('utf-8')).hexdigest()}"


class TaskControlError(Exception):
    def __init__(
        self,
        error_code: str,
        public_message: str,
        *,
        status_code: int = 409,
        retryable: bool = False,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.error_code = error_code
        self.public_message = public_message
        self.status_code = status_code
        self.retryable = retryable
        self.details = details or {}
        super().__init__(error_code)


class TaskControlService:
    """Application service owning task transactions, state changes, and lease checks."""

    def __init__(
        self,
        database: PostgresDatabase,
        repository: TaskControlRepository | None = None,
        *,
        clock: Callable[[], datetime] = _utc_now,
        token_factory: Callable[[], str] | None = None,
        runtime_root: Path | str | None = None,
    ) -> None:
        self.database = database
        self.repository = repository or TaskControlRepository()
        self.clock = clock
        self.token_factory = token_factory or (lambda: secrets.token_urlsafe(32))
        self.resolver = StorageNamespaceResolver(runtime_root) if runtime_root is not None else None

    def _now(self) -> datetime:
        now = self.clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("task control clock must return a timezone-aware datetime")
        return now

    @staticmethod
    def _idempotency_key(value: str) -> str:
        if not isinstance(value, str) or not value.strip() or len(value) > 255:
            raise TaskControlError(
                "TASK_IDEMPOTENCY_KEY_INVALID",
                "Idempotency-Key is required and must be valid.",
                status_code=400,
            )
        return value.strip()

    def _append_event(
        self,
        session: object,
        *,
        task_id: str,
        previous: TaskState | None,
        next_state: TaskState,
        reason_code: str,
        actor_ref: str,
        event_at: datetime,
        attempt_id: str | None,
    ) -> None:
        self.repository.append_event(
            session,
            TaskStateEventRecord(
                task_id=task_id,
                event_sequence=self.repository.next_event_sequence(session, task_id),
                previous_task_state=previous,
                next_task_state=next_state,
                reason_code=reason_code,
                actor_ref=actor_ref,
                event_at=event_at,
                attempt_id=attempt_id,
            ),
        )

    def _transition(
        self,
        session: object,
        task: TaskRecord,
        target: TaskState,
        *,
        reason_code: str,
        actor_ref: str,
        event_at: datetime,
        attempt_id: str | None = None,
        updates: dict[str, object] | None = None,
    ) -> TaskRecord:
        try:
            validate_task_transition(task.task_state, target)
        except InvalidTaskTransition as exc:
            raise TaskControlError(
                exc.error_code,
                "Task state transition is not allowed.",
                details={"task_id": task.task_id, "from": task.task_state.value, "to": target.value},
            ) from exc
        original = task.model_dump(mode="python")
        values = dict(original)
        values["task_state"] = target
        values.update(updates or {})
        if target is TaskState.QUEUED:
            values.update(
                queued_at=event_at,
                blocked_reason_code=None,
                unblock_condition=None,
                failure_code=None,
                terminal_at=None,
                active_attempt_id=None,
            )
        elif target in {TaskState.BLOCKED, TaskState.RETRY_WAIT}:
            values.update(active_attempt_id=None, failure_code=None, terminal_at=None)
        elif target in {TaskState.SUCCEEDED, TaskState.DEGRADED, TaskState.FAILED, TaskState.CANCELLED}:
            values.update(
                active_attempt_id=None,
                terminal_at=event_at,
                blocked_reason_code=None,
                unblock_condition=None,
            )
            if target is not TaskState.FAILED:
                values["failure_code"] = None
        transitioned = TaskRecord.model_validate(values)
        current = transitioned.model_dump(mode="python")
        self.repository.update_task(
            session,
            task.task_id,
            **{key: value for key, value in current.items() if value != original[key]},
        )
        self._append_event(
            session,
            task_id=task.task_id,
            previous=task.task_state,
            next_state=target,
            reason_code=reason_code,
            actor_ref=actor_ref,
            event_at=event_at,
            attempt_id=attempt_id,
        )
        return transitioned

    def create_task(
        self,
        request: TaskCreateRequest,
        *,
        idempotency_key: str,
        endpoint: str = "/api/platform/v1/tasks",
    ) -> TaskRecord:
        command_key = self._idempotency_key(idempotency_key)
        now = self._now()
        request_hash = compute_content_hash(request.model_dump(mode="python"))
        proposed_task_id = generate_resource_id(ResourceType.TASK)
        with self.database.transaction() as session:
            reserved, recorded_task_id, recorded_hash = self.repository.reserve_command(
                session,
                requested_by=request.requested_by,
                endpoint=endpoint,
                idempotency_key=command_key,
                request_hash=request_hash,
                task_id=proposed_task_id,
                created_at=now,
            )
            if not reserved:
                if recorded_hash != request_hash:
                    raise TaskControlError(
                        "TASK_IDEMPOTENCY_CONFLICT",
                        "Idempotency-Key was already used with a different payload.",
                        details={"endpoint": endpoint},
                    )
                existing = self.repository.get_task(session, recorded_task_id)
                if existing is None:
                    raise TaskControlError(
                        "TASK_IDEMPOTENCY_RECORD_INCOMPLETE",
                        "Idempotent task record is not yet available.",
                        status_code=503,
                        retryable=True,
                    )
                return existing
            task_key = (
                f"{request.task_type}:force:{proposed_task_id}"
                if request.force
                else f"{request.task_type}:{request_hash}"
            )
            accepted = TaskRecord(
                task_id=proposed_task_id,
                task_type=request.task_type,
                task_schema_version=request.task_schema_version,
                task_state=TaskState.ACCEPTED,
                priority_class=request.priority_class,
                priority_value=request.priority_value,
                idempotency_key=f"force:{proposed_task_id}" if request.force else command_key,
                task_key=task_key,
                canonical_request_hash=request_hash,
                requested_by=request.requested_by,
                request_source=request.request_source,
                input_refs=request.input_refs,
                requirements=request.requirements,
                active_attempt_id=None,
                blocked_reason_code=None,
                unblock_condition=None,
                max_attempts=request.max_attempts,
                cancel_requested_at=None,
                result_artifact_id=None,
                created_from_task_id=request.created_from_task_id,
                force_reason=request.force_reason,
                created_at=now,
                queued_at=None,
                terminal_at=None,
                failure_code=None,
            )
            if not self.repository.add_task(session, accepted):
                existing = self.repository.get_task_by_key(session, request.requested_by, task_key)
                if existing is None:
                    raise TaskControlError("TASK_CREATE_CONFLICT", "Task could not be created.")
                self.repository.repoint_command(
                    session,
                    requested_by=request.requested_by,
                    endpoint=endpoint,
                    idempotency_key=command_key,
                    task_id=existing.task_id,
                )
                return existing
            self._append_event(
                session,
                task_id=accepted.task_id,
                previous=None,
                next_state=TaskState.ACCEPTED,
                reason_code="TASK_COMMAND_ACCEPTED",
                actor_ref=request.requested_by,
                event_at=now,
                attempt_id=None,
            )
            return self._transition(
                session,
                accepted,
                TaskState.QUEUED,
                reason_code="TASK_READY",
                actor_ref="scheduler",
                event_at=now,
            )

    def get_task(self, task_id: str) -> TaskDetails:
        with self.database.transaction() as session:
            task = self.repository.get_task(session, task_id)
            if task is None:
                raise TaskControlError("TASK_NOT_FOUND", "Task was not found.", status_code=404)
            attempts = self.repository.list_attempts(session, task_id)
            return TaskDetails(
                task=task,
                attempts=attempts,
                state_events=self.repository.list_events(session, task_id),
                checkpoints=self.repository.list_checkpoints(session, task_id),
                diagnostic_artifact_refs=tuple(
                    ref for attempt in attempts for ref in attempt.diagnostic_artifact_refs
                ),
            )

    def list_tasks(self, query: TaskListQuery) -> tuple[tuple[TaskRecord, ...], str | None, bool]:
        try:
            with self.database.transaction() as session:
                return self.repository.list_tasks(
                    session,
                    tab=query.tab,
                    task_state=query.task_state,
                    task_type=query.task_type,
                    priority_class=query.priority_class,
                    requested_by=query.requested_by,
                    created_from=query.created_from,
                    created_to=query.created_to,
                    resource_id=query.resource_id,
                    cursor=query.cursor,
                    limit=query.limit,
                )
        except ValueError as exc:
            raise TaskControlError("TASK_CURSOR_INVALID", "Task cursor is invalid.", status_code=400) from exc

    def list_event_records(
        self,
        *,
        task_id: str | None = None,
        after_event_id: str | None = None,
        limit: int = 100,
    ) -> tuple[TaskEventRecord, ...]:
        with self.database.transaction() as session:
            if task_id is not None and self.repository.get_task(session, task_id) is None:
                raise TaskControlError("TASK_NOT_FOUND", "Task was not found.", status_code=404)
            events = self.repository.list_all_events(
                session,
                task_id=task_id,
                after_event_id=after_event_id,
                limit=limit,
            )
            return tuple(
                TaskEventRecord(
                    event_id=f"{event.task_id}:{event.event_sequence}",
                    event_type="task_state_changed",
                    resource_ref={"resource_id": event.task_id, "resource_type": ResourceType.TASK.value},
                    task_id=event.task_id,
                    attempt_id=event.attempt_id,
                    sequence=event.event_sequence,
                    occurred_at=event.event_at,
                    payload_schema_version="1.0.0",
                    payload=event,
                )
                for event in events
            )

    def _new_attempt(
        self,
        session: object,
        task: TaskRecord,
        *,
        worker_id: str,
        capabilities: tuple[str, ...],
        leased_at: datetime,
        lease_seconds: int,
    ) -> tuple[TaskAttemptRecord, str]:
        token = self.token_factory()
        if not isinstance(token, str) or len(token) < 32:
            raise ValueError("lease token factory must return at least 32 characters")
        attempt = TaskAttemptRecord(
            attempt_id=generate_resource_id(ResourceType.ATTEMPT),
            task_id=task.task_id,
            attempt_number=self.repository.next_attempt_number(session, task.task_id),
            attempt_phase="CLAIMED",
            phase_progress=0.0,
            worker_id=worker_id,
            worker_capabilities=capabilities,
            lease_token_hash=_secret_hash(token),
            leased_at=leased_at,
            lease_expires_at=leased_at + timedelta(seconds=lease_seconds),
            heartbeat_at=leased_at,
            started_at=None,
            finished_at=None,
            checkpoint_ref=None,
            resource_usage={},
            attempt_outcome=None,
            failure_code=None,
            retryable=None,
            diagnostic_artifact_refs=(),
        )
        self.repository.add_attempt(session, attempt)
        return attempt, token

    def _finish_attempt(
        self,
        session: object,
        attempt: TaskAttemptRecord,
        *,
        outcome: AttemptOutcome,
        finished_at: datetime,
        failure_code: str | None = None,
        retryable: bool | None = None,
    ) -> TaskAttemptRecord:
        if attempt.attempt_outcome is not None:
            raise TaskControlError("TASK_ATTEMPT_IMMUTABLE", "Finished attempts are immutable.")
        finished = TaskAttemptRecord.model_validate(
            {
                **attempt.model_dump(mode="python"),
                "attempt_outcome": outcome,
                "finished_at": finished_at,
                "failure_code": failure_code,
                "retryable": retryable,
            }
        )
        self.repository.update_attempt(
            session,
            attempt.attempt_id,
            attempt_outcome=outcome,
            finished_at=finished_at,
            failure_code=failure_code,
            retryable=retryable,
        )
        return finished

    def _validate_lease(
        self,
        session: object,
        attempt_id: str,
        lease_token: str,
        *,
        now: datetime,
        allowed_states: frozenset[TaskState],
    ) -> tuple[TaskRecord, TaskAttemptRecord]:
        attempt_reference = self.repository.get_attempt(session, attempt_id)
        if attempt_reference is None:
            raise TaskControlError("TASK_ATTEMPT_NOT_FOUND", "Task attempt was not found.", status_code=404)
        task = self.repository.get_task(session, attempt_reference.task_id, for_update=True)
        attempt = self.repository.get_attempt(session, attempt_id, for_update=True)
        valid = (
            task is not None
            and attempt is not None
            and task.active_attempt_id == attempt_id
            and task.task_state in allowed_states
            and attempt.attempt_outcome is None
            and attempt.lease_expires_at > now
            and hmac.compare_digest(attempt.lease_token_hash, _secret_hash(lease_token))
        )
        if not valid:
            raise TaskControlError(
                "TASK_LEASE_LOST",
                "Task lease is no longer valid.",
                details={"attempt_id": attempt_id},
            )
        assert task is not None and attempt is not None
        return task, attempt

    def _recover_expired_running(self, session: object, now: datetime, task_types: tuple[str, ...]) -> None:
        for task_id in self.repository.list_expired_running_task_ids(session, now, task_types):
            task = self.repository.get_task(session, task_id, for_update=True)
            if task is None or task.active_attempt_id is None or task.task_state is not TaskState.RUNNING:
                continue
            attempt = self.repository.get_attempt(session, task.active_attempt_id, for_update=True)
            if attempt is None or attempt.attempt_outcome is not None or attempt.lease_expires_at > now:
                continue
            can_retry = attempt.attempt_number < task.max_attempts
            self._finish_attempt(
                session,
                attempt,
                outcome=AttemptOutcome.LEASE_LOST,
                finished_at=now,
                failure_code="TASK_LEASE_EXPIRED",
                retryable=can_retry,
            )
            if can_retry:
                waiting = self._transition(
                    session,
                    task,
                    TaskState.RETRY_WAIT,
                    reason_code="TASK_LEASE_EXPIRED",
                    actor_ref="lease_reaper",
                    event_at=now,
                    attempt_id=attempt.attempt_id,
                )
                self._transition(
                    session,
                    waiting,
                    TaskState.QUEUED,
                    reason_code="TASK_RETRY_READY",
                    actor_ref="lease_reaper",
                    event_at=now,
                    attempt_id=attempt.attempt_id,
                )
            else:
                self._transition(
                    session,
                    task,
                    TaskState.FAILED,
                    reason_code="TASK_MAX_ATTEMPTS_EXCEEDED",
                    actor_ref="lease_reaper",
                    event_at=now,
                    attempt_id=attempt.attempt_id,
                    updates={"failure_code": "TASK_MAX_ATTEMPTS_EXCEEDED"},
                )

    def lease_next(
        self,
        *,
        worker_id: str,
        worker_capabilities: tuple[str, ...],
        lease_seconds: int = 60,
    ) -> TaskLease | None:
        if not worker_id.strip() or lease_seconds <= 0:
            raise ValueError("worker_id and positive lease_seconds are required")
        capabilities = tuple(sorted(set(worker_capabilities)))
        supported_task_types = tuple(
            sorted(
                set(capabilities)
                & {"artifact_orphan_dry_run", "raw_ingestion", "canonical_normalization"}
            )
        )
        if not supported_task_types:
            return None
        now = self._now()
        with self.database.transaction() as session:
            self._recover_expired_running(session, now, supported_task_types)
            expired = self.repository.claim_expired_leased_task(session, now, supported_task_types)
            if expired is not None:
                task, old_attempt = expired
                can_retry = old_attempt.attempt_number < task.max_attempts
                self._finish_attempt(
                    session,
                    old_attempt,
                    outcome=AttemptOutcome.LEASE_LOST,
                    finished_at=now,
                    failure_code="TASK_LEASE_EXPIRED_BEFORE_START",
                    retryable=can_retry,
                )
                if can_retry:
                    attempt, token = self._new_attempt(
                        session,
                        task,
                        worker_id=worker_id,
                        capabilities=capabilities,
                        leased_at=now,
                        lease_seconds=lease_seconds,
                    )
                    self.repository.update_task(session, task.task_id, active_attempt_id=attempt.attempt_id)
                    current = TaskRecord.model_validate(
                        {**task.model_dump(mode="python"), "active_attempt_id": attempt.attempt_id}
                    )
                    return TaskLease(task=current, attempt=attempt, lease_token=token)
                running = self._transition(
                    session,
                    task,
                    TaskState.RUNNING,
                    reason_code="TASK_LEASE_EXPIRY_REAPED",
                    actor_ref="lease_reaper",
                    event_at=now,
                    attempt_id=old_attempt.attempt_id,
                )
                self._transition(
                    session,
                    running,
                    TaskState.FAILED,
                    reason_code="TASK_MAX_ATTEMPTS_EXCEEDED",
                    actor_ref="lease_reaper",
                    event_at=now,
                    attempt_id=old_attempt.attempt_id,
                    updates={"failure_code": "TASK_MAX_ATTEMPTS_EXCEEDED"},
                )
            task = self.repository.claim_queued_task(session, supported_task_types)
            if task is None:
                return None
            attempt, token = self._new_attempt(
                session,
                task,
                worker_id=worker_id,
                capabilities=capabilities,
                leased_at=now,
                lease_seconds=lease_seconds,
            )
            leased = self._transition(
                session,
                task,
                TaskState.LEASED,
                reason_code="TASK_LEASE_ACQUIRED",
                actor_ref=f"worker:{worker_id}",
                event_at=now,
                attempt_id=attempt.attempt_id,
                updates={"active_attempt_id": attempt.attempt_id},
            )
            return TaskLease(task=leased, attempt=attempt, lease_token=token)

    def start_attempt(self, attempt_id: str, lease_token: str) -> TaskAttemptRecord:
        now = self._now()
        with self.database.transaction() as session:
            task, attempt = self._validate_lease(
                session,
                attempt_id,
                lease_token,
                now=now,
                allowed_states=frozenset({TaskState.LEASED}),
            )
            self.repository.update_attempt(
                session,
                attempt_id,
                attempt_phase="INITIALIZING",
                started_at=now,
                heartbeat_at=now,
            )
            self._transition(
                session,
                task,
                TaskState.RUNNING,
                reason_code="TASK_WORKER_STARTED",
                actor_ref=f"worker:{attempt.worker_id}",
                event_at=now,
                attempt_id=attempt_id,
            )
            return TaskAttemptRecord.model_validate(
                {
                    **attempt.model_dump(mode="python"),
                    "attempt_phase": "INITIALIZING",
                    "started_at": now,
                    "heartbeat_at": now,
                }
            )

    def heartbeat(self, attempt_id: str, lease_token: str, *, lease_seconds: int = 60) -> TaskAttemptRecord:
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        now = self._now()
        with self.database.transaction() as session:
            _, attempt = self._validate_lease(
                session,
                attempt_id,
                lease_token,
                now=now,
                allowed_states=frozenset({TaskState.LEASED, TaskState.RUNNING}),
            )
            expires_at = max(attempt.lease_expires_at, now) + timedelta(seconds=lease_seconds)
            self.repository.update_attempt(
                session,
                attempt_id,
                heartbeat_at=now,
                lease_expires_at=expires_at,
            )
            return TaskAttemptRecord.model_validate(
                {**attempt.model_dump(mode="python"), "heartbeat_at": now, "lease_expires_at": expires_at}
            )

    def request_cancel(
        self,
        task_id: str,
        *,
        reason_code: str = "TASK_CANCEL_REQUESTED",
        actor_ref: str = "platform_api",
    ) -> TaskRecord:
        now = self._now()
        with self.database.transaction() as session:
            task = self.repository.get_task(session, task_id, for_update=True)
            if task is None:
                raise TaskControlError("TASK_NOT_FOUND", "Task was not found.", status_code=404)
            if task.task_state in {TaskState.QUEUED, TaskState.BLOCKED}:
                return self._transition(
                    session,
                    task,
                    TaskState.CANCELLED,
                    reason_code=reason_code,
                    actor_ref=actor_ref,
                    event_at=now,
                    updates={"cancel_requested_at": now},
                )
            if task.task_state in {TaskState.LEASED, TaskState.RUNNING}:
                if task.cancel_requested_at is None:
                    self.repository.update_task(session, task_id, cancel_requested_at=now)
                    return TaskRecord.model_validate(
                        {**task.model_dump(mode="python"), "cancel_requested_at": now}
                    )
                return task
            if task.task_state is TaskState.CANCELLED:
                return task
            raise TaskControlError("TASK_CANCEL_NOT_ALLOWED", "Task cannot be cancelled in its current state.")

    def acknowledge_cancel(self, attempt_id: str, lease_token: str) -> TaskRecord:
        now = self._now()
        with self.database.transaction() as session:
            task, attempt = self._validate_lease(
                session,
                attempt_id,
                lease_token,
                now=now,
                allowed_states=frozenset({TaskState.RUNNING}),
            )
            if task.cancel_requested_at is None:
                raise TaskControlError("TASK_CANCEL_NOT_REQUESTED", "Task cancellation was not requested.")
            self._finish_attempt(session, attempt, outcome=AttemptOutcome.CANCELLED, finished_at=now)
            return self._transition(
                session,
                task,
                TaskState.CANCELLED,
                reason_code="TASK_CANCELLED_AT_SAFE_POINT",
                actor_ref=f"worker:{attempt.worker_id}",
                event_at=now,
                attempt_id=attempt_id,
            )

    def record_failure(
        self,
        attempt_id: str,
        lease_token: str,
        *,
        failure_code: str,
        retryable: bool,
    ) -> TaskRecord:
        now = self._now()
        with self.database.transaction() as session:
            task, attempt = self._validate_lease(
                session,
                attempt_id,
                lease_token,
                now=now,
                allowed_states=frozenset({TaskState.RUNNING}),
            )
            can_retry = retryable and attempt.attempt_number < task.max_attempts
            self._finish_attempt(
                session,
                attempt,
                outcome=AttemptOutcome.FAILED,
                finished_at=now,
                failure_code=failure_code,
                retryable=can_retry,
            )
            if can_retry:
                return self._transition(
                    session,
                    task,
                    TaskState.RETRY_WAIT,
                    reason_code=failure_code,
                    actor_ref=f"worker:{attempt.worker_id}",
                    event_at=now,
                    attempt_id=attempt_id,
                )
            return self._transition(
                session,
                task,
                TaskState.FAILED,
                reason_code=failure_code,
                actor_ref=f"worker:{attempt.worker_id}",
                event_at=now,
                attempt_id=attempt_id,
                updates={"failure_code": failure_code},
            )

    def request_retry(
        self,
        task_id: str,
        *,
        reason_code: str = "TASK_RETRY_REQUESTED",
        actor_ref: str = "platform_api",
    ) -> TaskRecord:
        now = self._now()
        with self.database.transaction() as session:
            task = self.repository.get_task(session, task_id, for_update=True)
            if task is None:
                raise TaskControlError("TASK_NOT_FOUND", "Task was not found.", status_code=404)
            if task.task_state is not TaskState.RETRY_WAIT:
                raise TaskControlError("TASK_RETRY_NOT_ALLOWED", "Task is not waiting for retry.")
            return self._transition(
                session,
                task,
                TaskState.QUEUED,
                reason_code=reason_code,
                actor_ref=actor_ref,
                event_at=now,
            )

    def block_task(
        self,
        task_id: str,
        *,
        reason_code: str,
        unblock_condition: str,
        actor_ref: str,
        attempt_id: str | None = None,
        lease_token: str | None = None,
    ) -> TaskRecord:
        now = self._now()
        with self.database.transaction() as session:
            if attempt_id is not None:
                if lease_token is None:
                    raise TaskControlError("TASK_LEASE_REQUIRED", "A valid task lease is required.")
                task, attempt = self._validate_lease(
                    session,
                    attempt_id,
                    lease_token,
                    now=now,
                    allowed_states=frozenset({TaskState.RUNNING}),
                )
                self._finish_attempt(session, attempt, outcome=AttemptOutcome.BLOCKED, finished_at=now)
            else:
                task = self.repository.get_task(session, task_id, for_update=True)
                attempt = None
                if task is None:
                    raise TaskControlError("TASK_NOT_FOUND", "Task was not found.", status_code=404)
                if task.task_state is not TaskState.QUEUED:
                    raise TaskControlError("TASK_BLOCK_NOT_ALLOWED", "Task cannot be blocked in its current state.")
            return self._transition(
                session,
                task,
                TaskState.BLOCKED,
                reason_code=reason_code,
                actor_ref=actor_ref,
                event_at=now,
                attempt_id=attempt.attempt_id if attempt is not None else None,
                updates={
                    "blocked_reason_code": reason_code,
                    "unblock_condition": unblock_condition,
                },
            )

    def unblock_task(
        self,
        task_id: str,
        *,
        actor_ref: str,
        reason_code: str = "TASK_UNBLOCK_CONDITION_MET",
    ) -> TaskRecord:
        now = self._now()
        with self.database.transaction() as session:
            task = self.repository.get_task(session, task_id, for_update=True)
            if task is None:
                raise TaskControlError("TASK_NOT_FOUND", "Task was not found.", status_code=404)
            if task.task_state is not TaskState.BLOCKED:
                raise TaskControlError("TASK_UNBLOCK_NOT_ALLOWED", "Task is not blocked.")
            return self._transition(
                session,
                task,
                TaskState.QUEUED,
                reason_code=reason_code,
                actor_ref=actor_ref,
                event_at=now,
            )

    def save_checkpoint(
        self,
        attempt_id: str,
        lease_token: str,
        *,
        phase: str,
        input_hash: str,
        handler_version: str,
        storage_ref: StorageRef,
        expires_at: datetime,
    ) -> tuple[TaskCheckpointRecord, str]:
        if self.resolver is None:
            raise TaskControlError(
                "TASK_CHECKPOINT_STORAGE_UNAVAILABLE",
                "Checkpoint storage is not configured.",
                status_code=503,
            )
        now = self._now()
        path = self.resolver.resolve(storage_ref, require_exists=True)
        content = path.read_bytes()
        if len(content) != storage_ref.size_bytes or compute_bytes_hash(content) != storage_ref.content_hash:
            raise TaskControlError(
                "TASK_CHECKPOINT_INTEGRITY_FAILED",
                "Checkpoint integrity validation failed.",
            )
        resume_token = self.token_factory()
        with self.database.transaction() as session:
            task, _ = self._validate_lease(
                session,
                attempt_id,
                lease_token,
                now=now,
                allowed_states=frozenset({TaskState.RUNNING}),
            )
            checkpoint = TaskCheckpointRecord(
                checkpoint_id=generate_resource_id(ResourceType.CHECKPOINT),
                task_id=task.task_id,
                attempt_id=attempt_id,
                phase=phase,
                sequence=self.repository.next_checkpoint_sequence(session, attempt_id),
                resume_token_hash=_secret_hash(resume_token),
                input_hash=input_hash,
                handler_version=handler_version,
                storage_ref=storage_ref,
                checkpoint_hash=storage_ref.content_hash,
                created_at=now,
                expires_at=expires_at,
            )
            self.repository.add_checkpoint(session, checkpoint)
            self.repository.update_attempt(session, attempt_id, checkpoint_ref=checkpoint.checkpoint_id)
            return checkpoint, resume_token

    def validate_checkpoint(
        self,
        checkpoint_id: str,
        *,
        resume_token: str,
        input_hash: str,
        handler_version: str,
    ) -> TaskCheckpointRecord:
        if self.resolver is None:
            raise TaskControlError(
                "TASK_CHECKPOINT_STORAGE_UNAVAILABLE",
                "Checkpoint storage is not configured.",
                status_code=503,
            )
        now = self._now()
        with self.database.transaction() as session:
            checkpoint = self.repository.get_checkpoint(session, checkpoint_id)
        if checkpoint is None:
            raise TaskControlError("TASK_CHECKPOINT_NOT_FOUND", "Checkpoint was not found.", status_code=404)
        valid_metadata = (
            checkpoint.expires_at > now
            and hmac.compare_digest(checkpoint.resume_token_hash, _secret_hash(resume_token))
            and checkpoint.input_hash == input_hash
            and checkpoint.handler_version == handler_version
        )
        if not valid_metadata:
            raise TaskControlError("TASK_CHECKPOINT_INVALID", "Checkpoint cannot be resumed.")
        try:
            path = self.resolver.resolve(checkpoint.storage_ref, require_exists=True)
            content = path.read_bytes()
        except Exception as exc:
            raise TaskControlError("TASK_CHECKPOINT_INVALID", "Checkpoint cannot be resumed.") from exc
        if len(content) != checkpoint.storage_ref.size_bytes or compute_bytes_hash(content) != checkpoint.checkpoint_hash:
            raise TaskControlError("TASK_CHECKPOINT_INVALID", "Checkpoint cannot be resumed.")
        return checkpoint

    def complete_in_session(
        self,
        session: object,
        *,
        attempt_id: str,
        lease_token: str,
        degraded: bool = False,
        result_artifact_id: str | None = None,
    ) -> TaskRecord:
        """Finish a worker attempt in the caller-owned registry transaction."""
        now = self._now()
        task, attempt = self._validate_lease(
            session,
            attempt_id,
            lease_token,
            now=now,
            allowed_states=frozenset({TaskState.RUNNING}),
        )
        if task.cancel_requested_at is not None:
            raise TaskControlError("TASK_CANCEL_PENDING", "Cancelled task cannot publish a result.")
        self._finish_attempt(
            session,
            attempt,
            outcome=AttemptOutcome.DEGRADED if degraded else AttemptOutcome.SUCCEEDED,
            finished_at=now,
        )
        updates = {"result_artifact_id": result_artifact_id} if result_artifact_id is not None else None
        return self._transition(
            session,
            task,
            TaskState.DEGRADED if degraded else TaskState.SUCCEEDED,
            reason_code="TASK_RESULT_PUBLISHED",
            actor_ref=f"worker:{attempt.worker_id}",
            event_at=now,
            attempt_id=attempt_id,
            updates=updates,
        )

    def record_failure_in_session(
        self,
        session: object,
        *,
        attempt_id: str,
        lease_token: str,
        failure_code: str,
        retryable: bool,
    ) -> TaskRecord:
        """Record worker failure atomically with another control-plane write."""
        now = self._now()
        task, attempt = self._validate_lease(
            session,
            attempt_id,
            lease_token,
            now=now,
            allowed_states=frozenset({TaskState.RUNNING}),
        )
        can_retry = retryable and attempt.attempt_number < task.max_attempts
        self._finish_attempt(
            session,
            attempt,
            outcome=AttemptOutcome.FAILED,
            finished_at=now,
            failure_code=failure_code,
            retryable=can_retry,
        )
        if can_retry:
            return self._transition(
                session,
                task,
                TaskState.RETRY_WAIT,
                reason_code=failure_code,
                actor_ref=f"worker:{attempt.worker_id}",
                event_at=now,
                attempt_id=attempt_id,
            )
        return self._transition(
            session,
            task,
            TaskState.FAILED,
            reason_code=failure_code,
            actor_ref=f"worker:{attempt.worker_id}",
            event_at=now,
            attempt_id=attempt_id,
            updates={"failure_code": failure_code},
        )

    def complete_with_artifact_in_session(
        self,
        session: object,
        *,
        attempt_id: str,
        lease_token: str,
        artifact_id: str,
        degraded: bool = False,
    ) -> TaskRecord:
        return self.complete_in_session(
            session,
            attempt_id=attempt_id,
            lease_token=lease_token,
            degraded=degraded,
            result_artifact_id=artifact_id,
        )
