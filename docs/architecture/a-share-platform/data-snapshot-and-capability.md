# DataSnapshot 与 Capability Gate v1

## 目标与边界

WP-0204 只建立不可变 DataSnapshot、分区清单、Capability 认证、Consumer Requirement 和 Current Pointer。它不迁移 Legacy 业务表，不创建真实 `/data`，不连接生产 Provider，也不实现 Backtest Core、Feature Store 或下载 API。

## Snapshot 契约

`DataSnapshot` 保存 `trade_date`、`cutoff_at`、Provider Policy 版本、Security Master/Calendar Canonical 引用、Canonical Partition 引用、质量报告引用、`publication_status`、`revision/revision_kind/supersedes_id`、`available_at`、确定性 `manifest_hash/content_hash` 和时间元数据。业务数据库只保存逻辑 `StorageRef`，`VISORY_RUNTIME_ROOT` 只负责运行时 Namespace 绑定，不写入数据库、Manifest 或 API。

Snapshot 只能追加发布：`PROVISIONAL` 用于预览和质量检查，`CERTIFIED` 仅在对应 Capability 认证后供正式消费者使用，`REJECTED` 只保留诊断语义。Correction 必须创建新 `snapshot_id`、新 Manifest 和新路径，并通过 `supersedes_id` 指向旧版本；旧 Snapshot 不覆盖、不重写。

## Gate 与 Manifest

Gate 在发布前验证 Canonical Partition、Quality Report、ProviderRun、RawObject 的完整血缘；检查分区文件存在、大小和内容 Hash，绑定 Canonical Manifest，拒绝 `available_at > cutoff_at`、Schema/Provider Policy 版本冲突、上市区间重叠、Corporate/Financial Revision 冲突和缺少身份/日历引用。Manifest 使用 canonical JSON 计算确定性 Hash，文件写入 staging 后 fsync 文件和必要目录，再在同一文件系统内原子 rename；目标已存在时拒绝覆盖。

发布路径采用逻辑 POSIX 形式：

```text
observations/domain=data_snapshot/trade_date=YYYY-MM-DD/snapshot_id=<snapshot_id>/manifest.json
```

数据库登记发生在 rename 成功之后。若登记事务失败，已 rename 文件保持不可见 Orphan；恢复或清理由后续受控流程处理，downgrade 不自动删除业务文件。

## Capability 与 Consumer

首批能力为 `identity_core`、`calendar_core`、`financial_research`。`backtest_core` 在 WP-0204 固定为 `UNAVAILABLE`，原因码为 `BENCHMARK_DATASET_MISSING`；不通过补默认值或静默降级伪造认证。Formal Backtest Requirement 必须声明 `backtest_core` 并只接受 `CERTIFIED`，Preview 必须显式声明是否接受 `PROVISIONAL`。

## Current Pointer

Current Pointer 以 `scope + trade_date + capability_id` 唯一。更新时使用 PostgreSQL 行锁和可选 `expected_snapshot_id` CAS，保存 `previous_snapshot_id` 与单调 `pointer_revision`。Pointer 只能指向具有目标 Capability 且已 `CERTIFIED` 的 Snapshot，Correction 更新 Pointer 时不改变旧记录。

## Durable Task 接入

`SnapshotBuildTaskWorker` 只处理 `task_type=data_snapshot_build`，复用现有 Task Control Service 的 Lease、状态和失败语义。Snapshot/Capability 注册与 Task 成功状态在同一数据库事务中提交；事务失败不删除已经原子 rename 的文件，消费者在数据库提交前不可查询到 Snapshot。
