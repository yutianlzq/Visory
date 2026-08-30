from __future__ import annotations

from pathlib import Path


def test_wp0103_migration_declares_expected_revision_and_tables() -> None:
    source = Path("migrations/versions/0004_wp0103_durable_task_control_plane.py").read_text(encoding="utf-8")
    assert 'revision: str = "0004_wp0103_durable_task_control_plane"' in source
    assert 'down_revision: str | Sequence[str] | None = "0003_wp0102_artifact_registry"' in source
    for table_name in (
        "platform_task",
        "task_attempt",
        "task_state_event",
        "task_checkpoint",
        "task_command_idempotency",
    ):
        assert f'"{table_name}"' in source
    assert "SKIP LOCKED" not in source
