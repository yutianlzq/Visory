"""WP-0303 C-006 内部计算：真实契约受限路径与隔离评分算法，不负责发布。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, localcontext, ROUND_HALF_UP
from functools import partial
from statistics import median
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from src.schemas.platform.hashing import canonical_json_bytes, compute_content_hash
from src.schemas.platform.indicator import (
    DatasetInputRef,
    IndicatorDependencyRef,
    IndicatorOutputDefinition,
    ParameterDefinition,
)

PREFIX = "market.sentiment."
SCOPE_ID = "cn_a_equity_v1"
AGGREGATE_KEY = "aggregate:" + SCOPE_ID
EPSILON = Decimal("1e-12")
QUANTUM = Decimal("1e-12")
DIMENSION_WEIGHTS = MappingProxyType(
    {
        "breadth": {
            "breadth.net_advance_ratio": 30,
            "breadth.above_ma20_ratio": 25,
            "breadth.above_ma60_ratio": 15,
            "breadth.new_high_low_spread_20": 15,
            "breadth.median_return": 15,
        },
        "limit": {
            "limit.limit_up_down_spread": 30,
            "limit.limit_break_rate": 25,
            "limit.max_streak_height": 20,
            "limit.promotion_rate": 25,
        },
        "risk_appetite": {
            "risk_appetite.prior_limit_up_premium": 30,
            "risk_appetite.high_turnover_return_spread": 25,
            "risk_appetite.small_large_return_spread": 20,
            "risk_appetite.top_amount20_median_return": 25,
        },
        "liquidity": {"liquidity.amount_ratio_20": 60, "liquidity.rising_amount_share": 40},
        "safety": {"risk.tail_loss_ratio": 40, "risk.return_dispersion_mad": 30, "risk.benchmark_realized_vol_20": 30},
    }
)
DIMENSION_WEIGHTS = MappingProxyType({key: MappingProxyType(value) for key, value in DIMENSION_WEIGHTS.items()})
TOTAL_WEIGHTS = MappingProxyType({"breadth": 25, "limit": 30, "risk_appetite": 20, "liquidity": 15, "safety": 10})
NEGATIVE_METRICS = frozenset(
    {"limit.limit_break_rate", "risk.tail_loss_ratio", "risk.return_dispersion_mad", "risk.benchmark_realized_vol_20"}
)


@dataclass(frozen=True, slots=True)
class MetricResult:
    value: Decimal | int | str | None
    flags: tuple[str, ...] = ()
    missing: tuple[str, ...] = ()
    valid_count: int = 0
    denominator_count: int = 0

    @property
    def coverage_ratio(self) -> Decimal | None:
        return ratio(self.valid_count, self.denominator_count)


@dataclass(frozen=True, slots=True)
class MetricPoint:
    trade_date: date
    value: Decimal | int | None
    available_at: datetime


@dataclass(frozen=True, slots=True)
class EmotionPoint:
    smoothed: Decimal | None
    state: str | None
    transition_from: str | None
    trigger: str | None


def decimal(value: Any) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (Decimal, int)):
        raise ValueError("numeric inputs require explicit Decimal or integer")
    result = Decimal(value)
    if not result.is_finite():
        raise ValueError("numeric input must be finite")
    return result


def ratio(numerator: Any, denominator: Any) -> Decimal | None:
    return None if denominator == 0 else decimal(numerator) / decimal(denominator)


def normalize_metric(
    current: Any, history: Sequence[MetricPoint], *, trade_date: date, cutoff_at: datetime, negative: bool = False
) -> MetricResult:
    if cutoff_at.tzinfo is None or cutoff_at.utcoffset() is None:
        raise ValueError("cutoff must be timezone-aware")
    if any(point.trade_date >= trade_date for point in history):
        raise ValueError("normalization history must end at T-1")
    if any(
        point.available_at.tzinfo is None or point.available_at.utcoffset() is None or point.available_at > cutoff_at
        for point in history
    ):
        raise ValueError("history exceeds cutoff")
    if len({point.trade_date for point in history}) != len(history):
        raise ValueError("duplicate historical trade date")
    if current is None:
        return MetricResult(None, ("SOURCE_UNAVAILABLE",))
    values = [
        decimal(point.value) for point in sorted(history, key=lambda point: point.trade_date) if point.value is not None
    ][-252:]
    if len(values) < 60:
        return MetricResult(None, ("WARMING_UP",))
    with localcontext() as context:
        context.prec = 38
        center = median(values)
        mad = median([abs(value - center) for value in values])
        z = (decimal(current) - center) / (Decimal("1.4826") * mad + EPSILON)
        if negative:
            z = -z
        score = max(
            Decimal(0),
            min(Decimal(100), Decimal(50) + max(Decimal(-3), min(Decimal(3), z)) * Decimal(100) / Decimal(6)),
        )
    return MetricResult(score)


def weighted_score(values: Mapping[str, Any], weights: Mapping[str, int], *, namespace: str) -> MetricResult:
    missing = tuple(sorted(namespace + key for key in weights if values.get(key) is None))
    if missing:
        return MetricResult(None, ("DEPENDENCY_MISSING",), missing)
    if sum(weights.values()) != 100:
        raise ValueError("weights must sum to 100")
    numbers = {key: decimal(values[key]) for key in weights}
    if any(value < 0 or value > 100 for value in numbers.values()):
        raise ValueError("score outside [0,100]")
    return MetricResult(sum((numbers[key] * weight / 100 for key, weight in weights.items()), Decimal(0)))


def composite_emotion(dimensions: Mapping[str, Any]) -> MetricResult:
    return weighted_score(dimensions, TOTAL_WEIGHTS, namespace=PREFIX + "score.")


def regime_sequence(scores: Sequence[Decimal | None]) -> tuple[EmotionPoint, ...]:
    states = ("PANIC", "WEAK", "RANGE", "ACTIVE", "OVERHEATED")
    current = pending = None
    count = 0
    result = []
    for value in scores:
        if value is None:
            current = pending = None
            count = 0
            result.append(EmotionPoint(None, None, None, None))
            continue
        score = decimal(value)
        if score < 0 or score > 100:
            raise ValueError("score outside [0,100]")
        candidate = min(int(score // 20), 4)
        previous, trigger = None, "NONE"
        if current is None:
            current, trigger = candidate, "INITIALIZED"
        elif candidate == current:
            pending, count = None, 0
        else:
            jump = score - Decimal((current + 1) * 20) if candidate > current else Decimal(current * 20) - score
            if jump >= 5:
                previous, current = states[current], candidate
                pending, count, trigger = None, 0, "BOUNDARY_JUMP_GE_5"
            else:
                count = count + 1 if pending == candidate else 1
                pending = candidate
                if count >= 2:
                    previous, current = states[current], candidate
                    pending, count, trigger = None, 0, "TWO_DAY_CONFIRM"
        result.append(EmotionPoint(score, states[current], previous, trigger))
    return tuple(result)


def emotion_sequence(raw_scores: Sequence[Decimal | None]) -> tuple[EmotionPoint, ...]:
    """只接受开放交易日序列；缺失日打断平滑与 pending 状态。Correction 重算整个尾部。"""
    previous = None
    values = []
    for raw in raw_scores:
        if raw is not None and not Decimal(0) <= decimal(raw) <= Decimal(100):
            raise ValueError("score outside [0,100]")
        previous = None if raw is None else decimal(raw) if previous is None else (decimal(raw) + previous) / 2
        values.append(previous)
    return regime_sequence(values)


@dataclass(frozen=True, slots=True)
class MarketDay:
    trade_date: date
    cutoff_at: datetime
    data_snapshot_id: str
    partition_refs: tuple[str, ...]
    datasets: Mapping[str, Sequence[Mapping[str, Any]]]

    def __post_init__(self):
        if self.cutoff_at.tzinfo is None or self.cutoff_at.utcoffset() is None or not self.partition_refs:
            raise ValueError("market inputs require cutoff and fixed partition refs")
        from src.schemas.platform.resources import parse_resource_id
        from src.schemas.platform.enums import ResourceType

        if parse_resource_id(self.data_snapshot_id)[0] is not ResourceType.DATA_SNAPSHOT:
            raise ValueError("fixed DataSnapshot reference required")
        for ref in self.partition_refs:
            if parse_resource_id(ref)[0] is not ResourceType.CANONICAL_PARTITION:
                raise ValueError("fixed CanonicalPartition reference required")
        object.__setattr__(
            self,
            "datasets",
            MappingProxyType(
                {name: tuple(MappingProxyType(dict(row)) for row in rows) for name, rows in self.datasets.items()}
            ),
        )


def _day_rows(day: MarketDay, name: str, fields: Sequence[str]) -> tuple[Mapping[str, Any], ...]:
    rows = tuple(day.datasets.get(name, ()))
    from .feature_dependency import DEFAULT_DATASET_CATALOG

    contract = DEFAULT_DATASET_CATALOG.get(name, "1.0.0")
    if contract is None:
        raise ValueError("input DatasetDefinition exact version is unavailable: " + name)
    for row in rows:
        if set(row) - set(contract.fields) or not set(fields) <= set(row):
            raise ValueError("input fields do not match real DatasetDefinition: " + name)
        instant = row.get("available_at")
        if (
            not isinstance(instant, datetime)
            or instant.tzinfo is None
            or instant.utcoffset() is None
            or instant > day.cutoff_at
        ):
            raise ValueError("input available_at exceeds cutoff")
        if name in {"bar_1d_raw", "instrument_status_daily", "benchmark_index_1d", "trading_calendar"}:
            if row.get("status_date", row.get("trade_date")) != day.trade_date:
                raise ValueError("input trade date mismatch")
    return rows


@dataclass(frozen=True, slots=True)
class MarketScopeManifest:
    trade_date: date
    members: tuple[tuple[str, bool, bool, bool, bool, tuple[str, ...]], ...]
    data_snapshot_id: str
    partition_refs: tuple[str, ...]
    market_scope_id: str = SCOPE_ID
    policy_version: str = "1.0.0"

    @property
    def universe_scope_hash(self) -> str:
        return compute_content_hash(
            {
                "market_scope_id": self.market_scope_id,
                "policy_version": self.policy_version,
                "trade_date": self.trade_date,
                "members": self.members,
                "data_snapshot_id": self.data_snapshot_id,
                "partition_refs": sorted(self.partition_refs),
            }
        )

    def pool(self, position: int) -> frozenset[str]:
        return frozenset(member[0] for member in self.members if member[position])


def freeze_market_scope(day: MarketDay) -> MarketScopeManifest:
    from src.schemas.platform.identity import parse_entity_key

    master = _day_rows(
        day, "security_master", ("entity_key", "asset_type", "exchange", "board", "list_date", "available_at")
    )
    bars = _day_rows(day, "bar_1d_raw", ("entity_key", "trade_date", "trading_status", "available_at"))
    statuses = _day_rows(
        day,
        "instrument_status_daily",
        ("entity_key", "status_date", "instrument_status", "is_tradable", "available_at"),
    )
    listing = _day_rows(
        day, "listing_status_history", ("entity_key", "effective_from", "listing_status", "available_at")
    )
    calendar = _day_rows(day, "trading_calendar", ("market", "trade_date", "is_open", "available_at"))
    if len(calendar) != 1 or calendar[0]["market"] != "CN" or not isinstance(calendar[0]["is_open"], bool):
        raise ValueError("one CN trading calendar observation is required")
    if not calendar[0]["is_open"]:
        raise ValueError("non-open day is not a market observation")

    def indexed(rows):
        result = {row["entity_key"]: row for row in rows}
        if len(result) != len(rows):
            raise ValueError("duplicate entity observation")
        return result

    bar_map, status_map = indexed(bars), indexed(statuses)
    indexed(master)
    members = []
    for row in sorted(master, key=lambda row: row["entity_key"]):
        key = row["entity_key"]
        identity_type, canonical_id = parse_entity_key(key)
        if (
            row["asset_type"] != "stock"
            or row["exchange"] not in {"SH", "SZ"}
            or row["board"] not in {"MAIN", "STAR", "CHINEXT"}
        ):
            continue
        if (
            identity_type.value != "stock"
            or len(canonical_id) != 8
            or not canonical_id.startswith(row["exchange"].lower())
            or not canonical_id[2:].isascii()
            or not canonical_id[2:].isdigit()
        ):
            raise ValueError("entity identity conflicts with frozen A-share scope")
        intervals = [
            r
            for r in listing
            if r["entity_key"] == key
            and r["effective_from"] <= day.trade_date
            and (r.get("effective_to") is None or day.trade_date < r["effective_to"])
        ]
        if len(intervals) != 1:
            raise ValueError("listing identity interval conflict or missing")
        listed = (
            intervals[0]["listing_status"] == "LISTED"
            and row["list_date"] <= day.trade_date
            and (row.get("delist_date") is None or day.trade_date < row["delist_date"])
        )
        status, bar = status_map.get(key), bar_map.get(key)
        reasons = []
        if status is None:
            reasons.append("STATUS_UNKNOWN")
        elif status["instrument_status"] not in {
            "ACTIVE",
            "ST",
            "SUSPENDED",
            "DELISTED",
            "NOT_LISTED",
        } or not isinstance(status["is_tradable"], bool):
            raise ValueError("instrument status contract mismatch")
        if status and (status["instrument_status"] in {"NOT_LISTED", "DELISTED"}) == listed:
            raise ValueError("listing and instrument status conflict")
        suspended = bool(status and status["instrument_status"] == "SUSPENDED") or bool(
            bar and bar["trading_status"] == "SUSPENDED"
        )
        if suspended:
            reasons.append("SUSPENDED")
        if status and status["instrument_status"] == "ST":
            reasons.append("ST")
        if row["list_date"] == day.trade_date:
            reasons.append("NEW_LISTING")
        if bar and bar["trading_status"] not in {"TRADED", "SUSPENDED", "NO_DATA", "NOT_LISTED"}:
            raise ValueError("bar trading status contract mismatch")
        valid_bar = bool(
            bar
            and bar["trading_status"] == "TRADED"
            and all(bar.get(f) is not None for f in ("open", "high", "low", "close", "volume_shares", "amount_cny"))
        )
        if valid_bar:
            values = {f: decimal(bar[f]) for f in ("open", "high", "low", "close", "volume_shares", "amount_cny")}
            valid_bar = (
                values["low"] > 0
                and values["low"]
                <= min(values["open"], values["close"])
                <= max(values["open"], values["close"])
                <= values["high"]
                and values["volume_shares"] >= 0
                and values["amount_cny"] >= 0
            )
        observable = (
            listed
            and valid_bar
            and not suspended
            and bool(status and status["is_tradable"])
            and bar.get("prev_close") is not None
            and decimal(bar["prev_close"]) > 0
        )
        limit = (
            observable
            and all(bar.get(f) is not None and decimal(bar[f]) > 0 for f in ("price_limit_up", "price_limit_down"))
            and decimal(bar["price_limit_up"]) > decimal(bar["price_limit_down"])
        )
        if listed and not (valid_bar or suspended):
            reasons.append("BAR_UNAVAILABLE")
        members.append((key, listed, listed and (valid_bar or suspended), observable, limit, tuple(sorted(reasons))))
    return MarketScopeManifest(day.trade_date, tuple(members), day.data_snapshot_id, tuple(sorted(day.partition_refs)))


# 每个指标具有独立输入、分母、公式和状态；不存在替代字段/动态权重。
RAW_SPECS = {
    "audit.listed_count": ("EXECUTABLE", "integer", "count", 0, 0),
    "audit.bar_valid_count": ("EXECUTABLE", "integer", "count", 0, 0),
    "audit.valid_return_count": ("BLOCKED", "integer", "count", 1, 0),
    "audit.limit_rule_count": ("EXECUTABLE", "integer", "count", 0, 0),
}
for name in (
    "advance_count",
    "decline_count",
    "flat_count",
    "net_advance_ratio",
    "advance_decline_log",
    "median_return",
    "above_ma20_ratio",
    "above_ma60_ratio",
    "new_high_low_spread_20",
):
    period = 60 if name == "above_ma60_ratio" else 20 if name in {"above_ma20_ratio", "new_high_low_spread_20"} else 1
    RAW_SPECS["breadth." + name] = (
        "BLOCKED",
        "integer" if name.endswith("count") else "decimal",
        "count" if name.endswith("count") else "ratio",
        period,
        period if period > 1 else 0,
    )
for name in (
    "limit_up_count",
    "limit_down_count",
    "limit_up_down_spread",
    "limit_break_count",
    "limit_break_rate",
    "max_streak_height",
    "streak_stock_count",
    "promotion_rate",
    "early_seal_ratio",
):
    period = 2 if name in {"streak_stock_count", "promotion_rate", "max_streak_height"} else 1
    kind = "integer" if name.endswith("count") or name == "max_streak_height" else "decimal"
    RAW_SPECS["limit." + name] = (
        "FIXTURE_ONLY" if name == "early_seal_ratio" else "EXECUTABLE",
        kind,
        "count" if kind == "integer" else "ratio",
        period,
        2 if period == 2 else 0,
    )
for name in (
    "prior_limit_up_premium",
    "high_turnover_return_spread",
    "small_large_return_spread",
    "top_amount20_median_return",
    "strong_stock_survival_ratio",
):
    period = 2 if name in {"prior_limit_up_premium", "strong_stock_survival_ratio"} else 1
    RAW_SPECS["risk_appetite." + name] = ("BLOCKED", "decimal", "ratio", period, 2 if period == 2 else 0)
for name in (
    "market_amount_cny",
    "amount_ratio_20",
    "rising_amount_share",
    "top20_amount_concentration",
    "zero_or_suspended_ratio",
):
    RAW_SPECS["liquidity." + name] = (
        "BLOCKED" if name == "rising_amount_share" else "EXECUTABLE",
        "decimal",
        "cny" if name == "market_amount_cny" else "ratio",
        21 if name == "amount_ratio_20" else 1,
        20 if name == "amount_ratio_20" else 0,
    )
for name in (
    "median_amplitude",
    "return_dispersion_mad",
    "benchmark_realized_vol_20",
    "tail_loss_ratio",
    "market_drawdown_20",
):
    state = (
        "EXECUTABLE"
        if name == "median_amplitude"
        else "FIXTURE_ONLY"
        if name in {"benchmark_realized_vol_20", "market_drawdown_20"}
        else "BLOCKED"
    )
    period = 21 if name == "benchmark_realized_vol_20" else 20 if name == "market_drawdown_20" else 1
    RAW_SPECS["risk." + name] = (state, "decimal", "ratio", period, period - 1 if period > 1 else 0)
RAW_SPECS = MappingProxyType(RAW_SPECS)
NORMALIZED_METRICS = frozenset(key for weights in DIMENSION_WEIGHTS.values() for key in weights)


def _raw_inputs(metric: str) -> tuple[DatasetInputRef, ...]:
    inputs = {
        "security_master": (
            "entity_key",
            "asset_type",
            "exchange",
            "board",
            "list_date",
            "delist_date",
            "available_at",
        ),
        "listing_status_history": ("entity_key", "listing_status", "effective_from", "effective_to", "available_at"),
        "instrument_status_daily": ("entity_key", "status_date", "instrument_status", "is_tradable", "available_at"),
        "trading_calendar": ("market", "trade_date", "is_open", "available_at"),
        "bar_1d_raw": (
            "entity_key",
            "trade_date",
            "open",
            "high",
            "low",
            "close",
            "prev_close",
            "volume_shares",
            "amount_cny",
            "trading_status",
            "price_limit_up",
            "price_limit_down",
            "available_at",
        ),
    }
    if RAW_SPECS[metric][0] == "BLOCKED":
        inputs["corporate_action"] = ("entity_key", "factor", "available_at")
    if metric == "risk_appetite.high_turnover_return_spread":
        inputs["security_master"] += ("shares_outstanding",)
    if metric.startswith("risk.benchmark") or metric == "risk.market_drawdown_20":
        inputs["benchmark_index_1d"] = ("benchmark_id", "trade_date", "close", "return_type", "available_at")
    return tuple(
        DatasetInputRef(dataset_id=name, schema_version="1.0.0", required_fields=fields)
        for name, fields in sorted(inputs.items())
    )


RAW_FORMULAS = MappingProxyType(
    {
        "audit.listed_count": ("count(listed_universe)", "listed_universe"),
        "audit.bar_valid_count": ("count(bar_valid_universe)", "listed_universe"),
        "audit.valid_return_count": ("count(PIT_adjusted_return_available)", "tradable_observation_universe"),
        "audit.limit_rule_count": ("count(limit_rule_universe)", "listed_universe"),
        "breadth.advance_count": ("count(PIT_return>0)", "valid_return_count"),
        "breadth.decline_count": ("count(PIT_return<0)", "valid_return_count"),
        "breadth.flat_count": ("count(PIT_return=0)", "valid_return_count"),
        "breadth.net_advance_ratio": ("(advance_count-decline_count)/valid_return_count", "valid_return_count"),
        "breadth.advance_decline_log": ("ln((advance_count+1)/(decline_count+1))", "valid_return_count"),
        "breadth.median_return": ("median(PIT_return)", "valid_return_count"),
        "breadth.above_ma20_ratio": (
            "count(PIT_adjusted_close>MA20_adjusted)/eligible_count",
            "20-day-PIT-adjusted-eligible",
        ),
        "breadth.above_ma60_ratio": (
            "count(PIT_adjusted_close>MA60_adjusted)/eligible_count",
            "60-day-PIT-adjusted-eligible",
        ),
        "breadth.new_high_low_spread_20": (
            "(20-day-new-high-count-20-day-new-low-count)/eligible_count",
            "20-day-PIT-adjusted-eligible",
        ),
        "limit.limit_up_count": ("count(close>=price_limit_up)", "limit_rule_universe"),
        "limit.limit_down_count": ("count(close<=price_limit_down)", "limit_rule_universe"),
        "limit.limit_up_down_spread": ("(limit_up_count-limit_down_count)/limit_rule_count", "limit_rule_universe"),
        "limit.limit_break_count": ("count(high>=price_limit_up>close)", "limit_rule_universe"),
        "limit.limit_break_rate": ("limit_break_count/(limit_up_count+limit_break_count)", "touched-limit-up"),
        "limit.max_streak_height": (
            "max(consecutive_open_trade_day_limit_up); no-up=0; unknown=null",
            "today-limit-up",
        ),
        "limit.streak_stock_count": ("count(known_streak>=2); exclude_unknown_with_coverage", "today-limit-up"),
        "limit.promotion_rate": (
            "count(T-1-frozen-streak>=2 and T-limit-up)/T-observable-prior-candidates",
            "T-observable-T-1-frozen-candidates",
        ),
        "limit.early_seal_ratio": (
            "count(reliable-first-seal-before-threshold and close-sealed)/timestamp-eligible",
            "reliable-first-seal-timestamp-eligible",
        ),
        "risk_appetite.prior_limit_up_premium": ("mean(T-PIT-return of T-1-limit-up)", "T-observable-T-1-limit-up"),
        "risk_appetite.high_turnover_return_spread": (
            "median(PIT-return of top-20%-PIT-turnover)-market-median-PIT-return",
            "PIT-shares-outstanding-eligible",
        ),
        "risk_appetite.small_large_return_spread": (
            "mean(PIT-return bottom-30%-PIT-free-float-cap)-mean(top-30%)",
            "PIT-free-float-cap-eligible",
        ),
        "risk_appetite.top_amount20_median_return": (
            "median(PIT-return of top-20-amount)",
            "tradable_observation_universe",
        ),
        "risk_appetite.strong_stock_survival_ratio": (
            "count(T-1-top-10%-return and T-return>market-median)/T-observable-candidates",
            "T-observable-T-1-top-10%-return",
        ),
        "liquidity.market_amount_cny": ("sum(valid amount_cny)", "amount-valid-bar_valid_universe"),
        "liquidity.amount_ratio_20": (
            "market_amount_cny(T)/mean(last-20-valid-open-days strictly<=T-1)",
            "20-valid-prior-market-amounts",
        ),
        "liquidity.rising_amount_share": (
            "sum(amount_cny where PIT_return>0)/sum(valid amount_cny)",
            "PIT-return-and-amount-eligible",
        ),
        "liquidity.top20_amount_concentration": (
            "sum(top-20-amount)/sum(valid amount_cny)",
            "amount-valid-bar_valid_universe",
        ),
        "liquidity.zero_or_suspended_ratio": (
            "count(volume_shares=0 or explicit-suspended)/listed_count; unknown=null",
            "listed_universe",
        ),
        "risk.median_amplitude": ("median((high-low)/prev_close)", "tradable_observation_universe"),
        "risk.return_dispersion_mad": ("median(abs(PIT_return-median(PIT_return)))", "valid_return_count"),
        "risk.benchmark_realized_vol_20": (
            "sample_std(20-benchmark-price-returns)*sqrt(252)",
            "21-prior-and-current-benchmark-closes",
        ),
        "risk.tail_loss_ratio": ("count(PIT_return<=-0.05)/valid_return_count", "valid_return_count"),
        "risk.market_drawdown_20": ("benchmark-close(T)/max(benchmark-close[T-19..T])-1", "20-benchmark-closes"),
    }
)


def f2_contracts() -> dict[str, dict[str, Any]]:
    result = {}
    for metric, (state, kind, unit, lookback, warmup) in RAW_SPECS.items():
        result[metric] = {
            "state": state,
            "kind": kind,
            "unit": unit,
            "lookback": lookback,
            "warmup": warmup,
            "datasets": _raw_inputs(metric),
            "dependencies": (),
            "formula": RAW_FORMULAS[metric][0],
            "denominator": RAW_FORMULAS[metric][1],
            "tie_break": "value-desc/entity_key-asc",
            "history_gap": "UNKNOWN_NOT_ZERO",
            "scope_sla": {
                "bar_or_suspended_status_coverage_min": "0.998",
                "excluded_ratio_max": "0.002",
                "excluded_count_max": 10,
            },
            "missing_inputs": ("PIT_free_float_market_cap",)
            if metric == "risk_appetite.small_large_return_spread"
            else (),
            "benchmark": "index:cn:000300.SH/PRICE" if state == "FIXTURE_ONLY" and metric.startswith("risk.") else None,
        }
    for metric in sorted(NORMALIZED_METRICS):
        result["normalized." + metric] = {
            "state": "DERIVED",
            "kind": "decimal",
            "unit": "score",
            "lookback": 253,
            "warmup": 60,
            "datasets": (),
            "dependencies": (metric,),
            "direction": -1 if metric in NEGATIVE_METRICS else 1,
            "normalization": "T-1/252/60/median/1.4826*MAD+1e-12/clip3/50+z*100/6",
        }
    for dimension, weights in DIMENSION_WEIGHTS.items():
        result["score." + dimension] = {
            "state": "DERIVED",
            "kind": "decimal",
            "unit": "score",
            "lookback": 253,
            "warmup": 60,
            "datasets": (),
            "dependencies": tuple("normalized." + key for key in weights),
            "weights": dict(weights),
        }
    result["score.emotion_raw"] = {
        "state": "DERIVED",
        "kind": "decimal",
        "unit": "score",
        "lookback": 253,
        "warmup": 60,
        "datasets": (),
        "dependencies": tuple("score." + key for key in TOTAL_WEIGHTS),
        "weights": dict(TOTAL_WEIGHTS),
    }
    result["score.emotion_smoothed"] = {
        "state": "DERIVED",
        "kind": "decimal",
        "unit": "score",
        "lookback": 253,
        "warmup": 60,
        "datasets": (),
        "dependencies": ("score.emotion_raw",),
        "recursion": "alpha=0.5/reset-on-null/recompute-entire-tail",
    }
    for name in ("state", "transition_from", "transition_trigger"):
        result["regime." + name] = {
            "state": "DERIVED",
            "kind": "string",
            "unit": "code",
            "lookback": 253,
            "warmup": 60,
            "datasets": (),
            "dependencies": ("score.emotion_raw", "score.emotion_smoothed"),
            "boundaries": (20, 40, 60, 80),
            "hysteresis": "two-open-days/or-jump>=5/reset-on-null",
        }
    return result


def f2_builtins(builder):
    result = {}
    for metric, spec in f2_contracts().items():
        builtin_id = "f2_" + metric.replace(".", "_")
        contract = canonical_json_bytes(
            spec | {"scope": SCOPE_ID, "policy_version": "1.0.0", "null_policy": "PROPAGATE"}
        ).decode()
        schema = (ParameterDefinition(name="contract", value_type="enum", allowed_values=(contract,)),)
        output = (
            IndicatorOutputDefinition(
                alias="value",
                value_type=spec["kind"],
                unit=spec["unit"],
                precision=12 if spec["kind"] == "decimal" else None,
            ),
        )
        result[builtin_id] = builder(
            builtin_id, partial(_market_builtin, metric=metric, expected_contract=contract), output, schema
        )
    return result


def f2_definitions(builder):
    from .indicator_registry import BUILTIN_REGISTRY

    result = {}
    for metric, spec in f2_contracts().items():
        name, builtin = PREFIX + metric, BUILTIN_REGISTRY["f2_" + metric.replace(".", "_")]
        result[name] = builder(
            name,
            name,
            builtin.builtin_id,
            input_dataset_refs=spec["datasets"],
            input_indicator_refs=tuple(
                IndicatorDependencyRef(indicator_id=PREFIX + key, definition_version="1.0.0")
                for key in spec["dependencies"]
            ),
            output_schema=builtin.output_schema,
            parameter_schema=builtin.supported_parameter_schema,
            defaults={"contract": builtin.supported_parameter_schema[0].allowed_values[0]},
            lookback_requirement=spec["lookback"],
            warmup_requirement=spec["warmup"],
            universe_policy="FROZEN_REQUIRED",
            capability_id="backtest_core",
            materialization="F2_LONG_TERM",
        )
    return MappingProxyType(result)


def _market_builtin(
    *,
    days: Sequence[MarketDay],
    contract: str,
    metric: str,
    expected_contract: str,
    open_trade_dates: Sequence[date] | None = None,
):
    if contract != expected_contract:
        raise ValueError("F2 contract override is forbidden")
    return tuple(batch.results[metric].value for batch in evaluate_market_days(days, open_trade_dates=open_trade_dates))


@dataclass(frozen=True, slots=True)
class MarketFeatureBatch:
    manifest: MarketScopeManifest
    results: Mapping[str, MetricResult]
    rows: tuple[Any, ...]


def _streak(days: Sequence[MarketDay], manifests: Sequence[MarketScopeManifest], index: int, key: str) -> int | None:
    height = 0
    for position in range(index, -1, -1):
        if key not in manifests[position].pool(1):
            return None
        if key not in manifests[position].pool(4):
            return None
        bar = next(row for row in days[position].datasets["bar_1d_raw"] if row["entity_key"] == key)
        if decimal(bar["close"]) < decimal(bar["price_limit_up"]):
            return height
        height += 1
        if any(member[0] == key and "NEW_LISTING" in member[5] for member in manifests[position].members):
            return height
    return None


def _raw_day(days, manifests, index, previous_results):
    day, manifest = days[index], manifests[index]
    listed, valid, tradable, rules = (manifest.pool(p) for p in range(1, 5))
    bars = {row["entity_key"]: row for row in day.datasets.get("bar_1d_raw", ())}
    results = {metric: MetricResult(None, ("SOURCE_UNAVAILABLE",), (PREFIX + metric,)) for metric in RAW_SPECS}

    def put(metric, value, members, denominator, *, null_reason="SOURCE_UNAVAILABLE"):
        flags = () if value is not None else ("DENOMINATOR_ZERO" if denominator == 0 else null_reason,)
        results[metric] = MetricResult(value, flags, (), len(members), denominator)

    put("audit.listed_count", len(listed), listed, len(listed))
    put("audit.bar_valid_count", len(valid), valid, len(listed))
    put("audit.limit_rule_count", len(rules), rules, len(listed))
    ups = {key for key in rules if decimal(bars[key]["close"]) >= decimal(bars[key]["price_limit_up"])}
    downs = {key for key in rules if decimal(bars[key]["close"]) <= decimal(bars[key]["price_limit_down"])}
    breaks = {
        key
        for key in rules
        if decimal(bars[key]["high"]) >= decimal(bars[key]["price_limit_up"]) > decimal(bars[key]["close"])
    }
    for metric, value in (
        ("limit_up_count", len(ups)),
        ("limit_down_count", len(downs)),
        ("limit_break_count", len(breaks)),
    ):
        put("limit." + metric, value if rules else None, rules, len(rules))
    put("limit.limit_up_down_spread", ratio(len(ups) - len(downs), len(rules)), rules, len(rules))
    put("limit.limit_break_rate", ratio(len(breaks), len(ups) + len(breaks)), ups | breaks, len(ups | breaks))
    heights = {key: _streak(days, manifests, index, key) for key in ups}
    results["limit.max_streak_height"] = (
        MetricResult(
            None, ("HISTORY_GAP",), valid_count=sum(v is not None for v in heights.values()), denominator_count=len(ups)
        )
        if any(v is None for v in heights.values())
        else MetricResult(max(heights.values(), default=0), valid_count=len(ups), denominator_count=len(ups))
    )
    known_heights = [value for value in heights.values() if value is not None]
    results["limit.streak_stock_count"] = MetricResult(
        sum(value >= 2 for value in known_heights) if known_heights or not ups else None,
        ("HISTORY_GAP",) if len(known_heights) < len(ups) else (),
        valid_count=len(known_heights),
        denominator_count=len(ups),
    )
    if not rules:
        for metric in ("limit.max_streak_height", "limit.streak_stock_count"):
            results[metric] = MetricResult(None, ("SOURCE_UNAVAILABLE",))
    if index:
        prior_rules = manifests[index - 1].pool(4)
        prior_bars = {row["entity_key"]: row for row in days[index - 1].datasets.get("bar_1d_raw", ())}
        prior_ups = {
            key
            for key in prior_rules
            if decimal(prior_bars[key]["close"]) >= decimal(prior_bars[key]["price_limit_up"])
        }
        prior_heights = {key: _streak(days, manifests, index - 1, key) for key in prior_ups}
        prior_candidates = {key for key, height in prior_heights.items() if height is not None and height >= 2}
        observable_candidates = prior_candidates & tradable & rules
        if any(height is None for height in prior_heights.values()):
            results["limit.promotion_rate"] = MetricResult(
                None, ("HISTORY_GAP",), valid_count=len(observable_candidates), denominator_count=len(prior_ups)
            )
        else:
            put(
                "limit.promotion_rate",
                ratio(len(observable_candidates & ups), len(observable_candidates)),
                observable_candidates,
                len(observable_candidates),
            )
    amounts = {
        key: decimal(bars[key]["amount_cny"])
        for key in valid
        if key in bars and bars[key].get("amount_cny") is not None and decimal(bars[key]["amount_cny"]) >= 0
    }
    total = sum(amounts.values(), Decimal(0))
    put("liquidity.market_amount_cny", total if amounts else None, amounts, len(valid))
    ranked = sorted(amounts, key=lambda key: (-amounts[key], key))
    put(
        "liquidity.top20_amount_concentration",
        ratio(sum((amounts[key] for key in ranked[:20]), Decimal(0)), total),
        amounts,
        len(valid),
        null_reason="DENOMINATOR_ZERO" if total == 0 else "SOURCE_UNAVAILABLE",
    )
    historical = [
        batch["liquidity.market_amount_cny"].value
        for batch in previous_results
        if batch["liquidity.market_amount_cny"].value is not None
    ][-20:]
    results["liquidity.amount_ratio_20"] = (
        MetricResult(None, ("WARMING_UP",))
        if len(historical) < 20
        else MetricResult(
            ratio(total, sum(historical, Decimal(0)) / 20) if amounts else None,
            ("DENOMINATOR_ZERO",) if sum(historical, Decimal(0)) == 0 else () if amounts else ("SOURCE_UNAVAILABLE",),
            valid_count=len(historical),
            denominator_count=20,
        )
    )
    zero = {
        key
        for key in listed
        if any(m[0] == key and "SUSPENDED" in m[5] for m in manifest.members)
        or (key in bars and bars[key].get("volume_shares") is not None and decimal(bars[key]["volume_shares"]) == 0)
    }
    observable = {
        key
        for key in listed
        if key in valid and not any(m[0] == key and "STATUS_UNKNOWN" in m[5] for m in manifest.members)
    }
    put(
        "liquidity.zero_or_suspended_ratio",
        ratio(len(zero), len(listed)) if observable == listed else None,
        observable,
        len(listed),
    )
    amplitudes = [
        (decimal(bars[key]["high"]) - decimal(bars[key]["low"])) / decimal(bars[key]["prev_close"])
        for key in sorted(tradable)
    ]
    put("risk.median_amplitude", median(amplitudes) if amplitudes else None, tradable, len(tradable))
    excluded = len(listed - valid)
    if listed and (
        ratio(len(valid), len(listed)) < Decimal("0.998")
        or ratio(excluded, len(listed)) > Decimal("0.002")
        or excluded > 10
    ):
        results = {
            key: MetricResult(
                value.value,
                tuple(sorted(set(value.flags) | {"SCOPE_SLA_FAILED"})),
                value.missing,
                value.valid_count,
                value.denominator_count,
            )
            for key, value in results.items()
        }
    return results


def evaluate_market_days(
    days: Sequence[MarketDay], *, open_trade_dates: Sequence[date] | None = None
) -> tuple[MarketFeatureBatch, ...]:
    """受限真实输入路径。完整评分 fixture 直接调用纯算法，不能注入本路径。"""
    from src.schemas.platform.feature import FeatureRow
    from src.schemas.platform.enums import QualityStatus
    from .indicator_registry import F2_INDICATOR_DEFINITIONS

    if (
        not days
        or list(days) != sorted(days, key=lambda day: day.trade_date)
        or len({day.trade_date for day in days}) != len(days)
    ):
        raise ValueError("market days must be nonempty, unique, and ordered")
    if len(days) > 1 and open_trade_dates is None:
        raise ValueError("multi-day history requires an authoritative open trading calendar")
    if open_trade_dates is not None:
        calendar = tuple(open_trade_dates)
        if calendar != tuple(sorted(set(calendar))) or tuple(day.trade_date for day in days) != tuple(
            value for value in calendar if days[0].trade_date <= value <= days[-1].trade_date
        ):
            raise ValueError("market days must cover every open trading day in range")
    manifests = [freeze_market_scope(day) for day in days]
    batches, raw_history, emotion = [], [], []
    for index, day in enumerate(days):
        results = _raw_day(days, manifests, index, raw_history)
        raw_history.append(dict(results))
        for metric in NORMALIZED_METRICS:
            history = [
                MetricPoint(prior.trade_date, raw_history[j][metric].value, prior.cutoff_at)
                for j, prior in enumerate(days[:index])
            ]
            results["normalized." + metric] = normalize_metric(
                results[metric].value,
                history,
                trade_date=day.trade_date,
                cutoff_at=day.cutoff_at,
                negative=metric in NEGATIVE_METRICS,
            )
        for dimension, weights in DIMENSION_WEIGHTS.items():
            results["score." + dimension] = weighted_score(
                {key: results["normalized." + key].value for key in weights}, weights, namespace=PREFIX + "normalized."
            )
        raw = composite_emotion({key: results["score." + key].value for key in TOTAL_WEIGHTS})
        results["score.emotion_raw"] = raw
        emotion.append(raw.value)
        point = emotion_sequence(emotion)[-1]
        for metric, value in (
            ("score.emotion_smoothed", point.smoothed),
            ("regime.state", point.state),
            ("regime.transition_from", point.transition_from),
            ("regime.transition_trigger", point.trigger),
        ):
            results[metric] = MetricResult(
                value, raw.flags if value is None else (), raw.missing if value is None else ()
            )
        rows = []
        for metric, value in sorted(results.items()):
            output = F2_INDICATOR_DEFINITIONS[PREFIX + metric].output_schema[0]
            number = value.value
            if isinstance(number, Decimal):
                with localcontext() as context:
                    context.prec = 38
                    number = number.quantize(QUANTUM, rounding=ROUND_HALF_UP)
            audit_flags = set()
            if metric in RAW_SPECS and RAW_SPECS[metric][0] == "EXECUTABLE":
                coverage = value.coverage_ratio
                audit_flags = {
                    "VALID_COUNT:" + str(value.valid_count),
                    "DENOMINATOR_COUNT:" + str(value.denominator_count),
                    "COVERAGE_RATIO:"
                    + (format(coverage.quantize(QUANTUM), "f") if coverage is not None else "UNKNOWN"),
                }
            flags = tuple(
                sorted(
                    set(value.flags)
                    | audit_flags
                    | {"UNIVERSE_SCOPE_HASH:" + manifests[index].universe_scope_hash}
                    | {"MISSING:" + key for key in value.missing}
                )
            )
            rows.append(
                FeatureRow(
                    entity_key=AGGREGATE_KEY,
                    trade_date=day.trade_date,
                    indicator_id=PREFIX + metric,
                    definition_version="1.0.0",
                    value=number,
                    value_type=output.value_type,
                    unit=output.unit,
                    available_at=day.cutoff_at,
                    data_snapshot_id=day.data_snapshot_id,
                    calculation_run_id="wp0303-restricted",
                    quality_status=QualityStatus.PARTIAL
                    if number is None or {"SCOPE_SLA_FAILED", "HISTORY_GAP"} & set(flags)
                    else QualityStatus.COMPLETE,
                    data_flags=flags,
                )
            )
        batches.append(MarketFeatureBatch(manifests[index], MappingProxyType(results), tuple(rows)))
    return tuple(batches)


MARKET_CAPABILITIES = ("market_breadth", "market_emotion")


def unavailable_metrics() -> frozenset[str]:
    specs = f2_contracts()
    unavailable = {metric for metric, spec in specs.items() if spec["state"] in {"BLOCKED", "FIXTURE_ONLY"}}
    for metric, spec in specs.items():
        if any(dependency in unavailable for dependency in spec["dependencies"]):
            unavailable.add(metric)
    return frozenset(unavailable)


def validate_market_publication(snapshot, consumer_kind) -> None:
    """B1-B3 尚未闭合；任何入口均不能把发布成功解释成市场能力认证。"""
    from src.schemas.platform.enums import ConsumerKind

    if set(snapshot.certified_capabilities) & set(MARKET_CAPABILITIES):
        raise ValueError("market capability is blocked by upstream Dataset contracts")
    market = any(ref.indicator_id.startswith(PREFIX) for ref in snapshot.feature_partition_refs)
    if market and snapshot.publication_status.value != "PROVISIONAL":
        raise ValueError("market diagnostic publication must remain PROVISIONAL")
    if market and not set(MARKET_CAPABILITIES) <= set(snapshot.missing_capabilities):
        raise ValueError("market missing_capabilities must remain explicit")
    if market and consumer_kind is ConsumerKind.FORMAL_BACKTEST:
        raise ValueError("market capability is unavailable for Formal/Paper consumption")


def validate_market_definition(definition) -> None:
    from .indicator_registry import F2_INDICATOR_DEFINITIONS, IndicatorResolutionError

    expected = F2_INDICATOR_DEFINITIONS.get(definition.indicator_id)
    if expected is None or expected.definition_hash != definition.definition_hash:
        raise IndicatorResolutionError(
            "INDICATOR_UNREGISTERED_INPUT", "market definition must match its fixed registered contract"
        )
