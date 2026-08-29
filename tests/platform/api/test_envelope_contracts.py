from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from src.schemas.platform.api import (
    PlatformErrorEnvelope,
    PlatformListEnvelope,
    PlatformSuccessEnvelope,
)


GOLDEN_ROOT = Path(__file__).resolve().parents[2] / "golden" / "platform" / "api"
MODEL_BY_NAME = {
    "PlatformSuccessEnvelope": PlatformSuccessEnvelope,
    "PlatformListEnvelope": PlatformListEnvelope,
    "PlatformErrorEnvelope": PlatformErrorEnvelope,
}


def _load_cases(kind: str) -> list[tuple[Path, dict[str, Any]]]:
    return [
        (path, json.loads(path.read_text(encoding="utf-8")))
        for path in sorted((GOLDEN_ROOT / kind).glob("*.json"))
    ]


@pytest.mark.parametrize(
    ("path", "case"),
    _load_cases("success"),
    ids=lambda value: value.name if isinstance(value, Path) else None,
)
def test_c010_success_golden_payloads(path: Path, case: dict[str, Any]) -> None:
    model_type = MODEL_BY_NAME[case["model"]]
    model = model_type.model_validate(case["payload"])

    assert model_type.model_validate_json(model.model_dump_json()) == model, path.name


@pytest.mark.parametrize(
    ("path", "case"),
    _load_cases("rejected"),
    ids=lambda value: value.name if isinstance(value, Path) else None,
)
def test_c010_rejected_payloads(path: Path, case: dict[str, Any]) -> None:
    model_type = MODEL_BY_NAME[case["model"]]

    with pytest.raises(ValidationError) as exc_info:
        model_type.model_validate(case["payload"])

    error_locations = {".".join(str(part) for part in error["loc"]) for error in exc_info.value.errors()}
    assert set(case["expected_error_locations"]) <= error_locations, path.name


def test_success_envelope_exposes_all_required_c010_fields() -> None:
    schema = PlatformSuccessEnvelope.model_json_schema()

    assert set(schema["required"]) == {"data", "meta"}
    meta = schema["$defs"]["PlatformResponseMeta"]
    assert set(meta["required"]) == {
        "request_id",
        "schema_version",
        "generated_at",
        "data_snapshot_id",
        "warnings",
    }


def test_list_envelope_requires_page_contract() -> None:
    schema = PlatformListEnvelope.model_json_schema()

    assert set(schema["required"]) == {"data", "meta", "page"}
    page = schema["$defs"]["PlatformPage"]
    assert set(page["required"]) == {"cursor", "next_cursor", "limit", "has_more"}
    assert page["properties"]["limit"]["minimum"] == 1
