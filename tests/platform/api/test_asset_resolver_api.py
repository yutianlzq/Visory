from __future__ import annotations

import json
import logging
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from api.platform.request_id import REQUEST_ID_HEADER
from src.core.platform.identity_resolver import AssetResolverService
from src.repositories.platform.errors import PlatformDatabaseError
from src.repositories.platform.identity import InMemoryAssetIdentityRepository
from src.schemas.platform import (
    AliasType,
    AliasVerificationStatus,
    AssetAlias,
    AssetIdentityRecord,
    AssetType,
    IdentityStatus,
)

sys.modules.setdefault("litellm", MagicMock())
from api.app import create_app


NOW = datetime(2026, 8, 27, 4, 0, tzinfo=timezone.utc)


def _service() -> AssetResolverService:
    identity = AssetIdentityRecord(
        entity_key="stock:sh600519", asset_type=AssetType.STOCK, canonical_id="sh600519",
        exchange="SH", market="CN", currency="CNY", country="CN", valid_from=date(2001, 8, 27),
        valid_to=None, list_date=date(2001, 8, 27), delist_date=None,
        identity_status=IdentityStatus.ACTIVE, schema_version="1.0.0", created_at=NOW,
    )
    alias = AssetAlias(
        alias_id="alias_api_1", entity_key=identity.entity_key, alias_type=AliasType.BARE_CODE,
        namespace="user:stock_route", alias_value="600519", normalized_value="600519",
        valid_from=date(2001, 8, 27), valid_to=None, available_at=NOW,
        source_provider="fixture", actual_upstream="fixture",
        verification_status=AliasVerificationStatus.VERIFIED, revision=1, created_at=NOW,
    )
    return AssetResolverService(InMemoryAssetIdentityRepository([identity], [alias]), clock=lambda: NOW)


def test_asset_resolution_endpoint_uses_c010_envelope(tmp_path: Path) -> None:
    app = create_app(static_dir=tmp_path / "missing-static")
    app.state.asset_resolver_service = _service()
    response = TestClient(app).post(
        "/api/platform/v1/asset-resolutions",
        json={
            "input_namespace": "user:stock_route",
            "input_value": "600519",
            "asset_type": "stock",
            "allow_inactive": False,
        },
        headers={REQUEST_ID_HEADER: "req_0123456789abcdef0123456789abcdef"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["data"] == {
        "asset_type": "stock",
        "canonical_id": "sh600519",
        "entity_key": "stock:sh600519",
        "resolution_status": "RESOLVED",
        "candidates": [],
        "reason_codes": [],
        "resolver_version": "1.0.0",
        "resolved_at": "2026-08-27T04:00:00Z",
    }
    assert body["meta"]["request_id"] == response.headers[REQUEST_ID_HEADER]
    assert body["meta"]["data_snapshot_id"] is None


def test_asset_resolution_database_failure_is_stable_retryable_and_sanitized(
    tmp_path: Path,
    caplog,
) -> None:
    class FailingService:
        def resolve(self, request):
            raise PlatformDatabaseError(
                error_code="DATABASE_UNAVAILABLE",
                public_message="PostgreSQL is temporarily unavailable.",
                retryable=True,
                details={"dependency": "postgresql", "operation": "query", "secret": "must-not-leak"},
                cause=RuntimeError("postgresql://user:super-secret@host/db"),
            )

    caplog.set_level(logging.INFO)
    app = create_app(static_dir=tmp_path / "missing-static")
    app.state.asset_resolver_service = FailingService()
    response = TestClient(app, raise_server_exceptions=False).post(
        "/api/platform/v1/asset-resolutions",
        json={"input_namespace": "user:stock_route", "input_value": "600519", "asset_type": "stock", "allow_inactive": False},
    )

    assert response.status_code == 503
    body = response.json()
    assert body["error"]["code"] == "PROVIDER_UNAVAILABLE"
    assert body["error"]["retryable"] is True
    serialized = json.dumps(body, ensure_ascii=False)
    for value in ("super-secret", "must-not-leak", "postgresql://"):
        assert value not in serialized
        assert value not in caplog.text
