from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.schemas.platform import PLATFORM_CONTRACTS, compute_content_hash
from src.schemas.platform.indicator import (
    FeatureInstanceKey,
    IndicatorDefinition,
    IndicatorDependencyRef,
    IndicatorOutputDefinition,
    ParameterDefinition,
    PublicationStatus,
)
from src.services.platform.feature_dependency import (
    DEFAULT_DATASET_CATALOG,
    FeatureDependencyPlan,
    FeatureDependencyResolver,
    FeatureInstance,
    IndicatorResolutionError,
)
from src.services.platform.indicator_registry import (
    BUILTIN_REGISTRY,
    F1_INDICATOR_DEFINITIONS,
    BuiltinImplementation,
    IndicatorRegistry,
    default_indicator_registry,
)


UTC = timezone.utc
CUTOFF = datetime(2026, 1, 2, 8, 0, tzinfo=UTC)


def _definition(
    indicator_id: str = "test_indicator",
    *,
    formula_ref: str = "volume_shares_builtin",
    definition_version: str = "1.0.0",
    input_indicator_refs: tuple[IndicatorDependencyRef, ...] = (),
    input_dataset_refs: tuple[str, ...] = ("bar_1d_raw",),
    domain: str = "a_share",
    point_in_time: bool = True,
    universe_policy: str = "ENTITY",
    capability_id: str | None = "market_bars_daily",
    publication_status: PublicationStatus = PublicationStatus.CERTIFIED,
    parameter_schema: tuple[ParameterDefinition, ...] = (),
    normalized_default_parameters: dict[str, object] | None = None,
    deprecated_at: datetime | None = None,
) -> IndicatorDefinition:
    return IndicatorDefinition(
        indicator_id=indicator_id,
        name=indicator_id.replace("_", " "),
        domain=domain,
        frequency="1d",
        schema_version="1.0.0",
        definition_version=definition_version,
        formula_type="PYTHON_BUILTIN",
        formula_ref=formula_ref,
        input_dataset_refs=input_dataset_refs,
        input_indicator_refs=input_indicator_refs,
        lookback_requirement=20,
        warmup_requirement=20,
        output_schema=(
            IndicatorOutputDefinition(
                alias="value",
                value_type="decimal",
                unit="shares",
                nullable=True,
            ),
        ),
        parameter_schema=parameter_schema,
        normalized_default_parameters=normalized_default_parameters or {},
        recompute_policy="DAILY_INCREMENTAL",
        adjustment_policy="NONE",
        universe_policy=universe_policy,
        asof_policy="AVAILABLE_AT",
        materialization="F1_LONG_TERM",
        capability_id=capability_id,
        point_in_time=point_in_time,
        pit_review_version="1.0.0" if point_in_time else None,
        numeric_policy="DECIMAL",
        null_policy="PROPAGATE",
        owner="tests",
        publication_status=publication_status,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        deprecated_at=deprecated_at,
    )


def test_indicator_definition_is_immutable_and_definition_hash_is_stable() -> None:
    definition = _definition()
    same_definition = _definition()

    assert definition.definition_hash.startswith("sha256:")
    assert definition.definition_hash == same_definition.definition_hash
    with pytest.raises(ValidationError):
        definition.indicator_id = "changed"  # type: ignore[misc]


def test_definition_rejects_uncontrolled_formula_reference() -> None:
    with pytest.raises(ValidationError, match="formula_ref"):
        payload = _definition().model_dump()
        payload["formula_ref"] = "src.services.indicators:run"
        IndicatorDefinition(**payload)


def test_definition_rejects_duplicate_output_aliases_and_inconsistent_defaults() -> None:
    with pytest.raises(ValidationError, match="output aliases"):
        payload = _definition().model_dump()
        payload["output_schema"] = (
            IndicatorOutputDefinition(alias="value", value_type="decimal", unit="ratio"),
            IndicatorOutputDefinition(alias="value", value_type="decimal", unit="ratio"),
        )
        IndicatorDefinition(**payload)

    with pytest.raises(ValidationError, match="normalized_default_parameters"):
        _definition(
            parameter_schema=(ParameterDefinition(name="period", value_type="integer", required=False),),
            normalized_default_parameters={"unknown": 20},
        )


def test_builtin_registry_is_static_and_contains_the_first_f1_definitions() -> None:
    registry = default_indicator_registry()
    registered_ids = {item.indicator_id for item in registry.list()}

    assert set(F1_INDICATOR_DEFINITIONS) == registered_ids
    assert {
        "return_unadjusted",
        "return_point_in_time_adjusted",
        "moving_average",
        "volatility",
        "atr",
        "volume_shares",
        "amount_cny",
        "turnover_ratio",
        "adv20",
        "price_limit_state",
        "trading_halt_state",
        "listing_age_days",
        "basic_valuation",
        "financial_available_flag",
    } <= registered_ids
    assert set(BUILTIN_REGISTRY) >= {definition.formula_ref for definition in registry.list()}

    with pytest.raises(ValueError, match="unknown controlled builtin"):
        IndicatorRegistry((_definition(indicator_id="unknown_builtin", formula_ref="unregistered_builtin"),))


def test_parameter_normalization_preserves_integer_decimal_and_string_distinctions() -> None:
    definition = _definition(
        parameter_schema=(
            ParameterDefinition(name="period", value_type="integer", required=False),
            ParameterDefinition(name="threshold", value_type="decimal", required=False),
            ParameterDefinition(name="label", value_type="string", required=False),
        ),
        normalized_default_parameters={
            "period": 20,
            "threshold": Decimal("0.10"),
            "label": "20",
        },
    )
    base_builtin = BUILTIN_REGISTRY["volume_shares_builtin"]
    test_builtin = BuiltinImplementation(
        builtin_id="typed_test_builtin",
        implementation_version=base_builtin.implementation_version,
        implementation_hash=compute_content_hash({"builtin_id": "typed_test_builtin", "implementation_version": base_builtin.implementation_version}),
        callable=base_builtin.callable,
        supported_parameter_schema=definition.parameter_schema,
        output_schema=definition.output_schema,
    )
    payload = definition.model_dump()
    payload["formula_ref"] = "typed_test_builtin"
    payload["definition_hash"] = ""
    payload["formula_hash"] = ""
    payload["implementation_hash"] = test_builtin.implementation_hash
    definition = IndicatorDefinition(**payload)
    registry = IndicatorRegistry((definition,), builtins={"typed_test_builtin": test_builtin})

    integer_instance = registry.create_instance("test_indicator", {"period": 14})
    decimal_instance = registry.create_instance("test_indicator", {"period": 14, "threshold": Decimal("14")})
    string_instance = registry.create_instance("test_indicator", {"period": 14, "label": "14"})

    assert integer_instance.parameter_hash != decimal_instance.parameter_hash
    assert decimal_instance.parameter_hash != string_instance.parameter_hash
    assert integer_instance.canonical_parameter_json != decimal_instance.canonical_parameter_json

    with pytest.raises(IndicatorResolutionError) as error:
        registry.create_instance("test_indicator", {"period": 14.0})
    assert error.value.code == "INDICATOR_PARAMETER_INVALID"


def test_resolver_returns_stable_topological_order_and_plan_hash() -> None:
    base = _definition(indicator_id="base")
    derived = _definition(
        indicator_id="derived",
        input_indicator_refs=(IndicatorDependencyRef(indicator_id="base", definition_version="1.0.0"),),
    )
    registry = IndicatorRegistry((derived, base))
    resolver = FeatureDependencyResolver(registry, dataset_catalog=DEFAULT_DATASET_CATALOG)

    first = resolver.resolve(
        (FeatureInstance(indicator_id="derived", parameters={}),),
        cutoff_at=CUTOFF,
        available_capabilities={"market_bars_daily"},
    )
    second = resolver.resolve(
        (FeatureInstance(indicator_id="derived", parameters={}),),
        cutoff_at=CUTOFF,
        available_capabilities={"market_bars_daily"},
    )

    assert isinstance(first, FeatureDependencyPlan)
    assert [item.indicator_id for item in first.ordered_instances] == ["base", "derived"]
    assert first.plan_hash == second.plan_hash
    assert first.required_columns == ("base.value", "derived.value")


def test_resolver_fails_closed_for_unknown_dependency_and_cycle() -> None:
    missing = _definition(
        indicator_id="missing_parent",
        input_indicator_refs=(IndicatorDependencyRef(indicator_id="not_registered"),),
    )
    with pytest.raises(IndicatorResolutionError) as missing_error:
        FeatureDependencyResolver(IndicatorRegistry((missing,))).resolve(("missing_parent",))
    assert missing_error.value.code == "INDICATOR_DEPENDENCY_UNKNOWN"

    first = _definition(indicator_id="cycle_a", input_indicator_refs=(IndicatorDependencyRef(indicator_id="cycle_b"),))
    second = _definition(indicator_id="cycle_b", input_indicator_refs=(IndicatorDependencyRef(indicator_id="cycle_a"),))
    with pytest.raises(IndicatorResolutionError) as cycle_error:
        FeatureDependencyResolver(IndicatorRegistry((first, second))).resolve(("cycle_a",))
    assert cycle_error.value.code == "INDICATOR_DEPENDENCY_CYCLE"


def test_resolver_enforces_publication_capability_pit_cutoff_and_frozen_universe() -> None:
    draft = _definition(indicator_id="draft_indicator", publication_status=PublicationStatus.DRAFT)
    with pytest.raises(IndicatorResolutionError) as draft_error:
        FeatureDependencyResolver(IndicatorRegistry((draft,))).resolve(("draft_indicator",))
    assert draft_error.value.code == "INDICATOR_DEFINITION_NOT_PUBLISHED"

    pit = _definition(indicator_id="not_pit", point_in_time=False)
    with pytest.raises(IndicatorResolutionError) as pit_error:
        FeatureDependencyResolver(IndicatorRegistry((pit,))).resolve(("not_pit",), consumer_kind="FORMAL")
    assert pit_error.value.code == "INDICATOR_PIT_NOT_ALLOWED"

    definition = _definition(indicator_id="gated")
    resolver = FeatureDependencyResolver(IndicatorRegistry((definition,)))
    with pytest.raises(IndicatorResolutionError) as capability_error:
        resolver.resolve(("gated",), available_capabilities=set())
    assert capability_error.value.code == "INDICATOR_CAPABILITY_MISSING"

    with pytest.raises(IndicatorResolutionError) as cutoff_error:
        resolver.resolve(
            ("gated",),
            cutoff_at=CUTOFF,
            dataset_available_at={"bar_1d_raw": CUTOFF + timedelta(seconds=1)},
            available_capabilities={"market_bars_daily"},
        )
    assert cutoff_error.value.code == "INDICATOR_AVAILABLE_AFTER_CUTOFF"

    cross_sectional = _definition(indicator_id="cross_sectional", universe_policy="FROZEN_REQUIRED")
    with pytest.raises(IndicatorResolutionError) as universe_error:
        FeatureDependencyResolver(IndicatorRegistry((cross_sectional,))).resolve(("cross_sectional",))
    assert universe_error.value.code == "INDICATOR_UNIVERSE_NOT_FROZEN"


def test_c006_contracts_are_registered_without_creating_runtime_api_routes() -> None:
    indicator = PLATFORM_CONTRACTS.get("C-006/IndicatorDefinition")
    plan = PLATFORM_CONTRACTS.get("C-006/FeatureDependencyPlan")

    assert indicator.schema_model is IndicatorDefinition
    assert plan.schema_model is FeatureDependencyPlan
    assert all(path.startswith("tests/golden/platform/contracts/") for path in indicator.golden_payloads)
    assert all(path.startswith("tests/golden/platform/contracts/") for path in plan.golden_payloads)


def test_golden_contract_payloads_exist_for_c006() -> None:
    root = Path(__file__).resolve().parents[1] / "golden" / "platform" / "contracts"
    for contract_id in ("C-006/IndicatorDefinition", "C-006/FeatureDependencyPlan"):
        registration = PLATFORM_CONTRACTS.get(contract_id)
        assert registration.golden_payloads
        for relative_path in registration.golden_payloads:
            assert (Path(__file__).resolve().parents[2] / relative_path).is_file(), relative_path




def test_registry_rejects_unknown_definition_version_and_builtin_schema_mismatch() -> None:
    definition = _definition()
    registry = IndicatorRegistry((definition,))

    with pytest.raises(IndicatorResolutionError) as version_error:
        registry.get("test_indicator", "2.0.0")
    assert version_error.value.code == "INDICATOR_VERSION_UNKNOWN"

    base_builtin = BUILTIN_REGISTRY["volume_shares_builtin"]
    incompatible_builtin = BuiltinImplementation(
        builtin_id=base_builtin.builtin_id,
        implementation_version=base_builtin.implementation_version,
        implementation_hash=base_builtin.implementation_hash,
        callable=base_builtin.callable,
        supported_parameter_schema=(ParameterDefinition(name="period", value_type="integer"),),
        output_schema=base_builtin.output_schema,
    )
    with pytest.raises(ValueError, match="parameter schema mismatch"):
        IndicatorRegistry((definition,), builtins={base_builtin.builtin_id: incompatible_builtin})


def test_definition_rejects_pit_review_version_for_non_pit_definition() -> None:
    payload = _definition(point_in_time=True).model_dump()
    payload["point_in_time"] = False
    payload["pit_review_version"] = "1.0.0"
    payload["definition_hash"] = ""
    with pytest.raises(ValidationError, match="non-point-in-time"):
        IndicatorDefinition(**payload)


def test_resolver_enforces_definition_version_lifecycle_domain_and_available_at_gates() -> None:
    retired = _definition(
        indicator_id="retired_indicator",
        publication_status=PublicationStatus.RETIRED,
        deprecated_at=datetime(2026, 2, 1, tzinfo=UTC),
    )
    resolver = FeatureDependencyResolver(IndicatorRegistry((retired,)))

    with pytest.raises(IndicatorResolutionError) as retired_error:
        resolver.resolve(("retired_indicator",), available_capabilities={"market_bars_daily"})
    assert retired_error.value.code == "INDICATOR_DEFINITION_NOT_PUBLISHED"

    plan = resolver.resolve(
        ("retired_indicator",),
        allow_retired=True,
        available_capabilities={"market_bars_daily"},
    )
    assert plan.ordered_instances[0].indicator_id == "retired_indicator"

    global_definition = _definition(indicator_id="global_indicator", domain="global")
    global_resolver = FeatureDependencyResolver(IndicatorRegistry((global_definition,)))
    with pytest.raises(IndicatorResolutionError) as domain_error:
        global_resolver.resolve(
            ("global_indicator",),
            allowed_domains={"a_share"},
            available_capabilities={"market_bars_daily"},
        )
    assert domain_error.value.code == "INDICATOR_GLOBAL_DOMAIN_NOT_ALLOWED"

    with pytest.raises(IndicatorResolutionError) as available_error:
        resolver.resolve(
            ("retired_indicator",),
            allow_retired=True,
            consumer_kind="FORMAL",
            cutoff_at=CUTOFF,
            available_capabilities={"market_bars_daily"},
        )
    assert available_error.value.code == "INDICATOR_AVAILABLE_AT_MISSING"


def test_feature_instance_key_rejects_noncanonical_or_mismatched_parameter_hash() -> None:
    with pytest.raises(ValidationError, match="parameter_hash"):
        FeatureInstanceKey(
            indicator_id="moving_average",
            definition_version="1.0.0",
            canonical_parameter_json='{"period":20}',
            parameter_hash=compute_content_hash({"period": 21}),
            frequency="1d",
        )


def test_resolver_rejects_mixed_root_universe_scopes() -> None:
    first = _definition(indicator_id="first")
    second = _definition(indicator_id="second")
    registry = IndicatorRegistry((first, second))
    resolver = FeatureDependencyResolver(registry)
    with pytest.raises(IndicatorResolutionError) as error:
        resolver.resolve(
            (
                FeatureInstance(indicator_id="first", universe_scope_hash="sha256:" + "1" * 64),
                FeatureInstance(indicator_id="second", universe_scope_hash="sha256:" + "2" * 64),
            ),
            available_capabilities={"market_bars_daily"},
        )
    assert error.value.code == "INDICATOR_UNIVERSE_MISMATCH"


@pytest.mark.parametrize("allowed_domains", [None, {"a_share"}, {"a_share", "global"}])
def test_resolver_never_admits_global_definitions_into_a_share_plans(allowed_domains) -> None:
    registry = IndicatorRegistry((_definition(domain="global"),))
    with pytest.raises(IndicatorResolutionError, match="INDICATOR_GLOBAL_DOMAIN_NOT_ALLOWED"):
        FeatureDependencyResolver(registry).resolve(("test_indicator",), allowed_domains=allowed_domains)


def test_resolver_rejects_global_dataset_catalog_by_default() -> None:
    from dataclasses import replace

    catalog = dict(DEFAULT_DATASET_CATALOG)
    catalog["bar_1d_raw"] = replace(catalog["bar_1d_raw"], domain="global")
    resolver = FeatureDependencyResolver(IndicatorRegistry((_definition(),)), dataset_catalog=catalog)
    with pytest.raises(IndicatorResolutionError, match="INDICATOR_GLOBAL_DOMAIN_NOT_ALLOWED"):
        resolver.resolve(("test_indicator",))
