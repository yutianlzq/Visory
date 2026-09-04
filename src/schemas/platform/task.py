from __future__ import annotations

import re
from typing import Annotated, Any, Literal

from pydantic import AwareDatetime, Field, field_validator, model_validator

from .base import PlatformContractModel
from .enums import AttemptOutcome, PriorityClass, ResourceType, TaskState
from .resources import ResourceRef, parse_resource_id
from .raw_ingestion import RawIngestionTaskRequirements
from .canonical import CanonicalNormalizationTaskRequirements
from .storage import StorageRef


_HASH_PATTERN = r"^sha256:[0-9a-f]{64}$"
_SEMVER_PATTERN = r"^[0-9]+\.[0-9]+\.[0-9]+$"
_IDENTIFIER_PATTERN = re.compile(r"^[a-z][a-z0-9._-]{0,63}$")
_PHASE_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")
_REASON_CODE_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{2,63}$")
_TERMINAL_STATES = frozenset(
    {TaskState.SUCCEEDED, TaskState.DEGRADED, TaskState.FAILED, TaskState.CANCELLED}
)


def _resource_id(value: str | None, expected: ResourceType, field_name: str) -> str | None:
    if value is None:
        return None
    resource_type, _ = parse_resource_id(value)
    if resource_type is not expected:
        raise ValueError(f"{field_name} must use the {expected.value} resource prefix")
    return value


def _nonblank(value: str | None, field_name: str) -> str | None:
    if value is not None and not value.strip():
        raise ValueError(f"{field_name} cannot be blank")
    return value


def _reason_code(value: str | None, field_name: str) -> str | None:
    if value is not None and not _REASON_CODE_PATTERN.fullmatch(value):
        raise ValueError(f"{field_name} must be a stable uppercase identifier")
    return value


class TaskRecord(PlatformContractModel):
    task_id: str
    task_type: str
    task_schema_version: Annotated[str, Field(pattern=_SEMVER_PATTERN, max_length=32)]
    task_state: TaskState
    priority_class: PriorityClass
    priority_value: int = Field(ge=0, le=2_147_483_647)
    idempotency_key: Annotated[str, Field(min_length=1, max_length=255)]
    task_key: Annotated[str, Field(min_length=1, max_length=512)]
    canonical_request_hash: Annotated[str, Field(pattern=_HASH_PATTERN)]
    requested_by: Annotated[str, Field(min_length=1, max_length=255)]
    request_source: Annotated[str, Field(min_length=1, max_length=64)]
    input_refs: tuple[ResourceRef, ...]
    requirements: dict[str, Any]
    active_attempt_id: str | None = None
    blocked_reason_code: str | None = None
    unblock_condition: str | None = None
    max_attempts: int = Field(ge=1, le=100)
    cancel_requested_at: AwareDatetime | None = None
    result_artifact_id: str | None = None
    created_from_task_id: str | None = None
    force_reason: str | None = None
    created_at: AwareDatetime
    queued_at: AwareDatetime | None
    terminal_at: AwareDatetime | None = None
    failure_code: str | None = None

    @field_validator("task_id")
    @classmethod
    def validate_task_id(cls, value: str) -> str:
        return _resource_id(value, ResourceType.TASK, "task_id") or value

    @field_validator("active_attempt_id")
    @classmethod
    def validate_attempt_id(cls, value: str | None) -> str | None:
        return _resource_id(value, ResourceType.ATTEMPT, "active_attempt_id")

    @field_validator("result_artifact_id")
    @classmethod
    def validate_artifact_id(cls, value: str | None) -> str | None:
        return _resource_id(value, ResourceType.ARTIFACT, "result_artifact_id")

    @field_validator("created_from_task_id")
    @classmethod
    def validate_created_from_task_id(cls, value: str | None) -> str | None:
        return _resource_id(value, ResourceType.TASK, "created_from_task_id")

    @field_validator("task_type")
    @classmethod
    def validate_task_type(cls, value: str) -> str:
        if not _IDENTIFIER_PATTERN.fullmatch(value):
            raise ValueError("task_type must be a normalized identifier")
        return value

    @field_validator(
        "idempotency_key",
        "task_key",
        "requested_by",
        "request_source",
        "unblock_condition",
        "force_reason",
    )
    @classmethod
    def validate_nonblank(cls, value: str | None, info: object) -> str | None:
        return _nonblank(value, getattr(info, "field_name", "value"))

    @field_validator("blocked_reason_code", "failure_code")
    @classmethod
    def validate_reason_code(cls, value: str | None, info: object) -> str | None:
        return _reason_code(value, getattr(info, "field_name", "reason_code"))

    @model_validator(mode="after")
    def validate_task_semantics(self) -> "TaskRecord":
        if self.created_from_task_id == self.task_id:
            raise ValueError("created_from_task_id cannot reference the same task")
        if len(self.input_refs) != len({item.resource_id for item in self.input_refs}):
            raise ValueError("input_refs cannot contain duplicates")
        if self.task_state is TaskState.BLOCKED:
            if self.blocked_reason_code is None or self.unblock_condition is None:
                raise ValueError("BLOCKED requires blocked_reason_code and unblock_condition")
        elif self.blocked_reason_code is not None or self.unblock_condition is not None:
            raise ValueError("blocking fields only apply to BLOCKED tasks")
        if self.task_state is TaskState.FAILED:
            if self.failure_code is None:
                raise ValueError("FAILED requires failure_code")
        elif self.failure_code is not None:
            raise ValueError("failure_code only applies to FAILED tasks")
        if self.task_state in _TERMINAL_STATES:
            if self.terminal_at is None:
                raise ValueError("terminal task requires terminal_at")
        elif self.terminal_at is not None:
            raise ValueError("non-terminal task cannot have terminal_at")
        if self.result_artifact_id is not None and self.task_state not in {
            TaskState.SUCCEEDED,
            TaskState.DEGRADED,
        }:
            raise ValueError("result_artifact_id only applies to successful task states")
        if self.active_attempt_id is not None and self.task_state not in {
            TaskState.LEASED,
            TaskState.RUNNING,
        }:
            raise ValueError("active_attempt_id only applies to leased or running tasks")
        if self.force_reason is not None and self.created_from_task_id is None:
            raise ValueError("force_reason requires created_from_task_id")
        return self


class TaskAttemptRecord(PlatformContractModel):
    attempt_id: str
    task_id: str
    attempt_number: int = Field(ge=1)
    attempt_phase: str
    phase_progress: float = Field(ge=0.0, le=1.0)
    worker_id: Annotated[str, Field(min_length=1, max_length=255)]
    worker_capabilities: tuple[str, ...]
    lease_token_hash: Annotated[str, Field(pattern=_HASH_PATTERN)]
    leased_at: AwareDatetime
    lease_expires_at: AwareDatetime
    heartbeat_at: AwareDatetime
    started_at: AwareDatetime | None = None
    finished_at: AwareDatetime | None = None
    checkpoint_ref: str | None = None
    resource_usage: dict[str, float]
    attempt_outcome: AttemptOutcome | None = None
    failure_code: str | None = None
    retryable: bool | None = None
    diagnostic_artifact_refs: tuple[str, ...]

    @field_validator("attempt_id")
    @classmethod
    def validate_attempt_id(cls, value: str) -> str:
        return _resource_id(value, ResourceType.ATTEMPT, "attempt_id") or value

    @field_validator("task_id")
    @classmethod
    def validate_task_id(cls, value: str) -> str:
        return _resource_id(value, ResourceType.TASK, "task_id") or value

    @field_validator("checkpoint_ref")
    @classmethod
    def validate_checkpoint_ref(cls, value: str | None) -> str | None:
        return _resource_id(value, ResourceType.CHECKPOINT, "checkpoint_ref")

    @field_validator("diagnostic_artifact_refs")
    @classmethod
    def validate_diagnostic_refs(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for item in value:
            _resource_id(item, ResourceType.ARTIFACT, "diagnostic_artifact_refs")
        if len(value) != len(set(value)):
            raise ValueError("diagnostic_artifact_refs cannot contain duplicates")
        return value

    @field_validator("attempt_phase")
    @classmethod
    def validate_phase(cls, value: str) -> str:
        if not _PHASE_PATTERN.fullmatch(value):
            raise ValueError("attempt_phase must be a stable uppercase identifier")
        if value in {item.value for item in TaskState}:
            raise ValueError("attempt_phase cannot reuse Task State values")
        return value

    @field_validator("worker_id")
    @classmethod
    def validate_worker_id(cls, value: str) -> str:
        return _nonblank(value, "worker_id") or value

    @field_validator("worker_capabilities")
    @classmethod
    def validate_capabilities(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not _IDENTIFIER_PATTERN.fullmatch(item) for item in value):
            raise ValueError("worker_capabilities must contain normalized identifiers")
        if len(value) != len(set(value)):
            raise ValueError("worker_capabilities cannot contain duplicates")
        return value

    @field_validator("failure_code")
    @classmethod
    def validate_failure_code(cls, value: str | None) -> str | None:
        return _reason_code(value, "failure_code")

    @model_validator(mode="after")
    def validate_attempt_semantics(self) -> "TaskAttemptRecord":
        if self.lease_expires_at <= self.leased_at:
            raise ValueError("lease_expires_at must follow leased_at")
        if self.heartbeat_at < self.leased_at or self.heartbeat_at > self.lease_expires_at:
            raise ValueError("heartbeat_at must fall inside the lease interval")
        if self.started_at is not None and self.started_at < self.leased_at:
            raise ValueError("started_at must not precede leased_at")
        if self.attempt_outcome is None:
            if self.finished_at is not None or self.failure_code is not None or self.retryable is not None:
                raise ValueError("active attempt cannot contain terminal outcome fields")
        else:
            if self.finished_at is None:
                raise ValueError("finished attempt requires finished_at")
            if self.attempt_outcome in {AttemptOutcome.FAILED, AttemptOutcome.LEASE_LOST}:
                if self.failure_code is None or self.retryable is None:
                    raise ValueError("failed attempt requires failure_code and retryable")
            elif self.failure_code is not None or self.retryable is not None:
                raise ValueError("non-failed attempt cannot contain failure fields")
        return self


class TaskStateEventRecord(PlatformContractModel):
    task_id: str
    event_sequence: int = Field(ge=1)
    previous_task_state: TaskState | None
    next_task_state: TaskState
    reason_code: str
    actor_ref: Annotated[str, Field(min_length=1, max_length=255)]
    event_at: AwareDatetime
    attempt_id: str | None = None

    @field_validator("task_id")
    @classmethod
    def validate_task_id(cls, value: str) -> str:
        return _resource_id(value, ResourceType.TASK, "task_id") or value

    @field_validator("attempt_id")
    @classmethod
    def validate_attempt_id(cls, value: str | None) -> str | None:
        return _resource_id(value, ResourceType.ATTEMPT, "attempt_id")

    @field_validator("reason_code")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        return _reason_code(value, "reason_code") or value

    @field_validator("actor_ref")
    @classmethod
    def validate_actor(cls, value: str) -> str:
        return _nonblank(value, "actor_ref") or value


class TaskCheckpointRecord(PlatformContractModel):
    checkpoint_id: str
    task_id: str
    attempt_id: str
    phase: str
    sequence: int = Field(ge=1)
    resume_token_hash: Annotated[str, Field(pattern=_HASH_PATTERN)]
    input_hash: Annotated[str, Field(pattern=_HASH_PATTERN)]
    handler_version: Annotated[str, Field(min_length=1, max_length=255)]
    storage_ref: StorageRef
    checkpoint_hash: Annotated[str, Field(pattern=_HASH_PATTERN)]
    created_at: AwareDatetime
    expires_at: AwareDatetime

    @field_validator("checkpoint_id")
    @classmethod
    def validate_checkpoint_id(cls, value: str) -> str:
        return _resource_id(value, ResourceType.CHECKPOINT, "checkpoint_id") or value

    @field_validator("task_id")
    @classmethod
    def validate_task_id(cls, value: str) -> str:
        return _resource_id(value, ResourceType.TASK, "task_id") or value

    @field_validator("attempt_id")
    @classmethod
    def validate_attempt_id(cls, value: str) -> str:
        return _resource_id(value, ResourceType.ATTEMPT, "attempt_id") or value

    @field_validator("phase")
    @classmethod
    def validate_phase(cls, value: str) -> str:
        if not _PHASE_PATTERN.fullmatch(value):
            raise ValueError("phase must be a stable uppercase identifier")
        if value in {item.value for item in TaskState}:
            raise ValueError("checkpoint phase cannot reuse Task State values")
        return value

    @field_validator("handler_version")
    @classmethod
    def validate_handler_version(cls, value: str) -> str:
        return _nonblank(value, "handler_version") or value

    @model_validator(mode="after")
    def validate_checkpoint_semantics(self) -> "TaskCheckpointRecord":
        if self.checkpoint_hash != self.storage_ref.content_hash:
            raise ValueError("checkpoint_hash must match storage_ref content_hash")
        if self.expires_at <= self.created_at:
            raise ValueError("expires_at must follow created_at")
        return self


class TaskCreateRequest(PlatformContractModel):
    task_type: Literal["artifact_orphan_dry_run", "raw_ingestion", "canonical_normalization"]
    task_schema_version: Annotated[str, Field(pattern=_SEMVER_PATTERN, max_length=32)] = "1.0.0"
    priority_class: PriorityClass = PriorityClass.P5_PREVIEW_AND_MAINTENANCE
    priority_value: int = Field(default=100, ge=0, le=2_147_483_647)
    requested_by: Annotated[str, Field(min_length=1, max_length=255)]
    request_source: Annotated[str, Field(min_length=1, max_length=64)] = "platform_api"
    input_refs: tuple[ResourceRef, ...] = ()
    requirements: dict[str, Any] = Field(default_factory=dict)
    max_attempts: int = Field(default=3, ge=1, le=100)
    force: bool = False
    force_reason: str | None = None
    created_from_task_id: str | None = None

    @model_validator(mode="after")
    def validate_task_requirements(self) -> "TaskCreateRequest":
        if self.task_type == "raw_ingestion":
            RawIngestionTaskRequirements.model_validate(self.requirements)
        elif self.task_type == "canonical_normalization":
            CanonicalNormalizationTaskRequirements.model_validate(self.requirements)
        return self
    @field_validator("requested_by", "request_source", "force_reason")
    @classmethod
    def validate_nonblank(cls, value: str | None, info: object) -> str | None:
        return _nonblank(value, getattr(info, "field_name", "value"))

    @field_validator("created_from_task_id")
    @classmethod
    def validate_created_from(cls, value: str | None) -> str | None:
        return _resource_id(value, ResourceType.TASK, "created_from_task_id")

    @model_validator(mode="after")
    def validate_force_semantics(self) -> "TaskCreateRequest":
        if self.force:
            if self.force_reason is None or self.created_from_task_id is None:
                raise ValueError("force requires force_reason and created_from_task_id")
        elif self.force_reason is not None or self.created_from_task_id is not None:
            raise ValueError("force lineage fields require force=true")
        return self


class TaskCancelRequest(PlatformContractModel):
    reason_code: str = "TASK_CANCEL_REQUESTED"

    @field_validator("reason_code")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        return _reason_code(value, "reason_code") or value


class TaskRetryRequest(PlatformContractModel):
    reason_code: str = "TASK_RETRY_REQUESTED"

    @field_validator("reason_code")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        return _reason_code(value, "reason_code") or value


class TaskLease(PlatformContractModel):
    task: TaskRecord
    attempt: TaskAttemptRecord
    lease_token: Annotated[str, Field(min_length=32, max_length=512)]


class TaskDetails(PlatformContractModel):
    task: TaskRecord
    attempts: tuple[TaskAttemptRecord, ...]
    state_events: tuple[TaskStateEventRecord, ...]
    checkpoints: tuple[TaskCheckpointRecord, ...] = ()
    diagnostic_artifact_refs: tuple[str, ...] = ()


class TaskListQuery(PlatformContractModel):
    """Stable, bounded task list query used by Operations."""

    tab: Literal["active", "blocked", "failed", "history"] | None = None
    task_state: TaskState | None = None
    task_type: str | None = None
    priority_class: PriorityClass | None = None
    requested_by: str | None = None
    created_from: AwareDatetime | None = None
    created_to: AwareDatetime | None = None
    resource_id: str | None = None
    cursor: str | None = None
    limit: int = Field(default=50, ge=1, le=100)

    @field_validator("task_type")
    @classmethod
    def validate_query_task_type(cls, value: str | None) -> str | None:
        if value is not None and not _IDENTIFIER_PATTERN.fullmatch(value):
            raise ValueError("task_type must be a normalized identifier")
        return value

    @field_validator("requested_by")
    @classmethod
    def validate_query_requested_by(cls, value: str | None) -> str | None:
        return _nonblank(value, "requested_by")

    @model_validator(mode="after")
    def validate_query_range(self) -> "TaskListQuery":
        if self.created_from is not None and self.created_to is not None and self.created_from > self.created_to:
            raise ValueError("created_from must not follow created_to")
        if self.tab == "active" and self.task_state is None:
            object.__setattr__(self, "task_state", None)
        return self


class TaskEventRecord(PlatformContractModel):
    """C-010 event projection for resumable task notifications."""

    event_id: str
    event_type: Literal["task_state_changed"]
    resource_ref: ResourceRef
    task_id: str
    attempt_id: str | None = None
    sequence: int = Field(ge=1)
    occurred_at: AwareDatetime
    payload_schema_version: Annotated[str, Field(pattern=_SEMVER_PATTERN, max_length=32)] = "1.0.0"
    payload: TaskStateEventRecord

    @field_validator("task_id")
    @classmethod
    def validate_event_task_id(cls, value: str) -> str:
        return _resource_id(value, ResourceType.TASK, "task_id") or value

    @field_validator("attempt_id")
    @classmethod
    def validate_event_attempt_id(cls, value: str | None) -> str | None:
        return _resource_id(value, ResourceType.ATTEMPT, "attempt_id")
