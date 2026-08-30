from __future__ import annotations

import os
from pathlib import Path, PurePosixPath

from src.schemas.platform import StorageNamespace, StorageRef

from .errors import ArtifactStorageError


_RESERVED_ROOT_SEGMENTS = frozenset({".staging", "quarantine"})


def _invalid_path() -> ArtifactStorageError:
    return ArtifactStorageError(
        error_code="ARTIFACT_PATH_INVALID",
        public_message="Artifact storage path is invalid.",
        details={"component": "storage_path"},
    )


def validate_relative_path(value: str, *, allow_internal: bool = False) -> PurePosixPath:
    if not isinstance(value, str) or not value or value.startswith("/") or "\\" in value:
        raise _invalid_path()
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise _invalid_path()
    segments = value.split("/")
    if any(segment in {"", ".", ".."} for segment in segments):
        raise _invalid_path()
    if any(":" in segment for segment in segments):
        raise _invalid_path()
    if not allow_internal and segments[0] in _RESERVED_ROOT_SEGMENTS:
        raise _invalid_path()
    path = PurePosixPath(value)
    if path.is_absolute() or path.as_posix() != value:
        raise _invalid_path()
    return path


class StorageNamespaceResolver:
    """Bind logical StorageRef values to one local runtime root."""

    def __init__(self, runtime_root: Path | str) -> None:
        root = Path(runtime_root)
        if not root.is_absolute():
            root = root.absolute()
        self.runtime_root = root
        self._reject_symlink(root)

    @staticmethod
    def _reject_symlink(path: Path) -> None:
        try:
            if path.is_symlink():
                raise ArtifactStorageError(
                    error_code="ARTIFACT_SYMLINK_ESCAPE",
                    public_message="Artifact storage symlink is not allowed.",
                    details={"component": "storage_path"},
                )
        except OSError as exc:
            raise ArtifactStorageError(
                error_code="ARTIFACT_PATH_UNAVAILABLE",
                public_message="Artifact storage path is unavailable.",
                retryable=True,
                details={"component": "storage_path"},
                cause=exc,
            ) from exc

    def namespace_root(self, namespace: StorageNamespace = StorageNamespace.APP) -> Path:
        root = self.runtime_root / "storage" / namespace.value
        for candidate in (self.runtime_root, self.runtime_root / "storage", root):
            self._reject_symlink(candidate)
        return root

    def ensure_namespace(self, namespace: StorageNamespace = StorageNamespace.APP) -> Path:
        root = self.namespace_root(namespace)
        try:
            root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ArtifactStorageError(
                error_code="ARTIFACT_PATH_UNAVAILABLE",
                public_message="Artifact storage path is unavailable.",
                retryable=True,
                details={"component": "storage_path"},
                cause=exc,
            ) from exc
        for candidate in (self.runtime_root, self.runtime_root / "storage", root):
            self._reject_symlink(candidate)
        return root

    def resolve(
        self,
        ref_or_path: StorageRef | str,
        namespace: StorageNamespace = StorageNamespace.APP,
        *,
        require_exists: bool = False,
        allow_internal: bool = False,
    ) -> Path:
        if isinstance(ref_or_path, StorageRef):
            namespace = ref_or_path.storage_namespace
            relative_path = ref_or_path.relative_path
        else:
            relative_path = ref_or_path
        logical = validate_relative_path(relative_path, allow_internal=allow_internal)
        root = self.ensure_namespace(namespace)
        current = root
        for segment in logical.parts:
            current = current / segment
            self._reject_symlink(current)
        if require_exists and not current.exists():
            raise ArtifactStorageError(
                error_code="ARTIFACT_FILE_MISSING",
                public_message="Artifact file is missing.",
                details={"component": "artifact_file"},
            )
        return current


def fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
