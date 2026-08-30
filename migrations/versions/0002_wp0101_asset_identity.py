"""Create WP-0101 asset identity, alias, and quarantine tables.

Revision ID: 0002_wp0101_asset_identity
Revises: 0001_wp0002_baseline
Create Date: 2026-08-30
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0002_wp0101_asset_identity"
down_revision: str | Sequence[str] | None = "0001_wp0002_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.create_table(
        "asset_identity",
        sa.Column("entity_key", sa.String(length=160), primary_key=True),
        sa.Column("asset_type", sa.String(length=32), nullable=False),
        sa.Column("canonical_id", sa.String(length=128), nullable=False),
        sa.Column("exchange", sa.String(length=16), nullable=False),
        sa.Column("market", sa.String(length=16), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("country", sa.String(length=2), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("list_date", sa.Date(), nullable=True),
        sa.Column("delist_date", sa.Date(), nullable=True),
        sa.Column("identity_status", sa.String(length=16), nullable=False),
        sa.Column("schema_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("entity_key = asset_type || ':' || canonical_id", name="ck_asset_identity_entity_key"),
        sa.CheckConstraint(
            "asset_type IN ('stock','index','etf','convertible_bond','fund','future','fx','commodity')",
            name="ck_asset_identity_asset_type",
        ),
        sa.CheckConstraint("canonical_id ~ '^[a-z][a-z0-9._-]*$'", name="ck_asset_identity_canonical_id"),
        sa.CheckConstraint("exchange ~ '^[A-Z][A-Z0-9_]{1,15}$'", name="ck_asset_identity_exchange"),
        sa.CheckConstraint("market ~ '^[A-Z][A-Z0-9_]{1,15}$'", name="ck_asset_identity_market"),
        sa.CheckConstraint("valid_to IS NULL OR valid_to > valid_from", name="ck_asset_identity_validity"),
        sa.CheckConstraint("delist_date IS NULL OR list_date IS NULL OR delist_date >= list_date", name="ck_asset_identity_listing"),
        sa.CheckConstraint("identity_status IN ('ACTIVE','INACTIVE','DELISTED','QUARANTINED')", name="ck_asset_identity_status"),
        sa.CheckConstraint("currency ~ '^[A-Z]{3}$'", name="ck_asset_identity_currency"),
        sa.CheckConstraint("country ~ '^[A-Z]{2}$'", name="ck_asset_identity_country"),
        sa.CheckConstraint("schema_version ~ '^[0-9]+\\.[0-9]+\\.[0-9]+$'", name="ck_asset_identity_schema_version"),
        sa.UniqueConstraint("asset_type", "canonical_id", name="uq_asset_identity_type_canonical"),
    )
    op.create_table(
        "asset_alias",
        sa.Column("alias_id", sa.String(length=128), primary_key=True),
        sa.Column("entity_key", sa.String(length=160), sa.ForeignKey("asset_identity.entity_key", ondelete="RESTRICT"), nullable=False),
        sa.Column("alias_type", sa.String(length=32), nullable=False),
        sa.Column("namespace", sa.String(length=128), nullable=False),
        sa.Column("alias_value", sa.Text(), nullable=False),
        sa.Column("normalized_value", sa.Text(), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_provider", sa.String(length=128), nullable=False),
        sa.Column("actual_upstream", sa.String(length=128), nullable=False),
        sa.Column("verification_status", sa.String(length=16), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("position(':' in namespace) > 1", name="ck_asset_alias_namespace"),
        sa.CheckConstraint("length(alias_value) > 0 AND length(normalized_value) > 0", name="ck_asset_alias_values"),
        sa.CheckConstraint("valid_to IS NULL OR valid_to > valid_from", name="ck_asset_alias_validity"),
        sa.CheckConstraint("revision >= 1", name="ck_asset_alias_revision"),
        sa.CheckConstraint("alias_type IN ('PROVIDER_SYMBOL','BARE_CODE','EXCHANGE_CODE','ISIN','CURRENT_NAME','HISTORICAL_NAME','PINYIN','USER_ALIAS')", name="ck_asset_alias_type"),
        sa.CheckConstraint("verification_status IN ('VERIFIED','CANDIDATE','REJECTED')", name="ck_asset_alias_verification"),
        sa.UniqueConstraint("namespace", "normalized_value", "entity_key", "revision", name="uq_asset_alias_revision"),
        postgresql.ExcludeConstraint(
            (sa.column("namespace"), "="),
            (sa.column("normalized_value"), "="),
            (sa.column("entity_key"), "<>"),
            (sa.func.daterange(sa.column("valid_from"), sa.column("valid_to"), "[)"), "&&"),
            where=sa.text("verification_status = 'VERIFIED'"),
            name="ex_asset_alias_verified_validity",
            using="gist",
        ),
    )
    op.create_index("ix_asset_alias_lookup", "asset_alias", ["namespace", "normalized_value", "available_at"])
    op.create_table(
        "identity_quarantine",
        sa.Column("quarantine_id", sa.String(length=128), primary_key=True),
        sa.Column("namespace", sa.String(length=128), nullable=False),
        sa.Column("normalized_value", sa.Text(), nullable=False),
        sa.Column("candidate_entity_key", sa.String(length=160), nullable=False),
        sa.Column("conflicting_entity_keys", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("reason_code", sa.String(length=64), nullable=False),
        sa.Column("source_provider", sa.String(length=128), nullable=False),
        sa.Column("actual_upstream", sa.String(length=128), nullable=False),
        sa.Column("alias_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("quarantine_status", sa.String(length=16), nullable=False),
        sa.Column("revision", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("position(':' in namespace) > 1", name="ck_identity_quarantine_namespace"),
        sa.CheckConstraint("quarantine_status IN ('OPEN','RESOLVED','REJECTED')", name="ck_identity_quarantine_status"),
        sa.CheckConstraint("revision >= 1", name="ck_identity_quarantine_revision"),
    )
    op.create_index("ix_identity_quarantine_lookup", "identity_quarantine", ["namespace", "normalized_value", "quarantine_status"])


def downgrade() -> None:
    op.drop_index("ix_identity_quarantine_lookup", table_name="identity_quarantine")
    op.drop_table("identity_quarantine")
    op.drop_index("ix_asset_alias_lookup", table_name="asset_alias")
    op.drop_table("asset_alias")
    op.drop_table("asset_identity")
