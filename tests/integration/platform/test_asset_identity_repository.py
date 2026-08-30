from __future__ import annotations

import threading
import time
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from src.repositories.platform import PostgresDatabase, upgrade_database
from src.repositories.platform.identity import AssetIdentityRepository
from src.schemas.platform import (
    AliasType,
    AliasVerificationStatus,
    AssetAlias,
    AssetIdentityRecord,
    AssetType,
    IdentityStatus,
)


NOW = datetime(2026, 8, 27, 4, 0, tzinfo=timezone.utc)


def _identity(canonical_id: str) -> AssetIdentityRecord:
    return AssetIdentityRecord(
        entity_key=f"stock:{canonical_id}", asset_type=AssetType.STOCK, canonical_id=canonical_id,
        exchange="SH" if canonical_id.startswith("sh") else "SZ", market="CN", currency="CNY", country="CN",
        valid_from=date(1990, 1, 1), valid_to=None, list_date=None, delist_date=None,
        identity_status=IdentityStatus.ACTIVE, schema_version="1.0.0", created_at=NOW,
    )


def _alias(alias_id: str, entity_key: str, *, valid_from: date = date(1990, 1, 1), valid_to: date | None = None) -> AssetAlias:
    return AssetAlias(
        alias_id=alias_id, entity_key=entity_key, alias_type=AliasType.PROVIDER_SYMBOL,
        namespace="financial_api:cn_stock", alias_value="600519.SH", normalized_value="600519.sh",
        valid_from=valid_from, valid_to=valid_to, available_at=NOW, source_provider="financial_api",
        actual_upstream="eastmoney", verification_status=AliasVerificationStatus.VERIFIED,
        revision=1, created_at=NOW,
    )


def _reset_identity_tables(database: PostgresDatabase) -> None:
    upgrade_database(database.engine)
    with database.engine.begin() as connection:
        connection.execute(text("TRUNCATE identity_quarantine, asset_alias, asset_identity CASCADE"))


def test_repository_persists_identity_without_implicit_commit(isolated_postgres_database: PostgresDatabase) -> None:
    database = isolated_postgres_database
    _reset_identity_tables(database)
    repository = AssetIdentityRepository()

    with pytest.raises(RuntimeError, match="rollback"):
        with database.transaction() as session:
            repository.add_identity(session, _identity("sh600519"))
            assert repository.get_identity(session, "stock:sh600519") is not None
            raise RuntimeError("rollback")

    with database.transaction() as session:
        assert repository.get_identity(session, "stock:sh600519") is None
        repository.add_identity(session, _identity("sh600519"))

    with database.transaction() as session:
        assert repository.get_identity(session, "stock:sh600519") is not None


def test_candidate_projection_preserves_distinct_identity_and_alias_timestamps(
    isolated_postgres_database: PostgresDatabase,
) -> None:
    database = isolated_postgres_database
    _reset_identity_tables(database)
    repository = AssetIdentityRepository()
    identity_created_at = NOW - timedelta(days=1)
    identity = _identity("sh600519").model_copy(update={"created_at": identity_created_at})
    alias = _alias("alias_projection_1", identity.entity_key)

    with database.transaction() as session:
        repository.add_identity(session, identity)
        repository.register_alias(session, alias)

    with database.transaction() as session:
        rows = repository.find_candidates_in_session(
            session,
            namespace=alias.namespace,
            normalized_value=alias.normalized_value,
            asset_type=identity.asset_type,
            valid_on=NOW.date(),
            available_at=NOW,
        )

    assert len(rows) == 1
    assert rows[0].identity.created_at == identity_created_at
    assert rows[0].alias.created_at == NOW


def test_overlapping_alias_conflict_enters_quarantine_and_preserves_original(isolated_postgres_database: PostgresDatabase) -> None:
    database = isolated_postgres_database
    _reset_identity_tables(database)
    repository = AssetIdentityRepository()

    with database.transaction() as session:
        repository.add_identity(session, _identity("sh600519"))
        repository.add_identity(session, _identity("sz000001"))
        first = repository.register_alias(session, _alias("alias_pg_1", "stock:sh600519"))
    with database.transaction() as session:
        conflict = repository.register_alias(session, _alias("alias_pg_2", "stock:sz000001"))

    assert first.inserted is True
    assert conflict.inserted is False
    assert conflict.quarantine_id is not None
    with database.engine.connect() as connection:
        aliases = connection.execute(text("SELECT alias_id, entity_key FROM asset_alias ORDER BY alias_id")).all()
        quarantine = connection.execute(
            text("SELECT candidate_entity_key, conflicting_entity_keys, reason_code, quarantine_status FROM identity_quarantine")
        ).one()
    assert aliases == [("alias_pg_1", "stock:sh600519")]
    assert quarantine[0] == "stock:sz000001"
    assert quarantine[1] == ["stock:sh600519"]
    assert quarantine[2] == "ALIAS_VALIDITY_CONFLICT"
    assert quarantine[3] == "OPEN"


def test_validity_is_right_open_and_non_overlapping_revisions_are_allowed(isolated_postgres_database: PostgresDatabase) -> None:
    database = isolated_postgres_database
    _reset_identity_tables(database)
    repository = AssetIdentityRepository()
    boundary = date(2020, 1, 1)

    with database.transaction() as session:
        repository.add_identity(session, _identity("sh600519"))
        first = repository.register_alias(session, _alias("alias_pg_1", "stock:sh600519", valid_to=boundary))
        second_alias = _alias(
            "alias_pg_2",
            "stock:sh600519",
            valid_from=boundary,
        ).model_copy(update={"revision": 2})
        second = repository.register_alias(session, second_alias)

    assert first.inserted is True
    assert second.inserted is True


def test_overlapping_revisions_for_the_same_entity_are_allowed(
    isolated_postgres_database: PostgresDatabase,
) -> None:
    database = isolated_postgres_database
    _reset_identity_tables(database)
    repository = AssetIdentityRepository()
    identity = _identity("sh600519")

    with database.transaction() as session:
        repository.add_identity(session, identity)
        first = repository.register_alias(session, _alias("alias_same_entity_1", identity.entity_key))
        second = repository.register_alias(
            session,
            _alias("alias_same_entity_2", identity.entity_key).model_copy(update={"revision": 2}),
        )

    assert first.inserted is True
    assert second.inserted is True
    with database.engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM asset_alias")).scalar_one() == 2
        assert connection.execute(text("SELECT count(*) FROM identity_quarantine")).scalar_one() == 0


def test_database_constraint_prevents_concurrent_overlapping_aliases(isolated_postgres_database: PostgresDatabase) -> None:
    database = isolated_postgres_database
    _reset_identity_tables(database)
    repository = AssetIdentityRepository()
    with database.transaction() as session:
        repository.add_identity(session, _identity("sh600519"))
        repository.add_identity(session, _identity("sz000001"))

    first_inserted = threading.Event()
    release_first = threading.Event()
    outcomes: list[str] = []

    def first_writer() -> None:
        try:
            with database.engine.begin() as connection:
                connection.execute(text(
                    "INSERT INTO asset_alias (alias_id, entity_key, alias_type, namespace, alias_value, normalized_value, valid_from, valid_to, available_at, source_provider, actual_upstream, verification_status, revision, created_at) "
                    "VALUES ('alias_concurrent_1', 'stock:sh600519', 'PROVIDER_SYMBOL', 'financial_api:cn_stock', '600519.SH', '600519.sh', DATE '1990-01-01', NULL, :now, 'financial_api', 'eastmoney', 'VERIFIED', 1, :now)"
                ), {"now": NOW})
                first_inserted.set()
                release_first.wait(timeout=5)
            outcomes.append("first_committed")
        except Exception as exc:  # pragma: no cover - assertion reports concrete type
            outcomes.append(type(exc).__name__)

    def second_writer() -> None:
        first_inserted.wait(timeout=5)
        try:
            with database.engine.begin() as connection:
                connection.execute(text(
                    "INSERT INTO asset_alias (alias_id, entity_key, alias_type, namespace, alias_value, normalized_value, valid_from, valid_to, available_at, source_provider, actual_upstream, verification_status, revision, created_at) "
                    "VALUES ('alias_concurrent_2', 'stock:sz000001', 'PROVIDER_SYMBOL', 'financial_api:cn_stock', '600519.SH', '600519.sh', DATE '1990-01-01', NULL, :now, 'financial_api', 'eastmoney', 'VERIFIED', 1, :now)"
                ), {"now": NOW})
            outcomes.append("second_committed")
        except IntegrityError:
            outcomes.append("second_conflict")

    first = threading.Thread(target=first_writer)
    second = threading.Thread(target=second_writer)
    first.start()
    second.start()
    assert first_inserted.wait(timeout=5)
    time.sleep(0.2)
    release_first.set()
    first.join(timeout=5)
    second.join(timeout=5)

    assert sorted(outcomes) == ["first_committed", "second_conflict"]
    with database.engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM asset_alias")).scalar_one() == 1
