from __future__ import annotations

from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

import pytest

from src.schemas.platform import TaskCreateRequest
from src.schemas.platform.scheduler import (
    DAILY_SCHEDULE_TIMEZONE,
    DailySchedulePhase,
    DailySchedulePhaseTaskRequirements,
)
from src.services.platform.daily_scheduler import (
    DailySchedulerService,
    SupplementalDecision,
)


SHANGHAI = ZoneInfo("Asia/Shanghai")
NOW = datetime(2026, 9, 8, 20, 35, tzinfo=SHANGHAI)
TRADE_DATE = date(2026, 9, 8)


class FakeTaskControl:
    def __init__(self) -> None:
        self.calls: list[tuple[TaskCreateRequest, str]] = []
        self.counter = 0

    def create_task(self, request: TaskCreateRequest, *, idempotency_key: str, endpoint: str = ""):
        self.calls.append((request, idempotency_key))
        self.counter += 1
        return f"task_{self.counter}"


def test_daily_schedule_uses_fixed_timezone_and_all_sla_slots() -> None:
    service = DailySchedulerService(FakeTaskControl(), trading_day_resolver=lambda _: True)

    plan = service.plan_day(TRADE_DATE, schedule_version="1.0.0")

    assert DAILY_SCHEDULE_TIMEZONE == SHANGHAI
    assert plan.timezone == "Asia/Shanghai"
    assert [slot.phase for slot in plan.slots] == list(DailySchedulePhase)
    assert [slot.local_time for slot in plan.slots] == [
        time(15, 50),
        time(16, 0),
        time(16, 20),
        time(16, 30),
        time(16, 40),
        time(17, 10),
        time(17, 30),
        time(19, 0),
        time(20, 30),
    ]


def test_schedule_day_skips_non_trading_day_without_creating_tasks() -> None:
    task_control = FakeTaskControl()
    service = DailySchedulerService(task_control, trading_day_resolver=lambda _: False)

    result = service.schedule_day(TRADE_DATE, now=NOW)

    assert result.skipped is True
    assert result.skip_reason == "NON_TRADING_DAY"
    assert result.submissions == ()
    assert task_control.calls == []


def test_idempotency_key_is_stable_and_dependencies_are_explicit() -> None:
    task_control = FakeTaskControl()
    service = DailySchedulerService(task_control, trading_day_resolver=lambda _: True)

    key = service.idempotency_key("1.0.0", TRADE_DATE, DailySchedulePhase.CORE_INGESTION)
    first = service.schedule_phase(
        TRADE_DATE,
        DailySchedulePhase.CORE_INGESTION,
        schedule_version="1.0.0",
        dependency_task_ids=("task_00000000-0000-7000-8000-000000000001",),
        now=NOW,
    )
    second = service.schedule_phase(
        TRADE_DATE,
        DailySchedulePhase.CORE_INGESTION,
        schedule_version="1.0.0",
        dependency_task_ids=("task_00000000-0000-7000-8000-000000000001",),
        now=NOW,
    )

    assert first.idempotency_key == key
    assert second.idempotency_key == key
    assert task_control.calls[0][1] == task_control.calls[1][1] == key
    req = DailySchedulePhaseTaskRequirements.model_validate(task_control.calls[0][0].requirements)
    assert req.phase is DailySchedulePhase.CORE_INGESTION
    assert req.dependency_task_ids == ("task_00000000-0000-7000-8000-000000000001",)
    assert req.primary_provider_id == "a_stock_data"
    assert req.supplemental_provider_ids == ("financial_api",)


def test_task_create_contract_accepts_scheduler_phase_and_rejects_missing_schedule_fields() -> None:
    valid = {
        "schedule_version": "1.0.0",
        "trade_date": TRADE_DATE,
        "phase": "PREFLIGHT",
        "scheduled_at": "2026-09-08T15:50:00+08:00",
        "timezone": "Asia/Shanghai",
        "formal_deadline_at": "2026-09-08T19:00:00+08:00",
    }
    request = TaskCreateRequest(
        task_type="daily_schedule_phase",
        requested_by="scheduler:daily",
        requirements=valid,
    )
    assert request.task_type == "daily_schedule_phase"

    with pytest.raises(ValueError, match="schedule_version"):
        TaskCreateRequest(
            task_type="daily_schedule_phase",
            requested_by="scheduler:daily",
            requirements={"phase": "PREFLIGHT"},
        )


def test_supplemental_source_is_only_selected_for_explicit_quality_or_failure_triggers() -> None:
    service = DailySchedulerService(FakeTaskControl(), trading_day_resolver=lambda _: True)

    no_fallback = service.decide_supplemental(
        primary_attempts=1,
        coverage_ratio=1.0,
        quality_gaps=(),
        schema_drift=False,
        cross_check_required=False,
    )
    fallback = service.decide_supplemental(
        primary_attempts=2,
        coverage_ratio=0.7,
        quality_gaps=("BAR_COVERAGE_LOW",),
        schema_drift=True,
        cross_check_required=False,
    )

    assert isinstance(no_fallback, SupplementalDecision)
    assert no_fallback.use_supplemental is False
    assert fallback.use_supplemental is True
    assert fallback.provider_id == "financial_api"
    assert fallback.reason_codes == ("PRIMARY_ATTEMPTS_EXHAUSTED", "QUALITY_GAP", "SCHEMA_DRIFT")


def test_formal_deadline_rejects_provisional_or_missing_certification() -> None:
    service = DailySchedulerService(FakeTaskControl(), trading_day_resolver=lambda _: True)

    decision = service.evaluate_formal_deadline(
        now=NOW,
        certified=False,
        provisional_snapshot_id="ds_00000000-0000-7000-8000-000000000001",
    )

    assert decision.rejected is True
    assert decision.failure_code == "FORMAL_DEADLINE_CERTIFICATION_MISSING"
    assert decision.provisional_snapshot_id == "ds_00000000-0000-7000-8000-000000000001"
    assert decision.allow_formal_prediction is False
    assert decision.allow_formal_backtest is False


def test_correction_requirements_always_point_to_new_snapshot_lineage() -> None:
    service = DailySchedulerService(FakeTaskControl(), trading_day_resolver=lambda _: True)

    requirements = service.build_phase_requirements(
        TRADE_DATE,
        DailySchedulePhase.CORRECTION_AUDIT,
        schedule_version="1.0.0",
        now=NOW,
        correction_of_snapshot_id="ds_00000000-0000-7000-8000-000000000001",
    )

    assert requirements.correction_of_snapshot_id == "ds_00000000-0000-7000-8000-000000000001"
    assert requirements.phase is DailySchedulePhase.CORRECTION_AUDIT
    assert requirements.revision_kind == "CORRECTION"
    assert requirements.snapshot_publication_status == "CORRECTION"
