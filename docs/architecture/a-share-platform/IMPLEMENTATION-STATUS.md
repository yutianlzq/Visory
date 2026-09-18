# Visory 实现状态

最后更新：2026-09-18

## 1. 当前结论

文档状态：可执行基线已形成。

工程底座状态：DSA 固定提交 `fb4735a1055caefa2396982af3b09121feb9ff30` 已完成导入和双基线验收，状态为 `IMPORTED / VERIFIED`。导入代码中的 React/FastAPI、Legacy SQLite、内存 Task Queue、分析、LLM、报告、通知和数据 Fetcher 仍是迁移基线，不能作为 Visory 新契约已实现的证据。

目标架构状态：implemented work packages 为 `13/45`；`WP-0001`、`WP-0002`、`WP-0003`、`WP-0101`、`WP-0102`、`WP-0103`、`WP-0104`、`WP-0201`、`WP-0202`、`WP-0203`、`WP-0204`、`WP-0205` 为 `VERIFIED`；其余 WP 为 `NOT_STARTED`。G013 Provider Raw Schema Hardening 已完成并通过最终 CI，仍计入同一 `WP-0202`。

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
| Implemented Work Packages | 13/45 | `WP-0001`、`WP-0002`、`WP-0003`、`WP-0101`、`WP-0102`、`WP-0103`、`WP-0104`、`WP-0201`、`WP-0202`、`WP-0203`、`WP-0204`、`WP-0205`、`WP-0206` 为 `VERIFIED`；其余 32 项 `NOT_STARTED` |

Current Goal: Visory-G019 / WP-0206 P-DATA 数据质量页面 is COMPLETE / MERGED from baseline `8bc1592e7bf3418555e3c6bec405404efd1b1841`; the implementation adds a read-only Data Quality Projection/API and `/data-quality?trade_date=YYYY-MM-DD` page over existing Snapshot, Capability, Provider, Canonical and Durable Task Control Plane contracts, including lineage drill-down, schedule timeline, revision/correction comparison, and controlled Recheck/Rebuild/Correction tasks. No new Migration is introduced and no real Provider, production database, real `/data`, production scheduler, or production `backtest_core` certification is included. Implemented work packages are `13/45`; P-DATA code capability gate is `VERIFIED`; implementation PR #36 merge commit `3db5057acd0029c6fb3557fe6a90ebfb2c288acd`; remote CI Run `34581431121` passed Governance, Python deterministic gate, and Web lint/build.

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
| WP-0207 | 分批Backfill | NOT_STARTED | — |
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
