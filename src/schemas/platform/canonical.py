from __future__ import annotations

import re
from typing import Annotated

from pydantic import AwareDatetime, Field, field_validator, model_validator

from .base import PlatformContractModel
from .hashing import compute_content_hash
from .enums import QualityStatus, ResourceType, RevisionKind
from .resources import parse_resource_id
from .storage import StorageRef

_HASH = r"^sha256:[0-9a-f]{64}$"
_SEMVER = r"^[0-9]+\.[0-9]+\.[0-9]+$"
_IDENT = re.compile(r"^[a-z][a-z0-9._-]{0,63}$")
_REASON = re.compile(r"^[A-Z][A-Z0-9_]{2,63}$")


def _id(value: str, field: str) -> str:
    if not _IDENT.fullmatch(value):
        raise ValueError(f"{field} must be a normalized identifier")
    return value


def _resource(value: str | None, expected: ResourceType, field: str) -> str | None:
    if value is None:
        return None
    kind, _ = parse_resource_id(value)
    if kind is not expected:
        raise ValueError(f"{field} must use the {expected.value} resource prefix")
    return value


def _mapping_payload(value: "ProviderCanonicalMappingDefinition" | dict[str, object]) -> dict[str, object]:
    source = value.model_dump(mode="python", exclude={"mapping_hash", "created_at"}) if isinstance(value, ProviderCanonicalMappingDefinition) else dict(value)
    return {
        "provider_id": source["provider_id"],
        "dataset_id": source["dataset_id"],
        "dataset_schema_version": source["dataset_schema_version"],
        "mapping_version": source["mapping_version"],
        "source_fields": {key: source["source_fields"][key] for key in sorted(source["source_fields"])},
        "source_field_types": {key: source.get("source_field_types", {})[key] for key in sorted(source.get("source_field_types", {}))},
        # Column order is schema-significant for deterministic Parquet output.
        "target_fields": tuple(source["target_fields"]),
        "target_field_types": {key: source.get("target_field_types", {})[key] for key in sorted(source.get("target_field_types", {}))},
        "target_units": {key: source.get("target_units", {})[key] for key in sorted(source.get("target_units", {}))},
        "unit_multipliers": {key: source["unit_multipliers"][key] for key in sorted(source.get("unit_multipliers", {}))},
        "enum_mappings": {key: {k: source["enum_mappings"][key][k] for k in sorted(source["enum_mappings"][key])} for key in sorted(source.get("enum_mappings", {}))},
        "null_semantics": {key: source["null_semantics"][key] for key in sorted(source.get("null_semantics", {}))},
        "time_semantics": {key: source["time_semantics"][key] for key in sorted(source.get("time_semantics", {}))},
    }


def compute_provider_canonical_mapping_hash(value: "ProviderCanonicalMappingDefinition" | dict[str, object]) -> str:
    return compute_content_hash(_mapping_payload(value))


class ProviderCanonicalMappingDefinition(PlatformContractModel):
    provider_id: str
    dataset_id: str
    dataset_schema_version: Annotated[str, Field(pattern=_SEMVER)]
    mapping_version: Annotated[str, Field(pattern=_SEMVER)]
    source_fields: dict[str, str]
    source_field_types: dict[str, str] = Field(default_factory=dict)
    target_fields: tuple[str, ...]
    target_field_types: dict[str, str] = Field(default_factory=dict)
    target_units: dict[str, str] = Field(default_factory=dict)
    unit_multipliers: dict[str, str] = Field(default_factory=dict)
    enum_mappings: dict[str, dict[str, str]] = Field(default_factory=dict)
    null_semantics: dict[str, str] = Field(default_factory=dict)
    time_semantics: dict[str, str] = Field(default_factory=dict)
    mapping_hash: Annotated[str, Field(pattern=_HASH)]
    created_at: AwareDatetime

    @field_validator("provider_id", "dataset_id")
    @classmethod
    def validate_ids(cls, value: str, info: object) -> str:
        return _id(value, getattr(info, "field_name", "identifier"))

    @field_validator("source_field_types")
    @classmethod
    def validate_source_field_types(cls, value: dict[str, str]) -> dict[str, str]:
        if any(not _IDENT.fullmatch(key) or not isinstance(item, str) or not item.strip() for key, item in value.items()):
            raise ValueError("source_field_types must contain normalized fields and non-blank types")
        return dict(value)

    @field_validator("target_field_types", "target_units")
    @classmethod
    def validate_target_metadata(cls, value: dict[str, str]) -> dict[str, str]:
        if any(not _IDENT.fullmatch(key) or not isinstance(item, str) or not item.strip() for key, item in value.items()):
            raise ValueError("target metadata must contain normalized fields and non-blank values")
        return dict(value)

    @field_validator("source_fields")
    @classmethod
    def validate_source_fields(cls, value: dict[str, str]) -> dict[str, str]:
        if not value or any(not _IDENT.fullmatch(k) or not isinstance(v, str) or not v.strip() for k, v in value.items()):
            raise ValueError("source_fields must map normalized targets to non-blank source fields")
        return dict(value)

    @field_validator("target_fields")
    @classmethod
    def validate_target_fields(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value or len(value) != len(set(value)) or any(not _IDENT.fullmatch(item) for item in value):
            raise ValueError("target_fields must contain unique normalized identifiers")
        return value

    @model_validator(mode="after")
    def validate_mapping(self) -> "ProviderCanonicalMappingDefinition":
        if set(self.source_fields) != set(self.target_fields):
            raise ValueError("source_fields and target_fields must cover the same canonical fields")
        if set(self.source_field_types) - set(self.source_fields.values()):
            raise ValueError("source_field_types references an undeclared source field")
        if set(self.target_field_types) != set(self.target_fields):
            raise ValueError("target_field_types must exactly cover target fields")
        if any(value not in {"string", "date", "number", "integer", "boolean", "timestamptz"} for value in self.target_field_types.values()):
            raise ValueError("target_field_types contains an unsupported type")
        if set(self.target_units) != set(self.target_fields):
            raise ValueError("target_units must exactly cover target fields")
        if set(self.unit_multipliers) - set(self.target_fields) or set(self.enum_mappings) - set(self.target_fields) or set(self.null_semantics) - set(self.target_fields) or set(self.time_semantics) - set(self.target_fields):
            raise ValueError("mapping metadata references an undeclared target field")
        if self.mapping_hash != compute_provider_canonical_mapping_hash(self):
            raise ValueError("mapping_hash does not match the canonical mapping definition")
        return self


class CanonicalQualityReport(PlatformContractModel):
    quality_report_id: str
    canonical_partition_id: str | None = None
    quality_status: QualityStatus
    rule_results: dict[str, str]
    row_count: int = Field(ge=0)
    rejected_row_count: int = Field(ge=0)
    duplicate_key_count: int = Field(ge=0)
    identity_unresolved_count: int = Field(ge=0)
    identity_ambiguous_count: int = Field(ge=0)
    failure_reasons: tuple[str, ...] = ()
    created_at: AwareDatetime

    @field_validator("quality_report_id")
    @classmethod
    def validate_report_id(cls, value: str) -> str:
        return _resource(value, ResourceType.QUALITY_REPORT, "quality_report_id") or value

    @field_validator("canonical_partition_id")
    @classmethod
    def validate_partition_id(cls, value: str | None) -> str | None:
        return _resource(value, ResourceType.CANONICAL_PARTITION, "canonical_partition_id")

    @field_validator("rule_results")
    @classmethod
    def validate_rules(cls, value: dict[str, str]) -> dict[str, str]:
        if any(not _IDENT.fullmatch(k) or v not in {"PASS", "FAIL", "SKIP"} for k, v in value.items()):
            raise ValueError("rule_results must contain normalized rule ids and PASS/FAIL/SKIP values")
        return dict(value)

    @field_validator("failure_reasons")
    @classmethod
    def validate_reasons(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not _REASON.fullmatch(item) for item in value):
            raise ValueError("failure_reasons must be stable uppercase codes")
        return value

    @model_validator(mode="after")
    def validate_quality(self) -> "CanonicalQualityReport":
        if self.quality_status is QualityStatus.FAILED and not self.failure_reasons:
            raise ValueError("FAILED quality report requires failure_reasons")
        if self.rejected_row_count > self.row_count:
            raise ValueError("rejected_row_count cannot exceed row_count")
        return self


class CanonicalPartition(PlatformContractModel):
    canonical_partition_id: str
    dataset_id: str
    dataset_schema_version: Annotated[str, Field(pattern=_SEMVER)]
    partition_key: str
    revision: int = Field(ge=1)
    revision_kind: RevisionKind = RevisionKind.INITIAL
    supersedes_id: str | None = None
    provider_policy_version: Annotated[str, Field(pattern=_SEMVER)]
    provider_run_refs: tuple[str, ...]
    raw_object_refs: tuple[str, ...]
    min_available_at: AwareDatetime
    max_available_at: AwareDatetime | None = None
    row_count: int = Field(ge=0)
    distinct_entity_count: int = Field(ge=0)
    storage_ref: StorageRef
    partition_hash: Annotated[str, Field(pattern=_HASH)]
    schema_hash: Annotated[str, Field(pattern=_HASH)]
    quality_status: QualityStatus
    quality_report_id: str
    created_at: AwareDatetime
    published_at: AwareDatetime | None = None

    @field_validator("canonical_partition_id")
    @classmethod
    def validate_partition_resource(cls, value: str) -> str:
        return _resource(value, ResourceType.CANONICAL_PARTITION, "canonical_partition_id") or value

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

    @field_validator("quality_report_id")
    @classmethod
    def validate_quality_report(cls, value: str) -> str:
        return _resource(value, ResourceType.QUALITY_REPORT, "quality_report_id") or value

    @field_validator("dataset_id")
    @classmethod
    def validate_dataset(cls, value: str) -> str:
        return _id(value, "dataset_id")

    @model_validator(mode="after")
    def validate_partition(self) -> "CanonicalPartition":
        if self.max_available_at is not None and self.max_available_at < self.min_available_at:
            raise ValueError("max_available_at must not precede min_available_at")
        if self.published_at is not None and self.published_at < self.created_at:
            raise ValueError("published_at must not precede created_at")
        if self.revision_kind is RevisionKind.CORRECTION and self.supersedes_id is None:
            raise ValueError("CORRECTION requires supersedes_id")
        return self

    @property
    def provider_run_id(self) -> str:
        return self.provider_run_refs[0]

    @property
    def raw_object_id(self) -> str:
        return self.raw_object_refs[0]


class CanonicalNormalizationTaskRequirements(PlatformContractModel):
    provider_id: str
    dataset_id: str
    dataset_schema_version: Annotated[str, Field(pattern=_SEMVER)]
    raw_object_id: str
    provider_run_id: str
    provider_policy_id: str
    provider_policy_version: Annotated[str, Field(pattern=_SEMVER)]
    mapping_version: Annotated[str, Field(pattern=_SEMVER)]
    partition_key: str
    market: str = "CN"
    requested_by: str = "canonical_normalizer"

    @field_validator("market")
    @classmethod
    def validate_market(cls, value: str) -> str:
        if not value or len(value) > 32 or any(character.isspace() for character in value):
            raise ValueError("market must be a bounded non-blank market code")
        return value

    @field_validator("provider_id", "dataset_id", "provider_policy_id")
    @classmethod
    def validate_identifiers(cls, value: str, info: object) -> str:
        return _id(value, getattr(info, "field_name", "identifier"))

    @field_validator("raw_object_id")
    @classmethod
    def validate_raw_id(cls, value: str) -> str:
        return _resource(value, ResourceType.RAW_OBJECT, "raw_object_id") or value

    @field_validator("provider_run_id")
    @classmethod
    def validate_run_id(cls, value: str) -> str:
        return _resource(value, ResourceType.PROVIDER_RUN, "provider_run_id") or value


class CanonicalNormalizationTaskResult(PlatformContractModel):
    task_id: str
    attempt_id: str
    canonical_partition: CanonicalPartition | None = None
    quality_report: CanonicalQualityReport
    published: bool
    failure_code: str | None = None

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
    def validate_result(self) -> "CanonicalNormalizationTaskResult":
        if self.published != (self.canonical_partition is not None):
            raise ValueError("published must match canonical_partition presence")
        if not self.published and self.failure_code is None:
            raise ValueError("failed normalization requires failure_code")
        return self


__all__ = [
    "CanonicalNormalizationTaskRequirements",
    "CanonicalNormalizationTaskResult",
    "CanonicalPartition",
    "CanonicalQualityReport",
    "ProviderCanonicalMappingDefinition",
    "compute_provider_canonical_mapping_hash",
]
