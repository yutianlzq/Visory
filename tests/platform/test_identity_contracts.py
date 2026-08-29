from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.schemas.platform import AssetType, EntityIdentity, build_entity_key, parse_entity_key


def test_build_and_parse_entity_key() -> None:
    assert build_entity_key(AssetType.STOCK, "sh600519") == "stock:sh600519"
    assert parse_entity_key("stock:sh600519") == (AssetType.STOCK, "sh600519")


@pytest.mark.parametrize("canonical_id", ["SH600519", "600519", " sh600519", "sh:600519", ""])
def test_canonical_id_must_be_normalized(canonical_id: str) -> None:
    with pytest.raises((TypeError, ValueError)):
        build_entity_key(AssetType.STOCK, canonical_id)


def test_entity_identity_rejects_mismatched_entity_key() -> None:
    with pytest.raises(ValidationError):
        EntityIdentity(
            asset_type=AssetType.STOCK,
            canonical_id="sh600519",
            entity_key="stock:sz000001",
        )


def test_entity_identity_forbids_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        EntityIdentity(
            asset_type=AssetType.STOCK,
            canonical_id="sh600519",
            entity_key="stock:sh600519",
            provider="example",
        )
