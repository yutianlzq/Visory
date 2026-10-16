from __future__ import annotations

import re
from datetime import date
from enum import Enum
from typing import Annotated, Any
from urllib.parse import urlsplit, urlunsplit

from pydantic import Field, field_validator, model_validator

from .base import PlatformContractModel
from .hashing import compute_content_hash


_COMMIT_SHA = r"^[0-9a-f]{40}$"
_HASH = r"^sha256:[0-9a-f]{64}$"
_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]{1,127}$")
_ENTRYPOINT = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]{0,127}$")
_REASON_CODE = re.compile(r"^[A-Z][A-Z0-9_]{2,95}$")
_SEMVER = r"^[0-9]+\.[0-9]+\.[0-9]+$"


class ProviderSourceKind(str, Enum):
    HTTP = "HTTP"
    TCP = "TCP"
    SDK = "SDK"
    FILE = "FILE"
    FIXTURE = "FIXTURE"


class ProviderSourceEvidenceState(str, Enum):
    PROVEN = "PROVEN"
    UNPROVEN = "UNPROVEN"
    FAILED = "FAILED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class ProviderSourceExecutionState(str, Enum):
    AVAILABLE = "AVAILABLE"
    BLOCKED = "BLOCKED"
    UNAVAILABLE = "UNAVAILABLE"
    FIXTURE_ONLY = "FIXTURE_ONLY"


def _safe_uri(value: str, field_name: str) -> str:
    if not value or len(value) > 512:
        raise ValueError(f"{field_name} must be a bounded URI")
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError(f"{field_name} must be an https URI")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError(f"{field_name} cannot contain credentials, query, or fragment")
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", ""))


def _safe_origin(value: str) -> str:
    if not value or len(value) > 255:
        raise ValueError("actual_upstream must be a bounded redacted origin")
    parsed = urlsplit(value)
    if parsed.scheme:
        if parsed.username or parsed.password or parsed.query or parsed.fragment or not parsed.hostname:
            raise ValueError("actual_upstream cannot contain credentials, query, or fragment")
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", ""))
    if any(marker in value for marker in ("/", "\\", "@", "?", "#", ":")):
        raise ValueError("actual_upstream must be a redacted origin or URI")
    return value


def _route_payload(value: "ProviderSourceRouteEvidence") -> dict[str, Any]:
    return value.model_dump(mode="json", exclude={"source_route_hash"})


class ProviderSourceRouteEvidence(PlatformContractModel):
    """Immutable binding from a controlled adapter to its real upstream source."""

    source_route_id: str
    provider_id: str
    dataset_id: str
    adapter_name: str
    adapter_version: Annotated[str, Field(pattern=_SEMVER)]
    adapter_repository: str
    adapter_release: Annotated[str, Field(pattern=_SEMVER)]
    adapter_commit: Annotated[str, Field(pattern=_COMMIT_SHA)]
    adapter_blob: Annotated[str, Field(pattern=_COMMIT_SHA)]
    adapter_entrypoint: str
    actual_upstream: str
    source_kind: ProviderSourceKind
    market: str
    documented_history_start: date | None = None
    coverage_evidence_state: ProviderSourceEvidenceState
    pit_evidence_state: ProviderSourceEvidenceState
    pagination_evidence_state: ProviderSourceEvidenceState
    revision_evidence_state: ProviderSourceEvidenceState
    execution_state: ProviderSourceExecutionState
    unavailable_reason_code: str | None = None
    license_id: str
    license_blob: Annotated[str, Field(pattern=_COMMIT_SHA)]
    source_route_hash: Annotated[str, Field(pattern=_HASH)]

    @field_validator("source_route_id", "provider_id", "dataset_id", "adapter_name")
    @classmethod
    def validate_identifiers(cls, value: str, info: object) -> str:
        if not _IDENTIFIER.fullmatch(value):
            raise ValueError(f"{getattr(info, 'field_name', 'identifier')} must be a normalized identifier")
        return value

    @field_validator("adapter_repository")
    @classmethod
    def validate_adapter_repository(cls, value: str) -> str:
        return _safe_uri(value, "adapter_repository")

    @field_validator("actual_upstream")
    @classmethod
    def validate_actual_upstream(cls, value: str) -> str:
        return _safe_origin(value)

    @field_validator("adapter_entrypoint")
    @classmethod
    def validate_entrypoint(cls, value: str) -> str:
        if not _ENTRYPOINT.fullmatch(value):
            raise ValueError("adapter_entrypoint must be a bounded Python entrypoint")
        return value

    @field_validator("market")
    @classmethod
    def validate_market(cls, value: str) -> str:
        if not value or len(value) > 32 or any(character.isspace() for character in value):
            raise ValueError("market must be a bounded non-blank market code")
        return value

    @field_validator("unavailable_reason_code")
    @classmethod
    def validate_reason_code(cls, value: str | None) -> str | None:
        if value is not None and not _REASON_CODE.fullmatch(value):
            raise ValueError("unavailable_reason_code must be a stable uppercase identifier")
        return value

    @field_validator("license_id")
    @classmethod
    def validate_license_id(cls, value: str) -> str:
        if not value or len(value) > 64 or any(character.isspace() for character in value):
            raise ValueError("license_id must be a bounded SPDX-style identifier")
        return value

    @model_validator(mode="after")
    def validate_route(self) -> "ProviderSourceRouteEvidence":
        expected_hash = compute_content_hash(_route_payload(self))
        if self.source_route_hash != expected_hash:
            raise ValueError("source_route_hash must match the canonical route evidence")
        if self.execution_state is ProviderSourceExecutionState.AVAILABLE:
            required = (
                self.coverage_evidence_state,
                self.pit_evidence_state,
                self.pagination_evidence_state,
                self.revision_evidence_state,
            )
            if any(state not in {ProviderSourceEvidenceState.PROVEN, ProviderSourceEvidenceState.NOT_APPLICABLE} for state in required):
                raise ValueError("available source route requires complete execution evidence")
            if self.unavailable_reason_code is not None:
                raise ValueError("available source route cannot contain an unavailable reason")
        elif self.unavailable_reason_code is None:
            raise ValueError("non-available source route requires an unavailable reason")
        if self.source_kind is ProviderSourceKind.FIXTURE and self.execution_state is not ProviderSourceExecutionState.FIXTURE_ONLY:
            raise ValueError("fixture source route must remain fixture-only")
        if self.execution_state is ProviderSourceExecutionState.FIXTURE_ONLY and self.source_kind is not ProviderSourceKind.FIXTURE:
            raise ValueError("fixture-only execution requires a fixture source")
        return self


def build_provider_source_route_evidence(**payload: Any) -> ProviderSourceRouteEvidence:
    canonical = dict(payload)
    canonical["source_route_hash"] = compute_content_hash(canonical)
    return ProviderSourceRouteEvidence.model_validate(canonical)


__all__ = [
    "ProviderSourceEvidenceState",
    "ProviderSourceExecutionState",
    "ProviderSourceKind",
    "ProviderSourceRouteEvidence",
    "build_provider_source_route_evidence",
]
