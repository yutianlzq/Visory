from __future__ import annotations

import os
import sys
from pathlib import Path
from types import ModuleType

import pytest
from sqlalchemy.engine import Engine


repositories_namespace = ModuleType("src.repositories")
repositories_namespace.__path__ = [str(Path(__file__).resolve().parents[3] / "src" / "repositories")]
sys.modules["src.repositories"] = repositories_namespace

from src.repositories.platform import (
    DatabaseConfigurationError,
    DatabaseSecretError,
    PlatformDatabaseError,
    PostgresSettings,
    build_postgres_url,
    create_postgres_engine,
    read_secret_file,
)


def _environment(secret_path: Path) -> dict[str, str]:
    return {
        "VISORY_POSTGRES_HOST": "127.0.0.1",
        "VISORY_POSTGRES_PORT": "5432",
        "VISORY_POSTGRES_DATABASE": "visory",
        "VISORY_POSTGRES_USER": "visory",
        "VISORY_POSTGRES_PASSWORD_FILE": str(secret_path),
        "VISORY_POSTGRES_CONNECT_TIMEOUT_SECONDS": "4",
        "VISORY_POSTGRES_POOL_SIZE": "3",
        "VISORY_POSTGRES_MAX_OVERFLOW": "2",
        "VISORY_POSTGRES_POOL_TIMEOUT_SECONDS": "7",
        "VISORY_POSTGRES_POOL_RECYCLE_SECONDS": "900",
    }


def test_settings_keep_only_secret_file_reference_without_reading_it(tmp_path: Path, monkeypatch) -> None:
    secret_path = (tmp_path / "postgres-password").resolve()

    def fail_read(_self: Path) -> bytes:
        raise AssertionError("settings construction must not read secrets")

    monkeypatch.setattr(Path, "read_bytes", fail_read)
    settings = PostgresSettings.from_environment(_environment(secret_path))

    assert settings.password_file == secret_path
    assert not hasattr(settings, "password")
    assert settings.pool_size == 3
    assert settings.max_overflow == 2


def test_settings_reject_raw_password_environment_even_with_file_reference(tmp_path: Path) -> None:
    environment = _environment((tmp_path / "postgres-password").resolve())
    environment["VISORY_POSTGRES_PASSWORD"] = "must-not-be-accepted"

    with pytest.raises(DatabaseConfigurationError) as captured:
        PostgresSettings.from_environment(environment)

    assert captured.value.error_code == "DATABASE_RAW_SECRET_FORBIDDEN"
    assert captured.value.retryable is False
    assert "must-not-be-accepted" not in str(captured.value)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("VISORY_POSTGRES_PORT", "0"),
        ("VISORY_POSTGRES_PORT", "65536"),
        ("VISORY_POSTGRES_POOL_SIZE", "0"),
        ("VISORY_POSTGRES_MAX_OVERFLOW", "-1"),
        ("VISORY_POSTGRES_CONNECT_TIMEOUT_SECONDS", "invalid"),
    ],
)
def test_settings_reject_invalid_numeric_values(tmp_path: Path, name: str, value: str) -> None:
    environment = _environment((tmp_path / "postgres-password").resolve())
    environment[name] = value

    with pytest.raises(DatabaseConfigurationError) as captured:
        PostgresSettings.from_environment(environment)

    assert captured.value.error_code == "DATABASE_CONFIG_INVALID"
    assert captured.value.retryable is False
    assert captured.value.details == {"setting": name}


def test_settings_require_an_absolute_secret_file_reference(tmp_path: Path) -> None:
    environment = _environment((tmp_path / "postgres-password").resolve())
    environment["VISORY_POSTGRES_PASSWORD_FILE"] = "relative/postgres-password"

    with pytest.raises(DatabaseConfigurationError) as captured:
        PostgresSettings.from_environment(environment)

    assert captured.value.error_code == "DATABASE_CONFIG_INVALID"
    assert captured.value.details == {"setting": "VISORY_POSTGRES_PASSWORD_FILE"}


def test_missing_secret_file_is_safely_rejected(tmp_path: Path) -> None:
    missing = (tmp_path / "missing-password").resolve()

    with pytest.raises(DatabaseSecretError) as captured:
        read_secret_file(missing)

    error = captured.value
    assert error.error_code == "DATABASE_SECRET_FILE_MISSING"
    assert error.retryable is False
    assert str(missing) not in str(error)
    assert str(missing) not in repr(error)


def test_unreadable_secret_file_is_safely_rejected(tmp_path: Path, monkeypatch) -> None:
    secret_path = (tmp_path / "postgres-password").resolve()
    secret_path.write_text("placeholder", encoding="utf-8")

    def deny_read(_self: Path) -> bytes:
        raise PermissionError("denied /private/secret/path")

    monkeypatch.setattr(Path, "read_bytes", deny_read)
    with pytest.raises(DatabaseSecretError) as captured:
        read_secret_file(secret_path)

    error = captured.value
    assert error.error_code == "DATABASE_SECRET_FILE_UNREADABLE"
    assert error.retryable is False
    assert "denied" not in str(error)
    assert str(secret_path) not in str(error)


@pytest.mark.parametrize(
    "payload",
    [
        b"",
        b"   ",
        b" leading",
        b"trailing ",
        b"line-one\nline-two",
        b"contains\x00nul",
        b"\xff\xfe",
    ],
)
def test_malformed_secret_file_is_safely_rejected(tmp_path: Path, payload: bytes) -> None:
    secret_path = (tmp_path / "postgres-password").resolve()
    secret_path.write_bytes(payload)
    if os.name != "nt":
        secret_path.chmod(0o600)

    with pytest.raises(DatabaseSecretError) as captured:
        read_secret_file(secret_path)

    assert captured.value.error_code == "DATABASE_SECRET_FILE_INVALID"
    assert captured.value.retryable is False
    assert payload.decode("utf-8", errors="ignore") not in str(captured.value)


def test_secret_file_accepts_one_terminal_newline(tmp_path: Path) -> None:
    secret_path = (tmp_path / "postgres-password").resolve()
    secret_path.write_bytes(b"placeholder-secret\r\n")
    if os.name != "nt":
        secret_path.chmod(0o600)

    assert read_secret_file(secret_path) == "placeholder-secret"


@pytest.mark.skipif(os.name == "nt", reason="POSIX mode bits are not authoritative on Windows")
def test_secret_file_rejects_group_or_other_permissions(tmp_path: Path) -> None:
    secret_path = (tmp_path / "postgres-password").resolve()
    secret_path.write_text("placeholder-secret", encoding="utf-8")
    secret_path.chmod(0o640)

    with pytest.raises(DatabaseSecretError) as captured:
        read_secret_file(secret_path)

    assert captured.value.error_code == "DATABASE_SECRET_FILE_PERMISSIONS"
    assert captured.value.retryable is False


def test_postgres_url_and_engine_never_render_password(tmp_path: Path) -> None:
    secret_path = (tmp_path / "postgres-password").resolve()
    settings = PostgresSettings.from_environment(_environment(secret_path))
    password = "sensitive:p@ssword"

    url = build_postgres_url(settings, password)
    engine = create_postgres_engine(settings, password=password)
    try:
        assert url.drivername == "postgresql+psycopg"
        assert isinstance(engine, Engine)
        assert engine.dialect.name == "postgresql"
        assert engine.dialect.driver == "psycopg"
        assert password not in str(url)
        assert password not in repr(url)
        assert password not in str(engine.url)
        assert password not in repr(engine.url)
        assert engine.pool.size() == 3
        assert engine.pool._max_overflow == 2
    finally:
        engine.dispose(close=True)


def test_platform_database_error_has_stable_public_shape_without_cause_leakage() -> None:
    secret = "database-password-must-not-leak"
    error = PlatformDatabaseError(
        error_code="DATABASE_UNAVAILABLE",
        public_message="PostgreSQL is temporarily unavailable.",
        retryable=True,
        details={"dependency": "postgresql"},
        cause=RuntimeError(f"connection failed with {secret}"),
    )

    assert error.error_code == "DATABASE_UNAVAILABLE"
    assert error.public_message == "PostgreSQL is temporarily unavailable."
    assert error.retryable is True
    assert error.details == {"dependency": "postgresql"}
    assert isinstance(error.cause, RuntimeError)
    assert secret not in str(error)
    assert secret not in repr(error)

