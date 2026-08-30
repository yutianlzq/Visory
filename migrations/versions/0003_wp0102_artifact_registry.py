"""Create WP-0102 Artifact Registry.

Revision ID: 0003_wp0102_artifact_registry
Revises: 0002_wp0101_asset_identity
Create Date: 2026-08-30
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0003_wp0102_artifact_registry"
down_revision: str | Sequence[str] | None = "0002_wp0101_asset_identity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "artifact_registry",
        sa.Column("artifact_id", sa.String(length=64), primary_key=True),
        sa.Column("artifact_type", sa.String(length=64), nullable=False),
        sa.Column("owner_resource_type", sa.String(length=64), nullable=False),
        sa.Column("owner_resource_id", sa.String(length=64), nullable=False),
        sa.Column("attempt_id", sa.String(length=64), nullable=True),
        sa.Column("storage_backend", sa.String(length=32), nullable=False),
        sa.Column("storage_namespace", sa.String(length=32), nullable=False),
        sa.Column("relative_path", sa.String(length=1024), nullable=False),
        sa.Column("content_hash", sa.String(length=71), nullable=False),
        sa.Column("media_type", sa.String(length=255), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("artifact_hash", sa.String(length=71), nullable=False),
        sa.Column("manifest_hash", sa.String(length=71), nullable=False),
        sa.Column("schema_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("retention_class", sa.String(length=32), nullable=False),
        sa.Column("visibility", sa.String(length=16), nullable=False),
        sa.Column("publication_state", sa.String(length=16), nullable=False),
        sa.Column("integrity_state", sa.String(length=32), nullable=False),
        sa.Column("integrity_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("integrity_failure_code", sa.String(length=64), nullable=True),
        sa.CheckConstraint("artifact_id ~ '^artifact_[0-9a-f-]{36}$'", name="ck_artifact_registry_artifact_id"),
        sa.CheckConstraint("attempt_id IS NULL OR attempt_id ~ '^attempt_[0-9a-f-]{36}$'", name="ck_artifact_registry_attempt_id"),
        sa.CheckConstraint("artifact_type ~ '^[a-z][a-z0-9._-]{0,63}$'", name="ck_artifact_registry_type"),
        sa.CheckConstraint("storage_backend = 'local_fs'", name="ck_artifact_registry_backend"),
        sa.CheckConstraint("storage_namespace = 'app'", name="ck_artifact_registry_namespace"),
        sa.CheckConstraint("relative_path !~ '(^/|\\\\|(^|/)\\.{1,2}(/|$)|//|:)'", name="ck_artifact_registry_relative_path"),
        sa.CheckConstraint("content_hash ~ '^sha256:[0-9a-f]{64}$'", name="ck_artifact_registry_content_hash"),
        sa.CheckConstraint("artifact_hash = content_hash", name="ck_artifact_registry_artifact_hash"),
        sa.CheckConstraint("manifest_hash ~ '^sha256:[0-9a-f]{64}$'", name="ck_artifact_registry_manifest_hash"),
        sa.CheckConstraint("size_bytes >= 0", name="ck_artifact_registry_size"),
        sa.CheckConstraint("schema_version ~ '^[0-9]+\\.[0-9]+\\.[0-9]+$'", name="ck_artifact_registry_schema_version"),
        sa.CheckConstraint("published_at >= created_at", name="ck_artifact_registry_published_at"),
        sa.CheckConstraint("retention_class IN ('PINNED','AUDIT','REBUILDABLE','CACHE','TEMP','QUARANTINE')", name="ck_artifact_registry_retention"),
        sa.CheckConstraint("visibility IN ('PRIVATE','OWNER','INTERNAL')", name="ck_artifact_registry_visibility"),
        sa.CheckConstraint("publication_state = 'PUBLISHED'", name="ck_artifact_registry_publication"),
        sa.CheckConstraint("integrity_state IN ('VERIFIED','MISSING','HASH_MISMATCH','SIZE_MISMATCH','MANIFEST_INVALID')", name="ck_artifact_registry_integrity"),
        sa.CheckConstraint("(integrity_state = 'VERIFIED' AND integrity_failure_code IS NULL) OR (integrity_state <> 'VERIFIED' AND integrity_failure_code IS NOT NULL)", name="ck_artifact_registry_integrity_failure"),
        sa.UniqueConstraint("storage_backend", "storage_namespace", "relative_path", name="uq_artifact_registry_storage_ref"),
    )
    op.create_index("ix_artifact_registry_owner", "artifact_registry", ["owner_resource_type", "owner_resource_id", "published_at"])
    op.create_index("ix_artifact_registry_consumable", "artifact_registry", ["publication_state", "integrity_state", "published_at"])


def downgrade() -> None:
    op.drop_index("ix_artifact_registry_consumable", table_name="artifact_registry")
    op.drop_index("ix_artifact_registry_owner", table_name="artifact_registry")
    op.drop_table("artifact_registry")
