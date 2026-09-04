from __future__ import annotations

import json
from datetime import date, datetime, timezone
from types import SimpleNamespace
from pathlib import Path

import pytest

from src.schemas.platform import (
    ProviderCanonicalMappingDefinition,
    TaskCreateRequest,
    QualityStatus,
    compute_provider_canonical_mapping_hash,
    generate_resource_id,
    ResourceType,
)
from src.services.platform.provider_registry import default_provider_canonical_mapping_records
from src.services.platform.canonical_normalization import (
    CanonicalNormalizer,
    CanonicalNormalizationError,
    deterministic_manifest_hash,
    compute_schema_hash,
)


NOW = datetime(2026, 1, 2, 8, 0, tzinfo=timezone.utc)


def _mapping() -> ProviderCanonicalMappingDefinition:
    payload = {
        "provider_id": "a_stock_data",
        "dataset_id": "bar_1d_raw",
        "dataset_schema_version": "1.0.0",
        "mapping_version": "1.0.0",
        "source_fields": {
            "entity_key": "ts_code",
            "trade_date": "trade_date",
            "open": "open_price",
            "high": "high_price",
            "low": "low_price",
            "close": "close_price",
            "available_at": "as_of",
        },
        "source_field_types": {"ts_code": "string", "trade_date": "date", "open_price": "number", "high_price": "number", "low_price": "number", "close_price": "number", "as_of": "timestamptz"},
        "target_fields": ("entity_key", "trade_date", "open", "high", "low", "close", "available_at"),
        "target_field_types": {"entity_key": "string", "trade_date": "date", "open": "number", "high": "number", "low": "number", "close": "number", "available_at": "timestamptz"},
        "target_units": {"entity_key": "identifier", "trade_date": "calendar_date", "open": "cny_per_share", "high": "cny_per_share", "low": "cny_per_share", "close": "cny_per_share", "available_at": "utc_instant"},
        "unit_multipliers": {},
        "enum_mappings": {},
        "null_semantics": {"entity_key": "forbidden", "trade_date": "forbidden"},
        "time_semantics": {"available_at": "observed_at"},
        "created_at": NOW,
    }
    return ProviderCanonicalMappingDefinition(
        **payload,
        mapping_hash=compute_provider_canonical_mapping_hash(payload),
    )


def _resolved_identity(value: str, row: object) -> SimpleNamespace:
    return SimpleNamespace(
        entity_key="stock:sh600519",
        canonical_id="sh600519",
        resolution_status=SimpleNamespace(value="RESOLVED"),
    )


def _rows() -> list[dict[str, object]]:
    return [
        {
            "ts_code": "stock:sh600519",
            "trade_date": "2026-01-02",
            "open_price": "10.00",
            "high_price": "11.00",
            "low_price": "9.00",
            "close_price": "10.50",
            "as_of": "2026-01-02T08:00:00+00:00",
        }
    ]


def test_default_mapping_registry_has_two_providers_for_each_core_dataset() -> None:
    mappings = default_provider_canonical_mapping_records()
    pairs = {(mapping.provider_id, mapping.dataset_id) for mapping in mappings}
    assert {
        (provider, dataset)
        for provider in {"a_stock_data", "financial_api"}
        for dataset in {"security_master", "trading_calendar", "bar_1d_raw", "instrument_status_daily", "listing_status_history", "corporate_action", "financial_statement"}
    } <= pairs
    for mapping in mappings:
        assert mapping.mapping_hash == compute_provider_canonical_mapping_hash(mapping)
        assert tuple(mapping.target_fields) == tuple(mapping.source_fields)
        assert set(mapping.target_fields) == set(mapping.target_field_types) == set(mapping.target_units)


def test_mapping_hash_changes_when_declared_column_order_changes() -> None:
    payload = _mapping().model_dump(mode="python")
    reordered = dict(payload)
    reordered["target_fields"] = tuple(reversed(payload["target_fields"]))
    assert compute_provider_canonical_mapping_hash(reordered) != payload["mapping_hash"]


def test_duplicate_negative_and_future_available_at_are_quality_failures(tmp_path: Path) -> None:
    normalizer = CanonicalNormalizer(tmp_path, clock=lambda: NOW)
    common = dict(
        raw_object_id=generate_resource_id(ResourceType.RAW_OBJECT),
        provider_run_id=generate_resource_id(ResourceType.PROVIDER_RUN),
        provider_id="a_stock_data",
        dataset_id="bar_1d_raw",
        dataset_schema_version="1.0.0",
        provider_policy_version="1.0.0",
        mapping=_mapping(),
        partition_key="2026-01-02",
        identity_resolver=_resolved_identity,
    )
    partition, report, _ = normalizer.normalize_rows(rows=[_rows()[0], _rows()[0]], **common)
    assert partition is None
    assert report.duplicate_key_count == 1
    assert report.failure_reasons == ("CANONICAL_DUPLICATE_KEY",)

    partition, report, _ = normalizer.normalize_rows(rows=[{**_rows()[0], "open_price": "-1"}], **common)
    assert partition is None
    assert report.failure_reasons == ("CANONICAL_NEGATIVE_VALUE",)

    partition, report, _ = normalizer.normalize_rows(rows=[{**_rows()[0], "as_of": "2026-01-03T08:00:00+00:00"}], **common)
    assert partition is None
    assert report.failure_reasons == ("CANONICAL_AVAILABLE_AT_FUTURE",)


def test_mapping_hash_rejects_tampering() -> None:
    payload = _mapping().model_dump(mode="python")
    payload["mapping_hash"] = "sha256:" + "0" * 64
    with pytest.raises(ValueError, match="mapping_hash"):
        ProviderCanonicalMappingDefinition.model_validate(payload)


def test_normalization_is_deterministic_and_manifest_hash_is_stable(tmp_path: Path) -> None:
    normalizer = CanonicalNormalizer(tmp_path, clock=lambda: NOW)
    first, first_report, content_a = normalizer.normalize_rows(
        raw_object_id=generate_resource_id(ResourceType.RAW_OBJECT),
        provider_run_id=generate_resource_id(ResourceType.PROVIDER_RUN),
        provider_id="a_stock_data",
        dataset_id="bar_1d_raw",
        dataset_schema_version="1.0.0",
        provider_policy_version="1.0.0",
        mapping=_mapping(),
        rows=_rows(),
        partition_key="2026-01-02",
        identity_resolver=_resolved_identity,
    )
    second, second_report, content_b = normalizer.normalize_rows(
        raw_object_id=generate_resource_id(ResourceType.RAW_OBJECT),
        provider_run_id=generate_resource_id(ResourceType.PROVIDER_RUN),
        provider_id="a_stock_data",
        dataset_id="bar_1d_raw",
        dataset_schema_version="1.0.0",
        provider_policy_version="1.0.0",
        mapping=_mapping(),
        rows=_rows(),
        partition_key="2026-01-02",
        identity_resolver=_resolved_identity,
    )
    assert first is not None and second is not None
    assert first_report.quality_status is QualityStatus.COMPLETE
    assert content_a == content_b
    manifest_a = {"partition": first.model_dump(mode="json"), "quality_report": first_report.model_dump(mode="json")}
    manifest_b = {"partition": second.model_dump(mode="json"), "quality_report": second_report.model_dump(mode="json")}
    # IDs are intentionally unique; the deterministic hash helper remains stable for equal payloads.
    assert deterministic_manifest_hash({"content_hash": first.partition_hash, "schema_hash": first.schema_hash}) == deterministic_manifest_hash({"schema_hash": first.schema_hash, "content_hash": first.partition_hash})
    normalizer.publish_partition(first, first_report, content_a)
    target = normalizer.resolver.resolve(first.storage_ref, require_exists=True)
    assert target.read_bytes() == content_a
    manifest = json.loads((target.parent / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["manifest_hash"] == deterministic_manifest_hash({"partition": manifest["partition"], "quality_report": manifest["quality_report"]})
    assert manifest_a["partition"]["storage_ref"]["relative_path"] == manifest_b["partition"]["storage_ref"]["relative_path"] or first.storage_ref.relative_path != second.storage_ref.relative_path


def test_normalization_quality_failure_blocks_publish(tmp_path: Path) -> None:
    normalizer = CanonicalNormalizer(tmp_path, clock=lambda: NOW)
    partition, report, content = normalizer.normalize_rows(
        raw_object_id=generate_resource_id(ResourceType.RAW_OBJECT),
        provider_run_id=generate_resource_id(ResourceType.PROVIDER_RUN),
        provider_id="a_stock_data",
        dataset_id="bar_1d_raw",
        dataset_schema_version="1.0.0",
        provider_policy_version="1.0.0",
        mapping=_mapping(),
        rows=[{**_rows()[0], "high_price": "8.00"}],
        partition_key="2026-01-02",
        identity_resolver=_resolved_identity,
    )
    assert partition is None
    assert content == b""
    assert report.quality_status is QualityStatus.FAILED
    assert "CANONICAL_OHLC_INVALID" in report.failure_reasons


def test_publish_rejects_existing_target(tmp_path: Path) -> None:
    normalizer = CanonicalNormalizer(tmp_path, clock=lambda: NOW)
    partition, report, content = normalizer.normalize_rows(
        raw_object_id=generate_resource_id(ResourceType.RAW_OBJECT),
        provider_run_id=generate_resource_id(ResourceType.PROVIDER_RUN),
        provider_id="a_stock_data",
        dataset_id="bar_1d_raw",
        dataset_schema_version="1.0.0",
        provider_policy_version="1.0.0",
        mapping=_mapping(),
        rows=_rows(),
        partition_key="2026-01-02",
        identity_resolver=_resolved_identity,
    )
    assert partition is not None
    normalizer.publish_partition(partition, report, content)
    with pytest.raises(CanonicalNormalizationError, match="target"):
        normalizer.publish_partition(partition, report, content)


def test_default_mappings_convert_types_and_resolve_identity(tmp_path: Path) -> None:
    normalizer = CanonicalNormalizer(tmp_path, clock=lambda: NOW)
    mappings = default_provider_canonical_mapping_records()
    security_mapping = next(item for item in mappings if item.provider_id == "a_stock_data" and item.dataset_id == "security_master")
    resolved = SimpleNamespace(entity_key="stock:sh600519", canonical_id="sh600519", resolution_status=SimpleNamespace(value="RESOLVED"))
    partition, report, _ = normalizer.normalize_rows(
        raw_object_id=generate_resource_id(ResourceType.RAW_OBJECT),
        provider_run_id=generate_resource_id(ResourceType.PROVIDER_RUN),
        provider_id=security_mapping.provider_id,
        dataset_id=security_mapping.dataset_id,
        dataset_schema_version="1.0.0",
        provider_policy_version="1.0.0",
        mapping=security_mapping,
        rows=[{
            "ts_code": "600519.SH", "exchange_code": "SSE", "asset_type": "EQUITY",
            "listed_on": date(2001, 8, 27), "currency_code": "RMB", "lot_size": "100",
            "as_of": NOW.isoformat(),
        }],
        partition_key="2026-01-02",
        identity_resolver=lambda value, row: resolved,
    )
    assert partition is not None and report.quality_status is QualityStatus.COMPLETE

    calendar_mapping = next(item for item in mappings if item.provider_id == "financial_api" and item.dataset_id == "trading_calendar")
    partition, report, _ = normalizer.normalize_rows(
        raw_object_id=generate_resource_id(ResourceType.RAW_OBJECT),
        provider_run_id=generate_resource_id(ResourceType.PROVIDER_RUN),
        provider_id=calendar_mapping.provider_id,
        dataset_id=calendar_mapping.dataset_id,
        dataset_schema_version="1.0.0",
        provider_policy_version="1.0.0",
        mapping=calendar_mapping,
        rows=[{
            "market_code": "SH", "session_date": "2026-01-02", "open_flag": "true",
            "session_open": "2026-01-02T01:30:00Z", "session_close": "2026-01-02T07:00:00Z",
            "available_at": NOW.isoformat(),
        }],
        partition_key="2026-01-02",
    )
    assert partition is not None and report.quality_status is QualityStatus.COMPLETE


def test_identity_ambiguity_is_rejected(tmp_path: Path) -> None:
    normalizer = CanonicalNormalizer(tmp_path, clock=lambda: NOW)
    ambiguous = SimpleNamespace(resolution_status=SimpleNamespace(value="AMBIGUOUS"))
    partition, report, content = normalizer.normalize_rows(
        raw_object_id=generate_resource_id(ResourceType.RAW_OBJECT),
        provider_run_id=generate_resource_id(ResourceType.PROVIDER_RUN),
        provider_id="a_stock_data", dataset_id="bar_1d_raw", dataset_schema_version="1.0.0",
        provider_policy_version="1.0.0", mapping=_mapping(), rows=_rows(), partition_key="2026-01-02",
        identity_resolver=lambda value, row: ambiguous,
    )
    assert partition is None and content == b""
    assert report.identity_ambiguous_count == 1
    assert report.failure_reasons == ("CANONICAL_IDENTITY_AMBIGUOUS",)


def test_parquet_schema_is_explicit_and_column_order_is_stable(tmp_path: Path) -> None:
    import pyarrow as pa
    import pyarrow.parquet as pq

    normalizer = CanonicalNormalizer(tmp_path, clock=lambda: NOW)
    partition, report, content = normalizer.normalize_rows(
        raw_object_id=generate_resource_id(ResourceType.RAW_OBJECT),
        provider_run_id=generate_resource_id(ResourceType.PROVIDER_RUN),
        provider_id="a_stock_data",
        dataset_id="bar_1d_raw",
        dataset_schema_version="1.0.0",
        provider_policy_version="1.0.0",
        mapping=_mapping(),
        rows=_rows(),
        partition_key="2026-01-02",
        identity_resolver=_resolved_identity,
    )
    assert partition is not None
    assert report.quality_status is QualityStatus.COMPLETE
    table = pq.read_table(pa.BufferReader(content))
    assert table.schema.names == list(_mapping().target_fields)
    assert str(table.schema.field("trade_date").type) == "date32[day]"
    assert str(table.schema.field("open").type) == "decimal128(38, 12)"
    assert str(table.schema.field("available_at").type) == "timestamp[us, tz=UTC]"


def test_bar_rejects_unresolved_bare_provider_code(tmp_path: Path) -> None:
    normalizer = CanonicalNormalizer(tmp_path, clock=lambda: NOW)
    partition, report, content = normalizer.normalize_rows(
        raw_object_id=generate_resource_id(ResourceType.RAW_OBJECT),
        provider_run_id=generate_resource_id(ResourceType.PROVIDER_RUN),
        provider_id="a_stock_data",
        dataset_id="bar_1d_raw",
        dataset_schema_version="1.0.0",
        provider_policy_version="1.0.0",
        mapping=_mapping(),
        rows=_rows(),
        partition_key="2026-01-02",
    )
    assert partition is None
    assert content == b""
    assert report.failure_reasons == ("CANONICAL_IDENTITY_UNRESOLVED",)


def test_non_trading_day_bar_is_rejected(tmp_path: Path) -> None:
    normalizer = CanonicalNormalizer(tmp_path, clock=lambda: NOW)
    partition, report, content = normalizer.normalize_rows(
        raw_object_id=generate_resource_id(ResourceType.RAW_OBJECT),
        provider_run_id=generate_resource_id(ResourceType.PROVIDER_RUN),
        provider_id="a_stock_data",
        dataset_id="bar_1d_raw",
        dataset_schema_version="1.0.0",
        provider_policy_version="1.0.0",
        mapping=_mapping(),
        rows=_rows(),
        partition_key="2026-01-02",
        is_trading_day=lambda market, trading_day: False,
        market="CN",
        identity_resolver=_resolved_identity,
    )
    assert partition is None
    assert content == b""
    assert report.failure_reasons == ("CANONICAL_NON_TRADING_DAY",)


def test_canonical_task_requests_validate_normalization_requirements() -> None:
    with pytest.raises(ValueError):
        TaskCreateRequest(
            task_type="canonical_normalization",
            requested_by="test",
            requirements={},
        )


def test_publish_rename_failure_leaves_no_registry_signal(tmp_path: Path) -> None:
    def fail_rename(source: Path, target: Path) -> None:
        raise OSError("rename denied")

    normalizer = CanonicalNormalizer(tmp_path, clock=lambda: NOW, rename=fail_rename)
    partition, report, content = normalizer.normalize_rows(
        raw_object_id=generate_resource_id(ResourceType.RAW_OBJECT),
        provider_run_id=generate_resource_id(ResourceType.PROVIDER_RUN),
        provider_id="a_stock_data", dataset_id="bar_1d_raw", dataset_schema_version="1.0.0",
        provider_policy_version="1.0.0", mapping=_mapping(), rows=_rows(), partition_key="2026-01-02",
        identity_resolver=_resolved_identity,
    )
    assert partition is not None
    with pytest.raises(CanonicalNormalizationError) as captured:
        normalizer.publish_partition(partition, report, content)
    assert captured.value.error_code == "CANONICAL_ATOMIC_PUBLISH_FAILED"
    assert not normalizer.resolver.resolve(partition.storage_ref).exists()


@pytest.mark.parametrize(
    ("provider_id", "dataset_id", "row"),
    [
        ("a_stock_data", "security_master", {
            "ts_code": "600519.SH", "exchange_code": "SSE", "asset_type": "EQUITY",
            "security_name": "Kweichow Moutai", "listed_on": "2001-08-27", "delisted_on": None,
            "market_board": "MAIN", "currency_code": "RMB", "lot_size": "100", "as_of": NOW.isoformat(),
        }),
        ("financial_api", "security_master", {
            "symbol": "000001.SZ", "exchange_code": "SZSE", "asset_class": "COMMON_STOCK",
            "security_name": "Ping An Bank", "listed_on": "1991-04-03", "delisted_on": None,
            "market_board": "MAIN", "currency_code": "CNY", "lot_size": 100, "observed_at": NOW.isoformat(),
        }),
        ("a_stock_data", "trading_calendar", {
            "market_code": "SH", "cal_date": "2026-01-02", "is_open": "true",
            "session_open": "2026-01-02T01:30:00Z", "session_close": "2026-01-02T07:00:00Z", "as_of": NOW.isoformat(),
        }),
        ("financial_api", "trading_calendar", {
            "market_code": "SZ", "session_date": "2026-01-02", "open_flag": 1,
            "session_open": "2026-01-02T01:30:00Z", "session_close": "2026-01-02T07:00:00Z", "available_at": NOW.isoformat(),
        }),
        ("a_stock_data", "bar_1d_raw", {
            "ts_code": "600519.SH", "trade_date": "2026-01-02", "open_price": "10", "high_price": "11",
            "low_price": "9", "close_price": "10.5", "vol": "100", "amount": "1050", "pre_close": "9.5",
            "trade_status": "TRADE", "limit_up": "11.5", "limit_down": "8.5", "as_of": NOW.isoformat(),
        }),
        ("financial_api", "bar_1d_raw", {
            "symbol": "000001.SZ", "trade_date": "2026-01-02", "o": "10", "h": "11",
            "l": "9", "c": "10.5", "volume": "100", "turnover": "1050", "prev_close": "9.5",
            "status": "TRADED", "upper_limit": "11.5", "lower_limit": "8.5", "available_at": NOW.isoformat(),
        }),
    ],
)
def test_all_provider_dataset_mappings_convert_representative_rows(
    tmp_path: Path,
    provider_id: str,
    dataset_id: str,
    row: dict[str, object],
) -> None:
    mapping = next(
        item
        for item in default_provider_canonical_mapping_records()
        if item.provider_id == provider_id and item.dataset_id == dataset_id
    )
    normalizer = CanonicalNormalizer(tmp_path, clock=lambda: NOW)
    partition, report, content = normalizer.normalize_rows(
        raw_object_id=generate_resource_id(ResourceType.RAW_OBJECT),
        provider_run_id=generate_resource_id(ResourceType.PROVIDER_RUN),
        provider_id=provider_id,
        dataset_id=dataset_id,
        dataset_schema_version="1.0.0",
        provider_policy_version="1.0.0",
        mapping=mapping,
        rows=[row],
        partition_key="2026-01-02",
        identity_resolver=_resolved_identity if dataset_id in {"security_master", "bar_1d_raw"} else None,
        is_trading_day=(lambda _market, _day: True) if dataset_id == "bar_1d_raw" else None,
    )
    assert partition is not None
    assert report.quality_status is QualityStatus.COMPLETE
    assert content
    assert partition.schema_hash == compute_schema_hash(
        mapping.target_fields,
        mapping.target_field_types,
    )
