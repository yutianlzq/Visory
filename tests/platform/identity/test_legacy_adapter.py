from __future__ import annotations

from src.schemas.platform import ResolutionStatus
from src.services.platform.legacy_asset_adapter import LegacyAssetResolverAdapter
from src.services.stock_list_parser import ParseStatus, parse_analysis_target


def test_legacy_adapter_preserves_existing_csi_read_only_seam() -> None:
    adapter = LegacyAssetResolverAdapter()
    for raw in ("csi930955", "930955.CSI"):
        legacy = parse_analysis_target(raw)
        adapted = adapter.resolve_analysis_target(raw)
        assert legacy.asset_type == ParseStatus.INDEX
        assert adapted.resolution_status is ResolutionStatus.RESOLVED
        assert adapted.entity_key == f"index:{legacy.canonical_id}"
        assert adapted.canonical_id == legacy.canonical_id

    unsupported = adapter.resolve_analysis_target("csi930956")
    assert unsupported.resolution_status is ResolutionStatus.UNSUPPORTED
    assert unsupported.entity_key is None
