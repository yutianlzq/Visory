from __future__ import annotations

import re
from typing import Annotated, Any
from urllib.parse import urlsplit, urlunsplit

from pydantic import AwareDatetime, Field, field_validator, model_validator

from .base import PlatformContractModel
from .enums import (
    ProviderRunOutcome,
    QuarantineStatus,
    RawCompression,
    RawSchemaDriftClassification,
    ResourceType,
    RetentionClass,
)
from .resources import parse_resource_id
from .storage import StorageRef


_HASH_PATTERN = r"^sha256:[0-9a-f]{64}$"
_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
_SEMVER = r"^[0-9]+\.[0-9]+\.[0-9]+$"
_REASON_CODE = re.compile(r"^[A-Z][A-Z0-9_]{2,63}$")
_SENSITIVE_KEY = re.compile(r"(?:api[_-]?key|authorization|cookie|password|secret|token)", re.IGNORECASE)
_SENSITIVE_VALUE = re.compile(r"(?:api[_-]?key|authorization|cookie|password|secret|token)\s*[:=]", re.IGNORECASE)
_SENSITIVE_VALUE = re.compile(r"(?:api[_-]?key|authorization|cookie|password|secret|token)\s*[:=]", re.IGNORECASE)


def _identifier(value: str, field_name: str) -> str:
    if not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"{field_name} must be a normalized lowercase identifier")
    return value


def _resource_id(value: str, expected: ResourceType, field_name: str) -> str:
    resource_type, _ = parse_resource_id(value)
    if resource_type is not expected:
        raise ValueError(f"{field_name} must use the {expected.value} resource prefix")
    return value


def _redacted_text(value: str | None) -> str | None:
    if value is None:
        return None
    if not value.strip() or len(value) > 512:
        raise ValueError("failure_detail_redacted must be a bounded non-blank diagnostic")
    if _SENSITIVE_KEY.search(value):
        raise ValueError("failure_detail_redacted cannot contain secret-bearing labels")
    if "@" in value or "?" in value:
        raise ValueError("failure_detail_redacted cannot contain credential or query syntax")
    return value


def _safe_actual_upstream(value: str) -> str:
    if not value or len(value) > 255 or _SENSITIVE_KEY.search(value):
        raise ValueError("actual_upstream must be a bounded redacted origin")
    parsed = urlsplit(value)
    if parsed.scheme:
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("actual_upstream cannot contain credentials, query, or fragment")
        if not parsed.hostname:
            raise ValueError("actual_upstream must identify a host when a URI is used")
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
    if any(marker in value for marker in ("/", "\\", "@", "?", "#", ":")):
        raise ValueError("actual_upstream must be a redacted origin or URI")
    return value


def ensure_safe_actual_upstream(value: str) -> str:
    """Validate a persisted upstream origin without retaining credentials or query data."""
    return _safe_actual_upstream(value)


def ensure_secret_free(value: Any, *, field_name: str = "request") -> Any:
    """Reject persisted task data that looks like credentials before it reaches the database."""

    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, child in value.items():
            if not isinstance(key, str):
                raise ValueError(f"{field_name} keys must be strings")
            if _SENSITIVE_KEY.search(key):
                raise ValueError(f"{field_name} cannot contain secret-bearing keys")
            result[key] = ensure_secret_free(child, field_name=field_name)
        return result
    if isinstance(value, (tuple, list)):
        return tuple(ensure_secret_free(item, field_name=field_name) for item in value)
    if isinstance(value, str):
        if len(value) > 2048:
            raise ValueError(f"{field_name} values must be bounded")
        if _SENSITIVE_VALUE.search(value):
            raise ValueError(f"{field_name} cannot contain secret-bearing values")
        parsed = urlsplit(value)
        if parsed.scheme and (parsed.username or parsed.password or parsed.query or parsed.fragment):
            raise ValueError(f"{field_name} cannot contain credential-bearing URL values")
    return value


class RawIngestionTaskRequirements(PlatformContractModel):
    """Secret-free durable task input for one controlled raw-provider request."""

    provider_id: str
    dataset_id: str
    dataset_schema_version: Annotated[str, Field(pattern=_SEMVER)]
    provider_policy_id: str
    market: str = "CN"
    request: dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: int = Field(default=30, ge=1, le=300)

    @field_validator("provider_id", "dataset_id", "provider_policy_id")
    @classmethod
    def validate_identifiers(cls, value: str, info: object) -> str:
        return _identifier(value, getattr(info, "field_name", "identifier"))

    @field_validator("market")
    @classmethod
    def validate_market(cls, value: str) -> str:
        if not value or len(value) > 32 or any(character.isspace() for character in value):
            raise ValueError("market must be a bounded non-blank market code")
        return value

    @field_validator("request")
    @classmethod
    def validate_request(cls, value: dict[str, Any]) -> dict[str, Any]:
        return ensure_secret_free(value)


class ProviderRun(PlatformContractModel):
    provider_run_id: str
    provider_id: str
    actual_upstream: str | None = None
    dataset_id: str
    dataset_schema_version: Annotated[str, Field(pattern=_SEMVER)]
    provider_policy_id: str
    provider_policy_version: Annotated[str, Field(pattern=_SEMVER)]
    adapter_version: Annotated[str, Field(pattern=_SEMVER)]
    capability_market: str
    capability_frequency: str
    task_id: str
    attempt_id: str
    request_fingerprint: Annotated[str, Field(pattern=_HASH_PATTERN)]
    started_at: AwareDatetime
    finished_at: AwareDatetime | None = None
    observed_schema_hash: str | None = Field(default=None, pattern=_HASH_PATTERN)
    row_count: int | None = Field(default=None, ge=0)
    byte_count: int | None = Field(default=None, ge=0)
    run_outcome: ProviderRunOutcome | None = None
    failure_code: str | None = None
    failure_detail_redacted: str | None = None
    raw_object_refs: tuple[str, ...] = ()

    @field_validator("provider_run_id")
    @classmethod
    def validate_provider_run_id(cls, value: str) -> str:
        return _resource_id(value, ResourceType.PROVIDER_RUN, "provider_run_id")

    @field_validator("task_id")
    @classmethod
    def validate_task_id(cls, value: str) -> str:
        return _resource_id(value, ResourceType.TASK, "task_id")

    @field_validator("attempt_id")
    @classmethod
    def validate_attempt_id(cls, value: str) -> str:
        return _resource_id(value, ResourceType.ATTEMPT, "attempt_id")

    @field_validator("provider_id", "dataset_id", "provider_policy_id")
    @classmethod
    def validate_identifiers(cls, value: str, info: object) -> str:
        return _identifier(value, getattr(info, "field_name", "identifier"))

    @field_validator("actual_upstream")
    @classmethod
    def validate_actual_upstream(cls, value: str | None) -> str | None:
        return _safe_actual_upstream(value) if value is not None else None

    @field_validator("failure_code")
    @classmethod
    def validate_failure_code(cls, value: str | None) -> str | None:
        if value is not None and not _REASON_CODE.fullmatch(value):
            raise ValueError("failure_code must be a stable uppercase identifier")
        return value

    @field_validator("failure_detail_redacted")
    @classmethod
    def validate_failure_detail(cls, value: str | None) -> str | None:
        return _redacted_text(value)

    @field_validator("raw_object_refs")
    @classmethod
    def validate_raw_object_refs(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for item in value:
            _resource_id(item, ResourceType.RAW_OBJECT, "raw_object_refs")
        if len(value) != len(set(value)):
            raise ValueError("raw_object_refs cannot contain duplicates")
        return value

    @model_validator(mode="after")
    def validate_terminal_semantics(self) -> "ProviderRun":
        if self.run_outcome is None:
            if self.finished_at is not None or self.failure_code is not None or self.failure_detail_redacted is not None:
                raise ValueError("active ProviderRun cannot contain terminal outcome fields")
            return self
        if self.finished_at is None or self.actual_upstream is None:
            raise ValueError("terminal ProviderRun requires finished_at and actual_upstream")
        if self.finished_at < self.started_at:
            raise ValueError("finished_at must not precede started_at")
        if self.run_outcome in {ProviderRunOutcome.FAILED, ProviderRunOutcome.CANCELLED}:
            if self.failure_code is None:
                raise ValueError("failed or cancelled ProviderRun requires failure_code")
        elif self.failure_code is not None or self.failure_detail_redacted is not None:
            raise ValueError("successful ProviderRun cannot contain failure diagnostics")
        if self.run_outcome is ProviderRunOutcome.SUCCEEDED and len(self.raw_object_refs) != 1:
            raise ValueError("successful ProviderRun requires exactly one RawObject")
        return self


class RawObject(PlatformContractModel):
    raw_object_id: str
    provider_run_id: str
    provider_id: str
    actual_upstream: str
    dataset_id: str
    dataset_schema_version: Annotated[str, Field(pattern=_SEMVER)]
    request_fingerprint: Annotated[str, Field(pattern=_HASH_PATTERN)]
    storage_ref: StorageRef
    raw_content_hash: Annotated[str, Field(pattern=_HASH_PATTERN)]
    media_type: str
    compression: RawCompression
    observed_at: AwareDatetime
    ingested_at: AwareDatetime
    source_published_at: AwareDatetime | None = None
    provider_schema_version: Annotated[str, Field(pattern=_SEMVER)]
    observed_schema_hash: Annotated[str, Field(pattern=_HASH_PATTERN)]
    row_count: int = Field(ge=0)
    byte_count: int = Field(ge=0)
    retention_class: RetentionClass = RetentionClass.PINNED

    @field_validator("raw_object_id")
    @classmethod
    def validate_raw_object_id(cls, value: str) -> str:
        return _resource_id(value, ResourceType.RAW_OBJECT, "raw_object_id")

    @field_validator("provider_run_id")
    @classmethod
    def validate_provider_run_id(cls, value: str) -> str:
        return _resource_id(value, ResourceType.PROVIDER_RUN, "provider_run_id")

    @field_validator("provider_id", "dataset_id")
    @classmethod
    def validate_identifiers(cls, value: str, info: object) -> str:
        return _identifier(value, getattr(info, "field_name", "identifier"))

    @field_validator("actual_upstream")
    @classmethod
    def validate_actual_upstream(cls, value: str) -> str:
        return _safe_actual_upstream(value)

    @model_validator(mode="after")
    def validate_raw_object(self) -> "RawObject":
        if self.media_type != self.storage_ref.media_type:
            raise ValueError("media_type must match storage_ref")
        if self.byte_count != self.storage_ref.size_bytes:
            raise ValueError("byte_count must match storage_ref")
        if self.raw_content_hash != self.storage_ref.content_hash:
            raise ValueError("raw_content_hash must match storage_ref")
        if self.retention_class is not RetentionClass.PINNED:
            raise ValueError("RawObject retention_class must be PINNED")
        if self.ingested_at < self.observed_at:
            raise ValueError("ingested_at must not precede observed_at")
        return self


class RawIngestionQuarantine(PlatformContractModel):
    raw_ingestion_quarantine_id: str
    provider_run_id: str
    classification: RawSchemaDriftClassification
    reason_code: str
    quarantine_status: QuarantineStatus = QuarantineStatus.OPEN
    observed_schema_hash: str | None = Field(default=None, pattern=_HASH_PATTERN)
    expected_schema_hash: Annotated[str, Field(pattern=_HASH_PATTERN)]
    evidence_storage_ref: StorageRef
    evidence_hash: Annotated[str, Field(pattern=_HASH_PATTERN)]
    created_at: AwareDatetime
    failure_detail_redacted: str | None = None

    @field_validator("raw_ingestion_quarantine_id")
    @classmethod
    def validate_quarantine_id(cls, value: str) -> str:
        return _resource_id(value, ResourceType.RAW_INGESTION_QUARANTINE, "raw_ingestion_quarantine_id")

    @field_validator("provider_run_id")
    @classmethod
    def validate_provider_run_id(cls, value: str) -> str:
        return _resource_id(value, ResourceType.PROVIDER_RUN, "provider_run_id")

    @field_validator("reason_code")
    @classmethod
    def validate_reason_code(cls, value: str) -> str:
        if not _REASON_CODE.fullmatch(value):
            raise ValueError("reason_code must be a stable uppercase identifier")
        return value

    @field_validator("failure_detail_redacted")
    @classmethod
    def validate_failure_detail(cls, value: str | None) -> str | None:
        return _redacted_text(value)

    @model_validator(mode="after")
    def validate_quarantine(self) -> "RawIngestionQuarantine":
        if self.evidence_hash != self.evidence_storage_ref.content_hash:
            raise ValueError("evidence_hash must match evidence_storage_ref")
        if self.classification is RawSchemaDriftClassification.MATCHED:
            raise ValueError("matched schemas must not enter RawIngestionQuarantine")
        return self


class RawIngestionPublishResult(PlatformContractModel):
    provider_run: ProviderRun
    raw_object: RawObject | None = None
    quarantine: RawIngestionQuarantine | None = None

    @model_validator(mode="after")
    def validate_result(self) -> "RawIngestionPublishResult":
        if (self.raw_object is None) == (self.quarantine is None):
            raise ValueError("result must contain exactly one RawObject or quarantine record")
        if self.raw_object is not None and self.provider_run.run_outcome is not ProviderRunOutcome.SUCCEEDED:
            raise ValueError("RawObject result requires a succeeded ProviderRun")
        if self.quarantine is not None and self.provider_run.run_outcome not in {
            ProviderRunOutcome.DEGRADED,
            ProviderRunOutcome.FAILED,
        }:
            raise ValueError("quarantine result requires degraded or failed ProviderRun")
        return self


__all__ = [
    "ProviderRun",
    "RawIngestionPublishResult",
    "RawIngestionQuarantine",
    "RawIngestionTaskRequirements",
    "RawObject",
    "ensure_safe_actual_upstream",
    "ensure_secret_free",
]
