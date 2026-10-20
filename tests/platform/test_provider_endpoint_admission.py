from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from src.schemas.platform import (
    EndpointDatasetBinding,
    ProviderRun,
    ResourceType,
    build_adapter_implementation_fingerprint,
    build_provider_endpoint_definition,
    build_provider_endpoint_run_binding,
    build_source_admission_receipt,
    compute_content_hash,
    generate_resource_id,
)
from src.services.platform.provider_admission import (
    AdapterImplementationObservation,
    ProviderAdmissionGateError,
    ProviderEndpointAdmissionVerifier,
)


from tests.platform._provider_admission_support import synthetic_source_route


NOW = datetime(2026, 1, 10, tzinfo=timezone.utc)
RUN_ID = "prun_019dbd74-2a00-7000-8000-000000000001"
RAW_ID = "raw_019dbd74-2a00-7000-8000-000000000001"


def _hash(label: str) -> str:
    return compute_content_hash({"evidence": label})


def _package(*, admission_level: str = "PIT_CERTIFIED", admission_status: str = "ACCEPTED"):
    endpoint = build_provider_endpoint_definition(
        provider_endpoint_id="a_stock_data_bar_daily",
        provider_id="a_stock_data",
        endpoint_contract_version="1.0.0",
        request_method="GET",
        redacted_origin_allowlist=("https://api.example.test",),
        path_family="/v1/bars/*",
        request_schema_hash=_hash("request-schema"),
        response_schema_hash=_hash("response-schema"),
        dataset_bindings=(
            EndpointDatasetBinding(
                dataset_id="bar_1d_raw",
                dataset_schema_version="1.0.0",
                market_scope=("CN",),
            ),
        ),
        market_scope=("CN",),
        pagination_semantics="cursor token is explicit",
        total_semantics="reported total is authoritative",
        terminal_semantics="missing next cursor terminates pagination",
        valid_zero_row_semantics="zero rows require terminal coverage evidence",
        no_data_semantics="no data is distinct from provider failure",
        error_semantics="errors are explicit",
        revision_semantics="stable identity and revision are required",
        cancellation_semantics="cancelled revisions remain explicit",
        source_publication_semantics="source publication time is preserved",
        rate_limit_semantics="fixed provider request window",
        retry_semantics="only bounded retryable errors are retried",
        license_semantics="pinned license evidence controls use",
        license_evidence_hash=_hash("license"),
        effective_from=NOW - timedelta(days=30),
    )
    fingerprint = build_adapter_implementation_fingerprint(
        adapter_implementation_fingerprint_id="a_stock_data_bar_impl_v1",
        provider_endpoint_id=endpoint.provider_endpoint_id,
        provider_id=endpoint.provider_id,
        endpoint_contract_version=endpoint.endpoint_contract_version,
        adapter_bundle_id="a_stock_data",
        adapter_bundle_version="1.0.0",
        source_repository="https://github.com/example/a-stock-data.git",
        source_commit="a" * 40,
        source_file_path="src/bar.py",
        source_file_blob_sha256=_hash("blob"),
        source_file_sha256=_hash("file"),
        function_symbol="bar.fetch",
        visory_wrapper_version="1.0.0",
        visory_wrapper_hash=_hash("wrapper"),
        mapping_version="1.0.0",
        mapping_hash=_hash("mapping"),
        quality_rule_versions=("1.0.0",),
        quality_rule_hashes=(_hash("quality"),),
        created_at=NOW - timedelta(days=2),
    )
    reason_codes = () if admission_status == "ACCEPTED" else ("SOURCE_REVOKED",)
    receipt = build_source_admission_receipt(
        source_admission_receipt_id="receipt_bar_cn_2026",
        provider_endpoint_id=endpoint.provider_endpoint_id,
        provider_id=endpoint.provider_id,
        endpoint_contract_version=endpoint.endpoint_contract_version,
        dataset_id="bar_1d_raw",
        dataset_schema_version="1.0.0",
        requested_market_scope=("CN",),
        requested_date_from=date(2026, 1, 1),
        requested_date_to=date(2026, 12, 31),
        source_contract_hash=_hash("source-contract"),
        sample_manifest_hash=_hash("sample-manifest"),
        observation_log_hash=_hash("observation-log"),
        coverage_manifest_hash=_hash("coverage-manifest"),
        revision_chain_hash=_hash("revision-chain"),
        quality_report_hash=_hash("quality-report"),
        license_evidence_hash=_hash("license"),
        expected_unit_and_identity_hash=_hash("unit-identity"),
        coverage_summary={"complete": True, "terminal_pages_verified": True},
        admission_level=admission_level,
        admission_status=admission_status,
        reason_codes=reason_codes,
        issued_at=NOW - timedelta(days=2),
        valid_from=NOW - timedelta(days=1),
    )
    binding = build_provider_endpoint_run_binding(
        provider_endpoint_run_binding_id="binding_bar_cn_2026",
        provider_run_id=RUN_ID,
        raw_object_refs=(RAW_ID,),
        provider_id=endpoint.provider_id,
        provider_endpoint_id=endpoint.provider_endpoint_id,
        endpoint_contract_version=endpoint.endpoint_contract_version,
        adapter_implementation_fingerprint_id=fingerprint.adapter_implementation_fingerprint_id,
        implementation_fingerprint=fingerprint.implementation_fingerprint,
        source_admission_receipt_id=receipt.source_admission_receipt_id,
        receipt_hash=receipt.receipt_hash,
        dataset_id="bar_1d_raw",
        dataset_schema_version="1.0.0",
        market="CN",
        request_fingerprint=_hash("request"),
        observed_schema_hash=_hash("schema"),
        actual_origin_redacted="https://api.example.test/v1/bars/daily",
        created_at=NOW,
    )
    return endpoint, fingerprint, receipt, binding


def _replace_receipt(receipt, **updates):
    payload = receipt.model_dump(mode="python", exclude={"receipt_hash"}) | updates
    return build_source_admission_receipt(**payload)


def _replace_binding(binding, **updates):
    payload = binding.model_dump(mode="python", exclude={"binding_hash"}) | updates
    return build_provider_endpoint_run_binding(**payload)


class _Repository:
    def __init__(self, endpoint, fingerprint, receipt, binding):
        self.endpoint = endpoint
        self.fingerprint = fingerprint
        self.receipt = receipt
        self.binding = binding

    def get_binding_by_run(self, _session, _provider_run_id):
        return self.binding

    def get_endpoint(self, _session, *_key):
        return self.endpoint

    def get_fingerprint(self, _session, _fingerprint_id):
        return self.fingerprint

    def get_receipt(self, _session, _receipt_id):
        return self.receipt


class _RawRepository:
    def __init__(self, binding):
        self.run = SimpleNamespace(
            provider_run_id=binding.provider_run_id,
            provider_id=binding.provider_id,
            dataset_id=binding.dataset_id,
            dataset_schema_version=binding.dataset_schema_version,
            capability_market=binding.market,
            adapter_version="1.0.0",
            request_fingerprint=binding.request_fingerprint,
            observed_schema_hash=binding.observed_schema_hash,
            actual_upstream=binding.actual_origin_redacted,
            raw_object_refs=binding.raw_object_refs,
        )
        self.run.source_route_evidence = synthetic_source_route(self.run)
        self.raw = SimpleNamespace(
            raw_object_id=binding.raw_object_refs[0],
            provider_run_id=binding.provider_run_id,
            provider_id=binding.provider_id,
            dataset_id=binding.dataset_id,
            dataset_schema_version=binding.dataset_schema_version,
            request_fingerprint=binding.request_fingerprint,
            observed_schema_hash=binding.observed_schema_hash,
            actual_upstream=binding.actual_origin_redacted,
        )

    def get_provider_run(self, _session, _provider_run_id):
        return self.run

    def get_raw_object(self, _session, _raw_object_id):
        return self.raw


def _verifier(endpoint, fingerprint, receipt, binding, *, evidence=None, observation=None):
    raw_binding = binding if binding is not None else _package()[3]
    return ProviderEndpointAdmissionVerifier(
        repository=_Repository(endpoint, fingerprint, receipt, binding),
        raw_repository=_RawRepository(raw_binding),
        evidence_hash_resolver=evidence or (lambda item: item.evidence_hashes()),
        implementation_observation_resolver=observation
        or AdapterImplementationObservation.from_fingerprint,
    )


def _assert_rejected(verifier, code: str, *, market: str = "CN", target_date=date(2026, 1, 10)):
    with pytest.raises(ProviderAdmissionGateError) as captured:
        verifier.verify_formal_run(
            object(), RUN_ID, target_market=market, target_date=target_date, cutoff_at=NOW
        )
    assert captured.value.error_code == code


def test_four_admission_models_are_deterministic_immutable_and_strict() -> None:
    first = _package()
    second = _package()
    assert first == second
    assert first[0].definition_hash == second[0].definition_hash
    assert first[1].implementation_fingerprint == second[1].implementation_fingerprint
    assert first[2].receipt_hash == second[2].receipt_hash
    assert first[3].binding_hash == second[3].binding_hash
    with pytest.raises(ValidationError):
        type(first[0]).model_validate(first[0].model_dump() | {"unexpected": True})
    with pytest.raises(ValidationError, match="definition_hash"):
        type(first[0]).model_validate(
            first[0].model_dump() | {"definition_hash": "sha256:" + "0" * 64}
        )
    with pytest.raises(ValidationError, match="frozen"):
        first[0].provider_id = "financial_api"


def test_receipt_builder_never_defaults_to_pit_certified() -> None:
    receipt = _package()[2]
    payload = receipt.model_dump(mode="python", exclude={"receipt_hash", "admission_level"})
    with pytest.raises(ValueError, match="admission_level must be explicit"):
        build_source_admission_receipt(**payload)


def test_formal_verifier_accepts_only_complete_current_evidence() -> None:
    endpoint, fingerprint, receipt, binding = _package()
    assert (
        _verifier(endpoint, fingerprint, receipt, binding).verify_formal_run(
            object(), RUN_ID, target_market="CN", target_date=date(2026, 1, 10), cutoff_at=NOW
        )
        == binding
    )


@pytest.mark.parametrize(
    "updates",
    (
        {"adapter_repository": "https://example.test/different-adapter.git"},
        {"adapter_commit": "b" * 40},
        {"adapter_entrypoint": "bar.other_fetch"},
        {"adapter_name": "different_bundle"},
        {"adapter_release": "2.0.0"},
        {"adapter_version": "2.0.0"},
    ),
    ids=("repository", "commit", "entrypoint", "bundle", "release", "wrapper"),
)
def test_formal_verifier_rejects_resealed_route_implementation_mismatch(updates) -> None:
    verifier = _verifier(*_package())
    original = verifier.raw_repository.run
    route = synthetic_source_route(original, **updates)
    # 使用完整且经 JSON 往返校验的 Run，错配对象自身的 Hash/契约仍然有效。
    run = ProviderRun(
        **(
            vars(original)
            | {
                "adapter_version": route.adapter_version,
                "source_route_evidence": route,
                "provider_policy_id": "bar_1d_raw_v1",
                "provider_policy_version": "1.0.0",
                "capability_frequency": "daily",
                "task_id": generate_resource_id(ResourceType.TASK),
                "attempt_id": generate_resource_id(ResourceType.ATTEMPT),
                "started_at": NOW - timedelta(minutes=5),
                "finished_at": NOW,
                "run_outcome": "SUCCEEDED",
            }
        )
    )
    verifier.raw_repository.run = ProviderRun.model_validate_json(run.model_dump_json())

    _assert_rejected(
        verifier, "SOURCE_ADMISSION_SOURCE_ROUTE_IMPLEMENTATION_MISMATCH"
    )


def test_legacy_run_without_binding_is_rejected() -> None:
    endpoint, fingerprint, receipt, _ = _package()
    _assert_rejected(
        _verifier(endpoint, fingerprint, receipt, None),
        "SOURCE_ADMISSION_BINDING_MISSING",
    )


@pytest.mark.parametrize(
    "level", ["CURRENT_SNAPSHOT", "HISTORICAL_SERIES", "VERSIONED_ARCHIVE"]
)
def test_non_pit_admission_levels_never_unlock_formal(level: str) -> None:
    endpoint, fingerprint, receipt, binding = _package(admission_level=level)
    _assert_rejected(
        _verifier(endpoint, fingerprint, receipt, binding),
        "SOURCE_ADMISSION_RECEIPT_NOT_PIT_CERTIFIED",
    )


def test_revoked_expired_and_out_of_scope_receipts_are_rejected() -> None:
    endpoint, fingerprint, receipt, binding = _package(admission_status="REVOKED")
    _assert_rejected(
        _verifier(endpoint, fingerprint, receipt, binding),
        "SOURCE_ADMISSION_RECEIPT_REVOKED",
    )

    endpoint, fingerprint, receipt, binding = _package()
    expired = _replace_receipt(receipt, valid_to=NOW - timedelta(hours=1))
    binding = _replace_binding(binding, receipt_hash=expired.receipt_hash)
    _assert_rejected(
        _verifier(endpoint, fingerprint, expired, binding),
        "SOURCE_ADMISSION_RECEIPT_EXPIRED",
    )
    _assert_rejected(
        _verifier(endpoint, fingerprint, receipt, _package()[3]),
        "SOURCE_ADMISSION_RECEIPT_SCOPE_MISMATCH",
        target_date=date(2027, 1, 1),
    )


def test_evidence_and_implementation_drift_are_rejected() -> None:
    endpoint, fingerprint, receipt, binding = _package()
    observed_hashes = receipt.evidence_hashes() | {"sample_manifest_hash": _hash("drift")}
    _assert_rejected(
        _verifier(
            endpoint,
            fingerprint,
            receipt,
            binding,
            evidence=lambda _receipt: observed_hashes,
        ),
        "SOURCE_ADMISSION_EVIDENCE_HASH_MISMATCH",
    )
    observation = replace(
        AdapterImplementationObservation.from_fingerprint(fingerprint),
        source_commit="b" * 40,
    )
    _assert_rejected(
        _verifier(
            endpoint,
            fingerprint,
            receipt,
            binding,
            observation=lambda _fingerprint: observation,
        ),
        "SOURCE_ADMISSION_IMPLEMENTATION_MISMATCH",
    )


def test_run_raw_request_schema_and_source_switch_mismatches_fail_closed() -> None:
    endpoint, fingerprint, receipt, binding = _package()
    verifier = _verifier(endpoint, fingerprint, receipt, binding)
    verifier.raw_repository.raw.provider_run_id = "prun_019dbd74-2a00-7000-8000-000000000002"
    _assert_rejected(verifier, "SOURCE_ADMISSION_RAW_LINEAGE_MISMATCH")

    verifier = _verifier(endpoint, fingerprint, receipt, binding)
    verifier.raw_repository.run.request_fingerprint = _hash("changed-request")
    _assert_rejected(verifier, "SOURCE_ADMISSION_RUN_CONTRACT_MISMATCH")

    verifier = _verifier(endpoint, fingerprint, receipt, binding)
    verifier.raw_repository.run.actual_upstream = "https://other.example.test/v1/bars/daily"
    _assert_rejected(verifier, "SOURCE_ADMISSION_ENDPOINT_MISMATCH")

    for actual_upstream in (
        "https://api.example.test/v1/bars/../admin",
        "https://api.example.test/v1/bars/%2e%2e/admin",
        "https://api.example.test/v1/bars/%2525252e%2525252e/admin",
    ):
        traversing_binding = build_provider_endpoint_run_binding(
            **(
                binding.model_dump(
                    mode="python", exclude={"actual_origin_hash", "binding_hash"}
                )
                | {"actual_origin_redacted": actual_upstream}
            )
        )
        _assert_rejected(
            _verifier(endpoint, fingerprint, receipt, traversing_binding),
            "SOURCE_ADMISSION_ENDPOINT_MISMATCH",
        )


def test_endpoint_version_mismatch_fails_closed() -> None:
    endpoint, fingerprint, receipt, binding = _package()
    other = build_provider_endpoint_definition(
        **(
            endpoint.model_dump(mode="python", exclude={"definition_hash"})
            | {"provider_endpoint_id": "a_stock_data_other_endpoint"}
        )
    )
    _assert_rejected(
        _verifier(other, fingerprint, receipt, binding),
        "SOURCE_ADMISSION_ENDPOINT_MISMATCH",
    )
