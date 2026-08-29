from __future__ import annotations

import os
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from .errors import DatabaseConfigurationError, DatabaseSecretError


_ENV_PREFIX = "VISORY_POSTGRES_"
_FORBIDDEN_RAW_SECRET_SETTINGS = (
    "VISORY_POSTGRES_PASSWORD",
    "VISORY_POSTGRES_DSN",
    "VISORY_POSTGRES_URL",
)
_MAX_SECRET_BYTES = 4096


def _configuration_error(setting: str, error_code: str = "DATABASE_CONFIG_INVALID") -> DatabaseConfigurationError:
    return DatabaseConfigurationError(
        error_code=error_code,
        public_message="PostgreSQL configuration is invalid.",
        retryable=False,
        details={"setting": setting},
    )


def _parse_int(
    environment: Mapping[str, str],
    name: str,
    default: int,
    *,
    minimum: int,
    maximum: int,
) -> int:
    raw_value = environment.get(name)
    if raw_value is None or raw_value == "":
        return default
    try:
        value = int(raw_value)
    except (TypeError, ValueError) as exc:
        raise _configuration_error(name) from exc
    if not minimum <= value <= maximum:
        raise _configuration_error(name)
    return value


def _nonblank(environment: Mapping[str, str], name: str, default: str) -> str:
    value = environment.get(name, default)
    if not isinstance(value, str) or not value.strip() or any(ord(character) < 32 for character in value):
        raise _configuration_error(name)
    return value


@dataclass(frozen=True, slots=True)
class PostgresSettings:
    host: str
    port: int
    database: str
    username: str
    password_file: Path
    connect_timeout_seconds: int = 5
    pool_size: int = 5
    max_overflow: int = 5
    pool_timeout_seconds: int = 30
    pool_recycle_seconds: int = 1800
    application_name: str = "visory"

    def __post_init__(self) -> None:
        if not self.host.strip() or any(ord(character) < 32 for character in self.host):
            raise _configuration_error(f"{_ENV_PREFIX}HOST")
        if not 1 <= self.port <= 65535:
            raise _configuration_error(f"{_ENV_PREFIX}PORT")
        if not self.database.strip() or any(ord(character) < 32 for character in self.database):
            raise _configuration_error(f"{_ENV_PREFIX}DATABASE")
        if not self.username.strip() or any(ord(character) < 32 for character in self.username):
            raise _configuration_error(f"{_ENV_PREFIX}USER")
        if not self.password_file.is_absolute():
            raise _configuration_error(f"{_ENV_PREFIX}PASSWORD_FILE")
        if not 1 <= self.connect_timeout_seconds <= 300:
            raise _configuration_error(f"{_ENV_PREFIX}CONNECT_TIMEOUT_SECONDS")
        if not 1 <= self.pool_size <= 100:
            raise _configuration_error(f"{_ENV_PREFIX}POOL_SIZE")
        if not 0 <= self.max_overflow <= 100:
            raise _configuration_error(f"{_ENV_PREFIX}MAX_OVERFLOW")
        if not 1 <= self.pool_timeout_seconds <= 300:
            raise _configuration_error(f"{_ENV_PREFIX}POOL_TIMEOUT_SECONDS")
        if not 0 <= self.pool_recycle_seconds <= 86400:
            raise _configuration_error(f"{_ENV_PREFIX}POOL_RECYCLE_SECONDS")
        if not self.application_name.strip() or any(ord(character) < 32 for character in self.application_name):
            raise _configuration_error(f"{_ENV_PREFIX}APPLICATION_NAME")

    @classmethod
    def from_environment(cls, environment: Mapping[str, str] | None = None) -> "PostgresSettings":
        active_environment = os.environ if environment is None else environment
        for setting in _FORBIDDEN_RAW_SECRET_SETTINGS:
            if active_environment.get(setting):
                raise _configuration_error(setting, "DATABASE_RAW_SECRET_FORBIDDEN")

        password_file_value = active_environment.get(f"{_ENV_PREFIX}PASSWORD_FILE")
        if not password_file_value:
            raise _configuration_error(f"{_ENV_PREFIX}PASSWORD_FILE")
        password_file = Path(password_file_value).expanduser()
        if not password_file.is_absolute():
            raise _configuration_error(f"{_ENV_PREFIX}PASSWORD_FILE")

        return cls(
            host=_nonblank(active_environment, f"{_ENV_PREFIX}HOST", "127.0.0.1"),
            port=_parse_int(active_environment, f"{_ENV_PREFIX}PORT", 5432, minimum=1, maximum=65535),
            database=_nonblank(active_environment, f"{_ENV_PREFIX}DATABASE", "visory"),
            username=_nonblank(active_environment, f"{_ENV_PREFIX}USER", "visory"),
            password_file=password_file.resolve(strict=False),
            connect_timeout_seconds=_parse_int(
                active_environment,
                f"{_ENV_PREFIX}CONNECT_TIMEOUT_SECONDS",
                5,
                minimum=1,
                maximum=300,
            ),
            pool_size=_parse_int(active_environment, f"{_ENV_PREFIX}POOL_SIZE", 5, minimum=1, maximum=100),
            max_overflow=_parse_int(
                active_environment,
                f"{_ENV_PREFIX}MAX_OVERFLOW",
                5,
                minimum=0,
                maximum=100,
            ),
            pool_timeout_seconds=_parse_int(
                active_environment,
                f"{_ENV_PREFIX}POOL_TIMEOUT_SECONDS",
                30,
                minimum=1,
                maximum=300,
            ),
            pool_recycle_seconds=_parse_int(
                active_environment,
                f"{_ENV_PREFIX}POOL_RECYCLE_SECONDS",
                1800,
                minimum=0,
                maximum=86400,
            ),
            application_name=_nonblank(active_environment, f"{_ENV_PREFIX}APPLICATION_NAME", "visory"),
        )


def _secret_error(error_code: str, public_message: str, cause: BaseException | None = None) -> DatabaseSecretError:
    return DatabaseSecretError(
        error_code=error_code,
        public_message=public_message,
        retryable=False,
        details={"secret": "postgres_password"},
        cause=cause,
    )


def read_secret_file(path: Path) -> str:
    secret_path = Path(path)
    try:
        file_stat = secret_path.lstat()
    except FileNotFoundError as exc:
        raise _secret_error("DATABASE_SECRET_FILE_MISSING", "PostgreSQL password file is missing.", exc) from exc
    except PermissionError as exc:
        raise _secret_error("DATABASE_SECRET_FILE_UNREADABLE", "PostgreSQL password file is unreadable.", exc) from exc
    except OSError as exc:
        raise _secret_error("DATABASE_SECRET_FILE_UNREADABLE", "PostgreSQL password file is unreadable.", exc) from exc

    if stat.S_ISLNK(file_stat.st_mode) or not stat.S_ISREG(file_stat.st_mode):
        raise _secret_error("DATABASE_SECRET_FILE_INVALID", "PostgreSQL password file is invalid.")
    if os.name != "nt" and file_stat.st_mode & 0o077:
        raise _secret_error(
            "DATABASE_SECRET_FILE_PERMISSIONS",
            "PostgreSQL password file permissions are too broad.",
        )

    try:
        payload = secret_path.read_bytes()
    except PermissionError as exc:
        raise _secret_error("DATABASE_SECRET_FILE_UNREADABLE", "PostgreSQL password file is unreadable.", exc) from exc
    except OSError as exc:
        raise _secret_error("DATABASE_SECRET_FILE_UNREADABLE", "PostgreSQL password file is unreadable.", exc) from exc

    if not payload or len(payload) > _MAX_SECRET_BYTES:
        raise _secret_error("DATABASE_SECRET_FILE_INVALID", "PostgreSQL password file is invalid.")
    try:
        secret = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _secret_error("DATABASE_SECRET_FILE_INVALID", "PostgreSQL password file is invalid.", exc) from exc

    if secret.endswith("\r\n"):
        secret = secret[:-2]
    elif secret.endswith("\n"):
        secret = secret[:-1]
    if not secret or secret != secret.strip() or "\n" in secret or "\r" in secret:
        raise _secret_error("DATABASE_SECRET_FILE_INVALID", "PostgreSQL password file is invalid.")
    if any(ord(character) < 32 or ord(character) == 127 for character in secret):
        raise _secret_error("DATABASE_SECRET_FILE_INVALID", "PostgreSQL password file is invalid.")
    return secret
