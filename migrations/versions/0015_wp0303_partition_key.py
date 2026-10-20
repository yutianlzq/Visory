"""Extend only the derived Feature partition key without changing its identity."""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0015_wp0303_partition_key"
down_revision = "0014_wp0303_indicator_id"
branch_labels = None
depends_on = None

_TABLES = ("feature_partition", "feature_snapshot_partition_ref", "feature_bundle_partition_ref")


def upgrade() -> None:
    op.alter_column("feature_partition", "partition_key", existing_type=sa.String(255),
                    type_=sa.String(386), existing_nullable=False)


def downgrade() -> None:
    connection = op.get_bind()
    # 与发布预检使用相同表锁顺序；所有拒绝条件必须先于任何缩列。
    connection.execute(sa.text(
        "LOCK TABLE feature_partition, feature_snapshot_partition_ref, "
        "feature_bundle_partition_ref IN ACCESS EXCLUSIVE MODE"
    ))
    if connection.execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM feature_partition WHERE char_length(partition_key) > 255)"
    )).scalar_one():
        raise RuntimeError("cannot downgrade partition_key: stored keys longer than 255 characters exist")
    # 即使目标只是 0014，也保守拒绝长 ID；降到 0013 时不得先缩键、再发现 ID 不兼容。
    for table in _TABLES:
        if connection.execute(sa.text(
            f"SELECT EXISTS (SELECT 1 FROM {table} WHERE char_length(indicator_id) > 64)"
        )).scalar_one():
            raise RuntimeError("cannot downgrade partition_key: stored IDs longer than 64 characters exist")
    op.alter_column("feature_partition", "partition_key", existing_type=sa.String(386),
                    type_=sa.String(255), existing_nullable=False)
