from __future__ import annotations

import re

from pydantic import field_validator, model_validator

from .base import PlatformContractModel
from .enums import AssetType


_CANONICAL_ID_PATTERN = re.compile(r"^[a-z][a-z0-9._-]*$")


def _validate_canonical_id(canonical_id: str) -> str:
    if not isinstance(canonical_id, str):
        raise TypeError("canonical_id must be a string")
    if not _CANONICAL_ID_PATTERN.fullmatch(canonical_id):
        raise ValueError("canonical_id must be normalized lowercase and namespace-qualified")
    return canonical_id


def build_entity_key(asset_type: AssetType, canonical_id: str) -> str:
    if not isinstance(asset_type, AssetType):
        try:
            asset_type = AssetType(asset_type)
        except (TypeError, ValueError) as exc:
            raise ValueError("asset_type must be registered") from exc
    return f"{asset_type.value}:{_validate_canonical_id(canonical_id)}"


def parse_entity_key(entity_key: str) -> tuple[AssetType, str]:
    if not isinstance(entity_key, str) or entity_key.count(":") != 1:
        raise ValueError("entity_key must use <asset_type>:<canonical_id>")
    asset_value, canonical_id = entity_key.split(":", 1)
    try:
        asset_type = AssetType(asset_value)
    except ValueError as exc:
        raise ValueError("entity_key asset_type must be registered") from exc
    canonical_id = _validate_canonical_id(canonical_id)
    if entity_key != f"{asset_type.value}:{canonical_id}":
        raise ValueError("entity_key must be canonical lowercase")
    return asset_type, canonical_id


class EntityIdentity(PlatformContractModel):
    asset_type: AssetType
    canonical_id: str
    entity_key: str

    @field_validator("canonical_id")
    @classmethod
    def validate_canonical_id(cls, value: str) -> str:
        return _validate_canonical_id(value)

    @field_validator("entity_key")
    @classmethod
    def validate_entity_key(cls, value: str) -> str:
        parse_entity_key(value)
        return value

    @model_validator(mode="after")
    def validate_identity_consistency(self) -> "EntityIdentity":
        if self.entity_key != build_entity_key(self.asset_type, self.canonical_id):
            raise ValueError("entity_key does not match asset_type and canonical_id")
        return self
