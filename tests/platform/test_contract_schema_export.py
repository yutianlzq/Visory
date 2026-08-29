from __future__ import annotations

from pathlib import Path

from src.schemas.platform.export import (
    check_exported_contracts,
    render_contract_exports,
    write_contract_exports,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
EXPORT_ROOT = REPO_ROOT / "schemas" / "platform"


def test_rendered_contract_exports_are_byte_stable() -> None:
    first = render_contract_exports()
    second = render_contract_exports()
    assert first == second
    assert first
    assert all(content.endswith("\n") for content in first.values())


def test_checked_in_contract_exports_match_runtime_models() -> None:
    assert check_exported_contracts(EXPORT_ROOT) == []


def test_export_check_detects_byte_level_line_ending_drift(tmp_path: Path) -> None:
    write_contract_exports(tmp_path)
    target = next(tmp_path.glob("*.schema.json"))
    content = target.read_bytes()
    target.write_bytes(content.replace(b"\n", b"\r\n"))

    assert target.name in check_exported_contracts(tmp_path)
