from __future__ import annotations

import json
from contextlib import contextmanager
from decimal import Decimal
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.artifacts.hashing import compute_bytes_hash
from src.services.platform.canonical_normalization import deterministic_manifest_hash
from src.services.platform.snapshot import SnapshotCapabilityEngine, SnapshotGateError, SnapshotGateService, SnapshotManifestPublisher
from src.schemas.platform import (
    BenchmarkIndexBar,
    CapabilityCertification,
    CanonicalPartition,
    CanonicalQualityReport,
    ConsumerKind,
    ConsumerRequirement,
    DataSnapshot,
    ProviderCapabilityStatus,
    ProviderMergeMode,
    ProviderRunOutcome,
    QualityStatus,
    QuarantineStatus,
    RevisionKind,
    SnapshotCapabilityStatus,
    SnapshotPublicationStatus,
    SnapshotPartitionRef,
    compute_content_hash,
    compute_snapshot_manifest_hash,
    StorageBackend,
    StorageNamespace,
    StorageRef,
)


GOLDEN = Path(__file__).resolve().parents[1] / "golden" / "platform" / "contracts" / "success" / "data-snapshot.json"


def load_snapshot() -> DataSnapshot:
    return DataSnapshot.model_validate(json.loads(GOLDEN.read_text(encoding="utf-8"))["payload"])


def test_snapshot_partition_coverage_ratio_uses_database_precision_for_manifest_round_trip() -> None:
    source = load_snapshot().canonical_partitions[0]
    low_scale = SnapshotPartitionRef.model_validate(
        {**source.model_dump(mode="python"), "coverage_ratio": Decimal("1.0")}
    )
    database_scale = SnapshotPartitionRef.model_validate(
        {**source.model_dump(mode="python"), "coverage_ratio": Decimal("1.00000")}
    )

    assert str(low_scale.coverage_ratio) == "1.00000"
    assert str(database_scale.coverage_ratio) == "1.00000"
    assert compute_content_hash(low_scale) == compute_content_hash(database_scale)


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
    def __init__(self, quarantine=None):
        self.quarantine = quarantine

    def get_provider_run(self, session, run_id):
        return object()

    def get_raw_object(self, session, raw_id):
        return object()

    def get_quarantine_by_run(self, session, run_id):
        return self.quarantine


class _FakeSnapshotRepository:
    def get_pointer(self, session, *, scope, trade_date, capability_id, for_update=False):
        return None

    def upsert_pointer(self, session, pointer, *, expected_snapshot_id=None):
        return pointer


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

    mismatched_report = report.model_copy(update={"canonical_partition_id": "cpart_019dbd74-2a00-7000-8000-000000000999"})
    mismatched_service = SnapshotGateService(
        _FakeDatabase(),
        runtime_root=tmp_path,
        canonical_repository=_FakeCanonicalRepository(partition, mismatched_report),
        raw_repository=_FakeRawRepository(),
    )
    with pytest.raises(SnapshotGateError, match="evidence") as mismatch:
        mismatched_service.validate_gate(req)
    assert mismatch.value.error_code == "SNAPSHOT_QUALITY_EVIDENCE_MISMATCH"

    late = partition.model_copy(update={"min_available_at": datetime(2026, 8, 31, 9, tzinfo=timezone.utc)})
    late_service = SnapshotGateService(_FakeDatabase(), runtime_root=tmp_path, canonical_repository=_FakeCanonicalRepository(late, report), raw_repository=_FakeRawRepository())
    with pytest.raises(SnapshotGateError, match="not available"):
        late_service.validate_gate(req)

    manifest_payload["partition"]["schema_hash"] = compute_bytes_hash(b"different-schema")
    manifest_payload["manifest_hash"] = deterministic_manifest_hash(manifest_payload)
    (path.parent / "manifest.json").write_text(json.dumps(manifest_payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    with pytest.raises(SnapshotGateError, match="manifest is invalid") as schema_mismatch:
        service.validate_gate(req)
    assert schema_mismatch.value.error_code == "SNAPSHOT_PARTITION_MANIFEST_INVALID"


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


def test_benchmark_index_contract_rejects_stock_and_requires_explicit_return_semantics() -> None:
    row = BenchmarkIndexBar(benchmark_id="index:cn:000300.SH", asset_type="index", trade_date=date(2026, 8, 31), open=3900, high=3950, low=3880, close=3940, return_type="TOTAL_RETURN", total_return_close=3980, available_at=datetime(2026, 8, 31, 8, tzinfo=timezone.utc))
    assert row.asset_type == "index"
    with pytest.raises(ValueError, match="asset_type"):
        BenchmarkIndexBar.model_validate({**row.model_dump(mode="python"), "asset_type": "stock"})
    with pytest.raises(ValueError, match="TOTAL_RETURN"):
        BenchmarkIndexBar(benchmark_id="index:cn:000300.SH", asset_type="index", trade_date=date(2026, 8, 31), open=1, high=1, low=1, close=1, return_type="TOTAL_RETURN", available_at=datetime(2026, 8, 31, 8, tzinfo=timezone.utc))



    for invalid_id in ("index:", "index:cn", "index:cn:", "index:cn:000 300.SH", "index:cn:000300\\SH", "index:cn:000300/../SH", "index:cn:.."):
        with pytest.raises(ValueError, match="benchmark_id"):
            BenchmarkIndexBar(
                benchmark_id=invalid_id,
                trade_date=date(2026, 8, 31),
                open=1,
                high=1,
                low=1,
                close=1,
                return_type="PRICE",
                available_at=datetime(2026, 8, 31, 8, tzinfo=timezone.utc),
            )


def _snapshot_with_datasets(
    snapshot: DataSnapshot,
    dataset_ids: tuple[str, ...],
    *,
    publication_status: SnapshotPublicationStatus = SnapshotPublicationStatus.CERTIFIED,
    quality_status: QualityStatus = QualityStatus.COMPLETE,
    available_at: datetime | None = None,
) -> DataSnapshot:
    base = snapshot.canonical_partitions[0]
    partitions = []
    for index, dataset_id in enumerate(dataset_ids):
        partition_id = f"cpart_019dbd74-2a00-7000-8000-{105 + index:012d}"
        quality_report_id = f"quality_019dbd74-2a00-7000-8000-{105 + index:012d}"
        provider_run_id = f"prun_019dbd74-2a00-7000-8000-{1 + index:012d}"
        raw_object_id = f"raw_019dbd74-2a00-7000-8000-{4 + index:012d}"
        storage_ref = base.storage_ref.model_copy(
            update={
                "relative_path": (
                    f"canonical/dataset={dataset_id}/partition=2026-08-31/"
                    "revision=1/cpart.parquet"
                )
            }
        )
        partitions.append(
            base.model_copy(
                update={
                    "canonical_partition_id": partition_id,
                    "quality_report_id": quality_report_id,
                    "dataset_id": dataset_id,
                    "partition_key": f"{dataset_id}:2026-08-31",
                    "provider_run_refs": (provider_run_id,),
                    "raw_object_refs": (raw_object_id,),
                    "storage_ref": storage_ref,
                }
            )
        )
    partitions = tuple(partitions)
    partition_by_dataset = {item.dataset_id: item for item in partitions}
    if "security_master" not in partition_by_dataset or "trading_calendar" not in partition_by_dataset:
        raise ValueError("test snapshot fixtures must include security_master and trading_calendar partitions")
    draft = snapshot.model_copy(
        update={
            "canonical_partitions": partitions,
            "security_master_ref": partition_by_dataset["security_master"].canonical_partition_id,
            "calendar_ref": partition_by_dataset["trading_calendar"].canonical_partition_id,
            "quality_report_refs": tuple(item.quality_report_id for item in partitions),
            "publication_status": publication_status,
            "quality_status": quality_status,
            "available_at": available_at or snapshot.available_at,
            "published_at": snapshot.created_at if publication_status is SnapshotPublicationStatus.CERTIFIED else None,
            "certified_capabilities": (),
            "missing_capabilities": (),
        }
    )
    return DataSnapshot.model_validate(
        {**draft.model_dump(mode="python"), "manifest_hash": compute_snapshot_manifest_hash(draft)}
    )


def _backtest_rows(
    snapshot: DataSnapshot,
    *,
    bar_dates: tuple[date, ...] | None = None,
    benchmark_dates: tuple[date, ...] | None = None,
) -> dict[str, list[dict[str, object]]]:
    dates = bar_dates or (snapshot.trade_date,)
    benchmark_dates = benchmark_dates or dates
    available_at = snapshot.cutoff_at
    return {
        "security_master": [
            {"entity_key": "stock:cn:600519.SH", "trade_date": snapshot.trade_date, "available_at": available_at}
        ],
        "trading_calendar": [
            {"trade_date": snapshot.trade_date, "is_open": True, "available_at": available_at}
        ],
        "bar_1d_raw": [
            {
                "entity_key": "stock:cn:600519.SH",
                "trade_date": item,
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.5,
                "available_at": available_at,
            }
            for item in dates
        ],
        "benchmark_index_1d": [
            {
                "benchmark_id": "index:cn:000300.SH",
                "asset_type": "index",
                "trade_date": item,
                "open": 3900.0,
                "high": 3950.0,
                "low": 3880.0,
                "close": 3940.0,
                "return_type": "TOTAL_RETURN",
                "total_return_close": 3980.0,
                "available_at": available_at,
            }
            for item in benchmark_dates
        ],
    }


class _PersistedSnapshotRepository:
    def __init__(self, snapshot: DataSnapshot, certifications: tuple[CapabilityCertification, ...], requirement: ConsumerRequirement):
        self.snapshot = snapshot
        self.certifications = certifications
        self.requirement = requirement
        self.pointer = None

    def get_snapshot(self, session, snapshot_id, *, include_partitions=True, for_update=False):
        return self.snapshot if snapshot_id == self.snapshot.snapshot_id else None

    def list_capabilities(self, session, snapshot_id):
        return self.certifications if snapshot_id == self.snapshot.snapshot_id else ()

    def get_consumer_requirement(self, session, consumer_id):
        return self.requirement if consumer_id == self.requirement.consumer_id else None

    def get_pointer(self, session, *, scope, trade_date, capability_id, for_update=False):
        return self.pointer

    def upsert_pointer(self, session, pointer, *, expected_snapshot_id=None):
        self.pointer = pointer
        return pointer


class _PersistedCanonicalRepository:
    def __init__(self, snapshot: DataSnapshot):
        self.partitions = {}
        self.reports = {}
        self.mappings = {}
        for ref in snapshot.canonical_partitions:
            partition = CanonicalPartition(
                **ref.model_dump(
                    mode="python",
                    exclude={
                        "coverage_ratio",
                        "excluded_instrument_count",
                        "quality_threshold_version",
                    },
                ),
                distinct_entity_count=ref.row_count,
                created_at=snapshot.created_at,
                published_at=snapshot.published_at,
            )
            mapping_hash = ref.schema_hash
            report = CanonicalQualityReport(
                quality_report_id=ref.quality_report_id,
                canonical_partition_id=ref.canonical_partition_id,
                quality_status=ref.quality_status,
                rule_results={"schema": "PASS"},
                row_count=ref.row_count,
                rejected_row_count=0,
                duplicate_key_count=0,
                identity_unresolved_count=0,
                identity_ambiguous_count=0,
                coverage_ratio=ref.coverage_ratio,
                excluded_instrument_count=ref.excluded_instrument_count,
                quality_threshold_version=ref.quality_threshold_version,
                dataset_id=ref.dataset_id,
                dataset_schema_version=ref.dataset_schema_version,
                mapping_version="1.0.0",
                mapping_hash=mapping_hash,
                provider_run_refs=ref.provider_run_refs,
                raw_object_refs=ref.raw_object_refs,
                created_at=snapshot.created_at,
            )
            self.partitions[partition.canonical_partition_id] = partition
            self.reports[report.quality_report_id] = report
            self.mappings[("a_stock_data", ref.dataset_id, ref.dataset_schema_version, "1.0.0")] = SimpleNamespace(
                mapping_hash=mapping_hash
            )

    def get_partition(self, session, partition_id):
        return self.partitions.get(partition_id)

    def get_quality_report(self, session, report_id):
        return self.reports.get(report_id)

    def get_mapping(self, session, provider_id, dataset_id, dataset_schema_version, mapping_version):
        return self.mappings.get((provider_id, dataset_id, dataset_schema_version, mapping_version))


class _PersistedRawRepository:
    def __init__(self, snapshot: DataSnapshot):
        self.runs = {}
        self.raws = {}
        frequencies = {
            "security_master": "event",
            "trading_calendar": "daily",
            "bar_1d_raw": "daily",
            "benchmark_index_1d": "daily",
        }
        for ref in snapshot.canonical_partitions:
            policy_id = (
                snapshot.provider_policy_id
                if ref.dataset_id == "security_master"
                else f"{ref.dataset_id}_v1"
            )
            request_fingerprint = ref.partition_hash
            for run_id in ref.provider_run_refs:
                self.runs[run_id] = SimpleNamespace(
                    provider_run_id=run_id,
                    provider_id="a_stock_data",
                    actual_upstream="a-stock-data",
                    dataset_id=ref.dataset_id,
                    dataset_schema_version=ref.dataset_schema_version,
                    provider_policy_id=policy_id,
                    provider_policy_version=ref.provider_policy_version,
                    adapter_version="1.0.0",
                    capability_market="CN",
                    capability_frequency=frequencies[ref.dataset_id],
                    request_fingerprint=request_fingerprint,
                    observed_schema_hash=ref.schema_hash,
                    row_count=ref.row_count,
                    byte_count=ref.storage_ref.size_bytes,
                    run_outcome=ProviderRunOutcome.SUCCEEDED,
                    raw_object_refs=ref.raw_object_refs,
                    started_at=snapshot.cutoff_at,
                    finished_at=snapshot.cutoff_at,
                )
            for raw_id in ref.raw_object_refs:
                self.raws[raw_id] = SimpleNamespace(
                    raw_object_id=raw_id,
                    provider_run_id=ref.provider_run_refs[0],
                    provider_id="a_stock_data",
                    actual_upstream="a-stock-data",
                    dataset_id=ref.dataset_id,
                    dataset_schema_version=ref.dataset_schema_version,
                    request_fingerprint=request_fingerprint,
                    provider_schema_version="1.0.0",
                    observed_schema_hash=ref.schema_hash,
                    row_count=ref.row_count,
                    byte_count=ref.storage_ref.size_bytes,
                    observed_at=snapshot.cutoff_at,
                    source_published_at=snapshot.cutoff_at,
                    ingested_at=snapshot.cutoff_at,
                )

    def get_provider_run(self, session, run_id):
        return self.runs.get(run_id)

    def get_raw_object(self, session, raw_id):
        return self.raws.get(raw_id)

    def get_quarantine_by_run(self, session, run_id):
        return None


class _PersistedProviderRegistry:
    def __init__(self, snapshot: DataSnapshot, raw_repository: _PersistedRawRepository):
        self.providers = {
            "a_stock_data": SimpleNamespace(
                provider_id="a_stock_data",
                adapter_name="a_stock_data",
                adapter_version="1.0.0",
                enabled=True,
            )
        }
        self.datasets = {}
        self.capabilities = {}
        self.policies = {}
        self.raw_schemas = {}
        for ref in snapshot.canonical_partitions:
            run = raw_repository.runs[ref.provider_run_refs[0]]
            self.datasets[(ref.dataset_id, ref.dataset_schema_version)] = SimpleNamespace(
                dataset_id=ref.dataset_id,
                schema_version=ref.dataset_schema_version,
                frequency=run.capability_frequency,
            )
            self.capabilities[(
                run.provider_id,
                ref.dataset_id,
                ref.dataset_schema_version,
                run.capability_market,
                run.capability_frequency,
            )] = SimpleNamespace(
                provider_capability_status=ProviderCapabilityStatus.AVAILABLE,
                history_start=None,
            )
            self.policies[run.provider_policy_id] = SimpleNamespace(
                provider_policy_id=run.provider_policy_id,
                dataset_id=ref.dataset_id,
                dataset_schema_version=ref.dataset_schema_version,
                policy_version=ref.provider_policy_version,
                primary_provider_id=run.provider_id,
                supplemental_provider_ids=(),
                allowed_merge_mode=ProviderMergeMode.REPLACE_PARTITION,
                required_quality_rules=("schema",),
                effective_from=datetime(2026, 1, 1, tzinfo=timezone.utc),
                effective_to=None,
            )
            self.raw_schemas[(
                run.provider_id,
                run.adapter_version,
                ref.dataset_id,
                ref.dataset_schema_version,
                "1.0.0",
            )] = SimpleNamespace(expected_schema_hash=ref.schema_hash)

    def get_provider(self, session, provider_id):
        return self.providers.get(provider_id)

    def get_dataset(self, session, dataset_id, schema_version):
        return self.datasets.get((dataset_id, schema_version))

    def get_capability(self, session, provider_id, dataset_id, schema_version, market, frequency):
        return self.capabilities.get((provider_id, dataset_id, schema_version, market, frequency))

    def get_policy(self, session, provider_policy_id):
        return self.policies.get(provider_policy_id)

    def get_provider_raw_schema(
        self,
        session,
        provider_id,
        adapter_version,
        dataset_id,
        dataset_schema_version,
        provider_schema_version,
    ):
        return self.raw_schemas.get((
            provider_id,
            adapter_version,
            dataset_id,
            dataset_schema_version,
            provider_schema_version,
        ))


def _persisted_lineage_repositories(snapshot: DataSnapshot):
    canonical = _PersistedCanonicalRepository(snapshot)
    raw = _PersistedRawRepository(snapshot)
    registry = _PersistedProviderRegistry(snapshot, raw)
    return canonical, raw, registry


def _certified_snapshot_fixture() -> tuple[DataSnapshot, tuple[CapabilityCertification, ...], ConsumerRequirement]:
    requirement = ConsumerRequirement(
        consumer_id="formal_backtest",
        consumer_kind=ConsumerKind.FORMAL_BACKTEST,
        required_capabilities=("backtest_core",),
        accepted_publication_statuses=(SnapshotPublicationStatus.CERTIFIED,),
    )
    draft = _snapshot_with_datasets(
        load_snapshot(),
        ("security_master", "trading_calendar", "bar_1d_raw", "benchmark_index_1d"),
    )
    certifications = SnapshotCapabilityEngine.certify(draft, now=datetime(2026, 8, 31, 9, tzinfo=timezone.utc), partition_rows=_backtest_rows(draft))
    certified = tuple(item.capability_id for item in certifications if item.capability_status is SnapshotCapabilityStatus.CERTIFIED)
    certified_snapshot = draft.model_copy(
        update={
            "certified_capabilities": certified,
            "missing_capabilities": tuple(
                item.capability_id
                for item in certifications
                if item.capability_status is not SnapshotCapabilityStatus.CERTIFIED
            ),
        }
    )
    snapshot = DataSnapshot.model_validate(
        {
            **certified_snapshot.model_dump(mode="python"),
            "manifest_hash": compute_snapshot_manifest_hash(certified_snapshot),
        }
    )
    return snapshot, certifications, requirement


def test_backtest_core_requires_cross_partition_evidence_even_when_refs_are_complete() -> None:
    snapshot = _snapshot_with_datasets(load_snapshot(), ("security_master", "trading_calendar", "bar_1d_raw", "benchmark_index_1d"))
    item = next(item for item in SnapshotCapabilityEngine.certify(snapshot, now=datetime(2026, 8, 31, 9, tzinfo=timezone.utc)) if item.capability_id == "backtest_core")
    assert item.capability_status is SnapshotCapabilityStatus.UNAVAILABLE
    assert item.reason_code == "SNAPSHOT_CROSS_PARTITION_EVIDENCE_REQUIRED"


def test_backtest_core_rejects_mismatched_bar_and_benchmark_date_ranges() -> None:
    snapshot = _snapshot_with_datasets(load_snapshot(), ("security_master", "trading_calendar", "bar_1d_raw", "benchmark_index_1d"))
    item = next(
        item
        for item in SnapshotCapabilityEngine.certify(
            snapshot,
            now=datetime(2026, 8, 31, 9, tzinfo=timezone.utc),
            partition_rows=_backtest_rows(snapshot, benchmark_dates=(date(2026, 8, 30),)),
        )
        if item.capability_id == "backtest_core"
    )
    assert item.capability_status is SnapshotCapabilityStatus.UNAVAILABLE
    assert item.reason_code == "SNAPSHOT_DATE_RANGE_CONFLICT"


def test_backtest_core_rejects_point_in_time_violation_in_partition_rows() -> None:
    snapshot = _snapshot_with_datasets(
        load_snapshot(),
        ("security_master", "trading_calendar", "bar_1d_raw", "benchmark_index_1d"),
    )
    rows = _backtest_rows(snapshot)
    rows["bar_1d_raw"][0]["available_at"] = snapshot.cutoff_at.replace(hour=snapshot.cutoff_at.hour + 1)
    item = next(
        item
        for item in SnapshotCapabilityEngine.certify(
            snapshot,
            now=datetime(2026, 8, 31, 9, tzinfo=timezone.utc),
            partition_rows=rows,
        )
        if item.capability_id == "backtest_core"
    )
    assert item.capability_status is SnapshotCapabilityStatus.UNAVAILABLE
    assert item.reason_code == "SNAPSHOT_PIT_VIOLATION"


def test_backtest_core_rejects_overlapping_listing_intervals() -> None:
    snapshot = _snapshot_with_datasets(
        load_snapshot(),
        ("security_master", "trading_calendar", "bar_1d_raw", "benchmark_index_1d"),
    )
    rows = _backtest_rows(snapshot)
    rows["listing_status_history"] = [
        {"entity_key": "stock:cn:600519.SH", "effective_from": date(2020, 1, 1), "effective_to": date(2026, 9, 1)},
        {"entity_key": "stock:cn:600519.SH", "effective_from": date(2026, 8, 31), "effective_to": None},
    ]
    item = next(
        item
        for item in SnapshotCapabilityEngine.certify(
            snapshot,
            now=datetime(2026, 8, 31, 9, tzinfo=timezone.utc),
            partition_rows=rows,
        )
        if item.capability_id == "backtest_core"
    )
    assert item.capability_status is SnapshotCapabilityStatus.UNAVAILABLE
    assert item.reason_code == "SNAPSHOT_LISTING_INTERVAL_CONFLICT"


def test_backtest_core_rejects_duplicate_revision_rows() -> None:
    snapshot = _snapshot_with_datasets(
        load_snapshot(),
        ("security_master", "trading_calendar", "bar_1d_raw", "benchmark_index_1d"),
    )
    rows = _backtest_rows(snapshot)
    rows["bar_1d_raw"].extend(
        [
            {"trade_date": snapshot.trade_date, "available_at": snapshot.cutoff_at, "revision": 1},
            {"trade_date": snapshot.trade_date, "available_at": snapshot.cutoff_at, "revision": 1},
        ]
    )
    item = next(
        item
        for item in SnapshotCapabilityEngine.certify(
            snapshot,
            now=datetime(2026, 8, 31, 9, tzinfo=timezone.utc),
            partition_rows=rows,
        )
        if item.capability_id == "backtest_core"
    )
    assert item.capability_status is SnapshotCapabilityStatus.UNAVAILABLE
    assert item.reason_code == "SNAPSHOT_REVISION_CONFLICT"

def test_formal_consumer_rejects_forged_certification_without_benchmark() -> None:
    requirement = ConsumerRequirement(
        consumer_id="formal_backtest",
        consumer_kind=ConsumerKind.FORMAL_BACKTEST,
        required_capabilities=("backtest_core",),
        accepted_publication_statuses=(SnapshotPublicationStatus.CERTIFIED,),
    )
    forged = _snapshot_with_datasets(load_snapshot(), ("security_master", "trading_calendar", "bar_1d_raw"))
    forged = forged.model_copy(
        update={
            "certified_capabilities": ("backtest_core",),
            "missing_capabilities": (),
            "manifest_hash": compute_snapshot_manifest_hash(forged.model_copy(update={"certified_capabilities": ("backtest_core",), "missing_capabilities": ()})),
        }
    )
    certification = CapabilityCertification(
        capability_id="backtest_core",
        capability_status=SnapshotCapabilityStatus.CERTIFIED,
        evidence_refs=forged.quality_report_refs,
        certified_at=datetime(2026, 8, 31, 9, tzinfo=timezone.utc),
        snapshot_id=forged.snapshot_id,
    )
    repository = _PersistedSnapshotRepository(forged, (certification,), requirement)
    service = SnapshotGateService(_FakeDatabase(), repository=repository)
    service._validate_persisted_snapshot_files = lambda snapshot: None
    with pytest.raises(SnapshotGateError) as captured:
        service.check_consumer(forged, requirement)
    assert captured.value.error_code == "SNAPSHOT_BACKTEST_CORE_UNAVAILABLE"


def test_formal_consumer_requires_registered_snapshot_and_capability_evidence() -> None:
    snapshot, certifications, requirement = _certified_snapshot_fixture()
    repository = _PersistedSnapshotRepository(snapshot, certifications, requirement)
    canonical, raw, registry = _persisted_lineage_repositories(snapshot)
    service = SnapshotGateService(
        _FakeDatabase(),
        repository=repository,
        canonical_repository=canonical,
        raw_repository=raw,
        provider_registry=registry,
        clock=lambda: datetime(2026, 8, 31, 9, tzinfo=timezone.utc),
    )
    service._validate_persisted_snapshot_files = lambda snapshot: None
    assert service.check_consumer(snapshot, requirement).value == "ACCEPTED"

    forged = snapshot.model_copy(update={"certified_capabilities": (), "missing_capabilities": ("backtest_core",), "manifest_hash": compute_snapshot_manifest_hash(snapshot.model_copy(update={"certified_capabilities": (), "missing_capabilities": ("backtest_core",)}))})
    with pytest.raises(SnapshotGateError) as captured:
        service.check_consumer(forged, requirement)
    assert captured.value.error_code == "SNAPSHOT_PERSISTED_STATE_MISMATCH"


def test_current_pointer_rejects_unregistered_snapshot_even_if_capability_is_claimed() -> None:
    snapshot, certifications, requirement = _certified_snapshot_fixture()
    repository = _PersistedSnapshotRepository(snapshot, certifications, requirement)
    service = SnapshotGateService(_FakeDatabase(), repository=repository, clock=lambda: datetime(2026, 8, 31, 9, tzinfo=timezone.utc))
    service._validate_persisted_snapshot_files = lambda snapshot: None
    forged = snapshot.model_copy(update={"snapshot_id": "ds_019dbd74-2a00-7000-8000-000000009999", "manifest_hash": compute_snapshot_manifest_hash(snapshot.model_copy(update={"snapshot_id": "ds_019dbd74-2a00-7000-8000-000000009999"}))})
    with pytest.raises(SnapshotGateError) as captured:
        service.update_current_pointer(scope="global", trade_date=forged.trade_date, capability_id="backtest_core", snapshot=forged)
    assert captured.value.error_code == "SNAPSHOT_NOT_REGISTERED"


def test_backtest_core_requires_complete_required_partitions_and_benchmark_dataset() -> None:
    snapshot = load_snapshot()
    complete = _snapshot_with_datasets(snapshot, ("security_master", "trading_calendar", "bar_1d_raw", "benchmark_index_1d"))
    complete = complete.model_copy(update={"manifest_hash": compute_snapshot_manifest_hash(complete)})
    certification = next(item for item in SnapshotCapabilityEngine.certify(complete, now=datetime(2026, 8, 31, 9, tzinfo=timezone.utc), partition_rows=_backtest_rows(complete)) if item.capability_id == "backtest_core")
    assert certification.capability_status is SnapshotCapabilityStatus.CERTIFIED

    partial = _snapshot_with_datasets(snapshot, ("security_master", "trading_calendar", "bar_1d_raw", "benchmark_index_1d"), quality_status=QualityStatus.PARTIAL)
    partial = partial.model_copy(update={"canonical_partitions": tuple(item.model_copy(update={"quality_status": QualityStatus.PARTIAL}) for item in partial.canonical_partitions)})
    partial = partial.model_copy(update={"manifest_hash": compute_snapshot_manifest_hash(partial)})
    partial_cert = next(item for item in SnapshotCapabilityEngine.certify(partial, now=datetime(2026, 8, 31, 9, tzinfo=timezone.utc), partition_rows=_backtest_rows(partial)) if item.capability_id == "backtest_core")
    assert partial_cert.capability_status is SnapshotCapabilityStatus.PARTIAL

    missing = _snapshot_with_datasets(snapshot, ("security_master", "trading_calendar", "bar_1d_raw"))
    missing = missing.model_copy(update={"manifest_hash": compute_snapshot_manifest_hash(missing)})
    missing_cert = next(item for item in SnapshotCapabilityEngine.certify(missing, now=datetime(2026, 8, 31, 9, tzinfo=timezone.utc)) if item.capability_id == "backtest_core")
    assert missing_cert.capability_status is SnapshotCapabilityStatus.UNAVAILABLE


def test_backtest_core_ignores_unrelated_partial_partition_for_capability() -> None:
    snapshot = load_snapshot()
    complete = _snapshot_with_datasets(snapshot, ("security_master", "trading_calendar", "bar_1d_raw", "benchmark_index_1d"))
    unrelated = complete.canonical_partitions[0].model_copy(
        update={
            "canonical_partition_id": "cpart_019dbd74-2a00-7000-8000-000000000109",
            "dataset_id": "news_research",
            "partition_key": "news_research:2026-08-31",
            "quality_status": QualityStatus.PARTIAL,
        }
    )
    partial_snapshot = complete.model_copy(
        update={
            "canonical_partitions": (*complete.canonical_partitions, unrelated),
            "quality_status": QualityStatus.PARTIAL,
        }
    )
    partial_snapshot = partial_snapshot.model_copy(update={"manifest_hash": compute_snapshot_manifest_hash(partial_snapshot)})
    item = next(
        item
        for item in SnapshotCapabilityEngine.certify(partial_snapshot, now=datetime(2026, 8, 31, 9, tzinfo=timezone.utc), partition_rows=_backtest_rows(partial_snapshot))
        if item.capability_id == "backtest_core"
    )
    assert item.capability_status is SnapshotCapabilityStatus.CERTIFIED


def test_backtest_core_stale_and_provisional_are_distinct() -> None:
    snapshot = load_snapshot()
    provisional = _snapshot_with_datasets(snapshot, ("security_master", "trading_calendar", "bar_1d_raw", "benchmark_index_1d"), publication_status=SnapshotPublicationStatus.PROVISIONAL)
    provisional = provisional.model_copy(update={"manifest_hash": compute_snapshot_manifest_hash(provisional)})
    item = next(item for item in SnapshotCapabilityEngine.certify(provisional, now=datetime(2026, 8, 31, 9, tzinfo=timezone.utc), partition_rows=_backtest_rows(provisional)) if item.capability_id == "backtest_core")
    assert item.capability_status is SnapshotCapabilityStatus.PROVISIONAL

    stale = _snapshot_with_datasets(snapshot, ("security_master", "trading_calendar", "bar_1d_raw", "benchmark_index_1d"), available_at=datetime(2026, 8, 1, 8, tzinfo=timezone.utc))
    stale = stale.model_copy(update={"manifest_hash": compute_snapshot_manifest_hash(stale)})
    item = next(item for item in SnapshotCapabilityEngine.certify(stale, now=datetime(2026, 8, 31, 9, tzinfo=timezone.utc), partition_rows=_backtest_rows(stale)) if item.capability_id == "backtest_core")
    assert item.capability_status is SnapshotCapabilityStatus.STALE


def test_backtest_core_rejects_zero_coverage_partition() -> None:
    snapshot = load_snapshot()
    incomplete = _snapshot_with_datasets(snapshot, ("security_master", "trading_calendar", "bar_1d_raw", "benchmark_index_1d"))
    partitions = tuple(item.model_copy(update={"row_count": 0}) for item in incomplete.canonical_partitions)
    incomplete = incomplete.model_copy(update={"canonical_partitions": partitions})
    incomplete = incomplete.model_copy(update={"manifest_hash": compute_snapshot_manifest_hash(incomplete)})
    item = next(item for item in SnapshotCapabilityEngine.certify(incomplete, now=datetime(2026, 8, 31, 9, tzinfo=timezone.utc), partition_rows=_backtest_rows(incomplete)) if item.capability_id == "backtest_core")
    assert item.capability_status is SnapshotCapabilityStatus.PARTIAL
    assert item.reason_code == "COVERAGE_INSUFFICIENT"


def test_gate_rejects_failed_schema_rule_before_snapshot_build(tmp_path: Path) -> None:
    now = datetime(2026, 8, 31, 8, tzinfo=timezone.utc)
    content = b"x"
    content_hash = compute_bytes_hash(content)
    partition_id = "cpart_019dbd74-2a00-7000-8000-000000000205"
    quality_id = "quality_019dbd74-2a00-7000-8000-000000000206"
    run_id = "prun_019dbd74-2a00-7000-8000-000000000201"
    raw_id = "raw_019dbd74-2a00-7000-8000-000000000204"
    storage_ref = StorageRef(storage_backend=StorageBackend.LOCAL_FS, storage_namespace=StorageNamespace.APP, relative_path="canonical/dataset=benchmark_index_1d/partition=2026-08-31/revision=1/cpart.parquet", content_hash=content_hash, media_type="application/vnd.apache.parquet", size_bytes=1)
    partition = CanonicalPartition(canonical_partition_id=partition_id, dataset_id="benchmark_index_1d", dataset_schema_version="1.0.0", partition_key="2026-08-31", revision=1, revision_kind=RevisionKind.INITIAL, provider_policy_version="1.0.0", provider_run_refs=(run_id,), raw_object_refs=(raw_id,), min_available_at=now, row_count=1, distinct_entity_count=1, storage_ref=storage_ref, partition_hash=content_hash, schema_hash=content_hash, quality_status=QualityStatus.COMPLETE, quality_report_id=quality_id, created_at=now, published_at=now)
    report = CanonicalQualityReport(quality_report_id=quality_id, canonical_partition_id=partition_id, quality_status=QualityStatus.COMPLETE, rule_results={"schema_drift": "FAIL"}, row_count=1, rejected_row_count=0, duplicate_key_count=0, identity_unresolved_count=0, identity_ambiguous_count=0, created_at=now)
    path = SnapshotManifestPublisher(tmp_path).resolver.resolve(storage_ref)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    manifest_payload = {"partition": partition.model_dump(mode="json"), "quality_report": report.model_dump(mode="json")}
    manifest_payload["manifest_hash"] = deterministic_manifest_hash(manifest_payload)
    (path.parent / "manifest.json").write_text(json.dumps(manifest_payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    service = SnapshotGateService(_FakeDatabase(), runtime_root=tmp_path, canonical_repository=_FakeCanonicalRepository(partition, report), raw_repository=_FakeRawRepository())
    from src.schemas.platform import SnapshotBuildTaskRequirements
    req = SnapshotBuildTaskRequirements(trade_date=date(2026, 8, 31), cutoff_at=now, provider_policy_id="policy_core", provider_policy_version="1.0.0", security_master_ref=partition_id, calendar_ref=partition_id, canonical_partition_ids=(partition_id,), requested_capabilities=("identity_core",))
    with pytest.raises(SnapshotGateError, match="schema drift"):
        service.validate_gate(req)


def test_gate_rejects_open_quarantine_for_partition_lineage(tmp_path: Path) -> None:
    now = datetime(2026, 8, 31, 8, tzinfo=timezone.utc)
    content = b"x"
    content_hash = compute_bytes_hash(content)
    partition_id = "cpart_019dbd74-2a00-7000-8000-000000000305"
    quality_id = "quality_019dbd74-2a00-7000-8000-000000000306"
    run_id = "prun_019dbd74-2a00-7000-8000-000000000301"
    raw_id = "raw_019dbd74-2a00-7000-8000-000000000304"
    storage_ref = StorageRef(storage_backend=StorageBackend.LOCAL_FS, storage_namespace=StorageNamespace.APP, relative_path="canonical/dataset=security_master/partition=2026-08-31/revision=1/cpart.parquet", content_hash=content_hash, media_type="application/vnd.apache.parquet", size_bytes=1)
    partition = CanonicalPartition(canonical_partition_id=partition_id, dataset_id="security_master", dataset_schema_version="1.0.0", partition_key="2026-08-31", revision=1, revision_kind=RevisionKind.INITIAL, provider_policy_version="1.0.0", provider_run_refs=(run_id,), raw_object_refs=(raw_id,), min_available_at=now, row_count=1, distinct_entity_count=1, storage_ref=storage_ref, partition_hash=content_hash, schema_hash=content_hash, quality_status=QualityStatus.COMPLETE, quality_report_id=quality_id, created_at=now, published_at=now)
    report = CanonicalQualityReport(quality_report_id=quality_id, canonical_partition_id=partition_id, quality_status=QualityStatus.COMPLETE, rule_results={"schema": "PASS"}, row_count=1, rejected_row_count=0, duplicate_key_count=0, identity_unresolved_count=0, identity_ambiguous_count=0, created_at=now)
    path = SnapshotManifestPublisher(tmp_path).resolver.resolve(storage_ref)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    manifest_payload = {"partition": partition.model_dump(mode="json"), "quality_report": report.model_dump(mode="json")}
    manifest_payload["manifest_hash"] = deterministic_manifest_hash(manifest_payload)
    (path.parent / "manifest.json").write_text(json.dumps(manifest_payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    service = SnapshotGateService(_FakeDatabase(), runtime_root=tmp_path, canonical_repository=_FakeCanonicalRepository(partition, report), raw_repository=_FakeRawRepository(quarantine=SimpleNamespace(quarantine_status=QuarantineStatus.OPEN)))
    from src.schemas.platform import SnapshotBuildTaskRequirements
    req = SnapshotBuildTaskRequirements(trade_date=date(2026, 8, 31), cutoff_at=now, provider_policy_id="policy_core", provider_policy_version="1.0.0", security_master_ref=partition_id, calendar_ref=partition_id, canonical_partition_ids=(partition_id,), requested_capabilities=("identity_core",))
    with pytest.raises(SnapshotGateError, match="quarantine"):
        service.validate_gate(req)


def test_formal_consumer_enforces_minimum_quality_even_if_capability_claimed() -> None:
    snapshot = load_snapshot()
    partial = _snapshot_with_datasets(snapshot, ("security_master", "trading_calendar", "bar_1d_raw", "benchmark_index_1d"), quality_status=QualityStatus.PARTIAL)
    partial = partial.model_copy(update={"certified_capabilities": ("backtest_core",), "missing_capabilities": (), "manifest_hash": compute_snapshot_manifest_hash(partial)})
    requirement = ConsumerRequirement(
        consumer_id="formal_backtest",
        consumer_kind=ConsumerKind.FORMAL_BACKTEST,
        required_capabilities=("backtest_core",),
        accepted_publication_statuses=(SnapshotPublicationStatus.CERTIFIED,),
    )
    service = object.__new__(SnapshotGateService)
    with pytest.raises(SnapshotGateError, match="quality"):
        service.check_consumer(partial, requirement)


def test_current_pointer_rejects_trade_date_mismatch() -> None:
    snapshot = _snapshot_with_datasets(load_snapshot(), ("security_master", "trading_calendar", "bar_1d_raw", "benchmark_index_1d"))
    snapshot = snapshot.model_copy(update={"certified_capabilities": ("backtest_core",), "missing_capabilities": (), "manifest_hash": compute_snapshot_manifest_hash(snapshot)})
    service = SnapshotGateService(_FakeDatabase(), repository=_FakeSnapshotRepository())
    with pytest.raises(SnapshotGateError, match="trade date"):
        service.update_current_pointer(
            scope="global",
            trade_date=date(2026, 9, 1),
            capability_id="backtest_core",
            snapshot=snapshot,
        )


def test_snapshot_gate_aggregates_partition_quality_for_consumer_visibility() -> None:
    refs = (load_snapshot().canonical_partitions[0].model_copy(update={"quality_status": QualityStatus.PARTIAL}),)
    assert SnapshotGateService.aggregate_partition_quality(refs) is QualityStatus.PARTIAL


def test_backtest_core_enforces_coverage_ratio_and_exclusion_thresholds() -> None:
    snapshot = _snapshot_with_datasets(load_snapshot(), ("security_master", "trading_calendar", "bar_1d_raw", "benchmark_index_1d"))
    partitions = tuple(item.model_copy(update={"coverage_ratio": Decimal("0.997")}) for item in snapshot.canonical_partitions)
    incomplete = snapshot.model_copy(update={"canonical_partitions": partitions})
    incomplete = incomplete.model_copy(update={"manifest_hash": compute_snapshot_manifest_hash(incomplete)})
    item = next(item for item in SnapshotCapabilityEngine.certify(incomplete, now=datetime(2026, 8, 31, 9, tzinfo=timezone.utc), partition_rows=_backtest_rows(incomplete)) if item.capability_id == "backtest_core")
    assert item.capability_status is SnapshotCapabilityStatus.PARTIAL
    assert item.reason_code == "COVERAGE_INSUFFICIENT"

    excluded = tuple(item.model_copy(update={"excluded_instrument_count": 11}) for item in snapshot.canonical_partitions)
    incomplete = snapshot.model_copy(update={"canonical_partitions": excluded})
    incomplete = incomplete.model_copy(update={"manifest_hash": compute_snapshot_manifest_hash(incomplete)})
    item = next(item for item in SnapshotCapabilityEngine.certify(incomplete, now=datetime(2026, 8, 31, 9, tzinfo=timezone.utc), partition_rows=_backtest_rows(incomplete)) if item.capability_id == "backtest_core")
    assert item.capability_status is SnapshotCapabilityStatus.PARTIAL
    assert item.reason_code == "COVERAGE_INSUFFICIENT"
