"""Authorized B5 derived-key extension, real migrations and old-DB protection."""
from datetime import date

import pytest
from sqlalchemy import inspect, text

from src.repositories.platform import FeatureRepository, PlatformDatabaseError, downgrade_database, upgrade_database
from src.repositories.platform.feature import feature_partition
from src.schemas.platform import FeatureInstanceKey, FeatureMaterializationError, compute_content_hash
from src.services.platform.feature_store import FeatureStore, FeaturePublicationError, _partition_key
from src.services.platform.indicator_registry import IndicatorRegistry
from tests.integration.platform.test_feature_indicator_id_postgres import (
    OLD, _boundary_plan, _database_state, _files, _preview,
)
from tests.integration.platform.test_feature_repository import _records
from tests.platform.test_feature_store_contracts import CUTOFF, _publish, _row, _single_plan
from tests.platform.test_indicator_registry import _definition
from tests.platform.test_market_sentiment import complete_score_fixture

INTERMEDIATE = '0014_wp0303_indicator_id'
LATEST = '0015_wp0303_partition_key'


def _key_width(db):
    with db.engine.connect() as connection:
        return next(c['type'].length for c in inspect(connection).get_columns('feature_partition')
                    if c['name'] == 'partition_key')


def _max_key_plan(extra_version=0):
    version = '1.0.0+' + 'v' * (26 + extra_version)
    frequency = 'f' * 32
    indicator = 'x' * 128
    scope = compute_content_hash({'isolated': True})
    instance = FeatureInstanceKey(indicator_id=indicator, definition_version=version, frequency=frequency,
                                  canonical_parameter_json='{}', parameter_hash=compute_content_hash({}),
                                  universe_scope_hash=scope)
    day = date(2026, 1, 3)
    plan = _single_plan(instance, date_from=day, date_to=day, universe_scope_hash=scope,
                        lookback_requirement=0, warmup_requirement=0)
    row = _row('cn.stock:000001', day).model_copy(update={
        'indicator_id': indicator, 'definition_version': version, 'unit': 'shares',
    })
    definition = _definition(indicator_id=indicator, definition_version=version)
    definition = type(definition).model_validate(definition.model_dump(exclude={'definition_hash'}) | {
        'frequency': frequency, 'lookback_requirement': 0, 'warmup_requirement': 0,
    })
    assert len(_partition_key(instance, day, day)) == 386 + extra_version
    return plan, {instance: (row,)}, IndicatorRegistry((definition,))


def test_intermediate_revision_complete_fixture_fails_before_any_file_or_dml(isolated_postgres_database, tmp_path):
    db = isolated_postgres_database
    upgrade_database(db.engine, INTERMEDIATE)
    plan, rows, _, source = complete_score_fixture()
    store = FeatureStore(tmp_path, database=db, fixture_only=True, clock=lambda: plan.cutoff_at)
    before = _database_state(db), _files(tmp_path)
    with pytest.raises(FeatureMaterializationError, match='existing PostgreSQL partition_key limit'):
        store.materialize_and_publish(plan, rows, data_snapshot_ids=(source,), cutoff_at=plan.cutoff_at,
                                      as_of_trade_date=date(2026, 3, 6), consumer_ref='isolated-complete-score-fixture')
    assert (_database_state(db), _files(tmp_path)) == before


@pytest.mark.parametrize('width', [256, 386])
def test_intermediate_revision_repository_preflights_key_before_dml(isolated_postgres_database, width):
    db = isolated_postgres_database
    upgrade_database(db.engine, INTERMEDIATE)
    partition, _, _ = _records()
    partition = partition.model_copy(update={'partition_key': 'k' * width})
    before = _database_state(db)
    # 在事务内部捕获校验异常，证明不依赖外层 rollback 来移除已写入的数据。
    with db.transaction() as session:
        with pytest.raises(ValueError, match='existing PostgreSQL partition_key limit'):
            FeatureRepository.add_partition(session, partition)
        assert session.execute(text('SELECT count(*) FROM feature_partition')).scalar_one() == 0
    assert _database_state(db) == before


@pytest.mark.parametrize('width', [255, 256, 386])
def test_latest_revision_repository_key_boundaries_round_trip(isolated_postgres_database, width):
    db = isolated_postgres_database
    upgrade_database(db.engine, INTERMEDIATE)
    upgrade_database(db.engine, LATEST)
    partition, _, _ = _records()
    partition = type(partition).model_validate(partition.model_dump() | {'partition_key': 'k' * width})
    with db.transaction() as session:
        FeatureRepository.add_partition(session, partition)
    with db.transaction() as session:
        assert FeatureRepository.get_partition(session, partition.feature_partition_id) == partition
    assert _key_width(db) == 386


def test_latest_revision_rejects_bypassed_387_before_dml(isolated_postgres_database):
    db = isolated_postgres_database
    upgrade_database(db.engine, LATEST)
    partition, _, _ = _records()
    before = _database_state(db)
    with db.transaction() as session:
        with pytest.raises(ValueError, match='386 character contract'):
            FeatureRepository.add_partition(session, partition.model_copy(update={'partition_key': 'k' * 387}))
        assert session.execute(text('SELECT count(*) FROM feature_partition')).scalar_one() == 0
    assert _database_state(db) == before


def test_max_derived_key_store_database_restart_round_trip(isolated_postgres_database, tmp_path):
    db = isolated_postgres_database
    upgrade_database(db.engine, LATEST)
    plan, rows, registry = _max_key_plan()
    day = date(2026, 1, 3)
    store = FeatureStore(tmp_path, database=db, indicator_registry=registry, clock=lambda: CUTOFF)
    snapshot, bundle = _publish(store, plan, rows, date_from=day, date_to=day)
    fresh = FeatureStore(tmp_path, database=db, indicator_registry=registry)
    with pytest.raises(FeaturePublicationError, match='not certified'):
        fresh.consume_bundle(bundle.feature_bundle_id, _preview())
    assert fresh.published_bundle(bundle.feature_bundle_id) == bundle
    partition = fresh.published_partition(snapshot.feature_partition_refs[0].feature_partition_id)
    assert len(partition.partition_key) == 386
    assert partition.partition_key == _partition_key(plan.ordered_instances[0], day, day)
    assert fresh.read_partition_payload(partition.feature_partition_id)


def test_store_rejects_387_before_files_even_in_memory(tmp_path):
    plan, rows, registry = _max_key_plan(extra_version=1)
    store = FeatureStore(tmp_path, indicator_registry=registry, clock=lambda: CUTOFF)
    before = _files(tmp_path)
    with pytest.raises(FeatureMaterializationError, match='386 character contract'):
        _publish(store, plan, rows, date_from=date(2026, 1, 3), date_to=date(2026, 1, 3))
    assert _files(tmp_path) == before


def test_key_migration_only_changes_authorized_column_and_safe_downgrade_reupgrade(isolated_postgres_database, tmp_path):
    db = isolated_postgres_database
    upgrade_database(db.engine, OLD)
    plan, rows, registry = _boundary_plan('x' * 64)
    snapshot, bundle = _publish(FeatureStore(tmp_path, database=db, indicator_registry=registry, clock=lambda: CUTOFF), plan, rows)
    upgrade_database(db.engine, INTERMEDIATE)
    old, files = _database_state(db), _files(tmp_path)
    upgrade_database(db.engine, LATEST)
    new = _database_state(db)
    assert new[1:4] == old[1:4]
    for name, columns in old[0].items():
        expected = tuple((n, 'VARCHAR(386)' if name == 'feature_partition' and n == 'partition_key' else t, nullable)
                         for n, t, nullable in columns)
        assert new[0][name] == expected
    assert new[4] == LATEST
    downgrade_database(db.engine, INTERMEDIATE)
    assert _database_state(db) == old
    assert _files(tmp_path) == files
    upgrade_database(db.engine, LATEST)
    assert _database_state(db) == new
    fresh = FeatureStore(tmp_path, database=db, indicator_registry=registry)
    with pytest.raises(FeaturePublicationError, match='not certified'):
        fresh.consume_bundle(bundle.feature_bundle_id, _preview())
    assert fresh.published_snapshot(snapshot.feature_snapshot_id) == snapshot
    assert fresh.published_bundle(bundle.feature_bundle_id) == bundle
    assert _files(tmp_path) == files


@pytest.mark.parametrize('width', [256, 386])
def test_key_downgrade_refuses_long_keys_without_schema_data_version_or_file_changes(isolated_postgres_database, tmp_path, width):
    db = isolated_postgres_database
    upgrade_database(db.engine, LATEST)
    plan, rows, registry = _boundary_plan('x' * 64)
    _publish(FeatureStore(tmp_path, database=db, indicator_registry=registry, clock=lambda: CUTOFF), plan, rows)
    with db.engine.begin() as connection:
        connection.execute(feature_partition.update().values(partition_key='k' * width))
    before = _database_state(db), _files(tmp_path)
    with pytest.raises(PlatformDatabaseError) as error:
        downgrade_database(db.engine, INTERMEDIATE)
    assert 'longer than 255' in str(error.value.__cause__)
    assert (_database_state(db), _files(tmp_path)) == before
    assert _key_width(db) == 386


def test_key_preflight_lock_prevents_concurrent_downgrade(isolated_postgres_database):
    from alembic import command
    from sqlalchemy.exc import DBAPIError
    from src.repositories.platform.migrations import _alembic_config

    db = isolated_postgres_database
    upgrade_database(db.engine, LATEST)
    before = _database_state(db)
    with db.transaction() as session:
        FeatureRepository.validate_indicator_ids(session, ('x' * 64,), partition_keys=('k' * 256,))
        with pytest.raises(DBAPIError) as error:
            with db.engine.begin() as connection:
                connection.execute(text("SET LOCAL lock_timeout = '250ms'"))
                config = _alembic_config()
                config.attributes['connection'] = connection
                command.downgrade(config, INTERMEDIATE)
        assert error.value.orig.sqlstate == '55P03'
    assert _database_state(db) == before
    downgrade_database(db.engine, INTERMEDIATE)
    assert _key_width(db) == 255


@pytest.mark.parametrize('width', [255, 256])
def test_intermediate_store_255_accepts_and_256_rejects_without_residue(isolated_postgres_database, tmp_path, width):
    db = isolated_postgres_database
    upgrade_database(db.engine, INTERMEDIATE)
    plan, rows, registry = _boundary_plan('x' * (width - 129))
    assert len(_partition_key(plan.ordered_instances[0], None, None)) == width
    store = FeatureStore(tmp_path, database=db, indicator_registry=registry, clock=lambda: CUTOFF)
    before = _database_state(db), _files(tmp_path)
    if width == 255:
        snapshot, _ = _publish(store, plan, rows)
        assert len(store.published_partition(snapshot.feature_partition_refs[0].feature_partition_id).partition_key) == 255
    else:
        with pytest.raises(FeatureMaterializationError, match='existing PostgreSQL partition_key limit'):
            _publish(store, plan, rows)
        assert (_database_state(db), _files(tmp_path)) == before


@pytest.mark.parametrize('table', ['feature_partition', 'feature_snapshot_partition_ref', 'feature_bundle_partition_ref'])
def test_latest_downgrade_long_id_rejects_before_any_alter_even_when_key_fits(isolated_postgres_database, tmp_path, table):
    from sqlalchemy import event
    from src.repositories.platform.feature import metadata

    db = isolated_postgres_database
    upgrade_database(db.engine, LATEST)
    plan, rows, registry = _boundary_plan('x' * 64)
    _publish(FeatureStore(tmp_path, database=db, indicator_registry=registry, clock=lambda: CUTOFF), plan, rows)
    with db.engine.begin() as connection:
        connection.execute(metadata.tables[table].update().values(indicator_id='x' * 65))
    before = _database_state(db), _files(tmp_path)
    statements = []

    def record_statement(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(db.engine, 'before_cursor_execute', record_statement)
    try:
        with pytest.raises(PlatformDatabaseError) as error:
            downgrade_database(db.engine, OLD)
    finally:
        event.remove(db.engine, 'before_cursor_execute', record_statement)
    assert 'longer than 64' in str(error.value.__cause__)
    assert not any('ALTER TABLE' in statement.upper() for statement in statements)
    assert (_database_state(db), _files(tmp_path)) == before



def test_same_store_rechecks_real_key_width_after_upgrade_without_cached_rejection(isolated_postgres_database, tmp_path):
    db = isolated_postgres_database
    upgrade_database(db.engine, INTERMEDIATE)
    plan, rows, registry = _boundary_plan('x' * 128)
    store = FeatureStore(tmp_path, database=db, indicator_registry=registry, clock=lambda: CUTOFF)
    before = _database_state(db), _files(tmp_path)
    with pytest.raises(FeatureMaterializationError, match='existing PostgreSQL partition_key limit'):
        _publish(store, plan, rows)
    assert (_database_state(db), _files(tmp_path)) == before
    upgrade_database(db.engine, LATEST)
    snapshot, bundle = _publish(store, plan, rows)
    assert len(store.published_partition(snapshot.feature_partition_refs[0].feature_partition_id).partition_key) == 257
    fresh = FeatureStore(tmp_path, database=db, indicator_registry=registry)
    with pytest.raises(FeaturePublicationError, match='not certified'):
        fresh.consume_bundle(bundle.feature_bundle_id, _preview())
    assert fresh.published_bundle(bundle.feature_bundle_id) == bundle


@pytest.mark.parametrize('complete_fixture', [False, True])
def test_publication_preflight_uses_single_connection_pool_through_restart_and_correction(
    isolated_postgres_database, tmp_path, complete_fixture,
):
    from dataclasses import replace
    from src.repositories.platform import PostgresDatabase

    original = isolated_postgres_database
    settings = replace(original.settings, pool_size=1, max_overflow=0, pool_timeout_seconds=1)
    db = PostgresDatabase.from_settings(settings)
    try:
        upgrade_database(db.engine, LATEST)
        if complete_fixture:
            plan, rows, _, source = complete_score_fixture()
            _, corrected, _, _ = complete_score_fixture(correction=True)
            registry = None
            args = dict(data_snapshot_ids=(source,), cutoff_at=plan.cutoff_at,
                        as_of_trade_date=date(2026, 3, 6), consumer_ref='isolated-single-pool-fixture')
        else:
            plan, rows, registry = _boundary_plan('x' * 128)
            corrected = {instance: tuple(row.model_copy(update={'value': row.value + 1}) for row in values)
                         for instance, values in rows.items()}
            args = dict(data_snapshot_ids=(next(iter(rows.values()))[0].data_snapshot_id,),
                        cutoff_at=plan.cutoff_at, as_of_trade_date=date(2026, 1, 3), consumer_ref='single-pool-boundary')
        store = FeatureStore(tmp_path, database=db, fixture_only=complete_fixture,
                             indicator_registry=registry, clock=lambda: plan.cutoff_at)
        snapshot, bundle = store.materialize_and_publish(plan, rows, **args)
        files = _files(tmp_path)
        fresh = FeatureStore(tmp_path, database=db, fixture_only=complete_fixture,
                             indicator_registry=registry, clock=lambda: plan.cutoff_at)
        # 固定重试也必须在单连接上完成水合/预检/持久化，不改旧文件。
        repeated = fresh.materialize_and_publish(
            plan, rows, snapshot_id=snapshot.feature_snapshot_id, bundle_id=bundle.feature_bundle_id, **args,
        )
        assert repeated == (snapshot, bundle)
        ids = {instance: next(ref.feature_partition_id for ref in snapshot.feature_partition_refs
                              if ref.indicator_id == instance.indicator_id) for instance in plan.ordered_instances}
        correction, new_bundle = fresh.materialize_and_publish(
            plan, corrected, correction_of_snapshot_id=snapshot.feature_snapshot_id,
            correction_of_partition_ids=ids, **args,
        )
        assert correction.revision == 2 and correction.supersedes_id == snapshot.feature_snapshot_id
        for name, payload in files.items():
            assert _files(tmp_path)[name] == payload
        restarted = FeatureStore(tmp_path, database=db, fixture_only=complete_fixture, indicator_registry=registry)
        for saved in (bundle, new_bundle):
            if complete_fixture:
                assert restarted.consume_bundle(saved.feature_bundle_id, _preview()) == saved
            else:
                with pytest.raises(FeaturePublicationError, match='not certified'):
                    restarted.consume_bundle(saved.feature_bundle_id, _preview())
                assert restarted.published_bundle(saved.feature_bundle_id) == saved
        assert db.engine.pool.checkedout() == 0
    finally:
        db.close()


def test_shared_publication_transaction_commit_failure_removes_new_files_and_cache(
    isolated_postgres_database, tmp_path,
):
    from dataclasses import replace
    from src.repositories.platform import PostgresDatabase

    original = isolated_postgres_database
    db = PostgresDatabase.from_settings(replace(original.settings, pool_size=1, max_overflow=0, pool_timeout_seconds=1))
    try:
        upgrade_database(db.engine, LATEST)
        # 只在随机临时库加延迟触发器，让真实COMMIT失败；不mock SQL或跳过持久化层。
        with db.engine.begin() as connection:
            connection.execute(text("""
                CREATE FUNCTION b5_reject_commit() RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN RAISE EXCEPTION 'b5 isolated deferred commit failure'; END $$
            """))
            connection.execute(text("""
                CREATE CONSTRAINT TRIGGER b5_reject_commit AFTER INSERT ON feature_bundle
                DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION b5_reject_commit()
            """))
        plan, rows, registry = _boundary_plan('x' * 128)
        store = FeatureStore(tmp_path, database=db, indicator_registry=registry, clock=lambda: CUTOFF)
        before = _database_state(db)
        with pytest.raises(PlatformDatabaseError) as error:
            _publish(store, plan, rows)
        assert 'b5 isolated deferred commit failure' in str(error.value.__cause__)
        assert _database_state(db) == before
        assert not list(tmp_path.rglob('*.parquet'))
        assert not store._partitions and not store._snapshots and not store._bundles
        assert store._publication_session is None
        assert db.engine.pool.checkedout() == 0
        with db.engine.begin() as connection:
            connection.execute(text('DROP TRIGGER b5_reject_commit ON feature_bundle'))
            connection.execute(text('DROP FUNCTION b5_reject_commit()'))
        snapshot, bundle = _publish(store, plan, rows)
        with db.transaction() as session:
            from src.repositories.platform import FeatureRepository
            assert FeatureRepository.get_snapshot(session, snapshot.feature_snapshot_id) == snapshot
        assert store.published_bundle(bundle.feature_bundle_id) == bundle
    finally:
        db.close()
