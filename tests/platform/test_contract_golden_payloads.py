from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from src.schemas.platform import PLATFORM_CONTRACTS, compute_content_hash


GOLDEN_ROOT = Path(__file__).resolve().parents[1] / "golden" / "platform" / "contracts"


def _load_cases(kind: str) -> list[tuple[Path, dict[str, Any]]]:
    return [(path, json.loads(path.read_text(encoding="utf-8"))) for path in sorted((GOLDEN_ROOT / kind).glob("*.json"))]


@pytest.mark.parametrize(("path", "case"), _load_cases("success") + _load_cases("correction"), ids=lambda value: value.name if isinstance(value, Path) else None)
def test_success_and_correction_golden_payloads(path: Path, case: dict[str, Any]) -> None:
    registration = PLATFORM_CONTRACTS.get(case["contract_id"])
    model = registration.schema_model.model_validate(case["payload"])
    serialized = model.model_dump_json(exclude_none=True)
    assert registration.schema_model.model_validate_json(serialized) == model
    if "expected_hash" in case:
        assert compute_content_hash(case["hash_input"], registration.hash_profile) == case["expected_hash"]


@pytest.mark.parametrize(("path", "case"), _load_cases("rejected"), ids=lambda value: value.name if isinstance(value, Path) else None)
def test_rejected_golden_payloads(path: Path, case: dict[str, Any]) -> None:
    registration = PLATFORM_CONTRACTS.get(case["contract_id"])
    with pytest.raises(ValidationError) as exc_info:
        registration.schema_model.model_validate(case["payload"])

    error_fields = {str(error["loc"][0]) for error in exc_info.value.errors() if error["loc"]}
    assert set(case.get("expected_error_fields", [])) <= error_fields, path.name


def test_every_registered_contract_references_existing_golden_payloads() -> None:
    for registration in PLATFORM_CONTRACTS.list():
        for relative_path in registration.golden_payloads:
            assert (Path(__file__).resolve().parents[2] / relative_path).is_file(), relative_path
