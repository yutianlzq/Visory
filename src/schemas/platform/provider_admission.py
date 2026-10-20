from __future__ import annotations

import re
from datetime import date
from pathlib import PurePosixPath
from typing import Annotated, Any
from urllib.parse import urlsplit, urlunsplit

from pydantic import AwareDatetime, Field, field_validator, model_validator

from .base import PlatformContractModel
from .hashing import compute_content_hash
from .raw_ingestion import ensure_safe_actual_upstream


_HASH = r"^sha256:[0-9a-f]{64}$"
_SEMVER = r"^[0-9]+\.[0-9]+\.[0-9]+$"
_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]{1,127}$")
_MARKET = re.compile(r"^[A-Z][A-Z0-9_]{1,31}$")
_REASON_CODE = re.compile(r"^[A-Z][A-Z0-9_]{2,63}$")
_FUNCTION_SYMBOL = re.compile(r"^[A-Za-z_][A-Za-z0-9_.:]{0,254}$")
_COMMIT = re.compile(r"^[0-9a-f]{40,64}$")
_REQUEST_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE"})
_ADMISSION_LEVELS = frozenset(
    {"CURRENT_SNAPSHOT", "HISTORICAL_SERIES", "VERSIONED_ARCHIVE", "PIT_CERTIFIED"}
)
_ADMISSION_STATUSES = frozenset({"ACCEPTED", "REJECTED", "REVOKED"})


def _identifier(value: str, field_name: str) -> str:
    if not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"{field_name} must be a normalized lowercase identifier")
    return value


def _market(value: str) -> str:
    if not _MARKET.fullmatch(value):
        raise ValueError("market scope values must be normalized uppercase identifiers")
    return value


def _sorted_unique(values: tuple[str, ...], field_name: str) -> tuple[str, ...]:
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} cannot contain duplicates")
    return tuple(sorted(values))


def _canonical_origin(value: str) -> str:
    safe = ensure_safe_actual_upstream(value)
    parsed = urlsplit(safe)
    if parsed.scheme:
        if parsed.path not in ("", "/"):
            raise ValueError("redacted_origin_allowlist entries must not include endpoint paths")
        return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), "", "", ""))
    return safe.lower()


def _source_repository(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme not in {"https", "ssh"} or not parsed.hostname:
        raise ValueError("source_repository must be an https or ssh repository URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("source_repository cannot contain credentials, query, or fragment")
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path.rstrip("/"), "", ""))


def _source_file_path(value: str) -> str:
    if not value or "\\" in value:
        raise ValueError("source_file_path must be a relative POSIX path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("source_file_path must not be absolute or traverse directories")
    return path.as_posix()


def _path_family(value: str) -> str:
    if not value.startswith("/") or "?" in value or "#" in value or "\\" in value:
        raise ValueError("path_family must be a redacted absolute URL path pattern")
    if ".." in PurePosixPath(value.replace("*", "segment")).parts:
        raise ValueError("path_family must not traverse directories")
    if value.count("*") > 1 or ("*" in value and not value.endswith("*")):
        raise ValueError("path_family supports at most one trailing wildcard")
    return value


def _hash_payload(value: PlatformContractModel, hash_field: str) -> dict[str, Any]:
    return value.model_dump(mode="python", exclude={hash_field})


class EndpointDatasetBinding(PlatformContractModel):
    dataset_id: str
    dataset_schema_version: Annotated[str, Field(pattern=_SEMVER)]
    market_scope: tuple[str, ...]

    @field_validator("dataset_id")
    @classmethod
    def validate_dataset_id(cls, value: str) -> str:
        return _identifier(value, "dataset_id")

    @field_validator("market_scope")
    @classmethod
    def validate_market_scope(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value:
            raise ValueError("market_scope must not be empty")
        return _sorted_unique(tuple(_market(item) for item in value), "market_scope")


class ProviderEndpointDefinition(PlatformContractModel):
    provider_endpoint_id: str
    provider_id: str
    endpoint_contract_version: Annotated[str, Field(pattern=_SEMVER)]
    request_method: str
    redacted_origin_allowlist: tuple[str, ...]
    path_family: str
    request_schema_hash: Annotated[str, Field(pattern=_HASH)]
    response_schema_hash: Annotated[str, Field(pattern=_HASH)]
    dataset_bindings: tuple[EndpointDatasetBinding, ...]
    market_scope: tuple[str, ...]
    pagination_semantics: Annotated[str, Field(min_length=1, max_length=512)]
    total_semantics: Annotated[str, Field(min_length=1, max_length=512)]
    terminal_semantics: Annotated[str, Field(min_length=1, max_length=512)]
    valid_zero_row_semantics: Annotated[str, Field(min_length=1, max_length=512)]
    no_data_semantics: Annotated[str, Field(min_length=1, max_length=512)]
    error_semantics: Annotated[str, Field(min_length=1, max_length=512)]
    revision_semantics: Annotated[str, Field(min_length=1, max_length=512)]
    cancellation_semantics: Annotated[str, Field(min_length=1, max_length=512)]
    source_publication_semantics: Annotated[str, Field(min_length=1, max_length=512)]
    rate_limit_semantics: Annotated[str, Field(min_length=1, max_length=512)]
    retry_semantics: Annotated[str, Field(min_length=1, max_length=512)]
    license_semantics: Annotated[str, Field(min_length=1, max_length=512)]
    license_evidence_hash: Annotated[str, Field(pattern=_HASH)]
    effective_from: AwareDatetime
    effective_to: AwareDatetime | None = None
    definition_hash: Annotated[str, Field(pattern=_HASH)]

    @field_validator("provider_endpoint_id", "provider_id")
    @classmethod
    def validate_identifiers(cls, value: str, info: object) -> str:
        return _identifier(value, getattr(info, "field_name", "identifier"))

    @field_validator("request_method")
    @classmethod
    def validate_request_method(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in _REQUEST_METHODS:
            raise ValueError("request_method is not supported")
        return normalized

    @field_validator("redacted_origin_allowlist")
    @classmethod
    def validate_origins(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value:
            raise ValueError("redacted_origin_allowlist must not be empty")
        return _sorted_unique(tuple(_canonical_origin(item) for item in value), "redacted_origin_allowlist")

    @field_validator("path_family")
    @classmethod
    def validate_path_family(cls, value: str) -> str:
        return _path_family(value)

    @field_validator("market_scope")
    @classmethod
    def validate_market_scope(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value:
            raise ValueError("market_scope must not be empty")
        return _sorted_unique(tuple(_market(item) for item in value), "market_scope")

    @field_validator("dataset_bindings")
    @classmethod
    def validate_dataset_bindings(
        cls, value: tuple[EndpointDatasetBinding, ...]
    ) -> tuple[EndpointDatasetBinding, ...]:
        if not value:
            raise ValueError("dataset_bindings must not be empty")
        ordered = tuple(
            sorted(value, key=lambda item: (item.dataset_id, item.dataset_schema_version))
        )
        keys = {(item.dataset_id, item.dataset_schema_version) for item in ordered}
        if len(keys) != len(ordered):
            raise ValueError("dataset_bindings cannot contain duplicate dataset versions")
        return ordered

    @model_validator(mode="after")
    def validate_definition(self) -> "ProviderEndpointDefinition":
        if self.effective_to is not None and self.effective_to <= self.effective_from:
            raise ValueError("effective_to must be after effective_from")
        bound_markets = {market for binding in self.dataset_bindings for market in binding.market_scope}
        if bound_markets != set(self.market_scope):
            raise ValueError("market_scope must exactly match dataset binding markets")
        if self.definition_hash != compute_provider_endpoint_definition_hash(self):
            raise ValueError("definition_hash does not match ProviderEndpointDefinition")
        return self


class AdapterImplementationFingerprint(PlatformContractModel):
    adapter_implementation_fingerprint_id: str
    provider_endpoint_id: str
    provider_id: str
    endpoint_contract_version: Annotated[str, Field(pattern=_SEMVER)]
    adapter_bundle_id: str
    adapter_bundle_version: Annotated[str, Field(pattern=_SEMVER)]
    source_repository: str
    source_commit: str
    source_file_path: str
    source_file_blob_sha256: Annotated[str, Field(pattern=_HASH)]
    source_file_sha256: Annotated[str, Field(pattern=_HASH)]
    function_symbol: str
    visory_wrapper_version: Annotated[str, Field(pattern=_SEMVER)]
    visory_wrapper_hash: Annotated[str, Field(pattern=_HASH)]
    mapping_version: Annotated[str, Field(pattern=_SEMVER)]
    mapping_hash: Annotated[str, Field(pattern=_HASH)]
    quality_rule_versions: tuple[str, ...]
    quality_rule_hashes: tuple[Annotated[str, Field(pattern=_HASH)], ...]
    created_at: AwareDatetime
    implementation_fingerprint: Annotated[str, Field(pattern=_HASH)]

    @field_validator(
        "adapter_implementation_fingerprint_id",
        "provider_endpoint_id",
        "provider_id",
        "adapter_bundle_id",
    )
    @classmethod
    def validate_identifiers(cls, value: str, info: object) -> str:
        return _identifier(value, getattr(info, "field_name", "identifier"))

    @field_validator("source_repository")
    @classmethod
    def validate_source_repository(cls, value: str) -> str:
        return _source_repository(value)

    @field_validator("source_commit")
    @classmethod
    def validate_source_commit(cls, value: str) -> str:
        if not _COMMIT.fullmatch(value):
            raise ValueError("source_commit must be a lowercase full commit digest")
        return value

    @field_validator("source_file_path")
    @classmethod
    def validate_source_file_path(cls, value: str) -> str:
        return _source_file_path(value)

    @field_validator("function_symbol")
    @classmethod
    def validate_function_symbol(cls, value: str) -> str:
        if not _FUNCTION_SYMBOL.fullmatch(value):
            raise ValueError("function_symbol must be a stable qualified symbol")
        return value

    @field_validator("quality_rule_versions")
    @classmethod
    def validate_quality_rule_versions(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value:
            raise ValueError("quality_rule_versions must not be empty")
        if any(re.fullmatch(_SEMVER, item) is None for item in value):
            raise ValueError("quality_rule_versions must contain semantic versions")
        return value

    @model_validator(mode="after")
    def validate_fingerprint(self) -> "AdapterImplementationFingerprint":
        if len(self.quality_rule_versions) != len(self.quality_rule_hashes):
            raise ValueError("quality rule versions and hashes must have the same length")
        if self.implementation_fingerprint != compute_adapter_implementation_fingerprint(self):
            raise ValueError("implementation_fingerprint does not match implementation evidence")
        return self


class SourceAdmissionReceipt(PlatformContractModel):
    source_admission_receipt_id: str
    provider_endpoint_id: str
    provider_id: str
    endpoint_contract_version: Annotated[str, Field(pattern=_SEMVER)]
    dataset_id: str
    dataset_schema_version: Annotated[str, Field(pattern=_SEMVER)]
    requested_market_scope: tuple[str, ...]
    requested_date_from: date
    requested_date_to: date
    source_contract_hash: Annotated[str, Field(pattern=_HASH)]
    sample_manifest_hash: Annotated[str, Field(pattern=_HASH)]
    observation_log_hash: Annotated[str, Field(pattern=_HASH)]
    coverage_manifest_hash: Annotated[str, Field(pattern=_HASH)]
    revision_chain_hash: Annotated[str, Field(pattern=_HASH)]
    quality_report_hash: Annotated[str, Field(pattern=_HASH)]
    license_evidence_hash: Annotated[str, Field(pattern=_HASH)]
    expected_unit_and_identity_hash: Annotated[str, Field(pattern=_HASH)]
    coverage_summary: dict[str, Any]
    admission_level: str
    admission_status: str
    reason_codes: tuple[str, ...] = ()
    issued_at: AwareDatetime
    valid_from: AwareDatetime
    valid_to: AwareDatetime | None = None
    receipt_hash: Annotated[str, Field(pattern=_HASH)]

    @field_validator(
        "source_admission_receipt_id", "provider_endpoint_id", "provider_id", "dataset_id"
    )
    @classmethod
    def validate_identifiers(cls, value: str, info: object) -> str:
        return _identifier(value, getattr(info, "field_name", "identifier"))

    @field_validator("requested_market_scope")
    @classmethod
    def validate_market_scope(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value:
            raise ValueError("requested_market_scope must not be empty")
        return _sorted_unique(tuple(_market(item) for item in value), "requested_market_scope")

    @field_validator("admission_level")
    @classmethod
    def validate_admission_level(cls, value: str) -> str:
        if value not in _ADMISSION_LEVELS:
            raise ValueError("admission_level is not supported")
        return value

    @field_validator("admission_status")
    @classmethod
    def validate_admission_status(cls, value: str) -> str:
        if value not in _ADMISSION_STATUSES:
            raise ValueError("admission_status is not supported")
        return value

    @field_validator("reason_codes")
    @classmethod
    def validate_reason_codes(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not _REASON_CODE.fullmatch(item) for item in value):
            raise ValueError("reason_codes must contain stable uppercase identifiers")
        return _sorted_unique(value, "reason_codes")

    @model_validator(mode="after")
    def validate_receipt(self) -> "SourceAdmissionReceipt":
        if self.requested_date_to < self.requested_date_from:
            raise ValueError("requested_date_to must not precede requested_date_from")
        if self.valid_from < self.issued_at:
            raise ValueError("valid_from must not precede issued_at")
        if self.valid_to is not None and self.valid_to <= self.valid_from:
            raise ValueError("valid_to must be after valid_from")
        if self.admission_status in {"REJECTED", "REVOKED"} and not self.reason_codes:
            raise ValueError("rejected or revoked receipts require reason_codes")
        if self.receipt_hash != compute_source_admission_receipt_hash(self):
            raise ValueError("receipt_hash does not match SourceAdmissionReceipt")
        return self

    def evidence_hashes(self) -> dict[str, str]:
        return {
            "source_contract_hash": self.source_contract_hash,
            "sample_manifest_hash": self.sample_manifest_hash,
            "observation_log_hash": self.observation_log_hash,
            "coverage_manifest_hash": self.coverage_manifest_hash,
            "revision_chain_hash": self.revision_chain_hash,
            "quality_report_hash": self.quality_report_hash,
            "license_evidence_hash": self.license_evidence_hash,
            "expected_unit_and_identity_hash": self.expected_unit_and_identity_hash,
        }


class ProviderEndpointRunBinding(PlatformContractModel):
    provider_endpoint_run_binding_id: str
    provider_run_id: str
    raw_object_refs: tuple[str, ...]
    provider_id: str
    provider_endpoint_id: str
    endpoint_contract_version: Annotated[str, Field(pattern=_SEMVER)]
    adapter_implementation_fingerprint_id: str
    implementation_fingerprint: Annotated[str, Field(pattern=_HASH)]
    source_admission_receipt_id: str
    receipt_hash: Annotated[str, Field(pattern=_HASH)]
    dataset_id: str
    dataset_schema_version: Annotated[str, Field(pattern=_SEMVER)]
    market: str
    request_fingerprint: Annotated[str, Field(pattern=_HASH)]
    observed_schema_hash: Annotated[str, Field(pattern=_HASH)]
    actual_origin_redacted: str | None = None
    actual_origin_hash: Annotated[str, Field(pattern=_HASH)]
    created_at: AwareDatetime
    binding_hash: Annotated[str, Field(pattern=_HASH)]

    @field_validator(
        "provider_endpoint_run_binding_id",
        "provider_id",
        "provider_endpoint_id",
        "adapter_implementation_fingerprint_id",
        "source_admission_receipt_id",
        "dataset_id",
    )
    @classmethod
    def validate_identifiers(cls, value: str, info: object) -> str:
        return _identifier(value, getattr(info, "field_name", "identifier"))

    @field_validator("raw_object_refs")
    @classmethod
    def validate_raw_object_refs(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value:
            raise ValueError("raw_object_refs must not be empty")
        return _sorted_unique(value, "raw_object_refs")

    @field_validator("market")
    @classmethod
    def validate_market(cls, value: str) -> str:
        return _market(value)

    @field_validator("actual_origin_redacted")
    @classmethod
    def validate_actual_origin(cls, value: str | None) -> str | None:
        return ensure_safe_actual_upstream(value) if value is not None else None

    @model_validator(mode="after")
    def validate_binding(self) -> "ProviderEndpointRunBinding":
        if self.actual_origin_redacted is not None:
            expected = compute_actual_origin_hash(self.actual_origin_redacted)
            if self.actual_origin_hash != expected:
                raise ValueError("actual_origin_hash does not match actual_origin_redacted")
        if self.binding_hash != compute_provider_endpoint_run_binding_hash(self):
            raise ValueError("binding_hash does not match ProviderEndpointRunBinding")
        return self


def compute_provider_endpoint_definition_hash(
    value: ProviderEndpointDefinition | dict[str, Any],
) -> str:
    payload = _hash_payload(value, "definition_hash") if isinstance(value, ProviderEndpointDefinition) else dict(value)
    payload.pop("definition_hash", None)
    return compute_content_hash(payload)


def compute_adapter_implementation_fingerprint(
    value: AdapterImplementationFingerprint | dict[str, Any],
) -> str:
    payload = (
        _hash_payload(value, "implementation_fingerprint")
        if isinstance(value, AdapterImplementationFingerprint)
        else dict(value)
    )
    payload.pop("implementation_fingerprint", None)
    return compute_content_hash(payload)


def compute_source_admission_receipt_hash(
    value: SourceAdmissionReceipt | dict[str, Any],
) -> str:
    payload = _hash_payload(value, "receipt_hash") if isinstance(value, SourceAdmissionReceipt) else dict(value)
    payload.pop("receipt_hash", None)
    return compute_content_hash(payload)


def compute_provider_endpoint_run_binding_hash(
    value: ProviderEndpointRunBinding | dict[str, Any],
) -> str:
    payload = (
        _hash_payload(value, "binding_hash")
        if isinstance(value, ProviderEndpointRunBinding)
        else dict(value)
    )
    payload.pop("binding_hash", None)
    return compute_content_hash(payload)


def compute_actual_origin_hash(value: str) -> str:
    return compute_content_hash({"actual_origin": ensure_safe_actual_upstream(value)})


def build_provider_endpoint_definition(**payload: Any) -> ProviderEndpointDefinition:
    payload = dict(payload)
    payload["request_method"] = str(payload["request_method"]).upper()
    payload["redacted_origin_allowlist"] = _sorted_unique(
        tuple(_canonical_origin(item) for item in payload["redacted_origin_allowlist"]),
        "redacted_origin_allowlist",
    )
    payload["path_family"] = _path_family(payload["path_family"])
    payload["market_scope"] = _sorted_unique(
        tuple(_market(item) for item in payload["market_scope"]), "market_scope"
    )
    payload["dataset_bindings"] = tuple(
        sorted(
            (
                item
                if isinstance(item, EndpointDatasetBinding)
                else EndpointDatasetBinding.model_validate(item)
                for item in payload["dataset_bindings"]
            ),
            key=lambda item: (item.dataset_id, item.dataset_schema_version),
        )
    )
    payload.setdefault("effective_to", None)
    return ProviderEndpointDefinition(
        **payload,
        definition_hash=compute_provider_endpoint_definition_hash(payload),
    )


def build_adapter_implementation_fingerprint(
    **payload: Any,
) -> AdapterImplementationFingerprint:
    payload = dict(payload)
    payload["source_repository"] = _source_repository(payload["source_repository"])
    payload["source_file_path"] = _source_file_path(payload["source_file_path"])
    payload["quality_rule_versions"] = tuple(payload["quality_rule_versions"])
    payload["quality_rule_hashes"] = tuple(payload["quality_rule_hashes"])
    return AdapterImplementationFingerprint(
        **payload,
        implementation_fingerprint=compute_adapter_implementation_fingerprint(payload),
    )


def build_source_admission_receipt(**payload: Any) -> SourceAdmissionReceipt:
    payload = dict(payload)
    if "admission_level" not in payload:
        raise ValueError("admission_level must be explicit")
    payload["requested_market_scope"] = _sorted_unique(
        tuple(_market(item) for item in payload["requested_market_scope"]),
        "requested_market_scope",
    )
    payload["reason_codes"] = _sorted_unique(
        tuple(payload.get("reason_codes", ())), "reason_codes"
    )
    payload.setdefault("valid_to", None)
    return SourceAdmissionReceipt(
        **payload,
        receipt_hash=compute_source_admission_receipt_hash(payload),
    )


def build_provider_endpoint_run_binding(**payload: Any) -> ProviderEndpointRunBinding:
    payload = dict(payload)
    payload["raw_object_refs"] = _sorted_unique(
        tuple(payload["raw_object_refs"]), "raw_object_refs"
    )
    payload.setdefault("actual_origin_redacted", None)
    if payload["actual_origin_redacted"] is not None:
        payload["actual_origin_redacted"] = ensure_safe_actual_upstream(
            payload["actual_origin_redacted"]
        )
    if "actual_origin_hash" not in payload:
        actual_origin = payload.get("actual_origin_redacted")
        if actual_origin is None:
            raise ValueError("actual_origin_hash or actual_origin_redacted is required")
        payload["actual_origin_hash"] = compute_actual_origin_hash(actual_origin)
    return ProviderEndpointRunBinding(
        **payload,
        binding_hash=compute_provider_endpoint_run_binding_hash(payload),
    )


__all__ = [
    "AdapterImplementationFingerprint",
    "EndpointDatasetBinding",
    "ProviderEndpointDefinition",
    "ProviderEndpointRunBinding",
    "SourceAdmissionReceipt",
    "build_adapter_implementation_fingerprint",
    "build_provider_endpoint_definition",
    "build_provider_endpoint_run_binding",
    "build_source_admission_receipt",
    "compute_actual_origin_hash",
    "compute_adapter_implementation_fingerprint",
    "compute_provider_endpoint_definition_hash",
    "compute_provider_endpoint_run_binding_hash",
    "compute_source_admission_receipt_hash",
]
