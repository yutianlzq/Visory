from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from types import MappingProxyType
from typing import Any, Callable, Mapping, Sequence

from src.schemas.platform.hashing import compute_content_hash
from src.schemas.platform.indicator import (
    DatasetInputRef,
    FeatureInstance,
    FormulaType,
    IndicatorDefinition,
    ParameterDefinition,
    PublicationStatus,
)
from src.schemas.platform.indicator import IndicatorOutputDefinition


BuiltinCallable = Callable[..., object]


@dataclass(frozen=True, slots=True)
class BuiltinImplementation:
    builtin_id: str
    implementation_version: str
    implementation_hash: str
    callable: BuiltinCallable
    supported_parameter_schema: tuple[ParameterDefinition, ...]
    output_schema: tuple[IndicatorOutputDefinition, ...]


def _decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, bool) or isinstance(value, float):
        raise TypeError("builtin inputs require bool/float-free numeric values")
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise TypeError("non-finite Decimal values are not supported")
        return value
    if isinstance(value, int):
        return Decimal(value)
    raise TypeError(f"unsupported numeric input: {type(value).__name__}")


def _return_unadjusted(closes: Sequence[Any], prev_closes: Sequence[Any] | None = None, **_: Any) -> tuple[Decimal | None, ...]:
    previous = prev_closes or (None,) + tuple(closes[:-1])
    return tuple(
        None if _decimal(current) is None or _decimal(previous[index]) in (None, Decimal("0")) else _decimal(current) / _decimal(previous[index]) - Decimal("1")
        for index, current in enumerate(closes)
    )


def _return_point_in_time_adjusted(
    closes: Sequence[Any],
    adjustment_factors: Sequence[Any],
    **_: Any,
) -> tuple[Decimal | None, ...]:
    adjusted = tuple(
        None if _decimal(close) is None or _decimal(factor) is None else _decimal(close) * _decimal(factor)
        for close, factor in zip(closes, adjustment_factors)
    )
    return _return_unadjusted(adjusted)


def _moving_average(values: Sequence[Any], period: int = 20, **_: Any) -> tuple[Decimal | None, ...]:
    if period < 1:
        raise ValueError("period must be positive")
    decimals = [_decimal(value) for value in values]
    result: list[Decimal | None] = []
    for index in range(len(decimals)):
        window = decimals[max(0, index - period + 1) : index + 1]
        result.append(None if len(window) < period or any(item is None for item in window) else sum(window, Decimal("0")) / Decimal(period))
    return tuple(result)


def _volatility(values: Sequence[Any], period: int = 20, **_: Any) -> tuple[Decimal | None, ...]:
    means = _moving_average(values, period)
    decimals = [_decimal(value) for value in values]
    result: list[Decimal | None] = []
    for index, mean in enumerate(means):
        window = decimals[max(0, index - period + 1) : index + 1]
        if mean is None or any(item is None for item in window):
            result.append(None)
            continue
        variance = sum((item - mean) ** 2 for item in window if item is not None) / Decimal(period)
        result.append(variance.sqrt() / mean if mean != 0 else None)
    return tuple(result)


def _atr(highs: Sequence[Any], lows: Sequence[Any], closes: Sequence[Any], period: int = 14, **_: Any) -> tuple[Decimal | None, ...]:
    true_ranges: list[Decimal | None] = []
    previous_close: Decimal | None = None
    for high, low, close in zip(highs, lows, closes):
        high_value, low_value, close_value = _decimal(high), _decimal(low), _decimal(close)
        if high_value is None or low_value is None or close_value is None:
            true_ranges.append(None)
        elif previous_close is None:
            true_ranges.append(high_value - low_value)
        else:
            true_ranges.append(max(high_value - low_value, abs(high_value - previous_close), abs(low_value - previous_close)))
        previous_close = close_value
    return _moving_average(true_ranges, period)


def _identity(values: Sequence[Any], **_: Any) -> tuple[Any, ...]:
    return tuple(values)


def _turnover(volume_shares: Sequence[Any], shares_outstanding: Sequence[Any], **_: Any) -> tuple[Decimal | None, ...]:
    result: list[Decimal | None] = []
    for volume, outstanding in zip(volume_shares, shares_outstanding):
        volume_value, outstanding_value = _decimal(volume), _decimal(outstanding)
        result.append(None if volume_value is None or outstanding_value in (None, Decimal("0")) else volume_value / outstanding_value)
    return tuple(result)


def _price_limit_state(closes: Sequence[Any], limit_up: Sequence[Any], limit_down: Sequence[Any], **_: Any) -> tuple[str | None, ...]:
    result: list[str | None] = []
    for close, upper, lower in zip(closes, limit_up, limit_down):
        close_value, upper_value, lower_value = _decimal(close), _decimal(upper), _decimal(lower)
        if close_value is None or (upper_value is None and lower_value is None):
            result.append(None)
        elif upper_value is not None and close_value >= upper_value:
            result.append("LIMIT_UP")
        elif lower_value is not None and close_value <= lower_value:
            result.append("LIMIT_DOWN")
        else:
            result.append("NORMAL")
    return tuple(result)


def _identity_bool(values: Sequence[Any], **_: Any) -> tuple[bool | None, ...]:
    return tuple(None if value is None else bool(value) for value in values)


def _builtin_hash(builtin_id: str, implementation_version: str) -> str:
    return compute_content_hash({"builtin_id": builtin_id, "implementation_version": implementation_version})


def _builtin(
    builtin_id: str,
    implementation: BuiltinCallable,
    output_schema: tuple[IndicatorOutputDefinition, ...],
    parameter_schema: tuple[ParameterDefinition, ...] = (),
    implementation_version: str = "1.0.0",
) -> BuiltinImplementation:
    return BuiltinImplementation(
        builtin_id=builtin_id,
        implementation_version=implementation_version,
        implementation_hash=_builtin_hash(builtin_id, implementation_version),
        callable=implementation,
        supported_parameter_schema=parameter_schema,
        output_schema=output_schema,
    )


_PERIOD_20 = (ParameterDefinition(name="period", value_type="integer", required=False),)
_PERIOD_14 = (ParameterDefinition(name="period", value_type="integer", required=False),)
_RATIO_OUTPUT = (IndicatorOutputDefinition(alias="value", value_type="decimal", unit="ratio", nullable=True),)


BUILTIN_REGISTRY: Mapping[str, BuiltinImplementation] = MappingProxyType(
    {
        "return_unadjusted_builtin": _builtin("return_unadjusted_builtin", _return_unadjusted, _RATIO_OUTPUT),
        "return_point_in_time_adjusted_builtin": _builtin("return_point_in_time_adjusted_builtin", _return_point_in_time_adjusted, _RATIO_OUTPUT),
        "moving_average_builtin": _builtin(
            "moving_average_builtin",
            _moving_average,
            (IndicatorOutputDefinition(alias="value", value_type="decimal", unit="cny_per_share"),),
            _PERIOD_20,
        ),
        "volatility_builtin": _builtin("volatility_builtin", _volatility, _RATIO_OUTPUT, _PERIOD_20),
        "atr_builtin": _builtin(
            "atr_builtin",
            _atr,
            (IndicatorOutputDefinition(alias="value", value_type="decimal", unit="cny_per_share"),),
            _PERIOD_14,
        ),
        "volume_shares_builtin": _builtin(
            "volume_shares_builtin",
            _identity,
            (IndicatorOutputDefinition(alias="value", value_type="decimal", unit="shares"),),
        ),
        "amount_cny_builtin": _builtin(
            "amount_cny_builtin",
            _identity,
            (IndicatorOutputDefinition(alias="value", value_type="decimal", unit="cny"),),
        ),
        "turnover_ratio_builtin": _builtin("turnover_ratio_builtin", _turnover, _RATIO_OUTPUT),
        "adv20_builtin": _builtin("adv20_builtin", _moving_average, (IndicatorOutputDefinition(alias="value", value_type="decimal", unit="shares"),), _PERIOD_20),
        "price_limit_state_builtin": _builtin(
            "price_limit_state_builtin",
            _price_limit_state,
            (IndicatorOutputDefinition(alias="value", value_type="string", unit="code"),),
        ),
        "trading_halt_state_builtin": _builtin(
            "trading_halt_state_builtin",
            _identity,
            (IndicatorOutputDefinition(alias="value", value_type="string", unit="code"),),
        ),
        "listing_age_days_builtin": _builtin(
            "listing_age_days_builtin",
            _identity,
            (IndicatorOutputDefinition(alias="value", value_type="integer", unit="calendar_days"),),
        ),
        "basic_valuation_builtin": _builtin("basic_valuation_builtin", _identity, _RATIO_OUTPUT),
        "financial_available_flag_builtin": _builtin(
            "financial_available_flag_builtin",
            _identity_bool,
            (IndicatorOutputDefinition(alias="value", value_type="boolean", unit="boolean"),),
        ),
    }
)


def _definition(
    indicator_id: str,
    name: str,
    formula_ref: str,
    *,
    input_dataset_refs: tuple[DatasetInputRef, ...],
    output_schema: tuple[IndicatorOutputDefinition, ...],
    input_indicator_refs: tuple[Any, ...] = (),
    parameter_schema: tuple[ParameterDefinition, ...] = (),
    defaults: dict[str, Any] | None = None,
    lookback_requirement: int = 0,
    warmup_requirement: int = 0,
    adjustment_policy: str = "NONE",
    universe_policy: str = "ENTITY",
    capability_id: str | None = "market_bars_daily",
    point_in_time: bool = True,
    domain: str = "a_share",
    materialization: str = "F1_LONG_TERM",
) -> IndicatorDefinition:
    implementation = BUILTIN_REGISTRY[formula_ref]
    return IndicatorDefinition(
        indicator_id=indicator_id,
        name=name,
        domain=domain,
        frequency="1d",
        schema_version="1.0.0",
        definition_version="1.0.0",
        formula_type=FormulaType.PYTHON_BUILTIN,
        formula_ref=formula_ref,
        implementation_version=implementation.implementation_version,
        input_dataset_refs=input_dataset_refs,
        input_indicator_refs=input_indicator_refs,
        lookback_requirement=lookback_requirement,
        warmup_requirement=warmup_requirement,
        output_schema=output_schema,
        parameter_schema=parameter_schema,
        normalized_default_parameters=defaults or {},
        recompute_policy="DAILY_INCREMENTAL",
        adjustment_policy=adjustment_policy,
        universe_policy=universe_policy,
        asof_policy="AVAILABLE_AT",
        materialization=materialization,
        capability_id=capability_id,
        point_in_time=point_in_time,
        pit_review_version="1.0.0" if point_in_time else None,
        numeric_policy="DECIMAL",
        null_policy="PROPAGATE",
        owner="src.services.platform.indicator_registry",
        publication_status=PublicationStatus.PROVISIONAL,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def _bar(*fields: str) -> DatasetInputRef:
    return DatasetInputRef(dataset_id="bar_1d_raw", required_fields=tuple(fields))


_BAR = _bar


F1_INDICATOR_DEFINITIONS: Mapping[str, IndicatorDefinition] = MappingProxyType(
    {
        "return_unadjusted": _definition("return_unadjusted", "Unadjusted Return", "return_unadjusted_builtin", input_dataset_refs=(_BAR("close", "prev_close", "available_at"),), output_schema=_RATIO_OUTPUT),
        "return_point_in_time_adjusted": _definition(
            "return_point_in_time_adjusted",
            "Point-in-time Adjusted Return",
            "return_point_in_time_adjusted_builtin",
            input_dataset_refs=(
                _BAR("close", "available_at"),
                DatasetInputRef(dataset_id="corporate_action", required_fields=("entity_key", "ex_date", "factor", "available_at")),
            ),
            output_schema=_RATIO_OUTPUT,
            adjustment_policy="POINT_IN_TIME_CORPORATE_ACTION",
            capability_id="corporate_actions_daily",
        ),
        "moving_average": _definition(
            "moving_average",
            "Moving Average",
            "moving_average_builtin",
            input_dataset_refs=(_BAR("close", "available_at"),),
            output_schema=(IndicatorOutputDefinition(alias="value", value_type="decimal", unit="cny_per_share"),),
            parameter_schema=_PERIOD_20,
            defaults={"period": 20},
            lookback_requirement=20,
            warmup_requirement=20,
        ),
        "volatility": _definition(
            "volatility",
            "Volatility",
            "volatility_builtin",
            input_dataset_refs=(_BAR("close", "available_at"),),
            output_schema=_RATIO_OUTPUT,
            parameter_schema=_PERIOD_20,
            defaults={"period": 20},
            lookback_requirement=20,
            warmup_requirement=20,
        ),
        "atr": _definition(
            "atr",
            "Average True Range",
            "atr_builtin",
            input_dataset_refs=(_BAR("high", "low", "close", "available_at"),),
            output_schema=(IndicatorOutputDefinition(alias="value", value_type="decimal", unit="cny_per_share"),),
            parameter_schema=_PERIOD_14,
            defaults={"period": 14},
            lookback_requirement=14,
            warmup_requirement=14,
        ),
        "volume_shares": _definition("volume_shares", "Volume", "volume_shares_builtin", input_dataset_refs=(_BAR("volume_shares", "available_at"),), output_schema=(IndicatorOutputDefinition(alias="value", value_type="decimal", unit="shares"),)),
        "amount_cny": _definition("amount_cny", "Amount", "amount_cny_builtin", input_dataset_refs=(_BAR("amount_cny", "available_at"),), output_schema=(IndicatorOutputDefinition(alias="value", value_type="decimal", unit="cny"),)),
        "turnover_ratio": _definition(
            "turnover_ratio",
            "Turnover Ratio",
            "turnover_ratio_builtin",
            input_dataset_refs=(_BAR("volume_shares", "available_at"), DatasetInputRef(dataset_id="security_master", required_fields=("entity_key", "shares_outstanding", "available_at"))),
            output_schema=_RATIO_OUTPUT,
            capability_id="security_master_daily",
        ),
        "adv20": _definition(
            "adv20",
            "Average Daily Volume 20",
            "adv20_builtin",
            input_dataset_refs=(_BAR("volume_shares", "available_at"),),
            output_schema=(IndicatorOutputDefinition(alias="value", value_type="decimal", unit="shares"),),
            parameter_schema=_PERIOD_20,
            defaults={"period": 20},
            lookback_requirement=20,
            warmup_requirement=20,
        ),
        "price_limit_state": _definition(
            "price_limit_state",
            "Price Limit State",
            "price_limit_state_builtin",
            input_dataset_refs=(_BAR("close", "price_limit_up", "price_limit_down", "available_at"),),
            output_schema=(IndicatorOutputDefinition(alias="value", value_type="string", unit="code"),),
        ),
        "trading_halt_state": _definition(
            "trading_halt_state",
            "Trading Halt State",
            "trading_halt_state_builtin",
            input_dataset_refs=(
                _BAR("trading_status", "available_at"),
                DatasetInputRef(dataset_id="instrument_status_daily", required_fields=("entity_key", "trade_date", "trading_status", "available_at")),
            ),
            output_schema=(IndicatorOutputDefinition(alias="value", value_type="string", unit="code"),),
            capability_id="instrument_status_daily",
        ),
        "listing_age_days": _definition(
            "listing_age_days",
            "Listing Age Days",
            "listing_age_days_builtin",
            input_dataset_refs=(DatasetInputRef(dataset_id="listing_status_history", required_fields=("entity_key", "effective_from", "available_at")),),
            output_schema=(IndicatorOutputDefinition(alias="value", value_type="integer", unit="calendar_days"),),
            capability_id="listing_status_history",
        ),
        "basic_valuation": _definition(
            "basic_valuation",
            "Basic Valuation",
            "basic_valuation_builtin",
            input_dataset_refs=(
                _BAR("close", "available_at"),
                DatasetInputRef(dataset_id="financial_statement", required_fields=("entity_key", "line_item", "value", "available_at")),
            ),
            output_schema=_RATIO_OUTPUT,
            capability_id="financial_statement_available_at",
        ),
        "financial_available_flag": _definition(
            "financial_available_flag",
            "Financial Available Flag",
            "financial_available_flag_builtin",
            input_dataset_refs=(DatasetInputRef(dataset_id="financial_statement", required_fields=("entity_key", "available_at")),),
            output_schema=(IndicatorOutputDefinition(alias="value", value_type="boolean", unit="boolean"),),
            capability_id="financial_statement_available_at",
        ),
    }
)


class IndicatorResolutionError(ValueError):
    def __init__(self, code: str, message: str, *, details: Mapping[str, Any] | None = None) -> None:
        self.code = code
        self.details = dict(details or {})
        super().__init__(f"{code}: {message}")


def _semver_key(value: str) -> tuple[int, int, int, str]:
    core, _, suffix = value.partition("-")
    major, minor, patch = (int(part) for part in core.split("."))
    return major, minor, patch, suffix


def _normalize_parameter_value(definition: ParameterDefinition, value: Any) -> Any:
    if isinstance(value, float) or isinstance(value, bool) and definition.value_type == "integer":
        raise IndicatorResolutionError("INDICATOR_PARAMETER_INVALID", f"parameter {definition.name} has an invalid value type")
    if definition.value_type == "integer":
        if not isinstance(value, int) or isinstance(value, bool):
            raise IndicatorResolutionError("INDICATOR_PARAMETER_INVALID", f"parameter {definition.name} requires an integer")
        return value
    if definition.value_type == "decimal":
        if isinstance(value, bool) or not isinstance(value, (int, Decimal)):
            raise IndicatorResolutionError("INDICATOR_PARAMETER_INVALID", f"parameter {definition.name} requires an explicit Decimal or integer")
        try:
            normalized = Decimal(value)
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise IndicatorResolutionError("INDICATOR_PARAMETER_INVALID", f"parameter {definition.name} is not a finite decimal") from exc
        if not normalized.is_finite():
            raise IndicatorResolutionError("INDICATOR_PARAMETER_INVALID", f"parameter {definition.name} is not a finite decimal")
        return normalized
    if definition.value_type == "boolean":
        if not isinstance(value, bool):
            raise IndicatorResolutionError("INDICATOR_PARAMETER_INVALID", f"parameter {definition.name} requires a boolean")
        return value
    if definition.value_type == "string":
        if not isinstance(value, str):
            raise IndicatorResolutionError("INDICATOR_PARAMETER_INVALID", f"parameter {definition.name} requires a string")
        return value
    if definition.value_type == "enum":
        if not isinstance(value, str) or value not in definition.allowed_values:
            raise IndicatorResolutionError("INDICATOR_PARAMETER_INVALID", f"parameter {definition.name} is outside its enum domain")
        return value
    raise IndicatorResolutionError("INDICATOR_PARAMETER_INVALID", f"unsupported parameter type: {definition.value_type}")


def normalize_parameters(definition: IndicatorDefinition, parameters: Mapping[str, Any] | None = None) -> dict[str, Any]:
    supplied = dict(parameters) if parameters is not None else {}
    declarations = {item.name: item for item in definition.parameter_schema}
    unknown = sorted(set(supplied) - set(declarations))
    if unknown:
        raise IndicatorResolutionError("INDICATOR_PARAMETER_UNKNOWN", "parameter is not declared", details={"parameters": unknown})
    normalized: dict[str, Any] = {}
    for declaration in definition.parameter_schema:
        if declaration.name in supplied:
            normalized[declaration.name] = _normalize_parameter_value(declaration, supplied[declaration.name])
        elif declaration.name in definition.normalized_default_parameters:
            normalized[declaration.name] = _normalize_parameter_value(declaration, definition.normalized_default_parameters[declaration.name])
        elif declaration.required:
            raise IndicatorResolutionError("INDICATOR_PARAMETER_INVALID", f"required parameter is missing: {declaration.name}")
    return normalized


class IndicatorRegistry:
    def __init__(self, definitions: Sequence[IndicatorDefinition], *, builtins: Mapping[str, BuiltinImplementation] = BUILTIN_REGISTRY) -> None:
        items = tuple(definitions)
        keys = [(item.indicator_id, item.definition_version) for item in items]
        if len(keys) != len(set(keys)):
            raise ValueError("indicator definition keys must be unique")
        builtin_items = dict(builtins)
        if any(key != implementation.builtin_id for key, implementation in builtin_items.items()):
            raise ValueError("builtin registry keys must match builtin identifiers")
        self._definitions = MappingProxyType({key: item for key, item in zip(keys, items)})
        self._builtins = MappingProxyType(builtin_items)
        for definition in items:
            if definition.formula_type is not FormulaType.PYTHON_BUILTIN:
                raise ValueError("WP-0301 registry only accepts controlled PYTHON_BUILTIN implementations")
            implementation = self._builtins.get(definition.formula_ref)
            if implementation is None:
                raise ValueError(f"unknown controlled builtin: {definition.formula_ref}")
            if implementation.implementation_version != definition.implementation_version:
                raise ValueError(f"implementation version mismatch for {definition.indicator_id}")
            if implementation.implementation_hash != definition.implementation_hash:
                raise ValueError(f"implementation hash mismatch for {definition.indicator_id}")
            if implementation.supported_parameter_schema != definition.parameter_schema:
                raise ValueError(f"parameter schema mismatch for {definition.indicator_id}")
            if implementation.output_schema != definition.output_schema:
                raise ValueError(f"output schema mismatch for {definition.indicator_id}")

    def list(self) -> tuple[IndicatorDefinition, ...]:
        return tuple(self._definitions[key] for key in sorted(self._definitions))

    def get(self, indicator_id: str, definition_version: str | None = None) -> IndicatorDefinition:
        if definition_version is not None:
            definition = self._definitions.get((indicator_id, definition_version))
            if definition is None:
                if any(key[0] == indicator_id for key in self._definitions):
                    raise IndicatorResolutionError("INDICATOR_VERSION_UNKNOWN", "indicator definition version is unknown")
                raise IndicatorResolutionError("INDICATOR_UNKNOWN", "indicator is not registered")
            return definition
        candidates = [item for (item_id, _), item in self._definitions.items() if item_id == indicator_id]
        if not candidates:
            raise IndicatorResolutionError("INDICATOR_UNKNOWN", "indicator is not registered")
        return max(candidates, key=lambda item: _semver_key(item.definition_version))

    def create_instance(
        self,
        indicator_id: str,
        parameters: Mapping[str, Any] | None = None,
        *,
        definition_version: str | None = None,
        universe_scope_hash: str | None = None,
    ) -> FeatureInstance:
        definition = self.get(indicator_id, definition_version)
        normalized = normalize_parameters(definition, parameters)
        return FeatureInstance(
            indicator_id=definition.indicator_id,
            definition_version=definition.definition_version,
            parameters=normalized,
            universe_scope_hash=universe_scope_hash,
        )

    def implementation(self, formula_ref: str) -> BuiltinImplementation:
        try:
            return self._builtins[formula_ref]
        except KeyError as exc:
            raise IndicatorResolutionError("INDICATOR_BUILTIN_UNKNOWN", "controlled builtin is not registered") from exc


def default_indicator_registry() -> IndicatorRegistry:
    return IndicatorRegistry(tuple(F1_INDICATOR_DEFINITIONS.values()))


__all__ = [
    "BUILTIN_REGISTRY",
    "BuiltinImplementation",
    "F1_INDICATOR_DEFINITIONS",
    "IndicatorRegistry",
    "IndicatorResolutionError",
    "default_indicator_registry",
    "normalize_parameters",
]
