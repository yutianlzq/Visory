from __future__ import annotations

import re
from typing import Annotated, Any

from pydantic import AwareDatetime, Field, field_validator, model_validator

from .base import PlatformContractModel
from .enums import ProviderCapabilityStatus, ProviderKind, ProviderMergeMode

_SEMVER = r"^[0-9]+\.[0-9]+\.[0-9]+$"
_KNOWN_UNITS = frozenset({"identifier", "calendar_date", "enum", "boolean", "reason_code", "utc_instant", "iso_4217", "ratio", "cny_per_share", "revision", "statement_type", "line_item", "financial_value", "financial_unit", "text", "code", "shares", "shares_per_lot", "cny"})
_ID = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
_CAPABILITY_STATUSES = ("AVAILABLE", "DEGRADED", "UNAVAILABLE", "UNVERIFIED")
_MERGE_MODES = ("REPLACE_PARTITION", "APPEND_DISJOINT", "ENRICH_FIELDS", "COMPARE_ONLY")
_FIELD_TYPES = frozenset({"string", "date", "number", "integer", "boolean", "timestamptz"})


def _identifier(value: str, field: str) -> str:
    if not _ID.fullmatch(value):
        raise ValueError(f"{field} must be a normalized lowercase identifier")
    return value


class ProviderDefinition(PlatformContractModel):
    provider_id: str
    display_name: Annotated[str, Field(min_length=1, max_length=255)]
    adapter_name: str
    adapter_version: Annotated[str, Field(pattern=_SEMVER)]
    provider_kind: ProviderKind
    enabled: bool = True
    credential_ref: str | None = None
    created_at: AwareDatetime
    updated_at: AwareDatetime

    @field_validator("provider_id")
    @classmethod
    def validate_provider_id(cls, value: str) -> str:
        return _identifier(value, "provider_id")

    @field_validator("adapter_name")
    @classmethod
    def validate_adapter_name(cls, value: str) -> str:
        return _identifier(value, "adapter_name")

    @field_validator("provider_kind")
    @classmethod
    def validate_provider_kind(cls, value: str) -> str:
        if value not in ProviderKind:
            raise ValueError("provider_kind is not supported")
        return value

    @field_validator("credential_ref")
    @classmethod
    def validate_credential_ref(cls, value: str | None) -> str | None:
        if value is not None and (not value.startswith("secret://") or len(value) > 255):
            raise ValueError("credential_ref must be a secret:// reference")
        return value

    @model_validator(mode="after")
    def validate_timestamps(self) -> "ProviderDefinition":
        if self.updated_at < self.created_at:
            raise ValueError("updated_at must not precede created_at")
        return self


class ProviderCapability(PlatformContractModel):
    provider_id: str
    dataset_id: str
    dataset_schema_version: Annotated[str, Field(pattern=_SEMVER)]
    market: str
    frequency: str
    supported_fields: tuple[str, ...]
    history_start: AwareDatetime | None = None
    freshness_sla_seconds: int = Field(ge=0)
    rate_limit_profile: dict[str, Any]
    provider_capability_status: ProviderCapabilityStatus
    checked_at: AwareDatetime

    @field_validator("provider_id", "dataset_id")
    @classmethod
    def validate_ids(cls, value: str, info) -> str:
        return _identifier(value, info.field_name)

    @field_validator("provider_capability_status")
    @classmethod
    def validate_capability_status(cls, value: str) -> str:
        if value not in _CAPABILITY_STATUSES:
            raise ValueError("provider_capability_status is not supported")
        return value

    @field_validator("supported_fields")
    @classmethod
    def validate_fields(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(value)) != len(value) or any(not _ID.fullmatch(item) for item in value):
            raise ValueError("supported_fields must contain unique normalized identifiers")
        return tuple(value)


class ProviderPolicy(PlatformContractModel):
    provider_policy_id: str
    dataset_id: str
    dataset_schema_version: Annotated[str, Field(pattern=_SEMVER)]
    policy_version: Annotated[str, Field(pattern=_SEMVER)]
    primary_provider_id: str
    supplemental_provider_ids: tuple[str, ...] = ()
    allowed_merge_mode: ProviderMergeMode
    fallback_triggers: tuple[str, ...] = ()
    field_authority_map: dict[str, str]
    conflict_tolerance: dict[str, Any]
    freshness_sla_seconds: int = Field(ge=0)
    required_quality_rules: tuple[str, ...] = ()
    effective_from: AwareDatetime
    effective_to: AwareDatetime | None = None

    @field_validator("provider_policy_id", "dataset_id", "primary_provider_id")
    @classmethod
    def validate_ids(cls, value: str, info) -> str:
        return _identifier(value, info.field_name)

    @field_validator("supplemental_provider_ids")
    @classmethod
    def validate_supplementals(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(value)) != len(value) or any(not _ID.fullmatch(item) for item in value):
            raise ValueError("supplemental_provider_ids must be unique normalized identifiers")
        return tuple(value)

    @field_validator("allowed_merge_mode")
    @classmethod
    def validate_merge_mode(cls, value: str) -> str:
        if value not in _MERGE_MODES:
            raise ValueError("allowed_merge_mode is not supported")
        return value

    @model_validator(mode="after")
    def validate_policy(self) -> "ProviderPolicy":
        if self.primary_provider_id in self.supplemental_provider_ids:
            raise ValueError("primary provider cannot be supplemental")
        if self.effective_to is not None and self.effective_to <= self.effective_from:
            raise ValueError("effective_to must be after effective_from")
        for field_name, provider_id in self.field_authority_map.items():
            if not _ID.fullmatch(field_name) or provider_id not in ({self.primary_provider_id} | set(self.supplemental_provider_ids)):
                raise ValueError("field_authority_map references an undeclared provider")
        return self


class DatasetDefinition(PlatformContractModel):
    dataset_id: str
    schema_version: Annotated[str, Field(pattern=_SEMVER)]
    entity_scope: str
    frequency: str
    primary_key_fields: tuple[str, ...]
    required_fields: tuple[str, ...]
    optional_fields: tuple[str, ...] = ()
    field_types: dict[str, str]
    units: dict[str, str]
    enum_domains: dict[str, tuple[str, ...]]
    time_semantics: dict[str, str]
    null_semantics: dict[str, str]
    partition_template: str
    quality_rule_ids: tuple[str, ...] = ()
    owner_module: str

    @field_validator("dataset_id")
    @classmethod
    def validate_dataset_id(cls, value: str) -> str:
        return _identifier(value, "dataset_id")

    @field_validator("primary_key_fields", "required_fields")
    @classmethod
    def validate_required_field_lists(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value or len(set(value)) != len(value) or any(not _ID.fullmatch(item) for item in value):
            raise ValueError("required field lists must contain unique normalized identifiers")
        return tuple(value)

    @field_validator("optional_fields")
    @classmethod
    def validate_optional_fields(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(value)) != len(value) or any(not _ID.fullmatch(item) for item in value):
            raise ValueError("optional_fields must contain unique normalized identifiers")
        return tuple(value)

    @model_validator(mode="after")
    def validate_fields(self) -> "DatasetDefinition":
        required = set(self.required_fields)
        optional = set(self.optional_fields)
        if required & optional:
            raise ValueError("required_fields and optional_fields must not overlap")
        if not set(self.primary_key_fields) <= required:
            raise ValueError("primary_key_fields must be required fields")
        declared = required | optional
        if set(self.field_types) != declared:
            raise ValueError("field_types must exactly cover required and optional fields")
        if any(value not in _FIELD_TYPES for value in self.field_types.values()):
            raise ValueError("field_types contains an unsupported type")
        if set(self.units) != declared:
            raise ValueError("units must explicitly cover every declared field")
        if any(unit not in _KNOWN_UNITS for unit in self.units.values()):
            raise ValueError("units contains an unsupported unit")
        if set(self.null_semantics) != declared:
            raise ValueError("null_semantics must explicitly cover every declared field")
        if set(self.time_semantics) != declared:
            raise ValueError("time_semantics must explicitly cover every declared field")
        if not set(self.enum_domains) <= declared:
            raise ValueError("enum_domains references an undeclared field")
        if any(not values for values in self.enum_domains.values()):
            raise ValueError("enum_domains must not contain empty enum domains")
        if self.dataset_id == "bar_1d_raw":
            forbidden = {"volume", "turnover"} & declared
            if forbidden:
                raise ValueError("bar_1d_raw must use formal volume_shares and amount_cny fields")
            required_bar_fields = {"entity_key", "trade_date", "open", "high", "low", "close", "volume_shares", "amount_cny", "prev_close", "trading_status", "price_limit_up", "price_limit_down", "available_at"}
            if not required_bar_fields <= required:
                raise ValueError("bar_1d_raw is missing a formal contract field")
        return self


class ProviderSettingsProvider(PlatformContractModel):
    """Public Settings projection; never exposes credential references or actual upstream claims."""

    provider_id: str
    display_name: Annotated[str, Field(min_length=1, max_length=255)]
    adapter_name: str
    adapter_version: Annotated[str, Field(pattern=_SEMVER)]
    provider_kind: ProviderKind
    enabled: bool = True
    credential_configured: bool = False


class ProviderSettingsProjection(PlatformContractModel):
    providers: tuple[ProviderSettingsProvider, ...]
    datasets: tuple[DatasetDefinition, ...]
    capabilities: tuple[ProviderCapability, ...]
    policies: tuple[ProviderPolicy, ...]


__all__ = ["DatasetDefinition", "ProviderCapability", "ProviderDefinition", "ProviderPolicy", "ProviderSettingsProvider", "ProviderSettingsProjection"]
