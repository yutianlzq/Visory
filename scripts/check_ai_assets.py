#!/usr/bin/env python3

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
AGENTS = ROOT / "AGENTS.md"
CLAUDE = ROOT / "CLAUDE.md"

REQUIRED_AGENT_RULES = (
    "每个实现任务只推进一个 Work Package",
    "最小文档集",
    "`upstream/` 与 `references/`",
    "Legacy SQLite",
    "内存 Task Queue",
    "不得把 Goal、WP 或能力标记为 `VERIFIED`",
)

REQUIRED_GITIGNORE_RULES = (
    "references/repos/",
    "upstream/daily_stock_analysis/",
)


def fail(message: str) -> None:
    print(f"[ai-assets] ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def check_canonical_rules() -> None:
    if not AGENTS.is_file():
        fail("canonical AGENTS.md is missing")
    content = AGENTS.read_text(encoding="utf-8")
    for rule in REQUIRED_AGENT_RULES:
        if rule not in content:
            fail(f"AGENTS.md is missing required rule text: {rule!r}")


def check_claude_entry() -> None:
    if not CLAUDE.exists():
        fail("CLAUDE.md is missing or its link target is unavailable")
    if CLAUDE.is_symlink():
        if CLAUDE.readlink() != Path("AGENTS.md"):
            fail(f"CLAUDE.md must point to AGENTS.md, found: {CLAUDE.readlink()}")
        return

    content = CLAUDE.read_text(encoding="utf-8").strip()
    if "AGENTS.md" not in content:
        fail("regular CLAUDE.md must direct readers to AGENTS.md")
    if len(content.splitlines()) > 12:
        fail("regular CLAUDE.md must remain a short pointer, not duplicate rules")


def check_ignore_boundaries() -> None:
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    for rule in REQUIRED_GITIGNORE_RULES:
        if rule not in gitignore:
            fail(f".gitignore is missing external source boundary: {rule}")

    result = subprocess.run(
        ["git", "ls-files", "--", "references/repos", "upstream"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    tracked = [line for line in result.stdout.splitlines() if line.strip()]
    if tracked:
        fail(f"external source files are tracked: {tracked[0]}")


def main() -> None:
    check_canonical_rules()
    check_claude_entry()
    check_ignore_boundaries()
    print("[ai-assets] OK")


if __name__ == "__main__":
    main()
