#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parent.parent
REQUIRED_RUNTIME_PATHS = (
    "main.py",
    "server.py",
    "src",
    "api",
    "data_provider",
    "apps/dsa-web",
    "tests",
    "requirements.txt",
)
LICENSE_NOTICE_PATHS = (
    "third_party/licenses/daily_stock_analysis-MIT.txt",
    "third_party/NOTICE.md",
)
EXTERNAL_SOURCE_PATHS = ("references/repos", "upstream")
UNSAFE_WORKFLOW_KEYS = ("push", "schedule", "release", "deployment")
MARKDOWN_LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")


def fail(message: str) -> None:
    print(f"[baseline] ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def check_required_paths() -> int:
    missing = [path for path in REQUIRED_RUNTIME_PATHS if not (ROOT / path).exists()]
    if missing:
        fail(f"required runtime paths missing: {', '.join(missing)}")
    return len(REQUIRED_RUNTIME_PATHS)


def check_reference_manifest() -> int:
    manifest = ROOT / "references" / "manifest.yaml"
    project_count = len(
        re.findall(r"(?m)^- id:\s+\S+\s*$", manifest.read_text(encoding="utf-8"))
    )
    if project_count != 10:
        fail(f"reference project count is {project_count}, expected 10")
    return project_count


def check_external_sources_untracked() -> int:
    result = subprocess.run(
        ["git", "ls-files", "--", *EXTERNAL_SOURCE_PATHS],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    tracked = [line for line in result.stdout.splitlines() if line.strip()]
    if tracked:
        fail(f"external source file is tracked: {tracked[0]}")
    return 0


def check_license_notice() -> int:
    missing = [path for path in LICENSE_NOTICE_PATHS if not (ROOT / path).is_file()]
    if missing:
        fail(f"license/notice files missing: {', '.join(missing)}")
    return len(LICENSE_NOTICE_PATHS)


def workflow_on_block(text: str) -> str:
    match = re.search(r"(?m)^on:\s*\n(?P<body>(?:^[ \t]+.*\n?)*)", text)
    if not match:
        fail("workflow does not contain a block-style top-level on section")
    return match.group("body")


def check_workflows() -> int:
    workflow_dir = ROOT / ".github" / "workflows"
    workflows = sorted((*workflow_dir.glob("*.yml"), *workflow_dir.glob("*.yaml")))
    if not workflows:
        fail("no validation workflow found")

    for workflow in workflows:
        text = workflow.read_text(encoding="utf-8")
        on_block = workflow_on_block(text)
        triggers = set(re.findall(r"(?m)^  ([a-zA-Z_]+):", on_block))
        unsupported = triggers - {"pull_request", "workflow_dispatch"}
        if unsupported:
            fail(f"unsafe trigger in {workflow.relative_to(ROOT)}: {sorted(unsupported)}")
        if "pull_request" not in triggers or "workflow_dispatch" not in triggers:
            fail(f"workflow must support pull_request and workflow_dispatch: {workflow.relative_to(ROOT)}")
        for key in UNSAFE_WORKFLOW_KEYS:
            if re.search(rf"(?m)^  {re.escape(key)}:", on_block):
                fail(f"unsafe workflow trigger {key!r}: {workflow.relative_to(ROOT)}")
        if not re.search(r"(?ms)^permissions:\s*\n  contents:\s*read\s*$", text):
            fail(f"workflow permissions must be contents: read: {workflow.relative_to(ROOT)}")
        if re.search(r"\bsecrets\s*\.", text, re.IGNORECASE):
            fail(f"workflow reads a secret: {workflow.relative_to(ROOT)}")
        if re.search(r"(?i)\b(push|publish|deploy|release)\b", "\n".join(
            line for line in text.splitlines() if line.lstrip().startswith(("run:", "uses:"))
        )):
            fail(f"workflow contains publish/deploy command: {workflow.relative_to(ROOT)}")
    return len(workflows)


def normalize_link(raw_target: str) -> str | None:
    target = raw_target.strip()
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1]
    if " " in target and not target.startswith(("./", "../", "/")):
        target = target.split(maxsplit=1)[0]
    lowered = target.lower()
    if not target or target.startswith("#") or lowered.startswith(
        ("http://", "https://", "mailto:", "data:", "javascript:")
    ):
        return None
    target = unquote(target.split("#", 1)[0].split("?", 1)[0])
    return target or None


def check_markdown_links() -> int:
    markdown_files = sorted(
        path
        for base in (ROOT, ROOT / "docs")
        for path in base.glob("*.md")
    )
    markdown_files.extend(sorted((ROOT / "docs").rglob("*.md")))
    markdown_files = sorted(set(markdown_files))
    broken: list[str] = []
    checked = 0
    for markdown in markdown_files:
        text = markdown.read_text(encoding="utf-8")
        for raw_target in MARKDOWN_LINK.findall(text):
            target = normalize_link(raw_target)
            if target is None or "{{" in target or "${" in target:
                continue
            destination = (
                ROOT / target.lstrip("/")
                if target.startswith("/")
                else markdown.parent / target
            )
            checked += 1
            if not destination.resolve().exists():
                broken.append(f"{markdown.relative_to(ROOT)} -> {target}")
    if broken:
        sample = "\n  ".join(broken[:100])
        fail(f"broken relative Markdown links ({len(broken)}):\n  {sample}")
    return checked


def check_high_confidence_secrets() -> int:
    patterns = {
        "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
        "GitHub token": re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36,}\b"),
        "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    }
    excluded_parts = {".git", "node_modules", "dist", "build", "upstream", "repos"}
    findings: list[str] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or any(part in excluded_parts for part in path.parts):
            continue
        if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".ico", ".woff", ".woff2"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for name, pattern in patterns.items():
            if pattern.search(text):
                findings.append(f"{name}: {path.relative_to(ROOT)}")
    if findings:
        fail(f"high-confidence secret findings: {findings[:10]}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-links", action="store_true")
    args = parser.parse_args()

    summary = {
        "required_runtime_paths": check_required_paths(),
        "reference_projects": check_reference_manifest(),
        "tracked_external_reference_files": check_external_sources_untracked(),
        "license_notice": check_license_notice(),
        "enabled_validation_workflows": check_workflows(),
        "imported_secrets": check_high_confidence_secrets(),
    }
    if not args.skip_links:
        summary["checked_relative_links"] = check_markdown_links()
        summary["broken_relative_links"] = 0
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
