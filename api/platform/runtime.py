from __future__ import annotations

import logging
import os

from fastapi import FastAPI

from src.core.platform.identity_resolver import AssetResolverService
from src.services.platform.task_control import TaskControlService
from src.repositories.platform import DatabaseConfigurationError, DatabaseSecretError, PostgresDatabase, PostgresSettings
from src.repositories.platform.identity import PostgresAssetResolverRepository


logger = logging.getLogger(__name__)


def initialize_asset_identity_runtime(app: FastAPI) -> None:
    if hasattr(app.state, "asset_resolver_service") and hasattr(app.state, "task_control_service"):
        return
    configured_names = [name for name in os.environ if name.startswith("VISORY_POSTGRES_")]
    if not configured_names:
        return
    try:
        settings = PostgresSettings.from_environment()
        database = PostgresDatabase.from_settings(settings)
    except (DatabaseConfigurationError, DatabaseSecretError) as exc:
        logger.error(
            "platform_identity_runtime_configuration_rejected",
            extra={"error_code": exc.error_code, "retryable": exc.retryable},
        )
        return
    app.state.platform_postgres_database = database
    app.state.asset_resolver_service = AssetResolverService(PostgresAssetResolverRepository(database))
    runtime_root = os.getenv("VISORY_RUNTIME_ROOT")
    app.state.task_control_service = TaskControlService(database, runtime_root=runtime_root)
    app.state.platform_identity_runtime_owned = True


def close_asset_identity_runtime(app: FastAPI) -> None:
    if not getattr(app.state, "platform_identity_runtime_owned", False):
        return
    database = getattr(app.state, "platform_postgres_database", None)
    if database is not None:
        database.close()
        delattr(app.state, "platform_postgres_database")
    if hasattr(app.state, "asset_resolver_service"):
        delattr(app.state, "asset_resolver_service")
    if hasattr(app.state, "task_control_service"):
        delattr(app.state, "task_control_service")
    delattr(app.state, "platform_identity_runtime_owned")
