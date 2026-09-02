"""Add provider-native raw schema definitions and coordinated rate-limit windows."""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0008_wp0202_raw_schema_hardening"
down_revision: str | Sequence[str] | None = "0007_wp0202_raw_ingestion"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "provider_raw_schema_definition",
        sa.Column("provider_id", sa.String(64), nullable=False),
        sa.Column("adapter_version", sa.String(32), nullable=False),
        sa.Column("dataset_id", sa.String(64), nullable=False),
        sa.Column("dataset_schema_version", sa.String(32), nullable=False),
        sa.Column("provider_schema_version", sa.String(32), nullable=False),
        sa.Column("required_fields", postgresql.JSONB(), nullable=False),
        sa.Column("optional_fields", postgresql.JSONB(), nullable=False),
        sa.Column("field_types", postgresql.JSONB(), nullable=False),
        sa.Column("expected_schema_hash", sa.String(71), nullable=False),
        sa.PrimaryKeyConstraint(
            "provider_id",
            "adapter_version",
            "dataset_id",
            "dataset_schema_version",
            "provider_schema_version",
            name="pk_provider_raw_schema_definition",
        ),
        sa.ForeignKeyConstraint(["provider_id"], ["provider_definition.provider_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["dataset_id", "dataset_schema_version"],
            ["dataset_definition.dataset_id", "dataset_definition.schema_version"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("adapter_version ~ '^[0-9]+\\.[0-9]+\\.[0-9]+$'", name="ck_raw_schema_adapter_version"),
        sa.CheckConstraint("dataset_schema_version ~ '^[0-9]+\\.[0-9]+\\.[0-9]+$'", name="ck_raw_schema_dataset_version"),
        sa.CheckConstraint("provider_schema_version ~ '^[0-9]+\\.[0-9]+\\.[0-9]+$'", name="ck_raw_schema_provider_version"),
        sa.CheckConstraint("expected_schema_hash ~ '^sha256:[0-9a-f]{64}$'", name="ck_raw_schema_hash"),
    )
    op.create_table(
        "provider_rate_limit_window",
        sa.Column("provider_id", sa.String(64), nullable=False),
        sa.Column("dataset_id", sa.String(64), nullable=False),
        sa.Column("market", sa.String(32), nullable=False),
        sa.Column("frequency", sa.String(32), nullable=False),
        sa.Column("window_epoch", sa.BigInteger(), nullable=False),
        sa.Column("request_count", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("provider_id", "dataset_id", "market", "frequency", name="pk_provider_rate_limit_window"),
        sa.ForeignKeyConstraint(["provider_id"], ["provider_definition.provider_id"], ondelete="RESTRICT"),
        sa.CheckConstraint("window_epoch >= 0", name="ck_rate_limit_window_epoch"),
        sa.CheckConstraint("request_count >= 0", name="ck_rate_limit_request_count"),
    )
    op.create_index(
        "ix_provider_raw_schema_dataset",
        "provider_raw_schema_definition",
        ["dataset_id", "dataset_schema_version"],
    )


def downgrade() -> None:
    op.drop_index("ix_provider_raw_schema_dataset", table_name="provider_raw_schema_definition")
    op.drop_table("provider_rate_limit_window")
    op.drop_table("provider_raw_schema_definition")
