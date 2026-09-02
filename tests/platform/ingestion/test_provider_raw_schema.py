from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.schemas.platform import ProviderRawSchemaDefinition, compute_provider_raw_schema_hash
from src.services.platform.provider_registry import default_provider_raw_schema_records


NOW = datetime(2026, 9, 1, tzinfo=timezone.utc)


def test_provider_raw_schema_definition_is_independent_from_canonical_fields() -> None:
    records = default_provider_raw_schema_records(NOW)
    assert len(records) == 6
    security = next(
        record
        for record in records
        if record.provider_id == "a_stock_data" and record.dataset_id == "security_master"
    )
    assert "entity_key" not in security.required_fields
    assert "canonical_id" not in security.required_fields
    assert security.expected_schema_hash == compute_provider_raw_schema_hash(security)


def test_raw_schema_registry_covers_both_providers_and_all_datasets() -> None:
    records = default_provider_raw_schema_records(NOW)
    assert {(item.provider_id, item.dataset_id) for item in records} == {
        (provider, dataset)
        for provider in ("a_stock_data", "financial_api")
        for dataset in ("security_master", "trading_calendar", "bar_1d_raw")
    }
    assert len({item.expected_schema_hash for item in records}) == 6


def test_provider_raw_schema_rejects_hash_not_matching_definition() -> None:
    with pytest.raises(ValueError, match="expected_schema_hash"):
        ProviderRawSchemaDefinition(
            provider_id="a_stock_data",
            adapter_version="1.0.0",
            dataset_id="security_master",
            dataset_schema_version="1.0.0",
            provider_schema_version="1.0.0",
            required_fields=("ts_code",),
            optional_fields=(),
            field_types={"ts_code": "string"},
            expected_schema_hash="sha256:" + "0" * 64,
        )


def test_raw_schema_drift_classification_uses_provider_fields_and_types() -> None:
    from src.services.platform.raw_ingestion import classify_raw_schema
    from src.schemas.platform import RawSchemaDriftClassification

    schema = next(item for item in default_provider_raw_schema_records() if item.provider_id == "a_stock_data" and item.dataset_id == "security_master")
    assert classify_raw_schema(schema, schema.required_fields, schema.field_types) is RawSchemaDriftClassification.MATCHED
    assert classify_raw_schema(schema, schema.required_fields + ("new_field",), {**schema.field_types, "new_field": "string"}) is RawSchemaDriftClassification.ADDITIVE_DRIFT
    missing = tuple(field for field in schema.required_fields if field != "ts_code")
    assert classify_raw_schema(schema, missing, schema.field_types) is RawSchemaDriftClassification.BREAKING_DRIFT
    mismatched = dict(schema.field_types)
    mismatched["lot_size"] = "number"
    assert classify_raw_schema(schema, schema.required_fields, mismatched) is RawSchemaDriftClassification.BREAKING_DRIFT
