from __future__ import annotations

from datetime import datetime, timezone

from src.repositories.platform import PostgresDatabase, ProviderRegistryRepository
from src.schemas.platform import (
    DatasetDefinition, ProviderCapability, ProviderDefinition, ProviderKind,
    ProviderCapabilityStatus, ProviderMergeMode, ProviderPolicy,
    ProviderRawSchemaDefinition, ProviderCanonicalMappingDefinition, build_provider_raw_schema_definition, compute_provider_canonical_mapping_hash,
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


def default_provider_raw_schema_records(now: datetime | None = None) -> tuple[ProviderRawSchemaDefinition, ...]:
    """Return provider-native raw schemas; never derive these from DatasetDefinition."""

    del now
    definitions = (
        ("a_stock_data", "security_master", ("ts_code", "exchange_code", "asset_type", "listed_on", "currency_code", "lot_size", "as_of"), ("security_name", "delisted_on", "market_board"), {"ts_code": "string", "exchange_code": "string", "asset_type": "string", "listed_on": "date", "currency_code": "string", "lot_size": "integer", "as_of": "timestamptz", "security_name": "string", "delisted_on": "date", "market_board": "string"}),
        ("a_stock_data", "trading_calendar", ("cal_date", "is_open", "as_of"), ("market_code", "session_open", "session_close"), {"cal_date": "date", "is_open": "boolean", "as_of": "timestamptz", "market_code": "string", "session_open": "timestamptz", "session_close": "timestamptz"}),
        ("a_stock_data", "bar_1d_raw", ("ts_code", "trade_date", "open_price", "high_price", "low_price", "close_price", "vol", "amount", "pre_close", "trade_status", "limit_up", "limit_down", "as_of"), (), {"ts_code": "string", "trade_date": "date", "open_price": "number", "high_price": "number", "low_price": "number", "close_price": "number", "vol": "number", "amount": "number", "pre_close": "number", "trade_status": "string", "limit_up": "number", "limit_down": "number", "as_of": "timestamptz"}),
        ("financial_api", "security_master", ("symbol", "exchange_code", "asset_class", "listed_on", "currency_code", "lot_size", "observed_at"), ("security_name", "delisted_on", "market_board"), {"symbol": "string", "exchange_code": "string", "asset_class": "string", "listed_on": "date", "currency_code": "string", "lot_size": "integer", "observed_at": "timestamptz", "security_name": "string", "delisted_on": "date", "market_board": "string"}),
        ("financial_api", "trading_calendar", ("session_date", "market_code", "open_flag", "available_at"), ("session_open", "session_close"), {"session_date": "date", "market_code": "string", "open_flag": "boolean", "available_at": "timestamptz", "session_open": "timestamptz", "session_close": "timestamptz"}),
        ("financial_api", "bar_1d_raw", ("symbol", "trade_date", "o", "h", "l", "c", "volume", "turnover", "prev_close", "status", "upper_limit", "lower_limit", "available_at"), (), {"symbol": "string", "trade_date": "date", "o": "number", "h": "number", "l": "number", "c": "number", "volume": "number", "turnover": "number", "prev_close": "number", "status": "string", "upper_limit": "number", "lower_limit": "number", "available_at": "timestamptz"}),
    )
    return tuple(
        build_provider_raw_schema_definition(
            provider_id=provider_id,
            adapter_version="1.0.0",
            dataset_id=dataset_id,
            dataset_schema_version="1.0.0",
            provider_schema_version="1.0.0",
            required_fields=required_fields,
            optional_fields=optional_fields,
            field_types=field_types,
        )
        for provider_id, dataset_id, required_fields, optional_fields, field_types in definitions
    )


def default_provider_canonical_mapping_records(now: datetime | None = None) -> tuple[ProviderCanonicalMappingDefinition, ...]:
    """Return the six explicit provider-to-canonical mappings used by WP-0203."""
    created_at = now or DEFAULT_REGISTRY_TIMESTAMP
    definitions = (
        {
            "provider_id": "a_stock_data", "dataset_id": "security_master",
            "source_fields": {"entity_key": "ts_code", "canonical_id": "ts_code", "code": "ts_code", "exchange": "exchange_code", "asset_type": "asset_type", "name": "security_name", "list_date": "listed_on", "delist_date": "delisted_on", "board": "market_board", "currency": "currency_code", "lot_size": "lot_size", "valid_from": "listed_on", "valid_to": "delisted_on", "available_at": "as_of"},
            "source_field_types": {"ts_code": "string", "exchange_code": "string", "asset_type": "string", "security_name": "string", "listed_on": "date", "delisted_on": "date", "market_board": "string", "currency_code": "string", "lot_size": "integer", "as_of": "timestamptz"},
            "target_fields": ("entity_key", "canonical_id", "code", "exchange", "asset_type", "name", "list_date", "delist_date", "board", "currency", "lot_size", "valid_from", "valid_to", "available_at"),
            "target_field_types": {"entity_key": "string", "canonical_id": "string", "code": "string", "exchange": "string", "asset_type": "string", "name": "string", "list_date": "date", "delist_date": "date", "board": "string", "currency": "string", "lot_size": "integer", "valid_from": "date", "valid_to": "date", "available_at": "timestamptz"},
            "target_units": {"entity_key": "identifier", "canonical_id": "identifier", "code": "identifier", "exchange": "code", "asset_type": "enum", "name": "text", "list_date": "calendar_date", "delist_date": "calendar_date", "board": "enum", "currency": "iso_4217", "lot_size": "shares_per_lot", "valid_from": "calendar_date", "valid_to": "calendar_date", "available_at": "utc_instant"},
            "enum_mappings": {"exchange": {"SSE": "SH", "SZSE": "SZ", "SH": "SH", "SZ": "SZ", "BSE": "BJ", "BJ": "BJ"}, "asset_type": {"EQUITY": "stock", "STOCK": "stock", "stock": "stock"}, "currency": {"CNY": "CNY", "RMB": "CNY"}},
            "null_semantics": {"entity_key": "forbidden", "canonical_id": "forbidden", "code": "forbidden", "exchange": "forbidden", "asset_type": "forbidden", "name": "nullable_unknown", "list_date": "forbidden", "delist_date": "nullable_until_delisted", "board": "nullable_unknown", "currency": "forbidden", "lot_size": "forbidden", "valid_from": "nullable_unbounded_start", "valid_to": "nullable_unbounded_end", "available_at": "forbidden"},
            "time_semantics": {"list_date": "listing_effective_date", "delist_date": "delisting_effective_date", "valid_from": "validity_start_date", "valid_to": "validity_end_date_exclusive", "available_at": "pit_usable_instant"},
        },
        {
            "provider_id": "financial_api", "dataset_id": "security_master",
            "source_fields": {"entity_key": "symbol", "canonical_id": "symbol", "code": "symbol", "exchange": "exchange_code", "asset_type": "asset_class", "name": "security_name", "list_date": "listed_on", "delist_date": "delisted_on", "board": "market_board", "currency": "currency_code", "lot_size": "lot_size", "valid_from": "listed_on", "valid_to": "delisted_on", "available_at": "observed_at"},
            "source_field_types": {"symbol": "string", "exchange_code": "string", "asset_class": "string", "security_name": "string", "listed_on": "date", "delisted_on": "date", "market_board": "string", "currency_code": "string", "lot_size": "integer", "observed_at": "timestamptz"},
            "target_fields": ("entity_key", "canonical_id", "code", "exchange", "asset_type", "name", "list_date", "delist_date", "board", "currency", "lot_size", "valid_from", "valid_to", "available_at"),
            "target_field_types": {"entity_key": "string", "canonical_id": "string", "code": "string", "exchange": "string", "asset_type": "string", "name": "string", "list_date": "date", "delist_date": "date", "board": "string", "currency": "string", "lot_size": "integer", "valid_from": "date", "valid_to": "date", "available_at": "timestamptz"},
            "target_units": {"entity_key": "identifier", "canonical_id": "identifier", "code": "identifier", "exchange": "code", "asset_type": "enum", "name": "text", "list_date": "calendar_date", "delist_date": "calendar_date", "board": "enum", "currency": "iso_4217", "lot_size": "shares_per_lot", "valid_from": "calendar_date", "valid_to": "calendar_date", "available_at": "utc_instant"},
            "enum_mappings": {"exchange": {"NYSE": "SH", "SSE": "SH", "SZSE": "SZ", "SH": "SH", "SZ": "SZ", "BSE": "BJ", "BJ": "BJ"}, "asset_type": {"EQUITY": "stock", "COMMON_STOCK": "stock", "STOCK": "stock", "stock": "stock"}, "currency": {"CNY": "CNY", "RMB": "CNY"}},
            "null_semantics": {"entity_key": "forbidden", "canonical_id": "forbidden", "code": "forbidden", "exchange": "forbidden", "asset_type": "forbidden", "name": "nullable_unknown", "list_date": "forbidden", "delist_date": "nullable_until_delisted", "board": "nullable_unknown", "currency": "forbidden", "lot_size": "forbidden", "valid_from": "nullable_unbounded_start", "valid_to": "nullable_unbounded_end", "available_at": "forbidden"},
            "time_semantics": {"list_date": "listing_effective_date", "delist_date": "delisting_effective_date", "valid_from": "validity_start_date", "valid_to": "validity_end_date_exclusive", "available_at": "pit_usable_instant"},
        },
        {
            "provider_id": "a_stock_data", "dataset_id": "trading_calendar",
            "source_fields": {"market": "market_code", "trade_date": "cal_date", "is_open": "is_open", "session_open_at": "session_open", "session_close_at": "session_close", "available_at": "as_of"},
            "source_field_types": {"market_code": "string", "cal_date": "date", "is_open": "boolean", "session_open": "timestamptz", "session_close": "timestamptz", "as_of": "timestamptz"},
            "target_fields": ("market", "trade_date", "is_open", "session_open_at", "session_close_at", "available_at"),
            "target_field_types": {"market": "string", "trade_date": "date", "is_open": "boolean", "session_open_at": "timestamptz", "session_close_at": "timestamptz", "available_at": "timestamptz"},
            "target_units": {"market": "enum", "trade_date": "calendar_date", "is_open": "boolean", "session_open_at": "utc_instant", "session_close_at": "utc_instant", "available_at": "utc_instant"},
            "enum_mappings": {"market": {"CN": "CN", "SH": "CN", "SZ": "CN"}},
            "null_semantics": {"market": "forbidden", "trade_date": "forbidden", "is_open": "forbidden", "session_open_at": "nullable_when_closed", "session_close_at": "nullable_when_closed", "available_at": "forbidden"},
            "time_semantics": {"trade_date": "exchange_session_date", "session_open_at": "session_open_instant", "session_close_at": "session_close_instant", "available_at": "pit_usable_instant"},
        },
        {
            "provider_id": "financial_api", "dataset_id": "trading_calendar",
            "source_fields": {"market": "market_code", "trade_date": "session_date", "is_open": "open_flag", "session_open_at": "session_open", "session_close_at": "session_close", "available_at": "available_at"},
            "source_field_types": {"market_code": "string", "session_date": "date", "open_flag": "boolean", "session_open": "timestamptz", "session_close": "timestamptz", "available_at": "timestamptz"},
            "target_fields": ("market", "trade_date", "is_open", "session_open_at", "session_close_at", "available_at"),
            "target_field_types": {"market": "string", "trade_date": "date", "is_open": "boolean", "session_open_at": "timestamptz", "session_close_at": "timestamptz", "available_at": "timestamptz"},
            "target_units": {"market": "enum", "trade_date": "calendar_date", "is_open": "boolean", "session_open_at": "utc_instant", "session_close_at": "utc_instant", "available_at": "utc_instant"},
            "enum_mappings": {"market": {"CN": "CN", "SH": "CN", "SZ": "CN"}},
            "null_semantics": {"market": "forbidden", "trade_date": "forbidden", "is_open": "forbidden", "session_open_at": "nullable_when_closed", "session_close_at": "nullable_when_closed", "available_at": "forbidden"},
            "time_semantics": {"trade_date": "exchange_session_date", "session_open_at": "session_open_instant", "session_close_at": "session_close_instant", "available_at": "pit_usable_instant"},
        },
        {
            "provider_id": "a_stock_data", "dataset_id": "bar_1d_raw",
            "source_fields": {"entity_key": "ts_code", "trade_date": "trade_date", "open": "open_price", "high": "high_price", "low": "low_price", "close": "close_price", "volume_shares": "vol", "amount_cny": "amount", "prev_close": "pre_close", "trading_status": "trade_status", "price_limit_up": "limit_up", "price_limit_down": "limit_down", "available_at": "as_of"},
            "source_field_types": {"ts_code": "string", "trade_date": "date", "open_price": "number", "high_price": "number", "low_price": "number", "close_price": "number", "vol": "number", "amount": "number", "pre_close": "number", "trade_status": "string", "limit_up": "number", "limit_down": "number", "as_of": "timestamptz"},
            "target_fields": ("entity_key", "trade_date", "open", "high", "low", "close", "volume_shares", "amount_cny", "prev_close", "trading_status", "price_limit_up", "price_limit_down", "available_at"),
            "target_field_types": {"entity_key": "string", "trade_date": "date", "open": "number", "high": "number", "low": "number", "close": "number", "volume_shares": "number", "amount_cny": "number", "prev_close": "number", "trading_status": "string", "price_limit_up": "number", "price_limit_down": "number", "available_at": "timestamptz"},
            "target_units": {"entity_key": "identifier", "trade_date": "calendar_date", "open": "cny_per_share", "high": "cny_per_share", "low": "cny_per_share", "close": "cny_per_share", "volume_shares": "shares", "amount_cny": "cny", "prev_close": "cny_per_share", "trading_status": "enum", "price_limit_up": "cny_per_share", "price_limit_down": "cny_per_share", "available_at": "utc_instant"},
            "unit_multipliers": {"open": "1", "high": "1", "low": "1", "close": "1", "volume_shares": "1", "amount_cny": "1", "prev_close": "1", "price_limit_up": "1", "price_limit_down": "1"},
            "enum_mappings": {"trading_status": {"TRADE": "TRADED", "TRADED": "TRADED", "SUSPENDED": "SUSPENDED", "SUSPEND": "SUSPENDED", "NO_DATA": "NO_DATA", "NOT_LISTED": "NOT_LISTED"}},
            "null_semantics": {"entity_key": "forbidden", "trade_date": "forbidden", "open": "nullable_when_not_traded", "high": "nullable_when_not_traded", "low": "nullable_when_not_traded", "close": "nullable_when_not_traded", "volume_shares": "nullable_when_not_traded", "amount_cny": "nullable_when_not_traded", "prev_close": "nullable_when_no_prior_session", "trading_status": "forbidden", "price_limit_up": "nullable_when_rule_unavailable", "price_limit_down": "nullable_when_rule_unavailable", "available_at": "forbidden"},
            "time_semantics": {"trade_date": "exchange_session_date", "available_at": "pit_usable_instant"},
        },
        {
            "provider_id": "financial_api", "dataset_id": "bar_1d_raw",
            "source_fields": {"entity_key": "symbol", "trade_date": "trade_date", "open": "o", "high": "h", "low": "l", "close": "c", "volume_shares": "volume", "amount_cny": "turnover", "prev_close": "prev_close", "trading_status": "status", "price_limit_up": "upper_limit", "price_limit_down": "lower_limit", "available_at": "available_at"},
            "source_field_types": {"symbol": "string", "trade_date": "date", "o": "number", "h": "number", "l": "number", "c": "number", "volume": "number", "turnover": "number", "prev_close": "number", "status": "string", "upper_limit": "number", "lower_limit": "number", "available_at": "timestamptz"},
            "target_fields": ("entity_key", "trade_date", "open", "high", "low", "close", "volume_shares", "amount_cny", "prev_close", "trading_status", "price_limit_up", "price_limit_down", "available_at"),
            "target_field_types": {"entity_key": "string", "trade_date": "date", "open": "number", "high": "number", "low": "number", "close": "number", "volume_shares": "number", "amount_cny": "number", "prev_close": "number", "trading_status": "string", "price_limit_up": "number", "price_limit_down": "number", "available_at": "timestamptz"},
            "target_units": {"entity_key": "identifier", "trade_date": "calendar_date", "open": "cny_per_share", "high": "cny_per_share", "low": "cny_per_share", "close": "cny_per_share", "volume_shares": "shares", "amount_cny": "cny", "prev_close": "cny_per_share", "trading_status": "enum", "price_limit_up": "cny_per_share", "price_limit_down": "cny_per_share", "available_at": "utc_instant"},
            "unit_multipliers": {"open": "1", "high": "1", "low": "1", "close": "1", "volume_shares": "1", "amount_cny": "1", "prev_close": "1", "price_limit_up": "1", "price_limit_down": "1"},
            "enum_mappings": {"trading_status": {"TRADE": "TRADED", "TRADED": "TRADED", "SUSPENDED": "SUSPENDED", "SUSPEND": "SUSPENDED", "NO_DATA": "NO_DATA", "NOT_LISTED": "NOT_LISTED"}},
            "null_semantics": {"entity_key": "forbidden", "trade_date": "forbidden", "open": "nullable_when_not_traded", "high": "nullable_when_not_traded", "low": "nullable_when_not_traded", "close": "nullable_when_not_traded", "volume_shares": "nullable_when_not_traded", "amount_cny": "nullable_when_not_traded", "prev_close": "nullable_when_no_prior_session", "trading_status": "forbidden", "price_limit_up": "nullable_when_rule_unavailable", "price_limit_down": "nullable_when_rule_unavailable", "available_at": "forbidden"},
            "time_semantics": {"trade_date": "exchange_session_date", "available_at": "pit_usable_instant"},
        },
    )
    records = []
    for definition in definitions:
        payload = {
            "dataset_schema_version": "1.0.0",
            "mapping_version": "1.0.0",
            **definition,
            "created_at": created_at,
        }
        payload["mapping_hash"] = compute_provider_canonical_mapping_hash(payload)
        records.append(ProviderCanonicalMappingDefinition(**payload))
    return tuple(records)


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
    def __init__(self, database: PostgresDatabase, repository: ProviderRegistryRepository | None = None, canonical_repository=None):
        self.database = database
        self.repository = repository or ProviderRegistryRepository()
        if canonical_repository is None:
            from src.repositories.platform.canonical import CanonicalRepository
            canonical_repository = CanonicalRepository()
        self.canonical_repository = canonical_repository

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
            self.repository.ensure_provider_raw_schemas(session, default_provider_raw_schema_records())
            for mapping in default_provider_canonical_mapping_records():
                existing = self.canonical_repository.get_mapping(
                    session, mapping.provider_id, mapping.dataset_id, mapping.dataset_schema_version, mapping.mapping_version
                )
                if existing is None:
                    self.canonical_repository.add_mapping(session, mapping)
                elif existing != mapping:
                    raise ValueError("canonical mapping bootstrap conflict")


__all__ = ["ADAPTER_REGISTRY", "DEFAULT_REGISTRY_TIMESTAMP", "ProviderRegistryService", "default_registry_records", "default_provider_raw_schema_records", "default_provider_canonical_mapping_records"]
