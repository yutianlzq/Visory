"""Add WP-0204 immutable snapshot foundation and capability gate."""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0011_wp0204_snapshot_foundation"
down_revision: str | Sequence[str] | None = "0010_wp0203_extended_canonical_datasets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "data_snapshot",
        sa.Column("snapshot_id", sa.String(64), primary_key=True),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("cutoff_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("provider_policy_id", sa.String(64), nullable=False),
        sa.Column("provider_policy_version", sa.String(32), nullable=False),
        sa.Column("security_master_ref", sa.String(64), nullable=False),
        sa.Column("calendar_ref", sa.String(64), nullable=False),
        sa.Column("quality_report_refs", postgresql.JSONB(), nullable=False),
        sa.Column("quality_status", sa.String(16), nullable=False),
        sa.Column("publication_status", sa.String(16), nullable=False),
        sa.Column("certified_capabilities", postgresql.JSONB(), nullable=False),
        sa.Column("missing_capabilities", postgresql.JSONB(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("revision_kind", sa.String(16), nullable=False),
        sa.Column("supersedes_id", sa.String(64)),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("manifest_version", sa.String(32), nullable=False),
        sa.Column("manifest_hash", sa.String(71), nullable=False),
        sa.Column("content_hash", sa.String(71), nullable=False),
        sa.Column("task_id", sa.String(64)),
        sa.Column("attempt_id", sa.String(64)),
        sa.ForeignKeyConstraint(["provider_policy_id"], ["provider_policy.provider_policy_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["security_master_ref"], ["canonical_partition.canonical_partition_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["calendar_ref"], ["canonical_partition.canonical_partition_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["supersedes_id"], ["data_snapshot.snapshot_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["task_id"], ["platform_task.task_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["attempt_id"], ["task_attempt.attempt_id"], ondelete="RESTRICT"),
        sa.CheckConstraint("revision >= 1", name="ck_data_snapshot_revision"),
        sa.CheckConstraint("available_at <= cutoff_at", name="ck_data_snapshot_available_at"),
        sa.CheckConstraint("manifest_hash ~ '^sha256:[0-9a-f]{64}$' AND content_hash ~ '^sha256:[0-9a-f]{64}$'", name="ck_data_snapshot_hashes"),
        sa.CheckConstraint("publication_status IN ('PROVISIONAL','CERTIFIED','REJECTED')", name="ck_data_snapshot_publication_status"),
        sa.CheckConstraint("quality_status <> 'FAILED' OR publication_status = 'REJECTED'", name="ck_data_snapshot_quality_gate"),
        sa.CheckConstraint("publication_status <> 'CERTIFIED' OR published_at IS NOT NULL", name="ck_data_snapshot_certified_published"),
        sa.CheckConstraint("publication_status <> 'REJECTED' OR published_at IS NULL", name="ck_data_snapshot_rejected_unpublished"),
        sa.CheckConstraint("published_at IS NULL OR published_at >= created_at", name="ck_data_snapshot_publish_time"),
        sa.CheckConstraint("revision_kind <> 'CORRECTION' OR supersedes_id IS NOT NULL", name="ck_data_snapshot_correction_target"),
        sa.CheckConstraint("revision_kind = 'CORRECTION' OR supersedes_id IS NULL", name="ck_data_snapshot_initial_no_target"),
    )
    op.create_table(
        "snapshot_partition_ref",
        sa.Column("snapshot_id", sa.String(64), primary_key=True),
        sa.Column("canonical_partition_id", sa.String(64), primary_key=True),
        sa.Column("dataset_id", sa.String(64), nullable=False),
        sa.Column("dataset_schema_version", sa.String(32), nullable=False),
        sa.Column("provider_policy_version", sa.String(32), nullable=False),
        sa.Column("partition_key", sa.String(255), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("revision_kind", sa.String(16), nullable=False),
        sa.Column("storage_backend", sa.String(32), nullable=False),
        sa.Column("storage_namespace", sa.String(32), nullable=False),
        sa.Column("relative_path", sa.String(1024), nullable=False),
        sa.Column("media_type", sa.String(255), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("partition_hash", sa.String(71), nullable=False),
        sa.Column("schema_hash", sa.String(71), nullable=False),
        sa.Column("quality_report_id", sa.String(64), nullable=False),
        sa.Column("quality_status", sa.String(16), nullable=False),
        sa.Column("provider_run_refs", postgresql.JSONB(), nullable=False),
        sa.Column("raw_object_refs", postgresql.JSONB(), nullable=False),
        sa.Column("min_available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("max_available_at", sa.DateTime(timezone=True)),
        sa.Column("row_count", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(["snapshot_id"], ["data_snapshot.snapshot_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["canonical_partition_id"], ["canonical_partition.canonical_partition_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["quality_report_id"], ["canonical_quality_report.quality_report_id"], ondelete="RESTRICT"),
        sa.CheckConstraint("partition_hash ~ '^sha256:[0-9a-f]{64}$' AND schema_hash ~ '^sha256:[0-9a-f]{64}$'", name="ck_snapshot_partition_hashes"),
        sa.CheckConstraint("row_count >= 0", name="ck_snapshot_partition_row_count"),
    )
    op.create_index("ix_snapshot_trade_date", "data_snapshot", ["trade_date", "publication_status", "revision"])
    op.create_index("ix_snapshot_partition_dataset", "snapshot_partition_ref", ["dataset_id", "partition_key", "revision"])
    op.create_table(
        "capability_certification",
        sa.Column("capability_id", sa.String(64), primary_key=True),
        sa.Column("snapshot_id", sa.String(64), primary_key=True),
        sa.Column("capability_status", sa.String(16), nullable=False),
        sa.Column("reason_code", sa.String(64)),
        sa.Column("evidence_refs", postgresql.JSONB(), nullable=False),
        sa.Column("certified_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["snapshot_id"], ["data_snapshot.snapshot_id"], ondelete="CASCADE"),
        sa.CheckConstraint("capability_status IN ('CERTIFIED','UNAVAILABLE','DEGRADED','UNVERIFIED')", name="ck_capability_certification_status"),
    )
    op.create_table(
        "consumer_requirement",
        sa.Column("consumer_id", sa.String(64), primary_key=True),
        sa.Column("consumer_kind", sa.String(32), nullable=False),
        sa.Column("required_capabilities", postgresql.JSONB(), nullable=False),
        sa.Column("accepted_publication_statuses", postgresql.JSONB(), nullable=False),
        sa.Column("min_quality_status", sa.String(16), nullable=False),
        sa.Column("allow_provisional", sa.Boolean(), nullable=False),
        sa.Column("requirement_version", sa.String(32), nullable=False),
    )
    op.create_table(
        "snapshot_current_pointer",
        sa.Column("scope", sa.String(64), primary_key=True),
        sa.Column("trade_date", sa.Date(), primary_key=True),
        sa.Column("capability_id", sa.String(64), primary_key=True),
        sa.Column("snapshot_id", sa.String(64), nullable=False),
        sa.Column("previous_snapshot_id", sa.String(64)),
        sa.Column("pointer_revision", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["snapshot_id"], ["data_snapshot.snapshot_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["previous_snapshot_id"], ["data_snapshot.snapshot_id"], ondelete="RESTRICT"),
        sa.CheckConstraint("pointer_revision >= 1", name="ck_snapshot_pointer_revision"),
    )


def downgrade() -> None:
    op.drop_table("snapshot_current_pointer")
    op.drop_table("consumer_requirement")
    op.drop_table("capability_certification")
    op.drop_index("ix_snapshot_partition_dataset", table_name="snapshot_partition_ref")
    op.drop_index("ix_snapshot_trade_date", table_name="data_snapshot")
    op.drop_table("snapshot_partition_ref")
    op.drop_table("data_snapshot")
