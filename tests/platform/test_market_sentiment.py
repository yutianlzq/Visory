from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from src.services.platform.feature_dependency import DEFAULT_DATASET_CATALOG, FeatureDependencyResolver
from src.services.platform.indicator_registry import default_indicator_registry, IndicatorResolutionError
from src.services.platform.provider_registry import _dataset_contracts


def test_catalog_projects_only_real_dataset_fields():
    actual = {(d.dataset_id, d.schema_version): d for d in _dataset_contracts()}
    for key, view in DEFAULT_DATASET_CATALOG.items():
        assert set(view.fields) == set(actual[key].field_types)
        assert view.schema_version == actual[key].schema_version
    assert "return_type" in DEFAULT_DATASET_CATALOG.get("benchmark_index_1d", "1.0.0").fields
    assert "shares_outstanding" not in DEFAULT_DATASET_CATALOG.get("security_master", "1.0.0").fields
    assert "factor" not in DEFAULT_DATASET_CATALOG.get("corporate_action", "1.0.0").fields


@pytest.mark.parametrize("name", ["return_point_in_time_adjusted", "turnover_ratio", "trading_halt_state"])
def test_legacy_f1_contract_drift_is_blocked_not_rewritten(name):
    with pytest.raises(IndicatorResolutionError, match="INDICATOR_UNREGISTERED_INPUT"):
        FeatureDependencyResolver(default_indicator_registry()).resolve([name])


def test_catalog_cannot_invent_factor_to_unlock_legacy_definition():
    catalog = dict(DEFAULT_DATASET_CATALOG)
    key = ("corporate_action", "1.0.0")
    catalog[key] = replace(
        catalog[key], fields={**catalog[key].fields, "factor": "decimal"}
    )
    with pytest.raises(IndicatorResolutionError, match="CATALOG"):
        FeatureDependencyResolver(default_indicator_registry(), dataset_catalog=catalog).resolve(
            ["return_point_in_time_adjusted"]
        )


def test_registered_market_definition_uses_documented_single_value_identity():
    definition = default_indicator_registry().get("market.sentiment.audit.listed_count", "1.0.0")
    assert definition.domain == "a_share"
    assert definition.materialization == "F2_LONG_TERM"
    assert definition.universe_policy == "FROZEN_REQUIRED"
    assert definition.capability_id == "backtest_core"
    assert len(definition.output_schema) == 1
    assert definition.output_schema[0].alias == "value"


def test_normalization_strict_t_minus_one_and_warming_up():
    from src.services.platform.market_sentiment import MetricPoint, normalize_metric
    from datetime import timedelta

    today = date(2026, 6, 1)
    cutoff = datetime(2026, 6, 1, 18, tzinfo=timezone.utc)
    history = [MetricPoint(today - timedelta(days=i), Decimal(i), cutoff) for i in range(1, 61)]
    assert normalize_metric(Decimal(61), history, trade_date=today, cutoff_at=cutoff).value > 50
    assert normalize_metric(Decimal(61), history[:59], trade_date=today, cutoff_at=cutoff).flags == ("WARMING_UP",)
    with pytest.raises(ValueError, match="T-1"):
        normalize_metric(
            Decimal(61), history + [MetricPoint(today, Decimal(1), cutoff)], trade_date=today, cutoff_at=cutoff
        )
    with pytest.raises(ValueError, match="cutoff"):
        normalize_metric(
            Decimal(61),
            [replace(p, available_at=cutoff + timedelta(seconds=1)) for p in history],
            trade_date=today,
            cutoff_at=cutoff,
        )


@pytest.mark.parametrize(
    "score,state",
    [("0", "PANIC"), ("20", "WEAK"), ("40", "RANGE"), ("60", "ACTIVE"), ("80", "OVERHEATED"), ("100", "OVERHEATED")],
)
def test_regime_boundaries(score, state):
    from src.services.platform.market_sentiment import emotion_sequence

    result = emotion_sequence([Decimal(score)])[0]
    assert result.state == state
    assert result.trigger == "INITIALIZED"


def test_regime_confirmation_jump_and_gap():
    from src.services.platform.market_sentiment import regime_sequence, emotion_sequence

    results = regime_sequence([Decimal(59), Decimal(60), Decimal(60), None, Decimal(60), Decimal(55)])
    assert [r.state for r in results] == ["RANGE", "RANGE", "ACTIVE", None, "ACTIVE", "RANGE"]
    assert results[2].trigger == "TWO_DAY_CONFIRM"
    assert results[5].trigger == "BOUNDARY_JUMP_GE_5"
    smoothed = emotion_sequence([Decimal(20), Decimal(60), None, Decimal(80)])
    assert [r.smoothed for r in smoothed] == [Decimal(20), Decimal(40), None, Decimal(80)]


def test_fixed_five_weights_and_missing_not_reweighted():
    from src.services.platform.market_sentiment import composite_emotion

    values = {
        "breadth": Decimal(10),
        "limit": Decimal(20),
        "risk_appetite": Decimal(30),
        "liquidity": Decimal(40),
        "safety": Decimal(50),
    }
    assert composite_emotion(values).value == Decimal("25.5")
    values["safety"] = None
    assert composite_emotion(values).value is None
    assert composite_emotion(values).missing == ("market.sentiment.score.safety",)


def market_day(day=None, closes=("10", "11", "9")):
    from datetime import timedelta
    from src.schemas.platform import ResourceType, generate_resource_id
    from src.services.platform.market_sentiment import MarketDay

    day = day or date(2026, 1, 1)
    cutoff = datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=18)
    keys = ["stock:sh600001", "stock:sz000001", "stock:sz300001"]
    datasets = {
        "security_master": [
            dict(
                entity_key=k,
                asset_type="stock",
                exchange="SH" if i == 0 else "SZ",
                board="MAIN",
                list_date=date(2020, 1, 1),
                available_at=cutoff,
            )
            for i, k in enumerate(keys)
        ],
        "listing_status_history": [
            dict(entity_key=k, listing_status="LISTED", effective_from=date(2020, 1, 1), available_at=cutoff)
            for k in keys
        ],
        "instrument_status_daily": [
            dict(entity_key=k, status_date=day, instrument_status="ACTIVE", is_tradable=True, available_at=cutoff)
            for k in keys
        ],
        "trading_calendar": [dict(market="CN", trade_date=day, is_open=True, available_at=cutoff)],
        "bar_1d_raw": [
            dict(
                entity_key=k,
                trade_date=day,
                open=Decimal(10),
                high=Decimal(11),
                low=Decimal(9),
                close=Decimal(closes[i]),
                volume_shares=Decimal(100),
                amount_cny=Decimal((i + 1) * 100),
                prev_close=Decimal(10),
                price_limit_up=Decimal(11),
                price_limit_down=Decimal(9),
                trading_status="TRADED",
                available_at=cutoff,
            )
            for i, k in enumerate(keys)
        ],
    }
    return MarketDay(
        day,
        cutoff,
        generate_resource_id(ResourceType.DATA_SNAPSHOT, timestamp_ms=1, random_bits=1),
        (generate_resource_id(ResourceType.CANONICAL_PARTITION, timestamp_ms=1, random_bits=2),),
        datasets,
    )


def test_real_raw_metrics_and_missing_composite():
    from src.services.platform.market_sentiment import evaluate_market_days

    batch = evaluate_market_days([market_day()])[0]
    assert batch.results["audit.listed_count"].value == 3
    assert batch.results["limit.limit_up_count"].value == 1
    assert batch.results["limit.limit_down_count"].value == 1
    assert batch.results["limit.limit_break_count"].value == 2
    assert batch.results["limit.limit_break_rate"].value == Decimal(2) / 3
    assert batch.results["liquidity.market_amount_cny"].value == 600
    assert batch.results["risk.median_amplitude"].value == Decimal(".2")
    for key in ("score.emotion_raw", "score.emotion_smoothed", "regime.state"):
        assert batch.results[key].value is None
    assert all(row.entity_key == "aggregate:cn_a_equity_v1" for row in batch.rows)


def test_real_definition_dag_and_unavailable_diagnostic_plan():
    from src.services.platform.market_sentiment import PREFIX

    resolver = FeatureDependencyResolver(default_indicator_registry())
    with pytest.raises(IndicatorResolutionError, match="NOT_FROZEN"):
        resolver.resolve([PREFIX + "audit.listed_count"])
    with pytest.raises(IndicatorResolutionError, match="UNREGISTERED_INPUT"):
        resolver.resolve([PREFIX + "score.emotion_raw"], universe_scope_hash="sha256:" + "1" * 64)
    plan = resolver.resolve(
        [PREFIX + "score.emotion_raw"], universe_scope_hash="sha256:" + "1" * 64, allow_unavailable=True
    )
    assert plan.ordered_instances[-1].indicator_id == PREFIX + "score.emotion_raw"
    assert len(plan.dependency_edges) > 10


def publish_market(store, batch, roots=None, **kwargs):
    from src.services.platform.market_sentiment import PREFIX

    roots = roots or [PREFIX + "audit.listed_count"]
    plan = FeatureDependencyResolver(default_indicator_registry()).resolve(
        roots,
        cutoff_at=batch.rows[0].available_at,
        universe_scope_hash=batch.manifest.universe_scope_hash,
        allow_unavailable=True,
    )
    mapping = {
        key: tuple(row for row in batch.rows if row.indicator_id == key.indicator_id) for key in plan.ordered_instances
    }
    snapshot, bundle = store.materialize_and_publish(
        plan,
        mapping,
        data_snapshot_ids=(batch.manifest.data_snapshot_id,),
        cutoff_at=plan.cutoff_at,
        as_of_trade_date=batch.manifest.trade_date,
        consumer_ref="test_market",
        **kwargs,
    )
    return plan, snapshot, bundle


def test_real_publication_and_formal_paper_consumption_remain_closed(tmp_path):
    from src.services.platform.feature_store import FeatureStore, FeaturePublicationError
    from src.services.platform.market_sentiment import evaluate_market_days, PREFIX
    from src.schemas.platform import ConsumerRequirement

    batch = evaluate_market_days([market_day()])[0]
    store = FeatureStore(tmp_path, clock=lambda: batch.rows[0].available_at)
    _, snapshot, bundle = publish_market(store, batch, [PREFIX + "score.emotion_raw", PREFIX + "regime.state"])
    assert snapshot.publication_status.value == "PROVISIONAL"
    assert snapshot.missing_capabilities == ("market_breadth", "market_emotion")
    assert snapshot.certified_capabilities == ()
    for consumer in ("formal_backtest", "paper"):
        requirement = ConsumerRequirement(
            consumer_id=consumer,
            consumer_kind="FORMAL_BACKTEST",
            required_capabilities=("backtest_core", "market_emotion"),
            accepted_publication_statuses=("CERTIFIED",),
        )
        with pytest.raises(FeaturePublicationError, match="capability"):
            store.consume_bundle(bundle.feature_bundle_id, requirement)
    with pytest.raises(FeaturePublicationError, match="market"):
        publish_market(
            store,
            batch,
            consumer_kind="FORMAL_BACKTEST",
            expected_entity_keys=("aggregate:cn_a_equity_v1",),
            expected_trade_dates=(batch.manifest.trade_date,),
        )


def test_scope_freezing_exclusions_pit_and_per_metric_denominators():
    from src.services.platform.market_sentiment import evaluate_market_days, freeze_market_scope
    from datetime import timedelta

    base = market_day()
    datasets = {k: [dict(row) for row in rows] for k, rows in base.datasets.items()}
    datasets["bar_1d_raw"][0]["price_limit_up"] = None
    changed = replace(base, datasets=datasets)
    batch = evaluate_market_days([changed])[0]
    assert batch.results["audit.listed_count"].value == 3
    assert batch.results["audit.limit_rule_count"].value == 2
    assert batch.results["risk.median_amplitude"].denominator_count == 3
    assert batch.results["limit.limit_break_rate"].denominator_count == 2
    assert freeze_market_scope(changed).universe_scope_hash != freeze_market_scope(base).universe_scope_hash
    for name in datasets:
        reversed_inputs = {**datasets, name: list(reversed(datasets[name]))}
        assert (
            freeze_market_scope(replace(base, datasets=reversed_inputs)).universe_scope_hash
            == batch.manifest.universe_scope_hash
        )
    datasets["bar_1d_raw"][0]["available_at"] = base.cutoff_at + timedelta(seconds=1)
    with pytest.raises(ValueError, match="cutoff"):
        evaluate_market_days([replace(base, datasets=datasets)])


def test_zero_denominator_no_ohlc_seal_guess_and_no_status_fallback():
    from src.services.platform.market_sentiment import evaluate_market_days

    base = market_day()
    datasets = {k: [dict(row) for row in rows] for k, rows in base.datasets.items()}
    for row in datasets["bar_1d_raw"]:
        row["price_limit_up"] = row["price_limit_down"] = None
    datasets["instrument_status_daily"] = []
    batch = evaluate_market_days([replace(base, datasets=datasets)])[0]
    assert batch.results["limit.limit_up_down_spread"].value is None
    assert batch.results["limit.limit_break_rate"].value is None
    assert batch.results["limit.early_seal_ratio"].value is None
    assert batch.results["liquidity.zero_or_suspended_ratio"].value is None


def test_amount_ratio_t_minus_one_streak_prior_candidates_and_open_calendar():
    from src.services.platform.market_sentiment import evaluate_market_days
    from datetime import timedelta

    days = [
        market_day(date(2026, 1, 1) + timedelta(days=i), ("10", "10", "10") if i == 0 else ("11", "10", "10"))
        for i in range(21)
    ]
    dates = tuple(d.trade_date for d in days)
    batches = evaluate_market_days(days, open_trade_dates=dates)
    assert batches[0].results["limit.max_streak_height"].value == 0
    assert batches[2].results["limit.max_streak_height"].value == 2
    assert batches[2].results["limit.promotion_rate"].value is None
    assert batches[3].results["limit.promotion_rate"].value == 1
    assert batches[19].results["liquidity.amount_ratio_20"].value is None
    assert batches[20].results["liquidity.amount_ratio_20"].value == 1
    with pytest.raises(ValueError, match="open trading"):
        evaluate_market_days(days[:5] + days[6:], open_trade_dates=dates)


def test_real_store_rejects_forged_nonnull_score_or_mixed_scope(tmp_path):
    from src.services.platform.market_sentiment import evaluate_market_days, PREFIX
    from src.services.platform.feature_store import FeatureStore, FeatureMaterializationError

    batch = evaluate_market_days([market_day()])[0]
    bad_rows = tuple(
        row.model_copy(update={"value": Decimal(50)}) if row.indicator_id == PREFIX + "score.emotion_raw" else row
        for row in batch.rows
    )
    store = FeatureStore(tmp_path, clock=lambda: batch.rows[0].available_at)
    with pytest.raises(FeatureMaterializationError, match="unavailable"):
        publish_market(store, replace(batch, rows=bad_rows), [PREFIX + "score.emotion_raw"])
    mixed = tuple(row.model_copy(update={"entity_key": "stock:sh600519"}) for row in batch.rows)
    with pytest.raises(FeatureMaterializationError, match="scope"):
        publish_market(store, replace(batch, rows=mixed))


def test_definition_contract_is_fixed_and_f1_hashes_unchanged():
    import json
    import subprocess
    from src.services.platform.indicator_registry import (
        F1_INDICATOR_DEFINITIONS,
        F2_INDICATOR_DEFINITIONS,
        BUILTIN_REGISTRY,
    )

    original = subprocess.check_output(["git", "show", "HEAD:src/services/platform/indicator_registry.py"], text=True)
    import sys
    from types import ModuleType

    module = ModuleType("src.services.platform.baseline_registry")
    module.__package__ = "src.services.platform"
    sys.modules[module.__name__] = module
    namespace = module.__dict__
    try:
        exec(compile(original, "<baseline-registry>", "exec"), namespace)
    finally:
        del sys.modules[module.__name__]
    for key, definition in F1_INDICATOR_DEFINITIONS.items():
        assert definition == namespace["F1_INDICATOR_DEFINITIONS"][key]
        assert definition.definition_hash == namespace["F1_INDICATOR_DEFINITIONS"][key].definition_hash
    for definition in F2_INDICATOR_DEFINITIONS.values():
        assert definition.definition_hash == type(definition).model_validate(definition.model_dump()).definition_hash
        assert definition.formula_ref in BUILTIN_REGISTRY
        contract = json.loads(definition.normalized_default_parameters["contract"])
        if contract["state"] != "DERIVED":
            assert contract["formula"] and contract["denominator"]
        with pytest.raises(IndicatorResolutionError):
            default_indicator_registry().create_instance(definition.indicator_id, {"contract": "override"})
    assert len(F1_INDICATOR_DEFINITIONS) == 14


def test_preview_consumes_fixed_bundle_and_fixture_requires_explicit_mark(tmp_path):
    from src.services.platform.market_sentiment import evaluate_market_days
    from src.services.platform.feature_store import FeatureStore, FeatureMaterializationError, FeaturePublicationError
    from src.schemas.platform import ConsumerRequirement

    batch = evaluate_market_days([market_day()])[0]
    requirement = ConsumerRequirement(
        consumer_id="preview",
        consumer_kind="PREVIEW",
        required_capabilities=("market_emotion",),
        allow_provisional=True,
        min_quality_status="PARTIAL",
        accepted_publication_statuses=("PROVISIONAL",),
    )
    store = FeatureStore(tmp_path / "real", clock=lambda: batch.rows[0].available_at)
    _, snapshot, bundle = publish_market(store, batch)
    assert store.consume_bundle(bundle.feature_bundle_id, requirement) == bundle
    with pytest.raises(FeaturePublicationError, match="latest"):
        store.consume_bundle("latest", requirement)
    fixture_store = FeatureStore(tmp_path / "fixture", fixture_only=True, clock=lambda: batch.rows[0].available_at)
    with pytest.raises(FeatureMaterializationError, match="FIXTURE_ONLY"):
        publish_market(fixture_store, batch)


def test_diagnostic_plan_cannot_unlock_a_forged_market_definition():
    from src.services.platform.indicator_registry import IndicatorRegistry

    payload = default_indicator_registry().get("market.sentiment.breadth.median_return").model_dump()
    payload["name"] = "forged"
    payload["definition_hash"] = ""
    definition = type(default_indicator_registry().get(payload["indicator_id"])).model_validate(payload)
    resolver = FeatureDependencyResolver(IndicatorRegistry((definition,)))
    with pytest.raises(IndicatorResolutionError, match="market definition"):
        resolver.resolve([definition.indicator_id], universe_scope_hash="sha256:" + "1" * 64, allow_unavailable=True)


def test_unknown_prior_streak_never_becomes_a_zero_candidate():
    from src.services.platform.market_sentiment import evaluate_market_days
    from datetime import timedelta

    days = [market_day(date(2026, 1, 1) + timedelta(days=i), ("11", "10", "10")) for i in range(3)]
    result = evaluate_market_days(days, open_trade_dates=tuple(day.trade_date for day in days))[-1].results[
        "limit.promotion_rate"
    ]
    assert result.value is None
    assert "HISTORY_GAP" in result.flags


def test_normalization_252_mad_zero_reverse_duplicate_and_numeric_guards():
    from datetime import timedelta
    from src.services.platform.market_sentiment import MetricPoint, normalize_metric

    today = date(2026, 9, 1)
    cutoff = datetime(2026, 9, 1, 18, tzinfo=timezone.utc)
    history = [MetricPoint(today - timedelta(days=i), Decimal(5), cutoff) for i in range(1, 253)]
    assert normalize_metric(Decimal(5), history, trade_date=today, cutoff_at=cutoff).value == 50
    assert normalize_metric(Decimal(6), history, trade_date=today, cutoff_at=cutoff).value == 100
    assert normalize_metric(Decimal(6), history, trade_date=today, cutoff_at=cutoff, negative=True).value == 0
    assert (
        normalize_metric(
            Decimal(5),
            history + [MetricPoint(today - timedelta(days=253), Decimal(99999), cutoff)],
            trade_date=today,
            cutoff_at=cutoff,
        ).value
        == 50
    )
    with pytest.raises(ValueError, match="duplicate"):
        normalize_metric(Decimal(5), history + [history[0]], trade_date=today, cutoff_at=cutoff)
    for value in (True, 1.0, Decimal("NaN")):
        with pytest.raises(ValueError):
            normalize_metric(value, history, trade_date=today, cutoff_at=cutoff)


@pytest.mark.parametrize("dimension", ["breadth", "limit", "risk_appetite", "liquidity", "safety"])
def test_dimension_missing_each_input_never_reweights(dimension):
    from src.services.platform.market_sentiment import DIMENSION_WEIGHTS, weighted_score, PREFIX

    weights = DIMENSION_WEIGHTS[dimension]
    full = {key: Decimal(50) for key in weights}
    assert weighted_score(full, weights, namespace=PREFIX + "normalized.").value == 50
    for key in weights:
        result = weighted_score(full | {key: None}, weights, namespace=PREFIX + "normalized.")
        assert result.value is None
        assert result.missing == (PREFIX + "normalized." + key,)


def test_state_direction_reversal_cross_level_and_missing_pending():
    from src.services.platform.market_sentiment import regime_sequence, emotion_sequence

    points = regime_sequence(
        [Decimal(39), Decimal(40), Decimal(39), Decimal(40), Decimal(40), Decimal(85), Decimal(15)]
    )
    assert [p.state for p in points] == ["WEAK", "WEAK", "WEAK", "WEAK", "RANGE", "OVERHEATED", "PANIC"]
    assert points[-1].trigger == "BOUNDARY_JUMP_GE_5"
    points = regime_sequence([Decimal(39), Decimal(40), None, Decimal(40)])
    assert points[-1].trigger == "INITIALIZED"
    with pytest.raises(ValueError):
        emotion_sequence([Decimal(101)])


def test_multi_day_history_requires_authoritative_open_calendar():
    from datetime import timedelta
    from src.services.platform.market_sentiment import evaluate_market_days

    days = [market_day(), market_day(date(2026, 1, 1) + timedelta(days=3))]
    with pytest.raises(ValueError, match="open trading"):
        evaluate_market_days(days)
    assert len(evaluate_market_days(days, open_trade_dates=tuple(day.trade_date for day in days))) == 2


def complete_score_fixture(*, correction=False):
    """合成全输入算法，不声称真实 Dataset 可用。固定测试 scope 仅用于隔离 Store。"""
    from datetime import timedelta
    from src.services.platform.market_sentiment import (
        NORMALIZED_METRICS,
        NEGATIVE_METRICS,
        DIMENSION_WEIGHTS,
        MetricPoint,
        normalize_metric,
        weighted_score,
        composite_emotion,
        emotion_sequence,
        PREFIX,
    )
    from src.schemas.platform import FeatureRow
    from src.services.platform.indicator_registry import F2_INDICATOR_DEFINITIONS

    dates = [date(2026, 1, 1) + timedelta(days=i) for i in range(65)]
    cutoff = datetime(2026, 3, 6, 18, tzinfo=timezone.utc)
    source = market_day().data_snapshot_id
    scope_hash = "sha256:" + "a" * 64
    input_values = [Decimal(40 + i % 10) for i in range(60)] + list(map(Decimal, (49, 51, 52, 52, 53)))
    if correction:
        input_values[60] = Decimal(0)
    normalized, raw_scores = [], []
    for i, day in enumerate(dates):
        values = {}
        for key in NORMALIZED_METRICS:
            direction = -1 if key in NEGATIVE_METRICS else 1
            history = [MetricPoint(dates[j], input_values[j] * direction, cutoff) for j in range(i)]
            values[key] = normalize_metric(
                input_values[i] * direction, history, trade_date=day, cutoff_at=cutoff, negative=direction == -1
            ).value
        normalized.append(values)
        dimensions = {
            key: weighted_score(values, weights, namespace=PREFIX + "normalized.").value
            for key, weights in DIMENSION_WEIGHTS.items()
        }
        raw_scores.append(composite_emotion(dimensions).value)
    emotion = emotion_sequence(raw_scores)
    plan = FeatureDependencyResolver(default_indicator_registry()).resolve(
        [PREFIX + "regime.state"], cutoff_at=cutoff, universe_scope_hash=scope_hash, allow_unavailable=True
    )
    rows = {}
    for instance in plan.ordered_instances:
        metric = instance.indicator_id[len(PREFIX) :]
        output = F2_INDICATOR_DEFINITIONS[instance.indicator_id].output_schema[0]
        values = []
        for i in range(60, 65):
            if metric.startswith("normalized."):
                value = normalized[i][metric[len("normalized.") :]]
            elif metric == "score.emotion_raw":
                value = raw_scores[i]
            elif metric == "score.emotion_smoothed":
                value = emotion[i].smoothed
            elif metric == "regime.state":
                value = emotion[i].state
            elif metric.startswith("score."):
                dimension = metric[len("score.") :]
                value = weighted_score(
                    normalized[i], DIMENSION_WEIGHTS[dimension], namespace=PREFIX + "normalized."
                ).value
            else:
                value = 1 if output.value_type == "integer" else input_values[i]
            if isinstance(value, Decimal):
                value = value.quantize(Decimal("1e-12"))
            values.append(
                FeatureRow(
                    entity_key="aggregate:cn_a_equity_v1",
                    trade_date=dates[i],
                    indicator_id=instance.indicator_id,
                    definition_version="1.0.0",
                    value=value,
                    value_type=output.value_type,
                    unit=output.unit,
                    available_at=cutoff,
                    data_snapshot_id=source,
                    calculation_run_id="wp0303-algorithm-fixture",
                    data_flags=("FIXTURE_ONLY", "UNIVERSE_SCOPE_HASH:" + scope_hash),
                )
            )
        rows[instance] = tuple(values)
    return plan, rows, emotion, source


def test_complete_algorithm_fixture_correction_preserves_every_old_reference(tmp_path):
    from src.services.platform.feature_store import FeatureStore, FeaturePublicationError
    from src.schemas.platform import ConsumerRequirement

    plan, rows, original, source = complete_score_fixture()
    _, corrected_rows, corrected, _ = complete_score_fixture(correction=True)
    assert original[:60] == corrected[:60]
    assert all(original[i].smoothed != corrected[i].smoothed for i in range(60, 65))
    assert original[60].state != corrected[60].state
    store = FeatureStore(tmp_path, fixture_only=True, clock=lambda: plan.cutoff_at)
    kwargs = dict(
        data_snapshot_ids=(source,), cutoff_at=plan.cutoff_at, as_of_trade_date=date(2026, 3, 6), consumer_ref="fixture"
    )
    old, old_bundle = store.materialize_and_publish(plan, rows, **kwargs)
    old_bytes = {
        ref.feature_partition_id: store.read_partition_payload(ref.feature_partition_id)
        for ref in old.feature_partition_refs
    }
    previous_ids = {
        instance: next(
            ref.feature_partition_id for ref in old.feature_partition_refs if ref.indicator_id == instance.indicator_id
        )
        for instance in plan.ordered_instances
    }
    new, new_bundle = store.materialize_and_publish(
        plan,
        corrected_rows,
        correction_of_snapshot_id=old.feature_snapshot_id,
        correction_of_partition_ids=previous_ids,
        **kwargs,
    )
    assert new.revision == 2 and new.supersedes_id == old.feature_snapshot_id
    assert new.as_of_trade_date == old.as_of_trade_date and new.cutoff_at == old.cutoff_at
    assert new.dependency_plan_hash == old.dependency_plan_hash
    assert new.manifest_hash != old.manifest_hash and new_bundle.bundle_hash != old_bundle.bundle_hash
    assert store.published_bundle(old_bundle.feature_bundle_id) == old_bundle
    for ref in old.feature_partition_refs:
        assert store.read_partition_payload(ref.feature_partition_id) == old_bytes[ref.feature_partition_id]
        assert store.published_partition(ref.feature_partition_id).revision == 1
    for ref in new.feature_partition_refs:
        assert store.published_partition(ref.feature_partition_id).revision == 2
    assert new.certified_capabilities == () and new.missing_capabilities == ("market_breadth", "market_emotion")
    with pytest.raises(FeaturePublicationError, match="capability"):
        store.consume_bundle(
            new_bundle.feature_bundle_id,
            ConsumerRequirement(
                consumer_id="paper",
                consumer_kind="FORMAL_BACKTEST",
                required_capabilities=("backtest_core", "market_emotion"),
                accepted_publication_statuses=("CERTIFIED",),
            ),
        )
    with pytest.raises(FeaturePublicationError, match="logical manifest identity"):
        store.materialize_and_publish(
            plan,
            corrected_rows,
            correction_of_snapshot_id=new.feature_snapshot_id,
            correction_of_partition_ids={
                instance: next(
                    ref.feature_partition_id
                    for ref in new.feature_partition_refs
                    if ref.indicator_id == instance.indicator_id
                )
                for instance in plan.ordered_instances
            },
            **(kwargs | {"as_of_trade_date": date(2026, 3, 7)}),
        )


def test_store_rejects_multiple_scope_hash_flags(tmp_path):
    from src.services.platform.market_sentiment import evaluate_market_days
    from src.services.platform.feature_store import FeatureStore, FeatureMaterializationError

    batch = evaluate_market_days([market_day()])[0]
    rows = tuple(
        row.model_copy(update={"data_flags": row.data_flags + ("UNIVERSE_SCOPE_HASH:sha256:" + "b" * 64,)})
        for row in batch.rows
    )
    with pytest.raises(FeatureMaterializationError, match="scope"):
        publish_market(FeatureStore(tmp_path, clock=lambda: batch.rows[0].available_at), replace(batch, rows=rows))


def test_market_snapshot_cannot_claim_certified_status_even_without_capabilities(tmp_path):
    from src.services.platform.market_sentiment import evaluate_market_days, validate_market_publication
    from src.services.platform.feature_store import FeatureStore
    from src.schemas.platform import ConsumerKind

    batch = evaluate_market_days([market_day()])[0]
    _, snapshot, _ = publish_market(FeatureStore(tmp_path, clock=lambda: batch.rows[0].available_at), batch)
    forged = type(snapshot).build(
        **(
            {key: value for key, value in snapshot.model_dump().items() if key != "manifest_hash"}
            | {"publication_status": "CERTIFIED"}
        )
    )
    with pytest.raises(ValueError, match="PROVISIONAL"):
        validate_market_publication(forged, ConsumerKind.PREVIEW)


def test_missing_zero_status_and_sla_reasons_are_explicit_and_persisted():
    from src.services.platform.market_sentiment import evaluate_market_days, PREFIX

    base = market_day()
    datasets = {name: [dict(row) for row in rows] for name, rows in base.datasets.items()}
    datasets["instrument_status_daily"] = []
    batch = evaluate_market_days([replace(base, datasets=datasets)])[0]
    assert "SOURCE_UNAVAILABLE" in batch.results["liquidity.zero_or_suspended_ratio"].flags
    row = next(row for row in batch.rows if row.indicator_id == PREFIX + "limit.limit_break_rate")
    assert "VALID_COUNT:0" in row.data_flags
    assert "DENOMINATOR_COUNT:0" in row.data_flags
    datasets["bar_1d_raw"] = datasets["bar_1d_raw"][:1]
    batch = evaluate_market_days([replace(base, datasets=datasets)])[0]
    assert "SCOPE_SLA_FAILED" in batch.results["liquidity.market_amount_cny"].flags
    assert (
        next(
            row for row in batch.rows if row.indicator_id == PREFIX + "liquidity.market_amount_cny"
        ).quality_status.value
        == "PARTIAL"
    )


def test_non_open_day_unsupported_fields_listing_conflict_and_suspended_denominator():
    from src.services.platform.market_sentiment import evaluate_market_days

    base = market_day()
    datasets = {name: [dict(row) for row in rows] for name, rows in base.datasets.items()}
    datasets["trading_calendar"][0]["is_open"] = False
    with pytest.raises(ValueError, match="non-open"):
        evaluate_market_days([replace(base, datasets=datasets)])
    datasets["trading_calendar"][0]["is_open"] = True
    datasets["security_master"][0]["shares_outstanding"] = Decimal(1000)
    with pytest.raises(ValueError, match="real DatasetDefinition"):
        evaluate_market_days([replace(base, datasets=datasets)])
    del datasets["security_master"][0]["shares_outstanding"]
    datasets["listing_status_history"].append(dict(datasets["listing_status_history"][0]))
    with pytest.raises(ValueError, match="interval conflict"):
        evaluate_market_days([replace(base, datasets=datasets)])
    datasets["listing_status_history"].pop()
    datasets["instrument_status_daily"][0].update(instrument_status="SUSPENDED", is_tradable=False)
    datasets["bar_1d_raw"] = datasets["bar_1d_raw"][1:]
    batch = evaluate_market_days([replace(base, datasets=datasets)])[0]
    assert batch.results["audit.bar_valid_count"].value == 3
    assert batch.results["liquidity.zero_or_suspended_ratio"].value == Decimal(1) / 3
    assert batch.results["risk.median_amplitude"].denominator_count == 2


def test_controlled_builtin_executes_real_path_and_rejects_contract_override():
    from src.services.platform.market_sentiment import PREFIX

    registry = default_indicator_registry()
    definition = registry.get(PREFIX + "audit.listed_count")
    builtin = registry.implementation(definition.formula_ref)
    contract = definition.normalized_default_parameters["contract"]
    assert builtin.callable(days=[market_day()], contract=contract) == (3,)
    with pytest.raises(ValueError, match="override"):
        builtin.callable(days=[market_day()], contract="override")


def test_unknown_limit_rules_do_not_claim_no_limit_up_streak():
    from src.services.platform.market_sentiment import evaluate_market_days

    base = market_day()
    datasets = {name: [dict(row) for row in rows] for name, rows in base.datasets.items()}
    for row in datasets["bar_1d_raw"]:
        row["price_limit_up"] = row["price_limit_down"] = None
    batch = evaluate_market_days([replace(base, datasets=datasets)])[0]
    assert batch.results["limit.max_streak_height"].value is None
    assert batch.results["limit.streak_stock_count"].value is None


def test_diagnostic_warming_up_range_publishes_null_not_fabricated_warmup(tmp_path):
    from src.services.platform.market_sentiment import evaluate_market_days, PREFIX
    from src.services.platform.feature_store import FeatureStore

    batch = evaluate_market_days([market_day()])[0]
    day = batch.manifest.trade_date
    plan = FeatureDependencyResolver(default_indicator_registry()).resolve(
        [PREFIX + "regime.state"],
        cutoff_at=batch.rows[0].available_at,
        universe_scope_hash=batch.manifest.universe_scope_hash,
        allow_unavailable=True,
        date_from=day,
        date_to=day,
    )
    mapping = {
        instance: tuple(row for row in batch.rows if row.indicator_id == instance.indicator_id)
        for instance in plan.ordered_instances
    }
    store = FeatureStore(tmp_path, clock=lambda: plan.cutoff_at)
    snapshot, _ = store.materialize_and_publish(
        plan,
        mapping,
        data_snapshot_ids=(batch.manifest.data_snapshot_id,),
        cutoff_at=plan.cutoff_at,
        as_of_trade_date=day,
        consumer_ref="preview",
        date_from=day,
        date_to=day,
    )
    assert snapshot.quality_status.value == "PARTIAL"
    assert snapshot.publication_status.value == "PROVISIONAL"
    assert (
        "WARMING_UP"
        in next(
            row for row in batch.rows if row.indicator_id == PREFIX + "normalized.limit.limit_up_down_spread"
        ).data_flags
    )


def test_raw_emotion_out_of_range_cannot_be_hidden_by_smoothing():
    from src.services.platform.market_sentiment import emotion_sequence

    with pytest.raises(ValueError, match="score outside"):
        emotion_sequence([Decimal(0), Decimal(200)])



def test_unknown_streak_history_never_claims_complete_zero_count():
    from src.services.platform.market_sentiment import evaluate_market_days, PREFIX

    batch = evaluate_market_days([market_day()])[0]
    result = batch.results["limit.streak_stock_count"]
    assert result.value is None
    assert result.valid_count == 0 and result.denominator_count == 1
    assert "HISTORY_GAP" in result.flags
    row = next(row for row in batch.rows if row.indicator_id == PREFIX + "limit.streak_stock_count")
    assert row.value is None and row.quality_status.value == "PARTIAL"


@pytest.mark.parametrize("key,exchange", [("etf:sh600001", "SH"), ("stock:usaapl", "SH"), ("stock:sh600001", "SZ")])
def test_frozen_scope_rejects_asset_or_exchange_identity_conflicts(key, exchange):
    from src.services.platform.market_sentiment import evaluate_market_days

    base = market_day()
    datasets = {name: [dict(row) for row in rows] for name, rows in base.datasets.items()}
    for rows in datasets.values():
        for row in rows:
            if row.get("entity_key") == "stock:sh600001":
                row["entity_key"] = key
    datasets["security_master"][0]["exchange"] = exchange
    with pytest.raises(ValueError, match="identity.*scope"):
        evaluate_market_days([replace(base, datasets=datasets)])
