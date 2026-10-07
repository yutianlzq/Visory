"""Add the WP-0302 Feature Partition/Snapshot/Bundle control plane."""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0013_wp0302_feature_store"
down_revision: str | Sequence[str] | None = "0012_wp0204_benchmark_dataset_extension"
branch_labels = None
depends_on = None


_UUID7 = r"[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}"
_HASH = r"^sha256:[0-9a-f]{64}$"


def _resource_check(column: str, prefix: str, name: str) -> sa.CheckConstraint:
    return sa.CheckConstraint(
        f"{column} ~ '^{prefix}_{_UUID7}$'",
        name=name,
    )


def _hash_check(column: str, name: str) -> sa.CheckConstraint:
    return sa.CheckConstraint(f"{column} ~ '{_HASH}'", name=name)


def upgrade() -> None:
    op.create_table(
        "feature_partition",
        sa.Column("feature_partition_id", sa.String(64), primary_key=True),
        sa.Column("indicator_id", sa.String(64), nullable=False),
        sa.Column("definition_version", sa.String(32), nullable=False),
        sa.Column("domain", sa.String(64), nullable=False),
        sa.Column("frequency", sa.String(32), nullable=False),
        sa.Column("partition_key", sa.String(255), nullable=False),
        sa.Column("data_snapshot_ids", postgresql.JSONB(), nullable=False),
        sa.Column("input_partition_ids", postgresql.JSONB(), nullable=False),
        sa.Column("universe_scope_hash", sa.String(71)),
        sa.Column("cutoff_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("row_count", sa.BigInteger(), nullable=False),
        sa.Column("null_count", sa.BigInteger(), nullable=False),
        sa.Column("coverage_ratio", sa.Numeric(6, 5), nullable=False),
        sa.Column("min_date", sa.Date(), nullable=False),
        sa.Column("max_date", sa.Date(), nullable=False),
        sa.Column("min_available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("max_available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("storage_backend", sa.String(32), nullable=False),
        sa.Column("storage_namespace", sa.String(32), nullable=False),
        sa.Column("relative_path", sa.String(1024), nullable=False),
        sa.Column("media_type", sa.String(255), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("partition_hash", sa.String(71), nullable=False),
        sa.Column("schema_hash", sa.String(71), nullable=False),
        sa.Column("quality_status", sa.String(16), nullable=False),
        sa.Column("quality_failure_reasons", postgresql.JSONB(), nullable=False),
        sa.Column("quality_report_id", sa.String(64), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("revision_kind", sa.String(16), nullable=False),
        sa.Column("supersedes_id", sa.String(64)),
        sa.Column("retention_class", sa.String(32), nullable=False),
        sa.Column("reference_count", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        _resource_check("feature_partition_id", "fpart", "ck_feature_partition_id"),
        sa.CheckConstraint("quality_report_id ~ '^quality_" + _UUID7 + "$'", name="ck_feature_partition_quality_report_id"),
        sa.CheckConstraint("universe_scope_hash IS NULL OR universe_scope_hash ~ '^sha256:[0-9a-f]{64}$'", name="ck_feature_partition_universe_scope_hash"),
        _hash_check("partition_hash", "ck_feature_partition_hash"),
        _hash_check("schema_hash", "ck_feature_partition_schema_hash"),
        sa.CheckConstraint("definition_version ~ '^[0-9]+\\.[0-9]+\\.[0-9]+(?:-[0-9A-Za-z.-]+)?(?:\\+[0-9A-Za-z.-]+)?$'", name="ck_feature_partition_definition_version"),
        sa.CheckConstraint("jsonb_typeof(data_snapshot_ids) = 'array' AND jsonb_array_length(data_snapshot_ids) > 0", name="ck_feature_partition_data_snapshots"),
        sa.CheckConstraint("jsonb_typeof(input_partition_ids) = 'array'", name="ck_feature_partition_inputs"),
        sa.CheckConstraint("jsonb_typeof(quality_failure_reasons) = 'array'", name="ck_feature_partition_quality_reasons"),
        sa.CheckConstraint("coverage_ratio >= 0 AND coverage_ratio <= 1", name="ck_feature_partition_coverage_ratio"),
        sa.CheckConstraint("row_count >= 0 AND null_count >= 0 AND null_count <= row_count", name="ck_feature_partition_counts"),
        sa.CheckConstraint("size_bytes > 0 AND reference_count >= 0 AND revision >= 1", name="ck_feature_partition_nonnegative"),
        sa.CheckConstraint("media_type = 'application/vnd.apache.parquet'", name="ck_feature_partition_parquet_media_type"),
        sa.CheckConstraint("min_date <= max_date AND min_available_at <= max_available_at", name="ck_feature_partition_ranges"),
        sa.CheckConstraint("max_available_at <= cutoff_at", name="ck_feature_partition_available_before_cutoff"),
        sa.CheckConstraint("published_at IS NULL OR published_at >= created_at", name="ck_feature_partition_published_after_created"),
        sa.CheckConstraint("quality_status IN ('COMPLETE','PARTIAL','FAILED','UNAVAILABLE','STALE')", name="ck_feature_partition_quality_status"),
        sa.CheckConstraint("revision_kind IN ('INITIAL','CORRECTION','REBUILD','MIGRATION')", name="ck_feature_partition_revision_kind"),
        sa.CheckConstraint("retention_class IN ('PINNED','AUDIT','REBUILDABLE','CACHE','TEMP','QUARANTINE')", name="ck_feature_partition_retention_class"),
        sa.CheckConstraint(
            "(revision_kind = 'INITIAL' AND revision = 1 AND supersedes_id IS NULL) "
            "OR (revision_kind = 'CORRECTION' AND revision >= 2 AND supersedes_id IS NOT NULL) "
            "OR (revision_kind IN ('REBUILD', 'MIGRATION') AND supersedes_id IS NULL)",
            name="ck_feature_partition_revision_lineage",
        ),
        sa.ForeignKeyConstraint(
            ["supersedes_id"], ["feature_partition.feature_partition_id"],
            name="fk_feature_partition_supersedes", ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("storage_backend", "storage_namespace", "relative_path", name="uq_feature_partition_storage_ref"),
    )
    # PostgreSQL treats NULLs as distinct in ordinary unique constraints.
    # Normalize the optional global-universe scope so the logical key remains
    # unique even when universe_scope_hash is NULL.
    op.execute(
        "CREATE UNIQUE INDEX uq_feature_partition_logical_revision "
        "ON feature_partition (domain, indicator_id, definition_version, frequency, "
        "partition_key, COALESCE(universe_scope_hash, ''), revision)"
    )
    op.create_index(
        "ix_feature_partition_identity",
        "feature_partition",
        ["indicator_id", "definition_version", "frequency", "partition_key", "revision"],
    )
    op.create_index(
        "ix_feature_partition_cutoff_quality",
        "feature_partition",
        ["cutoff_at", "quality_status", "published_at"],
    )

    op.create_table(
        "feature_snapshot",
        sa.Column("feature_snapshot_id", sa.String(64), primary_key=True),
        sa.Column("snapshot_type", sa.String(32), nullable=False),
        sa.Column("as_of_trade_date", sa.Date(), nullable=False),
        sa.Column("cutoff_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data_snapshot_ids", postgresql.JSONB(), nullable=False),
        sa.Column("dependency_plan_hash", sa.String(71), nullable=False),
        sa.Column("definition_refs", postgresql.JSONB(), nullable=False),
        sa.Column("publication_status", sa.String(16), nullable=False),
        sa.Column("quality_status", sa.String(16), nullable=False),
        sa.Column("certified_capabilities", postgresql.JSONB(), nullable=False),
        sa.Column("missing_capabilities", postgresql.JSONB(), nullable=False),
        sa.Column("max_source_available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("quality_report_id", sa.String(64)),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("revision_kind", sa.String(16), nullable=False),
        sa.Column("supersedes_id", sa.String(64)),
        sa.Column("manifest_hash", sa.String(71), nullable=False),
        sa.Column("manifest_version", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        _resource_check("feature_snapshot_id", "fs", "ck_feature_snapshot_id"),
        sa.CheckConstraint("dependency_plan_hash ~ '^sha256:[0-9a-f]{64}$'", name="ck_feature_snapshot_dependency_plan_hash"),
        sa.CheckConstraint("jsonb_typeof(data_snapshot_ids) = 'array' AND jsonb_array_length(data_snapshot_ids) > 0", name="ck_feature_snapshot_data_snapshots"),
        sa.CheckConstraint("jsonb_typeof(definition_refs) = 'array' AND jsonb_array_length(definition_refs) > 0", name="ck_feature_snapshot_definition_refs"),
        sa.CheckConstraint("jsonb_typeof(certified_capabilities) = 'array' AND jsonb_typeof(missing_capabilities) = 'array'", name="ck_feature_snapshot_capabilities"),
        sa.CheckConstraint("quality_report_id IS NULL OR quality_report_id ~ '^quality_" + _UUID7 + "$'", name="ck_feature_snapshot_quality_report_id"),
        _hash_check("manifest_hash", "ck_feature_snapshot_manifest_hash"),
        sa.CheckConstraint("manifest_version ~ '^[0-9]+\\.[0-9]+\\.[0-9]+(?:-[0-9A-Za-z.-]+)?(?:\\+[0-9A-Za-z.-]+)?$'", name="ck_feature_snapshot_manifest_version"),
        sa.CheckConstraint("max_source_available_at <= cutoff_at", name="ck_feature_snapshot_available_before_cutoff"),
        sa.CheckConstraint("revision >= 1 AND (published_at IS NULL OR published_at >= created_at)", name="ck_feature_snapshot_revision_and_published"),
        sa.CheckConstraint("snapshot_type IN ('CLOSE_CORE','LATE_A_SHARE','CORRECTION','HISTORICAL_REBUILD')", name="ck_feature_snapshot_type"),
        sa.CheckConstraint("publication_status IN ('DRAFT','PROVISIONAL','CERTIFIED','RETIRED')", name="ck_feature_snapshot_publication_status"),
        sa.CheckConstraint("quality_status IN ('COMPLETE','PARTIAL','FAILED','UNAVAILABLE','STALE')", name="ck_feature_snapshot_quality_status"),
        sa.CheckConstraint("revision_kind IN ('INITIAL','CORRECTION','REBUILD','MIGRATION')", name="ck_feature_snapshot_revision_kind"),
        sa.CheckConstraint(
            "(revision_kind = 'INITIAL' AND revision = 1 AND snapshot_type <> 'CORRECTION' AND supersedes_id IS NULL) "
            "OR (revision_kind = 'CORRECTION' AND revision >= 2 AND snapshot_type = 'CORRECTION' AND supersedes_id IS NOT NULL) "
            "OR (revision_kind IN ('REBUILD', 'MIGRATION') AND snapshot_type <> 'CORRECTION' AND supersedes_id IS NULL)",
            name="ck_feature_snapshot_revision_lineage",
        ),
        sa.ForeignKeyConstraint(
            ["supersedes_id"], ["feature_snapshot.feature_snapshot_id"],
            name="fk_feature_snapshot_supersedes", ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "ix_feature_snapshot_publication",
        "feature_snapshot",
        ["as_of_trade_date", "cutoff_at", "publication_status", "revision"],
    )

    op.create_table(
        "feature_snapshot_partition_ref",
        sa.Column("feature_snapshot_id", sa.String(64), primary_key=True),
        sa.Column("feature_partition_id", sa.String(64), primary_key=True),
        sa.Column("partition_hash", sa.String(71), nullable=False),
        sa.Column("schema_hash", sa.String(71), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("storage_backend", sa.String(32), nullable=False),
        sa.Column("storage_namespace", sa.String(32), nullable=False),
        sa.Column("relative_path", sa.String(1024), nullable=False),
        sa.Column("media_type", sa.String(255), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("indicator_id", sa.String(64), nullable=False),
        sa.Column("definition_version", sa.String(32), nullable=False),
        sa.Column("required_columns", postgresql.JSONB(), nullable=False),
        sa.Column("retention_class", sa.String(32), nullable=False),
        sa.Column("partition_order", sa.Integer(), nullable=False),
        _hash_check("partition_hash", "ck_feature_snapshot_ref_partition_hash"),
        _hash_check("schema_hash", "ck_feature_snapshot_ref_schema_hash"),
        sa.CheckConstraint("revision >= 1 AND size_bytes > 0 AND partition_order >= 0", name="ck_feature_snapshot_ref_nonnegative"),
        sa.CheckConstraint("media_type = 'application/vnd.apache.parquet'", name="ck_feature_snapshot_ref_parquet_media_type"),
        sa.CheckConstraint("retention_class IN ('PINNED','AUDIT','REBUILDABLE','CACHE','TEMP','QUARANTINE')", name="ck_feature_snapshot_ref_retention_class"),
        sa.ForeignKeyConstraint(
            ["feature_snapshot_id"], ["feature_snapshot.feature_snapshot_id"],
            name="fk_feature_snapshot_ref_snapshot", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["feature_partition_id"], ["feature_partition.feature_partition_id"],
            name="fk_feature_snapshot_ref_partition", ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("feature_snapshot_id", "partition_order", name="uq_feature_snapshot_partition_order"),
    )
    op.create_index("ix_feature_snapshot_ref_partition", "feature_snapshot_partition_ref", ["feature_partition_id"])

    op.create_table(
        "feature_bundle",
        sa.Column("feature_bundle_id", sa.String(64), primary_key=True),
        sa.Column("feature_snapshot_ids", postgresql.JSONB(), nullable=False),
        sa.Column("dependency_plan_hash", sa.String(71), nullable=False),
        sa.Column("required_columns", postgresql.JSONB(), nullable=False),
        sa.Column("consumer_ref", sa.String(255), nullable=False),
        sa.Column("consumer_kind", sa.String(32), nullable=False),
        sa.Column("cutoff_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("date_from", sa.Date()),
        sa.Column("date_to", sa.Date()),
        sa.Column("universe_scope_hash", sa.String(71)),
        sa.Column("bundle_hash", sa.String(71), nullable=False),
        sa.Column("bundle_version", sa.String(32), nullable=False),
        _resource_check("feature_bundle_id", "bundle", "ck_feature_bundle_id"),
        sa.CheckConstraint("dependency_plan_hash ~ '^sha256:[0-9a-f]{64}$'", name="ck_feature_bundle_dependency_plan_hash"),
        sa.CheckConstraint("jsonb_typeof(feature_snapshot_ids) = 'array' AND jsonb_array_length(feature_snapshot_ids) > 0", name="ck_feature_bundle_snapshots"),
        sa.CheckConstraint("jsonb_typeof(required_columns) = 'array' AND jsonb_array_length(required_columns) > 0", name="ck_feature_bundle_columns"),
        sa.CheckConstraint("universe_scope_hash IS NULL OR universe_scope_hash ~ '^sha256:[0-9a-f]{64}$'", name="ck_feature_bundle_universe_scope_hash"),
        _hash_check("bundle_hash", "ck_feature_bundle_hash"),
        sa.CheckConstraint("bundle_version ~ '^[0-9]+\\.[0-9]+\\.[0-9]+(?:-[0-9A-Za-z.-]+)?(?:\\+[0-9A-Za-z.-]+)?$'", name="ck_feature_bundle_version"),
        sa.CheckConstraint("date_to IS NULL OR date_from IS NOT NULL", name="ck_feature_bundle_date_range_start"),
        sa.CheckConstraint("date_to IS NULL OR date_from <= date_to", name="ck_feature_bundle_date_range_order"),
        sa.CheckConstraint("consumer_kind IN ('PREVIEW','FORMAL_BACKTEST')", name="ck_feature_bundle_consumer_kind"),
    )
    op.create_index("ix_feature_bundle_hash", "feature_bundle", ["bundle_hash"])
    op.create_index("ix_feature_bundle_consumer", "feature_bundle", ["consumer_ref", "consumer_kind", "cutoff_at"])

    op.create_table(
        "feature_bundle_partition_ref",
        sa.Column("feature_bundle_id", sa.String(64), primary_key=True),
        sa.Column("feature_partition_id", sa.String(64), primary_key=True),
        sa.Column("partition_hash", sa.String(71), nullable=False),
        sa.Column("schema_hash", sa.String(71), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("storage_backend", sa.String(32), nullable=False),
        sa.Column("storage_namespace", sa.String(32), nullable=False),
        sa.Column("relative_path", sa.String(1024), nullable=False),
        sa.Column("media_type", sa.String(255), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("indicator_id", sa.String(64), nullable=False),
        sa.Column("definition_version", sa.String(32), nullable=False),
        sa.Column("required_columns", postgresql.JSONB(), nullable=False),
        sa.Column("retention_class", sa.String(32), nullable=False),
        sa.Column("partition_order", sa.Integer(), nullable=False),
        _hash_check("partition_hash", "ck_feature_bundle_ref_partition_hash"),
        _hash_check("schema_hash", "ck_feature_bundle_ref_schema_hash"),
        sa.CheckConstraint("revision >= 1 AND size_bytes > 0 AND partition_order >= 0", name="ck_feature_bundle_ref_nonnegative"),
        sa.CheckConstraint("media_type = 'application/vnd.apache.parquet'", name="ck_feature_bundle_ref_parquet_media_type"),
        sa.CheckConstraint("retention_class IN ('PINNED','AUDIT','REBUILDABLE','CACHE','TEMP','QUARANTINE')", name="ck_feature_bundle_ref_retention_class"),
        sa.ForeignKeyConstraint(
            ["feature_bundle_id"], ["feature_bundle.feature_bundle_id"],
            name="fk_feature_bundle_ref_bundle", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["feature_partition_id"], ["feature_partition.feature_partition_id"],
            name="fk_feature_bundle_ref_partition", ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("feature_bundle_id", "partition_order", name="uq_feature_bundle_partition_order"),
    )
    op.create_index("ix_feature_bundle_ref_partition", "feature_bundle_partition_ref", ["feature_partition_id"])


def downgrade() -> None:
    op.drop_index("ix_feature_bundle_ref_partition", table_name="feature_bundle_partition_ref")
    op.drop_table("feature_bundle_partition_ref")
    op.drop_index("ix_feature_bundle_consumer", table_name="feature_bundle")
    op.drop_index("ix_feature_bundle_hash", table_name="feature_bundle")
    op.drop_table("feature_bundle")
    op.drop_index("ix_feature_snapshot_ref_partition", table_name="feature_snapshot_partition_ref")
    op.drop_table("feature_snapshot_partition_ref")
    op.drop_index("ix_feature_snapshot_publication", table_name="feature_snapshot")
    op.drop_table("feature_snapshot")
    op.drop_index("ix_feature_partition_cutoff_quality", table_name="feature_partition")
    op.drop_index("ix_feature_partition_identity", table_name="feature_partition")
    op.drop_index("uq_feature_partition_logical_revision", table_name="feature_partition")
    op.drop_table("feature_partition")
