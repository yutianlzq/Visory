from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from pathlib import Path

import pytest

from sqlalchemy import text

from src.repositories.platform import CanonicalRepository, RawIngestionRepository, upgrade_database
from src.schemas.platform import AttemptOutcome, RawCompression, TaskCreateRequest, TaskState
from src.services.platform.canonical_normalization import CanonicalNormalizationError, CanonicalNormalizationTaskWorker
from src.services.platform.provider_registry import ProviderRegistryService, default_provider_canonical_mapping_records, default_provider_raw_schema_records
from src.services.platform.raw_ingestion import FakeProviderTransport, ProviderFetchResponse, RawIngestionTaskWorker, RawObjectPublisher
from src.services.platform.task_control import TaskControlError, TaskControlService


NOW = datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc)


def _raw_requirements() -> dict[str, object]:
    return {
        "provider_id": "a_stock_data",
        "dataset_id": "trading_calendar",
        "dataset_schema_version": "1.0.0",
        "provider_policy_id": "trading_calendar_v1",
        "market": "CN",
        "request": {"as_of": "2026-08-31"},
        "timeout_seconds": 5,
    }


def _calendar_response() -> ProviderFetchResponse:
    schema = next(
        item
        for item in default_provider_raw_schema_records()
        if item.provider_id == "a_stock_data" and item.dataset_id == "trading_calendar"
    )
    payload = [{
        "market_code": "SH",
        "cal_date": "2026-08-31",
        "is_open": True,
        "session_open": "2026-08-31T01:30:00Z",
        "session_close": "2026-08-31T07:00:00Z",
        "as_of": NOW.isoformat(),
    }]
    return ProviderFetchResponse(
        content=json.dumps(payload, sort_keys=True).encode("utf-8"),
        media_type="application/json",
        compression=RawCompression.NONE,
        actual_upstream="fixture.a-stock-data",
        observed_at=NOW,
        source_published_at=None,
        raw_schema_fields=tuple(schema.field_types),
        raw_schema_field_types=dict(schema.field_types),
        row_count=1,
    )


def test_calendar_raw_to_canonical_is_durable_and_records_lineage(isolated_postgres_database, tmp_path: Path) -> None:
    database = isolated_postgres_database
    upgrade_database(database.engine)
    ProviderRegistryService(database).bootstrap_defaults()
    task_control = TaskControlService(database, clock=lambda: NOW, runtime_root=tmp_path)
    raw_publisher = RawObjectPublisher(tmp_path, database.transaction, clock=lambda: NOW)

    raw_task = task_control.create_task(
        TaskCreateRequest(task_type="raw_ingestion", requested_by="integration", request_source="integration_test", requirements=_raw_requirements()),
        idempotency_key="g014-calendar-raw",
    )
    raw_lease = task_control.lease_next(worker_id="raw-worker", worker_capabilities=("raw_ingestion",))
    assert raw_lease is not None
    raw_result = RawIngestionTaskWorker(
        task_control,
        database,
        raw_publisher,
        FakeProviderTransport({("a_stock_data", "trading_calendar"): _calendar_response()}),
        clock=lambda: NOW,
    ).execute(raw_lease)
    assert raw_result.raw_object is not None
    assert task_control.get_task(raw_task.task_id).task.task_state is TaskState.SUCCEEDED

    mapping = next(
        item
        for item in default_provider_canonical_mapping_records()
        if item.provider_id == "a_stock_data" and item.dataset_id == "trading_calendar"
    )
    canonical_task = task_control.create_task(
        TaskCreateRequest(
            task_type="canonical_normalization",
            requested_by="integration",
            request_source="integration_test",
            requirements={
                "provider_id": "a_stock_data",
                "dataset_id": "trading_calendar",
                "dataset_schema_version": "1.0.0",
                "raw_object_id": raw_result.raw_object.raw_object_id,
                "provider_run_id": raw_result.provider_run.provider_run_id,
                "provider_policy_id": "trading_calendar_v1",
                "provider_policy_version": "1.0.0",
                "mapping_version": "1.0.0",
                "partition_key": "2026-08-31",
                "market": "CN",
            },
        ),
        idempotency_key="g014-calendar-canonical",
    )
    canonical_lease = task_control.lease_next(worker_id="canonical-worker", worker_capabilities=("canonical_normalization",))
    assert canonical_lease is not None
    result = CanonicalNormalizationTaskWorker(
        task_control,
        database,
        runtime_root=tmp_path,
        mapping_loader=lambda _requirements: mapping,
        clock=lambda: NOW,
    ).execute(canonical_lease)

    assert result.published is True
    assert result.canonical_partition is not None
    assert task_control.get_task(canonical_task.task_id).task.task_state is TaskState.SUCCEEDED
    published_path = raw_publisher.resolver.resolve(result.canonical_partition.storage_ref, require_exists=True)
    assert published_path.read_bytes()
    with database.transaction() as session:
        repository = CanonicalRepository()
        assert repository.get_partition(session, result.canonical_partition.canonical_partition_id) == result.canonical_partition
        assert repository.get_quality_report(session, result.quality_report.quality_report_id) == result.quality_report
        assert RawIngestionRepository().get_raw_object(session, raw_result.raw_object.raw_object_id) == raw_result.raw_object
    with database.engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM canonical_partition_lineage")).scalar_one() == 1


def _raw_response(dataset_id: str) -> ProviderFetchResponse:
    schema = next(
        item
        for item in default_provider_raw_schema_records()
        if item.provider_id == "a_stock_data" and item.dataset_id == dataset_id
    )
    payloads = {
        "trading_calendar": {
            "market_code": "SH",
            "cal_date": "2026-08-31",
            "is_open": True,
            "session_open": "2026-08-31T01:30:00Z",
            "session_close": "2026-08-31T07:00:00Z",
            "as_of": NOW.isoformat(),
        },
        "security_master": {
            "ts_code": "600519.SH",
            "exchange_code": "SSE",
            "asset_type": "EQUITY",
            "security_name": "Kweichow Moutai",
            "listed_on": "2001-08-27",
            "currency_code": "RMB",
            "lot_size": 100,
            "as_of": NOW.isoformat(),
        },
        "bar_1d_raw": {
            "ts_code": "600519.SH",
            "trade_date": "2026-08-31",
            "open_price": "1400.00",
            "high_price": "1420.00",
            "low_price": "1395.00",
            "close_price": "1410.00",
            "vol": "1000",
            "amount": "1410000",
            "pre_close": "1398.00",
            "trade_status": "TRADE",
            "limit_up": "1537.80",
            "limit_down": "1258.20",
            "as_of": NOW.isoformat(),
        },
    }
    return ProviderFetchResponse(
        content=json.dumps([payloads[dataset_id]], sort_keys=True).encode("utf-8"),
        media_type="application/json",
        compression=RawCompression.NONE,
        actual_upstream="fixture.a-stock-data",
        observed_at=NOW,
        source_published_at=None,
        raw_schema_fields=tuple(schema.field_types),
        raw_schema_field_types=dict(schema.field_types),
        row_count=1,
    )


def _normalize_requirements(raw_result, dataset_id: str) -> dict[str, object]:
    return {
        "provider_id": "a_stock_data",
        "dataset_id": dataset_id,
        "dataset_schema_version": "1.0.0",
        "raw_object_id": raw_result.raw_object.raw_object_id,
        "provider_run_id": raw_result.provider_run.provider_run_id,
        "provider_policy_id": f"{dataset_id}_v1",
        "provider_policy_version": "1.0.0",
        "mapping_version": "1.0.0",
        "partition_key": "2026-08-31",
        "market": "CN",
    }


def test_security_master_registers_provider_alias_used_by_bar_normalization(isolated_postgres_database, tmp_path: Path) -> None:
    from src.repositories.platform.identity import AssetIdentityRepository
    from src.schemas.platform import AssetType, normalize_alias_value

    database = isolated_postgres_database
    upgrade_database(database.engine)
    ProviderRegistryService(database).bootstrap_defaults()
    task_control = TaskControlService(database, clock=lambda: NOW, runtime_root=tmp_path)
    raw_publisher = RawObjectPublisher(tmp_path, database.transaction, clock=lambda: NOW)
    raw_worker = RawIngestionTaskWorker(
        task_control,
        database,
        raw_publisher,
        FakeProviderTransport({
            ("a_stock_data", "security_master"): _raw_response("security_master"),
            ("a_stock_data", "bar_1d_raw"): _raw_response("bar_1d_raw"),
        }),
        clock=lambda: NOW,
    )

    def ingest(dataset_id: str):
        task = task_control.create_task(
            TaskCreateRequest(
                task_type="raw_ingestion",
                requested_by="integration",
                request_source="integration_test",
                requirements={**_raw_requirements(), "dataset_id": dataset_id, "provider_policy_id": f"{dataset_id}_v1"},
            ),
            idempotency_key=f"g014-{dataset_id}-raw",
        )
        lease = task_control.lease_next(worker_id="raw-worker", worker_capabilities=("raw_ingestion",))
        assert lease is not None
        result = raw_worker.execute(lease)
        assert task_control.get_task(task.task_id).task.task_state is TaskState.SUCCEEDED
        return result

    security_raw = ingest("security_master")
    security_mapping = next(
        item
        for item in default_provider_canonical_mapping_records()
        if item.provider_id == "a_stock_data" and item.dataset_id == "security_master"
    )
    security_task = task_control.create_task(
        TaskCreateRequest(
            task_type="canonical_normalization",
            requested_by="integration",
            request_source="integration_test",
            requirements=_normalize_requirements(security_raw, "security_master"),
        ),
        idempotency_key="g014-security-canonical",
    )
    security_lease = task_control.lease_next(worker_id="canonical-worker", worker_capabilities=("canonical_normalization",))
    assert security_lease is not None
    security_result = CanonicalNormalizationTaskWorker(
        task_control,
        database,
        runtime_root=tmp_path,
        mapping_loader=lambda _requirements: security_mapping,
        clock=lambda: NOW,
    ).execute(security_lease)
    assert security_result.published is True
    assert task_control.get_task(security_task.task_id).task.task_state is TaskState.SUCCEEDED

    with database.transaction() as session:
        identity_repository = AssetIdentityRepository()
        identity = identity_repository.get_identity(session, "stock:sh600519")
        assert identity is not None
        aliases = identity_repository.find_candidates_in_session(
            session,
            namespace="a_stock_data:cn_stock",
            normalized_value=normalize_alias_value("600519.SH"),
            asset_type=AssetType.STOCK,
            valid_on=NOW.date(),
            available_at=NOW,
        )
        assert tuple(alias.identity.entity_key for alias in aliases) == ("stock:sh600519",)

    bar_raw = ingest("bar_1d_raw")
    bar_mapping = next(
        item
        for item in default_provider_canonical_mapping_records()
        if item.provider_id == "a_stock_data" and item.dataset_id == "bar_1d_raw"
    )
    bar_task = task_control.create_task(
        TaskCreateRequest(
            task_type="canonical_normalization",
            requested_by="integration",
            request_source="integration_test",
            requirements=_normalize_requirements(bar_raw, "bar_1d_raw"),
        ),
        idempotency_key="g014-bar-canonical",
    )
    bar_lease = task_control.lease_next(worker_id="canonical-worker", worker_capabilities=("canonical_normalization",))
    assert bar_lease is not None
    bar_result = CanonicalNormalizationTaskWorker(
        task_control,
        database,
        runtime_root=tmp_path,
        mapping_loader=lambda _requirements: bar_mapping,
        clock=lambda: NOW,
    ).execute(bar_lease)
    assert bar_result.published is False
    assert bar_result.failure_code == "CANONICAL_TRADING_CALENDAR_UNAVAILABLE"
    assert task_control.get_task(bar_task.task_id).task.task_state is TaskState.FAILED


def test_three_core_datasets_complete_raw_to_canonical_with_default_identity_and_calendar(
    isolated_postgres_database,
    tmp_path: Path,
) -> None:
    database = isolated_postgres_database
    upgrade_database(database.engine)
    ProviderRegistryService(database).bootstrap_defaults()
    task_control = TaskControlService(database, clock=lambda: NOW, runtime_root=tmp_path)
    raw_publisher = RawObjectPublisher(tmp_path, database.transaction, clock=lambda: NOW)
    raw_worker = RawIngestionTaskWorker(
        task_control,
        database,
        raw_publisher,
        FakeProviderTransport({
            ("a_stock_data", "trading_calendar"): _raw_response("trading_calendar"),
            ("a_stock_data", "security_master"): _raw_response("security_master"),
            ("a_stock_data", "bar_1d_raw"): _raw_response("bar_1d_raw"),
        }),
        clock=lambda: NOW,
    )

    raw_results = {}
    for dataset_id in ("trading_calendar", "security_master", "bar_1d_raw"):
        task = task_control.create_task(
            TaskCreateRequest(
                task_type="raw_ingestion",
                requested_by="integration",
                request_source="integration_test",
                requirements={
                    **_raw_requirements(),
                    "dataset_id": dataset_id,
                    "provider_policy_id": f"{dataset_id}_v1",
                },
            ),
            idempotency_key=f"g014-full-chain-raw-{dataset_id}",
        )
        lease = task_control.lease_next(worker_id="raw-worker", worker_capabilities=("raw_ingestion",))
        assert lease is not None
        raw_results[dataset_id] = raw_worker.execute(lease)
        assert task_control.get_task(task.task_id).task.task_state is TaskState.SUCCEEDED

    partitions = {}
    for dataset_id in ("trading_calendar", "security_master", "bar_1d_raw"):
        raw_result = raw_results[dataset_id]
        task = task_control.create_task(
            TaskCreateRequest(
                task_type="canonical_normalization",
                requested_by="integration",
                request_source="integration_test",
                requirements=_normalize_requirements(raw_result, dataset_id),
            ),
            idempotency_key=f"g014-full-chain-canonical-{dataset_id}",
        )
        lease = task_control.lease_next(worker_id="canonical-worker", worker_capabilities=("canonical_normalization",))
        assert lease is not None
        result = CanonicalNormalizationTaskWorker(
            task_control,
            database,
            runtime_root=tmp_path,
            clock=lambda: NOW,
        ).execute(lease)
        assert result.published is True
        assert result.canonical_partition is not None
        assert task_control.get_task(task.task_id).task.task_state is TaskState.SUCCEEDED
        partitions[dataset_id] = result.canonical_partition

    assert partitions["bar_1d_raw"].distinct_entity_count == 1
    with database.transaction() as session:
        repository = CanonicalRepository()
        assert repository.get_latest_partition_for_key(
            session,
            dataset_id="trading_calendar",
            partition_key="2026-08-31",
        ) == partitions["trading_calendar"]


def _calendar_raw_result(database, tmp_path: Path, task_control: TaskControlService):
    raw_publisher = RawObjectPublisher(tmp_path, database.transaction, clock=lambda: NOW)
    raw_task = task_control.create_task(
        TaskCreateRequest(
            task_type="raw_ingestion",
            requested_by="integration",
            request_source="integration_test",
            requirements=_raw_requirements(),
        ),
        idempotency_key=f"g014-calendar-raw-{uuid4().hex}",
    )
    raw_lease = task_control.lease_next(worker_id="raw-worker", worker_capabilities=("raw_ingestion",))
    assert raw_lease is not None
    result = RawIngestionTaskWorker(
        task_control,
        database,
        raw_publisher,
        FakeProviderTransport({("a_stock_data", "trading_calendar"): _calendar_response()}),
        clock=lambda: NOW,
    ).execute(raw_lease)
    assert task_control.get_task(raw_task.task_id).task.task_state is TaskState.SUCCEEDED
    return result


def _calendar_canonical_task(task_control: TaskControlService, raw_result):
    return task_control.create_task(
        TaskCreateRequest(
            task_type="canonical_normalization",
            requested_by="integration",
            request_source="integration_test",
            requirements=_normalize_requirements(raw_result, "trading_calendar"),
        ),
        idempotency_key=f"g014-calendar-canonical-{uuid4().hex}",
    )


def test_cancelled_canonical_task_cannot_publish_a_partition(isolated_postgres_database, tmp_path: Path) -> None:
    database = isolated_postgres_database
    upgrade_database(database.engine)
    ProviderRegistryService(database).bootstrap_defaults()
    task_control = TaskControlService(database, clock=lambda: NOW, runtime_root=tmp_path)
    raw_result = _calendar_raw_result(database, tmp_path, task_control)
    task = _calendar_canonical_task(task_control, raw_result)
    lease = task_control.lease_next(worker_id="canonical-worker", worker_capabilities=("canonical_normalization",))
    assert lease is not None
    task_control.request_cancel(task.task_id)

    with pytest.raises(Exception, match="TASK_CANCEL_PENDING"):
        CanonicalNormalizationTaskWorker(
            task_control,
            database,
            runtime_root=tmp_path,
            clock=lambda: NOW,
        ).execute(lease)

    assert task_control.get_task(task.task_id).task.task_state is TaskState.CANCELLED
    assert not list(tmp_path.rglob("canonical/**/data.parquet"))


def test_registry_transaction_failure_leaves_only_an_invisible_canonical_orphan(
    isolated_postgres_database,
    tmp_path: Path,
) -> None:
    class FailingRegistry(CanonicalRepository):
        @staticmethod
        def add_quality_report(session, record) -> None:
            raise RuntimeError("forced registry transaction failure")

    database = isolated_postgres_database
    upgrade_database(database.engine)
    ProviderRegistryService(database).bootstrap_defaults()
    task_control = TaskControlService(database, clock=lambda: NOW, runtime_root=tmp_path)
    raw_result = _calendar_raw_result(database, tmp_path, task_control)
    task = _calendar_canonical_task(task_control, raw_result)
    lease = task_control.lease_next(worker_id="canonical-worker", worker_capabilities=("canonical_normalization",))
    assert lease is not None

    with pytest.raises(RuntimeError, match="forced registry transaction failure"):
        CanonicalNormalizationTaskWorker(
            task_control,
            database,
            runtime_root=tmp_path,
            canonical_repository=FailingRegistry(),
            clock=lambda: NOW,
        ).execute(lease)

    assert task_control.get_task(task.task_id).task.task_state is TaskState.RETRY_WAIT
    with database.transaction() as session:
        assert session.execute(text("SELECT count(*) FROM canonical_partition")).scalar_one() == 0
        assert session.execute(text("SELECT count(*) FROM canonical_quality_report")).scalar_one() == 0
    orphan_paths = list(tmp_path.rglob("data.parquet"))
    assert any("canonical" in path.as_posix() for path in orphan_paths)


@pytest.mark.parametrize(
    ("tamper_kind", "expected_code"),
    [
        ("manifest", "CANONICAL_RAW_MANIFEST_INVALID"),
        ("payload", "CANONICAL_RAW_INTEGRITY_FAILED"),
    ],
)
def test_raw_integrity_failure_is_rejected_and_audited(
    isolated_postgres_database,
    tmp_path: Path,
    tamper_kind: str,
    expected_code: str,
) -> None:
    database = isolated_postgres_database
    upgrade_database(database.engine)
    ProviderRegistryService(database).bootstrap_defaults()
    task_control = TaskControlService(database, clock=lambda: NOW, runtime_root=tmp_path)
    raw_result = _calendar_raw_result(database, tmp_path, task_control)

    from src.artifacts.namespace import StorageNamespaceResolver

    resolver = StorageNamespaceResolver(tmp_path)
    payload_path = resolver.resolve(raw_result.raw_object.storage_ref, require_exists=True)
    if tamper_kind == "manifest":
        (payload_path.parent / "manifest.json").write_text('{"corrupted": true}', encoding="utf-8")
    else:
        payload_path.write_bytes(b"tampered")

    task = _calendar_canonical_task(task_control, raw_result)
    lease = task_control.lease_next(worker_id="canonical-worker", worker_capabilities=("canonical_normalization",))
    assert lease is not None
    with pytest.raises(CanonicalNormalizationError) as exc_info:
        CanonicalNormalizationTaskWorker(
            task_control,
            database,
            runtime_root=tmp_path,
            clock=lambda: NOW,
        ).execute(lease)
    assert exc_info.value.error_code == expected_code

    assert task_control.get_task(task.task_id).task.task_state is TaskState.FAILED
    with database.engine.connect() as connection:
        reports = connection.execute(text("SELECT failure_reasons FROM canonical_quality_report")).scalars().all()
    assert any(expected_code in reasons for reasons in reports)


def test_canonical_worker_lease_loss_leaves_orphan_and_retries_with_new_attempt(
    isolated_postgres_database,
    tmp_path: Path,
) -> None:
    database = isolated_postgres_database
    upgrade_database(database.engine)
    ProviderRegistryService(database).bootstrap_defaults()
    current = [NOW]
    task_control = TaskControlService(database, clock=lambda: current[0], runtime_root=tmp_path)
    raw_result = _calendar_raw_result(database, tmp_path, task_control)
    task = _calendar_canonical_task(task_control, raw_result)
    lease = task_control.lease_next(
        worker_id="canonical-worker-1",
        worker_capabilities=("canonical_normalization",),
        lease_seconds=1,
    )
    assert lease is not None

    worker = CanonicalNormalizationTaskWorker(
        task_control,
        database,
        runtime_root=tmp_path,
        clock=lambda: current[0],
    )
    publish = worker.normalizer.publish_partition

    def publish_then_lose_lease(partition, report, content):
        publish(partition, report, content)
        current[0] = NOW + timedelta(seconds=2)

    worker.normalizer.publish_partition = publish_then_lose_lease
    with pytest.raises(TaskControlError, match="TASK_LEASE_LOST"):
        worker.execute(lease)

    assert task_control.get_task(task.task_id).task.task_state is TaskState.RUNNING
    with database.transaction() as session:
        assert session.execute(text("SELECT count(*) FROM canonical_partition")).scalar_one() == 0

    recovery_lease = task_control.lease_next(
        worker_id="canonical-worker-2",
        worker_capabilities=("canonical_normalization",),
        lease_seconds=30,
    )
    assert recovery_lease is not None
    assert recovery_lease.attempt.attempt_number == 2
    with pytest.raises(TaskControlError, match="TASK_LEASE_LOST"):
        task_control.heartbeat(lease.attempt.attempt_id, lease.lease_token)

    result = CanonicalNormalizationTaskWorker(
        task_control,
        database,
        runtime_root=tmp_path,
        clock=lambda: current[0],
    ).execute(recovery_lease)
    assert result.published is True
    assert task_control.get_task(task.task_id).task.task_state is TaskState.SUCCEEDED
    details = task_control.get_task(task.task_id)
    assert tuple(attempt.attempt_outcome for attempt in details.attempts) == (
        AttemptOutcome.LEASE_LOST,
        AttemptOutcome.SUCCEEDED,
    )
    with database.transaction() as session:
        assert session.execute(text("SELECT count(*) FROM canonical_partition")).scalar_one() == 1
    assert len(list(tmp_path.rglob("data.parquet"))) == 2
