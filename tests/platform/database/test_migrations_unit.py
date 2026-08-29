from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

from src.repositories.platform import (
    PlatformDatabaseError,
    downgrade_database,
    get_migration_status,
    upgrade_database,
)
from src.repositories.platform import migrations


@contextmanager
def _connection_context(connection: object):
    yield connection


def test_alembic_configuration_uses_repository_migration_tree() -> None:
    config = migrations._alembic_config()

    assert config.config_file_name == str(migrations._REPOSITORY_ROOT / "alembic.ini")
    assert config.get_main_option("script_location") == (migrations._REPOSITORY_ROOT / "migrations").as_posix()


@pytest.mark.parametrize(
    ("function", "command_name", "default_target"),
    [
        (upgrade_database, "upgrade", "head"),
        (downgrade_database, "downgrade", "base"),
    ],
)
def test_migration_commands_use_the_supplied_engine_connection(function, command_name: str, default_target: str) -> None:
    engine = MagicMock()
    connection = object()
    engine.begin.side_effect = lambda: _connection_context(connection)

    with patch.object(migrations.command, command_name) as command_call:
        function(engine)

    config = command_call.call_args.args[0]
    assert config.attributes["connection"] is connection
    assert command_call.call_args.args[1] == default_target


@pytest.mark.parametrize(
    ("function", "operation", "target"),
    [
        (upgrade_database, "upgrade", "head"),
        (downgrade_database, "downgrade", "base"),
    ],
)
def test_migration_command_failures_have_stable_sanitized_error(function, operation: str, target: str) -> None:
    engine = MagicMock()
    engine.begin.side_effect = RuntimeError("postgresql://user:secret@example.invalid/visory")

    with pytest.raises(PlatformDatabaseError) as captured:
        function(engine, target)

    error = captured.value
    assert error.error_code == "DATABASE_MIGRATION_FAILED"
    assert error.retryable is False
    assert error.details == {"dependency": "postgresql", "operation": operation, "target": target}
    assert "secret" not in str(error)
    assert "example.invalid" not in repr(error)


def test_migration_commands_do_not_mask_process_control_exceptions() -> None:
    engine = MagicMock()
    engine.begin.side_effect = KeyboardInterrupt()

    with pytest.raises(KeyboardInterrupt):
        upgrade_database(engine)

    engine.begin.side_effect = SystemExit(2)
    with pytest.raises(SystemExit) as captured:
        downgrade_database(engine)
    assert captured.value.code == 2


def test_migration_status_reports_current_revision_and_head() -> None:
    engine = MagicMock()
    connection = object()
    engine.connect.side_effect = lambda: _connection_context(connection)
    script = MagicMock()
    script.get_current_head.return_value = "0001_wp0002_baseline"
    context = MagicMock()
    context.get_current_revision.return_value = "0001_wp0002_baseline"

    with (
        patch.object(migrations.ScriptDirectory, "from_config", return_value=script),
        patch.object(migrations.MigrationContext, "configure", return_value=context) as configure,
    ):
        status = get_migration_status(engine)

    assert status.current_revision == "0001_wp0002_baseline"
    assert status.head_revision == "0001_wp0002_baseline"
    assert status.is_at_head is True
    configure.assert_called_once_with(connection)


def test_migration_status_supports_empty_database_and_rejects_missing_history_head() -> None:
    engine = MagicMock()
    engine.connect.side_effect = lambda: _connection_context(object())
    script = MagicMock()
    script.get_current_head.return_value = "0001_wp0002_baseline"
    context = MagicMock()
    context.get_current_revision.return_value = None

    with (
        patch.object(migrations.ScriptDirectory, "from_config", return_value=script),
        patch.object(migrations.MigrationContext, "configure", return_value=context),
    ):
        status = get_migration_status(engine)

    assert status.current_revision is None
    assert status.is_at_head is False

    script.get_current_head.return_value = None
    with (
        patch.object(migrations.ScriptDirectory, "from_config", return_value=script),
        pytest.raises(PlatformDatabaseError) as captured,
    ):
        get_migration_status(engine)

    assert captured.value.error_code == "DATABASE_MIGRATION_FAILED"
    assert captured.value.details == {"dependency": "postgresql", "operation": "status", "target": "head"}
