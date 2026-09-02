from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import text

from src.repositories.platform import RawIngestionRepository, upgrade_database
from src.schemas.platform import RawCompression, TaskCreateRequest, TaskState
from src.services.platform.provider_registry import ProviderRegistryService, default_provider_raw_schema_records
from src.services.platform.raw_ingestion import (
    FakeProviderTransport,
    ProviderFetchResponse,
    ProviderRateLimiter,
    RawIngestionError,
    RawIngestionTaskWorker,
    RawObjectPublisher,
)
from src.services.platform.task_control import TaskControlError, TaskControlService


NOW = datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc)


def _requirements(dataset_id: str) -> dict[str, object]:
    return {
        "provider_id": "a_stock_data",
        "dataset_id": dataset_id,
        "dataset_schema_version": "1.0.0",
        "provider_policy_id": f"{dataset_id}_v1",
        "market": "CN",
        "request": {"as_of": "2026-08-31"},
        "timeout_seconds": 5,
    }


def _request(dataset_id: str, *, key: str = "raw-key", max_attempts: int = 2) -> TaskCreateRequest:
    return TaskCreateRequest(
        task_type="raw_ingestion",
        requested_by="owner:raw-integration",
        request_source="integration_test",
        requirements=_requirements(dataset_id),
        max_attempts=max_attempts,
    )


def _response(dataset_id: str, *, extra_field: str | None = None) -> ProviderFetchResponse:
    schema = next(
        item for item in default_provider_raw_schema_records()
        if item.provider_id == "a_stock_data" and item.dataset_id == dataset_id
    )
    fields = tuple(schema.required_fields) + ((extra_field,) if extra_field else ())
    field_types = dict(schema.field_types)
    if extra_field:
        field_types[extra_field] = "string"
    payload = [{field: None for field in fields}]
    return ProviderFetchResponse(
        content=json.dumps(payload, sort_keys=True).encode("utf-8"),
        media_type="application/json",
        compression=RawCompression.NONE,
        actual_upstream="fixture.a-stock-data",
        observed_at=NOW,
        source_published_at=None,
        raw_schema_fields=fields,
        raw_schema_field_types=field_types,
        row_count=1,
    )


@pytest.fixture
def raw_runtime(isolated_postgres_database, tmp_path: Path):
    database = isolated_postgres_database
    upgrade_database(database.engine)
    ProviderRegistryService(database).bootstrap_defaults()
    task_control = TaskControlService(database, clock=lambda: NOW, runtime_root=tmp_path)
    publisher = RawObjectPublisher(tmp_path, database.transaction, clock=lambda: NOW)
    return database, task_control, publisher


@pytest.mark.parametrize("dataset_id", ["security_master", "trading_calendar", "bar_1d_raw"])
def test_raw_ingestion_vertical_success_for_all_initial_datasets(raw_runtime, dataset_id: str) -> None:
    database, task_control, publisher = raw_runtime
    task = task_control.create_task(_request(dataset_id), idempotency_key=f"raw-success-{dataset_id}")
    lease = task_control.lease_next(worker_id="raw-worker", worker_capabilities=("raw_ingestion",))
    assert lease is not None and lease.task.task_id == task.task_id
    worker = RawIngestionTaskWorker(
        task_control,
        database,
        publisher,
        FakeProviderTransport({("a_stock_data", dataset_id): _response(dataset_id)}),
        clock=lambda: NOW,
    )

    result = worker.execute(lease)

    assert result.raw_object is not None
    assert result.quarantine is None
    assert task_control.get_task(task.task_id).task.task_state is TaskState.SUCCEEDED
    raw_path = publisher.resolver.resolve(result.raw_object.storage_ref, require_exists=True)
    assert raw_path.read_bytes() == _response(dataset_id).content
    with database.transaction() as session:
        assert RawIngestionRepository().get_raw_object(session, result.raw_object.raw_object_id) == result.raw_object
        assert RawIngestionRepository().get_provider_run(session, result.provider_run.provider_run_id) == result.provider_run


def test_additive_schema_drift_is_quarantined_and_task_is_degraded(raw_runtime) -> None:
    database, task_control, publisher = raw_runtime
    task = task_control.create_task(_request("security_master"), idempotency_key="raw-additive")
    lease = task_control.lease_next(worker_id="raw-worker", worker_capabilities=("raw_ingestion",))
    assert lease is not None
    worker = RawIngestionTaskWorker(
        task_control, database, publisher,
        FakeProviderTransport({("a_stock_data", "security_master"): _response("security_master", extra_field="new_field")}),
        clock=lambda: NOW,
    )

    result = worker.execute(lease)

    assert result.raw_object is None
    assert result.quarantine is not None
    assert result.provider_run.run_outcome.value == "DEGRADED"
    assert task_control.get_task(task.task_id).task.task_state is TaskState.DEGRADED
    with database.engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM raw_object")).scalar_one() == 0
        assert connection.execute(text("SELECT count(*) FROM raw_ingestion_quarantine")).scalar_one() == 1


def test_timeout_rate_limit_and_retry_are_durable(raw_runtime) -> None:
    database, task_control, publisher = raw_runtime
    task = task_control.create_task(_request("trading_calendar"), idempotency_key="raw-timeout")
    lease = task_control.lease_next(worker_id="raw-worker", worker_capabilities=("raw_ingestion",))
    assert lease is not None
    worker = RawIngestionTaskWorker(
        task_control, database, publisher,
        FakeProviderTransport({("a_stock_data", "trading_calendar"): TimeoutError("network timeout")}),
        clock=lambda: NOW,
    )
    with pytest.raises(RawIngestionError) as captured:
        worker.execute(lease)
    assert captured.value.error_code == "RAW_TIMEOUT"
    assert task_control.get_task(task.task_id).task.task_state is TaskState.RETRY_WAIT
    task_control.request_retry(task.task_id)
    retry_lease = task_control.lease_next(worker_id="raw-worker", worker_capabilities=("raw_ingestion",))
    assert retry_lease is not None and retry_lease.attempt.attempt_number == 2

    limiter = ProviderRateLimiter(monotonic=lambda: 100.0)
    limiter.acquire("a_stock_data", "trading_calendar", {"requests_per_minute": 1})
    with pytest.raises(RawIngestionError, match="rate limit") as limited:
        limiter.acquire("a_stock_data", "trading_calendar", {"requests_per_minute": 1})
    assert limited.value.error_code == "RAW_RATE_LIMITED"


def test_lease_lost_prevents_raw_registry_success_and_leaves_controlled_orphan(raw_runtime) -> None:
    database, task_control, publisher = raw_runtime
    task = task_control.create_task(_request("security_master"), idempotency_key="raw-lease-lost")
    lease = task_control.lease_next(worker_id="raw-worker", worker_capabilities=("raw_ingestion",))
    assert lease is not None
    original = task_control.complete_in_session

    def lose_lease(*args, **kwargs):
        raise TaskControlError("TASK_LEASE_LOST", "Task lease is no longer valid.")

    task_control.complete_in_session = lose_lease  # type: ignore[method-assign]
    worker = RawIngestionTaskWorker(
        task_control, database, publisher,
        FakeProviderTransport({("a_stock_data", "security_master"): _response("security_master")}),
        clock=lambda: NOW,
    )
    try:
        with pytest.raises(RawIngestionError) as captured:
            worker.execute(lease)
        assert captured.value.error_code == "RAW_REGISTRY_WRITE_FAILED"
    finally:
        task_control.complete_in_session = original  # type: ignore[method-assign]

    assert task_control.get_task(task.task_id).task.task_state is TaskState.RETRY_WAIT
    with database.engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM raw_object")).scalar_one() == 0
    orphan_roots = list((publisher.resolver.namespace_root() / "raw").rglob("manifest.json"))
    assert len(orphan_roots) == 1


def test_task_requirements_are_idempotent_and_secret_free(raw_runtime) -> None:
    _, task_control, _ = raw_runtime
    request = _request("security_master")
    first = task_control.create_task(request, idempotency_key="raw-idempotency")
    replay = task_control.create_task(request, idempotency_key="raw-idempotency")
    assert replay.task_id == first.task_id
    with pytest.raises(TaskControlError) as captured:
        task_control.create_task(_request("trading_calendar"), idempotency_key="raw-idempotency")
    assert captured.value.error_code == "TASK_IDEMPOTENCY_CONFLICT"


@pytest.mark.parametrize(
    ("observed_fields", "classification", "reason_code"),
    [
        (("entity_key",), "BREAKING_DRIFT", "RAW_SCHEMA_BREAKING_DRIFT"),
        (None, "UNKNOWN_SCHEMA", "RAW_SCHEMA_UNKNOWN"),
    ],
)
def test_breaking_or_unknown_schema_drift_is_quarantined_and_task_fails(
    raw_runtime, observed_fields, classification: str, reason_code: str
) -> None:
    database, task_control, publisher = raw_runtime
    task = task_control.create_task(_request("security_master"), idempotency_key=f"raw-{classification.lower()}")
    lease = task_control.lease_next(worker_id="raw-worker", worker_capabilities=("raw_ingestion",))
    assert lease is not None
    response = replace(_response("security_master"), raw_schema_fields=observed_fields)
    worker = RawIngestionTaskWorker(
        task_control,
        database,
        publisher,
        FakeProviderTransport({("a_stock_data", "security_master"): response}),
        clock=lambda: NOW,
    )

    result = worker.execute(lease)

    assert result.raw_object is None
    assert result.quarantine is not None
    assert result.quarantine.classification.value == classification
    assert result.quarantine.reason_code == reason_code
    assert result.provider_run.run_outcome.value == "FAILED"
    assert task_control.get_task(task.task_id).task.task_state is TaskState.FAILED


def test_cancel_after_fetch_blocks_raw_publication_at_safe_point(raw_runtime) -> None:
    database, task_control, publisher = raw_runtime
    task = task_control.create_task(_request("security_master"), idempotency_key="raw-cancel-after-fetch")
    lease = task_control.lease_next(worker_id="raw-worker", worker_capabilities=("raw_ingestion",))
    assert lease is not None

    class CancelOnFetch:
        def fetch(self, adapter_name, request, *, timeout_seconds):
            task_control.request_cancel(task.task_id, actor_ref="test")
            return _response(request.dataset_id)

    worker = RawIngestionTaskWorker(task_control, database, publisher, CancelOnFetch(), clock=lambda: NOW)
    with pytest.raises(TaskControlError) as captured:
        worker.execute(lease)
    assert captured.value.error_code == "TASK_CANCEL_PENDING"
    assert task_control.get_task(task.task_id).task.task_state is TaskState.CANCELLED
    with database.transaction() as session:
        run = RawIngestionRepository().get_provider_run(session, next(iter(
            session.execute(text("SELECT provider_run_id FROM provider_run")).scalars()
        )))
    assert run is not None and run.run_outcome.value == "CANCELLED"
    assert list((publisher.resolver.namespace_root() / "raw").rglob("manifest.json")) == []


def test_rename_failure_never_creates_raw_registry_record(raw_runtime) -> None:
    database, task_control, publisher = raw_runtime
    task = task_control.create_task(_request("security_master"), idempotency_key="raw-rename-failure")
    lease = task_control.lease_next(worker_id="raw-worker", worker_capabilities=("raw_ingestion",))
    assert lease is not None

    def fail_rename(_source: Path, _target: Path) -> None:
        raise OSError("injected raw atomic rename failure")

    failing_publisher = RawObjectPublisher(publisher.resolver.runtime_root, database.transaction, clock=lambda: NOW, rename=fail_rename)
    worker = RawIngestionTaskWorker(
        task_control,
        database,
        failing_publisher,
        FakeProviderTransport({("a_stock_data", "security_master"): _response("security_master")}),
        clock=lambda: NOW,
    )
    with pytest.raises(RawIngestionError) as captured:
        worker.execute(lease)
    assert captured.value.error_code == "RAW_ATOMIC_PUBLISH_FAILED"
    assert task_control.get_task(task.task_id).task.task_state is TaskState.RETRY_WAIT
    with database.engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM raw_object")).scalar_one() == 0


def test_append_only_target_rejects_a_second_publication(raw_runtime) -> None:
    database, task_control, publisher = raw_runtime
    task_control.create_task(_request("security_master"), idempotency_key="raw-append-only")
    lease = task_control.lease_next(worker_id="raw-worker", worker_capabilities=("raw_ingestion",))
    assert lease is not None
    worker = RawIngestionTaskWorker(
        task_control,
        database,
        publisher,
        FakeProviderTransport({("a_stock_data", "security_master"): _response("security_master")}),
        clock=lambda: NOW,
    )
    result = worker.execute(lease)
    assert result.raw_object is not None
    with pytest.raises(RawIngestionError) as captured:
        publisher.publish_raw(result.raw_object, _response("security_master").content, after_register=lambda _session, _record: None)
    assert captured.value.error_code == "RAW_TARGET_EXISTS"


def test_postgres_rate_limiter_coordinates_fixed_window(raw_runtime) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from src.services.platform.raw_ingestion import PostgresRateLimiter

    database, _, _ = raw_runtime
    limiter_a = PostgresRateLimiter(database.transaction, clock=lambda: NOW)
    limiter_b = PostgresRateLimiter(database.transaction, clock=lambda: NOW)

    def attempt(limiter):
        try:
            limiter.acquire("a_stock_data", "security_master", {"requests_per_minute": 1}, market="CN", frequency="1d")
            return True
        except RawIngestionError as exc:
            assert exc.error_code == "RAW_RATE_LIMITED"
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, (limiter_a, limiter_b)))
    assert sorted(results) == [False, True]
