from __future__ import annotations

import json
import os
from decimal import Decimal
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from src.artifacts.hashing import compute_bytes_hash
from src.artifacts.namespace import StorageNamespaceResolver, fsync_directory
from src.repositories.platform.canonical import CanonicalRepository
from src.repositories.platform.provider import ProviderRegistryRepository
from src.repositories.platform.raw_ingestion import RawIngestionRepository
from src.repositories.platform.snapshot import SnapshotRepository
from src.schemas.platform import (
    BenchmarkIndexBar,
    CapabilityCertification,
    ConsumerKind,
    ConsumerRequirement,
    ConsumerRequirementStatus,
    DataSnapshot,
    ProviderCapabilityStatus,
    ProviderMergeMode,
    ProviderRunOutcome,
    QualityStatus,
    QuarantineStatus,
    ResourceType,
    RevisionKind,
    SnapshotBuildTaskRequirements,
    SnapshotBuildTaskResult,
    SnapshotCapabilityStatus,
    SnapshotCurrentPointer,
    SnapshotPartitionRef,
    SnapshotPublicationStatus,
    TaskLease,
    compute_content_hash,
    compute_snapshot_manifest_hash,
    generate_resource_id,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SnapshotGateError(Exception):
    def __init__(self, error_code: str, public_message: str, *, details: Mapping[str, Any] | None = None):
        super().__init__(public_message)
        self.error_code = error_code
        self.public_message = public_message
        self.details = dict(details or {})


@dataclass(frozen=True, slots=True)
class SnapshotGateEvidence:
    partition_refs: tuple[SnapshotPartitionRef, ...]
    quality_report_refs: tuple[str, ...]
    certified_capabilities: tuple[str, ...]
    missing_capabilities: tuple[str, ...]


class SnapshotManifestPublisher:
    """Writes deterministic snapshot manifests beneath the observations namespace."""

    def __init__(self, runtime_root: Path | str) -> None:
        self.resolver = StorageNamespaceResolver(runtime_root)

    def relative_manifest_path(self, snapshot: DataSnapshot) -> str:
        return f"observations/domain=data_snapshot/trade_date={snapshot.trade_date.isoformat()}/snapshot_id={snapshot.snapshot_id}/manifest.json"

    def publish(self, snapshot: DataSnapshot) -> str:
        relative = self.relative_manifest_path(snapshot)
        target = self.resolver.resolve(relative)
        if target.exists() or target.parent.exists():
            raise SnapshotGateError("SNAPSHOT_TARGET_EXISTS", "Snapshot manifest target already exists.")
        staging_root = self.resolver.resolve(".staging", allow_internal=True)
        staging_root.mkdir(parents=True, exist_ok=True)
        staging = staging_root / f"{snapshot.snapshot_id}-snapshot"
        staging.mkdir()
        manifest = staging / "manifest.json"
        payload = snapshot.model_dump(mode="json")
        manifest.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8", newline="\n")
        with manifest.open("r+b") as handle:
            handle.flush()
            os.fsync(handle.fileno())
        fsync_directory(staging)
        target.parent.parent.mkdir(parents=True, exist_ok=True)
        os.rename(staging, target.parent)
        fsync_directory(target.parent.parent)
        return relative

    def read_and_validate(self, snapshot: DataSnapshot) -> None:
        path = self.resolver.resolve(self.relative_manifest_path(snapshot), require_exists=True)
        try:
            value = json.loads(path.read_bytes())
            loaded = DataSnapshot.model_validate(value)
        except Exception as exc:
            raise SnapshotGateError("SNAPSHOT_MANIFEST_INVALID", "Snapshot manifest is invalid.") from exc
        if loaded != snapshot or compute_snapshot_manifest_hash(loaded) != snapshot.manifest_hash:
            raise SnapshotGateError("SNAPSHOT_MANIFEST_HASH_MISMATCH", "Snapshot manifest integrity validation failed.")


def _row_value(row: Mapping[str, Any] | Any, key: str) -> Any:
    if isinstance(row, Mapping):
        return row.get(key)
    return getattr(row, key, None)


def _coerce_row_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    return None


def _coerce_row_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            return None
        return value
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None
        return parsed
    return None


def _validate_cross_partition_rows(
    rows_by_dataset: Mapping[str, list[Mapping[str, Any]]],
    cutoff_at: datetime,
    *,
    trade_date: date | None = None,
    required_dataset_ids: frozenset[str] = frozenset(),
) -> None:
    """Validate cross-partition evidence required by a capability.

    Rows are supplied by the snapshot builder and are intentionally validated
    independently from the snapshot's claimed capability projection. This
    keeps the benchmark index contract separate from stock bars and makes PIT
    and calendar evidence auditable at certification time.
    """

    present = set(rows_by_dataset)
    missing = sorted(required_dataset_ids - present)
    empty = sorted(dataset_id for dataset_id in required_dataset_ids if not rows_by_dataset.get(dataset_id))
    if missing or empty:
        raise SnapshotGateError(
            "SNAPSHOT_CROSS_PARTITION_EVIDENCE_REQUIRED",
            "Backtest snapshot requires complete cross-partition evidence.",
            details={"missing_datasets": missing, "empty_datasets": empty},
        )

    for dataset_id, rows in rows_by_dataset.items():
        for row in rows:
            available_raw = _row_value(row, "available_at")
            if available_raw is None:
                if dataset_id in required_dataset_ids:
                    raise SnapshotGateError(
                        "SNAPSHOT_PIT_UNVERIFIED",
                        "Backtest partition availability evidence is incomplete.",
                        details={"dataset_id": dataset_id},
                    )
                continue
            available_at = _coerce_row_datetime(available_raw)
            if available_at is None:
                raise SnapshotGateError(
                    "SNAPSHOT_PIT_UNVERIFIED",
                    "Partition availability evidence must include a timezone-aware instant.",
                    details={"dataset_id": dataset_id},
                )
            if available_at > cutoff_at:
                raise SnapshotGateError(
                    "SNAPSHOT_PIT_VIOLATION",
                    "A partition row is not available by the snapshot cutoff.",
                    details={"dataset_id": dataset_id},
                )

    if "benchmark_index_1d" in required_dataset_ids:
        benchmark_ids: set[str] = set()
        return_types: set[str] = set()
        benchmark_fields = (
            "benchmark_id",
            "asset_type",
            "trade_date",
            "open",
            "high",
            "low",
            "close",
            "return_type",
            "total_return_close",
            "available_at",
        )
        for row_index, row in enumerate(rows_by_dataset["benchmark_index_1d"]):
            payload = {field: _row_value(row, field) for field in benchmark_fields}
            try:
                benchmark = BenchmarkIndexBar.model_validate(payload)
            except Exception as exc:
                raise SnapshotGateError(
                    "SNAPSHOT_BENCHMARK_CONTRACT_INVALID",
                    "Benchmark index evidence does not satisfy the independent benchmark contract.",
                    details={"row_index": row_index},
                ) from exc
            benchmark_ids.add(benchmark.benchmark_id)
            return_types.add(benchmark.return_type)
        if len(benchmark_ids) != 1 or len(return_types) != 1:
            raise SnapshotGateError(
                "SNAPSHOT_BENCHMARK_CONTRACT_CONFLICT",
                "Backtest benchmark evidence must use one benchmark id and one return mode per snapshot.",
                details={"benchmark_ids": sorted(benchmark_ids), "return_types": sorted(return_types)},
            )

    def date_set(dataset_id: str) -> set[date]:
        values: set[date] = set()
        for row in rows_by_dataset.get(dataset_id, []):
            raw = _row_value(row, "trade_date")
            if raw is None:
                raw = _row_value(row, "calendar_date")
            if raw is None:
                raw = _row_value(row, "date")
            parsed = _coerce_row_date(raw)
            if parsed is None:
                raise SnapshotGateError(
                    "SNAPSHOT_DATE_RANGE_UNVERIFIED",
                    "Backtest date-range evidence is incomplete.",
                    details={"dataset_id": dataset_id},
                )
            values.add(parsed)
        return values

    def open_calendar_dates() -> set[date]:
        values: set[date] = set()
        states: dict[date, bool] = {}
        for row in rows_by_dataset.get("trading_calendar", []):
            raw = _row_value(row, "trade_date")
            if raw is None:
                raw = _row_value(row, "calendar_date")
            parsed = _coerce_row_date(raw)
            is_open = _row_value(row, "is_open")
            if parsed is None or not isinstance(is_open, bool):
                raise SnapshotGateError(
                    "SNAPSHOT_CALENDAR_CONTRACT_INVALID",
                    "Trading calendar evidence must include a date and boolean is_open value.",
                )
            prior = states.get(parsed)
            if prior is not None and prior != is_open:
                raise SnapshotGateError(
                    "SNAPSHOT_DATE_RANGE_CONFLICT",
                    "Trading calendar contains conflicting open states for one date.",
                )
            states[parsed] = is_open
            if is_open:
                values.add(parsed)
        return values

    bar_dates = date_set("bar_1d_raw") if "bar_1d_raw" in required_dataset_ids else set()
    benchmark_dates = date_set("benchmark_index_1d") if "benchmark_index_1d" in required_dataset_ids else set()
    calendar_dates = open_calendar_dates() if "trading_calendar" in required_dataset_ids else set()
    date_sets = [dates for dates in (bar_dates, benchmark_dates, calendar_dates) if dates]
    if required_dataset_ids.intersection({"bar_1d_raw", "benchmark_index_1d", "trading_calendar"}):
        if len(date_sets) != 3 or any(not dates for dates in (bar_dates, benchmark_dates, calendar_dates)):
            raise SnapshotGateError(
                "SNAPSHOT_DATE_RANGE_UNVERIFIED",
                "Backtest bar, benchmark, and calendar date ranges cannot be verified.",
            )
        if not (bar_dates == benchmark_dates == calendar_dates):
            raise SnapshotGateError(
                "SNAPSHOT_DATE_RANGE_CONFLICT",
                "Backtest bar, benchmark, and open calendar date ranges do not match.",
            )
        if trade_date is not None and max(bar_dates) != trade_date:
            raise SnapshotGateError(
                "SNAPSHOT_DATE_RANGE_CONFLICT",
                "Backtest partition date range does not end at the snapshot trade date.",
            )

    listing = rows_by_dataset.get("listing_status_history", [])
    by_entity: dict[str, list[tuple[date, date | None]]] = {}
    for row in listing:
        effective_from = _coerce_row_date(_row_value(row, "effective_from"))
        effective_to = _coerce_row_date(_row_value(row, "effective_to"))
        if effective_from is None:
            raise SnapshotGateError(
                "SNAPSHOT_LISTING_INTERVAL_UNVERIFIED",
                "Listing validity interval evidence is incomplete.",
            )
        by_entity.setdefault(str(_row_value(row, "entity_key")), []).append((effective_from, effective_to))
    for intervals in by_entity.values():
        ordered = sorted(intervals, key=lambda item: item[0])
        for first, second in zip(ordered, ordered[1:]):
            if first[1] is None or second[0] < first[1]:
                raise SnapshotGateError("SNAPSHOT_LISTING_INTERVAL_CONFLICT", "Listing validity intervals overlap.")

    for dataset_id in ("corporate_action", "financial_statement", "bar_1d_raw", "benchmark_index_1d"):
        seen: set[tuple[Any, ...]] = set()
        for row in rows_by_dataset.get(dataset_id, []):
            revision = _row_value(row, "revision")
            if revision is None:
                continue
            key = tuple(
                _row_value(row, field)
                for field in (
                    "entity_key",
                    "benchmark_id",
                    "corporate_action_id",
                    "report_period",
                    "statement_type",
                    "line_item",
                    "trade_date",
                )
            )
            identity = (key, revision)
            if identity in seen:
                raise SnapshotGateError("SNAPSHOT_REVISION_CONFLICT", "Revision rows overlap in a snapshot.")
            seen.add(identity)


class SnapshotCapabilityEngine:
    BASE_CAPABILITIES = ("identity_core", "calendar_core", "financial_research")
    BACKTEST_REQUIRED_DATASETS = frozenset({"security_master", "trading_calendar", "bar_1d_raw", "benchmark_index_1d"})
    FRESHNESS_WINDOW = timedelta(days=7)
    MIN_BACKTEST_COVERAGE = Decimal("0.998")
    MAX_BACKTEST_EXCLUDED_INSTRUMENTS = 10
    MAX_BACKTEST_EXCLUSION_RATIO = Decimal("0.002")
    QUALITY_THRESHOLD_VERSION = "1.0.0"

    @classmethod
    def _certification(
        cls,
        snapshot: DataSnapshot,
        capability_id: str,
        status: SnapshotCapabilityStatus,
        *,
        now: datetime,
        reason_code: str | None = None,
    ) -> CapabilityCertification:
        return CapabilityCertification(
            capability_id=capability_id,
            capability_status=status,
            reason_code=reason_code,
            evidence_refs=snapshot.quality_report_refs,
            certified_at=now if status is SnapshotCapabilityStatus.CERTIFIED else None,
            snapshot_id=snapshot.snapshot_id,
        )

    @classmethod
    def certify(
        cls,
        snapshot: DataSnapshot,
        *,
        now: datetime | None = None,
        partition_rows: Mapping[str, list[Mapping[str, Any]]] | None = None,
    ) -> tuple[CapabilityCertification, ...]:
        instant = now or _utc_now()
        refs_by_dataset: dict[str, list[SnapshotPartitionRef]] = {}
        for ref in snapshot.canonical_partitions:
            refs_by_dataset.setdefault(ref.dataset_id, []).append(ref)

        def certify_datasets(capability_id: str, required: frozenset[str]) -> CapabilityCertification:
            missing = required - refs_by_dataset.keys()
            if missing:
                return cls._certification(snapshot, capability_id, SnapshotCapabilityStatus.UNAVAILABLE, now=instant, reason_code="CAPABILITY_DATASET_MISSING")
            refs = [ref for dataset_id in required for ref in refs_by_dataset[dataset_id]]
            if any(ref.quality_status is QualityStatus.FAILED for ref in refs):
                return cls._certification(snapshot, capability_id, SnapshotCapabilityStatus.UNAVAILABLE, now=instant, reason_code="QUALITY_GATE_FAILED")
            if any(ref.quality_status is QualityStatus.UNAVAILABLE for ref in refs):
                return cls._certification(snapshot, capability_id, SnapshotCapabilityStatus.UNAVAILABLE, now=instant, reason_code="CAPABILITY_DATASET_UNAVAILABLE")
            if any(ref.quality_status is QualityStatus.STALE for ref in refs):
                return cls._certification(snapshot, capability_id, SnapshotCapabilityStatus.STALE, now=instant, reason_code="DATASET_STALE")
            if any(ref.quality_status is QualityStatus.PARTIAL for ref in refs):
                return cls._certification(snapshot, capability_id, SnapshotCapabilityStatus.PARTIAL, now=instant, reason_code="DATASET_QUALITY_INCOMPLETE")
            if any(ref.row_count == 0 for ref in refs):
                return cls._certification(snapshot, capability_id, SnapshotCapabilityStatus.PARTIAL, now=instant, reason_code="COVERAGE_INSUFFICIENT")
            if any(ref.min_available_at > snapshot.cutoff_at for ref in refs):
                return cls._certification(snapshot, capability_id, SnapshotCapabilityStatus.UNAVAILABLE, now=instant, reason_code="PIT_VIOLATION")
            if snapshot.publication_status is SnapshotPublicationStatus.REJECTED:
                return cls._certification(snapshot, capability_id, SnapshotCapabilityStatus.UNAVAILABLE, now=instant, reason_code="SNAPSHOT_REJECTED")
            if snapshot.publication_status is SnapshotPublicationStatus.PROVISIONAL:
                return cls._certification(snapshot, capability_id, SnapshotCapabilityStatus.PROVISIONAL, now=instant, reason_code="SNAPSHOT_PROVISIONAL")
            if snapshot.available_at < instant - cls.FRESHNESS_WINDOW:
                return cls._certification(snapshot, capability_id, SnapshotCapabilityStatus.STALE, now=instant, reason_code="SNAPSHOT_STALE")
            return cls._certification(snapshot, capability_id, SnapshotCapabilityStatus.CERTIFIED, now=instant)

        result: list[CapabilityCertification] = []
        for capability_id, required in {
            "identity_core": frozenset({"security_master"}),
            "calendar_core": frozenset({"trading_calendar"}),
            "financial_research": frozenset({"financial_statement"}),
        }.items():
            result.append(certify_datasets(capability_id, required))

        required = cls.BACKTEST_REQUIRED_DATASETS
        missing = required - refs_by_dataset.keys()
        required_refs = [ref for dataset_id in required if dataset_id in refs_by_dataset for ref in refs_by_dataset[dataset_id]]
        coverage_insufficient = any(
            ref.quality_threshold_version != cls.QUALITY_THRESHOLD_VERSION
            or ref.coverage_ratio < cls.MIN_BACKTEST_COVERAGE
            or ref.excluded_instrument_count > cls.MAX_BACKTEST_EXCLUDED_INSTRUMENTS
            or (
                ref.row_count + ref.excluded_instrument_count > 0
                and Decimal(ref.excluded_instrument_count) / Decimal(ref.row_count + ref.excluded_instrument_count) > cls.MAX_BACKTEST_EXCLUSION_RATIO
            )
            for ref in required_refs
        )
        if missing:
            result.append(
                cls._certification(
                    snapshot,
                    "backtest_core",
                    SnapshotCapabilityStatus.UNAVAILABLE,
                    now=instant,
                    reason_code="BENCHMARK_DATASET_MISSING" if "benchmark_index_1d" in missing else "CAPABILITY_DATASET_MISSING",
                )
            )
            return tuple(result)
        if coverage_insufficient or any(ref.row_count == 0 for ref in required_refs):
            result.append(cls._certification(snapshot, "backtest_core", SnapshotCapabilityStatus.PARTIAL, now=instant, reason_code="COVERAGE_INSUFFICIENT"))
            return tuple(result)

        backtest = certify_datasets("backtest_core", required)
        if backtest.capability_status is not SnapshotCapabilityStatus.CERTIFIED:
            result.append(backtest)
            return tuple(result)
        if partition_rows is None:
            result.append(
                cls._certification(
                    snapshot,
                    "backtest_core",
                    SnapshotCapabilityStatus.UNAVAILABLE,
                    now=instant,
                    reason_code="SNAPSHOT_CROSS_PARTITION_EVIDENCE_REQUIRED",
                )
            )
            return tuple(result)
        try:
            _validate_cross_partition_rows(
                partition_rows,
                snapshot.cutoff_at,
                trade_date=snapshot.trade_date,
                required_dataset_ids=required,
            )
        except SnapshotGateError as exc:
            result.append(
                cls._certification(
                    snapshot,
                    "backtest_core",
                    SnapshotCapabilityStatus.UNAVAILABLE,
                    now=instant,
                    reason_code=exc.error_code,
                )
            )
            return tuple(result)
        result.append(backtest)
        return tuple(result)


class SnapshotGateService:
    _QUALITY_RANK = {
        QualityStatus.FAILED: 0,
        QualityStatus.UNAVAILABLE: 0,
        QualityStatus.PARTIAL: 1,
        QualityStatus.STALE: 1,
        QualityStatus.COMPLETE: 2,
    }

    def __init__(
        self,
        database,
        *,
        runtime_root: Path | str = ".",
        repository: SnapshotRepository | None = None,
        canonical_repository: CanonicalRepository | None = None,
        raw_repository: RawIngestionRepository | None = None,
        provider_registry: ProviderRegistryRepository | None = None,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self.database = database
        self.repository = repository or SnapshotRepository()
        self.canonical_repository = canonical_repository or CanonicalRepository()
        self.raw_repository = raw_repository or RawIngestionRepository()
        self.provider_registry = provider_registry or ProviderRegistryRepository()
        self.clock = clock
        self.manifest_publisher = SnapshotManifestPublisher(runtime_root)

    def _validate_file_and_manifest(self, ref: SnapshotPartitionRef) -> None:
        try:
            path = self.manifest_publisher.resolver.resolve(ref.storage_ref, require_exists=True)
            content = path.read_bytes()
        except Exception as exc:
            raise SnapshotGateError("SNAPSHOT_PARTITION_FILE_MISSING", "Canonical partition file is unavailable.") from exc
        if len(content) != ref.storage_ref.size_bytes or compute_bytes_hash(content) != ref.partition_hash:
            raise SnapshotGateError("SNAPSHOT_PARTITION_INTEGRITY_FAILED", "Canonical partition integrity validation failed.")
        manifest_path = path.parent / "manifest.json"
        try:
            self.manifest_publisher.resolver.resolve(manifest_path.relative_to(self.manifest_publisher.resolver.namespace_root()).as_posix(), require_exists=True)
            manifest = json.loads(manifest_path.read_bytes())
            manifest_partition = manifest.get("partition", {})
            expected_partition_evidence = {
                "canonical_partition_id": ref.canonical_partition_id,
                "dataset_id": ref.dataset_id,
                "dataset_schema_version": ref.dataset_schema_version,
                "partition_hash": ref.partition_hash,
                "schema_hash": ref.schema_hash,
                "quality_report_id": ref.quality_report_id,
                "quality_status": ref.quality_status.value,
                "row_count": ref.row_count,
            }
            if any(manifest_partition.get(key) != value for key, value in expected_partition_evidence.items()):
                raise ValueError("partition manifest evidence mismatch")
            manifest_hash = manifest.get("manifest_hash")
            body = dict(manifest)
            body.pop("manifest_hash", None)
            if manifest_hash != compute_bytes_hash(json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")):
                raise ValueError("partition manifest hash mismatch")
        except SnapshotGateError:
            raise
        except Exception as exc:
            raise SnapshotGateError("SNAPSHOT_PARTITION_MANIFEST_INVALID", "Canonical partition manifest is invalid.") from exc

    def _validate_persisted_snapshot_files(self, snapshot: DataSnapshot) -> None:
        """Re-check immutable file evidence before a formal read or pointer update."""
        self.manifest_publisher.read_and_validate(snapshot)
        for ref in snapshot.canonical_partitions:
            self._validate_file_and_manifest(ref)

    @staticmethod
    def _policy_is_effective(policy: Any, cutoff_at: datetime) -> bool:
        return policy.effective_from <= cutoff_at and (
            policy.effective_to is None or cutoff_at < policy.effective_to
        )

    def _validate_policy_anchor(
        self,
        session: Any,
        *,
        provider_policy_id: str,
        provider_policy_version: str,
        cutoff_at: datetime,
        partition_refs: tuple[SnapshotPartitionRef, ...],
    ) -> Any:
        policy = self.provider_registry.get_policy(session, provider_policy_id)
        if policy is None:
            raise SnapshotGateError(
                "SNAPSHOT_POLICY_NOT_REGISTERED",
                "Snapshot ProviderPolicy anchor is not registered.",
                details={"provider_policy_id": provider_policy_id},
            )
        bound_partition = any(
            ref.dataset_id == policy.dataset_id
            and ref.dataset_schema_version == policy.dataset_schema_version
            for ref in partition_refs
        )
        if (
            policy.policy_version != provider_policy_version
            or not self._policy_is_effective(policy, cutoff_at)
            or not bound_partition
        ):
            raise SnapshotGateError(
                "SNAPSHOT_POLICY_BINDING_INVALID",
                "Snapshot ProviderPolicy anchor does not match its version, dataset, schema, or effective interval.",
                details={"provider_policy_id": provider_policy_id},
            )
        return policy

    def _validate_partition_lineage(
        self,
        session: Any,
        *,
        partition: Any,
        report: Any,
        cutoff_at: datetime,
        trade_date: date,
        snapshot_policy_version: str,
    ) -> None:
        dataset = self.provider_registry.get_dataset(
            session, partition.dataset_id, partition.dataset_schema_version
        )
        if dataset is None:
            raise SnapshotGateError(
                "SNAPSHOT_POLICY_BINDING_INVALID",
                "Canonical partition dataset contract is not registered.",
                details={"dataset_id": partition.dataset_id},
            )

        if (
            report.canonical_partition_id != partition.canonical_partition_id
            or report.dataset_id != partition.dataset_id
            or report.dataset_schema_version != partition.dataset_schema_version
            or tuple(report.provider_run_refs) != tuple(partition.provider_run_refs)
            or tuple(report.raw_object_refs) != tuple(partition.raw_object_refs)
        ):
            raise SnapshotGateError(
                "SNAPSHOT_QUALITY_LINEAGE_MISMATCH",
                "Canonical QualityReport lineage does not match its partition.",
                details={"canonical_partition_id": partition.canonical_partition_id},
            )
        if (
            report.quality_status is not QualityStatus.COMPLETE
            or report.failure_reasons
            or report.rejected_row_count
            or report.duplicate_key_count
            or report.identity_unresolved_count
            or report.identity_ambiguous_count
        ):
            raise SnapshotGateError(
                "SNAPSHOT_QUALITY_FAILED",
                "Backtest lineage requires a complete Canonical QualityReport.",
                details={"quality_report_id": report.quality_report_id},
            )
        if report.mapping_version is None or report.mapping_hash is None:
            raise SnapshotGateError(
                "SNAPSHOT_QUALITY_LINEAGE_MISMATCH",
                "Backtest QualityReport must bind a canonical mapping version and hash.",
                details={"quality_report_id": report.quality_report_id},
            )

        runs_by_id: dict[str, Any] = {}
        policies_by_id: dict[str, Any] = {}
        used_provider_ids: set[str] = set()
        for run_id in partition.provider_run_refs:
            run = self.raw_repository.get_provider_run(session, run_id)
            if run is None:
                raise SnapshotGateError(
                    "SNAPSHOT_PROVIDER_RUN_MISSING",
                    "ProviderRun lineage is unavailable.",
                    details={"provider_run_id": run_id},
                )
            runs_by_id[run_id] = run
            if (
                run.run_outcome is not ProviderRunOutcome.SUCCEEDED
                or run.finished_at is None
                or run.finished_at > cutoff_at
                or getattr(run, "started_at", cutoff_at) > cutoff_at
                or run.dataset_id != partition.dataset_id
                or run.dataset_schema_version != partition.dataset_schema_version
                or run.provider_policy_version != partition.provider_policy_version
                or run.provider_policy_version != snapshot_policy_version
                or run.capability_frequency != dataset.frequency
            ):
                raise SnapshotGateError(
                    "SNAPSHOT_PROVIDER_LINEAGE_MISMATCH",
                    "ProviderRun does not match the canonical partition contract.",
                    details={"provider_run_id": run_id},
                )

            provider = self.provider_registry.get_provider(session, run.provider_id)
            if (
                provider is None
                or not provider.enabled
                or provider.adapter_version != run.adapter_version
            ):
                raise SnapshotGateError(
                    "SNAPSHOT_PROVIDER_LINEAGE_MISMATCH",
                    "ProviderRun references an unavailable or incompatible Provider.",
                    details={"provider_run_id": run_id, "provider_id": run.provider_id},
                )

            policy = self.provider_registry.get_policy(session, run.provider_policy_id)
            if policy is None:
                raise SnapshotGateError(
                    "SNAPSHOT_POLICY_NOT_REGISTERED",
                    "ProviderRun policy is not registered.",
                    details={"provider_policy_id": run.provider_policy_id},
                )
            policies_by_id[run.provider_policy_id] = policy
            allowed_providers = {policy.primary_provider_id, *policy.supplemental_provider_ids}
            if (
                policy.dataset_id != partition.dataset_id
                or policy.dataset_schema_version != partition.dataset_schema_version
                or policy.policy_version != partition.provider_policy_version
                or not self._policy_is_effective(policy, cutoff_at)
                or run.provider_id not in allowed_providers
            ):
                raise SnapshotGateError(
                    "SNAPSHOT_POLICY_BINDING_INVALID",
                    "ProviderRun does not satisfy its registered ProviderPolicy.",
                    details={"provider_run_id": run_id, "provider_policy_id": run.provider_policy_id},
                )

            capability = self.provider_registry.get_capability(
                session,
                run.provider_id,
                run.dataset_id,
                run.dataset_schema_version,
                run.capability_market,
                run.capability_frequency,
            )
            history_start = getattr(capability, "history_start", None) if capability is not None else None
            if (
                capability is None
                or capability.provider_capability_status is not ProviderCapabilityStatus.AVAILABLE
                or (history_start is not None and trade_date < history_start.date())
            ):
                raise SnapshotGateError(
                    "SNAPSHOT_PROVIDER_LINEAGE_MISMATCH",
                    "Provider capability is not available for the certified partition.",
                    details={"provider_run_id": run_id, "provider_id": run.provider_id},
                )

            required_rules = tuple(getattr(policy, "required_quality_rules", ()))
            if any(report.rule_results.get(rule_id) != "PASS" for rule_id in required_rules):
                raise SnapshotGateError(
                    "SNAPSHOT_QUALITY_FAILED",
                    "Canonical QualityReport does not pass all policy-required quality rules.",
                    details={"quality_report_id": report.quality_report_id},
                )
            used_provider_ids.add(run.provider_id)

        if not runs_by_id or len(runs_by_id) != len(partition.provider_run_refs):
            raise SnapshotGateError(
                "SNAPSHOT_PROVIDER_LINEAGE_MISMATCH",
                "Canonical partition ProviderRun lineage is incomplete or duplicated.",
            )
        if any(
            policy.allowed_merge_mode is ProviderMergeMode.REPLACE_PARTITION
            for policy in policies_by_id.values()
        ) and len(runs_by_id) != 1:
            raise SnapshotGateError(
                "SNAPSHOT_PROVIDER_LINEAGE_MISMATCH",
                "REPLACE_PARTITION cannot silently combine multiple ProviderRuns.",
                details={"canonical_partition_id": partition.canonical_partition_id},
            )

        raws_by_id: dict[str, Any] = {}
        for raw_id in partition.raw_object_refs:
            raw = self.raw_repository.get_raw_object(session, raw_id)
            if raw is None:
                raise SnapshotGateError(
                    "SNAPSHOT_RAW_OBJECT_MISSING",
                    "RawObject lineage is unavailable.",
                    details={"raw_object_id": raw_id},
                )
            raws_by_id[raw_id] = raw
            run = runs_by_id.get(raw.provider_run_id)
            if (
                run is None
                or raw.raw_object_id not in tuple(run.raw_object_refs)
                or raw.provider_id != run.provider_id
                or raw.actual_upstream != run.actual_upstream
                or raw.dataset_id != run.dataset_id
                or raw.dataset_schema_version != run.dataset_schema_version
                or raw.request_fingerprint != run.request_fingerprint
                or raw.row_count != run.row_count
                or raw.byte_count != run.byte_count
                or raw.ingested_at > cutoff_at
                or raw.observed_at > cutoff_at
                or (
                    getattr(raw, "source_published_at", None) is not None
                    and raw.source_published_at > cutoff_at
                )
            ):
                raise SnapshotGateError(
                    "SNAPSHOT_RAW_LINEAGE_MISMATCH",
                    "RawObject does not match its ProviderRun or snapshot PIT boundary.",
                    details={"raw_object_id": raw_id},
                )

            raw_schema = self.provider_registry.get_provider_raw_schema(
                session,
                raw.provider_id,
                run.adapter_version,
                raw.dataset_id,
                raw.dataset_schema_version,
                raw.provider_schema_version,
            )
            if (
                raw_schema is None
                or raw.observed_schema_hash != raw_schema.expected_schema_hash
                or run.observed_schema_hash != raw_schema.expected_schema_hash
            ):
                raise SnapshotGateError(
                    "SNAPSHOT_RAW_SCHEMA_MISMATCH",
                    "RawObject observed schema does not match the registered provider schema.",
                    details={"raw_object_id": raw_id},
                )

        expected_raw_ids = {
            raw_id
            for run in runs_by_id.values()
            for raw_id in tuple(run.raw_object_refs)
        }
        if (
            set(raws_by_id) != expected_raw_ids
            or len(raws_by_id) != len(partition.raw_object_refs)
        ):
            raise SnapshotGateError(
                "SNAPSHOT_RAW_LINEAGE_MISMATCH",
                "Canonical partition RawObject lineage is incomplete or duplicated.",
                details={"canonical_partition_id": partition.canonical_partition_id},
            )

        for provider_id in used_provider_ids:
            mapping = self.canonical_repository.get_mapping(
                session,
                provider_id,
                partition.dataset_id,
                partition.dataset_schema_version,
                report.mapping_version,
            )
            if mapping is None or mapping.mapping_hash != report.mapping_hash:
                raise SnapshotGateError(
                    "SNAPSHOT_PROVIDER_LINEAGE_MISMATCH",
                    "Canonical mapping evidence is missing or does not match the QualityReport.",
                    details={"provider_id": provider_id, "dataset_id": partition.dataset_id},
                )

    def _validate_persisted_snapshot_lineage(
        self,
        session: Any,
        snapshot: DataSnapshot,
    ) -> None:
        self._validate_policy_anchor(
            session,
            provider_policy_id=snapshot.provider_policy_id,
            provider_policy_version=snapshot.provider_policy_version,
            cutoff_at=snapshot.cutoff_at,
            partition_refs=snapshot.canonical_partitions,
        )
        anchor_run_found = False
        for ref in snapshot.canonical_partitions:
            partition = self.canonical_repository.get_partition(
                session, ref.canonical_partition_id
            )
            if partition is None:
                raise SnapshotGateError(
                    "SNAPSHOT_PARTITION_NOT_REGISTERED",
                    "Persisted snapshot canonical partition is unavailable.",
                )
            report = self.canonical_repository.get_quality_report(
                session, partition.quality_report_id
            )
            if report is None:
                raise SnapshotGateError(
                    "SNAPSHOT_QUALITY_FAILED",
                    "Persisted snapshot QualityReport is unavailable.",
                )
            try:
                persisted_ref = SnapshotPartitionRef.from_partition(partition, report)
            except ValueError as exc:
                raise SnapshotGateError(
                    "SNAPSHOT_QUALITY_LINEAGE_MISMATCH",
                    "Persisted Canonical and QualityReport evidence is inconsistent.",
                ) from exc
            if persisted_ref != ref:
                raise SnapshotGateError(
                    "SNAPSHOT_CANONICAL_LINEAGE_MISMATCH",
                    "Snapshot partition reference does not match the registered Canonical partition.",
                    details={"canonical_partition_id": ref.canonical_partition_id},
                )
            self._validate_partition_lineage(
                session,
                partition=partition,
                report=report,
                cutoff_at=snapshot.cutoff_at,
                trade_date=snapshot.trade_date,
                snapshot_policy_version=snapshot.provider_policy_version,
            )
            for run_id in partition.provider_run_refs:
                run = self.raw_repository.get_provider_run(session, run_id)
                if run is not None and run.provider_policy_id == snapshot.provider_policy_id:
                    anchor_run_found = True
        if not anchor_run_found:
            raise SnapshotGateError(
                "SNAPSHOT_POLICY_BINDING_INVALID",
                "Snapshot ProviderPolicy anchor is not used by any canonical partition.",
                details={"provider_policy_id": snapshot.provider_policy_id},
            )

    def _validate_build_lineage(
        self,
        session: Any,
        *,
        requirements: SnapshotBuildTaskRequirements,
        partition_refs: tuple[SnapshotPartitionRef, ...],
        lineage_records: tuple[tuple[Any, Any], ...],
    ) -> None:
        """Validate registry-backed lineage before a backtest snapshot is built."""

        self._validate_policy_anchor(
            session,
            provider_policy_id=requirements.provider_policy_id,
            provider_policy_version=requirements.provider_policy_version,
            cutoff_at=requirements.cutoff_at,
            partition_refs=partition_refs,
        )
        anchor_run_found = False
        for partition, report in lineage_records:
            self._validate_partition_lineage(
                session,
                partition=partition,
                report=report,
                cutoff_at=requirements.cutoff_at,
                trade_date=requirements.trade_date,
                snapshot_policy_version=requirements.provider_policy_version,
            )
            for run_id in partition.provider_run_refs:
                run = self.raw_repository.get_provider_run(session, run_id)
                if run is not None and run.provider_policy_id == requirements.provider_policy_id:
                    anchor_run_found = True
        if not anchor_run_found:
            raise SnapshotGateError(
                "SNAPSHOT_POLICY_BINDING_INVALID",
                "Snapshot ProviderPolicy anchor is not used by any canonical partition.",
                details={"provider_policy_id": requirements.provider_policy_id},
            )

    def _load_persisted_snapshot_and_capabilities(
        self,
        session: Any,
        snapshot: DataSnapshot,
        *,
        for_update: bool = False,
    ) -> tuple[DataSnapshot, tuple[CapabilityCertification, ...]]:
        try:
            persisted = self.repository.get_snapshot(
                session,
                snapshot.snapshot_id,
                include_partitions=True,
                for_update=for_update,
            )
            certifications = self.repository.list_capabilities(session, snapshot.snapshot_id)
        except ValueError as exc:
            raise SnapshotGateError("SNAPSHOT_PERSISTED_STATE_INVALID", "Persisted snapshot evidence is invalid.") from exc
        if persisted is None:
            raise SnapshotGateError("SNAPSHOT_NOT_REGISTERED", "Snapshot is not registered for consumption.")
        if persisted != snapshot:
            raise SnapshotGateError("SNAPSHOT_PERSISTED_STATE_MISMATCH", "Snapshot does not match the registered immutable record.")
        if any(item.snapshot_id != persisted.snapshot_id for item in certifications):
            raise SnapshotGateError("SNAPSHOT_CAPABILITY_EVIDENCE_MISMATCH", "Capability evidence is bound to a different snapshot.")
        certified_projection = {
            item.capability_id
            for item in certifications
            if item.capability_status is SnapshotCapabilityStatus.CERTIFIED
        }
        if certified_projection != set(persisted.certified_capabilities):
            raise SnapshotGateError("SNAPSHOT_CAPABILITY_PROJECTION_MISMATCH", "Snapshot capability projection does not match registered certifications.")
        expected_evidence_refs = tuple(persisted.quality_report_refs)
        if any(tuple(item.evidence_refs) != expected_evidence_refs for item in certifications):
            raise SnapshotGateError("SNAPSHOT_CAPABILITY_EVIDENCE_MISMATCH", "Capability evidence references do not match the snapshot.")
        return persisted, tuple(certifications)

    @staticmethod
    def _require_certified_capability(
        snapshot: DataSnapshot,
        certifications: tuple[CapabilityCertification, ...],
        capability_id: str,
    ) -> CapabilityCertification:
        certification = next((item for item in certifications if item.capability_id == capability_id), None)
        if certification is None or certification.snapshot_id != snapshot.snapshot_id or certification.capability_status is not SnapshotCapabilityStatus.CERTIFIED:
            raise SnapshotGateError("SNAPSHOT_CAPABILITY_UNVERIFIED", "Required snapshot capability is not persistently certified.")
        return certification

    def _validate_backtest_structure(self, snapshot: DataSnapshot) -> None:
        refs_by_dataset: dict[str, list[SnapshotPartitionRef]] = {}
        for ref in snapshot.canonical_partitions:
            refs_by_dataset.setdefault(ref.dataset_id, []).append(ref)
        missing = SnapshotCapabilityEngine.BACKTEST_REQUIRED_DATASETS - refs_by_dataset.keys()
        refs_by_id = {ref.canonical_partition_id: ref for ref in snapshot.canonical_partitions}
        if (
            snapshot.security_master_ref not in refs_by_id
            or refs_by_id[snapshot.security_master_ref].dataset_id != "security_master"
            or snapshot.calendar_ref not in refs_by_id
            or refs_by_id[snapshot.calendar_ref].dataset_id != "trading_calendar"
        ):
            raise SnapshotGateError("SNAPSHOT_IDENTITY_CALENDAR_MISMATCH", "Backtest identity and calendar references are inconsistent.")
        if missing:
            raise SnapshotGateError(
                "SNAPSHOT_BACKTEST_CORE_UNAVAILABLE",
                "Formal Backtest requires all backtest core datasets.",
                details={"missing_datasets": sorted(missing)},
            )
        for ref in [item for dataset_id in SnapshotCapabilityEngine.BACKTEST_REQUIRED_DATASETS for item in refs_by_dataset[dataset_id]]:
            if ref.quality_status is not QualityStatus.COMPLETE or ref.row_count <= 0:
                raise SnapshotGateError("SNAPSHOT_BACKTEST_CORE_UNAVAILABLE", "Formal Backtest requires complete non-empty core partitions.")
            if ref.quality_threshold_version != SnapshotCapabilityEngine.QUALITY_THRESHOLD_VERSION:
                raise SnapshotGateError("SNAPSHOT_BACKTEST_CORE_UNAVAILABLE", "Backtest quality threshold version is not certified.")
            if ref.coverage_ratio < SnapshotCapabilityEngine.MIN_BACKTEST_COVERAGE or ref.excluded_instrument_count > SnapshotCapabilityEngine.MAX_BACKTEST_EXCLUDED_INSTRUMENTS:
                raise SnapshotGateError("SNAPSHOT_BACKTEST_CORE_UNAVAILABLE", "Backtest partition coverage is below the certified threshold.")
            if ref.min_available_at > snapshot.cutoff_at:
                raise SnapshotGateError("SNAPSHOT_PIT_VIOLATION", "Backtest partition is not available by the snapshot cutoff.")
        if snapshot.available_at < self.clock() - SnapshotCapabilityEngine.FRESHNESS_WINDOW:
            raise SnapshotGateError("SNAPSHOT_BACKTEST_CORE_UNAVAILABLE", "Backtest snapshot is stale.")

    def _verify_registered_consumer_requirement(self, session: Any, requirement: ConsumerRequirement) -> None:
        persisted = self.repository.get_consumer_requirement(session, requirement.consumer_id)
        if persisted is None:
            raise SnapshotGateError("SNAPSHOT_CONSUMER_REQUIREMENT_NOT_REGISTERED", "Consumer requirement is not registered.")
        if persisted != requirement:
            raise SnapshotGateError("SNAPSHOT_CONSUMER_REQUIREMENT_MISMATCH", "Consumer requirement does not match the registered version.")

    def validate_gate(
        self,
        requirements: SnapshotBuildTaskRequirements,
        *,
        partition_rows: Mapping[str, list[Mapping[str, Any]]] | None = None,
    ) -> SnapshotGateEvidence:
        refs: list[SnapshotPartitionRef] = []
        quality_refs: list[str] = []
        lineage_records: list[tuple[Any, Any]] = []
        backtest_requested = "backtest_core" in requirements.requested_capabilities
        if len(requirements.canonical_partition_ids) != len(set(requirements.canonical_partition_ids)):
            raise SnapshotGateError("SNAPSHOT_PARTITION_DUPLICATE", "Snapshot requirements contain duplicate canonical partitions.")
        with self.database.transaction() as session:
            for partition_id in requirements.canonical_partition_ids:
                partition = self.canonical_repository.get_partition(session, partition_id)
                report = self.canonical_repository.get_quality_report(session, partition.quality_report_id) if partition else None
                if partition is None:
                    raise SnapshotGateError("SNAPSHOT_PARTITION_NOT_REGISTERED", "Canonical partition is not registered.")
                if report is None:
                    raise SnapshotGateError("SNAPSHOT_QUALITY_FAILED", "Snapshot cannot reference missing Canonical quality.")
                try:
                    partition_ref = SnapshotPartitionRef.from_partition(partition, report)
                except ValueError as exc:
                    raise SnapshotGateError(
                        "SNAPSHOT_QUALITY_EVIDENCE_MISMATCH",
                        "Canonical quality evidence does not match the partition.",
                    ) from exc
                if report.quality_status is QualityStatus.FAILED or partition.quality_status is QualityStatus.FAILED:
                    raise SnapshotGateError("SNAPSHOT_QUALITY_FAILED", "Snapshot cannot reference failed Canonical quality.")
                failed_rules = {rule_id for rule_id, result in (report.rule_results or {}).items() if result == "FAIL"}
                if failed_rules:
                    if any("SCHEMA" in rule_id.upper() or "DRIFT" in rule_id.upper() for rule_id in failed_rules):
                        raise SnapshotGateError("SNAPSHOT_SCHEMA_DRIFT", "Snapshot cannot reference a partition with schema drift.")
                    raise SnapshotGateError("SNAPSHOT_QUALITY_FAILED", "Snapshot cannot reference a partition with failed quality rules.")
                if partition.min_available_at > requirements.cutoff_at:
                    raise SnapshotGateError("SNAPSHOT_PIT_VIOLATION", "Canonical partition is not available by the snapshot cutoff.")
                if not partition.provider_run_refs or not partition.raw_object_refs:
                    raise SnapshotGateError("SNAPSHOT_LINEAGE_INCOMPLETE", "Canonical partition lineage is incomplete.")
                for run_id in partition.provider_run_refs:
                    if self.raw_repository.get_provider_run(session, run_id) is None:
                        raise SnapshotGateError("SNAPSHOT_PROVIDER_RUN_MISSING", "ProviderRun lineage is unavailable.")
                    quarantine = self.raw_repository.get_quarantine_by_run(session, run_id)
                    if quarantine is not None and quarantine.quarantine_status is QuarantineStatus.OPEN:
                        raise SnapshotGateError("SNAPSHOT_QUARANTINE_OPEN", "Snapshot cannot reference an open ingestion quarantine.")
                for raw_id in partition.raw_object_refs:
                    if self.raw_repository.get_raw_object(session, raw_id) is None:
                        raise SnapshotGateError("SNAPSHOT_RAW_OBJECT_MISSING", "RawObject lineage is unavailable.")
                refs.append(partition_ref)
                quality_refs.append(partition.quality_report_id)
                if backtest_requested:
                    lineage_records.append((partition, report))
            if backtest_requested:
                self._validate_build_lineage(
                    session,
                    requirements=requirements,
                    partition_refs=tuple(refs),
                    lineage_records=tuple(lineage_records),
                )

        if not refs:
            raise SnapshotGateError("SNAPSHOT_PARTITION_MISSING", "Snapshot must contain at least one canonical partition.")
        if any(ref.provider_policy_version != requirements.provider_policy_version for ref in refs):
            raise SnapshotGateError("SNAPSHOT_POLICY_VERSION_CONFLICT", "Snapshot partitions do not match the requested ProviderPolicy version.")
        if len({ref.provider_policy_version for ref in refs}) != 1:
            raise SnapshotGateError("SNAPSHOT_POLICY_VERSION_CONFLICT", "Snapshot partitions use different ProviderPolicy versions.")

        seen_partition_keys: set[tuple[str, str]] = set()
        by_dataset: dict[str, str] = {}
        refs_by_id = {ref.canonical_partition_id: ref for ref in refs}
        for ref in refs:
            key = (ref.dataset_id, ref.partition_key)
            if key in seen_partition_keys:
                raise SnapshotGateError("SNAPSHOT_REVISION_CONFLICT", "Snapshot contains multiple revisions for one partition key.")
            seen_partition_keys.add(key)
            prior_schema = by_dataset.setdefault(ref.dataset_id, ref.dataset_schema_version)
            if prior_schema != ref.dataset_schema_version:
                raise SnapshotGateError("SNAPSHOT_SCHEMA_VERSION_CONFLICT", "Snapshot partitions use conflicting schema versions.")
            self._validate_file_and_manifest(ref)

        if requirements.security_master_ref not in refs_by_id or requirements.calendar_ref not in refs_by_id:
            raise SnapshotGateError("SNAPSHOT_IDENTITY_CALENDAR_MISSING", "Security Master and Calendar references must be included in the snapshot.")

        required_cross_partition = (
            SnapshotCapabilityEngine.BACKTEST_REQUIRED_DATASETS
            if "backtest_core" in requirements.requested_capabilities
            else frozenset()
        )
        if required_cross_partition:
            if refs_by_id[requirements.security_master_ref].dataset_id != "security_master":
                raise SnapshotGateError("SNAPSHOT_IDENTITY_CALENDAR_MISMATCH", "Security Master reference must point to the security_master dataset.")
            if refs_by_id[requirements.calendar_ref].dataset_id != "trading_calendar":
                raise SnapshotGateError("SNAPSHOT_IDENTITY_CALENDAR_MISMATCH", "Calendar reference must point to the trading_calendar dataset.")
        if required_cross_partition and partition_rows is None:
            raise SnapshotGateError(
                "SNAPSHOT_CROSS_PARTITION_EVIDENCE_REQUIRED",
                "Backtest snapshot requires complete cross-partition evidence.",
            )
        if partition_rows is not None:
            _validate_cross_partition_rows(
                partition_rows,
                requirements.cutoff_at,
                trade_date=requirements.trade_date,
                required_dataset_ids=required_cross_partition,
            )

        ordered_refs = tuple(sorted(refs, key=lambda item: (item.dataset_id, item.partition_key, item.revision, item.canonical_partition_id)))
        ordered_quality_refs = tuple(dict.fromkeys(ref.quality_report_id for ref in ordered_refs))
        # Capability engine will compute final statuses after DataSnapshot exists.
        return SnapshotGateEvidence(ordered_refs, ordered_quality_refs, tuple(), tuple())

    @staticmethod
    def aggregate_partition_quality(refs: tuple[SnapshotPartitionRef, ...]) -> QualityStatus:
        statuses = {ref.quality_status for ref in refs}
        if QualityStatus.FAILED in statuses:
            return QualityStatus.FAILED
        if QualityStatus.UNAVAILABLE in statuses:
            return QualityStatus.UNAVAILABLE
        if QualityStatus.PARTIAL in statuses:
            return QualityStatus.PARTIAL
        if QualityStatus.STALE in statuses:
            return QualityStatus.STALE
        return QualityStatus.COMPLETE

    def build_snapshot(self, requirements: SnapshotBuildTaskRequirements, *, task_id: str | None = None, attempt_id: str | None = None, partition_rows: Mapping[str, list[Mapping[str, Any]]] | None = None, session: Any | None = None) -> tuple[DataSnapshot, tuple[CapabilityCertification, ...]]:
        evidence = self.validate_gate(requirements, partition_rows=partition_rows)
        now = self.clock()
        snapshot_id = generate_resource_id(ResourceType.DATA_SNAPSHOT)
        revision_kind = RevisionKind.CORRECTION if requirements.correction_of_snapshot_id else RevisionKind.INITIAL
        if session is None:
            with self.database.transaction() as lookup_session:
                prior = self.repository.get_snapshot(lookup_session, requirements.correction_of_snapshot_id) if requirements.correction_of_snapshot_id else None
        else:
            prior = self.repository.get_snapshot(session, requirements.correction_of_snapshot_id) if requirements.correction_of_snapshot_id else None
        if requirements.correction_of_snapshot_id and prior is None:
            raise SnapshotGateError("SNAPSHOT_SUPERSEDES_NOT_FOUND", "Correction target snapshot is unavailable.")
        revision = (prior.revision + 1) if prior else 1
        available_at = max(item.min_available_at for item in evidence.partition_refs)
        capability_input = DataSnapshot.model_construct(
            snapshot_id=snapshot_id,
            trade_date=requirements.trade_date,
            cutoff_at=requirements.cutoff_at,
            provider_policy_id=requirements.provider_policy_id,
            provider_policy_version=requirements.provider_policy_version,
            security_master_ref=requirements.security_master_ref,
            calendar_ref=requirements.calendar_ref,
            canonical_partitions=evidence.partition_refs,
            quality_report_refs=evidence.quality_report_refs,
            quality_status=self.aggregate_partition_quality(evidence.partition_refs),
            publication_status=requirements.publication_status,
            certified_capabilities=(),
            missing_capabilities=(),
            revision=revision,
            revision_kind=revision_kind,
            supersedes_id=requirements.correction_of_snapshot_id,
            available_at=available_at,
            created_at=now,
            published_at=now if requirements.publication_status is SnapshotPublicationStatus.CERTIFIED else None,
            manifest_hash="sha256:" + "0" * 64,
            content_hash="sha256:" + "0" * 64,
            manifest_version="1.0.0",
        )
        all_caps = SnapshotCapabilityEngine.certify(capability_input, partition_rows=partition_rows)
        certified_caps = tuple(
            item.capability_id
            for item in all_caps
            if item.capability_status is SnapshotCapabilityStatus.CERTIFIED
        )
        missing = tuple(
            item.capability_id
            for item in all_caps
            if item.capability_status is not SnapshotCapabilityStatus.CERTIFIED
        )
        draft = DataSnapshot.model_construct(
            **{
                **capability_input.model_dump(mode="python"),
                "certified_capabilities": certified_caps,
                "missing_capabilities": missing,
                "content_hash": compute_content_hash(
                    {"partition_hashes": [item.partition_hash for item in evidence.partition_refs]}
                ),
            }
        )
        snapshot = DataSnapshot.model_validate({**draft.model_dump(mode="python"), "manifest_hash": compute_snapshot_manifest_hash(draft)})
        if requirements.publication_status is SnapshotPublicationStatus.REJECTED:
            raise SnapshotGateError("SNAPSHOT_REJECTED", "Snapshot failed publication requirements.", details={"missing_capabilities": list(missing)})
        if requirements.publication_status is SnapshotPublicationStatus.CERTIFIED and "backtest_core" in requirements.requested_capabilities and "backtest_core" not in certified_caps:
            raise SnapshotGateError("SNAPSHOT_BACKTEST_CORE_UNAVAILABLE", "Certified publication requires backtest_core certification.", details={"missing_capabilities": list(missing)})
        self.manifest_publisher.publish(snapshot)
        if session is None:
            with self.database.transaction() as registry_session:
                self.repository.add_snapshot(registry_session, snapshot, task_id=task_id, attempt_id=attempt_id)
                for certification in all_caps:
                    self.repository.add_capability(registry_session, certification)
        else:
            self.repository.add_snapshot(session, snapshot, task_id=task_id, attempt_id=attempt_id)
            for certification in all_caps:
                self.repository.add_capability(session, certification)
        return snapshot, all_caps

    def check_consumer(
        self,
        snapshot: DataSnapshot,
        requirement: ConsumerRequirement,
        certifications: tuple[CapabilityCertification, ...] | None = None,
    ) -> ConsumerRequirementStatus:
        if snapshot.publication_status not in requirement.accepted_publication_statuses:
            raise SnapshotGateError("SNAPSHOT_CONSUMER_REJECTED", "Snapshot publication status is not accepted.")
        if self._QUALITY_RANK[snapshot.quality_status] < self._QUALITY_RANK[requirement.min_quality_status]:
            raise SnapshotGateError("SNAPSHOT_QUALITY_BELOW_MINIMUM", "Snapshot quality status is below the consumer minimum.")

        if requirement.consumer_kind is ConsumerKind.FORMAL_BACKTEST:
            if snapshot.publication_status is not SnapshotPublicationStatus.CERTIFIED:
                raise SnapshotGateError("SNAPSHOT_BACKTEST_CORE_UNAVAILABLE", "Formal Backtest requires a certified snapshot publication.")
            if not hasattr(self, "database"):
                raise SnapshotGateError("SNAPSHOT_CAPABILITY_UNVERIFIED", "Formal Backtest requires a persisted capability certification.")
            with self.database.transaction() as session:
                persisted, persisted_certifications = self._load_persisted_snapshot_and_capabilities(session, snapshot)
                self._verify_registered_consumer_requirement(session, requirement)
                self._require_certified_capability(persisted, persisted_certifications, "backtest_core")
                for capability_id in requirement.required_capabilities:
                    self._require_certified_capability(persisted, persisted_certifications, capability_id)
                self._validate_backtest_structure(persisted)
                self._validate_persisted_snapshot_lineage(session, persisted)
                self._validate_persisted_snapshot_files(persisted)
            return ConsumerRequirementStatus.ACCEPTED

        available = set(snapshot.certified_capabilities)
        if certifications:
            for item in certifications:
                if item.snapshot_id not in (None, snapshot.snapshot_id):
                    raise SnapshotGateError("SNAPSHOT_CAPABILITY_EVIDENCE_MISMATCH", "Capability evidence is bound to a different snapshot.")
                if item.capability_status is SnapshotCapabilityStatus.CERTIFIED:
                    available.add(item.capability_id)
        missing = set(requirement.required_capabilities) - available
        if missing:
            raise SnapshotGateError("SNAPSHOT_CAPABILITY_MISSING", "Required snapshot capability is unavailable.", details={"missing_capabilities": sorted(missing)})
        return ConsumerRequirementStatus.ACCEPTED

    def update_current_pointer(
        self,
        *,
        scope: str,
        trade_date,
        capability_id: str,
        snapshot: DataSnapshot,
        expected_snapshot_id: str | None = None,
    ) -> SnapshotCurrentPointer:
        if snapshot.trade_date != trade_date:
            raise SnapshotGateError("SNAPSHOT_POINTER_TRADE_DATE_MISMATCH", "Current pointer trade date must match the snapshot.")
        now = self.clock()
        with self.database.transaction() as session:
            persisted, certifications = self._load_persisted_snapshot_and_capabilities(session, snapshot, for_update=True)
            if persisted.publication_status is not SnapshotPublicationStatus.CERTIFIED:
                raise SnapshotGateError("SNAPSHOT_POINTER_CAPABILITY_UNAVAILABLE", "Current pointer requires a certified snapshot capability.")
            self._require_certified_capability(persisted, certifications, capability_id)
            if capability_id == "backtest_core":
                self._validate_backtest_structure(persisted)
                self._validate_persisted_snapshot_lineage(session, persisted)
            self._validate_persisted_snapshot_files(persisted)
            current = self.repository.get_pointer(session, scope=scope, trade_date=trade_date, capability_id=capability_id, for_update=True)
            if expected_snapshot_id is not None and (current is None or current.snapshot_id != expected_snapshot_id):
                raise SnapshotGateError("SNAPSHOT_POINTER_CAS_FAILED", "Current pointer compare-and-set failed.")
            pointer = SnapshotCurrentPointer(
                scope=scope,
                trade_date=trade_date,
                capability_id=capability_id,
                snapshot_id=persisted.snapshot_id,
                previous_snapshot_id=current.snapshot_id if current else None,
                pointer_revision=(current.pointer_revision + 1) if current else 1,
                updated_at=now,
            )
            try:
                return self.repository.upsert_pointer(session, pointer, expected_snapshot_id=expected_snapshot_id)
            except ValueError as exc:
                raise SnapshotGateError("SNAPSHOT_POINTER_CAS_FAILED", "Current pointer compare-and-set failed.") from exc


class SnapshotBuildTaskWorker:
    """Durable-task adapter; it intentionally reuses TaskControlService and its lease semantics."""
    def __init__(self, task_control, snapshot_service: SnapshotGateService):
        self.task_control = task_control
        self.snapshot_service = snapshot_service

    def execute(self, lease: TaskLease, *, partition_rows: Mapping[str, list[Mapping[str, Any]]] | None = None) -> SnapshotBuildTaskResult:
        from src.services.platform.task_control import TaskControlError
        if lease.task.task_type != "data_snapshot_build":
            raise TaskControlError("TASK_TYPE_UNSUPPORTED", "Worker does not support this task type.", status_code=422)
        self.task_control.start_attempt(lease.attempt.attempt_id, lease.lease_token)
        requirements = SnapshotBuildTaskRequirements.model_validate(lease.task.requirements)
        try:
            with self.snapshot_service.database.transaction() as session:
                snapshot, certifications = self.snapshot_service.build_snapshot(requirements, task_id=lease.task.task_id, attempt_id=lease.attempt.attempt_id, partition_rows=partition_rows, session=session)
                self.task_control.complete_in_session(session, attempt_id=lease.attempt.attempt_id, lease_token=lease.lease_token)
            return SnapshotBuildTaskResult(task_id=lease.task.task_id, attempt_id=lease.attempt.attempt_id, snapshot=snapshot, capability_certifications=certifications, published=True)
        except SnapshotGateError as exc:
            try:
                self.task_control.record_failure(lease.attempt.attempt_id, lease.lease_token, failure_code=exc.error_code, retryable=False)
            except TaskControlError:
                pass
            return SnapshotBuildTaskResult(task_id=lease.task.task_id, attempt_id=lease.attempt.attempt_id, capability_certifications=(), published=False, failure_code=exc.error_code, requirement_status=ConsumerRequirementStatus.REJECTED)


__all__ = ["SnapshotBuildTaskWorker", "SnapshotCapabilityEngine", "SnapshotGateError", "SnapshotGateService", "SnapshotManifestPublisher"]
