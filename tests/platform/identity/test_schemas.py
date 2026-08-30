from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from src.schemas.platform import (
    AliasType,
    AliasVerificationStatus,
    AssetAlias,
    AssetIdentityRecord,
    AssetResolutionRequest,
    AssetResolutionResult,
    AssetType,
    IdentityStatus,
    ResolutionStatus,
)


NOW = datetime(2026, 8, 27, 12, 0, tzinfo=timezone(timedelta(hours=8)))


def test_asset_identity_record_enforces_entity_key_and_lifecycle() -> None:
    record = AssetIdentityRecord(
        entity_key="stock:sh600519",
        asset_type=AssetType.STOCK,
        canonical_id="sh600519",
        exchange="SH",
        market="CN",
        currency="CNY",
        country="CN",
        valid_from=date(2001, 8, 27),
        valid_to=None,
        list_date=date(2001, 8, 27),
        delist_date=None,
        identity_status=IdentityStatus.ACTIVE,
        schema_version="1.0.0",
        created_at=NOW,
    )

    assert record.entity_key == "stock:sh600519"
    assert record.created_at.tzinfo is not None

    with pytest.raises(ValidationError):
        AssetIdentityRecord.model_validate({**record.model_dump(), "entity_key": "stock:sz000001"})
    with pytest.raises(ValidationError):
        AssetIdentityRecord.model_validate({**record.model_dump(), "valid_to": date(2001, 8, 27)})


def test_asset_alias_enforces_namespace_time_and_revision() -> None:
    alias = AssetAlias(
        alias_id="alias_00000001",
        entity_key="stock:sh600519",
        alias_type=AliasType.PROVIDER_SYMBOL,
        namespace="financial_api:cn_stock",
        alias_value="600519.SH",
        normalized_value="600519.sh",
        valid_from=date(2001, 8, 27),
        valid_to=None,
        available_at=NOW,
        source_provider="financial_api",
        actual_upstream="eastmoney",
        verification_status=AliasVerificationStatus.VERIFIED,
        revision=1,
        created_at=NOW,
    )

    assert alias.namespace == "financial_api:cn_stock"
    with pytest.raises(ValidationError):
        AssetAlias.model_validate({**alias.model_dump(), "namespace": "financial_api"})
    with pytest.raises(ValidationError):
        AssetAlias.model_validate({**alias.model_dump(), "revision": 0})
    with pytest.raises(ValidationError):
        AssetAlias.model_validate({**alias.model_dump(), "available_at": NOW.replace(tzinfo=None)})


def test_resolution_schema_uses_only_contract_statuses_and_required_fields() -> None:
    request = AssetResolutionRequest(
        input_namespace="user:stock_route",
        input_value="600519",
        asset_type=AssetType.STOCK,
        allow_inactive=False,
    )
    result = AssetResolutionResult(
        asset_type=AssetType.STOCK,
        canonical_id="sh600519",
        entity_key="stock:sh600519",
        resolution_status=ResolutionStatus.RESOLVED,
        candidates=(),
        reason_codes=(),
        resolver_version="1.0.0",
        resolved_at=NOW,
    )

    assert request.input_value == "600519"
    general_request = AssetResolutionRequest(
        input_namespace="user:general_search",
        input_value="贵州茅台",
    )
    assert general_request.asset_type is None
    assert general_request.allow_inactive is False
    assert set(ResolutionStatus) == {
        ResolutionStatus.RESOLVED,
        ResolutionStatus.AMBIGUOUS,
        ResolutionStatus.NOT_FOUND,
        ResolutionStatus.UNSUPPORTED,
        ResolutionStatus.CONFLICT,
        ResolutionStatus.INACTIVE,
    }
    assert result.entity_key == "stock:sh600519"
    with pytest.raises(ValidationError):
        AssetResolutionResult.model_validate(
            {**result.model_dump(), "canonical_id": None, "entity_key": "stock:sh600519"}
        )
