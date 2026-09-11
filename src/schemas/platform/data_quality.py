from __future__ import annotations

import re
from datetime import date, time
from typing import Any, Literal

from pydantic import AwareDatetime, Field, field_validator

from .base import PlatformContractModel
from .enums import QualityStatus, RevisionKind, SnapshotCapabilityStatus, SnapshotPublicationStatus
from .resources import parse_resource_id


DATA_QUALITY_CAPABILITIES: tuple[str, ...] = (
    "identity_core",
    "trading_calendar",
    "backtest_core",
    "market_observation",
    "sector_observation",
    "financial_research",
    "news_research",
    "global_observation",
)

_DATASET_ID = re.compile(r"^[a-z][a-z0-9._-]{0,63}$")
_REASON_CODE = re.compile(r"^[A-Z][A-Z0-9_]{2,63}$")


class DataQualityQuery(PlatformContractModel):
    """Bounded filters for the P-DATA read projection."""

    trade_date: date | None = None
    snapshot_id: str | None = None
    capability: str | None = None
    dataset: str | None = None
    provider: str | None = None
    quality_status: QualityStatus | None = None

    @field_validator("capability", "dataset", "provider")
    @classmethod
    def validate_identifier(cls, value: str | None) -> str | None:
        if value is not None and not _DATASET_ID.fullmatch(value):
            raise ValueError("filter must be a normalized identifier")
        return value

    @field_validator("snapshot_id")
    @classmethod
    def validate_snapshot_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        resource_type, _ = parse_resource_id(value)
        if resource_type.value != "data_snapshot":
            raise ValueError("snapshot_id must reference a data_snapshot")
        return value

    @property
    def status(self) -> QualityStatus | None:
        """Compatibility accessor for callers that name the external filter `status`."""

        return self.quality_status


class DataQualityActionRequest(PlatformContractModel):
    action: Literal["recheck", "rebuild", "correction"]
    snapshot_id: str | None = None
    trade_date: date
    reason_code: str = "QUALITY_RECHECK_REQUESTED"
    requested_by: str
    idempotency_key: str | None = None

    @field_validator("snapshot_id")
    @classmethod
    def validate_snapshot_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        resource_type, _ = parse_resource_id(value)
        if resource_type.value != "data_snapshot":
            raise ValueError("snapshot_id must reference a data_snapshot")
        return value

    @field_validator("reason_code")
    @classmethod
    def validate_reason_code(cls, value: str) -> str:
        if not _REASON_CODE.fullmatch(value):
            raise ValueError("reason_code must be a stable uppercase identifier")
        return value

    @field_validator("requested_by")
    @classmethod
    def validate_requested_by(cls, value: str) -> str:
        if not value.strip() or len(value) > 255:
            raise ValueError("requested_by must be bounded and non-blank")
        return value

    @field_validator("idempotency_key")
    @classmethod
    def validate_idempotency_key(cls, value: str | None) -> str | None:
        if value is not None and (not value.strip() or len(value) > 255):
            raise ValueError("idempotency_key must be bounded and non-blank")
        return value


class DataQualityEvidence(PlatformContractModel):
    resource_id: str
    resource_type: str
    dataset_id: str | None = None
    provider_id: str | None = None
    quality_status: QualityStatus | None = None
    revision: int | None = Field(default=None, ge=1)
    revision_kind: RevisionKind | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class DataQualityCapability(PlatformContractModel):
    capability_id: str
    capability_status: SnapshotCapabilityStatus
    reason_code: str | None = None
    evidence_refs: tuple[str, ...] = ()
    dataset_ids: tuple[str, ...] = ()
    provider_ids: tuple[str, ...] = ()


class DataQualityDataset(PlatformContractModel):
    dataset_id: str
    dataset_schema_version: str
    provider_ids: tuple[str, ...] = ()
    partition_key: str
    trade_date_from: date | None = None
    trade_date_to: date | None = None
    coverage_ratio: float = Field(ge=0.0, le=1.0)
    freshness_at: AwareDatetime | None = None
    row_count: int = Field(ge=0)
    conflict_count: int = Field(ge=0)
    quality_status: QualityStatus
    revision: int = Field(ge=1)
    revision_kind: RevisionKind
    snapshot_ids: tuple[str, ...] = ()
    provider_runs: tuple[DataQualityEvidence, ...] = ()
    raw_objects: tuple[DataQualityEvidence, ...] = ()
    canonical_partitions: tuple[DataQualityEvidence, ...] = ()
    quality_reports: tuple[DataQualityEvidence, ...] = ()
    quarantines: tuple[DataQualityEvidence, ...] = ()
    correction_snapshot_id: str | None = None


class DataQualityTimelineStage(PlatformContractModel):
    stage_id: str
    local_time: time
    stage_status: str
    reason_code: str | None = None
    task_ids: tuple[str, ...] = ()


class DataQualityProjection(PlatformContractModel):
    trade_date: date
    data_as_of: AwareDatetime
    snapshot_id: str
    publication_status: SnapshotPublicationStatus
    quality_status: QualityStatus
    cutoff_at: AwareDatetime
    revision: int = Field(ge=1)
    revision_kind: RevisionKind
    supersedes_id: str | None = None
    current_pointers: tuple[dict[str, Any], ...] = ()
    capabilities: tuple[DataQualityCapability, ...] = ()
    missing_capabilities: tuple[str, ...] = ()
    datasets: tuple[DataQualityDataset, ...] = ()
    timeline: tuple[DataQualityTimelineStage, ...] = ()
    task_ids: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


class DataQualityQueryResult(DataQualityProjection):
    """Named response contract for the data-quality projection endpoint."""


class DataQualityActionResult(PlatformContractModel):
    task_id: str
    action: Literal["recheck", "rebuild", "correction"]
    snapshot_id: str | None = None
    correction_of_snapshot_id: str | None = None
    task_type: Literal["data_snapshot_build"] = "data_snapshot_build"
    message: str = "受控任务已创建，未直接修改 Canonical 数据。"


class DataQualityDiff(PlatformContractModel):
    base_snapshot_id: str
    target_snapshot_id: str
    added_partitions: tuple[dict[str, Any], ...] = ()
    removed_partitions: tuple[dict[str, Any], ...] = ()
    revised_partitions: tuple[dict[str, Any], ...] = ()
    quality_changes: tuple[dict[str, Any], ...] = ()
    capability_changes: tuple[dict[str, Any], ...] = ()
    provider_switches: tuple[dict[str, Any], ...] = ()
    affected_consumers: tuple[dict[str, Any], ...] = ()
    affected_tasks: tuple[str, ...] = ()


__all__ = [
    "DATA_QUALITY_CAPABILITIES",
    "DataQualityActionRequest",
    "DataQualityActionResult",
    "DataQualityCapability",
    "DataQualityDataset",
    "DataQualityDiff",
    "DataQualityEvidence",
    "DataQualityProjection",
    "DataQualityQuery",
    "DataQualityQueryResult",
    "DataQualityTimelineStage",
]
