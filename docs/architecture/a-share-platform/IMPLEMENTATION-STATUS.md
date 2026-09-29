# Visory 实现状态


## 2026-09-28 当前回合最新复核：实时远程基线成功

- 连续两次执行带连接超时保护的 `git ls-remote origin refs/heads/main` 均成功返回 `46804661dbb897433f114c25898c8da7021254a1`。
- 该 SHA 与本地 `HEAD`、本地 `main` 和缓存 `origin/main` 一致，`main...origin/main = 0/0`。
- 本次仅执行只读远程核验，未执行 `fetch`、`pull`、`reset`、`stash`、`commit` 或 `push`。


## 2026-09-28 当前回合复核：实时远程仍不可用

- 本回合执行 `git -c http.connectTimeout=10 -c http.lowSpeedLimit=1 -c http.lowSpeedTime=10 ls-remote origin refs/heads/main`，因 GitHub 连接低速超时失败（exit 128）；本次未取得实时远程 SHA。
- 本地 `HEAD`、本地 `main` 与缓存 `origin/main` 仍为 `46804661dbb897433f114c25898c8da7021254a1`，`main...origin/main = 0/0`；未执行 `fetch`、`pull`、`reset`、`stash`、`commit` 或 `push`。
- 实时远程基线继续记录为 `BLOCKER`；WP-0207 保持 `IN_PROGRESS / NOT CERTIFIED / 13/45`。
- 本轮最小充分验证：Backfill/API/Contract Python `188 passed, 4 warnings`；隔离 `postgres:16` integration `16 passed, 2 warnings`；Contract Registry、治理检查、受影响 Python `py_compile`、`git diff --check` 通过；Backfill Web Vitest `9 passed`，修改文件定向 ESLint、`tsc -b`、Vite build 通过。

## 2026-09-28 当前回合最终复核：实时远程阻断

- 本回合最后一次 `git ls-remote origin refs/heads/main` 因连接 `github.com:443` 失败（exit 128）；不能把缓存 `origin/main` 当作本次实时远程成功证据。失败前后本地 `HEAD`、本地 `main` 与缓存 `origin/main` 均为 `46804661dbb897433f114c25898c8da7021254a1`。
- 当前工作树仅包含 WP-0207 未提交改动；未执行 `fetch`、`pull`、`reset`、`stash`、`commit`、`push` 或 PR。WP-0206 的代码、状态文档和 Run `34581431121` 证据未被当前工作树覆盖，未发现其状态与实现/既有 CI 证据矛盾。
- 最新本地定向套件为 `189 passed, 15 skipped, 4 warnings`；隔离 PostgreSQL 16 Backfill integration 的既有成功证据为 `16 passed, 2 warnings`。本地 Web 修改文件 ESLint、`tsc -b`、Vite build 和 Backfill Vitest `9 passed` 通过；全量 Web ESLint 仍有 41 个未修改既有错误。
- 实时远程基线缺口记录为 `BLOCKER`；WP-0207 保持 `IN_PROGRESS / NOT CERTIFIED / 13/45`，不得标记 `VERIFIED` 或 `RELEASED`。

最后更新：2026-09-28
最后更新：2026-09-28

## WP-0207 当前回合补验（2026-09-28）

- 实时 `git ls-remote origin refs/heads/main` 已成功返回 `46804661dbb897433f114c25898c8da7021254a1`，与本地 `HEAD`、`main` 和缓存 `origin/main` 一致。
- 使用隔离临时 `postgres:16` 容器执行 Backfill integration，结果为 `16 passed, 2 warnings`；容器与临时密码已清理，未连接生产资源。
- BackfillWorker 现累计 checkpoint/Projection 的 `differences_summary`，不再在正常分区 checkpoint 和最终聚合中丢失摘要；相关定向 Python 套件为 `189 passed, 15 skipped, 4 warnings`。
- WP-0207 仍为 `IN_PROGRESS / NOT CERTIFIED / 13/45`。远程 WP-0207 阻断 CI、七类数据完整执行/发布和生产资源认证仍未完成。

## 1. 当前结论

文档状态：可执行基线已形成。

工程底座状态：DSA 固定提交 `fb4735a1055caefa2396982af3b09121feb9ff30` 已完成导入和双基线验收，状态为 `IMPORTED / VERIFIED`。导入代码中的 React/FastAPI、Legacy SQLite、内存 Task Queue、分析、LLM、报告、通知和数据 Fetcher 仍是迁移基线，不能作为 Visory 新契约已实现的证据。

目标架构状态：implemented work packages 为 `13/45`；`WP-0001`、`WP-0002`、`WP-0003`、`WP-0101`、`WP-0102`、`WP-0103`、`WP-0104`、`WP-0201`、`WP-0202`、`WP-0203`、`WP-0204`、`WP-0205`、`WP-0206` 为 `VERIFIED`；除 WP-0207 外其余 WP 为 `NOT_STARTED`；WP-0207 当前为 `IN_PROGRESS`，尚未通过全部 Exit Gate。G013 Provider Raw Schema Hardening 已完成并通过最终 CI，仍计入同一 `WP-0202`。

最近完成的 Work Package：`WP-0206 P-DATA 数据质量页面`。`Visory-G019` 在既有 Snapshot、Capability、Provider、Canonical 与 Durable Task Control Plane 上增加只读数据质量 Projection/API、能力/数据集/血缘下钻、15:50—20:30 调度时间线、Snapshot/Correction 对比与受控 Recheck/Rebuild/Correction Task 入口；不新增 Migration，不接入真实 Provider、生产数据库、真实 `/data` 或生产调度。P-DATA 定向测试、平台契约/治理/Flake8/py_compile/Web 验证通过；PR #36 的 Run `34581431121` 三项阻断 Job 全绿，普通 merge commit `3db5057acd0029c6fb3557fe6a90ebfb2c288acd`；状态为 `COMPLETE / MERGED / VERIFIED / 13/45`，生产 Provider、真实 `/data` 和生产 `backtest_core` 数据仍未认证。

交付阶段：MVP 一期为本地核心功能版（M0—M6 + WP-0701—0703）；MVP 二期为本地生产预演与服务器发布版（WP-0704 + M8）。未过 Local Release Gate 不得将 WP 标记为 `RELEASED`。

### Goal 与底座状态

| 范围 | 状态 | 证据 |
| --- | --- | --- |
| Visory-G001 | COMPLETE | [G001 进度与验收记录](GOAL-STATUS.md) |
| Visory-G002 | COMPLETE | [G002 进度与验收记录](GOAL-G002-STATUS.md) |
| Visory-G003 | COMPLETE | [G003 / WP-0001 进度与验收记录](GOAL-G003-STATUS.md) |
| Visory-G004 | COMPLETE / MERGED | [G004 / WP-0002 进度与验收记录](GOAL-G004-STATUS.md)；PR #3 merge commit `7513208` |
| Visory-G005 | COMPLETE / MERGED | [G005 / WP-0003 进度与验收记录](GOAL-G005-STATUS.md)；PR #4 merge commit `98ab97e`；Runs `33265028192`、`33265537543` 全绿 |
| Visory-G006 | COMPLETE / MERGED | [G006 / WP-0101 进度与验收记录](GOAL-G006-STATUS.md)；PR #5 merge commit `01e1a986`；最终 Run `33288412520` 全绿 |
| Visory-G007 | COMPLETE / MERGED | [G007 / WP-0102 进度与验收记录](GOAL-G007-STATUS.md)；PR #6；merge commit `a9a640b`；最终 Run `33299476674` 三项全绿 |
| Visory-G008 | COMPLETE / MERGED | [G008 / WP-0103 进度与验收记录](GOAL-G008-STATUS.md)；merge commit `ea4f8b1`；PR #7；Run `33315054696` 三项全绿 |
| Visory-G009 | COMPLETE / MERGED | [G009 / WP-0104 进度与验收记录](GOAL-G009-STATUS.md)；PR #15 merge commit `9c03666740a1e7a90a616a2d774efc57ca5a0e6b`；真实认证 ASGI/浏览器旅程、PostgreSQL SSE replay 和连接清理通过；Run `33329710242` 三项阻断 Job 全绿 |
| Visory-G011 | COMPLETE / MERGED | [G011 / WP-0201 Registry Hardening](GOAL-G011-STATUS.md)；PR #20 merge commit `dbd8c271041b17323cff09ec00679f5f0ea59547`；Run `33373953485` 的 Governance、Python、Web 三项阻断 Job 全绿；进度保持 `8/45` |
| Visory-G012 | COMPLETE / MERGED / VERIFIED | [G012 / WP-0202 Raw Ingestion](GOAL-G012-STATUS.md)；PR #22；merge commit `1572a3f7f4bbeedc4fdeaafd03011b6a453073fe`；Migration `0007_wp0202_raw_ingestion`；Run `33405263970` 的 Governance、Python、Web 三项阻断 Job 全绿；进度 `9/45` |
| Visory-G013 | COMPLETE / VERIFIED | G013 / WP-0202 Provider Raw Schema Hardening; target migration `0008_wp0202_raw_schema_hardening`; PR #25 merged with head `766476d60bc3a1539dc8589fa2d830ed754b7117`, merge commit `71328fd512400a0cc0a2c38c128fead14a9a57d4`; final Run `33578007314` Governance/Python/Web all successful; progress remains `9/45` because WP-0202 is already counted |
| Visory-G014 | COMPLETE / MERGED | G014 / WP-0203 Core Canonical Normalization; PR #26 head `072484513b1f1a26d90bf6b33639fd8589af56a0`, ordinary merge commit `fbe34cbc0ee851ee99237a6b4e644abff5f48d66`; Run `33836754285` Governance/Python/Web all successful; Goal complete, WP-0203 remains `IN_PROGRESS`, progress `9/45` pending G015 |
| Visory-G015 | COMPLETE / MERGED / VERIFIED | [G015 / WP-0203 扩展 Canonical 数据集](GOAL-G015-STATUS.md)；Migration `0010_wp0203_extended_canonical_datasets`；四数据集、14 条 Provider Schema/Mapping 与质量血缘字段完成；PR #28 head `7e813208c710cd9ae3d43be541935e46085174e1`，普通 merge commit `76554416853314d6b3fe950f9d81a2c896320c27`；Run `33851938418` Governance/Python/Web 全绿；进度 `10/45` |
| Visory-G016 | COMPLETE / MERGED | [G016 / WP-0204 Snapshot Foundation](GOAL-G016-STATUS.md)；Migration `0011_wp0204_snapshot_foundation`；PR #30 merge commit `187550f434b64ea71d66452b748aba6943f8cb76`；Run `33941401645` 三项全绿；为 G017 提供不可变 Snapshot 基线 |
| Visory-G017 | COMPLETE / MERGED | [G017 / WP-0204 Backtest Core Certification](GOAL-G017-STATUS.md)；Migration `0012_wp0204_benchmark_dataset_extension`；独立 `benchmark_index_1d` Dataset/Provider/Raw/Canonical/Quality/Snapshot 血缘与 Formal Consumer Gate 完成；本地平台测试 `381 passed, 5 skipped` 与真实 PostgreSQL 16 集成 `61 passed`；PR #32 的 Run `34176102715` 中 Governance/Python deterministic gate/Web lint and build 三项阻断 Job 全部成功；实现提交 `6d28889b11e128f7d963acab469218c5c7955a8a` 以普通 merge commit `38bb737067e4e89bf766fb1b73023c3193cfa8ea` 合入 `main`；WP-0204 `VERIFIED`，`backtest_core` 代码能力门禁 `VERIFIED`，生产 `backtest_core` 数据 `NOT CERTIFIED` |
| Visory-G018 | COMPLETE / MERGED | [G018 / WP-0205 Daily Scheduler 与补充源](GOAL-G018-STATUS.md)；`Asia/Shanghai` 九阶段盘后调度、非交易日跳过、幂等依赖链、`a_stock_data` 主源与 `financial_api` 显式补充、19:00 Formal Deadline 和 20:30 Correction Audit 完成；本地平台 `390 passed, 5 skipped`、PostgreSQL 16 集成 `63 passed`；PR #34 head `d9255474dc52a4e36bf9eb33c5e967383a06f7a8`，Run `34264795037` 三项阻断 Job 全绿，普通 merge commit `76194dc378f689c0e0f34cc88d7a3989431a96fc`；WP-0205 `VERIFIED`，进度 `12/45`，生产数据 `NOT CERTIFIED` |
| DSA Baseline | IMPORTED / VERIFIED | 1126/1126 blob 验签；Python/Web 双基线；`baseline_regression_delta=0`；`web_lint_build_regression_delta=0` |
| Implemented Work Packages | 13/45 | `WP-0001`、`WP-0002`、`WP-0003`、`WP-0101`、`WP-0102`、`WP-0103`、`WP-0104`、`WP-0201`、`WP-0202`、`WP-0203`、`WP-0204`、`WP-0205`、`WP-0206` 为 `VERIFIED`；`WP-0207` 为 `IN_PROGRESS`；其余 31 项 `NOT_STARTED` |

Current Goal: Visory-G020 / WP-0207 分批 Backfill is `IN_PROGRESS` from the unchanged baseline `46804661dbb897433f114c25898c8da7021254a1`; the current worktree adds BackfillBatch/TaskRequirements/Projection contracts, a fixed seven-stage Durable Task control chain, controlled Backfill Task creation, deterministic MONTH/YEAR partition planning, existing Durable Task child-task coordination, checkpoint validation, idempotent fixture publication, and Operations/P-DATA observation entry points. Implemented work packages remain `13/45`; WP-0207 is not `VERIFIED` or `RELEASED`; no real Provider, production database, real `/data`, production scheduler, or production backfill certification is included.

### WP-0207 当前回合复核（2026-09-28，远程基线与定向套件）

- 当前分支为 `main`；本地 `HEAD`、本地 `main` 与缓存 `origin/main` 均为 `46804661dbb897433f114c25898c8da7021254a1`。
- 本轮使用 `git -c http.connectTimeout=5 -c http.lowSpeedLimit=1 -c http.lowSpeedTime=5 ls-remote origin refs/heads/main` 进行实时远程复核，因无法连接 `github.com:443` 失败；因此本轮不能把缓存 `origin/main` 作为实时远程成功证据，未执行 `fetch`、`pull`、`commit`、`push` 或 PR。
- `tests/platform/test_backfill.py tests/platform/api/test_generated_contracts.py` 定向套件为 `175 passed, 3 warnings`；`git diff --check` 通过。WP-0207 继续保持 `IN_PROGRESS / NOT CERTIFIED / 13/45`。
### WP-0207 当前回合补验（2026-09-28，批次查询一致性）

- 修正 `BackfillService.get_batch` 的重复记录处理：查询窗口扩大为 2 条并检查 `has_more`，同一 `batch_id` 存在多个 Durable Task 记录时返回稳定 `BACKFILL_BATCH_AMBIGUOUS`，不再静默选择第一条记录。
- 新增重复批次查询 fail-closed 回归；`tests/platform/test_backfill.py` 当前为 `169 passed, 2 warnings`（该条为本轮批次查询补验时的局部快照）；本轮联合定向套件为 `183 passed, 15 skipped, 4 warnings`。受影响 Python `py_compile` 与 `git diff --check` 通过。
- WP-0207 继续保持 `IN_PROGRESS / NOT CERTIFIED / 13/45`；本次仅收敛控制面可观测性，不改变七类数据完整执行、真实 Provider、生产数据库、真实 `/data`、生产调度或远程 CI 的未认证状态。

### WP-0207 当前验证补充（2026-09-27）

- Backfill 前端 API 的普通异常已统一脱敏为公开不可用文案，可信 API Envelope 仍仅投影公开错误字段；`platformBackfill` 定向 Vitest 为 `2 passed`。
- 新增只读 P-DATA 阶段链下钻 `GET /api/platform/v1/data-quality/backfills/{batch_id}/stages`；BackfillService 复用 `TaskListQuery(resource_id=..., task_type="backfill")`，固定路线图排序并对缺失批次、重复阶段和错误依赖 fail-closed；不创建 Task、不发布业务对象。
- 本轮 Backfill/阶段链/P-DATA/generated contract 定向 Python 套件为 `173 passed, 4 warnings`；本地 Docker `postgres:16` tmpfs/loopback 临时容器中的 Backfill integration 为 `16 passed, 2 warnings`。
- 本地 Docker `postgres:16` tmpfs 隔离容器中的 Backfill PostgreSQL integration 为 `16 passed, 2 warnings`。排除两个因未安装 `markdown2` 而无法导入完整 API 应用的既有模块后，`tests/integration/platform` 为 `81 passed, 3 warnings`；完整目录收集仍有 2 个同源 `ModuleNotFoundError: markdown2` 错误。排除三个同源 API 模块后，`tests/platform` 为 `549 passed, 5 skipped, 4 warnings`；完整目录收集仍有 3 个同源错误。持久化 `pg` 容器为 `Exited (255)`，未启动、未复用、未修改。
- bundled Node.js `v24.19.0` 直接运行项目本地 ESLint、`tsc -b`、Vite build 均通过；系统 Node.js `v16.20.2` 下的 `npm run lint/build` 受 Node/Vite 版本限制失败，未修改 Web 依赖。
- WP-0207 仍为 IN_PROGRESS、生产认证 NOT CERTIFIED、进度 13/45；本地 Docker PostgreSQL deterministic fixture 证据不代表真实 Provider、生产数据库、真实 /data、生产调度或生产回填已认证。
### WP-0207 当前回合补验（2026-09-28）

- 本轮再次尝试 `git ls-remote origin refs/heads/main` 时连接被远端重置；本地 `main`、缓存 `origin/main` 与 HEAD 仍一致，最近一次成功的实时复核仍返回 `46804661dbb897433f114c25898c8da7021254a1`，未执行 fetch、pull、commit、push 或 PR。
- 本轮使用 bundled Node.js `v24.19.0` 执行修改文件定向 ESLint 与 `npm run build`，均成功；全量 `npm run lint` 仍有 41 个既有未修改路径错误，构建产物包含 `BackfillPage` chunk。Docker 可用性探测未在本轮得到终态，因此没有新增 PostgreSQL 运行结果，继续引用此前隔离 `postgres:16` 证据。
- 随后使用临时 `postgres:16` 容器（tmpfs、loopback-only、独立数据库）实际执行 `tests/integration/platform/test_backfill_integration.py`，结果为 `16 passed, 1 warning`；容器和临时密码文件已清理，未复用持久化数据库。

- 基线复核：当前分支为 `main`，本地 `HEAD`、本地 `main`、缓存 `origin/main` 与实时 `git ls-remote origin refs/heads/main` 均为 `46804661dbb897433f114c25898c8da7021254a1`；未执行 fetch、pull、commit、push 或 PR。
- WP-0206 复核：GitHub 只读结果确认 PR #36 已合入、状态收尾 PR #37 已合入基线 `46804661dbb897433f114c25898c8da7021254a1`；PR #37 记录的 Run `34581431121` 三项阻断 Job 为成功。该历史证据不等同于 WP-0207 远程 CI。
- WP-0207 相关 Python 定向套件为 `389 passed, 53 skipped, 3 warnings`；隔离 `postgres:16` tmpfs/loopback 临时容器中的 `tests/integration/platform/test_backfill_integration.py` 为 `16 passed, 1 warning`。未配置环境的跳过项未被计入 PostgreSQL 通过证据。
- 本轮随后完成的完整 scripts/ci_gate.sh 离线 backend gate 为 6852 passed, 82 failed, 88 skipped, 4 deselected, 572 subtests passed；失败集中在既有 Codex transport/process、Local CLI、SQLite/Storage、screening 和 system-config 路径，未涉及 WP-0207 改动，故不据此扩大范围修复。
- Contract Registry/generated exports、`check_ai_assets.py`、`check_visory_baseline.py`、受影响 Python `py_compile`、`git diff --check` 均通过；Backfill 前端定向 Vitest 为 `7 passed`，bundled Node.js `v24.19.0` 下 Web lint/build 均通过。
- 完整 Web Vitest 为 `1107 passed, 3 failed, 2 skipped`；失败位于未被 WP-0207 修改的 `DecisionSignalsPage`、`AlertRuleForm`、`SettingsField` 既有测试路径，本轮不扩大范围修复，但不能将完整 Web 测试宣称为通过。新增 P-DATA 与 Backfill 四个公开入口未知异常脱敏回归后，WP-0207 定向 Backfill/API/Contract 套件为 `182 passed, 15 skipped, 3 warnings`；WP-0207 仍为 `IN_PROGRESS / NOT CERTIFIED / 13/45`。


### WP-0207 当前回合 PostgreSQL 补验（2026-09-28）

- 使用临时 `postgres:16` 容器、`tmpfs`、`127.0.0.1` 随机端口、独立测试数据库和临时凭据执行 `tests/integration/platform/test_backfill_integration.py`，结果为 `16 passed, 2 warnings`。
- 覆盖 MONTH 1/YEAR 12 pilot、dry-run/plan-only、checkpoint 恢复、幂等、取消/失败、fallback/quarantine/unavailable、Correction 不覆盖旧 Snapshot、七阶段 StageChain 和受控依赖 Task；测试资源已清理，未连接生产数据库。
- 该结果属于隔离 deterministic fixture 证据，不证明真实 Provider、生产 `/data`、生产调度或生产回填认证；WP-0207 仍为 `IN_PROGRESS / NOT CERTIFIED`。

## 2. 状态定义

```text
NOT_STARTED  尚无目标代码与验收证据
IN_PROGRESS  有当前实现分支/工作树，Exit Gate尚未通过
BLOCKED      有明确外部依赖或决策阻断，并记录证据
VERIFIED     代码、Migration、测试和本地/集成证据通过
RELEASED     已部署且通过运行观察和回滚/恢复要求
```

状态不能由文档存在、代码行数、单个单元测试或主观描述更新。`VERIFIED/RELEASED`必须在“证据”列链接到代码、Migration、测试命令结果和运行产物。

## 3. Work Package状态

| WP | 交付物 | 状态 | 证据 |
| --- | --- | --- | --- |
| WP-0001 | Contract Registry与公共Schema | VERIFIED | Commit `5537569`；PR #2；GitHub Actions Run `33242596600` 的 Governance、Python、Web 三项阻断 Job 全绿；平台契约测试 93 passed |
| WP-0002 | PostgreSQL与Alembic基础 | VERIFIED | 实现 head `32b318a`；PR #3；Migration `0001_wp0002_baseline`；GitHub Actions Run `33250185521` 三项阻断 Job 全绿；Python 6487 passed，含 PostgreSQL 16 真实集成验收 |
| WP-0003 | API Envelope、Error与生成类型 | VERIFIED | PR #4；首轮 Actions Run `33265028192` 三项阻断 Job 全绿；Python 6522 passed；平台契约 35 passed；Legacy/API 定向回归 112 passed；无新增 Migration |
| WP-0101 | Asset Identity与Alias Resolver | VERIFIED | 实现提交 `a272b25`；PR #5；Migration `0002_wp0101_asset_identity`；GitHub Actions Run `33288021328` 三项阻断 Job 全绿；Python 6549 passed，含 PostgreSQL 16 Migration、排他约束、Quarantine、并发、事务与连接清理验收 |
| WP-0102 | Storage Namespace与Artifact Publisher | VERIFIED | [G007 / WP-0102 进度与验收记录](GOAL-G007-STATUS.md)；实现 head `92ddde7`；PR #6；Migration `0003_wp0102_artifact_registry`；平台 218 passed、本地 PostgreSQL 16 集成 15 passed；Run `33299055144` 三项全绿，Python 6591 passed |
| WP-0103 | Durable Task Control Plane | VERIFIED | [G008 / WP-0103 进度与验收记录](GOAL-G008-STATUS.md)；实现 head `826aacfa2965c98efff8a8795a46dc9f72edec5f`；PR #7；Migration `0004_wp0103_durable_task_control_plane`；平台 257 passed、5 skipped，本地 PostgreSQL 16 集成 30 passed，Legacy 定向回归 106 passed；Run `33314470672` 三项全绿 |
| WP-0104 | Operations最小页面 | VERIFIED | [G009 / WP-0104 进度与验收记录](GOAL-G009-STATUS.md)；PR #9、#12、#13、#14、#15 已合并；真实认证 ASGI/浏览器旅程、PostgreSQL SSE replay 和连接池清理通过；平台 260 passed、5 skipped；集成目录本地 PostgreSQL 16 实例 31 passed（清理后默认 31 skipped）；Playwright 6 passed + 真实认证 1 passed；Run `33329710242` 三项阻断 Job 全绿 |
| WP-0201 | Dataset/Provider Registry | VERIFIED | [G010 / WP-0201 进度与验收记录](GOAL-G010-STATUS.md)；实现 head `77a38e5bacc85e986d8062a55d0d867ec9387d89`；PR #17；merge commit `208f1d442f642a17d412c02eb06c3fb3e4b19ba3`；Migration `0005_wp0201_dataset_provider_registry`；补充 credential-safe Settings projection、GiST exclusion constraint 与真实 PostgreSQL 重叠拒绝测试；Run `33351050060` 三项阻断 Job 全绿 |
| WP-0202 | Raw Ingestion + Provider Raw Schema Hardening | VERIFIED | [G012 / WP-0202 进度与验收记录](GOAL-G012-STATUS.md)；PR #22；merge commit `1572a3f7f4bbeedc4fdeaafd03011b6a453073fe`；Migration `0007_wp0202_raw_ingestion`；平台 283 passed、PostgreSQL 16 integration 46 passed；Run `33405263970` 三项阻断 Job 全绿；G013 新增 Migration `0008_wp0202_raw_schema_hardening`、Provider Raw Schema Registry 与协调限流，平台 288 passed/5 skipped、PostgreSQL 16 integration 47 passed；PR #25 head `41c101236047eaf68618dd3d239bead649f1011f`；Run `33531064869` Governance/Python/Web 全绿 |
| WP-0203 | Canonical Normalization + Extended Datasets | VERIFIED | [G014 / WP-0203](GOAL-G014-STATUS.md) 已完成 Core；[G015 / WP-0203 扩展](GOAL-G015-STATUS.md) 新增 `0010_wp0203_extended_canonical_datasets`、四数据集、14 条 Provider Schema/Mapping 与质量血缘门禁；平台 `323 passed, 5 skipped`、PostgreSQL integration `55 passed`、Run `33851938418` Governance/Python/Web 全绿；PR #28 普通 merge commit `76554416853314d6b3fe950f9d81a2c896320c27`；进度 `10/45` |
| WP-0204 | DataSnapshot与Capability Gate + Backtest Core Certification | VERIFIED | [G016 / Snapshot Foundation](GOAL-G016-STATUS.md) 已通过 PR #30 和 Run `33941401645` 合并，Migration `0011_wp0204_snapshot_foundation`；[G017 / Backtest Core Certification](GOAL-G017-STATUS.md) 新增 Migration `0012_wp0204_benchmark_dataset_extension`、独立 `benchmark_index_1d` 契约及 Formal Consumer Gate，本地平台测试 `381 passed, 5 skipped`、真实 PostgreSQL 16 集成 `61 passed`；PR #32 的 Run `34176102715` Governance/Python deterministic gate/Web lint and build 三项阻断 Job 全部成功；实现提交 `6d28889b11e128f7d963acab469218c5c7955a8a`、普通 merge commit `38bb737067e4e89bf766fb1b73023c3193cfa8ea`、最终 `main` SHA `38bb737067e4e89bf766fb1b73023c3193cfa8ea`；代码能力门禁 `VERIFIED`，生产 `backtest_core` 数据 `NOT CERTIFIED` |
| WP-0205 | 16:00 Scheduler与补充源 | VERIFIED | [G018 / WP-0205](GOAL-G018-STATUS.md)；既有 Durable Task Control Plane 上的 `Asia/Shanghai` 九阶段盘后调度、交易日跳过、幂等/依赖、`a_stock_data` 主源与 `financial_api` 显式补充、19:00 Formal Deadline、20:30 Correction Audit 和 Operations 投影完成；无新增 Migration，Alembic head `0012_wp0204_benchmark_dataset_extension`；平台 `390 passed, 5 skipped`、PostgreSQL 16 integration `63 passed`；PR #34 / Run `34264795037` 三项阻断 Job 全绿；普通 merge commit `76194dc378f689c0e0f34cc88d7a3989431a96fc`；生产数据 `NOT CERTIFIED` |
| WP-0206 | P-DATA数据质量页面 | VERIFIED | [G019 / WP-0206](GOAL-G019-STATUS.md)；PR #36；Run `34581431121` 三项阻断 Job 全绿；普通 merge commit `3db5057acd0029c6fb3557fe6a90ebfb2c288acd`；生产数据 `NOT CERTIFIED` |
| WP-0207 | 分批Backfill | IN_PROGRESS | 当前工作树：BackfillBatch/TaskRequirements/Projection、受控 `backfill` Task 创建 API、七阶段固定顺序 Durable Task 控制链、依赖阻断/解阻断、YEAR 月分区 worker、既有 Durable Task 子任务协调器与 BackfillWorker 分区回收、稳定 checkpoint、幂等恢复、父 attempt lease/cancel 发布 fence、Web Operations/P-DATA 只读观察入口和 Contract Registry；当前 head `b5ab2da578cbad1e34e854cc3b67a0bc957185bb`；PR #38；远程 Run `36404883866` 的 Governance/Python deterministic gate/Web lint and build 三项阻断 Job 全部成功。当前本地定向 Python `188 passed, 3 warnings`，隔离 PostgreSQL Backfill integration `16 passed, 1 warning`，Backfill Web Vitest `9 passed`，修改文件定向 ESLint、`tsc -b`、Vite build、generated exports、治理检查、受影响 Python `py_compile` 和 `git diff --check` 通过；全量 Web ESLint 仍有 41 个未修改路径既有错误。覆盖 MONTH 1/YEAR 12 pilot、dry-run/plan-only 无业务发布、checkpoint 恢复、幂等、取消/失败、fallback/quarantine/unavailable、Correction 不覆盖旧 Snapshot 与依赖 Task 原子阻断创建。七类数据完整逐阶段真实对象发布、完整脱敏矩阵和生产 Provider/数据库/`/data`/调度认证仍未完成；生产数据 `NOT CERTIFIED`，不得标记 `VERIFIED` 或 `RELEASED`。
| WP-0301 | Indicator Registry与DAG | NOT_STARTED | — |
| WP-0302 | Feature Partition/Snapshot/Bundle | NOT_STARTED | — |
| WP-0303 | 市场宽度与情绪F2 | NOT_STARTED | — |
| WP-0304 | 板块与资金F2 | NOT_STARTED | — |
| WP-0305 | Hikyuu Cache Builder | NOT_STARTED | — |
| WP-0401 | Market Observation | NOT_STARTED | — |
| WP-0402 | Sector Registry与Observation | NOT_STARTED | — |
| WP-0403 | P-MARKET/P-SECTOR | NOT_STARTED | — |
| WP-0404 | P-DASH | NOT_STARTED | — |
| WP-0405 | 全球观察隔离 | NOT_STARTED | — |
| WP-0501 | MarketCloseFactPack | NOT_STARTED | — |
| WP-0502 | Review AI与Claim/Evidence | NOT_STARTED | — |
| WP-0503 | Review Projection与通知 | NOT_STARTED | — |
| WP-0504 | T+1/T+H Review Validation | NOT_STARTED | — |
| WP-0505 | P-REVIEW | NOT_STARTED | — |
| WP-0601 | StrategySpec Schema与安全DSL | NOT_STARTED | — |
| WP-0602 | Resolver/Compiler/Preview | NOT_STARTED | — |
| WP-0603 | A股市场规则与Hikyuu Adapter | NOT_STARTED | — |
| WP-0604 | Backtest Task与原子结果 | NOT_STARTED | — |
| WP-0605 | Prediction/Execution/Validation | NOT_STARTED | — |
| WP-0606 | P-STRATEGY/P-BACKTEST | NOT_STARTED | — |
| WP-0607 | 固定权重MVP | NOT_STARTED | — |
| WP-0701 | StockResearchFactPack/L0 | NOT_STARTED | — |
| WP-0702 | L1 Quick Research | NOT_STARTED | — |
| WP-0703 | P-STOCK/P-RESEARCH | NOT_STARTED | — |
| WP-0704 | L2 Deep Research（MVP二期、单只人工触发） | NOT_STARTED | — |
| WP-0801 | Owner Auth与Turnstile | NOT_STARTED | — |
| WP-0802 | 目标Compose与目录 | NOT_STARTED | — |
| WP-0803 | Cloudflare与NPM上线 | NOT_STARTED | — |
| WP-0804 | Backup/Restore | NOT_STARTED | — |
| WP-0805 | Release Candidate验收 | NOT_STARTED | — |

## 4. 状态更新要求

每次更新一行必须同时记录：

- 对应Commit/PR或当前工作树范围；
- Schema/Migration版本；
- 测试命令和结果；
- 运行环境和Fixture/Snapshot；
- 未验证项、风险和回滚；
- 若为页面，附可视证据；
- 若为`RELEASED`，附Deployment/Backup/Restore或运行观察Manifest。

Work Package定义与Exit Gate见[实施路线与验收方案 v1](implementation-roadmap-and-acceptance-v1.md)。
- 本轮新增阶段链连续性边界回归：`BackfillStageChainProjection` 现在只接受路线图连续前缀，拒绝跳过中间阶段的非连续 partial chain；WP-0207 仍为 `IN_PROGRESS / NOT CERTIFIED / 13/45`。
- 2026-09-28 当前回合：`git ls-remote origin refs/heads/main` 曾短暂返回目标 SHA，但随后复核因连接 `github.com:443` 失败（exit 128）；本地 `HEAD`、`main` 与缓存 `origin/main` 仍为 `46804661dbb897433f114c25898c8da7021254a1`，实时远程基线列为 BLOCKER。WP-0207 定向 Python 套件为 `185 passed, 15 skipped, 3 warnings`；PostgreSQL integration 因当前环境未配置连接变量而跳过，隔离 PostgreSQL 既有证据仍单独保留。WP-0206 代码、状态文档和 Run `34581431121` 未发现被当前未提交改动覆盖，WP-0207 继续为 IN_PROGRESS / NOT CERTIFIED / 13/45。
- 2026-09-28 当前 Goal 续验：本地分支 `main`、`HEAD` 与缓存 `origin/main` 仍为 `46804661dbb897433f114c25898c8da7021254a1`，`main...origin/main = 0/0`；本次 `git ls-remote origin refs/heads/main` 因 GitHub 连接低速超时失败，记录为实时远程基线 `BLOCKER`，未执行 `fetch`、`pull`、`reset`、`stash`、`commit`、`push` 或 PR。定向 Python 为 `182 passed, 15 skipped, 2 warnings`；Backfill Web Vitest 为 `9 passed`；Contract/generation、治理检查、受影响 Python `py_compile`、定向 ESLint、`tsc -b`、Vite build 和 `git diff --check` 通过。全量 Web ESLint 的 41 个错误仍属于未修改路径既有问题；隔离 PostgreSQL `16 passed` 证据仍为 deterministic fixture，不代表生产认证。WP-0207 保持 `IN_PROGRESS / NOT CERTIFIED / 13/45`。
- 2026-09-28 当前 Goal 续验补充：使用临时 `postgres:16-alpine`、tmpfs、loopback-only `127.0.0.1:55439` 和临时 Secret 文件执行 `tests/integration/platform/test_backfill_integration.py`，结果 `16 passed, 2 warnings`；测试容器和凭据已清理。该结果仅证明隔离 deterministic fixture，不代表真实 Provider、生产数据库、真实 `/data` 或生产回填认证。WP-0207 仍为 `IN_PROGRESS / NOT CERTIFIED / 13/45`。
- 2026-09-28 当前 Goal 续验：实时 `git ls-remote origin refs/heads/main` 成功返回 `46804661dbb897433f114c25898c8da7021254a1`，与本地 `HEAD`、`main` 和缓存 `origin/main` 一致，`main...origin/main = 0/0`。WP-0207 定向 Python/Contract 套件为 `182 passed, 15 skipped, 2 warnings`；Contract/generated exports、`check_ai_assets.py`、`check_visory_baseline.py` 均通过；范围审计未发现 WP-0301 或相邻 Work Package 路径。WP-0207 仍保持 `IN_PROGRESS / NOT CERTIFIED / 13/45`。

## 2026-09-28 当前 checkout 与 TaskLease 脱敏复核

- 当前实际 checkout 为 `codex/wp-0207-backfill`；文档记录前代码工作树 clean，本轮当前仅有本节文档改动；HEAD 为 `b5ab2da578cbad1e34e854cc3b67a0bc957185bb`；本地 `main`、缓存 `origin/main` 与实时 `git ls-remote origin refs/heads/main` 均为 `46804661dbb897433f114c25898c8da7021254a1`，未执行 fetch、pull、reset、stash、commit 或 push。
- WP-0206 代码、`GOAL-G019-STATUS.md` 与既有 Run `34581431121` 证据未被 WP-0207 覆盖；WP-0207 仍保持 `IN_PROGRESS / NOT CERTIFIED / 13/45`，不得标记 `VERIFIED` 或 `RELEASED`。
- 只读审计确认 `TaskLease.lease_token` 仅在 worker/Task Control Plane 内部使用；公共任务详情移除 `lease_token_hash`，列表/取消/重试仅返回 `TaskRecord`，SSE 仅返回 `TaskEventRecord`，Backfill/P-DATA Projection 不包含 raw lease token。当前未发现 WP-0207 直接的 raw lease token 公共暴露；本轮不修改既有 Durable Task 脱敏契约。
- 本轮不连接真实 Provider、生产数据库、真实 `/data`、生产调度或生产回填；隔离 deterministic fixture 证据不等同于生产认证。

## 2026-09-28 当前回合续验结果

- 实时 `git ls-remote origin refs/heads/main` 成功返回 `46804661dbb897433f114c25898c8da7021254a1`；当前 checkout 为 `codex/wp-0207-backfill`，HEAD 为 `b5ab2da578cbad1e34e854cc3b67a0bc957185bb`，未执行任何 Git 写操作。
- `.venv` 定向 Python 套件 `tests/platform/test_backfill.py tests/platform/api/test_generated_contracts.py tests/integration/platform/test_data_quality_api.py` 为 `188 passed, 3 warnings`；临时 `postgres:16-alpine`、tmpfs、loopback-only 容器中的 `tests/integration/platform/test_backfill_integration.py` 为 `16 passed, 1 warning`，容器与测试凭据已清理。
- Contract Registry/generated exports、`check_ai_assets.py`、`check_visory_baseline.py`、22 个受影响 Python 文件 `py_compile`、`git diff --check`、Backfill Web Vitest `9 passed`、修改文件定向 ESLint、`tsc -b` 和 Vite build 均通过。
- 当前证据仍不包含真实 Provider、生产数据库、真实 `/data`、生产调度或生产回填认证；WP-0207 保持 `IN_PROGRESS / NOT CERTIFIED / 13/45`，不得标记 `VERIFIED` 或 `RELEASED`。

## 2026-09-28 当前回合远程阻断复核

- 本轮只读执行 `git ls-remote origin refs/heads/main` 因 GitHub 连接低速超时失败；本次未取得实时远程 SHA，记录为远程基线 `BLOCKER`。
- 本地 `main`、缓存 `origin/main` 仍为 `46804661dbb897433f114c25898c8da7021254a1`；当前 checkout 仍为 `codex/wp-0207-backfill`，未执行 fetch、pull、reset、stash、commit 或 push。
- 本地 WP-0207 验收证据保持有效。该历史记录形成时尚未完成远程复核；现已确认 PR #38 已存在，Run `36404883866` 的三项远程阻断 Job 均成功，因此本条“专用 PR 与远程阻断 CI 仍未建立”结论已被后续事实取代；状态继续为 `IN_PROGRESS / NOT CERTIFIED / 13/45`，不得标记 `VERIFIED` 或 `RELEASED`。
