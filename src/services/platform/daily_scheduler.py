from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Callable, Iterable

from src.schemas.platform import PriorityClass, TaskCreateRequest
from src.schemas.platform.scheduler import (
    DAILY_SCHEDULE_TIMEZONE,
    DailySchedulePhase,
    DailySchedulePhaseTaskRequirements,
    DailySchedulePlan,
    DailyScheduleSlot,
)


_PHASE_TIMES = {
    DailySchedulePhase.PREFLIGHT: time(15, 50),
    DailySchedulePhase.CORE_INGESTION: time(16, 0),
    DailySchedulePhase.NORMALIZATION_QUALITY: time(16, 20),
    DailySchedulePhase.PROVISIONAL_SNAPSHOT: time(16, 30),
    DailySchedulePhase.SUPPLEMENTAL_DECISION: time(16, 40),
    DailySchedulePhase.BACKTEST_CORE_CERTIFICATION: time(17, 10),
    DailySchedulePhase.REVIEW_CAPABILITY_TARGET: time(17, 30),
    DailySchedulePhase.FORMAL_DEADLINE: time(19, 0),
    DailySchedulePhase.CORRECTION_AUDIT: time(20, 30),
}


@dataclass(frozen=True, slots=True)
class SupplementalDecision:
    use_supplemental: bool
    provider_id: str | None
    reason_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FormalDeadlineDecision:
    rejected: bool
    failure_code: str | None
    provisional_snapshot_id: str | None
    allow_formal_prediction: bool
    allow_formal_backtest: bool


@dataclass(frozen=True, slots=True)
class ScheduledPhaseSubmission:
    phase: DailySchedulePhase
    task_id: str
    idempotency_key: str
    requirements: DailySchedulePhaseTaskRequirements


@dataclass(frozen=True, slots=True)
class DailyScheduleResult:
    skipped: bool
    skip_reason: str | None
    submissions: tuple[ScheduledPhaseSubmission, ...]


class DailySchedulerService:
    """Build and submit deterministic daily phase tasks to the durable task plane."""

    def __init__(
        self,
        task_control,
        trading_day_resolver: Callable[[date], bool] | None = None,
        *,
        primary_provider_id: str = "a_stock_data",
        supplemental_provider_ids: tuple[str, ...] = ("financial_api",),
        clock: Callable[[], datetime] | None = None,
        max_primary_attempts: int = 2,
    ) -> None:
        if not primary_provider_id.strip():
            raise ValueError("primary_provider_id cannot be blank")
        if not supplemental_provider_ids or len(supplemental_provider_ids) != len(set(supplemental_provider_ids)):
            raise ValueError("supplemental_provider_ids must be non-empty and unique")
        if max_primary_attempts < 1:
            raise ValueError("max_primary_attempts must be positive")
        self.task_control = task_control
        self.trading_day_resolver = trading_day_resolver or (lambda _: True)
        self.primary_provider_id = primary_provider_id
        self.supplemental_provider_ids = tuple(supplemental_provider_ids)
        self.clock = clock
        self.max_primary_attempts = max_primary_attempts

    @staticmethod
    def idempotency_key(schedule_version: str, trade_date: date, phase: DailySchedulePhase | str) -> str:
        normalized_phase = phase.value if isinstance(phase, DailySchedulePhase) else str(phase)
        return f"daily-schedule:{schedule_version}:{trade_date.isoformat()}:{normalized_phase}"

    @staticmethod
    def _phase_time(phase: DailySchedulePhase) -> time:
        return _PHASE_TIMES[phase]

    @staticmethod
    def _at_local_time(trade_date: date, local_time: time) -> datetime:
        return datetime.combine(trade_date, local_time, tzinfo=DAILY_SCHEDULE_TIMEZONE)

    @staticmethod
    def _validate_now(now: datetime) -> datetime:
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("scheduler clock must return a timezone-aware datetime")
        return now.astimezone(DAILY_SCHEDULE_TIMEZONE)

    def _now(self, now: datetime | None) -> datetime:
        value = now if now is not None else (self.clock() if self.clock is not None else datetime.now(DAILY_SCHEDULE_TIMEZONE))
        return self._validate_now(value)

    def plan_day(self, trade_date: date, schedule_version: str = "1.0.0") -> DailySchedulePlan:
        is_trading_day = bool(self.trading_day_resolver(trade_date))
        return DailySchedulePlan(
            schedule_version=schedule_version,
            trade_date=trade_date,
            timezone="Asia/Shanghai",
            trading_day=is_trading_day,
            slots=tuple(DailyScheduleSlot(phase=phase, local_time=self._phase_time(phase)) for phase in DailySchedulePhase),
        )

    def build_phase_requirements(
        self,
        trade_date: date,
        phase: DailySchedulePhase,
        *,
        schedule_version: str = "1.0.0",
        now: datetime | None = None,
        dependency_task_ids: Iterable[str] = (),
        correction_of_snapshot_id: str | None = None,
        snapshot_publication_status=None,
        quality_gaps: Iterable[str] = (),
        degradation_reasons: Iterable[str] = (),
    ) -> DailySchedulePhaseTaskRequirements:
        del now  # Scheduling timestamps are derived from the immutable phase SLA.
        normalized_phase = phase if isinstance(phase, DailySchedulePhase) else DailySchedulePhase(phase)
        publication_status = snapshot_publication_status
        if publication_status is None:
            from src.schemas.platform import SnapshotPublicationStatus

            publication_status = SnapshotPublicationStatus.PROVISIONAL
        return DailySchedulePhaseTaskRequirements(
            schedule_version=schedule_version,
            trade_date=trade_date,
            phase=normalized_phase,
            scheduled_at=self._at_local_time(trade_date, self._phase_time(normalized_phase)),
            timezone="Asia/Shanghai",
            formal_deadline_at=self._at_local_time(trade_date, time(19, 0)),
            dependency_task_ids=tuple(dependency_task_ids),
            primary_provider_id=self.primary_provider_id,
            supplemental_provider_ids=self.supplemental_provider_ids,
            snapshot_publication_status=publication_status,
            revision_kind=(
                "CORRECTION" if correction_of_snapshot_id is not None else "INITIAL"
            ),
            correction_of_snapshot_id=correction_of_snapshot_id,
            quality_gaps=tuple(quality_gaps),
            degradation_reasons=tuple(degradation_reasons),
        )

    def schedule_phase(
        self,
        trade_date: date,
        phase: DailySchedulePhase,
        *,
        schedule_version: str = "1.0.0",
        dependency_task_ids: Iterable[str] = (),
        correction_of_snapshot_id: str | None = None,
        now: datetime | None = None,
    ) -> ScheduledPhaseSubmission:
        requirements = self.build_phase_requirements(
            trade_date,
            phase,
            schedule_version=schedule_version,
            now=now,
            dependency_task_ids=dependency_task_ids,
            correction_of_snapshot_id=correction_of_snapshot_id,
        )
        request = TaskCreateRequest(
            task_type="daily_schedule_phase",
            requested_by="scheduler:daily",
            request_source="daily_scheduler",
            priority_class=PriorityClass.P0_DATA_CERTIFICATION,
            priority_value=0,
            requirements=requirements.model_dump(mode="python"),
        )
        key = self.idempotency_key(schedule_version, trade_date, phase)
        created = self.task_control.create_task(
            request,
            idempotency_key=key,
            endpoint="/api/platform/v1/daily-schedules",
        )
        task_id = getattr(created, "task_id", created)
        if not isinstance(task_id, str) or not task_id:
            raise TypeError("task control must return a task id or TaskRecord")
        return ScheduledPhaseSubmission(
            phase=requirements.phase,
            task_id=task_id,
            idempotency_key=key,
            requirements=requirements,
        )

    def schedule_day(
        self,
        trade_date: date,
        *,
        schedule_version: str = "1.0.0",
        now: datetime | None = None,
        correction_of_snapshot_id: str | None = None,
    ) -> DailyScheduleResult:
        del now  # The schedule is created for the full trading-day plan, not at wall-clock time.
        plan = self.plan_day(trade_date, schedule_version=schedule_version)
        if not plan.trading_day:
            return DailyScheduleResult(skipped=True, skip_reason="NON_TRADING_DAY", submissions=())

        submissions: list[ScheduledPhaseSubmission] = []
        dependency_ids: tuple[str, ...] = ()
        for slot in plan.slots:
            submission = self.schedule_phase(
                trade_date,
                slot.phase,
                schedule_version=schedule_version,
                dependency_task_ids=dependency_ids,
                correction_of_snapshot_id=(
                    correction_of_snapshot_id if slot.phase is DailySchedulePhase.CORRECTION_AUDIT else None
                ),
            )
            submissions.append(submission)
            dependency_ids = (submission.task_id,)
        return DailyScheduleResult(skipped=False, skip_reason=None, submissions=tuple(submissions))

    def decide_supplemental(
        self,
        *,
        primary_attempts: int,
        coverage_ratio: float,
        quality_gaps: Iterable[str],
        schema_drift: bool,
        cross_check_required: bool,
    ) -> SupplementalDecision:
        if primary_attempts < 0:
            raise ValueError("primary_attempts cannot be negative")
        if not 0.0 <= coverage_ratio <= 1.0:
            raise ValueError("coverage_ratio must be between 0 and 1")
        reasons: list[str] = []
        if primary_attempts >= self.max_primary_attempts:
            reasons.append("PRIMARY_ATTEMPTS_EXHAUSTED")
        if coverage_ratio < 1.0 or tuple(quality_gaps):
            reasons.append("QUALITY_GAP")
        if schema_drift:
            reasons.append("SCHEMA_DRIFT")
        if cross_check_required:
            reasons.append("CROSS_CHECK_REQUIRED")
        if not reasons:
            return SupplementalDecision(False, None, ())
        return SupplementalDecision(True, self.supplemental_provider_ids[0], tuple(reasons))

    def evaluate_formal_deadline(
        self,
        *,
        now: datetime,
        certified: bool,
        provisional_snapshot_id: str | None,
    ) -> FormalDeadlineDecision:
        local_now = self._validate_now(now)
        deadline = self._at_local_time(local_now.date(), time(19, 0))
        rejected = local_now >= deadline and not certified
        return FormalDeadlineDecision(
            rejected=rejected,
            failure_code="FORMAL_DEADLINE_CERTIFICATION_MISSING" if rejected else None,
            provisional_snapshot_id=provisional_snapshot_id,
            allow_formal_prediction=certified and not rejected,
            allow_formal_backtest=certified and not rejected,
        )


__all__ = [
    "DailyScheduleResult",
    "DailySchedulerService",
    "FormalDeadlineDecision",
    "ScheduledPhaseSubmission",
    "SupplementalDecision",
]
