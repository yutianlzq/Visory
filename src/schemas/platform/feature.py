from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
from typing import Any

from pydantic import AwareDatetime, Field, field_validator, model_validator


from .base import PlatformContractModel
from .enums import ConsumerKind, PlatformStringEnum, PublicationStatus, QualityStatus, ResourceType, RetentionClass, RevisionKind
from .hashing import canonical_json_bytes, compute_content_hash
from .resources import parse_resource_id
from .storage import StorageRef

_HASH = r"^sha256:[0-9a-f]{64}$"
_SEMVER = r"^(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_.:-]{0,127}$")
_COVERAGE_QUANTUM = Decimal("0.00001")
_ALLOWED_VALUE_TYPES = frozenset({"boolean", "date", "decimal", "integer", "string"})
_FEATURE_PARQUET_MEDIA_TYPE = "application/vnd.apache.parquet"


def _resource(value: str, expected: ResourceType, field_name: str) -> str:
    kind, _ = parse_resource_id(value)
    if kind is not expected:
        raise ValueError(f"{field_name} must use the {expected.value} resource prefix")
    return value


def _identifier(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value) or not value.strip():
        raise ValueError(f"{field_name} must be a normalized non-blank identifier")
    return value


def _finite_decimal(value: Any, field_name: str) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float):
        raise ValueError(f"{field_name} must use Decimal or an integer, not float")
    try:
        parsed = value if isinstance(value, Decimal) else Decimal(value)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a finite decimal") from exc
    if not parsed.is_finite():
        raise ValueError(f"{field_name} must be a finite decimal")
    return parsed


def _coverage(value: Any) -> Decimal:
    parsed = _finite_decimal(value, "coverage_ratio")
    return parsed.quantize(_COVERAGE_QUANTUM, rounding=ROUND_HALF_UP)


def _validate_feature_storage_ref(storage_ref: StorageRef) -> None:
    if storage_ref.media_type != _FEATURE_PARQUET_MEDIA_TYPE:
        raise ValueError("feature storage_ref must use Parquet media type")
    if storage_ref.size_bytes <= 0:
        raise ValueError("feature storage_ref.size_bytes must be positive")


def _row_value_payload(row: "FeatureRow") -> dict[str, Any]:
    return {
        "available_at": row.available_at,
        "data_flags": tuple(sorted(row.data_flags)),
        "data_snapshot_id": row.data_snapshot_id,
        "definition_version": row.definition_version,
        "entity_key": row.entity_key,
        "indicator_id": row.indicator_id,
        "quality_status": row.quality_status,
        "trade_date": row.trade_date,
        "unit": row.unit,
        "value": row.value,
        "value_type": row.value_type,
    }


class FeatureMaterializationError(ValueError):
    """Fail-closed validation error raised before a feature artifact is published."""


class FeatureSnapshotType(PlatformStringEnum):
    CLOSE_CORE = "CLOSE_CORE"
    LATE_A_SHARE = "LATE_A_SHARE"
    CORRECTION = "CORRECTION"
    HISTORICAL_REBUILD = "HISTORICAL_REBUILD"


class FeatureRow(PlatformContractModel):
    """One logical feature value; calculation metadata is not part of content identity."""

    entity_key: str
    trade_date: date
    indicator_id: str
    definition_version: str = Field(pattern=_SEMVER)
    value: Any | None
    value_type: str
    unit: str
    available_at: AwareDatetime
    data_snapshot_id: str
    calculation_run_id: str
    quality_status: QualityStatus = QualityStatus.COMPLETE
    data_flags: tuple[str, ...] = ()

    @field_validator("entity_key", "indicator_id", "unit", "calculation_run_id")
    @classmethod
    def validate_text(cls, value: str, info: Any) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{info.field_name} must be non-blank")
        return value

    @field_validator("value_type")
    @classmethod
    def validate_value_type(cls, value: str) -> str:
        if value not in _ALLOWED_VALUE_TYPES:
            raise ValueError("value_type is not supported")
        return value

    @field_validator("data_snapshot_id")
    @classmethod
    def validate_snapshot_id(cls, value: str) -> str:
        return _resource(value, ResourceType.DATA_SNAPSHOT, "data_snapshot_id")

    @field_validator("value")
    @classmethod
    def reject_float_values(cls, value: Any) -> Any:
        if isinstance(value, float):
            raise ValueError("feature value cannot be an implicit float")
        if isinstance(value, Decimal) and not value.is_finite():
            raise ValueError("feature value must be finite")
        return value

    @field_validator("data_flags")
    @classmethod
    def validate_flags(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)) or any(not item.strip() for item in value):
            raise ValueError("data_flags must be unique and non-blank")
        # Flags are a set-like quality annotation; canonical ordering keeps content hashes stable.
        return tuple(sorted(value))

    @model_validator(mode="after")
    def validate_value(self) -> "FeatureRow":
        if self.value is None:
            return self
        valid = {
            "boolean": isinstance(self.value, bool),
            "date": isinstance(self.value, date) and not isinstance(self.value, datetime),
            "decimal": isinstance(self.value, (Decimal, int)) and not isinstance(self.value, bool),
            "integer": isinstance(self.value, int) and not isinstance(self.value, bool),
            "string": isinstance(self.value, str),
        }
        if not valid[self.value_type]:
            raise ValueError("value does not match value_type")
        if self.value_type == "decimal":
            _finite_decimal(self.value, "value")
        return self

    @property
    def unique_key(self) -> tuple[str, date, str, str]:
        return (self.entity_key, self.trade_date, self.indicator_id, self.definition_version)

    @classmethod
    def content_payload(cls, rows: Sequence["FeatureRow"]) -> tuple[dict[str, Any], ...]:
        return tuple(_row_value_payload(row) for row in sorted(rows, key=lambda item: item.unique_key))


class FeaturePartitionRef(PlatformContractModel):
    feature_partition_id: str
    partition_hash: str = Field(pattern=_HASH)
    schema_hash: str = Field(pattern=_HASH)
    revision: int = Field(ge=1)
    storage_ref: StorageRef
    indicator_id: str
    definition_version: str = Field(pattern=_SEMVER)
    required_columns: tuple[str, ...] = ()
    retention_class: RetentionClass = RetentionClass.REBUILDABLE

    @field_validator("feature_partition_id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        return _resource(value, ResourceType.FEATURE_PARTITION, "feature_partition_id")

    @field_validator("indicator_id")
    @classmethod
    def validate_indicator(cls, value: str) -> str:
        return _identifier(value, "indicator_id")

    @field_validator("required_columns")
    @classmethod
    def validate_columns(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)) or any(not item.strip() for item in value):
            raise ValueError("required_columns must be unique and non-blank")
        return tuple(sorted(value))

    @model_validator(mode="after")
    def validate_ref(self) -> "FeaturePartitionRef":
        _validate_feature_storage_ref(self.storage_ref)
        if self.partition_hash != self.storage_ref.content_hash:
            raise ValueError("partition_hash must match storage_ref.content_hash")
        return self

    @classmethod
    def from_partition(cls, partition: "FeaturePartition", *, required_columns: Sequence[str] = (), pinned: bool = False) -> "FeaturePartitionRef":
        return cls(
            feature_partition_id=partition.feature_partition_id,
            partition_hash=partition.partition_hash,
            schema_hash=partition.schema_hash,
            revision=partition.revision,
            storage_ref=partition.storage_ref,
            indicator_id=partition.indicator_id,
            definition_version=partition.definition_version,
            required_columns=tuple(required_columns) or (f"{partition.indicator_id}.value",),
            retention_class=RetentionClass.PINNED if pinned else partition.retention_class,
        )


class FeaturePartition(PlatformContractModel):
    feature_partition_id: str
    indicator_id: str
    definition_version: str = Field(pattern=_SEMVER)
    domain: str
    frequency: str
    partition_key: str
    data_snapshot_ids: tuple[str, ...] = Field(min_length=1)
    input_partition_ids: tuple[str, ...] = ()
    universe_scope_hash: str | None = Field(default=None, pattern=_HASH)
    cutoff_at: AwareDatetime
    row_count: int = Field(ge=0)
    null_count: int = Field(ge=0)
    coverage_ratio: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    min_date: date
    max_date: date
    min_available_at: AwareDatetime
    max_available_at: AwareDatetime
    storage_ref: StorageRef
    partition_hash: str = Field(pattern=_HASH)
    schema_hash: str = Field(pattern=_HASH)
    quality_status: QualityStatus
    quality_failure_reasons: tuple[str, ...] = ()
    quality_report_id: str
    revision: int = Field(ge=1)
    revision_kind: RevisionKind = RevisionKind.INITIAL
    supersedes_id: str | None = None
    retention_class: RetentionClass = RetentionClass.REBUILDABLE
    reference_count: int = Field(default=0, ge=0)
    created_at: AwareDatetime
    published_at: AwareDatetime | None = None

    @field_validator("feature_partition_id")
    @classmethod
    def validate_partition_id(cls, value: str) -> str:
        return _resource(value, ResourceType.FEATURE_PARTITION, "feature_partition_id")

    @field_validator("indicator_id", "domain")
    @classmethod
    def validate_identifiers(cls, value: str, info: Any) -> str:
        return _identifier(value, info.field_name)

    @field_validator("frequency", "partition_key")
    @classmethod
    def validate_nonblank_text(cls, value: str, info: Any) -> str:
        if not value.strip() or any(ord(character) < 32 for character in value):
            raise ValueError(f"{info.field_name} must be non-blank text")
        return value

    @field_validator("data_snapshot_ids")
    @classmethod
    def validate_snapshot_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value or len(value) != len(set(value)):
            raise ValueError("data_snapshot_ids must be non-empty and unique")
        return tuple(sorted(_resource(item, ResourceType.DATA_SNAPSHOT, "data_snapshot_ids") for item in value))

    @field_validator("input_partition_ids")
    @classmethod
    def validate_input_partition_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("input_partition_ids must be unique")
        return tuple(sorted(_resource(item, ResourceType.FEATURE_PARTITION, "input_partition_ids") for item in value))

    @field_validator("quality_report_id")
    @classmethod
    def validate_quality_report(cls, value: str) -> str:
        return _resource(value, ResourceType.QUALITY_REPORT, "quality_report_id")

    @field_validator("supersedes_id")
    @classmethod
    def validate_supersedes(cls, value: str | None) -> str | None:
        return None if value is None else _resource(value, ResourceType.FEATURE_PARTITION, "supersedes_id")

    @field_validator("quality_failure_reasons")
    @classmethod
    def validate_quality_reasons(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)) or any(not re.fullmatch(r"[A-Z][A-Z0-9_]{2,63}", item) for item in value):
            raise ValueError("quality_failure_reasons must be unique uppercase reason codes")
        return value

    @field_validator("coverage_ratio", mode="before")
    @classmethod
    def normalize_coverage(cls, value: Any) -> Decimal:
        return _coverage(value)

    @model_validator(mode="after")
    def validate_partition(self) -> "FeaturePartition":
        _validate_feature_storage_ref(self.storage_ref)
        if self.max_date < self.min_date:
            raise ValueError("max_date must not precede min_date")
        if self.max_available_at < self.min_available_at:
            raise ValueError("max_available_at must not precede min_available_at")
        if self.max_available_at > self.cutoff_at:
            raise ValueError("max_available_at must not exceed cutoff_at")
        if self.null_count > self.row_count:
            raise ValueError("null_count cannot exceed row_count")
        expected_coverage = Decimal("0") if self.row_count == 0 else (Decimal(self.row_count - self.null_count) / Decimal(self.row_count)).quantize(_COVERAGE_QUANTUM, rounding=ROUND_HALF_UP)
        if self.coverage_ratio != expected_coverage:
            raise ValueError("coverage_ratio must match row_count and null_count")
        if self.row_count == 0 and self.quality_status is not QualityStatus.UNAVAILABLE:
            raise ValueError("empty feature partitions must be UNAVAILABLE")
        if self.quality_status in {QualityStatus.FAILED, QualityStatus.PARTIAL, QualityStatus.STALE, QualityStatus.UNAVAILABLE} and not self.quality_failure_reasons:
            raise ValueError("non-COMPLETE feature partition requires quality_failure_reasons")
        if self.quality_status is QualityStatus.COMPLETE and self.quality_failure_reasons:
            raise ValueError("COMPLETE feature partition cannot contain failure reasons")
        if self.quality_status is QualityStatus.COMPLETE and self.coverage_ratio != Decimal("1.00000"):
            raise ValueError("COMPLETE feature partition requires full coverage")
        if self.revision_kind is RevisionKind.INITIAL:
            if self.revision != 1 or self.supersedes_id is not None:
                raise ValueError("INITIAL partitions require revision=1 and no supersedes_id")
        elif self.revision_kind is RevisionKind.CORRECTION:
            if self.revision < 2 or self.supersedes_id is None:
                raise ValueError("CORRECTION requires revision >= 2 and supersedes_id")
        elif self.supersedes_id is not None:
            raise ValueError("only CORRECTION partitions may supersede another partition")
        if self.published_at is not None and self.published_at < self.created_at:
            raise ValueError("published_at must not precede created_at")
        if self.partition_hash != self.storage_ref.content_hash:
            raise ValueError("partition_hash must match storage_ref.content_hash")
        return self

    @classmethod
    def validate_rows(cls, rows: Sequence["FeatureRow"], *, cutoff_at: AwareDatetime,
                      data_snapshot_ids: tuple[str, ...]) -> None:
        """Validate inputs before projection, including rows used only for warmup."""
        if not rows:
            raise FeatureMaterializationError("feature partition rows cannot be empty")
        # 不信任 model_copy 构造的行；再次执行完整类型/数值校验。
        for row in rows:
            FeatureRow.model_validate(row.model_dump(mode="python"))
        keys = [row.unique_key for row in rows]
        if len(keys) != len(set(keys)):
            raise FeatureMaterializationError("duplicate feature row unique key")
        if any(row.available_at > cutoff_at for row in rows):
            raise FeatureMaterializationError("available_at exceeds cutoff_at")
        if any(row.data_snapshot_id not in data_snapshot_ids for row in rows):
            raise FeatureMaterializationError("row references an undeclared data snapshot")
        if len({(row.indicator_id, row.definition_version) for row in rows}) != 1:
            raise FeatureMaterializationError("a feature partition must contain one indicator definition")
        if len({(row.value_type, row.unit) for row in rows}) != 1:
            raise FeatureMaterializationError("feature column schema must have a single value_type and unit")

    @classmethod
    def parquet_bytes(cls, rows: Sequence["FeatureRow"]) -> bytes:
        items = tuple(rows)
        if not items:
            raise FeatureMaterializationError("feature partition cannot be empty")
        # Keep the public serializer fail-closed even when callers bypass
        # build_from_rows/materialize_and_publish.
        cls.validate_rows(
            items,
            cutoff_at=max(item.available_at for item in items),
            data_snapshot_ids=tuple(sorted({item.data_snapshot_id for item in items})),
        )
        return _feature_parquet_bytes(items)

    @classmethod
    def compute_hash(cls, rows: Sequence["FeatureRow"]) -> str:
        """Return the hash of the deterministic Parquet payload, not a run-local JSON dump."""
        if not rows:
            raise FeatureMaterializationError("feature partition cannot be empty")
        items = tuple(rows)
        cls.validate_rows(items, cutoff_at=max(item.available_at for item in items), data_snapshot_ids=tuple(sorted({item.data_snapshot_id for item in items})))
        return "sha256:" + hashlib.sha256(_feature_parquet_bytes(items)).hexdigest()

    @classmethod
    def compute_schema_hash(cls, rows: Sequence["FeatureRow"]) -> str:
        items = tuple(rows)
        if not items:
            raise FeatureMaterializationError("feature partition cannot be empty")
        cls.validate_rows(
            items,
            cutoff_at=max(item.available_at for item in items),
            data_snapshot_ids=tuple(sorted({item.data_snapshot_id for item in items})),
        )
        schema = sorted({(row.indicator_id, row.definition_version, row.value_type, row.unit) for row in items})
        return compute_content_hash(schema)

    @classmethod
    def build_from_rows(
        cls,
        rows: Sequence[FeatureRow],
        *,
        partition_id: str,
        data_snapshot_ids: tuple[str, ...],
        partition_key: str,
        storage_ref: StorageRef,
        quality_report_id: str,
        cutoff_at: AwareDatetime,
        created_at: AwareDatetime,
        domain: str = "a_share",
        frequency: str = "1d",
        published_at: AwareDatetime | None = None,
        input_partition_ids: tuple[str, ...] = (),
        universe_scope_hash: str | None = None,
        revision: int = 1,
        revision_kind: RevisionKind = RevisionKind.INITIAL,
        supersedes_id: str | None = None,
        retention_class: RetentionClass = RetentionClass.REBUILDABLE,
        min_coverage_ratio: Decimal = Decimal("1.0"),
    ) -> "FeaturePartition":
        items = tuple(rows)
        cls.validate_rows(items, cutoff_at=cutoff_at, data_snapshot_ids=data_snapshot_ids)
        indicator_pairs = {(row.indicator_id, row.definition_version) for row in items}
        partition_hash = cls.compute_hash(items)
        if storage_ref.content_hash != partition_hash:
            raise FeatureMaterializationError("storage_ref.content_hash does not match rows")
        min_coverage = _coverage(min_coverage_ratio)
        if min_coverage < Decimal("0") or min_coverage > Decimal("1"):
            raise FeatureMaterializationError("min_coverage_ratio must be between 0 and 1")
        schema_hash = cls.compute_schema_hash(items)
        null_count = sum(row.value is None for row in items)
        coverage_ratio = Decimal("1.0") if not items else (Decimal(len(items) - null_count) / Decimal(len(items))).quantize(_COVERAGE_QUANTUM, rounding=ROUND_HALF_UP)
        reasons: list[str] = []
        row_quality_statuses = {row.quality_status for row in items}
        if QualityStatus.FAILED in row_quality_statuses:
            reasons.append("ROW_QUALITY_FAILED")
            quality_status = QualityStatus.FAILED
        elif QualityStatus.UNAVAILABLE in row_quality_statuses:
            reasons.append("ROW_UNAVAILABLE")
            quality_status = QualityStatus.UNAVAILABLE
        elif QualityStatus.STALE in row_quality_statuses:
            reasons.append("ROW_QUALITY_STALE")
            quality_status = QualityStatus.STALE
        elif QualityStatus.PARTIAL in row_quality_statuses:
            reasons.append("ROW_QUALITY_PARTIAL")
            quality_status = QualityStatus.PARTIAL
        else:
            quality_status = QualityStatus.COMPLETE
        if coverage_ratio < min_coverage:
            reasons.append("COVERAGE_BELOW_THRESHOLD")
            if quality_status is QualityStatus.COMPLETE:
                quality_status = QualityStatus.PARTIAL
        quality_reasons = tuple(dict.fromkeys(reasons))
        return cls(
            feature_partition_id=partition_id,
            indicator_id=next(iter(indicator_pairs))[0],
            definition_version=next(iter(indicator_pairs))[1],
            domain=domain,
            frequency=frequency,
            partition_key=partition_key,
            data_snapshot_ids=data_snapshot_ids,
            input_partition_ids=input_partition_ids,
            universe_scope_hash=universe_scope_hash,
            cutoff_at=cutoff_at,
            row_count=len(items),
            null_count=null_count,
            coverage_ratio=coverage_ratio,
            min_date=min(row.trade_date for row in items),
            max_date=max(row.trade_date for row in items),
            min_available_at=min(row.available_at for row in items),
            max_available_at=max(row.available_at for row in items),
            storage_ref=storage_ref,
            partition_hash=partition_hash,
            schema_hash=schema_hash,
            quality_status=quality_status,
            quality_failure_reasons=quality_reasons,
            quality_report_id=quality_report_id,
            revision=revision,
            revision_kind=revision_kind,
            supersedes_id=supersedes_id,
            retention_class=retention_class,
            created_at=created_at,
            published_at=published_at,
        )


def _feature_parquet_bytes(rows: Sequence["FeatureRow"]) -> bytes:
    """Serialize feature rows with the same fixed Parquet writer policy as canonical data."""
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:  # pragma: no cover - CI installs the controlled engine
        raise FeatureMaterializationError("feature Parquet engine is unavailable") from exc

    items = tuple(sorted(rows, key=lambda item: item.unique_key))
    value_type = items[0].value_type
    physical_types = {
        "boolean": pa.bool_(),
        "date": pa.date32(),
        "decimal": pa.decimal128(38, 12),
        "integer": pa.int64(),
        "string": pa.string(),
    }
    value_type_arrow = physical_types[value_type]
    schema = pa.schema([
        pa.field("entity_key", pa.string()),
        pa.field("trade_date", pa.date32()),
        pa.field("indicator_id", pa.string()),
        pa.field("definition_version", pa.string()),
        pa.field("value", value_type_arrow),
        pa.field("value_type", pa.string()),
        pa.field("unit", pa.string()),
        pa.field("available_at", pa.timestamp("us", tz="UTC")),
        pa.field("data_snapshot_id", pa.string()),
        pa.field("quality_status", pa.string()),
        pa.field("data_flags", pa.string()),
    ])
    payload: list[dict[str, Any]] = []
    for row in items:
        value = row.value
        if value_type == "decimal" and value is not None:
            value = Decimal(value)
            decimal_tuple = value.as_tuple()
            scale = max(0, -decimal_tuple.exponent)
            integer_digits = max(1, value.copy_abs().adjusted() + 1) if value else 1
            if scale > 12 or integer_digits + 12 > 38:
                raise FeatureMaterializationError("feature decimal exceeds deterministic Parquet precision")
            try:
                # Decimal's process-wide default precision is only 28; use a
                # local context so valid decimal128(38, 12) values do not
                # fail merely because the caller has not changed the context.
                with localcontext() as context:
                    context.prec = max(50, len(decimal_tuple.digits) + abs(decimal_tuple.exponent) + 16)
                    value = value.quantize(Decimal("0.000000000001"))
            except InvalidOperation as exc:
                raise FeatureMaterializationError("feature decimal exceeds deterministic Parquet precision") from exc
        payload.append({
            "entity_key": row.entity_key,
            "trade_date": row.trade_date,
            "indicator_id": row.indicator_id,
            "definition_version": row.definition_version,
            "value": value,
            "value_type": row.value_type,
            "unit": row.unit,
            "available_at": row.available_at,
            "data_snapshot_id": row.data_snapshot_id,
            "quality_status": row.quality_status.value,
            "data_flags": canonical_json_bytes(tuple(sorted(row.data_flags))).decode("utf-8"),
        })
    table = pa.Table.from_pylist(payload, schema=schema)
    sink = pa.BufferOutputStream()
    pq.write_table(
        table,
        sink,
        version="2.6",
        compression="zstd",
        use_dictionary=False,
        write_statistics=False,
        data_page_version="1.0",
        store_schema=False,
    )
    return sink.getvalue().to_pybytes()


class FeatureSnapshot(PlatformContractModel):
    feature_snapshot_id: str
    snapshot_type: FeatureSnapshotType
    as_of_trade_date: date
    cutoff_at: AwareDatetime
    data_snapshot_ids: tuple[str, ...] = Field(min_length=1)
    feature_partition_refs: tuple[FeaturePartitionRef, ...] = Field(min_length=1)
    dependency_plan_hash: str = Field(pattern=_HASH)
    definition_refs: tuple[str, ...] = Field(min_length=1)
    publication_status: PublicationStatus
    quality_status: QualityStatus
    certified_capabilities: tuple[str, ...] = ()
    missing_capabilities: tuple[str, ...] = ()
    max_source_available_at: AwareDatetime
    quality_report_id: str | None = None
    revision: int = Field(ge=1)
    revision_kind: RevisionKind = RevisionKind.INITIAL
    supersedes_id: str | None = None
    manifest_hash: str = Field(pattern=_HASH)
    manifest_version: str = Field(default="1.0.0", pattern=_SEMVER)
    created_at: AwareDatetime
    published_at: AwareDatetime | None = None

    @field_validator("feature_snapshot_id")
    @classmethod
    def validate_snapshot_id(cls, value: str) -> str:
        return _resource(value, ResourceType.FEATURE_SNAPSHOT, "feature_snapshot_id")

    @field_validator("snapshot_type")
    @classmethod
    def validate_snapshot_type(cls, value: FeatureSnapshotType) -> FeatureSnapshotType:
        return value

    @field_validator("data_snapshot_ids")
    @classmethod
    def validate_data_snapshots(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value or len(value) != len(set(value)):
            raise ValueError("data_snapshot_ids must be non-empty and unique")
        return tuple(_resource(item, ResourceType.DATA_SNAPSHOT, "data_snapshot_ids") for item in value)

    @field_validator("definition_refs", "certified_capabilities", "missing_capabilities")
    @classmethod
    def validate_refs(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)) or any(not item.strip() for item in value):
            raise ValueError("references must be unique and non-blank")
        return tuple(sorted(value))

    @field_validator("quality_report_id")
    @classmethod
    def validate_quality_report(cls, value: str | None) -> str | None:
        return None if value is None else _resource(value, ResourceType.QUALITY_REPORT, "quality_report_id")

    @field_validator("supersedes_id")
    @classmethod
    def validate_supersedes(cls, value: str | None) -> str | None:
        return None if value is None else _resource(value, ResourceType.FEATURE_SNAPSHOT, "supersedes_id")

    @model_validator(mode="after")
    def validate_snapshot(self) -> "FeatureSnapshot":
        if not self.feature_partition_refs:
            raise ValueError("feature_partition_refs cannot be empty")
        if not self.definition_refs:
            raise ValueError("definition_refs cannot be empty")
        if len({item.feature_partition_id for item in self.feature_partition_refs}) != len(self.feature_partition_refs):
            raise ValueError("feature_partition_refs must be unique")
        object.__setattr__(self, "data_snapshot_ids", tuple(sorted(self.data_snapshot_ids)))
        object.__setattr__(self, "feature_partition_refs", tuple(sorted(self.feature_partition_refs, key=lambda item: (item.indicator_id, item.definition_version, item.partition_hash, item.revision, item.feature_partition_id))))
        if self.max_source_available_at > self.cutoff_at:
            raise ValueError("max_source_available_at must not exceed cutoff_at")
        if self.published_at is not None and self.published_at < self.created_at:
            raise ValueError("published_at must not precede created_at")
        if self.publication_status is PublicationStatus.CERTIFIED:
            if self.published_at is None or self.quality_status is not QualityStatus.COMPLETE:
                raise ValueError("CERTIFIED feature snapshot requires published_at and COMPLETE quality")
        if self.publication_status is PublicationStatus.RETIRED and self.published_at is None:
            raise ValueError("RETIRED feature snapshot must retain published_at")
        if set(self.certified_capabilities) & set(self.missing_capabilities):
            raise ValueError("certified and missing capabilities must be disjoint")
        if self.revision_kind is RevisionKind.INITIAL:
            if self.revision != 1 or self.snapshot_type is FeatureSnapshotType.CORRECTION or self.supersedes_id is not None:
                raise ValueError("INITIAL snapshots require revision=1, a non-correction snapshot_type, and no supersedes_id")
        elif self.revision_kind is RevisionKind.CORRECTION:
            if self.snapshot_type is not FeatureSnapshotType.CORRECTION:
                raise ValueError("CORRECTION revision requires snapshot_type=CORRECTION")
            if self.revision < 2 or self.supersedes_id is None:
                raise ValueError("CORRECTION requires revision >= 2 and supersedes_id")
        elif self.snapshot_type is FeatureSnapshotType.CORRECTION:
            raise ValueError("snapshot_type=CORRECTION requires revision_kind=CORRECTION")
        elif self.supersedes_id is not None:
            raise ValueError("only CORRECTION snapshots may supersede another snapshot")
        if set(item.storage_ref.content_hash for item in self.feature_partition_refs) != set(item.partition_hash for item in self.feature_partition_refs):
            raise ValueError("partition references must preserve storage hashes")
        if self.manifest_hash != compute_feature_snapshot_manifest_hash(self):
            raise ValueError("manifest_hash does not match snapshot manifest")
        return self

    @classmethod
    def compute_hash(cls, value: "FeatureSnapshot | Mapping[str, Any]") -> str:
        return compute_feature_snapshot_manifest_hash(value)

    @classmethod
    def build(cls, **kwargs: Any) -> "FeatureSnapshot":
        payload = dict(kwargs)
        payload.setdefault("certified_capabilities", ())
        payload.setdefault("missing_capabilities", ())
        payload.setdefault("quality_report_id", None)
        payload.setdefault("revision_kind", RevisionKind.INITIAL)
        payload.setdefault("supersedes_id", None)
        payload.setdefault("manifest_version", "1.0.0")
        payload.setdefault("manifest_hash", "")
        payload["manifest_hash"] = compute_feature_snapshot_manifest_hash(payload)
        return cls(**payload)


class FeatureBundle(PlatformContractModel):
    feature_bundle_id: str
    feature_snapshot_ids: tuple[str, ...] = Field(min_length=1)
    dependency_plan_hash: str = Field(pattern=_HASH)
    required_partition_refs: tuple[FeaturePartitionRef, ...] = Field(min_length=1)
    required_columns: tuple[str, ...] = Field(min_length=1)
    consumer_ref: str
    consumer_kind: ConsumerKind
    cutoff_at: AwareDatetime
    date_from: date | None = None
    date_to: date | None = None
    universe_scope_hash: str | None = Field(default=None, pattern=_HASH)
    bundle_hash: str = Field(pattern=_HASH)
    bundle_version: str = Field(default="1.0.0", pattern=_SEMVER)

    @field_validator("feature_bundle_id")
    @classmethod
    def validate_bundle_id(cls, value: str) -> str:
        return _resource(value, ResourceType.FEATURE_BUNDLE, "feature_bundle_id")

    @field_validator("feature_snapshot_ids")
    @classmethod
    def validate_snapshot_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value or len(value) != len(set(value)):
            raise ValueError("feature_snapshot_ids must be non-empty and unique")
        return tuple(_resource(item, ResourceType.FEATURE_SNAPSHOT, "feature_snapshot_ids") for item in value)

    @field_validator("required_columns")
    @classmethod
    def validate_columns(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value or len(value) != len(set(value)) or any(not item.strip() for item in value):
            raise ValueError("required_columns must be non-empty and unique")
        return tuple(sorted(value))

    @field_validator("consumer_ref")
    @classmethod
    def validate_consumer(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("consumer_ref cannot be blank")
        return value

    @model_validator(mode="after")
    def validate_bundle(self) -> "FeatureBundle":
        if not self.required_partition_refs:
            raise ValueError("required_partition_refs cannot be empty")
        partition_ids = [item.feature_partition_id for item in self.required_partition_refs]
        if len(partition_ids) != len(set(partition_ids)):
            raise ValueError("required_partition_refs must be unique")
        object.__setattr__(self, "feature_snapshot_ids", tuple(sorted(self.feature_snapshot_ids)))
        object.__setattr__(self, "required_partition_refs", tuple(sorted(self.required_partition_refs, key=lambda item: (item.indicator_id, item.definition_version, item.partition_hash, item.revision, item.feature_partition_id))))
        if self.date_to is not None and self.date_from is None:
            raise ValueError("date_to requires date_from")
        if self.date_from is not None and self.date_to is not None and self.date_to < self.date_from:
            raise ValueError("date_to must not precede date_from")
        if self.consumer_kind is ConsumerKind.FORMAL_BACKTEST and any(item.retention_class is not RetentionClass.PINNED for item in self.required_partition_refs):
            raise ValueError("formal bundles require PINNED partition references")
        required_columns = set(self.required_columns)
        if any(set(item.required_columns) - required_columns for item in self.required_partition_refs):
            raise ValueError("partition reference columns must be declared by the bundle")
        if {column for ref in self.required_partition_refs for column in ref.required_columns} != required_columns:
            raise ValueError("bundle column coverage must exactly match fixed partition references")
        if self.bundle_hash != compute_feature_bundle_hash(self):
            raise ValueError("bundle_hash does not match fixed bundle references")
        return self

    @classmethod
    def compute_hash(cls, value: "FeatureBundle | Mapping[str, Any]") -> str:
        return compute_feature_bundle_hash(value)

    @classmethod
    def build(cls, **kwargs: Any) -> "FeatureBundle":
        payload = dict(kwargs)
        payload.setdefault("date_from", None)
        payload.setdefault("date_to", None)
        payload.setdefault("universe_scope_hash", None)
        payload.setdefault("bundle_version", "1.0.0")
        if payload.get("consumer_kind") == "FORMAL_BACKTEST" or payload.get("consumer_kind") is ConsumerKind.FORMAL_BACKTEST:
            payload["required_partition_refs"] = tuple(
                item.model_copy(update={"retention_class": RetentionClass.PINNED}) if isinstance(item, FeaturePartitionRef) else FeaturePartitionRef.model_validate(item).model_copy(update={"retention_class": RetentionClass.PINNED})
                for item in payload["required_partition_refs"]
            )
        payload.setdefault("bundle_hash", "")
        payload["bundle_hash"] = compute_feature_bundle_hash(payload)
        return cls(**payload)


def _partition_ref_sort_key(value: FeaturePartitionRef | Mapping[str, Any]) -> tuple[str, str, str, int, str]:
    ref = value if isinstance(value, FeaturePartitionRef) else FeaturePartitionRef.model_validate(value)
    return (ref.indicator_id, ref.definition_version, ref.partition_hash, ref.revision, ref.feature_partition_id)


def _canonical_refs(value: Sequence[FeaturePartitionRef | Mapping[str, Any]]) -> tuple[FeaturePartitionRef, ...]:
    return tuple(sorted((item if isinstance(item, FeaturePartitionRef) else FeaturePartitionRef.model_validate(item) for item in value), key=_partition_ref_sort_key))


def _manifest_payload(value: FeatureSnapshot | Mapping[str, Any]) -> dict[str, Any]:
    source = value.model_dump(mode="python") if isinstance(value, FeatureSnapshot) else dict(value)
    for field in ("manifest_hash", "feature_snapshot_id", "created_at", "published_at"):
        source.pop(field, None)
    source["data_snapshot_ids"] = tuple(sorted(source["data_snapshot_ids"]))
    source["definition_refs"] = tuple(sorted(source["definition_refs"]))
    source["certified_capabilities"] = tuple(sorted(source["certified_capabilities"]))
    source["missing_capabilities"] = tuple(sorted(source["missing_capabilities"]))
    source["feature_partition_refs"] = _canonical_refs(source["feature_partition_refs"])
    return source


def compute_feature_snapshot_manifest_hash(value: FeatureSnapshot | Mapping[str, Any]) -> str:
    return compute_content_hash(_manifest_payload(value))


def _bundle_payload(value: FeatureBundle | Mapping[str, Any]) -> dict[str, Any]:
    source = value.model_dump(mode="python") if isinstance(value, FeatureBundle) else dict(value)
    for field in ("bundle_hash", "feature_bundle_id"):
        source.pop(field, None)
    source["feature_snapshot_ids"] = tuple(sorted(source["feature_snapshot_ids"]))
    source["required_columns"] = tuple(sorted(source["required_columns"]))
    source["required_partition_refs"] = _canonical_refs(source["required_partition_refs"])
    return source


def compute_feature_bundle_hash(value: FeatureBundle | Mapping[str, Any]) -> str:
    return compute_content_hash(_bundle_payload(value))


__all__ = [
    "FeatureBundle",
    "FeatureMaterializationError",
    "FeaturePartition",
    "FeaturePartitionRef",
    "FeatureRow",
    "FeatureSnapshot",
    "FeatureSnapshotType",
    "compute_feature_bundle_hash",
    "compute_feature_snapshot_manifest_hash",
]
