from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Iterable

from src.schemas.platform import (
    EndpointDatasetBinding,
    build_adapter_implementation_fingerprint,
    build_provider_endpoint_definition,
    build_provider_endpoint_run_binding,
    build_source_admission_receipt,
    compute_content_hash,
    build_provider_source_route_evidence,
)
from src.services.platform.provider_admission import (
    AdapterImplementationObservation,
    ProviderEndpointAdmissionVerifier,
)


def _hash(label: str) -> str:
    return compute_content_hash({"synthetic_admission_evidence": label})


def synthetic_source_route(run, *, state="AVAILABLE", kind="HTTP", **updates):
    """Synthetic route evidence only; never an admission claim for a real Endpoint."""
    payload = dict(
        source_route_id="synthetic_admission_" + run.dataset_id,
        provider_id=run.provider_id,
        dataset_id=run.dataset_id,
        adapter_name="a_stock_data",
        adapter_version=getattr(run, "adapter_version", "1.0.0"),
        adapter_repository="https://github.com/example/a-stock-data.git",
        adapter_release="1.0.0",
        adapter_commit="a" * 40,
        adapter_blob="b" * 40,
        adapter_entrypoint="bar.fetch",
        actual_upstream=run.actual_upstream,
        source_kind=kind,
        market=run.capability_market,
        documented_history_start=None,
        coverage_evidence_state="PROVEN",
        pit_evidence_state="PROVEN",
        pagination_evidence_state="NOT_APPLICABLE",
        revision_evidence_state="NOT_APPLICABLE",
        execution_state=state,
        unavailable_reason_code=None if state == "AVAILABLE" else "SYNTHETIC_ROUTE_BLOCKED",
        license_id="TEST-ONLY",
        license_blob="c" * 40,
    )
    return build_provider_source_route_evidence(**(payload | updates))



class SyntheticProviderAdmissionRepository:
    def __init__(self) -> None:
        self.endpoints = {}
        self.fingerprints = {}
        self.receipts = {}
        self.bindings_by_run = {}

    def get_endpoint(
        self,
        _session,
        provider_endpoint_id: str,
        provider_id: str,
        endpoint_contract_version: str,
    ):
        return self.endpoints.get(
            (provider_endpoint_id, provider_id, endpoint_contract_version)
        )

    def get_fingerprint(self, _session, fingerprint_id: str):
        return self.fingerprints.get(fingerprint_id)

    def get_receipt(self, _session, receipt_id: str):
        return self.receipts.get(receipt_id)

    def get_binding_by_run(self, _session, provider_run_id: str):
        return self.bindings_by_run.get(provider_run_id)


def synthetic_admission_verifier(
    *,
    runs: Iterable[object],
    raw_repository: object,
    cutoff_at: datetime,
    admission_level: str,
) -> ProviderEndpointAdmissionVerifier:
    repository = SyntheticProviderAdmissionRepository()
    for index, run in enumerate(runs, start=1):
        suffix = f"{index}_{run.dataset_id}"
        endpoint = build_provider_endpoint_definition(
            provider_endpoint_id=f"synthetic_endpoint_{suffix}",
            provider_id=run.provider_id,
            endpoint_contract_version="1.0.0",
            request_method="GET",
            redacted_origin_allowlist=(run.actual_upstream,),
            path_family="/",
            request_schema_hash=_hash(f"request-schema-{suffix}"),
            response_schema_hash=_hash(f"response-schema-{suffix}"),
            dataset_bindings=(
                EndpointDatasetBinding(
                    dataset_id=run.dataset_id,
                    dataset_schema_version=run.dataset_schema_version,
                    market_scope=(run.capability_market,),
                ),
            ),
            market_scope=(run.capability_market,),
            pagination_semantics="synthetic tests pin one terminal response",
            total_semantics="synthetic tests pin the declared row count",
            terminal_semantics="synthetic tests terminate after one response",
            valid_zero_row_semantics="synthetic tests require explicit zero-row evidence",
            no_data_semantics="synthetic tests distinguish no data from failure",
            error_semantics="synthetic tests surface provider errors",
            revision_semantics="synthetic tests pin the revision chain",
            cancellation_semantics="synthetic tests preserve cancellation evidence",
            source_publication_semantics="synthetic tests preserve publication time",
            rate_limit_semantics="synthetic tests do not issue network requests",
            retry_semantics="synthetic tests do not retry network requests",
            license_semantics="synthetic tests pin isolated license evidence",
            license_evidence_hash=_hash(f"license-{suffix}"),
            effective_from=cutoff_at - timedelta(days=2),
        )
        fingerprint = build_adapter_implementation_fingerprint(
            adapter_implementation_fingerprint_id=f"synthetic_fingerprint_{suffix}",
            provider_endpoint_id=endpoint.provider_endpoint_id,
            provider_id=run.provider_id,
            endpoint_contract_version=endpoint.endpoint_contract_version,
            adapter_bundle_id=f"synthetic_bundle_{index}",
            adapter_bundle_version="1.0.0",
            source_repository="https://example.test/synthetic/adapter.git",
            source_commit=f"{index:x}".rjust(40, "0"),
            source_file_path=f"synthetic/{run.dataset_id}.py",
            source_file_blob_sha256=_hash(f"blob-{suffix}"),
            source_file_sha256=_hash(f"file-{suffix}"),
            function_symbol=f"synthetic.{run.dataset_id}.fetch",
            visory_wrapper_version="1.0.0",
            visory_wrapper_hash=_hash(f"wrapper-{suffix}"),
            mapping_version="1.0.0",
            mapping_hash=_hash(f"mapping-{suffix}"),
            quality_rule_versions=("1.0.0",),
            quality_rule_hashes=(_hash(f"quality-{suffix}"),),
            created_at=cutoff_at - timedelta(days=1),
        )
        receipt = build_source_admission_receipt(
            source_admission_receipt_id=f"synthetic_receipt_{suffix}",
            provider_endpoint_id=endpoint.provider_endpoint_id,
            provider_id=run.provider_id,
            endpoint_contract_version=endpoint.endpoint_contract_version,
            dataset_id=run.dataset_id,
            dataset_schema_version=run.dataset_schema_version,
            requested_market_scope=(run.capability_market,),
            requested_date_from=date(2000, 1, 1),
            requested_date_to=date(2100, 12, 31),
            source_contract_hash=_hash(f"source-contract-{suffix}"),
            sample_manifest_hash=_hash(f"sample-manifest-{suffix}"),
            observation_log_hash=_hash(f"observation-log-{suffix}"),
            coverage_manifest_hash=_hash(f"coverage-manifest-{suffix}"),
            revision_chain_hash=_hash(f"revision-chain-{suffix}"),
            quality_report_hash=_hash(f"quality-report-{suffix}"),
            license_evidence_hash=endpoint.license_evidence_hash,
            expected_unit_and_identity_hash=_hash(f"unit-identity-{suffix}"),
            coverage_summary={"synthetic": True, "complete": True},
            admission_level=admission_level,
            admission_status="ACCEPTED",
            issued_at=cutoff_at - timedelta(days=2),
            valid_from=cutoff_at - timedelta(days=1),
        )
        binding = build_provider_endpoint_run_binding(
            provider_endpoint_run_binding_id=f"synthetic_binding_{suffix}",
            provider_run_id=run.provider_run_id,
            raw_object_refs=tuple(run.raw_object_refs),
            provider_id=run.provider_id,
            provider_endpoint_id=endpoint.provider_endpoint_id,
            endpoint_contract_version=endpoint.endpoint_contract_version,
            adapter_implementation_fingerprint_id=(
                fingerprint.adapter_implementation_fingerprint_id
            ),
            implementation_fingerprint=fingerprint.implementation_fingerprint,
            source_admission_receipt_id=receipt.source_admission_receipt_id,
            receipt_hash=receipt.receipt_hash,
            dataset_id=run.dataset_id,
            dataset_schema_version=run.dataset_schema_version,
            market=run.capability_market,
            request_fingerprint=run.request_fingerprint,
            observed_schema_hash=run.observed_schema_hash,
            actual_origin_redacted=run.actual_upstream,
            created_at=cutoff_at,
        )
        repository.endpoints[
            (
                endpoint.provider_endpoint_id,
                endpoint.provider_id,
                endpoint.endpoint_contract_version,
            )
        ] = endpoint
        repository.fingerprints[
            fingerprint.adapter_implementation_fingerprint_id
        ] = fingerprint
        repository.receipts[receipt.source_admission_receipt_id] = receipt
        repository.bindings_by_run[run.provider_run_id] = binding

    return ProviderEndpointAdmissionVerifier(
        repository=repository,
        raw_repository=raw_repository,
        evidence_hash_resolver=lambda receipt: receipt.evidence_hashes(),
        implementation_observation_resolver=(
            AdapterImplementationObservation.from_fingerprint
        ),
    )
