from __future__ import annotations

import re
from typing import Annotated

from pydantic import AwareDatetime, Field, field_validator, model_validator

from .base import PlatformContractModel
from .enums import (
    ArtifactIntegrityState,
    ArtifactPublicationState,
    ArtifactVisibility,
    OrphanAction,
    ResourceType,
    RetentionClass,
)
from .resources import ResourceRef, parse_resource_id
from .storage import StorageRef


_SCHEMA_VERSION_PATTERN = r"^[0-9]+\.[0-9]+\.[0-9]+$"
_IDENTIFIER_PATTERN = re.compile(r"^[a-z][a-z0-9._-]{0,63}$")
_REASON_CODE_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{2,63}$")
_HASH_PATTERN = r"^sha256:[0-9a-f]{64}$"


def _validate_resource_id(value: str, expected: ResourceType, field_name: str) -> str:
    resource_type, _ = parse_resource_id(value)
    if resource_type is not expected:
        raise ValueError(f"{field_name} must use the {expected.value} resource prefix")
    return value


class ArtifactRecord(PlatformContractModel):
    artifact_id: str
    artifact_type: str
    owner_resource_ref: ResourceRef
    attempt_id: str | None = None
    storage_ref: StorageRef
    media_type: str
    size_bytes: int = Field(ge=0)
    artifact_hash: str = Field(pattern=_HASH_PATTERN)
    manifest_hash: str = Field(pattern=_HASH_PATTERN)
    schema_version: Annotated[str, Field(pattern=_SCHEMA_VERSION_PATTERN)]
    created_at: AwareDatetime
    published_at: AwareDatetime
    retention_class: RetentionClass
    visibility: ArtifactVisibility
    publication_state: ArtifactPublicationState
    integrity_state: ArtifactIntegrityState
    integrity_checked_at: AwareDatetime | None = None
    integrity_failure_code: str | None = None

    @field_validator("artifact_id")
    @classmethod
    def validate_artifact_id(cls, value: str) -> str:
        return _validate_resource_id(value, ResourceType.ARTIFACT, "artifact_id")

    @field_validator("attempt_id")
    @classmethod
    def validate_attempt_id(cls, value: str | None) -> str | None:
        if value is not None:
            _validate_resource_id(value, ResourceType.ATTEMPT, "attempt_id")
        return value

    @field_validator("artifact_type")
    @classmethod
    def validate_artifact_type(cls, value: str) -> str:
        if not _IDENTIFIER_PATTERN.fullmatch(value):
            raise ValueError("artifact_type must be a normalized identifier")
        return value

    @field_validator("integrity_failure_code")
    @classmethod
    def validate_failure_code(cls, value: str | None) -> str | None:
        if value is not None and not _REASON_CODE_PATTERN.fullmatch(value):
            raise ValueError("integrity_failure_code must be a stable uppercase identifier")
        return value

    @model_validator(mode="after")
    def validate_record(self) -> "ArtifactRecord":
        if self.media_type != self.storage_ref.media_type:
            raise ValueError("media_type must match storage_ref")
        if self.size_bytes != self.storage_ref.size_bytes:
            raise ValueError("size_bytes must match storage_ref")
        if self.artifact_hash != self.storage_ref.content_hash:
            raise ValueError("artifact_hash must match storage_ref")
        if self.published_at < self.created_at:
            raise ValueError("published_at must not precede created_at")
        if self.integrity_state is ArtifactIntegrityState.VERIFIED:
            if self.integrity_failure_code is not None:
                raise ValueError("verified artifact cannot have integrity_failure_code")
        elif self.integrity_failure_code is None:
            raise ValueError("damaged artifact requires integrity_failure_code")
        return self


class ArtifactManifest(ArtifactRecord):
    @classmethod
    def from_record(cls, record: ArtifactRecord) -> "ArtifactManifest":
        return cls.model_validate(record.model_dump(mode="python"))

    def to_record(self) -> ArtifactRecord:
        return ArtifactRecord.model_validate(self.model_dump(mode="python"))


class ArtifactPublishRequest(PlatformContractModel):
    artifact_id: str
    artifact_type: str
    owner_resource_ref: ResourceRef
    attempt_id: str | None = None
    payload_filename: str
    media_type: str
    expected_content_hash: str | None = Field(default=None, pattern=_HASH_PATTERN)
    expected_size_bytes: int | None = Field(default=None, ge=0)
    schema_version: Annotated[str, Field(pattern=_SCHEMA_VERSION_PATTERN)]
    retention_class: RetentionClass
    visibility: ArtifactVisibility

    @field_validator("artifact_id")
    @classmethod
    def validate_artifact_id(cls, value: str) -> str:
        return _validate_resource_id(value, ResourceType.ARTIFACT, "artifact_id")

    @field_validator("attempt_id")
    @classmethod
    def validate_attempt_id(cls, value: str | None) -> str | None:
        if value is not None:
            _validate_resource_id(value, ResourceType.ATTEMPT, "attempt_id")
        return value

    @field_validator("artifact_type")
    @classmethod
    def validate_artifact_type(cls, value: str) -> str:
        if not _IDENTIFIER_PATTERN.fullmatch(value):
            raise ValueError("artifact_type must be a normalized identifier")
        return value

    @field_validator("payload_filename")
    @classmethod
    def validate_payload_filename(cls, value: str) -> str:
        if (
            not value
            or value in {".", "..", "manifest.json"}
            or "/" in value
            or "\\" in value
            or ":" in value
            or any(ord(character) < 32 or ord(character) == 127 for character in value)
        ):
            raise ValueError("payload_filename must be one safe path segment")
        return value

    @field_validator("media_type")
    @classmethod
    def validate_media_type(cls, value: str) -> str:
        StorageRef.validate_media_type(value)
        return value


class ArtifactPublishResult(PlatformContractModel):
    artifact_id: str
    storage_ref: StorageRef
    artifact_hash: str = Field(pattern=_HASH_PATTERN)
    manifest_hash: str = Field(pattern=_HASH_PATTERN)
    publication_state: ArtifactPublicationState
    integrity_state: ArtifactIntegrityState
    published_at: AwareDatetime

    @field_validator("artifact_id")
    @classmethod
    def validate_artifact_id(cls, value: str) -> str:
        return _validate_resource_id(value, ResourceType.ARTIFACT, "artifact_id")


class OrphanCandidate(PlatformContractModel):
    artifact_id: str
    manifest_relative_path: str
    reason_code: str
    estimated_size_bytes: int = Field(ge=0)
    recoverable_actions: tuple[OrphanAction, ...]

    @field_validator("artifact_id")
    @classmethod
    def validate_artifact_id(cls, value: str) -> str:
        return _validate_resource_id(value, ResourceType.ARTIFACT, "artifact_id")

    @field_validator("reason_code")
    @classmethod
    def validate_reason_code(cls, value: str) -> str:
        if not _REASON_CODE_PATTERN.fullmatch(value):
            raise ValueError("reason_code must be a stable uppercase identifier")
        return value


class OrphanDryRunResult(PlatformContractModel):
    scanned_known_directories: int = Field(ge=0)
    candidates: tuple[OrphanCandidate, ...]
    skipped_invalid_manifests: int = Field(ge=0)
    estimated_recoverable_bytes: int = Field(ge=0)
    deletion_performed: bool

    @model_validator(mode="after")
    def validate_dry_run(self) -> "OrphanDryRunResult":
        if self.deletion_performed:
            raise ValueError("WP-0102 orphan sweeper cannot delete artifacts")
        return self


class ArtifactRecoveryResult(PlatformContractModel):
    artifact_id: str
    recovered: bool
    already_registered: bool
    publication_state: ArtifactPublicationState

    @field_validator("artifact_id")
    @classmethod
    def validate_artifact_id(cls, value: str) -> str:
        return _validate_resource_id(value, ResourceType.ARTIFACT, "artifact_id")

    @model_validator(mode="after")
    def validate_outcome(self) -> "ArtifactRecoveryResult":
        if self.recovered == self.already_registered:
            raise ValueError("exactly one recovery outcome must be true")
        return self
