from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from sqlalchemy import Engine, URL, create_engine, text
from sqlalchemy.exc import DBAPIError, InterfaceError, OperationalError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from .errors import PlatformDatabaseError
from .settings import PostgresSettings, read_secret_file


@dataclass(frozen=True, slots=True)
class DatabaseHealth:
    is_healthy: bool
    dependency: str


def build_postgres_url(settings: PostgresSettings, password: str) -> URL:
    return URL.create(
        drivername="postgresql+psycopg",
        username=settings.username,
        password=password,
        host=settings.host,
        port=settings.port,
        database=settings.database,
    )


def create_postgres_engine(settings: PostgresSettings, *, password: str | None = None) -> Engine:
    active_password = read_secret_file(settings.password_file) if password is None else password
    return create_engine(
        build_postgres_url(settings, active_password),
        pool_pre_ping=True,
        pool_size=settings.pool_size,
        max_overflow=settings.max_overflow,
        pool_timeout=settings.pool_timeout_seconds,
        pool_recycle=settings.pool_recycle_seconds,
        pool_use_lifo=True,
        connect_args={
            "connect_timeout": settings.connect_timeout_seconds,
            "application_name": settings.application_name,
        },
    )


def _database_error(
    exc: SQLAlchemyError,
    *,
    operation: str,
) -> PlatformDatabaseError:
    is_connectivity_error = isinstance(exc, (OperationalError, InterfaceError)) or (
        isinstance(exc, DBAPIError) and exc.connection_invalidated
    )
    if is_connectivity_error:
        return PlatformDatabaseError(
            error_code="DATABASE_UNAVAILABLE",
            public_message="PostgreSQL is temporarily unavailable.",
            retryable=True,
            details={"dependency": "postgresql", "operation": operation},
            cause=exc,
        )
    return PlatformDatabaseError(
        error_code="DATABASE_OPERATION_FAILED",
        public_message="PostgreSQL operation failed.",
        retryable=False,
        details={"dependency": "postgresql", "operation": operation},
        cause=exc,
    )


class PostgresDatabase:
    """Owns the single synchronous PostgreSQL Engine and transaction factory."""

    def __init__(self, settings: PostgresSettings, engine: Engine) -> None:
        self.settings = settings
        self.engine = engine
        self._session_factory = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
        self._is_closed = False

    @classmethod
    def from_settings(cls, settings: PostgresSettings) -> "PostgresDatabase":
        return cls(settings, create_postgres_engine(settings))

    @property
    def is_closed(self) -> bool:
        return self._is_closed

    def _ensure_open(self, operation: str) -> None:
        if self._is_closed:
            raise PlatformDatabaseError(
                error_code="DATABASE_POOL_CLOSED",
                public_message="PostgreSQL connection pool is closed.",
                retryable=False,
                details={"dependency": "postgresql", "operation": operation},
            )

    def check_health(self) -> DatabaseHealth:
        self._ensure_open("health_check")
        try:
            with self.engine.connect() as connection:
                connection.execute(text("SELECT 1")).scalar_one()
        except SQLAlchemyError as exc:
            raise _database_error(exc, operation="health_check") from exc
        return DatabaseHealth(is_healthy=True, dependency="postgresql")

    @contextmanager
    def transaction(self) -> Iterator[Session]:
        self._ensure_open("transaction")
        try:
            with self._session_factory.begin() as session:
                yield session
        except SQLAlchemyError as exc:
            raise _database_error(exc, operation="transaction") from exc

    def close(self) -> None:
        if self._is_closed:
            return
        self.engine.dispose(close=True)
        self._is_closed = True
