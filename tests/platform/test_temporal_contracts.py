from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from src.schemas.platform import AvailabilityBasis, AvailabilityMetadata, PointInTimeWindow


def test_point_in_time_window_accepts_same_instant_with_different_offsets() -> None:
    window = PointInTimeWindow(
        available_at="2026-08-27T08:00:00Z",
        cutoff_at="2026-08-27T16:00:00+08:00",
    )
    assert window.available_at == window.cutoff_at


def test_point_in_time_window_rejects_naive_timestamp() -> None:
    with pytest.raises(ValidationError):
        PointInTimeWindow(
            available_at="2026-08-27T08:00:00",
            cutoff_at="2026-08-27T16:00:00+08:00",
        )


def test_point_in_time_window_rejects_future_available_data() -> None:
    with pytest.raises(ValidationError):
        PointInTimeWindow(
            available_at="2026-08-27T16:00:01+08:00",
            cutoff_at="2026-08-27T16:00:00+08:00",
        )


def test_historical_backfill_cannot_use_ingestion_time_as_availability() -> None:
    now = datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc)
    with pytest.raises(ValidationError):
        AvailabilityMetadata(
            event_time=now - timedelta(days=365),
            observed_at=now,
            ingested_at=now,
            available_at=now,
            availability_basis=AvailabilityBasis.PLATFORM_OBSERVED,
            is_historical_backfill=True,
        )


def test_versioned_assumption_requires_policy_version() -> None:
    with pytest.raises(ValidationError):
        AvailabilityMetadata(
            event_time="2025-01-01T00:00:00Z",
            ingested_at="2026-08-29T00:00:00Z",
            available_at="2025-01-02T00:00:00Z",
            availability_basis=AvailabilityBasis.VERSIONED_ASSUMPTION,
            is_historical_backfill=True,
        )


@pytest.mark.parametrize(
    ("basis", "basis_field"),
    [
        (AvailabilityBasis.SOURCE_DISCLOSURE, "source_published_at"),
        (AvailabilityBasis.PROVIDER_TIMESTAMP, "observed_at"),
        (AvailabilityBasis.PLATFORM_OBSERVED, "observed_at"),
    ],
)
def test_available_at_cannot_predate_declared_basis(
    basis: AvailabilityBasis,
    basis_field: str,
) -> None:
    payload = {
        "event_time": "2026-08-27T15:00:00+08:00",
        "ingested_at": "2026-08-27T16:02:11+08:00",
        "available_at": "2026-08-27T15:59:59+08:00",
        "availability_basis": basis,
        basis_field: "2026-08-27T16:00:00+08:00",
    }
    with pytest.raises(ValidationError):
        AvailabilityMetadata.model_validate(payload)
