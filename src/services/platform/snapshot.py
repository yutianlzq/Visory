from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from src.artifacts.hashing import compute_bytes_hash
from src.artifacts.namespace import StorageNamespaceResolver, fsync_directory
from src.repositories.platform.canonical import CanonicalRepository
from src.repositories.platform.raw_ingestion import RawIngestionRepository
from src.repositories.platform.snapshot import SnapshotRepository
from src.schemas.platform import (
    CapabilityCertification,
    ConsumerKind,
    ConsumerRequirement,
    ConsumerRequirementStatus,
    DataSnapshot,
    QualityStatus,
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


class SnapshotCapabilityEngine:
    BASE_CAPABILITIES = ("identity_core", "calendar_core", "financial_research")

    @classmethod
    def certify(cls, snapshot: DataSnapshot, *, now: datetime | None = None) -> tuple[CapabilityCertification, ...]:
        instant = now or _utc_now()
        dataset_ids = {item.dataset_id for item in snapshot.canonical_partitions}
        result: list[CapabilityCertification] = []
        for capability_id in cls.BASE_CAPABILITIES:
            required = {
                "identity_core": {"security_master"},
                "calendar_core": {"trading_calendar"},
                "financial_research": {"financial_statement"},
            }[capability_id]
            if required <= dataset_ids:
                result.append(CapabilityCertification(capability_id=capability_id, capability_status=SnapshotCapabilityStatus.CERTIFIED, evidence_refs=snapshot.quality_report_refs, certified_at=instant, snapshot_id=snapshot.snapshot_id))
            else:
                result.append(CapabilityCertification(capability_id=capability_id, capability_status=SnapshotCapabilityStatus.UNAVAILABLE, reason_code="CAPABILITY_DATASET_MISSING", evidence_refs=snapshot.quality_report_refs, snapshot_id=snapshot.snapshot_id))
        # Deliberately never certify this in WP-0204: the benchmark index dataset is not present.
        result.append(CapabilityCertification(capability_id="backtest_core", capability_status=SnapshotCapabilityStatus.UNAVAILABLE, reason_code="BENCHMARK_DATASET_MISSING", evidence_refs=snapshot.quality_report_refs, snapshot_id=snapshot.snapshot_id))
        return tuple(result)


class SnapshotGateService:
    def __init__(self, database, *, runtime_root: Path | str = ".", repository: SnapshotRepository | None = None, canonical_repository: CanonicalRepository | None = None, raw_repository: RawIngestionRepository | None = None, clock: Callable[[], datetime] = _utc_now) -> None:
        self.database = database
        self.repository = repository or SnapshotRepository()
        self.canonical_repository = canonical_repository or CanonicalRepository()
        self.raw_repository = raw_repository or RawIngestionRepository()
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
            if manifest.get("partition", {}).get("canonical_partition_id") != ref.canonical_partition_id:
                raise ValueError("partition manifest binding mismatch")
            if manifest.get("partition", {}).get("partition_hash") != ref.partition_hash:
                raise ValueError("partition manifest hash mismatch")
            manifest_hash = manifest.get("manifest_hash")
            body = dict(manifest)
            body.pop("manifest_hash", None)
            if manifest_hash != compute_bytes_hash(json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")):
                raise ValueError("partition manifest hash mismatch")
        except SnapshotGateError:
            raise
        except Exception as exc:
            raise SnapshotGateError("SNAPSHOT_PARTITION_MANIFEST_INVALID", "Canonical partition manifest is invalid.") from exc

    def validate_gate(self, requirements: SnapshotBuildTaskRequirements, *, partition_rows: Mapping[str, list[Mapping[str, Any]]] | None = None) -> SnapshotGateEvidence:
        refs: list[SnapshotPartitionRef] = []
        quality_refs: list[str] = []
        if len(requirements.canonical_partition_ids) != len(set(requirements.canonical_partition_ids)):
            raise SnapshotGateError("SNAPSHOT_PARTITION_DUPLICATE", "Snapshot requirements contain duplicate canonical partitions.")
        with self.database.transaction() as session:
            for partition_id in requirements.canonical_partition_ids:
                partition = self.canonical_repository.get_partition(session, partition_id)
                report = self.canonical_repository.get_quality_report(session, partition.quality_report_id) if partition else None
                if partition is None:
                    raise SnapshotGateError("SNAPSHOT_PARTITION_NOT_REGISTERED", "Canonical partition is not registered.")
                if report is None or report.quality_status is QualityStatus.FAILED or partition.quality_status is QualityStatus.FAILED:
                    raise SnapshotGateError("SNAPSHOT_QUALITY_FAILED", "Snapshot cannot reference failed Canonical quality.")
                if partition.min_available_at > requirements.cutoff_at:
                    raise SnapshotGateError("SNAPSHOT_PIT_VIOLATION", "Canonical partition is not available by the snapshot cutoff.")
                if not partition.provider_run_refs or not partition.raw_object_refs:
                    raise SnapshotGateError("SNAPSHOT_LINEAGE_INCOMPLETE", "Canonical partition lineage is incomplete.")
                for run_id in partition.provider_run_refs:
                    if self.raw_repository.get_provider_run(session, run_id) is None:
                        raise SnapshotGateError("SNAPSHOT_PROVIDER_RUN_MISSING", "ProviderRun lineage is unavailable.")
                for raw_id in partition.raw_object_refs:
                    if self.raw_repository.get_raw_object(session, raw_id) is None:
                        raise SnapshotGateError("SNAPSHOT_RAW_OBJECT_MISSING", "RawObject lineage is unavailable.")
                refs.append(SnapshotPartitionRef.from_partition(partition))
                quality_refs.append(partition.quality_report_id)
        if len({ref.provider_policy_version for ref in refs}) != 1:
            raise SnapshotGateError("SNAPSHOT_POLICY_VERSION_CONFLICT", "Snapshot partitions use different ProviderPolicy versions.")
        by_dataset = {}
        for ref in refs:
            prior = by_dataset.setdefault(ref.dataset_id, ref.dataset_schema_version)
            if prior != ref.dataset_schema_version:
                raise SnapshotGateError("SNAPSHOT_SCHEMA_VERSION_CONFLICT", "Snapshot partitions use conflicting schema versions.")
            self._validate_file_and_manifest(ref)
        if partition_rows:
            self._validate_cross_partition_rows(partition_rows, requirements.cutoff_at)
        if requirements.security_master_ref not in {ref.canonical_partition_id for ref in refs} or requirements.calendar_ref not in {ref.canonical_partition_id for ref in refs}:
            raise SnapshotGateError("SNAPSHOT_IDENTITY_CALENDAR_MISSING", "Security Master and Calendar references must be included in the snapshot.")
        # Capability engine will compute final statuses after DataSnapshot exists.
        return SnapshotGateEvidence(tuple(refs), tuple(dict.fromkeys(quality_refs)), tuple(), tuple())

    @staticmethod
    def _validate_cross_partition_rows(rows_by_dataset: Mapping[str, list[Mapping[str, Any]]], cutoff_at: datetime) -> None:
        listing = rows_by_dataset.get("listing_status_history", [])
        by_entity: dict[str, list[tuple[Any, Any]]] = {}
        for row in listing:
            if row.get("available_at") and row["available_at"] > cutoff_at:
                raise SnapshotGateError("SNAPSHOT_PIT_VIOLATION", "A partition row is not available by the snapshot cutoff.")
            by_entity.setdefault(str(row.get("entity_key")), []).append((row.get("effective_from"), row.get("effective_to")))
        for intervals in by_entity.values():
            ordered = sorted(intervals, key=lambda item: item[0])
            for first, second in zip(ordered, ordered[1:]):
                if first[1] is None or second[0] < first[1]:
                    raise SnapshotGateError("SNAPSHOT_LISTING_INTERVAL_CONFLICT", "Listing validity intervals overlap.")
        for dataset_id in ("corporate_action", "financial_statement"):
            seen: set[tuple[Any, ...]] = set()
            for row in rows_by_dataset.get(dataset_id, []):
                key = tuple(row.get(field) for field in ("entity_key", "corporate_action_id", "report_period", "statement_type", "line_item"))
                revision = row.get("revision")
                if row.get("available_at") and row["available_at"] > cutoff_at:
                    raise SnapshotGateError("SNAPSHOT_PIT_VIOLATION", "A partition row is not available by the snapshot cutoff.")
                if (key, revision) in seen:
                    raise SnapshotGateError("SNAPSHOT_REVISION_CONFLICT", "Revision rows overlap in a snapshot.")
                seen.add((key, revision))

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
            quality_status=QualityStatus.COMPLETE,
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
        all_caps = SnapshotCapabilityEngine.certify(capability_input)
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

    def check_consumer(self, snapshot: DataSnapshot, requirement: ConsumerRequirement, certifications: tuple[CapabilityCertification, ...] | None = None) -> ConsumerRequirementStatus:
        if snapshot.publication_status not in requirement.accepted_publication_statuses or snapshot.quality_status is QualityStatus.FAILED:
            raise SnapshotGateError("SNAPSHOT_CONSUMER_REJECTED", "Snapshot publication or quality status is not accepted.")
        if requirement.consumer_kind is ConsumerKind.FORMAL_BACKTEST and (snapshot.publication_status is not SnapshotPublicationStatus.CERTIFIED or "backtest_core" not in snapshot.certified_capabilities):
            raise SnapshotGateError("SNAPSHOT_BACKTEST_CORE_UNAVAILABLE", "Formal Backtest requires backtest_core certification.")
        available = set(snapshot.certified_capabilities)
        if certifications:
            available.update(item.capability_id for item in certifications if item.capability_status is SnapshotCapabilityStatus.CERTIFIED)
        missing = set(requirement.required_capabilities) - available
        if missing:
            raise SnapshotGateError("SNAPSHOT_CAPABILITY_MISSING", "Required snapshot capability is unavailable.", details={"missing_capabilities": sorted(missing)})
        return ConsumerRequirementStatus.ACCEPTED

    def update_current_pointer(self, *, scope: str, trade_date, capability_id: str, snapshot: DataSnapshot, expected_snapshot_id: str | None = None) -> SnapshotCurrentPointer:
        if snapshot.publication_status is not SnapshotPublicationStatus.CERTIFIED or capability_id not in snapshot.certified_capabilities:
            raise SnapshotGateError("SNAPSHOT_POINTER_CAPABILITY_UNAVAILABLE", "Current pointer requires a certified snapshot capability.")
        now = self.clock()
        with self.database.transaction() as session:
            current = self.repository.get_pointer(session, scope=scope, trade_date=trade_date, capability_id=capability_id, for_update=True)
            pointer = SnapshotCurrentPointer(scope=scope, trade_date=trade_date, capability_id=capability_id, snapshot_id=snapshot.snapshot_id, previous_snapshot_id=current.snapshot_id if current else None, pointer_revision=(current.pointer_revision + 1) if current else 1, updated_at=now)
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
