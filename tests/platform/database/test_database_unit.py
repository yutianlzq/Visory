from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from src.repositories.platform import PlatformDatabaseError, PostgresDatabase, PostgresSettings


def _settings(tmp_path: Path) -> PostgresSettings:
    return PostgresSettings(
        host="127.0.0.1",
        port=5432,
        database="visory_test",
        username="visory_test",
        password_file=(tmp_path / "postgres-password").resolve(),
    )


def _database(tmp_path: Path) -> tuple[PostgresDatabase, MagicMock]:
    engine = MagicMock()
    database = PostgresDatabase(_settings(tmp_path), engine)
    return database, engine


def test_health_check_returns_stable_dependency_shape(tmp_path: Path) -> None:
    database, engine = _database(tmp_path)
    connection = engine.connect.return_value.__enter__.return_value
    connection.execute.return_value.scalar_one.return_value = 1

    health = database.check_health()

    assert health.is_healthy is True
    assert health.dependency == "postgresql"
    connection.execute.return_value.scalar_one.assert_called_once_with()


def test_health_check_maps_connectivity_failure_to_retryable_error(tmp_path: Path) -> None:
    database, engine = _database(tmp_path)
    engine.connect.side_effect = OperationalError(
        "SELECT 1",
        {},
        RuntimeError("postgresql+psycopg://visory:secret@example.invalid/visory"),
        connection_invalidated=True,
    )

    with pytest.raises(PlatformDatabaseError) as captured:
        database.check_health()

    error = captured.value
    assert error.error_code == "DATABASE_UNAVAILABLE"
    assert error.retryable is True
    assert error.details == {"dependency": "postgresql", "operation": "health_check"}
    assert "secret" not in str(error)
    assert "example.invalid" not in repr(error)


def test_health_check_maps_non_connectivity_failure_to_non_retryable_error(tmp_path: Path) -> None:
    database, engine = _database(tmp_path)
    engine.connect.side_effect = SQLAlchemyError("must-not-leak")

    with pytest.raises(PlatformDatabaseError) as captured:
        database.check_health()

    error = captured.value
    assert error.error_code == "DATABASE_OPERATION_FAILED"
    assert error.retryable is False
    assert error.details == {"dependency": "postgresql", "operation": "health_check"}
    assert "must-not-leak" not in str(error)


def test_transaction_yields_session_and_delegates_commit_to_boundary(tmp_path: Path) -> None:
    database, _engine = _database(tmp_path)
    session = object()
    entered = False
    exited = False

    @contextmanager
    def begin():
        nonlocal entered, exited
        entered = True
        try:
            yield session
        finally:
            exited = True

    factory = MagicMock()
    factory.begin.side_effect = begin
    database._session_factory = factory

    with database.transaction() as active_session:
        assert active_session is session
        assert entered is True
        assert exited is False

    assert exited is True
    factory.begin.assert_called_once_with()


def test_transaction_maps_sqlalchemy_failure_and_preserves_runtime_failure(tmp_path: Path) -> None:
    database, _engine = _database(tmp_path)

    @contextmanager
    def failing_begin():
        raise SQLAlchemyError("transaction-secret")
        yield

    factory = MagicMock()
    factory.begin.side_effect = failing_begin
    database._session_factory = factory

    with pytest.raises(PlatformDatabaseError) as captured:
        with database.transaction():
            pass

    assert captured.value.error_code == "DATABASE_OPERATION_FAILED"
    assert captured.value.details == {"dependency": "postgresql", "operation": "transaction"}
    assert "transaction-secret" not in str(captured.value)

    @contextmanager
    def open_begin():
        yield object()

    factory.begin.side_effect = open_begin
    with pytest.raises(RuntimeError, match="domain failure"):
        with database.transaction():
            raise RuntimeError("domain failure")


def test_close_is_idempotent_and_closed_operations_have_stable_error(tmp_path: Path) -> None:
    database, engine = _database(tmp_path)

    database.close()
    database.close()

    engine.dispose.assert_called_once_with(close=True)
    assert database.is_closed is True

    with pytest.raises(PlatformDatabaseError) as health_error:
        database.check_health()
    assert health_error.value.error_code == "DATABASE_POOL_CLOSED"
    assert health_error.value.details == {"dependency": "postgresql", "operation": "health_check"}

    with pytest.raises(PlatformDatabaseError) as transaction_error:
        with database.transaction():
            pass
    assert transaction_error.value.error_code == "DATABASE_POOL_CLOSED"
    assert transaction_error.value.details == {"dependency": "postgresql", "operation": "transaction"}
