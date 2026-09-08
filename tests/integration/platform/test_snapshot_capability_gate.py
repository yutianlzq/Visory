from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import update

from src.artifacts.hashing import compute_bytes_hash
from src.artifacts.namespace import StorageNamespaceResolver
from src.repositories.platform import SnapshotRepository, upgrade_database
from src.repositories.platform.canonical import CanonicalRepository
from src.repositories.platform.provider import ProviderRegistryRepository, provider_capability
from src.repositories.platform.raw_ingestion import RawIngestionRepository
from src.repositories.platform.task import TaskControlRepository
from src.services.platform.provider_registry import ProviderRegistryService
from src.schemas.platform import (
    AttemptOutcome,
    CapabilityCertification,
    CanonicalPartition,
    CanonicalQualityReport,
    ConsumerKind,
    ConsumerRequirement,
    DataSnapshot,
    PriorityClass,
    ProviderCapabilityStatus,
    ProviderRun,
    ProviderRunOutcome,
    RawCompression,
    RawObject,
    RetentionClass,
    QualityStatus,
    ResourceType,
    RevisionKind,
    SnapshotCapabilityStatus,
    SnapshotCurrentPointer,
    SnapshotPartitionRef,
    SnapshotPublicationStatus,
    StorageBackend,
    StorageNamespace,
    StorageRef,
    TaskAttemptRecord,
    TaskRecord,
    TaskState,
    compute_content_hash,
    compute_snapshot_manifest_hash,
    generate_resource_id,
)
from src.services.platform.canonical_normalization import deterministic_manifest_hash
from src.services.platform.snapshot import SnapshotCapabilityEngine, SnapshotGateError, SnapshotGateService, SnapshotManifestPublisher


NOW = datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc)
TRADE_DATE = date(2026, 8, 31)
DATASETS = ("security_master", "trading_calendar", "bar_1d_raw", "benchmark_index_1d")


def _resource(prefix: ResourceType, suffix: str) -> str:
    return generate_resource_id(prefix, timestamp_ms=1788177600000, random_bits=int(suffix))


def _rows(snapshot: DataSnapshot) -> dict[str, list[dict[str, object]]]:
    return {
        "security_master": [
            {"entity_key": "stock:cn:600519.SH", "trade_date": snapshot.trade_date, "available_at": snapshot.cutoff_at}
        ],
        "trading_calendar": [
            {"trade_date": snapshot.trade_date, "is_open": True, "available_at": snapshot.cutoff_at}
        ],
        "bar_1d_raw": [
            {
                "entity_key": "stock:cn:600519.SH",
                "trade_date": snapshot.trade_date,
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.5,
                "available_at": snapshot.cutoff_at,
            }
        ],
        "benchmark_index_1d": [
            {
                "benchmark_id": "index:cn:000300.SH",
                "asset_type": "index",
                "trade_date": snapshot.trade_date,
                "open": 3900.0,
                "high": 3950.0,
                "low": 3880.0,
                "close": 3940.0,
                "return_type": "TOTAL_RETURN",
                "total_return_close": 3980.0,
                "available_at": snapshot.cutoff_at,
            }
        ],
    }


def _build_snapshot(*, snapshot_id: str, runtime_root: Path, revision: int = 1, revision_kind: RevisionKind = RevisionKind.INITIAL, supersedes_id: str | None = None) -> tuple[DataSnapshot, tuple[CapabilityCertification, ...]]:
    partitions: list[SnapshotPartitionRef] = []
    for index, dataset_id in enumerate(DATASETS, start=1):
        content = f"canonical:{dataset_id}:revision:{revision}".encode("utf-8")
        content_hash = compute_bytes_hash(content)
        partition_id = _resource(ResourceType.CANONICAL_PARTITION, f"{100 + revision * 10 + index:012d}")
        quality_id = _resource(ResourceType.QUALITY_REPORT, f"{200 + revision * 10 + index:012d}")
        provider_id = _resource(ResourceType.PROVIDER_RUN, f"{300 + revision * 10 + index:012d}")
        raw_id = _resource(ResourceType.RAW_OBJECT, f"{400 + revision * 10 + index:012d}")
        ref = StorageRef(
            storage_backend=StorageBackend.LOCAL_FS,
            storage_namespace=StorageNamespace.APP,
            relative_path=f"canonical/dataset={dataset_id}/trade_date={TRADE_DATE.isoformat()}/revision={revision}/partition-{index}.parquet",
            content_hash=content_hash,
            media_type="application/vnd.apache.parquet",
            size_bytes=len(content),
        )
        partitions.append(
            SnapshotPartitionRef(
                canonical_partition_id=partition_id,
                dataset_id=dataset_id,
                dataset_schema_version="1.0.0",
                provider_policy_version="1.0.0",
                partition_key=TRADE_DATE.isoformat(),
                revision=revision,
                revision_kind=revision_kind,
                storage_ref=ref,
                partition_hash=content_hash,
                schema_hash=compute_bytes_hash(f"schema:{dataset_id}".encode("utf-8")),
                quality_report_id=quality_id,
                quality_status=QualityStatus.COMPLETE,
                provider_run_refs=(provider_id,),
                raw_object_refs=(raw_id,),
                min_available_at=NOW - timedelta(minutes=30),
                max_available_at=None,
                row_count=1,
                coverage_ratio=Decimal("1.0"),
                excluded_instrument_count=0,
                quality_threshold_version="1.0.0",
            )
        )
    by_dataset = {item.dataset_id: item for item in partitions}
    draft = DataSnapshot.model_construct(
        snapshot_id=snapshot_id,
        trade_date=TRADE_DATE,
        cutoff_at=NOW,
        provider_policy_id="bar_1d_raw_v1",
        provider_policy_version="1.0.0",
        security_master_ref=by_dataset["security_master"].canonical_partition_id,
        calendar_ref=by_dataset["trading_calendar"].canonical_partition_id,
        canonical_partitions=tuple(partitions),
        quality_report_refs=tuple(item.quality_report_id for item in partitions),
        quality_status=QualityStatus.COMPLETE,
        publication_status=SnapshotPublicationStatus.CERTIFIED,
        certified_capabilities=(),
        missing_capabilities=(),
        revision=revision,
        revision_kind=revision_kind,
        supersedes_id=supersedes_id,
        available_at=NOW - timedelta(minutes=30),
        created_at=NOW - timedelta(minutes=30),
        published_at=NOW,
        manifest_hash="sha256:" + "0" * 64,
        content_hash=compute_content_hash({"partition_hashes": [item.partition_hash for item in partitions]}),
        manifest_version="1.0.0",
    )
    certifications = SnapshotCapabilityEngine.certify(draft, now=NOW, partition_rows=_rows(draft))
    certified = tuple(item.capability_id for item in certifications if item.capability_status is SnapshotCapabilityStatus.CERTIFIED)
    complete = draft.model_copy(
        update={
            "certified_capabilities": certified,
            "missing_capabilities": tuple(item.capability_id for item in certifications if item.capability_status is not SnapshotCapabilityStatus.CERTIFIED),
        }
    )
    snapshot = DataSnapshot.model_validate({**complete.model_dump(mode="python"), "manifest_hash": compute_snapshot_manifest_hash(complete)})
    resolver = StorageNamespaceResolver(runtime_root)
    for ref in snapshot.canonical_partitions:
        path = resolver.resolve(ref.storage_ref)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"canonical:{ref.dataset_id}:revision:{revision}".encode("utf-8"))
        manifest_body = {
            "partition": {
                "canonical_partition_id": ref.canonical_partition_id,
                "dataset_id": ref.dataset_id,
                "dataset_schema_version": ref.dataset_schema_version,
                "partition_hash": ref.partition_hash,
                "schema_hash": ref.schema_hash,
                "quality_report_id": ref.quality_report_id,
                "quality_status": ref.quality_status.value,
                "row_count": ref.row_count,
            }
        }
        manifest_body["manifest_hash"] = deterministic_manifest_hash(manifest_body)
        (path.parent / "manifest.json").write_text(json.dumps(manifest_body, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    SnapshotManifestPublisher(runtime_root).publish(snapshot)
    return snapshot, certifications


def _requirement() -> ConsumerRequirement:
    return ConsumerRequirement(
        consumer_id="formal_backtest",
        consumer_kind=ConsumerKind.FORMAL_BACKTEST,
        required_capabilities=("backtest_core",),
        accepted_publication_statuses=(SnapshotPublicationStatus.CERTIFIED,),
    )


class _FailingPointerRepository:
    def __init__(self) -> None:
        self._delegate = SnapshotRepository()

    def __getattr__(self, name: str):
        return getattr(self._delegate, name)

    def upsert_pointer(self, session, pointer, *, expected_snapshot_id=None):
        self._delegate.upsert_pointer(
            session,
            pointer,
            expected_snapshot_id=expected_snapshot_id,
        )
        raise RuntimeError("pointer update rollback probe")


def _bootstrap_registry(database) -> None:
    ProviderRegistryService(database).bootstrap_defaults()
    with database.transaction() as session:
        registry = ProviderRegistryRepository()
        for dataset_id in DATASETS:
            dataset = registry.get_dataset(session, dataset_id, "1.0.0")
            assert dataset is not None
            capability = registry.get_capability(
                session, "a_stock_data", dataset_id, "1.0.0", "CN", dataset.frequency
            )
            assert capability is not None
            session.execute(
                update(provider_capability)
                .where(
                    provider_capability.c.provider_id == "a_stock_data",
                    provider_capability.c.dataset_id == dataset_id,
                    provider_capability.c.dataset_schema_version == "1.0.0",
                    provider_capability.c.market == "CN",
                    provider_capability.c.frequency == dataset.frequency,
                )
                .values(
                    provider_capability_status=ProviderCapabilityStatus.AVAILABLE.value,
                    checked_at=NOW,
                )
            )


def _ensure_task_lineage(session) -> tuple[str, str]:
    task_id = _resource(ResourceType.TASK, "900000000001")
    attempt_id = _resource(ResourceType.ATTEMPT, "900000000002")
    task_repository = TaskControlRepository()
    if task_repository.get_task(session, task_id) is None:
        task_repository.add_task(
            session,
            TaskRecord(
                task_id=task_id,
                task_type="snapshot_build",
                task_schema_version="1.0.0",
                task_state=TaskState.SUCCEEDED,
                priority_class=PriorityClass.P0_DATA_CERTIFICATION,
                priority_value=0,
                idempotency_key="wp0204-postgres-lineage",
                task_key="wp0204-postgres-lineage",
                canonical_request_hash=compute_bytes_hash(b"wp0204-postgres-lineage"),
                requested_by="wp0204-integration",
                request_source="integration-test",
                input_refs=(),
                requirements={"requested_capabilities": ["backtest_core"]},
                max_attempts=1,
                created_at=NOW - timedelta(hours=2),
                queued_at=NOW - timedelta(hours=2),
                terminal_at=NOW - timedelta(minutes=20),
            ),
        )
    if task_repository.get_attempt(session, attempt_id) is None:
        task_repository.add_attempt(
            session,
            TaskAttemptRecord(
                attempt_id=attempt_id,
                task_id=task_id,
                attempt_number=1,
                attempt_phase="SNAPSHOT_BUILD",
                phase_progress=1.0,
                worker_id="wp0204-integration",
                worker_capabilities=("snapshot_build",),
                lease_token_hash=compute_bytes_hash(b"wp0204-lease-token"),
                leased_at=NOW - timedelta(hours=1),
                lease_expires_at=NOW + timedelta(hours=1),
                heartbeat_at=NOW - timedelta(minutes=30),
                started_at=NOW - timedelta(minutes=50),
                finished_at=NOW - timedelta(minutes=20),
                resource_usage={},
                attempt_outcome=AttemptOutcome.SUCCEEDED,
                diagnostic_artifact_refs=(),
            ),
        )
    return task_id, attempt_id


def _persist_lineage(session, snapshot: DataSnapshot) -> None:
    registry = ProviderRegistryRepository()
    canonical = CanonicalRepository()
    raw_repository = RawIngestionRepository()
    task_id, attempt_id = _ensure_task_lineage(session)
    prior = SnapshotRepository().get_snapshot(session, snapshot.supersedes_id) if snapshot.supersedes_id else None
    prior_by_dataset = {item.dataset_id: item for item in prior.canonical_partitions} if prior else {}

    for ref in snapshot.canonical_partitions:
        dataset = registry.get_dataset(session, ref.dataset_id, ref.dataset_schema_version)
        policy = registry.get_policy(session, f"{ref.dataset_id}_v1")
        raw_schema = registry.get_provider_raw_schema(
            session,
            "a_stock_data",
            "1.0.0",
            ref.dataset_id,
            ref.dataset_schema_version,
            "1.0.0",
        )
        mapping = canonical.get_mapping(
            session, "a_stock_data", ref.dataset_id, ref.dataset_schema_version, "1.0.0"
        )
        assert dataset is not None and policy is not None and raw_schema is not None and mapping is not None

        raw_content = f"raw:{snapshot.snapshot_id}:{ref.dataset_id}".encode("utf-8")
        raw_hash = compute_bytes_hash(raw_content)
        request_fingerprint = compute_bytes_hash(f"request:{snapshot.snapshot_id}:{ref.dataset_id}".encode("utf-8"))
        raw_ref = StorageRef(
            storage_backend=StorageBackend.LOCAL_FS,
            storage_namespace=StorageNamespace.APP,
            relative_path=(
                f"raw/provider=a_stock_data/dataset={ref.dataset_id}/"
                f"trade_date={snapshot.trade_date.isoformat()}/revision={ref.revision}/raw-{ref.raw_object_refs[0]}.json"
            ),
            content_hash=raw_hash,
            media_type="application/json",
            size_bytes=len(raw_content),
        )
        raw = RawObject(
            raw_object_id=ref.raw_object_refs[0],
            provider_run_id=ref.provider_run_refs[0],
            provider_id="a_stock_data",
            actual_upstream="a-stock-data",
            dataset_id=ref.dataset_id,
            dataset_schema_version=ref.dataset_schema_version,
            request_fingerprint=request_fingerprint,
            storage_ref=raw_ref,
            raw_content_hash=raw_hash,
            media_type="application/json",
            compression=RawCompression.NONE,
            observed_at=NOW - timedelta(minutes=50),
            ingested_at=NOW - timedelta(minutes=30),
            provider_schema_version="1.0.0",
            observed_schema_hash=raw_schema.expected_schema_hash,
            row_count=1,
            byte_count=len(raw_content),
            retention_class=RetentionClass.PINNED,
        )
        run = ProviderRun(
            provider_run_id=ref.provider_run_refs[0],
            provider_id="a_stock_data",
            actual_upstream="a-stock-data",
            dataset_id=ref.dataset_id,
            dataset_schema_version=ref.dataset_schema_version,
            provider_policy_id=policy.provider_policy_id,
            provider_policy_version=policy.policy_version,
            adapter_version="1.0.0",
            capability_market="CN",
            capability_frequency=dataset.frequency,
            task_id=task_id,
            attempt_id=attempt_id,
            request_fingerprint=request_fingerprint,
            started_at=NOW - timedelta(minutes=50),
            finished_at=NOW - timedelta(minutes=30),
            observed_schema_hash=raw_schema.expected_schema_hash,
            row_count=1,
            byte_count=len(raw_content),
            run_outcome=ProviderRunOutcome.SUCCEEDED,
            raw_object_refs=(raw.raw_object_id,),
        )
        report = canonical.get_quality_report(session, ref.quality_report_id)
        if report is not None:
            continue
        report = CanonicalQualityReport(
            quality_report_id=ref.quality_report_id,
            canonical_partition_id=ref.canonical_partition_id,
            quality_status=QualityStatus.COMPLETE,
            rule_results={rule_id: "PASS" for rule_id in policy.required_quality_rules},
            row_count=1,
            rejected_row_count=0,
            duplicate_key_count=0,
            identity_unresolved_count=0,
            identity_ambiguous_count=0,
            coverage_ratio=Decimal("1.0"),
            excluded_instrument_count=0,
            quality_threshold_version="1.0.0",
            task_id=task_id,
            attempt_id=attempt_id,
            dataset_id=ref.dataset_id,
            dataset_schema_version=ref.dataset_schema_version,
            mapping_version=mapping.mapping_version,
            mapping_hash=mapping.mapping_hash,
            provider_run_refs=(run.provider_run_id,),
            raw_object_refs=(raw.raw_object_id,),
            created_at=NOW - timedelta(minutes=30),
        )
        raw_repository.add_provider_run(session, run)
        raw_repository.add_raw_object(session, raw)
        canonical.add_quality_report(session, report)
        canonical.add_partition(
            session,
            CanonicalPartition(
                canonical_partition_id=ref.canonical_partition_id,
                dataset_id=ref.dataset_id,
                dataset_schema_version=ref.dataset_schema_version,
                partition_key=ref.partition_key,
                revision=ref.revision,
                revision_kind=ref.revision_kind,
                supersedes_id=(
                    prior_by_dataset[ref.dataset_id].canonical_partition_id
                    if ref.revision_kind is RevisionKind.CORRECTION and ref.dataset_id in prior_by_dataset
                    else None
                ),
                provider_policy_version=ref.provider_policy_version,
                provider_run_refs=(run.provider_run_id,),
                raw_object_refs=(raw.raw_object_id,),
                min_available_at=ref.min_available_at,
                max_available_at=ref.max_available_at,
                row_count=ref.row_count,
                distinct_entity_count=1,
                storage_ref=ref.storage_ref,
                partition_hash=ref.partition_hash,
                schema_hash=ref.schema_hash,
                quality_status=ref.quality_status,
                quality_report_id=report.quality_report_id,
                created_at=NOW - timedelta(minutes=30),
                published_at=NOW,
            ),
        )


def _persist_snapshot(database, snapshot: DataSnapshot, certifications: tuple[CapabilityCertification, ...], requirement: ConsumerRequirement) -> None:
    with database.transaction() as session:
        _persist_lineage(session, snapshot)
        repository = SnapshotRepository()
        repository.add_snapshot(session, snapshot)
        for certification in certifications:
            repository.add_capability(session, certification)
        persisted_requirement = repository.get_consumer_requirement(session, requirement.consumer_id)
        if persisted_requirement is None:
            repository.add_consumer_requirement(session, requirement)
        else:
            assert persisted_requirement == requirement


def test_persisted_snapshot_capability_consumer_round_trip_and_formal_gate(isolated_postgres_database, tmp_path: Path) -> None:
    database = isolated_postgres_database
    upgrade_database(database.engine)
    _bootstrap_registry(database)
    snapshot, certifications = _build_snapshot(snapshot_id=_resource(ResourceType.DATA_SNAPSHOT, "000000000001"), runtime_root=tmp_path)
    requirement = _requirement()
    _persist_snapshot(database, snapshot, certifications, requirement)

    repository = SnapshotRepository()
    with database.transaction() as session:
        restored = repository.get_snapshot(session, snapshot.snapshot_id)
        restored_certifications = repository.list_capabilities(session, snapshot.snapshot_id)
        restored_requirement = repository.get_consumer_requirement(session, requirement.consumer_id)
    assert restored == snapshot
    assert set(restored_certifications) == set(certifications)
    assert restored_requirement == requirement

    service = SnapshotGateService(database, runtime_root=tmp_path, clock=lambda: NOW)
    assert service.check_consumer(snapshot, requirement).value == "ACCEPTED"


def test_formal_gate_rejects_forged_snapshot_projection_against_real_postgres(isolated_postgres_database, tmp_path: Path) -> None:
    database = isolated_postgres_database
    upgrade_database(database.engine)
    _bootstrap_registry(database)
    snapshot, certifications = _build_snapshot(snapshot_id=_resource(ResourceType.DATA_SNAPSHOT, "000000000002"), runtime_root=tmp_path)
    requirement = _requirement()
    _persist_snapshot(database, snapshot, certifications, requirement)
    forged = snapshot.model_copy(update={"certified_capabilities": (), "missing_capabilities": tuple(snapshot.certified_capabilities)})
    forged = DataSnapshot.model_validate({**forged.model_dump(mode="python"), "manifest_hash": compute_snapshot_manifest_hash(forged)})

    service = SnapshotGateService(database, runtime_root=tmp_path, clock=lambda: NOW)
    with pytest.raises(SnapshotGateError) as captured:
        service.check_consumer(forged, requirement)
    assert captured.value.error_code == "SNAPSHOT_PERSISTED_STATE_MISMATCH"


def test_current_pointer_cas_switch_preserves_previous_snapshot_and_repository_rollback(isolated_postgres_database, tmp_path: Path) -> None:
    database = isolated_postgres_database
    upgrade_database(database.engine)
    _bootstrap_registry(database)
    first, first_certifications = _build_snapshot(snapshot_id=_resource(ResourceType.DATA_SNAPSHOT, "000000000003"), runtime_root=tmp_path, revision=1)
    requirement = _requirement()
    _persist_snapshot(database, first, first_certifications, requirement)
    second, second_certifications = _build_snapshot(
        snapshot_id=_resource(ResourceType.DATA_SNAPSHOT, "000000000004"),
        runtime_root=tmp_path,
        revision=2,
        revision_kind=RevisionKind.CORRECTION,
        supersedes_id=first.snapshot_id,
    )
    _persist_snapshot(database, second, second_certifications, requirement)

    service = SnapshotGateService(database, runtime_root=tmp_path, clock=lambda: NOW)
    initial = service.update_current_pointer(
        scope="global",
        trade_date=TRADE_DATE,
        capability_id="backtest_core",
        snapshot=first,
    )
    assert initial.snapshot_id == first.snapshot_id
    switched = service.update_current_pointer(
        scope="global",
        trade_date=TRADE_DATE,
        capability_id="backtest_core",
        snapshot=second,
        expected_snapshot_id=first.snapshot_id,
    )
    assert switched.snapshot_id == second.snapshot_id
    assert switched.previous_snapshot_id == first.snapshot_id
    assert switched.pointer_revision == 2

    with database.transaction() as session:
        repository = SnapshotRepository()
        current = repository.get_pointer(session, scope="global", trade_date=TRADE_DATE, capability_id="backtest_core")
        historical = repository.get_snapshot(session, first.snapshot_id)
    assert current == switched
    assert historical == first

    with pytest.raises(SnapshotGateError) as captured:
        service.update_current_pointer(
            scope="global",
            trade_date=TRADE_DATE,
            capability_id="backtest_core",
            snapshot=first,
            expected_snapshot_id="ds_019dbd74-2a00-7000-8000-999999999999",
        )
    assert captured.value.error_code == "SNAPSHOT_POINTER_CAS_FAILED"

    rollback_id = _resource(ResourceType.DATA_SNAPSHOT, "000000000005")
    rollback_snapshot, rollback_certifications = _build_snapshot(snapshot_id=rollback_id, runtime_root=tmp_path, revision=3)
    with pytest.raises(RuntimeError, match="rollback probe"):
        with database.transaction() as session:
            _persist_lineage(session, rollback_snapshot)
            repository = SnapshotRepository()
            repository.add_snapshot(session, rollback_snapshot)
            for certification in rollback_certifications:
                repository.add_capability(session, certification)
            raise RuntimeError("rollback probe")
    with database.transaction() as session:
        assert SnapshotRepository().get_snapshot(session, rollback_id) is None



def test_current_pointer_update_rolls_back_when_pointer_write_fails(
    isolated_postgres_database,
    tmp_path: Path,
) -> None:
    database = isolated_postgres_database
    upgrade_database(database.engine)
    _bootstrap_registry(database)
    first, first_certifications = _build_snapshot(
        snapshot_id=_resource(ResourceType.DATA_SNAPSHOT, "000000000006"),
        runtime_root=tmp_path,
        revision=1,
    )
    second, second_certifications = _build_snapshot(
        snapshot_id=_resource(ResourceType.DATA_SNAPSHOT, "000000000007"),
        runtime_root=tmp_path,
        revision=2,
        revision_kind=RevisionKind.CORRECTION,
        supersedes_id=first.snapshot_id,
    )
    requirement = _requirement()
    _persist_snapshot(database, first, first_certifications, requirement)
    _persist_snapshot(database, second, second_certifications, requirement)

    service = SnapshotGateService(database, runtime_root=tmp_path, clock=lambda: NOW)
    initial = service.update_current_pointer(
        scope="global",
        trade_date=TRADE_DATE,
        capability_id="backtest_core",
        snapshot=first,
    )
    failing_service = SnapshotGateService(
        database,
        runtime_root=tmp_path,
        repository=_FailingPointerRepository(),
        clock=lambda: NOW,
    )
    with pytest.raises(RuntimeError, match="pointer update rollback probe"):
        failing_service.update_current_pointer(
            scope="global",
            trade_date=TRADE_DATE,
            capability_id="backtest_core",
            snapshot=second,
            expected_snapshot_id=first.snapshot_id,
        )

    with database.transaction() as session:
        current = SnapshotRepository().get_pointer(
            session,
            scope="global",
            trade_date=TRADE_DATE,
            capability_id="backtest_core",
        )
    assert current == initial



def test_current_pointer_cas_allows_one_of_two_concurrent_switches(
    isolated_postgres_database,
    tmp_path: Path,
) -> None:
    database = isolated_postgres_database
    upgrade_database(database.engine)
    _bootstrap_registry(database)
    first, first_certifications = _build_snapshot(
        snapshot_id=_resource(ResourceType.DATA_SNAPSHOT, "000000000008"),
        runtime_root=tmp_path,
        revision=1,
    )
    second, second_certifications = _build_snapshot(
        snapshot_id=_resource(ResourceType.DATA_SNAPSHOT, "000000000009"),
        runtime_root=tmp_path,
        revision=2,
        revision_kind=RevisionKind.CORRECTION,
        supersedes_id=first.snapshot_id,
    )
    requirement = _requirement()
    _persist_snapshot(database, first, first_certifications, requirement)
    _persist_snapshot(database, second, second_certifications, requirement)
    service = SnapshotGateService(database, runtime_root=tmp_path, clock=lambda: NOW)
    initial = service.update_current_pointer(
        scope="global",
        trade_date=TRADE_DATE,
        capability_id="backtest_core",
        snapshot=first,
    )

    barrier = threading.Barrier(2)

    def switch_once() -> tuple[str, SnapshotCurrentPointer | str]:
        worker_service = SnapshotGateService(database, runtime_root=tmp_path, clock=lambda: NOW)
        barrier.wait(timeout=10)
        try:
            return (
                "ok",
                worker_service.update_current_pointer(
                    scope="global",
                    trade_date=TRADE_DATE,
                    capability_id="backtest_core",
                    snapshot=second,
                    expected_snapshot_id=first.snapshot_id,
                ),
            )
        except SnapshotGateError as exc:
            return ("error", exc.error_code)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: switch_once(), (1, 2)))

    assert sorted(result[0] for result in results) == ["error", "ok"]
    assert [result[1] for result in results if result[0] == "error"] == ["SNAPSHOT_POINTER_CAS_FAILED"]
    successful_pointer = next(result[1] for result in results if result[0] == "ok")
    assert successful_pointer.snapshot_id == second.snapshot_id
    assert successful_pointer.previous_snapshot_id == first.snapshot_id
    assert successful_pointer.pointer_revision == initial.pointer_revision + 1

    with database.transaction() as session:
        repository = SnapshotRepository()
        current = repository.get_pointer(
            session,
            scope="global",
            trade_date=TRADE_DATE,
            capability_id="backtest_core",
        )
        historical = repository.get_snapshot(session, first.snapshot_id)
        corrected = repository.get_snapshot(session, second.snapshot_id)
        corrected_partition = CanonicalRepository().get_partition(
            session,
            next(
                item.canonical_partition_id
                for item in second.canonical_partitions
                if item.dataset_id == "bar_1d_raw"
            ),
        )
    assert current == successful_pointer
    assert historical == first
    assert corrected == second
    assert corrected_partition is not None
    assert corrected_partition.supersedes_id == next(
        item.canonical_partition_id
        for item in first.canonical_partitions
        if item.dataset_id == "bar_1d_raw"
    )
