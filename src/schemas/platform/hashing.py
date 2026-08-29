from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import Field

from .base import PlatformContractModel


_CONTENT_HASH_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")


class HashProfile(PlatformContractModel):
    profile_id: str = Field(pattern=r"^[a-z][a-z0-9_]*_[0-9]+\.[0-9]+\.[0-9]+$")
    excluded_fields: frozenset[str] = frozenset({"content_hash"})
    unordered_array_paths: frozenset[str] = frozenset()


DEFAULT_HASH_PROFILE = HashProfile(profile_id="platform_canonical_json_1.0.0")


class ContentHashValue(PlatformContractModel):
    hash_algorithm: str = Field(default="sha256", pattern=r"^sha256$")
    content_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


def _path_matches(path: tuple[str, ...], configured_paths: frozenset[str]) -> bool:
    return ".".join(path) in configured_paths


def _normalize(value: Any, profile: HashProfile, path: tuple[str, ...]) -> Any:
    if isinstance(value, PlatformContractModel):
        value = value.model_dump(mode="python")
    if isinstance(value, Enum):
        return value.value
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        raise TypeError("float values are forbidden in deterministic contract hashes")
    if isinstance(value, Decimal):
        return {"$decimal": format(value, "f")}
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise TypeError("naive datetime is forbidden in deterministic contract hashes")
        utc_value = value.astimezone(timezone.utc)
        return {"$datetime": utc_value.isoformat(timespec="microseconds").replace("+00:00", "Z")}
    if isinstance(value, date):
        return {"$date": value.isoformat()}
    if isinstance(value, UUID):
        return {"$uuid": str(value)}
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key in sorted(value):
            if not isinstance(key, str):
                raise TypeError("deterministic contract hash mappings require string keys")
            if key in profile.excluded_fields:
                continue
            normalized[key] = _normalize(value[key], profile, (*path, key))
        return normalized
    if isinstance(value, (list, tuple)):
        normalized_items = [_normalize(item, profile, (*path, str(index))) for index, item in enumerate(value)]
        if _path_matches(path, profile.unordered_array_paths):
            normalized_items.sort(
                key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            )
        return normalized_items
    if isinstance(value, (set, frozenset)):
        raise TypeError("set values require an explicit ordered representation")
    raise TypeError(f"unsupported value in deterministic contract hash: {type(value).__name__}")


def canonical_json_bytes(value: Any, profile: HashProfile | None = None) -> bytes:
    active_profile = profile or DEFAULT_HASH_PROFILE
    normalized = _normalize(value, active_profile, ())
    return json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def compute_content_hash(value: Any, profile: HashProfile | None = None) -> str:
    digest = hashlib.sha256(canonical_json_bytes(value, profile)).hexdigest()
    result = f"sha256:{digest}"
    if not _CONTENT_HASH_PATTERN.fullmatch(result):
        raise AssertionError("sha256 output was not canonical")
    return result
