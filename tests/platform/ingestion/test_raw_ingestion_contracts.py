from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from src.schemas.platform import (
    ProviderRun,
    ProviderRunOutcome,
    RawIngestionQuarantine,
    RawIngestionTaskRequirements,
    RawSchemaDriftClassification,
    ResourceType,
    StorageBackend,
    StorageNamespace,
    StorageRef,
    generate_resource_id,
)
from src.services.platform.raw_ingestion import classify_raw_schema


NOW = datetime(2026, 8, 31, tzinfo=timezone.utc)
HASH = "sha256:" + "1" * 64


def test_raw_schema_drift_classification_is_explicit() -> None:
    expected = ("entity_key", "trade_date")
    assert classify_raw_schema(expected, expected) is RawSchemaDriftClassification.MATCHED
    assert classify_raw_schema(expected, ("entity_key", "trade_date", "optional")) is RawSchemaDriftClassification.ADDITIVE_DRIFT
    assert classify_raw_schema(expected, ("entity_key",)) is RawSchemaDriftClassification.BREAKING_DRIFT
    assert classify_raw_schema(expected, None) is RawSchemaDriftClassification.UNKNOWN_SCHEMA


def test_raw_task_requirements_reject_secret_bearing_persistence() -> None:
    base = {
        "provider_id": "a_stock_data",
        "dataset_id": "security_master",
        "dataset_schema_version": "1.0.0",
        "provider_policy_id": "security_master_v1",
    }
    assert RawIngestionTaskRequirements(**base).provider_id == "a_stock_data"
    with pytest.raises(ValidationError, match="secret-bearing"):
        RawIngestionTaskRequirements(**base, request={"authorization": "***"})
    with pytest.raises(ValidationError, match="secret-bearing"):
        RawIngestionTaskRequirements(**base, request={"url": "https://example.test/path?token=***"})
    with pytest.raises(ValidationError, match="secret-bearing"):
        RawIngestionTaskRequirements(**base, request={"headers": {"Authorization": "***"}})
    with pytest.raises(ValidationError, match="secret-bearing values"):
        RawIngestionTaskRequirements(**base, request={"body": "token=***"})


def test_provider_run_and_quarantine_never_accept_credentials_or_matched_drift() -> None:
    task_id = generate_resource_id(ResourceType.TASK, timestamp_ms=1, random_bits=1)
    attempt_id = generate_resource_id(ResourceType.ATTEMPT, timestamp_ms=1, random_bits=2)
    run_id = generate_resource_id(ResourceType.PROVIDER_RUN, timestamp_ms=1, random_bits=3)
    with pytest.raises(ValidationError, match="credentials"):
        ProviderRun(
            provider_run_id=run_id, provider_id="a_stock_data", actual_upstream="https://user:pass@example.test",
            dataset_id="security_master", dataset_schema_version="1.0.0", provider_policy_id="security_master_v1",
            provider_policy_version="1.0.0", adapter_version="1.0.0", capability_market="CN", capability_frequency="event",
            task_id=task_id, attempt_id=attempt_id, request_fingerprint=HASH, started_at=NOW,
            finished_at=NOW, run_outcome=ProviderRunOutcome.FAILED, failure_code="RAW_TIMEOUT",
        )
    with pytest.raises(ValidationError, match="matched schemas"):
        RawIngestionQuarantine(
            raw_ingestion_quarantine_id=generate_resource_id(ResourceType.RAW_INGESTION_QUARANTINE, timestamp_ms=1, random_bits=4),
            provider_run_id=run_id, classification=RawSchemaDriftClassification.MATCHED, reason_code="RAW_SCHEMA_MATCHED",
            expected_schema_hash=HASH, evidence_hash=HASH, created_at=NOW,
            evidence_storage_ref=StorageRef(storage_backend=StorageBackend.LOCAL_FS, storage_namespace=StorageNamespace.APP, relative_path="quarantine/evidence.bin", content_hash=HASH, media_type="application/octet-stream", size_bytes=0),
        )
