# Visory-G017 / WP-0204 Backtest Core Capability Certification

- 最后更新：2026-09-07
- 基线：`main@dfd76d61912c9cd15ebda4aebaa66de60d96e2b4`
- 工作分支：`goal/g017-wp0204-backtest-core`
- 状态：`IN_PROGRESS`（本地实现和验证已完成；PR/远端 CI 尚未创建）
- 进度：`10/45`（WP-0204 只有在远端合入并取得最终 CI 证据后才更新为 `11/45`）

## 本轮交付

1. 新增独立 `benchmark_index_1d` DatasetDefinition，`asset_type=index`，明确 benchmark identifier、交易日、OHLC、PRICE/TOTAL_RETURN、`available_at` 与 `index_points` 单位。
2. 新增 `BenchmarkIndexBar` 严格契约，拒绝股票类型和缺少 Total Return 值的伪装输入。
3. 补齐 `a_stock_data` 与 `financial_api` 的 Provider Raw Schema 和 Canonical Mapping，保留 Provider → Raw → Canonical → QualityReport → Snapshot 血缘；其中 `a_stock_data` 为核心主源，`financial_api` 仅作为补充、交叉校验和受控灾备，切换必须产生独立 ProviderRun/分区，不允许静默逐行混源。
4. 新增 Migration `0012_wp0204_benchmark_dataset_extension`（parent `0011_wp0204_snapshot_foundation`），登记独立 Benchmark Dataset Extension，并扩展 Capability 状态检查约束。
5. `SnapshotCapabilityEngine` 现在区分 `CERTIFIED`、`PROVISIONAL`、`PARTIAL`、`UNAVAILABLE`、`STALE`；`backtest_core` 只按自身所需的 security master、trading calendar、股票日线与 benchmark index 分区评估非零覆盖、质量、PIT 和新鲜度门禁；其他能力造成的顶层 `PARTIAL` 不会伪造或取消该能力认证，Formal Consumer 仍由最低质量等级门禁拒绝顶层 `PARTIAL`；Snapshot Gate 同时拒绝失败质量规则、Schema Drift 和未处理的 Raw Ingestion Quarantine；Consumer Gate 校验最低质量等级，Current Pointer 校验 `trade_date` 一致性。
6. Certified Snapshot 请求 `backtest_core` 时若认证失败会在发布前拒绝；Formal Backtest Consumer 继续只接受持久化的 `CERTIFIED` `backtest_core` 认证，不能用 Snapshot 自报字段或调用方传入的伪造证据绕过。
7. 更新 JSON Schema、Contract Registry、前端生成类型、Golden payload、状态文档与 Changelog。

## Benchmark Dataset Extension（独立于 WP-0203）

该扩展是 WP-0204 为完成 `backtest_core` 认证而新增的独立边界，不是对 WP-0203 既有 Canonical 数据集范围的静默修改。权威实现与导出证据为：`src/services/platform/extended_canonical.py`、`src/schemas/platform/benchmark.py`、`src/schemas/platform/registry.py`、`schemas/platform/C-004.BenchmarkIndexBar.schema.json` 以及 Migration `0012_wp0204_benchmark_dataset_extension`。

| 项目 | 契约 |
| --- | --- |
| Dataset | `benchmark_index_1d`，schema `1.0.0`，频率 `daily`，主键 `benchmark_id + trade_date` |
| 唯一标识 | `benchmark_id` 格式为 `index:<market>:<code>`，例如 `index:cn:000300.SH`；不得使用股票 `entity_key` 代替 |
| 资产类型 | `asset_type=index`；指数行不能进入股票 `bar_1d_raw` |
| 日期语义 | `trade_date` 是交易所会话日期；`open/high/low/close` 和可选 `total_return_close` 的单位均为 `index_points` |
| 复权/收益规则 | `return_type=PRICE` 表示价格指数；`return_type=TOTAL_RETURN` 表示全收益指数，并强制要求 `total_return_close`；一个 Snapshot 内只能使用一个 benchmark ID 和一种收益模式 |
| PIT 语义 | 需求中的 `effective_at` 在本仓库中物化为该指数事实的 timezone-aware `available_at`；必须满足 `available_at <= Snapshot.cutoff_at`，并与 `trade_date`、Provider Policy effective interval 一起校验 |
| 来源关系 | `a_stock_data` 是主源；`financial_api` 是补充、交叉校验和受控灾备源。切换或补数产生独立 ProviderRun、RawObject、CanonicalPartition 和质量报告，不做静默逐行混源 |
| 血缘关系 | `ProviderRun → RawObject → CanonicalPartition → CanonicalQualityReport → DataSnapshot/CapabilityCertification`；Formal Backtest 只读取通过完整门禁的 Snapshot |

## 验收证据

- `.venv\Scripts\python.exe -m pytest tests/platform -q --tb=short`：`381 passed, 5 skipped`；7 条 warning 为现有依赖/Windows `.pytest_cache` 权限等环境告警，不计为失败。
- 配置一次性 PostgreSQL 16 容器及临时 Secret 文件后，`.venv\Scripts\python.exe -m pytest tests/integration/platform -q --tb=short`：`61 passed`；6 条 warning，未发现本 Goal 回归。
- `.venv\Scripts\python.exe scripts/export_platform_contracts.py --check`：通过。
- `.venv\Scripts\python.exe -m alembic heads`：`0012_wp0204_benchmark_dataset_extension (head)`。
- `.venv\Scripts\python.exe scripts/check_ai_assets.py`：通过。
- `.venv\Scripts\python.exe scripts/check_visory_baseline.py`：通过。
- `.venv\Scripts\flake8.exe . --count --select=E9,F63,F7,F82 --show-source --statistics`：通过（输出 `0`）。
- 22 个变更/新增 Python 文件的 `.venv\Scripts\python.exe -m py_compile`：通过。
- 在 Windows Git Bash 中使用临时 Python 3.12 `python3` shim 执行 `bash scripts/ci_gate.sh deterministic`：通过；包含契约导出、代码识别和 YFinance 代码转换检查。
- `npm --prefix apps/dsa-web run lint` 与 `npm --prefix apps/dsa-web run build`：均通过。
- `git diff --check`：通过。
- 完整离线测试 `.venv\Scripts\python.exe -m pytest -m "not network" --timeout=120 -o timeout_method=thread -o faulthandler_timeout=300 --durations=30 --durations-min=0.5`：`6646 passed, 71 skipped, 4 deselected, 83 failed`；失败集中在既有 Codex/Agent transport/process、Docker、SQLite、本地 CLI 和环境敏感用例，未发现 WP-0204 平台或 PostgreSQL 集成测试失败，不将其误报为本 Goal 回归。

## 本地认证与生产认证的区别

本轮“认证通过”是指本地契约测试、真实 PostgreSQL 16 集成和确定性门禁证明代码可以判定并拒绝不合格 Snapshot；它不代表生产数据已经接入，也不代表生产 `CERTIFIED` 数据已经发布。生产认证仍需要真实 Provider/Secret、生产数据库和真实 `/data` 存储、生产运行观察及 GitHub PR 三项阻断 Job 的最终 CI 证据。WP-0204 在这些证据缺失时必须保持 `IN_PROGRESS`，不得把 `backtest_core` 或 WP 标记为生产 `CERTIFIED/VERIFIED`。

## 未验证与风险

- `bash scripts/ci_gate.sh syntax` 与 `bash scripts/ci_gate.sh flake8` 在 `.venv` 环境通过；`bash scripts/ci_gate.sh deterministic` 也在临时 Python 3.12 `python3` shim 下通过。默认 Windows Bash 的 `python3` 映射到不含项目依赖的 Python 3.14 时会在旧的 `scripts/test.sh` 入口处报 `pandas`/`tenacity` 缺失，因此该环境差异单独记录，不作为 WP-0204 回归。
- 完整 `pytest -m "not network"` 已执行但有 83 个既有 Codex/Agent、Docker、SQLite、本地 CLI 和环境敏感失败；平台定向测试与 PostgreSQL 集成测试均通过，不将这些失败误报为本 Goal 回归。
- 未连接真实 Provider，不写生产数据库、生产 Secret 或真实 `/data`。
- Capability `STALE` 使用固定 7 天新鲜度窗口；如平台 SLA 后续收紧，应在独立策略版本中调整。
- `SnapshotCapabilityStatus` 为兼容既有 Capability/Provider 契约仍保留 `DEGRADED`、`UNVERIFIED`；G017 的 `SnapshotCapabilityEngine` 对 `backtest_core` 只产生并明确判定 `CERTIFIED`、`PROVISIONAL`、`PARTIAL`、`UNAVAILABLE`、`STALE`。
- GitHub PR/Actions 尚未创建或运行，因此本地证据不足以完成 WP `VERIFIED` Exit Gate。

## 明确未实现项

本 Goal 暂不实现：Hikyuu 策略执行器、Fleur 策略移植、指标计算、16:00 生产调度、真实 Provider 连接、生产服务器部署、AI 动态仓位和权重优化、Web 回测页面，以及任何策略执行结果计算。当前交付的是回测数据认证与正式消费者门禁，不是完整回测执行器。

## 迁移、修订与回滚

- Migration 链：`0011_wp0204_snapshot_foundation → 0012_wp0204_benchmark_dataset_extension`。`0012` 增加独立 benchmark extension、质量阈值/覆盖字段及 Snapshot manifest 顺序持久化辅助字段；数据库约束保证 `benchmark_index_1d` 只能是 `asset_type=index`。
- 已发布 Snapshot 不可变；修订必须创建新的 `snapshot_id`、新的 Manifest/分区和 `supersedes_id`，旧 Snapshot、旧分区和旧 Pointer 历史保持可追溯、可复现。Current Pointer 使用行锁和 CAS，只能在质量门禁通过后原子切换。
- 代码和生成契约回滚可恢复 G016 行为；数据库回滚使用 `alembic downgrade 0011_wp0204_snapshot_foundation`，只撤销 `0012` 的 extension、约束和辅助字段，不删除已发布业务文件。