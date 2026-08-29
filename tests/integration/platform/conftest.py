from __future__ import annotations

import os
import re
import sys
import uuid
from dataclasses import replace
from pathlib import Path
from types import ModuleType

import pytest
from sqlalchemy import text


repositories_namespace = ModuleType("src.repositories")
repositories_namespace.__path__ = [str(Path(__file__).resolve().parents[3] / "src" / "repositories")]
sys.modules["src.repositories"] = repositories_namespace

from src.repositories.platform import PostgresDatabase, PostgresSettings, create_postgres_engine


_REQUIRED_ENVIRONMENT = (
    "VISORY_TEST_POSTGRES_HOST",
    "VISORY_TEST_POSTGRES_PORT",
    "VISORY_TEST_POSTGRES_USER",
    "VISORY_TEST_POSTGRES_PASSWORD_FILE",
)
_DATABASE_NAME_PATTERN = re.compile(r"^visory_test_[0-9a-f]{20}$")


def _integration_settings() -> PostgresSettings:
    missing = [name for name in _REQUIRED_ENVIRONMENT if not os.environ.get(name)]
    if missing:
        pytest.skip("PostgreSQL integration environment is not configured")
    return PostgresSettings(
        host=os.environ["VISORY_TEST_POSTGRES_HOST"],
        port=int(os.environ["VISORY_TEST_POSTGRES_PORT"]),
        database=os.environ.get("VISORY_TEST_POSTGRES_ADMIN_DATABASE", "postgres"),
        username=os.environ["VISORY_TEST_POSTGRES_USER"],
        password_file=Path(os.environ["VISORY_TEST_POSTGRES_PASSWORD_FILE"]).resolve(),
        connect_timeout_seconds=5,
        pool_size=2,
        max_overflow=1,
        pool_timeout_seconds=5,
        pool_recycle_seconds=300,
        application_name="visory-wp0002-tests",
    )


@pytest.fixture(scope="session")
def isolated_postgres_database() -> PostgresDatabase:
    admin_settings = _integration_settings()
    database_name = f"visory_test_{uuid.uuid4().hex[:20]}"
    assert _DATABASE_NAME_PATTERN.fullmatch(database_name)
    admin_engine = create_postgres_engine(admin_settings)
    database: PostgresDatabase | None = None

    try:
        with admin_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.exec_driver_sql(f'CREATE DATABASE "{database_name}"')
        database = PostgresDatabase.from_settings(replace(admin_settings, database=database_name))
        yield database
    finally:
        if database is not None:
            database.close()
        with admin_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :database_name AND pid <> pg_backend_pid()"
                ),
                {"database_name": database_name},
            )
            connection.exec_driver_sql(f'DROP DATABASE IF EXISTS "{database_name}"')
        admin_engine.dispose(close=True)

