from __future__ import annotations

import copy
import hashlib
import importlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.schemas.platform.adjustment import AdjustmentMethod, MethodRef

GOLDEN = Path(__file__).resolve().parents[1] / 'golden/platform/adjustment-calculation'
C0 = '2026-08-31T08:00:00Z'
C1 = '2026-09-01T08:00:00Z'
T0, T1, T2 = '2026-08-27', '2026-08-28', '2026-08-31'
KNOWN = dict(source_published_at='2026-08-26T08:00:00Z', available_at='2026-08-26T09:00:00Z')
CLOCK = datetime(2026, 9, 2, 8, tzinfo=timezone.utc)


def event(kind='DIVIDEND', quantity='1', *, key='cash_a', ex=T1, revision=1, **changes):
    units = {'DIVIDEND': 'PRE_TAX_CNY_PER_PRE_EVENT_SHARE',
             'BONUS': 'NEW_FREE_SHARES_PER_PRE_EVENT_SHARE',
             'SPLIT': 'POST_SHARES_OVER_PRE_SHARES'}
    return dict(entity_key='fixture_security', economic_event_key=key, action_group_id='plan_a',
                component_role=key, revision=revision, event_state='ACTIVE', action_type=kind,
                action_subtype='ORDINARY', share_basis='PRE_EVENT_OLD_SHARE',
                quantity=quantity, share_denominator='1', quantity_unit=units.get(kind, 'UNKNOWN'),
                currency='CNY' if kind == 'DIVIDEND' else None, ex_trade_date=ex,
                record_date=T0 if ex == T1 else T1, payment_date=None,
                **{**KNOWN, **changes})


def fixture(actions=(), *, direction='FORWARD_FIXED_ANCHOR', end=T2, closes=('10', '9', '9')):
    sessions = [T0, T1, T2]
    latest = {}
    for row in actions:
        k = row['economic_event_key']
        if k not in latest or row['revision'] > latest[k]['revision']:
            latest[k] = row
    groups = {}
    for row in latest.values():
        if row['event_state'] == 'ACTIVE' and T0 < row['ex_trade_date'] <= end:
            k = row['entity_key'], row['ex_trade_date'], row['action_group_id']
            groups.setdefault(k, []).append(row['component_role'])
    return dict(fixture_kind='FIXTURE_ONLY', input_contract_version='1.0.0', fixture_instance_id='fixture_c0',
                method=AdjustmentMethod(direction=direction).model_dump(mode='json'),
                securities=['fixture_security'], base_trade_date=T0, anchor_trade_date=end, cutoff_at=C0,
                calendar=dict(sessions=sessions, **KNOWN),
                identities=[dict(entity_key='fixture_security', valid_from=T0, valid_to=T2,
                                 identity_state='CONFIRMED', **KNOWN)],
                prices=[dict(entity_key='fixture_security', trade_date=t, raw_close=p, currency='CNY',
                             observation_state='ACTUAL', source_published_at=t+'T07:00:00Z',
                             available_at=t+'T07:00:00Z') for t, p in zip(sessions, closes) if t <= end],
                actions=list(actions),
                groups=[dict(entity_key=k[0], ex_trade_date=k[1], action_group_id=k[2],
                             component_roles=roles, share_basis='PRE_EVENT_OLD_SHARE',
                             confirmation_state='COMPLETE', **KNOWN) for k, roles in groups.items()],
                coverage=dict(securities=['fixture_security'], date_from=T0, date_to=end,
                              cutoff_at=C0, coverage_status='COMPLETE', source_row_count=len(actions),
                              event_type_coverage=['BONUS', 'DIVIDEND', 'OTHER', 'RIGHTS', 'SPLIT'],
                              end_marker='fixture_exhaustive_end', **KNOWN))


def run(data, *, clock=CLOCK, raw=None):
    module = importlib.import_module('src.services.platform.adjustment_calculation')
    raw = raw if raw is not None else json.dumps(data, ensure_ascii=False).encode('utf-8')
    return module.calculate_fixture(raw, materialized_at=clock)


def factors(execution):
    return [row.factor for row in execution.result.rows]


def rejection(data, match):
    with pytest.raises(ValueError, match=match):
        run(data)


# 先写拒绝路径：不允许过滤未来行、以缺失冒充无行动或同日逐组件累乘。
def test_future_revision_is_rejected_not_filtered():
    e = event(revision=2, available_at=C1, source_published_at=C1)
    rejection(fixture([event(), e]), 'cutoff')


def test_incomplete_zero_action_coverage_is_not_factor_one():
    data = fixture(); data['coverage']['coverage_status'] = 'PARTIAL'
    rejection(data, 'COMPLETE')


def test_duplicate_component_is_not_summed_twice():
    data = fixture([event(), event(key='alias')])
    data['actions'][1]['component_role'] = 'cash_a'
    rejection(data, 'component')


@pytest.mark.parametrize('direction,expected', [
    ('FORWARD_FIXED_ANCHOR', ['0.800000000000000000', '1.000000000000000000', '1.000000000000000000']),
    ('BACKWARD_FIXED_BASE', ['1.000000000000000000', '1.250000000000000000', '1.250000000000000000']),
])
def test_two_cash_components_combine_once_not_point81(direction, expected):
    execution = run(fixture([event(), event(key='cash_b')], direction=direction, closes=('10', '8', '8')))
    assert factors(execution) == expected
    assert execution.receipt.event_calculations[0].q == '0.8'


@pytest.mark.parametrize('name,actions,closes,forward,backward', [
    ('a01_no_action', [], ('10', '11', '11'), ['1', '1', '1'], ['1', '1', '1']),
    ('a02_cash', [event()], ('10', '9', '9'), ['0.9', '1', '1'], ['1', '1.111111111111111111', '1.111111111111111111']),
    ('a03_cash_bonus', [event(), event('BONUS', '0.5', key='bonus_a')], ('10', '6', '6'), ['0.6', '1', '1'], ['1', '1.666666666666666667', '1.666666666666666667']),
    ('a04_split', [event('SPLIT', '2', key='split_a')], ('10', '5', '5'), ['0.5', '1', '1'], ['1', '2', '2']),
    ('bonus_only', [event('BONUS', '1', key='bonus_a')], ('10', '5', '5'), ['0.5', '1', '1'], ['1', '2', '2']),
    ('a05_chain', [event(), {**event('SPLIT', '2', key='split_a', ex=T2), 'action_group_id': 'plan_b'}], ('10', '9', '4.5'), ['0.45', '0.5', '1'], ['1', '1.111111111111111111', '2.222222222222222222']),
])
def test_hand_calculation_and_decimal_golden(name, actions, closes, forward, backward):
    for direction, expected in [('FORWARD_FIXED_ANCHOR', forward), ('BACKWARD_FIXED_BASE', backward)]:
        execution = run(fixture(actions, closes=closes, direction=direction))
        expected = [v + '0' * (18-len(v.split('.')[1])) if '.' in v else v+'.'+'0'*18 for v in expected]
        assert factors(execution) == expected
        golden = json.loads((GOLDEN / 'factor-results.json').read_text(encoding='utf-8'))
        record = golden[f'{name}-{direction.lower()}']
        saved = json.dumps(record['canonical_result'], sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        assert record['content_hash'] == execution.result.content_hash
        assert execution.result.result_bytes() == saved
        assert execution.result.content_hash == 'sha256:' + hashlib.sha256(saved).hexdigest()


def test_a03_explicit_per_ten_share_conversion():
    actions = [{**event(quantity='10'), 'share_denominator': '10'},
               {**event('BONUS', '5', key='bonus_a'), 'share_denominator': '10'}]
    assert factors(run(fixture(actions))) == ['0.600000000000000000', '1.000000000000000000', '1.000000000000000000']


def test_a07_future_effective_and_base_date_have_receipt_but_no_jump():
    future = event(ex=T2)
    data = fixture([future, {**event(key='base_event', ex=T0), 'record_date': '2026-08-26'}], end=T1)
    execution = run(data)
    assert factors(execution) == ['1.000000000000000000'] * 2
    assert [r.disposition for r in execution.receipt.selection_rows] == ['OUT_OF_RANGE', 'OUT_OF_RANGE']
    assert execution.receipt.selection_status == 'ALL_OUT_OF_RANGE'


def test_a08_previous_actual_close_not_ex_day_reference():
    data = fixture([event()], end=T1)
    execution = run(data)
    assert execution.receipt.event_calculations[0].reference_trade_date.isoformat() == T0
    assert execution.receipt.event_calculations[0].reference_price == '10'
    data['actions'][0]['record_date'] = T1
    rejection(data, 'record_date')


@pytest.mark.parametrize('target', ['actions', 'prices', 'identities', 'groups'])
def test_all_input_availability_including_unused_rows_is_checked(target):
    data = fixture([event()]); data[target][0]['available_at'] = C1
    rejection(data, 'cutoff')


@pytest.mark.parametrize('target', ['calendar', 'coverage'])
def test_future_singleton_receipt_or_calendar_rejected(target):
    data = fixture(); data[target]['available_at'] = C1
    rejection(data, 'cutoff')


def test_published_after_available_and_operation_clock_before_inputs():
    data = fixture([event()]); data['actions'][0]['source_published_at'] = C1
    rejection(data, 'published')
    with pytest.raises(ValueError, match='materialized_at'):
        run(fixture(), clock=datetime(2026, 8, 1, tzinfo=timezone.utc))


@pytest.mark.parametrize('kind', ['OTHER', 'RIGHTS', 'UNKNOWN'])
def test_unsupported_action_never_disappears(kind):
    rejection(fixture([event(kind)]), 'unsupported')


@pytest.mark.parametrize('patch', [dict(action_subtype='RESTRUCTURING'), dict(share_basis='POST_EVENT'),
                                   dict(quantity_unit='UNKNOWN'), dict(currency='USD')])
def test_ambiguous_source_semantics_rejected(patch):
    data = fixture([{**event(), **patch}]); rejection(data, 'subtype|basis|unit|currency')


@pytest.mark.parametrize('quantity', [None, '0', '-1', 'NaN', 'Infinity', '1e-2', 0.5, 1])
def test_invalid_or_ambiguous_quantity_is_not_zero(quantity):
    rejection(fixture([event(quantity=quantity)]), 'quantity|decimal|float')


@pytest.mark.parametrize('patch', [dict(share_denominator=None), dict(share_denominator='0'),
                                   dict(share_denominator='-10'), dict(share_denominator=10)])
def test_conversion_requires_positive_explicit_denominator(patch):
    rejection(fixture([{**event(), **patch}]), 'denominator|decimal')


@pytest.mark.parametrize('actions', [
    [event(), event('SPLIT', '2', key='split_a')],
    [event('SPLIT', '2', key='split_a'), event('SPLIT', '2', key='split_b')],
    [event(), {**event(key='cash_b'), 'action_group_id': 'different_plan'}],
])
def test_same_day_unapproved_combinations_fail_closed(actions):
    rejection(fixture(actions), 'same.day|SPLIT')


def test_group_roster_missing_extra_or_duplicate():
    for roles in ([], ['cash_a', 'missing'], ['cash_a', 'cash_a']):
        data = fixture([event()]); data['groups'][0]['component_roles'] = roles
        rejection(data, 'component')
    data = fixture([event()]); data['groups'] = []
    rejection(data, 'group')
    data = fixture(); data['groups'] = fixture([event()])['groups']
    rejection(data, 'group')


@pytest.mark.parametrize('actions', [
    [event(), event()],
    [event(), event(revision=3)],
    [event(), event(revision=2)],  # availability未严格单调
    [event(), {**event(revision=2, available_at='2026-08-27T09:00:00Z'), 'component_role': 'changed'}],
])
def test_duplicate_gapped_nonmonotonic_or_conflicting_revisions(actions):
    rejection(fixture(actions), 'revision|identity')


def test_selected_highest_revision_and_cancelled_history_all_accounted_for():
    newer = event(revision=2, quantity='2', available_at='2026-08-27T09:00:00Z')
    execution = run(fixture([event(), newer]))
    assert [r.disposition for r in execution.receipt.selection_rows] == ['SUPERSEDED', 'SELECTED']
    assert [r.selected_revision for r in execution.receipt.selection_rows] == [2, 2]
    assert factors(execution)[0] == '0.800000000000000000'
    cancelled = {**newer, 'event_state': 'CANCELLED', 'quantity': None, 'share_denominator': None}
    execution = run(fixture([event(), cancelled]))
    assert [r.disposition for r in execution.receipt.selection_rows] == ['SUPERSEDED', 'CANCELLED']
    assert factors(execution) == ['1.000000000000000000'] * 3


@pytest.mark.parametrize('field,value', [('raw_close', None), ('raw_close', '0'), ('raw_close', '-1'),
                                        ('raw_close', 'NaN'), ('observation_state', 'SUSPENDED')])
def test_invalid_reference_price_not_filled(field, value):
    data = fixture([event()]); data['prices'][0][field] = value
    rejection(data, 'price|close|ACTUAL|decimal')


@pytest.mark.parametrize('quantity', ['10', '11'])
def test_nonpositive_q_rejected(quantity):
    rejection(fixture([event(quantity=quantity)]), 'positive')


@pytest.mark.parametrize('s', ['0', '-1', '1', '0.5', '10000000000000000000'])
def test_illegal_split_or_quantized_zero(s):
    rejection(fixture([event('SPLIT', s, key='split_a')]), 'positive|split|quantized')


def test_factor_output_overflow_rejected():
    actions = [event('SPLIT', '100000000000', key='split_a'),
               {**event('SPLIT', '100000000000', key='split_b', ex=T2), 'action_group_id': 'plan_b'}]
    rejection(fixture(actions, direction='BACKWARD_FIXED_BASE'), 'overflow')


@pytest.mark.parametrize('case', ['missing', 'duplicate', 'entity', 'calendar', 'identity', 'ex_non_session'])
def test_join_no_zip_truncation_or_calendar_identity_fallback(case):
    data = fixture([event()])
    if case == 'missing': data['prices'].pop(0)
    elif case == 'duplicate': data['prices'].append(copy.deepcopy(data['prices'][0]))
    elif case == 'entity': data['prices'][0]['entity_key'] = 'other'
    elif case == 'calendar': data['calendar']['sessions'].pop(0)
    elif case == 'identity': data['identities'][0]['identity_state'] = 'UNKNOWN'
    else: data['actions'][0]['ex_trade_date'] = '2026-08-29'
    rejection(data, 'price|duplicate|scope|session|identity|CONFIRMED')


@pytest.mark.parametrize('case', ['missing', 'rows', 'scope', 'end', 'interval', 'types', 'cutoff'])
def test_n01_n02_full_positive_coverage_binding(case):
    data = fixture()
    if case == 'missing': data.pop('coverage')
    elif case == 'rows': data['coverage']['source_row_count'] = 1
    elif case == 'scope': data['coverage']['securities'] = ['other']
    elif case == 'end': data['coverage']['end_marker'] = ''
    elif case == 'interval': data['coverage']['date_to'] = T1
    elif case == 'types': data['coverage']['event_type_coverage'] = ['DIVIDEND']
    else: data['coverage']['cutoff_at'] = C1
    rejection(data, 'coverage|end_marker|type')


def test_c0_c1_restatement_and_cancellation_do_not_mutate_old_inputs_or_result():
    for direction in ('FORWARD_FIXED_ANCHOR', 'BACKWARD_FIXED_BASE'):
        c0 = fixture([event()], direction=direction); original = copy.deepcopy(c0)
        old = run(c0); old_bytes = old.result.result_bytes()
        newer = event(revision=2, quantity='2', source_published_at=C1, available_at=C1)
        c1 = fixture([event(), newer], direction=direction)
        c1['cutoff_at'] = c1['coverage']['cutoff_at'] = C1
        revised = run(c1)
        indices = [i for i, (a, b) in enumerate(zip(factors(old), factors(revised))) if a != b]
        assert indices == ([0] if direction == 'FORWARD_FIXED_ANCHOR' else [1, 2])
        cancel = {**newer, 'event_state': 'CANCELLED', 'quantity': None, 'share_denominator': None}
        c1 = fixture([event(), cancel], direction=direction)
        c1['cutoff_at'] = c1['coverage']['cutoff_at'] = C1
        assert factors(run(c1)) == ['1.000000000000000000'] * 3
        assert c0 == original and old.result.result_bytes() == old_bytes
        assert run(c0).result.content_hash == old.result.content_hash
        assert revised.result.content_hash != old.result.content_hash


def test_same_input_bytes_repeat_and_semantic_decimal_row_permutation():
    data = fixture([event(), event('BONUS', '0.5', key='bonus_a')])
    first = run(data); second = run(data)
    assert first == second
    equivalent = copy.deepcopy(data)
    equivalent['actions'].reverse(); equivalent['prices'].reverse()
    equivalent['groups'][0]['component_roles'].reverse()
    equivalent['actions'][0]['quantity'] = '0.5000'
    equivalent['actions'][1]['quantity'] = '1.00'
    same = run(equivalent)
    assert same.result.result_bytes() == first.result.result_bytes()
    assert same.receipt.input_semantic_hash == first.receipt.input_semantic_hash
    assert same.receipt.raw_input_hash != first.receipt.raw_input_hash
    assert first.receipt.selection_hash == same.receipt.selection_hash
    instance = copy.deepcopy(data); instance['fixture_instance_id'] = 'new_instance'
    assert run(instance).result == first.result
    assert run(instance).receipt.execution_hash != first.receipt.execution_hash
    assert run(data, clock=datetime(2026, 9, 3, tzinfo=timezone.utc)).result == first.result


def test_true_input_hash_method_and_actual_source_fingerprint():
    data = fixture([event()]); raw = json.dumps(data).encode()
    execution = run(data, raw=raw)
    assert execution.receipt.raw_input_hash == 'sha256:' + hashlib.sha256(raw).hexdigest()
    root = Path(__file__).resolve().parents[2]
    for source in execution.receipt.implementation_sources:
        assert source.source_hash == 'sha256:' + hashlib.sha256((root / source.source_path).read_bytes()).hexdigest()
    assert execution.result.method_ref == MethodRef.from_method(AdjustmentMethod())
    assert data['method']['execution_status'] == 'CONTRACT_ONLY'
    tampered = copy.deepcopy(data); tampered['method']['precision'] = 28
    rejection(tampered, 'precision')
    tampered = copy.deepcopy(data); tampered['method']['method_contract_hash'] = 'sha256:'+'1'*64
    rejection(tampered, 'mismatch')
    tampered = copy.deepcopy(data); tampered['fixture_kind'] = 'PROVIDER_CERTIFIED'
    rejection(tampered, 'FIXTURE_ONLY')
    changed = copy.deepcopy(data); changed['prices'][0]['raw_close'] = '20'
    assert run(changed).receipt.input_semantic_hash != execution.receipt.input_semantic_hash
    assert run(changed).result.content_hash != execution.result.content_hash


def test_duplicate_json_keys_float_token_and_naive_clock_fail_closed():
    for raw, match in [(b'{"x":1,"x":2}', 'duplicate'), (b'{"x":NaN}', 'numeric'),
                       (b'{"x":1.1}', 'float'), (b'not json', 'JSON')]:
        with pytest.raises(ValueError, match=match): run({}, raw=raw)
    with pytest.raises(ValueError, match='aware'): run(fixture(), clock=datetime(2026, 9, 2))


def test_raw_close_cannot_be_disclosed_before_its_session():
    data = fixture([event()])
    data['prices'][-1].update(KNOWN)
    rejection(data, 'price.*trade_date')


def test_method_version_is_not_a_free_executable_label():
    data = fixture()
    data['method'] = AdjustmentMethod(method_version='2.0.0').model_dump(mode='json')
    rejection(data, 'unsupported Method')


def test_source_fingerprint_cannot_claim_changed_disk_for_old_loaded_code(monkeypatch):
    module = importlib.import_module('src.services.platform.adjustment_calculation')
    run(fixture())
    original = Path.read_bytes
    target = Path(module.__file__).resolve()

    def altered_source(path):
        content = original(path)
        return content+b'\n# changed source\n' if path.resolve() == target else content

    monkeypatch.setattr(Path, 'read_bytes', altered_source)
    with pytest.raises(ValueError, match='loaded.*source'):
        run(fixture())


def test_auxiliary_same_price_basis_and_c1_restatement_return():
    from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext
    with localcontext(Context(prec=38, rounding=ROUND_HALF_EVEN)):
        q = Decimal('0.000000000000000001')
        for direction in ('FORWARD_FIXED_ANCHOR', 'BACKWARD_FIXED_BASE'):
            data = fixture([event()], direction=direction)
            result = run(data).result
            adjusted = [(Decimal(p['raw_close'])*Decimal(r.factor)).quantize(q)
                        for p, r in zip(data['prices'], result.rows)]
            returns = [(right/left-1).quantize(q) for left, right in zip(adjusted, adjusted[1:])]
            assert returns == [Decimal(0), Decimal(0)]
        newer = event(revision=2, quantity='2', source_published_at=C1, available_at=C1)
        data = fixture([event(), newer]); data['cutoff_at'] = data['coverage']['cutoff_at'] = C1
        result = run(data).result
        before = Decimal('10')*Decimal(result.rows[0].factor)
        after = Decimal('9')*Decimal(result.rows[1].factor)
        assert after/before-1 == Decimal('0.125')


def test_ambient_decimal_context_and_timezone_representation_do_not_change_content():
    from decimal import Context, localcontext
    from datetime import timedelta
    data = fixture([event(), event('BONUS', '0.5', key='bonus_a')])
    first = run(data)
    with localcontext(Context(prec=3)):
        assert run(data).result == first.result
    def convert(value):
        if isinstance(value, dict): return {k: convert(v) for k, v in value.items()}
        if isinstance(value, list): return [convert(v) for v in value]
        if isinstance(value, str) and value.endswith('Z'):
            return datetime.fromisoformat(value).astimezone(timezone(timedelta(hours=8))).isoformat()
        return value
    assert run(convert(data)).result == first.result


def test_two_securities_get_full_independent_observation_grids():
    data = fixture([event()])
    data['securities'].append('other_security')
    data['coverage']['securities'].append('other_security')
    data['identities'].append({**data['identities'][0], 'entity_key': 'other_security'})
    data['prices'].extend([{**p, 'entity_key': 'other_security'} for p in list(data['prices'])])
    execution = run(data)
    assert len(execution.result.rows) == 6
    assert factors(execution) == ['0.900000000000000000', '1.000000000000000000', '1.000000000000000000'] + ['1.000000000000000000']*3


def test_unknown_superseded_or_outside_row_still_rejected():
    data = fixture([event(), event(revision=2, available_at='2026-08-27T09:00:00Z')])
    data['actions'][0]['action_type'] = 'RIGHTS'
    rejection(data, 'unsupported')
    rejection(fixture([event('UNKNOWN', ex=T2)], end=T1), 'unsupported')


def test_same_cutoff_input_restatement_has_directional_impact_without_publishing_correction():
    original = fixture([event()]); old = run(original)
    newer = event(revision=2, quantity='2', available_at='2026-08-27T09:00:00Z')
    revised = run(fixture([event(), newer]))
    assert old.result.cutoff_at == revised.result.cutoff_at
    assert factors(revised)[0] == '0.800000000000000000'
    assert old.result.content_hash != revised.result.content_hash
    assert run(original) == old
    narrowed = copy.deepcopy(original); narrowed['base_trade_date'] = T1; narrowed['groups'] = []
    assert factors(run(narrowed)) == ['1.000000000000000000']*2
    assert run(narrowed).receipt.input_semantic_hash != old.receipt.input_semantic_hash


def test_output_half_even_and_parameter_precision_boundaries():
    from decimal import Context, Decimal, localcontext
    module = importlib.import_module('src.services.platform.adjustment_calculation')
    with localcontext(Context(prec=38)):
        assert module._factor_text(Decimal('0.0000000000000000025')) == '0.000000000000000002'
        assert module._factor_text(Decimal('0.0000000000000000035')) == '0.000000000000000004'
        for bad in (Decimal('NaN'), Decimal('Infinity'), Decimal('-1'), Decimal('0')):
            with pytest.raises(ValueError, match='positive'): module._factor_text(bad)
    rejection(fixture([event(quantity='123456789012345678901234567890123456789')]), 'precision')


def test_receipts_are_sealed_immutable_and_recomputed_from_real_bytes():
    from src.schemas.platform.adjustment_calculation import FixtureCalculation, FixtureFactorResult
    module = importlib.import_module('src.services.platform.adjustment_calculation')
    data = fixture([event()]); raw = json.dumps(data).encode('utf-8'); execution = run(data, raw=raw)
    module.verify_fixture_execution(raw, execution)
    with pytest.raises(ValueError, match='frozen'):
        execution.result.direction = 'BACKWARD_FIXED_BASE'
    result = execution.result.model_dump(mode='python'); result['rows'][0]['factor'] = '0.800000000000000000'
    with pytest.raises(ValueError, match='content_hash mismatch'):
        FixtureFactorResult.model_validate(result)
    # 即使攻击者重新 seal 伪造因子和外层收据，实际字节重算也不接受。
    result.pop('content_hash'); forged = FixtureFactorResult.model_validate(result)
    receipt = execution.receipt.model_dump(mode='python')
    receipt.update(result_content_hash=forged.content_hash)
    receipt.pop('execution_hash')
    forged_execution = FixtureCalculation(result=forged, receipt=receipt)
    with pytest.raises(ValueError, match='actual input/source'):
        module.verify_fixture_execution(raw, forged_execution)
    receipt = execution.receipt.model_dump(mode='python'); receipt['selection_rows'] = []
    with pytest.raises(ValueError, match='every source revision'):
        FixtureCalculation(result=execution.result, receipt=receipt)
    changed = copy.deepcopy(data); changed['actions'][0]['quantity'] = '2'
    with pytest.raises(ValueError, match='actual input/source'):
        module.verify_fixture_execution(json.dumps(changed).encode(), execution)



def test_receipt_non_action_states_are_explicit_and_result_bytes_are_bound():
    empty = run(fixture())
    assert empty.receipt.selection_status == 'TRUE_NO_ACTION'
    assert empty.receipt.result_bytes_hash == 'sha256:' + hashlib.sha256(empty.result.result_bytes()).hexdigest()

    newer = event(revision=2, quantity='2', source_published_at=C1, available_at=C1)
    cancelled = {**newer, 'event_state': 'CANCELLED', 'quantity': None, 'share_denominator': None}
    cancelled_data = fixture([event(), cancelled])
    cancelled_data['cutoff_at'] = cancelled_data['coverage']['cutoff_at'] = C1
    assert run(cancelled_data).receipt.selection_status == 'ALL_CANCELLED'
