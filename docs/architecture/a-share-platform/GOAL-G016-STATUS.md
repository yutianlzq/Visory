# Visory-G016 / WP-0204 Snapshot Foundation & Capability Engine

## 状态

- Goal：`COMPLETE / MERGED`
- Work Package：`WP-0204`
- 目标分支：`goal/g016-wp-0204-snapshot-foundation`
- 基线：`main@b31171d75dabc1127aef69fdb9a2deab4f413e76`
- Migration：`0011_wp0204_snapshot_foundation`，父版本 `0010_wp0203_extended_canonical_datasets`
- 进度：`10/45`（WP-0204 保持 `IN_PROGRESS`，`backtest_core` 不得标记为 `CERTIFIED`）

## 本次实现

1. 新增 `DataSnapshot`、`SnapshotPartitionRef`、`CapabilityCertification`、`ConsumerRequirement`、`SnapshotCurrentPointer` 及 Snapshot Build Task 契约。
2. 新增不可变 Snapshot Registry Migration `0011_wp0204_snapshot_foundation` 与无隐式提交的 Repository。
3. 新增 Snapshot Gate：Canonical/Quality/ProviderRun/RawObject 血缘、PIT、Manifest、文件 Hash/大小、Schema/Policy 版本和跨分区冲突检查。
4. 新增确定性 Snapshot Manifest 发布器：临时 staging、fsync、同文件系统原子 rename，运行时根目录仅由环境绑定提供。
5. 新增能力认证与消费者门禁；`backtest_core` 在本 Work Package 固定返回 `UNAVAILABLE / BENCHMARK_DATASET_MISSING`，Formal Backtest 不静默降级。
6. 新增 Current Pointer 的行锁与 CAS 更新，Correction 只追加新 Snapshot，不覆盖旧版本。
7. Snapshot Build Worker 复用现有 Durable Task Control Service，并在同一注册事务中完成 Snapshot/Capability 登记与 Task 完成；数据库失败时保留不可见 Orphan。
8. 纳入 Contract Registry、JSON Schema、OpenAPI/前端类型的确定性生成链。

## 验收证据

- 平台契约 Registry/Golden：`tests/platform/test_contract_registry.py`、`tests/platform/test_contract_golden_payloads.py`。
- Snapshot 定向测试：`tests/platform/test_snapshot_foundation.py`。
- 生成检查：`.venv\Scripts\python.exe scripts/export_platform_contracts.py --check`。
- Alembic 当前 head：`0011_wp0204_snapshot_foundation`；PostgreSQL 16 空库升级、重复升级、降级和重新升级由 GitHub Actions Python Job 的隔离 PostgreSQL 服务验证通过。
- 本地 Snapshot/Contract 定向验证：`102 passed`；Contract export `--check`、`check_ai_assets.py`、`check_visory_baseline.py`、目标文件 `flake8` 与 `git diff --check` 通过。
- Web 验证：`npm ci`、`npm run lint`、`npm run build` 均通过（2026-09-05）。
- 完整离线回归：`6603 passed, 85 failed, 65 skipped, 4 deselected`；失败集中在既有 Codex app-server/process、Docker shell、SQLite migration、intelligence/screening 等 Legacy/环境相关测试，未发现 Snapshot 定向失败；仍不能替代 CI。
- 本地 Windows 未配置 Docker/PostgreSQL，因此本地 PostgreSQL 集成仍未运行；GitHub Actions Run `33941401645` 的 Governance、Python deterministic gate、Web lint/build 三项阻断 Job 全部成功，包含隔离 PostgreSQL 集成。WP-0204 仍保持 `IN_PROGRESS`，尚未标记为 `VERIFIED`。
- PR #30 已按普通 merge commit 合入 main：head `fb0f997cb51aecf364f37598ec7fd0c718780008`，merge commit `187550f434b64ea71d66452b748aba6943f8cb76`。

## 风险与回滚

- Snapshot Registry 仅保存控制面与逻辑 `StorageRef`，不会迁移 Legacy 表或真实业务数据。
- `backtest_core` 尚无基准指数数据集，任何 Formal Backtest 请求必须明确拒绝。
- 文件原子 rename 成功但数据库事务失败时会留下不可见 Orphan；Alembic downgrade 只回滚 Schema，不自动删除业务文件。
- 回滚使用 `git revert` 目标提交并按需执行 `alembic downgrade 0010_wp0203_extended_canonical_datasets`；不删除已发布业务文件。

## 下一步

补齐本地一次性 PostgreSQL 16 实例（如环境可用）上的补充验证，保持 `backtest_core=UNAVAILABLE / BENCHMARK_DATASET_MISSING`，下一建议目标为 `G017 / WP-0204 Backtest Core Certification`。
