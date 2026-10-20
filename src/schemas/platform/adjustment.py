from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import Annotated, Any, Literal

from pydantic import AwareDatetime, Field, StrictInt, StrictStr, field_validator, model_validator

from .base import PlatformContractModel
from .canonical import CanonicalPartition, CanonicalQualityReport
from .enums import ProviderRunOutcome, QualityStatus, ResourceType, RevisionKind, SnapshotPublicationStatus
from .hashing import HashProfile, compute_content_hash
from .raw_ingestion import ProviderRun, RawObject
from .resources import parse_resource_id
from .snapshot import DataSnapshot, SnapshotPartitionRef
from .storage import StorageRef

Digest = Annotated[StrictStr, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
Semver = Annotated[StrictStr, Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")]
Identifier = Annotated[StrictStr, Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")]
InputRole = Literal["bar_1d_raw", "corporate_action", "security_master", "trading_calendar"]
ActionType = Literal["DIVIDEND", "BONUS", "SPLIT"]
ADJUSTMENT_HASH_PROFILE = HashProfile(profile_id="adjustment_semantic_json_1.0.0", excluded_fields=frozenset())
_ROLES = {"bar_1d_raw", "corporate_action", "security_master", "trading_calendar"}


def _hash(value: Any) -> str:
    # 新契约必须覆盖嵌套固定 content_hash；不修改旧全局 HashProfile。
    return compute_content_hash(value, ADJUSTMENT_HASH_PROFILE)


def _resource(value: str, kind: ResourceType) -> str:
    if parse_resource_id(value)[0] is not kind:
        raise ValueError(f"expected {kind.value} resource")
    return value


def _unique(values: tuple[Any, ...], keys: tuple[Any, ...], name: str) -> None:
    if not values or len(keys) != len(set(keys)):
        raise ValueError(f"{name} must be non-empty and unique")


def _seal(model: PlatformContractModel, field: str, expected: str) -> None:
    current = getattr(model, field)
    if current and current != expected:
        raise ValueError(f"{field} mismatch")
    object.__setattr__(model, field, expected)


class AdjustmentMethod(PlatformContractModel):
    """不可执行的受控 Method 规范；这里不计算任何复权因子。"""

    method_contract_version: Literal["1.0.0"] = "1.0.0"
    method_id: Literal["pit_price_continuity"] = "pit_price_continuity"
    method_version: Semver = "1.0.0"
    algorithm_version: Literal["1.0.0"] = "1.0.0"
    execution_status: Literal["CONTRACT_ONLY"] = "CONTRACT_ONLY"
    return_semantics: Literal["PRICE_CONTINUITY_NOT_TOTAL_RETURN"] = "PRICE_CONTINUITY_NOT_TOTAL_RETURN"
    action_whitelist: tuple[ActionType, ...] = ("BONUS", "DIVIDEND", "SPLIT")
    cash_unit: Literal["PRE_TAX_CNY_PER_PRE_EVENT_SHARE"] = "PRE_TAX_CNY_PER_PRE_EVENT_SHARE"
    bonus_unit: Literal["NEW_FREE_SHARES_PER_PRE_EVENT_SHARE"] = "NEW_FREE_SHARES_PER_PRE_EVENT_SHARE"
    split_unit: Literal["POST_SHARES_OVER_PRE_SHARES_GT_ONE"] = "POST_SHARES_OVER_PRE_SHARES_GT_ONE"
    price_source: Literal["PINNED_RAW_CLOSE_PREVIOUS_SESSION_NO_FILL"] = "PINNED_RAW_CLOSE_PREVIOUS_SESSION_NO_FILL"
    cash_formula: Literal["Q=P-D;q=Q/P"] = "Q=P-D;q=Q/P"
    bonus_formula: Literal["Q=P/(1+b);q=Q/P"] = "Q=P/(1+b);q=Q/P"
    split_formula: Literal["Q=P/s;q=Q/P"] = "Q=P/s;q=Q/P"
    combined_formula: Literal["Q=(P-sum(D))/(1+sum(b));q=Q/P"] = "Q=(P-sum(D))/(1+sum(b));q=Q/P"
    same_day_policy: Literal["ONE_CONFIRMED_GROUP_COMMON_OLD_SHARE_BASIS"] = "ONE_CONFIRMED_GROUP_COMMON_OLD_SHARE_BASIS"
    direction: Literal["FORWARD_FIXED_ANCHOR", "BACKWARD_FIXED_BASE"] = "FORWARD_FIXED_ANCHOR"
    forward_formula: Literal["F(t,A)=product(q;t<ex<=A)"] = "F(t,A)=product(q;t<ex<=A)"
    backward_formula: Literal["H(B)=1;H(t)=product(1/q;B<ex<=t)"] = "H(B)=1;H(t)=product(1/q;B<ex<=t)"
    precision: StrictInt = 38
    output_scale: StrictInt = 18
    rounding: Literal["ROUND_HALF_EVEN"] = "ROUND_HALF_EVEN"
    operation_policy: Literal["CONTEXT_EACH_DIVISION_AND_SORTED_PRODUCT_QUANTIZE_OUTPUT_ONLY"] = "CONTEXT_EACH_DIVISION_AND_SORTED_PRODUCT_QUANTIZE_OUTPUT_ONLY"
    decimal_encoding: Literal["FACTOR_FIXED_18_PARAMETERS_PLAIN_TRIMMED_ZERO_NORMALIZED"] = "FACTOR_FIXED_18_PARAMETERS_PLAIN_TRIMMED_ZERO_NORMALIZED"
    numeric_failure_policy: Literal["REJECT_NONFINITE_NONPOSITIVE_OVERFLOW_OR_QUANTIZED_ZERO"] = "REJECT_NONFINITE_NONPOSITIVE_OVERFLOW_OR_QUANTIZED_ZERO"
    event_order: Literal["EX_SESSION_GROUP_COMPONENT_ROLE_EVENT_REVISION"] = "EX_SESSION_GROUP_COMPONENT_ROLE_EVENT_REVISION"
    pit_policy: Literal["SOURCE_PUBLISHED_LE_AVAILABLE_LE_CUTOFF_NO_BACKFILL"] = "SOURCE_PUBLISHED_LE_AVAILABLE_LE_CUTOFF_NO_BACKFILL"
    revision_policy: Literal["HIGHEST_KNOWN_IN_PINNED_INPUT_RETAIN_CANCELLED_EVIDENCE"] = "HIGHEST_KNOWN_IN_PINNED_INPUT_RETAIN_CANCELLED_EVIDENCE"
    coverage_policy: Literal["EXHAUSTIVE_PINNED_ACTION_SNAPSHOT_AND_RECEIPT"] = "EXHAUSTIVE_PINNED_ACTION_SNAPSHOT_AND_RECEIPT"
    missing_input_policy: Literal["FAIL_CLOSED_NOT_FACTOR_ONE"] = "FAIL_CLOSED_NOT_FACTOR_ONE"
    formula_digest: Digest = ""
    method_contract_hash: Digest = ""

    @model_validator(mode="after")
    def validate_method(self) -> "AdjustmentMethod":
        if self.precision != 38 or self.output_scale != 18:
            raise ValueError("only precision38/scale18 is approved")
        if self.action_whitelist != ("BONUS", "DIVIDEND", "SPLIT"):
            raise ValueError("action_whitelist must match the approved ordinary actions")
        data = self.model_dump(mode="python", exclude={"formula_digest", "method_contract_hash"})
        formula = {k: v for k, v in data.items() if k not in {
            "method_contract_version", "method_id", "method_version", "execution_status",
        }}
        _seal(self, "formula_digest", _hash(formula))
        _seal(self, "method_contract_hash", _hash({**data, "formula_digest": self.formula_digest}))
        return self


class MethodRef(PlatformContractModel):
    method_contract_version: Literal["1.0.0"]
    method_id: Identifier
    method_version: Semver
    method_contract_hash: Digest
    formula_digest: Digest

    @classmethod
    def from_method(cls, method: AdjustmentMethod) -> "MethodRef":
        return cls.model_validate({k: getattr(method, k) for k in cls.model_fields})


class SnapshotInputRef(PlatformContractModel):
    role: InputRole
    snapshot_id: StrictStr
    manifest_version: Literal["1.0.0"]
    snapshot_manifest_hash: Digest
    snapshot_content_hash: Digest
    snapshot_cutoff_at: AwareDatetime
    partitions: tuple[SnapshotPartitionRef, ...]

    @field_validator("snapshot_id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        return _resource(value, ResourceType.DATA_SNAPSHOT)

    @model_validator(mode="after")
    def validate_input(self) -> "SnapshotInputRef":
        _unique(self.partitions, tuple(p.canonical_partition_id for p in self.partitions), "partitions")
        selected = [p for p in self.partitions if p.dataset_id == self.role]
        if not selected or any(p.dataset_schema_version != "1.0.0" for p in self.partitions):
            raise ValueError("missing role dataset or unsupported input dataset version")
        object.__setattr__(self, "partitions", tuple(sorted(self.partitions, key=lambda p: p.canonical_partition_id)))
        return self

    @classmethod
    def from_snapshot(cls, snapshot: DataSnapshot, role: InputRole) -> "SnapshotInputRef":
        return cls(role=role, snapshot_id=snapshot.snapshot_id, manifest_version=snapshot.manifest_version,
                   snapshot_manifest_hash=snapshot.manifest_hash, snapshot_content_hash=snapshot.content_hash,
                   snapshot_cutoff_at=snapshot.cutoff_at, partitions=snapshot.canonical_partitions)


class SourceRootRef(PlatformContractModel):
    source_contract_version: Literal["1.0.0"] = "1.0.0"
    provider_run_id: StrictStr
    provider_run_contract_hash: Digest
    raw_object_id: StrictStr
    raw_object_contract_hash: Digest
    raw_content_hash: Digest
    provider_schema_version: Semver
    observed_schema_hash: Digest
    adapter_version: Semver
    source_published_at: AwareDatetime
    available_at: AwareDatetime
    availability_basis: Literal["OBSERVED_INGESTION"] = "OBSERVED_INGESTION"

    @field_validator("provider_run_id", "raw_object_id")
    @classmethod
    def validate_ids(cls, value: str, info: Any) -> str:
        return _resource(value, ResourceType.PROVIDER_RUN if info.field_name == "provider_run_id" else ResourceType.RAW_OBJECT)

    @model_validator(mode="after")
    def validate_time(self) -> "SourceRootRef":
        if self.source_published_at > self.available_at:
            raise ValueError("source published_at must not exceed available_at")
        return self

    @classmethod
    def from_objects(cls, run: ProviderRun, raw: RawObject) -> "SourceRootRef":
        if (raw.provider_run_id != run.provider_run_id or raw.raw_object_id not in run.raw_object_refs
                or run.run_outcome is not ProviderRunOutcome.SUCCEEDED
                or any(getattr(raw, k) != getattr(run, k) for k in (
                    "provider_id", "actual_upstream", "dataset_id", "dataset_schema_version", "request_fingerprint",
                    "observed_schema_hash", "row_count", "byte_count"))
                or run.finished_at is None
                or not run.started_at <= raw.observed_at <= raw.ingested_at <= run.finished_at):
            raise ValueError("source root mismatch")
        return cls(provider_run_id=run.provider_run_id, provider_run_contract_hash=_hash(run),
                   raw_object_id=raw.raw_object_id, raw_object_contract_hash=_hash(raw),
                   raw_content_hash=raw.raw_content_hash, provider_schema_version=raw.provider_schema_version,
                   observed_schema_hash=raw.observed_schema_hash, adapter_version=run.adapter_version,
                   source_published_at=raw.source_published_at, available_at=max(raw.ingested_at, run.finished_at))


class QualityEvidenceRef(PlatformContractModel):
    quality_contract_version: Literal["1.0.0"] = "1.0.0"
    quality_report_id: StrictStr
    quality_report_hash: Digest
    mapping_version: Semver
    mapping_hash: Digest
    quality_threshold_version: Semver

    @field_validator("quality_report_id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        return _resource(value, ResourceType.QUALITY_REPORT)

    @classmethod
    def from_report(cls, report: CanonicalQualityReport) -> "QualityEvidenceRef":
        return cls(quality_report_id=report.quality_report_id, quality_report_hash=_hash(report),
                   mapping_version=report.mapping_version, mapping_hash=report.mapping_hash,
                   quality_threshold_version=report.quality_threshold_version)


class AdjustmentCoverageReceipt(PlatformContractModel):
    receipt_contract_version: Literal["1.0.0"] = "1.0.0"
    receipt_id: Identifier
    action_snapshot_id: StrictStr
    action_manifest_hash: Digest
    universe_scope_hash: Digest
    date_from: date
    date_to: date
    cutoff_at: AwareDatetime
    available_at: AwareDatetime
    coverage_status: Literal["COMPLETE"] = "COMPLETE"
    completion_basis: Literal["EXHAUSTIVE_SOURCE_MANIFEST"] = "EXHAUSTIVE_SOURCE_MANIFEST"
    event_type_coverage: tuple[Literal["DIVIDEND", "BONUS", "SPLIT", "RIGHTS", "OTHER"], ...] = ("BONUS", "DIVIDEND", "OTHER", "RIGHTS", "SPLIT")
    page_raw_object_refs: tuple[StrictStr, ...]
    end_marker: StrictStr = Field(min_length=1)
    source_row_count: StrictInt = Field(ge=0)
    receipt_hash: Digest = ""

    @field_validator("action_snapshot_id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        return _resource(value, ResourceType.DATA_SNAPSHOT)

    @model_validator(mode="after")
    def validate_receipt(self) -> "AdjustmentCoverageReceipt":
        _unique(self.page_raw_object_refs, self.page_raw_object_refs, "page_raw_object_refs")
        for ref in self.page_raw_object_refs:
            _resource(ref, ResourceType.RAW_OBJECT)
        if self.event_type_coverage != ("BONUS", "DIVIDEND", "OTHER", "RIGHTS", "SPLIT"):
            raise ValueError("coverage must include discovery of unsupported action types")
        if self.date_from > self.date_to or self.available_at > self.cutoff_at:
            raise ValueError("invalid coverage interval or cutoff")
        object.__setattr__(self, "page_raw_object_refs", tuple(sorted(self.page_raw_object_refs)))
        _seal(self, "receipt_hash", _hash(self.model_dump(mode="python", exclude={"receipt_hash"})))
        return self


class AdjustmentEventRef(PlatformContractModel):
    economic_event_key: Identifier
    action_group_id: Identifier
    revision: StrictInt = Field(ge=1)
    action_type: ActionType
    event_state: Literal["ACTIVE", "CANCELLED"] = "ACTIVE"
    event_hash: Digest
    ex_trade_date: date
    source_published_at: AwareDatetime
    available_at: AwareDatetime
    raw_object_id: StrictStr

    @field_validator("raw_object_id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        return _resource(value, ResourceType.RAW_OBJECT)


class AdjustmentLineage(PlatformContractModel):
    lineage_contract_version: Literal["1.0.0"] = "1.0.0"
    method_ref: MethodRef
    inputs: tuple[SnapshotInputRef, ...]
    source_roots: tuple[SourceRootRef, ...]
    quality_evidence: tuple[QualityEvidenceRef, ...]
    coverage_receipt: AdjustmentCoverageReceipt
    selected_event_refs: tuple[AdjustmentEventRef, ...]
    base_trade_date: date
    anchor_trade_date: date
    cutoff_at: AwareDatetime
    available_at: AwareDatetime
    universe_scope_hash: Digest
    lineage_hash: Digest = ""

    @model_validator(mode="after")
    def validate_lineage(self) -> "AdjustmentLineage":
        _unique(self.inputs, tuple(i.role for i in self.inputs), "inputs")
        if {i.role for i in self.inputs} != _ROLES:
            raise ValueError("missing one of the four required inputs")
        _unique(self.source_roots, tuple(r.raw_object_id for r in self.source_roots), "source_roots")
        _unique(self.quality_evidence, tuple(r.quality_report_id for r in self.quality_evidence), "quality_evidence")
        if self.base_trade_date > self.anchor_trade_date or self.available_at > self.cutoff_at:
            raise ValueError("invalid anchor or available_at/cutoff")
        receipt = self.coverage_receipt
        action = next(i for i in self.inputs if i.role == "corporate_action")
        if (receipt.action_snapshot_id != action.snapshot_id or receipt.action_manifest_hash != action.snapshot_manifest_hash
                or receipt.universe_scope_hash != self.universe_scope_hash or receipt.cutoff_at != self.cutoff_at
                or receipt.date_from > self.base_trade_date or receipt.date_to < self.anchor_trade_date):
            raise ValueError("coverage scope, interval, cutoff or fixed input mismatch")
        times = [receipt.available_at, *(r.available_at for r in self.source_roots)]
        raw_ids, quality_ids = set(), set()
        for item in self.inputs:
            if item.snapshot_cutoff_at > self.cutoff_at:
                raise ValueError("input snapshot cutoff contamination")
            for part in item.partitions:
                if part.max_available_at is None or part.quality_status is not QualityStatus.COMPLETE:
                    raise ValueError("input requires complete quality and explicit availability upper bound")
                if part.coverage_ratio != 1 or part.excluded_instrument_count:
                    raise ValueError("input coverage is insufficient")
                times.append(part.max_available_at)
                raw_ids.update(part.raw_object_refs)
                quality_ids.add(part.quality_report_id)
        if raw_ids != {r.raw_object_id for r in self.source_roots} or quality_ids != {r.quality_report_id for r in self.quality_evidence}:
            raise ValueError("source roots or quality evidence mismatch")
        action_raws = {r for p in action.partitions if p.dataset_id == "corporate_action" for r in p.raw_object_refs}
        if set(receipt.page_raw_object_refs) != action_raws:
            raise ValueError("coverage pages must match the action source roots")
        if len({e.economic_event_key for e in self.selected_event_refs}) != len(self.selected_event_refs):
            raise ValueError("event selection contains duplicate economic events")
        roots = {r.raw_object_id: r for r in self.source_roots}
        for event in self.selected_event_refs:
            if (event.raw_object_id not in action_raws or event.source_published_at > event.available_at
                    or not self.base_trade_date < event.ex_trade_date <= self.anchor_trade_date
                    or event.available_at < roots[event.raw_object_id].available_at):
                raise ValueError("event source, interval or available_at mismatch")
            times.append(event.available_at)
        if any(t > self.cutoff_at for t in times):
            raise ValueError("input availability exceeds cutoff")
        if self.available_at < max(times):
            raise ValueError("derived available_at precedes a required input")
        object.__setattr__(self, "inputs", tuple(sorted(self.inputs, key=lambda i: i.role)))
        object.__setattr__(self, "source_roots", tuple(sorted(self.source_roots, key=lambda r: r.raw_object_id)))
        object.__setattr__(self, "quality_evidence", tuple(sorted(self.quality_evidence, key=lambda r: r.quality_report_id)))
        object.__setattr__(self, "selected_event_refs", tuple(sorted(self.selected_event_refs, key=lambda e: (e.ex_trade_date, e.action_group_id, e.economic_event_key, e.revision))))
        _seal(self, "lineage_hash", _hash(self.model_dump(mode="python", exclude={"lineage_hash"})))
        return self


class DerivedCanonicalPartition(PlatformContractModel):
    """沿用 Canonical 资源身份/StorageRef；尚无 Repository 或发布者。"""

    partition_contract_version: Literal["2.0.0"] = "2.0.0"
    provenance_kind: Literal["DERIVED"] = "DERIVED"
    canonical_partition_id: StrictStr
    dataset_id: Literal["adjustment_factor"] = "adjustment_factor"
    dataset_schema_version: Literal["1.0.0"] = "1.0.0"
    partition_key: StrictStr = Field(min_length=1)
    revision: StrictInt = Field(ge=1)
    revision_kind: RevisionKind = RevisionKind.INITIAL
    supersedes_id: StrictStr | None = None
    row_count: StrictInt = Field(ge=1)
    storage_ref: StorageRef
    partition_hash: Digest
    schema_hash: Digest
    quality_status: Literal["COMPLETE"] = "COMPLETE"
    quality_report_id: StrictStr
    lineage: AdjustmentLineage
    created_at: AwareDatetime
    published_at: AwareDatetime | None = None

    @field_validator("canonical_partition_id", "supersedes_id", "quality_report_id")
    @classmethod
    def validate_ids(cls, value: str | None, info: Any) -> str | None:
        if value is None:
            return None
        kind = ResourceType.QUALITY_REPORT if info.field_name == "quality_report_id" else ResourceType.CANONICAL_PARTITION
        return _resource(value, kind)

    @model_validator(mode="after")
    def validate_partition(self) -> "DerivedCanonicalPartition":
        if self.partition_hash != self.storage_ref.content_hash:
            raise ValueError("partition_hash mismatch")
        _validate_instance(self)
        return self


class DerivedDataSnapshot(PlatformContractModel):
    manifest_version: Literal["2.0.0"] = "2.0.0"
    provenance_kind: Literal["DERIVED"] = "DERIVED"
    snapshot_id: StrictStr
    trade_date: date
    cutoff_at: AwareDatetime
    canonical_partitions: tuple[DerivedCanonicalPartition, ...]
    revision: StrictInt = Field(ge=1)
    revision_kind: RevisionKind = RevisionKind.INITIAL
    supersedes_id: StrictStr | None = None
    publication_status: Literal["PROVISIONAL"] = "PROVISIONAL"
    certified_capabilities: tuple[StrictStr, ...] = ()
    missing_capabilities: tuple[Literal["market_breadth", "market_emotion"], ...] = ("market_breadth", "market_emotion")
    created_at: AwareDatetime
    published_at: AwareDatetime | None = None
    content_hash: Digest = ""
    manifest_hash: Digest = ""

    @field_validator("snapshot_id", "supersedes_id")
    @classmethod
    def validate_ids(cls, value: str | None) -> str | None:
        return _resource(value, ResourceType.DATA_SNAPSHOT) if value is not None else None

    @model_validator(mode="after")
    def validate_snapshot(self) -> "DerivedDataSnapshot":
        _unique(self.canonical_partitions, tuple(p.canonical_partition_id for p in self.canonical_partitions), "canonical_partitions")
        if self.certified_capabilities or self.missing_capabilities != ("market_breadth", "market_emotion"):
            raise ValueError("contract-only derived snapshots cannot certify capabilities")
        lineages = {p.lineage.lineage_hash for p in self.canonical_partitions}
        if len(lineages) != 1 or any(p.lineage.cutoff_at != self.cutoff_at or p.lineage.anchor_trade_date != self.trade_date for p in self.canonical_partitions):
            raise ValueError("derived snapshot must preserve one fixed lineage, cutoff and anchor")
        _validate_instance(self)
        if any(p.published_at is None or p.published_at > self.created_at for p in self.canonical_partitions):
            raise ValueError("snapshot requires previously materialized partitions")
        object.__setattr__(self, "canonical_partitions", tuple(sorted(self.canonical_partitions, key=lambda p: p.canonical_partition_id)))
        content = tuple((p.canonical_partition_id, p.partition_hash, p.schema_hash, p.lineage.lineage_hash) for p in self.canonical_partitions)
        _seal(self, "content_hash", _hash(content))
        _seal(self, "manifest_hash", _hash(self.model_dump(mode="python", exclude={"manifest_hash"})))
        return self


def _validate_instance(value: DerivedCanonicalPartition | DerivedDataSnapshot) -> None:
    if value.published_at is not None and value.published_at < value.created_at:
        raise ValueError("platform published_at must not precede created_at")
    if value.revision_kind is RevisionKind.CORRECTION:
        if value.supersedes_id is None or value.revision < 2:
            raise ValueError("CORRECTION requires predecessor and revision>=2")
    elif value.supersedes_id is not None:
        raise ValueError("only CORRECTION may supersede another object")


def parse_snapshot_contract(payload: dict[str, Any]) -> DataSnapshot | DerivedDataSnapshot:
    manifest_version = payload.get("manifest_version", "1.0.0")
    if manifest_version == "1.0.0":
        return DataSnapshot.model_validate(payload)
    if manifest_version == "2.0.0":
        return DerivedDataSnapshot.model_validate(payload)
    raise ValueError("unsupported snapshot manifest_version")


def parse_partition_contract(payload: dict[str, Any]) -> CanonicalPartition | DerivedCanonicalPartition:
    partition_version = payload.get("partition_contract_version", "1.0.0")
    if partition_version == "1.0.0":
        return CanonicalPartition.model_validate(payload)
    if partition_version == "2.0.0":
        return DerivedCanonicalPartition.model_validate(payload)
    raise ValueError("unsupported partition_contract_version")


def _required(
    objects: Mapping[Any, Any], key: Any, name: str, model_type: type[PlatformContractModel],
) -> Any:
    if key not in objects:
        raise ValueError(f"missing {name}: {key}")
    value = objects[key]
    if not isinstance(value, model_type):
        raise ValueError(f"unexpected {name} contract type")
    # 重新核验传入对象，不信任 model_copy/model_construct 或可变旧质量报告。
    return model_type.model_validate(value.model_dump(mode="python"))


def validate_adjustment_references(
    *, lineage: AdjustmentLineage, methods: Mapping[tuple[str, str], AdjustmentMethod],
    snapshots: Mapping[str, DataSnapshot], partitions: Mapping[str, CanonicalPartition],
    provider_runs: Mapping[str, ProviderRun], raw_objects: Mapping[str, RawObject],
    quality_reports: Mapping[str, CanonicalQualityReport],
) -> None:
    """纯内存引用/元数据核验；不读取文件内容，不认证 Provider 或算法。"""
    lineage = AdjustmentLineage.model_validate(lineage.model_dump(mode="python"))
    ref = lineage.method_ref
    method = _required(methods, (ref.method_id, ref.method_version), "Method", AdjustmentMethod)
    if MethodRef.from_method(method) != ref:
        raise ValueError("Method version/hash mismatch")
    source_roots = {r.raw_object_id: r for r in lineage.source_roots}
    quality_refs = {r.quality_report_id: r for r in lineage.quality_evidence}
    for item in lineage.inputs:
        snapshot = _required(snapshots, item.snapshot_id, "Snapshot", DataSnapshot)
        if not isinstance(snapshot, DataSnapshot) or SnapshotInputRef.from_snapshot(snapshot, item.role) != item:
            raise ValueError("Snapshot version/hash/partitions mismatch")
        if snapshot.published_at is None or snapshot.publication_status is SnapshotPublicationStatus.REJECTED or snapshot.quality_status is not QualityStatus.COMPLETE:
            raise ValueError("input Snapshot must be published and COMPLETE")
        if snapshot.available_at > lineage.cutoff_at:
            raise ValueError("Snapshot cutoff contamination")
        for part_ref in item.partitions:
            part = _required(partitions, part_ref.canonical_partition_id, "Partition", CanonicalPartition)
            report = _required(quality_reports, part_ref.quality_report_id, "QualityReport", CanonicalQualityReport)
            if (part.canonical_partition_id != part_ref.canonical_partition_id or part.published_at is None
                    or SnapshotPartitionRef.from_partition(part, report) != part_ref
                    or QualityEvidenceRef.from_report(report) != quality_refs[part.quality_report_id]
                    or set(report.raw_object_refs) != set(part.raw_object_refs)
                    or set(report.provider_run_refs) != set(part.provider_run_refs)):
                raise ValueError("Partition or quality version/hash/reference mismatch")
            part_runs = set()
            for raw_id in part.raw_object_refs:
                raw = _required(raw_objects, raw_id, "RawObject", RawObject)
                run = _required(provider_runs, raw.provider_run_id, "ProviderRun", ProviderRun)
                if (raw.raw_object_id != raw_id or SourceRootRef.from_objects(run, raw) != source_roots[raw_id]
                        or raw.dataset_id != part.dataset_id or raw.dataset_schema_version != part.dataset_schema_version
                        or run.provider_policy_version != part.provider_policy_version):
                    raise ValueError("source root version/hash/reference mismatch")
                part_runs.add(run.provider_run_id)
            if part_runs != set(part.provider_run_refs):
                raise ValueError("ProviderRun root mismatch")
    action = next(i for i in lineage.inputs if i.role == "corporate_action")
    count = sum(p.row_count for p in action.partitions if p.dataset_id == "corporate_action")
    if count != lineage.coverage_receipt.source_row_count:
        raise ValueError("coverage row count mismatch")
    if (count and not lineage.selected_event_refs) or len(lineage.selected_event_refs) > count:
        raise ValueError("nonempty event source cannot become an empty action selection")
