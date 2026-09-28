from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta, timezone
from calendar import monthrange
from types import SimpleNamespace
from typing import Any, Callable, Mapping, Protocol

from src.artifacts.hashing import compute_bytes_hash

from src.schemas.platform import (
    BackfillBatchProjection, BackfillBatchRequest, BackfillBatchType, BackfillStage,
    BackfillStageChainProjection, BackfillStageChainRequest, BackfillStatus,
    BackfillTaskRequirements, PriorityClass, ResourceRef, ResourceType, StorageRef, TaskDetails,
    TaskCreateRequest, TaskLease, TaskListQuery, TaskRecord, TaskState, StorageBackend, StorageNamespace,
    compute_content_hash, generate_resource_id, parse_resource_id,
)
from src.services.platform.task_control import TaskControlError, TaskControlService


class BackfillError(Exception):
    def __init__(self, error_code: str, public_message: str, *, status_code: int = 422, retryable: bool = False):
        super().__init__(public_message)
        self.error_code = error_code
        self.public_message = public_message
        self.status_code = status_code
        self.retryable = retryable


def _stable_resource_id(resource_type: ResourceType, key: str) -> str:
    """Build a deterministic fixture id while preserving the UUIDv7 contract.

    The production publisher owns durable idempotency. Offline backfill
    fixtures must still model a retry after a worker restart, so their lineage
    ids cannot depend on process-local state or random UUID generation.
    """
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    random_bits = int.from_bytes(digest[:10], "big") & ((1 << 74) - 1)
    return generate_resource_id(resource_type, timestamp_ms=0, random_bits=random_bits)


@dataclass(frozen=True, slots=True)
class BackfillProviderResult:
    completed_range: tuple[date, date] | None = None
    skipped_range: tuple[date, date] | None = None
    failed_range: tuple[date, date] | None = None
    skipped_ranges: tuple[tuple[date, date], ...] = ()
    failed_ranges: tuple[tuple[date, date], ...] = ()
    differences_summary: str | None = None
    resource_usage: dict[str, float] | None = None
    quality_events: tuple[str, ...] = ()
    next_phase: str | None = None
    published_refs: tuple[str, ...] = ()
    retryable: bool = False
    provider_run_refs: tuple[str, ...] = ()
    raw_object_refs: tuple[str, ...] = ()
    canonical_partition_refs: tuple[str, ...] = ()
    snapshot_refs: tuple[str, ...] = ()
    provider_fallback: bool = False
    unavailable: bool = False


_BACKFILL_STAGE_ORDER: tuple[BackfillStage, ...] = tuple(BackfillStage)


def backfill_stage_dependencies(stage: BackfillStage) -> tuple[BackfillStage, ...]:
    """Return the immutable prerequisite prefix defined by WP-0207's roadmap."""
    if not isinstance(stage, BackfillStage):
        raise TypeError("stage must be a BackfillStage")
    return _BACKFILL_STAGE_ORDER[:_BACKFILL_STAGE_ORDER.index(stage)]


def _merge_difference_summary(current: str | None, incoming: str | None) -> str | None:
    """Accumulate distinct bounded partition summaries without exposing raw payloads."""
    if incoming is None:
        return current
    incoming = incoming.strip()
    if not incoming:
        return current
    if current is None or not current.strip():
        return incoming[:2048]
    parts = [item for item in current.split("; ") if item]
    if incoming not in parts:
        parts.append(incoming)
    return "; ".join(parts)[:2048]


def plan_backfill_ranges(request: BackfillBatchRequest | BackfillTaskRequirements) -> tuple[tuple[date, date], ...]:
    """Expand a batch into deterministic calendar partitions without external I/O."""
    if request.batch_type is not BackfillBatchType.YEAR:
        return ((request.date_from, request.date_to),)
    ranges: list[tuple[date, date]] = []
    cursor = date(request.date_from.year, request.date_from.month, 1)
    while cursor <= request.date_to:
        month_end = date(cursor.year, cursor.month, monthrange(cursor.year, cursor.month)[1])
        ranges.append((max(cursor, request.date_from), min(month_end, request.date_to)))
        cursor = date(cursor.year + (cursor.month == 12), 1 if cursor.month == 12 else cursor.month + 1, 1)
    return tuple(ranges)


class BackfillProvider(Protocol):
    def run(self, requirements: BackfillTaskRequirements, *, resume_payload: dict[str, Any] | None = None) -> BackfillProviderResult: ...


class BackfillPublisher(Protocol):
    def publish(self, requirements: BackfillTaskRequirements, result: BackfillProviderResult, *, idempotency_key: str) -> tuple[str, ...]: ...


class CheckpointWriter(Protocol):
    def __call__(self, *, task_id: str, attempt_id: str, payload: bytes) -> StorageRef: ...


class DeterministicBackfillProvider:
    """Offline provider used by tests; it never connects to a network or production path."""

    def __init__(self, *, fail_on_stage: BackfillStage | None = None, quarantine: bool = False, fallback: bool = False, unavailable: bool = False) -> None:
        self.fail_on_stage = fail_on_stage
        self.quarantine = quarantine
        self.fallback = fallback
        self.unavailable = unavailable
        self.calls: list[str] = []

    def run(self, requirements: BackfillTaskRequirements, *, resume_payload: dict[str, Any] | None = None) -> BackfillProviderResult:
        self.calls.append(requirements.stage.value)
        if self.fail_on_stage is requirements.stage:
            return BackfillProviderResult(
                failed_range=(requirements.date_from, requirements.date_to),
                differences_summary="PROVIDER_FAILURE_NO_PUBLICATION",
                resource_usage={"provider_requests": 1.0},
                quality_events=("PROVIDER_UNAVAILABLE",),
                retryable=True,
            )
        if requirements.dry_run or requirements.plan_only:
            return BackfillProviderResult(
                skipped_range=(requirements.date_from, requirements.date_to),
                differences_summary="PLAN_ONLY_NO_BUSINESS_PUBLICATION",
                resource_usage={"planned_partitions": 1.0},
            )
        if self.unavailable:
            return BackfillProviderResult(
                skipped_range=(requirements.date_from, requirements.date_to),
                differences_summary="UNAVAILABLE_DATASET_NO_PUBLICATION",
                resource_usage={"provider_requests": 1.0},
                quality_events=("UNAVAILABLE_DATASET",),
                unavailable=True,
            )
        events = []
        if self.quarantine:
            events.append("QUARANTINE_SCHEMA_DRIFT")
        if self.fallback:
            events.extend(("PROVIDER_PRIMARY_ATTEMPT_RECORDED", "PROVIDER_FALLBACK_EXPLICIT"))
        base_key = ":".join((
            requirements.batch_id,
            requirements.stage.value,
            requirements.date_from.isoformat(),
            requirements.date_to.isoformat(),
            requirements.dataset,
            requirements.provider_policy_id,
        ))
        sources = ("primary", "supplement") if self.fallback else ("primary",)
        return BackfillProviderResult(
            completed_range=(requirements.date_from, requirements.date_to),
            differences_summary="DETERMINISTIC_FIXTURE_NO_DIFFERENCES",
            resource_usage={"provider_requests": 1.0, "estimated_rows": 1.0},
            quality_events=tuple(events),
            next_phase=None,
            provider_fallback=self.fallback,
            provider_run_refs=tuple(
                _stable_resource_id(ResourceType.PROVIDER_RUN, f"provider-run:{base_key}:{source}")
                for source in sources
            ),
            raw_object_refs=tuple(
                _stable_resource_id(ResourceType.RAW_OBJECT, f"raw:{base_key}:{source}")
                for source in sources
            ),
            canonical_partition_refs=tuple(
                _stable_resource_id(ResourceType.CANONICAL_PARTITION, f"canonical:{base_key}:{source}")
                for source in sources
            ),
        )


class DeterministicBackfillPublisher:
    """Idempotent offline publisher fixture; it never writes production storage."""

    def __init__(self) -> None:
        self._published: dict[str, tuple[str, ...]] = {}
        self._publication_inputs: dict[str, str] = {}
        self._publications: dict[str, BackfillFixturePublication] = {}

    @staticmethod
    def _publication_input_hash(requirements: BackfillTaskRequirements, result: BackfillProviderResult) -> str:
        return compute_content_hash({
            "batch_id": requirements.batch_id,
            "stage": requirements.stage.value,
            "date_from": requirements.date_from.isoformat(),
            "date_to": requirements.date_to.isoformat(),
            "dataset": requirements.dataset,
            "provider_policy_id": requirements.provider_policy_id,
            "provider_run_refs": result.provider_run_refs,
            "raw_object_refs": result.raw_object_refs,
            "canonical_partition_refs": result.canonical_partition_refs,
            "supersedes_id": getattr(requirements, "supersedes_id", None),
        })

    def publish(self, requirements: BackfillTaskRequirements, result: BackfillProviderResult, *, idempotency_key: str) -> tuple[str, ...]:
        if not requirements.dry_run and not requirements.plan_only:
            lineage = (result.provider_run_refs, result.raw_object_refs, result.canonical_partition_refs)
            if (
                any(not refs for refs in lineage)
                or len({len(refs) for refs in lineage}) != 1
                or any(len(refs) != len(set(refs)) for refs in lineage)
            ):
                raise BackfillError(
                    "BACKFILL_LINEAGE_INCOMPLETE",
                    "Backfill publication lineage is incomplete.",
                    status_code=422,
                )
        input_hash = self._publication_input_hash(requirements, result)
        prior_hash = self._publication_inputs.get(idempotency_key)
        if prior_hash is not None and prior_hash != input_hash:
            raise BackfillError(
                "BACKFILL_IDEMPOTENCY_CONFLICT",
                "Backfill publication idempotency key is already bound to different input.",
                status_code=409,
            )
        if idempotency_key not in self._published:
            self._publication_inputs[idempotency_key] = input_hash
            canonical_refs = tuple(result.canonical_partition_refs)
            self._published[idempotency_key] = canonical_refs
            self._publications[idempotency_key] = BackfillFixturePublication(
                idempotency_key=idempotency_key,
                provider_run_refs=tuple(result.provider_run_refs),
                raw_object_refs=tuple(result.raw_object_refs),
                canonical_partition_refs=canonical_refs,
                snapshot_id=_stable_resource_id(ResourceType.DATA_SNAPSHOT, f"snapshot:{idempotency_key}"),
                supersedes_id=getattr(requirements, "supersedes_id", None),
            )
        return self._published[idempotency_key]

    def get_publication(self, idempotency_key: str) -> BackfillFixturePublication:
        try:
            return self._publications[idempotency_key]
        except KeyError as exc:
            raise BackfillError("BACKFILL_PUBLICATION_NOT_FOUND", "Backfill publication was not found.", status_code=404) from exc


@dataclass(frozen=True, slots=True)
class BackfillFixturePublication:
    """Immutable offline publication record used to prove lineage and correction semantics."""

    idempotency_key: str
    canonical_partition_refs: tuple[str, ...]
    snapshot_id: str
    supersedes_id: str | None
    provider_run_refs: tuple[str, ...] = ()
    raw_object_refs: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class BackfillExecutionResult:
    task_id: str
    batch_id: str
    batch_state: BackfillStatus
    checkpoint_phase: str
    published_refs: tuple[str, ...] = ()
    failure_code: str | None = None


@dataclass(frozen=True, slots=True)
class BackfillPipelineSubmission:
    """Stable child-task lineage for one backfill partition."""

    raw_task_id: str
    canonical_task_id: str | None = None
    snapshot_task_id: str | None = None


class BackfillPipelineCoordinator:
    """Submit the existing raw -> canonical -> snapshot task chain in order.

    Downstream submission requires successful, partition-bound predecessor
    tasks read from the existing Task Control Plane. Published-object lineage
    must additionally be validated by the existing downstream workers.
    """

    def __init__(self, task_control_service: Any) -> None:
        self.task_control_service = task_control_service

    @staticmethod
    def _task_id(value: TaskRecord | str) -> str:
        return value.task_id if isinstance(value, TaskRecord) else value

    @staticmethod
    def _refs(requirements: BackfillTaskRequirements, parent_task: TaskRecord | str, *task_ids: str) -> tuple[ResourceRef, ...]:
        refs = [
            ResourceRef(resource_type=ResourceType.BACKFILL_BATCH, resource_id=requirements.batch_id),
            ResourceRef(resource_type=ResourceType.TASK, resource_id=BackfillPipelineCoordinator._task_id(parent_task)),
        ]
        refs.extend(ResourceRef(resource_type=ResourceType.TASK, resource_id=task_id) for task_id in task_ids)
        return tuple(refs)

    def _require_predecessor(
        self, task_id: str, *, task_type: str, requirements: BackfillTaskRequirements,
        partition_index: int, requested_by: str, suffix: str, refs: tuple[ResourceRef, ...],
    ) -> None:
        # 重新读取控制面，调用方持有的旧 TaskRecord 不能作为成功凭证。
        ResourceRef(resource_type=ResourceType.TASK, resource_id=task_id)
        record = self.task_control_service.get_task(task_id).task
        if (
            record.task_type != task_type
            or record.requested_by != requested_by
            or record.request_source != "backfill:child"
            or record.idempotency_key != f"backfill:{requirements.batch_id}:{partition_index}:{suffix}"
            or record.input_refs != refs
            or record.requirements.get("dataset_id") != requirements.dataset
            or record.requirements.get("provider_policy_id") != requirements.provider_policy_id
        ):
            raise BackfillError("BACKFILL_DEPENDENCY_MISMATCH", "Backfill dependency does not match the partition.", status_code=409)
        if record.task_state is not TaskState.SUCCEEDED:
            raise BackfillError("BACKFILL_DEPENDENCY_NOT_READY", "Backfill dependency has not succeeded.", status_code=409)

    def _submit(
        self,
        *,
        task_type: str,
        payload: Mapping[str, Any],
        requirements: BackfillTaskRequirements,
        parent_task: TaskRecord | str,
        partition_index: int,
        requested_by: str,
        suffix: str,
        refs: tuple[ResourceRef, ...],
    ) -> TaskRecord:
        if requirements.dry_run or requirements.plan_only:
            raise BackfillError("BACKFILL_PLAN_ONLY", "Plan-only backfill cannot enqueue business tasks.", status_code=409)
        request = TaskCreateRequest(
            task_type=task_type,
            priority_class=PriorityClass.P5_PREVIEW_AND_MAINTENANCE,
            priority_value=requirements.priority,
            requested_by=requested_by,
            request_source="backfill:child",
            input_refs=refs,
            requirements=dict(payload),
        )
        return self.task_control_service.create_task(
            request,
            idempotency_key=f"backfill:{requirements.batch_id}:{partition_index}:{suffix}",
            endpoint="/api/platform/v1/backfills/children",
        )

    def submit_partition(
        self,
        *,
        parent_task: TaskRecord | str,
        requirements: BackfillTaskRequirements,
        partition_index: int,
        requested_by: str,
        raw_requirements: Mapping[str, Any],
    ) -> BackfillPipelineSubmission:
        if partition_index < 0:
            raise BackfillError("BACKFILL_PARTITION_INVALID", "Backfill partition is invalid.", status_code=422)
        raw = self._submit(
            task_type="raw_ingestion", payload=raw_requirements, requirements=requirements,
            parent_task=parent_task, partition_index=partition_index, requested_by=requested_by,
            suffix="raw", refs=self._refs(requirements, parent_task),
        )
        return BackfillPipelineSubmission(raw_task_id=raw.task_id)

    def submit_canonical(
        self,
        *,
        parent_task: TaskRecord | str,
        raw_task: TaskRecord | str,
        requirements: BackfillTaskRequirements,
        partition_index: int,
        requested_by: str,
        canonical_requirements: Mapping[str, Any],
    ) -> BackfillPipelineSubmission:
        if partition_index < 0:
            raise BackfillError("BACKFILL_PARTITION_INVALID", "Backfill partition is invalid.", status_code=422)
        raw_id = self._task_id(raw_task)
        self._require_predecessor(
            raw_id, task_type="raw_ingestion", requirements=requirements,
            partition_index=partition_index, requested_by=requested_by, suffix="raw",
            refs=self._refs(requirements, parent_task),
        )
        canonical = self._submit(
            task_type="canonical_normalization", payload=canonical_requirements, requirements=requirements,
            parent_task=parent_task, partition_index=partition_index, requested_by=requested_by,
            suffix="canonical", refs=self._refs(requirements, parent_task, raw_id),
        )
        return BackfillPipelineSubmission(raw_task_id=raw_id, canonical_task_id=canonical.task_id)

    def submit_snapshot(
        self,
        *,
        parent_task: TaskRecord | str,
        raw_task: TaskRecord | str,
        canonical_task: TaskRecord | str,
        requirements: BackfillTaskRequirements,
        partition_index: int,
        requested_by: str,
        snapshot_requirements: Mapping[str, Any],
    ) -> BackfillPipelineSubmission:
        if partition_index < 0:
            raise BackfillError("BACKFILL_PARTITION_INVALID", "Backfill partition is invalid.", status_code=422)
        raw_id = self._task_id(raw_task)
        canonical_id = self._task_id(canonical_task)
        self._require_predecessor(
            raw_id, task_type="raw_ingestion", requirements=requirements,
            partition_index=partition_index, requested_by=requested_by, suffix="raw",
            refs=self._refs(requirements, parent_task),
        )
        self._require_predecessor(
            canonical_id, task_type="canonical_normalization", requirements=requirements,
            partition_index=partition_index, requested_by=requested_by, suffix="canonical",
            refs=self._refs(requirements, parent_task, raw_id),
        )
        snapshot_payload = dict(snapshot_requirements)
        snapshot_supersedes = snapshot_payload.get("correction_of_snapshot_id")
        if requirements.supersedes_id is None:
            if snapshot_supersedes is not None:
                raise BackfillError(
                    "BACKFILL_CORRECTION_LINEAGE_MISMATCH",
                    "Backfill correction lineage does not match the batch request.",
                    status_code=409,
                )
        elif snapshot_supersedes not in {None, requirements.supersedes_id}:
            raise BackfillError(
                "BACKFILL_CORRECTION_LINEAGE_MISMATCH",
                "Backfill correction lineage does not match the batch request.",
                status_code=409,
            )
        else:
            snapshot_payload["correction_of_snapshot_id"] = requirements.supersedes_id
        snapshot = self._submit(
            task_type="data_snapshot_build", payload=snapshot_payload, requirements=requirements,
            parent_task=parent_task, partition_index=partition_index, requested_by=requested_by,
            suffix="snapshot", refs=self._refs(requirements, parent_task, raw_id, canonical_id),
        )
        return BackfillPipelineSubmission(raw_task_id=raw_id, canonical_task_id=canonical_id, snapshot_task_id=snapshot.task_id)


class BackfillPipelineExecutor:
    """Run one isolated partition through the existing three task workers.

    The lease provider is injected so production scheduling remains owned by
    the existing Task Control Plane; tests can use the same worker contracts
    without a second queue or an in-memory scheduler.
    """

    def __init__(
        self,
        coordinator: BackfillPipelineCoordinator,
        *,
        lease_provider: Any,
        raw_worker: Any,
        canonical_worker: Any,
        snapshot_worker: Any,
        result_loader: Callable[[str, str], Any] | None = None,
    ) -> None:
        self.coordinator = coordinator
        self.lease_provider = lease_provider
        self.raw_worker = raw_worker
        self.canonical_worker = canonical_worker
        self.snapshot_worker = snapshot_worker
        self.result_loader = result_loader or self._default_result_loader()
        self.last_provider_run_refs: tuple[str, ...] = ()

    def _default_result_loader(self) -> Callable[[str, str], Any] | None:
        """Recover successful child results from existing immutable registries."""
        database = getattr(self.coordinator.task_control_service, "database", None)
        if database is None:
            return None

        def load(task_id: str, task_type: str) -> Any | None:
            from src.repositories.platform.canonical import CanonicalRepository
            from src.repositories.platform.raw_ingestion import RawIngestionRepository
            from src.repositories.platform.snapshot import SnapshotRepository

            with database.transaction() as session:
                if task_type == "raw_ingestion":
                    repository = RawIngestionRepository()
                    run = repository.get_provider_run_by_task(session, task_id)
                    raw = repository.get_raw_object_by_run(session, run.provider_run_id) if run else None
                    if run is None or raw is None or run.run_outcome is None or not run.raw_object_refs:
                        return None
                    if raw.raw_object_id not in run.raw_object_refs:
                        return None
                    return SimpleNamespace(provider_run=run, raw_object=raw)
                if task_type == "canonical_normalization":
                    repository = CanonicalRepository()
                    report = repository.get_quality_report_by_task(session, task_id)
                    partition = repository.get_partition(session, report.canonical_partition_id) if report and report.canonical_partition_id else None
                    if report is None or partition is None or report.quality_status.value in {"FAILED", "UNAVAILABLE"}:
                        return None
                    return SimpleNamespace(canonical_partition=partition, quality_report=report, published=True)
                if task_type == "data_snapshot_build":
                    repository = SnapshotRepository()
                    snapshot = repository.get_snapshot_by_task(session, task_id)
                    if snapshot is None:
                        return None
                    return SimpleNamespace(
                        snapshot=snapshot,
                        capability_certifications=repository.list_capabilities(session, snapshot.snapshot_id),
                        published=True,
                    )
            return None

        return load

    def _lease(self, task_id: str, task_type: str) -> TaskLease | None:
        lease = self.lease_provider(task_id, task_type)
        if lease is None:
            return None
        if lease.task.task_id != task_id or lease.task.task_type != task_type:
            raise BackfillError("BACKFILL_CHILD_LEASE_INVALID", "Backfill child task lease is invalid.", status_code=409, retryable=True)
        return lease

    def _cancel_child_after_parent_cancel(self, lease: TaskLease) -> None:
        request_cancel = getattr(self.coordinator.task_control_service, "request_cancel", None)
        acknowledge_cancel = getattr(self.coordinator.task_control_service, "acknowledge_cancel", None)
        if not callable(request_cancel) or not callable(acknowledge_cancel):
            return
        try:
            current = request_cancel(
                lease.task.task_id,
                reason_code="BACKFILL_PARENT_CANCEL_REQUESTED",
                actor_ref="backfill:parent",
            )
            if current.task_state is TaskState.RUNNING and current.cancel_requested_at is not None:
                acknowledge_cancel(lease.attempt.attempt_id, lease.lease_token)
        except TaskControlError as exc:
            if exc.error_code not in {
                "TASK_CANCEL_NOT_ALLOWED",
                "TASK_CANCEL_NOT_REQUESTED",
                "TASK_LEASE_LOST",
            }:
                raise

    def _execute_or_reuse(self, task_id: str, task_type: str, worker: Any, *, kwargs: Mapping[str, Any] | None = None) -> Any:
        lease = self._lease(task_id, task_type)
        if lease is not None:
            try:
                return worker.execute(lease, **dict(kwargs or {}))
            except TaskControlError as exc:
                if exc.error_code == "TASK_CANCEL_PENDING":
                    self._cancel_child_after_parent_cancel(lease)
                raise
        # A missing lease is only a recovery signal.  Before loading a
        # previously published result, re-read the authoritative Task Control
        # Plane record; a caller-provided or stale record must never authorize
        # reuse of a running, failed, cancelled, or unrelated task.
        try:
            details = self.coordinator.task_control_service.get_task(task_id)
        except TaskControlError as exc:
            raise BackfillError(
                "BACKFILL_CHILD_RESULT_UNAVAILABLE",
                "Backfill child result is unavailable for recovery.",
                status_code=409,
                retryable=True,
            ) from exc
        record = details.task
        if record.task_id != task_id or record.task_type != task_type:
            raise BackfillError(
                "BACKFILL_DEPENDENCY_MISMATCH",
                "Backfill dependency does not match the child task.",
                status_code=409,
            )
        if record.task_state is not TaskState.SUCCEEDED:
            raise BackfillError(
                "BACKFILL_DEPENDENCY_NOT_READY",
                "Backfill dependency has not succeeded.",
                status_code=409,
                retryable=record.task_state in {TaskState.ACCEPTED, TaskState.QUEUED, TaskState.BLOCKED, TaskState.LEASED, TaskState.RUNNING, TaskState.RETRY_WAIT},
            )
        if self.result_loader is None:
            raise BackfillError("BACKFILL_CHILD_RESULT_UNAVAILABLE", "Backfill child result is unavailable for recovery.", status_code=409, retryable=True)
        result = self.result_loader(task_id, task_type)
        if result is None:
            raise BackfillError("BACKFILL_CHILD_RESULT_UNAVAILABLE", "Backfill child result is unavailable for recovery.", status_code=409, retryable=True)
        return result

    def execute_partition(
        self,
        *,
        parent_task: TaskRecord | str,
        parent_lease: TaskLease | None = None,
        requirements: BackfillTaskRequirements,
        partition_index: int,
        requested_by: str,
        raw_requirements: Mapping[str, Any],
        canonical_requirements: Any,
        snapshot_requirements: Any,
        partition_rows: Mapping[str, list[Mapping[str, Any]]] | None = None,
    ) -> tuple[str, str, str]:
        publication_guard: Callable[[object], None] | None = None
        if parent_lease is not None:
            parent_task_id = self.coordinator._task_id(parent_task)
            if (
                parent_lease.task.task_id != parent_task_id
                or parent_lease.task.task_type != "backfill"
            ):
                raise BackfillError(
                    "BACKFILL_PARENT_LEASE_INVALID",
                    "Backfill parent lease is invalid.",
                    status_code=409,
                )
            assert_publishable = getattr(
                self.coordinator.task_control_service,
                "assert_attempt_publishable_in_session",
                None,
            )
            if not callable(assert_publishable):
                raise BackfillError(
                    "BACKFILL_PUBLICATION_FENCE_UNAVAILABLE",
                    "Backfill publication fence is unavailable.",
                    status_code=503,
                    retryable=True,
                )

            def publication_guard(session: object) -> None:
                assert_publishable(
                    session,
                    attempt_id=parent_lease.attempt.attempt_id,
                    lease_token=parent_lease.lease_token,
                    expected_task_id=parent_task_id,
                    expected_task_type="backfill",
                )

        raw_submission = self.coordinator.submit_partition(
            parent_task=parent_task, requirements=requirements, partition_index=partition_index,
            requested_by=requested_by, raw_requirements=raw_requirements,
        )
        raw_result = self._execute_or_reuse(
            raw_submission.raw_task_id,
            "raw_ingestion",
            self.raw_worker,
            kwargs={"publication_guard": publication_guard} if publication_guard is not None else None,
        )
        raw_object = getattr(raw_result, "raw_object", None)
        provider_run = getattr(raw_result, "provider_run", None)
        provider_run_id = getattr(provider_run, "provider_run_id", None)
        if raw_object is None or provider_run is None or not isinstance(provider_run_id, str):
            raise BackfillError("BACKFILL_RAW_NOT_PUBLISHED", "Backfill raw input was not published.", status_code=409, retryable=True)
        self.last_provider_run_refs = (provider_run_id,)

        canonical_payload = canonical_requirements(raw_result) if callable(canonical_requirements) else canonical_requirements
        canonical_submission = self.coordinator.submit_canonical(
            parent_task=parent_task, raw_task=raw_submission.raw_task_id, requirements=requirements,
            partition_index=partition_index, requested_by=requested_by, canonical_requirements=canonical_payload,
        )
        canonical_result = self._execute_or_reuse(
            canonical_submission.canonical_task_id or "",
            "canonical_normalization",
            self.canonical_worker,
            kwargs={"publication_guard": publication_guard} if publication_guard is not None else None,
        )
        canonical_partition = getattr(canonical_result, "canonical_partition", None)
        if canonical_partition is None or not getattr(canonical_result, "published", False):
            raise BackfillError("BACKFILL_CANONICAL_NOT_PUBLISHED", "Backfill canonical partition was not published.", status_code=409, retryable=True)

        snapshot_payload = snapshot_requirements(canonical_result) if callable(snapshot_requirements) else snapshot_requirements
        snapshot_submission = self.coordinator.submit_snapshot(
            parent_task=parent_task, raw_task=raw_submission.raw_task_id,
            canonical_task=canonical_submission.canonical_task_id or "", requirements=requirements,
            partition_index=partition_index, requested_by=requested_by, snapshot_requirements=snapshot_payload,
        )
        snapshot_result = self._execute_or_reuse(
            snapshot_submission.snapshot_task_id or "",
            "data_snapshot_build",
            self.snapshot_worker,
            kwargs={
                "partition_rows": partition_rows,
                **(
                    {"publication_guard": publication_guard}
                    if publication_guard is not None
                    else {}
                ),
            },
        )
        snapshot = getattr(snapshot_result, "snapshot", None)
        if snapshot is None or not getattr(snapshot_result, "published", False):
            raise BackfillError("BACKFILL_SNAPSHOT_NOT_PUBLISHED", "Backfill snapshot was not published.", status_code=409, retryable=True)
        return (raw_object.raw_object_id, canonical_partition.canonical_partition_id, snapshot.snapshot_id)


class BackfillWorker:
    """Executes one backfill task through the existing Durable Task Control Plane."""

    HANDLER_VERSION = "wp0207-backfill-v3"

    def __init__(
        self,
        task_control: TaskControlService,
        provider: BackfillProvider,
        *,
        publisher: BackfillPublisher | None = None,
        checkpoint_writer: CheckpointWriter | None = None,
        clock: Any | None = None,
        pipeline_executor: BackfillPipelineExecutor | None = None,
        pipeline_plan_factory: Any | None = None,
    ) -> None:
        self.task_control = task_control
        self.provider = provider
        self.publisher = publisher
        self.checkpoint_writer = checkpoint_writer
        # Checkpoint expiry must use the same clock as the Durable Task Control
        # Plane.  A test or isolated runtime may inject a deterministic control
        # clock; falling back to wall-clock time here can make ``expires_at``
        # precede the checkpoint's authoritative ``created_at``.
        control_clock = getattr(task_control, "_now", None)
        self.clock = clock or control_clock or (lambda: datetime.now(timezone.utc))
        self.pipeline_executor = pipeline_executor
        self.pipeline_plan_factory = pipeline_plan_factory

    @staticmethod
    def _checkpoint_hash(payload: dict[str, Any]) -> str:
        return compute_content_hash(payload)

    @classmethod
    def _checkpoint_input_hash(cls, requirements: BackfillTaskRequirements) -> str:
        return cls._checkpoint_hash({
            "batch_id": requirements.batch_id,
            "batch_type": requirements.batch_type.value,
            "date_from": requirements.date_from.isoformat(),
            "date_to": requirements.date_to.isoformat(),
            "dataset": requirements.dataset,
            "provider_policy_id": requirements.provider_policy_id,
            "dependency_task_ids": list(requirements.dependency_task_ids),
            "stage": requirements.stage.value,
            "dry_run": requirements.dry_run,
            "plan_only": requirements.plan_only,
            "supersedes_id": getattr(requirements, "supersedes_id", None),
        })

    def _validated_resume_partitions(
        self,
        lease: TaskLease,
        requirements: BackfillTaskRequirements,
        ranges: tuple[tuple[date, date], ...],
        resume_payload: dict[str, Any] | None,
        *,
        resume_checkpoint_id: str | None = None,
        resume_token: str | None = None,
    ) -> tuple[set[int], dict[str, Any]]:
        if (resume_checkpoint_id is None) != (resume_token is None) or (resume_payload is not None and resume_checkpoint_id is None):
            raise BackfillError("BACKFILL_CHECKPOINT_INVALID", "Backfill checkpoint cannot be resumed.", status_code=409)
        if resume_checkpoint_id is None:
            return set(), {}
        checkpoint_record = self.task_control.validate_checkpoint(
            resume_checkpoint_id,
            resume_token=resume_token or "",
            input_hash=self._checkpoint_input_hash(requirements),
            handler_version=self.HANDLER_VERSION,
        )
        if checkpoint_record is None or checkpoint_record.task_id != lease.task.task_id:
            raise BackfillError("BACKFILL_CHECKPOINT_INVALID", "Backfill checkpoint cannot be resumed.", status_code=409)
        try:
            path = self.task_control.resolver.resolve(checkpoint_record.storage_ref, require_exists=True)
            content = path.read_bytes()
            if len(content) != checkpoint_record.storage_ref.size_bytes or compute_bytes_hash(content) != checkpoint_record.checkpoint_hash:
                raise ValueError("checkpoint integrity mismatch")
            stored_payload = json.loads(content)
            if not isinstance(stored_payload, dict) or (resume_payload is not None and stored_payload != resume_payload):
                raise ValueError("checkpoint payload mismatch")
        except Exception as exc:
            raise BackfillError("BACKFILL_CHECKPOINT_INVALID", "Backfill checkpoint cannot be resumed.", status_code=409) from exc
        resume_payload = stored_payload
        required = {"batch_id", "task_id", "handler_version", "stage", "date_from", "date_to", "dataset", "input_hash", "completed_partitions"}
        if not required <= resume_payload.keys() or resume_payload["batch_id"] != requirements.batch_id or resume_payload["task_id"] != lease.task.task_id or resume_payload["handler_version"] != self.HANDLER_VERSION or resume_payload["stage"] != requirements.stage.value or resume_payload["date_from"] != requirements.date_from.isoformat() or resume_payload["date_to"] != requirements.date_to.isoformat() or resume_payload["dataset"] != requirements.dataset or resume_payload["input_hash"] != self._checkpoint_input_hash(requirements):
            raise BackfillError("BACKFILL_CHECKPOINT_INVALID", "Backfill checkpoint cannot be resumed.", status_code=409)
        partitions = resume_payload["completed_partitions"]
        if not isinstance(partitions, list) or any(type(index) is not int for index in partitions):
            raise BackfillError("BACKFILL_CHECKPOINT_INVALID", "Backfill checkpoint cannot be resumed.", status_code=409)
        completed = set(partitions)
        if any(index < 0 or index >= len(ranges) for index in completed):
            raise BackfillError("BACKFILL_CHECKPOINT_INVALID", "Backfill checkpoint cannot be resumed.", status_code=409)
        if partitions != list(range(len(partitions))):
            raise BackfillError("BACKFILL_CHECKPOINT_INVALID", "Backfill checkpoint cannot be resumed.", status_code=409)
        try:
            self._validate_checkpoint_accumulators(stored_payload, requirements, ranges, completed)
        except (TypeError, ValueError, KeyError) as exc:
            raise BackfillError("BACKFILL_CHECKPOINT_INVALID", "Backfill checkpoint cannot be resumed.", status_code=409) from exc
        return completed, stored_payload

    @staticmethod
    def _serialize_checkpoint_payload(payload: dict[str, Any]) -> bytes:
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")

    @staticmethod
    def _checkpoint_range_values(
        payload: Mapping[str, Any], plural_name: str, singular_name: str
    ) -> tuple[tuple[date, date], ...]:
        raw_values = payload.get(plural_name)
        if raw_values is None:
            single = payload.get(singular_name)
            raw_values = [single] if single is not None else []
        if not isinstance(raw_values, list):
            raise ValueError(f"{plural_name} must be a list")
        parsed: list[tuple[date, date]] = []
        for raw_range in raw_values:
            if not isinstance(raw_range, list) or len(raw_range) != 2:
                raise ValueError(f"{plural_name} contains an invalid range")
            start, end = (date.fromisoformat(value) for value in raw_range)
            if end < start or (start, end) in parsed:
                raise ValueError(f"{plural_name} contains an invalid range")
            parsed.append((start, end))
        return tuple(parsed)

    @classmethod
    def _validate_checkpoint_accumulators(
        cls,
        payload: Mapping[str, Any],
        requirements: BackfillTaskRequirements,
        ranges: tuple[tuple[date, date], ...],
        completed_partitions: set[int],
    ) -> None:
        range_to_index = {item: index for index, item in enumerate(ranges)}
        completed_range = payload.get("completed_range")
        if completed_range is not None:
            if not isinstance(completed_range, list) or len(completed_range) != 2:
                raise ValueError("completed_range is invalid")
            completed_value = tuple(date.fromisoformat(value) for value in completed_range)
            if not completed_partitions or completed_value[0] != requirements.date_from:
                raise ValueError("completed_range is inconsistent")
            completed_end_index = range_to_index.get(completed_value)
            if completed_end_index is None or not set(range(completed_end_index + 1)) <= completed_partitions:
                raise ValueError("completed_range is inconsistent")

        skipped_ranges = cls._checkpoint_range_values(payload, "skipped_ranges", "skipped_range")
        failed_ranges = cls._checkpoint_range_values(payload, "failed_ranges", "failed_range")
        skipped_indexes = {range_to_index[item] for item in skipped_ranges if item in range_to_index}
        failed_indexes = {range_to_index[item] for item in failed_ranges if item in range_to_index}
        if len(skipped_indexes) != len(skipped_ranges) or not skipped_indexes <= completed_partitions:
            raise ValueError("skipped_ranges are inconsistent")
        if len(failed_indexes) != len(failed_ranges) or failed_indexes & completed_partitions:
            raise ValueError("failed_ranges are inconsistent")

        differences_summary = payload.get("differences_summary")
        if differences_summary is not None and (
            not isinstance(differences_summary, str)
            or not differences_summary.strip()
            or len(differences_summary) > 2048
        ):
            raise ValueError("differences_summary is invalid")

        resource_usage = payload.get("resource_usage", {})
        if not isinstance(resource_usage, dict):
            raise ValueError("resource_usage is invalid")
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or value < 0
            for value in resource_usage.values()
        ):
            raise ValueError("resource_usage is invalid")

        ref_specs = (
            ("provider_run_refs", ResourceType.PROVIDER_RUN),
            ("raw_object_refs", ResourceType.RAW_OBJECT),
            ("canonical_partition_refs", ResourceType.CANONICAL_PARTITION),
            ("snapshot_refs", ResourceType.DATA_SNAPSHOT),
        )
        ref_values: dict[str, list[str]] = {}
        for field_name, expected_type in ref_specs:
            if field_name not in payload:
                continue
            values = payload[field_name]
            if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
                raise ValueError(f"{field_name} is invalid")
            if len(values) != len(set(values)):
                raise ValueError(f"{field_name} contains duplicates")
            for value in values:
                resource_type, _ = parse_resource_id(value)
                if resource_type is not expected_type:
                    raise ValueError(f"{field_name} is invalid")
            ref_values[field_name] = values
        lineage_fields = ("provider_run_refs", "raw_object_refs", "canonical_partition_refs")
        present_lineage = [field_name for field_name in lineage_fields if field_name in ref_values]
        if present_lineage and (
            len(present_lineage) != len(lineage_fields)
            or len({len(ref_values[field_name]) for field_name in lineage_fields}) != 1
        ):
            raise ValueError("checkpoint lineage is inconsistent")
        if "snapshot_refs" in ref_values and len(ref_values["snapshot_refs"]) > len(completed_partitions):
            raise ValueError("snapshot_refs are inconsistent")
        if "published_refs" in payload:
            published_refs = payload["published_refs"]
            if not isinstance(published_refs, list) or any(not isinstance(value, str) for value in published_refs) or len(published_refs) != len(set(published_refs)):
                raise ValueError("published_refs are invalid")

    def _write_checkpoint(self, lease: TaskLease, requirements: BackfillTaskRequirements, result: BackfillProviderResult, *, completed_partitions: set[int] | None = None) -> None:
        if self.checkpoint_writer is None:
            raise BackfillError("BACKFILL_CHECKPOINT_STORAGE_UNAVAILABLE", "Backfill checkpoint storage is unavailable.", status_code=503, retryable=True)
        skipped_ranges = tuple(result.skipped_ranges or ((result.skipped_range,) if result.skipped_range else ()))
        failed_ranges = tuple(result.failed_ranges or ((result.failed_range,) if result.failed_range else ()))
        payload = {
            "batch_id": requirements.batch_id,
            "task_id": lease.task.task_id,
            "attempt_id": lease.attempt.attempt_id,
            "handler_version": self.HANDLER_VERSION,
            "stage": requirements.stage.value,
            "date_from": requirements.date_from.isoformat(),
            "date_to": requirements.date_to.isoformat(),
            "dataset": requirements.dataset,
            "resource_usage": result.resource_usage or {},
            "differences_summary": result.differences_summary,
            "completed_range": [item.isoformat() for item in result.completed_range] if result.completed_range else None,
            "skipped_range": [item.isoformat() for item in result.skipped_range] if result.skipped_range else None,
            "failed_range": [item.isoformat() for item in result.failed_range] if result.failed_range else None,
            "skipped_ranges": [[start.isoformat(), end.isoformat()] for start, end in skipped_ranges],
            "failed_ranges": [[start.isoformat(), end.isoformat()] for start, end in failed_ranges],
            "published_refs": list(result.published_refs),
            "quality_events": list(result.quality_events),
            "provider_run_refs": list(result.provider_run_refs),
            "raw_object_refs": list(result.raw_object_refs),
            "canonical_partition_refs": list(result.canonical_partition_refs),
            "snapshot_refs": list(result.snapshot_refs),
            "provider_fallback": result.provider_fallback,
            "unavailable": result.unavailable,
            "completed_partitions": sorted(completed_partitions or set()),
            "input_hash": self._checkpoint_input_hash(requirements),
        }
        content = self._serialize_checkpoint_payload(payload)
        storage_ref = self.checkpoint_writer(task_id=lease.task.task_id, attempt_id=lease.attempt.attempt_id, payload=content)
        input_hash = self._checkpoint_input_hash(requirements)
        self.task_control.save_checkpoint(
            lease.attempt.attempt_id,
            lease.lease_token,
            phase=result.next_phase or requirements.stage.value,
            input_hash=input_hash,
            handler_version=self.HANDLER_VERSION,
            storage_ref=storage_ref,
            expires_at=self.clock() + timedelta(days=30),
        )

    def _cancel_at_safe_point(
        self,
        lease: TaskLease,
        requirements: BackfillTaskRequirements,
        *,
        checkpoint_result: BackfillProviderResult | None = None,
        completed_partitions: set[int] | None = None,
    ) -> BackfillExecutionResult | None:
        heartbeat = getattr(self.task_control, "heartbeat", None)
        if callable(heartbeat):
            heartbeat(lease.attempt.attempt_id, lease.lease_token)
        current = self.task_control.get_task(lease.task.task_id).task
        if current.cancel_requested_at is None:
            return None
        if checkpoint_result is not None:
            self._write_checkpoint(
                lease,
                requirements,
                checkpoint_result,
                completed_partitions=completed_partitions,
            )
        self.task_control.acknowledge_cancel(lease.attempt.attempt_id, lease.lease_token)
        return BackfillExecutionResult(
            lease.task.task_id,
            requirements.batch_id,
            BackfillStatus.CANCELLED,
            requirements.stage.value,
            failure_code="BACKFILL_CANCELLED",
        )

    def execute(self, lease: TaskLease, *, resume_payload: dict[str, Any] | None = None, resume_checkpoint_id: str | None = None, resume_token: str | None = None) -> BackfillExecutionResult:
        if lease.task.task_type != "backfill":
            raise TaskControlError("TASK_TYPE_UNSUPPORTED", "Worker does not support this task type.", status_code=422)
        self.task_control.start_attempt(lease.attempt.attempt_id, lease.lease_token)
        requirements = BackfillTaskRequirements.model_validate(lease.task.requirements)
        try:
            current = self.task_control.get_task(lease.task.task_id).task
            if current.cancel_requested_at is not None:
                self.task_control.acknowledge_cancel(lease.attempt.attempt_id, lease.lease_token)
                return BackfillExecutionResult(lease.task.task_id, requirements.batch_id, BackfillStatus.CANCELLED, requirements.stage.value, failure_code="BACKFILL_CANCELLED")
            ranges = plan_backfill_ranges(requirements)
            completed_partitions, resume_payload = self._validated_resume_partitions(lease, requirements, ranges, resume_payload, resume_checkpoint_id=resume_checkpoint_id, resume_token=resume_token)
            if any(not isinstance(index, int) or index < 0 or index >= len(ranges) for index in completed_partitions):
                raise BackfillError("BACKFILL_CHECKPOINT_INVALID", "Backfill checkpoint cannot be resumed.", status_code=409)
            published: list[str] = list(resume_payload.get("published_refs", []))
            quality_events: list[str] = list(resume_payload.get("quality_events", []))
            provider_runs: list[str] = list(resume_payload.get("provider_run_refs", []))
            raw_refs: list[str] = list(resume_payload.get("raw_object_refs", []))
            canonical_refs: list[str] = list(resume_payload.get("canonical_partition_refs", []))
            snapshot_refs: list[str] = list(resume_payload.get("snapshot_refs", []))
            resource_usage: dict[str, float] = dict(resume_payload.get("resource_usage", {}))
            differences_summary: str | None = resume_payload.get("differences_summary")
            skipped: list[tuple[date, date]] = list(
                self._checkpoint_range_values(resume_payload, "skipped_ranges", "skipped_range")
            )
            failed_ranges: list[tuple[date, date]] = list(
                self._checkpoint_range_values(resume_payload, "failed_ranges", "failed_range")
            )
            failed: tuple[date, date] | None = None
            completed_end: date | None = None
            resume_completed_range = resume_payload.get("completed_range")
            if resume_completed_range is not None:
                if not isinstance(resume_completed_range, list) or len(resume_completed_range) != 2:
                    raise BackfillError("BACKFILL_CHECKPOINT_INVALID", "Backfill checkpoint cannot be resumed.", status_code=409)
                try:
                    completed_start, completed_end = (
                        date.fromisoformat(value) for value in resume_completed_range
                    )
                except (TypeError, ValueError) as exc:
                    raise BackfillError("BACKFILL_CHECKPOINT_INVALID", "Backfill checkpoint cannot be resumed.", status_code=409) from exc
                if completed_start != requirements.date_from or completed_end not in {item[1] for item in ranges}:
                    raise BackfillError("BACKFILL_CHECKPOINT_INVALID", "Backfill checkpoint cannot be resumed.", status_code=409)
            last_processed_index = max(completed_partitions) if completed_partitions else None
            completion_prefix_open = last_processed_index is None or (
                completed_end is not None and completed_end == ranges[last_processed_index][1]
            )
            for index, (date_from, date_to) in enumerate(ranges):
                if index in completed_partitions:
                    continue
                cancelled = self._cancel_at_safe_point(
                    lease,
                    requirements,
                    completed_partitions=completed_partitions,
                )
                if cancelled is not None:
                    return cancelled
                part = requirements.model_copy(update={"date_from": date_from, "date_to": date_to})
                result = self.provider.run(part, resume_payload=resume_payload)
                quality_events.extend(result.quality_events)
                differences_summary = _merge_difference_summary(differences_summary, result.differences_summary)
                # When the existing task pipeline is configured, its registry
                # lineage is authoritative. Provider fixture refs describe the
                # planned source only and must not enter published-object
                # projection or checkpoint lineage.
                if self.pipeline_executor is None:
                    provider_runs.extend(result.provider_run_refs)
                    raw_refs.extend(result.raw_object_refs)
                    canonical_refs.extend(result.canonical_partition_refs)
                for key, value in (result.resource_usage or {}).items():
                    resource_usage[key] = resource_usage.get(key, 0.0) + value
                if result.failed_range is not None:
                    failed = result.failed_range
                    if failed not in failed_ranges:
                        failed_ranges.append(failed)
                    # Preserve all aggregate lineage and resource progress when a later
                    # partition fails. A failure checkpoint must be sufficient for a
                    # retry to resume at the failed partition without losing evidence
                    # from already completed partitions.
                    failure_checkpoint = BackfillProviderResult(
                        completed_range=(requirements.date_from, completed_end) if completed_end is not None else None,
                        skipped_range=skipped[-1] if skipped else None,
                        failed_range=failed,
                        skipped_ranges=tuple(skipped),
                        failed_ranges=tuple(failed_ranges),
                        differences_summary=differences_summary,
                        resource_usage=resource_usage,
                        quality_events=tuple(quality_events),
                        published_refs=tuple(published),
                        provider_run_refs=tuple(provider_runs),
                        raw_object_refs=tuple(raw_refs),
                        canonical_partition_refs=tuple(canonical_refs),
                        snapshot_refs=tuple(snapshot_refs),
                        provider_fallback=any("FALLBACK" in event for event in quality_events),
                        unavailable=any("UNAVAILABLE" in event for event in quality_events),
                        retryable=result.retryable,
                    )
                    self._write_checkpoint(lease, requirements, failure_checkpoint, completed_partitions=completed_partitions)
                    with self.task_control.database.transaction() as session:
                        self.task_control.record_failure_in_session(session, attempt_id=lease.attempt.attempt_id, lease_token=lease.lease_token, failure_code=result.quality_events[0] if result.quality_events else "BACKFILL_FAILED", retryable=result.retryable)
                    return BackfillExecutionResult(lease.task.task_id, requirements.batch_id, BackfillStatus.FAILED, requirements.stage.value, failure_code=result.quality_events[0] if result.quality_events else "BACKFILL_FAILED")
                quarantined = any(event.startswith("QUARANTINE") for event in result.quality_events)
                cancelled = self._cancel_at_safe_point(
                    lease,
                    requirements,
                    checkpoint_result=BackfillProviderResult(
                        completed_range=(requirements.date_from, completed_end) if completed_end is not None else None,
                        skipped_range=skipped[-1] if skipped else None,
                        skipped_ranges=tuple(skipped),
                        failed_ranges=tuple(failed_ranges),
                        differences_summary=differences_summary,
                        resource_usage=resource_usage,
                        quality_events=tuple(quality_events),
                        published_refs=tuple(published),
                        provider_run_refs=tuple(provider_runs),
                        raw_object_refs=tuple(raw_refs),
                        canonical_partition_refs=tuple(canonical_refs),
                        snapshot_refs=tuple(snapshot_refs),
                        provider_fallback=any("FALLBACK" in event for event in quality_events),
                        unavailable=any("UNAVAILABLE" in event for event in quality_events),
                    ),
                    completed_partitions=completed_partitions,
                )
                if cancelled is not None:
                    return cancelled
                if result.skipped_range is not None:
                    if result.skipped_range not in skipped:
                        skipped.append(result.skipped_range)
                for skipped_range in result.skipped_ranges:
                    if skipped_range not in skipped:
                        skipped.append(skipped_range)
                business_completed = False
                if not requirements.dry_run and not requirements.plan_only and not quarantined and result.completed_range is not None:
                    if self.pipeline_executor is not None:
                        if self.pipeline_plan_factory is None:
                            raise BackfillError(
                                "BACKFILL_PIPELINE_PLAN_UNAVAILABLE",
                                "Backfill pipeline plan is unavailable.",
                                status_code=503,
                                retryable=True,
                            )
                        plan = self.pipeline_plan_factory(part, result, index)
                        if not isinstance(plan, Mapping):
                            raise BackfillError(
                                "BACKFILL_PIPELINE_PLAN_INVALID",
                                "Backfill pipeline plan is invalid.",
                                status_code=422,
                            )
                        required_plan_keys = (
                            "raw_requirements",
                            "canonical_requirements",
                            "snapshot_requirements",
                            "partition_rows",
                        )
                        if any(key not in plan for key in required_plan_keys):
                            raise BackfillError(
                                "BACKFILL_PIPELINE_PLAN_INVALID",
                                "Backfill pipeline plan is invalid.",
                                status_code=422,
                            )
                        raw_id, canonical_id, snapshot_id = self.pipeline_executor.execute_partition(
                            parent_task=lease.task,
                            parent_lease=lease,
                            requirements=requirements,
                            partition_index=index,
                            requested_by=lease.task.requested_by,
                            raw_requirements=plan["raw_requirements"],
                            canonical_requirements=plan["canonical_requirements"],
                            snapshot_requirements=plan["snapshot_requirements"],
                            partition_rows=plan["partition_rows"],
                        )
                        for provider_run_id in getattr(self.pipeline_executor, "last_provider_run_refs", ()):
                            if provider_run_id not in provider_runs:
                                provider_runs.append(provider_run_id)
                        if raw_id not in raw_refs:
                            raw_refs.append(raw_id)
                        if canonical_id not in canonical_refs:
                            canonical_refs.append(canonical_id)
                        if snapshot_id not in snapshot_refs:
                            snapshot_refs.append(snapshot_id)
                        for ref in (canonical_id, snapshot_id):
                            if ref not in published:
                                published.append(ref)
                        business_completed = True
                    else:
                        if self.publisher is None:
                            raise BackfillError("BACKFILL_PUBLICATION_UNAVAILABLE", "Backfill publication is unavailable.", status_code=503, retryable=True)
                        publication_key = f"backfill:{requirements.batch_id}:{requirements.stage.value}:{index}:{date_from}:{date_to}"
                        refs = self.publisher.publish(part, result, idempotency_key=publication_key)
                        published.extend(refs)
                        publication = getattr(self.publisher, "get_publication", None)
                        if publication is not None:
                            snapshot = publication(publication_key)
                            snapshot_id = getattr(snapshot, "snapshot_id", None)
                            if isinstance(snapshot_id, str) and snapshot_id not in snapshot_refs:
                                snapshot_refs.append(snapshot_id)
                        business_completed = True
                if business_completed and completion_prefix_open:
                    completed_end = date_to
                else:
                    completion_prefix_open = False
                completed_partitions.add(index)
                checkpoint_result = BackfillProviderResult(completed_range=(requirements.date_from, completed_end) if completed_end is not None else None, skipped_range=skipped[-1] if skipped else None, skipped_ranges=tuple(skipped), failed_ranges=tuple(failed_ranges), differences_summary=differences_summary, published_refs=tuple(published), quality_events=tuple(quality_events), resource_usage=resource_usage, provider_run_refs=tuple(provider_runs), raw_object_refs=tuple(raw_refs), canonical_partition_refs=tuple(canonical_refs), snapshot_refs=tuple(snapshot_refs), provider_fallback=any("FALLBACK" in event for event in quality_events), unavailable=any("UNAVAILABLE" in event for event in quality_events))
                self._write_checkpoint(lease, requirements, checkpoint_result, completed_partitions=completed_partitions)
            aggregate = BackfillProviderResult(completed_range=(requirements.date_from, completed_end) if completed_end is not None else None, skipped_range=skipped[-1] if skipped else None, skipped_ranges=tuple(skipped), failed_ranges=tuple(failed_ranges), differences_summary=differences_summary, resource_usage=resource_usage, quality_events=tuple(quality_events), published_refs=tuple(published), provider_run_refs=tuple(provider_runs), raw_object_refs=tuple(raw_refs), canonical_partition_refs=tuple(canonical_refs), snapshot_refs=tuple(snapshot_refs), provider_fallback=any("FALLBACK" in event for event in quality_events), unavailable=any("UNAVAILABLE" in event for event in quality_events))
            self._write_checkpoint(lease, requirements, aggregate, completed_partitions=completed_partitions)
            degraded = bool(quality_events or skipped)
            with self.task_control.database.transaction() as session:
                # The original request remains immutable. Runtime progress is already
                # persisted in the append-only checkpoint written above; do not mutate
                # TaskRecord.requirements or its canonical request hash.
                self.task_control.complete_in_session(session, attempt_id=lease.attempt.attempt_id, lease_token=lease.lease_token, degraded=degraded)
            state = BackfillStatus.QUARANTINED if any(item.startswith("QUARANTINE") for item in quality_events) else BackfillStatus.UNAVAILABLE if any(item.startswith("UNAVAILABLE") for item in quality_events) else BackfillStatus.PARTIAL if degraded else BackfillStatus.COMPLETED
            return BackfillExecutionResult(lease.task.task_id, requirements.batch_id, state, requirements.stage.value, published_refs=tuple(published))
        except BackfillError as exc:
            self.task_control.record_failure(lease.attempt.attempt_id, lease.lease_token, failure_code=exc.error_code, retryable=exc.retryable)
            raise
        except TaskControlError as exc:
            if exc.error_code == "TASK_CANCEL_PENDING":
                current = self.task_control.get_task(lease.task.task_id).task
                if current.cancel_requested_at is not None:
                    self.task_control.acknowledge_cancel(
                        lease.attempt.attempt_id,
                        lease.lease_token,
                    )
                    return BackfillExecutionResult(
                        lease.task.task_id,
                        requirements.batch_id,
                        BackfillStatus.CANCELLED,
                        requirements.stage.value,
                        failure_code="BACKFILL_CANCELLED",
                    )
            raise
        except Exception as exc:
            try:
                self.task_control.record_failure(lease.attempt.attempt_id, lease.lease_token, failure_code="BACKFILL_WORKER_ERROR", retryable=False)
            except TaskControlError:
                pass
            raise BackfillError("BACKFILL_WORKER_ERROR", "Backfill worker failed.", status_code=500) from exc


@dataclass(frozen=True, slots=True)
class BackfillStageChainExecution:
    """Observable result of advancing an existing seven-stage Task chain."""

    projection: BackfillStageChainProjection
    executed_task_ids: tuple[str, ...] = ()
    stopped_task_id: str | None = None
    stopped_state: TaskState | None = None


class BackfillStageChainExecutor:
    """Advance a Backfill stage chain through the existing Durable Task plane.

    The executor deliberately does not introduce a queue or a second state
    machine.  Each iteration re-reads the persisted stage tasks, leases the
    first runnable task through ``lease_next`` (or an injected equivalent),
    delegates to the existing ``BackfillWorker`` contract, and reconciles the
    chain through ``BackfillService.create_stage_chain``.  A non-successful
    stage is observable and fences all later stages.
    """

    _RUNNABLE_STATES = frozenset({
        TaskState.ACCEPTED,
        TaskState.QUEUED,
        TaskState.RETRY_WAIT,
    })
    _TERMINAL_STATES = frozenset({
        TaskState.SUCCEEDED,
    })
    _STOP_STATES = frozenset({
        TaskState.BLOCKED,
        TaskState.DEGRADED,
        TaskState.FAILED,
        TaskState.CANCELLED,
        TaskState.LEASED,
        TaskState.RUNNING,
    })

    def __init__(
        self,
        task_control_service: Any,
        *,
        worker_factory: Callable[[TaskLease], Any],
        service: "BackfillService" | None = None,
        lease_provider: Callable[[str, str], TaskLease | None] | None = None,
        resume_loader: Callable[[TaskDetails], Mapping[str, Any] | None] | None = None,
    ) -> None:
        if not callable(worker_factory):
            raise TypeError("worker_factory must be callable")
        self.task_control_service = task_control_service
        self.service = service or BackfillService(task_control_service)
        self.worker_factory = worker_factory
        self.lease_provider = lease_provider
        self.resume_loader = resume_loader

    def _details(self, task_id: str) -> TaskDetails:
        details = self.task_control_service.get_task(task_id)
        candidate = getattr(details, "task", None)
        if candidate is None:
            raise BackfillError(
                "BACKFILL_STAGE_TASK_UNAVAILABLE",
                "Backfill stage task is unavailable.",
                status_code=409,
                retryable=True,
            )
        if candidate.task_id != task_id or candidate.task_type != "backfill":
            raise BackfillError(
                "BACKFILL_STAGE_TASK_MISMATCH",
                "Backfill stage task does not match the chain.",
                status_code=409,
            )
        return details

    @staticmethod
    def _is_plan_only_degraded(record: TaskRecord) -> bool:
        requirements = record.requirements
        return (
            record.task_state is TaskState.DEGRADED
            and bool(requirements.get("dry_run") or requirements.get("plan_only"))
        )

    def _next_stage(self, projection: BackfillStageChainProjection) -> tuple[TaskRecord, TaskDetails] | None:
        for batch in projection.batches:
            details = self._details(batch.task_id)
            record = details.task
            if record.task_state in self._TERMINAL_STATES or self._is_plan_only_degraded(record):
                continue
            if record.task_state in self._RUNNABLE_STATES or record.task_state in self._STOP_STATES:
                return record, details
            raise BackfillError(
                "BACKFILL_STAGE_STATE_UNSUPPORTED",
                "Backfill stage task state is unsupported.",
                status_code=409,
            )
        return None

    def _lease(self, record: TaskRecord, *, worker_id: str, lease_seconds: int) -> TaskLease | None:
        if self.lease_provider is not None:
            lease = self.lease_provider(record.task_id, record.task_type)
        else:
            lease = self.task_control_service.lease_next(
                worker_id=worker_id,
                worker_capabilities=("backfill",),
                lease_seconds=lease_seconds,
            )
        if lease is None:
            return None
        if lease.task.task_id != record.task_id or lease.task.task_type != "backfill":
            raise BackfillError(
                "BACKFILL_STAGE_LEASE_INVALID",
                "Backfill stage lease does not match the runnable stage.",
                status_code=409,
                retryable=True,
            )
        return lease

    def _resume_kwargs(self, details: TaskDetails) -> dict[str, Any]:
        if self.resume_loader is None:
            return {}
        loaded = self.resume_loader(details)
        if loaded is None:
            return {}
        if not isinstance(loaded, Mapping):
            raise BackfillError(
                "BACKFILL_CHECKPOINT_INVALID",
                "Backfill checkpoint cannot be resumed.",
                status_code=409,
            )
        allowed = {"resume_payload", "resume_checkpoint_id", "resume_token"}
        if set(loaded) - allowed:
            raise BackfillError(
                "BACKFILL_CHECKPOINT_INVALID",
                "Backfill checkpoint cannot be resumed.",
                status_code=409,
            )
        return dict(loaded)

    def execute(
        self,
        request: BackfillStageChainRequest,
        *,
        idempotency_key: str,
        worker_id: str = "backfill-stage-worker",
        lease_seconds: int = 60,
        max_stages: int | None = None,
    ) -> BackfillStageChainExecution:
        if not worker_id.strip() or lease_seconds <= 0:
            raise ValueError("worker_id and positive lease_seconds are required")
        if max_stages is not None and max_stages <= 0:
            raise ValueError("max_stages must be positive")

        projection = self.service.create_stage_chain(
            request,
            idempotency_key=idempotency_key,
        )
        executed: list[str] = []
        while max_stages is None or len(executed) < max_stages:
            projection = self.service.create_stage_chain(
                request,
                idempotency_key=idempotency_key,
            )
            next_stage = self._next_stage(projection)
            if next_stage is None:
                return BackfillStageChainExecution(
                    projection=projection,
                    executed_task_ids=tuple(executed),
                )
            record, details = next_stage
            if record.task_state not in self._RUNNABLE_STATES:
                return BackfillStageChainExecution(
                    projection=projection,
                    executed_task_ids=tuple(executed),
                    stopped_task_id=record.task_id,
                    stopped_state=record.task_state,
                )
            lease = self._lease(
                record,
                worker_id=f"{worker_id}:{record.requirements.get('stage', 'unknown').lower()}",
                lease_seconds=lease_seconds,
            )
            if lease is None:
                return BackfillStageChainExecution(
                    projection=projection,
                    executed_task_ids=tuple(executed),
                    stopped_task_id=record.task_id,
                    stopped_state=record.task_state,
                )
            worker = self.worker_factory(lease)
            if not callable(getattr(worker, "execute", None)):
                raise BackfillError(
                    "BACKFILL_STAGE_WORKER_UNAVAILABLE",
                    "Backfill stage worker is unavailable.",
                    status_code=503,
                    retryable=True,
                )
            result = worker.execute(lease, **self._resume_kwargs(details))
            executed.append(record.task_id)
            result_state = getattr(result, "batch_state", None)
            requirements = record.requirements
            plan_only_partial = (
                result_state is BackfillStatus.PARTIAL
                and bool(requirements.get("dry_run") or requirements.get("plan_only"))
            )
            persisted_state = self._details(record.task_id).task.task_state
            persisted_success = persisted_state is TaskState.SUCCEEDED
            persisted_plan_only_partial = self._is_plan_only_degraded(self._details(record.task_id).task)
            # A worker result never authorizes progression by itself. The durable
            # Task state must agree, otherwise the chain stops fail-closed.
            state_agrees = (
                result_state is BackfillStatus.COMPLETED and persisted_success
            ) or (
                plan_only_partial and persisted_plan_only_partial
            )
            # Plan-only/dry-run stages intentionally complete as DEGRADED because
            # they do not publish business objects. They may advance a matching
            # plan-only chain, but a degraded live stage must still fence later work.
            if not state_agrees:
                projection = self.service.create_stage_chain(
                    request,
                    idempotency_key=idempotency_key,
                )
                return BackfillStageChainExecution(
                    projection=projection,
                    executed_task_ids=tuple(executed),
                    stopped_task_id=record.task_id,
                    stopped_state=self._details(record.task_id).task.task_state,
                )

        projection = self.service.create_stage_chain(
            request,
            idempotency_key=idempotency_key,
        )
        return BackfillStageChainExecution(
            projection=projection,
            executed_task_ids=tuple(executed),
        )


class BackfillService:
    """Creates and projects backfill batches through the existing durable Task plane."""

    def __init__(self, task_control_service: TaskControlService | Any) -> None:
        self.task_control_service = task_control_service

    def create_batch(self, request: BackfillBatchRequest, *, idempotency_key: str) -> BackfillBatchProjection:
        return self._create_batch(
            request,
            idempotency_key=idempotency_key,
            endpoint="/api/platform/v1/backfills",
        )

    def create_stage_chain(
        self,
        request: BackfillStageChainRequest,
        *,
        idempotency_key: str,
    ) -> BackfillStageChainProjection:
        projections: list[BackfillBatchProjection] = []
        dependency_task_ids: tuple[str, ...] = ()
        for batch in request.batches:
            stage_request = batch.model_copy(
                update={"dependency_task_ids": dependency_task_ids}
            )
            stage_key = self._stage_chain_idempotency_key(idempotency_key, batch.stage)
            projection = self._create_batch(
                stage_request,
                idempotency_key=stage_key,
                endpoint="/api/platform/v1/backfills/stage-chain",
            )
            projections.append(projection)
            dependency_task_ids = (projection.task_id,)
        return BackfillStageChainProjection(batches=tuple(projections))

    @staticmethod
    def _stage_chain_idempotency_key(idempotency_key: str, stage: BackfillStage) -> str:
        candidate = f"{idempotency_key}:{stage.value.lower()}"
        if len(candidate) <= 255:
            return candidate
        digest = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()
        return f"backfill-stage-chain:{digest}:{stage.value.lower()}"

    def _create_batch(
        self,
        request: BackfillBatchRequest,
        *,
        idempotency_key: str,
        endpoint: str,
    ) -> BackfillBatchProjection:
        requirements = BackfillTaskRequirements(**request.model_dump(exclude={"requested_by"}))
        input_refs = (
            ResourceRef(resource_type=ResourceType.BACKFILL_BATCH, resource_id=request.batch_id),
            *(ResourceRef(resource_type=ResourceType.TASK, resource_id=task_id) for task_id in request.dependency_task_ids),
        )
        task_request = TaskCreateRequest(
            task_type="backfill", priority_class=PriorityClass.P5_PREVIEW_AND_MAINTENANCE,
            priority_value=request.priority, requested_by=request.requested_by, request_source="backfill:batch",
            input_refs=input_refs,
            requirements=requirements.model_dump(mode="json"),
        )
        dependency_states: dict[str, TaskState] = {}
        dependency_ready: dict[str, bool] = {}
        get_task = getattr(self.task_control_service, "get_task", None)
        if request.dependency_task_ids and not callable(get_task):
            raise BackfillError("BACKFILL_DEPENDENCY_UNAVAILABLE", "Backfill stage dependencies are unavailable.", status_code=503, retryable=True)
        if callable(get_task):
            for dependency_id in request.dependency_task_ids:
                try:
                    dependency = get_task(dependency_id)
                except TaskControlError as exc:
                    raise BackfillError("BACKFILL_DEPENDENCY_UNAVAILABLE", "Backfill stage dependency is unavailable.", status_code=409, retryable=exc.retryable) from exc
                dependency_record = getattr(dependency, "task", dependency)
                if dependency_record is None or dependency_record.task_id != dependency_id:
                    raise BackfillError("BACKFILL_DEPENDENCY_MISMATCH", "Backfill stage dependency does not match the requested task.", status_code=409)
                dependency_requirements = dependency_record.requirements
                try:
                    dependency_stage = BackfillStage(dependency_requirements.get("stage"))
                except (AttributeError, TypeError, ValueError) as exc:
                    raise BackfillError("BACKFILL_DEPENDENCY_MISMATCH", "Backfill stage dependency requirements are invalid.", status_code=409) from exc
                dependency_batch_type = getattr(dependency_requirements.get("batch_type"), "value", dependency_requirements.get("batch_type"))
                dependency_date_from = dependency_requirements.get("date_from")
                dependency_date_to = dependency_requirements.get("date_to")
                dependency_date_from = dependency_date_from.isoformat() if hasattr(dependency_date_from, "isoformat") else dependency_date_from
                dependency_date_to = dependency_date_to.isoformat() if hasattr(dependency_date_to, "isoformat") else dependency_date_to
                if (
                    dependency_record.task_type != "backfill"
                    or dependency_stage not in backfill_stage_dependencies(request.stage)
                    or dependency_batch_type != request.batch_type.value
                    or dependency_date_from != request.date_from.isoformat()
                    or dependency_date_to != request.date_to.isoformat()
                ):
                    raise BackfillError("BACKFILL_DEPENDENCY_MISMATCH", "Backfill stage dependency does not match the requested stage range.", status_code=409)
                dependency_states[dependency_id] = dependency_record.task_state
                dependency_requirements = dependency_record.requirements
                same_nonpublishing_mode = (
                    bool(request.dry_run or request.plan_only)
                    and request.dry_run == bool(dependency_requirements.get("dry_run"))
                    and request.plan_only == bool(dependency_requirements.get("plan_only"))
                )
                dependency_ready[dependency_id] = (
                    dependency_record.task_state is TaskState.SUCCEEDED
                    or (dependency_record.task_state is TaskState.DEGRADED and same_nonpublishing_mode)
                )
        unresolved = tuple(task_id for task_id in dependency_states if not dependency_ready.get(task_id, False))
        create_blocked_task = getattr(self.task_control_service, "create_blocked_task", None)
        if unresolved and callable(create_blocked_task):
            task = create_blocked_task(
                task_request,
                idempotency_key=idempotency_key,
                endpoint=endpoint,
                reason_code="BACKFILL_STAGE_DEPENDENCY",
                unblock_condition="dependencies_succeeded:" + ",".join(unresolved),
                actor_ref=request.requested_by,
            )
        else:
            task = self.task_control_service.create_task(task_request, idempotency_key=idempotency_key, endpoint=endpoint)
        if dependency_states and callable(get_task):
            current_state = getattr(task, "task_state", None)
            if unresolved and current_state is TaskState.QUEUED:
                block_task = getattr(self.task_control_service, "block_task", None)
                if not callable(block_task):
                    raise BackfillError("BACKFILL_DEPENDENCY_UNAVAILABLE", "Backfill stage dependency control is unavailable.", status_code=503, retryable=True)
                task = block_task(
                    task.task_id,
                    reason_code="BACKFILL_STAGE_DEPENDENCY",
                    unblock_condition="dependencies_succeeded:" + ",".join(unresolved),
                    actor_ref=request.requested_by,
                )
            elif not unresolved and current_state is TaskState.BLOCKED:
                unblock_task = getattr(self.task_control_service, "unblock_task", None)
                if not callable(unblock_task):
                    raise BackfillError("BACKFILL_DEPENDENCY_UNAVAILABLE", "Backfill stage dependency control is unavailable.", status_code=503, retryable=True)
                task = unblock_task(task.task_id, actor_ref=request.requested_by)
        return self._project(task)

    def get_batch(self, batch_id: str) -> BackfillBatchProjection:
        tasks, _, has_more = self.task_control_service.list_tasks(
            TaskListQuery(resource_id=batch_id, task_type="backfill", limit=2)
        )
        if not tasks:
            raise BackfillError("BACKFILL_BATCH_NOT_FOUND", "Backfill batch was not found.", status_code=404)
        if has_more or len(tasks) != 1:
            raise BackfillError(
                "BACKFILL_BATCH_AMBIGUOUS",
                "Backfill batch has multiple task records.",
                status_code=409,
            )
        details_loader = getattr(self.task_control_service, "get_task", None)
        details = details_loader(tasks[0].task_id) if callable(details_loader) else tasks[0]
        return self._project(details)

    def get_stage_chain(self, batch_id: str) -> BackfillStageChainProjection:
        """Project the linked stage prefix/suffix through the existing Task plane.

        Stage-chain creation deliberately gives each stage its own ``batch_id``.
        A lookup therefore starts at one anchor task and follows the persisted
        predecessor/successor task references instead of assuming all stages
        share the same resource id. Ambiguous or malformed links fail closed.
        """
        tasks, _, has_more = self.task_control_service.list_tasks(
            TaskListQuery(resource_id=batch_id, task_type="backfill", limit=7)
        )
        if not tasks:
            raise BackfillError("BACKFILL_BATCH_NOT_FOUND", "Backfill batch was not found.", status_code=404)
        if has_more:
            raise BackfillError(
                "BACKFILL_STAGE_CHAIN_INVALID",
                "Backfill stage chain anchor is ambiguous.",
                status_code=409,
            )

        details_loader = getattr(self.task_control_service, "get_task", None)
        if not callable(details_loader):
            # 保持只返回已查询记录的兼容能力；真实控制面有 get_task 时走
            # 下方的前后遍历，以便从任意阶段 batch_id 还原完整链。
            projections: list[BackfillBatchProjection] = []
            try:
                for task in tasks:
                    projections.append(self._project(task))
            except BackfillError:
                raise
            except (TypeError, ValueError) as exc:
                raise BackfillError(
                    "BACKFILL_STAGE_CHAIN_INVALID",
                    "Backfill stage chain could not be projected.",
                    status_code=409,
                ) from exc
            if batch_id not in {projection.batch_id for projection in projections}:
                raise BackfillError(
                    "BACKFILL_STAGE_CHAIN_INVALID",
                    "Backfill stage chain does not match the requested batch.",
                    status_code=409,
                )
            if len({projection.stage for projection in projections}) != len(projections):
                raise BackfillError(
                    "BACKFILL_STAGE_CHAIN_INVALID",
                    "Backfill stage chain contains duplicate stages.",
                    status_code=409,
                )
            ordered = tuple(sorted(projections, key=lambda item: _BACKFILL_STAGE_ORDER.index(item.stage)))
            try:
                return BackfillStageChainProjection(batches=ordered)
            except ValueError as exc:
                raise BackfillError(
                    "BACKFILL_STAGE_CHAIN_INVALID",
                    "Backfill stage chain is not in the required order.",
                    status_code=409,
                ) from exc

        if len(tasks) != 1:
            raise BackfillError(
                "BACKFILL_STAGE_CHAIN_INVALID",
                "Backfill stage chain anchor is ambiguous.",
                status_code=409,
            )

        loaded: dict[str, TaskDetails | TaskRecord] = {}

        def load(task_id: str) -> tuple[TaskDetails | TaskRecord, TaskRecord]:
            if task_id in loaded:
                details = loaded[task_id]
            else:
                try:
                    details = details_loader(task_id)
                except TaskControlError:
                    raise
                except (KeyError, TypeError, ValueError) as exc:
                    raise BackfillError(
                        "BACKFILL_STAGE_CHAIN_INVALID",
                        "Backfill stage dependency could not be loaded.",
                        status_code=409,
                    ) from exc
                loaded[task_id] = details
            record = details.task if isinstance(details, TaskDetails) else getattr(details, "task", details)
            if not isinstance(record, TaskRecord):
                raise BackfillError(
                    "BACKFILL_STAGE_CHAIN_INVALID",
                    "Backfill stage dependency is invalid.",
                    status_code=409,
                )
            projection_details = details if isinstance(details, TaskDetails) else record
            return projection_details, record

        def requirements(record: TaskRecord) -> BackfillTaskRequirements:
            try:
                return BackfillTaskRequirements.model_validate(record.requirements)
            except (TypeError, ValueError) as exc:
                raise BackfillError(
                    "BACKFILL_STAGE_CHAIN_INVALID",
                    "Backfill stage requirements are invalid.",
                    status_code=409,
                ) from exc

        def assert_linked_scope(current: TaskRecord, candidate: TaskRecord) -> None:
            current_req = requirements(current)
            candidate_req = requirements(candidate)
            current_stage_index = _BACKFILL_STAGE_ORDER.index(current_req.stage)
            candidate_stage_index = _BACKFILL_STAGE_ORDER.index(candidate_req.stage)
            if candidate_stage_index != current_stage_index + 1:
                raise BackfillError(
                    "BACKFILL_STAGE_CHAIN_INVALID",
                    "Backfill stage chain contains an invalid stage dependency.",
                    status_code=409,
                )
            if (
                candidate.task_type != "backfill"
                or candidate_req.batch_type is not current_req.batch_type
                or candidate_req.date_from != current_req.date_from
                or candidate_req.date_to != current_req.date_to
                or candidate_req.dry_run != current_req.dry_run
                or candidate_req.plan_only != current_req.plan_only
            ):
                raise BackfillError(
                    "BACKFILL_STAGE_CHAIN_INVALID",
                    "Backfill stage chain scope does not match.",
                    status_code=409,
                )

        anchor_details, anchor = load(tasks[0].task_id)
        anchor_req = requirements(anchor)
        if anchor_req.batch_id != batch_id or anchor.task_type != "backfill":
            raise BackfillError(
                "BACKFILL_STAGE_CHAIN_INVALID",
                "Backfill stage chain does not match the requested batch.",
                status_code=409,
            )

        records: dict[str, TaskRecord] = {anchor.task_id: anchor}
        details_by_id: dict[str, TaskDetails | TaskRecord] = {anchor.task_id: anchor_details}
        seen = {anchor.task_id}

        current = anchor
        while True:
            current_req = requirements(current)
            dependencies = tuple(current_req.dependency_task_ids)
            if not dependencies:
                break
            if len(dependencies) != 1 or dependencies[0] in seen:
                raise BackfillError(
                    "BACKFILL_STAGE_CHAIN_INVALID",
                    "Backfill stage chain contains an invalid predecessor link.",
                    status_code=409,
                )
            parent_details, parent = load(dependencies[0])
            parent_req = requirements(parent)
            current_stage_index = _BACKFILL_STAGE_ORDER.index(current_req.stage)
            if (
                parent.task_type != "backfill"
                or current_stage_index == 0
                or parent_req.stage is not _BACKFILL_STAGE_ORDER[current_stage_index - 1]
            ):
                raise BackfillError(
                    "BACKFILL_STAGE_CHAIN_INVALID",
                    "Backfill stage chain contains an invalid predecessor link.",
                    status_code=409,
                )
            if (
                parent_req.batch_type is not current_req.batch_type
                or parent_req.date_from != current_req.date_from
                or parent_req.date_to != current_req.date_to
                or parent_req.dry_run != current_req.dry_run
                or parent_req.plan_only != current_req.plan_only
            ):
                raise BackfillError(
                    "BACKFILL_STAGE_CHAIN_INVALID",
                    "Backfill stage chain scope does not match.",
                    status_code=409,
                )
            records[parent.task_id] = parent
            details_by_id[parent.task_id] = parent_details
            seen.add(parent.task_id)
            current = parent

        current = anchor
        while True:
            children, _, children_have_more = self.task_control_service.list_tasks(
                TaskListQuery(resource_id=current.task_id, task_type="backfill", limit=7)
            )
            candidates: list[tuple[TaskDetails | TaskRecord, TaskRecord]] = []
            for task in children:
                if task.task_id == current.task_id:
                    continue
                child_details, child = load(task.task_id)
                child_req = requirements(child)
                if current.task_id in child_req.dependency_task_ids:
                    candidates.append((child_details, child))
            if children_have_more or len(candidates) > 1:
                raise BackfillError(
                    "BACKFILL_STAGE_CHAIN_INVALID",
                    "Backfill stage chain has ambiguous successors.",
                    status_code=409,
                )
            if not candidates:
                break
            child_details, child = candidates[0]
            if child.task_id in seen:
                raise BackfillError(
                    "BACKFILL_STAGE_CHAIN_INVALID",
                    "Backfill stage chain contains a cycle.",
                    status_code=409,
                )
            assert_linked_scope(current, child)
            records[child.task_id] = child
            details_by_id[child.task_id] = child_details
            seen.add(child.task_id)
            current = child
            if len(records) > len(_BACKFILL_STAGE_ORDER):
                raise BackfillError(
                    "BACKFILL_STAGE_CHAIN_INVALID",
                    "Backfill stage chain exceeds the roadmap length.",
                    status_code=409,
                )

        projections: list[BackfillBatchProjection] = []
        try:
            for task_id in records:
                projections.append(self._project(details_by_id[task_id]))
        except BackfillError:
            raise
        except (TypeError, ValueError) as exc:
            raise BackfillError(
                "BACKFILL_STAGE_CHAIN_INVALID",
                "Backfill stage chain could not be projected.",
                status_code=409,
            ) from exc

        if len({projection.stage for projection in projections}) != len(projections):
            raise BackfillError(
                "BACKFILL_STAGE_CHAIN_INVALID",
                "Backfill stage chain contains duplicate stages.",
                status_code=409,
            )

        ordered = tuple(sorted(projections, key=lambda item: _BACKFILL_STAGE_ORDER.index(item.stage)))
        try:
            return BackfillStageChainProjection(batches=ordered)
        except ValueError as exc:
            raise BackfillError(
                "BACKFILL_STAGE_CHAIN_INVALID",
                "Backfill stage chain is not in the required order.",
                status_code=409,
            ) from exc

    def list_batches(self, query: TaskListQuery) -> tuple[tuple[BackfillBatchProjection, ...], str | None, bool]:
        task_query = query.model_copy(update={"task_type": "backfill"})
        tasks, next_cursor, has_more = self.task_control_service.list_tasks(task_query)
        details_loader = getattr(self.task_control_service, "get_task", None)
        projections = tuple(
            self._project(details_loader(task.task_id) if callable(details_loader) else task)
            for task in tasks
        )
        return projections, next_cursor, has_more

    def _checkpoint_payload(self, details: TaskDetails) -> dict[str, Any] | None:
        checkpoints = details.checkpoints
        resolver = getattr(self.task_control_service, "resolver", None)
        if not checkpoints or resolver is None:
            return None
        attempt_numbers = {attempt.attempt_id: attempt.attempt_number for attempt in details.attempts}
        checkpoint = max(
            checkpoints,
            key=lambda item: (attempt_numbers.get(item.attempt_id, 0), item.created_at, item.sequence),
        )
        try:
            path = resolver.resolve(checkpoint.storage_ref, require_exists=True)
            content = path.read_bytes()
            if len(content) != checkpoint.storage_ref.size_bytes or compute_bytes_hash(content) != checkpoint.checkpoint_hash:
                raise ValueError("checkpoint integrity mismatch")
            payload = json.loads(content)
        except (OSError, ValueError, TypeError, json.JSONDecodeError, KeyError) as exc:
            raise BackfillError(
                "BACKFILL_CHECKPOINT_INVALID",
                "Backfill checkpoint cannot be read.",
                status_code=409,
            ) from exc
        if not isinstance(payload, dict):
            raise BackfillError("BACKFILL_CHECKPOINT_INVALID", "Backfill checkpoint cannot be read.", status_code=409)
        if payload.get("task_id") != details.task.task_id or payload.get("batch_id") != details.task.requirements.get("batch_id"):
            raise BackfillError("BACKFILL_CHECKPOINT_INVALID", "Backfill checkpoint cannot be read.", status_code=409)
        if payload.get("handler_version") != BackfillWorker.HANDLER_VERSION:
            raise BackfillError("BACKFILL_CHECKPOINT_INVALID", "Backfill checkpoint cannot be read.", status_code=409)
        payload["checkpoint_phase"] = checkpoint.phase
        return payload

    def _project(self, task: TaskRecord | TaskDetails) -> BackfillBatchProjection:
        details = task if isinstance(task, TaskDetails) else None
        task_record = details.task if details is not None else task
        req_data = dict(task_record.requirements)
        payload = self._checkpoint_payload(details) if details is not None else None
        if payload is not None:
            for field in (
                "checkpoint_phase", "differences_summary", "resource_usage", "quality_events",
                "provider_run_refs", "raw_object_refs", "canonical_partition_refs", "snapshot_refs",
                "provider_fallback", "skipped_ranges", "failed_ranges",
            ):
                if field in payload:
                    req_data[field] = payload[field]
            for field in ("completed_range", "skipped_range", "failed_range"):
                value = payload.get(field)
                req_data[field] = tuple(date.fromisoformat(item) for item in value) if value else None
            for field in ("skipped_ranges", "failed_ranges"):
                req_data[field] = tuple(
                    tuple(date.fromisoformat(item) for item in value)
                    for value in payload.get(field, ())
                )
        req = BackfillTaskRequirements.model_validate(req_data)
        return self.project(task_record.model_copy(update={"requirements": req.model_dump(mode="python")}))

    @staticmethod
    def project(task: TaskRecord) -> BackfillBatchProjection:
        """保持纯 TaskRecord 调用方兼容；带 checkpoint 的入口使用实例方法。"""
        req = BackfillTaskRequirements.model_validate(task.requirements)
        state = {TaskState.ACCEPTED: BackfillStatus.PLANNED, TaskState.QUEUED: BackfillStatus.PLANNED, TaskState.LEASED: BackfillStatus.RUNNING, TaskState.RUNNING: BackfillStatus.RUNNING, TaskState.RETRY_WAIT: BackfillStatus.PAUSED, TaskState.BLOCKED: BackfillStatus.PAUSED, TaskState.DEGRADED: BackfillStatus.PARTIAL, TaskState.SUCCEEDED: BackfillStatus.COMPLETED, TaskState.FAILED: BackfillStatus.FAILED, TaskState.CANCELLED: BackfillStatus.CANCELLED}.get(task.task_state, BackfillStatus.FAILED)
        if req.quality_events and any(item.startswith("QUARANTINE") for item in req.quality_events):
            state = BackfillStatus.QUARANTINED
        elif req.quality_events and any(item.startswith("UNAVAILABLE") for item in req.quality_events):
            state = BackfillStatus.UNAVAILABLE
        return BackfillBatchProjection(batch_id=req.batch_id, task_id=task.task_id, batch_state=state, batch_type=req.batch_type, stage=req.stage, date_from=req.date_from, date_to=req.date_to, dataset=req.dataset, provider_policy_id=req.provider_policy_id, priority=req.priority, dry_run=req.dry_run, plan_only=req.plan_only, dependency_task_ids=req.dependency_task_ids, failure_code=task.failure_code, blocked_reason_code=task.blocked_reason_code, unblock_condition=task.unblock_condition, checkpoint_phase=req.checkpoint_phase, completed_range=req.completed_range, skipped_range=req.skipped_range, failed_range=req.failed_range, skipped_ranges=req.skipped_ranges, failed_ranges=req.failed_ranges, differences_summary=req.differences_summary, resource_usage=req.resource_usage, quality_events=req.quality_events, provider_run_refs=req.provider_run_refs, raw_object_refs=req.raw_object_refs, canonical_partition_refs=req.canonical_partition_refs, snapshot_refs=req.snapshot_refs, provider_fallback=req.provider_fallback, supersedes_id=req.supersedes_id)


__all__ = ["BackfillError", "BackfillProviderResult", "BackfillWorker", "BackfillPipelineCoordinator", "BackfillPipelineExecutor", "BackfillPipelineSubmission", "BackfillStageChainExecution", "BackfillStageChainExecutor", "BackfillService", "DeterministicBackfillProvider", "DeterministicBackfillPublisher", "BackfillFixturePublication", "BackfillExecutionResult", "backfill_stage_dependencies", "plan_backfill_ranges"]\n