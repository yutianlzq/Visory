"""Add WP-0203 extended canonical dataset lineage columns."""
from __future__ import annotations
from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0010_wp0203_extended_canonical_datasets"
down_revision: str | Sequence[str] | None = "0009_wp0203_core_canonical_normalization"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("canonical_quality_report", sa.Column("task_id", sa.String(64), nullable=True))
    op.add_column("canonical_quality_report", sa.Column("attempt_id", sa.String(64), nullable=True))
    op.add_column("canonical_quality_report", sa.Column("dataset_id", sa.String(64), nullable=True))
    op.add_column("canonical_quality_report", sa.Column("dataset_schema_version", sa.String(32), nullable=True))
    op.add_column("canonical_quality_report", sa.Column("mapping_version", sa.String(32), nullable=True))
    op.add_column("canonical_quality_report", sa.Column("mapping_hash", sa.String(71), nullable=True))
    op.add_column("canonical_quality_report", sa.Column("provider_run_refs", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")))
    op.add_column("canonical_quality_report", sa.Column("raw_object_refs", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")))
    op.create_check_constraint("ck_canonical_quality_mapping_hash", "canonical_quality_report", "mapping_hash IS NULL OR mapping_hash ~ '^sha256:[0-9a-f]{64}$'")
    op.create_index("ix_canonical_quality_dataset", "canonical_quality_report", ["dataset_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_canonical_quality_dataset", table_name="canonical_quality_report")
    op.drop_constraint("ck_canonical_quality_mapping_hash", "canonical_quality_report", type_="check")
    for name in ("raw_object_refs", "provider_run_refs", "mapping_hash", "mapping_version", "dataset_schema_version", "dataset_id", "attempt_id", "task_id"):
        op.drop_column("canonical_quality_report", name)
