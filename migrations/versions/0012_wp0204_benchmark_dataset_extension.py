"""Record the WP-0204 benchmark dataset extension and capability states."""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0012_wp0204_benchmark_dataset_extension"
down_revision: str | Sequence[str] | None = "0011_wp0204_snapshot_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_capability_certification_status", "capability_certification", type_="check")
    op.create_check_constraint(
        "ck_capability_certification_status",
        "capability_certification",
        "capability_status IN ('CERTIFIED','PROVISIONAL','PARTIAL','UNAVAILABLE','STALE','DEGRADED','UNVERIFIED')",
    )
    op.add_column("canonical_quality_report", sa.Column("coverage_ratio", sa.Numeric(6, 5), nullable=False, server_default=sa.text("1.0")))
    op.add_column("canonical_quality_report", sa.Column("excluded_instrument_count", sa.BigInteger(), nullable=False, server_default=sa.text("0")))
    op.add_column("canonical_quality_report", sa.Column("quality_threshold_version", sa.String(32), nullable=False, server_default="1.0.0"))
    op.add_column("snapshot_partition_ref", sa.Column("coverage_ratio", sa.Numeric(6, 5), nullable=False, server_default=sa.text("1.0")))
    op.add_column("snapshot_partition_ref", sa.Column("excluded_instrument_count", sa.BigInteger(), nullable=False, server_default=sa.text("0")))
    op.add_column("snapshot_partition_ref", sa.Column("quality_threshold_version", sa.String(32), nullable=False, server_default="1.0.0"))
    # Preserve the immutable partition-list order used by the Snapshot manifest.
    # Existing rows recover the order from the parent quality-report list; the
    # deterministic fallback only applies to malformed legacy rows.
    op.add_column("snapshot_partition_ref", sa.Column("partition_order", sa.Integer(), nullable=True))
    op.execute(
        sa.text(
            """
            WITH ranked AS (
                SELECT
                    spr.snapshot_id,
                    spr.canonical_partition_id,
                    COALESCE(
                        quality_order.partition_order,
                        ROW_NUMBER() OVER (
                            PARTITION BY spr.snapshot_id
                            ORDER BY spr.dataset_id, spr.partition_key, spr.revision, spr.canonical_partition_id
                        ) - 1
                    ) AS partition_order
                FROM snapshot_partition_ref AS spr
                JOIN data_snapshot AS ds
                  ON ds.snapshot_id = spr.snapshot_id
                LEFT JOIN LATERAL (
                    SELECT elements.ordinality - 1 AS partition_order
                    FROM jsonb_array_elements_text(ds.quality_report_refs)
                         WITH ORDINALITY AS elements(quality_report_id, ordinality)
                    WHERE elements.quality_report_id = spr.quality_report_id
                    LIMIT 1
                ) AS quality_order ON TRUE
            )
            UPDATE snapshot_partition_ref AS target
            SET partition_order = ranked.partition_order
            FROM ranked
            WHERE target.snapshot_id = ranked.snapshot_id
              AND target.canonical_partition_id = ranked.canonical_partition_id
            """
        )
    )
    op.alter_column("snapshot_partition_ref", "partition_order", nullable=False)
    for table in ("canonical_quality_report", "snapshot_partition_ref"):
        for column in ("coverage_ratio", "excluded_instrument_count", "quality_threshold_version"):
            op.alter_column(table, column, server_default=None)
    op.create_check_constraint("ck_canonical_quality_coverage_ratio", "canonical_quality_report", "coverage_ratio >= 0 AND coverage_ratio <= 1")
    op.create_check_constraint("ck_canonical_quality_excluded_count", "canonical_quality_report", "excluded_instrument_count >= 0")
    op.create_check_constraint("ck_snapshot_partition_coverage_ratio", "snapshot_partition_ref", "coverage_ratio >= 0 AND coverage_ratio <= 1")
    op.create_check_constraint("ck_snapshot_partition_excluded_count", "snapshot_partition_ref", "excluded_instrument_count >= 0")
    op.create_check_constraint("ck_canonical_quality_threshold_version", "canonical_quality_report", r"quality_threshold_version ~ '^[0-9]+\.[0-9]+\.[0-9]+$'")
    op.create_check_constraint("ck_snapshot_partition_threshold_version", "snapshot_partition_ref", r"quality_threshold_version ~ '^[0-9]+\.[0-9]+\.[0-9]+$'")
    op.create_check_constraint("ck_snapshot_partition_order", "snapshot_partition_ref", "partition_order >= 0")
    op.create_unique_constraint(
        "uq_snapshot_partition_order",
        "snapshot_partition_ref",
        ["snapshot_id", "partition_order"],
    )
    op.create_table(
        "benchmark_dataset_extension",
        sa.Column("dataset_id", sa.String(64), primary_key=True),
        sa.Column("schema_version", sa.String(32), nullable=False),
        sa.Column("asset_type", sa.String(32), nullable=False),
        sa.Column("return_types", postgresql.JSONB(), nullable=False),
        sa.Column("provider_ids", postgresql.JSONB(), nullable=False),
        sa.Column("contract_notes", sa.Text(), nullable=False),
        sa.CheckConstraint("asset_type = 'index'", name="ck_benchmark_extension_asset_type"),
        sa.CheckConstraint("dataset_id = 'benchmark_index_1d'", name="ck_benchmark_extension_dataset_id"),
    )
    op.execute(
        sa.text(
            "INSERT INTO benchmark_dataset_extension (dataset_id, schema_version, asset_type, return_types, provider_ids, contract_notes) "
            "VALUES (:dataset_id, :schema_version, :asset_type, CAST(:return_types AS jsonb), CAST(:provider_ids AS jsonb), :contract_notes)"
        ).bindparams(
            dataset_id="benchmark_index_1d",
            schema_version="1.0.0",
            asset_type="index",
            return_types='["PRICE", "TOTAL_RETURN"]',
            provider_ids='["a_stock_data", "financial_api"]',
            contract_notes="Independent benchmark index contract; never coerced into stock bar_1d_raw.",
        )
    )


def downgrade() -> None:
    op.drop_constraint("uq_snapshot_partition_order", "snapshot_partition_ref", type_="unique")
    op.drop_constraint("ck_snapshot_partition_order", "snapshot_partition_ref", type_="check")
    op.drop_constraint("ck_snapshot_partition_threshold_version", "snapshot_partition_ref", type_="check")
    op.drop_constraint("ck_canonical_quality_threshold_version", "canonical_quality_report", type_="check")
    op.drop_constraint("ck_snapshot_partition_excluded_count", "snapshot_partition_ref", type_="check")
    op.drop_constraint("ck_snapshot_partition_coverage_ratio", "snapshot_partition_ref", type_="check")
    op.drop_constraint("ck_canonical_quality_excluded_count", "canonical_quality_report", type_="check")
    op.drop_constraint("ck_canonical_quality_coverage_ratio", "canonical_quality_report", type_="check")
    op.drop_column("snapshot_partition_ref", "partition_order")
    for name in ("quality_threshold_version", "excluded_instrument_count", "coverage_ratio"):
        op.drop_column("snapshot_partition_ref", name)
    for name in ("quality_threshold_version", "excluded_instrument_count", "coverage_ratio"):
        op.drop_column("canonical_quality_report", name)
    op.drop_table("benchmark_dataset_extension")
    op.drop_constraint("ck_capability_certification_status", "capability_certification", type_="check")
    op.create_check_constraint(
        "ck_capability_certification_status",
        "capability_certification",
        "capability_status IN ('CERTIFIED','UNAVAILABLE','DEGRADED','UNVERIFIED')",
    )
