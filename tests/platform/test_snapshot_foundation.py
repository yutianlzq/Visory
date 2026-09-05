from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from src.artifacts.hashing import compute_bytes_hash
from src.services.platform.canonical_normalization import deterministic_manifest_hash
from src.services.platform.snapshot import SnapshotCapabilityEngine, SnapshotGateError, SnapshotGateService, SnapshotManifestPublisher
from src.schemas.platform import (
    CanonicalPartition,
    CanonicalQualityReport,
    ConsumerKind,
    ConsumerRequirement,
    DataSnapshot,
    QualityStatus,
    RevisionKind,
    SnapshotCapabilityStatus,
    SnapshotPublicationStatus,
    StorageBackend,
    StorageNamespace,
    StorageRef,
)


GOLDEN = Path(__file__).resolve().parents[1] / "golden" / "platform" / "contracts" / "success" / "data-snapshot.json"


def load_snapshot() -> DataSnapshot:
    return DataSnapshot.model_validate(json.loads(GOLDEN.read_text(encoding="utf-8"))["payload"])


def test_manifest_publisher_is_deterministic_and_append_only(tmp_path: Path) -> None:
    snapshot = load_snapshot()
    publisher = SnapshotManifestPublisher(tmp_path)

    relative = publisher.publish(snapshot)
    assert relative.endswith("/manifest.json")
    publisher.read_and_validate(snapshot)

    with pytest.raises(SnapshotGateError, match="already exists"):
        publisher.publish(snapshot)

    first = (publisher.resolver.resolve(relative, require_exists=True)).read_bytes()
    other_root = tmp_path / "second"
    other = SnapshotManifestPublisher(other_root)
    assert other.publish(snapshot) == relative
    second = other.resolver.resolve(relative, require_exists=True).read_bytes()
    assert first == second


def test_capability_engine_never_certifies_backtest_core() -> None:
    snapshot = load_snapshot()
    certifications = SnapshotCapabilityEngine.certify(snapshot, now=datetime(2026, 8, 31, 9, tzinfo=timezone.utc))
    backtest = next(item for item in certifications if item.capability_id == "backtest_core")
    assert backtest.capability_status is SnapshotCapabilityStatus.UNAVAILABLE
    assert backtest.reason_code == "BENCHMARK_DATASET_MISSING"


def test_formal_consumer_rejects_provisional_snapshot() -> None:
    service = object.__new__(SnapshotGateService)
    snapshot = load_snapshot()
    requirement = ConsumerRequirement(
        consumer_id="formal_backtest",
        consumer_kind=ConsumerKind.FORMAL_BACKTEST,
        required_capabilities=("backtest_core",),
        accepted_publication_statuses=(SnapshotPublicationStatus.CERTIFIED,),
    )
    with pytest.raises(SnapshotGateError, match="not accepted"):
        service.check_consumer(snapshot, requirement)


class _FakeDatabase:
    @contextmanager
    def transaction(self):
        yield object()


class _FakeCanonicalRepository:
    def __init__(self, partition: CanonicalPartition, report: CanonicalQualityReport):
        self.partition = partition
        self.report = report

    def get_partition(self, session, partition_id):
        return self.partition if partition_id == self.partition.canonical_partition_id else None

    def get_quality_report(self, session, report_id):
        return self.report if report_id == self.report.quality_report_id else None


class _FakeRawRepository:
    def get_provider_run(self, session, run_id):
        return object()

    def get_raw_object(self, session, raw_id):
        return object()


def test_gate_checks_partition_file_integrity_and_point_in_time(tmp_path: Path) -> None:
    now = datetime(2026, 8, 31, 8, tzinfo=timezone.utc)
    content = b"x"
    content_hash = compute_bytes_hash(content)
    partition_id = "cpart_019dbd74-2a00-7000-8000-000000000105"
    quality_id = "quality_019dbd74-2a00-7000-8000-000000000106"
    run_id = "prun_019dbd74-2a00-7000-8000-000000000101"
    raw_id = "raw_019dbd74-2a00-7000-8000-000000000104"
    storage_ref = StorageRef(storage_backend=StorageBackend.LOCAL_FS, storage_namespace=StorageNamespace.APP, relative_path="canonical/dataset=security_master/partition=2026-08-31/revision=1/cpart.parquet", content_hash=content_hash, media_type="application/vnd.apache.parquet", size_bytes=1)
    partition = CanonicalPartition(canonical_partition_id=partition_id, dataset_id="security_master", dataset_schema_version="1.0.0", partition_key="2026-08-31", revision=1, revision_kind=RevisionKind.INITIAL, provider_policy_version="1.0.0", provider_run_refs=(run_id,), raw_object_refs=(raw_id,), min_available_at=now, row_count=1, distinct_entity_count=1, storage_ref=storage_ref, partition_hash=content_hash, schema_hash=content_hash, quality_status=QualityStatus.COMPLETE, quality_report_id=quality_id, created_at=now, published_at=now)
    report = CanonicalQualityReport(quality_report_id=quality_id, canonical_partition_id=partition_id, quality_status=QualityStatus.COMPLETE, rule_results={"schema": "PASS"}, row_count=1, rejected_row_count=0, duplicate_key_count=0, identity_unresolved_count=0, identity_ambiguous_count=0, created_at=now)
    publisher = SnapshotManifestPublisher(tmp_path)
    path = publisher.resolver.resolve(storage_ref)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    manifest_payload = {"partition": partition.model_dump(mode="json"), "quality_report": report.model_dump(mode="json")}
    manifest_payload["manifest_hash"] = deterministic_manifest_hash(manifest_payload)
    (path.parent / "manifest.json").write_text(json.dumps(manifest_payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    service = SnapshotGateService(_FakeDatabase(), runtime_root=tmp_path, canonical_repository=_FakeCanonicalRepository(partition, report), raw_repository=_FakeRawRepository())
    from src.schemas.platform import SnapshotBuildTaskRequirements
    req = SnapshotBuildTaskRequirements(trade_date=date(2026, 8, 31), cutoff_at=now, provider_policy_id="policy_core", provider_policy_version="1.0.0", security_master_ref=partition_id, calendar_ref=partition_id, canonical_partition_ids=(partition_id,), requested_capabilities=("identity_core",))
    evidence = service.validate_gate(req)
    assert evidence.partition_refs[0].canonical_partition_id == partition_id

    late = partition.model_copy(update={"min_available_at": datetime(2026, 8, 31, 9, tzinfo=timezone.utc)})
    late_service = SnapshotGateService(_FakeDatabase(), runtime_root=tmp_path, canonical_repository=_FakeCanonicalRepository(late, report), raw_repository=_FakeRawRepository())
    with pytest.raises(SnapshotGateError, match="not available"):
        late_service.validate_gate(req)


def test_preview_requirement_must_explicitly_opt_in_to_provisional() -> None:
    with pytest.raises(ValueError, match="explicitly allow provisional"):
        ConsumerRequirement(
            consumer_id="preview_consumer",
            consumer_kind=ConsumerKind.PREVIEW,
            required_capabilities=("identity_core",),
            accepted_publication_statuses=(SnapshotPublicationStatus.PROVISIONAL,),
            allow_provisional=False,
        )


def test_snapshot_build_requirements_reject_duplicate_partitions() -> None:
    from src.schemas.platform import SnapshotBuildTaskRequirements

    partition_id = "cpart_019dbd74-2a00-7000-8000-000000000105"
    with pytest.raises(ValueError, match="non-empty and unique"):
        SnapshotBuildTaskRequirements(
            trade_date=date(2026, 8, 31),
            cutoff_at=datetime(2026, 8, 31, 8, tzinfo=timezone.utc),
            provider_policy_id="policy_core",
            provider_policy_version="1.0.0",
            security_master_ref=partition_id,
            calendar_ref=partition_id,
            canonical_partition_ids=(partition_id, partition_id),
            requested_capabilities=("identity_core",),
        )
