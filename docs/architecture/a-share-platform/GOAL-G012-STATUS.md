# Visory-G012 / WP-0202 进度与验收记录

最后更新：2026-08-31

## 1. 当前状态

- Goal：`Visory-G012`
- Work Package：`WP-0202 Raw Ingestion`
- Goal 状态：`COMPLETE / MERGED / VERIFIED`
- Work Package 状态：`VERIFIED`
- 固定基线：`main=79ae6d4a0742d054e0d18fb8418d6055847e0241`
- 工作分支：`goal/g012-wp-0202-raw-ingestion`
- 已验证 Work Package：`9/45`
- 目标 Migration head：`0007_wp0202_raw_ingestion`
- parent：`0006_wp0201_registry_contract_hardening`
- PR：[#22](https://github.com/yutianlzq/Visory/pull/22)`；合并提交：`1572a3f7f4bbeedc4fdeaafd03011b6a453073fe`（普通 merge commit）；最终 CI：Run [`33405263970`](https://github.com/yutianlzq/Visory/actions/runs/33405263970)，Governance、Python、Web 三项阻断 Job 全部成功。

开始前已核验本地 `HEAD`、本地 `origin/main` 与 GitHub `main` 均为固定基线，工作区干净。合并后重新 fetch，GitHub `main`、本地 `origin/main` 与 PR #22 merge commit 均为 `1572a3f7f4bbeedc4fdeaafd03011b6a453073fe`，工作区干净。本 Goal 只实现 Raw Ingestion，不启动 `WP-0203 Canonical Normalization` 或后续 Work Package。

## 2. 实现结果

### 2.1 正式契约、边界与脱敏

- 新增 C-004 平台正式契约：`ProviderRun`、`RawObject`、`RawIngestionQuarantine`、`RawIngestionTaskRequirements` 与 `RawIngestionPublishResult`，并纳入 Contract Registry、JSON Schema、C-010 OpenAPI 和前端 TypeScript 生成链；
- `ProviderRun` 记录 Provider、每次真实但脱敏的 `actual_upstream`、Dataset/Policy/Adapter/Capability 版本绑定、Task/Attempt、请求指纹、统计、Schema Hash、生命周期结果和受限诊断；
- `RawObject` 使用 `raw_` UUIDv7，固定 `retention_class=PINNED`，并要求 StorageRef、Hash、媒体类型和字节数一致；不保存 Token、Cookie、API Key、请求 Query 或宿主机绝对路径；
- 所有持久化请求与诊断都在进入数据库前拒绝敏感 key、Header、credential-bearing URL、query、fragment 和类似 `token=...` 的正文值。

### 2.2 Migration、Repository 与受控 Provider

- 新增 `0007_wp0202_raw_ingestion`，创建 `provider_run`、`raw_object`、`raw_ingestion_quarantine`，并显式关联 Registry、Durable Task 与 Attempt；
- `raw_object` 强制 append-only 的 provider-run 与相对路径唯一性、PINNED retention、非负统计和受控压缩枚举；Quarantine 禁止保存 `MATCHED` 分类；
- Repository 不隐式提交；ProviderRun、RawObject/Quarantine 和 Durable Task 终态在同一调用方事务中登记；
- 受控 Adapter Registry 只允许 `a_stock_data` 和 `financial_api`，使用可注入 Transport 和离线 `FakeProviderTransport`，不接受任意 import path，也不连接生产 Provider。

### 2.3 原子发布、漂移隔离与崩溃语义

- Raw publisher 在同一 Namespace 的 staging 目录写入，校验大小和 Hash、fsync 文件与目录，并以同文件系统 rename 形成 append-only 发布；已有目标不可覆盖；
- rename 失败不会创建 Registry 记录；rename 成功而数据库事务失败时留下不可见 Orphan，数据库回滚不会删除已发布文件；
- Provider raw schema 显式分类 `MATCHED`、`ADDITIVE_DRIFT`、`BREAKING_DRIFT`、`UNKNOWN_SCHEMA`；漂移内容进入受控 Quarantine，不能伪装为正常 RawObject；
- 只读 Orphan scanner 只遍历严格的已知 Raw 目录和有效 Manifest，重验路径、Symlink、Hash、大小和 Registry 状态，只报告可恢复候选，不删除、不会自动恢复注册，也不触碰未知目录。

### 2.4 Durable Task 闭环

- 复用 WP-0103 Durable Task；`raw_ingestion` 成为受支持的 Worker capability，不创建第二套任务队列；
- Worker 在 fetch 前和发布前检查取消，租约丢失时拒绝登记或完成 Task；Timeout、限流和可重试失败写入稳定的 Raw/Task 语义；
- 三个 Dataset（`security_master`、`trading_calendar`、`bar_1d_raw`）均通过离线 Provider→ProviderRun→RawObject/Quarantine→Task 终态纵向测试；
- 未修改或复用 `src.services.run_diagnostics.ProviderRun`，该 Legacy 诊断类型与平台正式 ProviderRun 保持命名空间隔离。

## 3. 本地验收证据

- Raw 契约：`tests/platform/ingestion/test_raw_ingestion_contracts.py`，`3 passed`；
- PostgreSQL 16 一次性 Docker 纵向/Migration/Task 定向：`26 passed`，覆盖三数据集成功、漂移、Timeout、限流、取消、Lease Lost、Orphan、rename 故障、append-only、幂等、upgrade/repeat/downgrade/re-upgrade、事务和连接清理；
- 平台全套：`tests/platform`，`283 passed, 5 skipped`；
- 平台 PostgreSQL 集成：`tests/integration/platform`，`46 passed`；
- 本 Goal Python 与 Migration 的定向 `flake8`：通过；
- `scripts/export_platform_contracts.py` 与 `--check`：通过，`40` 个平台契约导出无 drift；
- `scripts/check_ai_assets.py`、`scripts/check_visory_baseline.py`：通过；前者/后者均无本 Goal 新问题；
- Web `npm ci && npm run lint && npm run build`：通过；GitHub Actions Run `33405263970` 的 Governance、Python deterministic gate、Web lint and build 全部成功；全量本地 `scripts/ci_gate.sh` 在 Windows 环境报告 83 个与本 Goal 无关的既有环境敏感失败，Goal-specific 与平台测试均通过；`git diff --check`：通过。

## 4. 环境、风险与回滚

- Python 使用本地 `.venv`；PostgreSQL 使用 `postgres:16-alpine` 一次性 Docker 容器、每用例隔离数据库和临时 Secret 文件；所有 Secret 在记录中显示为 `***`；
- 测试仅使用每用例临时 Namespace，未写真实 `/data`，未连接生产 Provider、未写生产数据库或生产 Secret，未部署；PostgreSQL 16 Docker 容器、临时 Secret 文件和 Goal 临时目录已清理；未修改 `upstream/`、`references/`、Legacy Task Queue、依赖清单或 lockfile；
- Migration downgrade 仅回滚数据库 Schema，不删除 Raw、Quarantine 或 rename 后 Orphan 文件；因此回滚前必须保留 Storage 审计证据；
- 回滚代码：普通 revert 本 Goal 的 merge commit；Schema：在隔离数据库 downgrade 至 `0006_wp0201_registry_contract_hardening`，并按上述文件保留语义进行审计或受控恢复；
- 后续风险：真实 Provider 适配、Canonical Normalization、Raw 自动恢复/删除、生产调度与公网数据访问均明确不属于本 Goal。
