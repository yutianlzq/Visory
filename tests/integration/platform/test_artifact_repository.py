from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from src.repositories.platform import PostgresDatabase, downgrade_database, get_migration_status, upgrade_database
from src.repositories.platform.artifact import ArtifactRepository
from src.schemas.platform import (
    ArtifactIntegrityState,
    ArtifactPublicationState,
    ArtifactRecord,
    ArtifactVisibility,
    ResourceRef,
    ResourceType,
    RetentionClass,
    StorageBackend,
    StorageNamespace,
    StorageRef,
    generate_resource_id,
)


HEAD_REVISION = "0003_wp0102_artifact_registry"
NOW = datetime(2026, 8, 30, 10, 0, tzinfo=timezone.utc)
ARTIFACT_ID = generate_resource_id(ResourceType.ARTIFACT, timestamp_ms=1_777_000_300_000, random_bits=31)
REPORT_ID = generate_resource_id(ResourceType.REPORT, timestamp_ms=1_777_000_300_000, random_bits=32)
DIGEST = "sha256:" + "a" * 64
MANIFEST_DIGEST = "sha256:" + "b" * 64


def _record() -> ArtifactRecord:
    storage = StorageRef(
        storage_backend=StorageBackend.LOCAL_FS,
        storage_namespace=StorageNamespace.APP,
        relative_path=f"artifacts/type=report/year=2026/month=08/artifact_id={ARTIFACT_ID}/payload.json",
        content_hash=DIGEST,
        media_type="application/json",
        size_bytes=7,
    )
    return ArtifactRecord(
        artifact_id=ARTIFACT_ID,
        artifact_type="report",
        owner_resource_ref=ResourceRef(resource_type=ResourceType.REPORT, resource_id=REPORT_ID),
        attempt_id=None,
        storage_ref=storage,
        media_type=storage.media_type,
        size_bytes=storage.size_bytes,
        artifact_hash=DIGEST,
        manifest_hash=MANIFEST_DIGEST,
        schema_version="1.0.0",
        created_at=NOW,
        published_at=NOW,
        retention_class=RetentionClass.AUDIT,
        visibility=ArtifactVisibility.OWNER,
        publication_state=ArtifactPublicationState.PUBLISHED,
        integrity_state=ArtifactIntegrityState.VERIFIED,
        integrity_checked_at=NOW,
        integrity_failure_code=None,
    )


def test_migration_0003_is_reversible_and_does_not_touch_files(
    isolated_postgres_database: PostgresDatabase, tmp_path,
) -> None:
    marker = tmp_path / "published-artifact"
    marker.write_text("keep", encoding="utf-8")
    upgrade_database(isolated_postgres_database.engine, HEAD_REVISION)
    assert get_migration_status(isolated_postgres_database.engine).current_revision == HEAD_REVISION
    with isolated_postgres_database.engine.connect() as connection:
        assert connection.execute(text("SELECT to_regclass('public.artifact_registry')")).scalar_one() == "artifact_registry"
        columns = set(
            connection.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = 'artifact_registry'"
                )
            ).scalars()
        )
    assert {"runtime_root", "absolute_path", "host_path"}.isdisjoint(columns)

    downgrade_database(isolated_postgres_database.engine, "0002_wp0101_asset_identity")
    with isolated_postgres_database.engine.connect() as connection:
        assert connection.execute(text("SELECT to_regclass('public.artifact_registry')")).scalar_one() is None
    assert marker.read_text(encoding="utf-8") == "keep"

    upgrade_database(isolated_postgres_database.engine, HEAD_REVISION)
    assert get_migration_status(isolated_postgres_database.engine).current_revision == HEAD_REVISION


def test_repository_has_no_implicit_commit_and_integrity_failure_blocks_consumption(
    isolated_postgres_database: PostgresDatabase,
) -> None:
    database = isolated_postgres_database
    upgrade_database(database.engine)
    repository = ArtifactRepository()

    with pytest.raises(RuntimeError, match="rollback"):
        with database.transaction() as session:
            repository.add_published_artifact(session, _record())
            assert repository.get_artifact(session, ARTIFACT_ID) is not None
            raise RuntimeError("rollback")

    with database.transaction() as session:
        assert repository.get_artifact(session, ARTIFACT_ID) is None
        repository.add_published_artifact(session, _record())

    with database.transaction() as session:
        assert repository.get_consumable_artifact(session, ARTIFACT_ID) is not None
        repository.mark_integrity_failure(
            session,
            ARTIFACT_ID,
            integrity_state=ArtifactIntegrityState.MISSING,
            failure_code="ARTIFACT_FILE_MISSING",
            checked_at=NOW,
        )

    with database.transaction() as session:
        assert repository.get_consumable_artifact(session, ARTIFACT_ID) is None
        damaged = repository.get_artifact(session, ARTIFACT_ID)
    assert damaged is not None
    assert damaged.integrity_state is ArtifactIntegrityState.MISSING
