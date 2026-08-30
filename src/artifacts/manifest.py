from __future__ import annotations

import json

from pydantic import ValidationError

from src.schemas.platform import ArtifactManifest, HashProfile, canonical_json_bytes

from .errors import ArtifactManifestError
from .hashing import compute_bytes_hash


_MANIFEST_HASH_PROFILE = HashProfile(
    profile_id="artifact_manifest_1.0.0",
    excluded_fields=frozenset(),
)


def compute_manifest_hash(manifest: ArtifactManifest) -> str:
    payload = manifest.model_dump(mode="python", exclude={"manifest_hash"})
    return compute_bytes_hash(canonical_json_bytes(payload, _MANIFEST_HASH_PROFILE))


def manifest_json_bytes(manifest: ArtifactManifest) -> bytes:
    return (
        json.dumps(
            manifest.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def parse_and_verify_manifest(content: bytes) -> ArtifactManifest:
    try:
        payload = json.loads(content.decode("utf-8"))
        manifest = ArtifactManifest.model_validate(payload)
    except (UnicodeDecodeError, json.JSONDecodeError, ValidationError) as exc:
        raise ArtifactManifestError(
            error_code="ARTIFACT_MANIFEST_INVALID",
            public_message="Artifact manifest is invalid.",
            details={"component": "artifact_manifest"},
            cause=exc,
        ) from exc
    if compute_manifest_hash(manifest) != manifest.manifest_hash:
        raise ArtifactManifestError(
            error_code="ARTIFACT_MANIFEST_HASH_MISMATCH",
            public_message="Artifact manifest integrity check failed.",
            details={"component": "artifact_manifest"},
        )
    return manifest
