from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI

from api.platform.runtime import close_asset_identity_runtime, initialize_asset_identity_runtime


def _clear_postgres_environment(monkeypatch) -> None:
    for name in tuple(__import__("os").environ):
        if name.startswith("VISORY_POSTGRES_"):
            monkeypatch.delenv(name, raising=False)


def test_runtime_is_opt_in_and_preserves_legacy_app_without_postgres(monkeypatch) -> None:
    _clear_postgres_environment(monkeypatch)
    app = FastAPI()

    initialize_asset_identity_runtime(app)
    close_asset_identity_runtime(app)

    assert not hasattr(app.state, "asset_resolver_service")
    assert not hasattr(app.state, "task_control_service")
    assert not hasattr(app.state, "platform_postgres_database")


def test_runtime_rejects_invalid_secret_configuration_without_leaking_values(
    monkeypatch,
    tmp_path: Path,
    caplog,
) -> None:
    _clear_postgres_environment(monkeypatch)
    secret_value = "runtime-secret-must-not-leak"
    missing_file = (tmp_path / secret_value).resolve()
    monkeypatch.setenv("VISORY_POSTGRES_PASSWORD_FILE", str(missing_file))
    caplog.set_level(logging.ERROR, logger="api.platform.runtime")
    app = FastAPI()

    initialize_asset_identity_runtime(app)

    assert not hasattr(app.state, "asset_resolver_service")
    assert any(getattr(record, "error_code", None) == "DATABASE_SECRET_FILE_MISSING" for record in caplog.records)
    assert secret_value not in caplog.text
    assert str(missing_file) not in caplog.text


def test_runtime_owns_and_closes_its_pool(monkeypatch, tmp_path: Path) -> None:
    _clear_postgres_environment(monkeypatch)
    secret_file = (tmp_path / "postgres-password").resolve()
    secret_file.write_text("placeholder-not-production-secret\n", encoding="utf-8")
    secret_file.chmod(0o600)
    monkeypatch.setenv("VISORY_POSTGRES_PASSWORD_FILE", str(secret_file))
    app = FastAPI()

    initialize_asset_identity_runtime(app)
    database = app.state.platform_postgres_database

    assert app.state.platform_identity_runtime_owned is True
    assert hasattr(app.state, "asset_resolver_service")
    assert hasattr(app.state, "task_control_service")
    assert database.is_closed is False

    close_asset_identity_runtime(app)

    assert database.is_closed is True
    assert not hasattr(app.state, "asset_resolver_service")
    assert not hasattr(app.state, "platform_postgres_database")
