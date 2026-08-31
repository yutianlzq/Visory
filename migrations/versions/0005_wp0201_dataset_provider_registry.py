"""Create WP-0201 dataset/provider registry."""
from __future__ import annotations
from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005_wp0201_dataset_provider_registry"
down_revision: str | Sequence[str] | None = "0004_wp0103_durable_task_control_plane"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "provider_definition",
        sa.Column("provider_id", sa.String(64), primary_key=True),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("adapter_name", sa.String(64), nullable=False),
        sa.Column("adapter_version", sa.String(32), nullable=False),
        sa.Column("provider_kind", sa.String(16), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("credential_ref", sa.String(255)),
        sa.Column("actual_upstream", sa.String(255)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("provider_id ~ '^[a-z][a-z0-9_]{1,63}$'", name="ck_provider_id"),
        sa.CheckConstraint("adapter_name IN ('a_stock_data','financial_api')", name="ck_provider_adapter"),
        sa.CheckConstraint("adapter_version ~ '^[0-9]+\\.[0-9]+\\.[0-9]+$'", name="ck_provider_adapter_version"),
        sa.CheckConstraint("provider_kind IN ('AGGREGATOR','DIRECT','FILE','INTERNAL')", name="ck_provider_kind"),
        sa.CheckConstraint("credential_ref IS NULL OR credential_ref LIKE 'secret://%'", name="ck_provider_credential_ref"),
        sa.CheckConstraint("(provider_kind <> 'AGGREGATOR') OR actual_upstream IS NOT NULL", name="ck_provider_actual_upstream"),
        sa.CheckConstraint("updated_at >= created_at", name="ck_provider_updated_at"),
    )
    op.create_table(
        "dataset_definition",
        sa.Column("dataset_id", sa.String(64), primary_key=True),
        sa.Column("schema_version", sa.String(32), nullable=False),
        sa.Column("entity_scope", sa.String(64), nullable=False),
        sa.Column("frequency", sa.String(32), nullable=False),
        sa.Column("primary_key_fields", postgresql.JSONB(), nullable=False),
        sa.Column("required_fields", postgresql.JSONB(), nullable=False),
        sa.Column("optional_fields", postgresql.JSONB(), nullable=False),
        sa.Column("field_types", postgresql.JSONB(), nullable=False),
        sa.Column("units", postgresql.JSONB(), nullable=False),
        sa.Column("enum_domains", postgresql.JSONB(), nullable=False),
        sa.Column("time_semantics", postgresql.JSONB(), nullable=False),
        sa.Column("null_semantics", postgresql.JSONB(), nullable=False),
        sa.Column("partition_template", sa.String(255), nullable=False),
        sa.Column("quality_rule_ids", postgresql.JSONB(), nullable=False),
        sa.Column("owner_module", sa.String(255), nullable=False),
        sa.CheckConstraint("dataset_id ~ '^[a-z][a-z0-9_]{1,63}$'", name="ck_dataset_id"),
        sa.CheckConstraint("schema_version ~ '^[0-9]+\\.[0-9]+\\.[0-9]+$'", name="ck_dataset_schema_version"),
        sa.UniqueConstraint("dataset_id", "schema_version", name="uq_dataset_schema"),
    )
    op.create_table(
        "provider_capability",
        sa.Column("provider_id", sa.String(64), nullable=False),
        sa.Column("dataset_id", sa.String(64), nullable=False),
        sa.Column("market", sa.String(32), nullable=False),
        sa.Column("frequency", sa.String(32), nullable=False),
        sa.Column("supported_fields", postgresql.JSONB(), nullable=False),
        sa.Column("history_start", sa.DateTime(timezone=True)),
        sa.Column("freshness_sla_seconds", sa.Integer(), nullable=False),
        sa.Column("rate_limit_profile", postgresql.JSONB(), nullable=False),
        sa.Column("provider_capability_status", sa.String(16), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("provider_id", "dataset_id", "market", "frequency"),
        sa.ForeignKeyConstraint(["provider_id"], ["provider_definition.provider_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["dataset_id"], ["dataset_definition.dataset_id"], ondelete="CASCADE"),
        sa.CheckConstraint("provider_capability_status IN ('AVAILABLE','DEGRADED','UNAVAILABLE','UNVERIFIED')", name="ck_capability_status"),
        sa.CheckConstraint("freshness_sla_seconds >= 0", name="ck_capability_sla"),
    )
    op.create_table(
        "provider_policy",
        sa.Column("provider_policy_id", sa.String(64), primary_key=True),
        sa.Column("dataset_id", sa.String(64), nullable=False),
        sa.Column("policy_version", sa.String(32), nullable=False),
        sa.Column("primary_provider_id", sa.String(64), nullable=False),
        sa.Column("supplemental_provider_ids", postgresql.JSONB(), nullable=False),
        sa.Column("allowed_merge_mode", sa.String(32), nullable=False),
        sa.Column("fallback_triggers", postgresql.JSONB(), nullable=False),
        sa.Column("field_authority_map", postgresql.JSONB(), nullable=False),
        sa.Column("conflict_tolerance", postgresql.JSONB(), nullable=False),
        sa.Column("freshness_sla_seconds", sa.Integer(), nullable=False),
        sa.Column("required_quality_rules", postgresql.JSONB(), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_to", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["dataset_id"], ["dataset_definition.dataset_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["primary_provider_id"], ["provider_definition.provider_id"]),
        sa.CheckConstraint("provider_policy_id ~ '^[a-z][a-z0-9_]{1,63}$'", name="ck_policy_id"),
        sa.CheckConstraint("policy_version ~ '^[0-9]+\\.[0-9]+\\.[0-9]+$'", name="ck_policy_version"),
        sa.CheckConstraint("allowed_merge_mode IN ('REPLACE_PARTITION','APPEND_DISJOINT','ENRICH_FIELDS','COMPARE_ONLY')", name="ck_policy_merge_mode"),
        sa.CheckConstraint("freshness_sla_seconds >= 0", name="ck_policy_sla"),
        sa.CheckConstraint("effective_to IS NULL OR effective_to > effective_from", name="ck_policy_effective_interval"),
        sa.UniqueConstraint("dataset_id", "policy_version", name="uq_policy_dataset_version"),
    )
    op.create_index("ix_provider_capability_dataset", "provider_capability", ["dataset_id", "provider_capability_status"])
    op.create_index("ix_provider_policy_effective", "provider_policy", ["dataset_id", "effective_from", "effective_to"])
    # PostgreSQL GiST exclusion prevents overlapping effective policy intervals per dataset.
    op.execute("""
        ALTER TABLE provider_policy
        ADD CONSTRAINT ex_provider_policy_effective_no_overlap
        EXCLUDE USING gist (
            dataset_id WITH =,
            tstzrange(effective_from, COALESCE(effective_to, 'infinity'::timestamptz), '[)'::text) WITH &&
        )
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE provider_policy DROP CONSTRAINT IF EXISTS ex_provider_policy_effective_no_overlap")
    op.drop_index("ix_provider_policy_effective", table_name="provider_policy")
    op.drop_index("ix_provider_capability_dataset", table_name="provider_capability")
    op.drop_table("provider_policy")
    op.drop_table("provider_capability")
    op.drop_table("dataset_definition")
    op.drop_table("provider_definition")
