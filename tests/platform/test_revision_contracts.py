from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.schemas.platform import (
    PublicationMetadata,
    PublicationStatus,
    QualityStatus,
    RevisionKind,
    RevisionMetadata,
    TaskState,
    TaskStateMetadata,
)


def test_publication_status_does_not_include_correction() -> None:
    with pytest.raises(ValidationError):
        PublicationMetadata(
            publication_status="CORRECTION",
            quality_status=QualityStatus.COMPLETE,
        )


def test_correction_requires_supersedes_and_revision_two_or_greater() -> None:
    with pytest.raises(ValidationError):
        RevisionMetadata(
            schema_version="1.0.0",
            revision=2,
            revision_kind=RevisionKind.CORRECTION,
        )

    with pytest.raises(ValidationError):
        RevisionMetadata(
            schema_version="1.0.0",
            revision=1,
            revision_kind=RevisionKind.CORRECTION,
            supersedes_id="ds_019c5f2a-8c33-7ce9-882c-43a965c39b2d",
        )


def test_revision_must_be_positive_and_optional_ids_cannot_be_blank() -> None:
    with pytest.raises(ValidationError):
        RevisionMetadata(
            schema_version="1.0.0",
            revision=0,
            revision_kind=RevisionKind.INITIAL,
        )

    with pytest.raises(ValidationError):
        RevisionMetadata(
            schema_version="1.0.0",
            revision=2,
            revision_kind=RevisionKind.CORRECTION,
            supersedes_id="",
        )


def test_task_state_rejects_domain_phase_and_requires_failure_reason() -> None:
    with pytest.raises(ValidationError):
        TaskStateMetadata(task_state="RUNNING_HIKYUU")

    with pytest.raises(ValidationError):
        TaskStateMetadata(task_state=TaskState.FAILED)


def test_blocked_task_requires_reason_and_unblock_condition() -> None:
    with pytest.raises(ValidationError):
        TaskStateMetadata(task_state=TaskState.BLOCKED, blocked_reason_code="DEPENDENCY")


def test_valid_publication_metadata() -> None:
    metadata = PublicationMetadata(
        publication_status=PublicationStatus.CERTIFIED,
        quality_status=QualityStatus.COMPLETE,
    )
    assert metadata.publication_status is PublicationStatus.CERTIFIED


def test_certified_publication_rejects_failed_or_unavailable_quality() -> None:
    for quality_status in (QualityStatus.FAILED, QualityStatus.UNAVAILABLE):
        with pytest.raises(ValidationError):
            PublicationMetadata(
                publication_status=PublicationStatus.CERTIFIED,
                quality_status=quality_status,
            )
