from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from src.repositories.platform import FeatureRepository, PlatformDatabaseError, PostgresDatabase, downgrade_database, get_migration_status, upgrade_database
from src.schemas.platform import (
    ConsumerKind,
    FeatureBundle,
    FeaturePartition,
    FeaturePartitionRef,
    FeatureRow,
    FeatureSnapshot,
    FeatureSnapshotType,
    PublicationStatus,
    QualityStatus,
    RevisionKind,
    ResourceType,
    RetentionClass,
    StorageBackend,
    StorageNamespace,
    StorageRef,
    compute_content_hash,
    generate_resource_id,
)

UTC = timezone.utc
NOW = datetime(2026, 1, 3, 18, 0, tzinfo=UTC)


def _rid(kind: ResourceType, seed: int) -> str:
    return generate_resource_id(kind, timestamp_ms=1_700_000_000_000 + seed, random_bits=seed)


def _records() -> tuple[FeaturePartition, FeatureSnapshot, FeatureBundle]:
    data_snapshot_id = _rid(ResourceType.DATA_SNAPSHOT, 1)
    partition_id = _rid(ResourceType.FEATURE_PARTITION, 2)
    quality_report_id = _rid(ResourceType.QUALITY_REPORT, 3)
    row = FeatureRow(
        entity_key="cn.stock:000001",
        trade_date=date(2026, 1, 3),
        indicator_id="moving_average",
        definition_version="1.0.0",
        value=Decimal("1.20"),
        value_type="decimal",
        unit="cny_per_share",
        available_at=datetime(2026, 1, 3, 17, 30, tzinfo=UTC),
        data_snapshot_id=data_snapshot_id,
        calculation_run_id="run-1",
    )
    partition_hash = FeaturePartition.compute_hash((row,))
    parquet_size = len(FeaturePartition.parquet_bytes((row,)))
    partition = FeaturePartition.build_from_rows(
        (row,),
        partition_id=partition_id,
        data_snapshot_ids=(data_snapshot_id,),
        partition_key="2026-01-03",
        storage_ref=StorageRef(
            storage_backend=StorageBackend.LOCAL_FS,
            storage_namespace=StorageNamespace.APP,
            relative_path="features/moving_average/2026-01-03.parquet",
            content_hash=partition_hash,
            media_type="application/vnd.apache.parquet",
            size_bytes=parquet_size,
        ),
        quality_report_id=quality_report_id,
        cutoff_at=NOW,
        created_at=NOW,
        published_at=NOW,
    )
    snapshot = FeatureSnapshot.build(
        feature_snapshot_id=_rid(ResourceType.FEATURE_SNAPSHOT, 4),
        snapshot_type=FeatureSnapshotType.CLOSE_CORE,
        as_of_trade_date=date(2026, 1, 3),
        cutoff_at=NOW,
        data_snapshot_ids=(data_snapshot_id,),
        feature_partition_refs=(FeaturePartitionRef.from_partition(partition),),
        dependency_plan_hash=compute_content_hash({"plan": "repository-test"}),
        definition_refs=("moving_average@1.0.0",),
        publication_status=PublicationStatus.CERTIFIED,
        quality_status=QualityStatus.COMPLETE,
        max_source_available_at=row.available_at,
        revision=1,
        created_at=NOW,
        published_at=NOW,
    )
    bundle = FeatureBundle.build(
        feature_bundle_id=_rid(ResourceType.FEATURE_BUNDLE, 5),
        feature_snapshot_ids=(snapshot.feature_snapshot_id,),
        dependency_plan_hash=snapshot.dependency_plan_hash,
        required_partition_refs=(FeaturePartitionRef.from_partition(partition),),
        required_columns=("moving_average.value",),
        consumer_ref="strategy:repository-test",
        consumer_kind=ConsumerKind.FORMAL_BACKTEST,
        cutoff_at=NOW,
        date_from=date(2026, 1, 3),
        date_to=date(2026, 1, 3),
    )
    return partition, snapshot, bundle


def test_feature_repository_round_trip_and_pin_is_transactional(
    isolated_postgres_database: PostgresDatabase,
) -> None:
    database = isolated_postgres_database
    upgrade_database(database.engine)
    partition, snapshot, bundle = _records()
    repository = FeatureRepository()

    with database.transaction() as session:
        repository.add_partition(session, partition)
        repository.add_snapshot(session, snapshot)
        repository.add_bundle(session, bundle)

    with database.transaction() as session:
        saved_partition = repository.get_partition(session, partition.feature_partition_id)
        saved_snapshot = repository.get_snapshot(session, snapshot.feature_snapshot_id)
        saved_bundle = repository.get_bundle(session, bundle.feature_bundle_id)

    assert saved_partition == partition.model_copy(update={"reference_count": 1, "retention_class": RetentionClass.PINNED})
    assert saved_snapshot == snapshot
    assert saved_bundle == bundle

    duplicate = partition.model_copy(
        update={
            "feature_partition_id": _rid(ResourceType.FEATURE_PARTITION, 7),
            "storage_ref": partition.storage_ref.model_copy(
                update={"relative_path": "features/moving_average/2026-01-03-duplicate.parquet"}
            ),
        }
    )
    with pytest.raises(PlatformDatabaseError, match="DATABASE_OPERATION_FAILED"):
        with database.transaction() as session:
            repository.add_partition(session, duplicate)

    with pytest.raises(RuntimeError, match="rollback"):
        with database.transaction() as session:
            repository.add_partition(
                session,
                partition.model_copy(
                    update={
                        "feature_partition_id": _rid(ResourceType.FEATURE_PARTITION, 6),
                        "partition_key": "2026-01-03-rollback",
                        "storage_ref": partition.storage_ref.model_copy(
                            update={"relative_path": "features/moving_average/2026-01-03-rollback.parquet"}
                        ),
                    }
                ),
            )
            raise RuntimeError("rollback")

    with database.transaction() as session:
        assert repository.get_partition(session, _rid(ResourceType.FEATURE_PARTITION, 6)) is None


def test_feature_migration_downgrade_and_upgrade_round_trip(
    isolated_postgres_database: PostgresDatabase,
) -> None:
    database = isolated_postgres_database
    upgrade_database(database.engine)
    assert get_migration_status(database.engine).is_at_head
    downgrade_database(database.engine, "0012_wp0204_benchmark_dataset_extension")
    with database.engine.connect() as connection:
        assert not connection.dialect.has_table(connection, "feature_partition")
        assert not connection.dialect.has_table(connection, "feature_snapshot")
        assert not connection.dialect.has_table(connection, "feature_bundle")
    upgrade_database(database.engine)
    assert get_migration_status(database.engine).is_at_head


def _correction_partition(base: FeaturePartition, *, revision: int, supersedes_id: str) -> FeaturePartition:
    row = FeatureRow(
        entity_key="cn.stock:000001",
        trade_date=date(2026, 1, 3),
        indicator_id=base.indicator_id,
        definition_version=base.definition_version,
        value=Decimal("1.20"),
        value_type="decimal",
        unit="cny_per_share",
        available_at=datetime(2026, 1, 3, 17, 30, tzinfo=UTC),
        data_snapshot_id=base.data_snapshot_ids[0],
        calculation_run_id=f"correction-{revision}",
    )
    partition_hash = FeaturePartition.compute_hash((row,))
    return FeaturePartition.build_from_rows(
        (row,),
        partition_id=_rid(ResourceType.FEATURE_PARTITION, 100 + revision),
        data_snapshot_ids=base.data_snapshot_ids,
        partition_key=base.partition_key,
        storage_ref=base.storage_ref.model_copy(
            update={
                "relative_path": f"features/moving_average/2026-01-03-revision-{revision}.parquet",
                "content_hash": partition_hash,
            }
        ),
        quality_report_id=base.quality_report_id,
        cutoff_at=base.cutoff_at,
        created_at=base.created_at,
        published_at=base.published_at,
        revision=revision,
        revision_kind=RevisionKind.CORRECTION,
        supersedes_id=supersedes_id,
    )


def test_feature_repository_rejects_unpersisted_and_nonincremental_correction_lineage(
    isolated_postgres_database: PostgresDatabase,
) -> None:
    database = isolated_postgres_database
    upgrade_database(database.engine)
    partition, snapshot, _ = _records()
    repository = FeatureRepository()
    correction = _correction_partition(partition, revision=3, supersedes_id=partition.feature_partition_id)

    with pytest.raises(ValueError, match="supersede a persisted partition"):
        with database.transaction() as session:
            repository.add_partition(session, correction)

    with database.transaction() as session:
        repository.add_partition(session, partition)

    with pytest.raises(ValueError, match="revision must increment"):
        with database.transaction() as session:
            repository.add_partition(session, correction)

    correction_snapshot = FeatureSnapshot.build(
        feature_snapshot_id=_rid(ResourceType.FEATURE_SNAPSHOT, 103),
        snapshot_type=FeatureSnapshotType.CORRECTION,
        as_of_trade_date=snapshot.as_of_trade_date,
        cutoff_at=snapshot.cutoff_at,
        data_snapshot_ids=snapshot.data_snapshot_ids,
        feature_partition_refs=snapshot.feature_partition_refs,
        dependency_plan_hash=snapshot.dependency_plan_hash,
        definition_refs=snapshot.definition_refs,
        publication_status=snapshot.publication_status,
        quality_status=snapshot.quality_status,
        max_source_available_at=snapshot.max_source_available_at,
        revision=3,
        revision_kind=RevisionKind.CORRECTION,
        supersedes_id=snapshot.feature_snapshot_id,
        created_at=snapshot.created_at,
        published_at=snapshot.published_at,
    )
    with pytest.raises(ValueError, match="supersede a persisted snapshot"):
        with database.transaction() as session:
            repository.add_snapshot(session, correction_snapshot)

    with database.transaction() as session:
        repository.add_snapshot(session, snapshot)

    with pytest.raises(ValueError, match="revision must increment"):
        with database.transaction() as session:
            repository.add_snapshot(session, correction_snapshot)


def test_feature_repository_rejects_bundle_without_snapshot_or_matching_manifest(
    isolated_postgres_database: PostgresDatabase,
) -> None:
    database = isolated_postgres_database
    upgrade_database(database.engine)
    partition, snapshot, bundle = _records()
    repository = FeatureRepository()

    with database.transaction() as session:
        repository.add_partition(session, partition)
        repository.add_snapshot(session, snapshot)

    missing_snapshot_bundle = FeatureBundle.build(
        feature_bundle_id=_rid(ResourceType.FEATURE_BUNDLE, 106),
        feature_snapshot_ids=(_rid(ResourceType.FEATURE_SNAPSHOT, 107),),
        dependency_plan_hash=bundle.dependency_plan_hash,
        required_partition_refs=bundle.required_partition_refs,
        required_columns=bundle.required_columns,
        consumer_ref=bundle.consumer_ref,
        consumer_kind=bundle.consumer_kind,
        cutoff_at=bundle.cutoff_at,
        date_from=bundle.date_from,
        date_to=bundle.date_to,
    )
    with pytest.raises(ValueError, match="missing snapshot"):
        with database.transaction() as session:
            repository.add_bundle(session, missing_snapshot_bundle)

    mismatched_plan_bundle = FeatureBundle.build(
        feature_bundle_id=_rid(ResourceType.FEATURE_BUNDLE, 108),
        feature_snapshot_ids=bundle.feature_snapshot_ids,
        dependency_plan_hash=compute_content_hash({"plan": "mismatch"}),
        required_partition_refs=bundle.required_partition_refs,
        required_columns=bundle.required_columns,
        consumer_ref=bundle.consumer_ref,
        consumer_kind=bundle.consumer_kind,
        cutoff_at=bundle.cutoff_at,
        date_from=bundle.date_from,
        date_to=bundle.date_to,
    )
    with pytest.raises(ValueError, match="dependency plan does not match"):
        with database.transaction() as session:
            repository.add_bundle(session, mismatched_plan_bundle)

    mismatched_cutoff_bundle = FeatureBundle.build(
        feature_bundle_id=_rid(ResourceType.FEATURE_BUNDLE, 109),
        feature_snapshot_ids=bundle.feature_snapshot_ids,
        dependency_plan_hash=bundle.dependency_plan_hash,
        required_partition_refs=bundle.required_partition_refs,
        required_columns=bundle.required_columns,
        consumer_ref=bundle.consumer_ref,
        consumer_kind=bundle.consumer_kind,
        cutoff_at=bundle.cutoff_at.replace(hour=19),
        date_from=bundle.date_from,
        date_to=bundle.date_to,
    )
    with pytest.raises(ValueError, match="cutoff_at does not match"):
        with database.transaction() as session:
            repository.add_bundle(session, mismatched_cutoff_bundle)



def test_feature_repository_formal_bundle_rejects_late_snapshot_but_preview_can_read_it(
    isolated_postgres_database: PostgresDatabase,
) -> None:
    database = isolated_postgres_database
    upgrade_database(database.engine)
    partition, snapshot, bundle = _records()
    late_snapshot = snapshot.model_copy(update={"published_at": NOW + timedelta(seconds=1)})
    repository = FeatureRepository()
    with database.transaction() as session:
        repository.add_partition(session, partition)
        repository.add_snapshot(session, late_snapshot)
    with pytest.raises(ValueError, match="published_at.*cutoff_at"):
        with database.transaction() as session:
            repository.add_bundle(session, bundle)
    preview = FeatureBundle.build(
        **(bundle.model_dump(mode="python", exclude={"bundle_hash", "consumer_kind", "feature_bundle_id"})
           | {"consumer_kind": ConsumerKind.PREVIEW, "feature_bundle_id": _rid(ResourceType.FEATURE_BUNDLE, 150)})
    )
    with database.transaction() as session:
        repository.add_bundle(session, preview)
        assert repository.get_partition(session, partition.feature_partition_id).reference_count == 0
        assert repository.get_bundle(session, preview.feature_bundle_id) == preview



def test_feature_repository_formal_bundle_rejects_late_partition_with_early_manifest(
    isolated_postgres_database: PostgresDatabase,
) -> None:
    database = isolated_postgres_database
    upgrade_database(database.engine)
    partition, snapshot, bundle = _records()
    repository = FeatureRepository()
    with database.transaction() as session:
        repository.add_partition(session, partition.model_copy(update={"published_at": NOW + timedelta(seconds=1)}))
        repository.add_snapshot(session, snapshot)
    with pytest.raises(ValueError, match="partition published_at.*cutoff_at"):
        with database.transaction() as session:
            repository.add_bundle(session, bundle)
