from __future__ import annotations

import json
from pathlib import Path

from src.schemas.platform.api_export import (
    FRONTEND_TYPE_EXPORT,
    check_frontend_type_export,
    render_frontend_types,
    render_platform_openapi,
    render_platform_openapi_json,
    write_frontend_type_export,
)
from src.schemas.platform.export import check_exported_contracts, render_contract_exports


REPO_ROOT = Path(__file__).resolve().parents[3]
SCHEMA_EXPORT_ROOT = REPO_ROOT / "schemas" / "platform"


def test_c010_openapi_contains_examples_and_stable_components() -> None:
    spec = render_platform_openapi()

    assert spec["openapi"] == "3.1.0"
    assert spec["info"]["version"] == "1.0.0"
    assert spec["paths"] == {}
    schemas = spec["components"]["schemas"]
    assert set(schemas) == {
        "PlatformAPIError",
        "PlatformErrorEnvelope",
        "PlatformListEnvelope",
        "PlatformPage",
        "PlatformResponseMeta",
        "PlatformSuccessEnvelope",
    }
    assert schemas["PlatformSuccessEnvelope"]["examples"]
    assert schemas["PlatformErrorEnvelope"]["examples"]
    assert schemas["PlatformListEnvelope"]["examples"]


def test_openapi_and_frontend_types_are_byte_deterministic() -> None:
    assert render_platform_openapi_json() == render_platform_openapi_json()
    assert render_frontend_types() == render_frontend_types()
    assert render_platform_openapi_json().endswith("\n")
    assert render_frontend_types().endswith("\n")


def test_checked_in_c010_openapi_and_frontend_types_match_source_models() -> None:
    assert "C-010.openapi.json" in render_contract_exports()
    assert check_exported_contracts(SCHEMA_EXPORT_ROOT) == []
    assert check_frontend_type_export(FRONTEND_TYPE_EXPORT) is False


def test_frontend_type_drift_is_detected(tmp_path: Path) -> None:
    target = tmp_path / "platform-api.ts"
    write_frontend_type_export(target)
    assert check_frontend_type_export(target) is False

    target.write_text(target.read_text(encoding="utf-8") + "// manual drift\n", encoding="utf-8")
    assert check_frontend_type_export(target) is True


def test_generated_frontend_types_are_strict_and_cover_c010_fields() -> None:
    generated = render_frontend_types()

    assert "DO NOT EDIT" in generated
    assert "export interface PlatformResponseMeta" in generated
    assert "readonly request_id: string;" in generated
    assert 'readonly schema_version: "1.0.0";' in generated
    assert "readonly generated_at: string;" in generated
    assert "readonly data_snapshot_id: string | null;" in generated
    assert "readonly warnings: ReadonlyArray<string>;" in generated
    assert "export interface PlatformPage" in generated
    assert "export interface PlatformErrorEnvelope" in generated
    assert ": any" not in generated
    assert "<any>" not in generated


def test_exported_openapi_json_matches_rendered_structure() -> None:
    exported = json.loads((SCHEMA_EXPORT_ROOT / "C-010.openapi.json").read_text(encoding="utf-8"))
    assert exported == render_platform_openapi()
