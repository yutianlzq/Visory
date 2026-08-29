from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.schemas.platform import StorageRef


VALID_HASH = "sha256:" + "a" * 64


def test_storage_ref_accepts_logical_posix_path() -> None:
    ref = StorageRef(
        storage_backend="local_fs",
        storage_namespace="app",
        relative_path="features/domain=market/frequency=1d/year=2026/part-000.parquet",
        content_hash=VALID_HASH,
        media_type="application/vnd.apache.parquet",
        size_bytes=123456,
    )
    assert ref.relative_path.startswith("features/")


@pytest.mark.parametrize(
    "relative_path",
    [
        "/absolute/path",
        "C:/data/file.parquet",
        "\\\\server\\share\\file.parquet",
        "features\\file.parquet",
        "features//file.parquet",
        "features/./file.parquet",
        "features/../file.parquet",
        "",
    ],
)
def test_storage_ref_rejects_unsafe_paths(relative_path: str) -> None:
    with pytest.raises(ValidationError):
        StorageRef(
            storage_backend="local_fs",
            storage_namespace="app",
            relative_path=relative_path,
            content_hash=VALID_HASH,
            media_type="application/json",
            size_bytes=1,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("storage_backend", "s3"),
        ("storage_namespace", "postgres"),
        ("content_hash", "sha256:abc"),
        ("media_type", "not a media type"),
        ("size_bytes", -1),
    ],
)
def test_storage_ref_rejects_invalid_metadata(field: str, value: object) -> None:
    payload = {
        "storage_backend": "local_fs",
        "storage_namespace": "app",
        "relative_path": "artifacts/file.json",
        "content_hash": VALID_HASH,
        "media_type": "application/json",
        "size_bytes": 1,
    }
    payload[field] = value
    with pytest.raises(ValidationError):
        StorageRef.model_validate(payload)
