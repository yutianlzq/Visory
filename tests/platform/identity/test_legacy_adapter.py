from __future__ import annotations

from src.services.platform.legacy_asset_adapter import LegacyAssetResolverAdapter
from src.services.stock_list_parser import ParseStatus, parse_analysis_target


def test_legacy_adapter_preserves_existing_parser_output_for_read_only_seam() -> None:
    adapter = LegacyAssetResolverAdapter()
    for raw in ("sh600519", "600519", "sh000300", "csi930955", "930955.CSI", "not-a-symbol"):
        legacy = parse_analysis_target(raw)
        adapted = adapter.resolve_analysis_target(raw)
        expected_entity_key = (
            f"{legacy.asset_type}:{legacy.canonical_id}"
            if legacy.asset_type in {ParseStatus.STOCK, ParseStatus.INDEX} and legacy.canonical_id
            else None
        )
        assert adapted.entity_key == expected_entity_key
        assert adapted.canonical_id == (legacy.canonical_id or None)
