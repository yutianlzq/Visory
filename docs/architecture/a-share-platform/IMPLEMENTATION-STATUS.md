# Visory 实现状态

最后更新：2026-08-30

## 1. 当前结论

文档状态：可执行基线已形成。

工程底座状态：DSA 固定提交 `fb4735a1055caefa2396982af3b09121feb9ff30` 已完成导入和双基线验收，状态为 `IMPORTED / VERIFIED`。导入代码中的 React/FastAPI、Legacy SQLite、内存 Task Queue、分析、LLM、报告、通知和数据 Fetcher 仍是迁移基线，不能作为 Visory 新契约已实现的证据。

目标架构状态：implemented work packages 为 `7/45`；`WP-0001`、`WP-0002`、`WP-0003`、`WP-0101`、`WP-0102`、`WP-0103`、`WP-0104` 均为 `VERIFIED`，其余 38 个 WP 为 `NOT_STARTED`。

最近完成的 Work Package：`WP-0104 Operations 最小页面`。`Visory-G009` 完成真实认证 ASGI/浏览器旅程、PostgreSQL SSE replay、连接池清理和 Operations 回归验收；PR #15 已合并，merge commit `9c03666740a1e7a90a616a2d774efc57ca5a0e6b`，最终 Run `33329710242` 的 Governance、Python、Web 三项阻断 Job 全部成功，状态为 `COMPLETE / MERGED / VERIFIED / 7/45`。

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
| DSA Baseline | IMPORTED / VERIFIED | 1126/1126 blob 验签；Python/Web 双基线；`baseline_regression_delta=0`；`web_lint_build_regression_delta=0` |
| Implemented Work Packages | 7/45 | `WP-0001`、`WP-0002`、`WP-0003`、`WP-0101`、`WP-0102`、`WP-0103`、`WP-0104` 为 `VERIFIED`；其余 38 项 `NOT_STARTED` |

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
| WP-0201 | Dataset/Provider Registry | NOT_STARTED | — |
| WP-0202 | Raw Ingestion | NOT_STARTED | — |
| WP-0203 | Canonical Normalization | NOT_STARTED | — |
| WP-0204 | DataSnapshot与Capability Gate | NOT_STARTED | — |
| WP-0205 | 16:00 Scheduler与补充源 | NOT_STARTED | — |
| WP-0206 | P-DATA数据质量页面 | NOT_STARTED | — |
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
