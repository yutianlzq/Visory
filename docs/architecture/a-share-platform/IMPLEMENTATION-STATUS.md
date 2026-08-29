# Visory 实现状态

最后更新：2026-08-29

## 1. 当前结论

文档状态：可执行基线已形成。

工程底座状态：DSA 固定提交 `fb4735a1055caefa2396982af3b09121feb9ff30` 已完成导入和双基线验收，状态为 `IMPORTED / VERIFIED`。导入代码中的 React/FastAPI、Legacy SQLite、内存 Task Queue、分析、LLM、报告、通知和数据 Fetcher 仍是迁移基线，不能作为 Visory 新契约已实现的证据。

目标架构状态：implemented work packages 为 `2/45`；`WP-0001`、`WP-0002` 均为 `VERIFIED`，`WP-0003` 为 `IN_PROGRESS`，其余 42 个 WP 为 `NOT_STARTED`。

最近完成的 Work Package：`WP-0002 PostgreSQL 与 Alembic 基础`。`Visory-G004` 已通过 PR #3 以 merge commit `75132082544239b011682d37cd626a29bca15b49` 合入 `main`。`Visory-G005 / WP-0003` 已从该固定基线启动并保持 `IN_PROGRESS`；验收证据齐全前 implemented work packages 仍为 `2/45`。

交付阶段：MVP 一期为本地核心功能版（M0—M6 + WP-0701—0703）；MVP 二期为本地生产预演与服务器发布版（WP-0704 + M8）。未过 Local Release Gate 不得将 WP 标记为 `RELEASED`。

### Goal 与底座状态

| 范围 | 状态 | 证据 |
| --- | --- | --- |
| Visory-G001 | COMPLETE | [G001 进度与验收记录](GOAL-STATUS.md) |
| Visory-G002 | COMPLETE | [G002 进度与验收记录](GOAL-G002-STATUS.md) |
| Visory-G003 | COMPLETE | [G003 / WP-0001 进度与验收记录](GOAL-G003-STATUS.md) |
| Visory-G004 | COMPLETE / MERGED | [G004 / WP-0002 进度与验收记录](GOAL-G004-STATUS.md)；PR #3 merge commit `7513208` |
| Visory-G005 | IN_PROGRESS | [G005 / WP-0003 进度与验收记录](GOAL-G005-STATUS.md) |
| DSA Baseline | IMPORTED / VERIFIED | 1126/1126 blob 验签；Python/Web 双基线；`baseline_regression_delta=0`；`web_lint_build_regression_delta=0` |
| Implemented Work Packages | 2/45 | `WP-0001`、`WP-0002` 为 `VERIFIED`；`WP-0003` 为 `IN_PROGRESS`；其余 42 项 `NOT_STARTED` |

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
| WP-0003 | API Envelope、Error与生成类型 | IN_PROGRESS | 固定基线 `7513208`；分支 `goal/g005-wp-0003-api-envelope-types`；完成全部验收前不得标记为 `VERIFIED` |
| WP-0101 | Asset Identity与Alias Resolver | NOT_STARTED | — |
| WP-0102 | Storage Namespace与Artifact Publisher | NOT_STARTED | — |
| WP-0103 | Durable Task Control Plane | NOT_STARTED | — |
| WP-0104 | Operations最小页面 | NOT_STARTED | — |
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
