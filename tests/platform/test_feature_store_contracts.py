from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.schemas.platform import (
    FeatureBundle,
    FeaturePartition,
    FeatureRow,
    FeatureSnapshot,
    FeaturePartitionRef,
    FeatureSnapshotType,
    PublicationStatus,
    QualityStatus,
    RetentionClass,
    StorageBackend,
    StorageNamespace,
    StorageRef,
    compute_content_hash,
    generate_resource_id,
)
from src.schemas.platform.indicator import FeatureDependencyPlan, FeatureInstanceKey
from src.services.platform.indicator_registry import default_indicator_registry
from src.services.platform.feature_store import (
    FeatureMaterializationError,
    FeaturePublicationError,
    FeatureStore,
    affected_feature_instances,
)
from src.schemas.platform.enums import ConsumerKind, ResourceType

UTC = timezone.utc
CUTOFF = datetime(2026, 1, 3, 18, 0, tzinfo=UTC)


def _rid(kind: ResourceType, n: int) -> str:
    return generate_resource_id(kind, timestamp_ms=1_700_000_000_000 + n, random_bits=n)


def _row(entity: str, trade_date: date, *, available_at: datetime = datetime(2026, 1, 3, 17, 0, tzinfo=UTC), value: Decimal | None = Decimal("1.20")) -> FeatureRow:
    return FeatureRow(
        entity_key=entity,
        trade_date=trade_date,
        indicator_id="moving_average",
        definition_version="1.0.0",
        value=value,
        value_type="decimal",
        unit="cny_per_share",
        available_at=available_at,
        data_snapshot_id=_rid(ResourceType.DATA_SNAPSHOT, 1),
        calculation_run_id="run-1",
    )


def _storage(partition_hash: str, name: str = "feature.parquet") -> StorageRef:
    return StorageRef(
        storage_backend=StorageBackend.LOCAL_FS,
        storage_namespace=StorageNamespace.APP,
        relative_path=f"features/{name}",
        content_hash=partition_hash,
        media_type="application/vnd.apache.parquet",
        size_bytes=10,
    )


def _instance() -> FeatureInstanceKey:
    params = {"period": 20}
    return FeatureInstanceKey(
        indicator_id="moving_average",
        definition_version="1.0.0",
        canonical_parameter_json='{"period":20}',
        parameter_hash=compute_content_hash(params),
        frequency="1d",
    )


def test_feature_parquet_accepts_decimal128_boundary_with_high_precision_context() -> None:
    legal = Decimal("99999999999999999999999999.999999999999")
    assert FeaturePartition.compute_hash(
        (_row("cn.stock:000001", date(2026, 1, 3), value=legal),)
    ).startswith("sha256:")
    assert FeaturePartition.compute_hash(
        (_row("cn.stock:000001", date(2026, 1, 3), value=Decimal("1E-12")),)
    ).startswith("sha256:")


def test_feature_parquet_rejects_values_outside_fixed_decimal128_precision() -> None:
    with pytest.raises(FeatureMaterializationError, match="precision"):
        FeaturePartition.compute_hash(
            (_row("cn.stock:000001", date(2026, 1, 3), value=Decimal("0.1234567890123")),)
        )
    with pytest.raises(FeatureMaterializationError, match="precision"):
        FeaturePartition.compute_hash(
            (_row("cn.stock:000001", date(2026, 1, 3), value=Decimal("123456789012345678901234567.1")),)
        )


def test_feature_partition_from_rows_is_deterministic_and_rejects_pit_or_duplicate_keys() -> None:
    rows = [_row("cn.stock:000001", date(2026, 1, 3)), _row("cn.stock:000002", date(2026, 1, 3), value=None)]
    payload = FeaturePartition.build_from_rows(
        rows,
        partition_id=_rid(ResourceType.FEATURE_PARTITION, 2),
        data_snapshot_ids=(_rid(ResourceType.DATA_SNAPSHOT, 1),),
        partition_key="2026-01-03",
        storage_ref=_storage(FeaturePartition.compute_hash(rows), "one.parquet"),
        quality_report_id=_rid(ResourceType.QUALITY_REPORT, 3),
        cutoff_at=CUTOFF,
        created_at=CUTOFF,
    )
    repeat = FeaturePartition.build_from_rows(
        list(reversed(rows)),
        partition_id=_rid(ResourceType.FEATURE_PARTITION, 4),
        data_snapshot_ids=(_rid(ResourceType.DATA_SNAPSHOT, 1),),
        partition_key="2026-01-03",
        storage_ref=_storage(payload.partition_hash, "one.parquet"),
        quality_report_id=_rid(ResourceType.QUALITY_REPORT, 3),
        cutoff_at=CUTOFF,
        created_at=CUTOFF,
    )
    assert payload.partition_hash == repeat.partition_hash
    reordered_flags = [_row("cn.stock:000003", date(2026, 1, 3)).model_copy(update={"data_flags": ("Z_FLAG", "A_FLAG")})]
    reordered_flags_repeat = [reordered_flags[0].model_copy(update={"data_flags": ("A_FLAG", "Z_FLAG")})]
    assert FeaturePartition.compute_hash(reordered_flags) == FeaturePartition.compute_hash(reordered_flags_repeat)
    assert payload.schema_hash.startswith("sha256:")
    assert payload.null_count == 1
    with pytest.raises(FeatureMaterializationError, match="duplicate"):
        FeaturePartition.build_from_rows(
            rows + [rows[0]],
            partition_id=_rid(ResourceType.FEATURE_PARTITION, 5),
            data_snapshot_ids=(_rid(ResourceType.DATA_SNAPSHOT, 1),),
            partition_key="2026-01-03",
            storage_ref=_storage(payload.partition_hash, "dup.parquet"),
            quality_report_id=_rid(ResourceType.QUALITY_REPORT, 6),
            cutoff_at=CUTOFF,
            created_at=CUTOFF,
        )
    with pytest.raises(FeatureMaterializationError, match="available_at"):
        FeaturePartition.build_from_rows(
            [_row("cn.stock:000003", date(2026, 1, 3), available_at=CUTOFF.replace(hour=19))],
            partition_id=_rid(ResourceType.FEATURE_PARTITION, 7),
            data_snapshot_ids=(_rid(ResourceType.DATA_SNAPSHOT, 1),),
            partition_key="2026-01-03",
            storage_ref=_storage(FeaturePartition.compute_hash(rows), "late.parquet"),
            quality_report_id=_rid(ResourceType.QUALITY_REPORT, 8),
            cutoff_at=CUTOFF,
            created_at=CUTOFF,
        )


def test_feature_partition_storage_contract_is_fail_closed() -> None:
    rows = (_row("cn.stock:000001", date(2026, 1, 3)),)
    partition_hash = FeaturePartition.compute_hash(rows)
    partition = FeaturePartition.build_from_rows(
        rows,
        partition_id=_rid(ResourceType.FEATURE_PARTITION, 8),
        data_snapshot_ids=(_rid(ResourceType.DATA_SNAPSHOT, 1),),
        partition_key="2026-01-03",
        storage_ref=_storage(partition_hash),
        quality_report_id=_rid(ResourceType.QUALITY_REPORT, 9),
        cutoff_at=CUTOFF,
        created_at=CUTOFF,
    )
    for patch in (
        {"media_type": "application/json"},
        {"size_bytes": 0},
    ):
        bad_storage = partition.storage_ref.model_copy(update=patch)
        with pytest.raises(ValidationError, match="storage_ref"):
            FeaturePartition.model_validate(
                partition.model_dump(mode="python") | {"storage_ref": bad_storage}
            )
        with pytest.raises(ValidationError, match="storage_ref"):
            FeaturePartitionRef.model_validate(
                FeaturePartitionRef.from_partition(partition).model_dump(mode="python")
                | {"storage_ref": bad_storage}
            )


def test_snapshot_and_bundle_are_immutable_and_fix_references() -> None:
    rows = [_row("cn.stock:000001", date(2026, 1, 3))]
    partition_hash = FeaturePartition.compute_hash(rows)
    partition = FeaturePartition.build_from_rows(
        rows,
        partition_id=_rid(ResourceType.FEATURE_PARTITION, 10),
        data_snapshot_ids=(_rid(ResourceType.DATA_SNAPSHOT, 1),),
        partition_key="2026-01-03",
        storage_ref=_storage(partition_hash),
        quality_report_id=_rid(ResourceType.QUALITY_REPORT, 11),
        cutoff_at=CUTOFF,
        created_at=CUTOFF,
        published_at=CUTOFF,
    )
    snapshot = FeatureSnapshot.build(
        feature_snapshot_id=_rid(ResourceType.FEATURE_SNAPSHOT, 12),
        snapshot_type=FeatureSnapshotType.CLOSE_CORE,
        as_of_trade_date=date(2026, 1, 3),
        cutoff_at=CUTOFF,
        data_snapshot_ids=partition.data_snapshot_ids,
        feature_partition_refs=(FeaturePartitionRef.from_partition(partition),),
        dependency_plan_hash=compute_content_hash({"plan": "p"}),
        definition_refs=("moving_average@1.0.0",),
        publication_status=PublicationStatus.CERTIFIED,
        quality_status=QualityStatus.COMPLETE,
        max_source_available_at=rows[0].available_at,
        revision=1,
        created_at=CUTOFF,
        published_at=CUTOFF,
    )
    bundle = FeatureBundle.build(
        feature_bundle_id=_rid(ResourceType.FEATURE_BUNDLE, 13),
        feature_snapshot_ids=(snapshot.feature_snapshot_id,),
        dependency_plan_hash=snapshot.dependency_plan_hash,
        required_partition_refs=snapshot.feature_partition_refs,
        required_columns=("moving_average.value",),
        consumer_ref="strategy:test",
        cutoff_at=CUTOFF,
        consumer_kind="FORMAL_BACKTEST",
    )
    assert snapshot.manifest_hash == FeatureSnapshot.compute_hash(snapshot)
    assert bundle.bundle_hash == FeatureBundle.compute_hash(bundle)
    assert bundle.required_partition_refs[0].retention_class is RetentionClass.PINNED
    published_after_cutoff = FeatureSnapshot.model_validate(
        snapshot.model_dump(mode="python") | {"published_at": CUTOFF + timedelta(seconds=1)}
    )
    assert published_after_cutoff.published_at == CUTOFF + timedelta(seconds=1)
    with pytest.raises(ValidationError):
        snapshot.cutoff_at = CUTOFF  # type: ignore[misc]


def test_manifest_and_bundle_hashes_canonicalize_reference_order() -> None:
    data_snapshot_id = _rid(ResourceType.DATA_SNAPSHOT, 1)
    rows_one = (_row("cn.stock:000001", date(2026, 1, 3)),)
    rows_two = (_row("cn.stock:000002", date(2026, 1, 3)),)
    partitions = []
    for index, rows in enumerate((rows_one, rows_two), start=21):
        partition_hash = FeaturePartition.compute_hash(rows)
        partitions.append(
            FeaturePartition.build_from_rows(
                rows,
                partition_id=_rid(ResourceType.FEATURE_PARTITION, index),
                data_snapshot_ids=(data_snapshot_id,),
                partition_key=f"2026-01-03-{index}",
                storage_ref=_storage(partition_hash, f"{index}.parquet"),
                quality_report_id=_rid(ResourceType.QUALITY_REPORT, index),
                cutoff_at=CUTOFF,
                created_at=CUTOFF,
                published_at=CUTOFF,
            )
        )
    refs = tuple(FeaturePartitionRef.from_partition(partition) for partition in partitions)
    snapshot_one = FeatureSnapshot.build(
        feature_snapshot_id=_rid(ResourceType.FEATURE_SNAPSHOT, 23),
        snapshot_type=FeatureSnapshotType.CLOSE_CORE,
        as_of_trade_date=date(2026, 1, 3),
        cutoff_at=CUTOFF,
        data_snapshot_ids=(data_snapshot_id,),
        feature_partition_refs=refs,
        dependency_plan_hash=compute_content_hash({"plan": "canonical"}),
        definition_refs=("moving_average@1.0.0",),
        publication_status=PublicationStatus.CERTIFIED,
        quality_status=QualityStatus.COMPLETE,
        max_source_available_at=rows_one[0].available_at,
        revision=1,
        created_at=CUTOFF,
        published_at=CUTOFF,
    )
    snapshot_two = snapshot_one.model_copy(
        update={
            "feature_snapshot_id": _rid(ResourceType.FEATURE_SNAPSHOT, 24),
            "feature_partition_refs": tuple(reversed(refs)),
        }
    )
    assert snapshot_one.manifest_hash == snapshot_two.manifest_hash

    bundle_one = FeatureBundle.build(
        feature_bundle_id=_rid(ResourceType.FEATURE_BUNDLE, 25),
        feature_snapshot_ids=(snapshot_one.feature_snapshot_id,),
        dependency_plan_hash=snapshot_one.dependency_plan_hash,
        required_partition_refs=refs,
        required_columns=("moving_average.value",),
        consumer_ref="strategy:canonical",
        consumer_kind=ConsumerKind.FORMAL_BACKTEST,
        cutoff_at=CUTOFF,
    )
    bundle_two = FeatureBundle.build(
        feature_bundle_id=_rid(ResourceType.FEATURE_BUNDLE, 26),
        feature_snapshot_ids=(snapshot_one.feature_snapshot_id,),
        dependency_plan_hash=snapshot_one.dependency_plan_hash,
        required_partition_refs=tuple(reversed(refs)),
        required_columns=("moving_average.value",),
        consumer_ref="strategy:canonical",
        consumer_kind=ConsumerKind.FORMAL_BACKTEST,
        cutoff_at=CUTOFF,
    )
    assert bundle_one.bundle_hash == bundle_two.bundle_hash


def test_store_publishes_atomically_and_propagates_correction() -> None:
    a = _instance()
    b = a.model_copy(update={"indicator_id": "volatility"})
    plan = FeatureDependencyPlan(
        required_instances=(b,),
        ordered_instances=(a, b),
        dependency_edges=(
            {"dependency": a, "consumer": b},
        ),
        required_columns=("moving_average.value", "volatility.value"),
        dataset_refs=("bar_1d_raw@1.0.0",),
        capability_ids=("market_bars_daily",),
        cutoff_at=CUTOFF,
        lookback_requirement=20,
        warmup_requirement=20,
    )
    assert affected_feature_instances(plan, (a,)) == (a, b)
    store = FeatureStore(clock=lambda: CUTOFF)
    rows = {a: (_row("cn.stock:000001", date(2026, 1, 3)),), b: (_row("cn.stock:000001", date(2026, 1, 3)),)}
    rows[b] = (rows[b][0].model_copy(update={"indicator_id": "volatility", "unit": "ratio"}),)
    snapshot, bundle = store.materialize_and_publish(
        plan,
        rows,
        snapshot_id=_rid(ResourceType.FEATURE_SNAPSHOT, 14),
        bundle_id=_rid(ResourceType.FEATURE_BUNDLE, 15),
        data_snapshot_ids=(_rid(ResourceType.DATA_SNAPSHOT, 1),),
        quality_report_id=_rid(ResourceType.QUALITY_REPORT, 16),
        cutoff_at=CUTOFF,
        as_of_trade_date=date(2026, 1, 3),
        consumer_ref="strategy:test",
        consumer_kind=ConsumerKind.FORMAL_BACKTEST,
        expected_entity_keys=("cn.stock:000001",),
        expected_trade_dates=(date(2026, 1, 3),),
    )
    assert snapshot.publication_status is PublicationStatus.CERTIFIED
    assert bundle.required_partition_refs[0].retention_class is RetentionClass.PINNED
    assert bundle.required_partition_refs[0].required_columns == ("moving_average.value",)
    assert snapshot.feature_partition_refs[0].required_columns == ("moving_average.value",)
    assert store.is_pinned(bundle.required_partition_refs[0].feature_partition_id)
    assert store.published_snapshot(snapshot.feature_snapshot_id) == snapshot


def test_materialization_requires_exact_plan_scope_and_declared_instances() -> None:
    instance = _instance()
    plan = _single_plan(instance)
    rows = {instance: (_row("cn.stock:000001", date(2026, 1, 3)),)}
    with pytest.raises(FeatureMaterializationError, match="cutoff_at"):
        _publish(FeatureStore(), plan, rows, cutoff_at=CUTOFF + timedelta(seconds=1))
    with pytest.raises(FeatureMaterializationError, match="date range"):
        _publish(FeatureStore(), plan, rows, date_from=date(2026, 1, 3))
    extra = instance.model_copy(update={"indicator_id": "volatility"})
    extra_rows = dict(rows)
    extra_rows[extra] = (_row("cn.stock:000001", date(2026, 1, 3)).model_copy(update={"indicator_id": "volatility"}),)
    with pytest.raises(FeatureMaterializationError, match="exactly match"):
        _publish(FeatureStore(), plan, extra_rows)
    with pytest.raises(ValidationError, match="quality_report_id"):
        _publish(FeatureStore(), plan, rows, quality_report_id="")


def test_dependency_plan_requires_non_empty_instance_sets() -> None:
    instance = _instance()
    with pytest.raises(ValidationError, match="required_instances"):
        FeatureDependencyPlan(
            required_instances=(),
            ordered_instances=(instance,),
            required_columns=("moving_average.value",),
            cutoff_at=CUTOFF,
        )
    with pytest.raises(ValidationError, match="ordered_instances"):
        FeatureDependencyPlan(
            required_instances=(instance,),
            ordered_instances=(),
            required_columns=("moving_average.value",),
            cutoff_at=CUTOFF,
        )


def test_date_range_rejects_end_without_start_at_plan_and_bundle_boundaries() -> None:
    instance = _instance()
    with pytest.raises(ValidationError, match="date_to requires date_from"):
        FeatureDependencyPlan(
            required_instances=(instance,),
            ordered_instances=(instance,),
            required_columns=("moving_average.value",),
            date_to=date(2026, 1, 3),
        )

    plan = FeatureDependencyPlan(
        required_instances=(instance,),
        ordered_instances=(instance,),
        required_columns=("moving_average.value",),
        cutoff_at=CUTOFF,
    )
    rows = (_row("cn.stock:000001", date(2026, 1, 3)),)
    partition_hash = FeaturePartition.compute_hash(rows)
    partition = FeaturePartition.build_from_rows(
        rows,
        partition_id=_rid(ResourceType.FEATURE_PARTITION, 47),
        data_snapshot_ids=(_rid(ResourceType.DATA_SNAPSHOT, 1),),
        partition_key="2026-01-03",
        storage_ref=_storage(partition_hash),
        quality_report_id=_rid(ResourceType.QUALITY_REPORT, 48),
        cutoff_at=CUTOFF,
        created_at=CUTOFF,
        published_at=CUTOFF,
    )
    snapshot = FeatureSnapshot.build(
        feature_snapshot_id=_rid(ResourceType.FEATURE_SNAPSHOT, 49),
        snapshot_type=FeatureSnapshotType.CLOSE_CORE,
        as_of_trade_date=date(2026, 1, 3),
        cutoff_at=CUTOFF,
        data_snapshot_ids=partition.data_snapshot_ids,
        feature_partition_refs=(FeaturePartitionRef.from_partition(partition),),
        dependency_plan_hash=plan.plan_hash,
        definition_refs=("moving_average@1.0.0",),
        publication_status=PublicationStatus.CERTIFIED,
        quality_status=QualityStatus.COMPLETE,
        max_source_available_at=rows[0].available_at,
        revision=1,
        created_at=CUTOFF,
        published_at=CUTOFF,
    )
    with pytest.raises(ValidationError, match="date_to requires date_from"):
        FeatureBundle.build(
            feature_bundle_id=_rid(ResourceType.FEATURE_BUNDLE, 50),
            feature_snapshot_ids=(snapshot.feature_snapshot_id,),
            dependency_plan_hash=plan.plan_hash,
            required_partition_refs=(FeaturePartitionRef.from_partition(partition),),
            required_columns=("moving_average.value",),
            consumer_ref="strategy:invalid-range",
            consumer_kind=ConsumerKind.PREVIEW,
            cutoff_at=CUTOFF,
            date_to=date(2026, 1, 3),
        )


def test_plan_warmup_is_required_but_not_published_and_pit_applies_to_warmup_rows() -> None:
    instance = _instance()
    plan = FeatureDependencyPlan(
        required_instances=(instance,),
        ordered_instances=(instance,),
        required_columns=("moving_average.value",),
        dataset_refs=("bar_1d_raw@1.0.0",),
        capability_ids=("market_bars_daily",),
        cutoff_at=CUTOFF,
        date_from=date(2026, 1, 3),
        date_to=date(2026, 1, 3),
        lookback_requirement=20,
        warmup_requirement=20,
    )
    rows = tuple(
        _row("cn.stock:000001", date(2025, 12, 14) + timedelta(days=index))
        for index in range(21)
    )
    store = FeatureStore()
    snapshot, _ = store.materialize_and_publish(
        plan,
        {instance: rows},
        data_snapshot_ids=(_rid(ResourceType.DATA_SNAPSHOT, 1),),
        quality_report_id=_rid(ResourceType.QUALITY_REPORT, 30),
        cutoff_at=CUTOFF,
        as_of_trade_date=date(2026, 1, 3),
        consumer_ref="strategy:warmup",
        date_from=date(2026, 1, 3),
        date_to=date(2026, 1, 3),
    )
    partition = store.published_partition(snapshot.feature_partition_refs[0].feature_partition_id)
    assert partition.row_count == 1
    assert partition.min_date == partition.max_date == date(2026, 1, 3)
    with pytest.raises(FeatureMaterializationError, match="warmup evidence"):
        store.materialize_and_publish(
            plan,
            {instance: (rows[-1],)},
            data_snapshot_ids=(_rid(ResourceType.DATA_SNAPSHOT, 1),),
            quality_report_id=_rid(ResourceType.QUALITY_REPORT, 31),
            cutoff_at=CUTOFF,
            as_of_trade_date=date(2026, 1, 3),
            consumer_ref="strategy:missing-warmup",
            date_from=date(2026, 1, 3),
            date_to=date(2026, 1, 3),
        )
    with pytest.raises(FeatureMaterializationError, match="available_at"):
        store.materialize_and_publish(
            plan,
            {instance: rows[:-1] + (_row("cn.stock:000001", date(2026, 1, 3), available_at=CUTOFF + timedelta(seconds=1)),)},
            data_snapshot_ids=(_rid(ResourceType.DATA_SNAPSHOT, 1),),
            quality_report_id=_rid(ResourceType.QUALITY_REPORT, 32),
            cutoff_at=CUTOFF,
            as_of_trade_date=date(2026, 1, 3),
            consumer_ref="strategy:late-warmup",
            date_from=date(2026, 1, 3),
            date_to=date(2026, 1, 3),
        )


def test_partition_and_snapshot_publication_guards_are_point_in_time_consistent() -> None:
    rows = [_row("cn.stock:000001", date(2026, 1, 3))]
    partition_hash = FeaturePartition.compute_hash(rows)
    partition = FeaturePartition.build_from_rows(
        rows,
        partition_id=_rid(ResourceType.FEATURE_PARTITION, 90),
        data_snapshot_ids=(_rid(ResourceType.DATA_SNAPSHOT, 1),),
        partition_key="2026-01-03",
        storage_ref=_storage(partition_hash),
        quality_report_id=_rid(ResourceType.QUALITY_REPORT, 91),
        cutoff_at=CUTOFF,
        created_at=CUTOFF,
        published_at=CUTOFF,
    )
    published_after_cutoff = FeaturePartition.model_validate(
        partition.model_dump(mode="python") | {"published_at": CUTOFF + timedelta(seconds=1)}
    )
    assert published_after_cutoff.published_at == CUTOFF + timedelta(seconds=1)

    snapshot = FeatureSnapshot.build(
        feature_snapshot_id=_rid(ResourceType.FEATURE_SNAPSHOT, 92),
        snapshot_type=FeatureSnapshotType.CLOSE_CORE,
        as_of_trade_date=date(2026, 1, 3),
        cutoff_at=CUTOFF,
        data_snapshot_ids=partition.data_snapshot_ids,
        feature_partition_refs=(FeaturePartitionRef.from_partition(partition),),
        dependency_plan_hash=compute_content_hash({"plan": "guard"}),
        definition_refs=("moving_average@1.0.0",),
        publication_status=PublicationStatus.CERTIFIED,
        quality_status=QualityStatus.COMPLETE,
        max_source_available_at=rows[0].available_at,
        revision=1,
        created_at=CUTOFF,
        published_at=CUTOFF,
    )
    with pytest.raises(ValidationError, match="snapshot_type"):
        FeatureSnapshot.model_validate(
            snapshot.model_dump(mode="python") | {"snapshot_type": FeatureSnapshotType.CORRECTION}
        )


def test_bundle_rejects_partition_columns_outside_fixed_projection() -> None:
    rows = (_row("cn.stock:000001", date(2026, 1, 3)),)
    partition_hash = FeaturePartition.compute_hash(rows)
    partition = FeaturePartition.build_from_rows(
        rows,
        partition_id=_rid(ResourceType.FEATURE_PARTITION, 93),
        data_snapshot_ids=(_rid(ResourceType.DATA_SNAPSHOT, 1),),
        partition_key="2026-01-03",
        storage_ref=_storage(partition_hash),
        quality_report_id=_rid(ResourceType.QUALITY_REPORT, 94),
        cutoff_at=CUTOFF,
        created_at=CUTOFF,
        published_at=CUTOFF,
    )
    bundle = FeatureBundle.build(
        feature_bundle_id=_rid(ResourceType.FEATURE_BUNDLE, 95),
        feature_snapshot_ids=(_rid(ResourceType.FEATURE_SNAPSHOT, 96),),
        dependency_plan_hash=compute_content_hash({"plan": "columns"}),
        required_partition_refs=(FeaturePartitionRef.from_partition(partition, required_columns=("moving_average.value",)),),
        required_columns=("moving_average.value",),
        consumer_ref="strategy:columns",
        consumer_kind=ConsumerKind.FORMAL_BACKTEST,
        cutoff_at=CUTOFF,
    )
    bad_ref = bundle.required_partition_refs[0].model_copy(update={"required_columns": ("other.value",)})
    with pytest.raises(ValidationError, match="declared by the bundle"):
        FeatureBundle.model_validate(
            bundle.model_dump(mode="python") | {"required_partition_refs": (bad_ref.model_dump(mode="python"),)}
        )


def test_quality_and_coverage_validation_fail_closed_before_formal_publication() -> None:
    instance = _instance()
    partial_plan = FeatureDependencyPlan(
        required_instances=(instance,),
        ordered_instances=(instance,),
        required_columns=("moving_average.value",),
        cutoff_at=CUTOFF,
        lookback_requirement=20,
        warmup_requirement=20,
    )
    store = FeatureStore()
    with pytest.raises(FeaturePublicationError, match="quality gate"):
        store.materialize_and_publish(
            partial_plan,
            {instance: (_row("cn.stock:000001", date(2026, 1, 3), value=None),)},
            data_snapshot_ids=(_rid(ResourceType.DATA_SNAPSHOT, 1),),
            quality_report_id=_rid(ResourceType.QUALITY_REPORT, 33),
            cutoff_at=CUTOFF,
            as_of_trade_date=date(2026, 1, 3),
            consumer_ref="strategy:quality-gate",
        )
    row = _row("cn.stock:000001", date(2026, 1, 3))
    with pytest.raises(ValidationError, match="coverage_ratio"):
        FeaturePartition(
            feature_partition_id=_rid(ResourceType.FEATURE_PARTITION, 34),
            indicator_id="moving_average",
            definition_version="1.0.0",
            domain="a_share",
            frequency="1d",
            partition_key="2026-01-03",
            data_snapshot_ids=(_rid(ResourceType.DATA_SNAPSHOT, 1),),
            cutoff_at=CUTOFF,
            row_count=2,
            null_count=0,
            coverage_ratio=Decimal("0.5"),
            min_date=row.trade_date,
            max_date=row.trade_date,
            min_available_at=row.available_at,
            max_available_at=row.available_at,
            storage_ref=_storage("sha256:" + "0" * 64),
            partition_hash="sha256:" + "0" * 64,
            schema_hash="sha256:" + "1" * 64,
            quality_status=QualityStatus.COMPLETE,
            quality_report_id=_rid(ResourceType.QUALITY_REPORT, 35),
            revision=1,
            created_at=CUTOFF,
        )


def test_correction_requires_published_lineage_and_formal_reference_pins_partition_record() -> None:
    instance = _instance()
    plan = FeatureDependencyPlan(
        required_instances=(instance,),
        ordered_instances=(instance,),
        required_columns=("moving_average.value",),
        cutoff_at=CUTOFF,
        lookback_requirement=20,
        warmup_requirement=20,
    )
    store = FeatureStore(clock=lambda: CUTOFF)
    first_snapshot, first_bundle = store.materialize_and_publish(
        plan,
        {instance: (_row("cn.stock:000001", date(2026, 1, 3)),)},
        snapshot_id=_rid(ResourceType.FEATURE_SNAPSHOT, 36),
        bundle_id=_rid(ResourceType.FEATURE_BUNDLE, 37),
        data_snapshot_ids=(_rid(ResourceType.DATA_SNAPSHOT, 1),),
        quality_report_id=_rid(ResourceType.QUALITY_REPORT, 38),
        cutoff_at=CUTOFF,
        as_of_trade_date=date(2026, 1, 3),
        consumer_ref="strategy:lineage",
        consumer_kind=ConsumerKind.FORMAL_BACKTEST,
        expected_entity_keys=("cn.stock:000001",),
        expected_trade_dates=(date(2026, 1, 3),),
    )
    old_partition_id = first_snapshot.feature_partition_refs[0].feature_partition_id
    old_partition = store.published_partition(old_partition_id)
    assert old_partition.retention_class is RetentionClass.PINNED
    assert old_partition.reference_count == 1

    corrected_row = _row("cn.stock:000001", date(2026, 1, 3), value=Decimal("1.30"))
    corrected_snapshot, _ = store.materialize_and_publish(
        plan,
        {instance: (corrected_row,)},
        snapshot_id=_rid(ResourceType.FEATURE_SNAPSHOT, 39),
        bundle_id=_rid(ResourceType.FEATURE_BUNDLE, 40),
        data_snapshot_ids=(_rid(ResourceType.DATA_SNAPSHOT, 1),),
        quality_report_id=_rid(ResourceType.QUALITY_REPORT, 41),
        cutoff_at=CUTOFF,
        as_of_trade_date=date(2026, 1, 3),
        consumer_ref="strategy:lineage-correction",
        consumer_kind=ConsumerKind.FORMAL_BACKTEST,
        expected_entity_keys=("cn.stock:000001",),
        expected_trade_dates=(date(2026, 1, 3),),
        correction_of_snapshot_id=first_snapshot.feature_snapshot_id,
        correction_of_partition_ids={instance: old_partition_id},
    )
    corrected_partition = store.published_partition(corrected_snapshot.feature_partition_refs[0].feature_partition_id)
    assert corrected_snapshot.supersedes_id == first_snapshot.feature_snapshot_id
    assert corrected_partition.supersedes_id == old_partition_id
    assert corrected_partition.revision == 2
    assert first_bundle.feature_snapshot_ids == (first_snapshot.feature_snapshot_id,)

    third_snapshot, _ = store.materialize_and_publish(
        plan,
        {instance: (_row("cn.stock:000001", date(2026, 1, 3), value=Decimal("1.35")),)},
        snapshot_id=_rid(ResourceType.FEATURE_SNAPSHOT, 44),
        bundle_id=_rid(ResourceType.FEATURE_BUNDLE, 45),
        data_snapshot_ids=(_rid(ResourceType.DATA_SNAPSHOT, 1),),
        quality_report_id=_rid(ResourceType.QUALITY_REPORT, 46),
        cutoff_at=CUTOFF,
        as_of_trade_date=date(2026, 1, 3),
        consumer_ref="strategy:lineage-correction-again",
        consumer_kind=ConsumerKind.FORMAL_BACKTEST,
        expected_entity_keys=("cn.stock:000001",),
        expected_trade_dates=(date(2026, 1, 3),),
        correction_of_snapshot_id=corrected_snapshot.feature_snapshot_id,
        correction_of_partition_ids={instance: corrected_partition.feature_partition_id},
    )
    third_partition = store.published_partition(third_snapshot.feature_partition_refs[0].feature_partition_id)
    assert third_snapshot.revision == 3
    assert third_snapshot.supersedes_id == corrected_snapshot.feature_snapshot_id
    assert third_partition.revision == 3
    assert third_partition.supersedes_id == corrected_partition.feature_partition_id

    with pytest.raises(FeaturePublicationError, match="published snapshot"):
        store.materialize_and_publish(
            plan,
            {instance: (_row("cn.stock:000001", date(2026, 1, 3), value=Decimal("1.40")),)},
            data_snapshot_ids=(_rid(ResourceType.DATA_SNAPSHOT, 1),),
            quality_report_id=_rid(ResourceType.QUALITY_REPORT, 42),
            cutoff_at=CUTOFF,
            as_of_trade_date=date(2026, 1, 3),
            consumer_ref="strategy:unknown-correction",
            correction_of_snapshot_id=_rid(ResourceType.FEATURE_SNAPSHOT, 43),
            correction_of_partition_ids={instance: old_partition_id},
        )


def _single_plan(instance: FeatureInstanceKey, **kwargs) -> FeatureDependencyPlan:
    kwargs.setdefault("lookback_requirement", 20)
    kwargs.setdefault("warmup_requirement", 20)
    return FeatureDependencyPlan(
        required_instances=(instance,), ordered_instances=(instance,),
        required_columns=(f"{instance.indicator_id}.value",), cutoff_at=CUTOFF, **kwargs,
    )


def _publish(store, plan, rows, **kwargs):
    return store.materialize_and_publish(
        plan, rows, data_snapshot_ids=(_rid(ResourceType.DATA_SNAPSHOT, 1),),
        cutoff_at=kwargs.pop("cutoff_at", CUTOFF), as_of_trade_date=date(2026, 1, 3),
        consumer_ref=kwargs.pop("consumer_ref", "strategy:test"),
        consumer_kind=kwargs.pop("consumer_kind", ConsumerKind.PREVIEW), **kwargs,
    )


def test_dependency_plan_rejects_unregistered_required_columns() -> None:
    instance = _instance()
    plan = _single_plan(instance).model_copy(update={"required_columns": ("moving_average.value", "moving_average.unknown")})
    with pytest.raises(FeatureMaterializationError, match="required_columns"):
        _publish(FeatureStore(), plan, {instance: (_row("cn.stock:000001", date(2026, 1, 3)),)})


def test_partition_rejects_mixed_column_schema_before_publication() -> None:
    instance = _instance()
    rows = (
        _row("cn.stock:000001", date(2026, 1, 3)),
        _row("cn.stock:000002", date(2026, 1, 3)).model_copy(update={"unit": "percent"}),
    )
    with pytest.raises(FeatureMaterializationError, match="schema"):
        _publish(FeatureStore(), _single_plan(instance), {instance: rows})


@pytest.mark.parametrize("bad_warmup", ["duplicate", "null", "stale", "schema"])
def test_warmup_validation_cannot_be_bypassed_by_output_projection(bad_warmup) -> None:
    instance = _instance()
    plan = _single_plan(instance, date_from=date(2026, 1, 3), warmup_requirement=1)
    warmup = _row("cn.stock:000001", date(2026, 1, 2))
    if bad_warmup == "null":
        warmup = warmup.model_copy(update={"value": None})
    elif bad_warmup == "stale":
        warmup = warmup.model_copy(update={"quality_status": QualityStatus.STALE})
    elif bad_warmup == "schema":
        warmup = warmup.model_copy(update={"unit": "percent"})
    rows = [warmup, _row("cn.stock:000001", date(2026, 1, 3))]
    if bad_warmup == "duplicate":
        rows.insert(0, warmup)
    with pytest.raises(FeatureMaterializationError):
        _publish(FeatureStore(), plan, {instance: rows}, date_from=plan.date_from)


def test_same_partition_can_be_reused_by_new_consumer_and_retry_is_idempotent() -> None:
    instance = _instance()
    store = FeatureStore(clock=lambda: CUTOFF)
    plan = _single_plan(instance)
    rows = {instance: (_row("cn.stock:000001", date(2026, 1, 3)),)}
    formal = {"consumer_kind": ConsumerKind.FORMAL_BACKTEST, "expected_entity_keys": ("cn.stock:000001",), "expected_trade_dates": (date(2026, 1, 3),)}
    first_snapshot, first_bundle = _publish(store, plan, rows, consumer_ref="strategy:one", **formal)
    second_snapshot, second_bundle = _publish(store, plan, rows, consumer_ref="strategy:two", **formal)
    assert second_snapshot == first_snapshot
    assert second_bundle.bundle_hash != first_bundle.bundle_hash
    partition_id = first_snapshot.feature_partition_refs[0].feature_partition_id
    assert store.published_partition(partition_id).reference_count == 2
    repeated_snapshot, repeated_bundle = _publish(store, plan, rows, consumer_ref="strategy:two", **formal)
    assert (repeated_snapshot, repeated_bundle) == (second_snapshot, second_bundle)
    assert store.published_partition(partition_id).reference_count == 2


def test_partial_correction_reuses_unaffected_partition_and_preserves_old_bundle() -> None:
    a = _instance()
    b = a.model_copy(update={"indicator_id": "volatility"})
    plan = FeatureDependencyPlan(
        required_instances=(a, b), ordered_instances=(a, b),
        required_columns=("moving_average.value", "volatility.value"), cutoff_at=CUTOFF,
        lookback_requirement=20, warmup_requirement=20,
    )
    store = FeatureStore()
    initial_rows = {
        a: (_row("cn.stock:000001", date(2026, 1, 3)),),
        b: (_row("cn.stock:000001", date(2026, 1, 3)).model_copy(update={"indicator_id": "volatility", "unit": "ratio"}),),
    }
    first, bundle = _publish(store, plan, initial_rows)
    refs = {ref.indicator_id: ref for ref in first.feature_partition_refs}
    corrected = dict(initial_rows)
    corrected[a] = (_row("cn.stock:000001", date(2026, 1, 3), value=Decimal("1.25")),)
    second, _ = _publish(
        store, plan, corrected, correction_of_snapshot_id=first.feature_snapshot_id,
        correction_of_partition_ids={a: refs[a.indicator_id].feature_partition_id},
    )
    second_refs = {ref.indicator_id: ref for ref in second.feature_partition_refs}
    assert second_refs[b.indicator_id] == refs[b.indicator_id]
    assert second_refs[a.indicator_id].revision == 2
    assert store.published_bundle(bundle.feature_bundle_id) == bundle
    assert store.published_snapshot(first.feature_snapshot_id) == first


def test_unchanged_downstream_value_still_gets_new_correction_lineage() -> None:
    a = _instance()
    b = a.model_copy(update={"indicator_id": "volatility"})
    plan = FeatureDependencyPlan(
        required_instances=(b,), ordered_instances=(a, b),
        dependency_edges=({"dependency": a, "consumer": b},),
        required_columns=("moving_average.value", "volatility.value"), cutoff_at=CUTOFF,
        lookback_requirement=20, warmup_requirement=20,
    )
    store = FeatureStore()
    rows = {
        a: (_row("cn.stock:000001", date(2026, 1, 3)),),
        b: (_row("cn.stock:000001", date(2026, 1, 3)).model_copy(update={"indicator_id": "volatility", "unit": "ratio"}),),
    }
    first, _ = _publish(store, plan, rows)
    old_refs = {ref.indicator_id: ref for ref in first.feature_partition_refs}
    rows[a] = (_row("cn.stock:000001", date(2026, 1, 3), value=Decimal("1.25")),)
    second, _ = _publish(
        store, plan, rows, correction_of_snapshot_id=first.feature_snapshot_id,
        correction_of_partition_ids={instance: old_refs[instance.indicator_id].feature_partition_id for instance in (a, b)},
    )
    new_ref = next(ref for ref in second.feature_partition_refs if ref.indicator_id == b.indicator_id)
    assert new_ref.feature_partition_id != old_refs[b.indicator_id].feature_partition_id
    assert new_ref.partition_hash == old_refs[b.indicator_id].partition_hash
    assert new_ref.revision == 2
    assert new_ref.storage_ref.relative_path != old_refs[b.indicator_id].storage_ref.relative_path


def test_late_failure_leaves_no_partitions_snapshot_or_bundle_registered() -> None:
    instance = _instance()
    store = FeatureStore()
    plan = _single_plan(instance)
    rows = {instance: (_row("cn.stock:000001", date(2026, 1, 3)),)}
    snapshot_id = _rid(ResourceType.FEATURE_SNAPSHOT, 80)
    bundle_id = _rid(ResourceType.FEATURE_BUNDLE, 81)
    with pytest.raises(ValidationError, match="consumer_ref"):
        _publish(store, plan, rows, snapshot_id=snapshot_id, bundle_id=bundle_id, consumer_ref=" ")
    with pytest.raises(KeyError):
        store.published_snapshot(snapshot_id)
    with pytest.raises(KeyError):
        store.published_bundle(bundle_id)
    # 发布失败不能留下一个会导致后续正常重试被拒绝的分区。
    _publish(store, plan, rows, snapshot_id=snapshot_id, bundle_id=bundle_id)


def test_feature_row_rejects_datetime_for_date_value_type() -> None:
    payload = _row("cn.stock:000001", date(2026, 1, 3)).model_dump(mode="python")
    payload.update(value=datetime(2026, 1, 3, tzinfo=UTC), value_type="date")
    with pytest.raises(ValidationError, match="value does not match value_type"):
        FeatureRow.model_validate(payload)


def test_feature_store_writes_deterministic_parquet_and_preserves_real_publication_time(tmp_path) -> None:
    publication_time = datetime(2026, 9, 30, 12, 34, 56, tzinfo=UTC)
    store = FeatureStore(tmp_path, clock=lambda: publication_time)
    plan = _single_plan(_instance())
    snapshot, _ = _publish(store, plan, {_instance(): (_row("cn.stock:000001", date(2026, 1, 3)),)})
    partition = store.published_partition(snapshot.feature_partition_refs[0].feature_partition_id)
    payload_path = tmp_path / "storage" / "app" / Path(partition.storage_ref.relative_path)
    assert payload_path.is_file()
    assert payload_path.read_bytes() == store.read_partition_payload(partition.feature_partition_id)
    assert partition.storage_ref.size_bytes == payload_path.stat().st_size
    assert partition.created_at == publication_time
    assert partition.published_at == publication_time
    assert partition.published_at > partition.cutoff_at


def test_registered_indicator_schema_is_fail_closed() -> None:
    instance = _instance()
    plan = _single_plan(instance, lookback_requirement=20, warmup_requirement=20)
    bad_rows = (_row("cn.stock:000001", date(2026, 1, 3)).model_copy(update={"unit": "percent"}),)
    with pytest.raises(FeatureMaterializationError, match="registered output schema"):
        _publish(
            FeatureStore(indicator_registry=default_indicator_registry()),
            plan,
            {instance: bad_rows},
        )


def test_formal_publication_requires_pit_coverage_and_uses_explicit_clock() -> None:
    instance = _instance()
    plan = _single_plan(instance, lookback_requirement=20, warmup_requirement=20)
    rows = (_row("cn.stock:000001", date(2026, 1, 3)),)
    with pytest.raises(FeatureMaterializationError, match="coverage evidence"):
        _publish(
            FeatureStore(clock=lambda: CUTOFF),
            plan,
            {instance: rows},
            consumer_kind=ConsumerKind.FORMAL_BACKTEST,
        )
    snapshot, _ = _publish(
        FeatureStore(clock=lambda: CUTOFF),
        plan,
        {instance: rows},
        consumer_kind=ConsumerKind.FORMAL_BACKTEST,
        expected_entity_keys=("cn.stock:000001",),
        expected_trade_dates=(date(2026, 1, 3),),
    )
    assert snapshot.snapshot_type is FeatureSnapshotType.CLOSE_CORE


def test_late_preview_is_historical_rebuild_not_close_core() -> None:
    instance = _instance()
    plan = _single_plan(instance, lookback_requirement=20, warmup_requirement=20)
    snapshot, bundle = _publish(
        FeatureStore(clock=lambda: CUTOFF + timedelta(seconds=1)),
        plan,
        {instance: (_row("cn.stock:000001", date(2026, 1, 3)),)},
        consumer_kind=ConsumerKind.PREVIEW,
    )
    assert snapshot.snapshot_type is FeatureSnapshotType.HISTORICAL_REBUILD
    assert snapshot.publication_status is PublicationStatus.PROVISIONAL
    assert bundle.consumer_kind is ConsumerKind.PREVIEW


def test_formal_publication_rejects_late_computation_even_with_complete_rows() -> None:
    instance = _instance()
    plan = _single_plan(instance, lookback_requirement=20, warmup_requirement=20)
    with pytest.raises(FeaturePublicationError, match="published_at.*cutoff_at"):
        _publish(
            FeatureStore(clock=lambda: CUTOFF + timedelta(seconds=1)),
            plan,
            {instance: (_row("cn.stock:000001", date(2026, 1, 3)),)},
            consumer_kind=ConsumerKind.FORMAL_BACKTEST,
            expected_entity_keys=("cn.stock:000001",),
            expected_trade_dates=(date(2026, 1, 3),),
        )


def test_retry_rechecks_existing_bundle_partition_bytes(tmp_path) -> None:
    instance = _instance()
    plan = _single_plan(instance, lookback_requirement=20, warmup_requirement=20)
    store = FeatureStore(tmp_path, clock=lambda: CUTOFF)
    kwargs = {
        "consumer_kind": ConsumerKind.FORMAL_BACKTEST,
        "expected_entity_keys": ("cn.stock:000001",),
        "expected_trade_dates": (date(2026, 1, 3),),
        "snapshot_id": _rid(ResourceType.FEATURE_SNAPSHOT, 110),
        "bundle_id": _rid(ResourceType.FEATURE_BUNDLE, 111),
    }
    snapshot, _ = _publish(store, plan, {instance: (_row("cn.stock:000001", date(2026, 1, 3)),)}, **kwargs)
    partition = store.published_partition(snapshot.feature_partition_refs[0].feature_partition_id)
    path = tmp_path / "storage" / "app" / Path(partition.storage_ref.relative_path)
    path.write_bytes(b"corrupted")
    with pytest.raises(FeaturePublicationError, match="hash mismatch"):
        _publish(store, plan, {instance: (_row("cn.stock:000001", date(2026, 1, 3)),)}, **kwargs)


def test_formal_coverage_rejects_missing_expected_trade_date() -> None:
    instance = _instance()
    plan = _single_plan(instance, lookback_requirement=20, warmup_requirement=20)
    with pytest.raises(FeatureMaterializationError, match="coverage"):
        _publish(
            FeatureStore(clock=lambda: CUTOFF),
            plan,
            {instance: (_row("cn.stock:000001", date(2026, 1, 3)),)},
            consumer_kind=ConsumerKind.FORMAL_BACKTEST,
            expected_entity_keys=("cn.stock:000001",),
            expected_trade_dates=(date(2026, 1, 2),),
        )


@pytest.mark.parametrize("damaged_input", ["missing", "corrupt"])
def test_correction_closure_failure_removes_only_new_files(tmp_path, damaged_input) -> None:
    a = _instance()
    b = a.model_copy(update={"indicator_id": "volatility"})
    plan = FeatureDependencyPlan(
        required_instances=(a, b), ordered_instances=(a, b),
        required_columns=("moving_average.value", "volatility.value"), cutoff_at=CUTOFF,
        lookback_requirement=20, warmup_requirement=20,
    )
    store = FeatureStore(tmp_path, clock=lambda: CUTOFF)
    rows = {
        a: (_row("cn.stock:000001", date(2026, 1, 3)),),
        b: (_row("cn.stock:000001", date(2026, 1, 3)).model_copy(
            update={"indicator_id": "volatility", "unit": "ratio"}
        ),),
    }
    formal = {
        "consumer_kind": ConsumerKind.FORMAL_BACKTEST,
        "expected_entity_keys": ("cn.stock:000001",),
        "expected_trade_dates": (date(2026, 1, 3),),
    }
    original_snapshot, original_bundle = _publish(store, plan, rows, **formal)
    refs = {ref.indicator_id: ref for ref in original_snapshot.feature_partition_refs}
    original_partitions = {
        ref.feature_partition_id: store.published_partition(ref.feature_partition_id)
        for ref in refs.values()
    }
    storage_root = tmp_path / "storage" / "app"
    damaged_path = storage_root / refs[b.indicator_id].storage_ref.relative_path
    if damaged_input == "missing":
        damaged_path.unlink()
    else:
        original_bytes = damaged_path.read_bytes()
        damaged_path.write_bytes(bytes([original_bytes[0] ^ 1]) + original_bytes[1:])
    # 用真实文件缺失/同长度篡改触发闭包验证，不 mock 风险层。
    existing_files = {path: path.read_bytes() for path in storage_root.rglob("*.parquet")}
    corrected = dict(rows)
    corrected[a] = (_row("cn.stock:000001", date(2026, 1, 3), value=Decimal("1.25")),)
    correction_snapshot_id = _rid(ResourceType.FEATURE_SNAPSHOT, 90)
    correction_bundle_id = _rid(ResourceType.FEATURE_BUNDLE, 91)
    error = "file is missing" if damaged_input == "missing" else "payload hash mismatch"
    with pytest.raises(FeaturePublicationError, match=error):
        _publish(
            store, plan, corrected, **formal,
            snapshot_id=correction_snapshot_id, bundle_id=correction_bundle_id,
            correction_of_snapshot_id=original_snapshot.feature_snapshot_id,
            correction_of_partition_ids={a: refs[a.indicator_id].feature_partition_id},
        )
    assert {path: path.read_bytes() for path in storage_root.rglob("*.parquet")} == existing_files
    assert not tuple((storage_root / ".staging").iterdir())
    assert store.published_snapshot(original_snapshot.feature_snapshot_id) == original_snapshot
    assert store.published_bundle(original_bundle.feature_bundle_id) == original_bundle
    for partition_id, original_partition in original_partitions.items():
        assert store.published_partition(partition_id) == original_partition
        assert store.is_pinned(partition_id)
    with pytest.raises(KeyError):
        store.published_snapshot(correction_snapshot_id)
    with pytest.raises(KeyError):
        store.published_bundle(correction_bundle_id)



def test_materializer_rejects_global_definition_even_for_direct_plan() -> None:
    from src.schemas.platform.indicator import IndicatorDefinition
    from src.services.platform.indicator_registry import IndicatorRegistry

    payload = default_indicator_registry().get("moving_average", "1.0.0").model_dump(mode="python")
    payload.update(domain="global", definition_hash="")
    registry = IndicatorRegistry((IndicatorDefinition.model_validate(payload),))
    instance = _instance()
    with pytest.raises(FeatureMaterializationError, match="domain"):
        _publish(FeatureStore(indicator_registry=registry), _single_plan(instance),
                 {instance: (_row("cn.stock:000001", date(2026, 1, 3)),)})


def test_partial_correction_preserves_fixed_refs_after_formal_retention_promotion() -> None:
    a = _instance()
    b = a.model_copy(update={"indicator_id": "volatility"})
    plan = FeatureDependencyPlan(
        required_instances=(a, b), ordered_instances=(a, b),
        required_columns=("moving_average.value", "volatility.value"), cutoff_at=CUTOFF,
        lookback_requirement=20, warmup_requirement=20,
    )
    store = FeatureStore(clock=lambda: CUTOFF)
    rows = {
        a: (_row("cn.stock:000001", date(2026, 1, 3)),),
        b: (_row("cn.stock:000001", date(2026, 1, 3)).model_copy(update={"indicator_id": "volatility", "unit": "ratio"}),),
    }
    preview, preview_bundle = _publish(store, plan, rows)
    refs = {ref.indicator_id: ref for ref in preview.feature_partition_refs}
    formal = {"consumer_kind": ConsumerKind.FORMAL_BACKTEST, "expected_entity_keys": ("cn.stock:000001",),
              "expected_trade_dates": (date(2026, 1, 3),)}
    _, formal_bundle = _publish(store, plan, rows, consumer_ref="strategy:formal", **formal)
    assert store.is_pinned(refs[b.indicator_id].feature_partition_id)
    rows[a] = (_row("cn.stock:000001", date(2026, 1, 3), value=Decimal("1.25")),)
    corrected, _ = _publish(store, plan, rows, correction_of_snapshot_id=preview.feature_snapshot_id,
                            correction_of_partition_ids={a: refs[a.indicator_id].feature_partition_id})
    unchanged = next(ref for ref in corrected.feature_partition_refs if ref.indicator_id == b.indicator_id)
    assert unchanged == refs[b.indicator_id]
    assert store.published_bundle(preview_bundle.feature_bundle_id) == preview_bundle
    assert store.published_bundle(formal_bundle.feature_bundle_id) == formal_bundle



def test_feature_publication_lock_is_exclusive_across_processes(tmp_path) -> None:
    import subprocess
    import sys

    script = """
import sys
from pathlib import Path
from src.services.platform.feature_store import FeatureStore
store = FeatureStore(Path(sys.argv[1]))
with store._publication_guard():
    print("LOCKED", flush=True)
    sys.stdin.readline()
"""
    child = subprocess.Popen([sys.executable, "-u", "-c", script, str(tmp_path)],
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        assert child.stdout.readline().strip() == "LOCKED"
        instance = _instance()
        store = FeatureStore(tmp_path, clock=lambda: CUTOFF)
        with pytest.raises(FeaturePublicationError, match="publication.*busy"):
            _publish(store, _single_plan(instance), {instance: (_row("cn.stock:000001", date(2026, 1, 3)),)})
        _, stderr = child.communicate("release\n", timeout=15)
        assert child.returncode == 0, stderr
        _publish(store, _single_plan(instance), {instance: (_row("cn.stock:000001", date(2026, 1, 3)),)})
    finally:
        if child.poll() is None:
            child.kill()
            child.communicate(timeout=15)



def test_bundle_requires_exact_column_coverage_by_fixed_partition_refs() -> None:
    instance = _instance()
    _, bundle = _publish(FeatureStore(clock=lambda: CUTOFF), _single_plan(instance),
                         {instance: (_row("cn.stock:000001", date(2026, 1, 3)),)})
    values = bundle.model_dump(mode="python", exclude={"bundle_hash"})
    values["required_columns"] = ("moving_average.value", "volatility.value")
    with pytest.raises(ValidationError, match="column.*coverage"):
        FeatureBundle.build(**values)


@pytest.mark.parametrize("changed_boundary", ["as_of_trade_date", "cutoff_at", "dependency_plan_hash"])
def test_correction_cannot_change_logical_manifest_identity(tmp_path, changed_boundary) -> None:
    instance = _instance()
    plan = _single_plan(instance)
    store = FeatureStore(tmp_path, clock=lambda: CUTOFF)
    first_snapshot, first_bundle = _publish(
        store, plan, {instance: (_row("cn.stock:000001", date(2026, 1, 3)),)},
    )
    old_ref = first_snapshot.feature_partition_refs[0]
    old_files = set(tmp_path.rglob("*.parquet"))
    as_of_trade_date = first_snapshot.as_of_trade_date
    cutoff_at = CUTOFF
    if changed_boundary == "as_of_trade_date":
        as_of_trade_date += timedelta(days=1)
    elif changed_boundary == "cutoff_at":
        cutoff_at += timedelta(seconds=1)
        plan = FeatureDependencyPlan.model_validate(
            plan.model_dump(exclude={"plan_hash"}) | {"cutoff_at": cutoff_at}
        )
    else:
        plan = FeatureDependencyPlan.model_validate(
            plan.model_dump(exclude={"plan_hash"}) | {"capability_ids": ("changed_capability",)}
        )

    with pytest.raises(FeaturePublicationError, match="logical manifest identity"):
        store.materialize_and_publish(
            plan,
            {instance: (_row("cn.stock:000001", date(2026, 1, 3), value=Decimal("1.30")),)},
            data_snapshot_ids=first_snapshot.data_snapshot_ids,
            cutoff_at=cutoff_at,
            as_of_trade_date=as_of_trade_date,
            consumer_ref="strategy:invalid-correction",
            correction_of_snapshot_id=first_snapshot.feature_snapshot_id,
            correction_of_partition_ids={instance: old_ref.feature_partition_id},
        )
    assert set(tmp_path.rglob("*.parquet")) == old_files
    assert store.published_snapshot(first_snapshot.feature_snapshot_id) == first_snapshot
    assert store.published_bundle(first_bundle.feature_bundle_id) == first_bundle
