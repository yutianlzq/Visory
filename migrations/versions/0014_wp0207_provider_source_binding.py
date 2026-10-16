"""Bind new ProviderRun records to immutable source-route evidence.

Revision ID: 0014_wp0207_source_binding
Revises: 0013_wp0302_feature_store
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0014_wp0207_source_binding"
down_revision = "0013_wp0302_feature_store"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "provider_run",
        sa.Column("source_route_evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("provider_run", "source_route_evidence")
