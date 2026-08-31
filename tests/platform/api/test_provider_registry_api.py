from __future__ import annotations

from datetime import datetime, timezone
import re

from fastapi import FastAPI
from starlette.testclient import TestClient

from api.platform.router import router
from src.services.platform.provider_registry import default_registry_records
from src.schemas.platform import ProviderSettingsProjection, ProviderSettingsProvider
from api.platform.request_id import REQUEST_ID_PATTERN


class _ProjectionService:
    def settings_projection(self):
        providers, datasets, capabilities, policies = default_registry_records(datetime(2026, 8, 31, tzinfo=timezone.utc))
        return ProviderSettingsProjection(
            providers=tuple(ProviderSettingsProvider(
                provider_id=item.provider_id, display_name=item.display_name, adapter_name=item.adapter_name,
                adapter_version=item.adapter_version, provider_kind=item.provider_kind, enabled=item.enabled,
                credential_configured=item.credential_ref is not None, actual_upstream=item.actual_upstream,
            ) for item in providers),
            datasets=datasets, capabilities=capabilities, policies=policies,
        )


def test_provider_registry_read_only_projection_is_c010_enveloped():
    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.state.provider_registry_service = _ProjectionService()
    with TestClient(app) as client:
        response = client.get("/api/platform/v1/provider-registry", headers={"X-Request-ID": "req_0123456789abcdef0123456789abcdef"})
    assert response.status_code == 200
    payload = response.json()
    assert re.fullmatch(REQUEST_ID_PATTERN, payload["meta"]["request_id"])
    assert [item["provider_id"] for item in payload["data"]["providers"]] == ["a_stock_data", "financial_api"]
    assert "runtime_root" not in response.text
    assert "credential_ref" not in response.text
    assert payload["data"]["providers"][1]["credential_configured"] is True
