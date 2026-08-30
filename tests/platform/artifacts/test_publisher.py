from __future__ import annotations

from contextlib import contextmanager
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.artifacts.errors import ArtifactIntegrityError, ArtifactPublishError
from src.artifacts.manifest import compute_manifest_hash, manifest_json_bytes, parse_and_verify_manifest
from src.repositories.platform.artifact import InMemoryArtifactRepository
from src.schemas.platform import (
    ArtifactPublishRequest,
    ArtifactVisibility,
    ResourceRef,
    ResourceType,
    RetentionClass,
    generate_resource_id,
)
from src.services.platform.artifact_publisher import ArtifactPublisherService


NOW = datetime(2026, 8, 30, 8, 30, tzinfo=timezone.utc)
ARTIFACT_ID = generate_resource_id(ResourceType.ARTIFACT, timestamp_ms=1_777_000_100_000, random_bits=11)
REPORT_ID = generate_resource_id(ResourceType.REPORT, timestamp_ms=1_777_000_100_000, random_bits=12)


@contextmanager
def _session_scope():
    yield object()


def _request(**updates: object) -> ArtifactPublishRequest:
    values = dict(
        artifact_id=ARTIFACT_ID,
        artifact_type="report",
        owner_resource_ref=ResourceRef(resource_type=ResourceType.REPORT, resource_id=REPORT_ID),
        attempt_id=None,
        payload_filename="payload.json",
        media_type="application/json",
        expected_content_hash=None,
        expected_size_bytes=None,
        schema_version="1.0.0",
        retention_class=RetentionClass.AUDIT,
        visibility=ArtifactVisibility.OWNER,
    )
    values.update(updates)
    return ArtifactPublishRequest(**values)


def test_normal_publish_reads_content_and_manifest_hash_is_deterministic(tmp_path: Path) -> None:
    repository = InMemoryArtifactRepository()
    service = ArtifactPublisherService(
        runtime_root=tmp_path,
        repository=repository,
        transaction_context=_session_scope,
        clock=lambda: NOW,
    )
    content = b'{"ok":true}\n'

    result = service.publish(_request(), content)
    record = repository.get_artifact(object(), ARTIFACT_ID)
    assert record is not None
    assert service.read_content(ARTIFACT_ID) == content

    manifest_path = service.resolver.resolve(record.storage_ref.relative_path).parent / "manifest.json"
    manifest = parse_and_verify_manifest(manifest_path.read_bytes())
    assert manifest.manifest_hash == compute_manifest_hash(manifest)
    assert manifest_json_bytes(manifest) == manifest_json_bytes(manifest)
    assert result.manifest_hash == manifest.manifest_hash
    assert str(tmp_path) not in manifest_path.read_text(encoding="utf-8")


def test_hash_or_size_mismatch_is_quarantined_and_not_registered(tmp_path: Path) -> None:
    repository = InMemoryArtifactRepository()
    service = ArtifactPublisherService(tmp_path, repository, _session_scope, clock=lambda: NOW)

    with pytest.raises(ArtifactPublishError) as captured:
        service.publish(_request(expected_size_bytes=99), b"actual")
    assert captured.value.error_code == "ARTIFACT_SIZE_MISMATCH"
    assert repository.get_artifact(object(), ARTIFACT_ID) is None
    assert any((tmp_path / "storage" / "app" / "quarantine").iterdir())


def test_rename_failure_never_registers_artifact(tmp_path: Path) -> None:
    repository = InMemoryArtifactRepository()

    def fail_rename(_source: Path, _target: Path) -> None:
        raise OSError("injected rename failure")

    service = ArtifactPublisherService(
        tmp_path, repository, _session_scope, clock=lambda: NOW, rename=fail_rename
    )
    with pytest.raises(ArtifactPublishError) as captured:
        service.publish(_request(), b"content")
    assert captured.value.error_code == "ARTIFACT_RENAME_FAILED"
    assert repository.get_artifact(object(), ARTIFACT_ID) is None


def test_database_failure_after_rename_leaves_invisible_orphan(tmp_path: Path) -> None:
    repository = InMemoryArtifactRepository(fail_writes=True)
    service = ArtifactPublisherService(tmp_path, repository, _session_scope, clock=lambda: NOW)

    with pytest.raises(ArtifactPublishError) as captured:
        service.publish(_request(), b"content")
    assert captured.value.error_code == "ARTIFACT_REGISTRY_WRITE_FAILED"
    orphan_path = service.resolver.resolve(captured.value.details["orphan_relative_path"])
    assert orphan_path.is_dir()
    assert repository.get_artifact(object(), ARTIFACT_ID) is None


def test_missing_or_tampered_registry_file_is_marked_and_blocked(tmp_path: Path) -> None:
    repository = InMemoryArtifactRepository()
    service = ArtifactPublisherService(tmp_path, repository, _session_scope, clock=lambda: NOW)
    service.publish(_request(), b"content")
    record = repository.get_artifact(object(), ARTIFACT_ID)
    assert record is not None
    payload_path = service.resolver.resolve(record.storage_ref.relative_path, require_exists=True)

    payload_path.write_bytes(b"changed")
    with pytest.raises(ArtifactIntegrityError) as captured:
        service.read_content(ARTIFACT_ID)
    assert captured.value.error_code == "ARTIFACT_HASH_MISMATCH"
    damaged = repository.get_artifact(object(), ARTIFACT_ID)
    assert damaged is not None
    assert damaged.integrity_state.value == "HASH_MISMATCH"


def test_missing_registry_file_is_marked_and_blocked(tmp_path: Path) -> None:
    artifact_id = generate_resource_id(ResourceType.ARTIFACT, timestamp_ms=1_777_000_100_000, random_bits=13)
    repository = InMemoryArtifactRepository()
    service = ArtifactPublisherService(tmp_path, repository, _session_scope, clock=lambda: NOW)
    service.publish(_request(artifact_id=artifact_id), b"content")
    record = repository.get_artifact(object(), artifact_id)
    assert record is not None
    service.resolver.resolve(record.storage_ref.relative_path, require_exists=True).unlink()

    with pytest.raises(ArtifactIntegrityError) as captured:
        service.read_content(artifact_id)
    assert captured.value.error_code == "ARTIFACT_FILE_MISSING"
    damaged = repository.get_artifact(object(), artifact_id)
    assert damaged is not None
    assert damaged.integrity_state.value == "MISSING"


def test_concurrent_publishers_allow_only_one_atomic_target(tmp_path: Path) -> None:
    repository = InMemoryArtifactRepository()
    barrier = threading.Barrier(2)
    lock = threading.Lock()
    outcomes: list[str] = []

    def synchronized_rename(source: Path, target: Path) -> None:
        barrier.wait(timeout=5)
        os.rename(source, target)

    def publish(content: bytes) -> None:
        service = ArtifactPublisherService(
            tmp_path, repository, _session_scope, clock=lambda: NOW, rename=synchronized_rename
        )
        try:
            service.publish(_request(), content)
            outcome = "published"
        except ArtifactPublishError as exc:
            outcome = exc.error_code
        with lock:
            outcomes.append(outcome)

    first = threading.Thread(target=publish, args=(b"first",))
    second = threading.Thread(target=publish, args=(b"second",))
    first.start()
    second.start()
    first.join(timeout=10)
    second.join(timeout=10)

    assert sorted(outcomes) == ["ARTIFACT_TARGET_EXISTS", "published"]
    reader = ArtifactPublisherService(tmp_path, repository, _session_scope, clock=lambda: NOW)
    assert reader.read_content(ARTIFACT_ID) in {b"first", b"second"}


def test_concurrent_or_repeated_publish_cannot_overwrite_existing_target(tmp_path: Path) -> None:
    repository = InMemoryArtifactRepository()
    service = ArtifactPublisherService(tmp_path, repository, _session_scope, clock=lambda: NOW)
    service.publish(_request(), b"first")

    with pytest.raises(ArtifactPublishError) as captured:
        service.publish(_request(), b"second")
    assert captured.value.error_code == "ARTIFACT_TARGET_EXISTS"
    assert service.read_content(ARTIFACT_ID) == b"first"
