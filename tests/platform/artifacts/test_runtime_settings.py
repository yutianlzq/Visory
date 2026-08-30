from __future__ import annotations

from pathlib import Path

import pytest

from src.artifacts.errors import ArtifactStorageError
from src.artifacts.settings import StorageRuntimeSettings


def test_runtime_root_is_read_only_from_explicit_environment_binding(tmp_path: Path) -> None:
    settings = StorageRuntimeSettings.from_environment({"VISORY_RUNTIME_ROOT": str(tmp_path)})
    assert settings.runtime_root == tmp_path


@pytest.mark.parametrize("environment", ({}, {"VISORY_RUNTIME_ROOT": "relative/runtime"}))
def test_missing_or_relative_runtime_root_is_rejected(environment: dict[str, str]) -> None:
    with pytest.raises(ArtifactStorageError) as captured:
        StorageRuntimeSettings.from_environment(environment)
    assert captured.value.error_code == "ARTIFACT_RUNTIME_ROOT_INVALID"
