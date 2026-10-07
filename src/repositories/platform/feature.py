from __future__ import annotations

from typing import Any

from sqlalchemy import BigInteger, Column, Date, DateTime, Index, Integer, MetaData, Numeric, String, Table, func, insert, select, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from src.schemas.platform import (
    ConsumerKind,
    FeatureBundle,
    FeaturePartition,
    FeaturePartitionRef,
    FeatureSnapshot,
    FeatureSnapshotType,
    PublicationStatus,
    QualityStatus,
    RetentionClass,
    RevisionKind,
    StorageBackend,
    StorageNamespace,
    StorageRef,
)

metadata = MetaData()

feature_partition = Table(
    "feature_partition",
    metadata,
    Column("feature_partition_id", String(64), primary_key=True),
    Column("indicator_id", String(64), nullable=False),
    Column("definition_version", String(32), nullable=False),
    Column("domain", String(64), nullable=False),
    Column("frequency", String(32), nullable=False),
    Column("partition_key", String(255), nullable=False),
    Column("data_snapshot_ids", JSONB, nullable=False),
    Column("input_partition_ids", JSONB, nullable=False),
    Column("universe_scope_hash", String(71)),
    Column("cutoff_at", DateTime(timezone=True), nullable=False),
    Column("row_count", BigInteger, nullable=False),
    Column("null_count", BigInteger, nullable=False),
    Column("coverage_ratio", Numeric(6, 5), nullable=False),
    Column("min_date", Date, nullable=False),
    Column("max_date", Date, nullable=False),
    Column("min_available_at", DateTime(timezone=True), nullable=False),
    Column("max_available_at", DateTime(timezone=True), nullable=False),
    Column("storage_backend", String(32), nullable=False),
    Column("storage_namespace", String(32), nullable=False),
    Column("relative_path", String(1024), nullable=False),
    Column("media_type", String(255), nullable=False),
    Column("size_bytes", BigInteger, nullable=False),
    Column("partition_hash", String(71), nullable=False),
    Column("schema_hash", String(71), nullable=False),
    Column("quality_status", String(16), nullable=False),
    Column("quality_failure_reasons", JSONB, nullable=False),
    Column("quality_report_id", String(64), nullable=False),
    Column("revision", Integer, nullable=False),
    Column("revision_kind", String(16), nullable=False),
    Column("supersedes_id", String(64)),
    Column("retention_class", String(32), nullable=False),
    Column("reference_count", BigInteger, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("published_at", DateTime(timezone=True)),
)

Index(
    "uq_feature_partition_logical_revision",
    feature_partition.c.domain,
    feature_partition.c.indicator_id,
    feature_partition.c.definition_version,
    feature_partition.c.frequency,
    feature_partition.c.partition_key,
    func.coalesce(feature_partition.c.universe_scope_hash, ""),
    feature_partition.c.revision,
    unique=True,
)

feature_snapshot = Table(
    "feature_snapshot",
    metadata,
    Column("feature_snapshot_id", String(64), primary_key=True),
    Column("snapshot_type", String(32), nullable=False),
    Column("as_of_trade_date", Date, nullable=False),
    Column("cutoff_at", DateTime(timezone=True), nullable=False),
    Column("data_snapshot_ids", JSONB, nullable=False),
    Column("dependency_plan_hash", String(71), nullable=False),
    Column("definition_refs", JSONB, nullable=False),
    Column("publication_status", String(16), nullable=False),
    Column("quality_status", String(16), nullable=False),
    Column("certified_capabilities", JSONB, nullable=False),
    Column("missing_capabilities", JSONB, nullable=False),
    Column("max_source_available_at", DateTime(timezone=True), nullable=False),
    Column("quality_report_id", String(64)),
    Column("revision", Integer, nullable=False),
    Column("revision_kind", String(16), nullable=False),
    Column("supersedes_id", String(64)),
    Column("manifest_hash", String(71), nullable=False),
    Column("manifest_version", String(32), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("published_at", DateTime(timezone=True)),
)

feature_snapshot_partition_ref = Table(
    "feature_snapshot_partition_ref",
    metadata,
    Column("feature_snapshot_id", String(64), primary_key=True),
    Column("feature_partition_id", String(64), primary_key=True),
    Column("partition_hash", String(71), nullable=False),
    Column("schema_hash", String(71), nullable=False),
    Column("revision", Integer, nullable=False),
    Column("storage_backend", String(32), nullable=False),
    Column("storage_namespace", String(32), nullable=False),
    Column("relative_path", String(1024), nullable=False),
    Column("media_type", String(255), nullable=False),
    Column("size_bytes", BigInteger, nullable=False),
    Column("indicator_id", String(64), nullable=False),
    Column("definition_version", String(32), nullable=False),
    Column("required_columns", JSONB, nullable=False),
    Column("retention_class", String(32), nullable=False),
    Column("partition_order", Integer, nullable=False),
)

feature_bundle = Table(
    "feature_bundle",
    metadata,
    Column("feature_bundle_id", String(64), primary_key=True),
    Column("feature_snapshot_ids", JSONB, nullable=False),
    Column("dependency_plan_hash", String(71), nullable=False),
    Column("required_columns", JSONB, nullable=False),
    Column("consumer_ref", String(255), nullable=False),
    Column("consumer_kind", String(32), nullable=False),
    Column("cutoff_at", DateTime(timezone=True), nullable=False),
    Column("date_from", Date),
    Column("date_to", Date),
    Column("universe_scope_hash", String(71)),
    Column("bundle_hash", String(71), nullable=False),
    Column("bundle_version", String(32), nullable=False),
)

feature_bundle_partition_ref = Table(
    "feature_bundle_partition_ref",
    metadata,
    Column("feature_bundle_id", String(64), primary_key=True),
    Column("feature_partition_id", String(64), primary_key=True),
    Column("partition_hash", String(71), nullable=False),
    Column("schema_hash", String(71), nullable=False),
    Column("revision", Integer, nullable=False),
    Column("storage_backend", String(32), nullable=False),
    Column("storage_namespace", String(32), nullable=False),
    Column("relative_path", String(1024), nullable=False),
    Column("media_type", String(255), nullable=False),
    Column("size_bytes", BigInteger, nullable=False),
    Column("indicator_id", String(64), nullable=False),
    Column("definition_version", String(32), nullable=False),
    Column("required_columns", JSONB, nullable=False),
    Column("retention_class", String(32), nullable=False),
    Column("partition_order", Integer, nullable=False),
)


def _storage_values(ref: StorageRef) -> dict[str, Any]:
    return {
        "storage_backend": ref.storage_backend.value,
        "storage_namespace": ref.storage_namespace.value,
        "relative_path": ref.relative_path,
        "media_type": ref.media_type,
        "size_bytes": ref.size_bytes,
    }


def _storage_ref(row: dict[str, Any], *, content_hash: str) -> StorageRef:
    return StorageRef(
        storage_backend=StorageBackend(row["storage_backend"]),
        storage_namespace=StorageNamespace(row["storage_namespace"]),
        relative_path=row["relative_path"],
        media_type=row["media_type"],
        size_bytes=row["size_bytes"],
        content_hash=content_hash,
    )


def _partition_values(record: FeaturePartition) -> dict[str, Any]:
    value = record.model_dump(mode="python")
    value.pop("storage_ref")
    value.update(_storage_values(record.storage_ref))
    for key in ("data_snapshot_ids", "input_partition_ids", "quality_failure_reasons"):
        value[key] = list(value[key])
    for key in ("quality_status", "revision_kind", "retention_class"):
        value[key] = value[key].value
    return value


def _partition_from_row(row: Any) -> FeaturePartition:
    value = dict(row)
    value["storage_ref"] = _storage_ref(value, content_hash=value["partition_hash"])
    for key in ("data_snapshot_ids", "input_partition_ids", "quality_failure_reasons"):
        value[key] = tuple(value[key] or ())
    for key, enum_type in (("quality_status", QualityStatus), ("revision_kind", RevisionKind), ("retention_class", RetentionClass)):
        value[key] = enum_type(value[key])
    for key in ("storage_backend", "storage_namespace", "relative_path", "media_type", "size_bytes"):
        value.pop(key, None)
    return FeaturePartition.model_validate(value)


def _ref_values(ref: FeaturePartitionRef, parent_id: str, order: int, *, parent_column: str) -> dict[str, Any]:
    return {
        parent_column: parent_id,
        "feature_partition_id": ref.feature_partition_id,
        "partition_hash": ref.partition_hash,
        "schema_hash": ref.schema_hash,
        "revision": ref.revision,
        **_storage_values(ref.storage_ref),
        "indicator_id": ref.indicator_id,
        "definition_version": ref.definition_version,
        "required_columns": list(ref.required_columns),
        "retention_class": ref.retention_class.value,
        "partition_order": order,
    }


def _ref_from_row(row: Any) -> FeaturePartitionRef:
    value = dict(row)
    value["storage_ref"] = _storage_ref(value, content_hash=value["partition_hash"])
    value["required_columns"] = tuple(value["required_columns"] or ())
    value["retention_class"] = RetentionClass(value["retention_class"])
    for key in ("feature_snapshot_id", "feature_bundle_id", "partition_order", "storage_backend", "storage_namespace", "relative_path", "media_type", "size_bytes"):
        value.pop(key, None)
    return FeaturePartitionRef.model_validate(value)


def _snapshot_values(record: FeatureSnapshot) -> dict[str, Any]:
    value = record.model_dump(mode="python")
    value.pop("feature_partition_refs", None)
    for key in ("data_snapshot_ids", "definition_refs", "certified_capabilities", "missing_capabilities"):
        value[key] = list(value[key])
    for key in ("snapshot_type", "publication_status", "quality_status", "revision_kind"):
        value[key] = value[key].value
    return value


def _snapshot_from_row(row: Any, refs: tuple[FeaturePartitionRef, ...]) -> FeatureSnapshot:
    value = dict(row)
    value["feature_partition_refs"] = refs
    for key in ("data_snapshot_ids", "definition_refs", "certified_capabilities", "missing_capabilities"):
        value[key] = tuple(value[key] or ())
    for key, enum_type in (("snapshot_type", FeatureSnapshotType), ("publication_status", PublicationStatus), ("quality_status", QualityStatus), ("revision_kind", RevisionKind)):
        value[key] = enum_type(value[key])
    return FeatureSnapshot.model_validate(value)


def _bundle_values(record: FeatureBundle) -> dict[str, Any]:
    value = record.model_dump(mode="python")
    value.pop("required_partition_refs", None)
    for key in ("feature_snapshot_ids", "required_columns"):
        value[key] = list(value[key])
    value["consumer_kind"] = value["consumer_kind"].value
    return value


def _bundle_from_row(row: Any, refs: tuple[FeaturePartitionRef, ...]) -> FeatureBundle:
    value = dict(row)
    value["required_partition_refs"] = refs
    for key in ("feature_snapshot_ids", "required_columns"):
        value[key] = tuple(value[key] or ())
    value["consumer_kind"] = ConsumerKind(value["consumer_kind"])
    return FeatureBundle.model_validate(value)


def _partition_ref_matches_partition(ref: FeaturePartitionRef, partition: FeaturePartition) -> bool:
    return ref.model_dump(mode="python", exclude={"retention_class"}) == FeaturePartitionRef.from_partition(
        partition, required_columns=ref.required_columns,
    ).model_dump(mode="python", exclude={"retention_class"})


def _validate_refs(session: Session, refs: tuple[FeaturePartitionRef, ...]) -> None:
    seen: set[str] = set()
    for ref in refs:
        if ref.feature_partition_id in seen:
            raise ValueError("feature partition references must be unique")
        seen.add(ref.feature_partition_id)
        partition = FeatureRepository.get_partition(session, ref.feature_partition_id)
        if partition is None:
            raise ValueError("feature partition reference points to a missing partition")
        if not _partition_ref_matches_partition(ref, partition):
            raise ValueError("feature partition reference does not match the persisted partition")


def _validate_partition_lineage(session: Session, record: FeaturePartition) -> None:
    if record.published_at is None:
        raise ValueError("feature partition must be published before persistence")
    if record.revision_kind is not RevisionKind.CORRECTION:
        return
    previous = FeatureRepository.get_partition(session, record.supersedes_id or "")
    if previous is None or previous.published_at is None:
        raise ValueError("correction partition must supersede a persisted partition")
    if record.revision != previous.revision + 1:
        raise ValueError("correction partition revision must increment its superseded partition")
    if (
        record.indicator_id,
        record.definition_version,
        record.domain,
        record.frequency,
        record.partition_key,
        record.universe_scope_hash,
    ) != (
        previous.indicator_id,
        previous.definition_version,
        previous.domain,
        previous.frequency,
        previous.partition_key,
        previous.universe_scope_hash,
    ):
        raise ValueError("correction partition must preserve logical partition identity")


def _validate_snapshot_publication(session: Session, record: FeatureSnapshot) -> None:
    partitions = tuple(
        FeatureRepository.get_partition(session, ref.feature_partition_id)
        for ref in record.feature_partition_refs
    )
    if any(partition is None for partition in partitions):
        raise ValueError("snapshot references a missing partition")
    persisted_partitions = tuple(partition for partition in partitions if partition is not None)
    if any(partition.published_at is None for partition in persisted_partitions):
        raise ValueError("snapshot references an unpublished partition")
    if any(partition.cutoff_at != record.cutoff_at for partition in persisted_partitions):
        raise ValueError("snapshot cutoff_at does not match its partitions")
    partition_snapshot_ids = {
        snapshot_id
        for partition in persisted_partitions
        for snapshot_id in partition.data_snapshot_ids
    }
    if partition_snapshot_ids != set(record.data_snapshot_ids):
        raise ValueError("snapshot data_snapshot_ids must exactly match partition lineage")
    if record.max_source_available_at < max(partition.max_available_at for partition in persisted_partitions):
        raise ValueError("snapshot max_source_available_at does not cover its partitions")
    if record.publication_status is PublicationStatus.CERTIFIED:
        if record.published_at is None or record.quality_status is not QualityStatus.COMPLETE:
            raise ValueError("certified snapshot must be published and complete")
        if any(partition.quality_status is not QualityStatus.COMPLETE for partition in persisted_partitions):
            raise ValueError("certified snapshot cannot reference incomplete partitions")


def _validate_snapshot_lineage(session: Session, record: FeatureSnapshot) -> None:
    if record.revision_kind is not RevisionKind.CORRECTION:
        return
    previous = FeatureRepository.get_snapshot(session, record.supersedes_id or "")
    if previous is None or previous.published_at is None:
        raise ValueError("correction snapshot must supersede a persisted snapshot")
    if record.revision != previous.revision + 1:
        raise ValueError("correction snapshot revision must increment its superseded snapshot")
    if (
        record.as_of_trade_date != previous.as_of_trade_date
        or record.cutoff_at != previous.cutoff_at
        or record.dependency_plan_hash != previous.dependency_plan_hash
        or record.definition_refs != previous.definition_refs
    ):
        raise ValueError("correction snapshot must preserve its logical manifest identity")

    previous_refs = {ref.feature_partition_id: ref for ref in previous.feature_partition_refs}
    current_refs = {ref.feature_partition_id: ref for ref in record.feature_partition_refs}
    superseded_ids: set[str] = set()
    changed = False
    for ref in record.feature_partition_refs:
        current_partition = FeatureRepository.get_partition(session, ref.feature_partition_id)
        if current_partition is None:
            raise ValueError("correction snapshot references a missing partition")
        if ref.feature_partition_id in previous_refs:
            if ref != previous_refs[ref.feature_partition_id]:
                raise ValueError("correction snapshot must preserve unchanged partition references")
            continue
        changed = True
        predecessor_id = current_partition.supersedes_id
        if current_partition.revision_kind is not RevisionKind.CORRECTION or predecessor_id not in previous_refs:
            raise ValueError("correction snapshot contains a partition without predecessor lineage")
        if predecessor_id in superseded_ids:
            raise ValueError("correction snapshot cannot replace one predecessor twice")
        superseded_ids.add(predecessor_id)
    if not changed or superseded_ids != set(previous_refs) - set(current_refs):
        raise ValueError("correction snapshot must close over every replaced partition")
    if len(current_refs) != len(previous_refs):
        raise ValueError("correction snapshot must preserve partition coverage")


def _validate_bundle(session: Session, record: FeatureBundle) -> None:
    snapshots = tuple(
        FeatureRepository.get_snapshot(session, snapshot_id)
        for snapshot_id in record.feature_snapshot_ids
    )
    if any(snapshot is None for snapshot in snapshots):
        raise ValueError("feature bundle references a missing snapshot")
    persisted_snapshots = tuple(snapshot for snapshot in snapshots if snapshot is not None)
    if any(snapshot.publication_status is PublicationStatus.DRAFT or snapshot.published_at is None for snapshot in persisted_snapshots):
        raise ValueError("feature bundle references an unpublished snapshot")
    if record.consumer_kind is ConsumerKind.FORMAL_BACKTEST and any(
        snapshot.publication_status is not PublicationStatus.CERTIFIED
        or snapshot.quality_status is not QualityStatus.COMPLETE
        for snapshot in persisted_snapshots
    ):
        raise ValueError("formal feature bundle requires certified complete snapshots")
    if record.consumer_kind is ConsumerKind.FORMAL_BACKTEST and any(
        snapshot.published_at > record.cutoff_at for snapshot in persisted_snapshots
    ):
        raise ValueError("formal snapshot published_at must not exceed cutoff_at")
    if record.consumer_kind is ConsumerKind.FORMAL_BACKTEST:
        for ref in record.required_partition_refs:
            partition = FeatureRepository.get_partition(session, ref.feature_partition_id)
            if partition is None or partition.published_at is None or partition.published_at > record.cutoff_at:
                raise ValueError("formal partition published_at must not exceed cutoff_at")
    if any(snapshot.dependency_plan_hash != record.dependency_plan_hash for snapshot in persisted_snapshots):
        raise ValueError("feature bundle dependency plan does not match its snapshots")
    if any(snapshot.cutoff_at != record.cutoff_at for snapshot in persisted_snapshots):
        raise ValueError("feature bundle cutoff_at does not match its snapshots")

    snapshot_refs: dict[str, FeaturePartitionRef] = {}
    for snapshot in persisted_snapshots:
        for ref in snapshot.feature_partition_refs:
            previous = snapshot_refs.get(ref.feature_partition_id)
            if previous is not None and previous.model_dump(mode="python", exclude={"retention_class"}) != ref.model_dump(
                mode="python", exclude={"retention_class"}
            ):
                raise ValueError("feature bundle snapshots contain conflicting partition references")
            snapshot_refs[ref.feature_partition_id] = ref
    for ref in record.required_partition_refs:
        snapshot_ref = snapshot_refs.get(ref.feature_partition_id)
        if snapshot_ref is None:
            raise ValueError("feature bundle reference is not present in its snapshots")
        if ref.model_dump(mode="python", exclude={"retention_class"}) != snapshot_ref.model_dump(
            mode="python", exclude={"retention_class"}
        ):
            raise ValueError("feature bundle reference does not match its snapshot reference")


class FeatureRepository:
    """PostgreSQL control-plane persistence for immutable Feature artifacts."""

    @staticmethod
    def add_partition(session: Session, record: FeaturePartition) -> None:
        _validate_partition_lineage(session, record)
        session.execute(insert(feature_partition).values(**_partition_values(record)))

    @staticmethod
    def get_partition(session: Session, partition_id: str, *, for_update: bool = False) -> FeaturePartition | None:
        statement = select(feature_partition).where(feature_partition.c.feature_partition_id == partition_id)
        if for_update:
            statement = statement.with_for_update()
        row = session.execute(statement).mappings().one_or_none()
        return _partition_from_row(row) if row else None

    @staticmethod
    def add_snapshot(session: Session, record: FeatureSnapshot) -> None:
        _validate_refs(session, record.feature_partition_refs)
        _validate_snapshot_publication(session, record)
        _validate_snapshot_lineage(session, record)
        session.execute(insert(feature_snapshot).values(**_snapshot_values(record)))
        for order, ref in enumerate(record.feature_partition_refs):
            session.execute(insert(feature_snapshot_partition_ref).values(**_ref_values(ref, record.feature_snapshot_id, order, parent_column="feature_snapshot_id")))

    @staticmethod
    def get_snapshot(session: Session, snapshot_id: str, *, for_update: bool = False) -> FeatureSnapshot | None:
        statement = select(feature_snapshot).where(feature_snapshot.c.feature_snapshot_id == snapshot_id)
        if for_update:
            statement = statement.with_for_update()
        row = session.execute(statement).mappings().one_or_none()
        if row is None:
            return None
        refs = session.execute(
            select(feature_snapshot_partition_ref)
            .where(feature_snapshot_partition_ref.c.feature_snapshot_id == snapshot_id)
            .order_by(feature_snapshot_partition_ref.c.partition_order)
        ).mappings()
        return _snapshot_from_row(row, tuple(_ref_from_row(item) for item in refs))

    @staticmethod
    def add_bundle(session: Session, record: FeatureBundle) -> None:
        _validate_refs(session, record.required_partition_refs)
        _validate_bundle(session, record)
        session.execute(insert(feature_bundle).values(**_bundle_values(record)))
        for order, ref in enumerate(record.required_partition_refs):
            session.execute(insert(feature_bundle_partition_ref).values(**_ref_values(ref, record.feature_bundle_id, order, parent_column="feature_bundle_id")))

        if record.consumer_kind is ConsumerKind.FORMAL_BACKTEST:
            FeatureRepository.pin_partitions(session, tuple(ref.feature_partition_id for ref in record.required_partition_refs))

    @staticmethod
    def get_bundle(session: Session, bundle_id: str, *, for_update: bool = False) -> FeatureBundle | None:
        statement = select(feature_bundle).where(feature_bundle.c.feature_bundle_id == bundle_id)
        if for_update:
            statement = statement.with_for_update()
        row = session.execute(statement).mappings().one_or_none()
        if row is None:
            return None
        refs = session.execute(
            select(feature_bundle_partition_ref)
            .where(feature_bundle_partition_ref.c.feature_bundle_id == bundle_id)
            .order_by(feature_bundle_partition_ref.c.partition_order)
        ).mappings()
        return _bundle_from_row(row, tuple(_ref_from_row(item) for item in refs))

    @staticmethod
    def pin_partitions(session: Session, partition_ids: tuple[str, ...]) -> None:
        if not partition_ids:
            return
        unique_ids = tuple(dict.fromkeys(partition_ids))
        if len(unique_ids) != len(partition_ids):
            raise ValueError("partition_ids must be unique")
        result = session.execute(
            update(feature_partition)
            .where(feature_partition.c.feature_partition_id.in_(unique_ids))
            .values(
                retention_class=RetentionClass.PINNED.value,
                reference_count=feature_partition.c.reference_count + 1,
            )
        )
        if result.rowcount != len(unique_ids):
            raise ValueError("cannot pin a missing feature partition")


__all__ = [
    "FeatureRepository",
    "feature_bundle",
    "feature_bundle_partition_ref",
    "feature_partition",
    "feature_snapshot",
    "feature_snapshot_partition_ref",
    "metadata",
]
