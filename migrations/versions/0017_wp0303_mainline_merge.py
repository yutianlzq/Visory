"""Join reviewed SourceRoute binding and WP-0303 admission without rewriting either branch."""

revision = "0017_wp0303_mainline_merge"
down_revision = (
    "0014_wp0207_source_binding",
    "0016_wp0303_provider_endpoint_admission",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 两个父链的 DDL 互不重叠；这里只收敛版本图，不修改来源证据或业务数据。
    pass


def downgrade() -> None:
    # 只退回双父节点；进一步降级仍由原 migration 的保护规则负责。
    pass
