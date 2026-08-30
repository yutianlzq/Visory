from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import text

from src.artifacts.orphan import ArtifactOrphanSweeper
from src.repositories.platform import ArtifactRepository, PostgresDatabase, upgrade_database
from src.schemas.platform import TaskCreateRequest, TaskState
from src.services.platform.artifact_publisher import ArtifactPublisherService
from src.services.platform.task_control import TaskControlService
from src.workers.platform.artifact_orphan_dry_run import ArtifactOrphanDryRunTaskWorker


NOW = datetime(2026, 8, 30, 13, 0, tzinfo=timezone.utc)


@pytest.fixture
def vertical_runtime(
    isolated_postgres_database: PostgresDatabase,
    tmp_path: Path,
):
    database = isolated_postgres_database
    upgrade_database(database.engine)
    repository = ArtifactRepository()
    task_control = TaskControlService(database, clock=lambda: NOW, runtime_root=tmp_path)
    publisher = ArtifactPublisherService(
        tmp_path,
        repository,
        database.transaction,
        clock=lambda: NOW,
    )
    sweeper = ArtifactOrphanSweeper(tmp_path, repository, database.transaction)
    return database, task_control, publisher, sweeper


def _task_request() -> TaskCreateRequest:
    return TaskCreateRequest(
        task_type="artifact_orphan_dry_run",
        requested_by="owner:vertical",
        request_source="integration_test",
        requirements={"worker_kind": "maintenance"},
    )


def test_orphan_dry_run_vertical_task_atomically_publishes_result(vertical_runtime) -> None:
    database, task_control, publisher, sweeper = vertical_runtime
    task = task_control.create_task(_task_request(), idempotency_key="vertical-success")
    lease = task_control.lease_next(
        worker_id="worker-vertical",
        worker_capabilities=("artifact_orphan_dry_run",),
    )
    assert lease is not None and lease.task.task_id == task.task_id

    result = ArtifactOrphanDryRunTaskWorker(task_control, sweeper, publisher).execute(lease)
    details = task_control.get_task(task.task_id)
    assert details.task.task_state is TaskState.SUCCEEDED
    assert details.task.result_artifact_id == result.artifact_id
    assert details.attempts[-1].attempt_outcome.value == "SUCCEEDED"

    payload = json.loads(publisher.read_content(result.artifact_id))
    assert payload == {
        "candidates": [],
        "deletion_performed": False,
        "estimated_recoverable_bytes": 0,
        "scanned_known_directories": 0,
        "skipped_invalid_manifests": 0,
    }
    with database.engine.connect() as connection:
        row = connection.execute(
            text("SELECT attempt_id, owner_resource_type, owner_resource_id FROM artifact_registry WHERE artifact_id = :artifact_id"),
            {"artifact_id": result.artifact_id},
        ).one()
    assert row.attempt_id == lease.attempt.attempt_id
    assert row.owner_resource_type == "task"
    assert row.owner_resource_id == task.task_id


def test_artifact_registry_or_task_state_failure_never_exposes_half_success(vertical_runtime) -> None:
    database, task_control, publisher, sweeper = vertical_runtime
    task = task_control.create_task(_task_request(), idempotency_key="vertical-failure")
    lease = task_control.lease_next(
        worker_id="worker-failure",
        worker_capabilities=("artifact_orphan_dry_run",),
    )
    assert lease is not None

    original = task_control.complete_with_artifact_in_session

    def fail_state_transaction(*args, **kwargs):
        raise RuntimeError("injected task state transaction failure")

    task_control.complete_with_artifact_in_session = fail_state_transaction  # type: ignore[method-assign]
    try:
        with pytest.raises(Exception) as captured:
            ArtifactOrphanDryRunTaskWorker(task_control, sweeper, publisher).execute(lease)
        assert getattr(captured.value, "error_code", None) == "ARTIFACT_REGISTRY_WRITE_FAILED"
    finally:
        task_control.complete_with_artifact_in_session = original  # type: ignore[method-assign]

    details = task_control.get_task(task.task_id)
    assert details.task.task_state is not TaskState.SUCCEEDED
    assert details.task.result_artifact_id is None
    with database.engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM artifact_registry")).scalar_one() == 0
    orphan_directories = list((publisher.resolver.namespace_root() / "artifacts").glob("type=*/year=*/month=*/artifact_id=*"))
    assert len(orphan_directories) == 1


def test_artifact_rename_failure_keeps_task_nonterminal_and_registry_empty(vertical_runtime) -> None:
    database, task_control, _, sweeper = vertical_runtime
    task = task_control.create_task(_task_request(), idempotency_key="vertical-rename-failure")
    lease = task_control.lease_next(
        worker_id="worker-rename-failure",
        worker_capabilities=("artifact_orphan_dry_run",),
    )
    assert lease is not None

    def fail_rename(source: Path, target: Path) -> None:
        raise OSError("injected atomic rename failure")

    publisher = ArtifactPublisherService(
        Path(task_control.resolver.runtime_root),
        ArtifactRepository(),
        database.transaction,
        clock=lambda: NOW,
        rename=fail_rename,
    )
    with pytest.raises(Exception) as captured:
        ArtifactOrphanDryRunTaskWorker(task_control, sweeper, publisher).execute(lease)
    assert getattr(captured.value, "error_code", None) == "ARTIFACT_RENAME_FAILED"

    details = task_control.get_task(task.task_id)
    assert details.task.task_state is TaskState.RETRY_WAIT
    assert details.task.result_artifact_id is None
    assert details.attempts[-1].failure_code == "TASK_ARTIFACT_PUBLISH_FAILED"
    with database.engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM artifact_registry")).scalar_one() == 0


def test_cancel_race_before_registry_commit_finishes_cancelled_without_visible_artifact(vertical_runtime) -> None:
    database, task_control, publisher, sweeper = vertical_runtime
    task = task_control.create_task(_task_request(), idempotency_key="vertical-cancel-race")
    lease = task_control.lease_next(
        worker_id="worker-cancel-race",
        worker_capabilities=("artifact_orphan_dry_run",),
    )
    assert lease is not None

    original_publish = publisher.publish

    def publish_after_cancel(request, content, **kwargs):
        task_control.request_cancel(task.task_id)
        return original_publish(request, content, **kwargs)

    publisher.publish = publish_after_cancel  # type: ignore[method-assign]
    try:
        with pytest.raises(Exception) as captured:
            ArtifactOrphanDryRunTaskWorker(task_control, sweeper, publisher).execute(lease)
        assert getattr(captured.value, "error_code", None) == "ARTIFACT_REGISTRY_WRITE_FAILED"
    finally:
        publisher.publish = original_publish  # type: ignore[method-assign]

    details = task_control.get_task(task.task_id)
    assert details.task.task_state is TaskState.CANCELLED
    assert details.task.result_artifact_id is None
    assert details.attempts[-1].attempt_outcome.value == "CANCELLED"
    with database.engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM artifact_registry")).scalar_one() == 0
    orphan_directories = list(
        (publisher.resolver.namespace_root() / "artifacts").glob("type=*/year=*/month=*/artifact_id=*")
    )
    assert len(orphan_directories) == 1
