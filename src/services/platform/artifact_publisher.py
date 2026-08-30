from __future__ import annotations

import json
import os
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from src.artifacts.errors import ArtifactIntegrityError, ArtifactPublishError, ArtifactStorageError
from src.artifacts.hashing import compute_bytes_hash
from src.artifacts.manifest import compute_manifest_hash, manifest_json_bytes, parse_and_verify_manifest
from src.artifacts.namespace import StorageNamespaceResolver, fsync_directory
from src.schemas.platform import (
    ArtifactIntegrityState,
    ArtifactManifest,
    ArtifactPublicationState,
    ArtifactPublishRequest,
    ArtifactPublishResult,
    ArtifactRecord,
    StorageBackend,
    StorageNamespace,
    StorageRef,
)


class ArtifactRepositoryPort(Protocol):
    def add_published_artifact(self, session: object, record: ArtifactRecord) -> None:
        ...

    def get_artifact(self, session: object, artifact_id: str) -> ArtifactRecord | None:
        ...

    def get_consumable_artifact(self, session: object, artifact_id: str) -> ArtifactRecord | None:
        ...

    def mark_integrity_failure(
        self,
        session: object,
        artifact_id: str,
        *,
        integrity_state: ArtifactIntegrityState,
        failure_code: str,
        checked_at: datetime,
    ) -> None:
        ...


TransactionContext = Callable[[], AbstractContextManager[object]]
RenameFunction = Callable[[Path, Path], None]
RegistrationCallback = Callable[[object, ArtifactRecord], None]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _default_rename(source: Path, target: Path) -> None:
    os.rename(source, target)


class ArtifactPublisherService:
    """Validate, atomically publish, then register immutable Artifact files."""

    def __init__(
        self,
        runtime_root: Path | str,
        repository: ArtifactRepositoryPort,
        transaction_context: TransactionContext,
        *,
        clock: Callable[[], datetime] = _utc_now,
        rename: RenameFunction = _default_rename,
    ) -> None:
        self.resolver = StorageNamespaceResolver(runtime_root)
        self.repository = repository
        self.transaction_context = transaction_context
        self.clock = clock
        self.rename = rename

    @staticmethod
    def _target_relative_path(request: ArtifactPublishRequest, published_at: datetime) -> str:
        return (
            f"artifacts/type={request.artifact_type}/year={published_at:%Y}/month={published_at:%m}/"
            f"artifact_id={request.artifact_id}/{request.payload_filename}"
        )

    def _quarantine_diagnostic(self, artifact_id: str, error_code: str) -> None:
        quarantine_root = self.resolver.resolve("quarantine", allow_internal=True)
        quarantine_root.mkdir(parents=True, exist_ok=True)
        directory = quarantine_root / f"{artifact_id}-{uuid4().hex}"
        directory.mkdir()
        diagnostic = {"artifact_id": artifact_id, "error_code": error_code}
        path = directory / "diagnostic.json"
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(diagnostic, handle, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        fsync_directory(directory)
        fsync_directory(quarantine_root)

    def _validation_error(self, request: ArtifactPublishRequest, error_code: str) -> ArtifactPublishError:
        self._quarantine_diagnostic(request.artifact_id, error_code)
        return ArtifactPublishError(
            error_code=error_code,
            public_message="Artifact content validation failed.",
            details={"component": "artifact_content"},
        )

    def publish(
        self,
        request: ArtifactPublishRequest,
        content: bytes,
        *,
        after_register: RegistrationCallback | None = None,
    ) -> ArtifactPublishResult:
        if not isinstance(content, bytes):
            raise self._validation_error(request, "ARTIFACT_CONTENT_INVALID")
        now = self.clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("artifact publisher clock must return a timezone-aware datetime")
        content_hash = compute_bytes_hash(content)
        size_bytes = len(content)
        if request.expected_content_hash is not None and request.expected_content_hash != content_hash:
            raise self._validation_error(request, "ARTIFACT_HASH_MISMATCH")
        if request.expected_size_bytes is not None and request.expected_size_bytes != size_bytes:
            raise self._validation_error(request, "ARTIFACT_SIZE_MISMATCH")

        relative_path = self._target_relative_path(request, now)
        storage_ref = StorageRef(
            storage_backend=StorageBackend.LOCAL_FS,
            storage_namespace=StorageNamespace.APP,
            relative_path=relative_path,
            content_hash=content_hash,
            media_type=request.media_type,
            size_bytes=size_bytes,
        )
        target_payload = self.resolver.resolve(storage_ref)
        target_directory = target_payload.parent
        if target_directory.exists():
            raise ArtifactPublishError(
                error_code="ARTIFACT_TARGET_EXISTS",
                public_message="Artifact target already exists.",
                details={"component": "artifact_target"},
            )

        staging_root = self.resolver.resolve(".staging", allow_internal=True)
        staging_root.mkdir(parents=True, exist_ok=True)
        staging_directory = staging_root / f"{request.artifact_id}-{uuid4().hex}"
        staging_directory.mkdir()
        staging_payload = staging_directory / request.payload_filename
        try:
            with staging_payload.open("xb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())

            placeholder_hash = "sha256:" + "0" * 64
            placeholder_record = ArtifactRecord(
                artifact_id=request.artifact_id,
                artifact_type=request.artifact_type,
                owner_resource_ref=request.owner_resource_ref,
                attempt_id=request.attempt_id,
                storage_ref=storage_ref,
                media_type=request.media_type,
                size_bytes=size_bytes,
                artifact_hash=content_hash,
                manifest_hash=placeholder_hash,
                schema_version=request.schema_version,
                created_at=now,
                published_at=now,
                retention_class=request.retention_class,
                visibility=request.visibility,
                publication_state=ArtifactPublicationState.PUBLISHED,
                integrity_state=ArtifactIntegrityState.VERIFIED,
                integrity_checked_at=now,
                integrity_failure_code=None,
            )
            placeholder_manifest = ArtifactManifest.from_record(placeholder_record)
            manifest_hash = compute_manifest_hash(placeholder_manifest)
            record = ArtifactRecord.model_validate(
                {**placeholder_record.model_dump(mode="python"), "manifest_hash": manifest_hash}
            )
            manifest = ArtifactManifest.from_record(record)
            manifest_path = staging_directory / "manifest.json"
            with manifest_path.open("xb") as handle:
                handle.write(manifest_json_bytes(manifest))
                handle.flush()
                os.fsync(handle.fileno())
            fsync_directory(staging_directory)
            fsync_directory(staging_root)

            target_parent = target_directory.parent
            self.resolver.resolve(target_parent.relative_to(self.resolver.namespace_root()).as_posix()).mkdir(
                parents=True, exist_ok=True
            )
            self.resolver.resolve(storage_ref)
            if target_directory.exists():
                raise ArtifactPublishError(
                    error_code="ARTIFACT_TARGET_EXISTS",
                    public_message="Artifact target already exists.",
                    details={"component": "artifact_target"},
                )
            try:
                self.rename(staging_directory, target_directory)
            except OSError as exc:
                error_code = "ARTIFACT_TARGET_EXISTS" if target_directory.exists() else "ARTIFACT_RENAME_FAILED"
                raise ArtifactPublishError(
                    error_code=error_code,
                    public_message=(
                        "Artifact target already exists."
                        if error_code == "ARTIFACT_TARGET_EXISTS"
                        else "Artifact atomic publication failed."
                    ),
                    retryable=error_code == "ARTIFACT_RENAME_FAILED",
                    details={"component": "artifact_target"},
                    cause=exc,
                ) from exc
            fsync_directory(target_parent)
        except ArtifactPublishError:
            raise
        except OSError as exc:
            raise ArtifactPublishError(
                error_code="ARTIFACT_WRITE_FAILED",
                public_message="Artifact staging write failed.",
                retryable=True,
                details={"component": "artifact_staging"},
                cause=exc,
            ) from exc

        try:
            with self.transaction_context() as session:
                self.repository.add_published_artifact(session, record)
                if after_register is not None:
                    after_register(session, record)
        except Exception as exc:
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            raise ArtifactPublishError(
                error_code="ARTIFACT_REGISTRY_WRITE_FAILED",
                public_message="Artifact registry update failed after file publication.",
                retryable=True,
                details={"orphan_relative_path": target_directory.relative_to(self.resolver.namespace_root()).as_posix()},
                cause=exc,
            ) from exc

        return ArtifactPublishResult(
            artifact_id=record.artifact_id,
            storage_ref=record.storage_ref,
            artifact_hash=record.artifact_hash,
            manifest_hash=record.manifest_hash,
            publication_state=record.publication_state,
            integrity_state=record.integrity_state,
            published_at=record.published_at,
        )

    def _mark_failure(
        self,
        artifact_id: str,
        state: ArtifactIntegrityState,
        failure_code: str,
    ) -> None:
        with self.transaction_context() as session:
            self.repository.mark_integrity_failure(
                session,
                artifact_id,
                integrity_state=state,
                failure_code=failure_code,
                checked_at=self.clock(),
            )

    def read_content(self, artifact_id: str) -> bytes:
        with self.transaction_context() as session:
            record = self.repository.get_consumable_artifact(session, artifact_id)
        if record is None:
            raise ArtifactIntegrityError(
                error_code="ARTIFACT_NOT_CONSUMABLE",
                public_message="Artifact is not available for consumption.",
                details={"artifact_id": artifact_id},
            )
        try:
            payload_path = self.resolver.resolve(record.storage_ref, require_exists=True)
            content = payload_path.read_bytes()
        except ArtifactStorageError as exc:
            state = ArtifactIntegrityState.MISSING
            self._mark_failure(artifact_id, state, "ARTIFACT_FILE_MISSING")
            raise ArtifactIntegrityError(
                error_code="ARTIFACT_FILE_MISSING",
                public_message="Artifact file is missing.",
                details={"artifact_id": artifact_id},
                cause=exc,
            ) from exc
        if len(content) != record.size_bytes:
            self._mark_failure(artifact_id, ArtifactIntegrityState.SIZE_MISMATCH, "ARTIFACT_SIZE_MISMATCH")
            raise ArtifactIntegrityError(
                error_code="ARTIFACT_SIZE_MISMATCH",
                public_message="Artifact size integrity check failed.",
                details={"artifact_id": artifact_id},
            )
        if compute_bytes_hash(content) != record.artifact_hash:
            self._mark_failure(artifact_id, ArtifactIntegrityState.HASH_MISMATCH, "ARTIFACT_HASH_MISMATCH")
            raise ArtifactIntegrityError(
                error_code="ARTIFACT_HASH_MISMATCH",
                public_message="Artifact hash integrity check failed.",
                details={"artifact_id": artifact_id},
            )
        try:
            manifest = parse_and_verify_manifest((payload_path.parent / "manifest.json").read_bytes())
            if manifest.to_record() != record:
                raise ValueError("manifest does not match registry")
        except Exception as exc:
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            self._mark_failure(artifact_id, ArtifactIntegrityState.MANIFEST_INVALID, "ARTIFACT_MANIFEST_INVALID")
            raise ArtifactIntegrityError(
                error_code="ARTIFACT_MANIFEST_INVALID",
                public_message="Artifact manifest integrity check failed.",
                details={"artifact_id": artifact_id},
                cause=exc,
            ) from exc
        return content
