from __future__ import annotations

import re
from collections.abc import Callable
from contextlib import AbstractContextManager
from pathlib import Path

from src.artifacts.hashing import compute_bytes_hash
from src.artifacts.manifest import parse_and_verify_manifest
from src.artifacts.namespace import StorageNamespaceResolver
from src.schemas.platform import (
    ArtifactManifest,
    ArtifactPublicationState,
    ArtifactRecoveryResult,
    OrphanAction,
    OrphanCandidate,
    OrphanDryRunResult,
)


_KNOWN_DIRECTORY_PATTERN = re.compile(
    r"^artifacts/type=[a-z][a-z0-9._-]{0,63}/year=[0-9]{4}/month=(0[1-9]|1[0-2])/"
    r"artifact_id=(artifact_[0-9a-f-]{36})$"
)


class ArtifactOrphanSweeper:
    """Dry-run and recover Artifact orphans; WP-0102 never deletes files."""

    def __init__(self, runtime_root, repository, transaction_context: Callable[[], AbstractContextManager[object]]) -> None:
        self.resolver = StorageNamespaceResolver(runtime_root)
        self.repository = repository
        self.transaction_context = transaction_context

    def _known_manifests(self) -> tuple[Path, ...]:
        artifact_root = self.resolver.ensure_namespace() / "artifacts"
        if not artifact_root.is_dir() or artifact_root.is_symlink():
            return ()
        paths: list[Path] = []
        for manifest_path in artifact_root.glob("type=*/year=*/month=*/artifact_id=*/manifest.json"):
            relative_directory = manifest_path.parent.relative_to(self.resolver.namespace_root()).as_posix()
            if _KNOWN_DIRECTORY_PATTERN.fullmatch(relative_directory):
                paths.append(manifest_path)
        return tuple(sorted(paths, key=lambda path: path.as_posix()))

    def _load_valid_manifest(self, manifest_path: Path) -> ArtifactManifest:
        relative_manifest = manifest_path.relative_to(self.resolver.namespace_root()).as_posix()
        self.resolver.resolve(relative_manifest, require_exists=True)
        manifest = parse_and_verify_manifest(manifest_path.read_bytes())
        match = _KNOWN_DIRECTORY_PATTERN.fullmatch(manifest_path.parent.relative_to(self.resolver.namespace_root()).as_posix())
        if match is None or match.group(2) != manifest.artifact_id:
            raise ValueError("artifact directory does not match manifest")
        payload_path = self.resolver.resolve(manifest.storage_ref, require_exists=True)
        if payload_path.parent != manifest_path.parent:
            raise ValueError("manifest payload path is outside artifact directory")
        content = payload_path.read_bytes()
        if len(content) != manifest.size_bytes:
            raise ValueError("artifact size mismatch")
        if compute_bytes_hash(content) != manifest.artifact_hash:
            raise ValueError("artifact hash mismatch")
        return manifest

    def dry_run(self) -> OrphanDryRunResult:
        candidates: list[OrphanCandidate] = []
        skipped = 0
        manifests = self._known_manifests()
        for manifest_path in manifests:
            try:
                manifest = self._load_valid_manifest(manifest_path)
            except Exception:
                skipped += 1
                continue
            with self.transaction_context() as session:
                registered = self.repository.get_artifact(session, manifest.artifact_id)
            if registered is not None:
                continue
            candidates.append(
                OrphanCandidate(
                    artifact_id=manifest.artifact_id,
                    manifest_relative_path=manifest_path.relative_to(self.resolver.namespace_root()).as_posix(),
                    reason_code="REGISTRY_ENTRY_MISSING",
                    estimated_size_bytes=manifest.size_bytes,
                    recoverable_actions=(OrphanAction.RECOVER_REGISTRATION,),
                )
            )
        return OrphanDryRunResult(
            scanned_known_directories=len(manifests),
            candidates=tuple(candidates),
            skipped_invalid_manifests=skipped,
            estimated_recoverable_bytes=sum(candidate.estimated_size_bytes for candidate in candidates),
            deletion_performed=False,
        )

    def recover_registration(self, artifact_id: str) -> ArtifactRecoveryResult:
        with self.transaction_context() as session:
            existing = self.repository.get_artifact(session, artifact_id)
        if existing is not None:
            return ArtifactRecoveryResult(
                artifact_id=artifact_id,
                recovered=False,
                already_registered=True,
                publication_state=ArtifactPublicationState.PUBLISHED,
            )
        candidate = next((item for item in self.dry_run().candidates if item.artifact_id == artifact_id), None)
        if candidate is None:
            raise ValueError("recoverable orphan was not found")
        manifest_path = self.resolver.resolve(candidate.manifest_relative_path, require_exists=True)
        manifest = self._load_valid_manifest(manifest_path)
        with self.transaction_context() as session:
            inserted = self.repository.register_recovered_artifact(session, manifest.to_record())
        return ArtifactRecoveryResult(
            artifact_id=artifact_id,
            recovered=inserted,
            already_registered=not inserted,
            publication_state=ArtifactPublicationState.PUBLISHED,
        )
