from __future__ import annotations

from typing import Any

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, ForeignKeyConstraint, MetaData, String, Table, select, update
from sqlalchemy.dialects.postgresql import JSONB, insert as postgresql_insert
from sqlalchemy.orm import Session

from src.repositories.platform.provider import (
    dataset_definition,
    provider_capability,
    provider_definition,
    provider_policy,
    provider_raw_schema_definition,
    provider_rate_limit_window,
)
from src.schemas.platform import (
    DatasetDefinition,
    ProviderCapability,
    ProviderDefinition,
    ProviderPolicy,
    ProviderRun,
    RawIngestionQuarantine,
    RawObject,
    StorageBackend,
    StorageNamespace,
    StorageRef,
    ProviderRawSchemaDefinition,
)


metadata = MetaData()
provider_run = Table(
    "provider_run",
    metadata,
    Column("provider_run_id", String(64), primary_key=True),
    Column("provider_id", String(64), ForeignKey("provider_definition.provider_id"), nullable=False),
    Column("actual_upstream", String(255)),
    Column("dataset_id", String(64), nullable=False),
    Column("dataset_schema_version", String(32), nullable=False),
    Column("provider_policy_id", String(64), ForeignKey("provider_policy.provider_policy_id"), nullable=False),
    Column("provider_policy_version", String(32), nullable=False),
    Column("adapter_version", String(32), nullable=False),
    Column("capability_market", String(32), nullable=False),
    Column("capability_frequency", String(32), nullable=False),
    Column("task_id", String(64), ForeignKey("platform_task.task_id", deferrable=True, initially="DEFERRED"), nullable=False),
    Column("attempt_id", String(64), ForeignKey("task_attempt.attempt_id", deferrable=True, initially="DEFERRED"), nullable=False),
    Column("request_fingerprint", String(71), nullable=False),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("finished_at", DateTime(timezone=True)),
    Column("observed_schema_hash", String(71)),
    Column("row_count", BigInteger),
    Column("byte_count", BigInteger),
    Column("run_outcome", String(16)),
    Column("failure_code", String(64)),
    Column("failure_detail_redacted", String(512)),
    Column("raw_object_refs", JSONB, nullable=False),
    ForeignKeyConstraint(["dataset_id", "dataset_schema_version"], ["dataset_definition.dataset_id", "dataset_definition.schema_version"]),
    ForeignKeyConstraint(["provider_id", "dataset_id", "dataset_schema_version", "capability_market", "capability_frequency"], ["provider_capability.provider_id", "provider_capability.dataset_id", "provider_capability.dataset_schema_version", "provider_capability.market", "provider_capability.frequency"]),
)
raw_object = Table(
    "raw_object",
    metadata,
    Column("raw_object_id", String(64), primary_key=True),
    Column("provider_run_id", String(64), ForeignKey("provider_run.provider_run_id", ondelete="RESTRICT"), nullable=False, unique=True),
    Column("provider_id", String(64), nullable=False),
    Column("actual_upstream", String(255), nullable=False),
    Column("dataset_id", String(64), nullable=False),
    Column("dataset_schema_version", String(32), nullable=False),
    Column("request_fingerprint", String(71), nullable=False),
    Column("storage_backend", String(32), nullable=False),
    Column("storage_namespace", String(32), nullable=False),
    Column("relative_path", String(1024), nullable=False, unique=True),
    Column("raw_content_hash", String(71), nullable=False),
    Column("media_type", String(255), nullable=False),
    Column("compression", String(16), nullable=False),
    Column("observed_at", DateTime(timezone=True), nullable=False),
    Column("ingested_at", DateTime(timezone=True), nullable=False),
    Column("source_published_at", DateTime(timezone=True)),
    Column("provider_schema_version", String(32), nullable=False),
    Column("observed_schema_hash", String(71), nullable=False),
    Column("row_count", BigInteger, nullable=False),
    Column("byte_count", BigInteger, nullable=False),
    Column("retention_class", String(16), nullable=False),
)
raw_ingestion_quarantine = Table(
    "raw_ingestion_quarantine",
    metadata,
    Column("raw_ingestion_quarantine_id", String(64), primary_key=True),
    Column("provider_run_id", String(64), ForeignKey("provider_run.provider_run_id", ondelete="RESTRICT"), nullable=False, unique=True),
    Column("classification", String(32), nullable=False),
    Column("reason_code", String(64), nullable=False),
    Column("quarantine_status", String(16), nullable=False),
    Column("observed_schema_hash", String(71)),
    Column("expected_schema_hash", String(71), nullable=False),
    Column("storage_backend", String(32), nullable=False),
    Column("storage_namespace", String(32), nullable=False),
    Column("relative_path", String(1024), nullable=False, unique=True),
    Column("evidence_hash", String(71), nullable=False),
    Column("evidence_media_type", String(255), nullable=False),
    Column("evidence_size_bytes", BigInteger, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("failure_detail_redacted", String(512)),
)


def _storage(row: Any, *, hash_column: str) -> StorageRef:
    return StorageRef(
        storage_backend=StorageBackend(row["storage_backend"]),
        storage_namespace=StorageNamespace(row["storage_namespace"]),
        relative_path=row["relative_path"],
        content_hash=row[hash_column],
        media_type=row.get("media_type", "application/octet-stream"),
        size_bytes=row.get("byte_count", 0),
    )


def _provider_run(row: Any) -> ProviderRun:
    value = dict(row)
    value["raw_object_refs"] = tuple(value["raw_object_refs"])
    return ProviderRun.model_validate(value)


def _raw_object(row: Any) -> RawObject:
    value = dict(row)
    value["storage_ref"] = StorageRef(
        storage_backend=StorageBackend(value.pop("storage_backend")),
        storage_namespace=StorageNamespace(value.pop("storage_namespace")),
        relative_path=value.pop("relative_path"),
        content_hash=value["raw_content_hash"],
        media_type=value["media_type"],
        size_bytes=value["byte_count"],
    )
    return RawObject.model_validate(value)


def _quarantine(row: Any) -> RawIngestionQuarantine:
    value = dict(row)
    value["evidence_storage_ref"] = StorageRef(
        storage_backend=StorageBackend(value.pop("storage_backend")),
        storage_namespace=StorageNamespace(value.pop("storage_namespace")),
        relative_path=value.pop("relative_path"),
        content_hash=value["evidence_hash"],
        media_type=value.pop("evidence_media_type"),
        size_bytes=value.pop("evidence_size_bytes"),
    )
    # Quarantine evidence can be any media type. The table stores the hash and logical location only.
    return RawIngestionQuarantine.model_validate(value)


def _dataset(row: Any) -> DatasetDefinition:
    value = dict(row)
    for key in ("primary_key_fields", "required_fields", "optional_fields", "quality_rule_ids"):
        value[key] = tuple(value[key])
    value["enum_domains"] = {key: tuple(items) for key, items in value["enum_domains"].items()}
    return DatasetDefinition.model_validate(value)


def _capability(row: Any) -> ProviderCapability:
    value = dict(row)
    value["supported_fields"] = tuple(value["supported_fields"])
    return ProviderCapability.model_validate(value)


def _definition(row: Any) -> ProviderDefinition:
    return ProviderDefinition.model_validate(dict(row))


def _policy(row: Any) -> ProviderPolicy:
    value = dict(row)
    for key in ("supplemental_provider_ids", "fallback_triggers", "required_quality_rules"):
        value[key] = tuple(value[key])
    return ProviderPolicy.model_validate(value)


def _raw_schema(row: Any) -> ProviderRawSchemaDefinition:
    value = dict(row)
    value["required_fields"] = tuple(value["required_fields"])
    value["optional_fields"] = tuple(value["optional_fields"])
    return ProviderRawSchemaDefinition.model_validate(value)


class RawIngestionRepository:
    """Raw data persistence; application services own commit/rollback boundaries."""

    @staticmethod
    def add_provider_run(session: Session, record: ProviderRun) -> None:
        session.execute(provider_run.insert().values(**record.model_dump(mode="python")))

    @staticmethod
    def get_provider_run(session: Session, provider_run_id: str) -> ProviderRun | None:
        row = session.execute(select(provider_run).where(provider_run.c.provider_run_id == provider_run_id)).mappings().one_or_none()
        return _provider_run(row) if row is not None else None

    @staticmethod
    def update_provider_run(session: Session, record: ProviderRun) -> None:
        values = record.model_dump(mode="python")
        session.execute(update(provider_run).where(provider_run.c.provider_run_id == record.provider_run_id).values(**values))

    @staticmethod
    def add_raw_object(session: Session, record: RawObject) -> None:
        payload = record.model_dump(mode="python", exclude={"storage_ref"})
        storage_ref = record.storage_ref
        payload.update(
            storage_backend=storage_ref.storage_backend.value,
            storage_namespace=storage_ref.storage_namespace.value,
            relative_path=storage_ref.relative_path,
        )
        session.execute(raw_object.insert().values(**payload))

    @staticmethod
    def get_raw_object(session: Session, raw_object_id: str) -> RawObject | None:
        row = session.execute(select(raw_object).where(raw_object.c.raw_object_id == raw_object_id)).mappings().one_or_none()
        return _raw_object(row) if row is not None else None

    @staticmethod
    def get_raw_object_by_run(session: Session, provider_run_id: str) -> RawObject | None:
        row = session.execute(select(raw_object).where(raw_object.c.provider_run_id == provider_run_id)).mappings().one_or_none()
        return _raw_object(row) if row is not None else None

    @staticmethod
    def add_quarantine(session: Session, record: RawIngestionQuarantine) -> None:
        payload = record.model_dump(mode="python", exclude={"evidence_storage_ref"})
        storage_ref = record.evidence_storage_ref
        payload.update(
            storage_backend=storage_ref.storage_backend.value,
            storage_namespace=storage_ref.storage_namespace.value,
            relative_path=storage_ref.relative_path,
            evidence_media_type=storage_ref.media_type,
            evidence_size_bytes=storage_ref.size_bytes,
        )
        session.execute(raw_ingestion_quarantine.insert().values(**payload))

    @staticmethod
    def get_quarantine_by_run(session: Session, provider_run_id: str) -> RawIngestionQuarantine | None:
        row = session.execute(select(raw_ingestion_quarantine).where(raw_ingestion_quarantine.c.provider_run_id == provider_run_id)).mappings().one_or_none()
        return _quarantine(row) if row is not None else None

    @staticmethod
    def get_provider(session: Session, provider_id: str) -> ProviderDefinition | None:
        row = session.execute(select(provider_definition).where(provider_definition.c.provider_id == provider_id)).mappings().one_or_none()
        return _definition(row) if row is not None else None

    @staticmethod
    def get_dataset(session: Session, dataset_id: str, schema_version: str) -> DatasetDefinition | None:
        row = session.execute(select(dataset_definition).where(dataset_definition.c.dataset_id == dataset_id, dataset_definition.c.schema_version == schema_version)).mappings().one_or_none()
        return _dataset(row) if row is not None else None

    @staticmethod
    def get_capability(session: Session, provider_id: str, dataset_id: str, schema_version: str, market: str, frequency: str) -> ProviderCapability | None:
        row = session.execute(select(provider_capability).where(
            provider_capability.c.provider_id == provider_id,
            provider_capability.c.dataset_id == dataset_id,
            provider_capability.c.dataset_schema_version == schema_version,
            provider_capability.c.market == market,
            provider_capability.c.frequency == frequency,
        )).mappings().one_or_none()
        return _capability(row) if row is not None else None

    @staticmethod
    def get_policy(session: Session, provider_policy_id: str) -> ProviderPolicy | None:
        row = session.execute(select(provider_policy).where(provider_policy.c.provider_policy_id == provider_policy_id)).mappings().one_or_none()
        return _policy(row) if row is not None else None

    @staticmethod
    def get_provider_raw_schema(
        session: Session,
        provider_id: str,
        adapter_version: str,
        dataset_id: str,
        dataset_schema_version: str,
        provider_schema_version: str,
    ) -> ProviderRawSchemaDefinition | None:
        row = session.execute(
            select(provider_raw_schema_definition).where(
                provider_raw_schema_definition.c.provider_id == provider_id,
                provider_raw_schema_definition.c.adapter_version == adapter_version,
                provider_raw_schema_definition.c.dataset_id == dataset_id,
                provider_raw_schema_definition.c.dataset_schema_version == dataset_schema_version,
                provider_raw_schema_definition.c.provider_schema_version == provider_schema_version,
            )
        ).mappings().one_or_none()
        return _raw_schema(row) if row is not None else None

    @staticmethod
    def list_provider_raw_schemas(
        session: Session, provider_id: str, adapter_version: str, dataset_id: str, dataset_schema_version: str
    ) -> tuple[ProviderRawSchemaDefinition, ...]:
        rows = session.execute(
            select(provider_raw_schema_definition).where(
                provider_raw_schema_definition.c.provider_id == provider_id,
                provider_raw_schema_definition.c.adapter_version == adapter_version,
                provider_raw_schema_definition.c.dataset_id == dataset_id,
                provider_raw_schema_definition.c.dataset_schema_version == dataset_schema_version,
            ).order_by(provider_raw_schema_definition.c.provider_schema_version)
        ).mappings()
        return tuple(_raw_schema(row) for row in rows)

    @staticmethod
    def increment_rate_limit_window(
        session: Session,
        *,
        provider_id: str,
        dataset_id: str,
        market: str,
        frequency: str,
        window_epoch: int,
        limit: int,
    ) -> bool:
        key_columns = [
            provider_rate_limit_window.c.provider_id,
            provider_rate_limit_window.c.dataset_id,
            provider_rate_limit_window.c.market,
            provider_rate_limit_window.c.frequency,
        ]
        session.execute(
            postgresql_insert(provider_rate_limit_window)
            .values(
                provider_id=provider_id, dataset_id=dataset_id, market=market, frequency=frequency,
                window_epoch=window_epoch, request_count=0,
            )
            .on_conflict_do_nothing(index_elements=key_columns)
        )
        row = session.execute(
            select(provider_rate_limit_window).where(
                provider_rate_limit_window.c.provider_id == provider_id,
                provider_rate_limit_window.c.dataset_id == dataset_id,
                provider_rate_limit_window.c.market == market,
                provider_rate_limit_window.c.frequency == frequency,
            ).with_for_update()
        ).mappings().one()
        if row["window_epoch"] != window_epoch:
            session.execute(
                update(provider_rate_limit_window).where(
                    provider_rate_limit_window.c.provider_id == provider_id,
                    provider_rate_limit_window.c.dataset_id == dataset_id,
                    provider_rate_limit_window.c.market == market,
                    provider_rate_limit_window.c.frequency == frequency,
                ).values(window_epoch=window_epoch, request_count=1)
            )
            return True
        if row["request_count"] >= limit:
            return False
        session.execute(
            update(provider_rate_limit_window).where(
                provider_rate_limit_window.c.provider_id == provider_id,
                provider_rate_limit_window.c.dataset_id == dataset_id,
                provider_rate_limit_window.c.market == market,
                provider_rate_limit_window.c.frequency == frequency,
            ).values(request_count=row["request_count"] + 1)
        )
        return True


__all__ = [
    "RawIngestionRepository",
    "provider_run",
    "raw_ingestion_quarantine",
    "raw_object",
    "provider_raw_schema_definition",
    "provider_rate_limit_window",
]
