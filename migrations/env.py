from __future__ import annotations

from logging.config import fileConfig

from alembic import context

from src.repositories.platform import PostgresDatabase, PostgresSettings


config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = None


def _run_with_connection(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_offline() -> None:
    raise RuntimeError("offline migrations are not supported; use an isolated PostgreSQL connection")


def run_migrations_online() -> None:
    supplied_connection = config.attributes.get("connection")
    if supplied_connection is not None:
        _run_with_connection(supplied_connection)
        return

    database = PostgresDatabase.from_settings(PostgresSettings.from_environment())
    try:
        with database.engine.connect() as connection:
            _run_with_connection(connection)
    finally:
        database.close()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
