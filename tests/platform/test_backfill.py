from __future__ import annotations

import json

from contextlib import contextmanager
from datetime import date
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.platform.router import router

import pytest

from src.schemas.platform import BackfillBatchRequest, BackfillBatchType, BackfillStage, BackfillStageChainProjection, BackfillStageChainRequest, BackfillStatus, BackfillTaskRequirements, QualityStatus, ResourceType, TaskListQuery, TaskRecord, TaskState
from src.services.platform.backfill import BackfillError, BackfillPipelineCoordinator, BackfillPipelineExecutor, BackfillProviderResult, BackfillService, BackfillStageChainExecutor, BackfillWorker, DeterministicBackfillProvider, DeterministicBackfillPublisher
from src.services.platform.task_control import TaskControlError


def request(**overrides):
    values = dict(batch_id="backfill_019dbd74-2a00-7000-8000-000000000001", batch_type="MONTH", date_from=date(2026, 8, 1), date_to=date(2026, 8, 31), dataset="bar_1d_raw", provider_policy_id="default", stage="PRICE_MONTH", dry_run=True, plan_only=True, requested_by="owner:test")
    values.update(overrides)
    return BackfillBatchRequest.model_validate(values)


def task(req, state=TaskState.QUEUED, failure_code=None):
    requirements = req.requirements if hasattr(req, "requirements") else req.model_dump(mode="python", exclude={"requested_by"})
    batch_id = requirements["batch_id"]
    payload = {"task_id":"task_019dbd74-2a00-7000-8000-000000000002","task_type":"backfill","task_schema_version":"1.0.0","task_state":state,"priority_class":"P5_PREVIEW_AND_MAINTENANCE","priority_value":100,"idempotency_key":"bf-1","task_key":"backfill:bf-1","canonical_request_hash":"sha256:"+"1"*64,"requested_by":"owner:test","request_source":"backfill:batch","input_refs":[{"resource_type":"backfill_batch","resource_id":batch_id}],"requirements":requirements,"max_attempts":3,"created_at":"2026-09-18T00:00:00Z","queued_at":"2026-09-18T00:00:00Z"}
    if failure_code:
        payload["failure_code"] = failure_code
    if state in {TaskState.SUCCEEDED, TaskState.DEGRADED, TaskState.FAILED, TaskState.CANCELLED}:
        payload["terminal_at"] = "2026-09-18T00:01:00Z"
    return TaskRecord.model_validate(payload)


def test_backfill_stage_dependencies_follow_roadmap_order():
    from src.services.platform.backfill import backfill_stage_dependencies

    assert backfill_stage_dependencies(BackfillStage.IDENTITY_CALENDAR) == ()
    assert backfill_stage_dependencies(BackfillStage.PRICE_MONTH) == (BackfillStage.IDENTITY_CALENDAR,)
    assert backfill_stage_dependencies(BackfillStage.LIFECYCLE_NAMES) == (BackfillStage.IDENTITY_CALENDAR, BackfillStage.PRICE_MONTH)
    assert backfill_stage_dependencies(BackfillStage.CORPORATE_ACTION) == (BackfillStage.IDENTITY_CALENDAR, BackfillStage.PRICE_MONTH, BackfillStage.LIFECYCLE_NAMES)
    assert backfill_stage_dependencies(BackfillStage.FINANCIAL_VALUATION) == (BackfillStage.IDENTITY_CALENDAR, BackfillStage.PRICE_MONTH, BackfillStage.LIFECYCLE_NAMES, BackfillStage.CORPORATE_ACTION)
    assert backfill_stage_dependencies(BackfillStage.INDUSTRY_MEMBERS) == (BackfillStage.IDENTITY_CALENDAR, BackfillStage.PRICE_MONTH, BackfillStage.LIFECYCLE_NAMES, BackfillStage.CORPORATE_ACTION, BackfillStage.FINANCIAL_VALUATION)
    assert backfill_stage_dependencies(BackfillStage.NON_CORE_OBSERVATION) == tuple(BackfillStage)[:-1]


_STAGE_DATASETS = {
    BackfillStage.IDENTITY_CALENDAR: "identity_calendar",
    BackfillStage.PRICE_MONTH: "bar_1d_raw",
    BackfillStage.LIFECYCLE_NAMES: "listing_status_history",
    BackfillStage.CORPORATE_ACTION: "corporate_action",
    BackfillStage.FINANCIAL_VALUATION: "financial_statement",
    BackfillStage.INDUSTRY_MEMBERS: "industry_membership",
    BackfillStage.NON_CORE_OBSERVATION: "non_core_observation",
}


def stage_chain_request(**overrides):
    batches = tuple(
        request(
            batch_id=f"backfill_019dbd74-2a00-7000-8000-{index + 101:012x}",
            stage=stage,
            dataset=_STAGE_DATASETS[stage],
            **overrides,
        )
        for index, stage in enumerate(BackfillStage)
    )
    return BackfillStageChainRequest(batches=batches)


def test_backfill_request_accepts_trade_date_shorthand():
    single_day = request(
        trade_date=date(2026, 8, 31),
        date_from=None,
        date_to=None,
    )
    assert single_day.trade_date == date(2026, 8, 31)
    assert single_day.date_from == single_day.trade_date
    assert single_day.date_to == single_day.trade_date

    with pytest.raises(ValueError, match="trade_date must match"):
        request(
            trade_date=date(2026, 8, 30),
            date_from=date(2026, 8, 31),
            date_to=date(2026, 8, 31),
        )


def test_stage_chain_projection_rejects_non_contiguous_partial_chain():
    identity = task(request(stage=BackfillStage.IDENTITY_CALENDAR)).model_copy(
        update={"task_id": "task_019dbd74-2a00-7000-8000-000000000401"}
    )
    lifecycle = task(request(stage=BackfillStage.LIFECYCLE_NAMES)).model_copy(
        update={
            "task_id": "task_019dbd74-2a00-7000-8000-000000000402",
            "requirements": request(
                stage=BackfillStage.LIFECYCLE_NAMES,
                dependency_task_ids=(identity.task_id,),
            ).model_dump(mode="python", exclude={"requested_by"}),
        }
    )

    projections = tuple(
        BackfillService.project(item) for item in (identity, lifecycle)
    )
    with pytest.raises(ValueError, match="contiguous"):
        BackfillStageChainProjection(batches=projections)


def test_stage_chain_contract_requires_exact_roadmap_order_and_shared_scope():
    chain = stage_chain_request()
    assert tuple(batch.stage for batch in chain.batches) == tuple(BackfillStage)

    with pytest.raises(ValueError, match="roadmap order"):
        BackfillStageChainRequest(batches=tuple(reversed(chain.batches)))
    with pytest.raises(ValueError, match="same date range"):
        BackfillStageChainRequest(
            batches=(
                chain.batches[0],
                chain.batches[1].model_copy(update={"date_to": date(2026, 8, 30)}),
                *chain.batches[2:],
            )
        )
    with pytest.raises(ValueError, match="server-managed"):
        BackfillStageChainRequest(
            batches=(
                chain.batches[0],
                chain.batches[1].model_copy(
                    update={"dependency_task_ids": ("task_019dbd74-2a00-7000-8000-000000000099",)}
                ),
                *chain.batches[2:],
            )
        )


class _StageChainTaskControl:
    def __init__(self):
        self.records = {}
        self.keys = {}
        self.created_count = 0

    def create_task(self, task_request, *, idempotency_key, endpoint):
        assert endpoint == "/api/platform/v1/backfills/stage-chain"
        existing_id = self.keys.get(idempotency_key)
        if existing_id is not None:
            return self.records[existing_id]
        self.created_count += 1
        task_id = f"task_019dbd74-2a00-7000-8000-{self.created_count + 200:012x}"
        record = task(task_request).model_copy(
            update={
                "task_id": task_id,
                "idempotency_key": idempotency_key,
                "task_key": f"backfill:{idempotency_key}",
                "input_refs": task_request.input_refs,
            }
        )
        self.records[task_id] = record
        self.keys[idempotency_key] = task_id
        return record

    def get_task(self, task_id):
        return SimpleNamespace(task=self.records[task_id])

    def list_tasks(self, query):
        records = tuple(self.records.values())
        if query.task_type is not None:
            records = tuple(item for item in records if item.task_type == query.task_type)
        if query.resource_id is not None:
            records = tuple(
                item
                for item in records
                if item.task_id == query.resource_id
                or any(ref.resource_id == query.resource_id for ref in item.input_refs)
            )
        return records[:query.limit], None, len(records) > query.limit

    def block_task(self, task_id, *, reason_code, unblock_condition, actor_ref):
        del actor_ref
        record = self.records[task_id].model_copy(
            update={
                "task_state": TaskState.BLOCKED,
                "blocked_reason_code": reason_code,
                "unblock_condition": unblock_condition,
            }
        )
        self.records[task_id] = record
        return record

    def unblock_task(self, task_id, *, actor_ref):
        del actor_ref
        record = self.records[task_id].model_copy(
            update={
                "task_state": TaskState.QUEUED,
                "blocked_reason_code": None,
                "unblock_condition": None,
            }
        )
        self.records[task_id] = record
        return record

    def succeed(self, task_id):
        self.records[task_id] = self.records[task_id].model_copy(
            update={"task_state": TaskState.SUCCEEDED, "terminal_at": "2026-09-18T00:01:00Z"}
        )

    def degrade(self, task_id):
        self.records[task_id] = self.records[task_id].model_copy(
            update={"task_state": TaskState.DEGRADED, "terminal_at": "2026-09-18T00:01:00Z"}
        )


class _StageChainExecutionControl(_StageChainTaskControl):
    def lease_next(self, *, worker_id, worker_capabilities, lease_seconds=60):
        assert worker_capabilities == ("backfill",)
        assert lease_seconds > 0
        for record in self.records.values():
            if record.task_state is TaskState.QUEUED:
                leased = record.model_copy(update={"task_state": TaskState.LEASED})
                self.records[record.task_id] = leased
                return SimpleNamespace(
                    task=leased,
                    attempt=SimpleNamespace(
                        attempt_id=f"attempt-{record.task_id}",
                        attempt_number=1,
                    ),
                    lease_token=f"lease-{worker_id}",
                )
        return None


def test_stage_chain_executor_runs_real_stage_workers_in_order_and_unblocks_one_stage():
    control = _StageChainExecutionControl()
    chain = stage_chain_request(dry_run=False, plan_only=False)
    executed = []

    def worker_factory(lease):
        class Worker:
            def execute(self, current_lease, **kwargs):
                assert current_lease is lease
                assert kwargs == {}
                executed.append(BackfillStage(current_lease.task.requirements["stage"]))
                control.succeed(current_lease.task.task_id)
                return SimpleNamespace(
                    task_id=current_lease.task.task_id,
                    batch_id=current_lease.task.requirements["batch_id"],
                    batch_state=BackfillStatus.COMPLETED,
                    stage=current_lease.task.requirements["stage"],
                )

        return Worker()

    result = BackfillStageChainExecutor(
        control,
        worker_factory=worker_factory,
    ).execute(chain, idempotency_key="backfill-stage-chain-executor-1")

    assert tuple(executed) == tuple(BackfillStage)
    assert result.executed_task_ids == tuple(
        item.task_id for item in result.projection.batches
    )
    assert all(item.batch_state is BackfillStatus.COMPLETED for item in result.projection.batches)
    assert control.created_count == len(BackfillStage)


def test_plan_only_stage_chain_advances_all_seven_stages_without_business_publication():
    control = _StageChainExecutionControl()
    chain = stage_chain_request(dry_run=True, plan_only=True)
    executed = []

    def worker_factory(lease):
        class Worker:
            def execute(self, current_lease, **kwargs):
                assert kwargs == {}
                stage = BackfillStage(current_lease.task.requirements["stage"])
                executed.append(stage)
                control.degrade(current_lease.task.task_id)
                return SimpleNamespace(
                    task_id=current_lease.task.task_id,
                    batch_id=current_lease.task.requirements["batch_id"],
                    batch_state=BackfillStatus.PARTIAL,
                    stage=stage.value,
                    published_refs=(),
                )

        return Worker()

    result = BackfillStageChainExecutor(
        control,
        worker_factory=worker_factory,
    ).execute(chain, idempotency_key="backfill-stage-chain-plan-only")

    assert tuple(executed) == tuple(BackfillStage)
    assert result.executed_task_ids == tuple(
        item.task_id for item in result.projection.batches
    )
    assert all(item.batch_state is BackfillStatus.PARTIAL for item in result.projection.batches)
    assert all(
        not item.provider_run_refs
        and not item.raw_object_refs
        and not item.canonical_partition_refs
        and not item.snapshot_refs
        for item in result.projection.batches
    )


def test_degraded_published_stage_stops_chain_even_when_not_plan_only():
    control = _StageChainExecutionControl()
    chain = stage_chain_request(dry_run=False, plan_only=False)
    executed = []

    def worker_factory(lease):
        class Worker:
            def execute(self, current_lease, **kwargs):
                assert kwargs == {}
                stage = BackfillStage(current_lease.task.requirements["stage"])
                executed.append(stage)
                control.degrade(current_lease.task.task_id)
                return SimpleNamespace(
                    task_id=current_lease.task.task_id,
                    batch_id=current_lease.task.requirements["batch_id"],
                    batch_state=BackfillStatus.PARTIAL,
                    stage=stage.value,
                )

        return Worker()

    result = BackfillStageChainExecutor(
        control,
        worker_factory=worker_factory,
    ).execute(chain, idempotency_key="backfill-stage-chain-degraded-live")

    assert tuple(executed) == (BackfillStage.IDENTITY_CALENDAR,)
    assert result.stopped_task_id == result.projection.batches[0].task_id
    assert result.stopped_state is TaskState.DEGRADED
    assert all(
        item.batch_state is BackfillStatus.PAUSED
        for item in result.projection.batches[1:]
    )


def test_stage_chain_executor_stops_after_failed_stage_and_does_not_run_following_workers():
    control = _StageChainExecutionControl()
    chain = stage_chain_request(dry_run=False, plan_only=False)
    executed = []
    failing_stage = BackfillStage.CORPORATE_ACTION

    def worker_factory(lease):
        class Worker:
            def execute(self, current_lease, **kwargs):
                stage = BackfillStage(current_lease.task.requirements["stage"])
                executed.append(stage)
                if stage is failing_stage:
                    control.records[current_lease.task.task_id] = current_lease.task.model_copy(
                        update={"task_state": TaskState.FAILED, "failure_code": "FIXTURE_FAILED"}
                    )
                    return SimpleNamespace(
                        task_id=current_lease.task.task_id,
                        batch_id=current_lease.task.requirements["batch_id"],
                        batch_state=BackfillStatus.FAILED,
                        stage=stage.value,
                        failure_code="FIXTURE_FAILED",
                    )
                control.succeed(current_lease.task.task_id)
                return SimpleNamespace(
                    task_id=current_lease.task.task_id,
                    batch_id=current_lease.task.requirements["batch_id"],
                    batch_state=BackfillStatus.COMPLETED,
                    stage=stage.value,
                )

        return Worker()

    result = BackfillStageChainExecutor(
        control,
        worker_factory=worker_factory,
    ).execute(chain, idempotency_key="backfill-stage-chain-executor-failure")

    assert tuple(executed) == tuple(BackfillStage)[:4]
    assert result.stopped_task_id == result.projection.batches[3].task_id
    assert result.projection.batches[3].batch_state is BackfillStatus.FAILED
    assert all(
        item.batch_state is BackfillStatus.PAUSED
        for item in result.projection.batches[4:]
    )


def test_create_stage_chain_is_durable_linear_and_idempotently_advances_one_stage():
    control = _StageChainTaskControl()
    service = BackfillService(control)
    chain = stage_chain_request()

    for active_index in range(len(BackfillStage)):
        projection = service.create_stage_chain(chain, idempotency_key="backfill-stage-chain-1")
        assert isinstance(projection, BackfillStageChainProjection)
        assert control.created_count == len(BackfillStage)
        assert tuple(item.stage for item in projection.batches) == tuple(BackfillStage)
        assert all(item.batch_state is BackfillStatus.COMPLETED for item in projection.batches[:active_index])
        assert projection.batches[active_index].batch_state is BackfillStatus.PLANNED
        assert all(item.batch_state is BackfillStatus.PAUSED for item in projection.batches[active_index + 1:])
        for index, item in enumerate(projection.batches):
            expected = () if index == 0 else (projection.batches[index - 1].task_id,)
            assert item.dependency_task_ids == expected
        control.succeed(projection.batches[active_index].task_id)

    completed = service.create_stage_chain(chain, idempotency_key="backfill-stage-chain-1")
    assert all(item.batch_state is BackfillStatus.COMPLETED for item in completed.batches)
    assert control.created_count == len(BackfillStage)


def test_get_stage_chain_traverses_from_any_stage_batch_id():
    control = _StageChainTaskControl()
    service = BackfillService(control)
    chain = stage_chain_request()
    created = service.create_stage_chain(chain, idempotency_key="backfill-stage-chain-query-1")

    observed = service.get_stage_chain(created.batches[3].batch_id)

    assert tuple(item.stage for item in observed.batches) == tuple(BackfillStage)
    assert tuple(item.task_id for item in observed.batches) == tuple(item.task_id for item in created.batches)


def test_get_stage_chain_rejects_ambiguous_successor():
    control = _StageChainTaskControl()
    service = BackfillService(control)
    chain = stage_chain_request()
    created = service.create_stage_chain(chain, idempotency_key="backfill-stage-chain-query-2")
    duplicate = created.batches[1]
    control.records["task_019dbd74-2a00-7000-8000-000000000999"] = control.records[duplicate.task_id].model_copy(
        update={
            "task_id": "task_019dbd74-2a00-7000-8000-000000000999",
            "requirements": {
                **control.records[duplicate.task_id].requirements,
                "batch_id": "backfill_019dbd74-2a00-7000-8000-000000000999",
            },
        }
    )

    with pytest.raises(BackfillError, match="ambiguous successors"):
        service.get_stage_chain(created.batches[0].batch_id)


@pytest.mark.parametrize("stage", list(BackfillStage))
def test_deterministic_one_month_pilot_accepts_each_backfill_stage(stage):
    req = request(stage=stage, dry_run=False, plan_only=False)
    result = BackfillWorker(
        FakeWorkerControl(),
        DeterministicBackfillProvider(),
        publisher=DeterministicBackfillPublisher(),
        checkpoint_writer=lambda **kw: _storage_ref(kw["payload"]),
    ).execute(_lease_for(req))
    assert result.batch_state is BackfillStatus.COMPLETED


def test_month_and_year_boundaries():
    assert request().batch_type is BackfillBatchType.MONTH
    with pytest.raises(ValueError): request(date_to=date(2026, 9, 1))
    year = request(batch_type=BackfillBatchType.YEAR, date_from=date(2025,1,1), date_to=date(2025,12,31))
    assert year.batch_type is BackfillBatchType.YEAR
    assert DeterministicBackfillProvider().run(year.model_copy(update={"dry_run": True, "plan_only": True})).skipped_range == (date(2025,1,1), date(2025,12,31))


def test_create_batch_uses_existing_task_plane_and_dry_run_is_visible():
    captured = {}
    class Tasks:
        def create_task(self, request, **kwargs):
            captured["request"] = request
            captured["kwargs"] = kwargs
            return task(request)
    prior_snapshot = "ds_019dbd74-2a00-7000-8000-000000000010"
    projection = BackfillService(Tasks()).create_batch(
        request(supersedes_id=prior_snapshot), idempotency_key="bf-1"
    )
    assert projection.batch_state is BackfillStatus.PLANNED
    assert projection.supersedes_id == prior_snapshot
    assert captured["request"].task_type == "backfill"
    assert captured["request"].requirements["dry_run"] is True
    assert captured["request"].requirements["supersedes_id"] == prior_snapshot
    assert captured["kwargs"]["idempotency_key"] == "bf-1"


def test_projection_exposes_provider_policy_and_priority_inputs():
    projection = BackfillService.project(
        task(request(provider_policy_id="historical-primary", priority=42))
    )

    assert projection.provider_policy_id == "historical-primary"
    assert projection.priority == 42

def test_create_batch_blocks_until_stage_dependencies_succeed_and_records_task_refs():
    dependency = task(request(stage=BackfillStage.IDENTITY_CALENDAR), TaskState.RUNNING)

    class Tasks:
        def __init__(self):
            self.created = None
            self.blocked = None

        def get_task(self, task_id):
            assert task_id == dependency.task_id
            return SimpleNamespace(task=dependency)

        def create_task(self, request, **kwargs):
            self.created = request
            return task(request)

        def block_task(self, task_id, **kwargs):
            self.blocked = (task_id, kwargs)
            return task(dependency_request, TaskState.QUEUED).model_copy(update={
                "task_state": TaskState.BLOCKED,
                "blocked_reason_code": kwargs["reason_code"],
                "unblock_condition": kwargs["unblock_condition"],
            })

    service = BackfillService(Tasks())
    dependency_request = request(dependency_task_ids=(dependency.task_id,), dry_run=True, plan_only=True)
    tasks = service.task_control_service
    projection = service.create_batch(dependency_request, idempotency_key="bf-dependent")

    assert projection.batch_state is BackfillStatus.PAUSED
    assert projection.dependency_task_ids == (dependency.task_id,)
    assert projection.blocked_reason_code == "BACKFILL_STAGE_DEPENDENCY"
    assert dependency.task_id in projection.unblock_condition
    assert tasks.created.input_refs[1].resource_type is ResourceType.TASK
    assert tasks.created.input_refs[1].resource_id == dependency.task_id
    assert tasks.blocked[1]["reason_code"] == "BACKFILL_STAGE_DEPENDENCY"
    assert dependency.task_id in tasks.blocked[1]["unblock_condition"]


def test_create_batch_uses_atomic_task_plane_block_for_dependency():
    dependency = task(request(stage=BackfillStage.IDENTITY_CALENDAR), TaskState.RUNNING)

    class Tasks:
        def __init__(self):
            self.atomic = None

        def get_task(self, task_id):
            assert task_id == dependency.task_id
            return SimpleNamespace(task=dependency)

        def create_task(self, request, **kwargs):
            raise AssertionError("dependency task must be created blocked in one control-plane transaction")

        def create_blocked_task(self, request, **kwargs):
            self.atomic = (request, kwargs)
            record = task(request, TaskState.QUEUED).model_copy(
                update={
                    "task_state": TaskState.BLOCKED,
                    "blocked_reason_code": kwargs["reason_code"],
                    "unblock_condition": kwargs["unblock_condition"],
                }
            )
            return record

    tasks = Tasks()
    projection = BackfillService(tasks).create_batch(
        request(
            dependency_task_ids=(dependency.task_id,),
            dry_run=True,
            plan_only=True,
        ),
        idempotency_key="bf-atomic-dependent",
    )

    assert tasks.atomic is not None
    assert projection.batch_state is BackfillStatus.PAUSED
    assert tasks.atomic[1]["reason_code"] == "BACKFILL_STAGE_DEPENDENCY"
    assert dependency.task_id in tasks.atomic[1]["unblock_condition"]


def test_backfill_public_contract_rejects_empty_dataset():
    with pytest.raises(ValueError, match="dataset"):
        request(dataset="")

def test_backfill_dependency_ids_reject_wrong_resource_and_duplicates():
    with pytest.raises(ValueError, match="dependency_task_ids"):
        request(dependency_task_ids=("raw_019dbd74-2a00-7000-8000-000000000001",))
    with pytest.raises(ValueError, match="cannot contain duplicates"):
        request(dependency_task_ids=("task_019dbd74-2a00-7000-8000-000000000002",) * 2)


def test_backfill_request_exposes_correction_lineage_without_mutating_prior_snapshot():
    prior_snapshot = "ds_019dbd74-2a00-7000-8000-000000000010"
    correction = request(supersedes_id=prior_snapshot)
    assert correction.supersedes_id == prior_snapshot
    with pytest.raises(ValueError, match="supersedes_id"):
        request(supersedes_id="task_019dbd74-2a00-7000-8000-000000000002")


def test_state_projection_preserves_cancelled_terminal_state():
    projection = BackfillService.project(task(request(), TaskState.CANCELLED))

    assert projection.batch_state.value == "CANCELLED"

def test_state_projection_preserves_failure_and_quarantine():
    req = request().model_dump(mode="python", exclude={"requested_by"})
    req["quality_events"] = ("QUARANTINE_IDENTITY_CONFLICT",)
    record = task(request(), TaskState.FAILED, failure_code="PROVIDER_UNAVAILABLE")
    record = record.model_copy(update={"requirements": req, "terminal_at":"2026-09-18T00:01:00Z"})
    projection = BackfillService.project(record)
    assert projection.batch_state is BackfillStatus.QUARANTINED
    assert projection.quality_events == ("QUARANTINE_IDENTITY_CONFLICT",)




class _Tx:
    def __enter__(self): return self
    def __exit__(self, *args): return False


class FakeWorkerControl:
    def __init__(self):
        self.database = self
        self.calls = []
    def transaction(self): return _Tx()
    def start_attempt(self, *args): self.calls.append(("start", args))
    def get_task(self, task_id): return SimpleNamespace(task=SimpleNamespace(cancel_requested_at=None))
    def save_checkpoint(self, *args, **kwargs): self.calls.append(("checkpoint", kwargs))
    def validate_checkpoint(self, *args, **kwargs): self.calls.append(("validate_checkpoint", kwargs)); return None
    def update_requirements_in_session(self, *args, **kwargs): self.calls.append(("requirements", kwargs))
    def complete_in_session(self, *args, **kwargs): self.calls.append(("complete", kwargs))
    def record_failure_in_session(self, *args, **kwargs): self.calls.append(("failure", kwargs))
    def record_failure(self, *args, **kwargs): self.calls.append(("failure", kwargs))
    def acknowledge_cancel(self, *args): self.calls.append(("cancel", args))


def _lease_for(req, state=TaskState.QUEUED):
    record = task(req, state)
    return SimpleNamespace(task=record, attempt=SimpleNamespace(attempt_id="attempt_019dbd74-2a00-7000-8000-000000000003"), lease_token="lease-token")


def _storage_ref(payload):
    from src.artifacts.hashing import compute_bytes_hash
    return {"storage_backend":"local_fs", "storage_namespace":"app", "relative_path":"checkpoints/test.json", "content_hash":compute_bytes_hash(payload), "media_type":"application/json", "size_bytes":len(payload)}


def test_worker_cancellation_safe_points_do_not_publish_next_partition():
    class CancelAfterCheckpoint(FakeWorkerControl):
        def __init__(self):
            super().__init__()
            self.cancel_requested = False

        def save_checkpoint(self, *args, **kwargs):
            super().save_checkpoint(*args, **kwargs)
            self.cancel_requested = True

        def get_task(self, task_id):
            return SimpleNamespace(task=SimpleNamespace(cancel_requested_at="2026-09-18T00:01:00Z" if self.cancel_requested else None))

    control = CancelAfterCheckpoint()
    publisher = DeterministicBackfillPublisher()
    req = request(batch_type="YEAR", date_from=date(2025, 1, 1), date_to=date(2025, 12, 31), dry_run=False, plan_only=False)
    result = BackfillWorker(
        control,
        DeterministicBackfillProvider(),
        publisher=publisher,
        checkpoint_writer=lambda **kw: _storage_ref(kw["payload"]),
    ).execute(_lease_for(req))

    assert result.batch_state is BackfillStatus.CANCELLED
    assert result.failure_code == "BACKFILL_CANCELLED"
    assert len(publisher._published) == 1
    assert "2025-01-01:2025-01-31" in next(iter(publisher._published))
    assert any(kind == "cancel" for kind, _ in control.calls)


def test_worker_dry_run_checkpoints_without_publishing():
    control = FakeWorkerControl()
    provider = DeterministicBackfillProvider()
    worker = BackfillWorker(control, provider, checkpoint_writer=lambda **kw: _storage_ref(kw["payload"]))
    result = worker.execute(_lease_for(request()))
    assert result.batch_state is BackfillStatus.PARTIAL
    assert any(kind == "checkpoint" for kind, _ in control.calls)
    assert not any(kind == "complete" and data.get("degraded") is False for kind, data in control.calls)


@pytest.mark.parametrize(
    ("req", "provider", "expected_state"),
    [
        (request(), DeterministicBackfillProvider(), BackfillStatus.PARTIAL),
        (
            request(dry_run=False, plan_only=False),
            DeterministicBackfillProvider(unavailable=True),
            BackfillStatus.UNAVAILABLE,
        ),
    ],
)
def test_nonpublishing_batch_checkpoint_does_not_claim_completed_range(req, provider, expected_state):
    payloads = []
    result = BackfillWorker(
        FakeWorkerControl(),
        provider,
        checkpoint_writer=lambda **kw: (
            payloads.append(json.loads(kw["payload"])) or _storage_ref(kw["payload"])
        ),
    ).execute(_lease_for(req))

    assert result.batch_state is expected_state
    assert payloads[-1]["completed_range"] is None
    assert payloads[-1]["skipped_range"] == [req.date_from.isoformat(), req.date_to.isoformat()]
    assert payloads[-1]["published_refs"] == []


def test_worker_failed_provider_records_failure_and_can_be_retried():
    control = FakeWorkerControl()
    provider = DeterministicBackfillProvider(fail_on_stage=BackfillStage.PRICE_MONTH)
    req = request(dry_run=False, plan_only=False)
    worker = BackfillWorker(control, provider, checkpoint_writer=lambda **kw: _storage_ref(kw["payload"]))
    result = worker.execute(_lease_for(req))
    assert result.batch_state is BackfillStatus.FAILED
    assert any(kind == "failure" for kind, _ in control.calls)
    assert provider.calls == ["PRICE_MONTH"]


def test_backfill_api_requires_idempotency_and_returns_enveloped_task():
    app = FastAPI()
    app.include_router(router, prefix="/api")
    class Service:
        def create_batch(self, request, *, idempotency_key):
            return BackfillService.project(task(request_task(request)))
    def request_task(body):
        return task(body)
    app.state.backfill_service = Service()
    payload = {"batch_id":"backfill_019dbd74-2a00-7000-8000-000000000001","batch_type":"MONTH","date_from":"2026-08-01","date_to":"2026-08-31","dataset":"bar_1d_raw","provider_policy_id":"default","stage":"PRICE_MONTH","dry_run":True,"plan_only":True,"supersedes_id":"ds_019dbd74-2a00-7000-8000-000000000010","requested_by":"owner:test"}
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post("/api/platform/v1/backfills", headers={"Idempotency-Key":"bf-1"}, json=payload)
    assert response.status_code == 200
    assert response.json()["data"]["batch_state"] == "PLANNED"
    assert response.json()["data"]["supersedes_id"] == payload["supersedes_id"]



def test_backfill_stage_chain_api_requires_idempotency_and_returns_enveloped_chain():
    from api.middlewares.error_handler import add_error_handlers

    app = FastAPI()
    app.include_router(router, prefix="/api")
    add_error_handlers(app)
    service = BackfillService(_StageChainTaskControl())
    app.state.backfill_service = service
    payload = stage_chain_request().model_dump(mode="json")

    with TestClient(app, raise_server_exceptions=False) as client:
        missing = client.post("/api/platform/v1/backfills/stage-chain", json=payload)
        created = client.post(
            "/api/platform/v1/backfills/stage-chain",
            headers={"Idempotency-Key": "backfill-stage-chain-api-1"},
            json=payload,
        )

    assert missing.status_code == 400
    assert missing.json()["error"]["code"] == "TASK_IDEMPOTENCY_KEY_REQUIRED"
    assert created.status_code == 200
    batches = created.json()["data"]["batches"]
    assert [batch["stage"] for batch in batches] == [stage.value for stage in BackfillStage]
    assert batches[0]["batch_state"] == "PLANNED"
    assert all(batch["batch_state"] == "PAUSED" for batch in batches[1:])


def test_worker_missing_publisher_fails_closed():
    from src.services.platform.backfill import BackfillError
    control = FakeWorkerControl()
    worker = BackfillWorker(control, DeterministicBackfillProvider(), checkpoint_writer=lambda **kw: _storage_ref(kw['payload']))
    with pytest.raises(BackfillError, match='publication is unavailable'):
        worker.execute(_lease_for(request(dry_run=False, plan_only=False)))
    assert any(kind == 'failure' for kind, _ in control.calls)
    assert not any(kind == 'complete' for kind, _ in control.calls)


def test_worker_quarantine_never_calls_publisher():
    from unittest.mock import Mock
    control = FakeWorkerControl()
    publisher = Mock()
    publisher.publish.return_value = ()
    worker = BackfillWorker(control, DeterministicBackfillProvider(quarantine=True), publisher=publisher, checkpoint_writer=lambda **kw: _storage_ref(kw['payload']))
    result = worker.execute(_lease_for(request(dry_run=False, plan_only=False)))
    assert result.batch_state is BackfillStatus.QUARANTINED
    publisher.publish.assert_not_called()


def test_task_create_rejects_invalid_backfill_requirements():
    from src.schemas.platform import TaskCreateRequest
    with pytest.raises(ValueError):
        TaskCreateRequest(task_type='backfill', requested_by='owner:test', requirements={})
from unittest.mock import Mock


def test_deterministic_provider_records_resource_and_difference_summary():
    req = request(dry_run=False, plan_only=False)
    result = DeterministicBackfillProvider().run(req)
    assert result.differences_summary == "DETERMINISTIC_FIXTURE_NO_DIFFERENCES"
    assert result.resource_usage == {"provider_requests": 1.0, "estimated_rows": 1.0}

    plan = DeterministicBackfillProvider().run(request(dry_run=True, plan_only=True))
    assert plan.differences_summary == "PLAN_ONLY_NO_BUSINESS_PUBLICATION"
    assert plan.resource_usage == {"planned_partitions": 1.0}


def test_year_pilot_expands_to_twelve_month_partitions():
    from src.services.platform.backfill import plan_backfill_ranges
    year = request(batch_type="YEAR", date_from=date(2025, 1, 1), date_to=date(2025, 12, 31), dry_run=True, plan_only=True)
    ranges = plan_backfill_ranges(year)
    assert len(ranges) == 12
    assert ranges[0] == (date(2025, 1, 1), date(2025, 1, 31))
    assert ranges[-1] == (date(2025, 12, 1), date(2025, 12, 31))


def test_year_worker_resume_skips_completed_partitions_and_keeps_publish_keys_unique(tmp_path):
    control = FakeWorkerControl()
    provider = DeterministicBackfillProvider()
    publisher = Mock()
    publisher.publish.side_effect = lambda req, result, *, idempotency_key: (idempotency_key,)
    req = request(batch_type="YEAR", date_from=date(2025, 1, 1), date_to=date(2025, 12, 31), dry_run=False, plan_only=False)
    resume = {"batch_id": req.batch_id, "task_id": "task_019dbd74-2a00-7000-8000-000000000002", "handler_version": BackfillWorker.HANDLER_VERSION, "stage": req.stage.value, "date_from": req.date_from.isoformat(), "date_to": req.date_to.isoformat(), "dataset": req.dataset, "input_hash": BackfillWorker._checkpoint_input_hash(req.model_copy(update={"date_from": req.date_from, "date_to": req.date_to})), "completed_partitions": [0, 1]}
    from src.artifacts.namespace import StorageNamespaceResolver
    from src.schemas.platform import StorageRef
    content = BackfillWorker._serialize_checkpoint_payload(resume)
    ref = StorageRef.model_validate(_storage_ref(content))
    control.resolver = StorageNamespaceResolver(tmp_path)
    path = control.resolver.resolve(ref)
    path.parent.mkdir(parents=True)
    path.write_bytes(content)
    control.validate_checkpoint = lambda *args, **kwargs: SimpleNamespace(task_id=resume["task_id"], checkpoint_hash=ref.content_hash, storage_ref=ref)
    result = BackfillWorker(control, provider, publisher=publisher, checkpoint_writer=lambda **kw: _storage_ref(kw["payload"])).execute(_lease_for(req), resume_checkpoint_id="checkpoint_019dbd74-2a00-7000-8000-000000000004", resume_token="resume-token")
    assert result.batch_state is BackfillStatus.COMPLETED
    assert len(provider.calls) == 10
    keys = [call.kwargs["idempotency_key"] for call in publisher.publish.call_args_list]
    assert len(keys) == len(set(keys)) == 10
    assert any(kind == "checkpoint" for kind, _ in control.calls)


def test_resume_payload_without_durable_checkpoint_is_rejected():
    control = FakeWorkerControl()
    req = request(batch_type="YEAR", date_from=date(2025, 1, 1), date_to=date(2025, 12, 31))
    worker = BackfillWorker(control, DeterministicBackfillProvider(), checkpoint_writer=lambda **kw: _storage_ref(kw["payload"]))
    with pytest.raises(Exception, match="checkpoint cannot be resumed"):
        worker.execute(_lease_for(req), resume_payload={"completed_partitions": [0]})


def test_checkpoint_rejects_invalid_difference_summary():
    from src.services.platform.backfill import plan_backfill_ranges
    req = request(batch_type="YEAR", date_from=date(2025, 1, 1), date_to=date(2025, 12, 31))
    with pytest.raises(ValueError, match="differences_summary is invalid"):
        BackfillWorker._validate_checkpoint_accumulators(
            {"differences_summary": {"raw": "payload"}, "completed_partitions": []},
            req,
            plan_backfill_ranges(req),
            set(),
        )


def test_provider_fallback_is_explicit_and_unavailable_is_not_completed():
    control = FakeWorkerControl()
    fallback = DeterministicBackfillProvider(fallback=True)
    fallback_result = fallback.run(request(dry_run=False, plan_only=False))
    assert fallback_result.provider_fallback is True
    assert fallback_result.quality_events == ("PROVIDER_PRIMARY_ATTEMPT_RECORDED", "PROVIDER_FALLBACK_EXPLICIT")
    assert len(fallback_result.provider_run_refs) == 2
    assert len(fallback_result.raw_object_refs) == 2
    assert len(fallback_result.canonical_partition_refs) == 2
    assert len(set(fallback_result.provider_run_refs)) == 2
    assert len(set(fallback_result.raw_object_refs)) == 2
    assert len(set(fallback_result.canonical_partition_refs)) == 2

    unavailable = DeterministicBackfillProvider(unavailable=True)
    worker = BackfillWorker(control, unavailable, checkpoint_writer=lambda **kw: _storage_ref(kw["payload"]))
    result = worker.execute(_lease_for(request(dry_run=False, plan_only=False)))
    assert result.batch_state is BackfillStatus.UNAVAILABLE
    assert not any(kind == "complete" and data.get("degraded") is False for kind, data in control.calls)
from datetime import datetime, timezone


def test_service_list_batches_reuses_operations_task_query():
    captured = {}
    class Tasks:
        def list_tasks(self, query):
            captured["query"] = query
            return (task(request()),), "next-cursor", True
    batches, cursor, has_more = BackfillService(Tasks()).list_batches(TaskListQuery(limit=10))
    assert captured["query"].task_type == "backfill"
    assert len(batches) == 1
    assert cursor == "next-cursor"
    assert has_more is True


def test_service_get_stage_chain_sorts_by_roadmap_order_and_reuses_task_query():
    identity_task_id = "task_019dbd74-2a00-7000-8000-000000000301"
    price_task_id = "task_019dbd74-2a00-7000-8000-000000000302"
    identity = task(
        request(stage=BackfillStage.IDENTITY_CALENDAR),
    ).model_copy(update={"task_id": identity_task_id})
    price = task(
        request(stage=BackfillStage.PRICE_MONTH, dependency_task_ids=(identity_task_id,)),
    ).model_copy(update={"task_id": price_task_id})
    captured = {}

    class Tasks:
        def list_tasks(self, query):
            captured["query"] = query
            return (price, identity), None, False

    projection = BackfillService(Tasks()).get_stage_chain(identity.requirements["batch_id"])

    assert captured["query"].resource_id == identity.requirements["batch_id"]
    assert captured["query"].task_type == "backfill"
    assert captured["query"].limit == 7
    assert [item.stage for item in projection.batches] == [
        BackfillStage.IDENTITY_CALENDAR,
        BackfillStage.PRICE_MONTH,
    ]
    assert projection.batches[1].dependency_task_ids == (identity_task_id,)


def test_service_get_batch_fails_closed_for_duplicate_task_records():
    first = task(request()).model_copy(
        update={"task_id": "task_019dbd74-2a00-7000-8000-000000000305"}
    )
    second = first.model_copy(
        update={"task_id": "task_019dbd74-2a00-7000-8000-000000000306"}
    )

    class DuplicateTasks:
        def list_tasks(self, query):
            assert query.resource_id == first.requirements["batch_id"]
            assert query.task_type == "backfill"
            assert query.limit == 2
            return (first, second), None, False

    with pytest.raises(BackfillError, match="multiple task records"):
        BackfillService(DuplicateTasks()).get_batch(first.requirements["batch_id"])


def test_service_get_stage_chain_fails_closed_for_missing_or_duplicate_stages():
    class MissingTasks:
        def list_tasks(self, query):
            del query
            return (), None, False

    with pytest.raises(BackfillError, match="was not found"):
        BackfillService(MissingTasks()).get_stage_chain(
            "backfill_019dbd74-2a00-7000-8000-000000000301"
        )

    identity_task_id = "task_019dbd74-2a00-7000-8000-000000000303"
    first = task(request(stage=BackfillStage.IDENTITY_CALENDAR)).model_copy(
        update={"task_id": identity_task_id}
    )
    second = task(request(stage=BackfillStage.IDENTITY_CALENDAR)).model_copy(
        update={"task_id": "task_019dbd74-2a00-7000-8000-000000000304"}
    )

    class DuplicateTasks:
        def list_tasks(self, query):
            del query
            return (first, second), None, False

    with pytest.raises(BackfillError, match="duplicate stages"):
        BackfillService(DuplicateTasks()).get_stage_chain(
            first.requirements["batch_id"]
        )


def test_backfill_list_api_returns_list_envelope():
    app = FastAPI()
    app.include_router(router, prefix="/api")
    class Service:
        def list_batches(self, query):
            return (BackfillService.project(task(request())),), None, False
    app.state.backfill_service = Service()
    with TestClient(app) as client:
        response = client.get("/api/platform/v1/backfills?limit=10")
    assert response.status_code == 200
    assert response.json()["data"][0]["batch_state"] == "PLANNED"
    assert response.json()["page"]["has_more"] is False



def test_deterministic_publisher_deduplicates_same_idempotency_key():
    publisher = DeterministicBackfillPublisher()
    req = request(dry_run=False, plan_only=False)
    result = DeterministicBackfillProvider().run(req)
    first = publisher.publish(req.model_copy(), result, idempotency_key="same-key")
    second = publisher.publish(req.model_copy(), result, idempotency_key="same-key")
    assert first == second
    assert first[0].startswith("cpart_")


def test_deterministic_publication_retains_full_provider_raw_canonical_snapshot_lineage():
    req = request(dry_run=False, plan_only=False)
    provider = DeterministicBackfillProvider(fallback=True)
    publisher = DeterministicBackfillPublisher()
    result = provider.run(req)
    publisher.publish(req, result, idempotency_key="full-lineage")

    publication = publisher.get_publication("full-lineage")
    assert publication.provider_run_refs == result.provider_run_refs
    assert publication.raw_object_refs == result.raw_object_refs
    assert publication.canonical_partition_refs == result.canonical_partition_refs
    assert len(publication.canonical_partition_refs) == 2
    assert publication.snapshot_id.startswith("ds_")


def test_worker_records_deterministic_snapshot_reference_in_checkpoint_without_mutating_requirements():
    control = FakeWorkerControl()
    payloads = []

    def writer(**kwargs):
        payloads.append(json.loads(kwargs["payload"]))
        return _storage_ref(kwargs["payload"])

    req = request(dry_run=False, plan_only=False)
    publisher = DeterministicBackfillPublisher()
    result = BackfillWorker(
        control,
        DeterministicBackfillProvider(),
        publisher=publisher,
        checkpoint_writer=writer,
    ).execute(_lease_for(req))

    assert result.batch_state is BackfillStatus.COMPLETED
    expected = publisher.get_publication("backfill:" + req.batch_id + ":" + req.stage.value + ":0:2026-08-01:2026-08-31").snapshot_id
    assert payloads[-1]["snapshot_refs"] == [expected]
    assert not any(kind == "requirements" for kind, _ in control.calls)


def test_deterministic_publisher_keeps_correction_snapshot_append_only():
    publisher = DeterministicBackfillPublisher()
    base = request(dry_run=False, plan_only=False)
    base_requirements = BackfillTaskRequirements(**base.model_dump(exclude={"requested_by"}))
    result = DeterministicBackfillProvider().run(base_requirements)
    publisher.publish(base_requirements, result, idempotency_key="snapshot-initial")
    initial = publisher.get_publication("snapshot-initial")

    correction = base_requirements.model_copy(update={"supersedes_id": initial.snapshot_id})
    publisher.publish(correction, result, idempotency_key="snapshot-correction")
    corrected = publisher.get_publication("snapshot-correction")

    assert corrected.snapshot_id != initial.snapshot_id
    assert corrected.supersedes_id == initial.snapshot_id
    assert publisher.get_publication("snapshot-initial") == initial


def test_deterministic_publisher_rejects_incomplete_lineage():
    publisher = DeterministicBackfillPublisher()
    req = request(dry_run=False, plan_only=False)
    incomplete = BackfillProviderResult(
        completed_range=(req.date_from, req.date_to),
        canonical_partition_refs=("cpart_00000000-0000-7000-8000-000000000099",),
    )
    with pytest.raises(BackfillError, match="lineage is incomplete"):
        publisher.publish(req, incomplete, idempotency_key="incomplete-lineage")


def test_deterministic_publisher_rejects_idempotency_key_reuse_for_different_input():
    publisher = DeterministicBackfillPublisher()
    req = request(dry_run=False, plan_only=False)
    result = DeterministicBackfillProvider().run(req)
    publisher.publish(req, result, idempotency_key="conflicting-key")
    changed = req.model_copy(update={"dataset": "security_master"})
    changed_result = DeterministicBackfillProvider().run(changed)
    with pytest.raises(BackfillError, match="idempotency key"):
        publisher.publish(changed, changed_result, idempotency_key="conflicting-key")


def test_deterministic_fixture_lineage_is_stable_across_provider_and_publisher_instances():
    req = request()
    first_result = DeterministicBackfillProvider().run(req)
    second_result = DeterministicBackfillProvider().run(req)
    assert first_result.provider_run_refs == second_result.provider_run_refs
    assert first_result.raw_object_refs == second_result.raw_object_refs
    assert first_result.canonical_partition_refs == second_result.canonical_partition_refs

    first_published = DeterministicBackfillPublisher().publish(req, first_result, idempotency_key="restart-safe-key")
    second_published = DeterministicBackfillPublisher().publish(req, second_result, idempotency_key="restart-safe-key")
    assert first_published == second_published


def test_missing_checkpoint_record_cannot_authorize_resume():
    from src.services.platform.backfill import BackfillError, plan_backfill_ranges
    req = request()
    worker = BackfillWorker(FakeWorkerControl(), DeterministicBackfillProvider())
    with pytest.raises(BackfillError):
        worker._validated_resume_partitions(
            _lease_for(req), req, plan_backfill_ranges(req), None,
            resume_checkpoint_id='checkpoint_019dbd74-2a00-7000-8000-000000000004',
            resume_token='resume-token',
        )


def test_checkpoint_writer_includes_dataset_and_resource_usage():
    import json
    from src.services.platform.backfill import BackfillProviderResult
    payloads = []
    def writer(**kwargs):
        payloads.append(json.loads(kwargs['payload']))
        return _storage_ref(kwargs['payload'])
    req = request()
    worker = BackfillWorker(FakeWorkerControl(), DeterministicBackfillProvider(), checkpoint_writer=writer)
    worker._write_checkpoint(_lease_for(req), req, BackfillProviderResult(resource_usage={'rows': 3}), completed_partitions={0})
    assert payloads[0]['dataset'] == req.dataset
    assert payloads[0]['resource_usage'] == {'rows': 3}


@pytest.mark.parametrize('change', [
    {'provider_policy_id': 'different'}, {'stage': 'CORPORATE_ACTION'},
    {'dry_run': False}, {'plan_only': False}, {'batch_type': 'YEAR'},
])
def test_checkpoint_input_hash_binds_execution_policy(change):
    req = request()
    assert BackfillWorker._checkpoint_input_hash(req) != BackfillWorker._checkpoint_input_hash(request(**change))


@pytest.mark.parametrize('mutation', ['payload', 'file', 'task', 'boolean', 'hole'])
def test_resume_rejects_tampered_or_invalid_checkpoint(tmp_path, mutation):
    from src.artifacts.namespace import StorageNamespaceResolver
    from src.schemas.platform import StorageRef
    from src.services.platform.backfill import BackfillError, plan_backfill_ranges
    req = request(batch_type='YEAR', date_from=date(2025, 1, 1), date_to=date(2025, 12, 31))
    lease = _lease_for(req)
    payload = {
        'batch_id': req.batch_id, 'task_id': lease.task.task_id,
        'handler_version': BackfillWorker.HANDLER_VERSION, 'stage': req.stage.value,
        'date_from': req.date_from.isoformat(), 'date_to': req.date_to.isoformat(),
        'dataset': req.dataset, 'input_hash': BackfillWorker._checkpoint_input_hash(req),
        'completed_partitions': [0],
    }
    if mutation == 'boolean':
        payload['completed_partitions'] = [False]
    if mutation == 'hole':
        payload['completed_partitions'] = [1]
    content = BackfillWorker._serialize_checkpoint_payload(payload)
    ref = StorageRef.model_validate(_storage_ref(content))
    control = FakeWorkerControl()
    control.resolver = StorageNamespaceResolver(tmp_path)
    path = control.resolver.resolve(ref)
    path.parent.mkdir(parents=True)
    path.write_bytes(content if mutation != 'file' else content + b' ')
    record = SimpleNamespace(task_id=lease.task.task_id if mutation != 'task' else 'another-task', checkpoint_hash=ref.content_hash, storage_ref=ref)
    control.validate_checkpoint = lambda *args, **kwargs: record
    supplied = {**payload, 'completed_partitions': [0, 1]} if mutation == 'payload' else None
    worker = BackfillWorker(control, DeterministicBackfillProvider())
    with pytest.raises(BackfillError, match='checkpoint cannot be resumed'):
        worker._validated_resume_partitions(lease, req, plan_backfill_ranges(req), supplied, resume_checkpoint_id='checkpoint_019dbd74-2a00-7000-8000-000000000004', resume_token='resume-token')


def test_failure_checkpoint_preserves_prior_partition_lineage_and_usage():
    class FailOnSecondPartition:
        def __init__(self):
            self.calls = 0

        def run(self, requirements, *, resume_payload=None):
            self.calls += 1
            if self.calls == 2:
                return BackfillProviderResult(
                    failed_range=(requirements.date_from, requirements.date_to),
                    quality_events=("PROVIDER_UNAVAILABLE",),
                    resource_usage={"requests": 2},
                    retryable=True,
                )
            return BackfillProviderResult(
                completed_range=(requirements.date_from, requirements.date_to),
                resource_usage={"requests": 1},
                provider_run_refs=("prun_00000000-0000-7000-8000-000000000001",),
                raw_object_refs=("raw_00000000-0000-7000-8000-000000000001",),
                canonical_partition_refs=("cpart_00000000-0000-7000-8000-000000000001",),
            )

    control = FakeWorkerControl()
    payloads = []

    def writer(**kwargs):
        payloads.append(json.loads(kwargs["payload"]))
        return _storage_ref(kwargs["payload"])

    req = request(batch_type="YEAR", date_from=date(2025, 1, 1), date_to=date(2025, 12, 31), dry_run=False, plan_only=False)
    publisher = Mock()
    publisher.publish.return_value = ()
    result = BackfillWorker(control, FailOnSecondPartition(), publisher=publisher, checkpoint_writer=writer).execute(_lease_for(req))

    assert result.batch_state is BackfillStatus.FAILED
    failure = payloads[-1]
    assert failure["completed_partitions"] == [0]
    assert failure["provider_run_refs"] == ["prun_00000000-0000-7000-8000-000000000001"]
    assert failure["raw_object_refs"] == ["raw_00000000-0000-7000-8000-000000000001"]
    assert failure["canonical_partition_refs"] == ["cpart_00000000-0000-7000-8000-000000000001"]
    assert failure["resource_usage"] == {"requests": 3}
    assert failure["failed_range"] == ["2025-02-01", "2025-02-28"]







class _ChildTaskControl:
    def __init__(self):
        self.requests = []
        self.calls = []
        self.records = {}

    def get_task(self, task_id):
        return SimpleNamespace(task=self.records[task_id])

    def succeed(self, task_id):
        self.records[task_id] = self.records[task_id].model_copy(update={"task_state": TaskState.SUCCEEDED})

    def assert_attempt_publishable_in_session(self, _session, **_kwargs):
        return None

    def create_task(self, request, **kwargs):
        self.requests.append((request, kwargs))
        self.calls.append(kwargs["idempotency_key"])
        from src.schemas.platform import ResourceType, generate_resource_id, TaskState, PriorityClass
        record = task_record_for_child(request, generate_resource_id(ResourceType.TASK, timestamp_ms=0, random_bits=len(self.requests)))
        record = record.model_copy(update={"idempotency_key": kwargs["idempotency_key"]})
        self.records[record.task_id] = record
        return record


def task_record_for_child(request, task_id):
    from src.schemas.platform import TaskState, PriorityClass
    return TaskRecord.model_validate({
        "task_id": task_id, "task_type": request.task_type, "task_schema_version": "1.0.0",
        "task_state": TaskState.QUEUED, "priority_class": PriorityClass.P5_PREVIEW_AND_MAINTENANCE,
        "priority_value": request.priority_value, "idempotency_key": "child", "task_key": "child",
        "canonical_request_hash": "sha256:" + "1" * 64, "requested_by": request.requested_by,
        "request_source": request.request_source, "input_refs": request.input_refs,
        "requirements": request.requirements, "max_attempts": 3,
        "created_at": "2026-09-18T00:00:00Z", "queued_at": "2026-09-18T00:00:00Z",
    })


def test_pipeline_coordinator_submits_existing_child_task_chain_in_order():
    from src.schemas.platform import CanonicalNormalizationTaskRequirements, RawIngestionTaskRequirements, SnapshotBuildTaskRequirements, ResourceType, generate_resource_id
    control = _ChildTaskControl()
    prior_snapshot = "ds_019dbd74-2a00-7000-8000-000000000010"
    req = request(dry_run=False, plan_only=False, supersedes_id=prior_snapshot)
    typed_req = BackfillTaskRequirements(**req.model_dump(exclude={"requested_by"}))
    raw_id = generate_resource_id(ResourceType.RAW_OBJECT, timestamp_ms=0, random_bits=11)
    run_id = generate_resource_id(ResourceType.PROVIDER_RUN, timestamp_ms=0, random_bits=12)
    canonical_id = generate_resource_id(ResourceType.CANONICAL_PARTITION, timestamp_ms=0, random_bits=13)
    coordinator = BackfillPipelineCoordinator(control)
    raw = coordinator.submit_partition(
        parent_task=task(req), requirements=typed_req, partition_index=0, requested_by="owner:test",
        raw_requirements=RawIngestionTaskRequirements(
            provider_id="fixture", dataset_id=req.dataset, dataset_schema_version="1.0.0",
            provider_policy_id=req.provider_policy_id, request={"date_from": req.date_from.isoformat(), "date_to": req.date_to.isoformat()},
        ).model_dump(mode="json"),
    )
    control.succeed(raw.raw_task_id)
    canonical = coordinator.submit_canonical(
        parent_task=task(req), raw_task=raw.raw_task_id, requirements=typed_req, partition_index=0, requested_by="owner:test",
        canonical_requirements=CanonicalNormalizationTaskRequirements(
            provider_id="fixture", dataset_id=req.dataset, dataset_schema_version="1.0.0",
            raw_object_id=raw_id, provider_run_id=run_id, provider_policy_id=req.provider_policy_id,
            provider_policy_version="1.0.0", mapping_version="1.0.0", partition_key="2026-08",
        ).model_dump(mode="json"),
    )
    control.succeed(canonical.canonical_task_id)
    snapshot = coordinator.submit_snapshot(
        parent_task=task(req), raw_task=raw.raw_task_id, canonical_task=canonical.canonical_task_id or "",
        requirements=typed_req, partition_index=0, requested_by="owner:test",
        snapshot_requirements=SnapshotBuildTaskRequirements(
            trade_date=req.date_from, cutoff_at="2026-09-18T00:00:00Z", provider_policy_id=req.provider_policy_id,
            provider_policy_version="1.0.0", security_master_ref=canonical_id, calendar_ref=canonical_id,
            canonical_partition_ids=(canonical_id,), requested_capabilities=("bars",),
        ).model_dump(mode="json"),
    )
    assert snapshot.snapshot_task_id
    assert [request.task_type for request, _ in control.requests] == ["raw_ingestion", "canonical_normalization", "data_snapshot_build"]
    assert control.calls == [
        f"backfill:{req.batch_id}:0:raw",
        f"backfill:{req.batch_id}:0:canonical",
        f"backfill:{req.batch_id}:0:snapshot",
    ]
    assert control.requests[1][0].input_refs[-1].resource_id == raw.raw_task_id
    assert control.requests[2][0].input_refs[-1].resource_id == canonical.canonical_task_id
    assert control.requests[2][0].requirements["correction_of_snapshot_id"] == prior_snapshot


def _pipeline_gate_fixture():
    from src.schemas.platform import RawIngestionTaskRequirements, CanonicalNormalizationTaskRequirements
    control = _ChildTaskControl()
    req = request(dry_run=False, plan_only=False)
    requirements = BackfillTaskRequirements(**req.model_dump(exclude={"requested_by"}))
    coordinator = BackfillPipelineCoordinator(control)
    raw = coordinator.submit_partition(
        parent_task=task(req), requirements=requirements, partition_index=0, requested_by="owner:test",
        raw_requirements=RawIngestionTaskRequirements(
            provider_id="fixture", dataset_id=req.dataset, dataset_schema_version="1.0.0",
            provider_policy_id=req.provider_policy_id,
        ).model_dump(mode="json"),
    )
    payload = CanonicalNormalizationTaskRequirements(
        provider_id="fixture", dataset_id=req.dataset, dataset_schema_version="1.0.0",
        raw_object_id="raw_00000000-0000-7000-8000-000000000001",
        provider_run_id="prun_00000000-0000-7000-8000-000000000001",
        provider_policy_id=req.provider_policy_id, provider_policy_version="1.0.0",
        mapping_version="1.0.0", partition_key="2026-08",
    ).model_dump(mode="json")
    args = dict(parent_task=task(req), requirements=requirements, partition_index=0,
                requested_by="owner:test", raw_task=raw.raw_task_id, canonical_requirements=payload)
    return coordinator, control, raw.raw_task_id, args


@pytest.mark.parametrize("state", [state for state in TaskState if state is not TaskState.SUCCEEDED])
def test_pipeline_rejects_unsuccessful_raw_even_with_stale_success_argument(state):
    coordinator, control, raw_id, args = _pipeline_gate_fixture()
    stale = control.records[raw_id].model_copy(update={"task_state": TaskState.SUCCEEDED})
    control.records[raw_id] = control.records[raw_id].model_copy(update={"task_state": state})
    args["raw_task"] = stale
    with pytest.raises(BackfillError) as exc:
        coordinator.submit_canonical(**args)
    assert exc.value.error_code == "BACKFILL_DEPENDENCY_NOT_READY"
    assert len(control.requests) == 1


@pytest.mark.parametrize("mutation", [
    {"task_type": "data_snapshot_build"}, {"input_refs": ()},
    {"requested_by": "owner:other"}, {"idempotency_key": "another-partition"},
])
def test_pipeline_rejects_unrelated_successful_predecessor(mutation):
    coordinator, control, raw_id, args = _pipeline_gate_fixture()
    control.succeed(raw_id)
    control.records[raw_id] = control.records[raw_id].model_copy(update=mutation)
    with pytest.raises(BackfillError) as exc:
        coordinator.submit_canonical(**args)
    assert exc.value.error_code == "BACKFILL_DEPENDENCY_MISMATCH"
    assert len(control.requests) == 1


@pytest.mark.parametrize("mode", ["dry_run", "plan_only"])
def test_pipeline_plan_does_not_enqueue_business_tasks(mode):
    coordinator, control, _, args = _pipeline_gate_fixture()
    req = args["requirements"].model_copy(update={mode: True})
    with pytest.raises(BackfillError) as exc:
        coordinator.submit_partition(
            parent_task=args["parent_task"], requirements=req, partition_index=0,
            requested_by="owner:test", raw_requirements=control.requests[0][0].requirements,
        )
    assert exc.value.error_code == "BACKFILL_PLAN_ONLY"
    assert len(control.requests) == 1


@pytest.mark.parametrize("state", list(TaskState))
def test_pipeline_snapshot_requires_successful_canonical(state):
    from src.schemas.platform import SnapshotBuildTaskRequirements
    coordinator, control, raw_id, args = _pipeline_gate_fixture()
    control.succeed(raw_id)
    canonical = coordinator.submit_canonical(**args)
    canonical_id = canonical.canonical_task_id
    control.records[canonical_id] = control.records[canonical_id].model_copy(update={"task_state": state})
    partition_id = "cpart_00000000-0000-7000-8000-000000000001"
    payload = SnapshotBuildTaskRequirements(
        trade_date="2026-08-31", cutoff_at="2026-09-18T00:00:00Z",
        provider_policy_id="default", provider_policy_version="1.0.0",
        security_master_ref=partition_id, calendar_ref=partition_id,
        canonical_partition_ids=(partition_id,), requested_capabilities=("bars",),
    ).model_dump(mode="json")
    def submit():
        return coordinator.submit_snapshot(
            parent_task=args["parent_task"], raw_task=raw_id, canonical_task=canonical_id,
            requirements=args["requirements"], partition_index=0, requested_by="owner:test",
            snapshot_requirements=payload,
        )
    if state is TaskState.SUCCEEDED:
        assert submit().snapshot_task_id
        assert len(control.requests) == 3
    else:
        with pytest.raises(BackfillError) as exc:
            submit()
        assert exc.value.error_code == "BACKFILL_DEPENDENCY_NOT_READY"
        assert len(control.requests) == 2


@pytest.mark.parametrize(("batch_supersedes", "snapshot_supersedes"), [
    (None, "ds_019dbd74-2a00-7000-8000-000000000010"),
    ("ds_019dbd74-2a00-7000-8000-000000000010", "ds_019dbd74-2a00-7000-8000-000000000011"),
])
def test_pipeline_rejects_snapshot_correction_lineage_not_declared_by_batch(batch_supersedes, snapshot_supersedes):
    from src.schemas.platform import SnapshotBuildTaskRequirements

    coordinator, control, raw_id, args = _pipeline_gate_fixture()
    control.succeed(raw_id)
    canonical = coordinator.submit_canonical(**args)
    canonical_id = canonical.canonical_task_id
    control.succeed(canonical_id)
    partition_id = "cpart_00000000-0000-7000-8000-000000000001"
    payload = SnapshotBuildTaskRequirements(
        trade_date="2026-08-31", cutoff_at="2026-09-18T00:00:00Z",
        provider_policy_id="default", provider_policy_version="1.0.0",
        security_master_ref=partition_id, calendar_ref=partition_id,
        canonical_partition_ids=(partition_id,), requested_capabilities=("bars",),
        correction_of_snapshot_id=snapshot_supersedes,
    ).model_dump(mode="json")
    requirements = args["requirements"].model_copy(update={"supersedes_id": batch_supersedes})

    with pytest.raises(BackfillError) as exc:
        coordinator.submit_snapshot(
            parent_task=args["parent_task"], raw_task=raw_id, canonical_task=canonical_id,
            requirements=requirements, partition_index=0, requested_by="owner:test",
            snapshot_requirements=payload,
        )

    assert exc.value.error_code == "BACKFILL_CORRECTION_LINEAGE_MISMATCH"
    assert len(control.requests) == 2


class _PipelineWorker:
    def __init__(self, result, error=None):
        self.result = result
        self.error = error
        self.leases = []

    def execute(self, lease, **kwargs):
        self.leases.append((lease, kwargs))
        if self.error is not None:
            raise self.error
        return self.result


@pytest.mark.parametrize("reused_types", [(), ("raw_ingestion",), ("raw_ingestion", "canonical_normalization"), ("raw_ingestion", "canonical_normalization", "data_snapshot_build")])
def test_pipeline_executor_runs_existing_workers_in_raw_canonical_snapshot_order(reused_types):
    from src.schemas.platform import CanonicalNormalizationTaskResult, CanonicalQualityReport, RawIngestionPublishResult, SnapshotBuildTaskResult
    # The executor contract is intentionally tested with worker doubles; the
    # concrete workers remain the existing production implementations.
    control = _ChildTaskControl()
    req = request(dry_run=False, plan_only=False)
    typed_req = BackfillTaskRequirements(**req.model_dump(exclude={"requested_by"}))
    coordinator = BackfillPipelineCoordinator(control)
    parent = task(req)
    raw_result = SimpleNamespace(raw_object=SimpleNamespace(raw_object_id="raw_00000000-0000-7000-8000-000000000001"), provider_run=SimpleNamespace(provider_run_id="prun_00000000-0000-7000-8000-000000000001"))
    canonical_result = SimpleNamespace(canonical_partition=SimpleNamespace(canonical_partition_id="cpart_00000000-0000-7000-8000-000000000001"), published=True)
    snapshot_result = SimpleNamespace(snapshot=SimpleNamespace(snapshot_id="ds_00000000-0000-7000-8000-000000000001"), published=True)
    workers = [_PipelineWorker(raw_result), _PipelineWorker(canonical_result), _PipelineWorker(snapshot_result)]
    leases = {}
    loaded = []
    results = dict(zip(("raw_ingestion", "canonical_normalization", "data_snapshot_build"), (raw_result, canonical_result, snapshot_result)))

    def load_result(task_id, task_type):
        assert control.records[task_id].task_state is TaskState.SUCCEEDED
        loaded.append(task_type)
        return results[task_type]

    def lease_for(task_id, task_type):
        record = control.records[task_id]
        control.succeed(task_id)
        if task_type in reused_types:
            return None
        lease = SimpleNamespace(task=record, attempt=SimpleNamespace(attempt_id=f"attempt_{len(leases)+1:08d}-0000-7000-8000-000000000000"), lease_token="x" * 32)
        leases[task_id] = lease
        return lease
    executor = BackfillPipelineExecutor(coordinator, lease_provider=lease_for, raw_worker=workers[0], canonical_worker=workers[1], snapshot_worker=workers[2], result_loader=load_result)
    result = executor.execute_partition(
        parent_task=parent, requirements=typed_req, partition_index=0, requested_by="owner:test",
        raw_requirements={"provider_id":"fixture", "dataset_id":req.dataset, "dataset_schema_version":"1.0.0", "provider_policy_id":req.provider_policy_id},
        canonical_requirements=lambda raw: {"provider_id":"fixture", "dataset_id":req.dataset, "dataset_schema_version":"1.0.0", "raw_object_id":raw.raw_object.raw_object_id, "provider_run_id":raw.provider_run.provider_run_id, "provider_policy_id":req.provider_policy_id, "provider_policy_version":"1.0.0", "mapping_version":"1.0.0", "partition_key":"2026-08"},
        snapshot_requirements=lambda canonical: {"trade_date":"2026-08-31", "cutoff_at":"2026-09-18T00:00:00Z", "provider_policy_id":req.provider_policy_id, "provider_policy_version":"1.0.0", "security_master_ref":canonical.canonical_partition.canonical_partition_id, "calendar_ref":canonical.canonical_partition.canonical_partition_id, "canonical_partition_ids":(canonical.canonical_partition.canonical_partition_id,), "requested_capabilities":("bars",)},
        partition_rows={"bars": [{"asset_id":"asset_1"}]},
    )
    assert result == ("raw_00000000-0000-7000-8000-000000000001", "cpart_00000000-0000-7000-8000-000000000001", "ds_00000000-0000-7000-8000-000000000001")
    assert executor.last_provider_run_refs == ("prun_00000000-0000-7000-8000-000000000001",)
    assert [item[0].task.task_type for worker in workers for item in worker.leases] == [kind for kind in results if kind not in reused_types]
    assert loaded == list(reused_types)
    if "data_snapshot_build" not in reused_types:
        assert workers[2].leases[0][1]["partition_rows"] == {"bars": [{"asset_id":"asset_1"}]}


def test_pipeline_executor_fences_each_child_publication_with_parent_lease():
    class FenceControl(_ChildTaskControl):
        def __init__(self):
            super().__init__()
            self.fence_calls = []

        def assert_attempt_publishable_in_session(
            self, session, *, attempt_id, lease_token, expected_task_id, expected_task_type
        ):
            self.fence_calls.append(
                (session, attempt_id, lease_token, expected_task_id, expected_task_type)
            )

    class FenceWorker(_PipelineWorker):
        def execute(self, lease, **kwargs):
            self.leases.append((lease, kwargs))
            kwargs["publication_guard"](f"session:{lease.task.task_type}")
            return self.result

    control = FenceControl()
    req = request(dry_run=False, plan_only=False)
    typed_req = BackfillTaskRequirements(**req.model_dump(exclude={"requested_by"}))
    parent = task(req).model_copy(update={"task_state": TaskState.RUNNING})
    parent_lease = SimpleNamespace(
        task=parent,
        attempt=SimpleNamespace(attempt_id="attempt_00000000-0000-7000-8000-000000000099"),
        lease_token="p" * 32,
    )
    raw_result = SimpleNamespace(
        raw_object=SimpleNamespace(raw_object_id="raw_00000000-0000-7000-8000-000000000091"),
        provider_run=SimpleNamespace(provider_run_id="prun_00000000-0000-7000-8000-000000000091"),
    )
    canonical_result = SimpleNamespace(
        canonical_partition=SimpleNamespace(
            canonical_partition_id="cpart_00000000-0000-7000-8000-000000000091"
        ),
        published=True,
    )
    snapshot_result = SimpleNamespace(
        snapshot=SimpleNamespace(snapshot_id="ds_00000000-0000-7000-8000-000000000091"),
        published=True,
    )
    workers = [
        FenceWorker(raw_result),
        FenceWorker(canonical_result),
        FenceWorker(snapshot_result),
    ]

    def lease_for(task_id, task_type):
        control.succeed(task_id)
        return SimpleNamespace(
            task=control.records[task_id],
            attempt=SimpleNamespace(
                attempt_id=f"attempt_{len(control.records):08d}-0000-7000-8000-000000000000"
            ),
            lease_token="x" * 32,
        )

    executor = BackfillPipelineExecutor(
        BackfillPipelineCoordinator(control),
        lease_provider=lease_for,
        raw_worker=workers[0],
        canonical_worker=workers[1],
        snapshot_worker=workers[2],
    )
    executor.execute_partition(
        parent_task=parent,
        parent_lease=parent_lease,
        requirements=typed_req,
        partition_index=0,
        requested_by="owner:test",
        raw_requirements={
            "provider_id": "fixture",
            "dataset_id": req.dataset,
            "dataset_schema_version": "1.0.0",
            "provider_policy_id": req.provider_policy_id,
        },
        canonical_requirements=lambda raw: {
            "provider_id": "fixture",
            "dataset_id": req.dataset,
            "dataset_schema_version": "1.0.0",
            "raw_object_id": raw.raw_object.raw_object_id,
            "provider_run_id": raw.provider_run.provider_run_id,
            "provider_policy_id": req.provider_policy_id,
            "provider_policy_version": "1.0.0",
            "mapping_version": "1.0.0",
            "partition_key": "2026-08",
        },
        snapshot_requirements=lambda canonical: {
            "trade_date": "2026-08-31",
            "cutoff_at": "2026-09-22T00:00:00Z",
            "provider_policy_id": req.provider_policy_id,
            "provider_policy_version": "1.0.0",
            "security_master_ref": canonical.canonical_partition.canonical_partition_id,
            "calendar_ref": canonical.canonical_partition.canonical_partition_id,
            "canonical_partition_ids": (
                canonical.canonical_partition.canonical_partition_id,
            ),
            "requested_capabilities": ("bars",),
        },
        partition_rows={"bars": [{"asset_id": "asset_1"}]},
    )

    assert [call[0] for call in control.fence_calls] == [
        "session:raw_ingestion",
        "session:canonical_normalization",
        "session:data_snapshot_build",
    ]
    assert all(call[1:] == (
        parent_lease.attempt.attempt_id,
        parent_lease.lease_token,
        parent.task_id,
        "backfill",
    ) for call in control.fence_calls)


def test_pipeline_executor_cancels_running_child_when_parent_publication_fence_rejects():
    class CancelControl(_ChildTaskControl):
        def __init__(self):
            super().__init__()
            self.cancel_calls = []

        def assert_attempt_publishable_in_session(self, _session, **_kwargs):
            raise TaskControlError(
                "TASK_CANCEL_PENDING",
                "Cancelled task cannot publish a result.",
            )

        def request_cancel(self, task_id, **kwargs):
            self.cancel_calls.append(("request", task_id, kwargs))
            current = self.records[task_id]
            updated = current.model_copy(
                update={"cancel_requested_at": "2026-09-22T00:00:00Z"}
            )
            self.records[task_id] = updated
            return updated

        def acknowledge_cancel(self, attempt_id, lease_token):
            self.cancel_calls.append(("ack", attempt_id, lease_token))
            task_id = next(
                task_id
                for task_id, record in self.records.items()
                if record.active_attempt_id == attempt_id
            )
            updated = self.records[task_id].model_copy(
                update={
                    "task_state": TaskState.CANCELLED,
                    "terminal_at": "2026-09-22T00:00:01Z",
                }
            )
            self.records[task_id] = updated
            return updated

    class GuardWorker(_PipelineWorker):
        def execute(self, lease, **kwargs):
            self.leases.append((lease, kwargs))
            kwargs["publication_guard"](object())
            return self.result

    control = CancelControl()
    req = request(dry_run=False, plan_only=False)
    typed_req = BackfillTaskRequirements(**req.model_dump(exclude={"requested_by"}))
    parent = task(req).model_copy(update={"task_state": TaskState.RUNNING})
    parent_lease = SimpleNamespace(
        task=parent,
        attempt=SimpleNamespace(
            attempt_id="attempt_00000000-0000-7000-8000-000000000109"
        ),
        lease_token="p" * 32,
    )
    worker = GuardWorker(None)

    def lease_for(task_id, _task_type):
        record = control.records[task_id].model_copy(
            update={
                "task_state": TaskState.RUNNING,
                "active_attempt_id": "attempt_00000000-0000-7000-8000-000000000110",
            }
        )
        control.records[task_id] = record
        return SimpleNamespace(
            task=record,
            attempt=SimpleNamespace(attempt_id=record.active_attempt_id),
            lease_token="x" * 32,
        )

    executor = BackfillPipelineExecutor(
        BackfillPipelineCoordinator(control),
        lease_provider=lease_for,
        raw_worker=worker,
        canonical_worker=worker,
        snapshot_worker=worker,
    )
    with pytest.raises(TaskControlError, match="TASK_CANCEL_PENDING"):
        executor.execute_partition(
            parent_task=parent,
            parent_lease=parent_lease,
            requirements=typed_req,
            partition_index=0,
            requested_by="owner:test",
            raw_requirements={
                "provider_id": "fixture",
                "dataset_id": req.dataset,
                "dataset_schema_version": "1.0.0",
                "provider_policy_id": req.provider_policy_id,
            },
            canonical_requirements={},
            snapshot_requirements={},
            partition_rows={},
        )

    child_task_id = worker.leases[0][0].task.task_id
    assert control.records[child_task_id].task_state is TaskState.CANCELLED
    assert [call[0] for call in control.cancel_calls] == ["request", "ack"]


def test_backfill_worker_acknowledges_parent_cancel_rejected_by_child_publication_fence():
    class ParentControl(FakeWorkerControl):
        def __init__(self):
            super().__init__()
            self.cancel_requested = False

        def get_task(self, task_id):
            return SimpleNamespace(
                task=SimpleNamespace(
                    cancel_requested_at="2026-09-22T00:00:00Z"
                    if self.cancel_requested
                    else None
                )
            )

    control = ParentControl()

    class CancellingExecutor:
        last_provider_run_refs = ()

        def execute_partition(self, **kwargs):
            control.cancel_requested = True
            raise TaskControlError(
                "TASK_CANCEL_PENDING",
                "Cancelled task cannot publish a result.",
            )

    req = request(dry_run=False, plan_only=False)
    result = BackfillWorker(
        control,
        DeterministicBackfillProvider(),
        checkpoint_writer=lambda **kwargs: _storage_ref(kwargs["payload"]),
        pipeline_executor=CancellingExecutor(),
        pipeline_plan_factory=lambda *_args: {
            "raw_requirements": {},
            "canonical_requirements": {},
            "snapshot_requirements": {},
            "partition_rows": {},
        },
    ).execute(_lease_for(req))

    assert result.batch_state is BackfillStatus.CANCELLED
    assert result.failure_code == "BACKFILL_CANCELLED"
    assert any(kind == "cancel" for kind, _args in control.calls)
    assert not any(kind == "failure" for kind, _args in control.calls)


def test_pipeline_executor_stops_before_snapshot_when_canonical_worker_fails():
    control = _ChildTaskControl()
    req = request(dry_run=False, plan_only=False)
    typed_req = BackfillTaskRequirements(**req.model_dump(exclude={"requested_by"}))
    coordinator = BackfillPipelineCoordinator(control)
    parent = task(req)
    raw_result = SimpleNamespace(raw_object=SimpleNamespace(raw_object_id="raw_00000000-0000-7000-8000-000000000031"), provider_run=SimpleNamespace(provider_run_id="prun_00000000-0000-7000-8000-000000000032"))
    workers = [
        _PipelineWorker(raw_result),
        _PipelineWorker(None, error=BackfillError("CANONICAL_FAILED", "canonical failed")),
        _PipelineWorker(SimpleNamespace(snapshot=SimpleNamespace(snapshot_id="unused"), published=True)),
    ]
    leases = {}

    def lease_for(task_id, task_type):
        record = control.records[task_id]
        control.succeed(task_id)
        lease = SimpleNamespace(task=record, attempt=SimpleNamespace(attempt_id=f"attempt_{len(leases)+1:08d}-0000-7000-8000-000000000000"), lease_token="x" * 32)
        leases[task_id] = lease
        return lease

    executor = BackfillPipelineExecutor(coordinator, lease_provider=lease_for, raw_worker=workers[0], canonical_worker=workers[1], snapshot_worker=workers[2])
    with pytest.raises(BackfillError, match="canonical failed"):
        executor.execute_partition(
            parent_task=parent, requirements=typed_req, partition_index=0, requested_by="owner:test",
            raw_requirements={"provider_id": "fixture", "dataset_id": req.dataset, "dataset_schema_version": "1.0.0", "provider_policy_id": req.provider_policy_id},
            canonical_requirements={
                "provider_id": "fixture", "dataset_id": req.dataset, "dataset_schema_version": "1.0.0",
                "raw_object_id": raw_result.raw_object.raw_object_id, "provider_run_id": raw_result.provider_run.provider_run_id,
                "provider_policy_id": req.provider_policy_id, "provider_policy_version": "1.0.0",
                "mapping_version": "1.0.0", "partition_key": "2026-08",
            },
            snapshot_requirements={}, partition_rows={},
        )
    assert [item[0].task.task_type for worker in workers for item in worker.leases] == ["raw_ingestion", "canonical_normalization"]


class _BackfillExecutorSpy:
    def __init__(self):
        self.calls = []
        self.last_provider_run_refs = ("prun_00000000-0000-7000-8000-000000000024",)
    def execute_partition(self, **kwargs):
        self.calls.append(kwargs)
        return (
            "raw_00000000-0000-7000-8000-000000000021",
            "cpart_00000000-0000-7000-8000-000000000022",
            "ds_00000000-0000-7000-8000-000000000023",
        )


def test_backfill_worker_can_delegate_business_publication_to_existing_pipeline_executor():
    control = FakeWorkerControl()
    payloads = []
    executor = _BackfillExecutorSpy()
    req = request(dry_run=False, plan_only=False)
    worker = BackfillWorker(
        control, DeterministicBackfillProvider(),
        publisher=Mock(),
        checkpoint_writer=lambda **kwargs: (payloads.append(json.loads(kwargs["payload"])) or _storage_ref(kwargs["payload"])),
        pipeline_executor=executor,
        pipeline_plan_factory=lambda part, result, index: {"raw_requirements": {"provider_id":"fixture"}, "canonical_requirements": {}, "snapshot_requirements": {}, "partition_rows": {}},
    )
    result = worker.execute(_lease_for(req))
    assert result.batch_state is BackfillStatus.COMPLETED
    assert len(executor.calls) == 1
    assert executor.calls[0]["partition_index"] == 0
    assert payloads[-1]["provider_run_refs"] == ["prun_00000000-0000-7000-8000-000000000024"]
    assert payloads[-1]["raw_object_refs"] == ["raw_00000000-0000-7000-8000-000000000021"]
    assert payloads[-1]["canonical_partition_refs"] == ["cpart_00000000-0000-7000-8000-000000000022"]
    assert payloads[-1]["snapshot_refs"] == ["ds_00000000-0000-7000-8000-000000000023"]


@pytest.mark.parametrize("task_type", ["raw_ingestion", "canonical_normalization", "data_snapshot_build"])
@pytest.mark.parametrize("loader_present", [False, True])
def test_pipeline_recovery_missing_result_never_reexecutes_worker(task_type, loader_present):
    worker = _PipelineWorker(None)
    loaded = []

    def load_result(task_id, kind):
        loaded.append((task_id, kind))
        return None

    control = _ChildTaskControl()
    control.records["child-task"] = SimpleNamespace(task_id="child-task", task_type=task_type, task_state=TaskState.SUCCEEDED)
    executor = BackfillPipelineExecutor(
        BackfillPipelineCoordinator(control),
        lease_provider=lambda *_: None,
        raw_worker=worker, canonical_worker=worker, snapshot_worker=worker,
        result_loader=load_result if loader_present else None,
    )
    with pytest.raises(BackfillError) as exc:
        executor._execute_or_reuse("child-task", task_type, worker)
    assert exc.value.error_code == "BACKFILL_CHILD_RESULT_UNAVAILABLE"
    assert exc.value.retryable is True
    assert worker.leases == []
    assert loaded == ([("child-task", task_type)] if loader_present else [])


@pytest.mark.parametrize("wrong_field", ["task_id", "task_type"])
def test_pipeline_recovery_invalid_lease_does_not_fall_back_to_loader(wrong_field):
    worker = _PipelineWorker(None)
    loaded = []
    values = dict(task_id="child-task", task_type="raw_ingestion")
    values[wrong_field] = "wrong"
    executor = BackfillPipelineExecutor(
        BackfillPipelineCoordinator(_ChildTaskControl()),
        lease_provider=lambda *_: SimpleNamespace(task=SimpleNamespace(**values)),
        raw_worker=worker, canonical_worker=worker, snapshot_worker=worker,
        result_loader=lambda *args: loaded.append(args),
    )
    with pytest.raises(BackfillError) as exc:
        executor._execute_or_reuse("child-task", "raw_ingestion", worker)
    assert exc.value.error_code == "BACKFILL_CHILD_LEASE_INVALID"
    assert worker.leases == []
    assert loaded == []


@pytest.mark.parametrize("task_type", ["raw_ingestion", "canonical_normalization", "data_snapshot_build"])
@pytest.mark.parametrize("state", list(TaskState))
def test_pipeline_recovery_requires_authoritative_success_before_loading(task_type, state):
    control = _ChildTaskControl()
    control.records["child-task"] = SimpleNamespace(task_id="child-task", task_type=task_type, task_state=state)
    loaded = []
    result = object()
    worker = _PipelineWorker(None)

    def load_result(*args):
        loaded.append(args)
        return result

    executor = BackfillPipelineExecutor(
        BackfillPipelineCoordinator(control), lease_provider=lambda *_: None,
        raw_worker=worker, canonical_worker=worker, snapshot_worker=worker,
        result_loader=load_result,
    )
    if state is TaskState.SUCCEEDED:
        assert executor._execute_or_reuse("child-task", task_type, worker) is result
        assert loaded == [("child-task", task_type)]
    else:
        with pytest.raises(BackfillError) as exc:
            executor._execute_or_reuse("child-task", task_type, worker)
        assert exc.value.error_code == "BACKFILL_DEPENDENCY_NOT_READY"
        assert loaded == []
    assert worker.leases == []


@pytest.mark.parametrize("wrong_field", ["task_id", "task_type"])
def test_pipeline_recovery_rejects_mismatched_authoritative_task(wrong_field):
    control = _ChildTaskControl()
    values = dict(task_id="child-task", task_type="data_snapshot_build", task_state=TaskState.SUCCEEDED)
    values[wrong_field] = "wrong"
    control.records["child-task"] = SimpleNamespace(**values)
    loaded = []
    worker = _PipelineWorker(None)
    executor = BackfillPipelineExecutor(
        BackfillPipelineCoordinator(control), lease_provider=lambda *_: None,
        raw_worker=worker, canonical_worker=worker, snapshot_worker=worker,
        result_loader=lambda *args: loaded.append(args),
    )
    with pytest.raises(BackfillError) as exc:
        executor._execute_or_reuse("child-task", "data_snapshot_build", worker)
    assert exc.value.error_code == "BACKFILL_DEPENDENCY_MISMATCH"
    assert loaded == []
    assert worker.leases == []


@pytest.mark.parametrize("dry_run,expected_summary", [
    (True, "PLAN_ONLY_NO_BUSINESS_PUBLICATION"),
    (False, "DETERMINISTIC_FIXTURE_NO_DIFFERENCES"),
])
def test_checkpoint_projection_reads_worker_payload_without_mutating_request(tmp_path, dry_run, expected_summary):
    from src.schemas.platform import TaskDetails, TaskCheckpointRecord, StorageRef
    from datetime import datetime, timezone
    req = request(dry_run=dry_run, plan_only=dry_run)
    lease = _lease_for(req)
    payloads = []
    BackfillWorker(FakeWorkerControl(), DeterministicBackfillProvider(),
        publisher=DeterministicBackfillPublisher(),
        checkpoint_writer=lambda **kw: (payloads.append(kw["payload"]) or _storage_ref(kw["payload"]))
    ).execute(lease)
    content = payloads[-1]
    path = tmp_path / "checkpoint.json"
    path.write_bytes(content)
    checkpoint = TaskCheckpointRecord(
        checkpoint_id="checkpoint_019dbd74-2a00-7000-8000-000000000004",
        task_id=lease.task.task_id, attempt_id=lease.attempt.attempt_id,
        phase="PRICE_MONTH", sequence=1, resume_token_hash="sha256:" + "1" * 64,
        input_hash=BackfillWorker._checkpoint_input_hash(req), handler_version=BackfillWorker.HANDLER_VERSION,
        storage_ref=StorageRef.model_validate(_storage_ref(content)),
        checkpoint_hash=_storage_ref(content)["content_hash"],
        created_at=datetime(2026, 8, 31, tzinfo=timezone.utc),
        expires_at=datetime(2026, 9, 30, tzinfo=timezone.utc),
    )
    details = TaskDetails(task=lease.task, attempts=(), state_events=(), checkpoints=(checkpoint,))
    control = SimpleNamespace(resolver=SimpleNamespace(resolve=lambda *a, **k: path))
    projected = BackfillService(control)._project(details)
    assert projected.checkpoint_phase == "PRICE_MONTH"
    assert projected.differences_summary == expected_summary
    assert details.task.requirements.get("checkpoint_phase", "PLANNED") == "PLANNED"


def test_cancel_during_provider_does_not_claim_current_partition_complete():
    control = FakeWorkerControl()
    class Provider:
        def run(self, requirements, **kwargs):
            control.get_task = lambda task_id: SimpleNamespace(task=SimpleNamespace(cancel_requested_at="requested"))
            return BackfillProviderResult(completed_range=(requirements.date_from, requirements.date_to))
    payloads = []
    publisher = DeterministicBackfillPublisher()
    result = BackfillWorker(control, Provider(), publisher=publisher,
        checkpoint_writer=lambda **kw: (payloads.append(json.loads(kw["payload"])) or _storage_ref(kw["payload"]))
    ).execute(_lease_for(request(dry_run=False, plan_only=False)))
    assert result.failure_code == "BACKFILL_CANCELLED"
    assert payloads[-1]["completed_range"] is None
    assert payloads[-1]["completed_partitions"] == []
    assert not publisher._published



def test_checkpoint_projection_uses_latest_attempt_not_global_sequence(tmp_path):
    from datetime import datetime, timezone
    from src.schemas.platform import TaskDetails, TaskCheckpointRecord, StorageRef

    req = request()
    lease = _lease_for(req)
    payloads = []
    worker = BackfillWorker(FakeWorkerControl(), DeterministicBackfillProvider(),
        checkpoint_writer=lambda **kw: (payloads.append(kw["payload"]) or _storage_ref(kw["payload"]))
    )
    worker.execute(lease)
    old = json.loads(payloads[0])
    latest = json.loads(payloads[-1])
    latest["checkpoint_phase"] = "LATEST_PHASE"
    paths = {}
    checkpoints = []
    for number, (attempt_id, payload, created_at) in enumerate((
        ("attempt_019dbd74-2a00-7000-8000-000000000003", old, datetime(2026, 8, 31, 1, tzinfo=timezone.utc)),
        ("attempt_019dbd74-2a00-7000-8000-000000000004", latest, datetime(2026, 8, 31, 2, tzinfo=timezone.utc)),
    ), start=1):
        content = BackfillWorker._serialize_checkpoint_payload(payload)
        ref_data = _storage_ref(content)
        path = tmp_path / f"checkpoint-{number}.json"
        path.write_bytes(content)
        paths[ref_data["relative_path"]] = path
        checkpoints.append(TaskCheckpointRecord(
            checkpoint_id=f"checkpoint_019dbd74-2a00-7000-8000-{number:012d}",
            task_id=lease.task.task_id, attempt_id=attempt_id, phase="LATEST_PHASE" if number == 2 else "OLD_PHASE",
            sequence=1, resume_token_hash="sha256:" + "1" * 64,
            input_hash=BackfillWorker._checkpoint_input_hash(req), handler_version=BackfillWorker.HANDLER_VERSION,
            storage_ref=StorageRef.model_validate(ref_data), checkpoint_hash=ref_data["content_hash"],
            created_at=created_at, expires_at=datetime(2026, 9, 30, tzinfo=timezone.utc),
        ))
    details = TaskDetails(task=lease.task, attempts=(), state_events=(), checkpoints=tuple(checkpoints))
    resolver = SimpleNamespace(resolve=lambda ref, **kwargs: paths[ref.relative_path])
    projected = BackfillService(SimpleNamespace(resolver=resolver))._project(details)
    assert projected.checkpoint_phase == "LATEST_PHASE"


def test_corrupt_checkpoint_projection_returns_sanitized_contract_error(tmp_path):
    from datetime import datetime, timezone
    from src.schemas.platform import TaskDetails, TaskCheckpointRecord, StorageRef

    req = request()
    lease = _lease_for(req)
    content = b"not-json"
    ref_data = _storage_ref(content)
    path = tmp_path / "corrupt.json"
    path.write_bytes(content)
    checkpoint = TaskCheckpointRecord(
        checkpoint_id="checkpoint_019dbd74-2a00-7000-8000-000000000006",
        task_id=lease.task.task_id, attempt_id=lease.attempt.attempt_id, phase="PRICE_MONTH", sequence=1,
        resume_token_hash="sha256:" + "1" * 64, input_hash=BackfillWorker._checkpoint_input_hash(req),
        handler_version=BackfillWorker.HANDLER_VERSION, storage_ref=StorageRef.model_validate(ref_data),
        checkpoint_hash=ref_data["content_hash"], created_at=datetime(2026, 8, 31, tzinfo=timezone.utc),
        expires_at=datetime(2026, 9, 30, tzinfo=timezone.utc),
    )
    details = TaskDetails(task=lease.task, attempts=(), state_events=(), checkpoints=(checkpoint,))
    with pytest.raises(BackfillError) as exc:
        BackfillService(SimpleNamespace(resolver=SimpleNamespace(resolve=lambda *a, **k: path)))._project(details)
    assert exc.value.error_code == "BACKFILL_CHECKPOINT_INVALID"
    assert str(path) not in exc.value.public_message



def test_worker_renews_existing_task_lease_at_partition_safe_points():
    class HeartbeatControl(FakeWorkerControl):
        def heartbeat(self, attempt_id, lease_token, **kwargs):
            self.calls.append(("heartbeat", (attempt_id, lease_token, kwargs)))

    control = HeartbeatControl()
    result = BackfillWorker(
        control,
        DeterministicBackfillProvider(),
        publisher=DeterministicBackfillPublisher(),
        checkpoint_writer=lambda **kw: _storage_ref(kw["payload"]),
    ).execute(_lease_for(request(dry_run=False, plan_only=False)))
    assert result.batch_state is BackfillStatus.COMPLETED
    heartbeats = [item for item in control.calls if item[0] == "heartbeat"]
    assert len(heartbeats) >= 2


def test_worker_fails_closed_when_heartbeat_rejects_before_provider_call():
    class ExpiredLeaseControl(FakeWorkerControl):
        def heartbeat(self, attempt_id, lease_token, **kwargs):
            raise TaskControlError("TASK_LEASE_LOST", "Task lease is no longer valid.", status_code=409)

    control = ExpiredLeaseControl()
    provider = DeterministicBackfillProvider()
    publisher = Mock()
    with pytest.raises(TaskControlError, match="TASK_LEASE_LOST"):
        BackfillWorker(
            control,
            provider,
            publisher=publisher,
            checkpoint_writer=lambda **kw: _storage_ref(kw["payload"]),
        ).execute(_lease_for(request(dry_run=False, plan_only=False)))
    assert provider.calls == []
    publisher.publish.assert_not_called()


def test_worker_does_not_publish_after_heartbeat_rejection_at_publish_safe_point():
    class ExpireAtPublishSafePointControl(FakeWorkerControl):
        def __init__(self):
            super().__init__()
            self.heartbeat_calls = 0

        def heartbeat(self, attempt_id, lease_token, **kwargs):
            self.heartbeat_calls += 1
            if self.heartbeat_calls == 2:
                raise TaskControlError("TASK_LEASE_LOST", "Task lease is no longer valid.", status_code=409)

    control = ExpireAtPublishSafePointControl()
    provider = DeterministicBackfillProvider()
    publisher = Mock()
    with pytest.raises(TaskControlError, match="TASK_LEASE_LOST"):
        BackfillWorker(
            control,
            provider,
            publisher=publisher,
            checkpoint_writer=lambda **kw: _storage_ref(kw["payload"]),
        ).execute(_lease_for(request(dry_run=False, plan_only=False)))
    assert provider.calls == ["PRICE_MONTH"]
    publisher.publish.assert_not_called()

@pytest.mark.parametrize("operation", ["list", "get", "create"])
@pytest.mark.parametrize("status_code,retryable", [(409, True), (503, False)])
def test_backfill_api_preserves_service_retryability(operation, status_code, retryable):
    from api.middlewares.error_handler import add_error_handlers

    class FailingService:
        def fail(self, *args, **kwargs):
            raise BackfillError(
                "BACKFILL_CHILD_RESULT_UNAVAILABLE", "Backfill result is unavailable.",
                status_code=status_code, retryable=retryable,
            )
        list_batches = fail
        get_batch = fail
        create_batch = fail

    app = FastAPI()
    app.include_router(router, prefix="/api")
    add_error_handlers(app)
    app.state.backfill_service = FailingService()
    with TestClient(app, raise_server_exceptions=False) as client:
        if operation == "create":
            response = client.post(
                "/api/platform/v1/backfills", headers={"Idempotency-Key": "retry-contract"},
                json=request().model_dump(mode="json"),
            )
        else:
            suffix = "" if operation == "list" else "/" + request().batch_id
            response = client.get("/api/platform/v1/backfills" + suffix)
    assert response.status_code == status_code
    error = response.json()["error"]
    assert error["code"] == "BACKFILL_CHILD_RESULT_UNAVAILABLE"
    assert error["message"] == "Backfill result is unavailable."
    assert error["retryable"] is retryable
    assert error["details"] == {}


@pytest.mark.parametrize("operation", ["list", "get", "create", "stage_chain"])
def test_backfill_api_unknown_failures_use_safe_platform_envelope(operation):
    from api.middlewares.error_handler import add_error_handlers

    class ExplodingService:
        def fail(self, *args, **kwargs):
            raise RuntimeError("database password=fixture-secret at C:\\private\\raw_payload.json")

        list_batches = fail
        get_batch = fail
        create_batch = fail
        create_stage_chain = fail

    app = FastAPI()
    app.include_router(router, prefix="/api")
    add_error_handlers(app)
    app.state.backfill_service = ExplodingService()
    payload = stage_chain_request().model_dump(mode="json")

    with TestClient(app, raise_server_exceptions=False) as client:
        if operation == "list":
            response = client.get("/api/platform/v1/backfills")
        elif operation == "get":
            response = client.get(f"/api/platform/v1/backfills/{request().batch_id}")
        elif operation == "create":
            response = client.post(
                "/api/platform/v1/backfills",
                headers={"Idempotency-Key": "unknown-failure"},
                json=request().model_dump(mode="json"),
            )
        else:
            response = client.post(
                "/api/platform/v1/backfills/stage-chain",
                headers={"Idempotency-Key": "unknown-stage-chain-failure"},
                json=payload,
            )

    assert response.status_code == 500
    assert response.json()["error"] == {
        "code": "INTERNAL_ERROR",
        "message": "服务器内部错误",
        "details": {},
        "retryable": False,
        "request_id": response.json()["error"]["request_id"],
    }
    assert "fixture-secret" not in response.text
    assert "raw_payload" not in response.text

def test_deterministic_publisher_rejects_misaligned_lineage_cardinality():
    publisher = DeterministicBackfillPublisher()
    req = request(dry_run=False, plan_only=False)
    result = BackfillProviderResult(
        completed_range=(req.date_from, req.date_to),
        provider_run_refs=("prun_00000000-0000-7000-8000-000000000091", "prun_00000000-0000-7000-8000-000000000092"),
        raw_object_refs=("raw_00000000-0000-7000-8000-000000000091",),
        canonical_partition_refs=(
            "cpart_00000000-0000-7000-8000-000000000091",
            "cpart_00000000-0000-7000-8000-000000000092",
        ),
    )
    with pytest.raises(BackfillError, match="lineage is incomplete"):
        publisher.publish(req, result, idempotency_key="misaligned-lineage")


def test_pipeline_default_result_loader_reads_existing_registry_lineage(monkeypatch):
    class Database:
        @contextmanager
        def transaction(self):
            yield object()

    class Control:
        database = Database()

    provider_run = SimpleNamespace(run_outcome=object(), raw_object_refs=("raw_1",), provider_run_id="prun_1")
    raw_object = SimpleNamespace(raw_object_id="raw_1")
    quality_report = SimpleNamespace(canonical_partition_id="cpart_1", quality_status=QualityStatus.COMPLETE)
    canonical_partition = SimpleNamespace(canonical_partition_id="cpart_1")
    snapshot = SimpleNamespace(snapshot_id="ds_1")
    certifications = (SimpleNamespace(capability_id="bars"),)

    class RawRepository:
        def get_provider_run_by_task(self, _session, _task_id):
            return provider_run

        def get_raw_object_by_run(self, _session, _run_id):
            return raw_object

    class CanonicalRepository:
        def get_quality_report_by_task(self, _session, _task_id):
            return quality_report

        def get_partition(self, _session, _partition_id):
            return canonical_partition

    class SnapshotRepository:
        def get_snapshot_by_task(self, _session, _task_id):
            return snapshot

        def list_capabilities(self, _session, _snapshot_id):
            return certifications

    import src.repositories.platform.canonical as canonical_module
    import src.repositories.platform.raw_ingestion as raw_module
    import src.repositories.platform.snapshot as snapshot_module

    monkeypatch.setattr(raw_module, "RawIngestionRepository", RawRepository)
    monkeypatch.setattr(canonical_module, "CanonicalRepository", CanonicalRepository)
    monkeypatch.setattr(snapshot_module, "SnapshotRepository", SnapshotRepository)

    executor = BackfillPipelineExecutor(
        BackfillPipelineCoordinator(Control()),
        lease_provider=lambda *_args: None,
        raw_worker=object(),
        canonical_worker=object(),
        snapshot_worker=object(),
    )
    loader = executor.result_loader
    assert loader is not None
    assert loader("raw-task", "raw_ingestion").raw_object is raw_object
    assert loader("canonical-task", "canonical_normalization").canonical_partition is canonical_partition
    assert loader("snapshot-task", "data_snapshot_build").snapshot is snapshot
    assert loader("snapshot-task", "data_snapshot_build").capability_certifications == certifications




def test_worker_recovers_published_child_chain_after_parent_checkpoint_crash():
    class IdempotentChildTaskControl(_ChildTaskControl):
        def __init__(self):
            super().__init__()
            self.task_ids_by_key = {}

        def create_task(self, request, **kwargs):
            idempotency_key = kwargs["idempotency_key"]
            existing_id = self.task_ids_by_key.get(idempotency_key)
            if existing_id is not None:
                return self.records[existing_id]
            record = super().create_task(request, **kwargs)
            self.task_ids_by_key[idempotency_key] = record.task_id
            return record

    child_control = IdempotentChildTaskControl()
    req = request(dry_run=False, plan_only=False)
    raw_result = SimpleNamespace(
        raw_object=SimpleNamespace(raw_object_id="raw_00000000-0000-7000-8000-000000000071"),
        provider_run=SimpleNamespace(provider_run_id="prun_00000000-0000-7000-8000-000000000071"),
    )
    canonical_result = SimpleNamespace(
        canonical_partition=SimpleNamespace(
            canonical_partition_id="cpart_00000000-0000-7000-8000-000000000071"
        ),
        published=True,
    )
    snapshot_result = SimpleNamespace(
        snapshot=SimpleNamespace(snapshot_id="ds_00000000-0000-7000-8000-000000000071"),
        published=True,
    )
    results = {
        "raw_ingestion": raw_result,
        "canonical_normalization": canonical_result,
        "data_snapshot_build": snapshot_result,
    }
    workers = {
        task_type: _PipelineWorker(result)
        for task_type, result in results.items()
    }
    loaded = []

    def lease_for(task_id, task_type):
        record = child_control.records[task_id]
        if record.task_state is TaskState.SUCCEEDED:
            return None
        child_control.succeed(task_id)
        return SimpleNamespace(
            task=record,
            attempt=SimpleNamespace(
                attempt_id=f"attempt_{len(child_control.records):08d}-0000-7000-8000-000000000000"
            ),
            lease_token="x" * 32,
        )

    def load_result(task_id, task_type):
        loaded.append((task_id, task_type))
        return results[task_type]

    executor = BackfillPipelineExecutor(
        BackfillPipelineCoordinator(child_control),
        lease_provider=lease_for,
        raw_worker=workers["raw_ingestion"],
        canonical_worker=workers["canonical_normalization"],
        snapshot_worker=workers["data_snapshot_build"],
        result_loader=load_result,
    )

    def plan_factory(part, _result, _index):
        return {
            "raw_requirements": {
                "provider_id": "fixture",
                "dataset_id": part.dataset,
                "dataset_schema_version": "1.0.0",
                "provider_policy_id": part.provider_policy_id,
            },
            "canonical_requirements": lambda raw: {
                "provider_id": "fixture",
                "dataset_id": part.dataset,
                "dataset_schema_version": "1.0.0",
                "raw_object_id": raw.raw_object.raw_object_id,
                "provider_run_id": raw.provider_run.provider_run_id,
                "provider_policy_id": part.provider_policy_id,
                "provider_policy_version": "1.0.0",
                "mapping_version": "1.0.0",
                "partition_key": "2026-08",
            },
            "snapshot_requirements": lambda canonical: {
                "trade_date": "2026-08-31",
                "cutoff_at": "2026-09-22T00:00:00Z",
                "provider_policy_id": part.provider_policy_id,
                "provider_policy_version": "1.0.0",
                "security_master_ref": canonical.canonical_partition.canonical_partition_id,
                "calendar_ref": canonical.canonical_partition.canonical_partition_id,
                "canonical_partition_ids": (
                    canonical.canonical_partition.canonical_partition_id,
                ),
                "requested_capabilities": ("bars",),
            },
            "partition_rows": {"bars": [{"asset_id": "asset_1"}]},
        }

    def crash_after_publication(**_kwargs):
        raise OSError("simulated parent checkpoint crash")

    first_control = FakeWorkerControl()
    with pytest.raises(BackfillError) as captured:
        BackfillWorker(
            first_control,
            DeterministicBackfillProvider(),
            checkpoint_writer=crash_after_publication,
            pipeline_executor=executor,
            pipeline_plan_factory=plan_factory,
        ).execute(_lease_for(req))
    assert captured.value.error_code == "BACKFILL_WORKER_ERROR"
    assert len(child_control.records) == 3
    assert all(len(worker.leases) == 1 for worker in workers.values())

    payloads = []
    recovered = BackfillWorker(
        FakeWorkerControl(),
        DeterministicBackfillProvider(),
        checkpoint_writer=lambda **kwargs: (
            payloads.append(json.loads(kwargs["payload"])) or _storage_ref(kwargs["payload"])
        ),
        pipeline_executor=executor,
        pipeline_plan_factory=plan_factory,
    ).execute(_lease_for(req))

    assert recovered.batch_state is BackfillStatus.COMPLETED
    assert len(child_control.records) == 3
    assert all(len(worker.leases) == 1 for worker in workers.values())
    assert [task_type for _task_id, task_type in loaded] == [
        "raw_ingestion",
        "canonical_normalization",
        "data_snapshot_build",
    ]
    assert payloads[-1]["snapshot_refs"] == [snapshot_result.snapshot.snapshot_id]
from unittest.mock import Mock


def test_phase_one_rejects_custom_batch_type_before_range_planning():
    with pytest.raises(ValueError):
        request(
            batch_type="CUSTOM",
            date_from=date(2025, 1, 1),
            date_to=date(2025, 3, 31),
        )


def test_year_worker_checkpoint_preserves_all_skipped_and_failed_ranges():
    class MixedPartitionProvider:
        def __init__(self):
            self.calls = 0

        def run(self, requirements, *, resume_payload=None):
            del resume_payload
            self.calls += 1
            if self.calls in {2, 4}:
                return BackfillProviderResult(
                    skipped_range=(requirements.date_from, requirements.date_to),
                    differences_summary="FIXTURE_PARTITION_SKIPPED",
                )
            if self.calls == 5:
                return BackfillProviderResult(
                    failed_range=(requirements.date_from, requirements.date_to),
                    quality_events=("PROVIDER_UNAVAILABLE",),
                    retryable=True,
                )
            return BackfillProviderResult(
                completed_range=(requirements.date_from, requirements.date_to),
            )

    control = FakeWorkerControl()
    payloads = []

    def writer(**kwargs):
        payloads.append(json.loads(kwargs["payload"]))
        return _storage_ref(kwargs["payload"])

    req = request(
        batch_type="YEAR",
        date_from=date(2025, 1, 1),
        date_to=date(2025, 12, 31),
        dry_run=False,
        plan_only=False,
    )
    publisher = Mock()
    publisher.publish.return_value = ()
    result = BackfillWorker(
        control,
        MixedPartitionProvider(),
        publisher=publisher,
        checkpoint_writer=writer,
    ).execute(_lease_for(req))

    assert result.batch_state is BackfillStatus.FAILED
    failure = payloads[-1]
    assert failure["skipped_ranges"] == [
        ["2025-02-01", "2025-02-28"],
        ["2025-04-01", "2025-04-30"],
    ]
    assert failure["failed_ranges"] == [["2025-05-01", "2025-05-31"]]


def test_stage_chain_fails_closed_when_worker_result_disagrees_with_task_state():
    control = _StageChainExecutionControl()
    chain = stage_chain_request(dry_run=False, plan_only=False)
    executed = []

    def worker_factory(lease):
        class Worker:
            def execute(self, current_lease, **kwargs):
                del kwargs
                executed.append(current_lease.task.task_id)
                control.records[current_lease.task.task_id] = current_lease.task.model_copy(
                    update={"task_state": TaskState.QUEUED}
                )
                return SimpleNamespace(
                    task_id=current_lease.task.task_id,
                    batch_id=current_lease.task.requirements["batch_id"],
                    batch_state=BackfillStatus.COMPLETED,
                    stage=current_lease.task.requirements["stage"],
                )

        return Worker()

    result = BackfillStageChainExecutor(control, worker_factory=worker_factory).execute(
        chain,
        idempotency_key="backfill-stage-chain-state-mismatch",
        max_stages=2,
    )

    assert executed == [result.projection.batches[0].task_id]
    assert result.stopped_task_id == result.projection.batches[0].task_id
    assert result.stopped_state is TaskState.QUEUED


@pytest.mark.parametrize("mutation", ["completed_range", "resource_usage", "provider_lineage"])
def test_resume_rejects_inconsistent_checkpoint_accumulators(tmp_path, mutation):
    from src.artifacts.namespace import StorageNamespaceResolver
    from src.schemas.platform import StorageRef
    from src.services.platform.backfill import BackfillError, plan_backfill_ranges

    req = request(
        batch_type="YEAR",
        date_from=date(2025, 1, 1),
        date_to=date(2025, 12, 31),
        dry_run=False,
        plan_only=False,
    )
    lease = _lease_for(req)
    payload = {
        "batch_id": req.batch_id,
        "task_id": lease.task.task_id,
        "handler_version": BackfillWorker.HANDLER_VERSION,
        "stage": req.stage.value,
        "date_from": req.date_from.isoformat(),
        "date_to": req.date_to.isoformat(),
        "dataset": req.dataset,
        "input_hash": BackfillWorker._checkpoint_input_hash(req),
        "completed_partitions": [0, 1],
        "completed_range": ["2025-01-01", "2025-02-28"],
        "resource_usage": {"requests": 2.0},
        "provider_run_refs": ["prun_00000000-0000-7000-8000-000000000001"],
        "raw_object_refs": ["raw_00000000-0000-7000-8000-000000000001"],
        "canonical_partition_refs": ["cpart_00000000-0000-7000-8000-000000000001"],
        "snapshot_refs": ["ds_00000000-0000-7000-8000-000000000001"],
    }
    if mutation == "completed_range":
        payload["completed_range"] = ["2025-01-01", "2025-03-31"]
    elif mutation == "resource_usage":
        payload["resource_usage"] = {"requests": -1.0}
    else:
        payload["provider_run_refs"] = [
            "prun_00000000-0000-7000-8000-000000000001",
            "prun_00000000-0000-7000-8000-000000000001",
        ]

    content = BackfillWorker._serialize_checkpoint_payload(payload)
    ref = StorageRef.model_validate(_storage_ref(content))
    control = FakeWorkerControl()
    control.resolver = StorageNamespaceResolver(tmp_path)
    path = control.resolver.resolve(ref)
    path.parent.mkdir(parents=True)
    path.write_bytes(content)
    control.validate_checkpoint = lambda *args, **kwargs: SimpleNamespace(
        task_id=lease.task.task_id,
        checkpoint_hash=ref.content_hash,
        storage_ref=ref,
    )
    worker = BackfillWorker(control, DeterministicBackfillProvider())

    with pytest.raises(BackfillError, match="checkpoint cannot be resumed"):
        worker._validated_resume_partitions(
            lease,
            req,
            plan_backfill_ranges(req),
            payload,
            resume_checkpoint_id="checkpoint_019dbd74-2a00-7000-8000-000000000004",
            resume_token="resume-token",
        )




@pytest.mark.parametrize("failed", [False, True])
def test_year_worker_preserves_distinct_partition_difference_summaries(failed):
    from dataclasses import replace

    class Provider(DeterministicBackfillProvider):
        def run(self, requirements, **kwargs):
            result = super().run(requirements, **kwargs)
            if failed and requirements.date_from.month == 2:
                return BackfillProviderResult(
                    failed_range=(requirements.date_from, requirements.date_to),
                    differences_summary="FEBRUARY_FAILED", retryable=True,
                )
            return replace(result, differences_summary=f"MONTH_{requirements.date_from.month}_CHECKED")

    payloads = []
    req = request(batch_type="YEAR", date_from=date(2025, 1, 1), date_to=date(2025, 12, 31), dry_run=False, plan_only=False)
    BackfillWorker(FakeWorkerControl(), Provider(), publisher=DeterministicBackfillPublisher(),
        checkpoint_writer=lambda **kw: (payloads.append(json.loads(kw["payload"])) or _storage_ref(kw["payload"]))
    ).execute(_lease_for(req))
    expected = ["MONTH_1_CHECKED", "FEBRUARY_FAILED"] if failed else [f"MONTH_{month}_CHECKED" for month in range(1, 13)]
    assert payloads[-1]["differences_summary"] == "; ".join(expected)
    assert payloads[0]["differences_summary"] == "MONTH_1_CHECKED"
