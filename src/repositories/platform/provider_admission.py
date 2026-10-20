from __future__ import annotations

from typing import Any
from urllib.parse import unquote, urlsplit, urlunsplit

from sqlalchemy import Column, Date, DateTime, ForeignKey, ForeignKeyConstraint, Integer, MetaData, String, Table, insert, select, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from src.repositories.platform.provider import dataset_definition, provider_definition
from src.repositories.platform.raw_ingestion import provider_run, raw_object
from src.schemas.platform.provider_admission import (
    AdapterImplementationFingerprint,
    EndpointDatasetBinding,
    ProviderEndpointDefinition,
    ProviderEndpointRunBinding,
    SourceAdmissionReceipt,
    compute_actual_origin_hash,
)


metadata = MetaData()

provider_endpoint_definition = Table(
    "provider_endpoint_definition",
    metadata,
    Column("provider_endpoint_id", String(128), primary_key=True),
    Column("provider_id", String(64), ForeignKey("provider_definition.provider_id", ondelete="RESTRICT"), primary_key=True),
    Column("endpoint_contract_version", String(32), primary_key=True),
    Column("request_method", String(16), nullable=False),
    Column("redacted_origin_allowlist", JSONB, nullable=False),
    Column("path_family", String(512), nullable=False),
    Column("request_schema_hash", String(71), nullable=False),
    Column("response_schema_hash", String(71), nullable=False),
    Column("dataset_bindings", JSONB, nullable=False),
    Column("market_scope", JSONB, nullable=False),
    Column("pagination_semantics", String(512), nullable=False),
    Column("total_semantics", String(512), nullable=False),
    Column("terminal_semantics", String(512), nullable=False),
    Column("valid_zero_row_semantics", String(512), nullable=False),
    Column("no_data_semantics", String(512), nullable=False),
    Column("error_semantics", String(512), nullable=False),
    Column("revision_semantics", String(512), nullable=False),
    Column("cancellation_semantics", String(512), nullable=False),
    Column("source_publication_semantics", String(512), nullable=False),
    Column("rate_limit_semantics", String(512), nullable=False),
    Column("retry_semantics", String(512), nullable=False),
    Column("license_semantics", String(512), nullable=False),
    Column("license_evidence_hash", String(71), nullable=False),
    Column("effective_from", DateTime(timezone=True), nullable=False),
    Column("effective_to", DateTime(timezone=True)),
    Column("definition_hash", String(71), nullable=False),
)

adapter_implementation_fingerprint = Table(
    "adapter_implementation_fingerprint",
    metadata,
    Column("adapter_implementation_fingerprint_id", String(128), primary_key=True),
    Column("provider_endpoint_id", String(128), nullable=False),
    Column("provider_id", String(64), nullable=False),
    Column("endpoint_contract_version", String(32), nullable=False),
    Column("adapter_bundle_id", String(128), nullable=False),
    Column("adapter_bundle_version", String(32), nullable=False),
    Column("source_repository", String(1024), nullable=False),
    Column("source_commit", String(64), nullable=False),
    Column("source_file_path", String(1024), nullable=False),
    Column("source_file_blob_sha256", String(71), nullable=False),
    Column("source_file_sha256", String(71), nullable=False),
    Column("function_symbol", String(255), nullable=False),
    Column("visory_wrapper_version", String(32), nullable=False),
    Column("visory_wrapper_hash", String(71), nullable=False),
    Column("mapping_version", String(32), nullable=False),
    Column("mapping_hash", String(71), nullable=False),
    Column("quality_rule_versions", JSONB, nullable=False),
    Column("quality_rule_hashes", JSONB, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("implementation_fingerprint", String(71), nullable=False),
    ForeignKeyConstraint(
        ["provider_endpoint_id", "provider_id", "endpoint_contract_version"],
        [
            "provider_endpoint_definition.provider_endpoint_id",
            "provider_endpoint_definition.provider_id",
            "provider_endpoint_definition.endpoint_contract_version",
        ],
        ondelete="RESTRICT",
    ),
)

source_admission_receipt = Table(
    "source_admission_receipt",
    metadata,
    Column("source_admission_receipt_id", String(128), primary_key=True),
    Column("provider_endpoint_id", String(128), nullable=False),
    Column("provider_id", String(64), nullable=False),
    Column("endpoint_contract_version", String(32), nullable=False),
    Column("dataset_id", String(64), nullable=False),
    Column("dataset_schema_version", String(32), nullable=False),
    Column("requested_market_scope", JSONB, nullable=False),
    Column("requested_date_from", Date, nullable=False),
    Column("requested_date_to", Date, nullable=False),
    Column("source_contract_hash", String(71), nullable=False),
    Column("sample_manifest_hash", String(71), nullable=False),
    Column("observation_log_hash", String(71), nullable=False),
    Column("coverage_manifest_hash", String(71), nullable=False),
    Column("revision_chain_hash", String(71), nullable=False),
    Column("quality_report_hash", String(71), nullable=False),
    Column("license_evidence_hash", String(71), nullable=False),
    Column("expected_unit_and_identity_hash", String(71), nullable=False),
    Column("coverage_summary", JSONB, nullable=False),
    Column("admission_level", String(32), nullable=False),
    Column("admission_status", String(16), nullable=False),
    Column("reason_codes", JSONB, nullable=False),
    Column("issued_at", DateTime(timezone=True), nullable=False),
    Column("valid_from", DateTime(timezone=True), nullable=False),
    Column("valid_to", DateTime(timezone=True)),
    Column("receipt_hash", String(71), nullable=False),
    ForeignKeyConstraint(
        ["provider_endpoint_id", "provider_id", "endpoint_contract_version"],
        [
            "provider_endpoint_definition.provider_endpoint_id",
            "provider_endpoint_definition.provider_id",
            "provider_endpoint_definition.endpoint_contract_version",
        ],
        ondelete="RESTRICT",
    ),
    ForeignKeyConstraint(
        ["dataset_id", "dataset_schema_version"],
        ["dataset_definition.dataset_id", "dataset_definition.schema_version"],
        ondelete="RESTRICT",
    ),
)

provider_endpoint_run_binding = Table(
    "provider_endpoint_run_binding",
    metadata,
    Column("provider_endpoint_run_binding_id", String(128), primary_key=True),
    Column("provider_run_id", String(64), ForeignKey("provider_run.provider_run_id", ondelete="RESTRICT"), nullable=False, unique=True),
    Column("provider_id", String(64), nullable=False),
    Column("provider_endpoint_id", String(128), nullable=False),
    Column("endpoint_contract_version", String(32), nullable=False),
    Column(
        "adapter_implementation_fingerprint_id",
        String(128),
        ForeignKey("adapter_implementation_fingerprint.adapter_implementation_fingerprint_id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column("implementation_fingerprint", String(71), nullable=False),
    Column(
        "source_admission_receipt_id",
        String(128),
        ForeignKey("source_admission_receipt.source_admission_receipt_id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column("receipt_hash", String(71), nullable=False),
    Column("dataset_id", String(64), nullable=False),
    Column("dataset_schema_version", String(32), nullable=False),
    Column("market", String(32), nullable=False),
    Column("request_fingerprint", String(71), nullable=False),
    Column("observed_schema_hash", String(71), nullable=False),
    Column("actual_origin_redacted", String(255)),
    Column("actual_origin_hash", String(71), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("binding_hash", String(71), nullable=False),
    ForeignKeyConstraint(
        ["provider_endpoint_id", "provider_id", "endpoint_contract_version"],
        [
            "provider_endpoint_definition.provider_endpoint_id",
            "provider_endpoint_definition.provider_id",
            "provider_endpoint_definition.endpoint_contract_version",
        ],
        ondelete="RESTRICT",
    ),
    ForeignKeyConstraint(
        ["dataset_id", "dataset_schema_version"],
        ["dataset_definition.dataset_id", "dataset_definition.schema_version"],
        ondelete="RESTRICT",
    ),
)

provider_endpoint_run_binding_raw_object = Table(
    "provider_endpoint_run_binding_raw_object",
    metadata,
    Column(
        "provider_endpoint_run_binding_id",
        String(128),
        ForeignKey("provider_endpoint_run_binding.provider_endpoint_run_binding_id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("raw_object_id", String(64), ForeignKey("raw_object.raw_object_id", ondelete="RESTRICT"), primary_key=True),
    Column("raw_order", Integer, nullable=False),
)


def _endpoint(row: Any) -> ProviderEndpointDefinition:
    value = dict(row)
    value["redacted_origin_allowlist"] = tuple(value["redacted_origin_allowlist"])
    value["market_scope"] = tuple(value["market_scope"])
    value["dataset_bindings"] = tuple(
        EndpointDatasetBinding.model_validate(item) for item in value["dataset_bindings"]
    )
    return ProviderEndpointDefinition.model_validate(value)


def _fingerprint(row: Any) -> AdapterImplementationFingerprint:
    value = dict(row)
    value["quality_rule_versions"] = tuple(value["quality_rule_versions"])
    value["quality_rule_hashes"] = tuple(value["quality_rule_hashes"])
    return AdapterImplementationFingerprint.model_validate(value)


def _receipt(row: Any) -> SourceAdmissionReceipt:
    value = dict(row)
    value["requested_market_scope"] = tuple(value["requested_market_scope"])
    value["reason_codes"] = tuple(value["reason_codes"])
    return SourceAdmissionReceipt.model_validate(value)


def _binding(row: Any, raw_object_refs: tuple[str, ...]) -> ProviderEndpointRunBinding:
    value = dict(row)
    value["raw_object_refs"] = raw_object_refs
    return ProviderEndpointRunBinding.model_validate(value)


def endpoint_allows_actual_upstream(endpoint: ProviderEndpointDefinition, actual_upstream: str) -> bool:
    parsed = urlsplit(actual_upstream)
    if parsed.scheme:
        origin = urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), "", "", ""))
        path = parsed.path or "/"
    else:
        origin = actual_upstream.lower()
        path = "/"
    if origin not in endpoint.redacted_origin_allowlist:
        return False
    for _ in range(3):
        decoded_path = unquote(path)
        if decoded_path == path:
            break
        path = decoded_path
    else:
        if unquote(path) != path:
            return False
    if "\\" in path or any(segment in {".", ".."} for segment in path.split("/")):
        return False
    family = endpoint.path_family
    return path.startswith(family[:-1]) if family.endswith("*") else path == family


class ProviderAdmissionRepository:
    """Append-only Endpoint Admission persistence; callers own transactions."""

    @staticmethod
    def lock_publication_tables(session: Session) -> None:
        session.execute(
            text(
                "LOCK TABLE provider_endpoint_run_binding_raw_object, "
                "provider_endpoint_run_binding, source_admission_receipt, "
                "adapter_implementation_fingerprint, provider_endpoint_definition "
                "IN SHARE ROW EXCLUSIVE MODE"
            )
        )

    @staticmethod
    def add_endpoint(session: Session, record: ProviderEndpointDefinition) -> None:
        if session.execute(
            select(provider_definition.c.provider_id).where(
                provider_definition.c.provider_id == record.provider_id
            )
        ).scalar_one_or_none() is None:
            raise ValueError("ProviderEndpointDefinition references an unknown Provider")
        payload = record.model_dump(mode="python")
        payload["redacted_origin_allowlist"] = list(record.redacted_origin_allowlist)
        payload["market_scope"] = list(record.market_scope)
        payload["dataset_bindings"] = [item.model_dump(mode="json") for item in record.dataset_bindings]
        session.execute(insert(provider_endpoint_definition).values(**payload))

    @staticmethod
    def get_endpoint(
        session: Session,
        provider_endpoint_id: str,
        provider_id: str,
        endpoint_contract_version: str,
    ) -> ProviderEndpointDefinition | None:
        row = session.execute(
            select(provider_endpoint_definition).where(
                provider_endpoint_definition.c.provider_endpoint_id == provider_endpoint_id,
                provider_endpoint_definition.c.provider_id == provider_id,
                provider_endpoint_definition.c.endpoint_contract_version == endpoint_contract_version,
            )
        ).mappings().one_or_none()
        return _endpoint(row) if row is not None else None

    @classmethod
    def add_fingerprint(cls, session: Session, record: AdapterImplementationFingerprint) -> None:
        endpoint = cls.get_endpoint(
            session,
            record.provider_endpoint_id,
            record.provider_id,
            record.endpoint_contract_version,
        )
        if endpoint is None:
            raise ValueError("AdapterImplementationFingerprint references an unknown Endpoint version")
        payload = record.model_dump(mode="python")
        payload["quality_rule_versions"] = list(record.quality_rule_versions)
        payload["quality_rule_hashes"] = list(record.quality_rule_hashes)
        session.execute(insert(adapter_implementation_fingerprint).values(**payload))

    @staticmethod
    def get_fingerprint(
        session: Session, adapter_implementation_fingerprint_id: str
    ) -> AdapterImplementationFingerprint | None:
        row = session.execute(
            select(adapter_implementation_fingerprint).where(
                adapter_implementation_fingerprint.c.adapter_implementation_fingerprint_id
                == adapter_implementation_fingerprint_id
            )
        ).mappings().one_or_none()
        return _fingerprint(row) if row is not None else None

    @classmethod
    def add_receipt(cls, session: Session, record: SourceAdmissionReceipt) -> None:
        endpoint = cls.get_endpoint(
            session,
            record.provider_endpoint_id,
            record.provider_id,
            record.endpoint_contract_version,
        )
        if endpoint is None:
            raise ValueError("SourceAdmissionReceipt references an unknown Endpoint version")
        binding = next(
            (
                item
                for item in endpoint.dataset_bindings
                if item.dataset_id == record.dataset_id
                and item.dataset_schema_version == record.dataset_schema_version
            ),
            None,
        )
        if binding is None or not set(record.requested_market_scope) <= set(binding.market_scope):
            raise ValueError("SourceAdmissionReceipt scope is not declared by the Endpoint")
        if record.license_evidence_hash != endpoint.license_evidence_hash:
            raise ValueError("SourceAdmissionReceipt license evidence does not match the Endpoint")
        if session.execute(
            select(dataset_definition.c.dataset_id).where(
                dataset_definition.c.dataset_id == record.dataset_id,
                dataset_definition.c.schema_version == record.dataset_schema_version,
            )
        ).first() is None:
            raise ValueError("SourceAdmissionReceipt references an unknown Dataset version")
        payload = record.model_dump(mode="python")
        payload["requested_market_scope"] = list(record.requested_market_scope)
        payload["reason_codes"] = list(record.reason_codes)
        session.execute(insert(source_admission_receipt).values(**payload))

    @staticmethod
    def get_receipt(
        session: Session, source_admission_receipt_id: str
    ) -> SourceAdmissionReceipt | None:
        row = session.execute(
            select(source_admission_receipt).where(
                source_admission_receipt.c.source_admission_receipt_id
                == source_admission_receipt_id
            )
        ).mappings().one_or_none()
        return _receipt(row) if row is not None else None

    @classmethod
    def add_binding(cls, session: Session, record: ProviderEndpointRunBinding) -> None:
        run_row = session.execute(
            select(provider_run).where(provider_run.c.provider_run_id == record.provider_run_id)
        ).mappings().one_or_none()
        if run_row is None:
            raise ValueError("ProviderEndpointRunBinding references an unknown ProviderRun")
        run = dict(run_row)
        run_raw_refs = tuple(run["raw_object_refs"] or ())
        if set(run_raw_refs) != set(record.raw_object_refs) or len(run_raw_refs) != len(record.raw_object_refs):
            raise ValueError("ProviderEndpointRunBinding must include every ProviderRun RawObject exactly once")
        if (
            run["provider_id"] != record.provider_id
            or run["dataset_id"] != record.dataset_id
            or run["dataset_schema_version"] != record.dataset_schema_version
            or run["capability_market"] != record.market
            or run["request_fingerprint"] != record.request_fingerprint
            or run["observed_schema_hash"] != record.observed_schema_hash
        ):
            raise ValueError("ProviderEndpointRunBinding does not match its ProviderRun")
        if run["actual_upstream"] is None or compute_actual_origin_hash(run["actual_upstream"]) != record.actual_origin_hash:
            raise ValueError("ProviderEndpointRunBinding actual origin does not match its ProviderRun")
        if record.actual_origin_redacted is not None and record.actual_origin_redacted != run["actual_upstream"]:
            raise ValueError("ProviderEndpointRunBinding redacted origin does not match its ProviderRun")

        endpoint = cls.get_endpoint(
            session,
            record.provider_endpoint_id,
            record.provider_id,
            record.endpoint_contract_version,
        )
        if endpoint is None or not endpoint_allows_actual_upstream(endpoint, run["actual_upstream"]):
            raise ValueError("ProviderEndpointRunBinding origin is not allowed by the Endpoint")
        dataset_binding = next(
            (
                item
                for item in endpoint.dataset_bindings
                if item.dataset_id == record.dataset_id
                and item.dataset_schema_version == record.dataset_schema_version
            ),
            None,
        )
        if dataset_binding is None or record.market not in dataset_binding.market_scope:
            raise ValueError("ProviderEndpointRunBinding Dataset or market is not allowed by the Endpoint")

        fingerprint = cls.get_fingerprint(session, record.adapter_implementation_fingerprint_id)
        if (
            fingerprint is None
            or fingerprint.provider_endpoint_id != record.provider_endpoint_id
            or fingerprint.provider_id != record.provider_id
            or fingerprint.endpoint_contract_version != record.endpoint_contract_version
            or fingerprint.implementation_fingerprint != record.implementation_fingerprint
        ):
            raise ValueError("ProviderEndpointRunBinding implementation fingerprint is inconsistent")

        receipt = cls.get_receipt(session, record.source_admission_receipt_id)
        if (
            receipt is None
            or receipt.provider_endpoint_id != record.provider_endpoint_id
            or receipt.provider_id != record.provider_id
            or receipt.endpoint_contract_version != record.endpoint_contract_version
            or receipt.dataset_id != record.dataset_id
            or receipt.dataset_schema_version != record.dataset_schema_version
            or receipt.receipt_hash != record.receipt_hash
            or record.market not in receipt.requested_market_scope
        ):
            raise ValueError("ProviderEndpointRunBinding SourceAdmissionReceipt is inconsistent")

        raw_rows = tuple(
            session.execute(
                select(raw_object).where(raw_object.c.raw_object_id.in_(record.raw_object_refs))
            ).mappings()
        )
        if len(raw_rows) != len(record.raw_object_refs):
            raise ValueError("ProviderEndpointRunBinding references an unknown RawObject")
        for raw in raw_rows:
            if (
                raw["provider_run_id"] != record.provider_run_id
                or raw["provider_id"] != record.provider_id
                or raw["dataset_id"] != record.dataset_id
                or raw["dataset_schema_version"] != record.dataset_schema_version
                or raw["request_fingerprint"] != record.request_fingerprint
                or raw["observed_schema_hash"] != record.observed_schema_hash
                or compute_actual_origin_hash(raw["actual_upstream"]) != record.actual_origin_hash
            ):
                raise ValueError("ProviderEndpointRunBinding RawObject lineage is inconsistent")

        payload = record.model_dump(mode="python", exclude={"raw_object_refs"})
        session.execute(insert(provider_endpoint_run_binding).values(**payload))
        for order, raw_object_id in enumerate(record.raw_object_refs):
            session.execute(
                insert(provider_endpoint_run_binding_raw_object).values(
                    provider_endpoint_run_binding_id=record.provider_endpoint_run_binding_id,
                    raw_object_id=raw_object_id,
                    raw_order=order,
                )
            )

    @staticmethod
    def _get_binding_from_statement(session: Session, statement: Any) -> ProviderEndpointRunBinding | None:
        row = session.execute(statement).mappings().one_or_none()
        if row is None:
            return None
        raw_refs = tuple(
            session.execute(
                select(provider_endpoint_run_binding_raw_object.c.raw_object_id)
                .where(
                    provider_endpoint_run_binding_raw_object.c.provider_endpoint_run_binding_id
                    == row["provider_endpoint_run_binding_id"]
                )
                .order_by(provider_endpoint_run_binding_raw_object.c.raw_order)
            ).scalars()
        )
        return _binding(row, raw_refs)

    @classmethod
    def get_binding(
        cls, session: Session, provider_endpoint_run_binding_id: str
    ) -> ProviderEndpointRunBinding | None:
        return cls._get_binding_from_statement(
            session,
            select(provider_endpoint_run_binding).where(
                provider_endpoint_run_binding.c.provider_endpoint_run_binding_id
                == provider_endpoint_run_binding_id
            ),
        )

    @classmethod
    def get_binding_by_run(
        cls, session: Session, provider_run_id: str
    ) -> ProviderEndpointRunBinding | None:
        return cls._get_binding_from_statement(
            session,
            select(provider_endpoint_run_binding).where(
                provider_endpoint_run_binding.c.provider_run_id == provider_run_id
            ),
        )


__all__ = [
    "ProviderAdmissionRepository",
    "adapter_implementation_fingerprint",
    "endpoint_allows_actual_upstream",
    "provider_endpoint_definition",
    "provider_endpoint_run_binding",
    "provider_endpoint_run_binding_raw_object",
    "source_admission_receipt",
]
