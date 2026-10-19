from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Annotated, Any, Literal

from pydantic import Field, field_validator, model_validator

from .base import PlatformContractModel
from .enums import PriorityClass, ResourceType, TaskState
from .resources import parse_resource_id
from .storage import StorageRef


class BackfillPublicationEvidence(PlatformContractModel):
    """Fixed publication evidence; a published fixture never proves historical coverage."""

    date_from: date
    date_to: date
    dataset_id: str
    dataset_schema_version: Annotated[str, Field(pattern=r"^\d+\.\d+\.\d+$")]
    provider_policy_version: Annotated[str, Field(pattern=r"^\d+\.\d+\.\d+$")]
    provider_run_id: str
    raw_object_id: str
    canonical_partition_id: str
    quality_report_id: str
    snapshot_id: str
    provider_run_hash: Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
    quality_report_hash: Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
    raw_storage_ref: StorageRef
    canonical_storage_ref: StorageRef
    raw_manifest_hash: Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
    canonical_manifest_hash: Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
    snapshot_manifest_hash: Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
    snapshot_file_hash: Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
    mapping_version: str
    mapping_hash: Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
    row_count: int = Field(gt=0)
    coverage_state: Literal["PUBLISHED_UNCERTIFIED"] = "PUBLISHED_UNCERTIFIED"
    failed_provider_run_hashes: dict[str, Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_bindings(self):
        for field, expected in (
            ("provider_run_id", ResourceType.PROVIDER_RUN),
            ("raw_object_id", ResourceType.RAW_OBJECT),
            ("canonical_partition_id", ResourceType.CANONICAL_PARTITION),
            ("quality_report_id", ResourceType.QUALITY_REPORT),
            ("snapshot_id", ResourceType.DATA_SNAPSHOT),
        ):
            if parse_resource_id(getattr(self, field))[0] is not expected:
                raise ValueError(f"{field} has the wrong resource type")
        if self.date_to < self.date_from:
            raise ValueError("publication date range is invalid")
        for ref in self.failed_provider_run_hashes:
            if parse_resource_id(ref)[0] is not ResourceType.PROVIDER_RUN:
                raise ValueError("failed provider evidence must reference ProviderRun")
        return self


class BackfillQuarantineEvidence(PlatformContractModel):
    provider_run_id: str
    raw_ingestion_quarantine_id: str
    provider_run_hash: Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
    evidence_storage_ref: StorageRef
    manifest_file_hash: Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
    reason_code: Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9_]{2,79}$")]
    failed_provider_run_hashes: dict[str, Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_refs(self):
        if parse_resource_id(self.provider_run_id)[0] is not ResourceType.PROVIDER_RUN:
            raise ValueError("quarantine must reference ProviderRun")
        if parse_resource_id(self.raw_ingestion_quarantine_id)[0] is not ResourceType.RAW_INGESTION_QUARANTINE:
            raise ValueError("quarantine must reference a Raw ingestion quarantine")
        for ref in self.failed_provider_run_hashes:
            if ref == self.provider_run_id or parse_resource_id(ref)[0] is not ResourceType.PROVIDER_RUN:
                raise ValueError("failed primary evidence must reference a different ProviderRun")
        return self


class BackfillRejectionEvidence(PlatformContractModel):
    """Fixed inputs and diagnosis for a child that refused business publication."""

    date_from: date
    date_to: date
    dataset_id: str
    batch_id: str
    parent_task_id: str
    phase: Literal["CANONICAL", "SNAPSHOT"]
    child_task_id: str
    child_attempt_id: str
    child_input_hash: Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
    canonical_task_id: str
    failure_code: Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9_]{2,79}$")]
    provider_run_id: str
    provider_run_hash: Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
    raw_object_id: str
    raw_storage_ref: StorageRef
    raw_manifest_hash: Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
    quality_report_id: str
    quality_report_hash: Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
    canonical_partition_id: str | None = None
    canonical_storage_ref: StorageRef | None = None
    canonical_manifest_hash: Annotated[str | None, Field(pattern=r"^sha256:[0-9a-f]{64}$")] = None
    failed_provider_run_hashes: dict[str, Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_bindings(self):
        for field, kind in (
            ("child_task_id", ResourceType.TASK), ("canonical_task_id", ResourceType.TASK),
            ("batch_id", ResourceType.BACKFILL_BATCH), ("parent_task_id", ResourceType.TASK),
            ("child_attempt_id", ResourceType.ATTEMPT), ("provider_run_id", ResourceType.PROVIDER_RUN),
            ("raw_object_id", ResourceType.RAW_OBJECT), ("quality_report_id", ResourceType.QUALITY_REPORT),
        ):
            if parse_resource_id(getattr(self, field))[0] is not kind:
                raise ValueError(f"{field} has the wrong resource type")
        if self.date_to < self.date_from:
            raise ValueError("rejection date range is invalid")
        for ref in self.failed_provider_run_hashes:
            if ref == self.provider_run_id or parse_resource_id(ref)[0] is not ResourceType.PROVIDER_RUN:
                raise ValueError("failed primary evidence must reference a different ProviderRun")
        canonical_values = (self.canonical_partition_id, self.canonical_storage_ref, self.canonical_manifest_hash)
        if self.phase == "CANONICAL":
            if self.child_task_id != self.canonical_task_id or any(value is not None for value in canonical_values):
                raise ValueError("Canonical rejection cannot claim a published partition")
        elif any(value is None for value in canonical_values):
            raise ValueError("Snapshot rejection requires fixed Canonical inputs")
        elif parse_resource_id(self.canonical_partition_id)[0] is not ResourceType.CANONICAL_PARTITION:
            raise ValueError("canonical_partition_id has the wrong resource type")
        return self


class BackfillBatchType(str, Enum):
    MONTH = "MONTH"
    YEAR = "YEAR"


class BackfillStage(str, Enum):
    IDENTITY_CALENDAR = "IDENTITY_CALENDAR"
    PRICE_MONTH = "PRICE_MONTH"
    LIFECYCLE_NAMES = "LIFECYCLE_NAMES"
    CORPORATE_ACTION = "CORPORATE_ACTION"
    FINANCIAL_VALUATION = "FINANCIAL_VALUATION"
    INDUSTRY_MEMBERS = "INDUSTRY_MEMBERS"
    NON_CORE_OBSERVATION = "NON_CORE_OBSERVATION"


class BackfillStatus(str, Enum):
    PLANNED = "PLANNED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"
    UNAVAILABLE = "UNAVAILABLE"
    QUARANTINED = "QUARANTINED"


def _validate_resource_refs(values: tuple[str, ...], expected: ResourceType, field_name: str) -> tuple[str, ...]:
    for value in values:
        resource_type, _ = parse_resource_id(value)
        if resource_type is not expected:
            raise ValueError(f"{field_name} must reference {expected.value} resources")
    return values


class _BackfillDateScopeModel(PlatformContractModel):
    """Shared date scope accepting an explicit single-day trade_date shorthand."""

    trade_date: date | None = None
    date_from: date | None = None
    date_to: date | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_trade_date_shorthand(cls, values: Any) -> Any:
        if not isinstance(values, dict):
            return values
        normalized = dict(values)
        if normalized.get("trade_date") is not None:
            if normalized.get("date_from") is None and normalized.get("date_to") is None:
                normalized["date_from"] = normalized["trade_date"]
                normalized["date_to"] = normalized["trade_date"]
        return normalized

    @model_validator(mode="after")
    def validate_date_scope(self):
        if self.date_from is None or self.date_to is None:
            raise ValueError("trade_date or both date_from and date_to are required")
        if self.trade_date is not None and (self.date_from != self.trade_date or self.date_to != self.trade_date):
            raise ValueError("trade_date must match date_from and date_to")
        return self


class BackfillBatchRequest(_BackfillDateScopeModel):
    batch_id: str
    batch_type: BackfillBatchType
    dataset: Annotated[str, Field(min_length=1, max_length=128)]
    provider_policy_id: Annotated[str, Field(min_length=1, max_length=128)]
    priority: int = Field(default=100, ge=0, le=2_147_483_647)
    stage: BackfillStage = BackfillStage.IDENTITY_CALENDAR
    dry_run: bool = False
    plan_only: bool = False
    supersedes_id: str | None = None
    dependency_task_ids: tuple[str, ...] = ()
    requested_by: Annotated[str, Field(min_length=1, max_length=255)]

    @field_validator("supersedes_id")
    @classmethod
    def validate_supersedes_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        resource_type, _ = parse_resource_id(value)
        if resource_type is not ResourceType.DATA_SNAPSHOT:
            raise ValueError("supersedes_id must reference a data_snapshot")
        return value

    @model_validator(mode="after")
    def validate_range(self) -> "BackfillBatchRequest":
        if self.date_to < self.date_from:
            raise ValueError("date_to must not precede date_from")
        if self.batch_type is BackfillBatchType.MONTH and (self.date_to.year != self.date_from.year or self.date_to.month != self.date_from.month):
            raise ValueError("MONTH batch must fit within one calendar month")
        if self.batch_type is BackfillBatchType.YEAR and self.date_to.year != self.date_from.year:
            raise ValueError("YEAR batch must fit within one calendar year")
        resource_type, _ = parse_resource_id(self.batch_id)
        if resource_type is not ResourceType.BACKFILL_BATCH:
            raise ValueError("batch_id must use backfill_batch resource prefix")
        for task_id in self.dependency_task_ids:
            task_type, _ = parse_resource_id(task_id)
            if task_type is not ResourceType.TASK:
                raise ValueError("dependency_task_ids must reference task resources")
        if len(self.dependency_task_ids) != len(set(self.dependency_task_ids)):
            raise ValueError("dependency_task_ids cannot contain duplicates")
        return self


class BackfillStageChainRequest(PlatformContractModel):
    batches: tuple[BackfillBatchRequest, ...] = Field(min_length=7, max_length=7)

    @model_validator(mode="after")
    def validate_chain(self) -> "BackfillStageChainRequest":
        if tuple(batch.stage for batch in self.batches) != tuple(BackfillStage):
            raise ValueError("batches must follow the complete backfill roadmap order")
        if len({batch.batch_id for batch in self.batches}) != len(self.batches):
            raise ValueError("stage chain batch_id values must be unique")
        if any(batch.dependency_task_ids for batch in self.batches):
            raise ValueError("stage chain dependency_task_ids are server-managed")
        first = self.batches[0]
        for batch in self.batches[1:]:
            if (
                batch.batch_type is not first.batch_type
                or batch.date_from != first.date_from
                or batch.date_to != first.date_to
            ):
                raise ValueError("stage chain batches must use the same date range and batch type")
            if batch.requested_by != first.requested_by:
                raise ValueError("stage chain batches must use the same requested_by")
            if batch.dry_run != first.dry_run or batch.plan_only != first.plan_only:
                raise ValueError("stage chain batches must use the same publication mode")
        return self


class BackfillTaskRequirements(_BackfillDateScopeModel):
    batch_id: str
    batch_type: BackfillBatchType
    dataset: Annotated[str, Field(min_length=1, max_length=128)]
    provider_policy_id: Annotated[str, Field(min_length=1, max_length=128)]
    priority: int = Field(ge=0, le=2_147_483_647)
    stage: BackfillStage
    dry_run: bool = False
    plan_only: bool = False
    dependency_task_ids: tuple[str, ...] = ()
    checkpoint_phase: str = "PLANNED"
    completed_range: tuple[date, date] | None = None
    skipped_range: tuple[date, date] | None = None
    failed_range: tuple[date, date] | None = None
    skipped_ranges: tuple[tuple[date, date], ...] = ()
    failed_ranges: tuple[tuple[date, date], ...] = ()
    differences_summary: str | None = None
    resource_usage: dict[str, float] = Field(default_factory=dict)
    quality_events: tuple[str, ...] = ()
    supersedes_id: str | None = None
    provider_run_refs: tuple[str, ...] = ()
    raw_object_refs: tuple[str, ...] = ()
    canonical_partition_refs: tuple[str, ...] = ()
    snapshot_refs: tuple[str, ...] = ()
    provider_fallback: bool = False
    publication_evidence: tuple[BackfillPublicationEvidence, ...] = ()
    quarantine_evidence: tuple[BackfillQuarantineEvidence, ...] = ()
    rejection_evidence: tuple[BackfillRejectionEvidence, ...] = ()

    @field_validator("supersedes_id")
    @classmethod
    def validate_supersedes_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        resource_type, _ = parse_resource_id(value)
        if resource_type is not ResourceType.DATA_SNAPSHOT:
            raise ValueError("supersedes_id must reference a data_snapshot")
        return value

    @field_validator("provider_run_refs")
    @classmethod
    def validate_provider_run_refs(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _validate_resource_refs(value, ResourceType.PROVIDER_RUN, "provider_run_refs")

    @field_validator("raw_object_refs")
    @classmethod
    def validate_raw_object_refs(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _validate_resource_refs(value, ResourceType.RAW_OBJECT, "raw_object_refs")

    @field_validator("canonical_partition_refs")
    @classmethod
    def validate_canonical_partition_refs(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _validate_resource_refs(value, ResourceType.CANONICAL_PARTITION, "canonical_partition_refs")

    @field_validator("snapshot_refs")
    @classmethod
    def validate_snapshot_refs(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _validate_resource_refs(value, ResourceType.DATA_SNAPSHOT, "snapshot_refs")

    @field_validator("differences_summary")
    @classmethod
    def validate_differences_summary(cls, value: str | None) -> str | None:
        if value is not None and len(value) > 2048:
            raise ValueError("differences_summary must be at most 2048 characters")
        return value

    @model_validator(mode="after")
    def validate_batch(self) -> "BackfillTaskRequirements":
        resource_type, _ = parse_resource_id(self.batch_id)
        if resource_type is not ResourceType.BACKFILL_BATCH:
            raise ValueError("batch_id must use backfill_batch resource prefix")
        if self.date_to < self.date_from:
            raise ValueError("date_to must not precede date_from")
        if self.batch_type is BackfillBatchType.MONTH and (self.date_to.year != self.date_from.year or self.date_to.month != self.date_from.month):
            raise ValueError("MONTH batch must fit within one calendar month")
        if self.batch_type is BackfillBatchType.YEAR and self.date_to.year != self.date_from.year:
            raise ValueError("YEAR batch must fit within one calendar year")
        for task_id in self.dependency_task_ids:
            task_type, _ = parse_resource_id(task_id)
            if task_type is not ResourceType.TASK:
                raise ValueError("dependency_task_ids must reference task resources")
        if len(self.dependency_task_ids) != len(set(self.dependency_task_ids)):
            raise ValueError("dependency_task_ids cannot contain duplicates")
        for field_name in ("skipped_ranges", "failed_ranges"):
            for start, end in getattr(self, field_name):
                if end < start or start < self.date_from or end > self.date_to:
                    raise ValueError(f"{field_name} must stay within the batch date range")
        return self


class BackfillBatchProjection(_BackfillDateScopeModel):
    batch_id: str
    task_id: str
    batch_state: BackfillStatus
    batch_type: BackfillBatchType
    stage: BackfillStage
    dataset: Annotated[str, Field(min_length=1, max_length=128)]
    provider_policy_id: Annotated[str, Field(min_length=1, max_length=128)]
    priority: int = Field(ge=0, le=2_147_483_647)
    dry_run: bool
    plan_only: bool
    dependency_task_ids: tuple[str, ...] = ()
    failure_code: str | None = None
    blocked_reason_code: str | None = None
    unblock_condition: str | None = None
    checkpoint_phase: str
    completed_range: tuple[date, date] | None = None
    skipped_range: tuple[date, date] | None = None
    failed_range: tuple[date, date] | None = None
    skipped_ranges: tuple[tuple[date, date], ...] = ()
    failed_ranges: tuple[tuple[date, date], ...] = ()
    differences_summary: str | None = None
    resource_usage: dict[str, float] = Field(default_factory=dict)
    quality_events: tuple[str, ...] = ()
    provider_run_refs: tuple[str, ...] = ()
    raw_object_refs: tuple[str, ...] = ()
    canonical_partition_refs: tuple[str, ...] = ()
    snapshot_refs: tuple[str, ...] = ()
    provider_fallback: bool = False
    supersedes_id: str | None = None
    publication_evidence: tuple[BackfillPublicationEvidence, ...] = ()
    quarantine_evidence: tuple[BackfillQuarantineEvidence, ...] = ()
    rejection_evidence: tuple[BackfillRejectionEvidence, ...] = ()
    coverage_state: Literal["UNPROVEN"] = "UNPROVEN"
    gap_ranges: tuple[tuple[date, date], ...] = ()
    retry_plan: tuple[str, ...] = ()

    @field_validator("provider_run_refs")
    @classmethod
    def validate_projection_provider_run_refs(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _validate_resource_refs(value, ResourceType.PROVIDER_RUN, "provider_run_refs")

    @field_validator("raw_object_refs")
    @classmethod
    def validate_projection_raw_object_refs(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _validate_resource_refs(value, ResourceType.RAW_OBJECT, "raw_object_refs")

    @field_validator("canonical_partition_refs")
    @classmethod
    def validate_projection_canonical_refs(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _validate_resource_refs(value, ResourceType.CANONICAL_PARTITION, "canonical_partition_refs")

    @field_validator("snapshot_refs")
    @classmethod
    def validate_projection_snapshot_refs(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _validate_resource_refs(value, ResourceType.DATA_SNAPSHOT, "snapshot_refs")

    @field_validator("batch_id")
    @classmethod
    def validate_batch_id(cls, value: str) -> str:
        resource_type, _ = parse_resource_id(value)
        if resource_type is not ResourceType.BACKFILL_BATCH:
            raise ValueError("batch_id must use backfill_batch resource prefix")
        return value

    @field_validator("task_id")
    @classmethod
    def validate_task_id(cls, value: str) -> str:
        resource_type, _ = parse_resource_id(value)
        if resource_type is not ResourceType.TASK:
            raise ValueError("task_id must reference a task")
        return value

    @field_validator("dependency_task_ids")
    @classmethod
    def validate_projection_dependency_task_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for task_id in value:
            resource_type, _ = parse_resource_id(task_id)
            if resource_type is not ResourceType.TASK:
                raise ValueError("dependency_task_ids must reference task resources")
        if len(value) != len(set(value)):
            raise ValueError("dependency_task_ids cannot contain duplicates")
        return value


class BackfillStageChainProjection(PlatformContractModel):
    """Ordered read projection for the created prefix or partial stage chain."""

    batches: tuple[BackfillBatchProjection, ...] = Field(min_length=1, max_length=7)

    @model_validator(mode="after")
    def validate_chain(self) -> "BackfillStageChainProjection":
        stage_indexes = [tuple(BackfillStage).index(batch.stage) for batch in self.batches]
        if stage_indexes != sorted(stage_indexes) or len(stage_indexes) != len(set(stage_indexes)):
            raise ValueError("batches must follow a unique backfill roadmap order")
        if stage_indexes != list(range(len(stage_indexes))):
            raise ValueError("batches must form a contiguous backfill roadmap prefix")
        for index, batch in enumerate(self.batches):
            if index == 0:
                continue
            previous = self.batches[index - 1]
            if stage_indexes[index] == stage_indexes[index - 1] + 1 and batch.dependency_task_ids != (previous.task_id,):
                raise ValueError("stage chain dependency_task_ids must reference the previous stage task")
        return self


class BackfillExecutionRangeProjection(_BackfillDateScopeModel):
    """Recorded execution and recovery actions, separate from historical coverage."""

    batch_id: str | None = None
    task_id: str | None = None
    task_state: TaskState | None = None
    provider_policy_id: str | None = None
    execution_state: Literal[
        "UNATTEMPTED", "PENDING", "FAILED", "SKIPPED", "UNPROVEN", "PUBLISHED_UNCERTIFIED",
    ]
    next_action: Literal[
        "CREATE_MONTH_BATCH", "WAIT_EXISTING_TASK", "RETRY_EXISTING_TASK",
        "RESOLVE_DEPENDENCY", "REVIEW_SKIPPED_RANGE", "REVIEW_FAILURE",
        "REVIEW_CANCELLED", "VERIFY_COVERAGE", "REVIEW_INCOMPLETE_PUBLICATION",
    ]
    snapshot_refs: tuple[str, ...] = ()
    blocking_codes: tuple[Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9_]{2,79}$")], ...] = ()

    @model_validator(mode="after")
    def validate_execution_range(self):
        if self.date_to < self.date_from or (self.date_from.year, self.date_from.month) != (self.date_to.year, self.date_to.month):
            raise ValueError("execution range must fit within one calendar month")
        if self.task_id is None:
            if any(value is not None for value in (self.batch_id, self.task_state, self.provider_policy_id)) or self.snapshot_refs:
                raise ValueError("unbound execution range cannot contain task evidence")
        else:
            if self.batch_id is None or self.task_state is None or not self.provider_policy_id:
                raise ValueError("execution range requires a complete task binding")
            _validate_resource_refs((self.task_id,), ResourceType.TASK, "task_id")
            _validate_resource_refs((self.batch_id,), ResourceType.BACKFILL_BATCH, "batch_id")
        _validate_resource_refs(self.snapshot_refs, ResourceType.DATA_SNAPSHOT, "snapshot_refs")
        if self.next_action == "RETRY_EXISTING_TASK" and self.task_state is not TaskState.RETRY_WAIT:
            raise ValueError("retry action requires an existing RETRY_WAIT task")
        if (self.execution_state == "PUBLISHED_UNCERTIFIED") != bool(self.snapshot_refs):
            raise ValueError("published execution range requires fixed Snapshot references")
        return self


class BackfillCoverageProjection(_BackfillDateScopeModel):
    dataset: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,127}$")]
    coverage_state: Literal["UNPROVEN"] = "UNPROVEN"
    gap_ranges: tuple[tuple[date, date], ...]
    retry_plan: tuple[str, ...]
    batches: tuple[BackfillBatchProjection, ...] = ()
    execution_ranges: tuple[BackfillExecutionRangeProjection, ...] = ()

    @model_validator(mode="after")
    def validate_coverage_range(self):
        if self.date_to < self.date_from:
            raise ValueError("coverage date range is invalid")
        for start, end in self.gap_ranges:
            if start < self.date_from or end > self.date_to or end < start:
                raise ValueError("gap ranges must stay within the coverage query")
        if any(item.date_from < self.date_from or item.date_to > self.date_to for item in self.execution_ranges):
            raise ValueError("execution ranges must stay within the coverage query")
        return self


__all__ = [
    "BackfillBatchType",
    "BackfillStage",
    "BackfillStatus",
    "BackfillBatchRequest",
    "BackfillStageChainRequest",
    "BackfillTaskRequirements",
    "BackfillBatchProjection",
    "BackfillStageChainProjection",
    "BackfillPublicationEvidence",
    "BackfillQuarantineEvidence",
    "BackfillCoverageProjection",
    "BackfillExecutionRangeProjection",
]
