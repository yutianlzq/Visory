from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.schemas.platform import (
    CapabilityCertification,
    DataSnapshot,
    QualityStatus,
    SnapshotCapabilityStatus,
    SnapshotCurrentPointer,
    TaskRecord,
    TaskState,
)
from src.services.platform.snapshot import SnapshotCapabilityEngine
from src.services.platform.data_quality import (
    DATA_QUALITY_CAPABILITIES,
    DataQualityActionRequest,
    DataQualityQuery,
    DataQualityService,
)


GOLDEN = Path(__file__).resolve().parents[1] / "golden" / "platform" / "contracts" / "success" / "data-snapshot.json"
NOW = datetime(2026, 8, 31, 12, tzinfo=timezone.utc)


def snapshot_fixture() -> DataSnapshot:
    return DataSnapshot.model_validate(json.loads(GOLDEN.read_text(encoding="utf-8"))["payload"])


class FakeSnapshotRepository:
    def __init__(self, snapshot: DataSnapshot, prior: DataSnapshot | None = None):
        self.snapshot = snapshot
        self.prior = prior
        self.certifications = tuple(
            CapabilityCertification(
                capability_id=capability,
                capability_status=(SnapshotCapabilityStatus.CERTIFIED if capability in snapshot.certified_capabilities else SnapshotCapabilityStatus.UNAVAILABLE),
                reason_code=None if capability in snapshot.certified_capabilities else "NOT_PRESENT",
                certified_at=NOW if capability in snapshot.certified_capabilities else None,
                snapshot_id=snapshot.snapshot_id,
            )
            for capability in DATA_QUALITY_CAPABILITIES
        )
        self.pointer = SnapshotCurrentPointer(
            scope="global",
            trade_date=snapshot.trade_date,
            capability_id="backtest_core",
            snapshot_id=snapshot.snapshot_id,
            previous_snapshot_id=prior.snapshot_id if prior else None,
            pointer_revision=2 if prior else 1,
            updated_at=NOW,
        )

    def get_snapshot(self, session, snapshot_id, **kwargs):
        if snapshot_id == self.snapshot.snapshot_id:
            return self.snapshot
        if self.prior is not None and snapshot_id == self.prior.snapshot_id:
            return self.prior
        return None

    def get_latest_for_trade_date(self, session, trade_date):
        return self.snapshot if trade_date == self.snapshot.trade_date else None

    def list_capabilities(self, session, snapshot_id):
        return self.certifications if snapshot_id == self.snapshot.snapshot_id else ()

    def list_pointers(self, session, trade_date):
        return (self.pointer,) if trade_date == self.snapshot.trade_date else ()


class FakeCanonicalRepository:
    def get_partition(self, session, partition_id):
        return SimpleNamespace(canonical_partition_id=partition_id, dataset_id="security_master")

    def get_quality_report(self, session, report_id):
        return SimpleNamespace(quality_report_id=report_id, duplicate_key_count=0, rejected_row_count=0)


class FakeRawRepository:
    def get_provider_run(self, session, run_id):
        return SimpleNamespace(provider_run_id=run_id, provider_id="a_stock_data", dataset_id="security_master", actual_upstream="a-stock-data")

    def get_raw_object(self, session, raw_id):
        return SimpleNamespace(raw_object_id=raw_id, provider_id="a_stock_data", actual_upstream="a-stock-data", relative_path="raw/hidden")

    def get_raw_object_by_run(self, session, run_id):
        return self.get_raw_object(session, run_id.replace("prun_", "raw_", 1))

    def get_quarantine_by_run(self, session, run_id):
        return None

    def get_provider(self, session, provider_id):
        return SimpleNamespace(provider_id=provider_id, display_name="A Stock Data", credential_ref="secret-ref")

    def get_dataset(self, session, dataset_id, schema_version):
        return SimpleNamespace(dataset_id=dataset_id, schema_version=schema_version, frequency="1d")


class FakeProviderRepository:
    def get_provider(self, session, provider_id):
        return SimpleNamespace(provider_id=provider_id, display_name="A Stock Data", credential_ref="secret-ref")

    def get_dataset(self, session, dataset_id, schema_version):
        return SimpleNamespace(dataset_id=dataset_id, schema_version=schema_version, frequency="1d")


class FakeDatabase:
    class _Tx:
        def __enter__(self):
            return object()

        def __exit__(self, *args):
            return False

    def transaction(self):
        return self._Tx()


def test_projection_contains_snapshot_capabilities_lineage_timeline_and_secret_free_evidence():
    snapshot = snapshot_fixture()
    service = DataQualityService(
        FakeDatabase(),
        snapshot_repository=FakeSnapshotRepository(snapshot),
        canonical_repository=FakeCanonicalRepository(),
        raw_repository=FakeRawRepository(),
        provider_repository=FakeProviderRepository(),
        task_repository=FakeTimelineRepository(),
        task_control_service=None,
    )

    projection = service.get_projection(DataQualityQuery(trade_date=snapshot.trade_date))

    assert projection.snapshot_id == snapshot.snapshot_id
    assert projection.data_as_of == snapshot.available_at
    assert projection.quality_status == snapshot.quality_status
    assert set(projection.missing_capabilities) == set(snapshot.missing_capabilities)
    assert tuple(item.capability_id for item in projection.capabilities) == DATA_QUALITY_CAPABILITIES
    assert [item.stage_id for item in projection.timeline] == [
        "PREFLIGHT", "CORE_INGESTION", "NORMALIZATION_QUALITY", "PROVISIONAL_SNAPSHOT",
        "SUPPLEMENTAL_DECISION", "BACKTEST_CORE_CERTIFICATION", "CORRECTION_AUDIT",
    ]
    assert projection.datasets
    evidence = projection.datasets[0]
    assert evidence.provider_runs and evidence.raw_objects and evidence.canonical_partitions and evidence.quality_reports
    assert "credential_ref" not in projection.model_dump_json()
    assert "secret-ref" not in projection.model_dump_json()
    assert "raw/hidden" not in projection.model_dump_json()


def test_compare_reports_partition_quality_capability_and_provider_changes():
    current = snapshot_fixture()
    prior = current.model_copy(update={"snapshot_id": "ds_019dbd74-2a00-7000-8000-000000000008", "revision": 1})
    service = DataQualityService(
        FakeDatabase(),
        snapshot_repository=FakeSnapshotRepository(current, prior),
        canonical_repository=FakeCanonicalRepository(),
        raw_repository=FakeRawRepository(),
        provider_repository=FakeProviderRepository(),
        task_control_service=None,
    )

    result = service.compare_snapshots(current.snapshot_id, prior.snapshot_id)

    assert result.base_snapshot_id == prior.snapshot_id
    assert result.target_snapshot_id == current.snapshot_id
    assert hasattr(result, "added_partitions")
    assert hasattr(result, "removed_partitions")
    assert hasattr(result, "revised_partitions")
    assert hasattr(result, "capability_changes")
    assert hasattr(result, "provider_switches")
    assert hasattr(result, "affected_consumers")
    assert hasattr(result, "affected_tasks")


def test_controlled_correction_only_creates_data_snapshot_build_task():
    snapshot = snapshot_fixture()
    created = {}

    task = TaskRecord.model_validate({
        "task_id": "task_019dbd74-2a00-7000-8000-000000000777",
        "task_type": "data_snapshot_build",
        "task_schema_version": "1.0.0",
        "task_state": TaskState.QUEUED,
        "priority_class": "P5_PREVIEW_AND_MAINTENANCE",
        "priority_value": 100,
        "idempotency_key": "quality-correction",
        "task_key": "data_snapshot_build:quality-correction",
        "canonical_request_hash": "sha256:" + "1" * 64,
        "requested_by": "owner:quality",
        "request_source": "data_quality:correction",
        "input_refs": [{"resource_id": snapshot.snapshot_id, "resource_type": "data_snapshot"}],
        "requirements": {},
        "max_attempts": 3,
        "created_at": NOW,
        "queued_at": NOW,
    })

    class FakeTaskService:
        def create_task(self, request, *, idempotency_key, endpoint):
            created["request"] = request
            created["idempotency_key"] = idempotency_key
            created["endpoint"] = endpoint
            return task

    service = DataQualityService(
        FakeDatabase(),
        snapshot_repository=FakeSnapshotRepository(snapshot),
        canonical_repository=FakeCanonicalRepository(),
        raw_repository=FakeRawRepository(),
        provider_repository=FakeProviderRepository(),
        task_control_service=FakeTaskService(),
    )

    result = service.create_action(DataQualityActionRequest(
        action="correction",
        snapshot_id=snapshot.snapshot_id,
        trade_date=snapshot.trade_date,
        reason_code="QUALITY_RECHECK_REQUESTED",
        requested_by="owner:quality",
    ), idempotency_key="quality-correction")

    assert result.task_id == task.task_id
    request = created["request"]
    assert request.task_type == "data_snapshot_build"
    assert request.request_source == "data_quality:correction"
    assert request.requirements["correction_of_snapshot_id"] == snapshot.snapshot_id
    assert request.requirements["trade_date"] == snapshot.trade_date
    assert request.requirements["reason_code"] == "QUALITY_RECHECK_REQUESTED"
    assert "storage_ref" not in request.requirements
    assert "canonical" not in service.__class__.__module__.lower()

class FakeTimelineRepository:
    def __init__(self, tasks=()):
        self.tasks = tasks

    def list_schedule_tasks(self, session, trade_date):
        assert session is not None
        return self.tasks


def test_timeline_never_infers_execution_from_certified_snapshot():
    snapshot = snapshot_fixture()
    service = DataQualityService(
        FakeDatabase(), snapshot_repository=FakeSnapshotRepository(snapshot),
        canonical_repository=FakeCanonicalRepository(), raw_repository=FakeRawRepository(),
        task_repository=FakeTimelineRepository(),
    )
    timeline = service.get_projection(DataQualityQuery(snapshot_id=snapshot.snapshot_id)).timeline
    assert all(stage.stage_status == 'UNVERIFIED' for stage in timeline)
    assert all(stage.reason_code == 'SCHEDULE_TASK_NOT_RECORDED' for stage in timeline)
    assert all(stage.task_ids == () for stage in timeline)


def test_timeline_uses_phase_task_state_and_reason():
    snapshot = snapshot_fixture()
    task = SimpleNamespace(
        task_id='task_019dbd74-2a00-7000-8000-000000000201',
        requirements={'phase': 'CORE_INGESTION'}, task_state=TaskState.BLOCKED,
        blocked_reason_code='PROVIDER_UNAVAILABLE', failure_code=None,
    )
    service = DataQualityService(
        FakeDatabase(), snapshot_repository=FakeSnapshotRepository(snapshot),
        canonical_repository=FakeCanonicalRepository(), raw_repository=FakeRawRepository(),
        task_repository=FakeTimelineRepository((task,)),
    )
    timeline = service.get_projection(DataQualityQuery(snapshot_id=snapshot.snapshot_id)).timeline
    stage = next(item for item in timeline if item.stage_id == 'CORE_INGESTION')
    assert stage.stage_status == 'BLOCKED'
    assert stage.reason_code == 'PROVIDER_UNAVAILABLE'
    assert stage.task_ids == (task.task_id,)
    assert timeline[-1].stage_status == 'UNVERIFIED'


def test_snapshot_task_links_exclude_attempt_resource_ids():
    snapshot = snapshot_fixture()
    repository = FakeSnapshotRepository(snapshot)
    task_id = 'task_019dbd74-2a00-7000-8000-000000000201'
    repository.get_lineage = lambda session, snapshot_id: (
        task_id, 'attempt_019dbd74-2a00-7000-8000-000000000202',
    )
    service = DataQualityService(FakeDatabase(), snapshot_repository=repository)
    assert service._snapshot_task_ids(object(), snapshot.snapshot_id) == (task_id,)
    assert service._lineage_for_session(object(), snapshot.snapshot_id) == (task_id,)
