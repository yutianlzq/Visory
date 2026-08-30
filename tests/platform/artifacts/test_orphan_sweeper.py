from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.artifacts.orphan import ArtifactOrphanSweeper
from src.repositories.platform.artifact import InMemoryArtifactRepository
from src.schemas.platform import ArtifactPublishRequest, ResourceRef, ResourceType, generate_resource_id
from src.services.platform.artifact_publisher import ArtifactPublisherService


NOW = datetime(2026, 8, 30, 9, 0, tzinfo=timezone.utc)
ARTIFACT_ID = generate_resource_id(ResourceType.ARTIFACT, timestamp_ms=1_777_000_200_000, random_bits=21)
REPORT_ID = generate_resource_id(ResourceType.REPORT, timestamp_ms=1_777_000_200_000, random_bits=22)


@contextmanager
def _session_scope():
    yield object()


def _request() -> ArtifactPublishRequest:
    return ArtifactPublishRequest(
        artifact_id=ARTIFACT_ID,
        artifact_type="report",
        owner_resource_ref=ResourceRef(resource_type=ResourceType.REPORT, resource_id=REPORT_ID),
        attempt_id=None,
        payload_filename="payload.json",
        media_type="application/json",
        expected_content_hash=None,
        expected_size_bytes=None,
        schema_version="1.0.0",
        retention_class="REBUILDABLE",
        visibility="PRIVATE",
    )


def test_orphan_dry_run_and_recovery_are_safe_and_idempotent(tmp_path: Path) -> None:
    failing = InMemoryArtifactRepository(fail_writes=True)
    publisher = ArtifactPublisherService(tmp_path, failing, _session_scope, clock=lambda: NOW)
    try:
        publisher.publish(_request(), b"orphan")
    except Exception:
        pass

    repository = InMemoryArtifactRepository()
    sweeper = ArtifactOrphanSweeper(tmp_path, repository, _session_scope)
    first = sweeper.dry_run()
    assert first.deletion_performed is False
    assert [candidate.artifact_id for candidate in first.candidates] == [ARTIFACT_ID]
    assert first.estimated_recoverable_bytes == len(b"orphan")

    recovered = sweeper.recover_registration(ARTIFACT_ID)
    repeated = sweeper.recover_registration(ARTIFACT_ID)
    assert recovered.recovered is True
    assert recovered.already_registered is False
    assert repeated.recovered is False
    assert repeated.already_registered is True
    assert sweeper.dry_run().candidates == ()


def test_sweeper_ignores_unknown_directories_and_invalid_manifests(tmp_path: Path) -> None:
    unknown = tmp_path / "storage" / "app" / "unknown" / "nested"
    unknown.mkdir(parents=True)
    (unknown / "manifest.json").write_text("{}", encoding="utf-8")
    known = tmp_path / "storage" / "app" / "artifacts" / "type=report" / "year=2026" / "month=08" / f"artifact_id={ARTIFACT_ID}"
    known.mkdir(parents=True)
    (known / "manifest.json").write_text("{}", encoding="utf-8")

    result = ArtifactOrphanSweeper(tmp_path, InMemoryArtifactRepository(), _session_scope).dry_run()
    assert result.candidates == ()
    assert result.scanned_known_directories == 1
    assert result.skipped_invalid_manifests == 1


def test_sweeper_does_not_descend_into_symlinked_known_directory(tmp_path: Path) -> None:
    namespace_root = tmp_path / "storage" / "app"
    artifact_root = namespace_root / "artifacts"
    artifact_root.mkdir(parents=True)
    outside_type = tmp_path / "outside-type"
    manifest_directory = (
        outside_type / "year=2026" / "month=08" / f"artifact_id={ARTIFACT_ID}"
    )
    manifest_directory.mkdir(parents=True)
    (manifest_directory / "manifest.json").write_text("{}", encoding="utf-8")
    try:
        (artifact_root / "type=report").symlink_to(outside_type, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink unavailable: {exc}")

    result = ArtifactOrphanSweeper(
        tmp_path, InMemoryArtifactRepository(), _session_scope
    ).dry_run()

    assert result.scanned_known_directories == 0
    assert result.skipped_invalid_manifests == 0
    assert result.candidates == ()
