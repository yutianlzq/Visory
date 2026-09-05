from __future__ import annotations

import re
from datetime import date
from typing import Annotated, Any

from pydantic import AwareDatetime, Field, field_validator, model_validator

from .base import PlatformContractModel
from .canonical import CanonicalPartition
from .enums import (
    ConsumerKind,
    ConsumerRequirementStatus,
    QualityStatus,
    ResourceType,
    RevisionKind,
    SnapshotCapabilityStatus,
    SnapshotPublicationStatus,
)
from .hashing import compute_content_hash
from .resources import parse_resource_id
from .storage import StorageRef

_HASH = r"^sha256:[0-9a-f]{64}$"
_SEMVER = r"^[0-9]+\.[0-9]+\.[0-9]+$"
_IDENT = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
_REASON = re.compile(r"^[A-Z][A-Z0-9_]{2,63}$")


def _resource(value: str | None, expected: ResourceType, name: str) -> str | None:
    if value is None:
        return None
    kind, _ = parse_resource_id(value)
    if kind is not expected:
        raise ValueError(f"{name} must use the {expected.value} resource prefix")
    return value


def _identifier(value: str, name: str) -> str:
    if not _IDENT.fullmatch(value):
        raise ValueError(f"{name} must be a normalized lowercase identifier")
    return value


class SnapshotPartitionRef(PlatformContractModel):
    canonical_partition_id: str
    dataset_id: str
    dataset_schema_version: Annotated[str, Field(pattern=_SEMVER)]
    provider_policy_version: Annotated[str, Field(pattern=_SEMVER)]
    partition_key: str
    revision: int = Field(ge=1)
    revision_kind: RevisionKind = RevisionKind.INITIAL
    storage_ref: StorageRef
    partition_hash: Annotated[str, Field(pattern=_HASH)]
    schema_hash: Annotated[str, Field(pattern=_HASH)]
    quality_report_id: str
    quality_status: QualityStatus
    provider_run_refs: tuple[str, ...]
    raw_object_refs: tuple[str, ...]
    min_available_at: AwareDatetime
    max_available_at: AwareDatetime | None = None
    row_count: int = Field(ge=0)

    @field_validator("canonical_partition_id")
    @classmethod
    def validate_partition_id(cls, value: str) -> str:
        return _resource(value, ResourceType.CANONICAL_PARTITION, "canonical_partition_id") or value

    @field_validator("quality_report_id")
    @classmethod
    def validate_quality_report_id(cls, value: str) -> str:
        return _resource(value, ResourceType.QUALITY_REPORT, "quality_report_id") or value

    @field_validator("dataset_id")
    @classmethod
    def validate_dataset_id(cls, value: str) -> str:
        return _identifier(value, "dataset_id")

    @field_validator("provider_run_refs")
    @classmethod
    def validate_provider_runs(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value:
            raise ValueError("provider_run_refs cannot be empty")
        for item in value:
            _resource(item, ResourceType.PROVIDER_RUN, "provider_run_refs")
        return value

    @field_validator("raw_object_refs")
    @classmethod
    def validate_raw_objects(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value:
            raise ValueError("raw_object_refs cannot be empty")
        for item in value:
            _resource(item, ResourceType.RAW_OBJECT, "raw_object_refs")
        return value

    @model_validator(mode="after")
    def validate_partition(self) -> "SnapshotPartitionRef":
        if self.partition_hash != self.storage_ref.content_hash:
            raise ValueError("partition_hash must match storage_ref.content_hash")
        if self.storage_ref.size_bytes < 0:
            raise ValueError("partition size must be non-negative")
        if self.max_available_at is not None and self.max_available_at < self.min_available_at:
            raise ValueError("max_available_at must not precede min_available_at")
        if self.revision_kind is RevisionKind.CORRECTION and self.revision < 2:
            raise ValueError("corrected partition revision must be at least two")
        return self

    @classmethod
    def from_partition(cls, partition: CanonicalPartition) -> "SnapshotPartitionRef":
        return cls(
            canonical_partition_id=partition.canonical_partition_id,
            dataset_id=partition.dataset_id,
            dataset_schema_version=partition.dataset_schema_version,
            provider_policy_version=partition.provider_policy_version,
            partition_key=partition.partition_key,
            revision=partition.revision,
            revision_kind=partition.revision_kind,
            storage_ref=partition.storage_ref,
            partition_hash=partition.partition_hash,
            schema_hash=partition.schema_hash,
            quality_report_id=partition.quality_report_id,
            quality_status=partition.quality_status,
            provider_run_refs=partition.provider_run_refs,
            raw_object_refs=partition.raw_object_refs,
            min_available_at=partition.min_available_at,
            max_available_at=partition.max_available_at,
            row_count=partition.row_count,
        )


class CapabilityCertification(PlatformContractModel):
    capability_id: str
    capability_status: SnapshotCapabilityStatus
    reason_code: str | None = None
    evidence_refs: tuple[str, ...] = ()
    certified_at: AwareDatetime | None = None
    snapshot_id: str | None = None

    @field_validator("capability_id")
    @classmethod
    def validate_capability_id(cls, value: str) -> str:
        return _identifier(value, "capability_id")

    @field_validator("reason_code")
    @classmethod
    def validate_reason(cls, value: str | None) -> str | None:
        if value is not None and not _REASON.fullmatch(value):
            raise ValueError("reason_code must be a stable uppercase identifier")
        return value

    @field_validator("snapshot_id")
    @classmethod
    def validate_snapshot_id(cls, value: str | None) -> str | None:
        return _resource(value, ResourceType.DATA_SNAPSHOT, "snapshot_id")

    @model_validator(mode="after")
    def validate_capability(self) -> "CapabilityCertification":
        if self.capability_status is SnapshotCapabilityStatus.CERTIFIED:
            if self.certified_at is None or self.reason_code is not None:
                raise ValueError("certified capability requires certified_at and no failure reason")
        elif self.reason_code is None:
            raise ValueError("non-certified capability requires reason_code")
        return self


class ConsumerRequirement(PlatformContractModel):
    consumer_id: str
    consumer_kind: ConsumerKind
    required_capabilities: tuple[str, ...]
    accepted_publication_statuses: tuple[SnapshotPublicationStatus, ...]
    min_quality_status: QualityStatus = QualityStatus.COMPLETE
    allow_provisional: bool = False
    requirement_version: Annotated[str, Field(pattern=_SEMVER)] = "1.0.0"

    @field_validator("consumer_id")
    @classmethod
    def validate_consumer_id(cls, value: str) -> str:
        return _identifier(value, "consumer_id")

    @field_validator("required_capabilities")
    @classmethod
    def validate_capabilities(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value or len(value) != len(set(value)):
            raise ValueError("required_capabilities must be non-empty and unique")
        return tuple(_identifier(item, "required_capabilities") for item in value)

    @field_validator("accepted_publication_statuses")
    @classmethod
    def validate_publication_statuses(cls, value: tuple[SnapshotPublicationStatus, ...]) -> tuple[SnapshotPublicationStatus, ...]:
        if not value or len(value) != len(set(value)):
            raise ValueError("accepted_publication_statuses must be non-empty and unique")
        return value

    @model_validator(mode="after")
    def validate_requirement(self) -> "ConsumerRequirement":
        statuses = set(self.accepted_publication_statuses)
        if self.consumer_kind is ConsumerKind.PREVIEW:
            if SnapshotPublicationStatus.PROVISIONAL in statuses and not self.allow_provisional:
                raise ValueError("preview consumers must explicitly allow provisional snapshots")
            if self.allow_provisional and SnapshotPublicationStatus.PROVISIONAL not in statuses:
                raise ValueError("preview consumers accepting provisional snapshots must list PROVISIONAL")
        else:
            if self.allow_provisional or statuses != {SnapshotPublicationStatus.CERTIFIED}:
                raise ValueError("formal backtest consumers only accept CERTIFIED snapshots")
            if "backtest_core" not in self.required_capabilities:
                raise ValueError("formal backtest requires backtest_core")
        return self


class DataSnapshot(PlatformContractModel):
    snapshot_id: str
    trade_date: date
    cutoff_at: AwareDatetime
    provider_policy_id: str
    provider_policy_version: Annotated[str, Field(pattern=_SEMVER)]
    security_master_ref: str
    calendar_ref: str
    canonical_partitions: tuple[SnapshotPartitionRef, ...]
    quality_report_refs: tuple[str, ...]
    quality_status: QualityStatus
    publication_status: SnapshotPublicationStatus
    certified_capabilities: tuple[str, ...] = ()
    missing_capabilities: tuple[str, ...] = ()
    revision: int = Field(ge=1)
    revision_kind: RevisionKind = RevisionKind.INITIAL
    supersedes_id: str | None = None
    available_at: AwareDatetime
    created_at: AwareDatetime
    published_at: AwareDatetime | None = None
    manifest_hash: Annotated[str, Field(pattern=_HASH)]
    content_hash: Annotated[str, Field(pattern=_HASH)]
    manifest_version: Annotated[str, Field(pattern=_SEMVER)] = "1.0.0"

    @field_validator("snapshot_id")
    @classmethod
    def validate_snapshot_id(cls, value: str) -> str:
        return _resource(value, ResourceType.DATA_SNAPSHOT, "snapshot_id") or value

    @field_validator("provider_policy_id")
    @classmethod
    def validate_provider_policy_id(cls, value: str) -> str:
        return _identifier(value, "provider_policy_id")

    @field_validator("security_master_ref", "calendar_ref")
    @classmethod
    def validate_partition_refs(cls, value: str, info: Any) -> str:
        return _resource(value, ResourceType.CANONICAL_PARTITION, info.field_name) or value

    @field_validator("canonical_partitions")
    @classmethod
    def validate_partitions(cls, value: tuple[SnapshotPartitionRef, ...]) -> tuple[SnapshotPartitionRef, ...]:
        if not value or len({item.canonical_partition_id for item in value}) != len(value):
            raise ValueError("canonical_partitions must be non-empty and unique")
        return value

    @field_validator("quality_report_refs")
    @classmethod
    def validate_quality_refs(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value or len(value) != len(set(value)):
            raise ValueError("quality_report_refs must be non-empty and unique")
        for item in value:
            _resource(item, ResourceType.QUALITY_REPORT, "quality_report_refs")
        return value

    @field_validator("certified_capabilities", "missing_capabilities")
    @classmethod
    def validate_capability_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("capability ids must be unique")
        return tuple(_identifier(item, "capability") for item in value)

    @model_validator(mode="after")
    def validate_snapshot(self) -> "DataSnapshot":
        if self.available_at > self.cutoff_at:
            raise ValueError("available_at must not exceed cutoff_at")
        if self.published_at is not None and self.published_at < self.created_at:
            raise ValueError("published_at must not precede created_at")
        if self.revision_kind is RevisionKind.CORRECTION:
            if self.supersedes_id is None:
                raise ValueError("CORRECTION requires supersedes_id")
        elif self.supersedes_id is not None:
            raise ValueError("only CORRECTION snapshots may supersede another snapshot")
        if set(self.certified_capabilities) & set(self.missing_capabilities):
            raise ValueError("certified and missing capabilities must be disjoint")
        if self.publication_status is SnapshotPublicationStatus.CERTIFIED and self.published_at is None:
            raise ValueError("CERTIFIED snapshot requires published_at")
        if self.publication_status is SnapshotPublicationStatus.REJECTED and self.published_at is not None:
            raise ValueError("REJECTED snapshot cannot be published")
        expected_manifest = compute_snapshot_manifest_hash(self)
        if expected_manifest != self.manifest_hash:
            raise ValueError("manifest_hash does not match snapshot manifest")
        return self

    @classmethod
    def build_manifest_hash(cls, value: "DataSnapshot | dict[str, Any]") -> str:
        return compute_snapshot_manifest_hash(value)


class SnapshotCurrentPointer(PlatformContractModel):
    scope: str
    trade_date: date
    capability_id: str
    snapshot_id: str
    previous_snapshot_id: str | None = None
    pointer_revision: int = Field(ge=1)
    updated_at: AwareDatetime

    @field_validator("scope", "capability_id")
    @classmethod
    def validate_ids(cls, value: str, info: Any) -> str:
        return _identifier(value, info.field_name)

    @field_validator("snapshot_id", "previous_snapshot_id")
    @classmethod
    def validate_snapshot_refs(cls, value: str | None, info: Any) -> str | None:
        return _resource(value, ResourceType.DATA_SNAPSHOT, info.field_name)

    @model_validator(mode="after")
    def validate_pointer(self) -> "SnapshotCurrentPointer":
        if self.previous_snapshot_id == self.snapshot_id:
            raise ValueError("previous_snapshot_id must differ from snapshot_id")
        return self


class SnapshotBuildTaskRequirements(PlatformContractModel):
    trade_date: date
    cutoff_at: AwareDatetime
    provider_policy_id: str
    provider_policy_version: Annotated[str, Field(pattern=_SEMVER)]
    security_master_ref: str
    calendar_ref: str
    canonical_partition_ids: tuple[str, ...]
    requested_capabilities: tuple[str, ...]
    publication_status: SnapshotPublicationStatus = SnapshotPublicationStatus.PROVISIONAL
    correction_of_snapshot_id: str | None = None

    @field_validator("provider_policy_id")
    @classmethod
    def validate_provider_policy_id(cls, value: str) -> str:
        return _identifier(value, "provider_policy_id")

    @field_validator("security_master_ref", "calendar_ref", "correction_of_snapshot_id")
    @classmethod
    def validate_refs(cls, value: str | None, info: Any) -> str | None:
        expected = ResourceType.DATA_SNAPSHOT if info.field_name == "correction_of_snapshot_id" else ResourceType.CANONICAL_PARTITION
        return _resource(value, expected, info.field_name)

    @field_validator("canonical_partition_ids")
    @classmethod
    def validate_partition_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value or len(value) != len(set(value)):
            raise ValueError("canonical_partition_ids must be non-empty and unique")
        return tuple(_resource(item, ResourceType.CANONICAL_PARTITION, "canonical_partition_ids") or item for item in value)

    @field_validator("requested_capabilities")
    @classmethod
    def validate_requested_capabilities(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value:
            raise ValueError("requested_capabilities cannot be empty")
        return tuple(_identifier(item, "requested_capabilities") for item in value)


class SnapshotBuildTaskResult(PlatformContractModel):
    task_id: str
    attempt_id: str
    snapshot: DataSnapshot | None = None
    capability_certifications: tuple[CapabilityCertification, ...]
    published: bool
    failure_code: str | None = None
    requirement_status: ConsumerRequirementStatus = ConsumerRequirementStatus.ACCEPTED

    @field_validator("task_id")
    @classmethod
    def validate_task_id(cls, value: str) -> str:
        return _resource(value, ResourceType.TASK, "task_id") or value

    @field_validator("attempt_id")
    @classmethod
    def validate_attempt_id(cls, value: str) -> str:
        return _resource(value, ResourceType.ATTEMPT, "attempt_id") or value

    @field_validator("failure_code")
    @classmethod
    def validate_failure_code(cls, value: str | None) -> str | None:
        if value is not None and not _REASON.fullmatch(value):
            raise ValueError("failure_code must be a stable uppercase identifier")
        return value

    @model_validator(mode="after")
    def validate_result(self) -> "SnapshotBuildTaskResult":
        if self.published != (self.snapshot is not None):
            raise ValueError("published must match snapshot presence")
        if not self.published and self.failure_code is None:
            raise ValueError("unpublished snapshot build requires failure_code")
        return self


def _manifest_payload(value: DataSnapshot | dict[str, Any]) -> dict[str, Any]:
    source = value.model_dump(mode="python") if isinstance(value, DataSnapshot) else dict(value)
    source.pop("manifest_hash", None)
    source.pop("content_hash", None)
    return source


def compute_snapshot_manifest_hash(value: DataSnapshot | dict[str, Any]) -> str:
    return compute_content_hash(_manifest_payload(value))


__all__ = [
    "CapabilityCertification",
    "ConsumerRequirement",
    "DataSnapshot",
    "SnapshotBuildTaskRequirements",
    "SnapshotBuildTaskResult",
    "SnapshotCurrentPointer",
    "SnapshotPartitionRef",
    "compute_snapshot_manifest_hash",
]
