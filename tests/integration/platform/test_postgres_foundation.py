from __future__ import annotations

import logging
import socket
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from src.repositories.platform import (
    PlatformDatabaseError,
    PostgresDatabase,
    downgrade_database,
    get_migration_status,
    upgrade_database,
)


HEAD_REVISION = "0012_wp0204_benchmark_dataset_extension"


def _table_names(database: PostgresDatabase) -> tuple[str, ...]:
    with database.engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT tablename FROM pg_catalog.pg_tables "
                "WHERE schemaname = 'public' ORDER BY tablename"
            )
        )
        return tuple(row[0] for row in rows)


def _column_names(database: PostgresDatabase, table_name: str) -> tuple[str, ...]:
    with database.engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = :table_name "
                "ORDER BY ordinal_position"
            ),
            {"table_name": table_name},
        )
        return tuple(row[0] for row in rows)


def _constraint_definition(database: PostgresDatabase, table_name: str, constraint_name: str) -> str:
    with database.engine.connect() as connection:
        return connection.execute(
            text(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE conrelid = to_regclass(:table_name) AND conname = :constraint_name"
            ),
            {"table_name": table_name, "constraint_name": constraint_name},
        ).scalar_one()


def test_empty_database_upgrade_is_idempotent_and_reversible(isolated_postgres_database: PostgresDatabase) -> None:
    database = isolated_postgres_database

    initial = get_migration_status(database.engine)
    assert initial.current_revision is None
    assert initial.head_revision == HEAD_REVISION
    assert initial.is_at_head is False

    existing_logger = logging.getLogger("visory.wp0002.migration-probe")
    existing_logger.disabled = False

    upgrade_database(database.engine)
    assert existing_logger.disabled is False
    upgraded = get_migration_status(database.engine)
    first_tables = _table_names(database)
    assert upgraded.current_revision == HEAD_REVISION
    assert upgraded.head_revision == HEAD_REVISION
    assert upgraded.is_at_head is True
    assert first_tables == (
        "alembic_version",
        "artifact_registry",
        "asset_alias",
        "asset_identity",
        "benchmark_dataset_extension",
        "canonical_mapping_definition",
        "canonical_partition",
        "canonical_partition_lineage",
        "canonical_quality_report",
        "capability_certification",
        "consumer_requirement",
        "data_snapshot",
        "dataset_definition",
        "identity_quarantine",
        "platform_task",
        "provider_capability",
        "provider_definition",
        "provider_policy",
        "provider_rate_limit_window",
        "provider_raw_schema_definition",
        "provider_run",
        "raw_ingestion_quarantine",
        "raw_object",
        "snapshot_current_pointer",
        "snapshot_partition_ref",
        "task_attempt",
        "task_checkpoint",
        "task_command_idempotency",
        "task_state_event",
    )
    upgrade_database(database.engine)
    repeated = get_migration_status(database.engine)
    assert repeated == upgraded
    assert _table_names(database) == first_tables

    downgrade_database(database.engine, "base")
    downgraded = get_migration_status(database.engine)
    assert downgraded.current_revision is None
    assert downgraded.head_revision == HEAD_REVISION
    assert downgraded.is_at_head is False

    upgrade_database(database.engine)
    restored = get_migration_status(database.engine)
    assert restored.current_revision == HEAD_REVISION
    assert restored.is_at_head is True
    assert _table_names(database) == first_tables


def test_benchmark_dataset_extension_is_independent_and_reversible(
    isolated_postgres_database: PostgresDatabase,
) -> None:
    database = isolated_postgres_database
    upgrade_database(database.engine)

    with database.engine.connect() as connection:
        extension = connection.execute(
            text(
                "SELECT dataset_id, schema_version, asset_type, return_types, provider_ids "
                "FROM benchmark_dataset_extension"
            )
        ).mappings().one()
    assert extension["dataset_id"] == "benchmark_index_1d"
    assert extension["schema_version"] == "1.0.0"
    assert extension["asset_type"] == "index"
    assert tuple(extension["return_types"]) == ("PRICE", "TOTAL_RETURN")
    assert set(extension["provider_ids"]) == {"a_stock_data", "financial_api"}

    for values in (
        {"dataset_id": "benchmark_index_1d", "asset_type": "stock"},
        {"dataset_id": "not_a_benchmark", "asset_type": "index"},
    ):
        with pytest.raises(IntegrityError):
            with database.engine.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO benchmark_dataset_extension "
                        "(dataset_id, schema_version, asset_type, return_types, provider_ids, contract_notes) "
                        "VALUES (:dataset_id, '1.0.0', :asset_type, '[]'::jsonb, '[]'::jsonb, 'invalid')"
                    ),
                    values,
                )

    expected_quality_columns = {
        "coverage_ratio",
        "excluded_instrument_count",
        "quality_threshold_version",
    }
    assert expected_quality_columns.issubset(set(_column_names(database, "canonical_quality_report")))
    assert expected_quality_columns.issubset(set(_column_names(database, "snapshot_partition_ref")))
    upgraded_status = _constraint_definition(
        database,
        "capability_certification",
        "ck_capability_certification_status",
    ).upper()
    for status in ("CERTIFIED", "PROVISIONAL", "PARTIAL", "UNAVAILABLE", "STALE"):
        assert status in upgraded_status

    downgrade_database(database.engine, "0011_wp0204_snapshot_foundation")
    assert get_migration_status(database.engine).current_revision == "0011_wp0204_snapshot_foundation"
    assert "benchmark_dataset_extension" not in _table_names(database)
    assert not expected_quality_columns.intersection(_column_names(database, "canonical_quality_report"))
    assert not expected_quality_columns.intersection(_column_names(database, "snapshot_partition_ref"))
    downgraded_status = _constraint_definition(
        database,
        "capability_certification",
        "ck_capability_certification_status",
    ).upper()
    for status in ("CERTIFIED", "UNAVAILABLE", "DEGRADED", "UNVERIFIED"):
        assert status in downgraded_status
    for status in ("PROVISIONAL", "PARTIAL", "STALE"):
        assert status not in downgraded_status

    upgrade_database(database.engine, "0012_wp0204_benchmark_dataset_extension")
    assert get_migration_status(database.engine).current_revision == HEAD_REVISION
    assert "benchmark_dataset_extension" in _table_names(database)
    assert expected_quality_columns.issubset(set(_column_names(database, "canonical_quality_report")))
    assert expected_quality_columns.issubset(set(_column_names(database, "snapshot_partition_ref")))


def test_timestamptz_round_trip_preserves_the_same_instant(isolated_postgres_database: PostgresDatabase) -> None:
    database = isolated_postgres_database
    original = datetime(2026, 8, 29, 16, 45, 12, 345678, tzinfo=timezone(timedelta(hours=5, minutes=30)))

    with database.engine.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS wp0002_timezone_probe"))
        connection.execute(text("CREATE TABLE wp0002_timezone_probe (observed_at timestamptz NOT NULL)"))
        connection.execute(
            text("INSERT INTO wp0002_timezone_probe (observed_at) VALUES (:observed_at)"),
            {"observed_at": original},
        )
        restored = connection.execute(text("SELECT observed_at FROM wp0002_timezone_probe")).scalar_one()
        connection.execute(text("DROP TABLE wp0002_timezone_probe"))

    assert restored.tzinfo is not None
    assert restored.astimezone(timezone.utc) == original.astimezone(timezone.utc)


class _ProbeRepository:
    @staticmethod
    def add_value(session, value: str) -> None:
        session.execute(text("INSERT INTO wp0002_transaction_probe (value) VALUES (:value)"), {"value": value})


def test_transaction_commits_success_and_rolls_back_exception(isolated_postgres_database: PostgresDatabase) -> None:
    database = isolated_postgres_database
    with database.engine.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS wp0002_transaction_probe"))
        connection.execute(text("CREATE TABLE wp0002_transaction_probe (value text NOT NULL)"))

    with database.transaction() as session:
        _ProbeRepository.add_value(session, "committed")

    with database.engine.connect() as connection:
        assert connection.execute(text("SELECT value FROM wp0002_transaction_probe ORDER BY value")).scalars().all() == [
            "committed"
        ]

    with pytest.raises(RuntimeError, match="force rollback"):
        with database.transaction() as session:
            _ProbeRepository.add_value(session, "rolled-back")
            raise RuntimeError("force rollback")

    with database.engine.connect() as connection:
        assert connection.execute(text("SELECT value FROM wp0002_transaction_probe ORDER BY value")).scalars().all() == [
            "committed"
        ]

    with database.engine.begin() as connection:
        connection.execute(text("DROP TABLE wp0002_transaction_probe"))


def test_unavailable_postgres_returns_stable_retryable_sanitized_error(
    isolated_postgres_database: PostgresDatabase,
) -> None:
    source = isolated_postgres_database.settings
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        unused_port = probe.getsockname()[1]
    unavailable = PostgresDatabase.from_settings(
        replace(source, host="127.0.0.1", port=unused_port, connect_timeout_seconds=1)
    )
    secret = source.password_file.read_text(encoding="utf-8").strip()

    try:
        with pytest.raises(PlatformDatabaseError) as captured:
            unavailable.check_health()
    finally:
        unavailable.close()

    error = captured.value
    assert error.error_code == "DATABASE_UNAVAILABLE"
    assert error.retryable is True
    assert error.details == {"dependency": "postgresql", "operation": "health_check"}
    assert secret not in str(error)
    assert secret not in repr(error)
    assert str(source.password_file) not in str(error)
    assert "postgresql+psycopg://" not in str(error)


def test_connection_pool_can_close_without_checked_out_connections(
    isolated_postgres_database: PostgresDatabase,
) -> None:
    source = isolated_postgres_database.settings
    database = PostgresDatabase.from_settings(replace(source, application_name="visory-wp0002-pool-close"))

    health = database.check_health()
    assert health.is_healthy is True
    assert health.dependency == "postgresql"
    assert database.engine.pool.checkedout() == 0

    database.close()
    assert database.is_closed is True
    assert database.engine.pool.checkedout() == 0

    with pytest.raises(PlatformDatabaseError) as captured:
        database.check_health()
    assert captured.value.error_code == "DATABASE_POOL_CLOSED"
    assert captured.value.retryable is False
