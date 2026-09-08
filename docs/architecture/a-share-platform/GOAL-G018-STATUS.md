# Visory-G018 / WP-0205 Daily Scheduler 与补充源

- 最后更新：2026-09-09
- 基线：`main@9b26a1ecfb404932c3694dec7230a2c706de628a`
- 实现分支：`codex/g018-wp0205-scheduler`
- 状态收尾分支：`codex/g018-wp0205-status`
- 状态：`COMPLETE / MERGED`（WP-0205 代码能力已通过本地与远端 Exit Gate；生产 Provider、生产数据库、真实 `/data` 和生产 `backtest_core` 数据仍未认证）
- 进度：`12/45`

## 本轮交付

1. 新增 `DailySchedulePhase`、`DailySchedulePlan`、`DailyScheduleSlot` 与 `DailySchedulePhaseTaskRequirements`，固定 `Asia/Shanghai` 时区和九个盘后阶段：15:50 Preflight、16:00 Core Ingestion、16:20 Normalization/Quality、16:30 Provisional Snapshot、16:40 Supplemental Decision、17:10 backtest_core Certification、17:30 Review Capability Target、19:00 Formal Deadline、20:30 Correction Audit。
2. 新增 `DailySchedulerService`，通过既有 Durable Task Control Plane 创建 `daily_schedule_phase` 任务；幂等键固定为 `daily-schedule:{schedule_version}:{trade_date}:{phase}`，阶段依赖显式串联，同一交易日、Schedule Version 和阶段重复触发时复用任务控制面的幂等语义。
3. 交易日解析器判定非交易日时跳过整日计划，不创建任务；Preflight、阶段依赖、失败/阻塞码、重试与租约丢失继续使用既有持久 Task/Attempt/StateEvent 语义。
4. `a_stock_data` 保持主源，`financial_api` 仅能作为 Provider Policy 已声明的补充、交叉校验或受控灾备源。Raw Ingestion 不再错误地只接受主源，但未登记 Provider 或未在策略中声明的 Provider 仍被拒绝；切换和补数必须生成独立 ProviderRun、RawObject、Partition、QualityReport 或 Snapshot，不允许静默逐行混源。
5. 16:30 允许发布 Provisional Snapshot；17:10 目标是 `backtest_core` Certified；19:00 未认证时拒绝 Formal Prediction 和 Formal Backtest，并保存 `FORMAL_DEADLINE_CERTIFICATION_MISSING`；不得使用 Provisional 数据冒充正式回测输入。
6. 20:30 例行审计使用 `INITIAL` revision 且不要求旧 Snapshot；真实修订必须同时使用 `CORRECTION` 和 `correction_of_snapshot_id`，并建立新的追加式 Snapshot 血缘，不覆盖旧 Snapshot、Prediction 或 Run。
7. Operations Task 页面新增调度阶段、交易日、时区、计划时间、Formal Deadline、依赖任务、主/补充源、Snapshot/Revision、质量缺口、降级、阻塞/失败和旧 Snapshot 展示。
8. 将调度要求纳入 C-010 Contract Registry、JSON Schema、OpenAPI、Golden Payload 和前端生成类型；本 WP 不新增数据库 Migration，Alembic head 保持 `0012_wp0204_benchmark_dataset_extension`。

## 调度与门禁契约

| 时间 | 阶段 | 关键输出或门禁 |
| --- | --- | --- |
| 15:50 | `PREFLIGHT` | 校验交易日、Provider Policy、存储与任务前置条件；失败不得创建正式 DataSnapshot |
| 16:00 | `CORE_INGESTION` | `a_stock_data` 主源核心采集，每个数据集独立 ProviderRun |
| 16:20 | `NORMALIZATION_QUALITY` | Canonical Normalization、质量检查和显式缺口记录 |
| 16:30 | `PROVISIONAL_SNAPSHOT` | 发布可追溯的 Provisional Snapshot，不等同于 Formal 能力认证 |
| 16:40 | `SUPPLEMENTAL_DECISION` | 仅按主源重试耗尽、覆盖缺口、Schema Drift 或明确交叉校验要求启用 `financial_api` |
| 17:10 | `BACKTEST_CORE_CERTIFICATION` | 复用 WP-0204 Snapshot/Capability Gate，目标为 `backtest_core` Certified |
| 17:30 | `REVIEW_CAPABILITY_TARGET` | 记录市场、板块和复盘能力目标；本 WP 不实现这些计算 |
| 19:00 | `FORMAL_DEADLINE` | 缺少认证则拒绝正式预测和 Formal Backtest，并持久化失败原因 |
| 20:30 | `CORRECTION_AUDIT` | 例行检查晚到数据；实际修订创建新的 CORRECTION lineage，不覆盖历史 |

## 本地验收证据

- `.venv\Scripts\python.exe -m pytest tests/platform/test_daily_scheduler.py -q --tb=short`：`8 passed`。
- `.venv\Scripts\python.exe -m pytest tests/platform -q --tb=short`：`390 passed, 5 skipped`。
- 配置一次性 PostgreSQL 16 容器及临时 Secret 文件后，`.venv\Scripts\python.exe -m pytest tests/integration/platform -q --tb=short`：`63 passed`。
- `.venv\Scripts\python.exe -m py_compile src/schemas/platform/scheduler.py src/services/platform/daily_scheduler.py src/schemas/platform/task.py src/services/platform/raw_ingestion.py src/services/platform/task_control.py tests/platform/test_daily_scheduler.py tests/integration/platform/test_task_control_plane.py tests/integration/platform/test_raw_ingestion.py`：通过。
- `.venv\Scripts\python.exe scripts/export_platform_contracts.py --check`：通过。
- `.venv\Scripts\python.exe scripts/check_ai_assets.py`：`[ai-assets] OK`。
- `.venv\Scripts\python.exe scripts/check_visory_baseline.py`：8 个 runtime path、10 个 reference project、0 个 tracked external file、2 个 license/notice、1 个启用 workflow、0 个 imported secret、597 个相对链接、0 个 broken link。
- `.venv\Scripts\python.exe -m flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics`：通过（输出 `0`）。
- `.venv\Scripts\python.exe -m alembic heads`：`0012_wp0204_benchmark_dataset_extension (head)`。
- 在 Windows Git Bash 中显式将 `python`/`python3` 绑定到项目 `.venv` 后执行 `source scripts/ci_gate.sh deterministic`：通过，包含契约导出、代码识别与 YFinance 转换检查。首次直接调用系统 Bash 时错误选中 Python 3.14.7 且缺少 `pandas`，属于本地 PATH/依赖环境差异，不是 G018 回归。
- `npm --prefix apps/dsa-web run lint` 与 `npm --prefix apps/dsa-web run build`：均通过。
- `git diff --check`：通过。

## PostgreSQL、Docker 与临时 Secret 环境

- PostgreSQL 镜像：`postgres:16-alpine`；临时容器：`visory-wp0205-postgres`；端口：`127.0.0.1:55432`；数据库用户：`visory_test`。
- 集成测试通过 `VISORY_TEST_POSTGRES_ADMIN_DATABASE`、`VISORY_TEST_POSTGRES_HOST`、`VISORY_TEST_POSTGRES_PORT`、`VISORY_TEST_POSTGRES_USER` 和 `VISORY_TEST_POSTGRES_PASSWORD_FILE` 注入隔离环境；密码使用随机临时文件，不进入仓库、日志、提交或文档。
- 验收后执行 `docker stop visory-wp0205-postgres` 与 `docker rm visory-wp0205-postgres`；`.tmp/wp0205-env.ps1` 和随机密码文件均已删除，复核容器名为空且两个文件 `Test-Path=False`。现有 `nginx`、`redis` 容器未触碰。

## 远端 Exit Gate 证据

- 实现 PR：[#34](https://github.com/yutianlzq/Visory/pull/34)，标题 `feat: add daily scheduler and supplemental source policy`，目标 `main`。
- 实现提交：测试锚点 `486a6a907b021d00a627d7c54f516897830251a1`；实现 head `d9255474dc52a4e36bf9eb33c5e967383a06f7a8`。
- CI Run：`34264795037`；Governance and repository boundaries、Python deterministic gate、Web lint and build 全部 `success`。
- 合并：PR #34 以普通 merge commit 合入，merge commit 为 `76194dc378f689c0e0f34cc88d7a3989431a96fc`；实现合并后的 `main` SHA 为同一提交。
- 结论：Visory-G018 为 `COMPLETE / MERGED`；WP-0205 为 `VERIFIED`；implemented work packages 为 `12/45`；Daily Scheduler/补充源代码能力门禁为 `VERIFIED`；生产 `backtest_core` 数据仍为 `NOT CERTIFIED`。

## 未验证、风险与明确未实现项

- 本轮没有连接生产 Provider、生产数据库、生产 Secret 或真实 `/data`，没有执行生产调度或部署观察；因此只能认证代码能力，不能认证生产数据或生产运行状态。
- 当前交付创建的是调度计划、持久任务要求与门禁判定能力，不包含真实 Provider Worker 编排器、真实 Dataset 全链路执行或自动生成正式 Prediction/Backtest Run 的生产接线。
- 不实现 WP-0206、Indicator Registry、Feature Store、市场情绪、板块资金、Hikyuu 策略执行器、生产部署、Cloudflare/NPM/生产 Docker 配置或任何 G018 外目标。
- 例行 Correction Audit 与实际 CORRECTION lineage 已区分；真正发布 Correction Snapshot 仍依赖后续生产数据与 Snapshot Worker 接线，旧 Snapshot 不得被覆盖。

## 回滚

- 代码与契约回滚：回退 PR #34 的普通 merge commit `76194dc378f689c0e0f34cc88d7a3989431a96fc`，恢复 WP-0204 的 Snapshot/Capability 基线。
- 本 WP 没有新增 Migration，不需要数据库 downgrade；Alembic head 保持 Migration `0012_wp0204_benchmark_dataset_extension`。
- 已发布 Task、ProviderRun、Partition、QualityReport 和 Snapshot 必须保留审计历史；回滚调度入口不得删除或覆盖既有记录。
