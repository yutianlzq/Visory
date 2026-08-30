from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from .errors import ArtifactStorageError


@dataclass(frozen=True, slots=True)
class StorageRuntimeSettings:
    runtime_root: Path

    @classmethod
    def from_environment(cls, environment: Mapping[str, str] | None = None) -> "StorageRuntimeSettings":
        active = os.environ if environment is None else environment
        raw = active.get("VISORY_RUNTIME_ROOT", "")
        path = Path(raw) if raw else None
        if path is None or not path.is_absolute():
            raise ArtifactStorageError(
                error_code="ARTIFACT_RUNTIME_ROOT_INVALID",
                public_message="Artifact runtime root is not configured correctly.",
                details={"configuration": "VISORY_RUNTIME_ROOT"},
            )
        return cls(runtime_root=path)
