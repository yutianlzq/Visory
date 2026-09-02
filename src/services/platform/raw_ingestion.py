from __future__ import annotations

import json
import os
import re
import shutil
import time
from collections import deque
from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from src.artifacts.hashing import compute_bytes_hash
from src.artifacts.namespace import StorageNamespaceResolver, fsync_directory
from src.repositories.platform.database import PostgresDatabase
from src.repositories.platform.raw_ingestion import RawIngestionRepository
from src.schemas.platform import (
    ProviderRawSchemaDefinition,
    ProviderRun,
    ProviderRunOutcome,
    RawCompression,
    RawIngestionPublishResult,
    RawIngestionQuarantine,
    RawIngestionTaskRequirements,
    RawObject,
    RawSchemaDriftClassification,
    ResourceType,
    RetentionClass,
    StorageBackend,
    StorageNamespace,
    StorageRef,
    TaskLease,
    TaskState,
    compute_content_hash,
    ensure_safe_actual_upstream,
    generate_resource_id,
)
from src.services.platform.task_control import TaskControlError, TaskControlService


_SAFE_FILENAME = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RawIngestionError(Exception):
    def __init__(
        self,
        error_code: str,
        public_message: str,
        *,
        retryable: bool = False,
        details: Mapping[str, str] | None = None,
        cause: Exception | None = None,
    ) -> None:
        super().__init__(public_message)
        self.error_code = error_code
        self.public_message = public_message
        self.retryable = retryable
        self.details = dict(details or {})
        self.__cause__ = cause


@dataclass(frozen=True, slots=True)
class ProviderFetchRequest:
    provider_id: str
    dataset_id: str
    dataset_schema_version: str
    request: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class ProviderFetchResponse:
    content: bytes
    media_type: str
    compression: RawCompression
    actual_upstream: str
    observed_at: datetime
    source_published_at: datetime | None
    raw_schema_fields: tuple[str, ...] | None
    raw_schema_field_types: Mapping[str, str] | None = None
    provider_schema_version: str = "1.0.0"
    row_count: int | None = None


class ProviderTransport(Protocol):
    def fetch(
        self, adapter_name: str, request: ProviderFetchRequest, *, timeout_seconds: int
    ) -> ProviderFetchResponse:
        ...


class ControlledProviderAdapter:
    def __init__(self, adapter_name: str, default_actual_upstream: str) -> None:
        self.adapter_name = adapter_name
        self.default_actual_upstream = default_actual_upstream

    def fetch(self, transport: ProviderTransport, request: ProviderFetchRequest, *, timeout_seconds: int) -> ProviderFetchResponse:
        return transport.fetch(self.adapter_name, request, timeout_seconds=timeout_seconds)


class ControlledProviderAdapterRegistry:
    """Fixed adapters only; caller input never controls Python import paths."""

    def __init__(self, adapters: Mapping[str, ControlledProviderAdapter] | None = None) -> None:
        self._adapters = dict(
            adapters
            or {
                "a_stock_data": ControlledProviderAdapter("a_stock_data", "a-stock-data"),
                "financial_api": ControlledProviderAdapter("financial_api", "financial-api"),
            }
        )

    def resolve(self, adapter_name: str) -> ControlledProviderAdapter:
        try:
            return self._adapters[adapter_name]
        except KeyError as exc:
            raise RawIngestionError(
                "RAW_ADAPTER_NOT_REGISTERED",
                "Provider adapter is not registered.",
                details={"adapter_name": adapter_name},
            ) from exc


class FakeProviderTransport:
    """Deterministic offline transport for fixtures and failure injection."""

    def __init__(self, responses: Mapping[tuple[str, str], ProviderFetchResponse | Exception]) -> None:
        self._responses = dict(responses)
        self.calls: list[tuple[str, str, int]] = []

    def fetch(self, adapter_name: str, request: ProviderFetchRequest, *, timeout_seconds: int) -> ProviderFetchResponse:
        self.calls.append((adapter_name, request.dataset_id, timeout_seconds))
        response = self._responses.get((adapter_name, request.dataset_id))
        if response is None:
            raise RawIngestionError("RAW_FIXTURE_MISSING", "Offline provider fixture is missing.")
        if isinstance(response, Exception):
            raise response
        return response


class ProviderRateLimiter:
    """In-memory limiter retained for deterministic unit tests only."""

    def __init__(self, *, monotonic: Callable[[], float] = time.monotonic) -> None:
        self._monotonic = monotonic
        self._requests: dict[tuple[str, str], deque[float]] = {}

    def acquire(self, provider_id: str, dataset_id: str, profile: Mapping[str, Any], **_: Any) -> None:
        limit = profile.get("requests_per_minute")
        if not isinstance(limit, int) or limit <= 0:
            raise RawIngestionError("RAW_RATE_LIMIT_PROFILE_INVALID", "Provider rate-limit policy is invalid.")
        key = (provider_id, dataset_id)
        now = self._monotonic()
        window = self._requests.setdefault(key, deque())
        while window and window[0] <= now - 60:
            window.popleft()
        if len(window) >= limit:
            raise RawIngestionError(
                "RAW_RATE_LIMITED",
                "Provider rate limit is currently exhausted.",
                retryable=True,
                details={"provider_id": provider_id, "dataset_id": dataset_id},
            )
        window.append(now)


class PostgresRateLimiter:
    """Coordinates provider quotas across workers using PostgreSQL row locks."""

    def __init__(
        self,
        transaction_context: Callable[[], AbstractContextManager[object]],
        *,
        clock: Callable[[], datetime] = _utc_now,
        repository: RawIngestionRepository | None = None,
    ) -> None:
        self.transaction_context = transaction_context
        self.clock = clock
        self.repository = repository or RawIngestionRepository()

    def acquire(
        self,
        provider_id: str,
        dataset_id: str,
        profile: Mapping[str, Any],
        *,
        market: str = "CN",
        frequency: str = "1d",
    ) -> None:
        limit = profile.get("requests_per_minute")
        if not isinstance(limit, int) or limit <= 0:
            raise RawIngestionError("RAW_RATE_LIMIT_PROFILE_INVALID", "Provider rate-limit policy is invalid.")
        window_epoch = int(self.clock().timestamp() // 60)
        with self.transaction_context() as session:
            allowed = self.repository.increment_rate_limit_window(
                session, provider_id=provider_id, dataset_id=dataset_id, market=market,
                frequency=frequency, window_epoch=window_epoch, limit=limit,
            )
        if not allowed:
            raise RawIngestionError(
                "RAW_RATE_LIMITED",
                "Provider rate limit is currently exhausted.",
                retryable=True,
                details={"provider_id": provider_id, "dataset_id": dataset_id},
            )


def classify_raw_schema(
    expected: ProviderRawSchemaDefinition | tuple[str, ...],
    observed_fields: tuple[str, ...] | None,
    observed_field_types: Mapping[str, str] | None = None,
) -> RawSchemaDriftClassification:
    """Classify only provider-native fields; canonical DatasetDefinition is never used."""

    if observed_fields is None or not observed_fields:
        return RawSchemaDriftClassification.UNKNOWN_SCHEMA
    if isinstance(expected, ProviderRawSchemaDefinition):
        required = set(expected.required_fields)
        optional = set(expected.optional_fields)
        declared = required | optional
        observed = set(observed_fields)
        if not required <= observed:
            return RawSchemaDriftClassification.BREAKING_DRIFT
        if observed_field_types is not None:
            for field_name in observed & declared:
                if observed_field_types.get(field_name) != expected.field_types[field_name]:
                    return RawSchemaDriftClassification.BREAKING_DRIFT
        return RawSchemaDriftClassification.MATCHED if observed <= declared and observed >= required else RawSchemaDriftClassification.ADDITIVE_DRIFT
    observed = set(observed_fields)
    expected_fields = set(expected)
    if observed == expected_fields:
        return RawSchemaDriftClassification.MATCHED
    if expected_fields <= observed:
        return RawSchemaDriftClassification.ADDITIVE_DRIFT
    return RawSchemaDriftClassification.BREAKING_DRIFT


def _schema_hash(
    fields: tuple[str, ...] | None, field_types: Mapping[str, str] | None = None
) -> str | None:
    if not fields:
        return None
    payload: dict[str, object] = {"raw_schema_fields": tuple(sorted(fields))}
    if field_types is not None:
        payload["raw_schema_field_types"] = {key: field_types[key] for key in sorted(field_types)}
    return compute_content_hash(payload)


def _row_count(content: bytes, declared: int | None) -> int:
    if declared is not None:
        return declared
    try:
        value = json.loads(content)
    except (UnicodeDecodeError, ValueError):
        return 0
    return len(value) if isinstance(value, list) else 1


def _error_detail(exc: Exception) -> str:
    # Error strings can include URLs, headers, provider bodies, and credentials; retain only the type.
    return f"provider_error:{exc.__class__.__name__}"


class RawObjectPublisher:
    """Atomic raw/quarantine file publication bound to StorageRef, never host paths."""

    def __init__(
        self,
        runtime_root: Path | str,
        transaction_context: Callable[[], AbstractContextManager[object]],
        *,
        clock: Callable[[], datetime] = _utc_now,
        rename: Callable[[Path, Path], None] = os.replace,
    ) -> None:
        self.resolver = StorageNamespaceResolver(runtime_root)
        self.transaction_context = transaction_context
        self.clock = clock
        self.rename = rename

    def _write_directory(
        self,
        relative_directory: str,
        payload_filename: str,
        content: bytes,
        manifest: dict[str, Any],
        *,
        allow_internal: bool = False,
    ) -> StorageRef:
        if not _SAFE_FILENAME.fullmatch(payload_filename):
            raise RawIngestionError("RAW_PATH_INVALID", "Raw payload filename is invalid.")
        namespace_root = self.resolver.ensure_namespace()
        staging_root = self.resolver.resolve(".staging", allow_internal=True)
        staging_root.mkdir(parents=True, exist_ok=True)
        target_directory = self.resolver.resolve(relative_directory, allow_internal=allow_internal)
        if target_directory.exists():
            raise RawIngestionError("RAW_TARGET_EXISTS", "Raw target already exists.")
        staging_directory = staging_root / f"raw-{generate_resource_id(ResourceType.RAW_OBJECT)}"
        staging_directory.mkdir(mode=0o700)
        payload_path = staging_directory / payload_filename
        try:
            with payload_path.open("xb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            manifest_path = staging_directory / "manifest.json"
            with manifest_path.open("xb") as handle:
                encoded = (json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            fsync_directory(staging_directory)
            fsync_directory(staging_root)
            target_directory.parent.mkdir(parents=True, exist_ok=True)
            self.resolver.resolve(target_directory.parent.relative_to(namespace_root).as_posix(), allow_internal=allow_internal)
            self.rename(staging_directory, target_directory)
            fsync_directory(target_directory.parent)
        except RawIngestionError:
            raise
        except OSError as exc:
            try:
                if staging_directory.exists():
                    shutil.rmtree(staging_directory)
            except OSError:
                pass
            raise RawIngestionError(
                "RAW_ATOMIC_PUBLISH_FAILED",
                "Raw storage publication failed.",
                retryable=True,
                details={"component": "raw_storage"},
                cause=exc,
            ) from exc
        return StorageRef(
            storage_backend=StorageBackend.LOCAL_FS,
            storage_namespace=StorageNamespace.APP,
            relative_path=f"{relative_directory}/{payload_filename}",
            content_hash=compute_bytes_hash(content),
            media_type=str(manifest["media_type"]),
            size_bytes=len(content),
        )

    def publish_raw(self, record: RawObject, content: bytes, *, after_register: Callable[[object, RawObject], None]) -> RawObject:
        if compute_bytes_hash(content) != record.raw_content_hash or len(content) != record.byte_count:
            raise RawIngestionError("RAW_CONTENT_VALIDATION_FAILED", "Raw content integrity validation failed.")
        directory = (
            f"raw/provider={record.provider_id}/dataset={record.dataset_id}/"
            f"year={record.ingested_at:%Y}/month={record.ingested_at:%m}/"
            f"provider_run={record.provider_run_id}/raw_object={record.raw_object_id}"
        )
        expected_ref = StorageRef(
            storage_backend=StorageBackend.LOCAL_FS,
            storage_namespace=StorageNamespace.APP,
            relative_path=f"{directory}/payload.bin",
            content_hash=compute_bytes_hash(content),
            media_type=record.media_type,
            size_bytes=len(content),
        )
        publishable = record.model_copy(update={"storage_ref": expected_ref})
        storage_ref = self._write_directory(directory, "payload.bin", content, {**publishable.model_dump(mode="json"), "media_type": record.media_type})
        published = publishable.model_copy(update={"storage_ref": storage_ref})
        try:
            with self.transaction_context() as session:
                after_register(session, published)
        except Exception as exc:
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            raise RawIngestionError(
                "RAW_REGISTRY_WRITE_FAILED",
                "Raw registry update failed after file publication.",
                retryable=True,
                details={"orphan_relative_path": directory},
                cause=exc,
            ) from exc
        return published

    def publish_quarantine(
        self,
        record: RawIngestionQuarantine,
        content: bytes,
        *,
        after_register: Callable[[object, RawIngestionQuarantine], None],
    ) -> RawIngestionQuarantine:
        if compute_bytes_hash(content) != record.evidence_hash:
            raise RawIngestionError("RAW_QUARANTINE_CONTENT_INVALID", "Quarantine evidence integrity validation failed.")
        directory = f"quarantine/raw/provider_run={record.provider_run_id}/quarantine_id={record.raw_ingestion_quarantine_id}"
        expected_ref = StorageRef(
            storage_backend=StorageBackend.LOCAL_FS,
            storage_namespace=StorageNamespace.APP,
            relative_path=f"{directory}/payload.bin",
            content_hash=compute_bytes_hash(content),
            media_type=record.evidence_storage_ref.media_type,
            size_bytes=len(content),
        )
        publishable = record.model_copy(update={"evidence_storage_ref": expected_ref})
        storage_ref = self._write_directory(
            directory,
            "payload.bin",
            content,
            {**publishable.model_dump(mode="json"), "media_type": record.evidence_storage_ref.media_type},
            allow_internal=True,
        )
        published = publishable.model_copy(update={"evidence_storage_ref": storage_ref})
        try:
            with self.transaction_context() as session:
                after_register(session, published)
        except Exception as exc:
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            raise RawIngestionError(
                "RAW_QUARANTINE_REGISTRY_WRITE_FAILED",
                "Quarantine registry update failed after file publication.",
                retryable=True,
                details={"orphan_relative_path": directory},
                cause=exc,
            ) from exc
        return published


_RAW_ORPHAN_DIRECTORY_PATTERN = re.compile(
    r"^raw/provider=[a-z][a-z0-9_]{1,63}/dataset=[a-z][a-z0-9_]{1,63}/"
    r"year=[0-9]{4}/month=(0[1-9]|1[0-2])/"
    r"provider_run=(prun_[0-9a-f-]{36})/raw_object=(raw_[0-9a-f-]{36})$"
)


@dataclass(frozen=True, slots=True)
class RawIngestionOrphanCandidate:
    raw_object_id: str
    provider_run_id: str
    manifest_relative_path: str
    reason_code: str
    estimated_size_bytes: int


@dataclass(frozen=True, slots=True)
class RawIngestionOrphanScanResult:
    scanned_known_directories: int
    candidates: tuple[RawIngestionOrphanCandidate, ...]
    skipped_invalid_manifests: int
    estimated_recoverable_bytes: int


class RawIngestionOrphanScanner:
    """Read-only detector for post-rename RawObject files absent from the registry."""

    def __init__(
        self,
        runtime_root: Path | str,
        repository: RawIngestionRepository,
        transaction_context: Callable[[], AbstractContextManager[object]],
    ) -> None:
        self.resolver = StorageNamespaceResolver(runtime_root)
        self.repository = repository
        self.transaction_context = transaction_context

    @staticmethod
    def _safe_child_directories(parent: Path, pattern: re.Pattern[str]) -> tuple[Path, ...]:
        try:
            with os.scandir(parent) as entries:
                children = [
                    Path(entry.path)
                    for entry in entries
                    if pattern.fullmatch(entry.name) and entry.is_dir(follow_symlinks=False)
                ]
        except OSError:
            return ()
        return tuple(sorted(children, key=lambda path: path.name))

    @staticmethod
    def _safe_manifest(directory: Path) -> Path | None:
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    if entry.name == "manifest.json" and entry.is_file(follow_symlinks=False):
                        return Path(entry.path)
        except OSError:
            return None
        return None

    def _known_manifests(self) -> tuple[Path, ...]:
        raw_root = self.resolver.ensure_namespace() / "raw"
        if not raw_root.is_dir() or raw_root.is_symlink():
            return ()
        provider_pattern = re.compile(r"^provider=[a-z][a-z0-9_]{1,63}$")
        dataset_pattern = re.compile(r"^dataset=[a-z][a-z0-9_]{1,63}$")
        year_pattern = re.compile(r"^year=[0-9]{4}$")
        month_pattern = re.compile(r"^month=(0[1-9]|1[0-2])$")
        run_pattern = re.compile(r"^provider_run=prun_[0-9a-f-]{36}$")
        raw_object_pattern = re.compile(r"^raw_object=raw_[0-9a-f-]{36}$")
        manifests: list[Path] = []
        for provider_directory in self._safe_child_directories(raw_root, provider_pattern):
            for dataset_directory in self._safe_child_directories(provider_directory, dataset_pattern):
                for year_directory in self._safe_child_directories(dataset_directory, year_pattern):
                    for month_directory in self._safe_child_directories(year_directory, month_pattern):
                        for run_directory in self._safe_child_directories(month_directory, run_pattern):
                            for object_directory in self._safe_child_directories(run_directory, raw_object_pattern):
                                manifest_path = self._safe_manifest(object_directory)
                                if manifest_path is None:
                                    continue
                                relative = object_directory.relative_to(self.resolver.namespace_root()).as_posix()
                                if _RAW_ORPHAN_DIRECTORY_PATTERN.fullmatch(relative):
                                    manifests.append(manifest_path)
        return tuple(sorted(manifests, key=lambda path: path.as_posix()))

    def _load_valid_raw_object(self, manifest_path: Path) -> RawObject:
        namespace_root = self.resolver.namespace_root()
        relative_manifest = manifest_path.relative_to(namespace_root).as_posix()
        self.resolver.resolve(relative_manifest, require_exists=True)
        value = json.loads(manifest_path.read_bytes())
        record = RawObject.model_validate(value)
        match = _RAW_ORPHAN_DIRECTORY_PATTERN.fullmatch(manifest_path.parent.relative_to(namespace_root).as_posix())
        if match is None or match.group(2) != record.provider_run_id or match.group(3) != record.raw_object_id:
            raise ValueError("raw directory does not match manifest")
        payload_path = self.resolver.resolve(record.storage_ref, require_exists=True)
        if payload_path.parent != manifest_path.parent:
            raise ValueError("raw payload path is outside raw directory")
        content = payload_path.read_bytes()
        if len(content) != record.byte_count or compute_bytes_hash(content) != record.raw_content_hash:
            raise ValueError("raw payload integrity mismatch")
        return record

    def dry_run(self) -> RawIngestionOrphanScanResult:
        candidates: list[RawIngestionOrphanCandidate] = []
        skipped = 0
        manifests = self._known_manifests()
        for manifest_path in manifests:
            try:
                record = self._load_valid_raw_object(manifest_path)
            except Exception:
                skipped += 1
                continue
            with self.transaction_context() as session:
                raw_registered = self.repository.get_raw_object(session, record.raw_object_id)
                run_registered = self.repository.get_provider_run(session, record.provider_run_id)
            if raw_registered is not None:
                continue
            candidates.append(
                RawIngestionOrphanCandidate(
                    raw_object_id=record.raw_object_id,
                    provider_run_id=record.provider_run_id,
                    manifest_relative_path=manifest_path.relative_to(self.resolver.namespace_root()).as_posix(),
                    reason_code="RAW_REGISTRY_ENTRY_MISSING" if run_registered is not None else "PROVIDER_RUN_ENTRY_MISSING",
                    estimated_size_bytes=record.byte_count,
                )
            )
        return RawIngestionOrphanScanResult(
            scanned_known_directories=len(manifests),
            candidates=tuple(candidates),
            skipped_invalid_manifests=skipped,
            estimated_recoverable_bytes=sum(candidate.estimated_size_bytes for candidate in candidates),
        )


class RawIngestionTaskWorker:
    """One durable Worker handler for controlled, offline-testable raw ingestion."""

    def __init__(
        self,
        task_control: TaskControlService,
        database: PostgresDatabase,
        publisher: RawObjectPublisher,
        transport: ProviderTransport,
        *,
        repository: RawIngestionRepository | None = None,
        adapter_registry: ControlledProviderAdapterRegistry | None = None,
        rate_limiter: ProviderRateLimiter | PostgresRateLimiter | None = None,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self.task_control = task_control
        self.database = database
        self.publisher = publisher
        self.transport = transport
        self.repository = repository or RawIngestionRepository()
        self.adapter_registry = adapter_registry or ControlledProviderAdapterRegistry()
        self.rate_limiter = rate_limiter or PostgresRateLimiter(database.transaction, clock=clock, repository=self.repository)
        self.clock = clock

    def _configuration(self, requirements: RawIngestionTaskRequirements):
        with self.database.transaction() as session:
            provider = self.repository.get_provider(session, requirements.provider_id)
            dataset = self.repository.get_dataset(session, requirements.dataset_id, requirements.dataset_schema_version)
            policy = self.repository.get_policy(session, requirements.provider_policy_id)
            if provider is None or dataset is None or policy is None:
                raise RawIngestionError("RAW_REGISTRY_CONFIGURATION_INVALID", "Raw ingestion registry configuration is unavailable.")
            if (
                policy.dataset_id != requirements.dataset_id
                or policy.dataset_schema_version != requirements.dataset_schema_version
                or policy.primary_provider_id != requirements.provider_id
            ):
                raise RawIngestionError("RAW_POLICY_BINDING_INVALID", "Raw ingestion policy binding is invalid.")
            capability = self.repository.get_capability(
                session,
                requirements.provider_id,
                requirements.dataset_id,
                requirements.dataset_schema_version,
                requirements.market,
                dataset.frequency,
            )
            raw_schemas = self.repository.list_provider_raw_schemas(
                session, provider.provider_id, provider.adapter_version,
                requirements.dataset_id, requirements.dataset_schema_version,
            )
            if capability is None:
                raise RawIngestionError("RAW_CAPABILITY_UNAVAILABLE", "Provider capability is unavailable.", retryable=True)
            if not raw_schemas:
                raise RawIngestionError("RAW_SCHEMA_REGISTRY_UNAVAILABLE", "Provider raw schema is unavailable.")
        return provider, dataset, policy, capability, raw_schemas

    def _start_run(self, lease: TaskLease, requirements: RawIngestionTaskRequirements, provider: Any, dataset: Any, policy: Any, capability: Any, adapter: ControlledProviderAdapter) -> ProviderRun:
        now = self.clock()
        run = ProviderRun(
            provider_run_id=generate_resource_id(ResourceType.PROVIDER_RUN),
            provider_id=requirements.provider_id,
            actual_upstream=adapter.default_actual_upstream,
            dataset_id=requirements.dataset_id,
            dataset_schema_version=requirements.dataset_schema_version,
            provider_policy_id=policy.provider_policy_id,
            provider_policy_version=policy.policy_version,
            adapter_version=provider.adapter_version,
            capability_market=capability.market,
            capability_frequency=capability.frequency,
            task_id=lease.task.task_id,
            attempt_id=lease.attempt.attempt_id,
            request_fingerprint=compute_content_hash({"provider_id": requirements.provider_id, "dataset_id": requirements.dataset_id, "request": requirements.request}),
            started_at=now,
            raw_object_refs=(),
        )
        with self.database.transaction() as session:
            self.repository.add_provider_run(session, run)
        return run

    def _mark_run_failure(self, run: ProviderRun, *, outcome: ProviderRunOutcome, failure_code: str, exc: Exception | None = None) -> ProviderRun:
        final = run.model_copy(update={
            "finished_at": self.clock(),
            "run_outcome": outcome,
            "failure_code": failure_code,
            "failure_detail_redacted": _error_detail(exc) if exc is not None and outcome is ProviderRunOutcome.FAILED else None,
        })
        with self.database.transaction() as session:
            current = self.repository.get_provider_run(session, run.provider_run_id)
            if current is not None and current.run_outcome is None:
                self.repository.update_provider_run(session, final)
                return final
        return final

    def _cancel(self, lease: TaskLease, run: ProviderRun, code: str) -> None:
        self._mark_run_failure(run, outcome=ProviderRunOutcome.CANCELLED, failure_code=code)
        try:
            self.task_control.acknowledge_cancel(lease.attempt.attempt_id, lease.lease_token)
        except TaskControlError as exc:
            if exc.error_code != "TASK_LEASE_LOST":
                raise

    def execute(self, lease: TaskLease) -> RawIngestionPublishResult:
        if lease.task.task_type != "raw_ingestion":
            raise TaskControlError("TASK_TYPE_UNSUPPORTED", "Worker does not support this task type.", status_code=422)
        self.task_control.start_attempt(lease.attempt.attempt_id, lease.lease_token)
        requirements = RawIngestionTaskRequirements.model_validate(lease.task.requirements)
        provider, dataset, policy, capability, raw_schemas = self._configuration(requirements)
        adapter = self.adapter_registry.resolve(provider.adapter_name)
        run = self._start_run(lease, requirements, provider, dataset, policy, capability, adapter)
        try:
            current = self.task_control.get_task(lease.task.task_id).task
            if current.cancel_requested_at is not None:
                self._cancel(lease, run, "RAW_CANCELLED_BEFORE_FETCH")
                raise TaskControlError("TASK_CANCEL_PENDING", "Cancelled task cannot publish raw data.")
            self.rate_limiter.acquire(requirements.provider_id, requirements.dataset_id, capability.rate_limit_profile, market=requirements.market, frequency=capability.frequency)
            try:
                response = adapter.fetch(
                    self.transport,
                    ProviderFetchRequest(
                        provider_id=requirements.provider_id,
                        dataset_id=requirements.dataset_id,
                        dataset_schema_version=requirements.dataset_schema_version,
                        request=requirements.request,
                    ),
                    timeout_seconds=requirements.timeout_seconds,
                )
            except TimeoutError as exc:
                raise RawIngestionError("RAW_TIMEOUT", "Provider request timed out.", retryable=True, cause=exc) from exc
            actual_upstream = ensure_safe_actual_upstream(response.actual_upstream)
            current = self.task_control.get_task(lease.task.task_id).task
            if current.cancel_requested_at is not None:
                self._cancel(lease, run.model_copy(update={"actual_upstream": actual_upstream}), "RAW_CANCELLED_AFTER_FETCH")
                raise TaskControlError("TASK_CANCEL_PENDING", "Cancelled task cannot publish raw data.")
            observed_schema_hash = _schema_hash(response.raw_schema_fields, response.raw_schema_field_types)
            expected_schema = next((item for item in raw_schemas if item.provider_schema_version == response.provider_schema_version), raw_schemas[-1])
            expected_schema_hash = expected_schema.expected_schema_hash
            classification = classify_raw_schema(expected_schema, response.raw_schema_fields, response.raw_schema_field_types)
            if response.provider_schema_version != expected_schema.provider_schema_version:
                classification = RawSchemaDriftClassification.BREAKING_DRIFT
            now = self.clock()
            bytes_count = len(response.content)
            rows = _row_count(response.content, response.row_count)
            if classification is RawSchemaDriftClassification.MATCHED:
                raw = RawObject(
                    raw_object_id=generate_resource_id(ResourceType.RAW_OBJECT),
                    provider_run_id=run.provider_run_id,
                    provider_id=run.provider_id,
                    actual_upstream=actual_upstream,
                    dataset_id=run.dataset_id,
                    dataset_schema_version=run.dataset_schema_version,
                    request_fingerprint=run.request_fingerprint,
                    storage_ref=StorageRef(storage_backend=StorageBackend.LOCAL_FS, storage_namespace=StorageNamespace.APP, relative_path="raw/pending", content_hash=compute_bytes_hash(response.content), media_type=response.media_type, size_bytes=bytes_count),
                    raw_content_hash=compute_bytes_hash(response.content),
                    media_type=response.media_type,
                    compression=response.compression,
                    observed_at=response.observed_at,
                    ingested_at=now,
                    source_published_at=response.source_published_at,
                    provider_schema_version=response.provider_schema_version,
                    observed_schema_hash=observed_schema_hash or expected_schema_hash,
                    row_count=rows,
                    byte_count=bytes_count,
                    retention_class=RetentionClass.PINNED,
                )
                final = run.model_copy(update={
                    "actual_upstream": actual_upstream,
                    "finished_at": now,
                    "observed_schema_hash": raw.observed_schema_hash,
                    "row_count": rows,
                    "byte_count": bytes_count,
                    "run_outcome": ProviderRunOutcome.SUCCEEDED,
                    "raw_object_refs": (raw.raw_object_id,),
                })
                published = self.publisher.publish_raw(
                    raw,
                    response.content,
                    after_register=lambda session, record: (
                        self.repository.add_raw_object(session, record),
                        self.repository.update_provider_run(session, final),
                        self.task_control.complete_in_session(session, attempt_id=lease.attempt.attempt_id, lease_token=lease.lease_token),
                    ),
                )
                return RawIngestionPublishResult(provider_run=final, raw_object=published)

            reason = {
                RawSchemaDriftClassification.ADDITIVE_DRIFT: "RAW_SCHEMA_ADDITIVE_DRIFT",
                RawSchemaDriftClassification.BREAKING_DRIFT: "RAW_SCHEMA_BREAKING_DRIFT",
                RawSchemaDriftClassification.UNKNOWN_SCHEMA: "RAW_SCHEMA_UNKNOWN",
            }[classification]
            outcome = ProviderRunOutcome.DEGRADED if classification is RawSchemaDriftClassification.ADDITIVE_DRIFT else ProviderRunOutcome.FAILED
            quarantine = RawIngestionQuarantine(
                raw_ingestion_quarantine_id=generate_resource_id(ResourceType.RAW_INGESTION_QUARANTINE),
                provider_run_id=run.provider_run_id,
                classification=classification,
                reason_code=reason,
                observed_schema_hash=observed_schema_hash,
                expected_schema_hash=expected_schema_hash,
                evidence_storage_ref=StorageRef(storage_backend=StorageBackend.LOCAL_FS, storage_namespace=StorageNamespace.APP, relative_path="quarantine/pending", content_hash=compute_bytes_hash(response.content), media_type=response.media_type, size_bytes=bytes_count),
                evidence_hash=compute_bytes_hash(response.content),
                created_at=now,
            )
            final = run.model_copy(update={
                "actual_upstream": actual_upstream,
                "finished_at": now,
                "observed_schema_hash": observed_schema_hash,
                "row_count": rows,
                "byte_count": bytes_count,
                "run_outcome": outcome,
                "failure_code": reason if outcome is ProviderRunOutcome.FAILED else None,
            })
            published_quarantine = self.publisher.publish_quarantine(
                quarantine,
                response.content,
                after_register=lambda session, record: (
                    self.repository.add_quarantine(session, record),
                    self.repository.update_provider_run(session, final),
                    self.task_control.complete_in_session(session, attempt_id=lease.attempt.attempt_id, lease_token=lease.lease_token, degraded=True)
                    if outcome is ProviderRunOutcome.DEGRADED
                    else self.task_control.record_failure_in_session(session, attempt_id=lease.attempt.attempt_id, lease_token=lease.lease_token, failure_code=reason, retryable=False),
                ),
            )
            return RawIngestionPublishResult(provider_run=final, quarantine=published_quarantine)
        except TaskControlError as exc:
            if exc.error_code == "TASK_CANCEL_PENDING":
                raise
            if exc.error_code == "TASK_LEASE_LOST":
                self._mark_run_failure(run, outcome=ProviderRunOutcome.FAILED, failure_code="RAW_TASK_LEASE_LOST", exc=exc)
                raise
            self._mark_run_failure(run, outcome=ProviderRunOutcome.FAILED, failure_code="RAW_TASK_CONTROL_FAILED", exc=exc)
            raise
        except RawIngestionError as exc:
            self._mark_run_failure(run, outcome=ProviderRunOutcome.FAILED, failure_code=exc.error_code, exc=exc)
            try:
                current = self.task_control.get_task(lease.task.task_id).task
                if current.task_state is TaskState.RUNNING and current.cancel_requested_at is not None:
                    self._cancel(lease, run, "RAW_CANCELLED_DURING_FETCH")
                else:
                    self.task_control.record_failure(lease.attempt.attempt_id, lease.lease_token, failure_code=exc.error_code, retryable=exc.retryable)
            except TaskControlError as task_error:
                if task_error.error_code != "TASK_LEASE_LOST":
                    raise
            raise
        except Exception as exc:
            self._mark_run_failure(run, outcome=ProviderRunOutcome.FAILED, failure_code="RAW_INGESTION_FAILED", exc=exc)
            try:
                self.task_control.record_failure(lease.attempt.attempt_id, lease.lease_token, failure_code="RAW_INGESTION_FAILED", retryable=True)
            except TaskControlError as task_error:
                if task_error.error_code != "TASK_LEASE_LOST":
                    raise
            raise


__all__ = [
    "ControlledProviderAdapterRegistry",
    "FakeProviderTransport",
    "ProviderFetchRequest",
    "ProviderFetchResponse",
    "ProviderRateLimiter",
    "PostgresRateLimiter",
    "RawIngestionError",
    "RawIngestionOrphanCandidate",
    "RawIngestionOrphanScanResult",
    "RawIngestionOrphanScanner",
    "RawIngestionTaskWorker",
    "RawObjectPublisher",
    "classify_raw_schema",
]
