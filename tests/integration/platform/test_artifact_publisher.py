from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.artifacts.errors import ArtifactPublishError
from src.artifacts.orphan import ArtifactOrphanSweeper
from src.repositories.platform import ArtifactRepository, PostgresDatabase, upgrade_database
from src.schemas.platform import ArtifactPublishRequest, ResourceRef, ResourceType, generate_resource_id
from src.services.platform.artifact_publisher import ArtifactPublisherService


NOW = datetime(2026, 8, 30, 11, 0, tzinfo=timezone.utc)
REPORT_ID = generate_resource_id(ResourceType.REPORT, timestamp_ms=1_777_000_400_000, random_bits=41)


def _request(artifact_id: str) -> ArtifactPublishRequest:
    return ArtifactPublishRequest(
        artifact_id=artifact_id,
        artifact_type="report",
        owner_resource_ref=ResourceRef(resource_type=ResourceType.REPORT, resource_id=REPORT_ID),
        attempt_id=None,
        payload_filename="payload.json",
        media_type="application/json",
        expected_content_hash=None,
        expected_size_bytes=None,
        schema_version="1.0.0",
        retention_class="AUDIT",
        visibility="OWNER",
    )


class _FailAfterInsertRepository(ArtifactRepository):
    def add_published_artifact(self, session, record) -> None:
        super().add_published_artifact(session, record)
        raise RuntimeError("force registry transaction rollback")


def test_real_postgres_publish_and_read_release_all_connections(
    isolated_postgres_database: PostgresDatabase,
    tmp_path,
) -> None:
    database = isolated_postgres_database
    upgrade_database(database.engine)
    repository = ArtifactRepository()
    artifact_id = generate_resource_id(ResourceType.ARTIFACT, timestamp_ms=1_777_000_400_000, random_bits=42)
    publisher = ArtifactPublisherService(
        tmp_path,
        repository,
        database.transaction,
        clock=lambda: NOW,
    )

    result = publisher.publish(_request(artifact_id), b'{"ok":true}\n')

    assert result.artifact_id == artifact_id
    assert publisher.read_content(artifact_id) == b'{"ok":true}\n'
    assert database.engine.pool.checkedout() == 0


def test_real_postgres_rollback_leaves_orphan_then_recovery_is_idempotent(
    isolated_postgres_database: PostgresDatabase,
    tmp_path,
) -> None:
    database = isolated_postgres_database
    upgrade_database(database.engine)
    artifact_id = generate_resource_id(ResourceType.ARTIFACT, timestamp_ms=1_777_000_400_000, random_bits=43)
    publisher = ArtifactPublisherService(
        tmp_path,
        _FailAfterInsertRepository(),
        database.transaction,
        clock=lambda: NOW,
    )

    with pytest.raises(ArtifactPublishError) as captured:
        publisher.publish(_request(artifact_id), b"orphan")
    assert captured.value.error_code == "ARTIFACT_REGISTRY_WRITE_FAILED"

    repository = ArtifactRepository()
    with database.transaction() as session:
        assert repository.get_artifact(session, artifact_id) is None
    orphan_directory = publisher.resolver.resolve(captured.value.details["orphan_relative_path"])
    assert orphan_directory.is_dir()

    sweeper = ArtifactOrphanSweeper(tmp_path, repository, database.transaction)
    assert [candidate.artifact_id for candidate in sweeper.dry_run().candidates] == [artifact_id]
    first = sweeper.recover_registration(artifact_id)
    second = sweeper.recover_registration(artifact_id)
    assert first.recovered is True
    assert second.already_registered is True
    assert database.engine.pool.checkedout() == 0
