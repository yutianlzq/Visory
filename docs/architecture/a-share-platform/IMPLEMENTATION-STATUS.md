# Visory 实现状态

最后更新：2026-08-28

## 1. 当前结论

文档状态：可执行基线已形成。

代码状态：Visory尚未按M0—M8完成实现。当前`daily_stock_analysis`仓库的React/FastAPI、SQLite、内存Task Queue、分析、LLM、报告、通知和数据Fetcher是迁移基线，不能作为新契约已实现的证据。

下一Work Package：`WP-0001 Contract Registry与公共Schema`。

交付阶段：MVP一期为本地核心功能版（M0—M6 + WP-0701—0703）；MVP二期为本地生产预演与服务器发布版（WP-0704 + M8）。未过Local Release Gate不得将WP标记为`RELEASED`。

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
| WP-0001 | Contract Registry与公共Schema | NOT_STARTED | — |
| WP-0002 | PostgreSQL与Alembic基础 | NOT_STARTED | — |
| WP-0003 | API Envelope、Error与生成类型 | NOT_STARTED | — |
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
