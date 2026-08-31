"""Create WP-0202 append-only raw ingestion registry."""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0007_wp0202_raw_ingestion"
down_revision: str | Sequence[str] | None = "0006_wp0201_registry_contract_hardening"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "provider_run",
        sa.Column("provider_run_id", sa.String(64), primary_key=True),
        sa.Column("provider_id", sa.String(64), nullable=False),
        sa.Column("actual_upstream", sa.String(255)),
        sa.Column("dataset_id", sa.String(64), nullable=False),
        sa.Column("dataset_schema_version", sa.String(32), nullable=False),
        sa.Column("provider_policy_id", sa.String(64), nullable=False),
        sa.Column("provider_policy_version", sa.String(32), nullable=False),
        sa.Column("adapter_version", sa.String(32), nullable=False),
        sa.Column("capability_market", sa.String(32), nullable=False),
        sa.Column("capability_frequency", sa.String(32), nullable=False),
        sa.Column("task_id", sa.String(64), nullable=False),
        sa.Column("attempt_id", sa.String(64), nullable=False),
        sa.Column("request_fingerprint", sa.String(71), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("observed_schema_hash", sa.String(71)),
        sa.Column("row_count", sa.BigInteger()),
        sa.Column("byte_count", sa.BigInteger()),
        sa.Column("run_outcome", sa.String(16)),
        sa.Column("failure_code", sa.String(64)),
        sa.Column("failure_detail_redacted", sa.String(512)),
        sa.Column("raw_object_refs", postgresql.JSONB(), nullable=False),
        sa.ForeignKeyConstraint(["provider_id"], ["provider_definition.provider_id"]),
        sa.ForeignKeyConstraint(["dataset_id", "dataset_schema_version"], ["dataset_definition.dataset_id", "dataset_definition.schema_version"]),
        sa.ForeignKeyConstraint(["provider_policy_id"], ["provider_policy.provider_policy_id"]),
        sa.ForeignKeyConstraint(["task_id"], ["platform_task.task_id"], deferrable=True, initially="DEFERRED"),
        sa.ForeignKeyConstraint(["attempt_id"], ["task_attempt.attempt_id"], deferrable=True, initially="DEFERRED"),
        sa.ForeignKeyConstraint(
            ["provider_id", "dataset_id", "dataset_schema_version", "capability_market", "capability_frequency"],
            ["provider_capability.provider_id", "provider_capability.dataset_id", "provider_capability.dataset_schema_version", "provider_capability.market", "provider_capability.frequency"],
        ),
        sa.CheckConstraint("provider_run_id ~ '^prun_[0-9a-f-]{36}$'", name="ck_provider_run_id"),
        sa.CheckConstraint("run_outcome IS NULL OR run_outcome IN ('SUCCEEDED','DEGRADED','FAILED','CANCELLED')", name="ck_provider_run_outcome"),
        sa.CheckConstraint("row_count IS NULL OR row_count >= 0", name="ck_provider_run_row_count"),
        sa.CheckConstraint("byte_count IS NULL OR byte_count >= 0", name="ck_provider_run_byte_count"),
        sa.CheckConstraint("finished_at IS NULL OR finished_at >= started_at", name="ck_provider_run_finished_at"),
    )
    op.create_table(
        "raw_object",
        sa.Column("raw_object_id", sa.String(64), primary_key=True),
        sa.Column("provider_run_id", sa.String(64), nullable=False),
        sa.Column("provider_id", sa.String(64), nullable=False),
        sa.Column("actual_upstream", sa.String(255), nullable=False),
        sa.Column("dataset_id", sa.String(64), nullable=False),
        sa.Column("dataset_schema_version", sa.String(32), nullable=False),
        sa.Column("request_fingerprint", sa.String(71), nullable=False),
        sa.Column("storage_backend", sa.String(32), nullable=False),
        sa.Column("storage_namespace", sa.String(32), nullable=False),
        sa.Column("relative_path", sa.String(1024), nullable=False),
        sa.Column("raw_content_hash", sa.String(71), nullable=False),
        sa.Column("media_type", sa.String(255), nullable=False),
        sa.Column("compression", sa.String(16), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_published_at", sa.DateTime(timezone=True)),
        sa.Column("provider_schema_version", sa.String(32), nullable=False),
        sa.Column("observed_schema_hash", sa.String(71), nullable=False),
        sa.Column("row_count", sa.BigInteger(), nullable=False),
        sa.Column("byte_count", sa.BigInteger(), nullable=False),
        sa.Column("retention_class", sa.String(16), nullable=False),
        sa.ForeignKeyConstraint(["provider_run_id"], ["provider_run.provider_run_id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("provider_run_id", name="uq_raw_object_provider_run"),
        sa.UniqueConstraint("relative_path", name="uq_raw_object_relative_path"),
        sa.CheckConstraint("raw_object_id ~ '^raw_[0-9a-f-]{36}$'", name="ck_raw_object_id"),
        sa.CheckConstraint("retention_class = 'PINNED'", name="ck_raw_object_retention_pinned"),
        sa.CheckConstraint("compression IN ('NONE','GZIP')", name="ck_raw_object_compression"),
        sa.CheckConstraint("row_count >= 0 AND byte_count >= 0", name="ck_raw_object_counts"),
        sa.CheckConstraint("ingested_at >= observed_at", name="ck_raw_object_ingested_at"),
    )
    op.create_table(
        "raw_ingestion_quarantine",
        sa.Column("raw_ingestion_quarantine_id", sa.String(64), primary_key=True),
        sa.Column("provider_run_id", sa.String(64), nullable=False),
        sa.Column("classification", sa.String(32), nullable=False),
        sa.Column("reason_code", sa.String(64), nullable=False),
        sa.Column("quarantine_status", sa.String(16), nullable=False),
        sa.Column("observed_schema_hash", sa.String(71)),
        sa.Column("expected_schema_hash", sa.String(71), nullable=False),
        sa.Column("storage_backend", sa.String(32), nullable=False),
        sa.Column("storage_namespace", sa.String(32), nullable=False),
        sa.Column("relative_path", sa.String(1024), nullable=False),
        sa.Column("evidence_hash", sa.String(71), nullable=False),
        sa.Column("evidence_media_type", sa.String(255), nullable=False),
        sa.Column("evidence_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("failure_detail_redacted", sa.String(512)),
        sa.ForeignKeyConstraint(["provider_run_id"], ["provider_run.provider_run_id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("provider_run_id", name="uq_raw_quarantine_provider_run"),
        sa.UniqueConstraint("relative_path", name="uq_raw_quarantine_relative_path"),
        sa.CheckConstraint("raw_ingestion_quarantine_id ~ '^rawq_[0-9a-f-]{36}$'", name="ck_raw_quarantine_id"),
        sa.CheckConstraint("classification IN ('ADDITIVE_DRIFT','BREAKING_DRIFT','UNKNOWN_SCHEMA')", name="ck_raw_quarantine_classification"),
        sa.CheckConstraint("quarantine_status IN ('OPEN','RESOLVED','REJECTED')", name="ck_raw_quarantine_status"),
        sa.CheckConstraint("evidence_size_bytes >= 0", name="ck_raw_quarantine_size"),
    )
    op.create_index("ix_provider_run_task_attempt", "provider_run", ["task_id", "attempt_id"])
    op.create_index("ix_provider_run_dataset_started", "provider_run", ["dataset_id", "dataset_schema_version", "started_at"])
    op.create_index("ix_raw_object_dataset_ingested", "raw_object", ["dataset_id", "dataset_schema_version", "ingested_at"])


def downgrade() -> None:
    # Database schema only: raw files and post-rename orphans are intentionally retained for audit/recovery.
    op.drop_index("ix_raw_object_dataset_ingested", table_name="raw_object")
    op.drop_index("ix_provider_run_dataset_started", table_name="provider_run")
    op.drop_index("ix_provider_run_task_attempt", table_name="provider_run")
    op.drop_table("raw_ingestion_quarantine")
    op.drop_table("raw_object")
    op.drop_table("provider_run")
