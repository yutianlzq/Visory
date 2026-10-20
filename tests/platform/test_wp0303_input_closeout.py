"""WP-0303 B4 versioned references; no Provider or historical certification."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from src.services.platform.feature_dependency import (
    DEFAULT_DATASET_CATALOG,
    FeatureDependencyResolver,
    validate_definition_inputs,
)
from src.services.platform.indicator_registry import (
    F1_INDICATOR_DEFINITIONS,
    IndicatorRegistry,
    IndicatorResolutionError,
    default_indicator_registry,
)


CUTOFF = datetime(2026, 1, 3, 18, tzinfo=timezone.utc)


def halt_plan(**kwargs):
    registry = default_indicator_registry()
    instance = registry.create_instance("trading_halt_state", definition_version="2.0.0")
    return FeatureDependencyResolver(registry).resolve(
        (instance,), cutoff_at=CUTOFF, **kwargs
    )


def test_halt_v2_pins_actual_status_contract_and_preserves_legacy_rejection():
    registry = default_indicator_registry()
    legacy = registry.get("trading_halt_state", "1.0.0")
    assert legacy == F1_INDICATOR_DEFINITIONS["trading_halt_state"]
    assert registry.get("trading_halt_state") == legacy
    with pytest.raises(IndicatorResolutionError, match="INDICATOR_UNREGISTERED_INPUT"):
        validate_definition_inputs(legacy)

    current = registry.get("trading_halt_state", "2.0.0")
    assert current.definition_hash != legacy.definition_hash
    assert current.definition_hash == "sha256:ead447cc4d0dd07be2b11651789d6cea0ebfa3c13d9de26e406a2e054f2f22f0"
    assert current.output_schema == legacy.output_schema
    assert current.formula_ref == legacy.formula_ref
    assert current.implementation_hash == legacy.implementation_hash
    assert len(current.input_dataset_refs) == 1
    ref = current.input_dataset_refs[0]
    assert (ref.dataset_id, ref.schema_version) == ("instrument_status_daily", "1.0.0")
    assert ref.required_fields == (
        "entity_key", "status_date", "instrument_status", "is_tradable", "available_at"
    )
    validate_definition_inputs(current)
    plan = halt_plan()
    assert plan.dataset_refs == ("instrument_status_daily@1.0.0",)
    assert plan.ordered_instances[0].definition_version == "2.0.0"
    assert plan.plan_hash == halt_plan().plan_hash


def test_halt_v2_does_not_accept_fabricated_projection_or_future_input():
    registry = default_indicator_registry()
    instance = registry.create_instance("trading_halt_state", definition_version="2.0.0")
    view = DEFAULT_DATASET_CATALOG.get("instrument_status_daily", "1.0.0")
    catalog = dict(DEFAULT_DATASET_CATALOG.items())
    catalog[("instrument_status_daily", "1.0.0")] = replace(
        view, fields=dict(view.fields) | {"trade_date": "date"}
    )
    with pytest.raises(IndicatorResolutionError, match="INDICATOR_CATALOG_DRIFT"):
        FeatureDependencyResolver(registry, dataset_catalog=catalog).resolve((instance,))
    with pytest.raises(IndicatorResolutionError, match="INDICATOR_AVAILABLE_AFTER_CUTOFF"):
        halt_plan(dataset_available_at={
            "instrument_status_daily": CUTOFF + timedelta(seconds=1)
        })


def test_halt_v2_stays_provisional_and_does_not_unlock_missing_market_inputs():
    assert default_indicator_registry().get(
        "trading_halt_state", "2.0.0"
    ).publication_status.value == "PROVISIONAL"
    with pytest.raises(IndicatorResolutionError, match="INDICATOR_CAPABILITY_MISSING"):
        halt_plan(
            consumer_kind="FORMAL",
            available_capabilities=set(),
            dataset_available_at={"instrument_status_daily": CUTOFF},
        )
    for name in ("turnover_ratio", "return_point_in_time_adjusted"):
        with pytest.raises(IndicatorResolutionError, match="INDICATOR_UNREGISTERED_INPUT"):
            validate_definition_inputs(F1_INDICATOR_DEFINITIONS[name])


def test_registry_default_version_must_be_registered_and_never_falls_back():
    definitions = default_indicator_registry().list()
    with pytest.raises(ValueError, match="registered exact versions"):
        IndicatorRegistry(definitions, default_definition_versions={"trading_halt_state": "9.0.0"})
    registry = IndicatorRegistry(
        definitions, default_definition_versions={"trading_halt_state": "1.0.0"}
    )
    assert registry.create_instance("trading_halt_state").definition_version == "1.0.0"
    with pytest.raises(IndicatorResolutionError, match="INDICATOR_VERSION_UNKNOWN"):
        registry.get("trading_halt_state", "9.0.0")
