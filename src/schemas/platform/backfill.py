from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Annotated, Any

from pydantic import Field, field_validator, model_validator

from .base import PlatformContractModel
from .enums import PriorityClass, ResourceType
from .resources import parse_resource_id


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


__all__ = [
    "BackfillBatchType",
    "BackfillStage",
    "BackfillStatus",
    "BackfillBatchRequest",
    "BackfillStageChainRequest",
    "BackfillTaskRequirements",
    "BackfillBatchProjection",
    "BackfillStageChainProjection",
]
