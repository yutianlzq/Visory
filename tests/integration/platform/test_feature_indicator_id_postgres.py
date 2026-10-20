"""B5 real PostgreSQL migration, fixed-fixture publication and guarded rollback."""
from datetime import date

import pytest
from sqlalchemy import inspect, select, text

from src.repositories.platform import (
    FeatureRepository, PlatformDatabaseError, downgrade_database, get_migration_status, upgrade_database,
)
from src.repositories.platform.feature import metadata
from src.schemas.platform import ConsumerRequirement, FeatureInstanceKey, FeatureMaterializationError, compute_content_hash
from src.services.platform.feature_store import FeatureStore, FeaturePublicationError
from src.services.platform.indicator_registry import IndicatorRegistry
from tests.platform.test_feature_indicator_id_contract import LONG_IDS
from tests.platform.test_feature_store_contracts import _row, _single_plan, _publish, CUTOFF
from tests.platform.test_indicator_registry import _definition
from tests.platform.test_market_sentiment import complete_score_fixture, market_day, publish_market
from src.services.platform.market_sentiment import evaluate_market_days

OLD = '0013_wp0302_feature_store'
INTERMEDIATE = '0014_wp0303_indicator_id'
NEW = '0015_wp0303_partition_key'
TABLES = ('feature_partition', 'feature_snapshot_partition_ref', 'feature_bundle_partition_ref')
ALL_TABLES = tuple(sorted(metadata.tables))


def _database_state(db):
    with db.engine.connect() as connection:
        inspector = inspect(connection)
        columns = {
            name: tuple((c['name'], str(c['type']), c['nullable']) for c in inspector.get_columns(name))
            for name in ALL_TABLES
        }
        constraints = tuple(connection.execute(text(
            "SELECT c.relname, con.conname, pg_get_constraintdef(con.oid) "
            "FROM pg_constraint con JOIN pg_class c ON c.oid = con.conrelid "
            "WHERE c.relname LIKE 'feature_%' AND c.relnamespace = 'public'::regnamespace "
            "ORDER BY c.relname, con.conname"
        )).all())
        indexes = tuple(connection.execute(text(
            "SELECT tablename, indexname, indexdef FROM pg_indexes "
            "WHERE schemaname = 'public' AND tablename LIKE 'feature_%' ORDER BY tablename, indexname"
        )).all())
        data = {
            name: tuple(connection.execute(select(metadata.tables[name]).order_by(*metadata.tables[name].primary_key.columns)).all())
            for name in ALL_TABLES
        }
        revision = connection.execute(text('SELECT version_num FROM alembic_version')).scalar_one()
    return columns, constraints, indexes, data, revision


def _assert_width(db, width):
    with db.engine.connect() as connection:
        for name in TABLES:
            column = next(c for c in inspect(connection).get_columns(name) if c['name'] == 'indicator_id')
            assert column['type'].length == width
            assert not column['nullable']


def _files(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file()}


def _preview():
    return ConsumerRequirement(consumer_id='isolated_preview', consumer_kind='PREVIEW',
                               required_capabilities=('market_emotion',), allow_provisional=True,
                               accepted_publication_statuses=('CERTIFIED', 'PROVISIONAL'), min_quality_status='PARTIAL')


def _boundary_plan(indicator_id):
    instance = FeatureInstanceKey(
        indicator_id=indicator_id, definition_version='1.0.0', canonical_parameter_json='{}',
        parameter_hash=compute_content_hash({}), frequency='1d',
    )
    return _single_plan(instance), {instance: (_row('cn.stock:000001', date(2026, 1, 3)).model_copy(
        update={'indicator_id': indicator_id, 'unit': 'shares'}
    ),)}, IndicatorRegistry((_definition(indicator_id=indicator_id),))


@pytest.mark.parametrize('width', [64, 65, 128])
def test_old_revision_length_boundaries_fail_before_files_or_writes(isolated_postgres_database, tmp_path, width):
    db = isolated_postgres_database
    upgrade_database(db.engine, OLD)
    plan, rows, registry = _boundary_plan('x' * width)
    store = FeatureStore(tmp_path / 'database', database=db, indicator_registry=registry, clock=lambda: CUTOFF)
    if width == 64:
        _publish(store, plan, rows)
        _assert_width(db, 64)
        return
    before = _database_state(db), _files(tmp_path / 'database')
    with pytest.raises(FeatureMaterializationError, match='existing PostgreSQL indicator_id limit'):
        _publish(store, plan, rows)
    assert (_database_state(db), _files(tmp_path / 'database')) == before
    # Direct Repository entry points must reject before DML, even with widened Python metadata.
    memory = FeatureStore(tmp_path / 'memory', indicator_registry=registry, clock=lambda: CUTOFF)
    snapshot, bundle = _publish(memory, plan, rows)
    partition = memory.published_partition(snapshot.feature_partition_refs[0].feature_partition_id)
    for method, record in (
        (FeatureRepository.add_partition, partition), (FeatureRepository.add_snapshot, snapshot),
        (FeatureRepository.add_bundle, bundle),
    ):
        with pytest.raises(ValueError, match='existing PostgreSQL indicator_id limit'):
            with db.transaction() as session:
                method(session, record)
        assert _database_state(db) == before[0]


@pytest.mark.parametrize('indicator_id', LONG_IDS)
def test_old_revision_rejects_each_actual_long_id(isolated_postgres_database, tmp_path, indicator_id):
    db = isolated_postgres_database
    upgrade_database(db.engine, OLD)
    plan, rows, _, source = complete_score_fixture()
    # Preserve original Definition IDs and rows; select the actual long instance for each entry point.
    instance = next(i for i in plan.ordered_instances if i.indicator_id == indicator_id)
    direct_plan = _single_plan(instance)
    store = FeatureStore(tmp_path, database=db, fixture_only=True, clock=lambda: plan.cutoff_at)
    before = _database_state(db), _files(tmp_path)
    with pytest.raises(FeatureMaterializationError, match='existing PostgreSQL indicator_id limit'):
        store.materialize_and_publish(direct_plan, {instance: rows[instance]}, data_snapshot_ids=(source,),
                                      cutoff_at=CUTOFF, as_of_trade_date=date(2026, 1, 3), consumer_ref='fixture')
    assert (_database_state(db), _files(tmp_path)) == before


@pytest.mark.parametrize('width', [64, 65, 128])
def test_new_revision_boundary_publication_round_trip(isolated_postgres_database, tmp_path, width):
    db = isolated_postgres_database
    upgrade_database(db.engine, OLD)
    upgrade_database(db.engine, NEW)
    plan, rows, registry = _boundary_plan('x' * width)
    store = FeatureStore(tmp_path, database=db, indicator_registry=registry, clock=lambda: CUTOFF)
    snapshot, bundle = _publish(store, plan, rows)
    fresh = FeatureStore(tmp_path, database=db, indicator_registry=registry, clock=lambda: CUTOFF)
    # 合成非市场边界 Snapshot 未认证任何能力；固定读取可水合，但不得伪造消费权限。
    with pytest.raises(FeaturePublicationError, match='not certified'):
        fresh.consume_bundle(bundle.feature_bundle_id, _preview())
    assert fresh.published_bundle(bundle.feature_bundle_id) == bundle
    assert fresh.published_snapshot(snapshot.feature_snapshot_id) == snapshot
    _assert_width(db, 128)
    with db.engine.connect() as connection:
        for name in TABLES:
            assert connection.execute(select(metadata.tables[name].c.indicator_id)).scalar_one() == 'x' * width


@pytest.mark.parametrize('indicator_id', LONG_IDS)
def test_actual_long_ids_with_valid_partition_keys_persist_without_truncation(isolated_postgres_database, tmp_path, indicator_id):
    from src.schemas.platform import FeatureDependencyPlan

    db = isolated_postgres_database
    upgrade_database(db.engine, OLD)
    upgrade_database(db.engine, NEW)
    full_plan, rows, _, source = complete_score_fixture()
    instance = next(item for item in full_plan.ordered_instances if item.indicator_id == indicator_id)
    # 三个实际长 ID 原样落库；下方另验收完整评分 DAG，不改变 fixture。
    plan = FeatureDependencyPlan(
        required_instances=(instance,), ordered_instances=(instance,),
        required_columns=(indicator_id + '.value',), cutoff_at=full_plan.cutoff_at,
        universe_scope_hash=full_plan.universe_scope_hash,
        lookback_requirement=full_plan.lookback_requirement, warmup_requirement=full_plan.warmup_requirement,
    )
    store = FeatureStore(tmp_path, database=db, fixture_only=True, clock=lambda: plan.cutoff_at)
    snapshot, bundle = store.materialize_and_publish(
        plan, {instance: rows[instance]}, data_snapshot_ids=(source,), cutoff_at=plan.cutoff_at,
        as_of_trade_date=date(2026, 3, 6), consumer_ref='isolated-long-id-boundary',
    )
    fresh = FeatureStore(tmp_path, database=db, fixture_only=True)
    assert fresh.consume_bundle(bundle.feature_bundle_id, _preview()) == bundle
    assert fresh.published_snapshot(snapshot.feature_snapshot_id) == snapshot
    with db.engine.connect() as connection:
        for name in TABLES:
            assert connection.execute(select(metadata.tables[name].c.indicator_id)).scalar_one() == indicator_id


@pytest.mark.parametrize('table', TABLES)
def test_downgrade_checks_every_column_before_any_narrowing(isolated_postgres_database, tmp_path, table):
    db = isolated_postgres_database
    upgrade_database(db.engine, OLD)
    plan, rows, registry = _boundary_plan('x' * 64)
    _publish(FeatureStore(tmp_path, database=db, indicator_registry=registry, clock=lambda: CUTOFF), plan, rows)
    upgrade_database(db.engine, INTERMEDIATE)
    # Independently exercise each stored column (not merely the partition table).
    with db.engine.begin() as connection:
        connection.execute(metadata.tables[table].update().values(indicator_id='x' * 65))
    before = _database_state(db), _files(tmp_path)
    with pytest.raises(PlatformDatabaseError) as error:
        downgrade_database(db.engine, OLD)
    assert 'longer than 64' in str(error.value.__cause__)
    assert (_database_state(db), _files(tmp_path)) == before
    _assert_width(db, 128)


def test_safe_downgrade_and_reupgrade_preserve_short_data_constraints_indexes_and_refs(isolated_postgres_database, tmp_path):
    db = isolated_postgres_database
    upgrade_database(db.engine, OLD)
    plan, rows, registry = _boundary_plan('x' * 64)
    snapshot, bundle = _publish(FeatureStore(tmp_path, database=db, indicator_registry=registry, clock=lambda: CUTOFF), plan, rows)
    old = _database_state(db)
    files = _files(tmp_path)
    upgrade_database(db.engine, NEW)
    new = _database_state(db)
    assert new[1:4] == old[1:4]
    for name in ALL_TABLES:
        expected = tuple((n, 'VARCHAR(128)' if name in TABLES and n == 'indicator_id' else
                          'VARCHAR(386)' if name == 'feature_partition' and n == 'partition_key' else t, nullable)
                         for n, t, nullable in old[0][name])
        assert new[0][name] == expected
    assert new[4] == NEW
    downgrade_database(db.engine, OLD)
    assert _database_state(db) == old
    assert _files(tmp_path) == files
    upgrade_database(db.engine, NEW)
    assert _database_state(db) == new
    fresh = FeatureStore(tmp_path, database=db, indicator_registry=registry)
    # 合成非市场边界 Snapshot 未认证任何能力；固定读取可水合，但不得伪造消费权限。
    with pytest.raises(FeaturePublicationError, match='not certified'):
        fresh.consume_bundle(bundle.feature_bundle_id, _preview())
    assert fresh.published_bundle(bundle.feature_bundle_id) == bundle
    assert fresh.published_snapshot(snapshot.feature_snapshot_id) == snapshot


def test_complete_score_dag_migration_fixed_consumption_restart_and_correction(isolated_postgres_database, tmp_path):
    db = isolated_postgres_database
    upgrade_database(db.engine, OLD)
    # Existing short-ID fixed artifacts must survive widening and all later fixture work.
    batch = evaluate_market_days([market_day()])[0]
    short_store = FeatureStore(tmp_path / 'short', database=db, clock=lambda: batch.rows[0].available_at)
    _, short_snapshot, short_bundle = publish_market(short_store, batch)
    old = _database_state(db)
    short_files = _files(tmp_path / 'short')
    upgrade_database(db.engine, NEW)
    # 完整发布/重启/Correction 使用统一主线 head；其他边界测试仍精确验证 0014/0015。
    upgrade_database(db.engine)
    assert _database_state(db)[1:4] == old[1:4]
    plan, rows, original, source = complete_score_fixture()
    _, corrected_rows, corrected, _ = complete_score_fixture(correction=True)
    assert original[:60] == corrected[:60]
    assert all(original[i].smoothed != corrected[i].smoothed for i in range(60, 65))
    assert original[60].state != corrected[60].state
    root = tmp_path / 'score-fixture'
    store = FeatureStore(root, database=db, fixture_only=True, clock=lambda: plan.cutoff_at)
    args = dict(data_snapshot_ids=(source,), cutoff_at=plan.cutoff_at,
                as_of_trade_date=date(2026, 3, 6), consumer_ref='isolated-complete-score-fixture')
    before_publication = _database_state(db)
    try:
        snapshot, bundle = store.materialize_and_publish(plan, rows, **args)
    except PlatformDatabaseError:
        # 真实链路失败也须证明没有部分控制面写入或 Parquet 残留；不吞掉失败。
        assert _database_state(db) == before_publication
        assert not list(root.rglob('*.parquet'))
        assert _files(tmp_path / 'short') == short_files
        raise
    assert {r.indicator_id for r in snapshot.feature_partition_refs} == {i.indicator_id for i in plan.ordered_instances}
    assert set(LONG_IDS) <= {r.indicator_id for r in snapshot.feature_partition_refs}
    files = _files(root)
    before_correction = _database_state(db)
    fresh = FeatureStore(root, database=db, fixture_only=True, clock=lambda: plan.cutoff_at)
    preview = ConsumerRequirement(consumer_id='isolated_preview', consumer_kind='PREVIEW',
                                  required_capabilities=('market_emotion',), allow_provisional=True,
                                  accepted_publication_statuses=('PROVISIONAL',), min_quality_status='PARTIAL')
    assert fresh.consume_bundle(bundle.feature_bundle_id, preview) == bundle
    ids = {instance: next(ref.feature_partition_id for ref in snapshot.feature_partition_refs
                          if ref.indicator_id == instance.indicator_id) for instance in plan.ordered_instances}
    correction, new_bundle = fresh.materialize_and_publish(
        plan, corrected_rows, correction_of_snapshot_id=snapshot.feature_snapshot_id,
        correction_of_partition_ids=ids, **args,
    )
    assert correction.revision == 2 and correction.supersedes_id == snapshot.feature_snapshot_id
    assert (correction.as_of_trade_date, correction.cutoff_at, correction.dependency_plan_hash, correction.definition_refs) == (
        snapshot.as_of_trade_date, snapshot.cutoff_at, snapshot.dependency_plan_hash, snapshot.definition_refs,
    )
    assert correction.manifest_hash != snapshot.manifest_hash and new_bundle.bundle_hash != bundle.bundle_hash
    restarted = FeatureStore(root, database=db, fixture_only=True, clock=lambda: plan.cutoff_at)
    assert restarted.consume_bundle(bundle.feature_bundle_id, preview) == bundle
    assert restarted.consume_bundle(new_bundle.feature_bundle_id, preview) == new_bundle
    for old_ref in snapshot.feature_partition_refs:
        assert restarted.published_partition(old_ref.feature_partition_id).revision == 1
        assert _files(root)[next(p for p in files if p.endswith(old_ref.storage_ref.relative_path))] == files[
            next(p for p in files if p.endswith(old_ref.storage_ref.relative_path))]
    from src.schemas.platform import FeaturePartition
    from src.services.platform.feature_store import _partition_key

    for instance in plan.ordered_instances:
        old_ref = next(ref for ref in snapshot.feature_partition_refs if ref.indicator_id == instance.indicator_id)
        new_ref = next(ref for ref in correction.feature_partition_refs if ref.indicator_id == instance.indicator_id)
        previous = restarted.published_partition(old_ref.feature_partition_id)
        current = restarted.published_partition(new_ref.feature_partition_id)
        assert current.revision == 2 and current.supersedes_id == previous.feature_partition_id
        assert current.partition_key == previous.partition_key == _partition_key(instance, None, None)
        assert restarted.read_partition_payload(previous.feature_partition_id) == FeaturePartition.parquet_bytes(rows[instance])
        assert restarted.read_partition_payload(current.feature_partition_id) == FeaturePartition.parquet_bytes(corrected_rows[instance])
    for record in (snapshot, correction):
        assert record.publication_status.value == 'PROVISIONAL'
        assert record.certified_capabilities == ()
        assert record.missing_capabilities == ('market_breadth', 'market_emotion')
    with db.engine.connect() as connection:
        for name in TABLES:
            ids_in_database = set(connection.execute(select(metadata.tables[name].c.indicator_id)).scalars())
            assert set(LONG_IDS) <= ids_in_database
    after = _database_state(db)
    for name in ALL_TABLES:
        for record in before_correction[3][name]:
            assert record in after[3][name]
    for consumer in ('formal', 'paper'):
        requirement = ConsumerRequirement(consumer_id=consumer, consumer_kind='FORMAL_BACKTEST',
                                          required_capabilities=('backtest_core', 'market_emotion'),
                                          accepted_publication_statuses=('CERTIFIED',))
        with pytest.raises(FeaturePublicationError, match='capability'):
            restarted.consume_bundle(new_bundle.feature_bundle_id, requirement)
    before_rejection = _database_state(db), _files(root)
    with pytest.raises(FeaturePublicationError, match='capability'):
        restarted.materialize_and_publish(plan, rows, consumer_kind='FORMAL_BACKTEST', **args)
    with pytest.raises(FeatureMaterializationError, match='fixture cannot certify real inputs'):
        FeatureStore(root, database=db, clock=lambda: plan.cutoff_at).materialize_and_publish(plan, rows, **args)
    assert (_database_state(db), _files(root)) == before_rejection
    # Refuse invalid Correction identity without touching previous files or SQL records.
    before = _database_state(db), _files(root)
    with pytest.raises(FeaturePublicationError, match='logical manifest identity'):
        restarted.materialize_and_publish(
            plan, corrected_rows, correction_of_snapshot_id=correction.feature_snapshot_id,
            correction_of_partition_ids={
                instance: next(ref.feature_partition_id for ref in correction.feature_partition_refs
                               if ref.indicator_id == instance.indicator_id) for instance in plan.ordered_instances
            }, **(args | {'as_of_trade_date': date(2026, 3, 7)}),
        )
    assert (_database_state(db), _files(root)) == before
    with pytest.raises(PlatformDatabaseError) as error:
        downgrade_database(db.engine, OLD)
    assert 'longer than 255' in str(error.value.__cause__)
    assert (_database_state(db), _files(root)) == before
    _assert_width(db, 128)
    assert get_migration_status(db.engine).is_at_head
    assert _files(tmp_path / 'short') == short_files
    short_fresh = FeatureStore(tmp_path / 'short', database=db)
    assert short_fresh.consume_bundle(short_bundle.feature_bundle_id, _preview()) == short_bundle
    assert short_fresh.published_snapshot(short_snapshot.feature_snapshot_id) == short_snapshot


def test_new_revision_repository_accepts_128_without_changing_any_other_column(isolated_postgres_database):
    from tests.integration.platform.test_feature_repository import _records
    from src.schemas.platform import FeaturePartitionRef, FeatureSnapshot, FeatureBundle

    db = isolated_postgres_database
    upgrade_database(db.engine, OLD)
    upgrade_database(db.engine, NEW)
    original, old_snapshot, old_bundle = _records()
    # Isolate the indicator column boundary from the separate Store partition_key length problem.
    partition = type(original).model_validate(original.model_dump() | {'indicator_id': 'x' * 128})
    ref = FeaturePartitionRef.from_partition(partition)
    snapshot = FeatureSnapshot.build(**(old_snapshot.model_dump(exclude={'manifest_hash'}) | {
        'feature_partition_refs': (ref,), 'definition_refs': ('x' * 128 + '@1.0.0',),
    }))
    bundle = FeatureBundle.build(**(old_bundle.model_dump(exclude={'bundle_hash'}) | {
        'required_partition_refs': (ref,), 'required_columns': ('x' * 128 + '.value',),
    }))
    with db.transaction() as session:
        FeatureRepository.add_partition(session, partition)
        FeatureRepository.add_snapshot(session, snapshot)
        FeatureRepository.add_bundle(session, bundle)
    with db.transaction() as session:
        assert FeatureRepository.get_partition(session, partition.feature_partition_id).indicator_id == 'x' * 128
        assert FeatureRepository.get_snapshot(session, snapshot.feature_snapshot_id) == snapshot
        assert FeatureRepository.get_bundle(session, bundle.feature_bundle_id) == bundle
    _assert_width(db, 128)


@pytest.mark.parametrize('entry', ['partition', 'snapshot', 'bundle'])
def test_repository_rejects_129_even_if_model_validation_is_bypassed(isolated_postgres_database, entry):
    from tests.integration.platform.test_feature_repository import _records

    db = isolated_postgres_database
    upgrade_database(db.engine, NEW)
    partition, snapshot, bundle = _records()
    records = {
        'partition': partition.model_copy(update={'indicator_id': 'x' * 129}),
        'snapshot': snapshot.model_copy(update={'feature_partition_refs': (
            snapshot.feature_partition_refs[0].model_copy(update={'indicator_id': 'x' * 129}),
        )}),
        'bundle': bundle.model_copy(update={'required_partition_refs': (
            bundle.required_partition_refs[0].model_copy(update={'indicator_id': 'x' * 129}),
        )}),
    }
    before = _database_state(db)
    with pytest.raises(ValueError, match='128 character contract'):
        with db.transaction() as session:
            getattr(FeatureRepository, 'add_' + entry)(session, records[entry])
    assert _database_state(db) == before


def test_actual_column_preflight_lock_prevents_concurrent_downgrade(isolated_postgres_database):
    from alembic import command
    from sqlalchemy.exc import DBAPIError
    from src.repositories.platform.migrations import _alembic_config

    db = isolated_postgres_database
    upgrade_database(db.engine, NEW)
    before = _database_state(db)
    with db.transaction() as session:
        FeatureRepository.validate_indicator_ids(session, ('x' * 65,))
        with pytest.raises(DBAPIError) as error:
            with db.engine.begin() as connection:
                connection.execute(text("SET LOCAL lock_timeout = '250ms'"))
                config = _alembic_config()
                config.attributes['connection'] = connection
                command.downgrade(config, OLD)
        assert error.value.orig.sqlstate == "55P03"  # lock_not_available，不能用任意 SQL 错误冒充互斥证据。
    assert _database_state(db) == before
    downgrade_database(db.engine, OLD)
    _assert_width(db, 64)
