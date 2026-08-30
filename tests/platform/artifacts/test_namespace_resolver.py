from __future__ import annotations

import os
from pathlib import Path

import pytest

from src.artifacts.errors import ArtifactStorageError
from src.artifacts.namespace import StorageNamespaceResolver
from src.schemas.platform import StorageNamespace


@pytest.mark.parametrize(
    "relative_path",
    (
        "/absolute/file",
        "../escape",
        "a/../escape",
        "a//b",
        "./file",
        r"C:\\temp\\file",
        "C:file",
        "file://host/path",
        "a/\x00b",
        "a/\x7fb",
    ),
)
def test_resolver_rejects_noncanonical_or_path_capable_input(tmp_path: Path, relative_path: str) -> None:
    resolver = StorageNamespaceResolver(tmp_path)
    with pytest.raises(ArtifactStorageError) as captured:
        resolver.resolve(relative_path)
    assert captured.value.error_code == "ARTIFACT_PATH_INVALID"


def _symlink_or_skip(link: Path, target: Path, *, target_is_directory: bool = True) -> None:
    try:
        link.symlink_to(target, target_is_directory=target_is_directory)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink unavailable: {exc}")


def test_runtime_root_and_namespace_root_cannot_be_symlinks(tmp_path: Path) -> None:
    real_root = tmp_path / "real"
    real_root.mkdir()
    linked_root = tmp_path / "linked"
    _symlink_or_skip(linked_root, real_root)

    with pytest.raises(ArtifactStorageError) as captured:
        StorageNamespaceResolver(linked_root)
    assert captured.value.error_code == "ARTIFACT_SYMLINK_ESCAPE"


def test_intermediate_and_target_symlinks_are_rejected(tmp_path: Path) -> None:
    resolver = StorageNamespaceResolver(tmp_path)
    root = resolver.ensure_namespace(StorageNamespace.APP)
    outside = tmp_path / "outside"
    outside.mkdir()
    intermediate = root / "artifacts"
    _symlink_or_skip(intermediate, outside)

    with pytest.raises(ArtifactStorageError) as captured:
        resolver.resolve("artifacts/type=report/payload.json")
    assert captured.value.error_code == "ARTIFACT_SYMLINK_ESCAPE"

    intermediate.unlink()
    (root / "artifacts").mkdir()
    target = root / "artifacts" / "payload.json"
    outside_file = outside / "payload.json"
    outside_file.write_bytes(b"outside")
    _symlink_or_skip(target, outside_file, target_is_directory=False)
    with pytest.raises(ArtifactStorageError) as captured:
        resolver.resolve("artifacts/payload.json", require_exists=True)
    assert captured.value.error_code == "ARTIFACT_SYMLINK_ESCAPE"


def test_resolver_returns_path_under_namespace_without_persisting_runtime_root(tmp_path: Path) -> None:
    resolver = StorageNamespaceResolver(tmp_path)
    resolved = resolver.resolve("artifacts/type=report/file.json")

    assert resolved == tmp_path / "storage" / "app" / "artifacts" / "type=report" / "file.json"
    assert str(tmp_path) not in "artifacts/type=report/file.json"
