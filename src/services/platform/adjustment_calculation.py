from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from decimal import Context, Decimal, DecimalException, ROUND_HALF_EVEN, localcontext
from pathlib import Path
from platform import python_version

from pydantic import __version__ as pydantic_version
from decimal import __libmpdec_version__
from collections.abc import Mapping
from typing import Any

from src.schemas.platform.adjustment import (
    AdjustmentLineage,
    MethodRef,
    validate_adjustment_references,
)
from src.schemas.platform.adjustment_calculation import (
    FixtureAction, FixtureAdjustmentInput, FixtureCalculation, FixtureEventCalculation,
    FixtureExecutionLineageBridge, FixtureExecutionReceipt, FixtureFactorResult,
    FixtureFactorRow, FixtureSelectionRow, ImplementationSource, decimal_parameter,
    semantic_hash,
)

_CONTEXT = Context(prec=38, rounding=ROUND_HALF_EVEN)
_QUANTUM = Decimal('0.000000000000000001')
_UNITS = {'DIVIDEND': 'PRE_TAX_CNY_PER_PRE_EVENT_SHARE',
          'BONUS': 'NEW_FREE_SHARES_PER_PRE_EVENT_SHARE',
          'SPLIT': 'POST_SHARES_OVER_PRE_SHARES'}


def _byte_hash(data: bytes) -> str:
    return 'sha256:' + hashlib.sha256(data).hexdigest()


def _result_bytes_hash(result: FixtureFactorResult) -> str:
    return _byte_hash(result.result_bytes())


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'duplicate JSON key: {key}')
        result[key] = value
    return result


def _reject_number(value: str) -> None:
    raise ValueError(f'JSON float/nonfinite numeric token is forbidden: {value}')


def _read_fixture(raw: bytes) -> FixtureAdjustmentInput:
    if not isinstance(raw, bytes):
        raise ValueError('actual UTF-8 JSON input bytes are required')
    try:
        payload = json.loads(raw.decode('utf-8'), object_pairs_hook=_unique_pairs,
                             parse_float=_reject_number, parse_constant=_reject_number)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError('invalid UTF-8 JSON input') from error
    return FixtureAdjustmentInput.model_validate(payload)


def _validate_input(data: FixtureAdjustmentInput) -> datetime:
    b, a, c = data.base_trade_date, data.anchor_trade_date, data.cutoff_at
    if data.method.method_version != "1.0.0":
        raise ValueError("unsupported Method version for offline executable")
    if b > a or b not in data.calendar.sessions or a not in data.calendar.sessions:
        raise ValueError('base/anchor must be ordered pinned calendar sessions')
    known = [data.calendar, data.coverage, *data.identities, *data.prices, *data.actions, *data.groups]
    if any(r.available_at > c for r in known):
        raise ValueError('fixed input contains availability after cutoff')
    coverage = data.coverage
    if (coverage.cutoff_at != c or coverage.securities != data.securities
            or coverage.date_from > b or coverage.date_to < a
            or coverage.source_row_count != len(data.actions)):
        raise ValueError('coverage scope/interval/cutoff/source row count mismatch')
    identities = {r.entity_key: r for r in data.identities}
    if len(identities) != len(data.identities) or set(identities) != set(data.securities):
        raise ValueError('identity scope must be complete and unambiguous')
    if any(r.valid_from > b or r.valid_to < a for r in identities.values()):
        raise ValueError('identity validity must span fixed base/anchor')
    sessions = [t for t in data.calendar.sessions if b <= t <= a]
    expected = {(entity, t) for entity in data.securities for t in sessions}
    seen = set()
    for row in data.prices:
        key = row.entity_key, row.trade_date
        if key in seen:
            raise ValueError('duplicate price observation')
        seen.add(key)
        if row.entity_key not in identities or row.trade_date not in data.calendar.sessions:
            raise ValueError('price scope/session mismatch')
        if row.source_published_at.astimezone(timezone.utc).date() < row.trade_date:
            raise ValueError('raw price disclosure precedes its trade_date')
        identity = identities[row.entity_key]
        if not identity.valid_from <= row.trade_date <= identity.valid_to:
            raise ValueError('price identity outside validity')
        if row.observation_state != 'ACTUAL' or row.raw_close is None or Decimal(row.raw_close) <= 0:
            raise ValueError('price requires positive actual raw close; no fill or suspended fallback')
    if {k for k in seen if b <= k[1] <= a} != expected:
        raise ValueError('price observation grid incomplete; no zip truncation')
    for row in data.actions:
        _validate_action(row, identities, b, a, data.calendar.sessions)
    return max(r.available_at for r in known)


def _validate_action(row: FixtureAction, identities: dict, b: Any, a: Any, sessions: tuple) -> None:
    if row.entity_key not in identities:
        raise ValueError('action identity outside scope')
    if row.action_type not in _UNITS or row.action_subtype != 'ORDINARY':
        raise ValueError('unsupported action type/subtype; no silent omission')
    if row.share_basis != 'PRE_EVENT_OLD_SHARE' or row.quantity_unit != _UNITS[row.action_type]:
        raise ValueError('ambiguous share basis/quantity unit')
    if (row.action_type == 'DIVIDEND' and row.currency != 'CNY') or (
            row.action_type != 'DIVIDEND' and row.currency is not None):
        raise ValueError('action currency mismatch')
    if b <= row.ex_trade_date <= a and row.ex_trade_date not in sessions:
        raise ValueError('ex_date must be an exact pinned session')
    if row.record_date is not None and row.record_date >= row.ex_trade_date:
        raise ValueError('ordinary record_date must precede ex_date')
    if row.payment_date is not None and row.payment_date < row.ex_trade_date:
        raise ValueError('ordinary payment_date must not precede ex_date')
    # 取消可以不携带新数值，但取消证据仍需通过类型、身份和时间核验。
    if row.event_state == 'ACTIVE':
        if row.quantity is None or row.share_denominator is None:
            raise ValueError('active quantity/share_denominator are required, not implicit zero')
        if Decimal(row.quantity) <= 0 or Decimal(row.share_denominator) <= 0:
            raise ValueError('quantity and share_denominator must be positive')
        if row.action_type == 'SPLIT' and Decimal(row.quantity) <= Decimal(row.share_denominator):
            raise ValueError('ordinary split must increase total shares (s>1)')


def _select(data: FixtureAdjustmentInput) -> tuple[tuple[FixtureAction, ...], tuple[FixtureSelectionRow, ...]]:
    histories = {}
    for row in data.actions:
        histories.setdefault((row.entity_key, row.economic_event_key), []).append(row)
    selected, receipts = [], []
    for key in sorted(histories):
        history = sorted(histories[key], key=lambda r: r.revision)
        if [r.revision for r in history] != list(range(1, len(history)+1)):
            raise ValueError('fixture revisions must be unique consecutive integers beginning at one')
        identity = {(r.action_group_id, r.component_role, r.action_type) for r in history}
        if len(identity) != 1:
            raise ValueError('revision component identity conflict')
        for previous, current in zip(history, history[1:]):
            if (current.available_at <= previous.available_at
                    or current.source_published_at < previous.source_published_at):
                raise ValueError('revision availability must increase; publication must not decrease')
        latest = history[-1]
        if latest.event_state == 'CANCELLED':
            disposition = 'CANCELLED'
        elif not data.base_trade_date < latest.ex_trade_date <= data.anchor_trade_date:
            disposition = 'OUT_OF_RANGE'
        else:
            disposition = 'SELECTED'
            selected.append(latest)
        latest_hash = semantic_hash(latest)
        for row in history:
            receipts.append(FixtureSelectionRow(entity_key=row.entity_key,
                            economic_event_key=row.economic_event_key, revision=row.revision,
                            row_hash=semantic_hash(row), selected_revision=latest.revision,
                            selected_row_hash=latest_hash,
                            disposition=disposition if row == latest else 'SUPERSEDED'))
    selected.sort(key=lambda r: (r.entity_key, r.ex_trade_date, r.action_group_id,
                                r.component_role, r.economic_event_key, r.revision))
    return tuple(selected), tuple(receipts)


def _group_events(data: FixtureAdjustmentInput, selected: tuple[FixtureAction, ...]) -> dict:
    groups = {}
    for row in selected:
        groups.setdefault((row.entity_key, row.ex_trade_date, row.action_group_id), []).append(row)
    evidence = {}
    for group in data.groups:
        key = group.entity_key, group.ex_trade_date, group.action_group_id
        if key in evidence:
            raise ValueError('duplicate group confirmation')
        evidence[key] = group
    if set(evidence) != set(groups):
        raise ValueError('group confirmation must match all and only selected event groups')
    days = set()
    for key, rows in groups.items():
        if key[:2] in days:
            raise ValueError('ambiguous same-day multiple plans')
        days.add(key[:2])
        roles = [r.component_role for r in rows]
        if len(roles) != len(set(roles)) or tuple(sorted(roles)) != evidence[key].component_roles:
            raise ValueError('duplicate/missing/extra group component')
        if any(r.action_type == 'SPLIT' for r in rows) and len(rows) != 1:
            raise ValueError('SPLIT cannot combine with cash/bonus/another split')
    return groups


def _positive(value: Decimal, label: str) -> Decimal:
    if not value.is_finite() or value <= 0:
        raise ValueError(f'{label} must be positive finite')
    return value


def _calculate_events(data: FixtureAdjustmentInput, groups: dict) -> tuple[FixtureEventCalculation, ...]:
    prices = {(r.entity_key, r.trade_date): r for r in data.prices}
    events = []
    for (entity, ex, group_id), rows in sorted(groups.items()):
        index = data.calendar.sessions.index(ex)
        if index == 0:
            raise ValueError('reference price requires previous pinned session')
        prev = data.calendar.sessions[index-1]
        if (entity, prev) not in prices:
            raise ValueError('missing actual previous-session reference price')
        price = prices[entity, prev]
        p = Decimal(price.raw_close)
        d, b, split = Decimal(0), Decimal(0), None
        for row in rows:
            amount = Decimal(row.quantity) / Decimal(row.share_denominator)
            if row.action_type == 'DIVIDEND':
                d += amount
            elif row.action_type == 'BONUS':
                b += amount
            else:
                split = amount
        # 同组现金/无偿股先求和，只在共同旧股基数上算一次 Q/q。
        q_price = (p-d) / (split if split is not None else Decimal(1)+b)
        _positive(q_price, 'theoretical reference price Q')
        q = _positive(q_price/p, 'event q')
        events.append(FixtureEventCalculation(entity_key=entity, ex_trade_date=ex, action_group_id=group_id,
                      selected_row_hashes=tuple(semantic_hash(r) for r in rows), reference_trade_date=prev,
                      reference_row_hash=semantic_hash(price), reference_price=price.raw_close,
                      cash_per_old_share=decimal_parameter(d), bonus_new_shares_per_old_share=decimal_parameter(b),
                      split_total_share_multiplier=decimal_parameter(split) if split is not None else None,
                      theoretical_reference_price=decimal_parameter(q_price), q=decimal_parameter(q)))
    return tuple(events)


def _factor_text(value: Decimal) -> str:
    _positive(value, 'factor')
    if value >= Decimal('1e20'):
        raise ValueError('factor output integer precision overflow')
    value = value.quantize(_QUANTUM)
    if value <= 0:
        raise ValueError('factor quantized to zero')
    return format(value, '.18f')


def _implementation_sources() -> tuple[ImplementationSource, ...]:
    root = Path(__file__).resolve().parents[3]
    # 固定闭包的实际源码字节，不以 algorithm_version 标签冒充源码指纹。
    paths = ('src/schemas/platform/base.py', 'src/schemas/platform/hashing.py',
             'src/schemas/platform/adjustment.py', 'src/schemas/platform/adjustment_calculation.py',
             'src/services/platform/adjustment_calculation.py')
    return tuple(ImplementationSource(source_path=p, source_hash=_byte_hash((root/p).read_bytes())) for p in paths)


_LOADED_IMPLEMENTATION_SOURCES = _implementation_sources()


def calculate_fixture(raw_input: bytes, *, materialized_at: datetime) -> FixtureCalculation:
    """仅计算合成固定字节；不查 Provider/DB、存储、发布或改变认证门禁。"""
    data = _read_fixture(raw_input)
    available = _validate_input(data)
    if not isinstance(materialized_at, datetime) or materialized_at.tzinfo is None or materialized_at.utcoffset() is None:
        raise ValueError('materialized_at must be aware datetime')
    if materialized_at < available:
        raise ValueError('materialized_at must not precede required input availability')
    selected, selection = _select(data)
    groups = _group_events(data, selected)
    try:
        # 不依赖调用方 context；各次除法、求和和有序连乘均用固定 38 位 context。
        with localcontext(_CONTEXT):
            events = _calculate_events(data, groups)
            rows = []
            for price in data.prices:
                t = price.trade_date
                if not data.base_trade_date <= t <= data.anchor_trade_date:
                    continue
                value = Decimal(1)
                for event in events:
                    if event.entity_key != price.entity_key:
                        continue
                    if data.method.direction == 'FORWARD_FIXED_ANCHOR':
                        if t < event.ex_trade_date <= data.anchor_trade_date:
                            value *= Decimal(event.q)
                    elif data.base_trade_date < event.ex_trade_date <= t:
                        value *= Decimal(1)/Decimal(event.q)
                rows.append(FixtureFactorRow(entity_key=price.entity_key, trade_date=t,
                            factor=_factor_text(value), available_at=available))
    except DecimalException as error:
        raise ValueError('decimal arithmetic/precision overflow') from error
    input_hash, selection_hash = semantic_hash(data.semantic_payload()), semantic_hash(selection)
    method_ref = MethodRef.from_method(data.method)
    result = FixtureFactorResult(method_ref=method_ref, direction=data.method.direction,
                 base_trade_date=data.base_trade_date, anchor_trade_date=data.anchor_trade_date,
                 cutoff_at=data.cutoff_at, input_semantic_hash=input_hash, selection_hash=selection_hash, rows=tuple(rows))
    terminal_dispositions = tuple(
        row.disposition for row in selection if row.revision == row.selected_revision
    )
    if not data.actions:
        selection_status = 'TRUE_NO_ACTION'
    elif terminal_dispositions and all(value == 'SELECTED' for value in terminal_dispositions):
        selection_status = 'SELECTED_ACTIONS'
    elif terminal_dispositions and all(value == 'CANCELLED' for value in terminal_dispositions):
        selection_status = 'ALL_CANCELLED'
    elif terminal_dispositions and all(value == 'OUT_OF_RANGE' for value in terminal_dispositions):
        selection_status = 'ALL_OUT_OF_RANGE'
    else:
        selection_status = 'PARTIAL_SELECTION'
    sources = _implementation_sources()
    if sources != _LOADED_IMPLEMENTATION_SOURCES:
        raise ValueError("loaded implementation/source bytes changed; reload before execution")
    receipt = FixtureExecutionReceipt(method_ref=method_ref, fixture_instance_id=data.fixture_instance_id,
                 raw_input_hash=_byte_hash(raw_input), input_semantic_hash=input_hash,
                 action_rows_hash=semantic_hash(data.actions), calendar_hash=semantic_hash(data.calendar),
                 identity_rows_hash=semantic_hash(data.identities), price_rows_hash=semantic_hash(data.prices),
                 coverage_hash=semantic_hash(data.coverage), group_rows_hash=semantic_hash(data.groups),
                 source_row_count=len(data.actions), selection_status=selection_status,
                 selection_rows=selection, selection_hash=selection_hash, event_calculations=events,
                 implementation_sources=sources, implementation_digest=semantic_hash(sources),
                 runtime_versions=(('python', python_version()), ('libmpdec', __libmpdec_version__), ('pydantic', pydantic_version)),
                 result_content_hash=result.content_hash, result_bytes_hash=_result_bytes_hash(result),
                 input_available_at=available, materialized_at=materialized_at)
    return FixtureCalculation(result=result, receipt=receipt)


def verify_fixture_execution(raw_input: bytes, execution: FixtureCalculation) -> None:
    """从实际字节重新选择、运算、seal；不是只相信传入的 Hash 声明。"""
    actual = calculate_fixture(raw_input, materialized_at=execution.receipt.materialized_at)
    if actual != execution:
        raise ValueError('execution does not match actual input/source bytes and calculation')


_BRIDGE_GRAPH_KEYS = (
    'lineage', 'methods', 'snapshots', 'partitions', 'provider_runs',
    'raw_objects', 'quality_reports',
)


def _validated_bridge_graph(graph: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(graph, Mapping):
        raise ValueError('bridge graph must be a mapping')
    missing = tuple(key for key in _BRIDGE_GRAPH_KEYS if key not in graph)
    if missing:
        raise ValueError(f'missing bridge graph objects: {", ".join(missing)}')
    values = {key: graph[key] for key in _BRIDGE_GRAPH_KEYS}
    if not isinstance(values['lineage'], AdjustmentLineage):
        raise ValueError('unexpected bridge lineage contract type')
    validate_adjustment_references(**values)
    values['lineage'] = AdjustmentLineage.model_validate(
        values['lineage'].model_dump(mode='python')
    )
    return values


def _selected_fixture_actions(
    data: FixtureAdjustmentInput,
    execution: FixtureCalculation,
) -> tuple[FixtureAction, ...]:
    actions = {
        (row.entity_key, row.economic_event_key, row.revision): row
        for row in data.actions
    }
    selected = []
    for receipt_row in execution.receipt.selection_rows:
        if receipt_row.disposition != 'SELECTED':
            continue
        key = (
            receipt_row.entity_key,
            receipt_row.economic_event_key,
            receipt_row.revision,
        )
        action = actions.get(key)
        if action is None or semantic_hash(action) != receipt_row.row_hash:
            raise ValueError('selected receipt row does not match actual fixture action')
        selected.append(action)
    return tuple(selected)


def _verify_selected_event_refs(
    actions: tuple[FixtureAction, ...],
    lineage: AdjustmentLineage,
) -> None:
    refs = {
        (ref.economic_event_key, ref.revision): ref
        for ref in lineage.selected_event_refs
    }
    if len(refs) != len(lineage.selected_event_refs) or len(refs) != len(actions):
        raise ValueError('lineage selection does not exactly match receipt selection')
    coverage_pages = set(lineage.coverage_receipt.page_raw_object_refs)
    for action in actions:
        ref = refs.get((action.economic_event_key, action.revision))
        if ref is None:
            raise ValueError('lineage is missing a selected receipt event')
        if (
            ref.action_group_id != action.action_group_id
            or ref.action_type != action.action_type
            or ref.event_state != action.event_state
            or ref.event_hash != semantic_hash(action)
            or ref.ex_trade_date != action.ex_trade_date
            or ref.source_published_at < action.source_published_at
            or ref.available_at < action.available_at
            or ref.raw_object_id not in coverage_pages
        ):
            raise ValueError('lineage selected event does not match actual fixture action')


def bridge_fixture_execution(
    raw_input: bytes,
    execution: FixtureCalculation,
    *,
    execution_revision: int,
    graph: Mapping[str, Any],
) -> FixtureExecutionLineageBridge:
    """Bind a verified fixture execution to an already valid DERIVED lineage graph."""
    verify_fixture_execution(raw_input, execution)
    data = _read_fixture(raw_input)
    receipt = execution.receipt
    result = execution.result

    now = datetime.now(timezone.utc)
    if any(value > now for value in (
        data.cutoff_at, receipt.input_available_at, receipt.materialized_at,
    )):
        raise ValueError('future cutoff, availability or materialization is not allowed')
    if receipt.selection_status not in {'TRUE_NO_ACTION', 'SELECTED_ACTIONS'}:
        raise ValueError('nonempty cancel, out-of-range or partial selection state is not bridgeable')
    if receipt.source_row_count == 0:
        if receipt.selection_status != 'TRUE_NO_ACTION':
            raise ValueError('empty source must be an explicit true zero action')
    elif receipt.selection_status != 'SELECTED_ACTIONS':
        raise ValueError('nonempty source cannot become an empty action selection')

    values = _validated_bridge_graph(graph)
    lineage = values['lineage']
    if receipt.source_row_count == 0 and lineage.selected_event_refs:
        raise ValueError('empty source must have no selected lineage events')
    if not (
        lineage.method_ref == receipt.method_ref == result.method_ref
        and lineage.base_trade_date == result.base_trade_date == data.base_trade_date
        and lineage.anchor_trade_date == result.anchor_trade_date == data.anchor_trade_date
        and lineage.cutoff_at == result.cutoff_at == data.cutoff_at
    ):
        raise ValueError('execution and DERIVED lineage identity mismatch')
    coverage = lineage.coverage_receipt
    if (
        coverage.universe_scope_hash != semantic_hash(data.securities)
        or coverage.date_from > data.base_trade_date
        or coverage.date_to < data.anchor_trade_date
        or coverage.cutoff_at != data.coverage.cutoff_at
        or coverage.source_row_count != receipt.source_row_count
        or coverage.source_row_count != data.coverage.source_row_count
        or coverage.event_type_coverage != data.coverage.event_type_coverage
        or coverage.end_marker != data.coverage.end_marker
    ):
        raise ValueError('coverage scope, interval or source receipt mismatch')

    selected = _selected_fixture_actions(data, execution)
    terminal_count = sum(
        row.revision == row.selected_revision
        for row in receipt.selection_rows
    )
    if terminal_count != len({
        (row.entity_key, row.economic_event_key) for row in data.actions
    }):
        raise ValueError('selection receipt omits an event revision history')
    if receipt.selection_status == 'SELECTED_ACTIONS' and len(selected) != terminal_count:
        raise ValueError('partial source selection is not bridgeable')
    _verify_selected_event_refs(selected, lineage)

    return FixtureExecutionLineageBridge(
        execution_revision=execution_revision,
        receipt=receipt,
        result=result,
        lineage=lineage,
        coverage_receipt=coverage,
        quality_evidence=lineage.quality_evidence,
        selected_event_refs=lineage.selected_event_refs,
        method_contract_hash=receipt.method_ref.method_contract_hash,
        formula_digest=receipt.method_ref.formula_digest,
        algorithm_version=receipt.algorithm_version,
        implementation_digest=receipt.implementation_digest,
        raw_input_hash=receipt.raw_input_hash,
        input_semantic_hash=receipt.input_semantic_hash,
        result_content_hash=receipt.result_content_hash,
        result_bytes_hash=receipt.result_bytes_hash,
        cutoff_at=result.cutoff_at,
        input_available_at=receipt.input_available_at,
        materialized_at=receipt.materialized_at,
    )


def verify_fixture_execution_bridge(
    raw_input: bytes,
    bridge: FixtureExecutionLineageBridge,
    *,
    graph: Mapping[str, Any],
) -> None:
    """Rebuild the bridge from bytes and graph so resealing cannot hide forgery."""
    actual_bridge = FixtureExecutionLineageBridge.model_validate(
        bridge.model_dump(mode='python')
    )
    execution = FixtureCalculation(
        result=actual_bridge.result,
        receipt=actual_bridge.receipt,
    )
    verify_fixture_execution(raw_input, execution)
    rebuilt = bridge_fixture_execution(
        raw_input,
        execution,
        execution_revision=actual_bridge.execution_revision,
        graph=graph,
    )
    if rebuilt != actual_bridge:
        raise ValueError('bridge does not match actual input, execution and lineage graph')
