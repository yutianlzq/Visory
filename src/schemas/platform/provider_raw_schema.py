from __future__ import annotations

import re
from typing import Annotated

from pydantic import Field, field_validator, model_validator

from .base import PlatformContractModel
from .hashing import compute_content_hash

_SEMVER = r"^[0-9]+\.[0-9]+\.[0-9]+$"
_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_HASH = r"^sha256:[0-9a-f]{64}$"
_FIELD_TYPES = frozenset({"string", "date", "number", "integer", "boolean", "timestamptz"})


def _validate_identifier(value: str, field_name: str) -> str:
    if not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"{field_name} must be a normalized lowercase identifier")
    return value


def _schema_payload(value: ProviderRawSchemaDefinition | dict[str, object]) -> dict[str, object]:
    if isinstance(value, ProviderRawSchemaDefinition):
        source = value.model_dump(mode="python", exclude={"expected_schema_hash"})
    else:
        source = dict(value)
    return {
        "provider_id": source["provider_id"],
        "adapter_version": source["adapter_version"],
        "dataset_id": source["dataset_id"],
        "dataset_schema_version": source["dataset_schema_version"],
        "provider_schema_version": source["provider_schema_version"],
        "required_fields": tuple(sorted(source["required_fields"])),
        "optional_fields": tuple(sorted(source["optional_fields"])),
        "field_types": {key: source["field_types"][key] for key in sorted(source["field_types"])},
    }


class ProviderRawSchemaDefinition(PlatformContractModel):
    """Versioned provider-native schema; intentionally separate from DatasetDefinition."""

    provider_id: str
    adapter_version: Annotated[str, Field(pattern=_SEMVER)]
    dataset_id: str
    dataset_schema_version: Annotated[str, Field(pattern=_SEMVER)]
    provider_schema_version: Annotated[str, Field(pattern=_SEMVER)]
    required_fields: tuple[str, ...]
    optional_fields: tuple[str, ...] = ()
    field_types: dict[str, str]
    expected_schema_hash: Annotated[str, Field(pattern=_HASH)]

    @field_validator("provider_id", "dataset_id")
    @classmethod
    def validate_identifiers(cls, value: str, info: object) -> str:
        return _validate_identifier(value, getattr(info, "field_name", "identifier"))

    @field_validator("required_fields", "optional_fields")
    @classmethod
    def validate_field_lists(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(value)) != len(value) or any(not _IDENTIFIER.fullmatch(item) for item in value):
            raise ValueError("raw schema fields must contain unique normalized identifiers")
        return tuple(value)

    @field_validator("field_types")
    @classmethod
    def validate_field_types(cls, value: dict[str, str]) -> dict[str, str]:
        if any(not _IDENTIFIER.fullmatch(key) for key in value):
            raise ValueError("raw schema field_types keys must be normalized identifiers")
        if any(field_type not in _FIELD_TYPES for field_type in value.values()):
            raise ValueError("raw schema field_types contains an unsupported type")
        return dict(value)

    @model_validator(mode="after")
    def validate_definition(self) -> "ProviderRawSchemaDefinition":
        required = set(self.required_fields)
        optional = set(self.optional_fields)
        declared = required | optional
        if not required:
            raise ValueError("raw schema must declare at least one required field")
        if required & optional:
            raise ValueError("raw schema required_fields and optional_fields must not overlap")
        if set(self.field_types) != declared:
            raise ValueError("raw schema field_types must exactly cover required and optional fields")
        expected = compute_provider_raw_schema_hash(self)
        if self.expected_schema_hash != expected:
            raise ValueError("expected_schema_hash does not match the raw schema definition")
        return self


def compute_provider_raw_schema_hash(value: ProviderRawSchemaDefinition | dict[str, object]) -> str:
    """Compute the stable hash over provider-native fields and types only."""

    return compute_content_hash(_schema_payload(value))


def build_provider_raw_schema_definition(
    *,
    provider_id: str,
    adapter_version: str,
    dataset_id: str,
    dataset_schema_version: str,
    provider_schema_version: str,
    required_fields: tuple[str, ...],
    optional_fields: tuple[str, ...] = (),
    field_types: dict[str, str],
) -> ProviderRawSchemaDefinition:
    payload = {
        "provider_id": provider_id,
        "adapter_version": adapter_version,
        "dataset_id": dataset_id,
        "dataset_schema_version": dataset_schema_version,
        "provider_schema_version": provider_schema_version,
        "required_fields": required_fields,
        "optional_fields": optional_fields,
        "field_types": field_types,
    }
    return ProviderRawSchemaDefinition(**payload, expected_schema_hash=compute_provider_raw_schema_hash(payload))


__all__ = [
    "ProviderRawSchemaDefinition",
    "build_provider_raw_schema_definition",
    "compute_provider_raw_schema_hash",
]
