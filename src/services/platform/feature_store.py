from __future__ import annotations

import json
import os
import shutil
import tempfile
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from datetime import date, datetime, timezone
from decimal import Decimal
from functools import wraps
from hashlib import sha256
from pathlib import Path
from threading import RLock
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from src.schemas.platform.feature import (
    FeatureBundle,
    FeatureMaterializationError,
    FeaturePartition,
    FeaturePartitionRef,
    FeatureRow,
    FeatureSnapshot,
    FeatureSnapshotType,
)
from src.schemas.platform.enums import ConsumerKind, PublicationStatus, QualityStatus, ResourceType, RetentionClass, RevisionKind
from src.schemas.platform.hashing import compute_content_hash
from src.schemas.platform.indicator import FeatureDependencyPlan, FeatureInstanceKey
from src.services.platform.indicator_registry import IndicatorRegistry, default_indicator_registry
from src.schemas.platform.resources import generate_resource_id
from src.schemas.platform.storage import StorageBackend, StorageNamespace, StorageRef
from src.artifacts.namespace import StorageNamespaceResolver, fsync_directory
from src.repositories.platform.feature import FeatureRepository

if TYPE_CHECKING:
    from src.repositories.platform.database import PostgresDatabase


class FeaturePublicationError(FeatureMaterializationError):
    pass


def _stable_id(resource_type: ResourceType, seed: Any) -> str:
    digest = sha256(compute_content_hash(seed).encode("ascii")).digest()
    return generate_resource_id(resource_type, timestamp_ms=0, random_bits=int.from_bytes(digest[:10], "big") & ((1 << 74) - 1))


def _locked(method):
    @wraps(method)
    def call(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)
    return call


def _publication_locked(method):
    @wraps(method)
    def call(self, *args, **kwargs):
        with self._publication_guard():
            return method(self, *args, **kwargs)
    return call


def affected_feature_instances(
    plan: FeatureDependencyPlan,
    corrected_instances: Sequence[FeatureInstanceKey],
) -> tuple[FeatureInstanceKey, ...]:
    """Return corrected roots plus all transitive downstream consumers in plan order."""

    known = {item.sort_key: item for item in plan.ordered_instances}
    corrected_keys = {item.sort_key for item in corrected_instances}
    if not corrected_keys <= known.keys():
        raise FeatureMaterializationError("corrected instances must belong to the dependency plan")
    affected = set(corrected_keys)
    changed = True
    while changed:
        changed = False
        for edge in plan.dependency_edges:
            if edge.dependency.sort_key in affected and edge.consumer.sort_key not in affected:
                affected.add(edge.consumer.sort_key)
                changed = True
    return tuple(item for item in plan.ordered_instances if item.sort_key in affected)


def _partition_key(instance: FeatureInstanceKey, date_from: date | None, date_to: date | None) -> str:
    left = date_from.isoformat() if date_from is not None else "all"
    right = date_to.isoformat() if date_to is not None else left
    universe = instance.universe_scope_hash[7:] if instance.universe_scope_hash else "global"
    return (
        f"{instance.indicator_id}/definition={instance.definition_version}/"
        f"frequency={instance.frequency}/parameter={instance.parameter_hash[7:]}/"
        f"universe={universe}/{left}_{right}"
    )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class FeatureStore:
    """Feature materialization boundary for isolated workers and PostgreSQL control-plane publication.

    The default mode remains an isolated in-memory catalog; passing a PostgresDatabase
    enables the same immutable file + control-plane transaction without connecting to
    providers, production /data, or schedulers.
    """

    def __init__(
        self,
        runtime_root: Path | str | None = None,
        *,
        clock: Callable[[], datetime] = _utc_now,
        indicator_registry: IndicatorRegistry | None = None,
        database: "PostgresDatabase | None" = None,
        repository: FeatureRepository | None = None,
    ) -> None:
        self._lock = RLock()
        self._temporary_root = tempfile.TemporaryDirectory(prefix="visory-feature-store-") if runtime_root is None else None
        root = Path(self._temporary_root.name if self._temporary_root is not None else runtime_root)
        self._resolver = StorageNamespaceResolver(root)
        self._clock = clock
        self._database = database
        self._repository = repository or FeatureRepository()
        # A materializer without a Definition registry cannot prove schema, PIT, or warmup semantics.
        self._indicator_registry = indicator_registry or default_indicator_registry()
        self._partitions: dict[str, FeaturePartition] = {}
        self._snapshots: dict[str, FeatureSnapshot] = {}
        self._bundles: dict[str, FeatureBundle] = {}
        self._pinned: set[str] = set()
        self._partition_payloads: dict[str, bytes] = {}

    def _hydrate_snapshot_from_database(self, snapshot_id: str) -> None:
        if snapshot_id in self._snapshots or self._database is None:
            return
        with self._database.transaction() as session:
            snapshot = self._repository.get_snapshot(session, snapshot_id)
            if snapshot is None:
                return
            partitions = tuple(
                self._repository.get_partition(session, ref.feature_partition_id)
                for ref in snapshot.feature_partition_refs
            )
        if any(partition is None for partition in partitions):
            raise FeaturePublicationError("persisted snapshot references a missing partition")
        self._snapshots[snapshot.feature_snapshot_id] = snapshot
        for partition in partitions:
            assert partition is not None
            self._partitions[partition.feature_partition_id] = partition
            if partition.retention_class is RetentionClass.PINNED:
                self._pinned.add(partition.feature_partition_id)

    def _hydrate_bundle_from_database(self, bundle_id: str) -> None:
        if bundle_id in self._bundles or self._database is None:
            return
        with self._database.transaction() as session:
            bundle = self._repository.get_bundle(session, bundle_id)
            if bundle is None:
                return
            partitions = tuple(
                self._repository.get_partition(session, ref.feature_partition_id)
                for ref in bundle.required_partition_refs
            )
        if any(partition is None for partition in partitions):
            raise FeaturePublicationError("persisted bundle references a missing partition")
        self._bundles[bundle.feature_bundle_id] = bundle
        for partition in partitions:
            assert partition is not None
            self._partitions[partition.feature_partition_id] = partition
            if partition.retention_class is RetentionClass.PINNED:
                self._pinned.add(partition.feature_partition_id)
        for snapshot_id in bundle.feature_snapshot_ids:
            self._hydrate_snapshot_from_database(snapshot_id)

    @contextmanager
    def _publication_guard(self) -> Iterator[None]:
        # 锁文件保留固定 inode；不得删除，否则不同进程可能锁住不同文件。
        lock_path = self._resolver.resolve(".feature-publication.lock", allow_internal=True)
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("a+b") as handle:
            if handle.tell() == 0:
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                acquire = lambda: msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                release = lambda: msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                acquire = lambda: fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                release = lambda: fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            try:
                acquire()
            except OSError as exc:
                raise FeaturePublicationError("feature publication is busy or its lock is unavailable; retry required") from exc
            try:
                yield
            finally:
                handle.seek(0)
                release()

    @_locked
    @_publication_locked
    def materialize_and_publish(
        self,
        plan: FeatureDependencyPlan,
        rows_by_instance: Mapping[FeatureInstanceKey, Sequence[FeatureRow]],
        *,
        snapshot_id: str | None = None,
        bundle_id: str | None = None,
        data_snapshot_ids: tuple[str, ...],
        quality_report_id: str | None = None,
        cutoff_at: datetime,
        as_of_trade_date: date,
        consumer_ref: str,
        consumer_kind: ConsumerKind | str = ConsumerKind.PREVIEW,
        date_from: date | None = None,
        date_to: date | None = None,
        expected_entity_keys: Sequence[str] | None = None,
        expected_trade_dates: Sequence[date] | None = None,
        snapshot_type: FeatureSnapshotType | str | None = None,
        correction_of_snapshot_id: str | None = None,
        correction_of_partition_ids: Mapping[FeatureInstanceKey, str] | None = None,
    ) -> tuple[FeatureSnapshot, FeatureBundle]:
        if plan.cutoff_at != cutoff_at:
            raise FeatureMaterializationError("materialization cutoff_at must match FeatureDependencyPlan")
        if cutoff_at.tzinfo is None or cutoff_at.utcoffset() is None:
            raise FeatureMaterializationError("cutoff_at must be timezone-aware")
        if date_to is not None and date_from is None:
            raise FeatureMaterializationError("date_to requires date_from")
        if date_from is not None and date_to is not None and date_to < date_from:
            raise FeatureMaterializationError("date_to must not precede date_from")
        if (plan.date_from, plan.date_to) != (date_from, date_to):
            raise FeatureMaterializationError("materialization date range must match FeatureDependencyPlan")
        declared_instances = set(plan.ordered_instances)
        self._validate_plan_columns(plan)
        if set(rows_by_instance) != declared_instances:
            raise FeatureMaterializationError("rows_by_instance must exactly match FeatureDependencyPlan")
        kind = ConsumerKind(consumer_kind)
        if correction_of_snapshot_id is not None:
            self._hydrate_snapshot_from_database(correction_of_snapshot_id)
        if bundle_id is not None:
            self._hydrate_bundle_from_database(bundle_id)
        requested_snapshot_type = FeatureSnapshotType(snapshot_type) if snapshot_type is not None else None
        publication_time = self._clock()
        if publication_time.tzinfo is None or publication_time.utcoffset() is None:
            raise FeatureMaterializationError("feature store clock must return a timezone-aware datetime")
        if kind is ConsumerKind.FORMAL_BACKTEST and plan.cutoff_at is None:
            raise FeatureMaterializationError("formal materialization requires a point-in-time cutoff")
        if kind is ConsumerKind.FORMAL_BACKTEST:
            if expected_entity_keys is None or expected_trade_dates is None:
                raise FeatureMaterializationError("formal materialization requires coverage evidence")
            if publication_time > cutoff_at:
                raise FeaturePublicationError("formal published_at must not exceed cutoff_at")
        if requested_snapshot_type is FeatureSnapshotType.HISTORICAL_REBUILD and kind is ConsumerKind.FORMAL_BACKTEST:
            raise FeaturePublicationError("historical rebuild cannot be published as a formal bundle")
        if requested_snapshot_type in {FeatureSnapshotType.CLOSE_CORE, FeatureSnapshotType.LATE_A_SHARE} and publication_time > cutoff_at:
            raise FeaturePublicationError("published_at must not exceed cutoff_at for live feature snapshots")
        effective_snapshot_type = (
            FeatureSnapshotType.CORRECTION
            if correction_of_snapshot_id
            else requested_snapshot_type
            or (FeatureSnapshotType.CLOSE_CORE if publication_time <= cutoff_at else FeatureSnapshotType.HISTORICAL_REBUILD)
        )
        if effective_snapshot_type in {FeatureSnapshotType.CLOSE_CORE, FeatureSnapshotType.LATE_A_SHARE} and publication_time > cutoff_at:
            raise FeaturePublicationError("published_at must not exceed cutoff_at for live feature snapshots")
        if effective_snapshot_type is FeatureSnapshotType.HISTORICAL_REBUILD and kind is ConsumerKind.FORMAL_BACKTEST:
            raise FeaturePublicationError("historical rebuild cannot be published as a formal bundle")
        effective_revision_kind = (
            RevisionKind.CORRECTION
            if correction_of_snapshot_id
            else RevisionKind.REBUILD if effective_snapshot_type is FeatureSnapshotType.HISTORICAL_REBUILD else RevisionKind.INITIAL
        )

        if (correction_of_snapshot_id is None) != (correction_of_partition_ids is None):
            raise FeatureMaterializationError("correction snapshot and partition lineage must be supplied together")
        if correction_of_snapshot_id is not None and not correction_of_partition_ids:
            raise FeatureMaterializationError("correction snapshot requires correction partition lineage")
        if correction_of_partition_ids:
            affected = affected_feature_instances(plan, tuple(correction_of_partition_ids))
            if set(correction_of_partition_ids) != set(affected):
                raise FeatureMaterializationError("correction partition lineage must cover all affected dependency instances")
            previous_snapshot = self._snapshots.get(correction_of_snapshot_id or "")
            if previous_snapshot is None:
                raise FeaturePublicationError("correction snapshot must supersede a published snapshot")
            if len(set(correction_of_partition_ids.values())) != len(correction_of_partition_ids):
                raise FeatureMaterializationError("correction partition lineage cannot reuse a predecessor")
            if not set(correction_of_partition_ids.values()) <= {
                item.feature_partition_id for item in previous_snapshot.feature_partition_refs
            }:
                raise FeatureMaterializationError(
                    "correction partition lineage must match the superseded snapshot partitions"
                )

        preserved_refs: dict[FeatureInstanceKey, FeaturePartitionRef] = {}
        staged: dict[str, FeaturePartition] = {}
        staged_payloads: dict[str, bytes] = {}
        staged_by_instance: dict[FeatureInstanceKey, FeaturePartition] = {}
        for instance in plan.ordered_instances:
            rows = rows_by_instance.get(instance)
            if rows is None:
                raise FeatureMaterializationError(f"missing rows for dependency plan instance {instance.indicator_id}")
            all_items = tuple(rows)
            FeaturePartition.validate_rows(all_items, cutoff_at=cutoff_at, data_snapshot_ids=data_snapshot_ids)
            if any(item.available_at > cutoff_at for item in all_items):
                raise FeatureMaterializationError("available_at exceeds cutoff_at")
            if any(item.indicator_id != instance.indicator_id or item.definition_version != instance.definition_version for item in all_items):
                raise FeatureMaterializationError("feature rows do not match dependency plan instance")
            self._validate_registered_schema(instance, all_items, plan, kind)
            previous_id = correction_of_partition_ids.get(instance) if correction_of_partition_ids else None

            items = all_items
            if date_from is not None:
                output_end = date_to or date_from
                output_items = tuple(item for item in all_items if date_from <= item.trade_date <= output_end)
                if not output_items:
                    raise FeatureMaterializationError(f"missing output rows after warmup for {instance.indicator_id}")
                if plan.warmup_requirement:
                    warmup_rows = tuple(item for item in all_items if item.trade_date < date_from)
                    if any(item.value is None or item.quality_status is not QualityStatus.COMPLETE for item in warmup_rows):
                        raise FeaturePublicationError("quality gate rejected warmup inputs")
                    output_entities = {item.entity_key for item in output_items}
                    for entity_key in output_entities:
                        warmup_dates = {
                            item.trade_date
                            for item in all_items
                            if item.entity_key == entity_key and item.trade_date < date_from
                        }
                        if len(warmup_dates) < plan.warmup_requirement:
                            raise FeatureMaterializationError(
                                f"warmup evidence is missing for {instance.indicator_id}:{entity_key}"
                            )
                # Warmup rows are inputs to computation only; they never leak into the published partition.
                items = output_items
            if expected_entity_keys is not None:
                expected = frozenset(expected_entity_keys)
                if not expected or any(not item for item in expected):
                    raise FeatureMaterializationError("expected_entity_keys must be non-empty")
                for output_date in {item.trade_date for item in items}:
                    actual = frozenset(item.entity_key for item in items if item.trade_date == output_date)
                    if actual != expected:
                        raise FeatureMaterializationError("feature coverage does not match the expected entity universe")
            if expected_trade_dates is not None:
                expected_dates = frozenset(expected_trade_dates)
                if not expected_dates:
                    raise FeatureMaterializationError("expected_trade_dates must be non-empty")
                actual_dates = frozenset(item.trade_date for item in items)
                if actual_dates != expected_dates:
                    raise FeatureMaterializationError("feature coverage does not match the expected trade dates")

            # A correction only publishes changed partitions. Unaffected partitions are
            # copied by fixed reference, but their recomputed bytes must prove unchanged.
            if correction_of_snapshot_id is not None and previous_id is None:
                previous_snapshot = self._snapshots[correction_of_snapshot_id]
                previous_ref = next(
                    (
                        ref for ref in previous_snapshot.feature_partition_refs
                        if ref.indicator_id == instance.indicator_id
                        and ref.definition_version == instance.definition_version
                        and (
                            self._partitions.get(ref.feature_partition_id) is not None
                            and self._partitions[ref.feature_partition_id].partition_key
                            == _partition_key(instance, date_from, date_to)
                            and self._partitions[ref.feature_partition_id].frequency == instance.frequency
                            and self._partitions[ref.feature_partition_id].universe_scope_hash == instance.universe_scope_hash
                        )
                    ),
                    None,
                )
                if previous_ref is None:
                    raise FeaturePublicationError("correction snapshot is missing an unaffected partition reference")
                if FeaturePartition.compute_hash(items) != previous_ref.partition_hash:
                    raise FeatureMaterializationError(
                        "correction partition lineage must include every changed partition"
                    )
                previous_partition = self._partitions.get(previous_ref.feature_partition_id)
                if previous_partition is None:
                    raise FeaturePublicationError("correction snapshot references a missing unaffected partition")
                staged_by_instance[instance] = previous_partition
                preserved_refs[instance] = previous_ref
                continue

            partition_payload = FeaturePartition.parquet_bytes(items)
            partition_hash = FeaturePartition.compute_hash(items)
            if "sha256:" + sha256(partition_payload).hexdigest() != partition_hash:
                raise FeatureMaterializationError("feature Parquet hash is not deterministic")
            previous_partition = self._partitions.get(previous_id or "")
            if previous_id is not None and previous_partition is None:
                raise FeaturePublicationError("correction partition must supersede a published partition")
            revision = previous_partition.revision + 1 if previous_partition is not None else 1
            revision_kind = (
                RevisionKind.CORRECTION
                if previous_id
                else (RevisionKind.REBUILD if effective_snapshot_type is FeatureSnapshotType.HISTORICAL_REBUILD else RevisionKind.INITIAL)
            )
            input_partition_ids = tuple(sorted(
                staged_by_instance[edge.dependency].feature_partition_id
                for edge in plan.dependency_edges if edge.consumer == instance
            ))
            partition_id = _stable_id(
                ResourceType.FEATURE_PARTITION,
                {"instance": instance, "partition_hash": partition_hash, "range": [date_from, date_to],
                 "data_snapshot_ids": sorted(data_snapshot_ids), "cutoff_at": cutoff_at,
                 "input_partition_ids": input_partition_ids, "revision": revision,
                 "supersedes_id": previous_id},
            )
            storage_ref = StorageRef(
                storage_backend=StorageBackend.LOCAL_FS,
                storage_namespace=StorageNamespace.APP,
                relative_path=f"features/{_partition_key(instance, date_from, date_to)}/{partition_id}/{partition_hash[7:]}.parquet",
                content_hash=partition_hash,
                media_type="application/vnd.apache.parquet",
                size_bytes=len(partition_payload),
            )
            partition = FeaturePartition.build_from_rows(
                items,
                partition_id=partition_id,
                data_snapshot_ids=tuple(sorted(data_snapshot_ids)),
                partition_key=_partition_key(instance, date_from, date_to),
                storage_ref=storage_ref,
                frequency=instance.frequency,
                quality_report_id=(
                    quality_report_id
                    if quality_report_id is not None
                    else _stable_id(ResourceType.QUALITY_REPORT, partition_hash)
                ),
                cutoff_at=cutoff_at,
                created_at=publication_time,
                published_at=publication_time,
                input_partition_ids=input_partition_ids,
                universe_scope_hash=instance.universe_scope_hash,
                retention_class=self._retention_class_for(instance),
                revision=revision,
                revision_kind=revision_kind,
                supersedes_id=previous_id,
            )
            if correction_of_snapshot_id is not None and previous_id is None:
                prior_ids = {ref.feature_partition_id for ref in previous_snapshot.feature_partition_refs}
                if partition_id not in prior_ids:
                    raise FeaturePublicationError("changed partitions require explicit correction lineage")
            staged[partition.feature_partition_id] = partition
            staged_payloads[partition.feature_partition_id] = partition_payload
            staged_by_instance[instance] = partition

        if any(item.quality_status is not QualityStatus.COMPLETE for item in staged.values()):
            raise FeaturePublicationError("quality gate rejected feature publication")
        snapshot_id = snapshot_id or _stable_id(
            ResourceType.FEATURE_SNAPSHOT, {
                "plan": plan.plan_hash, "partitions": sorted(staged),
                "as_of_trade_date": as_of_trade_date, "data_snapshot_ids": sorted(data_snapshot_ids),
                "supersedes_id": correction_of_snapshot_id,
            }
        )

        def columns_for(instance: FeatureInstanceKey) -> tuple[str, ...]:
            prefix = f"{instance.indicator_id}."
            matching = tuple(column for column in plan.required_columns if column.startswith(prefix))
            if not matching:
                raise FeatureMaterializationError(
                    f"dependency plan has no required output columns for {instance.indicator_id}"
                )
            return matching

        snapshot = FeatureSnapshot.build(
            feature_snapshot_id=snapshot_id,
            snapshot_type=effective_snapshot_type,
            as_of_trade_date=as_of_trade_date,
            cutoff_at=cutoff_at,
            data_snapshot_ids=data_snapshot_ids,
            feature_partition_refs=tuple(
                preserved_refs.get(instance) or FeaturePartitionRef.from_partition(
                    staged_by_instance[instance],
                    required_columns=columns_for(instance),
                )
                for instance in plan.ordered_instances
            ),
            dependency_plan_hash=plan.plan_hash,
            definition_refs=tuple(sorted({f"{item.indicator_id}@{item.definition_version}" for item in plan.ordered_instances})),
            publication_status=(
                PublicationStatus.PROVISIONAL
                if effective_snapshot_type is FeatureSnapshotType.HISTORICAL_REBUILD
                else PublicationStatus.CERTIFIED
            ),
            quality_status=QualityStatus.COMPLETE,
            max_source_available_at=max(item.max_available_at for item in staged_by_instance.values()),
            quality_report_id=quality_report_id,
            revision=(
                self._snapshots[correction_of_snapshot_id].revision + 1
                if correction_of_snapshot_id in self._snapshots
                else (2 if correction_of_snapshot_id else 1)
            ),
            revision_kind=effective_revision_kind,
            supersedes_id=correction_of_snapshot_id,
            created_at=publication_time,
            published_at=publication_time,
        )
        bundle_refs = tuple(
            ref.model_copy(update={"retention_class": RetentionClass.PINNED})
            for ref in snapshot.feature_partition_refs
        ) if kind is ConsumerKind.FORMAL_BACKTEST else snapshot.feature_partition_refs
        bundle_id = bundle_id or _stable_id(
            ResourceType.FEATURE_BUNDLE,
            {"snapshot": snapshot.feature_snapshot_id, "columns": plan.required_columns,
             "consumer": consumer_ref, "consumer_kind": kind, "cutoff_at": cutoff_at,
             "range": [date_from, date_to], "universe_scope_hash": plan.universe_scope_hash},
        )
        bundle = FeatureBundle.build(
            feature_bundle_id=bundle_id,
            feature_snapshot_ids=(snapshot.feature_snapshot_id,),
            dependency_plan_hash=plan.plan_hash,
            required_partition_refs=bundle_refs,
            required_columns=plan.required_columns,
            consumer_ref=consumer_ref,
            consumer_kind=kind,
            cutoff_at=cutoff_at,
            date_from=date_from,
            date_to=date_to,
            universe_scope_hash=plan.universe_scope_hash,
        )
        published_snapshot = self._publish_atomic(tuple(staged.values()), staged_payloads, snapshot, bundle)
        return published_snapshot, bundle

    def _validate_plan_columns(self, plan: FeatureDependencyPlan) -> None:
        expected: set[str] = set()
        for instance in plan.ordered_instances:
            definition = self._indicator_registry.get(instance.indicator_id, instance.definition_version)
            if len(definition.output_schema) != 1 or definition.output_schema[0].alias != "value":
                raise FeatureMaterializationError(
                    "FeatureRow materialization requires exactly one output column named value"
                )
            expected.add(f"{instance.indicator_id}.value")
        supplied = set(plan.required_columns)
        unknown = supplied - expected
        missing = expected - supplied
        if unknown or missing:
            raise FeatureMaterializationError(
                "dependency plan required_columns must exactly match registered feature outputs"
            )

    def _retention_class_for(self, instance: FeatureInstanceKey) -> RetentionClass:
        definition = self._indicator_registry.get(instance.indicator_id, instance.definition_version)
        materialization = definition.materialization.upper()
        if materialization.startswith("F1") or materialization.startswith("F2") or materialization == "ALWAYS":
            return RetentionClass.AUDIT
        return RetentionClass.CACHE

    def _validate_registered_schema(
        self,
        instance: FeatureInstanceKey,
        rows: Sequence[FeatureRow],
        plan: FeatureDependencyPlan,
        consumer_kind: ConsumerKind,
    ) -> None:
        definition = self._indicator_registry.get(instance.indicator_id, instance.definition_version)
        if definition.domain != "a_share":
            raise FeatureMaterializationError("feature definition domain is outside A-share scope")
        try:
            canonical_parameters = json.loads(instance.canonical_parameter_json)
            resolved = self._indicator_registry.create_instance(
                instance.indicator_id,
                canonical_parameters,
                definition_version=instance.definition_version,
                universe_scope_hash=instance.universe_scope_hash,
            )
        except Exception as exc:
            raise FeatureMaterializationError("feature instance is not a valid registered definition") from exc
        if (
            resolved.parameter_hash != instance.parameter_hash
            or definition.frequency != instance.frequency
            or resolved.universe_scope_hash != instance.universe_scope_hash
        ):
            raise FeatureMaterializationError("feature instance identity does not match the registered definition")
        outputs = tuple(definition.output_schema)
        if len(outputs) != 1 or outputs[0].alias != "value":
            raise FeatureMaterializationError(
                "FeatureRow materialization requires exactly one output column named value"
            )
        output = outputs[0]
        if f"{instance.indicator_id}.{output.alias}" not in plan.required_columns:
            raise FeatureMaterializationError("dependency plan omits the registered output column")
        if consumer_kind is ConsumerKind.FORMAL_BACKTEST and not definition.point_in_time:
            raise FeatureMaterializationError("formal feature materialization requires a PIT definition")
        if plan.lookback_requirement < definition.lookback_requirement:
            raise FeatureMaterializationError("dependency plan lookback is below the definition requirement")
        if plan.warmup_requirement < definition.warmup_requirement:
            raise FeatureMaterializationError("dependency plan warmup is below the definition requirement")
        for row in rows:
            if row.value_type != output.value_type or row.unit != output.unit:
                raise FeatureMaterializationError("feature rows do not match the registered output schema")
            if row.value is None and not output.nullable:
                raise FeatureMaterializationError("registered output schema does not allow null feature values")
            if output.precision is not None and isinstance(row.value, Decimal):
                if -row.value.as_tuple().exponent > output.precision:
                    raise FeatureMaterializationError("feature value exceeds the registered output precision")

    def _verify_partition_file(self, partition: FeaturePartition) -> bytes:
        """Verify every fixed reference before control-plane publication or hydration."""
        target = self._resolver.resolve(partition.storage_ref)
        if not target.is_file():
            raise FeaturePublicationError("feature partition file is missing")
        payload = target.read_bytes()
        if len(payload) != partition.storage_ref.size_bytes:
            raise FeaturePublicationError("feature partition payload size mismatch")
        if "sha256:" + sha256(payload).hexdigest() != partition.partition_hash:
            raise FeaturePublicationError("feature partition payload hash mismatch")
        return payload

    def _verify_snapshot_files(
        self,
        snapshot: FeatureSnapshot,
        partition_by_id: Mapping[str, FeaturePartition],
    ) -> dict[str, bytes]:
        payloads: dict[str, bytes] = {}
        for ref in snapshot.feature_partition_refs:
            partition = partition_by_id.get(ref.feature_partition_id) or self._partitions.get(ref.feature_partition_id)
            if partition is None:
                raise FeaturePublicationError("feature snapshot references a missing partition")
            if partition.partition_hash != ref.partition_hash or partition.schema_hash != ref.schema_hash:
                raise FeaturePublicationError("feature snapshot reference does not match its partition")
            payloads[partition.feature_partition_id] = self._verify_partition_file(partition)
        return payloads

    def _publish_atomic(
        self,
        partitions: Sequence[FeaturePartition],
        payloads: Mapping[str, bytes],
        snapshot: FeatureSnapshot,
        bundle: FeatureBundle,
    ) -> FeatureSnapshot:
        existing_snapshot = self._snapshots.get(snapshot.feature_snapshot_id)
        if existing_snapshot is not None and existing_snapshot != snapshot:
            # Manifest identity excludes computed/published timestamps; retrying the same
            # deterministic snapshot may therefore have a different wall-clock envelope.
            if existing_snapshot.manifest_hash != snapshot.manifest_hash:
                raise FeaturePublicationError("publication identity already exists with different snapshot content")
            snapshot = existing_snapshot
        existing_bundle = self._bundles.get(bundle.feature_bundle_id)
        if existing_bundle is not None:
            if existing_bundle != bundle or existing_snapshot is None:
                raise FeaturePublicationError("publication identity already exists with different bundle content")
            for ref in existing_bundle.required_partition_refs:
                partition = self._partitions.get(ref.feature_partition_id)
                if partition is None:
                    raise FeaturePublicationError("published bundle references a missing partition")
                target = self._resolver.resolve(partition.storage_ref)
                if not target.is_file():
                    raise FeaturePublicationError("feature partition file is missing")
                payload = target.read_bytes()
                if len(payload) != partition.storage_ref.size_bytes or "sha256:" + sha256(payload).hexdigest() != partition.partition_hash:
                    raise FeaturePublicationError("feature partition payload hash mismatch")
            return existing_snapshot
        compare_exclusions = {"retention_class", "reference_count", "created_at", "published_at"}
        for partition in partitions:
            previous = self._partitions.get(partition.feature_partition_id)
            if previous is not None and previous.model_dump(exclude=compare_exclusions) != partition.model_dump(exclude=compare_exclusions):
                raise FeaturePublicationError("partition identity already exists with different content")
        if snapshot.publication_status is PublicationStatus.CERTIFIED and any(
            item.quality_status is not QualityStatus.COMPLETE for item in partitions
        ):
            raise FeaturePublicationError("certified snapshot cannot reference failed or partial partitions")
        if bundle.feature_snapshot_ids != (snapshot.feature_snapshot_id,):
            raise FeaturePublicationError("bundle must reference the published snapshot")
        if bundle.dependency_plan_hash != snapshot.dependency_plan_hash:
            raise FeaturePublicationError("bundle dependency plan must match the published snapshot")
        snapshot_refs = {item.feature_partition_id: item for item in snapshot.feature_partition_refs}
        for bundle_ref in bundle.required_partition_refs:
            snapshot_ref = snapshot_refs.get(bundle_ref.feature_partition_id)
            if snapshot_ref is None:
                raise FeaturePublicationError("bundle must reference exact partitions from the published snapshot")
            if bundle_ref.model_dump(mode="python", exclude={"retention_class"}) != snapshot_ref.model_dump(mode="python", exclude={"retention_class"}):
                raise FeaturePublicationError("bundle must reference exact partitions from the published snapshot")
        partition_by_id = {item.feature_partition_id: item for item in partitions}
        for partition in partitions:
            if partition.revision_kind is RevisionKind.CORRECTION:
                previous = self._partitions.get(partition.supersedes_id or "")
                if previous is None:
                    raise FeaturePublicationError("correction partition must supersede a published partition")
                if partition.revision != previous.revision + 1:
                    raise FeaturePublicationError("correction partition revision must increment its superseded partition")
                if (partition.indicator_id, partition.definition_version, partition.partition_key, partition.frequency, partition.universe_scope_hash) != (
                    previous.indicator_id, previous.definition_version, previous.partition_key,
                    previous.frequency, previous.universe_scope_hash,
                ):
                    raise FeaturePublicationError("correction partition must preserve logical partition identity")
        if snapshot.revision_kind is RevisionKind.CORRECTION:
            previous_snapshot = self._snapshots.get(snapshot.supersedes_id or "")
            if previous_snapshot is None:
                raise FeaturePublicationError("correction snapshot must supersede a published snapshot")
            if snapshot.revision != previous_snapshot.revision + 1:
                raise FeaturePublicationError("correction snapshot revision must increment its superseded snapshot")
            if (
                snapshot.as_of_trade_date != previous_snapshot.as_of_trade_date
                or snapshot.cutoff_at != previous_snapshot.cutoff_at
                or snapshot.dependency_plan_hash != previous_snapshot.dependency_plan_hash
                or snapshot.definition_refs != previous_snapshot.definition_refs
            ):
                raise FeaturePublicationError("correction snapshot must preserve its logical manifest identity")

        # 先将所有 Parquet 文件以临时文件写入并原子 rename；只有全部成功后才提交内存目录。
        moved_paths: list[Path] = []
        staging_root = self._resolver.resolve(".staging", allow_internal=True)
        staging_root.mkdir(parents=True, exist_ok=True)
        staging_dir = staging_root / f"feature-{uuid4().hex}"
        staging_dir.mkdir()
        try:
            for partition in partitions:
                payload = payloads[partition.feature_partition_id]
                target = self._resolver.resolve(partition.storage_ref)
                if target.exists():
                    if target.read_bytes() != payload:
                        raise FeaturePublicationError("feature partition target exists with different bytes")
                    continue
                staged_file = staging_dir / f"{uuid4().hex}.parquet"
                staged_file.write_bytes(payload)
                with staged_file.open("r+b") as handle:
                    os.fsync(handle.fileno())
                target.parent.mkdir(parents=True, exist_ok=True)
                os.rename(staged_file, target)
                moved_paths.append(target)
                fsync_directory(target.parent)
            # 复用分区的闭包校验也属于发布事务；失败时回收本次新文件，保留旧文件。
            self._verify_snapshot_files(snapshot, partition_by_id)
        except Exception:
            for moved in moved_paths:
                try:
                    moved.unlink(missing_ok=True)
                except OSError:
                    pass
            raise
        finally:
            shutil.rmtree(staging_dir, ignore_errors=True)

        if self._database is not None:
            return self._persist_control_plane(
                tuple(partitions), payloads, snapshot, bundle, partition_by_id, moved_paths,
            )

        try:
            # Manifest 的固定引用不随以后消费者的 retention 提升而改写。
            # Catalog 引用计数按新 Bundle 累加；相同 Bundle 重试在上方直接返回。
            new_partitions = dict(self._partitions)
            new_snapshots = dict(self._snapshots)
            new_bundles = dict(self._bundles)
            new_pinned = set(self._pinned)
            new_partition_payloads = dict(self._partition_payloads)
            for partition_id, partition in partition_by_id.items():
                new_partitions.setdefault(partition_id, partition)
                new_partition_payloads[partition_id] = payloads[partition_id]
            if bundle.consumer_kind is ConsumerKind.FORMAL_BACKTEST:
                for ref in bundle.required_partition_refs:
                    current = new_partitions[ref.feature_partition_id]
                    new_partitions[ref.feature_partition_id] = current.model_copy(update={
                        "retention_class": RetentionClass.PINNED,
                        "reference_count": current.reference_count + 1,
                    })
                    new_pinned.add(ref.feature_partition_id)
            new_snapshots[snapshot.feature_snapshot_id] = snapshot
            new_bundles[bundle.feature_bundle_id] = bundle
            self._partitions, self._snapshots, self._bundles, self._pinned, self._partition_payloads = (
                new_partitions, new_snapshots, new_bundles, new_pinned, new_partition_payloads,
            )
            return snapshot
        except Exception:
            # Control-plane failure must not leave newly moved files looking
            # published. Existing files are intentionally not in moved_paths.
            for moved in moved_paths:
                try:
                    moved.unlink(missing_ok=True)
                except OSError:
                    pass
            raise

    def _persist_control_plane(
        self,
        partitions: tuple[FeaturePartition, ...],
        payloads: Mapping[str, bytes],
        snapshot: FeatureSnapshot,
        bundle: FeatureBundle,
        partition_by_id: Mapping[str, FeaturePartition],
        moved_paths: Sequence[Path],
    ) -> FeatureSnapshot:
        """Commit feature files and their immutable control-plane records as one publication."""
        assert self._database is not None
        try:
            with self._database.transaction() as session:
                existing_bundle = self._repository.get_bundle(session, bundle.feature_bundle_id, for_update=True)
                if existing_bundle is not None:
                    if existing_bundle != bundle:
                        raise FeaturePublicationError("publication identity already exists with different bundle content")
                    existing_snapshot = self._repository.get_snapshot(session, snapshot.feature_snapshot_id)
                    if existing_snapshot is None:
                        raise FeaturePublicationError("published bundle references a missing snapshot")
                    if existing_snapshot.manifest_hash != snapshot.manifest_hash:
                        raise FeaturePublicationError("publication identity already exists with different snapshot content")
                    saved_partitions = tuple(
                        self._repository.get_partition(session, ref.feature_partition_id)
                        for ref in existing_bundle.required_partition_refs
                    )
                    if any(partition is None for partition in saved_partitions):
                        raise FeaturePublicationError("published bundle references a missing partition")
                    saved_snapshot = existing_snapshot
                    was_new_bundle = False
                else:
                    existing_snapshot = self._repository.get_snapshot(session, snapshot.feature_snapshot_id, for_update=True)
                    if existing_snapshot is not None and existing_snapshot.manifest_hash != snapshot.manifest_hash:
                        raise FeaturePublicationError("publication identity already exists with different snapshot content")
                    for partition in partitions:
                        existing_partition = self._repository.get_partition(
                            session, partition.feature_partition_id, for_update=True,
                        )
                        if existing_partition is None:
                            self._repository.add_partition(session, partition)
                        elif existing_partition.model_dump(
                            exclude={"retention_class", "reference_count", "created_at", "published_at"}
                        ) != partition.model_dump(
                            exclude={"retention_class", "reference_count", "created_at", "published_at"}
                        ):
                            raise FeaturePublicationError("partition identity already exists with different content")
                    if existing_snapshot is None:
                        self._repository.add_snapshot(session, snapshot)
                        saved_snapshot = snapshot
                    else:
                        saved_snapshot = existing_snapshot
                    self._repository.add_bundle(session, bundle)
                    was_new_bundle = True

                # Cache every partition referenced by the committed snapshot, not only
                # partitions materialized in this publication. A later correction on the
                # same store must be able to resolve unchanged fixed references too.
                hydrate_partition_ids = tuple(dict.fromkeys(
                    ref.feature_partition_id for ref in saved_snapshot.feature_partition_refs
                ))
                saved_partition_records = tuple(
                    self._repository.get_partition(session, partition_id)
                    for partition_id in hydrate_partition_ids
                )
                if any(partition is None for partition in saved_partition_records):
                    raise FeaturePublicationError("committed publication references a missing partition")
                # The control-plane transaction must not commit a manifest whose fixed
                # references are missing or whose local immutable files are corrupted.
                for partition in saved_partition_records:
                    assert partition is not None
                    target = self._resolver.resolve(partition.storage_ref)
                    if not target.is_file():
                        raise FeaturePublicationError("feature partition file is missing")
                    persisted_payload = target.read_bytes()
                    if len(persisted_payload) != partition.storage_ref.size_bytes:
                        raise FeaturePublicationError("feature partition payload size mismatch")
                    if "sha256:" + sha256(persisted_payload).hexdigest() != partition.partition_hash:
                        raise FeaturePublicationError("feature partition payload hash mismatch")
        except Exception:
            for moved in moved_paths:
                try:
                    moved.unlink(missing_ok=True)
                except OSError:
                    pass
            raise

        self._snapshots[saved_snapshot.feature_snapshot_id] = saved_snapshot
        self._bundles[bundle.feature_bundle_id] = bundle if was_new_bundle else existing_bundle
        for partition in saved_partition_records:
            assert partition is not None
            self._partitions[partition.feature_partition_id] = partition
            if partition.feature_partition_id in payloads:
                self._partition_payloads[partition.feature_partition_id] = payloads[partition.feature_partition_id]
            elif partition.feature_partition_id not in self._partition_payloads:
                self._partition_payloads[partition.feature_partition_id] = self._verify_partition_file(partition)
            if partition.retention_class is RetentionClass.PINNED:
                self._pinned.add(partition.feature_partition_id)
        return saved_snapshot

    @_locked
    def read_partition_payload(self, partition_id: str) -> bytes:
        partition = self._partitions[partition_id]
        payload = self._resolver.resolve(partition.storage_ref).read_bytes()
        if "sha256:" + sha256(payload).hexdigest() != partition.partition_hash:
            raise FeaturePublicationError("feature partition payload hash mismatch")
        return payload

    @_locked
    def is_pinned(self, partition_id: str) -> bool:
        return partition_id in self._pinned

    @_locked
    def published_snapshot(self, snapshot_id: str) -> FeatureSnapshot:
        return self._snapshots[snapshot_id]

    @_locked
    def published_partition(self, partition_id: str) -> FeaturePartition:
        return self._partitions[partition_id]

    @_locked
    def published_bundle(self, bundle_id: str) -> FeatureBundle:
        return self._bundles[bundle_id]


FeatureStoreMaterializer = FeatureStore

__all__ = [
    "FeatureMaterializationError",
    "FeaturePublicationError",
    "FeatureStore",
    "FeatureStoreMaterializer",
    "affected_feature_instances",
]
