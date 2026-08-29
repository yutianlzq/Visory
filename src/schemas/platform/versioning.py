from __future__ import annotations

import re

from pydantic import Field, field_validator, model_validator

from .base import PlatformContractModel
from .enums import PublicationStatus, QualityStatus, RevisionKind, TaskState


_SEMVER = r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
_SEMVER_PATTERN = re.compile(rf"^{_SEMVER}$")
_POLICY_VERSION_PATTERN = re.compile(rf"^[a-z][a-z0-9_]*_{_SEMVER}$")


def _validate_nonblank(value: str | None, field_name: str) -> str | None:
    if value is not None and not value.strip():
        raise ValueError(f"{field_name} cannot be blank")
    return value


class RevisionMetadata(PlatformContractModel):
    schema_version: str
    definition_version: str | None = None
    policy_version: str | None = None
    revision: int = Field(ge=1)
    revision_kind: RevisionKind
    supersedes_id: str | None = None

    @field_validator("schema_version", "definition_version")
    @classmethod
    def validate_semver(cls, value: str | None, info: object) -> str | None:
        if value is None:
            return value
        if not _SEMVER_PATTERN.fullmatch(value):
            raise ValueError(f"{getattr(info, 'field_name', 'version')} must be semantic version")
        return value

    @field_validator("policy_version")
    @classmethod
    def validate_policy_version(cls, value: str | None) -> str | None:
        if value is not None and not _POLICY_VERSION_PATTERN.fullmatch(value):
            raise ValueError("policy_version must use <policy_name>_<semver>")
        return value

    @field_validator("supersedes_id")
    @classmethod
    def reject_blank_supersedes(cls, value: str | None) -> str | None:
        return _validate_nonblank(value, "supersedes_id")

    @model_validator(mode="after")
    def validate_revision_relationship(self) -> "RevisionMetadata":
        if self.revision_kind is RevisionKind.CORRECTION:
            if self.revision < 2 or self.supersedes_id is None:
                raise ValueError("CORRECTION requires revision >= 2 and supersedes_id")
        if self.revision_kind is RevisionKind.INITIAL and self.supersedes_id is not None:
            raise ValueError("INITIAL revision cannot supersede another object")
        return self


class PublicationMetadata(PlatformContractModel):
    publication_status: PublicationStatus
    quality_status: QualityStatus
    certified_capabilities: tuple[str, ...] = ()

    @field_validator("certified_capabilities")
    @classmethod
    def validate_capabilities(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not item.strip() for item in value):
            raise ValueError("certified_capabilities cannot contain blank values")
        if len(value) != len(set(value)):
            raise ValueError("certified_capabilities cannot contain duplicates")
        return value

    @model_validator(mode="after")
    def validate_certification_quality(self) -> "PublicationMetadata":
        if self.publication_status is PublicationStatus.CERTIFIED and self.quality_status in {
            QualityStatus.FAILED,
            QualityStatus.UNAVAILABLE,
        }:
            raise ValueError("CERTIFIED publication cannot have failed or unavailable quality")
        return self


class TaskStateMetadata(PlatformContractModel):
    task_state: TaskState
    blocked_reason_code: str | None = None
    unblock_condition: str | None = None
    failure_code: str | None = None

    @field_validator("blocked_reason_code", "unblock_condition", "failure_code")
    @classmethod
    def reject_blank_reason(cls, value: str | None, info: object) -> str | None:
        return _validate_nonblank(value, getattr(info, "field_name", "reason"))

    @model_validator(mode="after")
    def validate_state_metadata(self) -> "TaskStateMetadata":
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
        return self
