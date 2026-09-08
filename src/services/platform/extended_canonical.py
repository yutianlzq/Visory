from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.schemas.platform import (
    DatasetDefinition,
    ProviderCanonicalMappingDefinition,
    ProviderRawSchemaDefinition,
    build_provider_raw_schema_definition,
    compute_provider_canonical_mapping_hash,
)

EXTENDED_DATASET_IDS = (
    "instrument_status_daily",
    "listing_status_history",
    "corporate_action",
    "financial_statement",
    "benchmark_index_1d",
)


def _dataset(dataset_id: str, *, primary_key_fields: tuple[str, ...], required_fields: tuple[str, ...], optional_fields: tuple[str, ...], field_types: dict[str, str], units: dict[str, str], enum_domains: dict[str, tuple[str, ...]], time_semantics: dict[str, str], null_semantics: dict[str, str], partition_template: str, quality_rule_ids: tuple[str, ...], frequency: str = "event") -> DatasetDefinition:
    return DatasetDefinition(dataset_id=dataset_id, schema_version="1.0.0", entity_scope="a_share", frequency=frequency, primary_key_fields=primary_key_fields, required_fields=required_fields, optional_fields=optional_fields, field_types=field_types, units=units, enum_domains=enum_domains, time_semantics=time_semantics, null_semantics=null_semantics, partition_template=partition_template, quality_rule_ids=quality_rule_ids, owner_module="data_platform")


def extended_dataset_contracts() -> tuple[DatasetDefinition, ...]:
    return (
        _dataset("instrument_status_daily", primary_key_fields=("entity_key", "status_date"), required_fields=("entity_key", "status_date", "instrument_status", "is_tradable", "available_at"), optional_fields=("suspension_reason",), field_types={"entity_key":"string","status_date":"date","instrument_status":"string","is_tradable":"boolean","suspension_reason":"string","available_at":"timestamptz"}, units={"entity_key":"identifier","status_date":"calendar_date","instrument_status":"enum","is_tradable":"boolean","suspension_reason":"reason_code","available_at":"utc_instant"}, enum_domains={"instrument_status":("ACTIVE","ST","SUSPENDED","DELISTED","NOT_LISTED")}, time_semantics={"entity_key":"identity_stable","status_date":"historical_status_date","instrument_status":"historical_status_effective","is_tradable":"session_state","suspension_reason":"status_reason","available_at":"pit_usable_instant"}, null_semantics={"entity_key":"forbidden","status_date":"forbidden","instrument_status":"forbidden","is_tradable":"forbidden","suspension_reason":"nullable_when_not_suspended","available_at":"forbidden"}, partition_template="instrument_status_daily/{date}", quality_rule_ids=("identity_resolved","historical_status_preserved","status_consistent"), frequency="daily"),
        _dataset("listing_status_history", primary_key_fields=("entity_key", "effective_from"), required_fields=("entity_key","listing_status","effective_from","available_at"), optional_fields=("effective_to",), field_types={"entity_key":"string","listing_status":"string","effective_from":"date","effective_to":"date","available_at":"timestamptz"}, units={"entity_key":"identifier","listing_status":"enum","effective_from":"calendar_date","effective_to":"calendar_date","available_at":"utc_instant"}, enum_domains={"listing_status":("NOT_LISTED","LISTED","DELISTED")}, time_semantics={"entity_key":"identity_stable","listing_status":"listing_status_effective","effective_from":"validity_start_date","effective_to":"validity_end_date_exclusive","available_at":"pit_usable_instant"}, null_semantics={"entity_key":"forbidden","listing_status":"forbidden","effective_from":"forbidden","effective_to":"nullable_open_ended","available_at":"forbidden"}, partition_template="listing_status_history/{year}", quality_rule_ids=("identity_resolved","listing_interval_non_overlapping","historical_status_preserved")),
        _dataset("corporate_action", primary_key_fields=("corporate_action_id","revision"), required_fields=("corporate_action_id","entity_key","action_type","ex_date","revision","published_at","available_at"), optional_fields=("record_date","payment_date","ratio","cash_amount","currency"), field_types={"corporate_action_id":"string","entity_key":"string","action_type":"string","ex_date":"date","record_date":"date","payment_date":"date","ratio":"number","cash_amount":"number","currency":"string","revision":"integer","published_at":"timestamptz","available_at":"timestamptz"}, units={"corporate_action_id":"identifier","entity_key":"identifier","action_type":"enum","ex_date":"calendar_date","record_date":"calendar_date","payment_date":"calendar_date","ratio":"ratio","cash_amount":"cny_per_share","currency":"iso_4217","revision":"revision","published_at":"utc_instant","available_at":"utc_instant"}, enum_domains={"action_type":("DIVIDEND","SPLIT","BONUS","RIGHTS","OTHER"),"currency":("CNY",)}, time_semantics={"corporate_action_id":"action_identity","entity_key":"identity_stable","action_type":"action_type","ex_date":"action_effective_date","record_date":"action_record_date","payment_date":"action_payment_date","ratio":"action_ratio","cash_amount":"action_cash_amount","currency":"valuation_currency","revision":"revision_effective","published_at":"disclosure_instant","available_at":"pit_usable_instant"}, null_semantics={"corporate_action_id":"forbidden","entity_key":"forbidden","action_type":"forbidden","ex_date":"forbidden","record_date":"nullable_when_not_disclosed","payment_date":"nullable_when_not_disclosed","ratio":"nullable_when_not_applicable","cash_amount":"nullable_when_not_applicable","currency":"nullable_when_no_cash","revision":"forbidden","published_at":"forbidden","available_at":"forbidden"}, partition_template="corporate_action/{year}", quality_rule_ids=("identity_resolved","action_dates_ordered","action_amounts_valid","revision_append_only")),
        _dataset("financial_statement", primary_key_fields=("entity_key","report_period","statement_type","line_item","revision"), required_fields=("entity_key","report_period","statement_type","line_item","value","unit","currency","published_at","available_at","revision"), optional_fields=(), field_types={"entity_key":"string","report_period":"date","statement_type":"string","line_item":"string","value":"number","unit":"string","currency":"string","published_at":"timestamptz","available_at":"timestamptz","revision":"integer"}, units={"entity_key":"identifier","report_period":"calendar_date","statement_type":"statement_type","line_item":"line_item","value":"financial_value","unit":"financial_unit","currency":"iso_4217","published_at":"utc_instant","available_at":"utc_instant","revision":"revision"}, enum_domains={"statement_type":("BALANCE_SHEET","INCOME_STATEMENT","CASH_FLOW"),"currency":("CNY",)}, time_semantics={"entity_key":"identity_stable","report_period":"report_period_end","statement_type":"statement_dimension","line_item":"statement_dimension","value":"financial_value_observation","unit":"financial_unit_declaration","currency":"valuation_currency","published_at":"disclosure_instant","available_at":"pit_usable_instant","revision":"revision_effective"}, null_semantics={"entity_key":"forbidden","report_period":"forbidden","statement_type":"forbidden","line_item":"forbidden","value":"nullable_when_not_reported","unit":"forbidden","currency":"forbidden","published_at":"forbidden","available_at":"forbidden","revision":"forbidden"}, partition_template="financial_statement/{report_period}", quality_rule_ids=("identity_resolved","financial_pit_complete","financial_unit_known","revision_append_only")),
        _dataset("benchmark_index_1d", primary_key_fields=("benchmark_id","trade_date"), required_fields=("benchmark_id","asset_type","trade_date","open","high","low","close","return_type","available_at"), optional_fields=("index_name","total_return_close"), field_types={"benchmark_id":"string","asset_type":"string","trade_date":"date","open":"number","high":"number","low":"number","close":"number","return_type":"string","index_name":"string","total_return_close":"number","available_at":"timestamptz"}, units={"benchmark_id":"identifier","asset_type":"enum","trade_date":"calendar_date","open":"index_points","high":"index_points","low":"index_points","close":"index_points","return_type":"enum","index_name":"text","total_return_close":"index_points","available_at":"utc_instant"}, enum_domains={"asset_type":("index",),"return_type":("PRICE","TOTAL_RETURN")}, time_semantics={"benchmark_id":"benchmark_identity_stable","asset_type":"asset_class","trade_date":"exchange_session_date","open":"session_observation","high":"session_observation","low":"session_observation","close":"session_observation","return_type":"benchmark_return_semantics","index_name":"display_name","total_return_close":"total_return_observation","available_at":"pit_usable_instant"}, null_semantics={"benchmark_id":"forbidden","asset_type":"forbidden","trade_date":"forbidden","open":"forbidden","high":"forbidden","low":"forbidden","close":"forbidden","return_type":"forbidden","index_name":"nullable_display_name","total_return_close":"nullable_when_price_only","available_at":"forbidden"}, partition_template="benchmark_index_1d/{date}", quality_rule_ids=("benchmark_identity_resolved","benchmark_asset_type_index","benchmark_ohlc_consistent","benchmark_return_semantics_explicit","benchmark_pit_complete"), frequency="daily"),
    )


def _raw(provider_id: str, dataset_id: str, fields: dict[str, str]) -> ProviderRawSchemaDefinition:
    return build_provider_raw_schema_definition(provider_id=provider_id, adapter_version="1.0.0", dataset_id=dataset_id, dataset_schema_version="1.0.0", provider_schema_version="1.0.0", required_fields=tuple(fields), field_types=fields)


def extended_provider_raw_schema_records(now: datetime | None = None) -> tuple[ProviderRawSchemaDefinition, ...]:
    del now
    a = {
        "instrument_status_daily":{"ts_code":"string","status_date":"date","status":"string","tradable":"boolean","suspension_reason":"string","as_of":"timestamptz"},
        "listing_status_history":{"ts_code":"string","effective_from":"date","effective_to":"date","listing_status":"string","as_of":"timestamptz"},
        "corporate_action":{"action_id":"string","ts_code":"string","action_type":"string","ex_date":"date","record_date":"date","payment_date":"date","ratio":"number","cash_amount":"number","currency_code":"string","revision":"integer","published_at":"timestamptz","as_of":"timestamptz"},
        "financial_statement":{"ts_code":"string","report_period":"date","statement_type":"string","line_item":"string","value":"number","unit":"string","currency_code":"string","published_at":"timestamptz","available_at":"timestamptz","revision":"integer"},
        "benchmark_index_1d":{"index_code":"string","asset_type":"string","trade_date":"date","open":"number","high":"number","low":"number","close":"number","return_type":"string","index_name":"string","total_return_close":"number","available_at":"timestamptz"},
    }
    f = {
        "instrument_status_daily":{"symbol":"string","status_date":"date","status":"string","is_tradable":"boolean","reason":"string","observed_at":"timestamptz"},
        "listing_status_history":{"symbol":"string","from_date":"date","to_date":"date","status":"string","observed_at":"timestamptz"},
        "corporate_action":{"corporate_action_id":"string","symbol":"string","type":"string","ex_date":"date","record_date":"date","payment_date":"date","ratio":"number","cash_per_share":"number","currency":"string","revision":"integer","published_at":"timestamptz","available_at":"timestamptz"},
        "financial_statement":{"symbol":"string","period_end":"date","statement":"string","item":"string","amount":"number","unit":"string","currency":"string","published_at":"timestamptz","available_at":"timestamptz","revision":"integer"},
        "benchmark_index_1d":{"benchmark":"string","asset_type":"string","session_date":"date","o":"number","h":"number","l":"number","c":"number","return_kind":"string","name":"string","total_return":"number","available_at":"timestamptz"},
    }
    return tuple([_raw("a_stock_data", k, v) for k, v in a.items()] + [_raw("financial_api", k, v) for k, v in f.items()])


def _mapping(provider_id: str, dataset_id: str, source_fields: dict[str, str], source_field_types: dict[str, str], target_fields: tuple[str, ...], target_field_types: dict[str, str], target_units: dict[str, str], enum_mappings: dict[str, dict[str, str]], null_semantics: dict[str, str], time_semantics: dict[str, str], created_at: datetime) -> ProviderCanonicalMappingDefinition:
    actual_source_types = {source_fields[target]: source_field_types.get(source_fields[target], source_field_types.get(target, "string")) for target in source_fields}
    payload: dict[str, Any] = {"provider_id":provider_id,"dataset_id":dataset_id,"dataset_schema_version":"1.0.0","mapping_version":"1.0.0","source_fields":source_fields,"source_field_types":actual_source_types,"target_fields":target_fields,"target_field_types":target_field_types,"target_units":target_units,"unit_multipliers":{field:"1" for field, unit in target_units.items() if unit in {"ratio","cny_per_share","financial_value"}},"enum_mappings":enum_mappings,"null_semantics":null_semantics,"time_semantics":time_semantics,"created_at":created_at}
    payload["mapping_hash"] = compute_provider_canonical_mapping_hash(payload)
    return ProviderCanonicalMappingDefinition(**payload)


def extended_provider_canonical_mapping_records(now: datetime | None = None) -> tuple[ProviderCanonicalMappingDefinition, ...]:
    created_at = now or datetime(2026, 8, 31, tzinfo=timezone.utc)
    target_types = {
        "instrument_status_daily":{"entity_key":"string","status_date":"date","instrument_status":"string","is_tradable":"boolean","suspension_reason":"string","available_at":"timestamptz"},
        "listing_status_history":{"entity_key":"string","listing_status":"string","effective_from":"date","effective_to":"date","available_at":"timestamptz"},
        "corporate_action":{"corporate_action_id":"string","entity_key":"string","action_type":"string","ex_date":"date","record_date":"date","payment_date":"date","ratio":"number","cash_amount":"number","currency":"string","revision":"integer","published_at":"timestamptz","available_at":"timestamptz"},
        "financial_statement":{"entity_key":"string","report_period":"date","statement_type":"string","line_item":"string","value":"number","unit":"string","currency":"string","published_at":"timestamptz","available_at":"timestamptz","revision":"integer"},
        "benchmark_index_1d":{"benchmark_id":"string","asset_type":"string","trade_date":"date","open":"number","high":"number","low":"number","close":"number","return_type":"string","index_name":"string","total_return_close":"number","available_at":"timestamptz"},
    }
    target_units = {
        "instrument_status_daily":{"entity_key":"identifier","status_date":"calendar_date","instrument_status":"enum","is_tradable":"boolean","suspension_reason":"reason_code","available_at":"utc_instant"},
        "listing_status_history":{"entity_key":"identifier","listing_status":"enum","effective_from":"calendar_date","effective_to":"calendar_date","available_at":"utc_instant"},
        "corporate_action":{"corporate_action_id":"identifier","entity_key":"identifier","action_type":"enum","ex_date":"calendar_date","record_date":"calendar_date","payment_date":"calendar_date","ratio":"ratio","cash_amount":"cny_per_share","currency":"iso_4217","revision":"revision","published_at":"utc_instant","available_at":"utc_instant"},
        "financial_statement":{"entity_key":"identifier","report_period":"calendar_date","statement_type":"statement_type","line_item":"line_item","value":"financial_value","unit":"financial_unit","currency":"iso_4217","published_at":"utc_instant","available_at":"utc_instant","revision":"revision"},
        "benchmark_index_1d":{"benchmark_id":"identifier","asset_type":"enum","trade_date":"calendar_date","open":"index_points","high":"index_points","low":"index_points","close":"index_points","return_type":"enum","index_name":"text","total_return_close":"index_points","available_at":"utc_instant"},
    }
    source_types = {
        "instrument_status_daily":{"entity_key":"string","status_date":"date","instrument_status":"string","is_tradable":"boolean","suspension_reason":"string","available_at":"timestamptz"},
        "listing_status_history":{"entity_key":"string","listing_status":"string","effective_from":"date","effective_to":"date","available_at":"timestamptz"},
        "corporate_action":{"corporate_action_id":"string","entity_key":"string","action_type":"string","ex_date":"date","record_date":"date","payment_date":"date","ratio":"number","cash_amount":"number","currency":"string","revision":"integer","published_at":"timestamptz","available_at":"timestamptz"},
        "financial_statement":{"entity_key":"string","report_period":"date","statement_type":"string","line_item":"string","value":"number","unit":"string","currency":"string","published_at":"timestamptz","available_at":"timestamptz","revision":"integer"},
    }
    a = {
        "instrument_status_daily":{"entity_key":"ts_code","status_date":"status_date","instrument_status":"status","is_tradable":"tradable","suspension_reason":"suspension_reason","available_at":"as_of"},
        "listing_status_history":{"entity_key":"ts_code","listing_status":"listing_status","effective_from":"effective_from","effective_to":"effective_to","available_at":"as_of"},
        "corporate_action":{"corporate_action_id":"action_id","entity_key":"ts_code","action_type":"action_type","ex_date":"ex_date","record_date":"record_date","payment_date":"payment_date","ratio":"ratio","cash_amount":"cash_amount","currency":"currency_code","revision":"revision","published_at":"published_at","available_at":"as_of"},
        "financial_statement":{"entity_key":"ts_code","report_period":"report_period","statement_type":"statement_type","line_item":"line_item","value":"value","unit":"unit","currency":"currency_code","published_at":"published_at","available_at":"available_at","revision":"revision"},
        "benchmark_index_1d":{"benchmark_id":"index_code","asset_type":"asset_type","trade_date":"trade_date","open":"open","high":"high","low":"low","close":"close","return_type":"return_type","index_name":"index_name","total_return_close":"total_return_close","available_at":"available_at"},
    }
    f = {
        "instrument_status_daily":{"entity_key":"symbol","status_date":"status_date","instrument_status":"status","is_tradable":"is_tradable","suspension_reason":"reason","available_at":"observed_at"},
        "listing_status_history":{"entity_key":"symbol","listing_status":"status","effective_from":"from_date","effective_to":"to_date","available_at":"observed_at"},
        "corporate_action":{"corporate_action_id":"corporate_action_id","entity_key":"symbol","action_type":"type","ex_date":"ex_date","record_date":"record_date","payment_date":"payment_date","ratio":"ratio","cash_amount":"cash_per_share","currency":"currency","revision":"revision","published_at":"published_at","available_at":"available_at"},
        "financial_statement":{"entity_key":"symbol","report_period":"period_end","statement_type":"statement","line_item":"item","value":"amount","unit":"unit","currency":"currency","published_at":"published_at","available_at":"available_at","revision":"revision"},
        "benchmark_index_1d":{"benchmark_id":"benchmark","asset_type":"asset_type","trade_date":"session_date","open":"o","high":"h","low":"l","close":"c","return_type":"return_kind","index_name":"name","total_return_close":"total_return","available_at":"available_at"},
    }
    enums = {
        "instrument_status_daily":{"instrument_status":{"NORMAL":"ACTIVE","ACTIVE":"ACTIVE","ST":"ST","SUSPENDED":"SUSPENDED","SUSPEND":"SUSPENDED","DELISTED":"DELISTED","NOT_LISTED":"NOT_LISTED"}},
        "listing_status_history":{"listing_status":{"NOT_LISTED":"NOT_LISTED","LISTED":"LISTED","ACTIVE":"LISTED","DELISTED":"DELISTED"}},
        "corporate_action":{"action_type":{"DIV":"DIVIDEND","DIVIDEND":"DIVIDEND","SPLIT":"SPLIT","BONUS":"BONUS","RIGHTS":"RIGHTS","OTHER":"OTHER"},"currency":{"CNY":"CNY","RMB":"CNY"}},
        "financial_statement":{"statement_type":{"BS":"BALANCE_SHEET","BALANCE_SHEET":"BALANCE_SHEET","IS":"INCOME_STATEMENT","INCOME_STATEMENT":"INCOME_STATEMENT","CF":"CASH_FLOW","CASH_FLOW":"CASH_FLOW"},"currency":{"CNY":"CNY","RMB":"CNY"}},
        "benchmark_index_1d":{"asset_type":{"INDEX":"index","index":"index"},"return_type":{"PRICE":"PRICE","TOTAL_RETURN":"TOTAL_RETURN"}},
    }
    nulls = {
        "instrument_status_daily":{"entity_key":"forbidden","status_date":"forbidden","instrument_status":"forbidden","is_tradable":"forbidden","suspension_reason":"nullable_when_not_suspended","available_at":"forbidden"},
        "listing_status_history":{"entity_key":"forbidden","listing_status":"forbidden","effective_from":"forbidden","effective_to":"nullable_open_ended","available_at":"forbidden"},
        "corporate_action":{"corporate_action_id":"forbidden","entity_key":"forbidden","action_type":"forbidden","ex_date":"forbidden","record_date":"nullable_when_not_disclosed","payment_date":"nullable_when_not_disclosed","ratio":"nullable_when_not_applicable","cash_amount":"nullable_when_not_applicable","currency":"nullable_when_no_cash","revision":"forbidden","published_at":"forbidden","available_at":"forbidden"},
        "financial_statement":{"entity_key":"forbidden","report_period":"forbidden","statement_type":"forbidden","line_item":"forbidden","value":"nullable_when_not_reported","unit":"forbidden","currency":"forbidden","published_at":"forbidden","available_at":"forbidden","revision":"forbidden"},
        "benchmark_index_1d":{"benchmark_id":"forbidden","asset_type":"forbidden","trade_date":"forbidden","open":"forbidden","high":"forbidden","low":"forbidden","close":"forbidden","return_type":"forbidden","index_name":"nullable_display_name","total_return_close":"nullable_when_price_only","available_at":"forbidden"},
    }
    times = {
        "instrument_status_daily":{"entity_key":"identity_stable","status_date":"historical_status_date","instrument_status":"historical_status_effective","is_tradable":"session_state","suspension_reason":"status_reason","available_at":"pit_usable_instant"},
        "listing_status_history":{"entity_key":"identity_stable","listing_status":"listing_status_effective","effective_from":"validity_start_date","effective_to":"validity_end_date_exclusive","available_at":"pit_usable_instant"},
        "corporate_action":{"corporate_action_id":"action_identity","entity_key":"identity_stable","action_type":"action_type","ex_date":"action_effective_date","record_date":"action_record_date","payment_date":"action_payment_date","ratio":"action_ratio","cash_amount":"action_cash_amount","currency":"valuation_currency","revision":"revision_effective","published_at":"disclosure_instant","available_at":"pit_usable_instant"},
        "financial_statement":{"entity_key":"identity_stable","report_period":"report_period_end","statement_type":"statement_dimension","line_item":"statement_dimension","value":"financial_value_observation","unit":"financial_unit_declaration","currency":"valuation_currency","published_at":"disclosure_instant","available_at":"pit_usable_instant","revision":"revision_effective"},
        "benchmark_index_1d":{"benchmark_id":"benchmark_identity_stable","asset_type":"asset_class","trade_date":"exchange_session_date","open":"session_observation","high":"session_observation","low":"session_observation","close":"session_observation","return_type":"benchmark_return_semantics","index_name":"display_name","total_return_close":"total_return_observation","available_at":"pit_usable_instant"},
    }
    a["benchmark_index_1d"] = {"benchmark_id":"index_code","asset_type":"asset_type","trade_date":"trade_date","open":"open","high":"high","low":"low","close":"close","return_type":"return_type","index_name":"index_name","total_return_close":"total_return_close","available_at":"available_at"}
    f["benchmark_index_1d"] = {"benchmark_id":"benchmark","asset_type":"asset_type","trade_date":"session_date","open":"o","high":"h","low":"l","close":"c","return_type":"return_kind","index_name":"name","total_return_close":"total_return","available_at":"available_at"}
    source_types["benchmark_index_1d"] = {"benchmark_id":"string","asset_type":"string","trade_date":"date","open":"number","high":"number","low":"number","close":"number","return_type":"string","index_name":"string","total_return_close":"number","available_at":"timestamptz"}
    target_types["benchmark_index_1d"] = {"benchmark_id":"string","asset_type":"string","trade_date":"date","open":"number","high":"number","low":"number","close":"number","return_type":"string","index_name":"string","total_return_close":"number","available_at":"timestamptz"}
    target_units["benchmark_index_1d"] = {"benchmark_id":"identifier","asset_type":"enum","trade_date":"calendar_date","open":"index_points","high":"index_points","low":"index_points","close":"index_points","return_type":"enum","index_name":"text","total_return_close":"index_points","available_at":"utc_instant"}
    enums["benchmark_index_1d"] = {"asset_type":{"INDEX":"index","index":"index"},"return_type":{"PRICE":"PRICE","TOTAL_RETURN":"TOTAL_RETURN"}}
    nulls["benchmark_index_1d"] = {"benchmark_id":"forbidden","asset_type":"forbidden","trade_date":"forbidden","open":"forbidden","high":"forbidden","low":"forbidden","close":"forbidden","return_type":"forbidden","index_name":"nullable_display_name","total_return_close":"nullable_when_price_only","available_at":"forbidden"}
    times["benchmark_index_1d"] = {"benchmark_id":"benchmark_identity_stable","asset_type":"asset_class","trade_date":"exchange_session_date","open":"session_observation","high":"session_observation","low":"session_observation","close":"session_observation","return_type":"benchmark_return_semantics","index_name":"display_name","total_return_close":"total_return_observation","available_at":"pit_usable_instant"}
    records: list[ProviderCanonicalMappingDefinition] = []
    for provider_id, sources in (("a_stock_data", a), ("financial_api", f)):
        for dataset_id, source_fields in sources.items():
            records.append(_mapping(provider_id, dataset_id, source_fields, source_types[dataset_id], tuple(target_types[dataset_id]), target_types[dataset_id], target_units[dataset_id], enums[dataset_id], nulls[dataset_id], times[dataset_id], created_at))
    return tuple(records)

__all__ = ["EXTENDED_DATASET_IDS", "extended_dataset_contracts", "extended_provider_raw_schema_records", "extended_provider_canonical_mapping_records"]
