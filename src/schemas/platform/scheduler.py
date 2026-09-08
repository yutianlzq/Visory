from __future__ import annotations

import re
from datetime import date, datetime, time
from enum import Enum
from zoneinfo import ZoneInfo

from pydantic import AwareDatetime, Field, field_validator, model_validator

from .base import PlatformContractModel
from .enums import RevisionKind, SnapshotPublicationStatus


DAILY_SCHEDULE_TIMEZONE = ZoneInfo("Asia/Shanghai")
_SCHEDULE_VERSION = r"^[0-9]+\.[0-9]+\.[0-9]+$"
_IDENTIFIER = re.compile(r"^[a-z][a-z0-9._-]{0,63}$")
_REASON_CODE = re.compile(r"^[A-Z][A-Z0-9_]{2,63}$")


class DailySchedulePhase(str, Enum):
    PREFLIGHT = "PREFLIGHT"
    CORE_INGESTION = "CORE_INGESTION"
    NORMALIZATION_QUALITY = "NORMALIZATION_QUALITY"
    PROVISIONAL_SNAPSHOT = "PROVISIONAL_SNAPSHOT"
    SUPPLEMENTAL_DECISION = "SUPPLEMENTAL_DECISION"
    BACKTEST_CORE_CERTIFICATION = "BACKTEST_CORE_CERTIFICATION"
    REVIEW_CAPABILITY_TARGET = "REVIEW_CAPABILITY_TARGET"
    FORMAL_DEADLINE = "FORMAL_DEADLINE"
    CORRECTION_AUDIT = "CORRECTION_AUDIT"


_PHASE_TIMES: dict[DailySchedulePhase, time] = {
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


class DailyScheduleSlot(PlatformContractModel):
    phase: DailySchedulePhase
    local_time: time


class DailySchedulePlan(PlatformContractModel):
    schedule_version: str
    trade_date: date
    timezone: str
    trading_day: bool
    slots: tuple[DailyScheduleSlot, ...]

    @field_validator("schedule_version")
    @classmethod
    def validate_schedule_version(cls, value: str) -> str:
        if not re.fullmatch(_SCHEDULE_VERSION, value):
            raise ValueError("schedule_version must be a semantic version")
        return value

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        if value != "Asia/Shanghai":
            raise ValueError("daily schedule timezone must be Asia/Shanghai")
        return value

    @model_validator(mode="after")
    def validate_slots(self) -> "DailySchedulePlan":
        if tuple(slot.phase for slot in self.slots) != tuple(DailySchedulePhase):
            raise ValueError("daily schedule slots must contain all phases in order")
        if tuple(slot.local_time for slot in self.slots) != tuple(_PHASE_TIMES[phase] for phase in DailySchedulePhase):
            raise ValueError("daily schedule slots must use the fixed SLA times")
        return self


class DailySchedulePhaseTaskRequirements(PlatformContractModel):
    """Secret-free durable task input for one daily scheduler phase."""

    schedule_version: str
    trade_date: date
    phase: DailySchedulePhase
    scheduled_at: AwareDatetime
    timezone: str = "Asia/Shanghai"
    formal_deadline_at: AwareDatetime
    dependency_task_ids: tuple[str, ...] = ()
    primary_provider_id: str = "a_stock_data"
    supplemental_provider_ids: tuple[str, ...] = ("financial_api",)
    snapshot_publication_status: SnapshotPublicationStatus = SnapshotPublicationStatus.PROVISIONAL
    revision_kind: RevisionKind = RevisionKind.INITIAL
    correction_of_snapshot_id: str | None = None
    quality_gaps: tuple[str, ...] = ()
    degradation_reasons: tuple[str, ...] = ()
    blocked_reason_code: str | None = None
    failure_code: str | None = None

    @field_validator("schedule_version")
    @classmethod
    def validate_schedule_version(cls, value: str) -> str:
        if not re.fullmatch(_SCHEDULE_VERSION, value):
            raise ValueError("schedule_version must be a semantic version")
        return value

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        if value != "Asia/Shanghai":
            raise ValueError("daily schedule timezone must be Asia/Shanghai")
        return value

    @field_validator("primary_provider_id")
    @classmethod
    def validate_primary_provider(cls, value: str) -> str:
        if not _IDENTIFIER.fullmatch(value):
            raise ValueError("primary_provider_id must be a normalized identifier")
        return value

    @field_validator("supplemental_provider_ids")
    @classmethod
    def validate_supplemental_providers(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)) or any(not _IDENTIFIER.fullmatch(item) for item in value):
            raise ValueError("supplemental_provider_ids must contain unique normalized identifiers")
        return value

    @field_validator("quality_gaps", "degradation_reasons")
    @classmethod
    def validate_reason_codes(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)) or any(not _REASON_CODE.fullmatch(item) for item in value):
            raise ValueError("reason codes must contain unique stable uppercase identifiers")
        return value

    @field_validator("blocked_reason_code", "failure_code")
    @classmethod
    def validate_reason_code(cls, value: str | None) -> str | None:
        if value is not None and not _REASON_CODE.fullmatch(value):
            raise ValueError("reason code must be a stable uppercase identifier")
        return value

    @model_validator(mode="after")
    def validate_phase_semantics(self) -> "DailySchedulePhaseTaskRequirements":
        if self.scheduled_at.tzinfo is None or self.formal_deadline_at.tzinfo is None:
            raise ValueError("schedule timestamps must be timezone-aware")
        local_scheduled_at = self.scheduled_at.astimezone(DAILY_SCHEDULE_TIMEZONE)
        local_deadline_at = self.formal_deadline_at.astimezone(DAILY_SCHEDULE_TIMEZONE)
        expected_scheduled_at = datetime.combine(self.trade_date, _PHASE_TIMES[self.phase], tzinfo=DAILY_SCHEDULE_TIMEZONE)
        expected_deadline_at = datetime.combine(self.trade_date, time(19, 0), tzinfo=DAILY_SCHEDULE_TIMEZONE)
        if local_scheduled_at != expected_scheduled_at or local_deadline_at != expected_deadline_at:
            raise ValueError("schedule timestamps must match the fixed Asia/Shanghai SLA")
        if self.phase is not DailySchedulePhase.CORRECTION_AUDIT and self.formal_deadline_at < self.scheduled_at:
            raise ValueError("formal_deadline_at must not precede scheduled_at")
        if len(self.dependency_task_ids) != len(set(self.dependency_task_ids)):
            raise ValueError("dependency_task_ids must be unique")
        if self.primary_provider_id in self.supplemental_provider_ids:
            raise ValueError("primary provider cannot be supplemental")
        if self.phase is DailySchedulePhase.CORRECTION_AUDIT:
            if self.revision_kind is RevisionKind.CORRECTION and self.correction_of_snapshot_id is None:
                raise ValueError("CORRECTION revision requires correction_of_snapshot_id")
            if self.correction_of_snapshot_id is not None and self.revision_kind is not RevisionKind.CORRECTION:
                raise ValueError("correction_of_snapshot_id requires CORRECTION revision_kind")
        elif self.revision_kind is RevisionKind.CORRECTION or self.correction_of_snapshot_id is not None:
            raise ValueError("correction lineage only applies to CORRECTION_AUDIT")
        return self


__all__ = [
    "DAILY_SCHEDULE_TIMEZONE",
    "DailySchedulePhase",
    "DailySchedulePlan",
    "DailySchedulePhaseTaskRequirements",
    "DailyScheduleSlot",
]
