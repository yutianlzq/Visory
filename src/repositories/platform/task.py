from __future__ import annotations

from datetime import datetime, timezone
import base64
import json
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    and_,
    func,
    insert,
    or_,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import JSONB, insert as postgresql_insert
from sqlalchemy.orm import Session

from src.schemas.platform import (
    AttemptOutcome,
    PriorityClass,
    ResourceRef,
    StorageBackend,
    StorageNamespace,
    StorageRef,
    TaskAttemptRecord,
    TaskCheckpointRecord,
    TaskRecord,
    TaskState,
    TaskStateEventRecord,
)


metadata = MetaData()

platform_task = Table(
    "platform_task",
    metadata,
    Column("task_id", String(64), primary_key=True),
    Column("task_type", String(64), nullable=False),
    Column("task_schema_version", String(32), nullable=False),
    Column("task_state", String(16), nullable=False),
    Column("priority_class", String(32), nullable=False),
    Column("priority_value", Integer, nullable=False),
    Column("idempotency_key", String(255), nullable=False),
    Column("task_key", String(512), nullable=False),
    Column("canonical_request_hash", String(71), nullable=False),
    Column("requested_by", String(255), nullable=False),
    Column("request_source", String(64), nullable=False),
    Column("input_refs", JSONB, nullable=False),
    Column("requirements", JSONB, nullable=False),
    Column("active_attempt_id", String(64)),
    Column("blocked_reason_code", String(64)),
    Column("unblock_condition", Text),
    Column("max_attempts", Integer, nullable=False),
    Column("cancel_requested_at", DateTime(timezone=True)),
    Column("result_artifact_id", String(64), ForeignKey("artifact_registry.artifact_id", deferrable=True, initially="DEFERRED")),
    Column("created_from_task_id", String(64)),
    Column("force_reason", Text),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("queued_at", DateTime(timezone=True)),
    Column("terminal_at", DateTime(timezone=True)),
    Column("failure_code", String(64)),
    ForeignKeyConstraint(["created_from_task_id"], ["platform_task.task_id"], deferrable=True, initially="DEFERRED"),
)

task_attempt = Table(
    "task_attempt",
    metadata,
    Column("attempt_id", String(64), primary_key=True),
    Column("task_id", String(64), ForeignKey("platform_task.task_id", ondelete="CASCADE"), nullable=False),
    Column("attempt_number", Integer, nullable=False),
    Column("attempt_phase", String(64), nullable=False),
    Column("phase_progress", Float, nullable=False),
    Column("worker_id", String(255), nullable=False),
    Column("worker_capabilities", JSONB, nullable=False),
    Column("lease_token_hash", String(71), nullable=False),
    Column("leased_at", DateTime(timezone=True), nullable=False),
    Column("lease_expires_at", DateTime(timezone=True), nullable=False),
    Column("heartbeat_at", DateTime(timezone=True), nullable=False),
    Column("started_at", DateTime(timezone=True)),
    Column("finished_at", DateTime(timezone=True)),
    Column("checkpoint_ref", String(64)),
    Column("resource_usage", JSONB, nullable=False),
    Column("attempt_outcome", String(32)),
    Column("failure_code", String(64)),
    Column("retryable", Boolean),
    Column("diagnostic_artifact_refs", JSONB, nullable=False),
)

# The migration adds this circular FK after both tables exist.
platform_task.append_constraint(
    ForeignKeyConstraint(
        [platform_task.c.active_attempt_id],
        [task_attempt.c.attempt_id],
        name="fk_platform_task_active_attempt",
        deferrable=True,
        initially="DEFERRED",
    )
)

task_state_event = Table(
    "task_state_event",
    metadata,
    Column("task_id", String(64), ForeignKey("platform_task.task_id", ondelete="CASCADE"), primary_key=True),
    Column("event_sequence", BigInteger, primary_key=True),
    Column("previous_task_state", String(16)),
    Column("next_task_state", String(16), nullable=False),
    Column("reason_code", String(64), nullable=False),
    Column("actor_ref", String(255), nullable=False),
    Column("event_at", DateTime(timezone=True), nullable=False),
    Column("attempt_id", String(64), ForeignKey("task_attempt.attempt_id", deferrable=True, initially="DEFERRED")),
)

task_checkpoint = Table(
    "task_checkpoint",
    metadata,
    Column("checkpoint_id", String(64), primary_key=True),
    Column("task_id", String(64), ForeignKey("platform_task.task_id", ondelete="CASCADE"), nullable=False),
    Column("attempt_id", String(64), ForeignKey("task_attempt.attempt_id", ondelete="CASCADE"), nullable=False),
    Column("phase", String(64), nullable=False),
    Column("sequence", Integer, nullable=False),
    Column("resume_token_hash", String(71), nullable=False),
    Column("input_hash", String(71), nullable=False),
    Column("handler_version", String(255), nullable=False),
    Column("storage_backend", String(32), nullable=False),
    Column("storage_namespace", String(32), nullable=False),
    Column("relative_path", String(1024), nullable=False),
    Column("content_hash", String(71), nullable=False),
    Column("media_type", String(255), nullable=False),
    Column("size_bytes", BigInteger, nullable=False),
    Column("checkpoint_hash", String(71), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
)

task_command_idempotency = Table(
    "task_command_idempotency",
    metadata,
    Column("requested_by", String(255), primary_key=True),
    Column("endpoint", String(255), primary_key=True),
    Column("idempotency_key", String(255), primary_key=True),
    Column("request_hash", String(71), nullable=False),
    Column("task_id", String(64), ForeignKey("platform_task.task_id", deferrable=True, initially="DEFERRED", ondelete="CASCADE"), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)


def _task_values(record: TaskRecord) -> dict[str, object]:
    return {
        **record.model_dump(mode="python", exclude={"input_refs", "priority_class", "task_state"}),
        "task_state": record.task_state.value,
        "priority_class": record.priority_class.value,
        "input_refs": [item.model_dump(mode="json") for item in record.input_refs],
    }


def _task_record(row: Any) -> TaskRecord:
    return TaskRecord(
        task_id=row["task_id"],
        task_type=row["task_type"],
        task_schema_version=row["task_schema_version"],
        task_state=TaskState(row["task_state"]),
        priority_class=PriorityClass(row["priority_class"]),
        priority_value=row["priority_value"],
        idempotency_key=row["idempotency_key"],
        task_key=row["task_key"],
        canonical_request_hash=row["canonical_request_hash"],
        requested_by=row["requested_by"],
        request_source=row["request_source"],
        input_refs=tuple(ResourceRef.model_validate(item) for item in row["input_refs"]),
        requirements=dict(row["requirements"]),
        active_attempt_id=row["active_attempt_id"],
        blocked_reason_code=row["blocked_reason_code"],
        unblock_condition=row["unblock_condition"],
        max_attempts=row["max_attempts"],
        cancel_requested_at=row["cancel_requested_at"],
        result_artifact_id=row["result_artifact_id"],
        created_from_task_id=row["created_from_task_id"],
        force_reason=row["force_reason"],
        created_at=row["created_at"],
        queued_at=row["queued_at"],
        terminal_at=row["terminal_at"],
        failure_code=row["failure_code"],
    )


def _attempt_values(record: TaskAttemptRecord) -> dict[str, object]:
    return {
        **record.model_dump(
            mode="python",
            exclude={"worker_capabilities", "attempt_outcome", "diagnostic_artifact_refs"},
        ),
        "worker_capabilities": list(record.worker_capabilities),
        "attempt_outcome": record.attempt_outcome.value if record.attempt_outcome is not None else None,
        "diagnostic_artifact_refs": list(record.diagnostic_artifact_refs),
    }


def _attempt_record(row: Any) -> TaskAttemptRecord:
    return TaskAttemptRecord(
        attempt_id=row["attempt_id"],
        task_id=row["task_id"],
        attempt_number=row["attempt_number"],
        attempt_phase=row["attempt_phase"],
        phase_progress=row["phase_progress"],
        worker_id=row["worker_id"],
        worker_capabilities=tuple(row["worker_capabilities"]),
        lease_token_hash=row["lease_token_hash"],
        leased_at=row["leased_at"],
        lease_expires_at=row["lease_expires_at"],
        heartbeat_at=row["heartbeat_at"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        checkpoint_ref=row["checkpoint_ref"],
        resource_usage=dict(row["resource_usage"]),
        attempt_outcome=AttemptOutcome(row["attempt_outcome"]) if row["attempt_outcome"] else None,
        failure_code=row["failure_code"],
        retryable=row["retryable"],
        diagnostic_artifact_refs=tuple(row["diagnostic_artifact_refs"]),
    )


def _event_record(row: Any) -> TaskStateEventRecord:
    return TaskStateEventRecord(
        task_id=row["task_id"],
        event_sequence=row["event_sequence"],
        previous_task_state=TaskState(row["previous_task_state"]) if row["previous_task_state"] else None,
        next_task_state=TaskState(row["next_task_state"]),
        reason_code=row["reason_code"],
        actor_ref=row["actor_ref"],
        event_at=row["event_at"],
        attempt_id=row["attempt_id"],
    )


def _checkpoint_values(record: TaskCheckpointRecord) -> dict[str, object]:
    return {
        "checkpoint_id": record.checkpoint_id,
        "task_id": record.task_id,
        "attempt_id": record.attempt_id,
        "phase": record.phase,
        "sequence": record.sequence,
        "resume_token_hash": record.resume_token_hash,
        "input_hash": record.input_hash,
        "handler_version": record.handler_version,
        "storage_backend": record.storage_ref.storage_backend.value,
        "storage_namespace": record.storage_ref.storage_namespace.value,
        "relative_path": record.storage_ref.relative_path,
        "content_hash": record.storage_ref.content_hash,
        "media_type": record.storage_ref.media_type,
        "size_bytes": record.storage_ref.size_bytes,
        "checkpoint_hash": record.checkpoint_hash,
        "created_at": record.created_at,
        "expires_at": record.expires_at,
    }


def _checkpoint_record(row: Any) -> TaskCheckpointRecord:
    return TaskCheckpointRecord(
        checkpoint_id=row["checkpoint_id"],
        task_id=row["task_id"],
        attempt_id=row["attempt_id"],
        phase=row["phase"],
        sequence=row["sequence"],
        resume_token_hash=row["resume_token_hash"],
        input_hash=row["input_hash"],
        handler_version=row["handler_version"],
        storage_ref=StorageRef(
            storage_backend=StorageBackend(row["storage_backend"]),
            storage_namespace=StorageNamespace(row["storage_namespace"]),
            relative_path=row["relative_path"],
            content_hash=row["content_hash"],
            media_type=row["media_type"],
            size_bytes=row["size_bytes"],
        ),
        checkpoint_hash=row["checkpoint_hash"],
        created_at=row["created_at"],
        expires_at=row["expires_at"],
    )


class TaskControlRepository:
    """Durable task persistence. Every caller owns its transaction boundary."""

    @staticmethod
    def reserve_command(
        session: Session,
        *,
        requested_by: str,
        endpoint: str,
        idempotency_key: str,
        request_hash: str,
        task_id: str,
        created_at: datetime,
    ) -> tuple[bool, str, str]:
        statement = (
            postgresql_insert(task_command_idempotency)
            .values(
                requested_by=requested_by,
                endpoint=endpoint,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                task_id=task_id,
                created_at=created_at,
            )
            .on_conflict_do_nothing(
                index_elements=[
                    task_command_idempotency.c.requested_by,
                    task_command_idempotency.c.endpoint,
                    task_command_idempotency.c.idempotency_key,
                ]
            )
            .returning(task_command_idempotency.c.task_id)
        )
        inserted_task_id = session.execute(statement).scalar_one_or_none()
        if inserted_task_id is not None:
            return True, task_id, request_hash
        row = session.execute(
            select(task_command_idempotency.c.task_id, task_command_idempotency.c.request_hash).where(
                task_command_idempotency.c.requested_by == requested_by,
                task_command_idempotency.c.endpoint == endpoint,
                task_command_idempotency.c.idempotency_key == idempotency_key,
            )
        ).one()
        return False, row.task_id, row.request_hash

    @staticmethod
    def repoint_command(session: Session, *, requested_by: str, endpoint: str, idempotency_key: str, task_id: str) -> None:
        session.execute(
            update(task_command_idempotency)
            .where(
                task_command_idempotency.c.requested_by == requested_by,
                task_command_idempotency.c.endpoint == endpoint,
                task_command_idempotency.c.idempotency_key == idempotency_key,
            )
            .values(task_id=task_id)
        )

    @staticmethod
    def add_task(session: Session, record: TaskRecord) -> bool:
        statement = (
            postgresql_insert(platform_task)
            .values(**_task_values(record))
            .on_conflict_do_nothing(index_elements=[platform_task.c.requested_by, platform_task.c.task_key])
            .returning(platform_task.c.task_id)
        )
        return session.execute(statement).scalar_one_or_none() is not None

    @staticmethod
    def get_task_by_key(session: Session, requested_by: str, task_key: str) -> TaskRecord | None:
        row = session.execute(
            select(platform_task).where(
                platform_task.c.requested_by == requested_by,
                platform_task.c.task_key == task_key,
            )
        ).mappings().one_or_none()
        return _task_record(row) if row is not None else None

    @staticmethod
    def get_task(session: Session, task_id: str, *, for_update: bool = False) -> TaskRecord | None:
        statement = select(platform_task).where(platform_task.c.task_id == task_id)
        if for_update:
            statement = statement.with_for_update()
        row = session.execute(statement).mappings().one_or_none()
        return _task_record(row) if row is not None else None

    @staticmethod
    def update_task(session: Session, task_id: str, **values: object) -> None:
        normalized = {
            key: (value.value if isinstance(value, (TaskState, PriorityClass)) else value)
            for key, value in values.items()
        }
        session.execute(update(platform_task).where(platform_task.c.task_id == task_id).values(**normalized))

    @staticmethod
    def next_event_sequence(session: Session, task_id: str) -> int:
        return int(
            session.execute(
                select(func.coalesce(func.max(task_state_event.c.event_sequence), 0) + 1).where(
                    task_state_event.c.task_id == task_id
                )
            ).scalar_one()
        )

    @classmethod
    def append_event(cls, session: Session, record: TaskStateEventRecord) -> None:
        session.execute(
            insert(task_state_event).values(
                task_id=record.task_id,
                event_sequence=record.event_sequence,
                previous_task_state=(
                    record.previous_task_state.value if record.previous_task_state is not None else None
                ),
                next_task_state=record.next_task_state.value,
                reason_code=record.reason_code,
                actor_ref=record.actor_ref,
                event_at=record.event_at,
                attempt_id=record.attempt_id,
            )
        )

    @staticmethod
    def list_tasks(
        session: Session,
        *,
        tab: str | None = None,
        task_state: TaskState | None = None,
        task_type: str | None = None,
        priority_class: PriorityClass | None = None,
        requested_by: str | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
        resource_id: str | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> tuple[tuple[TaskRecord, ...], str | None, bool]:
        conditions = []
        if tab == "active":
            conditions.append(platform_task.c.task_state.in_([TaskState.ACCEPTED.value, TaskState.QUEUED.value, TaskState.LEASED.value, TaskState.RUNNING.value, TaskState.RETRY_WAIT.value]))
        elif tab == "blocked":
            conditions.append(platform_task.c.task_state == TaskState.BLOCKED.value)
        elif tab == "failed":
            conditions.append(platform_task.c.task_state == TaskState.FAILED.value)
        elif tab == "history":
            conditions.append(platform_task.c.task_state.in_([TaskState.SUCCEEDED.value, TaskState.DEGRADED.value, TaskState.FAILED.value, TaskState.CANCELLED.value]))
        if task_state is not None:
            conditions.append(platform_task.c.task_state == task_state.value)
        if task_type is not None:
            conditions.append(platform_task.c.task_type == task_type)
        if priority_class is not None:
            conditions.append(platform_task.c.priority_class == priority_class.value)
        if requested_by is not None:
            conditions.append(platform_task.c.requested_by == requested_by)
        if created_from is not None:
            conditions.append(platform_task.c.created_at >= created_from)
        if created_to is not None:
            conditions.append(platform_task.c.created_at <= created_to)
        if resource_id is not None:
            conditions.append(
                or_(
                    platform_task.c.task_id == resource_id,
                    platform_task.c.result_artifact_id == resource_id,
                    platform_task.c.active_attempt_id == resource_id,
                    platform_task.c.input_refs.contains([{"resource_id": resource_id}]),
                )
            )
        if cursor:
            try:
                decoded = json.loads(base64.urlsafe_b64decode(cursor.encode("ascii") + b"=" * (-len(cursor) % 4)))
                cursor_at = datetime.fromisoformat(decoded[0])
                cursor_id = str(decoded[1])
            except (ValueError, TypeError, json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise ValueError("invalid task cursor") from exc
            conditions.append(
                or_(
                    platform_task.c.created_at < cursor_at,
                    and_(platform_task.c.created_at == cursor_at, platform_task.c.task_id < cursor_id),
                )
            )
        statement = select(platform_task).order_by(platform_task.c.created_at.desc(), platform_task.c.task_id.desc()).limit(limit + 1)
        if conditions:
            statement = statement.where(and_(*conditions))
        rows = list(session.execute(statement).mappings())
        has_more = len(rows) > limit
        rows = rows[:limit]
        records = tuple(_task_record(row) for row in rows)
        next_cursor = None
        if has_more and records:
            last = records[-1]
            raw = json.dumps([last.created_at.astimezone(timezone.utc).isoformat(), last.task_id], separators=(",", ":"))
            next_cursor = base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")
        return records, next_cursor, has_more

    @staticmethod
    def list_all_events(session: Session, *, task_id: str | None = None, after_event_id: str | None = None, limit: int = 100) -> tuple[TaskStateEventRecord, ...]:
        statement = select(task_state_event).order_by(task_state_event.c.event_at, task_state_event.c.task_id, task_state_event.c.event_sequence).limit(limit)
        if task_id is not None:
            statement = statement.where(task_state_event.c.task_id == task_id)
        rows = list(session.execute(statement).mappings())
        events = []
        for row in rows:
            event_id = f"{row['task_id']}:{row['event_sequence']}"
            if after_event_id and event_id <= after_event_id:
                continue
            events.append(_event_record(row))
        return tuple(events)

    @staticmethod
    def list_checkpoints(session: Session, task_id: str) -> tuple[TaskCheckpointRecord, ...]:
        rows = session.execute(select(task_checkpoint).where(task_checkpoint.c.task_id == task_id).order_by(task_checkpoint.c.sequence)).mappings()
        return tuple(_checkpoint_record(row) for row in rows)

    @staticmethod
    def list_events(session: Session, task_id: str) -> tuple[TaskStateEventRecord, ...]:
        rows = session.execute(
            select(task_state_event)
            .where(task_state_event.c.task_id == task_id)
            .order_by(task_state_event.c.event_sequence)
        ).mappings()
        return tuple(_event_record(row) for row in rows)

    @staticmethod
    def next_attempt_number(session: Session, task_id: str) -> int:
        return int(
            session.execute(
                select(func.coalesce(func.max(task_attempt.c.attempt_number), 0) + 1).where(
                    task_attempt.c.task_id == task_id
                )
            ).scalar_one()
        )

    @staticmethod
    def add_attempt(session: Session, record: TaskAttemptRecord) -> None:
        session.execute(insert(task_attempt).values(**_attempt_values(record)))

    @staticmethod
    def get_attempt(session: Session, attempt_id: str, *, for_update: bool = False) -> TaskAttemptRecord | None:
        statement = select(task_attempt).where(task_attempt.c.attempt_id == attempt_id)
        if for_update:
            statement = statement.with_for_update()
        row = session.execute(statement).mappings().one_or_none()
        return _attempt_record(row) if row is not None else None

    @staticmethod
    def get_active_attempt(session: Session, task_id: str, *, for_update: bool = False) -> TaskAttemptRecord | None:
        statement = select(task_attempt).where(
            task_attempt.c.task_id == task_id,
            task_attempt.c.attempt_outcome.is_(None),
        )
        if for_update:
            statement = statement.with_for_update()
        row = session.execute(statement).mappings().one_or_none()
        return _attempt_record(row) if row is not None else None

    @staticmethod
    def list_attempts(session: Session, task_id: str) -> tuple[TaskAttemptRecord, ...]:
        rows = session.execute(
            select(task_attempt)
            .where(task_attempt.c.task_id == task_id)
            .order_by(task_attempt.c.attempt_number)
        ).mappings()
        return tuple(_attempt_record(row) for row in rows)

    @staticmethod
    def update_attempt(session: Session, attempt_id: str, **values: object) -> None:
        normalized = {
            key: (value.value if isinstance(value, AttemptOutcome) else value)
            for key, value in values.items()
        }
        session.execute(update(task_attempt).where(task_attempt.c.attempt_id == attempt_id).values(**normalized))

    @staticmethod
    def claim_queued_task(session: Session) -> TaskRecord | None:
        row = session.execute(
            select(platform_task)
            .where(
                platform_task.c.task_state == TaskState.QUEUED.value,
                platform_task.c.cancel_requested_at.is_(None),
            )
            .order_by(
                platform_task.c.priority_class,
                platform_task.c.priority_value,
                platform_task.c.queued_at,
                platform_task.c.task_id,
            )
            .limit(1)
            .with_for_update(skip_locked=True)
        ).mappings().one_or_none()
        return _task_record(row) if row is not None else None

    @staticmethod
    def claim_expired_leased_task(session: Session, now: datetime) -> tuple[TaskRecord, TaskAttemptRecord] | None:
        row = session.execute(
            select(platform_task, task_attempt)
            .join(task_attempt, platform_task.c.active_attempt_id == task_attempt.c.attempt_id)
            .where(
                platform_task.c.task_state == TaskState.LEASED.value,
                task_attempt.c.attempt_outcome.is_(None),
                task_attempt.c.lease_expires_at <= now,
            )
            .order_by(
                platform_task.c.priority_class,
                platform_task.c.priority_value,
                platform_task.c.queued_at,
                platform_task.c.task_id,
            )
            .limit(1)
            .with_for_update(of=platform_task, skip_locked=True)
        ).mappings().one_or_none()
        if row is None:
            return None
        task_row = {column.name: row[column.name] for column in platform_task.columns}
        attempt_row = {column.name: row[column.name] for column in task_attempt.columns}
        return _task_record(task_row), _attempt_record(attempt_row)

    @staticmethod
    def list_expired_running_task_ids(session: Session, now: datetime) -> tuple[str, ...]:
        rows = session.execute(
            select(platform_task.c.task_id)
            .join(task_attempt, platform_task.c.active_attempt_id == task_attempt.c.attempt_id)
            .where(
                platform_task.c.task_state == TaskState.RUNNING.value,
                task_attempt.c.attempt_outcome.is_(None),
                task_attempt.c.lease_expires_at <= now,
            )
            .order_by(platform_task.c.task_id)
            .with_for_update(of=platform_task, skip_locked=True)
        ).scalars()
        return tuple(rows)

    @staticmethod
    def next_checkpoint_sequence(session: Session, attempt_id: str) -> int:
        return int(
            session.execute(
                select(func.coalesce(func.max(task_checkpoint.c.sequence), 0) + 1).where(
                    task_checkpoint.c.attempt_id == attempt_id
                )
            ).scalar_one()
        )

    @staticmethod
    def add_checkpoint(session: Session, record: TaskCheckpointRecord) -> None:
        session.execute(insert(task_checkpoint).values(**_checkpoint_values(record)))

    @staticmethod
    def get_checkpoint(session: Session, checkpoint_id: str) -> TaskCheckpointRecord | None:
        row = session.execute(
            select(task_checkpoint).where(task_checkpoint.c.checkpoint_id == checkpoint_id)
        ).mappings().one_or_none()
        return _checkpoint_record(row) if row is not None else None


__all__ = [
    "TaskControlRepository",
    "platform_task",
    "task_attempt",
    "task_checkpoint",
    "task_command_idempotency",
    "task_state_event",
]
