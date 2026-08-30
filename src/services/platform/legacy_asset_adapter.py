from __future__ import annotations

from datetime import datetime, timezone

from src.core.platform.identity_resolver import RESOLVER_VERSION
from src.schemas.platform import AssetResolutionResult, AssetType, ResolutionStatus, build_entity_key


class LegacyAssetResolverAdapter:
    """Read-only bridge from the Legacy parser to the C-002 result contract."""

    def resolve_analysis_target(self, raw_input: str) -> AssetResolutionResult:
        from src.services.stock_list_parser import ParseStatus, parse_analysis_target

        target = parse_analysis_target(raw_input)
        if target.asset_type in {ParseStatus.STOCK, ParseStatus.INDEX} and target.canonical_id:
            asset_type = AssetType(target.asset_type)
            return AssetResolutionResult(
                asset_type=asset_type,
                canonical_id=target.canonical_id,
                entity_key=build_entity_key(asset_type, target.canonical_id),
                resolution_status=ResolutionStatus.RESOLVED,
                candidates=(),
                reason_codes=("LEGACY_ADAPTER",),
                resolver_version=RESOLVER_VERSION,
                resolved_at=datetime.now(timezone.utc),
            )
        return AssetResolutionResult(
            asset_type=None,
            canonical_id=None,
            entity_key=None,
            resolution_status=ResolutionStatus.UNSUPPORTED,
            candidates=(),
            reason_codes=("LEGACY_UNSUPPORTED",),
            resolver_version=RESOLVER_VERSION,
            resolved_at=datetime.now(timezone.utc),
        )
