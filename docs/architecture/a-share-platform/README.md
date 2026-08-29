# Visory 架构索引

状态：DSA Engineering Baseline Imported / Verified（目标架构 Work Package 2/45；WP-0001、WP-0002 VERIFIED，WP-0003 IN_PROGRESS）
最后更新：2026-08-29

本文是 **Visory** 个人A股研究平台的架构索引。面向Claude Code和Codex的需求、契约、页面、编码、实施和部署总入口见[Visory开发总指引](CLAUDE-CODE-GUIDE.md)。当前文档集已经形成可编码基线，但不代表相应能力已经完成开发；实现状态只能由代码、Migration、测试和运行证据证明。
> 当前工作区状态：G002 已将 `daily_stock_analysis` 固定提交 `fb4735a1055caefa2396982af3b09121feb9ff30` 导入项目，形成可安装、可测试、可构建的迁移底座；历史快照仍只读保存在 `upstream/daily_stock_analysis/`，其他外部项目保存在 `references/repos/`。G003/WP-0001 与 G004/WP-0002 均已完成并通过本地验收及 GitHub 三项阻断 CI；G004 已由 PR #3 以 merge commit `7513208` 合入 `main`。G005 正在实现 `WP-0003 API Envelope、Error 与生成类型`，验收完成前保持 `IN_PROGRESS`，已验证 Work Package 仍为 `2/45`。

## 项目标识

| 项 | 已确认值 |
| --- | --- |
| 产品名/页面展示名 | `Visory` |
| 代码和Compose新资源前缀 | `visory` |
| 定位 | 单owner、以A股为核心的个人研究与策略验证平台 |
| 开发基线 | 继续在当前`daily_stock_analysis`仓库渐进实现；`daily_stock_analysis`/`DSA`只表示上游底座或遗留模块，不再是目标产品名 |
| 本地运行根 | 由`VISORY_RUNTIME_ROOT`显式指定；开发默认使用仓库外部或已忽略的本地目录，测试使用临时目录 |
| 服务器物理根 | 保留已确认的`/data/daily_stock_analysis`；品牌更名不触发存储迁移 |
| 业务文件逻辑根 | `storage/app`；Manifest只保存逻辑StorageRef，不保存宿主机绝对路径 |

仓库Slug、Python遗留包名和已有`apps/dsa-web`目录不在文档阶段破坏性重命名；新的用户可见文案、Docker Compose Project、网络和未来新配置采用`Visory`/`visory`。源码目录迁移只能作为独立、可回滚的Work Package执行。

## 目标能力

平台最终覆盖：

- A 股市场情绪、市场宽度和大盘结构；
- 全球市场、资金行为、板块异动、热门板块和热点股；
- 个股题材、财务、估值、公告、新闻和资金行为证据；
- 策略定义、指标/因子验证、组合回测和模拟组合；
- AI 日报、收盘复盘、重点个股快速研究和深度研究；
- 数据质量、运行监控、结果复现和全链路追溯。

## 总体原则

1. **一个事实源**：所有页面、策略、回测和 AI 模块只消费统一数据平台发布的事实，不允许各仓库各自抓取并形成相互冲突的行情口径。
2. **一个正式回测内核**：Hikyuu 是正式策略回测与组合模拟内核；现有简单后验评估保留兼容语义，但不再扩展为第二套策略回测引擎。
3. **事实与观点分离**：行情、指标、财务和事件是事实；策略信号、预测和 AI 结论是有版本的派生结果，必须分表存储。
4. **时间可用性优先**：所有输入都记录 `available_at`，回测只可读取决策时点已经可用的数据。
5. **不可变快照**：原始数据、数据快照、指标快照、预测和回测运行均追加版本，不静默覆盖历史结果。
6. **模块化单体起步**：主 API 保持模块化单体，数据、量化和研究任务通过独立 Worker 隔离；出现明确规模瓶颈后再拆服务。
7. **外部项目通过适配器接入**：复用外部项目的能力和设计，不把多个完整应用直接拼成一个运行栈。

## 目标架构

```text
Visory 统一 Web / API（交互仅参考 tick-stock-panel/Vibe）
                            │
        ┌───────────────────┼────────────────────┐
        │                   │                    │
  Market/Sector       Strategy/Backtest     Review/Research
  Vibe 能力迁移        Sequoia + Hikyuu       DSA/UZI/Agents
        │                   │                    │
        └───────────────────┼────────────────────┘
                            │
                 Canonical Data + FactPack
                            │
        Raw → Normalized → Features → Marts/Snapshots
                            │
             a-stock-data + Financial-API Providers
```

Fleur 不作为运行时依赖。平台只吸收其数据契约、分层建模、策略表达、任务幂等、T+1、回测/模拟事实分离和工程治理思想。

## 已确认的架构决策

| 编号 | 决策 | 状态 | 说明 |
| --- | --- | --- | --- |
| D-001 | Hikyuu 作为唯一正式回测内核 | 已确认 | 指标/因子测试、策略交易回测和组合模拟统一由 Hikyuu Adapter 接入 |
| D-002 | Fleur 只作设计与策略参考 | 已确认 | 不引入 Furnace、Rearview、Racingline、RustFS、NATS、Dagster 和 Fleur 完整 ClickHouse 栈 |
| D-003 | 指标平台自主管理 | 已确认 | 建立 Indicator Registry 与 Feature Store，不依赖 Hikyuu 专属因子持久化能力 |
| D-004 | 日线策略采用 T/T+1/T+H 时序 | 已确认 | T 日冻结事实并预测，T+1 尝试执行，T+H 完成一个或多个周期验证 |
| D-005 | 预测、执行、验证分离 | 已确认 | 未成交不能伪装成策略收益；预测方向评估与可交易收益分别统计 |
| D-006 | 数据与结果全链路可追溯 | 已确认 | Validation → Prediction → Strategy/Feature/Data Snapshot → Raw Hash |
| D-007 | Financial-API 主用、a-stock-data 补充（原提案） | 已废止 | 数据源顺序经后续讨论调整，由 D-021 替代；保留编号用于记录决策演进 |
| D-008 | Vibe 能力迁入统一前端和数据口径 | 已确认 | 不运行第二套独立页面和数据后端；客观模块、全球隔离和复盘边界由D-027至D-029固化 |
| D-009 | DSA 负责日报和收盘复盘 | 已确认 | DSA 消费 FactPack，不重新抓取权威行情事实 |
| D-010 | UZI + TradingAgents 提供分层个股研究 | 已确认 | UZI 快速研究，TradingAgents 仅对重点标的执行深度研究；具体运行边界由 D-030 固化 |
| D-011 | 评分与资金权重分层管理 | 已确认 | 因子、个股仓位、策略资金、总仓/板块敞口四层分离，AI 置信度不直接等于资金权重 |
| D-012 | 自动寻优必须区分研究与样本外运行 | 已确认 | 全区间最优和同区间结果反推仅作研究；正式结果使用滚动训练、冻结执行和独立测试 |
| D-013 | v1 先覆盖沪深主板、创业板和科创板日线现货多头 | 已确认 | 北交所、分钟线、ETF、可转债、融资融券、做空和杠杆延后 |
| D-014 | 历史股票池和复权必须 point-in-time | 已确认 | 保留退市证券；指标使用时点复权序列，成交使用真实未复权价格，公司行动独立记账 |
| D-015 | T+1 开盘采用保守撮合 | 已确认 | 先卖后买；开盘涨停不买、开盘跌停不卖；订单当日有效，容量使用 T 日前 ADV20 |
| D-016 | v1 固化成本和容量基准 | 已确认 | 默认佣金万 3/最低 5 元、基础滑点 5 bp、100 万主资金和 1000 万容量对照，税费按日期版本化 |
| D-017 | StrategySpec 与执行/权重/组合/运行契约分离 | 已确认 | 策略只表达股票池、特征、筛选、评分、信号和退出，其他能力通过版本引用组合 |
| D-018 | StrategySpec 采用安全 DSL 与受控插件 | 已确认 | 禁止 YAML 内任意代码；复杂状态策略通过无网络/文件/数据库权限的标准插件输出信号 |
| D-019 | Preview、回测和模拟组合共用 Resolver/Compiler | 已确认 | 同一 ResolvedStrategySpec 必须生成相同候选、分数和信号，禁止页面或脚本另算 |
| D-020 | 采用 Fleur-Lite 五阶段异步回测模式 | 已确认 | Preview/Research/Formal 分级；Hikyuu 生成唯一正式业绩；PostgreSQL 持久任务替代 NATS，单 Worker 起步且重试不覆盖旧 Attempt |
| D-021 | a-stock-data 核心源、Financial-API 补充 | 已确认 | 数据必须经过Adapter、Canonical Schema和质量门禁；降级产生新分区和新DataSnapshot |
| D-022 | 规范股票代码作为唯一业务标识 | 已确认 | 使用带市场前缀的`canonical_id`（如`sh600519`、`sz000001`）；六码裸码只作输入/显示，保留asset_type防串桶 |
| D-023 | 交易日16:00启动盘后数据采集 | 已确认 | 由17:00前移以增加计算窗口；16:30目标发布Provisional、16:40启用补充源、17:10目标认证核心数据、19:00为T日正式策略硬截止 |
| D-025 | 建立市场情绪与资金行为模块 | 已确认 | 情绪采用五维固定解释分；资金按订单规模、杠杆、公开席位、大宗、板块和互联互通分证据建模，并保存可信度和时点血缘 |
| D-026 | 板块与热点观察域不建立统一评分 | 已确认 | 只展示客观指标、独立榜单、公开排名和规则事件；具体Strategy引用相关因素时才生成策略专属评分并交由Hikyuu验证 |
| D-027 | 全球市场只作观察和复盘背景 | 已确认 | 全球指数、汇率、利率、商品和海外事件不进入Strategy、权重、Paper Portfolio或Hikyuu回测；失败不阻断A股流水线 |
| D-028 | Feature Store采用三级物化和不可变Manifest | 已确认 | F1/F2公共特征长期物化，F3策略特征按需缓存；PostgreSQL管理控制面，Parquet与DuckDB承载数据和计算，正式引用永久固定 |
| D-029 | DSA收盘复盘采用FactPack、AI分析和报告三层分离 | 已确认 | DSA复用任务、LLM、渲染、历史和通知能力；Vibe系列迁移客观模块；T+1观察条件只验证，不自动成为策略信号 |
| D-030 | DSA统一承载L0/L1/L2个股研究 | 已确认 | UZI迁移快速研究、覆盖矩阵和自查门禁；TradingAgents迁移七角色、辩论和风险审查；共用StockResearchFactPack且研究观点不自动进入策略 |
| D-031 | 主平台采用DSA模块化单体和持久任务控制面 | 已确认 | React/Vite与FastAPI作为统一平台壳；PostgreSQL管理任务和权限；Parquet/DuckDB承载数据；单重Worker；MVP只有owner，viewer延后 |
| D-032 | 公网域名采用Cloudflare + NPM + Visory唯一密码 + Turnstile | 已确认 | Cloudflare橙云和Full Strict；NPM反代与DNS-01证书；公网v1仅owner；登录同时校验Turnstile与密码；全部目录位于`/data/daily_stock_analysis` |
| D-033 | 建立跨模块契约收敛总纲并确认C-001基础语义 | 已确认 | `entity_key=asset_type:canonical_id`全局隔离资产；时间、发布/修订/质量/任务/阶段状态和版本Hash分层；禁止新增裸`status` |
| D-034 | 固化Claude Code/Codex可执行文档与C-002至C-013实现基线 | 已确认 | 统一资源ID、存储根、Provider/Snapshot/Feature/Task/Run/Fact/API/部署契约，并建立需求闭环、页面原型、编码规范和M0—M9实施路线 |
| D-035 | 目标产品统一命名为Visory | 已确认 | 界面、新服务和新资源使用`Visory`/`visory`；DSA只作遗留底座语义；保留已确认的服务器物理根 |
| D-036 | 本地开发验收通过后才允许服务器部署 | 已确认 | 一期完成本地核心功能闭环；二期先在本地完成安全/部署预演，再由owner提供Secret并发布到服务器 |

## 模块设计状态

| 模块 | 主要职责 | 参考/复用 | 状态 | 文档 |
| --- | --- | --- | --- | --- |
| 指标、因子与回测 | 指标注册、因子评价、T+1 执行、组合回测、追溯 | Hikyuu；Fleur 设计 | 已形成首版设计 | [指标、预测与 Hikyuu 回测架构](backtest-and-indicator-architecture.md)；[A 股 Feature Store 与指标注册中心架构 v1](feature-store-architecture.md)；[A 股回测市场规则 v1](backtest-market-rules-v1.md)；[Fleur-Lite 回测运行与结果一致性架构](fleur-lite-backtest-runtime.md) |
| 评分与自动权重 | 因子/仓位/策略/敞口权重、滚动寻优、AI Overlay、均值方差与叠加归因 | Hikyuu；Fleur 设计 | 已形成首版设计 | [评分、仓位与自动权重优化架构](weight-optimization-architecture.md) |
| 数据平台 | Provider、契约、Raw/Normalized、Feature Store、快照、质量、发布SLA | a-stock-data、Financial-API、Fleur 设计 | 已形成首版设计 | [A 股数据平台与 Canonical Data Contract v1](data-platform-and-canonical-contract.md)；[盘后数据采集与 Snapshot 发布 SLA v1](data-ingestion-and-snapshot-sla.md)；[A 股 Feature Store 与指标注册中心架构 v1](feature-store-architecture.md) |
| 市场与板块 | 宽度、情绪、资金行为、全球市场、板块资金、热点 | Vibe-Research；vibe-astock；global-stock-data；a-stock-data；Financial-API | 已形成首版设计 | [A 股市场情绪与资金行为架构 v1](market-sentiment-and-capital-flow-architecture.md)；[A 股板块异动、热门观察与策略评分边界 v1](sector-observation-and-strategy-scoring-architecture.md)；[全球市场观察与 A 股策略隔离架构 v1](global-market-observation-boundary.md) |
| 策略中心 | StrategySpec、策略版本、Sequoia 迁移、筛选与信号 | Sequoia-X、Fleur 设计 | 已形成首版设计 | [StrategySpec v1 策略契约](strategy-spec-v1.md) |
| 日报与复盘 | 收盘事实包、AI复盘、T+1观察验证、报告、历史和通知 | daily_stock_analysis；Vibe-Research；vibe-astock | 已形成首版设计 | [DSA A 股收盘复盘 FactPack 架构 v1](dsa-close-review-fact-pack.md) |
| 个股研究 | 客观事实卡、快速研究、深度研究、分歧、证据和自查 | daily_stock_analysis；UZI-Skill；TradingAgents-astock | 已形成首版设计 | [A 股分层个股研究与 StockResearchFactPack 架构 v1](stock-research-architecture.md) |
| 主平台与前端 | 页面、API、鉴权、查询、持久任务和统一运维入口 | daily_stock_analysis；tick-stock-panel、Vibe UI仅作交互参考 | 已形成首版设计 | [A 股主平台模块化单体、API、任务与权限架构 v1](platform-shell-api-task-permission-architecture.md) |
| 任务与运行 | 调度、Worker、重试、幂等、监控 | Fleur 设计 | 已形成回测运行首版设计 | [Fleur-Lite 回测运行与结果一致性架构](fleur-lite-backtest-runtime.md) |
| 部署与安全 | Docker、Cloudflare、NPM、唯一密码、Turnstile、目录、密钥、备份、资源限制 | 当前仓库部署能力；Cloudflare；Nginx Proxy Manager | 已形成首版设计 | [A 股平台 Docker、Cloudflare、NPM 与访问安全架构 v1](docker-cloudflare-npm-deployment-architecture.md) |
| 契约治理 | 身份、时间、状态、版本、数据、任务、API和MVP机器契约 | 全部平台模块 | C-001至C-013已形成实现基线 | [Visory契约收敛总纲 v1](platform-contract-convergence-v1.md)；[Visory实现契约目录 v1](platform-implementation-contract-catalog-v1.md) |
| 产品与功能闭环 | FR/NFR、用户旅程、页面、API、任务、产物和验收追踪 | 全部平台模块 | MVP需求基线已形成 | [需求与功能闭环 v1](product-requirements-and-feature-closure-v1.md) |
| 页面与交互 | 信息架构、路由、线框图、页面状态、Evidence与响应式 | React/Vite统一前端 | MVP UX基线已形成 | [页面信息架构与低保真原型 v1](page-prototypes-and-information-architecture-v1.md) |
| 工程与实施 | 代码规范、Migration、测试、Work Package、回填和Exit Gate | 当前仓库及目标平台 | M0—M9执行基线已形成 | [工程与编码规范 v1](engineering-and-coding-standards-v1.md)；[实施路线与验收方案 v1](implementation-roadmap-and-acceptance-v1.md) |
| 仓库与参考治理 | 文档、基础上游、外部参考快照、只读边界和后续代码目录规划 | daily_stock_analysis及九类参考项目 | 目录治理基线已形成 | [仓库布局与目录责任](repository-layout.md)；[参考项目采用矩阵](reference-adoption-matrix.md) |
| 实现状态 | Goal、底座、Work Package真实代码、验证和发布状态 | 全部平台模块 | G001—G004完成；G005/WP-0003进行中；已验证目标WP 2/45 | [Visory实现状态](IMPLEMENTATION-STATUS.md)；[G004进度](GOAL-G004-STATUS.md)；[G005进度](GOAL-G005-STATUS.md) |

## 仓库与参考项目治理

当前目录按职责分为：

- `src/`、`api/`、`apps/`、`scripts/`、`tests/` 等：已导入的 DSA 迁移底座；
- `.github/workflows/ci.yml`：唯一启用的 Visory 安全 CI；
- `docs/`：Visory 第一方需求、架构、契约、Goal/WP 状态，以及重定位的上游文档；
- `upstream-baseline/` 与 `third_party/`：固定提交清单、验证结果和许可证归属；
- `upstream/daily_stock_analysis/`：本地只读基础上游历史快照，不提交；
- `references/repos/`：九个本地只读外部参考快照，不属于运行时代码；
- `references/README.md` 与 `references/manifest.yaml`：可提交的参考治理说明和机器可读核验清单。

2026-08-28 已按 GitHub 默认分支 HEAD、Git tree/blob SHA 和提交历史完成十个快照核验：八个与核验时 HEAD 完全一致，`daily_stock_analysis` 与 `Financial-API` 对应已定位历史提交。Sequoia-X 与本地治理名为 UZI-Skill 的衍生快照（直接来源 `gosinkx/UZI-SKILL-astock`）的 MIT 信息仅来自 HEAD README 声明，其余许可证由 GitHub License API 检测。目录责任见[仓库布局与目录责任](repository-layout.md)，允许采用方式和 Work Package 边界见[参考项目采用矩阵](reference-adoption-matrix.md)，完整核验信息见[`../../../references/manifest.yaml`](../../../references/manifest.yaml)。核验不代表允许整体复制或直接依赖；代码吸收仍需按许可证、契约和独立 Work Package 执行。

G002 已按固定提交完成 DSA 底座导入与验证：1126/1126 blob 验签，Python 失败差异经对称重跑归一化为 `baseline_regression_delta=0`，固定 DSA 与 Visory 的 Web lint/build 均通过，`web_lint_build_regression_delta=0`。详细证据见 [Visory-G002 进度与验收记录](GOAL-G002-STATUS.md)。归档在 `docs/upstream/daily_stock_analysis/workflows/` 的上游 workflow 仅作测试证据，未启用。

## 推荐实施顺序

数据平台、Feature Store、市场/板块、复盘、研究、策略、Hikyuu回测、主平台及公网部署已经形成可编码文档基线。实现必须遵循[实施路线与验收方案](implementation-roadmap-and-acceptance-v1.md)，且所有代码、Migration、Compose和恢复流程先在本地/隔离环境验收，不直接在服务器边开发边试错：

1. M0：Contract Registry、公共Schema、PostgreSQL/Alembic和API Envelope；
2. M1：Identity、Storage/Artifact和持久Task；
3. M2—M3：Canonical Data、Snapshot、Feature和Hikyuu Cache；
4. M4—M7：市场/板块、复盘、Strategy/Hikyuu和个股研究；
5. M8：认证、Cloudflare/NPM、备份恢复和MVP发布；
6. M9：样本外自动权重、MVO、AI Overlay等MVP后能力。

`WP-0001 Contract Registry与公共Schema`、`WP-0002 PostgreSQL与Alembic基础` 已完成并处于 `VERIFIED`；`WP-0003 API Envelope、Error与生成类型` 已由 G005 启动并保持 `IN_PROGRESS`，必须在 C-010、Legacy 回归、确定性类型生成和 GitHub 三项阻断 CI 全绿后才能标记为 `VERIFIED`。每个Package必须补齐目标、边界、输入/输出契约、时序、存储、失败语义、追溯、测试、迁移、回滚和运行证据。
