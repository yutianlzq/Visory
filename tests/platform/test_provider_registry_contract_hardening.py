from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from src.schemas.platform import DatasetDefinition, ProviderDefinition
from src.services.platform.provider_registry import DEFAULT_REGISTRY_TIMESTAMP, default_registry_records


def test_default_registry_contracts_are_explicit_and_deterministic() -> None:
    first = default_registry_records()
    second = default_registry_records()
    assert first == second
    assert first[0][0].created_at == DEFAULT_REGISTRY_TIMESTAMP
    datasets = {item.dataset_id: item for item in first[1]}
    assert set(datasets) == {"security_master", "trading_calendar", "bar_1d_raw"}
    bars = datasets["bar_1d_raw"]
    assert {"volume_shares", "amount_cny", "prev_close", "trading_status", "price_limit_up", "price_limit_down", "available_at"} <= set(bars.required_fields)
    assert "volume" not in bars.field_types
    assert "turnover" not in bars.field_types
    for dataset in datasets.values():
        declared = set(dataset.required_fields) | set(dataset.optional_fields)
        assert set(dataset.field_types) == declared
        assert set(dataset.units) == declared
        assert set(dataset.null_semantics) == declared
        assert set(dataset.time_semantics) == declared
        assert set(dataset.primary_key_fields) <= set(dataset.required_fields)


def test_dataset_definition_rejects_incomplete_explicit_metadata() -> None:
    _, datasets, _, _ = default_registry_records()
    payload = datasets[2].model_dump()
    payload["units"] = dict(payload["units"])
    payload["units"].pop("close")
    with pytest.raises(ValidationError, match="units must explicitly cover"):
        DatasetDefinition.model_validate(payload)


def test_dataset_definition_rejects_ambiguous_legacy_fields() -> None:
    _, datasets, _, _ = default_registry_records()
    payload = datasets[2].model_dump()
    payload["required_fields"] = tuple(payload["required_fields"]) + ("volume",)
    payload["field_types"] = dict(payload["field_types"], volume="number")
    payload["units"] = dict(payload["units"], volume="shares")
    payload["null_semantics"] = dict(payload["null_semantics"], volume="nullable_when_not_traded")
    payload["time_semantics"] = dict(payload["time_semantics"], volume="session_observation")
    with pytest.raises(ValidationError):
        DatasetDefinition.model_validate(payload)


def test_provider_definition_has_no_actual_upstream_placeholder() -> None:
    providers, _, capabilities, policies = default_registry_records(datetime(2026, 8, 31, tzinfo=timezone.utc))
    assert not hasattr(providers[0], "actual_upstream")
    assert all(item.dataset_schema_version == "1.0.0" for item in capabilities)
    assert all(item.dataset_schema_version == "1.0.0" for item in policies)
    assert not hasattr(ProviderDefinition, "actual_upstream")
