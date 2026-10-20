"""Align only Feature indicator IDs with the existing 128-character contract."""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0014_wp0303_indicator_id"
down_revision = "0013_wp0302_feature_store"
branch_labels = None
depends_on = None

_TABLES = ("feature_partition", "feature_snapshot_partition_ref", "feature_bundle_partition_ref")


def upgrade() -> None:
    for table in _TABLES:
        op.alter_column(table, "indicator_id", existing_type=sa.String(64), type_=sa.String(128), existing_nullable=False)


def downgrade() -> None:
    connection = op.get_bind()
    # 在任何缩列前同时锁定全部目标表，避免预检后并发插入长 ID。
    connection.execute(sa.text(
        "LOCK TABLE feature_partition, feature_snapshot_partition_ref, "
        "feature_bundle_partition_ref IN ACCESS EXCLUSIVE MODE"
    ))
    for table in _TABLES:
        # 表名来自本 migration 的固定白名单；不接受外部标识符，不进行 USING 截断。
        if connection.execute(sa.text(
            f"SELECT EXISTS (SELECT 1 FROM {table} WHERE char_length(indicator_id) > 64)"
        )).scalar_one():
            raise RuntimeError("cannot downgrade indicator_id: stored IDs longer than 64 characters exist")
    for table in _TABLES:
        op.alter_column(table, "indicator_id", existing_type=sa.String(128), type_=sa.String(64), existing_nullable=False)
