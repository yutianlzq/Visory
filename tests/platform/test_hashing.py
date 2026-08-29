from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.schemas.platform import ContentHashValue, HashProfile, canonical_json_bytes, compute_content_hash


def test_hash_is_deterministic_across_mapping_order_and_timezone_offsets() -> None:
    first = {
        "price": Decimal("123.4500"),
        "observed_at": datetime(2026, 8, 27, 8, 0, tzinfo=timezone.utc),
        "items": ["a", "b"],
    }
    second = {
        "items": ["a", "b"],
        "observed_at": datetime.fromisoformat("2026-08-27T16:00:00+08:00"),
        "price": Decimal("123.4500"),
    }

    assert canonical_json_bytes(first) == canonical_json_bytes(second)
    assert compute_content_hash(first) == compute_content_hash(second)


def test_decimal_precision_is_not_lost_to_float() -> None:
    assert compute_content_hash({"value": Decimal("1.0")}) != compute_content_hash(
        {"value": Decimal("1.00")}
    )
    with pytest.raises(TypeError):
        compute_content_hash({"value": 1.0})


def test_arrays_preserve_order_unless_profile_declares_unordered_semantics() -> None:
    ordered_a = compute_content_hash({"tags": ["a", "b"]})
    ordered_b = compute_content_hash({"tags": ["b", "a"]})
    assert ordered_a != ordered_b

    profile = HashProfile(
        profile_id="test_unordered_tags_1.0.0",
        unordered_array_paths=frozenset({"tags"}),
    )
    assert compute_content_hash({"tags": ["a", "b"]}, profile) == compute_content_hash(
        {"tags": ["b", "a"]}, profile
    )


def test_content_hash_field_is_excluded_by_default() -> None:
    payload = {"value": "stable"}
    digest = compute_content_hash(payload)
    assert compute_content_hash({**payload, "content_hash": digest}) == digest


def test_content_hash_schema_rejects_invalid_value() -> None:
    with pytest.raises(ValidationError):
        ContentHashValue(content_hash="SHA256:ABC")
