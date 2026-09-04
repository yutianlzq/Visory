"""Add WP-0203 canonical normalization control-plane tables."""
from __future__ import annotations
from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0009_wp0203_core_canonical_normalization"
down_revision: str | Sequence[str] | None = "0008_wp0202_raw_schema_hardening"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "canonical_mapping_definition",
        sa.Column("provider_id", sa.String(64), nullable=False),
        sa.Column("dataset_id", sa.String(64), nullable=False),
        sa.Column("dataset_schema_version", sa.String(32), nullable=False),
        sa.Column("mapping_version", sa.String(32), nullable=False),
        sa.Column("source_fields", postgresql.JSONB(), nullable=False),
        sa.Column("source_field_types", postgresql.JSONB(), nullable=False),
        sa.Column("target_fields", postgresql.JSONB(), nullable=False),
        sa.Column("target_field_types", postgresql.JSONB(), nullable=False),
        sa.Column("target_units", postgresql.JSONB(), nullable=False),
        sa.Column("unit_multipliers", postgresql.JSONB(), nullable=False),
        sa.Column("enum_mappings", postgresql.JSONB(), nullable=False),
        sa.Column("null_semantics", postgresql.JSONB(), nullable=False),
        sa.Column("time_semantics", postgresql.JSONB(), nullable=False),
        sa.Column("mapping_hash", sa.String(71), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("provider_id", "dataset_id", "dataset_schema_version", "mapping_version", name="pk_canonical_mapping_definition"),
        sa.ForeignKeyConstraint(["provider_id"], ["provider_definition.provider_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["dataset_id", "dataset_schema_version"], ["dataset_definition.dataset_id", "dataset_definition.schema_version"], ondelete="RESTRICT"),
        sa.CheckConstraint("mapping_hash ~ '^sha256:[0-9a-f]{64}$'", name="ck_canonical_mapping_hash"),
    )
    op.create_table(
        "canonical_quality_report",
        sa.Column("quality_report_id", sa.String(64), primary_key=True),
        sa.Column("canonical_partition_id", sa.String(64)),
        sa.Column("quality_status", sa.String(16), nullable=False),
        sa.Column("rule_results", postgresql.JSONB(), nullable=False),
        sa.Column("row_count", sa.BigInteger(), nullable=False),
        sa.Column("rejected_row_count", sa.BigInteger(), nullable=False),
        sa.Column("duplicate_key_count", sa.BigInteger(), nullable=False),
        sa.Column("identity_unresolved_count", sa.BigInteger(), nullable=False),
        sa.Column("identity_ambiguous_count", sa.BigInteger(), nullable=False),
        sa.Column("failure_reasons", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("row_count >= 0 AND rejected_row_count >= 0", name="ck_canonical_quality_counts"),
    )
    op.create_table(
        "canonical_partition",
        sa.Column("canonical_partition_id", sa.String(64), primary_key=True),
        sa.Column("dataset_id", sa.String(64), nullable=False),
        sa.Column("dataset_schema_version", sa.String(32), nullable=False),
        sa.Column("partition_key", sa.String(255), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("revision_kind", sa.String(16), nullable=False),
        sa.Column("supersedes_id", sa.String(64)),
        sa.Column("provider_policy_version", sa.String(32), nullable=False),
        sa.Column("provider_run_id", sa.String(64), nullable=False),
        sa.Column("raw_object_id", sa.String(64), nullable=False),
        sa.Column("available_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("available_to", sa.DateTime(timezone=True)),
        sa.Column("row_count", sa.BigInteger(), nullable=False),
        sa.Column("security_count", sa.BigInteger(), nullable=False),
        sa.Column("storage_backend", sa.String(32), nullable=False),
        sa.Column("storage_namespace", sa.String(32), nullable=False),
        sa.Column("relative_path", sa.String(1024), nullable=False, unique=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("partition_hash", sa.String(71), nullable=False),
        sa.Column("schema_hash", sa.String(71), nullable=False),
        sa.Column("quality_status", sa.String(16), nullable=False),
        sa.Column("quality_report_id", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["dataset_id", "dataset_schema_version"], ["dataset_definition.dataset_id", "dataset_definition.schema_version"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["provider_run_id"], ["provider_run.provider_run_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["raw_object_id"], ["raw_object.raw_object_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["quality_report_id"], ["canonical_quality_report.quality_report_id"], ondelete="RESTRICT", deferrable=True, initially="DEFERRED"),
        sa.ForeignKeyConstraint(["supersedes_id"], ["canonical_partition.canonical_partition_id"], ondelete="RESTRICT"),
        sa.CheckConstraint("revision >= 1", name="ck_canonical_partition_revision"),
        sa.CheckConstraint("partition_hash ~ '^sha256:[0-9a-f]{64}$' AND schema_hash ~ '^sha256:[0-9a-f]{64}$'", name="ck_canonical_partition_hashes"),
    )
    op.create_foreign_key(
        "fk_quality_report_partition",
        "canonical_quality_report",
        "canonical_partition",
        ["canonical_partition_id"],
        ["canonical_partition_id"],
        ondelete="SET NULL",
        deferrable=True,
        initially="DEFERRED",
    )
    op.create_table(
        "canonical_partition_lineage",
        sa.Column("canonical_partition_id", sa.String(64), primary_key=True),
        sa.Column("provider_run_id", sa.String(64), primary_key=True),
        sa.Column("raw_object_id", sa.String(64), primary_key=True),
        sa.ForeignKeyConstraint(["canonical_partition_id"], ["canonical_partition.canonical_partition_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["provider_run_id"], ["provider_run.provider_run_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["raw_object_id"], ["raw_object.raw_object_id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_canonical_partition_dataset", "canonical_partition", ["dataset_id", "partition_key", "revision"])


def downgrade() -> None:
    op.drop_index("ix_canonical_partition_dataset", table_name="canonical_partition")
    op.drop_table("canonical_partition_lineage")
    op.drop_constraint("fk_quality_report_partition", "canonical_quality_report", type_="foreignkey")
    op.drop_table("canonical_partition")
    op.drop_table("canonical_quality_report")
    op.drop_table("canonical_mapping_definition")
