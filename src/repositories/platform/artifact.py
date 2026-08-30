from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    MetaData,
    String,
    Table,
    insert,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.orm import Session

from src.schemas.platform import (
    ArtifactIntegrityState,
    ArtifactPublicationState,
    ArtifactRecord,
    ResourceRef,
    ResourceType,
    StorageBackend,
    StorageNamespace,
    StorageRef,
)


metadata = MetaData()

artifact_registry = Table(
    "artifact_registry",
    metadata,
    Column("artifact_id", String(64), primary_key=True),
    Column("artifact_type", String(64), nullable=False),
    Column("owner_resource_type", String(64), nullable=False),
    Column("owner_resource_id", String(64), nullable=False),
    Column("attempt_id", String(64)),
    Column("storage_backend", String(32), nullable=False),
    Column("storage_namespace", String(32), nullable=False),
    Column("relative_path", String(1024), nullable=False),
    Column("content_hash", String(71), nullable=False),
    Column("media_type", String(255), nullable=False),
    Column("size_bytes", BigInteger, nullable=False),
    Column("artifact_hash", String(71), nullable=False),
    Column("manifest_hash", String(71), nullable=False),
    Column("schema_version", String(32), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("published_at", DateTime(timezone=True), nullable=False),
    Column("retention_class", String(32), nullable=False),
    Column("visibility", String(16), nullable=False),
    Column("publication_state", String(16), nullable=False),
    Column("integrity_state", String(32), nullable=False),
    Column("integrity_checked_at", DateTime(timezone=True)),
    Column("integrity_failure_code", String(64)),
)


def _values(record: ArtifactRecord) -> dict[str, object]:
    return {
        "artifact_id": record.artifact_id,
        "artifact_type": record.artifact_type,
        "owner_resource_type": record.owner_resource_ref.resource_type.value,
        "owner_resource_id": record.owner_resource_ref.resource_id,
        "attempt_id": record.attempt_id,
        "storage_backend": record.storage_ref.storage_backend.value,
        "storage_namespace": record.storage_ref.storage_namespace.value,
        "relative_path": record.storage_ref.relative_path,
        "content_hash": record.storage_ref.content_hash,
        "media_type": record.media_type,
        "size_bytes": record.size_bytes,
        "artifact_hash": record.artifact_hash,
        "manifest_hash": record.manifest_hash,
        "schema_version": record.schema_version,
        "created_at": record.created_at,
        "published_at": record.published_at,
        "retention_class": record.retention_class.value,
        "visibility": record.visibility.value,
        "publication_state": record.publication_state.value,
        "integrity_state": record.integrity_state.value,
        "integrity_checked_at": record.integrity_checked_at,
        "integrity_failure_code": record.integrity_failure_code,
    }


def _record(row) -> ArtifactRecord:
    storage_ref = StorageRef(
        storage_backend=StorageBackend(row["storage_backend"]),
        storage_namespace=StorageNamespace(row["storage_namespace"]),
        relative_path=row["relative_path"],
        content_hash=row["content_hash"],
        media_type=row["media_type"],
        size_bytes=row["size_bytes"],
    )
    return ArtifactRecord(
        artifact_id=row["artifact_id"],
        artifact_type=row["artifact_type"],
        owner_resource_ref=ResourceRef(
            resource_type=ResourceType(row["owner_resource_type"]),
            resource_id=row["owner_resource_id"],
        ),
        attempt_id=row["attempt_id"],
        storage_ref=storage_ref,
        media_type=row["media_type"],
        size_bytes=row["size_bytes"],
        artifact_hash=row["artifact_hash"],
        manifest_hash=row["manifest_hash"],
        schema_version=row["schema_version"],
        created_at=row["created_at"],
        published_at=row["published_at"],
        retention_class=row["retention_class"],
        visibility=row["visibility"],
        publication_state=row["publication_state"],
        integrity_state=row["integrity_state"],
        integrity_checked_at=row["integrity_checked_at"],
        integrity_failure_code=row["integrity_failure_code"],
    )


class ArtifactRepository:
    """Artifact Registry persistence. Callers own commit and rollback."""

    @staticmethod
    def add_published_artifact(session: Session, record: ArtifactRecord) -> None:
        session.execute(insert(artifact_registry).values(**_values(record)))

    @staticmethod
    def register_recovered_artifact(session: Session, record: ArtifactRecord) -> bool:
        statement = (
            postgresql_insert(artifact_registry)
            .values(**_values(record))
            .on_conflict_do_nothing(index_elements=[artifact_registry.c.artifact_id])
            .returning(artifact_registry.c.artifact_id)
        )
        return session.execute(statement).scalar_one_or_none() is not None

    @staticmethod
    def get_artifact(session: Session, artifact_id: str) -> ArtifactRecord | None:
        row = session.execute(
            select(artifact_registry).where(artifact_registry.c.artifact_id == artifact_id)
        ).mappings().one_or_none()
        return _record(row) if row is not None else None

    @staticmethod
    def get_consumable_artifact(session: Session, artifact_id: str) -> ArtifactRecord | None:
        row = session.execute(
            select(artifact_registry).where(
                artifact_registry.c.artifact_id == artifact_id,
                artifact_registry.c.publication_state == ArtifactPublicationState.PUBLISHED.value,
                artifact_registry.c.integrity_state == ArtifactIntegrityState.VERIFIED.value,
            )
        ).mappings().one_or_none()
        return _record(row) if row is not None else None

    @staticmethod
    def find_by_storage_ref(session: Session, storage_ref: StorageRef) -> ArtifactRecord | None:
        row = session.execute(
            select(artifact_registry).where(
                artifact_registry.c.storage_backend == storage_ref.storage_backend.value,
                artifact_registry.c.storage_namespace == storage_ref.storage_namespace.value,
                artifact_registry.c.relative_path == storage_ref.relative_path,
            )
        ).mappings().one_or_none()
        return _record(row) if row is not None else None

    @staticmethod
    def mark_integrity_failure(
        session: Session,
        artifact_id: str,
        *,
        integrity_state: ArtifactIntegrityState,
        failure_code: str,
        checked_at: datetime,
    ) -> None:
        if integrity_state is ArtifactIntegrityState.VERIFIED:
            raise ValueError("integrity failure cannot use VERIFIED")
        session.execute(
            update(artifact_registry)
            .where(artifact_registry.c.artifact_id == artifact_id)
            .values(
                integrity_state=integrity_state.value,
                integrity_checked_at=checked_at,
                integrity_failure_code=failure_code,
            )
        )


class InMemoryArtifactRepository:
    """Deterministic test repository; never a production fallback."""

    def __init__(self, *, fail_writes: bool = False) -> None:
        self._records: dict[str, ArtifactRecord] = {}
        self.fail_writes = fail_writes

    def add_published_artifact(self, _session: object, record: ArtifactRecord) -> None:
        if self.fail_writes:
            raise RuntimeError("injected artifact registry failure")
        if record.artifact_id in self._records:
            raise RuntimeError("artifact already registered")
        self._records[record.artifact_id] = record

    def register_recovered_artifact(self, _session: object, record: ArtifactRecord) -> bool:
        if self.fail_writes:
            raise RuntimeError("injected artifact registry failure")
        if record.artifact_id in self._records:
            return False
        self._records[record.artifact_id] = record
        return True

    def get_artifact(self, _session: object, artifact_id: str) -> ArtifactRecord | None:
        return self._records.get(artifact_id)

    def get_consumable_artifact(self, _session: object, artifact_id: str) -> ArtifactRecord | None:
        record = self._records.get(artifact_id)
        if record is None:
            return None
        if (
            record.publication_state is not ArtifactPublicationState.PUBLISHED
            or record.integrity_state is not ArtifactIntegrityState.VERIFIED
        ):
            return None
        return record

    def find_by_storage_ref(self, _session: object, storage_ref: StorageRef) -> ArtifactRecord | None:
        return next((record for record in self._records.values() if record.storage_ref == storage_ref), None)

    def mark_integrity_failure(
        self,
        _session: object,
        artifact_id: str,
        *,
        integrity_state: ArtifactIntegrityState,
        failure_code: str,
        checked_at: datetime,
    ) -> None:
        record = self._records[artifact_id]
        self._records[artifact_id] = ArtifactRecord.model_validate(
            {
                **record.model_dump(mode="python"),
                "integrity_state": integrity_state,
                "integrity_checked_at": checked_at,
                "integrity_failure_code": failure_code,
            }
        )


__all__ = ["ArtifactRepository", "InMemoryArtifactRepository", "artifact_registry"]
