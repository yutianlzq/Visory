from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Callable, Mapping

from pydantic import ValidationError

from src.repositories.platform.provider_admission import (
    ProviderAdmissionRepository,
    endpoint_allows_actual_upstream,
)
from src.repositories.platform.raw_ingestion import RawIngestionRepository
from src.schemas.platform.provider_admission import (
    AdapterImplementationFingerprint,
    ProviderEndpointDefinition,
    ProviderEndpointRunBinding,
    SourceAdmissionReceipt,
    compute_actual_origin_hash,
)
from src.schemas.platform.provider_source import (
    ProviderSourceExecutionState,
    ProviderSourceKind,
    ProviderSourceRouteEvidence,
)


class ProviderAdmissionGateError(Exception):
    def __init__(self, error_code: str, public_message: str):
        super().__init__(public_message)
        self.error_code = error_code
        self.public_message = public_message


@dataclass(frozen=True, slots=True)
class AdapterImplementationObservation:
    adapter_bundle_id: str
    adapter_bundle_version: str
    source_repository: str
    source_commit: str
    source_file_path: str
    source_file_blob_sha256: str
    source_file_sha256: str
    function_symbol: str
    visory_wrapper_version: str
    visory_wrapper_hash: str
    mapping_version: str
    mapping_hash: str
    quality_rule_versions: tuple[str, ...]
    quality_rule_hashes: tuple[str, ...]

    @classmethod
    def from_fingerprint(
        cls, fingerprint: AdapterImplementationFingerprint
    ) -> "AdapterImplementationObservation":
        return cls(
            **{
                field: getattr(fingerprint, field)
                for field in cls.__dataclass_fields__
            }
        )


EvidenceHashResolver = Callable[[SourceAdmissionReceipt], Mapping[str, str]]
ImplementationObservationResolver = Callable[
    [AdapterImplementationFingerprint], AdapterImplementationObservation
]


class ProviderEndpointAdmissionVerifier:
    """Revalidates persisted admission evidence at every Formal boundary."""

    def __init__(
        self,
        *,
        repository: ProviderAdmissionRepository | None = None,
        raw_repository: RawIngestionRepository | None = None,
        evidence_hash_resolver: EvidenceHashResolver | None = None,
        implementation_observation_resolver: ImplementationObservationResolver | None = None,
    ) -> None:
        self.repository = repository or ProviderAdmissionRepository()
        self.raw_repository = raw_repository or RawIngestionRepository()
        self.evidence_hash_resolver = evidence_hash_resolver
        self.implementation_observation_resolver = implementation_observation_resolver

    @staticmethod
    def _record_invalid(exc: Exception) -> ProviderAdmissionGateError:
        return ProviderAdmissionGateError(
            "SOURCE_ADMISSION_RECORD_HASH_MISMATCH",
            "Persisted Endpoint Admission evidence is invalid or has drifted.",
        )

    def _load_records(
        self, session: object, provider_run_id: str
    ) -> tuple[
        ProviderEndpointRunBinding,
        ProviderEndpointDefinition,
        AdapterImplementationFingerprint,
        SourceAdmissionReceipt,
    ]:
        try:
            binding = self.repository.get_binding_by_run(session, provider_run_id)
            if binding is None:
                raise ProviderAdmissionGateError(
                    "SOURCE_ADMISSION_BINDING_MISSING",
                    "Formal input requires a ProviderEndpointRunBinding.",
                )
            endpoint = self.repository.get_endpoint(
                session,
                binding.provider_endpoint_id,
                binding.provider_id,
                binding.endpoint_contract_version,
            )
            fingerprint = self.repository.get_fingerprint(
                session, binding.adapter_implementation_fingerprint_id
            )
            receipt = self.repository.get_receipt(
                session, binding.source_admission_receipt_id
            )
        except ProviderAdmissionGateError:
            raise
        except (ValidationError, ValueError, TypeError) as exc:
            raise self._record_invalid(exc) from exc
        if endpoint is None or fingerprint is None or receipt is None:
            raise ProviderAdmissionGateError(
                "SOURCE_ADMISSION_REFERENCE_MISSING",
                "Formal Endpoint Admission references are incomplete.",
            )
        return binding, endpoint, fingerprint, receipt

    @staticmethod
    def _validate_endpoint_binding(
        binding: ProviderEndpointRunBinding,
        endpoint: ProviderEndpointDefinition,
        *,
        cutoff_at: datetime,
        target_market: str,
    ) -> None:
        if (
            endpoint.provider_endpoint_id != binding.provider_endpoint_id
            or endpoint.provider_id != binding.provider_id
            or endpoint.endpoint_contract_version != binding.endpoint_contract_version
            or target_market != binding.market
        ):
            raise ProviderAdmissionGateError(
                "SOURCE_ADMISSION_ENDPOINT_MISMATCH",
                "Provider, Endpoint version, or market does not match the bound run.",
            )
        if cutoff_at < endpoint.effective_from or (
            endpoint.effective_to is not None and cutoff_at >= endpoint.effective_to
        ):
            raise ProviderAdmissionGateError(
                "SOURCE_ADMISSION_ENDPOINT_INACTIVE",
                "Provider Endpoint definition is not effective at the Formal cutoff.",
            )
        dataset_binding = next(
            (
                item
                for item in endpoint.dataset_bindings
                if item.dataset_id == binding.dataset_id
                and item.dataset_schema_version == binding.dataset_schema_version
            ),
            None,
        )
        if dataset_binding is None or target_market not in dataset_binding.market_scope:
            raise ProviderAdmissionGateError(
                "SOURCE_ADMISSION_DATASET_SCOPE_MISMATCH",
                "Endpoint does not admit the bound Dataset, schema, and market.",
            )

    def _validate_run_and_raw(
        self,
        session: object,
        binding: ProviderEndpointRunBinding,
        endpoint: ProviderEndpointDefinition,
    ) -> None:
        run = self.raw_repository.get_provider_run(session, binding.provider_run_id)
        if run is None:
            raise ProviderAdmissionGateError(
                "SOURCE_ADMISSION_RUN_MISSING", "Bound ProviderRun is unavailable."
            )
        if (
            run.provider_id != binding.provider_id
            or run.dataset_id != binding.dataset_id
            or run.dataset_schema_version != binding.dataset_schema_version
            or run.capability_market != binding.market
            or run.request_fingerprint != binding.request_fingerprint
            or run.observed_schema_hash != binding.observed_schema_hash
        ):
            raise ProviderAdmissionGateError(
                "SOURCE_ADMISSION_RUN_CONTRACT_MISMATCH",
                "ProviderRun contract evidence does not match its Endpoint binding.",
            )
        if (
            run.actual_upstream is None
            or compute_actual_origin_hash(run.actual_upstream) != binding.actual_origin_hash
            or not endpoint_allows_actual_upstream(endpoint, run.actual_upstream)
        ):
            raise ProviderAdmissionGateError(
                "SOURCE_ADMISSION_ENDPOINT_MISMATCH",
                "ProviderRun actual origin does not match the admitted Endpoint.",
            )
        if binding.actual_origin_redacted is not None and binding.actual_origin_redacted != run.actual_upstream:
            raise ProviderAdmissionGateError(
                "SOURCE_ADMISSION_ENDPOINT_MISMATCH",
                "ProviderRun redacted origin does not match the bound origin.",
            )
        self._validate_source_route(run)
        if set(run.raw_object_refs) != set(binding.raw_object_refs) or len(
            run.raw_object_refs
        ) != len(binding.raw_object_refs):
            raise ProviderAdmissionGateError(
                "SOURCE_ADMISSION_RAW_LINEAGE_MISMATCH",
                "Endpoint binding omits or duplicates ProviderRun RawObjects.",
            )
        for raw_object_id in binding.raw_object_refs:
            raw = self.raw_repository.get_raw_object(session, raw_object_id)
            if (
                raw is None
                or raw.provider_run_id != run.provider_run_id
                or raw.provider_id != binding.provider_id
                or raw.dataset_id != binding.dataset_id
                or raw.dataset_schema_version != binding.dataset_schema_version
                or raw.request_fingerprint != binding.request_fingerprint
                or raw.observed_schema_hash != binding.observed_schema_hash
                or compute_actual_origin_hash(raw.actual_upstream) != binding.actual_origin_hash
            ):
                raise ProviderAdmissionGateError(
                    "SOURCE_ADMISSION_RAW_LINEAGE_MISMATCH",
                    "RawObject does not belong to the bound ProviderRun and Endpoint contract.",
                )

    @staticmethod
    def _validate_source_route(run: object) -> None:
        evidence = getattr(run, "source_route_evidence", None)
        if evidence is None:
            raise ProviderAdmissionGateError(
                "SOURCE_ADMISSION_SOURCE_ROUTE_MISSING",
                "Formal input requires immutable Provider source-route evidence.",
            )
        try:
            # 不信任 model_copy 或从持久层直接取回的对象；重新核验来源 Hash。
            route = ProviderSourceRouteEvidence.model_validate(evidence.model_dump(mode="python"))
        except (ValidationError, ValueError, TypeError, AttributeError) as exc:
            raise ProviderAdmissionGateError(
                "SOURCE_ADMISSION_SOURCE_ROUTE_INVALID",
                "Provider source-route evidence is invalid or has drifted.",
            ) from exc
        if (
            route.execution_state is not ProviderSourceExecutionState.AVAILABLE
            or route.source_kind is ProviderSourceKind.FIXTURE
        ):
            raise ProviderAdmissionGateError(
                "SOURCE_ADMISSION_SOURCE_ROUTE_UNAVAILABLE",
                "A non-executable or fixture source route cannot admit Formal input.",
            )
        if (
            route.provider_id != run.provider_id
            or route.dataset_id != run.dataset_id
            or route.adapter_version != run.adapter_version
            or route.market != run.capability_market
            or route.actual_upstream != run.actual_upstream
        ):
            raise ProviderAdmissionGateError(
                "SOURCE_ADMISSION_SOURCE_ROUTE_MISMATCH",
                "Provider source route does not match the admitted Run and Endpoint.",
            )

    def _validate_receipt(
        self,
        binding: ProviderEndpointRunBinding,
        endpoint: ProviderEndpointDefinition,
        receipt: SourceAdmissionReceipt,
        *,
        cutoff_at: datetime,
        target_market: str,
        target_date: date,
    ) -> None:
        if (
            receipt.source_admission_receipt_id != binding.source_admission_receipt_id
            or receipt.receipt_hash != binding.receipt_hash
            or receipt.provider_endpoint_id != binding.provider_endpoint_id
            or receipt.provider_id != binding.provider_id
            or receipt.endpoint_contract_version != binding.endpoint_contract_version
            or receipt.dataset_id != binding.dataset_id
            or receipt.dataset_schema_version != binding.dataset_schema_version
            or receipt.license_evidence_hash != endpoint.license_evidence_hash
        ):
            raise ProviderAdmissionGateError(
                "SOURCE_ADMISSION_RECEIPT_MISMATCH",
                "SourceAdmissionReceipt does not match the bound Endpoint and Dataset.",
            )
        if receipt.admission_status == "REVOKED":
            raise ProviderAdmissionGateError(
                "SOURCE_ADMISSION_RECEIPT_REVOKED",
                "SourceAdmissionReceipt has been revoked.",
            )
        if receipt.admission_status != "ACCEPTED":
            raise ProviderAdmissionGateError(
                "SOURCE_ADMISSION_RECEIPT_REJECTED",
                "SourceAdmissionReceipt is not accepted.",
            )
        if receipt.admission_level != "PIT_CERTIFIED":
            raise ProviderAdmissionGateError(
                "SOURCE_ADMISSION_RECEIPT_NOT_PIT_CERTIFIED",
                "Formal input requires an explicit PIT_CERTIFIED receipt.",
            )
        if cutoff_at < receipt.valid_from or (
            receipt.valid_to is not None and cutoff_at >= receipt.valid_to
        ):
            raise ProviderAdmissionGateError(
                "SOURCE_ADMISSION_RECEIPT_EXPIRED",
                "SourceAdmissionReceipt is not valid at the Formal cutoff.",
            )
        if (
            target_market not in receipt.requested_market_scope
            or target_date < receipt.requested_date_from
            or target_date > receipt.requested_date_to
        ):
            raise ProviderAdmissionGateError(
                "SOURCE_ADMISSION_RECEIPT_SCOPE_MISMATCH",
                "SourceAdmissionReceipt does not cover the requested market and date.",
            )
        if self.evidence_hash_resolver is None:
            raise ProviderAdmissionGateError(
                "SOURCE_ADMISSION_EVIDENCE_UNAVAILABLE",
                "Formal input requires current source evidence bytes for hash verification.",
            )
        observed_hashes = dict(self.evidence_hash_resolver(receipt))
        if observed_hashes != receipt.evidence_hashes():
            raise ProviderAdmissionGateError(
                "SOURCE_ADMISSION_EVIDENCE_HASH_MISMATCH",
                "Source admission evidence bytes have drifted.",
            )

    def _validate_implementation(
        self,
        binding: ProviderEndpointRunBinding,
        fingerprint: AdapterImplementationFingerprint,
    ) -> None:
        if (
            fingerprint.adapter_implementation_fingerprint_id
            != binding.adapter_implementation_fingerprint_id
            or fingerprint.provider_endpoint_id != binding.provider_endpoint_id
            or fingerprint.provider_id != binding.provider_id
            or fingerprint.endpoint_contract_version != binding.endpoint_contract_version
            or fingerprint.implementation_fingerprint
            != binding.implementation_fingerprint
        ):
            raise ProviderAdmissionGateError(
                "SOURCE_ADMISSION_IMPLEMENTATION_MISMATCH",
                "AdapterImplementationFingerprint does not match the bound Endpoint.",
            )
        if self.implementation_observation_resolver is None:
            raise ProviderAdmissionGateError(
                "SOURCE_ADMISSION_IMPLEMENTATION_UNAVAILABLE",
                "Formal input requires current adapter implementation evidence.",
            )
        observed = self.implementation_observation_resolver(fingerprint)
        expected = AdapterImplementationObservation.from_fingerprint(fingerprint)
        if observed != expected:
            raise ProviderAdmissionGateError(
                "SOURCE_ADMISSION_IMPLEMENTATION_MISMATCH",
                "Adapter commit, file bytes, symbol, wrapper, Mapping, or quality rules have drifted.",
            )

    def verify_formal_run(
        self,
        session: object,
        provider_run_id: str,
        *,
        target_market: str,
        target_date: date,
        cutoff_at: datetime,
    ) -> ProviderEndpointRunBinding:
        binding, endpoint, fingerprint, receipt = self._load_records(
            session, provider_run_id
        )
        self._validate_endpoint_binding(
            binding, endpoint, cutoff_at=cutoff_at, target_market=target_market
        )
        self._validate_run_and_raw(session, binding, endpoint)
        self._validate_receipt(
            binding,
            endpoint,
            receipt,
            cutoff_at=cutoff_at,
            target_market=target_market,
            target_date=target_date,
        )
        self._validate_implementation(binding, fingerprint)
        return binding


class ProviderAdmissionService:
    """Publishes one immutable admission package in a single database transaction."""

    def __init__(self, database: object, repository: ProviderAdmissionRepository | None = None) -> None:
        self.database = database
        self.repository = repository or ProviderAdmissionRepository()

    def _ensure_endpoint(
        self, session: object, record: ProviderEndpointDefinition
    ) -> None:
        existing = self.repository.get_endpoint(
            session,
            record.provider_endpoint_id,
            record.provider_id,
            record.endpoint_contract_version,
        )
        if existing is None:
            self.repository.add_endpoint(session, record)
        elif existing != record:
            raise ValueError(
                "ProviderEndpointDefinition identity conflicts with an immutable record"
            )

    def _ensure_fingerprint(
        self, session: object, record: AdapterImplementationFingerprint
    ) -> None:
        existing = self.repository.get_fingerprint(
            session, record.adapter_implementation_fingerprint_id
        )
        if existing is None:
            self.repository.add_fingerprint(session, record)
        elif existing != record:
            raise ValueError(
                "AdapterImplementationFingerprint identity conflicts with an immutable record"
            )

    def _ensure_receipt(
        self, session: object, record: SourceAdmissionReceipt
    ) -> None:
        existing = self.repository.get_receipt(
            session, record.source_admission_receipt_id
        )
        if existing is None:
            self.repository.add_receipt(session, record)
        elif existing != record:
            raise ValueError(
                "SourceAdmissionReceipt identity conflicts with an immutable record"
            )

    def _ensure_binding(
        self, session: object, record: ProviderEndpointRunBinding
    ) -> None:
        existing_by_id = self.repository.get_binding(
            session, record.provider_endpoint_run_binding_id
        )
        existing_by_run = self.repository.get_binding_by_run(
            session, record.provider_run_id
        )
        existing = existing_by_id or existing_by_run
        if existing is None:
            self.repository.add_binding(session, record)
        elif existing != record or (
            existing_by_id is not None
            and existing_by_run is not None
            and existing_by_id != existing_by_run
        ):
            raise ValueError(
                "ProviderEndpointRunBinding identity conflicts with an immutable record"
            )

    def publish_package(
        self,
        endpoint: ProviderEndpointDefinition,
        fingerprint: AdapterImplementationFingerprint,
        receipt: SourceAdmissionReceipt,
        binding: ProviderEndpointRunBinding,
    ) -> ProviderEndpointRunBinding:
        with self.database.transaction() as session:
            self.repository.lock_publication_tables(session)
            self._ensure_endpoint(session, endpoint)
            self._ensure_fingerprint(session, fingerprint)
            self._ensure_receipt(session, receipt)
            self._ensure_binding(session, binding)
        return binding


__all__ = [
    "AdapterImplementationObservation",
    "ProviderAdmissionGateError",
    "ProviderAdmissionService",
    "ProviderEndpointAdmissionVerifier",
]
