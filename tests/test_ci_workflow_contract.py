# -*- coding: utf-8 -*-
"""Contracts for the intentionally minimal Visory baseline CI."""

from __future__ import annotations

import re
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"
CI_PATH = WORKFLOW_DIR / "ci.yml"


def _workflow() -> dict:
    return yaml.load(CI_PATH.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def _run_text(job: dict) -> str:
    return "\n".join(
        str(step.get("run", ""))
        for step in job.get("steps", [])
        if isinstance(step, dict)
    )


def test_visory_ci_has_only_safe_validation_triggers_and_read_permissions() -> None:
    raw = CI_PATH.read_text(encoding="utf-8")
    ci = _workflow()

    assert set(ci["on"]) == {"pull_request", "workflow_dispatch"}
    assert ci["permissions"] == {"contents": "read"}
    assert set(ci["jobs"]) == {"governance", "backend", "web"}
    assert "secrets." not in raw.lower()
    assert not re.search(r"(?m)^  (?:push|schedule|release|deployment):", raw)

    for job in ci["jobs"].values():
        checkout = next(
            step
            for step in job["steps"]
            if str(step.get("uses", "")).startswith("actions/checkout@")
        )
        assert checkout["with"]["persist-credentials"] == "false"


def test_visory_ci_runs_governance_backend_and_web_baseline_gates() -> None:
    ci = _workflow()
    governance = _run_text(ci["jobs"]["governance"])
    backend = _run_text(ci["jobs"]["backend"])
    web = _run_text(ci["jobs"]["web"])

    assert "python scripts/check_ai_assets.py" in governance
    assert "python scripts/check_visory_baseline.py" in governance
    assert "python -m pip install -r .github/requirements-ci.txt" in backend
    assert "bash scripts/ci_gate.sh" in backend
    assert ci["jobs"]["web"]["defaults"]["run"]["working-directory"] == "apps/dsa-web"
    assert "npm ci" in web
    assert "npm run lint" in web
    assert "npm run build" in web

    active_workflows = sorted(path.name for path in WORKFLOW_DIR.glob("*.y*ml"))
    assert active_workflows == ["ci.yml"]
    assert (REPO_ROOT / "docs/upstream/daily_stock_analysis/workflows/ci.yml").is_file()
