# Visory 开发总指引（Claude Code / Codex）

状态：Executable Documentation Baseline

最后更新：2026-08-28

## 1. 如何使用本文

本文是 **Visory** 开发的单一索引入口，供owner、Claude Code、Codex和代码审查者使用。它不重复所有字段和算法，而是明确：目标是什么、哪些决策已锁定、架构如何分层、每类问题去哪里找权威答案、代码按什么顺序实现、怎样证明功能闭环。

开始任何实现任务前，Claude Code或Codex必须：

1. 阅读根目录`AGENTS.md`；
2. 在本文定位目标FR、Contract和Work Package；
3. 阅读本文指定的最小权威文档集；
4. 检查现有代码、配置、测试和Migration；
5. 只实现一个可验收Work Package；
6. 完成代码、Schema、数据、API、页面、任务、失败路径、测试和文档闭环；
7. 用真实命令和产物证明结果，不把“已设计”当作“已实现”。

## 2. 项目目标

建设一套名为 **Visory** 的个人A股研究平台，覆盖：

- A股情绪、大盘结构、市场宽度、资金行为；
- 板块异动、热门板块、热点股和题材关联；
- 个股行情技术、资金证据、财务、估值、公告、新闻和风险；
- DSA AI日报、收盘复盘、T+1/T+H观察验证；
- L0事实卡、L1快速研究、L2重点个股深度研究；
- StrategySpec、指标/因子、评分、权重和策略版本；
- Hikyuu正式回测、预测/成交/验证、归因和复现；
- 统一数据质量、任务、监控、权限、部署、备份和恢复。

平台是研究辅助系统，不自动连接实盘券商，不承诺收益。

### 2.1 命名与运行环境

- 产品、页面标题、新Compose Project和新Docker网络统一使用`Visory`/`visory`；
- `daily_stock_analysis`和`DSA`只用于指代当前仓库、上游能力或需要兼容的Legacy实现；
- 本地开发通过`VISORY_RUNTIME_ROOT`绑定仓库外部或已忽略的运行目录，测试使用临时目录；
- 服务器继续使用已确认的`/data/daily_stock_analysis`物理根，业务Manifest不记录绝对路径；
- 品牌更名不触发仓库Slug、历史Python包或`apps/dsa-web`目录的一次性破坏迁移。

## 3. 已锁定的核心决策

| 领域 | 实现基线 |
| --- | --- |
| 产品标识 | 产品名`Visory`，新资源技术前缀`visory` |
| 主平台 | 以daily_stock_analysis现有React/Vite + FastAPI为模块化单体底座 |
| 正式回测 | Hikyuu是唯一正式回测内核 |
| Fleur | 只吸收策略/数据/任务/五阶段回测设计，不作为运行时依赖 |
| 数据源 | a-stock-data核心，Financial-API补充/校验/受控灾备 |
| 唯一身份 | `canonical_id`是资产类型上下文代码；跨域使用`entity_key=asset_type:canonical_id` |
| 数据发布 | Raw→Canonical→DataSnapshot→FeatureSnapshot→Observation/FactPack |
| 盘后调度 | 交易日16:00开始，19:00是正式策略硬截止 |
| 特征 | F1/F2长期物化，F3按需缓存；PostgreSQL控制面，Parquet/DuckDB数据面 |
| 市场/板块 | 展示客观指标、独立榜单和规则事件；不建立平台统一热度评分 |
| 策略评分 | 只有具体Strategy引用相关因素时才产生版本化评分 |
| 全球市场 | 仅用于页面和复盘背景，不进入A股Strategy、权重、Paper或Hikyuu回测 |
| 收盘复盘 | MarketCloseFactPack→AI Analysis→Claim/Evidence→Report/Validation |
| 个股研究 | DSA统一L0/L1/L2；吸收UZI和TradingAgents方法，不运行多个独立平台 |
| 时间 | 正式事实带`available_at`；Formal消费必须满足`available_at <= cutoff_at` |
| 修订 | 正式对象不可变；Correction生成新Revision和新资源ID |
| 任务 | PostgreSQL Task/Attempt/Lease；单重Worker优先；重试不覆盖Attempt |
| 安全 | Cloudflare橙云+Full Strict+NPM+owner密码+Turnstile服务端验证 |
| 目录 | 服务器运行资产在`/data/daily_stock_analysis`，本地由`VISORY_RUNTIME_ROOT`绑定；业务文件唯一逻辑根为`storage/app` |
| MVP资产 | 沪深主板、创业板、科创板日线现货多头 |
| MVP回填 | 核心数据2018-01-01至今，财务从2017报告期开始；新闻从上线日增量 |
| 交付顺序 | 所有功能、Migration、Compose和恢复流程先本地/隔离验收，通过Local Release Gate后才部署服务器 |

更完整的D-001至D-036记录见[架构索引](README.md)。

## 4. 文档权威顺序

冲突时按以下顺序处理：

1. 根目录`AGENTS.md`：仓库协作、安全、验证和提交规则；
2. [平台契约收敛总纲](platform-contract-convergence-v1.md)：C-001至C-003基础语义；
3. [平台实现契约目录](platform-implementation-contract-catalog-v1.md)：C-004至C-013对象、字段和不变量；
4. [需求与功能闭环](product-requirements-and-feature-closure-v1.md)：FR/NFR、范围和验收；
5. 对应领域架构文档：公式、时序、业务边界；
6. [工程与编码规范](engineering-and-coding-standards-v1.md)：代码、数据库、API、前端和测试；
7. [页面原型](page-prototypes-and-information-architecture-v1.md)：路由、组件、状态和交互；
8. [实施路线](implementation-roadmap-and-acceptance-v1.md)：Work Package、顺序和Exit Gate；
9. 示例配置/Payload；
10. 当前Legacy实现。

当前代码与目标契约冲突时，不能直接把Legacy行为提升为新契约。先判断是需要Legacy Adapter、迁移还是修正文档。

## 5. 总体架构

### 5.1 逻辑架构

```text
┌─────────────────────────────────────────────────────────────────────┐
│ React/Vite统一Web：Dashboard/Market/Sector/Stock/Review/Strategy/...│
└──────────────────────────────┬──────────────────────────────────────┘
                               │ /api/v1 + SSE + owner session
┌──────────────────────────────▼──────────────────────────────────────┐
│ FastAPI模块化单体                                                │
│ Identity | Data | Feature | Observation | Review | Research       │
│ Strategy | Backtest | Task | Auth | Operations                    │
└──────────────┬───────────────────┬──────────────────┬───────────────┘
               │                   │                  │
      ┌────────▼────────┐ ┌────────▼────────┐ ┌──────▼───────────┐
      │ PostgreSQL控制面 │ │ Parquet/DuckDB  │ │ Durable Worker   │
      │ Registry/Task/  │ │ Facts/Features/ │ │ Provider/Feature/│
      │ Manifest/Audit  │ │ Results/Artifact│ │ Hikyuu/AI        │
      └────────┬────────┘ └────────┬────────┘ └──────┬───────────┘
               └───────────────────┼──────────────────┘
                                   │
                       ┌───────────▼────────────┐
                       │ a-stock-data核心       │
                       │ Financial-API补充      │
                       │ Hikyuu唯一Formal Engine│
                       └────────────────────────┘
```

### 5.2 运行单元

```text
Cloudflare → NPM → visory-api（React静态资源+FastAPI）
                          │
                  PostgreSQL控制面
                          │
              scheduler → durable-worker
                          │
        /data/daily_stock_analysis/storage/app
```

MVP不引入NATS、Kafka、Dagster、ClickHouse、RustFS或多微服务。只有出现真实Benchmark和隔离需求后才评估拆分。

### 5.3 数据闭环

```text
ProviderRun
  → RawObject
  → CanonicalPartition
  → DataSnapshot(Capability Gate)
  → FeaturePartition/FeatureSnapshot
  → ObservationSnapshot/FactPack
  ├→ 页面客观展示
  ├→ DSA Review / Stock Research
  └→ Strategy Compiler → Hikyuu Run
                           ├→ Prediction(T)
                           ├→ Execution(T+1)
                           └→ Validation(T+H)
```

页面、AI和Hikyuu都不能绕过发布快照重新抓取事实。

## 6. 功能模块与权威文档

| 模块 | 主要产物 | 必读文档 |
| --- | --- | --- |
| 产品范围/闭环 | FR/NFR、页面、API、任务、验收矩阵 | [需求与功能闭环](product-requirements-and-feature-closure-v1.md) |
| 基础契约 | Identity、时间、状态、版本、Hash、Storage | [契约收敛总纲](platform-contract-convergence-v1.md) |
| 实现契约 | Provider/Snapshot/Feature/Task/Run/Fact/API/Deploy | [实现契约目录](platform-implementation-contract-catalog-v1.md) |
| 数据平台 | Provider、Raw、Canonical、Snapshot、质量 | [数据平台契约](data-platform-and-canonical-contract.md)、[采集SLA](data-ingestion-and-snapshot-sla.md) |
| 特征指标 | Indicator、F1/F2/F3、DAG、Manifest | [Feature Store](feature-store-architecture.md)、[指标回测架构](backtest-and-indicator-architecture.md) |
| 市场情绪/资金 | 市场状态、五维情绪、资金Evidence | [市场情绪与资金](market-sentiment-and-capital-flow-architecture.md) |
| 板块热点 | Taxonomy、客观榜单、异动、热点股 | [板块与评分边界](sector-observation-and-strategy-scoring-architecture.md) |
| 全球观察 | 页面背景、与策略隔离 | [全球观察边界](global-market-observation-boundary.md) |
| 收盘复盘 | MarketCloseFactPack、Review、Claim、Validation | [DSA收盘复盘](dsa-close-review-fact-pack.md) |
| 个股研究 | StockResearchFactPack、L0/L1/L2、Evidence | [分层个股研究](stock-research-architecture.md) |
| 策略 | StrategySpec、安全DSL、Compiler | [StrategySpec v1](strategy-spec-v1.md) |
| 回测规则 | 股票池、价格、T+1、费用、容量、基准 | [A股回测市场规则](backtest-market-rules-v1.md) |
| 回测运行 | Preview/Research/Formal、Task、Attempt、Artifact | [Fleur-Lite运行架构](fleur-lite-backtest-runtime.md) |
| 权重 | 固定权重、滚动寻优、AI/MVO边界 | [权重优化架构](weight-optimization-architecture.md) |
| 平台壳 | API、持久任务、权限、Operations | [主平台架构](platform-shell-api-task-permission-architecture.md) |
| 页面 | 路由、线框图、状态、响应式 | [页面原型](page-prototypes-and-information-architecture-v1.md) |
| 编码 | Python/Postgres/Parquet/API/React/测试/安全 | [工程规范](engineering-and-coding-standards-v1.md) |
| 实施 | M0–M9、WP、回填、验收、发布/回滚 | [实施路线](implementation-roadmap-and-acceptance-v1.md) |
| 实现状态 | 每个WP的真实代码/验证/发布状态 | [实现状态](IMPLEMENTATION-STATUS.md) |
| 部署 | Docker、Cloudflare、NPM、配置、Secret、备份 | [部署安全架构](docker-cloudflare-npm-deployment-architecture.md) |

## 7. 外部项目复用边界

| 项目 | 吸收 | 不直接采用 |
| --- | --- | --- |
| daily_stock_analysis | React/FastAPI壳、LLM、报告、通知、历史、现有分析能力 | 现有SQLite/内存Task作为目标架构 |
| Hikyuu | 正式交易回测、组合和市场模拟能力 | 让Hikyuu成为指标/数据唯一存储 |
| Fleur | 五阶段、任务幂等、数据/策略契约、筛选瘦身理念 | 完整运行时和重基础设施 |
| a-stock-data | 核心数据能力、来源适配经验 | 外部Schema直接成为平台事实 |
| Financial-API | 补充、交叉校验、批量数据能力 | 静默逐行混合或全局主源 |
| Vibe-Research | 市场宽度、全球、板块资金、复盘页面思想 | 第二套前端和独立事实口径 |
| Sequoia-X | 策略结构、候选策略方法 | 任意代码策略或第二回测引擎 |
| UZI-Skill | L1覆盖矩阵、快速研究、自查方法 | 运行时拉取可变Skill作为事实源 |
| TradingAgents-astock | L2七角色、辩论、风险审查 | 全市场自动多Agent或自动下单 |
| tick-stock-panel | Dashboard信息密度和交互参考 | 直接拼接独立应用 |

任何外部模块先转换为平台Contract，并经过许可证、依赖、安全、数据口径和资源审查。

## 8. 页面与功能闭环

```text
P-DATA确认事实可用
  → P-MARKET/P-SECTOR发现结构与异动
    → P-STOCK核对个股事实
      → P-RESEARCH形成带证据研究
        → P-STRATEGY人工形成可执行规则
          → P-BACKTEST正式验证
            → P-REVIEW复盘Prediction/Execution/Validation
              → 新Strategy版本（人工批准）
```

运维闭环始终并行：

```text
P-TASKS发现失败/阻塞
  → Task/Attempt/Artifact诊断
  → Retry/Correction/Rebuild
  → P-DATA重新认证
  → 消费者显式绑定新资源
```

页面详细图见[页面原型](page-prototypes-and-information-architecture-v1.md)，FR到页面/API/任务/产物/测试的矩阵见[需求文档第8节](product-requirements-and-feature-closure-v1.md#8-功能闭环追踪矩阵)。

## 9. 数据契约快速规则

Claude Code写任何新持久对象前必须回答：

```text
谁拥有写入？
业务唯一键是什么？
公开resource_id是什么？
哪些时间字段适用？available_at如何得到？
Schema/Definition/Policy/Revision分别如何变化？
质量、Capability、Partial和失败如何表达？
上游Resource Reference和Hash是什么？
存在PostgreSQL还是Parquet/Artifact？
物理路径和Retention是什么？
Correction/Retry是否创建新对象？
哪些消费者可以读取？
Golden成功/降级/失败/修订样例在哪里？
```

任一问题无答案，不开始业务实现。

## 10. 实施顺序与MVP两期

| Milestone | 结果 | 入口 |
| --- | --- | --- |
| M0 | Contract Registry、PostgreSQL、统一API错误 | WP-0001~0003 |
| M1 | Identity、Storage/Artifact、Durable Task、Operations | WP-0101~0104 |
| M2 | Provider/Raw/Canonical/Snapshot、16:00、P-DATA、Backfill | WP-0201~0207 |
| M3 | Indicator/Feature、市场/板块F2、Hikyuu Cache | WP-0301~0305 |
| M4 | Market/Sector/Dashboard/Global隔离页面 | WP-0401~0405 |
| M5 | DSA FactPack/Review/Claim/Validation | WP-0501~0505 |
| M6 | StrategySpec/Hikyuu/Prediction/Validation/页面 | WP-0601~0607 |
| M7 | L0/L1研究；L2单只人工深研在MVP二期交付 | WP-0701~0704 |
| M8 | Auth/Turnstile/Compose/Cloudflare/Backup/MVP | WP-0801~0805 |
| M9 | 自动权重、MVO、AI Overlay、Paper等 | MVP后 |

第一项编码任务固定为`WP-0001 Contract Registry与公共Schema`，当前状态见[实现状态](IMPLEMENTATION-STATUS.md)。不得跳过M0/M1直接实现页面或Hikyuu正式运行，因为身份、时间、任务和Artifact会再次返工。

### 10.1 MVP一期：本地核心功能闭环

范围是`M0—M6 + WP-0701—WP-0703`，共39个WP，必须在本地或隔离测试环境完成：

1. 契约、PostgreSQL、身份、StorageRef、持久任务和Operations；
2. a-stock-data/Financial-API Adapter、Raw/Canonical/Snapshot、16:00调度及分批回填；
3. Feature Store、市场宽度/情绪/资金、板块/热点、消息证据和总览页；
4. 收盘FactPack、AI复盘、Claim/Evidence和T+1/T+H观察验证；
5. StrategySpec、固定/等权、Hikyuu Formal回测和Prediction/Execution/Validation追溯；
6. 个股L0事实卡、L1快速研究与页面闭环。

一期产物只允许绑定本机回环或受控开发网络，不配置真实Cloudflare DNS，不将开发数据写入服务器正式根。

### 10.2 MVP二期：本地生产预演与服务器发布

范围是`WP-0704 + M8`，共6个WP：

1. 单只、owner人工触发的L2深度研究，含七角色、分歧、Checkpoint和资源上限；
2. owner密码、Session、CSRF、Turnstile、全路由默认保护与安全反例；
3. Visory双Compose、最小挂载、非root运行、备份/恢复和镜像Digest；
4. 在本地/CI完成Compose Config、Build、Migration、Loopback、Restore和升降级预演；
5. Local Release Gate通过后，再由owner在服务器提供Secret、域名和基础设施配置，完成Cloudflare/NPM上线及恢复演练。

### 10.3 Local Release Gate

未同时满足以下条件，AI agent不得执行服务器写操作：

- MVP一期的所有必需WP达到`VERIFIED`；
- 本地无Secret的生产等价Compose可构建、可启动、可健康检查；
- Migration空库升级、兼容回滚和备份恢复预演通过；
- Golden契约、PIT、Hikyuu市场规则、安全反例和核心E2E通过；
- 本地Benchmark和目标服务器预检表明磁盘/内存/任务排队可接受；
- owner明确批准部署窗口、备份点和回滚方案。

## 11. Claude Code / Codex执行协议

### 11.1 开始任务

1. 在实施路线复制WP模板；
2. 列出FR、Contract、允许修改范围和非目标；
3. 用`rg`查找现有实现、测试、配置和文档；
4. 检查工作树，保留用户现有改动；
5. 为当前WP建立最小计划；
6. 先写/更新Golden Contract和失败反例，再写实现。

### 11.2 实现顺序

```text
Schema/Enum
  → Migration/Repository
  → Domain Policy/State Machine
  → Application Service
  → Worker/Artifact
  → API/OpenAPI
  → Generated Type/UI
  → Contract/Integration/E2E/Security Test
  → Docs/Changelog
```

不是每个WP都涉及所有层，但受影响层不能遗漏。

### 11.3 必须暂停的情况

- 文档之间存在无法按权威顺序解决的冲突；
- 需要新增外部服务、付费数据、券商权限或远端写操作；
- 真实Provider不具备文档假定的字段/历史/许可证；
- Migration可能破坏用户数据且没有兼容/备份路径；
- Formal结果无法证明PIT、Hash或Hikyuu规则；
- 实现范围需要跨越多个Milestone或大规模移动现有代码；
- 需要Secret、域名、Cloudflare Token或owner密码。

暂停时给出证据、影响、可选方案和推荐，不写猜测Fallback。

### 11.4 禁止行为

- 页面/策略/AI直接访问Provider；
- Router直接写业务表；
- 使用裸`status/version/date/hash`；
- 用当前股票池、当前名称或回填时间覆盖历史；
- 覆盖旧Snapshot/Attempt/Result；
- 用`latest`构建Formal Run；
- 使用`eval/exec`策略；
- Hikyuu运行中联网补数；
- 全球观察进入A股策略；
- AI直接发布策略或权重；
- 保存宿主机绝对Artifact路径；
- 静默把失败变为空数据/成功；
- 把Secret写入Git、日志、Manifest、前端或测试Fixture。

## 12. 单个PR的完成定义

只有同时满足以下条件才可声称完成：

1. 目标FR和Contract行为已实现，不是占位；
2. Schema/Migration/Repository/API/UI/Worker受影响面一致；
3. 成功、Partial/Degraded、失败、重试/Correction路径明确；
4. PIT、幂等、权限、资源和Hash不变量有测试；
5. Legacy兼容或迁移有证据；
6. 相关验证命令真实通过；
7. OpenAPI、生成类型、`.env.example`和文档按影响同步；
8. 页面改动有Desktop/Mobile和状态证据；
9. 性能/磁盘/内存风险按WP预算验证；
10. 回滚路径可执行；
11. `git diff`无无关改动、Secret和路径漂移；
12. 需求闭环矩阵能指向测试或运行证据。

## 13. 完整MVP验收

MVP发布前必须证明：

- 2018至今核心数据回填和当前日16:00链路可用；
- Snapshot按Capability认证，Correction可追溯；
- 市场/板块/个股/数据质量/任务页面使用同一事实链；
- DSA复盘和L1研究的Claim具有Evidence；
- 最少两个代表性Strategy在Hikyuu完成2018至今Formal回测；
- T/T+1/T+H、未成交、市场规则和账本通过Golden验证；
- 相同RunBundle重复结果确定；
- Cloudflare/NPM/密码/Turnstile保护全部入口；
- 备份已在空恢复环境完成Restore Manifest；
- 当前服务器资源Benchmark达标或任务策略显式排队；
- 所有MVP FR/NFR有直接证据，无悬空项。

详细场景见[实施路线第15节](implementation-roadmap-and-acceptance-v1.md#15-mvp全链路验收)。

## 14. 部署交接

owner负责提供/配置：

- 实际域名及Cloudflare Zone；
- Cloudflare DNS API Token、Turnstile Site/Secret Key；
- owner密码/Hash初始化输入；
- a-stock-data/Financial-API所需凭据；
- LLM Provider Key；
- 备份目标和加密口令。

Claude Code负责生成不含Secret的Compose、`.env.example`、配置模板、Preflight、备份/恢复脚本和检查清单。具体目录、网络、NPM、Cloudflare和恢复流程见[部署安全架构](docker-cloudflare-npm-deployment-architecture.md)。在owner填入配置前，可以完成离线Schema、Compose Config、容器Build和本地Loopback测试，但不能宣称公网部署完成。

## 15. 文档维护规则

- 新需求先分配FR/NFR ID；
- 新跨模块对象先分配Contract ID并登记；
- 新实现工作先分配WP；
- 业务口径变化先更新领域文档和Definition/Policy版本；
- 页面变化同步原型和E2E；
- 配置变化同步`.env.example`和部署文档；
- 每次用户可见/契约/部署变化更新`docs/CHANGELOG.md`；
- 文档中的`Implementation Baseline`表示可编码，不表示代码已完成；
- 只有实际Exit Gate证据可以更新Milestone实现状态。

## 16. 快速检查清单

### 开始前

- [ ] 已读`AGENTS.md`
- [ ] 已确定FR/Contract/WP
- [ ] 已读最小权威文档集
- [ ] 已检查当前代码/测试/工作树
- [ ] 已列出非目标和风险

### 编码中

- [ ] 先Schema/反例，后实现
- [ ] 无第二事实源/第二状态机/第二公式
- [ ] PIT、Hash、版本、血缘完整
- [ ] 失败、Partial、Retry、Correction可观察
- [ ] Secret、路径、权限安全

### 交付前

- [ ] 验证命令真实执行
- [ ] 数据库/API/前端/Worker契约一致
- [ ] 文档/Changelog/配置同步
- [ ] 性能、迁移、回滚已说明
- [ ] 功能闭环有验收证据

## 17. 下一步

文档基线完成后，编码从[WP-0001 Contract Registry与公共Schema](implementation-roadmap-and-acceptance-v1.md#wp-0001-contract-registry与公共schema)开始。首次任务只实现基础Schema、验证器、JSON Schema导出和Golden Payload，不引入业务页面、不迁移生产数据、不修改远程部署。

## 18. 文档交付覆盖审计

| 用户要求 | 权威交付物 | 完成证据 |
| --- | --- | --- |
| 指引文档是索引文档 | 本文 | 决策、架构、模块、执行协议和全部专题入口集中在本文 |
| 架构设计 | [架构索引](README.md)及17份领域设计 | 逻辑架构、运行单元、数据流、模块边界和外部复用边界明确 |
| 功能设计 | [需求与功能闭环](product-requirements-and-feature-closure-v1.md) | DATA/MKT/SECTOR/STOCK/REVIEW/STRATEGY/BT/OPS功能均有ID和验收 |
| 需求文档 | [需求与功能闭环](product-requirements-and-feature-closure-v1.md) | 用户、范围、FR、NFR、场景、页面和变更规则齐全 |
| 编码规范 | [工程与编码规范](engineering-and-coding-standards-v1.md) | Python、数据库、文件、Provider、Hikyuu、API、前端、AI、测试、安全和DoD齐全 |
| 原型设计/页面图 | [页面原型](page-prototypes-and-information-architecture-v1.md) | 全局平台壳、12个页面线框图、状态、数据和响应式规则齐全 |
| 实施方案 | [实施路线](implementation-roadmap-and-acceptance-v1.md) | M0—M9、45个WP、历史回填、Exit Gate、发布和回滚明确 |
| 部署方案 | [部署安全架构](docker-cloudflare-npm-deployment-architecture.md) | Docker、Cloudflare、NPM、Turnstile、目录、Secret、备份和恢复明确 |
| 数据契约要素明确 | [契约总纲](platform-contract-convergence-v1.md)与[实现契约目录](platform-implementation-contract-catalog-v1.md) | C-001至C-013、责任矩阵、字段、时间、版本、质量、血缘、存储、保留和Golden Gate明确 |
| 功能闭环 | [功能闭环追踪矩阵](product-requirements-and-feature-closure-v1.md#8-功能闭环追踪矩阵) | 每个闭环绑定需求、页面、API、Task、输入、正式输出和验收证据 |
| 可指导Claude Code | 本文、[实施路线](implementation-roadmap-and-acceptance-v1.md)、[实现状态](IMPLEMENTATION-STATUS.md) | 固定首个WP、任务模板、实现顺序、暂停条件、禁止项和完成定义 |

审计只证明文档交付完整，不证明目标平台代码已经实现；代码状态始终以[实现状态](IMPLEMENTATION-STATUS.md)及其证据为准。

## 19. 功能模块闭环审计

| 闭环 | 起点 | 处理 | 正式产物 | 反馈/失败路径 | 文档结论 |
| --- | --- | --- | --- | --- | --- |
| 数据 | Provider | Raw→Canonical→Quality Gate | DataSnapshot | Correction/Quarantine/Capability | 已闭环 |
| 指标 | Certified DataSnapshot | DAG、增量分区、PIT | FeatureSnapshot/Bundle | 修订传播/重建 | 已闭环 |
| 市场与板块 | FeatureSnapshot | 宽度、情绪、资金、异动 | ObservationSnapshot | 缺失显示/规则版本 | 已闭环 |
| 消息面 | 公告/新闻/政策Provider | 实体解析、许可和`available_at` | Evidence/Event Feature | 无源不补写/不完整降级 | 已闭环 |
| 复盘 | Observation/FactPack | AI Claim/Evidence | Review/Report/Validation | LLM降级/Correction/T+H校验 | 已闭环 |
| 个股研究 | StockResearchFactPack | L0/L1/L2、分歧和自查 | ResearchResult | Evidence Gate/人工Promotion | 已闭环 |
| 策略与权重 | StrategySpec/FeatureBundle | Resolver/Compiler/Policy | ResolvedSpec/WeightSnapshot | 新版本/人工批准 | 已闭环 |
| 回测验证 | RunBundle | Hikyuu Formal | Prediction/Execution/NAV/Validation | Attempt/Retry/归因/复现 | 已闭环 |
| 运维安全 | Task/Config | Auth/Lease/Artifact/Backup | Audit/Deployment/Restore Manifest | 告警/恢复/回滚 | 已闭环 |

结论：功能模块在文档层已形成“输入→处理→版本化产物→页面/API消费→验证/修订/回滚”闭环。跨模块Identity、时间、状态、Hash、ResourceRef、Task和Error契约也已统一。尚未闭环的是代码、真实Provider、性能和生产运行证据，而不是模块设计。

## 20. 尚需实施时确认的输入

当前没有阻断`WP-0001`启动的业务架构未决项。下列内容不能在文档中伪造，必须由真实探针、Benchmark或owner输入确认：

| 项 | 确认时点 | 是否阻断当前开发 |
| --- | --- | --- |
| a-stock-data/Financial-API真实字段、历史深度、频控、许可和冲突比例 | WP-0201/0202 Provider Probe | 不阻断M0/M1；阻断对应Dataset认证 |
| 目标服务器CPU、内存、磁盘、IOPS和Docker版本 | 二期Preflight | 不阻断本地开发；阻断生产限额和发布 |
| 域名、Cloudflare Zone/Token、Turnstile Key、owner密码 | WP-0803上线前 | 只阻断公网验收 |
| LLM Provider、模型、Token/费用/时间预算 | WP-0502/0702/0704 | 不阻断事实链；阻断对应AI质量验收 |
| 加密离机备份目标和恢复口令 | WP-0804 | 只阻断二期Release Gate |
| Visory Logo、色彩和视觉资产 | 前端视觉收口时 | 不阻断信息架构和功能开发 |
| 远程仓库Slug或Python历史包是否重命名 | MVP发布后单独决策 | 不阻断MVP，禁止顺手破坏性迁移 |

## 21. AI agent能否直接完结

结论是：**可以直接开始并按Work Package连续实现，但不能以一个超大Prompt或单次任务合规地“一键完结”整个平台。**

Claude Code或Codex可独立完成契约、Migration、后端、Worker、前端、测试、无Secret配置模板、本地Compose、文档和验收证据。但必须遵循以下边界：

1. 每次只接受一个WP或经明确拆分的小批量WP，达到`VERIFIED`后再继续；
2. 每个Milestone Exit Gate由新任务复核，不依赖长上下文中的自我声明；
3. Provider能力、付费或许可限制、Secret、域名、备份目标和生产发布由owner提供或批准；
4. 未通过Local Release Gate时，不允许连接服务器写入、更改Cloudflare或宣称`RELEASED`；
5. 不得自动`git commit/push`或做破坏性Migration，除非owner对该操作单独授权。

因此，将本文和`WP-0001`交给Claude Code或Codex已足以直接启动一期开发；整体完结需要以45个WP证据、两期Release Gate和owner的外部配置/上线验收为准。
