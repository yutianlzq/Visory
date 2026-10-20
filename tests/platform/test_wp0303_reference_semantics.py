"""Reference counterexamples; source pins are in WP-0303-IMPLEMENTATION section 14."""

from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from hashlib import sha256
from io import BytesIO

import pyarrow.parquet as pq
import pytest

from src.schemas.platform import ConsumerRequirement
from src.services.platform.feature_store import FeaturePublicationError, FeatureStore
from src.services.platform.market_sentiment import PREFIX, evaluate_market_days
from tests.platform.test_market_sentiment import market_day, publish_market


def _mixed_limit_day(trade_date, closes):
    base = market_day(trade_date)
    datasets = {name: [dict(row) for row in rows] for name, rows in base.datasets.items()}
    datasets["instrument_status_daily"][0]["instrument_status"] = "ST"
    datasets["security_master"][2]["board"] = "CHINEXT"
    limits = (("10.5", "9.5"), ("11", "9"), ("12", "8"))
    for bar, close, (upper, lower) in zip(datasets["bar_1d_raw"], closes, limits, strict=True):
        bar.update(
            close=Decimal(close),
            high=Decimal(upper),
            low=max(Decimal(lower), Decimal(9)),
            price_limit_up=Decimal(upper),
            price_limit_down=Decimal(lower),
        )
    return replace(base, datasets=datasets)


def test_reference_ecology_uses_actual_limit_prices_and_ratio_units():
    day = _mixed_limit_day(date(2026, 6, 8), ("10.5", "10.99", "12"))
    results = evaluate_market_days((day,))[0].results

    # ST at 5% is sealed, MAIN at 9.9% is broken, and CHINEXT at 20% is sealed.
    assert results["limit.limit_up_count"].value == 2
    assert results["limit.limit_break_count"].value == 1
    assert results["limit.limit_break_rate"].value == Decimal(1) / 3
    assert results["limit.limit_break_rate"].denominator_count == 3
    assert results["limit.limit_break_rate"].coverage_ratio == 1
    assert results["limit.limit_break_rate"].value != Decimal("33.3")
    assert results["limit.early_seal_ratio"].value is None


def test_reference_empty_touch_pool_keeps_a_known_zero_count_and_missing_rate():
    base = market_day(date(2026, 6, 8), ("10", "10", "10"))
    datasets = {name: [dict(row) for row in rows] for name, rows in base.datasets.items()}
    for bar in datasets["bar_1d_raw"]:
        bar["high"] = Decimal("10.5")
    results = evaluate_market_days((replace(base, datasets=datasets),))[0].results

    assert results["audit.limit_rule_count"].value == 3
    assert results["limit.limit_up_count"].value == 0
    assert results["limit.limit_break_count"].value == 0
    assert results["limit.limit_break_rate"].value is None
    assert results["limit.limit_break_rate"].flags == ("DENOMINATOR_ZERO",)
    assert results["limit.limit_break_rate"].coverage_ratio is None


def test_reference_percent_shortcut_cannot_select_promotion_candidates():
    start = date(2026, 6, 8)
    days = (
        _mixed_limit_day(start, ("10", "10", "10")),
        _mixed_limit_day(start + timedelta(days=1), ("10.5", "10.99", "12")),
        _mixed_limit_day(start + timedelta(days=2), ("10.5", "10.99", "12")),
        _mixed_limit_day(start + timedelta(days=3), ("10.49", "10.99", "12")),
    )
    batch = evaluate_market_days(days, open_trade_dates=tuple(day.trade_date for day in days))[-1]
    promotion = batch.results["limit.promotion_rate"]

    assert batch.results["limit.streak_stock_count"].value == 1
    assert promotion.value == Decimal("0.5")
    assert promotion.valid_count == promotion.denominator_count == 2
    assert promotion.coverage_ratio == 1


@pytest.mark.parametrize("field", ("outstanding_share", "shares_outstanding", "circulating_market_cap"))
def test_reference_share_or_current_cap_fields_cannot_expand_the_old_master(field):
    base = market_day()
    datasets = {name: [dict(row) for row in rows] for name, rows in base.datasets.items()}
    datasets["security_master"][0][field] = Decimal(100000000)

    with pytest.raises(ValueError, match="real DatasetDefinition: security_master"):
        evaluate_market_days((replace(base, datasets=datasets),))


@pytest.mark.parametrize(
    "field,value", (("fbt", "092500"), ("first_limit_up_time", 1780881900))
)
def test_reference_clock_formats_require_a_separate_verified_input_contract(field, value):
    base = market_day()
    datasets = {name: [dict(row) for row in rows] for name, rows in base.datasets.items()}
    datasets["bar_1d_raw"][0][field] = value

    with pytest.raises(ValueError, match="real DatasetDefinition: bar_1d_raw"):
        evaluate_market_days((replace(base, datasets=datasets),))


def test_reference_raw_price_directions_cannot_replace_pit_adjusted_breadth():
    results = evaluate_market_days((market_day(closes=("9", "10", "11")),))[0].results
    for metric in ("breadth.advance_count", "breadth.decline_count", "breadth.median_return"):
        assert results[metric].value is None
        assert results[metric].flags == ("SOURCE_UNAVAILABLE",)
    assert results["risk_appetite.high_turnover_return_spread"].value is None
    assert results["risk_appetite.small_large_return_spread"].value is None


def test_reference_ecology_publishes_fixed_rows_without_certifying_market_inputs(tmp_path):
    day = _mixed_limit_day(date(2026, 6, 8), ("10.5", "10.99", "12"))
    batch = evaluate_market_days((day,))[0]
    store = FeatureStore(tmp_path, clock=lambda: day.cutoff_at)
    _, snapshot, bundle = publish_market(store, batch, (PREFIX + "limit.limit_break_rate",))

    assert snapshot.publication_status.value == "PROVISIONAL"
    assert snapshot.certified_capabilities == ()
    assert snapshot.missing_capabilities == ("market_breadth", "market_emotion")
    assert len(bundle.required_partition_refs) == 1
    partition_id = bundle.required_partition_refs[0].feature_partition_id
    payload = store.read_partition_payload(partition_id)
    assert "sha256:" + sha256(payload).hexdigest() == bundle.required_partition_refs[0].partition_hash
    rows = pq.read_table(BytesIO(payload)).to_pylist()
    assert len(rows) == 1
    assert rows[0]["value"] == Decimal("0.333333333333")
    assert rows[0]["definition_version"] == "1.0.0"

    preview = ConsumerRequirement(
        consumer_id="reference_preview",
        consumer_kind="PREVIEW",
        required_capabilities=("market_emotion",),
        allow_provisional=True,
        min_quality_status="PARTIAL",
        accepted_publication_statuses=("PROVISIONAL",),
    )
    assert store.consume_bundle(bundle.feature_bundle_id, preview) == bundle
    formal = ConsumerRequirement(
        consumer_id="reference_formal",
        consumer_kind="FORMAL_BACKTEST",
        required_capabilities=("backtest_core", "market_emotion"),
        accepted_publication_statuses=("CERTIFIED",),
    )
    with pytest.raises(FeaturePublicationError, match="capability"):
        store.consume_bundle(bundle.feature_bundle_id, formal)
