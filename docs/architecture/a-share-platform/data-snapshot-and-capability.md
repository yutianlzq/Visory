# DataSnapshot 与 Capability Gate v1

## 目标与边界

WP-0204 建立不可变 DataSnapshot、分区清单、Capability 认证、Consumer Requirement、Current Pointer，以及 `benchmark_index_1d` 与 `backtest_core` 的认证门禁。它不迁移 Legacy 业务表，不创建真实 `/data`，不连接生产 Provider，也不实现 Feature Store 或下载 API。

## Snapshot 契约

`DataSnapshot` 保存 `trade_date`、`cutoff_at`、Provider Policy 版本、Security Master/Calendar Canonical 引用、Canonical Partition 引用、质量报告引用、`publication_status`、`revision/revision_kind/supersedes_id`、`available_at`、确定性 `manifest_hash/content_hash` 和时间元数据。业务数据库只保存逻辑 `StorageRef`，`VISORY_RUNTIME_ROOT` 只负责运行时 Namespace 绑定，不写入数据库、Manifest 或 API。

Snapshot 只能追加发布：`PROVISIONAL` 用于预览和质量检查，`CERTIFIED` 仅在对应 Capability 认证后供正式消费者使用，`REJECTED` 只保留诊断语义。Correction 必须创建新 `snapshot_id`、新 Manifest 和新路径，并通过 `supersedes_id` 指向旧版本；旧 Snapshot 不覆盖、不重写。

## Benchmark Dataset Extension（独立于 WP-0203）

`benchmark_index_1d` 是 WP-0204 为 `backtest_core` 新增的独立 Benchmark Dataset Extension，不是把指数数据伪装成股票，也不是静默扩大 WP-0203 的既有数据集边界。权威契约位于 `src/schemas/platform/benchmark.py`、`src/services/platform/extended_canonical.py`、Contract Registry 和 `0012_wp0204_benchmark_dataset_extension`。

| 项目 | 规则 |
| --- | --- |
| 唯一标识 | `benchmark_id` 使用 `index:<market>:<code>`，主键为 `benchmark_id + trade_date`；不使用股票 `entity_key` |
| 资产类型 | 固定 `asset_type=index`；指数分区与 `bar_1d_raw` 股票分区物理、语义分离 |
| 日期/字段 | `trade_date` 是交易所会话日期；`open/high/low/close` 与 `total_return_close` 使用 `index_points`；OHLC 必须一致 |
| 复权规则 | `return_type=PRICE` 或 `TOTAL_RETURN`；后者必须提供 `total_return_close`；同一 Snapshot 不允许混用 benchmark ID 或收益模式 |
| PIT 规则 | 需求中的 `effective_at` 在本仓库中物化为 timezone-aware 的 `available_at`；该时点必须不晚于 Snapshot `cutoff_at`，并与 `trade_date`、Provider Policy 的 effective interval 一起校验 |
| 数据源 | `a_stock_data` 为主源；`financial_api` 仅用于补充、交叉校验和受控灾备，不做静默逐行混源 |
| 血缘 | 两个 Provider 都必须沿 `ProviderRun → RawObject → CanonicalPartition → CanonicalQualityReport → DataSnapshot/CapabilityCertification` 记录；切换源产生独立 Run、Raw、分区和质量证据 |

## Gate 与 Manifest

Gate 在发布前验证 Canonical Partition、Quality Report、ProviderRun、RawObject 的完整血缘；检查分区文件存在、大小和内容 Hash，绑定 Canonical Manifest，拒绝 `available_at > cutoff_at`、Schema/Provider Policy 版本冲突、失败质量规则、未处理的 Raw Ingestion Quarantine、上市区间重叠、Corporate/Financial Revision 冲突和缺少身份/日历引用。Manifest 使用 canonical JSON 计算确定性 Hash，文件写入 staging 后 fsync 文件和必要目录，再在同一文件系统内原子 rename；目标已存在时拒绝覆盖。

发布路径采用逻辑 POSIX 形式：

```text
observations/domain=data_snapshot/trade_date=YYYY-MM-DD/snapshot_id=<snapshot_id>/manifest.json
```

数据库登记发生在 rename 成功之后。若登记事务失败，已 rename 文件保持不可见 Orphan；恢复或清理由后续受控流程处理，downgrade 不自动删除业务文件。

## Capability 与 Consumer

首批能力为 `identity_core`、`calendar_core`、`financial_research` 与 `backtest_core`。WP-0204 的 Benchmark Dataset Extension 新增独立 `benchmark_index_1d`（`asset_type=index`），不复用或伪装为股票 `bar_1d_raw`。`backtest_core` 只根据自身所需的 security master、trading calendar、股票日线和独立基准指数分区评估非零覆盖、质量、PIT 和新鲜度门禁；这些分区全部通过时，即使同一 Snapshot 因其他非回测能力缺口而为顶层 `PARTIAL`，`backtest_core` 仍可为 `CERTIFIED`。Consumer Gate 另外比较 Snapshot 与 ConsumerRequirement 的最低质量等级，因此默认的 Formal Backtest Requirement 仍拒绝顶层 `PARTIAL`，并且必须声明 `backtest_core` 与 `CERTIFIED` publication；Preview 必须显式声明是否接受 `PROVISIONAL`。
`backtest_core` 的状态判定是闭集语义：

- `CERTIFIED`：所需四类数据存在，覆盖、质量、PIT、日期/版本/血缘和新鲜度全部通过。
- `PROVISIONAL`：数据已具备但 Snapshot 仍为预览发布；只能用于显式允许预览的消费者。
- `PARTIAL`：存在覆盖不足、质量不完整或排除比例超阈值；正式回测拒绝。
- `UNAVAILABLE`：缺少基准或核心数据、质量失败、Schema Drift、未处理 Quarantine、PIT/日期/修订冲突；正式回测拒绝。
- `STALE`：数据超出固定新鲜度窗口；正式回测拒绝。

Formal Backtest Consumer 必须验证数据库中的持久化 CapabilityCertification、注册的 ConsumerRequirement、Snapshot/Partition/Pointer 一致性和文件/血缘完整性；不能依赖 Snapshot 自报的 `certified_capabilities`，也不能用调用方传入的 `PROVISIONAL` 或 `PARTIAL` 证据绕过门禁。

## Current Pointer

Current Pointer 以 `scope + trade_date + capability_id` 唯一。更新时使用 PostgreSQL 行锁和可选 `expected_snapshot_id` CAS，保存 `previous_snapshot_id` 与单调 `pointer_revision`。Pointer 只能指向具有目标 Capability 且已 `CERTIFIED`、且 `trade_date` 与 Pointer 键一致的 Snapshot，Correction 更新 Pointer 时不改变旧记录。

## Durable Task 接入

`SnapshotBuildTaskWorker` 只处理 `task_type=data_snapshot_build`，复用现有 Task Control Service 的 Lease、状态和失败语义。Snapshot/Capability 注册与 Task 成功状态在同一数据库事务中提交；事务失败不删除已经原子 rename 的文件，消费者在数据库提交前不可查询到 Snapshot。

## 本地认证与生产认证

本地测试认证只证明契约和门禁在测试 Fixture、真实 PostgreSQL 集成和确定性文件校验下可执行；它不代表真实 Provider、生产 Secret、生产数据库、真实 `/data` 或生产发布链路已经完成。生产 `CERTIFIED` 数据还需要生产运行观察及 GitHub PR/CI Exit Gate 证据。WP-0204 在这些证据缺失前保持 `IN_PROGRESS`，不得把本地认证结果写成生产 `CERTIFIED` 或 `VERIFIED`。