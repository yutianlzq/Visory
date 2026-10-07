from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import text

from src.repositories.platform import FeatureRepository, PostgresDatabase, upgrade_database
from src.schemas.platform import (
    ConsumerKind,
    FeatureDependencyPlan,
    FeatureInstanceKey,
    FeatureRow,
    ResourceType,
    compute_content_hash,
    generate_resource_id,
)
from src.services.platform.feature_store import FeatureStore

UTC = timezone.utc
CUTOFF = datetime(2026, 1, 3, 18, 0, tzinfo=UTC)


def _rid(kind: ResourceType, seed: int) -> str:
    return generate_resource_id(kind, timestamp_ms=1_700_000_000_000 + seed, random_bits=seed)


def _instance() -> FeatureInstanceKey:
    parameters = {"period": 20}
    return FeatureInstanceKey(
        indicator_id="moving_average",
        definition_version="1.0.0",
        canonical_parameter_json='{"period":20}',
        parameter_hash=compute_content_hash(parameters),
        frequency="1d",
    )


def _plan() -> FeatureDependencyPlan:
    instance = _instance()
    return FeatureDependencyPlan(
        required_instances=(instance,),
        ordered_instances=(instance,),
        required_columns=("moving_average.value",),
        cutoff_at=CUTOFF,
        lookback_requirement=20,
        warmup_requirement=20,
    )


def _rows() -> dict[FeatureInstanceKey, tuple[FeatureRow, ...]]:
    instance = _instance()
    return {
        instance: (
            FeatureRow(
                entity_key="cn.stock:000001",
                trade_date=date(2026, 1, 3),
                indicator_id=instance.indicator_id,
                definition_version=instance.definition_version,
                value=Decimal("1.20"),
                value_type="decimal",
                unit="cny_per_share",
                available_at=datetime(2026, 1, 3, 17, 0, tzinfo=UTC),
                data_snapshot_id=_rid(ResourceType.DATA_SNAPSHOT, 1),
                calculation_run_id="run-wp0302",
            ),
        )
    }


def _publish(store: FeatureStore, *, consumer_ref: str, snapshot_id: str | None = None, bundle_id: str | None = None):
    return store.materialize_and_publish(
        _plan(),
        _rows(),
        data_snapshot_ids=(_rid(ResourceType.DATA_SNAPSHOT, 1),),
        quality_report_id=_rid(ResourceType.QUALITY_REPORT, 2),
        cutoff_at=CUTOFF,
        as_of_trade_date=date(2026, 1, 3),
        consumer_ref=consumer_ref,
        consumer_kind=ConsumerKind.FORMAL_BACKTEST,
        expected_entity_keys=("cn.stock:000001",),
        expected_trade_dates=(date(2026, 1, 3),),
        snapshot_id=snapshot_id,
        bundle_id=bundle_id,
    )


def test_feature_store_persists_atomic_publication_and_idempotent_formal_pin(
    isolated_postgres_database: PostgresDatabase,
    tmp_path: Path,
) -> None:
    database = isolated_postgres_database
    upgrade_database(database.engine)
    first_store = FeatureStore(tmp_path, database=database, clock=lambda: CUTOFF)
    first_snapshot, first_bundle = _publish(first_store, consumer_ref="strategy:db-one")
    partition_id = first_snapshot.feature_partition_refs[0].feature_partition_id

    second_store = FeatureStore(tmp_path, database=database, clock=lambda: CUTOFF)
    repeated_snapshot, repeated_bundle = _publish(
        second_store,
        consumer_ref="strategy:db-one",
        snapshot_id=first_snapshot.feature_snapshot_id,
        bundle_id=first_bundle.feature_bundle_id,
    )
    assert repeated_snapshot == first_snapshot
    assert repeated_bundle == first_bundle

    with database.transaction() as session:
        saved_partition = FeatureRepository.get_partition(session, partition_id)
        saved_snapshot = FeatureRepository.get_snapshot(session, first_snapshot.feature_snapshot_id)
        saved_bundle = FeatureRepository.get_bundle(session, first_bundle.feature_bundle_id)
    assert saved_partition is not None
    assert saved_partition.reference_count == 1
    assert saved_partition.retention_class.value == "PINNED"
    assert saved_snapshot == first_snapshot
    assert saved_bundle == first_bundle
    assert second_store.read_partition_payload(partition_id)

    _, second_bundle = _publish(second_store, consumer_ref="strategy:db-two")
    assert second_bundle.bundle_hash != first_bundle.bundle_hash
    with database.transaction() as session:
        saved_partition = FeatureRepository.get_partition(session, partition_id)
    assert saved_partition is not None
    assert saved_partition.reference_count == 2


def test_feature_store_control_plane_rollback_removes_staged_files_and_rows(
    isolated_postgres_database: PostgresDatabase,
    tmp_path: Path,
) -> None:
    database = isolated_postgres_database
    upgrade_database(database.engine)

    class FailingRepository(FeatureRepository):
        @staticmethod
        def add_bundle(session, record):  # type: ignore[no-untyped-def]
            raise RuntimeError("injected feature bundle registry failure")

    failing_store = FeatureStore(
        tmp_path,
        database=database,
        repository=FailingRepository(),
        clock=lambda: CUTOFF,
    )
    with pytest.raises(RuntimeError, match="injected feature bundle registry failure"):
        _publish(failing_store, consumer_ref="strategy:rollback")

    assert not list((tmp_path / "storage" / "app").rglob("*.parquet"))
    with database.transaction() as session:
        assert session.execute(text("SELECT count(*) FROM feature_partition")).scalar_one() == 0
        assert session.execute(text("SELECT count(*) FROM feature_snapshot")).scalar_one() == 0
        assert session.execute(text("SELECT count(*) FROM feature_bundle")).scalar_one() == 0

    recovered_store = FeatureStore(tmp_path, database=database, clock=lambda: CUTOFF)
    snapshot, bundle = _publish(recovered_store, consumer_ref="strategy:rollback")
    with database.transaction() as session:
        assert FeatureRepository.get_snapshot(session, snapshot.feature_snapshot_id) is not None
        assert FeatureRepository.get_bundle(session, bundle.feature_bundle_id) is not None


def test_feature_store_rehydrates_fixed_partition_references_across_corrections(
    isolated_postgres_database: PostgresDatabase,
    tmp_path: Path,
) -> None:
    database = isolated_postgres_database
    upgrade_database(database.engine)
    store = FeatureStore(tmp_path, database=database, clock=lambda: CUTOFF)
    first_instance = _instance()
    second_instance = FeatureInstanceKey(
        indicator_id="moving_average",
        definition_version="1.0.0",
        canonical_parameter_json='{"period":30}',
        parameter_hash=compute_content_hash({"period": 30}),
        frequency="1d",
    )
    plan = FeatureDependencyPlan(
        required_instances=(first_instance, second_instance),
        ordered_instances=(first_instance, second_instance),
        required_columns=("moving_average.value",),
        cutoff_at=CUTOFF,
        lookback_requirement=20,
        warmup_requirement=20,
    )

    def rows(first_value: str) -> dict[FeatureInstanceKey, tuple[FeatureRow, ...]]:
        return {
            instance: (
                FeatureRow(
                    entity_key="cn.stock:000001",
                    trade_date=date(2026, 1, 3),
                    indicator_id=instance.indicator_id,
                    definition_version=instance.definition_version,
                    value=Decimal(first_value if instance is first_instance else "2.20"),
                    value_type="decimal",
                    unit="cny_per_share",
                    available_at=datetime(2026, 1, 3, 17, 0, tzinfo=UTC),
                    data_snapshot_id=_rid(ResourceType.DATA_SNAPSHOT, 1),
                    calculation_run_id=f"run-{instance.parameter_hash}",
                ),
            )
            for instance in plan.ordered_instances
        }

    def publish(
        values: dict[FeatureInstanceKey, tuple[FeatureRow, ...]],
        *,
        correction_of_snapshot_id: str | None = None,
        correction_of_partition_ids: dict[FeatureInstanceKey, str] | None = None,
    ):
        return store.materialize_and_publish(
            plan,
            values,
            data_snapshot_ids=(_rid(ResourceType.DATA_SNAPSHOT, 1),),
            quality_report_id=_rid(ResourceType.QUALITY_REPORT, 2),
            cutoff_at=CUTOFF,
            as_of_trade_date=date(2026, 1, 3),
            consumer_ref="strategy:correction-rehydration",
            consumer_kind=ConsumerKind.FORMAL_BACKTEST,
            expected_entity_keys=("cn.stock:000001",),
            expected_trade_dates=(date(2026, 1, 3),),
            correction_of_snapshot_id=correction_of_snapshot_id,
            correction_of_partition_ids=correction_of_partition_ids,
        )

    first_snapshot, _ = publish(rows("1.20"))
    first_partition = next(
        ref
        for ref in first_snapshot.feature_partition_refs
        if (
            "parameter=" + first_instance.parameter_hash[7:]
            in store.published_partition(ref.feature_partition_id).partition_key
        )
    )

    second_snapshot, _ = publish(
        rows("1.30"),
        correction_of_snapshot_id=first_snapshot.feature_snapshot_id,
        correction_of_partition_ids={first_instance: first_partition.feature_partition_id},
    )
    unchanged_id = next(
        ref.feature_partition_id
        for ref in first_snapshot.feature_partition_refs
        if ref.feature_partition_id != first_partition.feature_partition_id
    )
    corrected_first_id = next(
        ref.feature_partition_id
        for ref in second_snapshot.feature_partition_refs
        if ref.feature_partition_id != unchanged_id
    )

    third_snapshot, _ = publish(
        rows("1.40"),
        correction_of_snapshot_id=second_snapshot.feature_snapshot_id,
        correction_of_partition_ids={first_instance: corrected_first_id},
    )

    assert unchanged_id in {ref.feature_partition_id for ref in third_snapshot.feature_partition_refs}
    assert third_snapshot.supersedes_id == second_snapshot.feature_snapshot_id



def test_postgres_correction_same_bytes_new_lineage_and_fixed_refs_survive_pin(
    isolated_postgres_database: PostgresDatabase,
    tmp_path: Path,
) -> None:
    database = isolated_postgres_database
    upgrade_database(database.engine)
    a = _instance()
    b = a.model_copy(update={"indicator_id": "volatility"})
    c = a.model_copy(update={"indicator_id": "adv20"})
    plan = FeatureDependencyPlan(
        required_instances=(b, c), ordered_instances=(a, b, c),
        dependency_edges=({"dependency": a, "consumer": b},),
        required_columns=("moving_average.value", "volatility.value", "adv20.value"),
        cutoff_at=CUTOFF, lookback_requirement=20, warmup_requirement=20,
    )
    base = _rows()[a][0]
    rows = {a: (base,), b: (base.model_copy(update={"indicator_id": "volatility", "unit": "ratio"}),),
            c: (base.model_copy(update={"indicator_id": "adv20", "unit": "shares"}),)}
    args = {"data_snapshot_ids": (_rid(ResourceType.DATA_SNAPSHOT, 1),), "cutoff_at": CUTOFF,
            "as_of_trade_date": date(2026, 1, 3), "consumer_ref": "strategy:lineage"}
    store = FeatureStore(tmp_path, database=database, clock=lambda: CUTOFF)
    first, first_bundle = store.materialize_and_publish(plan, rows, **args)
    old = {ref.indicator_id: ref for ref in first.feature_partition_refs}
    _, formal_bundle = store.materialize_and_publish(
        plan, rows, **(args | {"consumer_ref": "strategy:formal-lineage"}),
        consumer_kind=ConsumerKind.FORMAL_BACKTEST, expected_entity_keys=(base.entity_key,),
        expected_trade_dates=(base.trade_date,),
    )
    rows[a] = (base.model_copy(update={"value": Decimal("1.30")}),)
    restarted = FeatureStore(tmp_path, database=database, clock=lambda: CUTOFF)
    second, _ = restarted.materialize_and_publish(
        plan, rows, **args, correction_of_snapshot_id=first.feature_snapshot_id,
        correction_of_partition_ids={instance: old[instance.indicator_id].feature_partition_id for instance in (a, b)},
    )
    new = {ref.indicator_id: ref for ref in second.feature_partition_refs}
    assert new[c.indicator_id] == old[c.indicator_id]
    assert new[b.indicator_id].partition_hash == old[b.indicator_id].partition_hash
    assert new[b.indicator_id].feature_partition_id != old[b.indicator_id].feature_partition_id
    assert new[b.indicator_id].storage_ref.relative_path != old[b.indicator_id].storage_ref.relative_path
    with database.transaction() as session:
        assert FeatureRepository.get_snapshot(session, first.feature_snapshot_id) == first
        assert FeatureRepository.get_bundle(session, first_bundle.feature_bundle_id) == first_bundle
        assert FeatureRepository.get_bundle(session, formal_bundle.feature_bundle_id) == formal_bundle
        assert FeatureRepository.get_snapshot(session, second.feature_snapshot_id) == second



def test_concurrent_publication_cannot_adopt_files_pending_rollback(
    isolated_postgres_database: PostgresDatabase, tmp_path: Path,
) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from src.services.platform.feature_store import FeaturePublicationError

    database = isolated_postgres_database
    upgrade_database(database.engine)
    entered, release = Event(), Event()

    class PausedFailingRepository(FeatureRepository):
        @staticmethod
        def add_partition(session, record):
            entered.set()
            assert release.wait(15), "test failed to release paused publisher"
            raise RuntimeError("injected concurrent rollback")

    failing = FeatureStore(tmp_path, database=database, repository=PausedFailingRepository(), clock=lambda: CUTOFF)
    other = FeatureStore(tmp_path, database=database, clock=lambda: CUTOFF)
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_publish, failing, consumer_ref="strategy:concurrent-failing")
        try:
            assert entered.wait(15)
            with pytest.raises(FeaturePublicationError, match="publication.*busy"):
                _publish(other, consumer_ref="strategy:concurrent-success")
        finally:
            release.set()
        with pytest.raises(RuntimeError, match="injected concurrent rollback"):
            future.result(timeout=15)
    snapshot, bundle = _publish(other, consumer_ref="strategy:concurrent-success")
    with database.transaction() as session:
        assert FeatureRepository.get_snapshot(session, snapshot.feature_snapshot_id) == snapshot
        assert FeatureRepository.get_bundle(session, bundle.feature_bundle_id) == bundle
    assert other.read_partition_payload(snapshot.feature_partition_refs[0].feature_partition_id)
