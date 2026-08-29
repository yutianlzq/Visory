from __future__ import annotations

from datetime import datetime

from pydantic import field_validator, model_validator

from .base import PlatformContractModel
from .enums import AvailabilityBasis


def _require_aware(value: datetime | None, field_name: str) -> datetime | None:
    if value is not None and (value.tzinfo is None or value.utcoffset() is None):
        raise ValueError(f"{field_name} must include a timezone")
    return value


class PointInTimeWindow(PlatformContractModel):
    available_at: datetime
    cutoff_at: datetime

    @field_validator("available_at", "cutoff_at")
    @classmethod
    def validate_timezone(cls, value: datetime, info: object) -> datetime:
        field_name = getattr(info, "field_name", "timestamp")
        return _require_aware(value, field_name)  # type: ignore[return-value]

    @model_validator(mode="after")
    def validate_window(self) -> "PointInTimeWindow":
        if self.available_at > self.cutoff_at:
            raise ValueError("available_at must be less than or equal to cutoff_at")
        return self


class AvailabilityMetadata(PlatformContractModel):
    event_time: datetime | None = None
    source_published_at: datetime | None = None
    observed_at: datetime | None = None
    ingested_at: datetime
    available_at: datetime
    availability_basis: AvailabilityBasis
    availability_policy_version: str | None = None
    is_historical_backfill: bool = False

    @field_validator(
        "event_time",
        "source_published_at",
        "observed_at",
        "ingested_at",
        "available_at",
    )
    @classmethod
    def validate_timezone(cls, value: datetime | None, info: object) -> datetime | None:
        return _require_aware(value, getattr(info, "field_name", "timestamp"))

    @field_validator("availability_policy_version")
    @classmethod
    def reject_blank_policy(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("availability_policy_version cannot be blank")
        return value

    @model_validator(mode="after")
    def validate_basis_and_backfill(self) -> "AvailabilityMetadata":
        if self.availability_basis is AvailabilityBasis.SOURCE_DISCLOSURE and self.source_published_at is None:
            raise ValueError("SOURCE_DISCLOSURE requires source_published_at")
        if self.availability_basis is AvailabilityBasis.PROVIDER_TIMESTAMP and self.observed_at is None:
            raise ValueError("PROVIDER_TIMESTAMP requires observed_at")
        if self.availability_basis is AvailabilityBasis.PLATFORM_OBSERVED and self.observed_at is None:
            raise ValueError("PLATFORM_OBSERVED requires observed_at")
        if self.availability_basis is AvailabilityBasis.VERSIONED_ASSUMPTION and self.availability_policy_version is None:
            raise ValueError("VERSIONED_ASSUMPTION requires availability_policy_version")
        if self.is_historical_backfill:
            if self.availability_basis is AvailabilityBasis.PLATFORM_OBSERVED:
                raise ValueError("historical backfill cannot use PLATFORM_OBSERVED availability")
            if self.available_at == self.ingested_at:
                raise ValueError("historical backfill cannot use ingested_at as available_at")
        basis_time = None
        if self.availability_basis is AvailabilityBasis.SOURCE_DISCLOSURE:
            basis_time = self.source_published_at
        elif self.availability_basis in {
            AvailabilityBasis.PROVIDER_TIMESTAMP,
            AvailabilityBasis.PLATFORM_OBSERVED,
        }:
            basis_time = self.observed_at
        if basis_time is not None and self.available_at < basis_time:
            raise ValueError("available_at cannot predate its declared availability basis")
        return self
