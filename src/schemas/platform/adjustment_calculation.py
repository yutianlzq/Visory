from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from typing import Any, Literal

from pydantic import AwareDatetime, Field, StrictInt, StrictStr, field_validator, model_validator

from .adjustment import ADJUSTMENT_HASH_PROFILE, AdjustmentMethod, Digest, MethodRef
from .adjustment import (
    AdjustmentCoverageReceipt,
    AdjustmentEventRef,
    AdjustmentLineage,
    QualityEvidenceRef,
)
from .base import PlatformContractModel
from .hashing import canonical_json_bytes, compute_content_hash


def semantic_hash(value: Any) -> str:
    return compute_content_hash(value, ADJUSTMENT_HASH_PROFILE)


def decimal_parameter(value: Any) -> str:
    """不借用外部 Decimal context 规范化，也不接受浮点或隐式整数单位。"""
    if not isinstance(value, (str, Decimal)):
        raise ValueError('decimal parameter requires Decimal or decimal string, not float/int')
    text = format(value, 'f') if isinstance(value, Decimal) else value
    if not re.fullmatch(r'[+-]?\d+(?:\.\d+)?', text):
        raise ValueError('invalid plain finite decimal parameter')
    number = Decimal(text)
    digits = number.as_tuple().digits
    significant = len(''.join(map(str, digits)).rstrip('0'))
    if not number.is_finite() or significant > 38 or abs(number.adjusted()) > 1000:
        raise ValueError('decimal parameter precision/exponent overflow')
    if number == 0:
        return '0'
    result = format(number, 'f')
    return result.rstrip('0').rstrip('.') if '.' in result else result


def unique_sorted(values: tuple[Any, ...], name: str) -> tuple[Any, ...]:
    if not values or len(set(values)) != len(values):
        raise ValueError(f'{name} must be nonempty and unique')
    return tuple(sorted(values))


class FixtureKnownInput(PlatformContractModel):
    source_published_at: AwareDatetime
    available_at: AwareDatetime

    @model_validator(mode='after')
    def check_known_time(self) -> 'FixtureKnownInput':
        if self.source_published_at > self.available_at:
            raise ValueError('source published_at must not exceed available_at')
        return self


class FixtureCalendar(FixtureKnownInput):
    sessions: tuple[date, ...]

    @field_validator('sessions')
    @classmethod
    def check_sessions(cls, value: tuple[date, ...]) -> tuple[date, ...]:
        return unique_sorted(value, 'calendar sessions')


class FixtureIdentity(FixtureKnownInput):
    entity_key: StrictStr = Field(min_length=1)
    valid_from: date
    valid_to: date
    identity_state: Literal['CONFIRMED']


class FixturePrice(FixtureKnownInput):
    entity_key: StrictStr = Field(min_length=1)
    trade_date: date
    raw_close: StrictStr | None
    currency: Literal['CNY']
    observation_state: Literal['ACTUAL', 'SUSPENDED']

    @field_validator('raw_close', mode='before')
    @classmethod
    def check_close(cls, value: Any) -> str | None:
        return decimal_parameter(value) if value is not None else None


class FixtureAction(FixtureKnownInput):
    entity_key: StrictStr = Field(min_length=1)
    economic_event_key: StrictStr = Field(min_length=1)
    action_group_id: StrictStr = Field(min_length=1)
    component_role: StrictStr = Field(min_length=1)
    revision: StrictInt = Field(ge=1)
    event_state: Literal['ACTIVE', 'CANCELLED']
    action_type: StrictStr
    action_subtype: StrictStr
    share_basis: StrictStr
    quantity: StrictStr | None
    share_denominator: StrictStr | None
    quantity_unit: StrictStr
    currency: StrictStr | None
    ex_trade_date: date
    record_date: date | None = None
    payment_date: date | None = None

    @field_validator('quantity', 'share_denominator', mode='before')
    @classmethod
    def check_quantity(cls, value: Any) -> str | None:
        return decimal_parameter(value) if value is not None else None


class FixtureGroup(FixtureKnownInput):
    entity_key: StrictStr
    ex_trade_date: date
    action_group_id: StrictStr
    component_roles: tuple[StrictStr, ...]
    share_basis: Literal['PRE_EVENT_OLD_SHARE']
    confirmation_state: Literal['COMPLETE']

    @field_validator('component_roles')
    @classmethod
    def check_components(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return unique_sorted(value, 'group components')


class FixtureCoverage(FixtureKnownInput):
    securities: tuple[StrictStr, ...]
    date_from: date
    date_to: date
    cutoff_at: AwareDatetime
    coverage_status: Literal['COMPLETE']
    source_row_count: StrictInt = Field(ge=0)
    event_type_coverage: tuple[StrictStr, ...]
    end_marker: StrictStr = Field(min_length=1)

    @field_validator('securities')
    @classmethod
    def check_scope(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return unique_sorted(value, 'coverage securities')

    @field_validator('event_type_coverage')
    @classmethod
    def check_types(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        value = unique_sorted(value, 'coverage types')
        if value != ('BONUS', 'DIVIDEND', 'OTHER', 'RIGHTS', 'SPLIT'):
            raise ValueError('coverage types must include unsupported event discovery')
        return value


class FixtureAdjustmentInput(PlatformContractModel):
    """私有合成输入：不兼容/注册为生产 corporate_action@1 或候选 @2。"""
    fixture_kind: Literal['FIXTURE_ONLY']
    input_contract_version: Literal['1.0.0']
    fixture_instance_id: StrictStr = Field(min_length=1)
    method: AdjustmentMethod
    securities: tuple[StrictStr, ...]
    base_trade_date: date
    anchor_trade_date: date
    cutoff_at: AwareDatetime
    calendar: FixtureCalendar
    identities: tuple[FixtureIdentity, ...]
    prices: tuple[FixturePrice, ...]
    actions: tuple[FixtureAction, ...]
    groups: tuple[FixtureGroup, ...]
    coverage: FixtureCoverage

    @field_validator('securities')
    @classmethod
    def check_scope(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return unique_sorted(value, 'securities')

    @model_validator(mode='after')
    def sort_row_sets(self) -> 'FixtureAdjustmentInput':
        for name, key in (
            ('identities', lambda r: r.entity_key),
            ('prices', lambda r: (r.entity_key, r.trade_date)),
            ('actions', lambda r: (r.entity_key, r.ex_trade_date, r.action_group_id,
                                   r.component_role, r.economic_event_key, r.revision)),
            ('groups', lambda r: (r.entity_key, r.ex_trade_date, r.action_group_id)),
        ):
            object.__setattr__(self, name, tuple(sorted(getattr(self, name), key=key)))
        return self

    def semantic_payload(self) -> dict[str, Any]:
        return self.model_dump(mode='python', exclude={'fixture_instance_id'})


class FixtureSelectionRow(PlatformContractModel):
    entity_key: StrictStr
    economic_event_key: StrictStr
    revision: StrictInt
    row_hash: Digest
    selected_revision: StrictInt
    selected_row_hash: Digest
    disposition: Literal['SELECTED', 'SUPERSEDED', 'CANCELLED', 'OUT_OF_RANGE']


class FixtureEventCalculation(PlatformContractModel):
    entity_key: StrictStr
    ex_trade_date: date
    action_group_id: StrictStr
    selected_row_hashes: tuple[Digest, ...]
    reference_trade_date: date
    reference_row_hash: Digest
    reference_price: StrictStr
    cash_per_old_share: StrictStr
    bonus_new_shares_per_old_share: StrictStr
    split_total_share_multiplier: StrictStr | None
    theoretical_reference_price: StrictStr
    q: StrictStr


class FixtureFactorRow(PlatformContractModel):
    entity_key: StrictStr
    trade_date: date
    factor: StrictStr = Field(pattern=r'^\d+\.\d{18}$')
    available_at: AwareDatetime

    @field_validator('factor')
    @classmethod
    def check_factor(cls, value: str) -> str:
        if not Decimal(value).is_finite() or not 0 < Decimal(value) < Decimal('1e20'):
            raise ValueError('factor must be positive finite with at most 20 integer digits')
        return value


class FixtureFactorResult(PlatformContractModel):
    fixture_kind: Literal['FIXTURE_ONLY'] = 'FIXTURE_ONLY'
    result_contract_version: Literal['1.0.0'] = '1.0.0'
    method_ref: MethodRef
    direction: Literal['FORWARD_FIXED_ANCHOR', 'BACKWARD_FIXED_BASE']
    base_trade_date: date
    anchor_trade_date: date
    cutoff_at: AwareDatetime
    input_semantic_hash: Digest
    selection_hash: Digest
    rows: tuple[FixtureFactorRow, ...]
    content_hash: Digest = ''

    def result_bytes(self) -> bytes:
        return canonical_json_bytes(self.model_dump(mode='python', exclude={'content_hash'}), ADJUSTMENT_HASH_PROFILE)

    @model_validator(mode='after')
    def seal_result(self) -> 'FixtureFactorResult':
        keys = tuple((r.entity_key, r.trade_date) for r in self.rows)
        if not keys or keys != tuple(sorted(set(keys))):
            raise ValueError('result rows must have unique ordered keys')
        expected = semantic_hash(self.model_dump(mode='python', exclude={'content_hash'}))
        if self.content_hash and self.content_hash != expected:
            raise ValueError('result content_hash mismatch')
        object.__setattr__(self, 'content_hash', expected)
        return self


class ImplementationSource(PlatformContractModel):
    source_path: StrictStr
    source_hash: Digest


class FixtureExecutionReceipt(PlatformContractModel):
    fixture_kind: Literal['FIXTURE_ONLY'] = 'FIXTURE_ONLY'
    execution_contract_version: Literal['1.0.0'] = '1.0.0'
    algorithm_version: Literal['offline_fixture_factor_1.0.0'] = 'offline_fixture_factor_1.0.0'
    method_ref: MethodRef
    fixture_instance_id: StrictStr
    raw_input_hash: Digest
    input_semantic_hash: Digest
    action_rows_hash: Digest
    calendar_hash: Digest
    identity_rows_hash: Digest
    price_rows_hash: Digest
    coverage_hash: Digest
    group_rows_hash: Digest
    source_row_count: StrictInt
    selection_status: Literal[
        'TRUE_NO_ACTION', 'SELECTED_ACTIONS', 'ALL_CANCELLED',
        'ALL_OUT_OF_RANGE', 'PARTIAL_SELECTION',
    ]
    selection_rows: tuple[FixtureSelectionRow, ...]
    selection_hash: Digest
    event_calculations: tuple[FixtureEventCalculation, ...]
    implementation_sources: tuple[ImplementationSource, ...]
    implementation_digest: Digest
    runtime_versions: tuple[tuple[StrictStr, StrictStr], ...]
    result_content_hash: Digest
    result_bytes_hash: Digest
    input_available_at: AwareDatetime
    materialized_at: AwareDatetime
    execution_hash: Digest = ''

    @model_validator(mode='after')
    def seal_execution(self) -> 'FixtureExecutionReceipt':
        if len(self.selection_rows) != self.source_row_count:
            raise ValueError('selection receipt must account for every source revision')
        terminal = tuple(
            row.disposition for row in self.selection_rows
            if row.revision == row.selected_revision
        )
        if self.source_row_count == 0:
            expected_status = 'TRUE_NO_ACTION'
        elif terminal and all(value == 'SELECTED' for value in terminal):
            expected_status = 'SELECTED_ACTIONS'
        elif terminal and all(value == 'CANCELLED' for value in terminal):
            expected_status = 'ALL_CANCELLED'
        elif terminal and all(value == 'OUT_OF_RANGE' for value in terminal):
            expected_status = 'ALL_OUT_OF_RANGE'
        else:
            expected_status = 'PARTIAL_SELECTION'
        if self.selection_status != expected_status:
            raise ValueError('selection status does not match terminal revision dispositions')
        if self.selection_hash != semantic_hash(self.selection_rows):
            raise ValueError('selection_hash mismatch')
        if self.implementation_digest != semantic_hash(self.implementation_sources):
            raise ValueError('implementation_digest mismatch')
        expected = semantic_hash(self.model_dump(mode='python', exclude={'execution_hash'}))
        if self.execution_hash and self.execution_hash != expected:
            raise ValueError('execution_hash mismatch')
        object.__setattr__(self, 'execution_hash', expected)
        return self


class FixtureCalculation(PlatformContractModel):
    result: FixtureFactorResult
    receipt: FixtureExecutionReceipt

    @model_validator(mode='after')
    def check_result_receipt(self) -> 'FixtureCalculation':
        for name in ('method_ref', 'input_semantic_hash', 'selection_hash'):
            if getattr(self.result, name) != getattr(self.receipt, name):
                raise ValueError('result/receipt reference mismatch')
        if self.result.content_hash != self.receipt.result_content_hash:
            raise ValueError('result/receipt content hash mismatch')
        return self


class FixtureExecutionLineageBridge(PlatformContractModel):
    """Versioned, fixture-only bridge from execution evidence to DERIVED lineage."""

    bridge_contract_version: Literal['1.0.0'] = '1.0.0'
    execution_revision: StrictInt = Field(ge=1)
    receipt: FixtureExecutionReceipt
    result: FixtureFactorResult
    lineage: AdjustmentLineage
    coverage_receipt: AdjustmentCoverageReceipt
    quality_evidence: tuple[QualityEvidenceRef, ...]
    selected_event_refs: tuple[AdjustmentEventRef, ...]
    quality_status: Literal['COMPLETE'] = 'COMPLETE'
    method_contract_hash: Digest
    formula_digest: Digest
    algorithm_version: Literal['offline_fixture_factor_1.0.0']
    implementation_digest: Digest
    raw_input_hash: Digest
    input_semantic_hash: Digest
    result_content_hash: Digest
    result_bytes_hash: Digest
    cutoff_at: AwareDatetime
    input_available_at: AwareDatetime
    materialized_at: AwareDatetime
    bridge_lineage_hash: Digest = ''
    bridge_hash: Digest = ''

    @model_validator(mode='after')
    def seal_bridge(self) -> 'FixtureExecutionLineageBridge':
        FixtureCalculation(result=self.result, receipt=self.receipt)
        if self.receipt.execution_contract_version != '1.0.0':
            raise ValueError('unsupported execution receipt contract version')
        if self.receipt.algorithm_version != self.algorithm_version:
            raise ValueError('algorithm version mismatch')
        if not (
            self.receipt.method_ref == self.result.method_ref == self.lineage.method_ref
        ):
            raise ValueError('Method reference mismatch')
        if self.method_contract_hash != self.receipt.method_ref.method_contract_hash:
            raise ValueError('method contract hash mismatch')
        if self.formula_digest != self.receipt.method_ref.formula_digest:
            raise ValueError('formula digest mismatch')
        if self.implementation_digest != self.receipt.implementation_digest:
            raise ValueError('implementation digest mismatch')
        if self.raw_input_hash != self.receipt.raw_input_hash:
            raise ValueError('raw input hash mismatch')
        if self.input_semantic_hash != self.receipt.input_semantic_hash != self.result.input_semantic_hash:
            raise ValueError('input semantic hash mismatch')
        if self.result_content_hash != self.receipt.result_content_hash != self.result.content_hash:
            raise ValueError('result content hash mismatch')
        if self.result_bytes_hash != _result_bytes_hash(self.result):
            raise ValueError('result bytes hash mismatch')
        if self.result_bytes_hash != self.receipt.result_bytes_hash:
            raise ValueError('receipt result bytes hash mismatch')
        if self.coverage_receipt != self.lineage.coverage_receipt:
            raise ValueError('coverage receipt mismatch')
        if self.quality_evidence != self.lineage.quality_evidence:
            raise ValueError('quality evidence mismatch')
        if self.selected_event_refs != self.lineage.selected_event_refs:
            raise ValueError('selected event references mismatch')
        if self.cutoff_at != self.result.cutoff_at or self.cutoff_at != self.lineage.cutoff_at:
            raise ValueError('cutoff mismatch')
        if (
            self.result.base_trade_date != self.lineage.base_trade_date
            or self.result.anchor_trade_date != self.lineage.anchor_trade_date
        ):
            raise ValueError('execution/lineage date interval mismatch')
        if self.input_available_at != self.receipt.input_available_at:
            raise ValueError('input availability mismatch')
        if self.materialized_at != self.receipt.materialized_at:
            raise ValueError('materialization timestamp mismatch')
        if self.input_available_at > self.cutoff_at or self.materialized_at < self.input_available_at:
            raise ValueError('execution timestamps violate PIT ordering')
        expected_lineage = compute_bridge_lineage_hash(self)
        if self.bridge_lineage_hash and self.bridge_lineage_hash != expected_lineage:
            raise ValueError('bridge lineage hash mismatch')
        object.__setattr__(self, 'bridge_lineage_hash', expected_lineage)
        expected_bridge = compute_bridge_hash(self)
        if self.bridge_hash and self.bridge_hash != expected_bridge:
            raise ValueError('bridge hash mismatch')
        object.__setattr__(self, 'bridge_hash', expected_bridge)
        return self


def _result_bytes_hash(result: FixtureFactorResult) -> str:
    import hashlib

    return 'sha256:' + hashlib.sha256(result.result_bytes()).hexdigest()


def compute_bridge_lineage_hash(value: FixtureExecutionLineageBridge | dict[str, Any]) -> str:
    model = value if isinstance(value, FixtureExecutionLineageBridge) else FixtureExecutionLineageBridge.model_validate(value)
    payload = {
        'bridge_contract_version': model.bridge_contract_version,
        'execution_revision': model.execution_revision,
        'lineage_hash': model.lineage.lineage_hash,
        'coverage_receipt_hash': model.coverage_receipt.receipt_hash,
        'quality_evidence': model.quality_evidence,
        'selected_event_refs': model.selected_event_refs,
        'method_contract_hash': model.method_contract_hash,
        'formula_digest': model.formula_digest,
        'algorithm_version': model.algorithm_version,
        'implementation_digest': model.implementation_digest,
        'raw_input_hash': model.raw_input_hash,
        'input_semantic_hash': model.input_semantic_hash,
        'result_content_hash': model.result_content_hash,
        'result_bytes_hash': model.result_bytes_hash,
        'cutoff_at': model.cutoff_at,
        'input_available_at': model.input_available_at,
    }
    return semantic_hash(payload)


def compute_bridge_hash(value: FixtureExecutionLineageBridge | dict[str, Any]) -> str:
    payload = value.model_dump(mode='python') if isinstance(value, FixtureExecutionLineageBridge) else dict(value)
    payload.pop('bridge_hash', None)
    return semantic_hash(payload)
