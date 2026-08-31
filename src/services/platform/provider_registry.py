from __future__ import annotations

from datetime import datetime, timezone

from src.repositories.platform import PostgresDatabase, ProviderRegistryRepository
from src.schemas.platform import (
    DatasetDefinition, ProviderCapability, ProviderDefinition, ProviderKind,
    ProviderCapabilityStatus, ProviderMergeMode, ProviderPolicy,
)

ADAPTER_REGISTRY: dict[str, str] = {
    "a_stock_data": "a-stock-data controlled adapter",
    "financial_api": "Financial-API controlled adapter",
}
DEFAULT_REGISTRY_TIMESTAMP = datetime(2026, 8, 31, tzinfo=timezone.utc)


def _dataset_contracts() -> tuple[DatasetDefinition, ...]:
    return (
        DatasetDefinition(
            dataset_id="security_master", schema_version="1.0.0", entity_scope="a_share", frequency="event",
            primary_key_fields=("entity_key",),
            required_fields=("entity_key", "canonical_id", "code", "exchange", "asset_type", "list_date", "currency", "lot_size", "available_at"),
            optional_fields=("name", "delist_date", "board", "valid_from", "valid_to"),
            field_types={
                "entity_key": "string", "canonical_id": "string", "code": "string", "exchange": "string", "asset_type": "string",
                "name": "string", "list_date": "date", "delist_date": "date", "board": "string", "currency": "string",
                "lot_size": "integer", "valid_from": "date", "valid_to": "date", "available_at": "timestamptz",
            },
            units={
                "entity_key": "identifier", "canonical_id": "identifier", "code": "identifier", "exchange": "code", "asset_type": "enum",
                "name": "text", "list_date": "calendar_date", "delist_date": "calendar_date", "board": "enum", "currency": "iso_4217",
                "lot_size": "shares_per_lot", "valid_from": "calendar_date", "valid_to": "calendar_date", "available_at": "utc_instant",
            },
            enum_domains={"exchange": ("SH", "SZ", "BJ"), "asset_type": ("stock",), "board": ("MAIN", "STAR", "CHINEXT", "BSE"), "currency": ("CNY",)},
            time_semantics={
                "entity_key": "identity_stable", "canonical_id": "identity_stable", "code": "provider_identity_value", "exchange": "identity_context",
                "asset_type": "identity_context", "name": "effective_name", "list_date": "listing_effective_date", "delist_date": "delisting_effective_date",
                "board": "classification_effective", "currency": "valuation_currency", "lot_size": "settlement_rule_effective", "valid_from": "validity_start_date",
                "valid_to": "validity_end_date_exclusive", "available_at": "pit_usable_instant",
            },
            null_semantics={
                "entity_key": "forbidden", "canonical_id": "forbidden", "code": "forbidden", "exchange": "forbidden", "asset_type": "forbidden",
                "name": "nullable_unknown", "list_date": "forbidden", "delist_date": "nullable_until_delisted", "board": "nullable_unknown", "currency": "forbidden",
                "lot_size": "forbidden", "valid_from": "nullable_unbounded_start", "valid_to": "nullable_unbounded_end", "available_at": "forbidden",
            },
            partition_template="security_master/{date}", quality_rule_ids=("identity_resolved", "entity_key_consistent"), owner_module="data_platform",
        ),
        DatasetDefinition(
            dataset_id="trading_calendar", schema_version="1.0.0", entity_scope="a_share", frequency="daily",
            primary_key_fields=("market", "trade_date"),
            required_fields=("market", "trade_date", "is_open", "available_at"),
            optional_fields=("session_open_at", "session_close_at"),
            field_types={"market": "string", "trade_date": "date", "is_open": "boolean", "session_open_at": "timestamptz", "session_close_at": "timestamptz", "available_at": "timestamptz"},
            units={"market": "enum", "trade_date": "calendar_date", "is_open": "boolean", "session_open_at": "utc_instant", "session_close_at": "utc_instant", "available_at": "utc_instant"},
            enum_domains={"market": ("CN",)},
            time_semantics={"market": "calendar_scope", "trade_date": "exchange_session_date", "is_open": "session_state", "session_open_at": "session_open_instant", "session_close_at": "session_close_instant", "available_at": "pit_usable_instant"},
            null_semantics={"market": "forbidden", "trade_date": "forbidden", "is_open": "forbidden", "session_open_at": "nullable_when_closed", "session_close_at": "nullable_when_closed", "available_at": "forbidden"},
            partition_template="trading_calendar/{date}", quality_rule_ids=("calendar_consistent",), owner_module="data_platform",
        ),
        DatasetDefinition(
            dataset_id="bar_1d_raw", schema_version="1.0.0", entity_scope="a_share", frequency="daily",
            primary_key_fields=("entity_key", "trade_date"),
            required_fields=("entity_key", "trade_date", "open", "high", "low", "close", "volume_shares", "amount_cny", "prev_close", "trading_status", "price_limit_up", "price_limit_down", "available_at"),
            optional_fields=(),
            field_types={"entity_key": "string", "trade_date": "date", "open": "number", "high": "number", "low": "number", "close": "number", "volume_shares": "number", "amount_cny": "number", "prev_close": "number", "trading_status": "string", "price_limit_up": "number", "price_limit_down": "number", "available_at": "timestamptz"},
            units={"entity_key": "identifier", "trade_date": "calendar_date", "open": "cny_per_share", "high": "cny_per_share", "low": "cny_per_share", "close": "cny_per_share", "volume_shares": "shares", "amount_cny": "cny", "prev_close": "cny_per_share", "trading_status": "enum", "price_limit_up": "cny_per_share", "price_limit_down": "cny_per_share", "available_at": "utc_instant"},
            enum_domains={"trading_status": ("TRADED", "SUSPENDED", "NO_DATA", "NOT_LISTED")},
            time_semantics={"entity_key": "identity_stable", "trade_date": "exchange_session_date", "open": "session_observation", "high": "session_observation", "low": "session_observation", "close": "session_observation", "volume_shares": "session_observation", "amount_cny": "session_observation", "prev_close": "prior_session_observation", "trading_status": "session_state", "price_limit_up": "session_rule", "price_limit_down": "session_rule", "available_at": "pit_usable_instant"},
            null_semantics={"entity_key": "forbidden", "trade_date": "forbidden", "open": "nullable_when_not_traded", "high": "nullable_when_not_traded", "low": "nullable_when_not_traded", "close": "nullable_when_not_traded", "volume_shares": "nullable_when_not_traded", "amount_cny": "nullable_when_not_traded", "prev_close": "nullable_when_no_prior_session", "trading_status": "forbidden", "price_limit_up": "nullable_when_rule_unavailable", "price_limit_down": "nullable_when_rule_unavailable", "available_at": "forbidden"},
            partition_template="bar_1d_raw/{date}", quality_rule_ids=("identity_resolved", "ohlcv_consistent", "units_known"), owner_module="data_platform",
        ),
    )


def default_registry_records(now: datetime | None = None):
    # The default seed is a deterministic contract fixture. Runtime timestamps are not part of its business hash.
    effective_at = now or DEFAULT_REGISTRY_TIMESTAMP
    providers = (
        ProviderDefinition(provider_id="a_stock_data", display_name="a-stock-data", adapter_name="a_stock_data", adapter_version="1.0.0", provider_kind=ProviderKind.AGGREGATOR, credential_ref=None, created_at=effective_at, updated_at=effective_at),
        ProviderDefinition(provider_id="financial_api", display_name="Financial-API", adapter_name="financial_api", adapter_version="1.0.0", provider_kind=ProviderKind.DIRECT, credential_ref="secret://financial_api", created_at=effective_at, updated_at=effective_at),
    )
    datasets = _dataset_contracts()
    capabilities = tuple(
        ProviderCapability(provider_id=provider_id, dataset_id=dataset.dataset_id, dataset_schema_version=dataset.schema_version, market="CN", frequency=dataset.frequency, supported_fields=dataset.required_fields, history_start=None, freshness_sla_seconds=86400, rate_limit_profile={"requests_per_minute": 60}, provider_capability_status=ProviderCapabilityStatus.UNVERIFIED, checked_at=effective_at)
        for provider_id in ("a_stock_data", "financial_api") for dataset in datasets
    )
    policies = tuple(
        ProviderPolicy(provider_policy_id=f"{dataset.dataset_id}_v1", dataset_id=dataset.dataset_id, dataset_schema_version=dataset.schema_version, policy_version="1.0.0", primary_provider_id="a_stock_data", supplemental_provider_ids=("financial_api",), allowed_merge_mode=ProviderMergeMode.REPLACE_PARTITION, fallback_triggers=("PRIMARY_UNAVAILABLE", "QUALITY_FAILED"), field_authority_map={field: "a_stock_data" for field in dataset.required_fields}, conflict_tolerance={"mode": "reject"}, freshness_sla_seconds=86400, required_quality_rules=dataset.quality_rule_ids, effective_from=effective_at)
        for dataset in datasets
    )
    return providers, datasets, capabilities, policies


class ProviderRegistryService:
    def __init__(self, database: PostgresDatabase, repository: ProviderRegistryRepository | None = None):
        self.database = database
        self.repository = repository or ProviderRegistryRepository()

    def settings_projection(self):
        with self.database.transaction() as session:
            return self.repository.settings_projection(session)

    def bootstrap_defaults(self) -> None:
        providers, datasets, capabilities, policies = default_registry_records()
        with self.database.transaction() as session:
            self.repository.ensure_providers(session, providers)
            self.repository.ensure_datasets(session, datasets)
            self.repository.ensure_capabilities(session, capabilities)
            self.repository.ensure_policies(session, policies)


__all__ = ["ADAPTER_REGISTRY", "DEFAULT_REGISTRY_TIMESTAMP", "ProviderRegistryService", "default_registry_records"]
