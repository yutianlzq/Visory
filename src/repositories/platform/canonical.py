from __future__ import annotations
from typing import Any
from sqlalchemy import BigInteger, Column, DateTime, Integer, MetaData, String, Table, select, insert
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session
from src.schemas.platform import CanonicalPartition, CanonicalQualityReport, ProviderCanonicalMappingDefinition, StorageBackend, StorageNamespace, StorageRef

metadata = MetaData()
canonical_mapping_definition = Table(
    "canonical_mapping_definition", metadata,
    Column("provider_id", String(64), primary_key=True), Column("dataset_id", String(64), primary_key=True),
    Column("dataset_schema_version", String(32), primary_key=True), Column("mapping_version", String(32), primary_key=True),
    Column("source_fields", JSONB, nullable=False), Column("source_field_types", JSONB, nullable=False),
    Column("target_fields", JSONB, nullable=False), Column("target_field_types", JSONB, nullable=False),
    Column("target_units", JSONB, nullable=False), Column("unit_multipliers", JSONB, nullable=False), Column("enum_mappings", JSONB, nullable=False),
    Column("null_semantics", JSONB, nullable=False), Column("time_semantics", JSONB, nullable=False),
    Column("mapping_hash", String(71), nullable=False), Column("created_at", DateTime(timezone=True), nullable=False),
)
canonical_quality_report = Table(
    "canonical_quality_report", metadata,
    Column("quality_report_id", String(64), primary_key=True), Column("canonical_partition_id", String(64)),
    Column("quality_status", String(16), nullable=False), Column("rule_results", JSONB, nullable=False),
    Column("row_count", BigInteger, nullable=False), Column("rejected_row_count", BigInteger, nullable=False),
    Column("duplicate_key_count", BigInteger, nullable=False), Column("identity_unresolved_count", BigInteger, nullable=False),
    Column("identity_ambiguous_count", BigInteger, nullable=False), Column("failure_reasons", JSONB, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)
canonical_partition = Table(
    "canonical_partition", metadata,
    Column("canonical_partition_id", String(64), primary_key=True), Column("dataset_id", String(64), nullable=False),
    Column("dataset_schema_version", String(32), nullable=False), Column("partition_key", String(255), nullable=False),
    Column("revision", Integer, nullable=False), Column("revision_kind", String(16), nullable=False), Column("supersedes_id", String(64)),
    Column("provider_policy_version", String(32), nullable=False), Column("provider_run_id", String(64), nullable=False), Column("raw_object_id", String(64), nullable=False),
    Column("available_from", DateTime(timezone=True), nullable=False), Column("available_to", DateTime(timezone=True)),
    Column("row_count", BigInteger, nullable=False), Column("security_count", BigInteger, nullable=False),
    Column("storage_backend", String(32), nullable=False), Column("storage_namespace", String(32), nullable=False), Column("relative_path", String(1024), nullable=False), Column("size_bytes", BigInteger, nullable=False),
    Column("partition_hash", String(71), nullable=False), Column("schema_hash", String(71), nullable=False), Column("quality_status", String(16), nullable=False),
    Column("quality_report_id", String(64), nullable=False), Column("created_at", DateTime(timezone=True), nullable=False), Column("published_at", DateTime(timezone=True)),
)
canonical_partition_lineage = Table(
    "canonical_partition_lineage", metadata,
    Column("canonical_partition_id", String(64), primary_key=True), Column("provider_run_id", String(64), primary_key=True), Column("raw_object_id", String(64), primary_key=True),
)


def _mapping(row: Any) -> ProviderCanonicalMappingDefinition:
    return ProviderCanonicalMappingDefinition.model_validate(dict(row))


def _quality(row: Any) -> CanonicalQualityReport:
    value = dict(row)
    value["failure_reasons"] = tuple(value["failure_reasons"])
    return CanonicalQualityReport.model_validate(value)


def _partition(row: Any) -> CanonicalPartition:
    value = dict(row)
    value["provider_run_refs"] = (value.pop("provider_run_id"),)
    value["raw_object_refs"] = (value.pop("raw_object_id"),)
    value["min_available_at"] = value.pop("available_from")
    value["max_available_at"] = value.pop("available_to")
    value["distinct_entity_count"] = value.pop("security_count")
    value["storage_ref"] = StorageRef(storage_backend=StorageBackend(value.pop("storage_backend")), storage_namespace=StorageNamespace(value.pop("storage_namespace")), relative_path=value.pop("relative_path"), content_hash=value["partition_hash"], media_type="application/vnd.apache.parquet", size_bytes=value.pop("size_bytes"))
    return CanonicalPartition.model_validate(value)


class CanonicalRepository:
    """Persistence for immutable canonical registry rows; callers own transaction boundaries."""
    @staticmethod
    def add_mapping(session: Session, record: ProviderCanonicalMappingDefinition) -> None:
        session.execute(insert(canonical_mapping_definition).values(**record.model_dump(mode="python")))

    @staticmethod
    def get_mapping(session: Session, provider_id: str, dataset_id: str, dataset_schema_version: str, mapping_version: str):
        row = session.execute(select(canonical_mapping_definition).where(canonical_mapping_definition.c.provider_id == provider_id, canonical_mapping_definition.c.dataset_id == dataset_id, canonical_mapping_definition.c.dataset_schema_version == dataset_schema_version, canonical_mapping_definition.c.mapping_version == mapping_version)).mappings().one_or_none()
        return _mapping(row) if row else None

    @staticmethod
    def add_quality_report(session: Session, record: CanonicalQualityReport) -> None:
        session.execute(insert(canonical_quality_report).values(**record.model_dump(mode="python")))

    @staticmethod
    def add_partition(session: Session, record: CanonicalPartition) -> None:
        payload = record.model_dump(mode="python", exclude={"storage_ref", "provider_run_refs", "raw_object_refs", "min_available_at", "max_available_at", "distinct_entity_count"})
        payload.update(provider_run_id=record.provider_run_id, raw_object_id=record.raw_object_id, available_from=record.min_available_at, available_to=record.max_available_at, security_count=record.distinct_entity_count)
        ref = record.storage_ref
        payload.update(storage_backend=ref.storage_backend.value, storage_namespace=ref.storage_namespace.value, relative_path=ref.relative_path, size_bytes=ref.size_bytes)
        session.execute(insert(canonical_partition).values(**payload))
        session.execute(insert(canonical_partition_lineage).values(canonical_partition_id=record.canonical_partition_id, provider_run_id=record.provider_run_id, raw_object_id=record.raw_object_id))

    @staticmethod
    def get_partition(session: Session, partition_id: str) -> CanonicalPartition | None:
        row = session.execute(select(canonical_partition).where(canonical_partition.c.canonical_partition_id == partition_id)).mappings().one_or_none()
        return _partition(row) if row else None

    @staticmethod
    def get_quality_report(session: Session, report_id: str) -> CanonicalQualityReport | None:
        row = session.execute(select(canonical_quality_report).where(canonical_quality_report.c.quality_report_id == report_id)).mappings().one_or_none()
        return _quality(row) if row else None

    @staticmethod
    def get_latest_partition_for_key(
        session: Session,
        *,
        dataset_id: str,
        partition_key: str,
    ) -> CanonicalPartition | None:
        row = session.execute(
            select(canonical_partition)
            .where(
                canonical_partition.c.dataset_id == dataset_id,
                canonical_partition.c.partition_key == partition_key,
            )
            .order_by(canonical_partition.c.revision.desc(), canonical_partition.c.created_at.desc())
            .limit(1)
        ).mappings().one_or_none()
        return _partition(row) if row else None


__all__ = ["CanonicalRepository", "canonical_mapping_definition", "canonical_partition", "canonical_partition_lineage", "canonical_quality_report"]
