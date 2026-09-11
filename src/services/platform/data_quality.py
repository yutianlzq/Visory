from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import date, datetime, time, timezone
from typing import Any

from src.repositories.platform.canonical import CanonicalRepository
from src.repositories.platform.provider import ProviderRegistryRepository
from src.repositories.platform.raw_ingestion import RawIngestionRepository
from src.repositories.platform.snapshot import SnapshotRepository
from src.repositories.platform.task import TaskControlRepository
from src.repositories.platform.database import PostgresDatabase
from src.schemas.platform import (
    DATA_QUALITY_CAPABILITIES,
    CanonicalPartition,
    CanonicalQualityReport,
    DataQualityActionRequest,
    DataQualityActionResult,
    DataQualityCapability,
    DataQualityDataset,
    DataQualityDiff,
    DataQualityEvidence,
    DataQualityProjection,
    DataQualityQuery,
    DataQualityQueryResult,
    DataQualityTimelineStage,
    DataSnapshot,
    QualityStatus,
    ResourceRef,
    ResourceType,
    RevisionKind,
    SnapshotBuildTaskRequirements,
    SnapshotCapabilityStatus,
    SnapshotPublicationStatus,
    TaskCreateRequest,
)
from src.schemas.platform.scheduler import DAILY_SCHEDULE_TIMEZONE, DailySchedulePhase


_CAPABILITY_DATASETS: dict[str, frozenset[str]] = {
    "identity_core": frozenset({"security_master"}),
    "trading_calendar": frozenset({"trading_calendar"}),
    "calendar_core": frozenset({"trading_calendar"}),
    "backtest_core": frozenset({"security_master", "trading_calendar", "bar_1d_raw", "benchmark_index_1d"}),
    "market_observation": frozenset({"bar_1d_raw"}),
    "sector_observation": frozenset({"sector_observation"}),
    "financial_research": frozenset({"financial_statement"}),
    "news_research": frozenset({"news"}),
    "global_observation": frozenset({"global_observation"}),
}

_TIMELINE: tuple[tuple[str, time], ...] = (
    (DailySchedulePhase.PREFLIGHT.value, time(15, 50)),
    (DailySchedulePhase.CORE_INGESTION.value, time(16, 0)),
    (DailySchedulePhase.NORMALIZATION_QUALITY.value, time(16, 20)),
    (DailySchedulePhase.PROVISIONAL_SNAPSHOT.value, time(16, 30)),
    (DailySchedulePhase.SUPPLEMENTAL_DECISION.value, time(16, 40)),
    (DailySchedulePhase.BACKTEST_CORE_CERTIFICATION.value, time(17, 10)),
    (DailySchedulePhase.CORRECTION_AUDIT.value, time(20, 30)),
)


def _value(value: Any, default: Any = None) -> Any:
    return default if value is None else value


def _enum_value(value: Any) -> Any:
    return getattr(value, "value", value)


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    return str(value)


def _as_date(value: Any) -> date | None:
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


def _as_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo is not None and parsed.utcoffset() is not None else None
    return None


def _partition_date_range(partition_key: str, fallback: date) -> tuple[date, date]:
    parts = [item.strip() for item in partition_key.split("/", 1)]
    if len(parts) == 1:
        parsed = _as_date(parts[0])
        return (parsed or fallback, parsed or fallback)
    start = _as_date(parts[0]) or fallback
    end = _as_date(parts[1]) or start
    return (min(start, end), max(start, end))


def _resource_type(resource_id: str) -> str:
    try:
        resource_type, _ = SnapshotRepositoryResource.parse(resource_id)
        return resource_type.value
    except Exception:
        # Evidence IDs are already validated by their source contracts. This
        # fallback keeps fake repositories and legacy rows observable without
        # leaking storage paths or opaque provider configuration.
        prefix = resource_id.split("_", 1)[0]
        return {
            "prun": ResourceType.PROVIDER_RUN.value,
            "raw": ResourceType.RAW_OBJECT.value,
            "cpart": ResourceType.CANONICAL_PARTITION.value,
            "quality": ResourceType.QUALITY_REPORT.value,
            "rawq": ResourceType.RAW_INGESTION_QUARANTINE.value,
            "ds": ResourceType.DATA_SNAPSHOT.value,
            "task": ResourceType.TASK.value,
        }.get(prefix, "resource")


class SnapshotRepositoryResource:
    """Small indirection to keep resource parsing isolated in this service."""

    @staticmethod
    def parse(resource_id: str):
        from src.schemas.platform import parse_resource_id

        return parse_resource_id(resource_id)


class DataQualityError(Exception):
    """Stable application error for the P-DATA projection and actions."""

    def __init__(
        self,
        error_code: str,
        public_message: str,
        *,
        status_code: int = 404,
        retryable: bool = False,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(public_message)
        self.error_code = error_code
        self.public_message = public_message
        self.status_code = status_code
        self.retryable = retryable
        self.details = dict(details or {})


class DataQualityService:
    """Read-only data-quality projection plus controlled Task Control Plane actions."""

    def __init__(
        self,
        database: PostgresDatabase,
        *,
        snapshot_repository: SnapshotRepository | Any | None = None,
        canonical_repository: CanonicalRepository | Any | None = None,
        raw_repository: RawIngestionRepository | Any | None = None,
        provider_repository: ProviderRegistryRepository | Any | None = None,
        task_control_service: Any | None = None,
        task_repository: Any | None = None,
    ) -> None:
        self.database = database
        self.snapshot_repository = snapshot_repository or SnapshotRepository()
        self.canonical_repository = canonical_repository or CanonicalRepository()
        self.raw_repository = raw_repository or RawIngestionRepository()
        self.provider_repository = provider_repository or ProviderRegistryRepository()
        self.task_control_service = task_control_service
        self.task_repository = task_repository or TaskControlRepository()

    @staticmethod
    def _snapshot_capability_id(capability_id: str) -> tuple[str, ...]:
        return (capability_id, "calendar_core") if capability_id == "trading_calendar" else (capability_id,)

    def _find_snapshot(self, session: Any, query: DataQualityQuery) -> DataSnapshot:
        snapshot = None
        if query.snapshot_id is not None:
            snapshot = self.snapshot_repository.get_snapshot(session, query.snapshot_id)
        elif query.trade_date is not None:
            snapshot = self.snapshot_repository.get_latest_for_trade_date(session, query.trade_date)
        else:
            raise DataQualityError(
                "DATA_QUALITY_QUERY_REQUIRED",
                "trade_date or snapshot_id is required.",
                status_code=422,
            )
        if snapshot is None or (query.trade_date is not None and snapshot.trade_date != query.trade_date):
            raise DataQualityError(
                "DATA_QUALITY_SNAPSHOT_NOT_FOUND",
                "No data snapshot matches the requested filters.",
                status_code=404,
            )
        return snapshot

    def _capability_records(self, session: Any, snapshot: DataSnapshot) -> tuple[DataQualityCapability, ...]:
        records = {
            item.capability_id: item
            for item in self.snapshot_repository.list_capabilities(session, snapshot.snapshot_id)
        }
        capabilities: list[DataQualityCapability] = []
        partition_datasets = {item.dataset_id for item in snapshot.canonical_partitions}
        for capability_id in DATA_QUALITY_CAPABILITIES:
            certification = next(
                (records[item] for item in self._snapshot_capability_id(capability_id) if item in records),
                None,
            )
            if certification is not None:
                status = certification.capability_status
                reason_code = certification.reason_code
                evidence_refs = certification.evidence_refs
            elif capability_id in snapshot.certified_capabilities:
                status = SnapshotCapabilityStatus.CERTIFIED
                reason_code = None
                evidence_refs = snapshot.quality_report_refs
            elif capability_id in snapshot.missing_capabilities or (
                capability_id == "trading_calendar" and "calendar_core" in snapshot.missing_capabilities
            ):
                status = SnapshotCapabilityStatus.UNAVAILABLE
                reason_code = "CAPABILITY_NOT_PRESENT"
                evidence_refs = ()
            else:
                status = SnapshotCapabilityStatus.UNVERIFIED
                reason_code = "CAPABILITY_NOT_RECORDED"
                evidence_refs = ()
            dataset_ids = tuple(
                sorted(partition_datasets.intersection(_CAPABILITY_DATASETS.get(capability_id, frozenset())))
            )
            capabilities.append(
                DataQualityCapability(
                    capability_id=capability_id,
                    capability_status=status,
                    reason_code=reason_code,
                    evidence_refs=tuple(evidence_refs),
                    dataset_ids=dataset_ids,
                    provider_ids=self._provider_ids_for_datasets(snapshot, dataset_ids, session),
                )
            )
        return tuple(capabilities)

    def _provider_ids_for_datasets(self, snapshot: DataSnapshot, dataset_ids: Iterable[str], session: Any) -> tuple[str, ...]:
        selected = set(dataset_ids)
        provider_ids: set[str] = set()
        for ref in snapshot.canonical_partitions:
            if ref.dataset_id not in selected:
                continue
            for run_id in ref.provider_run_refs:
                run = self.raw_repository.get_provider_run(session, run_id)
                if run is not None and getattr(run, "provider_id", None):
                    provider_ids.add(run.provider_id)
        return tuple(sorted(provider_ids))

    @staticmethod
    def _evidence(
        resource_id: str,
        resource_type: str,
        *,
        dataset_id: str | None = None,
        provider_id: str | None = None,
        quality_status: QualityStatus | None = None,
        revision: int | None = None,
        revision_kind: RevisionKind | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> DataQualityEvidence:
        return DataQualityEvidence(
            resource_id=resource_id,
            resource_type=resource_type,
            dataset_id=dataset_id,
            provider_id=provider_id,
            quality_status=quality_status,
            revision=revision,
            revision_kind=revision_kind,
            details=dict(details or {}),
        )

    def _dataset_projection(self, session: Any, snapshot: DataSnapshot, ref: Any) -> DataQualityDataset:
        provider_runs: list[DataQualityEvidence] = []
        raw_objects: list[DataQualityEvidence] = []
        quarantines: list[DataQualityEvidence] = []
        provider_ids: set[str] = set()
        conflict_count = 0
        for run_id in ref.provider_run_refs:
            run = self.raw_repository.get_provider_run(session, run_id)
            if run is None:
                continue
            provider_id = getattr(run, "provider_id", None)
            if provider_id:
                provider_ids.add(provider_id)
            provider_runs.append(
                self._evidence(
                    run.provider_run_id,
                    ResourceType.PROVIDER_RUN.value,
                    dataset_id=getattr(run, "dataset_id", ref.dataset_id),
                    provider_id=provider_id,
                    details={
                        key: _enum_value(getattr(run, key, None))
                        for key in ("actual_upstream", "run_outcome", "started_at", "finished_at", "row_count", "failure_code")
                        if getattr(run, key, None) is not None
                    },
                )
            )
            raw = self.raw_repository.get_raw_object_by_run(session, run_id)
            if raw is None:
                for raw_id in ref.raw_object_refs:
                    raw = self.raw_repository.get_raw_object(session, raw_id)
                    if raw is not None:
                        break
            if raw is not None:
                raw_provider = getattr(raw, "provider_id", provider_id)
                if raw_provider:
                    provider_ids.add(raw_provider)
                raw_objects.append(
                    self._evidence(
                        raw.raw_object_id,
                        ResourceType.RAW_OBJECT.value,
                        dataset_id=getattr(raw, "dataset_id", ref.dataset_id),
                        provider_id=raw_provider,
                        details={
                            key: _enum_value(getattr(raw, key, None))
                            for key in ("actual_upstream", "media_type", "compression", "observed_at", "ingested_at", "row_count", "byte_count")
                            if getattr(raw, key, None) is not None
                        },
                    )
                )
            quarantine = self.raw_repository.get_quarantine_by_run(session, run_id)
            if quarantine is not None:
                quarantines.append(
                    self._evidence(
                        quarantine.raw_ingestion_quarantine_id,
                        ResourceType.RAW_INGESTION_QUARANTINE.value,
                        dataset_id=ref.dataset_id,
                        provider_id=provider_id,
                        details={
                            key: _enum_value(getattr(quarantine, key, None))
                            for key in ("classification", "reason_code", "quarantine_status", "created_at", "failure_detail_redacted")
                            if getattr(quarantine, key, None) is not None
                        },
                    )
                )

        canonical = self.canonical_repository.get_partition(session, ref.canonical_partition_id)
        canonical_evidence = (
            self._evidence(
                ref.canonical_partition_id,
                ResourceType.CANONICAL_PARTITION.value,
                dataset_id=ref.dataset_id,
                quality_status=ref.quality_status,
                revision=ref.revision,
                revision_kind=ref.revision_kind,
                details={
                    "partition_key": ref.partition_key,
                    "partition_hash": ref.partition_hash,
                    "schema_hash": ref.schema_hash,
                    "row_count": ref.row_count,
                    "available_from": _iso(ref.min_available_at),
                    "available_to": _iso(ref.max_available_at),
                },
            ),
        )
        if canonical is None:
            canonical_evidence = ()

        report = self.canonical_repository.get_quality_report(session, ref.quality_report_id)
        report_evidence: tuple[DataQualityEvidence, ...] = ()
        if report is not None:
            conflict_count = int(getattr(report, "duplicate_key_count", 0) or 0)
            report_evidence = (
                self._evidence(
                    report.quality_report_id,
                    ResourceType.QUALITY_REPORT.value,
                    dataset_id=getattr(report, "dataset_id", ref.dataset_id),
                    quality_status=getattr(report, "quality_status", ref.quality_status),
                    details={
                        key: _enum_value(getattr(report, key, None))
                        for key in ("row_count", "rejected_row_count", "duplicate_key_count", "coverage_ratio", "failure_reasons", "created_at")
                        if getattr(report, key, None) is not None
                    },
                ),
            )

        trade_date_from, trade_date_to = _partition_date_range(ref.partition_key, snapshot.trade_date)
        freshness = ref.max_available_at or ref.min_available_at
        return DataQualityDataset(
            dataset_id=ref.dataset_id,
            dataset_schema_version=ref.dataset_schema_version,
            provider_ids=tuple(sorted(provider_ids)),
            partition_key=ref.partition_key,
            trade_date_from=trade_date_from,
            trade_date_to=trade_date_to,
            coverage_ratio=float(ref.coverage_ratio),
            freshness_at=freshness,
            row_count=ref.row_count,
            conflict_count=conflict_count,
            quality_status=ref.quality_status,
            revision=ref.revision,
            revision_kind=ref.revision_kind,
            snapshot_ids=(snapshot.snapshot_id,),
            provider_runs=tuple(provider_runs),
            raw_objects=tuple(raw_objects),
            canonical_partitions=canonical_evidence,
            quality_reports=report_evidence,
            quarantines=tuple(quarantines),
            correction_snapshot_id=snapshot.supersedes_id,
        )

    def _timeline_tasks(self, session: Any, trade_date: date) -> dict[str, Any]:
        method = getattr(self.task_repository, "list_schedule_tasks", None)
        if method is None:
            return {}
        rows = method(session, trade_date)
        return {str(getattr(task, "requirements", {}).get("phase")): task for task in rows}

    def _timeline(self, session: Any, snapshot: DataSnapshot) -> tuple[DataQualityTimelineStage, ...]:
        tasks = self._timeline_tasks(session, snapshot.trade_date)
        stages = []
        for stage_id, stage_time in _TIMELINE:
            task = tasks.get(stage_id)
            if task is None:
                status, reason, ids = "UNVERIFIED", "SCHEDULE_TASK_NOT_RECORDED", ()
            else:
                state = _enum_value(getattr(task, "task_state", None))
                status = {"SUCCEEDED":"COMPLETE", "DEGRADED":"DEGRADED", "BLOCKED":"BLOCKED", "FAILED":"FAILED"}.get(state, "PENDING")
                reason = getattr(task, "blocked_reason_code", None) or getattr(task, "failure_code", None)
                ids = (task.task_id,)
            stages.append(DataQualityTimelineStage(stage_id=stage_id, local_time=stage_time, stage_status=status, reason_code=reason, task_ids=ids))
        return tuple(stages)

    def _snapshot_task_ids(self, session: Any, snapshot_id: str) -> tuple[str, ...]:
        method = getattr(self.snapshot_repository, "get_lineage", None)
        if method is None:
            return ()
        return tuple(item for item in method(session, snapshot_id) if item and _resource_type(item) == ResourceType.TASK.value)

    def _current_pointers(self, session: Any, trade_date: date) -> tuple[dict[str, Any], ...]:
        pointers = self.snapshot_repository.list_pointers(session, trade_date)
        return tuple(
            {
                "scope": item.scope,
                "trade_date": item.trade_date,
                "capability_id": item.capability_id,
                "snapshot_id": item.snapshot_id,
                "previous_snapshot_id": item.previous_snapshot_id,
                "pointer_revision": item.pointer_revision,
                "updated_at": item.updated_at,
            }
            for item in pointers
        )

    def get_projection(self, query: DataQualityQuery) -> DataQualityQueryResult:
        with self.database.transaction() as session:
            snapshot = self._find_snapshot(session, query)
            capabilities = self._capability_records(session, snapshot)
            datasets = tuple(self._dataset_projection(session, snapshot, ref) for ref in snapshot.canonical_partitions)
            pointers = self._current_pointers(session, snapshot.trade_date)
            timeline = self._timeline(session, snapshot)
            task_ids = self._snapshot_task_ids(session, snapshot.snapshot_id)

            if query.dataset is not None:
                datasets = tuple(item for item in datasets if item.dataset_id == query.dataset)
            if query.provider is not None:
                datasets = tuple(item for item in datasets if query.provider in item.provider_ids)
            if query.quality_status is not None:
                datasets = tuple(item for item in datasets if item.quality_status is query.quality_status)
            if query.capability is not None:
                capabilities = tuple(item for item in capabilities if item.capability_id == query.capability)
                allowed_datasets = _CAPABILITY_DATASETS.get(query.capability, frozenset())
                datasets = tuple(item for item in datasets if item.dataset_id in allowed_datasets)

            if query.dataset is not None and not datasets:
                raise DataQualityError(
                    "DATA_QUALITY_DATASET_NOT_FOUND",
                    "No data-quality dataset matches the requested filters.",
                    status_code=404,
                )
            if query.provider is not None and not datasets:
                raise DataQualityError(
                    "DATA_QUALITY_PROVIDER_NOT_FOUND",
                    "No data-quality provider matches the requested filters.",
                    status_code=404,
                )
            if query.capability is not None and not capabilities:
                raise DataQualityError(
                    "DATA_QUALITY_CAPABILITY_NOT_FOUND",
                    "No data-quality capability matches the requested filters.",
                    status_code=404,
                )
            if query.quality_status is not None and snapshot.quality_status is not query.quality_status and not datasets:
                raise DataQualityError(
                    "DATA_QUALITY_STATUS_NOT_FOUND",
                    "No data-quality records match the requested status.",
                    status_code=404,
                )

            warnings = list(snapshot.missing_capabilities)
            if snapshot.quality_status is not QualityStatus.COMPLETE:
                warnings.append(f"QUALITY_{snapshot.quality_status.value}")
            return DataQualityQueryResult(
                trade_date=snapshot.trade_date,
                data_as_of=snapshot.available_at,
                snapshot_id=snapshot.snapshot_id,
                publication_status=snapshot.publication_status,
                quality_status=snapshot.quality_status,
                cutoff_at=snapshot.cutoff_at,
                revision=snapshot.revision,
                revision_kind=snapshot.revision_kind,
                supersedes_id=snapshot.supersedes_id,
                current_pointers=pointers,
                capabilities=capabilities,
                missing_capabilities=snapshot.missing_capabilities,
                datasets=datasets,
                timeline=timeline,
                task_ids=task_ids,
                warnings=tuple(dict.fromkeys(warnings)),
            )

    def _load_snapshot(self, session: Any, snapshot_id: str) -> DataSnapshot:
        snapshot = self.snapshot_repository.get_snapshot(session, snapshot_id)
        if snapshot is None:
            raise DataQualityError("DATA_QUALITY_SNAPSHOT_NOT_FOUND", "Snapshot does not exist.", status_code=404)
        return snapshot

    @staticmethod
    def _partition_summary(ref: Any) -> dict[str, Any]:
        return {
            "canonical_partition_id": ref.canonical_partition_id,
            "dataset_id": ref.dataset_id,
            "partition_key": ref.partition_key,
            "revision": ref.revision,
            "revision_kind": _enum_value(ref.revision_kind),
            "quality_status": _enum_value(ref.quality_status),
            "partition_hash": ref.partition_hash,
            "provider_run_refs": list(ref.provider_run_refs),
        }

    def _provider_ids_for_snapshot(self, session: Any, snapshot: DataSnapshot) -> dict[tuple[str, str], set[str]]:
        result: dict[tuple[str, str], set[str]] = {}
        for ref in snapshot.canonical_partitions:
            providers = result.setdefault((ref.dataset_id, ref.partition_key), set())
            for run_id in ref.provider_run_refs:
                run = self.raw_repository.get_provider_run(session, run_id)
                provider_id = getattr(run, "provider_id", None) if run is not None else None
                if provider_id:
                    providers.add(provider_id)
        return result

    def _capability_status_map(self, session: Any, snapshot: DataSnapshot) -> dict[str, str]:
        records = {item.capability_id: item for item in self.snapshot_repository.list_capabilities(session, snapshot.snapshot_id)}
        result = {}
        for capability_id in DATA_QUALITY_CAPABILITIES:
            record = next((records[item] for item in self._snapshot_capability_id(capability_id) if item in records), None)
            if record is not None:
                result[capability_id] = _enum_value(record.capability_status)
            elif capability_id in snapshot.certified_capabilities:
                result[capability_id] = SnapshotCapabilityStatus.CERTIFIED.value
            else:
                result[capability_id] = SnapshotCapabilityStatus.UNAVAILABLE.value
        return result

    def compare_snapshots(self, snapshot_id: str, base_snapshot_id: str | None = None) -> DataQualityDiff:
        with self.database.transaction() as session:
            target = self._load_snapshot(session, snapshot_id)
            base_id = base_snapshot_id or target.supersedes_id
            if base_id is None:
                pointers = self.snapshot_repository.list_pointers(session, target.trade_date)
                base_id = next((item.previous_snapshot_id for item in pointers if item.previous_snapshot_id), None)
            if base_id is None:
                raise DataQualityError(
                    "DATA_QUALITY_COMPARE_BASE_REQUIRED",
                    "A previous or correction snapshot is required for comparison.",
                    status_code=422,
                )
            base = self._load_snapshot(session, base_id)
            if base.snapshot_id == target.snapshot_id:
                raise DataQualityError(
                    "DATA_QUALITY_COMPARE_SAME_SNAPSHOT",
                    "Snapshot compare requires two distinct snapshots.",
                    status_code=422,
                )
            if base.trade_date != target.trade_date:
                raise DataQualityError(
                    "DATA_QUALITY_COMPARE_TRADE_DATE_MISMATCH",
                    "Snapshot compare requires snapshots from the same trade date.",
                    status_code=422,
                )
            target_by_key = {(item.dataset_id, item.partition_key): item for item in target.canonical_partitions}
            base_by_key = {(item.dataset_id, item.partition_key): item for item in base.canonical_partitions}
            added = tuple(self._partition_summary(target_by_key[key]) for key in sorted(target_by_key.keys() - base_by_key.keys()))
            removed = tuple(self._partition_summary(base_by_key[key]) for key in sorted(base_by_key.keys() - target_by_key.keys()))
            revised = tuple(
                self._partition_summary(target_by_key[key])
                for key in sorted(target_by_key.keys() & base_by_key.keys())
                if target_by_key[key].canonical_partition_id != base_by_key[key].canonical_partition_id
                or target_by_key[key].revision != base_by_key[key].revision
                or target_by_key[key].partition_hash != base_by_key[key].partition_hash
                or target_by_key[key].quality_status != base_by_key[key].quality_status
            )
            quality_changes = tuple(
                {
                    "dataset_id": key[0],
                    "partition_key": key[1],
                    "from": _enum_value(base_by_key[key].quality_status),
                    "to": _enum_value(target_by_key[key].quality_status),
                }
                for key in sorted(target_by_key.keys() & base_by_key.keys())
                if target_by_key[key].quality_status != base_by_key[key].quality_status
            )
            base_caps = self._capability_status_map(session, base)
            target_caps = self._capability_status_map(session, target)
            capability_changes = tuple(
                {"capability_id": key, "from": base_caps[key], "to": target_caps[key]}
                for key in DATA_QUALITY_CAPABILITIES
                if base_caps[key] != target_caps[key]
            )
            base_providers = self._provider_ids_for_snapshot(session, base)
            target_providers = self._provider_ids_for_snapshot(session, target)
            provider_switches = tuple(
                {
                    "dataset_id": key[0],
                    "partition_key": key[1],
                    "from": sorted(base_providers.get(key, set())),
                    "to": sorted(target_providers.get(key, set())),
                }
                for key in sorted(set(base_providers) | set(target_providers))
                if base_providers.get(key, set()) != target_providers.get(key, set())
            )
            consumers = []
            list_consumers = getattr(self.snapshot_repository, "list_consumer_requirements", None)
            if list_consumers is not None:
                changed_caps = {item["capability_id"] for item in capability_changes}
                for consumer in list_consumers(session):
                    if changed_caps.intersection(consumer.required_capabilities) or base.quality_status != target.quality_status:
                        consumers.append(
                            {
                                "consumer_id": consumer.consumer_id,
                                "consumer_kind": _enum_value(consumer.consumer_kind),
                                "required_capabilities": list(consumer.required_capabilities),
                            }
                        )
            task_ids = tuple(dict.fromkeys(self._lineage_for_session(session, base.snapshot_id) + self._lineage_for_session(session, target.snapshot_id)))
        return DataQualityDiff(
            base_snapshot_id=base.snapshot_id,
            target_snapshot_id=target.snapshot_id,
            added_partitions=added,
            removed_partitions=removed,
            revised_partitions=revised,
            quality_changes=quality_changes,
            capability_changes=capability_changes,
            provider_switches=provider_switches,
            affected_consumers=tuple(consumers),
            affected_tasks=task_ids,
        )

    def _lineage_for_session(self, session: Any, snapshot_id: str) -> tuple[str, ...]:
        method = getattr(self.snapshot_repository, "get_lineage", None)
        if method is None:
            return ()
        return tuple(item for item in method(session, snapshot_id) if item and _resource_type(item) == ResourceType.TASK.value)

    def create_action(self, action: DataQualityActionRequest, *, idempotency_key: str) -> DataQualityActionResult:
        if self.task_control_service is None:
            raise DataQualityError(
                "DATA_QUALITY_TASK_CONTROL_UNAVAILABLE",
                "Task Control Plane is unavailable.",
                status_code=503,
                retryable=True,
            )
        with self.database.transaction() as session:
            snapshot = self._find_snapshot(
                session,
                DataQualityQuery(trade_date=action.trade_date, snapshot_id=action.snapshot_id),
            )
            requirements = SnapshotBuildTaskRequirements(
                trade_date=snapshot.trade_date,
                cutoff_at=snapshot.cutoff_at,
                provider_policy_id=snapshot.provider_policy_id,
                provider_policy_version=snapshot.provider_policy_version,
                security_master_ref=snapshot.security_master_ref,
                calendar_ref=snapshot.calendar_ref,
                canonical_partition_ids=tuple(item.canonical_partition_id for item in snapshot.canonical_partitions),
                requested_capabilities=tuple(dict.fromkeys(snapshot.certified_capabilities + snapshot.missing_capabilities)) or DATA_QUALITY_CAPABILITIES,
                publication_status=snapshot.publication_status,
                correction_of_snapshot_id=snapshot.snapshot_id if action.action == "correction" else None,
                reason_code=action.reason_code,
            )
            request = TaskCreateRequest(
                task_type="data_snapshot_build",
                requested_by=action.requested_by,
                request_source=f"data_quality:{action.action}",
                input_refs=(ResourceRef(resource_type=ResourceType.DATA_SNAPSHOT, resource_id=snapshot.snapshot_id),),
                requirements=requirements.model_dump(mode="python", exclude_none=True),
            )
        task = self.task_control_service.create_task(
            request,
            idempotency_key=idempotency_key,
            endpoint="/api/platform/v1/data-quality/actions",
        )
        return DataQualityActionResult(
            task_id=task.task_id,
            action=action.action,
            snapshot_id=snapshot.snapshot_id,
            correction_of_snapshot_id=snapshot.snapshot_id if action.action == "correction" else None,
        )


__all__ = [
    "DATA_QUALITY_CAPABILITIES",
    "DataQualityActionRequest",
    "DataQualityActionResult",
    "DataQualityError",
    "DataQualityQuery",
    "DataQualityQueryResult",
    "DataQualityService",
]
