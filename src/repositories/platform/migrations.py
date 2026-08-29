from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine

from .errors import PlatformDatabaseError


_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True, slots=True)
class MigrationStatus:
    current_revision: str | None
    head_revision: str
    is_at_head: bool


def _alembic_config() -> Config:
    config = Config(str(_REPOSITORY_ROOT / "alembic.ini"))
    config.set_main_option("script_location", (_REPOSITORY_ROOT / "migrations").as_posix())
    return config


def _migration_error(exc: Exception, operation: str, target: str) -> PlatformDatabaseError:
    return PlatformDatabaseError(
        error_code="DATABASE_MIGRATION_FAILED",
        public_message="PostgreSQL migration failed.",
        retryable=False,
        details={"dependency": "postgresql", "operation": operation, "target": target},
        cause=exc,
    )


def upgrade_database(engine: Engine, target: str = "head") -> None:
    config = _alembic_config()
    try:
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, target)
    except Exception as exc:
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        raise _migration_error(exc, "upgrade", target) from exc


def downgrade_database(engine: Engine, target: str = "base") -> None:
    config = _alembic_config()
    try:
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.downgrade(config, target)
    except Exception as exc:
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        raise _migration_error(exc, "downgrade", target) from exc


def get_migration_status(engine: Engine) -> MigrationStatus:
    config = _alembic_config()
    try:
        script = ScriptDirectory.from_config(config)
        head_revision = script.get_current_head()
        if head_revision is None:
            raise RuntimeError("Alembic migration history has no head")
        with engine.connect() as connection:
            current_revision = MigrationContext.configure(connection).get_current_revision()
    except Exception as exc:
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        raise _migration_error(exc, "status", "head") from exc
    return MigrationStatus(
        current_revision=current_revision,
        head_revision=head_revision,
        is_at_head=current_revision == head_revision,
    )
