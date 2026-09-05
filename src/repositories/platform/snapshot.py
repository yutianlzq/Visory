from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import BigInteger, Boolean, Column, Date, DateTime, Integer, MetaData, String, Table, insert, select, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from src.schemas.platform import (
    CapabilityCertification,
    ConsumerKind,
    ConsumerRequirement,
    DataSnapshot,
    QualityStatus,
    SnapshotCapabilityStatus,
    SnapshotCurrentPointer,
    SnapshotPartitionRef,
)

metadata = MetaData()
data_snapshot = Table(
    "data_snapshot", metadata,
    Column("snapshot_id", String(64), primary_key=True), Column("trade_date", Date, nullable=False),
    Column("cutoff_at", DateTime(timezone=True), nullable=False), Column("provider_policy_id", String(64), nullable=False),
    Column("provider_policy_version", String(32), nullable=False), Column("security_master_ref", String(64), nullable=False),
    Column("calendar_ref", String(64), nullable=False), Column("quality_report_refs", JSONB, nullable=False),
    Column("quality_status", String(16), nullable=False), Column("publication_status", String(16), nullable=False),
    Column("certified_capabilities", JSONB, nullable=False), Column("missing_capabilities", JSONB, nullable=False),
    Column("revision", Integer, nullable=False), Column("revision_kind", String(16), nullable=False), Column("supersedes_id", String(64)),
    Column("available_at", DateTime(timezone=True), nullable=False), Column("created_at", DateTime(timezone=True), nullable=False),
    Column("published_at", DateTime(timezone=True)), Column("manifest_version", String(32), nullable=False),
    Column("manifest_hash", String(71), nullable=False), Column("content_hash", String(71), nullable=False),
    Column("task_id", String(64)), Column("attempt_id", String(64)),
)
snapshot_partition_ref = Table(
    "snapshot_partition_ref", metadata,
    Column("snapshot_id", String(64), primary_key=True), Column("canonical_partition_id", String(64), primary_key=True),
    Column("dataset_id", String(64), nullable=False), Column("dataset_schema_version", String(32), nullable=False),
    Column("provider_policy_version", String(32), nullable=False), Column("partition_key", String(255), nullable=False),
    Column("revision", Integer, nullable=False), Column("revision_kind", String(16), nullable=False), Column("storage_backend", String(32), nullable=False),
    Column("storage_namespace", String(32), nullable=False), Column("relative_path", String(1024), nullable=False), Column("media_type", String(255), nullable=False), Column("size_bytes", BigInteger, nullable=False),
    Column("partition_hash", String(71), nullable=False), Column("schema_hash", String(71), nullable=False),
    Column("quality_report_id", String(64), nullable=False), Column("quality_status", String(16), nullable=False),
    Column("provider_run_refs", JSONB, nullable=False), Column("raw_object_refs", JSONB, nullable=False),
    Column("min_available_at", DateTime(timezone=True), nullable=False), Column("max_available_at", DateTime(timezone=True)), Column("row_count", BigInteger, nullable=False),
)
capability_certification = Table(
    "capability_certification", metadata,
    Column("capability_id", String(64), primary_key=True), Column("snapshot_id", String(64), primary_key=True),
    Column("capability_status", String(16), nullable=False), Column("reason_code", String(64)), Column("evidence_refs", JSONB, nullable=False), Column("certified_at", DateTime(timezone=True)),
)
consumer_requirement = Table(
    "consumer_requirement", metadata,
    Column("consumer_id", String(64), primary_key=True), Column("consumer_kind", String(32), nullable=False),
    Column("required_capabilities", JSONB, nullable=False), Column("accepted_publication_statuses", JSONB, nullable=False),
    Column("min_quality_status", String(16), nullable=False), Column("allow_provisional", Boolean, nullable=False), Column("requirement_version", String(32), nullable=False),
)
snapshot_current_pointer = Table(
    "snapshot_current_pointer", metadata,
    Column("scope", String(64), primary_key=True), Column("trade_date", Date, primary_key=True), Column("capability_id", String(64), primary_key=True),
    Column("snapshot_id", String(64), nullable=False), Column("previous_snapshot_id", String(64)), Column("pointer_revision", Integer, nullable=False), Column("updated_at", DateTime(timezone=True), nullable=False),
)


def _snapshot_values(record: DataSnapshot, *, task_id: str | None = None, attempt_id: str | None = None) -> dict[str, Any]:
    value = record.model_dump(mode="python")
    for key in ("canonical_partitions",):
        value.pop(key, None)
    value.update(
        trade_date=record.trade_date,
        quality_report_refs=list(record.quality_report_refs),
        certified_capabilities=list(record.certified_capabilities),
        missing_capabilities=list(record.missing_capabilities),
        quality_status=record.quality_status.value,
        publication_status=record.publication_status.value,
        revision_kind=record.revision_kind.value,
        task_id=task_id,
        attempt_id=attempt_id,
    )
    return value


def _snapshot_values_from_row(row: Any) -> dict[str, Any]:
    value = dict(row)
    for key in ("quality_report_refs", "certified_capabilities", "missing_capabilities"):
        value[key] = tuple(value.get(key) or ())
    return value


def _partition_values(record: SnapshotPartitionRef, snapshot_id: str) -> dict[str, Any]:
    ref = record.storage_ref
    return {
        "snapshot_id": snapshot_id, "canonical_partition_id": record.canonical_partition_id, "dataset_id": record.dataset_id,
        "dataset_schema_version": record.dataset_schema_version, "provider_policy_version": record.provider_policy_version,
        "partition_key": record.partition_key, "revision": record.revision, "revision_kind": record.revision_kind.value,
        "storage_backend": ref.storage_backend.value, "storage_namespace": ref.storage_namespace.value, "relative_path": ref.relative_path, "media_type": ref.media_type, "size_bytes": ref.size_bytes,
        "partition_hash": record.partition_hash, "schema_hash": record.schema_hash, "quality_report_id": record.quality_report_id,
        "quality_status": record.quality_status.value, "provider_run_refs": list(record.provider_run_refs), "raw_object_refs": list(record.raw_object_refs),
        "min_available_at": record.min_available_at, "max_available_at": record.max_available_at, "row_count": record.row_count,
    }


def _partition(row: Any) -> SnapshotPartitionRef:
    from src.schemas.platform import StorageBackend, StorageNamespace, StorageRef, RevisionKind
    value = dict(row)
    value["revision_kind"] = RevisionKind(value["revision_kind"])
    value["quality_status"] = QualityStatus(value["quality_status"])
    value["provider_run_refs"] = tuple(value["provider_run_refs"] or ())
    value["raw_object_refs"] = tuple(value["raw_object_refs"] or ())
    value["storage_ref"] = StorageRef(storage_backend=StorageBackend(value.pop("storage_backend")), storage_namespace=StorageNamespace(value.pop("storage_namespace")), relative_path=value.pop("relative_path"), content_hash=value["partition_hash"], media_type=value.pop("media_type"), size_bytes=value.pop("size_bytes"))
    return SnapshotPartitionRef.model_validate(value)


def _capability(row: Any) -> CapabilityCertification:
    value = dict(row)
    value["capability_status"] = SnapshotCapabilityStatus(value["capability_status"])
    value["evidence_refs"] = tuple(value.get("evidence_refs") or ())
    return CapabilityCertification.model_validate(value)


def _consumer(row: Any) -> ConsumerRequirement:
    value = dict(row)
    value["consumer_kind"] = ConsumerKind(value["consumer_kind"])
    value["required_capabilities"] = tuple(value["required_capabilities"] or ())
    value["accepted_publication_statuses"] = tuple(value["accepted_publication_statuses"] or ())
    return ConsumerRequirement.model_validate(value)


class SnapshotRepository:
    """Immutable snapshot persistence; callers own transaction and rollback boundaries."""

    @staticmethod
    def add_snapshot(session: Session, record: DataSnapshot, *, task_id: str | None = None, attempt_id: str | None = None) -> None:
        session.execute(insert(data_snapshot).values(**_snapshot_values(record, task_id=task_id, attempt_id=attempt_id)))
        for ref in record.canonical_partitions:
            session.execute(insert(snapshot_partition_ref).values(**_partition_values(ref, record.snapshot_id)))

    @staticmethod
    def get_snapshot(session: Session, snapshot_id: str, *, include_partitions: bool = True) -> DataSnapshot | None:
        row = session.execute(select(data_snapshot).where(data_snapshot.c.snapshot_id == snapshot_id)).mappings().one_or_none()
        if row is None:
            return None
        value = _snapshot_values_from_row(row)
        if include_partitions:
            parts = session.execute(select(snapshot_partition_ref).where(snapshot_partition_ref.c.snapshot_id == snapshot_id).order_by(snapshot_partition_ref.c.dataset_id, snapshot_partition_ref.c.partition_key, snapshot_partition_ref.c.revision)).mappings()
            value["canonical_partitions"] = tuple(_partition(item) for item in parts)
        else:
            value["canonical_partitions"] = ()
        return DataSnapshot.model_validate(value)

    @staticmethod
    def add_capability(session: Session, record: CapabilityCertification) -> None:
        session.execute(insert(capability_certification).values(**{**record.model_dump(mode="python"), "capability_status": record.capability_status.value, "evidence_refs": list(record.evidence_refs)}))

    @staticmethod
    def get_capability(session: Session, snapshot_id: str, capability_id: str) -> CapabilityCertification | None:
        row = session.execute(select(capability_certification).where(capability_certification.c.snapshot_id == snapshot_id, capability_certification.c.capability_id == capability_id)).mappings().one_or_none()
        return _capability(row) if row else None

    @staticmethod
    def list_capabilities(session: Session, snapshot_id: str) -> tuple[CapabilityCertification, ...]:
        rows = session.execute(select(capability_certification).where(capability_certification.c.snapshot_id == snapshot_id).order_by(capability_certification.c.capability_id)).mappings()
        return tuple(_capability(row) for row in rows)

    @staticmethod
    def add_consumer_requirement(session: Session, record: ConsumerRequirement) -> None:
        session.execute(insert(consumer_requirement).values(consumer_id=record.consumer_id, consumer_kind=record.consumer_kind.value, required_capabilities=list(record.required_capabilities), accepted_publication_statuses=[item.value for item in record.accepted_publication_statuses], min_quality_status=record.min_quality_status.value, allow_provisional=record.allow_provisional, requirement_version=record.requirement_version))

    @staticmethod
    def get_consumer_requirement(session: Session, consumer_id: str) -> ConsumerRequirement | None:
        row = session.execute(select(consumer_requirement).where(consumer_requirement.c.consumer_id == consumer_id)).mappings().one_or_none()
        return _consumer(row) if row else None

    @staticmethod
    def get_pointer(session: Session, *, scope: str, trade_date: date, capability_id: str, for_update: bool = False) -> SnapshotCurrentPointer | None:
        statement = select(snapshot_current_pointer).where(snapshot_current_pointer.c.scope == scope, snapshot_current_pointer.c.trade_date == trade_date, snapshot_current_pointer.c.capability_id == capability_id)
        if for_update:
            statement = statement.with_for_update()
        row = session.execute(statement).mappings().one_or_none()
        return SnapshotCurrentPointer.model_validate(dict(row)) if row else None

    @staticmethod
    def upsert_pointer(session: Session, pointer: SnapshotCurrentPointer, *, expected_snapshot_id: str | None = None) -> SnapshotCurrentPointer:
        current = SnapshotRepository.get_pointer(session, scope=pointer.scope, trade_date=pointer.trade_date, capability_id=pointer.capability_id, for_update=True)
        if expected_snapshot_id is not None and (current is None or current.snapshot_id != expected_snapshot_id):
            raise ValueError("SNAPSHOT_POINTER_CAS_FAILED")
        if current is None:
            session.execute(insert(snapshot_current_pointer).values(**pointer.model_dump(mode="python")))
        else:
            session.execute(update(snapshot_current_pointer).where(snapshot_current_pointer.c.scope == pointer.scope, snapshot_current_pointer.c.trade_date == pointer.trade_date, snapshot_current_pointer.c.capability_id == pointer.capability_id).values(**pointer.model_dump(mode="python")))
        return pointer


__all__ = ["SnapshotRepository", "capability_certification", "consumer_requirement", "data_snapshot", "snapshot_current_pointer", "snapshot_partition_ref"]
