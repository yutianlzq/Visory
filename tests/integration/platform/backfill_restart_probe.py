"""Separate process used only against the isolated PostgreSQL fixture database."""
from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import runpy
import sys
from types import ModuleType


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
namespace = ModuleType("src.repositories")
namespace.__path__ = [str(ROOT / "src" / "repositories")]
sys.modules["src.repositories"] = namespace

from src.repositories.platform import PostgresDatabase, PostgresSettings
from src.services.platform.backfill import (
    BackfillError, BackfillPipelineCoordinator, BackfillPipelineExecutor, BackfillService,
    BackfillWorker, DeterministicBackfillProvider,
)
from src.services.platform.canonical_normalization import CanonicalNormalizationTaskWorker
from src.services.platform.provider_source_routes import build_fixture_provider_source_route
from src.services.platform.raw_ingestion import RawIngestionTaskWorker, RawObjectPublisher
from src.services.platform.snapshot import SnapshotBuildTaskWorker, SnapshotGateService
from src.services.platform.task_control import TaskControlService


def main():
    inputs = json.load(sys.stdin)
    inputs["settings"]["password_file"] = Path(inputs["settings"]["password_file"])
    database_name = inputs["settings"]["database"]
    if not database_name.startswith("visory_test_"):
        raise ValueError("restart probe requires an isolated test database")
    database = PostgresDatabase.from_settings(PostgresSettings(**inputs["settings"]))
    now = datetime.fromisoformat(inputs["now"])
    cutoff = inputs["cutoff"]
    runtime_root = Path(inputs["runtime_root"])
    control = TaskControlService(database, runtime_root=runtime_root, clock=lambda: now)

    class NoRefetchTransport:
        fixture_only = True

        def fixture_source_route(self, *, adapter_name, adapter_version, request):
            return build_fixture_provider_source_route(
                provider_id=request.provider_id,
                dataset_id=request.dataset_id,
                adapter_name=adapter_name,
                adapter_version=adapter_version,
                actual_upstream=f"fixture.{request.provider_id}",
            )

        def fetch(self, *args, **kwargs):
            raise AssertionError("a published child must be recovered without refetch")

    def lease_child(task_id, task_type):
        lease = control.lease_next(worker_id="restarted-child", worker_capabilities=(task_type,))
        assert lease is None or lease.task.task_id == task_id
        return lease

    executor = BackfillPipelineExecutor(
        BackfillPipelineCoordinator(control), lease_provider=lease_child,
        raw_worker=RawIngestionTaskWorker(
            control, database, RawObjectPublisher(runtime_root, database.transaction),
            NoRefetchTransport(), clock=lambda: now,
        ),
        canonical_worker=CanonicalNormalizationTaskWorker(control, database, runtime_root=runtime_root),
        snapshot_worker=SnapshotBuildTaskWorker(
            control, SnapshotGateService(database, runtime_root=runtime_root),
        ),
    )

    def plan(part, _result, _index):
        return {
            "raw_requirements": {
                "provider_id": "a_stock_data", "dataset_id": part.dataset,
                "dataset_schema_version": "1.0.0", "provider_policy_id": part.provider_policy_id,
                "market": "CN", "request": {"trade_date": part.date_to.isoformat()},
                "timeout_seconds": 5,
            },
            "canonical_requirements": lambda raw: {
                "provider_id": raw.raw_object.provider_id, "dataset_id": part.dataset,
                "dataset_schema_version": "1.0.0", "provider_policy_id": part.provider_policy_id,
                "provider_policy_version": "1.0.0", "mapping_version": inputs.get("mapping_version", "1.0.0"),
                "raw_object_id": raw.raw_object.raw_object_id,
                "provider_run_id": raw.provider_run.provider_run_id,
                "partition_key": part.date_to.isoformat(), "market": "CN",
            },
            "snapshot_requirements": lambda canonical: {
                "trade_date": part.date_to.isoformat(), "cutoff_at": cutoff,
                "provider_policy_id": part.provider_policy_id, "provider_policy_version": "1.0.0",
                "security_master_ref": inputs["security_ref"],
                "calendar_ref": inputs["calendar_ref"],
                "canonical_partition_ids": (
                    inputs["security_ref"], inputs["calendar_ref"],
                    canonical.canonical_partition.canonical_partition_id,
                ),
                "requested_capabilities": ("identity_core", "calendar_core"),
            },
            "partition_rows": None,
            **({
                "supplemental_raw_requirements": {
                    "provider_id": "financial_api", "dataset_id": part.dataset,
                    "dataset_schema_version": "1.0.0", "provider_policy_id": part.provider_policy_id,
                    "market": "CN", "request": {"trade_date": part.date_to.isoformat()},
                    "timeout_seconds": 5,
                },
            } if inputs.get("supplemental_source") else {}),
        }

    try:
        lease = control.lease_next(worker_id="restarted-parent", worker_capabilities=("backfill",), lease_seconds=60)
        assert lease is not None and lease.task.task_id == inputs["task_id"]
        helpers = runpy.run_path(str(Path(__file__).with_name("test_backfill_integration.py")))
        worker = BackfillWorker(
            control, DeterministicBackfillProvider(), pipeline_executor=executor,
            pipeline_plan_factory=plan, checkpoint_writer=helpers["_checkpoint_writer"](runtime_root),
        )
        failure_code = None
        retryable = None
        try:
            result = worker.execute(lease)
            batch_state = result.batch_state.value
        except BackfillError as exc:
            assert inputs.get("expected_rejection") == exc.error_code and exc.retryable is False
            failure_code = exc.error_code
            retryable = exc.retryable
            batch_state = BackfillService(control).get_batch(inputs["batch_id"]).batch_state.value
        print(json.dumps({
            "batch_state": batch_state, "failure_code": failure_code, "retryable": retryable,
            "attempt_number": lease.attempt.attempt_number,
            "projection": BackfillService(control).get_batch(inputs["batch_id"]).model_dump(mode="json"),
        }))
    finally:
        database.close()


if __name__ == "__main__":
    main()
