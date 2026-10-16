from __future__ import annotations

from pydantic import ValidationError
import pytest

from src.schemas.platform import (
    ProviderSourceEvidenceState,
    ProviderSourceExecutionState,
    ProviderSourceKind,
)
from src.services.platform.provider_source_routes import (
    ProviderSourceRouteError,
    ProviderSourceRouteRegistry,
    build_fixture_provider_source_route,
    default_provider_source_routes,
)


def test_a_stock_data_routes_pin_adapter_source_and_remain_fail_closed() -> None:
    routes = {
        route.dataset_id: route
        for route in default_provider_source_routes()
        if route.provider_id == "a_stock_data"
    }

    assert set(routes) == {
        "security_master",
        "trading_calendar",
        "bar_1d_raw",
        "instrument_status_daily",
        "listing_status_history",
        "corporate_action",
        "financial_statement",
        "benchmark_index_1d",
    }
    assert {route.adapter_repository for route in routes.values()} == {
        "https://github.com/simonlin1212/a-stock-data"
    }
    assert {route.adapter_commit for route in routes.values()} == {
        "29b07d2e37005b9fd568bca1262f6e572b5f9407"
    }
    assert {route.adapter_blob for route in routes.values()} == {
        "8e334569f7cfd334b56f3b3bd067469d175ba892"
    }
    assert {route.adapter_release for route in routes.values()} == {"3.10.2"}
    assert {route.license_id for route in routes.values()} == {"Apache-2.0"}
    assert {route.license_blob for route in routes.values()} == {
        "088c0826ad3a02908696b1ff6c9e4fbd9b2823af"
    }
    assert all(route.execution_state is ProviderSourceExecutionState.BLOCKED for route in routes.values())
    assert all(route.source_route_hash.startswith("sha256:") for route in routes.values())

    assert routes["security_master"].adapter_entrypoint == "baostock_stock_basic"
    assert routes["trading_calendar"].adapter_entrypoint == "trading_calendar"
    assert routes["bar_1d_raw"].adapter_entrypoint == "tdx_daily_package"
    assert routes["corporate_action"].revision_evidence_state is ProviderSourceEvidenceState.UNPROVEN
    assert routes["financial_statement"].pit_evidence_state is ProviderSourceEvidenceState.UNPROVEN


def test_source_route_hash_rejects_tampering() -> None:
    route = default_provider_source_routes()[0]
    tampered = route.model_copy(update={"actual_upstream": "https://tampered.example"})

    with pytest.raises(ValidationError, match="source_route_hash"):
        route.model_validate(tampered.model_dump(mode="python"))


def test_fixture_route_is_not_executable_without_explicit_test_opt_in() -> None:
    route = build_fixture_provider_source_route(
        provider_id="a_stock_data",
        dataset_id="security_master",
        adapter_name="a_stock_data",
        adapter_version="1.0.0",
        actual_upstream="fixture.a_stock_data",
    )
    assert route.source_kind is ProviderSourceKind.FIXTURE
    assert route.execution_state is ProviderSourceExecutionState.FIXTURE_ONLY

    registry = ProviderSourceRouteRegistry((route,))
    with pytest.raises(ProviderSourceRouteError) as captured:
        registry.require_executable(
            provider_id="a_stock_data",
            dataset_id="security_master",
            adapter_name="a_stock_data",
            adapter_version="1.0.0",
        )
    assert captured.value.error_code == "RAW_SOURCE_ROUTE_FIXTURE_ONLY"

    fixture_registry = ProviderSourceRouteRegistry((route,), allow_fixture_only=True)
    assert fixture_registry.require_executable(
        provider_id="a_stock_data",
        dataset_id="security_master",
        adapter_name="a_stock_data",
        adapter_version="1.0.0",
    ) == route
