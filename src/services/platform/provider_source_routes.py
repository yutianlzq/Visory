from __future__ import annotations

from collections.abc import Iterable

from src.schemas.platform.provider_source import (
    ProviderSourceEvidenceState,
    ProviderSourceExecutionState,
    ProviderSourceKind,
    ProviderSourceRouteEvidence,
    build_provider_source_route_evidence,
)


_A_STOCK_DATA_REPOSITORY = "https://github.com/simonlin1212/a-stock-data"
_A_STOCK_DATA_RELEASE = "3.10.2"
_A_STOCK_DATA_COMMIT = "29b07d2e37005b9fd568bca1262f6e572b5f9407"
_A_STOCK_DATA_SKILL_BLOB = "8e334569f7cfd334b56f3b3bd067469d175ba892"
_A_STOCK_DATA_LICENSE_BLOB = "088c0826ad3a02908696b1ff6c9e4fbd9b2823af"


class ProviderSourceRouteError(Exception):
    def __init__(self, error_code: str, public_message: str, *, reason_code: str | None = None) -> None:
        super().__init__(public_message)
        self.error_code = error_code
        self.public_message = public_message
        self.reason_code = reason_code


def _a_stock_data_route(
    dataset_id: str,
    *,
    entrypoint: str,
    actual_upstream: str,
    source_kind: ProviderSourceKind,
    reason_code: str,
    coverage: ProviderSourceEvidenceState = ProviderSourceEvidenceState.UNPROVEN,
    pit: ProviderSourceEvidenceState = ProviderSourceEvidenceState.UNPROVEN,
    pagination: ProviderSourceEvidenceState = ProviderSourceEvidenceState.UNPROVEN,
    revision: ProviderSourceEvidenceState = ProviderSourceEvidenceState.UNPROVEN,
) -> ProviderSourceRouteEvidence:
    return build_provider_source_route_evidence(
        source_route_id=f"a_stock_data_{dataset_id}_v1",
        provider_id="a_stock_data",
        dataset_id=dataset_id,
        adapter_name="a_stock_data",
        adapter_version="1.0.0",
        adapter_repository=_A_STOCK_DATA_REPOSITORY,
        adapter_release=_A_STOCK_DATA_RELEASE,
        adapter_commit=_A_STOCK_DATA_COMMIT,
        adapter_blob=_A_STOCK_DATA_SKILL_BLOB,
        adapter_entrypoint=entrypoint,
        actual_upstream=actual_upstream,
        source_kind=source_kind,
        market="CN",
        documented_history_start=None,
        coverage_evidence_state=coverage,
        pit_evidence_state=pit,
        pagination_evidence_state=pagination,
        revision_evidence_state=revision,
        execution_state=ProviderSourceExecutionState.BLOCKED,
        unavailable_reason_code=reason_code,
        license_id="Apache-2.0",
        license_blob=_A_STOCK_DATA_LICENSE_BLOB,
    )


def default_provider_source_routes() -> tuple[ProviderSourceRouteEvidence, ...]:
    """Pinned candidate routes; every unproven route remains non-executable."""

    return (
        _a_stock_data_route(
            "security_master",
            entrypoint="baostock_stock_basic",
            actual_upstream="https://www.baostock.com",
            source_kind=ProviderSourceKind.SDK,
            reason_code="SOURCE_UNIVERSE_COVERAGE_UNPROVEN",
            pagination=ProviderSourceEvidenceState.NOT_APPLICABLE,
            revision=ProviderSourceEvidenceState.NOT_APPLICABLE,
        ),
        _a_stock_data_route(
            "trading_calendar",
            entrypoint="trading_calendar",
            actual_upstream="https://www.szse.cn",
            source_kind=ProviderSourceKind.HTTP,
            reason_code="SOURCE_HISTORY_COVERAGE_UNPROVEN",
            pagination=ProviderSourceEvidenceState.NOT_APPLICABLE,
            revision=ProviderSourceEvidenceState.NOT_APPLICABLE,
        ),
        _a_stock_data_route(
            "bar_1d_raw",
            entrypoint="tdx_daily_package",
            actual_upstream="https://www.tdx.com.cn",
            source_kind=ProviderSourceKind.FILE,
            reason_code="SOURCE_BAR_REQUIRED_FIELDS_UNPROVEN",
            pagination=ProviderSourceEvidenceState.NOT_APPLICABLE,
            revision=ProviderSourceEvidenceState.NOT_APPLICABLE,
        ),
        _a_stock_data_route(
            "instrument_status_daily",
            entrypoint="baostock_valuation_history",
            actual_upstream="https://www.baostock.com",
            source_kind=ProviderSourceKind.SDK,
            reason_code="SOURCE_BJ_COVERAGE_UNAVAILABLE",
            pagination=ProviderSourceEvidenceState.NOT_APPLICABLE,
            revision=ProviderSourceEvidenceState.NOT_APPLICABLE,
        ),
        _a_stock_data_route(
            "listing_status_history",
            entrypoint="baostock_stock_basic",
            actual_upstream="https://www.baostock.com",
            source_kind=ProviderSourceKind.SDK,
            reason_code="SOURCE_HISTORICAL_IDENTITY_UNPROVEN",
            pagination=ProviderSourceEvidenceState.NOT_APPLICABLE,
            revision=ProviderSourceEvidenceState.NOT_APPLICABLE,
        ),
        _a_stock_data_route(
            "corporate_action",
            entrypoint="dividend_history",
            actual_upstream="https://www.eastmoney.com",
            source_kind=ProviderSourceKind.HTTP,
            reason_code="SOURCE_REVISION_PIT_UNPROVEN",
        ),
        _a_stock_data_route(
            "financial_statement",
            entrypoint="sina_financial_report",
            actual_upstream="https://finance.sina.com.cn",
            source_kind=ProviderSourceKind.HTTP,
            reason_code="SOURCE_REVISION_PIT_UNPROVEN",
            pagination=ProviderSourceEvidenceState.NOT_APPLICABLE,
        ),
        _a_stock_data_route(
            "benchmark_index_1d",
            entrypoint="tencent_kline",
            actual_upstream="https://web.ifzq.gtimg.cn",
            source_kind=ProviderSourceKind.HTTP,
            reason_code="SOURCE_TOTAL_RETURN_PIT_UNPROVEN",
            pagination=ProviderSourceEvidenceState.NOT_APPLICABLE,
            revision=ProviderSourceEvidenceState.NOT_APPLICABLE,
        ),
    )


def build_fixture_provider_source_route(
    *,
    provider_id: str,
    dataset_id: str,
    adapter_name: str,
    adapter_version: str,
    actual_upstream: str,
) -> ProviderSourceRouteEvidence:
    return build_provider_source_route_evidence(
        source_route_id=f"fixture_{provider_id}_{dataset_id}",
        provider_id=provider_id,
        dataset_id=dataset_id,
        adapter_name=adapter_name,
        adapter_version=adapter_version,
        adapter_repository="https://fixtures.invalid/provider-source",
        adapter_release="0.0.0",
        adapter_commit="0" * 40,
        adapter_blob="0" * 40,
        adapter_entrypoint="fixture_response",
        actual_upstream=actual_upstream,
        source_kind=ProviderSourceKind.FIXTURE,
        market="CN",
        documented_history_start=None,
        coverage_evidence_state=ProviderSourceEvidenceState.PROVEN,
        pit_evidence_state=ProviderSourceEvidenceState.PROVEN,
        pagination_evidence_state=ProviderSourceEvidenceState.NOT_APPLICABLE,
        revision_evidence_state=ProviderSourceEvidenceState.NOT_APPLICABLE,
        execution_state=ProviderSourceExecutionState.FIXTURE_ONLY,
        unavailable_reason_code="FIXTURE_ONLY_SOURCE",
        license_id="TEST-ONLY",
        license_blob="0" * 40,
    )


class ProviderSourceRouteRegistry:
    def __init__(
        self,
        routes: Iterable[ProviderSourceRouteEvidence] | None = None,
        *,
        allow_fixture_only: bool = False,
    ) -> None:
        records = tuple(routes if routes is not None else default_provider_source_routes())
        self._routes: dict[tuple[str, str, str, str], ProviderSourceRouteEvidence] = {}
        for route in records:
            key = (route.provider_id, route.dataset_id, route.adapter_name, route.adapter_version)
            if key in self._routes:
                raise ValueError("provider source routes must be unique")
            self._routes[key] = route
        self.allow_fixture_only = allow_fixture_only

    def get(
        self,
        *,
        provider_id: str,
        dataset_id: str,
        adapter_name: str,
        adapter_version: str,
    ) -> ProviderSourceRouteEvidence | None:
        return self._routes.get((provider_id, dataset_id, adapter_name, adapter_version))

    def require_executable(
        self,
        *,
        provider_id: str,
        dataset_id: str,
        adapter_name: str,
        adapter_version: str,
    ) -> ProviderSourceRouteEvidence:
        route = self.get(
            provider_id=provider_id,
            dataset_id=dataset_id,
            adapter_name=adapter_name,
            adapter_version=adapter_version,
        )
        if route is None:
            raise ProviderSourceRouteError(
                "RAW_SOURCE_ROUTE_UNAVAILABLE",
                "Provider source route is unavailable.",
                reason_code="SOURCE_ROUTE_NOT_REGISTERED",
            )
        if route.execution_state is ProviderSourceExecutionState.AVAILABLE:
            return route
        if route.execution_state is ProviderSourceExecutionState.FIXTURE_ONLY:
            if self.allow_fixture_only:
                return route
            raise ProviderSourceRouteError(
                "RAW_SOURCE_ROUTE_FIXTURE_ONLY",
                "Fixture provider source route is not executable in this runtime.",
                reason_code=route.unavailable_reason_code,
            )
        error_code = (
            "RAW_SOURCE_ROUTE_BLOCKED"
            if route.execution_state is ProviderSourceExecutionState.BLOCKED
            else "RAW_SOURCE_ROUTE_UNAVAILABLE"
        )
        raise ProviderSourceRouteError(
            error_code,
            "Provider source route is not execution-ready.",
            reason_code=route.unavailable_reason_code,
        )


__all__ = [
    "ProviderSourceRouteError",
    "ProviderSourceRouteRegistry",
    "build_fixture_provider_source_route",
    "default_provider_source_routes",
]
