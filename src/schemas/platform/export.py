from __future__ import annotations

import json
from pathlib import Path

from .api_export import render_platform_openapi_json
from .registry import PLATFORM_CONTRACTS, ContractRegistration


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_EXPORT_ROOT = REPO_ROOT / "schemas" / "platform"


def _schema_filename(registration: ContractRegistration) -> str:
    contract_family, object_name = registration.contract_id.split("/", 1)
    return f"{contract_family}.{object_name}.schema.json"


def _json_text(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def _registration_export(registration: ContractRegistration) -> dict[str, object]:
    return {
        "business_key": registration.business_key,
        "compatibility": registration.compatibility,
        "consumers": list(registration.consumers),
        "contract_id": registration.contract_id,
        "golden_payloads": list(registration.golden_payloads),
        "hash_profile": {
            "excluded_fields": sorted(registration.hash_profile.excluded_fields),
            "profile_id": registration.hash_profile.profile_id,
            "unordered_array_paths": sorted(registration.hash_profile.unordered_array_paths),
        },
        "json_schema_file": _schema_filename(registration),
        "lineage_fields": list(registration.lineage_fields),
        "owner_module": registration.owner_module,
        "producer": registration.producer,
        "quality_semantics": list(registration.quality_semantics),
        "resource_id_field": registration.resource_id_field,
        "retention_class": registration.retention_class,
        "schema_version": registration.schema_version,
        "storage_profile": registration.storage_profile,
        "time_semantics": list(registration.time_semantics),
        "version_semantics": list(registration.version_semantics),
    }


def render_contract_exports() -> dict[str, str]:
    rendered: dict[str, str] = {}
    registry_rows: list[dict[str, object]] = []
    for registration in PLATFORM_CONTRACTS.list():
        filename = _schema_filename(registration)
        rendered[filename] = _json_text(registration.json_schema)
        registry_rows.append(_registration_export(registration))
    rendered["C-010.openapi.json"] = render_platform_openapi_json()
    rendered["contract-registry.json"] = _json_text(
        {
            "contract_registry_version": "1.0.0",
            "contracts": registry_rows,
        }
    )
    return dict(sorted(rendered.items()))


def write_contract_exports(export_root: Path = DEFAULT_EXPORT_ROOT) -> tuple[Path, ...]:
    export_root.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for relative_name, content in render_contract_exports().items():
        destination = export_root / relative_name
        destination.write_text(content, encoding="utf-8", newline="\n")
        written.append(destination)
    return tuple(written)


def check_exported_contracts(export_root: Path = DEFAULT_EXPORT_ROOT) -> list[str]:
    expected = render_contract_exports()
    drift: list[str] = []
    for relative_name, content in expected.items():
        path = export_root / relative_name
        if not path.is_file() or path.read_bytes() != content.encode("utf-8"):
            drift.append(relative_name)
    if export_root.is_dir():
        expected_names = set(expected)
        for path in export_root.glob("*.json"):
            if path.name not in expected_names:
                drift.append(path.name)
    return sorted(set(drift))
