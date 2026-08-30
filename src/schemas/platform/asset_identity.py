from __future__ import annotations

import re
import unicodedata
from datetime import date
from typing import Annotated

from pydantic import AwareDatetime, Field, ValidationInfo, field_validator, model_validator

from .base import PlatformContractModel
from .enums import (
    AliasType,
    AliasVerificationStatus,
    AssetType,
    IdentityStatus,
    QuarantineStatus,
    ResolutionStatus,
)
from .identity import build_entity_key, parse_entity_key


_SCHEMA_VERSION_PATTERN = r"^[0-9]+\.[0-9]+\.[0-9]+$"
_IDENTIFIER_PATTERN = re.compile(r"^[a-z][a-z0-9._-]{0,127}$")
_NAMESPACE_PATTERN = re.compile(r"^[a-z][a-z0-9._-]{0,63}:[a-z][a-z0-9._-]{0,63}$")
_ALIAS_ID_PATTERN = re.compile(r"^alias_[a-zA-Z0-9._-]{1,120}$")
_REASON_CODE_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{2,63}$")


def normalize_alias_value(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("alias value must be a string")
    normalized = unicodedata.normalize("NFKC", value).strip().casefold()
    if not normalized or any(ord(character) < 32 for character in normalized):
        raise ValueError("alias value must be nonblank printable text")
    return normalized


class AssetIdentityRecord(PlatformContractModel):
    asset_type: AssetType
    canonical_id: str
    entity_key: str
    exchange: Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9_]{1,15}$")]
    market: Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9_]{1,15}$")]
    currency: Annotated[str, Field(pattern=r"^[A-Z]{3}$")]
    country: Annotated[str, Field(pattern=r"^[A-Z]{2}$")]
    valid_from: date
    valid_to: date | None = None
    list_date: date | None = None
    delist_date: date | None = None
    identity_status: IdentityStatus
    schema_version: Annotated[str, Field(pattern=_SCHEMA_VERSION_PATTERN)]
    created_at: AwareDatetime

    @field_validator("entity_key")
    @classmethod
    def validate_entity_key(cls, value: str, info: ValidationInfo) -> str:
        parse_entity_key(value)
        asset_type = info.data.get("asset_type")
        canonical_id = info.data.get("canonical_id")
        if asset_type is not None and canonical_id is not None and value != build_entity_key(asset_type, canonical_id):
            raise ValueError("entity_key does not match asset_type and canonical_id")
        return value

    @model_validator(mode="after")
    def validate_identity(self) -> "AssetIdentityRecord":
        if self.valid_to is not None and self.valid_to <= self.valid_from:
            raise ValueError("valid_to must be after valid_from")
        if self.list_date is not None and self.delist_date is not None and self.delist_date < self.list_date:
            raise ValueError("delist_date must not precede list_date")
        return self


class AssetAlias(PlatformContractModel):
    alias_id: str
    entity_key: str
    alias_type: AliasType
    namespace: Annotated[str, Field(max_length=128)]
    alias_value: Annotated[str, Field(min_length=1, max_length=256)]
    normalized_value: Annotated[str, Field(min_length=1, max_length=256)]
    valid_from: date
    valid_to: date | None = None
    available_at: AwareDatetime
    source_provider: str
    actual_upstream: str
    verification_status: AliasVerificationStatus
    revision: Annotated[int, Field(ge=1)]
    created_at: AwareDatetime

    @field_validator("alias_id")
    @classmethod
    def validate_alias_id(cls, value: str) -> str:
        if not _ALIAS_ID_PATTERN.fullmatch(value):
            raise ValueError("alias_id must use the alias_ prefix")
        return value

    @field_validator("entity_key")
    @classmethod
    def validate_entity_key(cls, value: str) -> str:
        parse_entity_key(value)
        return value

    @field_validator("namespace")
    @classmethod
    def validate_namespace(cls, value: str) -> str:
        if not _NAMESPACE_PATTERN.fullmatch(value):
            raise ValueError("namespace must identify producer and context")
        return value

    @field_validator("source_provider", "actual_upstream")
    @classmethod
    def validate_lineage_id(cls, value: str) -> str:
        if not _IDENTIFIER_PATTERN.fullmatch(value):
            raise ValueError("provider lineage values must be normalized identifiers")
        return value

    @model_validator(mode="after")
    def validate_alias(self) -> "AssetAlias":
        if self.normalized_value != normalize_alias_value(self.alias_value):
            raise ValueError("normalized_value does not match alias_value")
        if self.valid_to is not None and self.valid_to <= self.valid_from:
            raise ValueError("valid_to must be after valid_from")
        return self


class AssetResolutionRequest(PlatformContractModel):
    input_namespace: Annotated[str, Field(max_length=128)]
    input_value: Annotated[str, Field(min_length=1, max_length=256)]
    asset_type: AssetType | None = None
    allow_inactive: bool = False

    @field_validator("input_namespace")
    @classmethod
    def validate_namespace(cls, value: str) -> str:
        if not _NAMESPACE_PATTERN.fullmatch(value):
            raise ValueError("input_namespace must identify producer and context")
        return value

    @field_validator("input_value")
    @classmethod
    def validate_input_value(cls, value: str) -> str:
        if value != value.strip() or any(ord(character) < 32 for character in value):
            raise ValueError("input_value must be trimmed printable text")
        return value


class AssetResolutionCandidate(PlatformContractModel):
    asset_type: AssetType
    canonical_id: str
    entity_key: str
    alias_type: AliasType
    namespace: Annotated[str, Field(max_length=128)]
    matched_value: str
    identity_status: IdentityStatus

    @model_validator(mode="after")
    def validate_identity(self) -> "AssetResolutionCandidate":
        if self.entity_key != build_entity_key(self.asset_type, self.canonical_id):
            raise ValueError("candidate entity_key does not match identity")
        return self


class AssetResolutionResult(PlatformContractModel):
    asset_type: AssetType | None
    canonical_id: str | None
    entity_key: str | None
    resolution_status: ResolutionStatus
    candidates: tuple[AssetResolutionCandidate, ...]
    reason_codes: tuple[str, ...]
    resolver_version: Annotated[str, Field(pattern=_SCHEMA_VERSION_PATTERN)]
    resolved_at: AwareDatetime

    @field_validator("reason_codes")
    @classmethod
    def validate_reason_codes(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if any(not _REASON_CODE_PATTERN.fullmatch(value) for value in values):
            raise ValueError("reason_codes must use stable uppercase identifiers")
        return values

    @model_validator(mode="after")
    def validate_resolution(self) -> "AssetResolutionResult":
        identity_values = (self.asset_type, self.canonical_id, self.entity_key)
        if any(value is not None for value in identity_values) and not all(value is not None for value in identity_values):
            raise ValueError("asset_type, canonical_id and entity_key must be provided together")
        if self.entity_key is not None and self.entity_key != build_entity_key(self.asset_type, self.canonical_id):
            raise ValueError("resolved entity_key does not match identity")
        if self.resolution_status in {ResolutionStatus.RESOLVED, ResolutionStatus.INACTIVE} and self.entity_key is None:
            raise ValueError("resolved and inactive results require an identity")
        if self.resolution_status is ResolutionStatus.AMBIGUOUS and not self.candidates:
            raise ValueError("ambiguous results require candidates")
        return self


class IdentityQuarantineRecord(PlatformContractModel):
    quarantine_id: str
    namespace: Annotated[str, Field(max_length=128)]
    normalized_value: str
    candidate_entity_key: str
    conflicting_entity_keys: tuple[str, ...]
    reason_code: str
    source_provider: str
    actual_upstream: str
    quarantine_status: QuarantineStatus
    revision: Annotated[int, Field(ge=1)]
    created_at: AwareDatetime

    @field_validator("namespace")
    @classmethod
    def validate_namespace(cls, value: str) -> str:
        if not _NAMESPACE_PATTERN.fullmatch(value):
            raise ValueError("namespace must identify producer and context")
        return value

    @field_validator("candidate_entity_key")
    @classmethod
    def validate_candidate(cls, value: str) -> str:
        parse_entity_key(value)
        return value

    @field_validator("conflicting_entity_keys")
    @classmethod
    def validate_conflicts(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if not values:
            raise ValueError("conflicting_entity_keys cannot be empty")
        for value in values:
            parse_entity_key(value)
        return values

    @field_validator("reason_code")
    @classmethod
    def validate_reason_code(cls, value: str) -> str:
        if not _REASON_CODE_PATTERN.fullmatch(value):
            raise ValueError("reason_code must be stable uppercase identifier")
        return value
