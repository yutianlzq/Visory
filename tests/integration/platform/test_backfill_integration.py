from __future__ import annotations

import json

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

from src.artifacts.hashing import compute_bytes_hash
from src.schemas.platform import (
    BackfillBatchRequest,
    BackfillStatus,
    RawCompression,
    StorageBackend,
    StorageNamespace,
    StorageRef,
    TaskCreateRequest,
    TaskState,
)
from src.services.platform.backfill import BackfillPipelineCoordinator, BackfillPipelineExecutor, BackfillService, BackfillStageChainExecutor, BackfillWorker, DeterministicBackfillProvider, DeterministicBackfillPublisher
from src.services.platform.canonical_normalization import CanonicalNormalizationTaskWorker
from src.services.platform.provider_registry import ProviderRegistryService, default_provider_raw_schema_records
from src.services.platform.raw_ingestion import ProviderFetchResponse, RawIngestionTaskWorker, RawObjectPublisher
from src.services.platform.snapshot import SnapshotBuildTaskWorker, SnapshotGateService
from src.services.platform.task_control import TaskControlError, TaskControlService
import pytest
from src.repositories.platform import CanonicalRepository, RawIngestionRepository, SnapshotRepository, upgrade_database
from src.artifacts.namespace import StorageNamespaceResolver


def _checkpoint_writer(runtime_root):
    resolver = StorageNamespaceResolver(runtime_root)

    def write(*, task_id, attempt_id, payload):
        content_hash = compute_bytes_hash(payload)
        digest = content_hash.split(":", 1)[1]
        ref = StorageRef(
            storage_backend=StorageBackend.LOCAL_FS,
            storage_namespace=StorageNamespace.APP,
            relative_path=f"checkpoints/{task_id}/{attempt_id}/{digest}.json",
            content_hash=content_hash, media_type="application/json", size_bytes=len(payload),
        )
        path = resolver.resolve(ref)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            assert path.read_bytes() == payload
        else:
            with path.open("xb") as output:
                output.write(payload)
        return ref

    return write


class _PostgresPipelineWorker:
    def __init__(self, control, result, worker_capability, *, before_guard=None):
        self.control = control
        self.result = result
        self.worker_capability = worker_capability
        self.before_guard = before_guard
        self.executed_task_ids = []
        self.registered_task_ids = []

    def execute(self, lease, **kwargs):
        self.executed_task_ids.append(lease.task.task_id)
        self.control.start_attempt(lease.attempt.attempt_id, lease.lease_token)
        if self.before_guard is not None:
            self.before_guard()
        with self.control.database.transaction() as session:
            publication_guard = kwargs.get("publication_guard")
            assert publication_guard is not None
            publication_guard(session)
            self.registered_task_ids.append(lease.task.task_id)
            self.control.complete_in_session(
                session,
                attempt_id=lease.attempt.attempt_id,
                lease_token=lease.lease_token,
            )
        return self.result


def test_backfill_fixture_checkpoint_writer_retains_previous_content(tmp_path):
    writer = _checkpoint_writer(tmp_path)
    kwargs = dict(task_id="task_019dbd74-2a00-7000-8000-000000000002", attempt_id="attempt_019dbd74-2a00-7000-8000-000000000003")
    first = writer(**kwargs, payload=b'{"completed_partitions":[0]}')
    second = writer(**kwargs, payload=b'{"completed_partitions":[0,1]}')
    replay = writer(**kwargs, payload=b'{"completed_partitions":[0]}')
    assert first == replay
    assert first.relative_path != second.relative_path
    resolver = StorageNamespaceResolver(tmp_path)
    for ref in (first, second):
        content = resolver.resolve(ref, require_exists=True).read_bytes()
        assert compute_bytes_hash(content) == ref.content_hash
        assert len(content) == ref.size_bytes


@pytest.fixture
def task_database(isolated_postgres_database):
    upgrade_database(isolated_postgres_database.engine)
    return isolated_postgres_database


def _request(**updates):
    values = dict(batch_id="backfill_019dbd74-2a00-7000-8000-000000000101", batch_type="MONTH", date_from=date(2026, 8, 1), date_to=date(2026, 8, 31), dataset="bar_1d_raw", provider_policy_id="default", stage="PRICE_MONTH", dry_run=True, plan_only=True, requested_by="owner:integration")
    values.update(updates)
    return BackfillBatchRequest.model_validate(values)


def test_backfill_batch_uses_postgres_task_checkpoint_and_idempotency(task_database, tmp_path):
    control = TaskControlService(task_database, clock=lambda: datetime(2026, 8, 31, 12, tzinfo=timezone.utc), runtime_root=tmp_path)
    service = BackfillService(control)
    first = service.create_batch(_request(), idempotency_key="backfill-integration-1")
    replay = service.create_batch(_request(), idempotency_key="backfill-integration-1")
    assert first.task_id == replay.task_id

    lease = control.lease_next(worker_id="backfill-worker", worker_capabilities=("backfill",))
    assert lease is not None
    writer = _checkpoint_writer(tmp_path)

    result = BackfillWorker(control, DeterministicBackfillProvider(), checkpoint_writer=writer).execute(lease)
    assert result.batch_state is BackfillStatus.PARTIAL
    details = control.get_task(first.task_id)
    assert len(details.checkpoints) == 2
    assert details.task.requirements == lease.task.requirements
    assert details.task.canonical_request_hash == lease.task.canonical_request_hash
    assert service.get_batch(_request().batch_id).checkpoint_phase == "PRICE_MONTH"


def test_postgres_backfill_stage_chain_is_linear_idempotent_and_incrementally_unblocked(
    task_database,
    tmp_path,
):
    from src.schemas.platform import BackfillStage, BackfillStageChainRequest, TaskListQuery

    stage_datasets = {
        BackfillStage.IDENTITY_CALENDAR: "identity_calendar",
        BackfillStage.PRICE_MONTH: "bar_1d_raw",
        BackfillStage.LIFECYCLE_NAMES: "listing_status_history",
        BackfillStage.CORPORATE_ACTION: "corporate_action",
        BackfillStage.FINANCIAL_VALUATION: "financial_statement",
        BackfillStage.INDUSTRY_MEMBERS: "industry_membership",
        BackfillStage.NON_CORE_OBSERVATION: "non_core_observation",
    }
    request = BackfillStageChainRequest(
        batches=tuple(
            _request(
                batch_id=f"backfill_019dbd74-2a00-7000-8000-{index + 301:012x}",
                stage=stage,
                dataset=stage_datasets[stage],
                provider_policy_id=f"{stage_datasets[stage]}_v1",
            )
            for index, stage in enumerate(BackfillStage)
        )
    )
    control = TaskControlService(
        task_database,
        clock=lambda: datetime(2026, 8, 31, 12, tzinfo=timezone.utc),
        runtime_root=tmp_path,
    )
    service = BackfillService(control)
    idempotency_key = "backfill-stage-chain-postgres-1"

    created = service.create_stage_chain(request, idempotency_key=idempotency_key)
    replay = service.create_stage_chain(request, idempotency_key=idempotency_key)
    stable_task_ids = tuple(batch.task_id for batch in created.batches)

    assert tuple(batch.task_id for batch in replay.batches) == stable_task_ids
    assert created.batches[0].batch_state is BackfillStatus.PLANNED
    assert all(batch.batch_state is BackfillStatus.PAUSED for batch in created.batches[1:])

    persisted, next_cursor, has_more = control.list_tasks(
        TaskListQuery(task_type="backfill", limit=100)
    )
    assert next_cursor is None
    assert has_more is False
    assert len(persisted) == 7

    for index, task_id in enumerate(stable_task_ids):
        details = control.get_task(task_id)
        expected_dependencies = () if index == 0 else (stable_task_ids[index - 1],)
        assert tuple(details.task.requirements["dependency_task_ids"]) == expected_dependencies
        assert tuple(ref.resource_id for ref in details.task.input_refs[1:]) == expected_dependencies
        assert details.task.task_state is (
            TaskState.QUEUED if index == 0 else TaskState.BLOCKED
        )

    latest = created
    for index, expected_task_id in enumerate(stable_task_ids):
        lease = control.lease_next(
            worker_id=f"backfill-stage-{index}",
            worker_capabilities=("backfill",),
        )
        assert lease is not None
        assert lease.task.task_id == expected_task_id
        control.start_attempt(lease.attempt.attempt_id, lease.lease_token)
        with task_database.transaction() as session:
            control.complete_in_session(
                session,
                attempt_id=lease.attempt.attempt_id,
                lease_token=lease.lease_token,
            )

        latest = service.create_stage_chain(request, idempotency_key=idempotency_key)
        assert tuple(batch.task_id for batch in latest.batches) == stable_task_ids
        assert all(
            batch.batch_state is BackfillStatus.COMPLETED
            for batch in latest.batches[: index + 1]
        )
        if index + 1 < len(stable_task_ids):
            assert latest.batches[index + 1].batch_state is BackfillStatus.PLANNED
            assert all(
                batch.batch_state is BackfillStatus.PAUSED
                for batch in latest.batches[index + 2 :]
            )

    assert all(batch.batch_state is BackfillStatus.COMPLETED for batch in latest.batches)
    persisted_after, _, _ = control.list_tasks(TaskListQuery(task_type="backfill", limit=100))
    assert len(persisted_after) == 7
    for task_id in stable_task_ids:
        details = control.get_task(task_id)
        assert details.task.task_state is TaskState.SUCCEEDED
        assert len(details.attempts) == 1



@pytest.mark.parametrize(
    ("dry_run", "plan_only"),
    [(False, False), (True, False), (False, True), (True, True)],
    ids=["publish-fixture", "dry-run", "plan-only", "dry-run-and-plan-only"],
)
def test_postgres_backfill_stage_chain_executes_each_stage_worker(
    task_database,
    tmp_path,
    dry_run,
    plan_only,
):
    from src.schemas.platform import BackfillStage, BackfillStageChainRequest

    stage_datasets = {
        BackfillStage.IDENTITY_CALENDAR: "identity_calendar",
        BackfillStage.PRICE_MONTH: "bar_1d_raw",
        BackfillStage.LIFECYCLE_NAMES: "listing_status_history",
        BackfillStage.CORPORATE_ACTION: "corporate_action",
        BackfillStage.FINANCIAL_VALUATION: "financial_statement",
        BackfillStage.INDUSTRY_MEMBERS: "industry_membership",
        BackfillStage.NON_CORE_OBSERVATION: "non_core_observation",
    }
    request = BackfillStageChainRequest(
        batches=tuple(
            _request(
                batch_id=f"backfill_019dbd74-2a00-7000-8000-{index + 401:012x}",
                stage=stage,
                dataset=stage_datasets[stage],
                provider_policy_id=f"{stage_datasets[stage]}_v1",
                dry_run=dry_run,
                plan_only=plan_only,
            )
            for index, stage in enumerate(BackfillStage)
        )
    )
    control = TaskControlService(
        task_database,
        clock=lambda: datetime(2026, 8, 31, 12, tzinfo=timezone.utc),
        runtime_root=tmp_path,
    )
    workers = []

    def worker_factory(lease):
        publisher = DeterministicBackfillPublisher()
        worker = BackfillWorker(
            control,
            DeterministicBackfillProvider(),
            publisher=publisher,
            checkpoint_writer=_checkpoint_writer(tmp_path),
        )
        workers.append((lease.task.task_id, lease.task.requirements["stage"], worker, publisher))
        return worker

    executor = BackfillStageChainExecutor(
        control,
        worker_factory=worker_factory,
    )
    result = executor.execute(
        request,
        idempotency_key="backfill-stage-chain-postgres-workers",
    )

    assert result.stopped_task_id is None
    assert len(result.executed_task_ids) == len(BackfillStage)
    assert tuple(stage for _, stage, _, _ in workers) == tuple(stage.value for stage in BackfillStage)
    nonpublishing = dry_run or plan_only
    expected_state = BackfillStatus.PARTIAL if nonpublishing else BackfillStatus.COMPLETED
    assert all(item.batch_state is expected_state for item in result.projection.batches)
    for task_id in result.executed_task_ids:
        details = control.get_task(task_id)
        assert details.task.task_state is (
            TaskState.DEGRADED if nonpublishing else TaskState.SUCCEEDED
        )
        assert len(details.attempts) == 1
        assert len(details.checkpoints) == 2

    replay = executor.execute(
        request, idempotency_key="backfill-stage-chain-postgres-workers"
    )
    assert replay.executed_task_ids == ()
    assert replay.stopped_task_id is None
    assert tuple(batch.task_id for batch in replay.projection.batches) == result.executed_task_ids
    assert len(workers) == len(BackfillStage)
    for task_id in result.executed_task_ids:
        assert len(control.get_task(task_id).attempts) == 1

    if nonpublishing:
        from sqlalchemy import func, select
        from src.repositories.platform.canonical import canonical_partition, canonical_quality_report
        from src.repositories.platform.raw_ingestion import provider_run, raw_object
        from src.repositories.platform.snapshot import data_snapshot
        from src.repositories.platform.task import platform_task

        service = BackfillService(control)
        for batch in request.batches:
            observed = service.get_batch(batch.batch_id)
            assert observed.completed_range is None
            assert observed.skipped_range == (batch.date_from, batch.date_to)
            assert not observed.provider_run_refs
            assert not observed.raw_object_refs
            assert not observed.canonical_partition_refs
            assert not observed.snapshot_refs
        with task_database.engine.connect() as connection:
            assert connection.scalar(select(func.count()).select_from(platform_task)) == 7
            for table in (provider_run, raw_object, canonical_partition, canonical_quality_report, data_snapshot):
                assert connection.scalar(select(func.count()).select_from(table)) == 0


@pytest.mark.parametrize(
    ("batch_type", "date_from", "date_to", "expected_partitions"),
    [
        ("MONTH", date(2026, 8, 1), date(2026, 8, 31), 1),
        ("YEAR", date(2026, 1, 1), date(2026, 12, 31), 12),
    ],
)
def test_postgres_backfill_fixture_pilot_persists_checkpoint_and_publication(
    task_database, tmp_path, batch_type, date_from, date_to, expected_partitions
):
    request = _request(
        batch_id=f"backfill_019dbd74-2a00-7000-8000-{expected_partitions:012d}",
        batch_type=batch_type,
        date_from=date_from,
        date_to=date_to,
        dry_run=False,
        plan_only=False,
    )
    control = TaskControlService(task_database, clock=lambda: datetime(2026, 12, 31, 12, tzinfo=timezone.utc), runtime_root=tmp_path)
    service = BackfillService(control)
    projection = service.create_batch(request, idempotency_key=f"backfill-pilot-{batch_type}")
    lease = control.lease_next(worker_id="backfill-pilot", worker_capabilities=("backfill",))
    assert lease is not None

    writer = _checkpoint_writer(tmp_path)

    provider = DeterministicBackfillProvider()
    publisher = DeterministicBackfillPublisher()
    result = BackfillWorker(control, provider, publisher=publisher, checkpoint_writer=writer).execute(lease)
    assert result.batch_state is BackfillStatus.COMPLETED
    assert len(provider.calls) == expected_partitions
    details = control.get_task(projection.task_id)
    assert details.task.task_state.name == "SUCCEEDED"
    assert len(details.checkpoints) == expected_partitions + 1
    assert details.task.requirements == lease.task.requirements
    assert details.task.canonical_request_hash == lease.task.canonical_request_hash
    observed = service.get_batch(request.batch_id)
    assert len(observed.canonical_partition_refs) == expected_partitions
    resolver = StorageNamespaceResolver(tmp_path)
    for checkpoint in details.checkpoints:
        content = resolver.resolve(checkpoint.storage_ref, require_exists=True).read_bytes()
        assert compute_bytes_hash(content) == checkpoint.checkpoint_hash
    final_payload = json.loads(resolver.resolve(details.checkpoints[-1].storage_ref).read_bytes())
    assert len(final_payload["published_refs"]) == expected_partitions
    assert final_payload["completed_partitions"] == list(range(expected_partitions))
    assert len(observed.snapshot_refs) == expected_partitions


def _provider_response(
    dataset_id: str,
    now: datetime,
    *,
    calendar_dates: tuple[date, ...],
    trade_date: date,
) -> ProviderFetchResponse:
    schema = next(
        item
        for item in default_provider_raw_schema_records()
        if item.provider_id == "a_stock_data" and item.dataset_id == dataset_id
    )
    payloads = {
        "trading_calendar": [
            {
                "market_code": "SH",
                "cal_date": calendar_date.isoformat(),
                "is_open": True,
                "session_open": f"{calendar_date.isoformat()}T01:30:00Z",
                "session_close": f"{calendar_date.isoformat()}T07:00:00Z",
                "as_of": now.isoformat(),
            }
            for calendar_date in calendar_dates
        ],
        "security_master": [
            {
                "ts_code": "600519.SH",
                "exchange_code": "SSE",
                "asset_type": "EQUITY",
                "security_name": "Kweichow Moutai",
                "listed_on": "2001-08-27",
                "currency_code": "RMB",
                "lot_size": 100,
                "as_of": now.isoformat(),
            }
        ],
        "bar_1d_raw": [
            {
                "ts_code": "600519.SH",
                "trade_date": trade_date.isoformat(),
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
                "as_of": now.isoformat(),
            }
        ],
    }
    payload = payloads[dataset_id]
    return ProviderFetchResponse(
        content=json.dumps(payload, sort_keys=True).encode("utf-8"),
        media_type="application/json",
        compression=RawCompression.NONE,
        actual_upstream="fixture.a-stock-data",
        observed_at=now,
        source_published_at=None,
        raw_schema_fields=tuple(schema.field_types),
        raw_schema_field_types=dict(schema.field_types),
        row_count=len(payload),
    )


@pytest.mark.parametrize(
    ("batch_type", "date_from", "date_to", "calendar_dates", "simulate_checkpoint_crash"),
    [
        (
            "MONTH",
            date(2026, 8, 1),
            date(2026, 8, 31),
            (date(2026, 8, 31),),
            False,
        ),
        (
            "YEAR",
            date(2026, 1, 1),
            date(2026, 12, 31),
            (
                date(2026, 1, 31),
                date(2026, 2, 28),
                date(2026, 3, 31),
                date(2026, 4, 30),
                date(2026, 5, 31),
                date(2026, 6, 30),
                date(2026, 7, 31),
                date(2026, 8, 31),
                date(2026, 9, 30),
                date(2026, 10, 31),
                date(2026, 11, 30),
                date(2026, 12, 31),
            ),
            False,
        ),
        (
            "MONTH",
            date(2026, 8, 1),
            date(2026, 8, 31),
            (date(2026, 8, 31),),
            True,
        ),
    ],
    ids=("month", "year", "month-checkpoint-crash-recovery"),
)
def test_postgres_backfill_pipeline_publishes_real_raw_canonical_and_snapshot_pilots(
    task_database,
    tmp_path,
    batch_type,
    date_from,
    date_to,
    calendar_dates,
    simulate_checkpoint_crash,
):
    now = datetime(2026, 12, 31, 12, tzinfo=timezone.utc)
    clock = {"value": now}
    ProviderRegistryService(task_database).bootstrap_defaults()
    control = TaskControlService(
        task_database,
        clock=lambda: clock["value"],
        runtime_root=tmp_path,
    )
    publisher = RawObjectPublisher(tmp_path, task_database.transaction, clock=lambda: now)

    class BackfillFixtureTransport:
        def __init__(self):
            self.bar_fetch_count = 0

        def fetch(self, adapter_name, fetch_request, *, timeout_seconds):
            assert adapter_name == "a_stock_data"
            if fetch_request.dataset_id == "bar_1d_raw":
                self.bar_fetch_count += 1
            requested_day = fetch_request.request.get("trade_date")
            trade_day = (
                date.fromisoformat(requested_day)
                if isinstance(requested_day, str)
                else calendar_dates[-1]
            )
            return _provider_response(
                fetch_request.dataset_id,
                now,
                calendar_dates=(trade_day,)
                if fetch_request.dataset_id == "trading_calendar"
                else calendar_dates,
                trade_date=trade_day,
            )

    transport = BackfillFixtureTransport()
    raw_worker = RawIngestionTaskWorker(
        control,
        task_database,
        publisher,
        transport,
        clock=lambda: now,
    )
    canonical_worker = CanonicalNormalizationTaskWorker(
        control,
        task_database,
        runtime_root=tmp_path,
        clock=lambda: now,
    )

    def raw_requirements(
        dataset_id: str,
        trade_day: date | None = None,
    ) -> dict[str, object]:
        request_payload = (
            {"trade_date": trade_day.isoformat()}
            if trade_day is not None
            else {"as_of": now.date().isoformat()}
        )
        return {
            "provider_id": "a_stock_data",
            "dataset_id": dataset_id,
            "dataset_schema_version": "1.0.0",
            "provider_policy_id": f"{dataset_id}_v1",
            "market": "CN",
            "request": request_payload,
            "timeout_seconds": 5,
        }

    def canonical_requirements(
        raw_result,
        dataset_id: str,
        partition_key: str,
    ) -> dict[str, object]:
        return {
            "provider_id": "a_stock_data",
            "dataset_id": dataset_id,
            "dataset_schema_version": "1.0.0",
            "raw_object_id": raw_result.raw_object.raw_object_id,
            "provider_run_id": raw_result.provider_run.provider_run_id,
            "provider_policy_id": f"{dataset_id}_v1",
            "provider_policy_version": "1.0.0",
            "mapping_version": "1.0.0",
            "partition_key": partition_key,
            "market": "CN",
        }

    security_raw_task = control.create_task(
        TaskCreateRequest(
            task_type="raw_ingestion",
            requested_by="integration",
            request_source="integration_test",
            requirements=raw_requirements("security_master"),
        ),
        idempotency_key=f"wp0207-real-{batch_type}-seed-raw-security-master",
    )
    security_raw_lease = control.lease_next(
        worker_id="seed-raw-security-master",
        worker_capabilities=("raw_ingestion",),
    )
    assert (
        security_raw_lease is not None
        and security_raw_lease.task.task_id == security_raw_task.task_id
    )
    security_raw_result = raw_worker.execute(security_raw_lease)
    assert security_raw_result.raw_object is not None
    security_task = control.create_task(
        TaskCreateRequest(
            task_type="canonical_normalization",
            requested_by="integration",
            request_source="integration_test",
            requirements=canonical_requirements(
                security_raw_result,
                "security_master",
                "2026",
            ),
        ),
        idempotency_key=f"wp0207-real-{batch_type}-seed-canonical-security-master",
    )
    security_lease = control.lease_next(
        worker_id="seed-canonical-security-master",
        worker_capabilities=("canonical_normalization",),
    )
    assert security_lease is not None and security_lease.task.task_id == security_task.task_id
    security_result = canonical_worker.execute(security_lease)
    assert security_result.published is True
    assert security_result.canonical_partition is not None
    security_partition = security_result.canonical_partition

    calendar_partitions = {}
    for calendar_date in calendar_dates:
        date_key = calendar_date.isoformat()
        calendar_raw_task = control.create_task(
            TaskCreateRequest(
                task_type="raw_ingestion",
                requested_by="integration",
                request_source="integration_test",
                requirements=raw_requirements("trading_calendar", calendar_date),
            ),
            idempotency_key=f"wp0207-real-{batch_type}-seed-raw-calendar-{date_key}",
        )
        calendar_raw_lease = control.lease_next(
            worker_id=f"seed-raw-calendar-{date_key}",
            worker_capabilities=("raw_ingestion",),
        )
        assert (
            calendar_raw_lease is not None
            and calendar_raw_lease.task.task_id == calendar_raw_task.task_id
        )
        calendar_raw_result = raw_worker.execute(calendar_raw_lease)
        assert calendar_raw_result.raw_object is not None
        calendar_task = control.create_task(
            TaskCreateRequest(
                task_type="canonical_normalization",
                requested_by="integration",
                request_source="integration_test",
                requirements=canonical_requirements(
                    calendar_raw_result,
                    "trading_calendar",
                    date_key,
                ),
            ),
            idempotency_key=f"wp0207-real-{batch_type}-seed-canonical-calendar-{date_key}",
        )
        calendar_lease = control.lease_next(
            worker_id=f"seed-canonical-calendar-{date_key}",
            worker_capabilities=("canonical_normalization",),
        )
        assert (
            calendar_lease is not None
            and calendar_lease.task.task_id == calendar_task.task_id
        )
        calendar_result = canonical_worker.execute(calendar_lease)
        assert calendar_result.published is True
        assert calendar_result.canonical_partition is not None
        calendar_partitions[calendar_date] = calendar_result.canonical_partition

    expected_partitions = len(calendar_dates)
    request = _request(
        batch_id=f"backfill_019dbd74-2a00-7000-8000-{expected_partitions + 716:012d}",
        batch_type=batch_type,
        date_from=date_from,
        date_to=date_to,
        provider_policy_id="bar_1d_raw_v1",
        dry_run=False,
        plan_only=False,
    )
    service = BackfillService(control)
    projection = service.create_batch(
        request,
        idempotency_key=f"wp0207-real-object-chain-{batch_type}",
    )
    parent_lease = control.lease_next(
        worker_id="backfill-real-parent",
        worker_capabilities=("backfill",),
        lease_seconds=60,
    )
    assert parent_lease is not None and parent_lease.task.task_id == projection.task_id

    leased_child_task_ids: list[str] = []

    def lease_child(task_id: str, task_type: str):
        lease = control.lease_next(
            worker_id=f"backfill-real-{task_type}",
            worker_capabilities=(task_type,),
        )
        if lease is None:
            return None
        assert lease.task.task_id == task_id
        leased_child_task_ids.append(task_id)
        return lease

    snapshot_service = SnapshotGateService(
        task_database,
        runtime_root=tmp_path,
        clock=lambda: now,
    )
    executor = BackfillPipelineExecutor(
        BackfillPipelineCoordinator(control),
        lease_provider=lease_child,
        raw_worker=raw_worker,
        canonical_worker=canonical_worker,
        snapshot_worker=SnapshotBuildTaskWorker(control, snapshot_service),
    )

    def plan_factory(part, provider_result, index):
        return {
            "raw_requirements": raw_requirements("bar_1d_raw", part.date_to),
            "canonical_requirements": lambda raw: canonical_requirements(
                raw,
                "bar_1d_raw",
                part.date_to.isoformat(),
            ),
            "snapshot_requirements": lambda canonical: {
                "trade_date": part.date_to.isoformat(),
                "cutoff_at": now.isoformat(),
                "provider_policy_id": request.provider_policy_id,
                "provider_policy_version": "1.0.0",
                "security_master_ref": security_partition.canonical_partition_id,
                "calendar_ref": calendar_partitions[part.date_to].canonical_partition_id,
                "canonical_partition_ids": (
                    security_partition.canonical_partition_id,
                    calendar_partitions[part.date_to].canonical_partition_id,
                    canonical.canonical_partition.canonical_partition_id,
                ),
                "requested_capabilities": ("identity_core", "calendar_core"),
            },
            "partition_rows": None,
        }

    def worker(checkpoint_writer):
        return BackfillWorker(
            control,
            DeterministicBackfillProvider(),
            checkpoint_writer=checkpoint_writer,
            pipeline_executor=executor,
            pipeline_plan_factory=plan_factory,
        )

    published_before_crash = None
    if simulate_checkpoint_crash:
        class SimulatedProcessCrash(BaseException):
            pass

        def crash_after_child_publication(**_kwargs):
            raise SimulatedProcessCrash("simulated process exit before parent checkpoint")

        with pytest.raises(SimulatedProcessCrash):
            worker(crash_after_child_publication).execute(parent_lease)

        assert len(leased_child_task_ids) == 3
        assert transport.bar_fetch_count == 1
        crashed_parent = control.get_task(projection.task_id)
        assert crashed_parent.task.task_state is TaskState.RUNNING
        assert crashed_parent.checkpoints == ()
        assert all(
            control.get_task(task_id).task.task_state is TaskState.SUCCEEDED
            for task_id in leased_child_task_ids
        )

        with task_database.transaction() as session:
            raw_repository = RawIngestionRepository()
            canonical_repository = CanonicalRepository()
            snapshot_repository = SnapshotRepository()
            provider_run = raw_repository.get_provider_run_by_task(
                session,
                leased_child_task_ids[0],
            )
            raw_object = (
                raw_repository.get_raw_object_by_run(session, provider_run.provider_run_id)
                if provider_run is not None
                else None
            )
            quality_report = canonical_repository.get_quality_report_by_task(
                session,
                leased_child_task_ids[1],
            )
            canonical_partition = (
                canonical_repository.get_partition(
                    session,
                    quality_report.canonical_partition_id,
                )
                if quality_report is not None
                and quality_report.canonical_partition_id is not None
                else None
            )
            snapshot = snapshot_repository.get_snapshot_by_task(
                session,
                leased_child_task_ids[2],
            )
        assert provider_run is not None
        assert raw_object is not None
        assert canonical_partition is not None
        assert snapshot is not None
        published_before_crash = (
            provider_run.provider_run_id,
            raw_object.raw_object_id,
            canonical_partition.canonical_partition_id,
            snapshot.snapshot_id,
        )

        clock["value"] = now + timedelta(seconds=181)
        parent_lease = control.lease_next(
            worker_id="backfill-real-parent-recovery",
            worker_capabilities=("backfill",),
            lease_seconds=60,
        )
        assert parent_lease is not None
        assert parent_lease.task.task_id == projection.task_id
        assert parent_lease.attempt.attempt_number == 2

    result = worker(_checkpoint_writer(tmp_path)).execute(parent_lease)

    assert result.batch_state is BackfillStatus.COMPLETED
    observed = service.get_batch(request.batch_id)
    if published_before_crash is not None:
        assert len(leased_child_task_ids) == 3
        assert transport.bar_fetch_count == 1
        assert all(
            len(control.get_task(task_id).attempts) == 1
            for task_id in leased_child_task_ids
        )
        assert (
            observed.provider_run_refs[0],
            observed.raw_object_refs[0],
            observed.canonical_partition_refs[0],
            observed.snapshot_refs[0],
        ) == published_before_crash
    assert len(set(observed.provider_run_refs)) == len(observed.provider_run_refs)
    assert len(observed.raw_object_refs) == expected_partitions
    assert len(observed.canonical_partition_refs) == expected_partitions
    assert len(observed.snapshot_refs) == expected_partitions
    details = control.get_task(projection.task_id)
    assert details.task.task_state is TaskState.SUCCEEDED
    assert len(details.checkpoints) == expected_partitions + 1

    with task_database.transaction() as session:
        raw_repository = RawIngestionRepository()
        canonical_repository = CanonicalRepository()
        snapshot_repository = SnapshotRepository()
        raw_objects = tuple(
            raw_repository.get_raw_object(session, raw_object_id)
            for raw_object_id in observed.raw_object_refs
        )
        provider_runs = tuple(
            raw_repository.get_provider_run(session, raw_object.provider_run_id)
            if raw_object is not None
            else None
            for raw_object in raw_objects
        )
        partitions = tuple(
            canonical_repository.get_partition(session, partition_id)
            for partition_id in observed.canonical_partition_refs
        )
        snapshots = tuple(
            snapshot_repository.get_snapshot(session, snapshot_id)
            for snapshot_id in observed.snapshot_refs
        )

    assert all(raw_object is not None for raw_object in raw_objects)
    assert all(provider_run is not None for provider_run in provider_runs)
    assert all(partition is not None for partition in partitions)
    assert all(snapshot is not None for snapshot in snapshots)
    for raw_object, provider_run in zip(raw_objects, provider_runs, strict=True):
        assert raw_object is not None and provider_run is not None
        assert provider_run.raw_object_refs == (raw_object.raw_object_id,)
        assert provider_run.provider_run_id in observed.provider_run_refs
        assert raw_object.provider_run_id == provider_run.provider_run_id
        publisher.resolver.resolve(raw_object.storage_ref, require_exists=True)
    for partition, snapshot in zip(partitions, snapshots, strict=True):
        assert partition is not None and snapshot is not None
        assert partition.raw_object_refs in {
            (raw_object.raw_object_id,)
            for raw_object in raw_objects
            if raw_object is not None
        }
        assert {item.canonical_partition_id for item in snapshot.canonical_partitions} == {
            security_partition.canonical_partition_id,
            calendar_partitions[snapshot.trade_date].canonical_partition_id,
            partition.canonical_partition_id,
        }
        publisher.resolver.resolve(partition.storage_ref, require_exists=True)
        snapshot_service.manifest_publisher.read_and_validate(snapshot)


def test_postgres_backfill_pipeline_executes_real_child_task_chain(task_database, tmp_path):
    request = _request(
        batch_id="backfill_019dbd74-2a00-7000-8000-000000000707",
        dry_run=False,
        plan_only=False,
    )
    control = TaskControlService(
        task_database,
        clock=lambda: datetime(2026, 12, 31, 12, tzinfo=timezone.utc),
        runtime_root=tmp_path,
    )
    service = BackfillService(control)
    projection = service.create_batch(request, idempotency_key="backfill-pipeline-postgres")
    parent_lease = control.lease_next(worker_id="backfill-parent", worker_capabilities=("backfill",))
    assert parent_lease is not None

    raw_result = SimpleNamespace(
        raw_object=SimpleNamespace(raw_object_id="raw_00000000-0000-7000-8000-000000000707"),
        provider_run=SimpleNamespace(provider_run_id="prun_00000000-0000-7000-8000-000000000707"),
    )
    canonical_result = SimpleNamespace(
        canonical_partition=SimpleNamespace(canonical_partition_id="cpart_00000000-0000-7000-8000-000000000707"),
        published=True,
    )
    snapshot_result = SimpleNamespace(
        snapshot=SimpleNamespace(snapshot_id="ds_00000000-0000-7000-8000-000000000707"),
        published=True,
    )
    workers = (
        _PostgresPipelineWorker(control, raw_result, "raw_ingestion"),
        _PostgresPipelineWorker(control, canonical_result, "canonical_normalization"),
        _PostgresPipelineWorker(control, snapshot_result, "data_snapshot_build"),
    )

    def lease_child(task_id, task_type):
        lease = control.lease_next(
            worker_id=f"backfill-child-{task_type}",
            worker_capabilities=(task_type,),
        )
        assert lease is not None
        assert lease.task.task_id == task_id
        return lease

    executor = BackfillPipelineExecutor(
        BackfillPipelineCoordinator(control),
        lease_provider=lease_child,
        raw_worker=workers[0],
        canonical_worker=workers[1],
        snapshot_worker=workers[2],
    )
    result = BackfillWorker(
        control,
        DeterministicBackfillProvider(),
        checkpoint_writer=_checkpoint_writer(tmp_path),
        pipeline_executor=executor,
        pipeline_plan_factory=lambda part, provider_result, index: {
            "raw_requirements": {
                "provider_id": "fixture",
                "dataset_id": request.dataset,
                "dataset_schema_version": "1.0.0",
                "provider_policy_id": request.provider_policy_id,
            },
            "canonical_requirements": lambda raw: {
                "provider_id": "fixture",
                "dataset_id": request.dataset,
                "dataset_schema_version": "1.0.0",
                "raw_object_id": raw.raw_object.raw_object_id,
                "provider_run_id": raw.provider_run.provider_run_id,
                "provider_policy_id": request.provider_policy_id,
                "provider_policy_version": "1.0.0",
                "mapping_version": "1.0.0",
                "partition_key": "2026-08",
            },
            "snapshot_requirements": lambda canonical: {
                "trade_date": "2026-08-31",
                "cutoff_at": "2026-09-18T00:00:00Z",
                "provider_policy_id": request.provider_policy_id,
                "provider_policy_version": "1.0.0",
                "security_master_ref": canonical.canonical_partition.canonical_partition_id,
                "calendar_ref": canonical.canonical_partition.canonical_partition_id,
                "canonical_partition_ids": (canonical.canonical_partition.canonical_partition_id,),
                "requested_capabilities": ("bars",),
            },
            "partition_rows": {"bars": [{"asset_id": "asset_fixture"}]},
        },
    ).execute(parent_lease)

    assert result.batch_state is BackfillStatus.COMPLETED
    assert all(len(worker.executed_task_ids) == 1 for worker in workers)
    details = control.get_task(projection.task_id)
    assert details.task.task_state.name == "SUCCEEDED"
    observed = service.get_batch(request.batch_id)
    assert observed.raw_object_refs == (raw_result.raw_object.raw_object_id,)
    assert observed.canonical_partition_refs == (canonical_result.canonical_partition.canonical_partition_id,)
    assert observed.snapshot_refs == (snapshot_result.snapshot.snapshot_id,)


def test_postgres_parent_cancel_fences_child_publication_transaction(task_database, tmp_path):
    request = _request(
        batch_id="backfill_019dbd74-2a00-7000-8000-000000000708",
        dry_run=False,
        plan_only=False,
    )
    control = TaskControlService(
        task_database,
        clock=lambda: datetime(2026, 12, 31, 12, tzinfo=timezone.utc),
        runtime_root=tmp_path,
    )
    projection = BackfillService(control).create_batch(
        request,
        idempotency_key="backfill-parent-cancel-fence",
    )
    parent_lease = control.lease_next(
        worker_id="backfill-parent-cancel",
        worker_capabilities=("backfill",),
    )
    assert parent_lease is not None

    raw_result = SimpleNamespace(
        raw_object=SimpleNamespace(
            raw_object_id="raw_00000000-0000-7000-8000-000000000708"
        ),
        provider_run=SimpleNamespace(
            provider_run_id="prun_00000000-0000-7000-8000-000000000708"
        ),
    )
    canonical_result = SimpleNamespace(
        canonical_partition=SimpleNamespace(
            canonical_partition_id="cpart_00000000-0000-7000-8000-000000000708"
        ),
        published=True,
    )
    snapshot_result = SimpleNamespace(
        snapshot=SimpleNamespace(
            snapshot_id="ds_00000000-0000-7000-8000-000000000708"
        ),
        published=True,
    )
    workers = (
        _PostgresPipelineWorker(
            control,
            raw_result,
            "raw_ingestion",
            before_guard=lambda: control.request_cancel(
                projection.task_id,
                actor_ref="test:cancel-fence",
            ),
        ),
        _PostgresPipelineWorker(control, canonical_result, "canonical_normalization"),
        _PostgresPipelineWorker(control, snapshot_result, "data_snapshot_build"),
    )

    def lease_child(task_id, task_type):
        lease = control.lease_next(
            worker_id=f"backfill-cancel-child-{task_type}",
            worker_capabilities=(task_type,),
        )
        assert lease is not None
        assert lease.task.task_id == task_id
        return lease

    executor = BackfillPipelineExecutor(
        BackfillPipelineCoordinator(control),
        lease_provider=lease_child,
        raw_worker=workers[0],
        canonical_worker=workers[1],
        snapshot_worker=workers[2],
    )
    result = BackfillWorker(
        control,
        DeterministicBackfillProvider(),
        checkpoint_writer=_checkpoint_writer(tmp_path),
        pipeline_executor=executor,
        pipeline_plan_factory=lambda part, provider_result, index: {
            "raw_requirements": {
                "provider_id": "fixture",
                "dataset_id": request.dataset,
                "dataset_schema_version": "1.0.0",
                "provider_policy_id": request.provider_policy_id,
            },
            "canonical_requirements": {},
            "snapshot_requirements": {},
            "partition_rows": {},
        },
    ).execute(parent_lease)

    assert result.batch_state is BackfillStatus.CANCELLED
    assert control.get_task(projection.task_id).task.task_state.name == "CANCELLED"
    assert len(workers[0].executed_task_ids) == 1
    assert workers[0].registered_task_ids == []
    assert workers[1].executed_task_ids == []
    assert workers[2].executed_task_ids == []
    child = control.get_task(workers[0].executed_task_ids[0]).task
    assert child.task_state.name == "CANCELLED"


def test_postgres_parent_lease_expiry_fences_child_and_reaper_recovers(task_database, tmp_path):
    now = {"value": datetime(2026, 12, 31, 12, tzinfo=timezone.utc)}
    request = _request(
        batch_id="backfill_019dbd74-2a00-7000-8000-000000000709",
        dry_run=False,
        plan_only=False,
    )
    control = TaskControlService(
        task_database,
        clock=lambda: now["value"],
        runtime_root=tmp_path,
    )
    projection = BackfillService(control).create_batch(
        request,
        idempotency_key="backfill-parent-lease-fence",
    )
    parent_lease = control.lease_next(
        worker_id="backfill-parent-expiry",
        worker_capabilities=("backfill",),
        lease_seconds=60,
    )
    assert parent_lease is not None

    raw_result = SimpleNamespace(
        raw_object=SimpleNamespace(
            raw_object_id="raw_00000000-0000-7000-8000-000000000709"
        ),
        provider_run=SimpleNamespace(
            provider_run_id="prun_00000000-0000-7000-8000-000000000709"
        ),
    )
    raw_worker = _PostgresPipelineWorker(
        control,
        raw_result,
        "raw_ingestion",
        before_guard=lambda: now.update(
            value=datetime(2026, 12, 31, 12, 5, 1, tzinfo=timezone.utc)
        ),
    )
    unused_worker = _PostgresPipelineWorker(
        control,
        SimpleNamespace(published=True),
        "unused",
    )

    def lease_child(task_id, task_type):
        lease = control.lease_next(
            worker_id=f"backfill-expiry-child-{task_type}",
            worker_capabilities=(task_type,),
            lease_seconds=60,
        )
        assert lease is not None
        assert lease.task.task_id == task_id
        return lease

    executor = BackfillPipelineExecutor(
        BackfillPipelineCoordinator(control),
        lease_provider=lease_child,
        raw_worker=raw_worker,
        canonical_worker=unused_worker,
        snapshot_worker=unused_worker,
    )
    with pytest.raises(TaskControlError, match="TASK_LEASE_LOST"):
        BackfillWorker(
            control,
            DeterministicBackfillProvider(),
            checkpoint_writer=_checkpoint_writer(tmp_path),
            pipeline_executor=executor,
            pipeline_plan_factory=lambda part, provider_result, index: {
                "raw_requirements": {
                    "provider_id": "fixture",
                    "dataset_id": request.dataset,
                    "dataset_schema_version": "1.0.0",
                    "provider_policy_id": request.provider_policy_id,
                },
                "canonical_requirements": {},
                "snapshot_requirements": {},
                "partition_rows": {},
            },
        ).execute(parent_lease)

    assert raw_worker.registered_task_ids == []
    child_task_id = raw_worker.executed_task_ids[0]
    assert control.get_task(child_task_id).task.task_state.name == "RUNNING"
    assert control.get_task(projection.task_id).task.task_state.name == "RUNNING"

    recovered_child = control.lease_next(
        worker_id="backfill-child-reaper",
        worker_capabilities=("raw_ingestion",),
        lease_seconds=60,
    )
    assert recovered_child is not None
    assert recovered_child.task.task_id == child_task_id
    assert recovered_child.attempt.attempt_number == 2

    recovered_parent = control.lease_next(
        worker_id="backfill-parent-reaper",
        worker_capabilities=("backfill",),
        lease_seconds=60,
    )
    assert recovered_parent is not None
    assert recovered_parent.task.task_id == projection.task_id
    assert recovered_parent.attempt.attempt_number == 2


def test_postgres_backfill_dependency_creation_has_no_visible_queue_window(
    task_database, tmp_path, monkeypatch
):
    from sqlalchemy import select
    from src.repositories.platform.task import platform_task
    from src.schemas.platform import BackfillStage

    control = TaskControlService(
        task_database,
        clock=lambda: datetime(2026, 8, 31, 12, tzinfo=timezone.utc),
        runtime_root=tmp_path,
    )
    service = BackfillService(control)
    dependency = service.create_batch(
        _request(stage=BackfillStage.IDENTITY_CALENDAR),
        idempotency_key="atomic-backfill-dependency",
    )
    parent_lease = control.lease_next(
        worker_id="dependency-worker", worker_capabilities=("backfill",)
    )
    assert parent_lease is not None
    control.start_attempt(parent_lease.attempt.attempt_id, parent_lease.lease_token)
    child = _request(
        batch_id="backfill_019dbd74-2a00-7000-8000-000000000601",
        dependency_task_ids=(dependency.task_id,),
    )
    scheduler = TaskControlService(task_database, clock=control.clock)
    original_transition = control._transition
    observations = []

    def observe_before_block(session, task, target, **kwargs):
        if target is TaskState.BLOCKED and task.requirements["batch_id"] == child.batch_id:
            # 第二条连接观察提交可见性，不能只用当前事务的最终状态证明没有领取窗口。
            with task_database.engine.connect() as connection:
                visible = connection.scalar(
                    select(platform_task.c.task_state).where(platform_task.c.task_id == task.task_id)
                )
            lease = scheduler.lease_next(
                worker_id="concurrent-scheduler", worker_capabilities=("backfill",)
            )
            observations.append((visible, lease))
        return original_transition(session, task, target, **kwargs)

    monkeypatch.setattr(control, "_transition", observe_before_block)
    created = service.create_batch(child, idempotency_key="atomic-backfill-child")
    assert observations == [(None, None)]
    details = control.get_task(created.task_id)
    assert details.task.task_state is TaskState.BLOCKED
    assert details.attempts == ()
    assert [event.next_task_state for event in details.state_events] == [
        TaskState.ACCEPTED, TaskState.QUEUED, TaskState.BLOCKED
    ]
    assert scheduler.lease_next(
        worker_id="after-commit-scheduler", worker_capabilities=("backfill",)
    ) is None
