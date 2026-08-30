from __future__ import annotations

from datetime import date, datetime, timezone

from src.core.platform.identity_resolver import AssetResolverService
from src.repositories.platform.identity import InMemoryAssetIdentityRepository
from src.schemas.platform import (
    AliasType,
    AliasVerificationStatus,
    AssetAlias,
    AssetIdentityRecord,
    AssetResolutionRequest,
    AssetType,
    IdentityStatus,
    ResolutionStatus,
)


NOW = datetime(2026, 8, 27, 4, 0, tzinfo=timezone.utc)


def _identity(canonical_id: str, *, asset_type: AssetType = AssetType.STOCK, status: IdentityStatus = IdentityStatus.ACTIVE):
    exchange = "SH" if canonical_id.startswith("sh") else "SZ"
    return AssetIdentityRecord(
        entity_key=f"{asset_type.value}:{canonical_id}", asset_type=asset_type, canonical_id=canonical_id,
        exchange=exchange, market="CN", currency="CNY", country="CN", valid_from=date(1990, 1, 1),
        valid_to=None, list_date=None, delist_date=None, identity_status=status, schema_version="1.0.0",
        created_at=NOW,
    )


def _alias(alias_id: str, entity_key: str, alias_type: AliasType, namespace: str, value: str, *, verification: AliasVerificationStatus = AliasVerificationStatus.VERIFIED):
    return AssetAlias(
        alias_id=alias_id, entity_key=entity_key, alias_type=alias_type, namespace=namespace,
        alias_value=value, normalized_value=value.casefold(), valid_from=date(1990, 1, 1), valid_to=None,
        available_at=NOW, source_provider="fixture", actual_upstream="fixture",
        verification_status=verification, revision=1, created_at=NOW,
    )


def _service() -> AssetResolverService:
    identities = [
        _identity("sh600519"), _identity("sz000001"), _identity("sz300750"), _identity("sh688981"),
        _identity("sh600000", status=IdentityStatus.DELISTED),
        _identity("sh000300", asset_type=AssetType.INDEX),
    ]
    aliases = [
        _alias("alias_1", "stock:sh600519", AliasType.BARE_CODE, "user:stock_route", "600519"),
        _alias("alias_2", "stock:sh600519", AliasType.BARE_CODE, "user:general_search", "600519", verification=AliasVerificationStatus.CANDIDATE),
        _alias("alias_3", "stock:sz000001", AliasType.BARE_CODE, "user:stock_route", "000001"),
        _alias("alias_4", "stock:sz300750", AliasType.BARE_CODE, "user:stock_route", "300750"),
        _alias("alias_5", "stock:sh688981", AliasType.BARE_CODE, "user:stock_route", "688981"),
        _alias("alias_6", "index:sh000300", AliasType.BARE_CODE, "user:general_search", "600519", verification=AliasVerificationStatus.CANDIDATE),
        _alias("alias_7", "stock:sh600519", AliasType.PROVIDER_SYMBOL, "financial_api:cn_stock", "600519.SH"),
        _alias("alias_8", "stock:sh600519", AliasType.HISTORICAL_NAME, "user:general_search", "贵州茅台股份", verification=AliasVerificationStatus.CANDIDATE),
        _alias("alias_9", "stock:sh600000", AliasType.BARE_CODE, "user:stock_route", "600000"),
        _alias("alias_10", "stock:sh600519", AliasType.CURRENT_NAME, "user:general_search", "贵州茅台", verification=AliasVerificationStatus.CANDIDATE),
        _alias("alias_11", "stock:sh600519", AliasType.CURRENT_NAME, "user:general_search", "ST茅台", verification=AliasVerificationStatus.CANDIDATE),
    ]
    return AssetResolverService(InMemoryAssetIdentityRepository(identities, aliases), clock=lambda: NOW)


def test_stock_route_resolves_bare_codes_across_required_boards() -> None:
    service = _service()
    expected = {"600519": "stock:sh600519", "000001": "stock:sz000001", "300750": "stock:sz300750", "688981": "stock:sh688981"}
    for value, entity_key in expected.items():
        result = service.resolve(AssetResolutionRequest(input_namespace="user:stock_route", input_value=value, asset_type=AssetType.STOCK, allow_inactive=False))
        assert result.resolution_status is ResolutionStatus.RESOLVED
        assert result.entity_key == entity_key


def test_general_search_does_not_guess_between_stock_and_index() -> None:
    result = _service().resolve(AssetResolutionRequest(input_namespace="user:general_search", input_value="600519", asset_type=None, allow_inactive=True))
    assert result.resolution_status is ResolutionStatus.AMBIGUOUS
    assert {candidate.entity_key for candidate in result.candidates} == {"stock:sh600519", "index:sh000300"}
    assert "MULTIPLE_CANDIDATES" in result.reason_codes


def test_provider_namespace_isolation_and_historical_name_candidate_only() -> None:
    service = _service()
    provider = service.resolve(AssetResolutionRequest(input_namespace="financial_api:cn_stock", input_value="600519.SH", asset_type=AssetType.STOCK, allow_inactive=False))
    wrong_namespace = service.resolve(AssetResolutionRequest(input_namespace="another_provider:cn_stock", input_value="600519.SH", asset_type=AssetType.STOCK, allow_inactive=False))
    wrong_canonical_namespace = service.resolve(AssetResolutionRequest(input_namespace="another_provider:cn_stock", input_value="sh600519", asset_type=AssetType.STOCK, allow_inactive=False))
    historical = service.resolve(AssetResolutionRequest(input_namespace="user:general_search", input_value="贵州茅台股份", asset_type=None, allow_inactive=True))
    assert provider.resolution_status is ResolutionStatus.RESOLVED
    assert wrong_namespace.resolution_status is ResolutionStatus.NOT_FOUND
    assert wrong_canonical_namespace.resolution_status is ResolutionStatus.NOT_FOUND
    assert historical.resolution_status is ResolutionStatus.AMBIGUOUS
    assert historical.entity_key is None
    assert historical.reason_codes == ("CANDIDATE_ALIAS_REQUIRES_CONFIRMATION",)


def test_inactive_identity_is_not_resolved_for_new_intent() -> None:
    result = _service().resolve(AssetResolutionRequest(input_namespace="user:stock_route", input_value="600000", asset_type=AssetType.STOCK, allow_inactive=False))
    assert result.resolution_status is ResolutionStatus.INACTIVE
    assert result.entity_key == "stock:sh600000"
    assert "INACTIVE_ASSET" in result.reason_codes


def test_current_name_and_st_name_remain_candidates_for_the_same_identity() -> None:
    service = _service()
    for value in ("贵州茅台", "ST茅台"):
        result = service.resolve(
            AssetResolutionRequest(
                input_namespace="user:general_search",
                input_value=value,
                asset_type=None,
                allow_inactive=True,
            )
        )
        assert result.resolution_status is ResolutionStatus.AMBIGUOUS
        assert result.entity_key is None
        assert [candidate.entity_key for candidate in result.candidates] == ["stock:sh600519"]
        assert result.reason_codes == ("CANDIDATE_ALIAS_REQUIRES_CONFIRMATION",)


def test_open_quarantine_blocks_resolution_without_guessing() -> None:
    identity = _identity("sh600519")
    alias = _alias(
        "alias_conflict_1",
        identity.entity_key,
        AliasType.PROVIDER_SYMBOL,
        "financial_api:cn_stock",
        "600519.SH",
    )
    repository = InMemoryAssetIdentityRepository(
        [identity],
        [alias],
        conflicts={(alias.namespace, alias.normalized_value)},
    )
    result = AssetResolverService(repository, clock=lambda: NOW).resolve(
        AssetResolutionRequest(
            input_namespace=alias.namespace,
            input_value=alias.alias_value,
            asset_type=AssetType.STOCK,
            allow_inactive=False,
        )
    )

    assert result.resolution_status is ResolutionStatus.CONFLICT
    assert result.entity_key is None
    assert [candidate.entity_key for candidate in result.candidates] == [identity.entity_key]
    assert result.reason_codes == ("IDENTITY_QUARANTINE_OPEN",)


def test_alias_validity_uses_asia_shanghai_calendar_date() -> None:
    identity = _identity("sh600519")
    alias = _alias(
        "alias_timezone_1",
        identity.entity_key,
        AliasType.BARE_CODE,
        "user:stock_route",
        "600519",
    ).model_copy(update={"valid_from": date(2026, 8, 28)})
    clock_time = datetime(2026, 8, 27, 16, 30, tzinfo=timezone.utc)
    result = AssetResolverService(
        InMemoryAssetIdentityRepository([identity], [alias]),
        clock=lambda: clock_time,
    ).resolve(
        AssetResolutionRequest(
            input_namespace="user:stock_route",
            input_value="600519",
            asset_type=AssetType.STOCK,
            allow_inactive=False,
        )
    )

    assert result.resolution_status is ResolutionStatus.RESOLVED
    assert result.entity_key == identity.entity_key
