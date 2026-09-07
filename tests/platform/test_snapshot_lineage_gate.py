from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.artifacts.hashing import compute_bytes_hash
from src.artifacts.namespace import StorageNamespaceResolver
from src.schemas.platform import (
    CanonicalPartition,
    CanonicalQualityReport,
    ProviderCapabilityStatus,
    ProviderMergeMode,
    ProviderRunOutcome,
    QualityStatus,
    ResourceType,
    RevisionKind,
    SnapshotBuildTaskRequirements,
    StorageBackend,
    StorageNamespace,
    StorageRef,
    generate_resource_id,
)
from src.services.platform.canonical_normalization import deterministic_manifest_hash
from src.services.platform.snapshot import SnapshotGateError, SnapshotGateService


NOW = datetime(2026, 8, 31, 8, tzinfo=timezone.utc)
DATASETS = ("security_master", "trading_calendar", "bar_1d_raw", "benchmark_index_1d")


def _resource(prefix: ResourceType, number: int) -> str:
    return generate_resource_id(prefix, timestamp_ms=1788177600000, random_bits=number)


class _Database:
    @contextmanager
    def transaction(self):
        yield object()


class _TrackingDatabase:
    def __init__(self) -> None:
        self.transaction_active = False

    @contextmanager
    def transaction(self):
        if self.transaction_active:
            raise AssertionError("nested transaction is not expected in this probe")
        self.transaction_active = True
        try:
            yield object()
        finally:
            self.transaction_active = False


class _CanonicalRepository:
    def __init__(self, partitions, reports, mappings):
        self.partitions = partitions
        self.reports = reports
        self.mappings = mappings

    def get_partition(self, session, partition_id):
        return self.partitions.get(partition_id)

    def get_quality_report(self, session, report_id):
        return self.reports.get(report_id)

    def get_mapping(self, session, provider_id, dataset_id, dataset_schema_version, mapping_version):
        return self.mappings.get((provider_id, dataset_id, dataset_schema_version, mapping_version))


class _RawRepository:
    def __init__(self, runs, raws):
        self.runs = runs
        self.raws = raws

    def get_provider_run(self, session, run_id):
        return self.runs.get(run_id)

    def get_raw_object(self, session, raw_id):
        return self.raws.get(raw_id)

    def get_quarantine_by_run(self, session, run_id):
        return None


class _Registry:
    def __init__(self, providers, datasets, capabilities, policies, raw_schemas):
        self.providers = providers
        self.datasets = datasets
        self.capabilities = capabilities
        self.policies = policies
        self.raw_schemas = raw_schemas

    def get_provider(self, session, provider_id):
        return self.providers.get(provider_id)

    def get_dataset(self, session, dataset_id, schema_version):
        return self.datasets.get((dataset_id, schema_version))

    def get_capability(self, session, provider_id, dataset_id, schema_version, market, frequency):
        return self.capabilities.get((provider_id, dataset_id, schema_version, market, frequency))

    def get_policy(self, session, provider_policy_id):
        return self.policies.get(provider_policy_id)

    def get_provider_raw_schema(self, session, provider_id, adapter_version, dataset_id, dataset_schema_version, provider_schema_version):
        return self.raw_schemas.get((provider_id, adapter_version, dataset_id, dataset_schema_version, provider_schema_version))


class _Fixture:
    def __init__(self, tmp_path: Path):
        partitions = {}
        reports = {}
        mappings = {}
        runs = {}
        raws = {}
        providers = {
            "a_stock_data": SimpleNamespace(provider_id="a_stock_data", adapter_name="a_stock_data", adapter_version="1.0.0", enabled=True),
            "financial_api": SimpleNamespace(provider_id="financial_api", adapter_name="financial_api", adapter_version="1.0.0", enabled=True),
        }
        datasets = {}
        capabilities = {}
        policies = {}
        raw_schemas = {}
        self.rows = {
            "security_master": [{"entity_key": "stock:cn:600519.SH", "trade_date": NOW.date(), "available_at": NOW}],
            "trading_calendar": [{"trade_date": NOW.date(), "is_open": True, "available_at": NOW}],
            "bar_1d_raw": [{"entity_key": "stock:cn:600519.SH", "trade_date": NOW.date(), "available_at": NOW}],
            "benchmark_index_1d": [{
                "benchmark_id": "index:cn:000300.SH", "asset_type": "index", "trade_date": NOW.date(),
                "open": 3900, "high": 3950, "low": 3880, "close": 3940,
                "return_type": "TOTAL_RETURN", "total_return_close": 3980, "available_at": NOW,
            }],
        }
        frequencies = {"security_master": "event", "trading_calendar": "daily", "bar_1d_raw": "daily", "benchmark_index_1d": "daily"}
        for index, dataset_id in enumerate(DATASETS, start=1):
            provider_run_id = _resource(ResourceType.PROVIDER_RUN, 100 + index)
            raw_object_id = _resource(ResourceType.RAW_OBJECT, 200 + index)
            partition_id = _resource(ResourceType.CANONICAL_PARTITION, 300 + index)
            quality_id = _resource(ResourceType.QUALITY_REPORT, 400 + index)
            policy_id = f"{dataset_id}_v1"
            request_fingerprint = compute_bytes_hash(f"request:{dataset_id}".encode())
            raw_schema_hash = compute_bytes_hash(f"raw-schema:{dataset_id}".encode())
            mapping_hash = compute_bytes_hash(f"mapping:{dataset_id}".encode())
            content = f"canonical:{dataset_id}".encode()
            content_hash = compute_bytes_hash(content)
            storage_ref = StorageRef(
                storage_backend=StorageBackend.LOCAL_FS,
                storage_namespace=StorageNamespace.APP,
                relative_path=f"canonical/dataset={dataset_id}/trade_date={NOW.date().isoformat()}/partition-{index}.bin",
                content_hash=content_hash,
                media_type="application/octet-stream",
                size_bytes=len(content),
            )
            partition = CanonicalPartition(
                canonical_partition_id=partition_id,
                dataset_id=dataset_id,
                dataset_schema_version="1.0.0",
                partition_key=NOW.date().isoformat(),
                revision=1,
                revision_kind=RevisionKind.INITIAL,
                provider_policy_version="1.0.0",
                provider_run_refs=(provider_run_id,),
                raw_object_refs=(raw_object_id,),
                min_available_at=NOW - timezone.utc.utcoffset(NOW),
                row_count=1,
                distinct_entity_count=1,
                storage_ref=storage_ref,
                partition_hash=content_hash,
                schema_hash=compute_bytes_hash(f"canonical-schema:{dataset_id}".encode()),
                quality_status=QualityStatus.COMPLETE,
                quality_report_id=quality_id,
                created_at=NOW - timezone.utc.utcoffset(NOW),
                published_at=NOW,
            )
            report = CanonicalQualityReport(
                quality_report_id=quality_id,
                canonical_partition_id=partition_id,
                quality_status=QualityStatus.COMPLETE,
                rule_results={"schema": "PASS"},
                row_count=1,
                rejected_row_count=0,
                duplicate_key_count=0,
                identity_unresolved_count=0,
                identity_ambiguous_count=0,
                dataset_id=dataset_id,
                dataset_schema_version="1.0.0",
                mapping_version="1.0.0",
                mapping_hash=mapping_hash,
                provider_run_refs=(provider_run_id,),
                raw_object_refs=(raw_object_id,),
                created_at=NOW,
            )
            provider_run = SimpleNamespace(
                provider_run_id=provider_run_id,
                provider_id="a_stock_data",
                actual_upstream="a-stock-data",
                dataset_id=dataset_id,
                dataset_schema_version="1.0.0",
                provider_policy_id=policy_id,
                provider_policy_version="1.0.0",
                adapter_version="1.0.0",
                capability_market="CN",
                capability_frequency=frequencies[dataset_id],
                request_fingerprint=request_fingerprint,
                observed_schema_hash=raw_schema_hash,
                row_count=1,
                byte_count=len(content),
                run_outcome=ProviderRunOutcome.SUCCEEDED,
                raw_object_refs=(raw_object_id,),
                finished_at=NOW,
            )
            raw_object = SimpleNamespace(
                raw_object_id=raw_object_id,
                provider_run_id=provider_run_id,
                provider_id="a_stock_data",
                actual_upstream="a-stock-data",
                dataset_id=dataset_id,
                dataset_schema_version="1.0.0",
                request_fingerprint=request_fingerprint,
                provider_schema_version="1.0.0",
                observed_schema_hash=raw_schema_hash,
                row_count=1,
                byte_count=len(content),
                observed_at=NOW - timezone.utc.utcoffset(NOW),
                ingested_at=NOW,
            )
            policy = SimpleNamespace(
                provider_policy_id=policy_id,
                dataset_id=dataset_id,
                dataset_schema_version="1.0.0",
                policy_version="1.0.0",
                primary_provider_id="a_stock_data",
                supplemental_provider_ids=("financial_api",),
                allowed_merge_mode=ProviderMergeMode.REPLACE_PARTITION,
                effective_from=datetime(2026, 1, 1, tzinfo=timezone.utc),
                effective_to=None,
            )
            datasets[(dataset_id, "1.0.0")] = SimpleNamespace(dataset_id=dataset_id, schema_version="1.0.0", frequency=frequencies[dataset_id])
            capabilities[("a_stock_data", dataset_id, "1.0.0", "CN", frequencies[dataset_id])] = SimpleNamespace(
                provider_capability_status=ProviderCapabilityStatus.AVAILABLE,
                history_start=None,
            )
            capabilities[("financial_api", dataset_id, "1.0.0", "CN", frequencies[dataset_id])] = SimpleNamespace(
                provider_capability_status=ProviderCapabilityStatus.AVAILABLE,
                history_start=None,
            )
            policies[policy_id] = policy
            raw_schemas[("a_stock_data", "1.0.0", dataset_id, "1.0.0", "1.0.0")] = SimpleNamespace(expected_schema_hash=raw_schema_hash)
            mappings[("a_stock_data", dataset_id, "1.0.0", "1.0.0")] = SimpleNamespace(mapping_hash=mapping_hash)
            partitions[partition_id] = partition
            reports[quality_id] = report
            runs[provider_run_id] = provider_run
            raws[raw_object_id] = raw_object

            path = StorageNamespaceResolver(tmp_path).resolve(storage_ref)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            manifest = {"partition": {
                "canonical_partition_id": partition_id,
                "dataset_id": dataset_id,
                "dataset_schema_version": "1.0.0",
                "partition_hash": content_hash,
                "schema_hash": partition.schema_hash,
                "quality_report_id": quality_id,
                "quality_status": "COMPLETE",
                "row_count": 1,
            }}
            manifest["manifest_hash"] = deterministic_manifest_hash(manifest)
            (path.parent / "manifest.json").write_text(json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
        self.canonical = _CanonicalRepository(partitions, reports, mappings)
        self.raw = _RawRepository(runs, raws)
        self.registry = _Registry(providers, datasets, capabilities, policies, raw_schemas)
        self.requirements = SnapshotBuildTaskRequirements(
            trade_date=NOW.date(),
            cutoff_at=NOW,
            provider_policy_id="bar_1d_raw_v1",
            provider_policy_version="1.0.0",
            security_master_ref=next(item.canonical_partition_id for item in partitions.values() if item.dataset_id == "security_master"),
            calendar_ref=next(item.canonical_partition_id for item in partitions.values() if item.dataset_id == "trading_calendar"),
            canonical_partition_ids=tuple(partitions),
            requested_capabilities=("backtest_core",),
        )


def _service(fixture: _Fixture, tmp_path: Path) -> SnapshotGateService:
    return SnapshotGateService(
        _Database(),
        runtime_root=tmp_path,
        canonical_repository=fixture.canonical,
        raw_repository=fixture.raw,
        provider_registry=fixture.registry,
    )


def test_build_lineage_validation_runs_inside_database_transaction(tmp_path: Path) -> None:
    fixture = _Fixture(tmp_path)
    database = _TrackingDatabase()
    service = SnapshotGateService(
        database,
        runtime_root=tmp_path,
        canonical_repository=fixture.canonical,
        raw_repository=fixture.raw,
        provider_registry=fixture.registry,
    )
    observed_transaction_state: list[bool] = []
    original = service._validate_build_lineage

    def probe(session, **kwargs):
        observed_transaction_state.append(database.transaction_active)
        return original(session, **kwargs)

    service._validate_build_lineage = probe
    service.validate_gate(fixture.requirements, partition_rows=fixture.rows)

    assert observed_transaction_state == [True]


def test_backtest_gate_rejects_unregistered_policy_anchor(tmp_path: Path) -> None:
    fixture = _Fixture(tmp_path)
    fixture.registry.policies.pop("bar_1d_raw_v1")

    with pytest.raises(SnapshotGateError) as captured:
        _service(fixture, tmp_path).validate_gate(fixture.requirements, partition_rows=fixture.rows)

    assert captured.value.error_code == "SNAPSHOT_POLICY_NOT_REGISTERED"


def test_backtest_gate_rejects_raw_provider_lineage_mismatch(tmp_path: Path) -> None:
    fixture = _Fixture(tmp_path)
    raw = next(iter(fixture.raw.raws.values()))
    raw.request_fingerprint = compute_bytes_hash(b"different-request")

    with pytest.raises(SnapshotGateError) as captured:
        _service(fixture, tmp_path).validate_gate(fixture.requirements, partition_rows=fixture.rows)

    assert captured.value.error_code == "SNAPSHOT_RAW_LINEAGE_MISMATCH"


def test_backtest_gate_rejects_provider_raw_schema_drift(tmp_path: Path) -> None:
    fixture = _Fixture(tmp_path)
    raw = next(iter(fixture.raw.raws.values()))
    raw.observed_schema_hash = compute_bytes_hash(b"drifted-schema")

    with pytest.raises(SnapshotGateError) as captured:
        _service(fixture, tmp_path).validate_gate(fixture.requirements, partition_rows=fixture.rows)

    assert captured.value.error_code == "SNAPSHOT_RAW_SCHEMA_MISMATCH"


def test_backtest_gate_accepts_declared_supplemental_provider(tmp_path: Path) -> None:
    fixture = _Fixture(tmp_path)
    run = next(iter(fixture.raw.runs.values()))
    raw = fixture.raw.raws[run.raw_object_refs[0]]
    run.provider_id = "financial_api"
    run.actual_upstream = "Financial-API"
    raw.provider_id = "financial_api"
    raw.actual_upstream = "Financial-API"
    fixture.registry.raw_schemas[("financial_api", "1.0.0", run.dataset_id, "1.0.0", "1.0.0")] = fixture.registry.raw_schemas.pop(("a_stock_data", "1.0.0", run.dataset_id, "1.0.0", "1.0.0"))
    mapping = fixture.canonical.mappings.pop(("a_stock_data", run.dataset_id, "1.0.0", "1.0.0"))
    fixture.canonical.mappings[("financial_api", run.dataset_id, "1.0.0", "1.0.0")] = mapping

    evidence = _service(fixture, tmp_path).validate_gate(fixture.requirements, partition_rows=fixture.rows)

    assert len(evidence.partition_refs) == len(DATASETS)
