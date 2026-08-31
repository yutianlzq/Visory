from __future__ import annotations

import re
import secrets
import time
from uuid import UUID

from pydantic import field_validator, model_validator

from .base import PlatformContractModel
from .enums import ResourceType


_RESOURCE_PREFIXES: dict[ResourceType, str] = {
    ResourceType.TASK: "task",
    ResourceType.ATTEMPT: "attempt",
    ResourceType.DATA_SNAPSHOT: "ds",
    ResourceType.FEATURE_SNAPSHOT: "fs",
    ResourceType.OBSERVATION_SNAPSHOT: "obs",
    ResourceType.FACT_PACK: "fact",
    ResourceType.RESEARCH: "research",
    ResourceType.REVIEW: "review",
    ResourceType.STRATEGY: "strategy",
    ResourceType.BACKTEST_RUN: "backtest",
    ResourceType.PREDICTION: "prediction",
    ResourceType.ARTIFACT: "artifact",
    ResourceType.REPORT: "report",
    ResourceType.PROVIDER_RUN: "prun",
    ResourceType.SECTOR: "sector",
    ResourceType.TAXONOMY: "taxonomy",
    ResourceType.INDICATOR: "indicator",
    ResourceType.RAW_OBJECT: "raw",
    ResourceType.CANONICAL_PARTITION: "cpart",
    ResourceType.FEATURE_PARTITION: "fpart",
    ResourceType.FACT_BLOCK: "fblock",
    ResourceType.CLAIM: "claim",
    ResourceType.WATCH_CONDITION: "watch",
    ResourceType.QUALITY_REPORT: "quality",
    ResourceType.REQUEST: "request",
    ResourceType.CHECKPOINT: "checkpoint",
    ResourceType.BACKUP: "backup",
    ResourceType.DEPLOYMENT: "deployment",
    ResourceType.RAW_INGESTION_QUARANTINE: "rawq",
}
_PREFIX_TYPES = {prefix: resource_type for resource_type, prefix in _RESOURCE_PREFIXES.items()}
_RESOURCE_ID_PATTERN = re.compile(r"^([a-z][a-z0-9]*)_([0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12})$")


def generate_uuid7(*, timestamp_ms: int | None = None, random_bits: int | None = None) -> UUID:
    if timestamp_ms is None:
        timestamp_ms = time.time_ns() // 1_000_000
    if not isinstance(timestamp_ms, int) or not 0 <= timestamp_ms < (1 << 48):
        raise ValueError("timestamp_ms must fit in 48 unsigned bits")
    if random_bits is None:
        random_bits = secrets.randbits(74)
    if not isinstance(random_bits, int) or not 0 <= random_bits < (1 << 74):
        raise ValueError("random_bits must fit in 74 unsigned bits")

    random_high = random_bits >> 62
    random_low = random_bits & ((1 << 62) - 1)
    value = (
        (timestamp_ms << 80)
        | (0x7 << 76)
        | (random_high << 64)
        | (0b10 << 62)
        | random_low
    )
    return UUID(int=value)


def generate_resource_id(
    resource_type: ResourceType,
    *,
    timestamp_ms: int | None = None,
    random_bits: int | None = None,
) -> str:
    if not isinstance(resource_type, ResourceType):
        try:
            resource_type = ResourceType(resource_type)
        except (TypeError, ValueError) as exc:
            raise ValueError("resource_type must be registered") from exc
    return f"{_RESOURCE_PREFIXES[resource_type]}_{generate_uuid7(timestamp_ms=timestamp_ms, random_bits=random_bits)}"


def parse_resource_id(resource_id: str) -> tuple[ResourceType, UUID]:
    if not isinstance(resource_id, str):
        raise TypeError("resource_id must be a string")
    match = _RESOURCE_ID_PATTERN.fullmatch(resource_id)
    if match is None:
        raise ValueError("resource_id must be canonical <registered_prefix>_<uuidv7>")
    prefix, uuid_text = match.groups()
    resource_type = _PREFIX_TYPES.get(prefix)
    if resource_type is None:
        raise ValueError("resource_id prefix must be registered")
    resource_uuid = UUID(uuid_text)
    if resource_uuid.version != 7 or str(resource_uuid) != uuid_text:
        raise ValueError("resource_id must contain a canonical UUIDv7")
    return resource_type, resource_uuid


class ResourceRef(PlatformContractModel):
    resource_type: ResourceType
    resource_id: str

    @field_validator("resource_id")
    @classmethod
    def validate_resource_id(cls, value: str) -> str:
        parse_resource_id(value)
        return value

    @model_validator(mode="after")
    def validate_type_matches_prefix(self) -> "ResourceRef":
        parsed_type, _ = parse_resource_id(self.resource_id)
        if parsed_type is not self.resource_type:
            raise ValueError("resource_type does not match resource_id prefix")
        return self
