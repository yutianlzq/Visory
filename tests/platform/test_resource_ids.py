from __future__ import annotations

from uuid import UUID

import pytest
from pydantic import ValidationError

from src.schemas.platform import (
    ResourceRef,
    ResourceType,
    generate_resource_id,
    generate_uuid7,
    parse_resource_id,
)


def test_uuid7_generator_is_canonical_and_time_ordered() -> None:
    first = generate_uuid7(timestamp_ms=1_700_000_000_000, random_bits=0)
    second = generate_uuid7(timestamp_ms=1_700_000_000_001, random_bits=0)

    assert isinstance(first, UUID)
    assert first.version == 7
    assert str(first) == "018bcfe5-6800-7000-8000-000000000000"
    assert str(first) == str(first).lower()
    assert first.int < second.int


def test_resource_id_round_trip() -> None:
    resource_id = generate_resource_id(
        ResourceType.FEATURE_SNAPSHOT,
        timestamp_ms=1_700_000_000_000,
        random_bits=123,
    )
    resource_type, resource_uuid = parse_resource_id(resource_id)

    assert resource_type is ResourceType.FEATURE_SNAPSHOT
    assert resource_uuid.version == 7
    assert resource_id.startswith("fs_")


def test_resource_ref_rejects_type_prefix_mismatch() -> None:
    with pytest.raises(ValidationError):
        ResourceRef(
            resource_type=ResourceType.DATA_SNAPSHOT,
            resource_id="fs_019c5f2a-8c34-75cd-a013-4b4ee2b25a48",
        )


@pytest.mark.parametrize(
    "resource_id",
    [
        "fs_550e8400-e29b-41d4-a716-446655440000",
        "unknown_019c5f2a-8c34-75cd-a013-4b4ee2b25a48",
        "FS_019C5F2A-8C34-75CD-A013-4B4EE2B25A48",
        "fs_019c5f2a8c3475cda0134b4ee2b25a48",
    ],
)
def test_resource_id_rejects_invalid_format(resource_id: str) -> None:
    with pytest.raises(ValueError):
        parse_resource_id(resource_id)
