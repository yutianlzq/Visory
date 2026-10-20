"""Add append-only C-004 Provider Endpoint Admission evidence."""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0016_wp0303_provider_endpoint_admission"
down_revision = "0015_wp0303_partition_key"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "provider_endpoint_definition",
        sa.Column("provider_endpoint_id", sa.String(128), nullable=False),
        sa.Column("provider_id", sa.String(64), nullable=False),
        sa.Column("endpoint_contract_version", sa.String(32), nullable=False),
        sa.Column("request_method", sa.String(16), nullable=False),
        sa.Column("redacted_origin_allowlist", postgresql.JSONB(), nullable=False),
        sa.Column("path_family", sa.String(512), nullable=False),
        sa.Column("request_schema_hash", sa.String(71), nullable=False),
        sa.Column("response_schema_hash", sa.String(71), nullable=False),
        sa.Column("dataset_bindings", postgresql.JSONB(), nullable=False),
        sa.Column("market_scope", postgresql.JSONB(), nullable=False),
        sa.Column("pagination_semantics", sa.String(512), nullable=False),
        sa.Column("total_semantics", sa.String(512), nullable=False),
        sa.Column("terminal_semantics", sa.String(512), nullable=False),
        sa.Column("valid_zero_row_semantics", sa.String(512), nullable=False),
        sa.Column("no_data_semantics", sa.String(512), nullable=False),
        sa.Column("error_semantics", sa.String(512), nullable=False),
        sa.Column("revision_semantics", sa.String(512), nullable=False),
        sa.Column("cancellation_semantics", sa.String(512), nullable=False),
        sa.Column("source_publication_semantics", sa.String(512), nullable=False),
        sa.Column("rate_limit_semantics", sa.String(512), nullable=False),
        sa.Column("retry_semantics", sa.String(512), nullable=False),
        sa.Column("license_semantics", sa.String(512), nullable=False),
        sa.Column("license_evidence_hash", sa.String(71), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_to", sa.DateTime(timezone=True)),
        sa.Column("definition_hash", sa.String(71), nullable=False),
        sa.PrimaryKeyConstraint(
            "provider_endpoint_id",
            "provider_id",
            "endpoint_contract_version",
            name="pk_provider_endpoint_definition",
        ),
        sa.ForeignKeyConstraint(
            ["provider_id"], ["provider_definition.provider_id"], ondelete="RESTRICT"
        ),
        sa.CheckConstraint(
            "endpoint_contract_version ~ '^[0-9]+\\.[0-9]+\\.[0-9]+$'",
            name="ck_provider_endpoint_version",
        ),
        sa.CheckConstraint(
            "request_method IN ('GET','POST','PUT','PATCH','DELETE')",
            name="ck_provider_endpoint_method",
        ),
        sa.CheckConstraint(
            "request_schema_hash ~ '^sha256:[0-9a-f]{64}$' AND "
            "response_schema_hash ~ '^sha256:[0-9a-f]{64}$' AND "
            "license_evidence_hash ~ '^sha256:[0-9a-f]{64}$' AND "
            "definition_hash ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_provider_endpoint_hashes",
        ),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from",
            name="ck_provider_endpoint_effective_interval",
        ),
    )
    op.create_index(
        "ix_provider_endpoint_provider_version",
        "provider_endpoint_definition",
        ["provider_id", "endpoint_contract_version"],
    )
    op.create_index(
        "ix_provider_endpoint_definition_hash",
        "provider_endpoint_definition",
        ["definition_hash"],
    )

    op.create_table(
        "adapter_implementation_fingerprint",
        sa.Column("adapter_implementation_fingerprint_id", sa.String(128), primary_key=True),
        sa.Column("provider_endpoint_id", sa.String(128), nullable=False),
        sa.Column("provider_id", sa.String(64), nullable=False),
        sa.Column("endpoint_contract_version", sa.String(32), nullable=False),
        sa.Column("adapter_bundle_id", sa.String(128), nullable=False),
        sa.Column("adapter_bundle_version", sa.String(32), nullable=False),
        sa.Column("source_repository", sa.String(1024), nullable=False),
        sa.Column("source_commit", sa.String(64), nullable=False),
        sa.Column("source_file_path", sa.String(1024), nullable=False),
        sa.Column("source_file_blob_sha256", sa.String(71), nullable=False),
        sa.Column("source_file_sha256", sa.String(71), nullable=False),
        sa.Column("function_symbol", sa.String(255), nullable=False),
        sa.Column("visory_wrapper_version", sa.String(32), nullable=False),
        sa.Column("visory_wrapper_hash", sa.String(71), nullable=False),
        sa.Column("mapping_version", sa.String(32), nullable=False),
        sa.Column("mapping_hash", sa.String(71), nullable=False),
        sa.Column("quality_rule_versions", postgresql.JSONB(), nullable=False),
        sa.Column("quality_rule_hashes", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("implementation_fingerprint", sa.String(71), nullable=False),
        sa.ForeignKeyConstraint(
            ["provider_endpoint_id", "provider_id", "endpoint_contract_version"],
            [
                "provider_endpoint_definition.provider_endpoint_id",
                "provider_endpoint_definition.provider_id",
                "provider_endpoint_definition.endpoint_contract_version",
            ],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "adapter_bundle_version ~ '^[0-9]+\\.[0-9]+\\.[0-9]+$' AND "
            "endpoint_contract_version ~ '^[0-9]+\\.[0-9]+\\.[0-9]+$' AND "
            "visory_wrapper_version ~ '^[0-9]+\\.[0-9]+\\.[0-9]+$' AND "
            "mapping_version ~ '^[0-9]+\\.[0-9]+\\.[0-9]+$'",
            name="ck_adapter_fingerprint_versions",
        ),
        sa.CheckConstraint(
            "source_file_blob_sha256 ~ '^sha256:[0-9a-f]{64}$' AND "
            "source_file_sha256 ~ '^sha256:[0-9a-f]{64}$' AND "
            "visory_wrapper_hash ~ '^sha256:[0-9a-f]{64}$' AND "
            "mapping_hash ~ '^sha256:[0-9a-f]{64}$' AND "
            "implementation_fingerprint ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_adapter_fingerprint_hashes",
        ),
        sa.CheckConstraint(
            "source_commit ~ '^[0-9a-f]{40,64}$'", name="ck_adapter_fingerprint_commit"
        ),
    )
    op.create_index(
        "ix_adapter_fingerprint_endpoint",
        "adapter_implementation_fingerprint",
        ["provider_endpoint_id", "provider_id", "endpoint_contract_version"],
    )
    op.create_index(
        "ix_adapter_implementation_fingerprint_hash",
        "adapter_implementation_fingerprint",
        ["implementation_fingerprint"],
    )

    op.create_table(
        "source_admission_receipt",
        sa.Column("source_admission_receipt_id", sa.String(128), primary_key=True),
        sa.Column("provider_endpoint_id", sa.String(128), nullable=False),
        sa.Column("provider_id", sa.String(64), nullable=False),
        sa.Column("endpoint_contract_version", sa.String(32), nullable=False),
        sa.Column("dataset_id", sa.String(64), nullable=False),
        sa.Column("dataset_schema_version", sa.String(32), nullable=False),
        sa.Column("requested_market_scope", postgresql.JSONB(), nullable=False),
        sa.Column("requested_date_from", sa.Date(), nullable=False),
        sa.Column("requested_date_to", sa.Date(), nullable=False),
        sa.Column("source_contract_hash", sa.String(71), nullable=False),
        sa.Column("sample_manifest_hash", sa.String(71), nullable=False),
        sa.Column("observation_log_hash", sa.String(71), nullable=False),
        sa.Column("coverage_manifest_hash", sa.String(71), nullable=False),
        sa.Column("revision_chain_hash", sa.String(71), nullable=False),
        sa.Column("quality_report_hash", sa.String(71), nullable=False),
        sa.Column("license_evidence_hash", sa.String(71), nullable=False),
        sa.Column("expected_unit_and_identity_hash", sa.String(71), nullable=False),
        sa.Column("coverage_summary", postgresql.JSONB(), nullable=False),
        sa.Column("admission_level", sa.String(32), nullable=False),
        sa.Column("admission_status", sa.String(16), nullable=False),
        sa.Column("reason_codes", postgresql.JSONB(), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True)),
        sa.Column("receipt_hash", sa.String(71), nullable=False),
        sa.ForeignKeyConstraint(
            ["provider_endpoint_id", "provider_id", "endpoint_contract_version"],
            [
                "provider_endpoint_definition.provider_endpoint_id",
                "provider_endpoint_definition.provider_id",
                "provider_endpoint_definition.endpoint_contract_version",
            ],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id", "dataset_schema_version"],
            ["dataset_definition.dataset_id", "dataset_definition.schema_version"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "requested_date_to >= requested_date_from", name="ck_source_admission_requested_interval"
        ),
        sa.CheckConstraint(
            "valid_from >= issued_at AND (valid_to IS NULL OR valid_to > valid_from)",
            name="ck_source_admission_valid_interval",
        ),
        sa.CheckConstraint(
            "admission_level IN ('CURRENT_SNAPSHOT','HISTORICAL_SERIES','VERSIONED_ARCHIVE','PIT_CERTIFIED')",
            name="ck_source_admission_level",
        ),
        sa.CheckConstraint(
            "admission_status IN ('ACCEPTED','REJECTED','REVOKED')",
            name="ck_source_admission_status",
        ),
        sa.CheckConstraint(
            "source_contract_hash ~ '^sha256:[0-9a-f]{64}$' AND "
            "sample_manifest_hash ~ '^sha256:[0-9a-f]{64}$' AND "
            "observation_log_hash ~ '^sha256:[0-9a-f]{64}$' AND "
            "coverage_manifest_hash ~ '^sha256:[0-9a-f]{64}$' AND "
            "revision_chain_hash ~ '^sha256:[0-9a-f]{64}$' AND "
            "quality_report_hash ~ '^sha256:[0-9a-f]{64}$' AND "
            "license_evidence_hash ~ '^sha256:[0-9a-f]{64}$' AND "
            "expected_unit_and_identity_hash ~ '^sha256:[0-9a-f]{64}$' AND "
            "receipt_hash ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_source_admission_hashes",
        ),
    )
    op.create_index(
        "ix_source_admission_endpoint_dataset",
        "source_admission_receipt",
        [
            "provider_endpoint_id",
            "provider_id",
            "endpoint_contract_version",
            "dataset_id",
            "dataset_schema_version",
        ],
    )
    op.create_index(
        "ix_source_admission_level_status_valid",
        "source_admission_receipt",
        ["admission_level", "admission_status", "valid_from", "valid_to"],
    )
    op.create_index(
        "ix_source_admission_receipt_hash", "source_admission_receipt", ["receipt_hash"]
    )

    op.create_table(
        "provider_endpoint_run_binding",
        sa.Column("provider_endpoint_run_binding_id", sa.String(128), primary_key=True),
        sa.Column("provider_run_id", sa.String(64), nullable=False),
        sa.Column("provider_id", sa.String(64), nullable=False),
        sa.Column("provider_endpoint_id", sa.String(128), nullable=False),
        sa.Column("endpoint_contract_version", sa.String(32), nullable=False),
        sa.Column("adapter_implementation_fingerprint_id", sa.String(128), nullable=False),
        sa.Column("implementation_fingerprint", sa.String(71), nullable=False),
        sa.Column("source_admission_receipt_id", sa.String(128), nullable=False),
        sa.Column("receipt_hash", sa.String(71), nullable=False),
        sa.Column("dataset_id", sa.String(64), nullable=False),
        sa.Column("dataset_schema_version", sa.String(32), nullable=False),
        sa.Column("market", sa.String(32), nullable=False),
        sa.Column("request_fingerprint", sa.String(71), nullable=False),
        sa.Column("observed_schema_hash", sa.String(71), nullable=False),
        sa.Column("actual_origin_redacted", sa.String(255)),
        sa.Column("actual_origin_hash", sa.String(71), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("binding_hash", sa.String(71), nullable=False),
        sa.ForeignKeyConstraint(
            ["provider_run_id"], ["provider_run.provider_run_id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["provider_endpoint_id", "provider_id", "endpoint_contract_version"],
            [
                "provider_endpoint_definition.provider_endpoint_id",
                "provider_endpoint_definition.provider_id",
                "provider_endpoint_definition.endpoint_contract_version",
            ],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["adapter_implementation_fingerprint_id"],
            ["adapter_implementation_fingerprint.adapter_implementation_fingerprint_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_admission_receipt_id"],
            ["source_admission_receipt.source_admission_receipt_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id", "dataset_schema_version"],
            ["dataset_definition.dataset_id", "dataset_definition.schema_version"],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("provider_run_id", name="uq_provider_endpoint_binding_run"),
        sa.CheckConstraint(
            "implementation_fingerprint ~ '^sha256:[0-9a-f]{64}$' AND "
            "receipt_hash ~ '^sha256:[0-9a-f]{64}$' AND "
            "request_fingerprint ~ '^sha256:[0-9a-f]{64}$' AND "
            "observed_schema_hash ~ '^sha256:[0-9a-f]{64}$' AND "
            "actual_origin_hash ~ '^sha256:[0-9a-f]{64}$' AND "
            "binding_hash ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_provider_endpoint_binding_hashes",
        ),
    )
    op.create_index(
        "ix_provider_endpoint_binding_endpoint",
        "provider_endpoint_run_binding",
        ["provider_endpoint_id", "provider_id", "endpoint_contract_version"],
    )
    op.create_index(
        "ix_provider_endpoint_binding_dataset",
        "provider_endpoint_run_binding",
        ["dataset_id", "dataset_schema_version", "market"],
    )
    op.create_index(
        "ix_provider_endpoint_binding_hash", "provider_endpoint_run_binding", ["binding_hash"]
    )

    op.create_table(
        "provider_endpoint_run_binding_raw_object",
        sa.Column("provider_endpoint_run_binding_id", sa.String(128), nullable=False),
        sa.Column("raw_object_id", sa.String(64), nullable=False),
        sa.Column("raw_order", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint(
            "provider_endpoint_run_binding_id",
            "raw_object_id",
            name="pk_provider_endpoint_binding_raw",
        ),
        sa.ForeignKeyConstraint(
            ["provider_endpoint_run_binding_id"],
            ["provider_endpoint_run_binding.provider_endpoint_run_binding_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["raw_object_id"], ["raw_object.raw_object_id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint(
            "provider_endpoint_run_binding_id",
            "raw_order",
            name="uq_provider_endpoint_binding_raw_order",
        ),
        sa.CheckConstraint("raw_order >= 0", name="ck_provider_endpoint_binding_raw_order"),
    )
    op.create_index(
        "ix_provider_endpoint_binding_raw_object",
        "provider_endpoint_run_binding_raw_object",
        ["raw_object_id"],
    )


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text(
            "LOCK TABLE provider_endpoint_run_binding_raw_object, "
            "provider_endpoint_run_binding, source_admission_receipt, "
            "adapter_implementation_fingerprint, provider_endpoint_definition "
            "IN ACCESS EXCLUSIVE MODE"
        )
    )
    has_records = connection.execute(
        sa.text(
            "SELECT EXISTS ("
            "SELECT 1 FROM provider_endpoint_definition UNION ALL "
            "SELECT 1 FROM adapter_implementation_fingerprint UNION ALL "
            "SELECT 1 FROM source_admission_receipt UNION ALL "
            "SELECT 1 FROM provider_endpoint_run_binding UNION ALL "
            "SELECT 1 FROM provider_endpoint_run_binding_raw_object"
            ")"
        )
    ).scalar_one()
    if has_records:
        raise RuntimeError(
            "cannot downgrade Provider Endpoint Admission while immutable admission records exist"
        )

    op.drop_index(
        "ix_provider_endpoint_binding_raw_object",
        table_name="provider_endpoint_run_binding_raw_object",
    )
    op.drop_table("provider_endpoint_run_binding_raw_object")
    op.drop_index("ix_provider_endpoint_binding_hash", table_name="provider_endpoint_run_binding")
    op.drop_index("ix_provider_endpoint_binding_dataset", table_name="provider_endpoint_run_binding")
    op.drop_index("ix_provider_endpoint_binding_endpoint", table_name="provider_endpoint_run_binding")
    op.drop_table("provider_endpoint_run_binding")
    op.drop_index("ix_source_admission_receipt_hash", table_name="source_admission_receipt")
    op.drop_index("ix_source_admission_level_status_valid", table_name="source_admission_receipt")
    op.drop_index("ix_source_admission_endpoint_dataset", table_name="source_admission_receipt")
    op.drop_table("source_admission_receipt")
    op.drop_index(
        "ix_adapter_implementation_fingerprint_hash",
        table_name="adapter_implementation_fingerprint",
    )
    op.drop_index("ix_adapter_fingerprint_endpoint", table_name="adapter_implementation_fingerprint")
    op.drop_table("adapter_implementation_fingerprint")
    op.drop_index("ix_provider_endpoint_definition_hash", table_name="provider_endpoint_definition")
    op.drop_index("ix_provider_endpoint_provider_version", table_name="provider_endpoint_definition")
    op.drop_table("provider_endpoint_definition")
