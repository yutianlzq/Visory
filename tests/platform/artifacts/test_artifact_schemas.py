from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from src.schemas.platform import (
    ArtifactIntegrityState,
    ArtifactManifest,
    ArtifactPublicationState,
    ArtifactPublishRequest,
    ArtifactRecord,
    ArtifactVisibility,
    OrphanAction,
    OrphanCandidate,
    OrphanDryRunResult,
    ResourceRef,
    ResourceType,
    RetentionClass,
    StorageBackend,
    StorageNamespace,
    StorageRef,
    generate_resource_id,
)


NOW = datetime(2026, 8, 30, 8, 0, tzinfo=timezone.utc)
ARTIFACT_ID = generate_resource_id(ResourceType.ARTIFACT, timestamp_ms=1_777_000_000_000, random_bits=1)
REPORT_ID = generate_resource_id(ResourceType.REPORT, timestamp_ms=1_777_000_000_000, random_bits=2)
ATTEMPT_ID = generate_resource_id(ResourceType.ATTEMPT, timestamp_ms=1_777_000_000_000, random_bits=3)
DIGEST = "sha256:" + "1" * 64
MANIFEST_DIGEST = "sha256:" + "2" * 64


def _storage_ref() -> StorageRef:
    return StorageRef(
        storage_backend=StorageBackend.LOCAL_FS,
        storage_namespace=StorageNamespace.APP,
        relative_path=f"artifacts/type=report/year=2026/month=08/artifact_id={ARTIFACT_ID}/payload.json",
        content_hash=DIGEST,
        media_type="application/json",
        size_bytes=2,
    )


def test_artifact_record_requires_typed_ids_and_consistent_storage_metadata() -> None:
    record = ArtifactRecord(
        artifact_id=ARTIFACT_ID,
        artifact_type="report",
        owner_resource_ref=ResourceRef(resource_type=ResourceType.REPORT, resource_id=REPORT_ID),
        attempt_id=ATTEMPT_ID,
        storage_ref=_storage_ref(),
        media_type="application/json",
        size_bytes=2,
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

    assert record.storage_ref.relative_path.endswith("/payload.json")

    with pytest.raises(ValidationError, match="attempt_id"):
        record.model_copy(update={"attempt_id": ARTIFACT_ID}).model_validate(
            {**record.model_dump(mode="python"), "attempt_id": ARTIFACT_ID}
        )

    with pytest.raises(ValidationError, match="storage_ref"):
        ArtifactRecord.model_validate({**record.model_dump(mode="python"), "size_bytes": 3})


def test_artifact_manifest_and_orphan_contracts_have_explicit_semantics() -> None:
    record = ArtifactRecord(
        artifact_id=ARTIFACT_ID,
        artifact_type="report",
        owner_resource_ref=ResourceRef(resource_type=ResourceType.REPORT, resource_id=REPORT_ID),
        attempt_id=None,
        storage_ref=_storage_ref(),
        media_type="application/json",
        size_bytes=2,
        artifact_hash=DIGEST,
        manifest_hash=MANIFEST_DIGEST,
        schema_version="1.0.0",
        created_at=NOW,
        published_at=NOW,
        retention_class=RetentionClass.REBUILDABLE,
        visibility=ArtifactVisibility.PRIVATE,
        publication_state=ArtifactPublicationState.PUBLISHED,
        integrity_state=ArtifactIntegrityState.VERIFIED,
        integrity_checked_at=NOW,
        integrity_failure_code=None,
    )
    manifest = ArtifactManifest.from_record(record)
    candidate = OrphanCandidate(
        artifact_id=ARTIFACT_ID,
        manifest_relative_path=record.storage_ref.relative_path.rsplit("/", 1)[0] + "/manifest.json",
        reason_code="REGISTRY_ENTRY_MISSING",
        estimated_size_bytes=record.size_bytes,
        recoverable_actions=(OrphanAction.RECOVER_REGISTRATION,),
    )
    dry_run = OrphanDryRunResult(
        scanned_known_directories=1,
        candidates=(candidate,),
        skipped_invalid_manifests=0,
        estimated_recoverable_bytes=2,
        deletion_performed=False,
    )

    assert manifest.manifest_hash == MANIFEST_DIGEST
    assert dry_run.deletion_performed is False
    assert dry_run.candidates[0].recoverable_actions == (OrphanAction.RECOVER_REGISTRATION,)


def test_publish_request_rejects_path_capable_filename_and_wrong_attempt_prefix() -> None:
    payload = {
        "artifact_id": ARTIFACT_ID,
        "artifact_type": "report",
        "owner_resource_ref": {"resource_type": "report", "resource_id": REPORT_ID},
        "attempt_id": None,
        "payload_filename": "payload.json",
        "media_type": "application/json",
        "expected_content_hash": DIGEST,
        "expected_size_bytes": 2,
        "schema_version": "1.0.0",
        "retention_class": "AUDIT",
        "visibility": "OWNER",
    }
    ArtifactPublishRequest.model_validate(payload)

    for filename in ("../payload.json", "a/b.json", r"a\\b.json", "manifest.json", "C:payload"):
        with pytest.raises(ValidationError):
            ArtifactPublishRequest.model_validate({**payload, "payload_filename": filename})

    with pytest.raises(ValidationError, match="attempt_id"):
        ArtifactPublishRequest.model_validate({**payload, "attempt_id": ARTIFACT_ID})
