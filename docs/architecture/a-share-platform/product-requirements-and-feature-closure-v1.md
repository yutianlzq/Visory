# Visory 需求与功能闭环 v1

状态：MVP Product Baseline

最后更新：2026-08-28

## 1. 产品目标

建设一个名为 **Visory** 的单用户、可追溯、以A股为核心的个人研究平台，帮助owner在盘后完成“看懂市场—发现板块和个股—形成可验证假设—运行策略—复盘结果—修正方法”的闭环。平台提供研究和决策辅助，不承诺收益，不自动连接实盘券商下单。

核心成功标准：

1. owner在一个Web平台内查看统一口径的大盘、情绪、资金、板块、热点和个股事实；
2. 盘后16:00自动采集，明确展示数据是否达到正式策略所需质量；
3. DSA依据同一FactPack生成日报/复盘，所有关键结论可回到证据；
4. StrategySpec可由同一Compiler用于预览、Hikyuu回测和后续模拟组合；
5. T日预测、T+1执行和T+H验证分别保存并可追溯；
6. 任意正式结果能定位到策略、指标、快照、Provider Run和Raw Hash；
7. 当前服务器不升级也能用单重Worker和任务优先级稳定运行MVP。

## 2. 用户与权限

### 2.1 MVP角色

| 角色 | 能力 |
| --- | --- |
| `owner` | 唯一账户；查看全部页面，创建/取消任务，发布策略，管理配置和备份 |
| `viewer` | MVP不实现/不创建；仅作为MVP后的只读角色预留 |

MVP只存在一个`owner`账户。公网登录需要owner密码与Cloudflare Turnstile双重验证。平台不开放匿名页面，不允许通过Artifact URL绕过会话。

### 2.2 典型使用场景

- 盘后查看DataSnapshot和FeatureSnapshot是否认证；
- 查看市场情绪、大盘结构、宽度、资金证据和异常原因；
- 从板块异动/热门板块进入热点股，再进入个股事实卡；
- 对重点股运行L1快速研究，必要时人工触发L2研究；
- 阅读DSA收盘复盘，核对Claim与Evidence；
- 创建/版本化StrategySpec并预览候选和信号；
- 提交Hikyuu回测，查看成交、净值、回撤、预测验证和可复现清单；
- 在任务/数据质量页处理失败、重试、Correction和存储告警。

## 3. 范围边界

### 3.1 MVP包含

- 沪深主板、创业板、科创板日线现货多头；
- a-stock-data核心、Financial-API补充的数据平台；
- 市场/板块/个股客观观察，A股收盘复盘；
- L0个股事实卡、L1快速研究；MVP二期交付owner单只人工触发的L2深度研究；
- 最小StrategySpec、固定权重和Hikyuu正式回测；
- 单owner认证、持久任务、运维、备份恢复。

### 3.2 MVP明确不包含

- 自动实盘下单、券商账户、收益承诺；
- 全球数据参与A股策略、权重或回测；
- 北交所、分钟/Tick、ETF、可转债、期货、做空、融资融券和杠杆；
- Fleur运行时；
- AI直接修改正式策略、资金权重或事实；
- 多租户、团队审批、分布式Worker和微服务。

### 3.3 MVP两期交付边界

| 阶段 | 环境 | 功能范围 | Exit Gate |
| --- | --- | --- | --- |
| MVP一期 | 本机回环/CI/隔离开发环境 | M0—M6及L0/L1：数据、指标、市场/板块/消息、复盘、个股、策略与Hikyuu回测核心闭环 | 所有必需WP达到`VERIFIED`，不触及服务器正式根和Cloudflare |
| MVP二期 | 先本地生产等价预演，后服务器 | 单只人工L2、owner认证、Turnstile、Compose、备份恢复、Cloudflare/NPM和发布硬化 | Local Release Gate通过、owner批准部署和外部配置已就绪 |

MVP两期均不包含M9的自动权重生产化、复杂MVO、AI动态仓位、Paper Portfolio、L2批量自动运行和多Worker弹性。

## 4. 核心业务流程

### 4.1 盘后事实发布

```text
16:00核心采集
  → Raw/Canonical/Quality Gate
  → Provisional DataSnapshot
  → 必要时Financial-API补充
  → Certified DataSnapshot(backtest_core)
  → F1/F2 FeatureSnapshot
  → Market/Sector ObservationSnapshot
  → MarketCloseFactPack
  → DSA复盘/策略信号/个股研究
```

任一步失败必须在数据质量和任务中心可见；全球观察和非核心研究失败不阻断A股核心快照。

### 4.2 研究到验证

```text
客观观察/FactPack
  → 人工形成研究问题
  → L1/L2研究生成Claim与Evidence
  → 人工决定是否提出StrategySpec变更
  → Preview
  → Formal Hikyuu回测
  → T日Prediction
  → T+1 ExecutionResult
  → T+H ValidationResult
  → 复盘归因
```

研究观点不能自动Promotion为策略。策略修改需要新版本和重新回测。

## 5. 功能需求

### 5.1 身份、数据与质量

| ID | 需求 | MVP验收 |
| --- | --- | --- |
| FR-DATA-001 | 统一解析股票代码、名称和Provider Symbol | 歧义返回候选，不猜测；正式数据保存`entity_key` |
| FR-DATA-002 | 按数据集配置核心源、补充源和冲突规则 | 主备切换产生新Partition/Snapshot并保留血缘 |
| FR-DATA-003 | 保存Raw、Canonical Partition及Hash | 任意正式值可定位Raw Object |
| FR-DATA-004 | 16:00开始盘后采集并显示阶段 | 任务页可见采集、补充、认证和失败原因 |
| FR-DATA-005 | 发布Provisional/Certified/Correction快照 | Formal Backtest只接受`backtest_core=CERTIFIED` |
| FR-DATA-006 | 质量门禁覆盖身份、日历、OHLCV、状态和公司行动 | 关键冲突阻断，非关键缺失按Capability降级 |
| FR-DATA-007 | 数据质量页展示覆盖、新鲜度、冲突、缺口和修订 | 可从Capability下钻Dataset/Partition/ProviderRun |
| FR-DATA-008 | 修订不覆盖旧数据，允许对比影响 | 旧Run保持原结果，新Run显式绑定Correction |

### 5.2 大盘、情绪与资金

| ID | 需求 | MVP验收 |
| --- | --- | --- |
| FR-MKT-001 | 展示指数走势、成交、量价结构和关键位置 | 每个指标带日期、定义版本和数据状态 |
| FR-MKT-002 | 展示上涨/下跌、涨停/跌停、创新高/新低等市场宽度 | 可查看全市场及板块切片，缺失不显示为0 |
| FR-MKT-003 | 展示五维市场情绪、解释项和市场状态 | 分数公式固定版本，可展开原始分量 |
| FR-MKT-004 | 展示订单规模、杠杆、公开席位、大宗、板块及互联互通资金证据 | 每项有Evidence Grade、口径、覆盖和来源 |
| FR-MKT-005 | 展示规则化市场异动和风险提醒 | 事件包含触发阈值、证据和失效时间 |
| FR-MKT-006 | 全球市场只作观察背景 | 全球数据缺失不阻断A股页面/策略；RunBundle中不存在全球输入 |

### 5.3 板块、热点与个股发现

| ID | 需求 | MVP验收 |
| --- | --- | --- |
| FR-SECTOR-001 | 展示行业/概念分类及历史成员 | 同名板块按Taxonomy隔离，历史成员PIT正确 |
| FR-SECTOR-002 | 展示板块涨幅、相对强度、宽度、流动性和资金 | 指标为独立客观列，不输出平台统一热度分 |
| FR-SECTOR-003 | 展示板块异动事件 | 规则、阈值、Definition版本和Evidence可见 |
| FR-SECTOR-004 | 展示热门板块和热点股客观榜单 | 排名口径独立，保留入榜原因和风险标签 |
| FR-SECTOR-005 | 支持板块→热点股→个股详情下钻 | 上下文保留trade_date和Snapshot ID |
| FR-SECTOR-006 | 策略引用板块因素时生成策略专属分数 | 分数属于Strategy版本并由Hikyuu回测验证 |

### 5.4 个股事实与研究

| ID | 需求 | MVP验收 |
| --- | --- | --- |
| FR-STOCK-001 | 个股页展示身份、行情、技术、流动性、板块/题材、资金、财务、估值、事件和风险 | 每个Block有状态、截止时间和来源 |
| FR-STOCK-002 | 展示题材归因和历史板块成员 | AI候选与正式注册关系明确区分 |
| FR-STOCK-003 | 展示个股资金证据而非虚构单一“主力”真值 | 指标按来源口径分列并显示可信度 |
| FR-STOCK-004 | 人工触发L1快速研究 | 生成结构化结果、Claim/Evidence和自查状态 |
| FR-STOCK-005 | 重点标的人工触发L2深度研究 | MVP二期交付七角色输出、分歧、风险审查、取消/恢复和资源上限；自动候选与批量执行延后 |
| FR-STOCK-006 | 研究观点与策略硬隔离 | Promotion只生成待审Strategy提案，不自动发布 |

### 5.5 收盘复盘

| ID | 需求 | MVP验收 |
| --- | --- | --- |
| FR-REVIEW-001 | 按交易日生成MarketCloseFactPack | 八类事实块有独立质量状态和Hash |
| FR-REVIEW-002 | DSA基于固定FactPack生成AI收盘复盘 | AI不重新抓取权威行情，结果固定Prompt和输入Hash |
| FR-REVIEW-003 | 关键结论可展开Claim与Evidence | 不支持/矛盾结论被标记，不伪装确定事实 |
| FR-REVIEW-004 | 生成Web、Markdown、通知和历史投影 | 多投影引用同一Review Result，不各算一遍 |
| FR-REVIEW-005 | 复盘观察条件在T+1/T+H验证 | 验证用于评估复盘，不自动成为策略业绩 |
| FR-REVIEW-006 | 晚到数据可生成Correction复盘 | 旧报告保留，新报告显式标注替代关系 |

### 5.6 策略、评分和权重

| ID | 需求 | MVP验收 |
| --- | --- | --- |
| FR-STRAT-001 | 可创建、校验、版本化和归档StrategySpec | YAML/JSON使用安全DSL，不执行任意代码 |
| FR-STRAT-002 | 股票池、特征、筛选、评分、入场、退出分层 | Resolver输出可解释的候选、分数和排除原因 |
| FR-STRAT-003 | Preview、Formal和未来Paper共用Resolver/Compiler | 相同ResolvedSpec产生相同信号Hash |
| FR-STRAT-004 | 策略状态变更需owner确认 | 草稿、验证、发布、归档有审计记录 |
| FR-WEIGHT-001 | MVP支持固定权重、等权和约束投影 | 权重前后、约束命中和现金余量可解释 |
| FR-WEIGHT-002 | 全区间最优只作研究上界 | 页面显式标记In-sample，不可发布为Formal策略结论 |
| FR-WEIGHT-003 | 后续支持滚动寻优、AI Overlay、MVO和叠加 | 接口/Schema预留但MVP不要求生产启用 |

### 5.7 Hikyuu回测与验证

| ID | 需求 | MVP验收 |
| --- | --- | --- |
| FR-BT-001 | Hikyuu是唯一正式回测内核 | Formal结果包含Hikyuu/Adapter/镜像版本 |
| FR-BT-002 | 支持Preview/Research/Formal运行级别 | 三者资源、门禁和结果标识不可混淆 |
| FR-BT-003 | 固化A股历史股票池、复权、T+1、涨跌停、整手、费用、容量和基准 | Golden Dataset覆盖所有市场规则反例 |
| FR-BT-004 | 保存RunBundle和全部输入Hash | 任意Run可离线重建或解释无法重建原因 |
| FR-BT-005 | 分别保存Prediction、Order、Execution、Position、Trade、NAV和Validation | 未成交与预测错误可区分 |
| FR-BT-006 | 展示收益、回撤、风险、换手、容量、基准、因子与权重归因 | 指标口径和样本区间明确 |
| FR-BT-007 | 支持取消、重试、失败诊断和结果原子发布 | 失败Attempt不可被API当作成功结果 |
| FR-BT-008 | 支持T/T+1/T+H追溯 | Validation可反查Prediction→Strategy→Feature→Data→Raw |

### 5.8 平台、任务、安全与运维

| ID | 需求 | MVP验收 |
| --- | --- | --- |
| FR-PLAT-001 | 提供统一React/FastAPI平台壳 | 一级导航和路由遵循页面原型文档 |
| FR-PLAT-002 | PostgreSQL持久化Task/Attempt/Lease/Artifact | 服务重启后任务状态不丢失 |
| FR-PLAT-003 | 单重Worker按优先级和资源预算执行 | 16:00核心链不会被L2研究/大回测抢占 |
| FR-PLAT-004 | Operations页展示任务、阶段、资源、告警和重试 | 可按Task ID关联日志与Artifact |
| FR-SEC-001 | Cloudflare+NPM+owner密码+Turnstile保护全部页面 | 源站直连、无会话、Turnstile失败均被拒绝 |
| FR-SEC-002 | 配置与Secret分离 | Secret不进入Git、日志、Manifest、Artifact和前端 |
| FR-OPS-001 | 服务器全部持久数据和配置位于`/data/daily_stock_analysis`；本地通过`VISORY_RUNTIME_ROOT`绑定 | 各环境新写入遵循C-003逻辑目录，单一运行环境内无第二数据根 |
| FR-OPS-002 | 执行备份、Hash校验和恢复演练 | Restore Manifest证明数据库/Parquet/登录/回测缓存可用 |

## 6. 非功能需求

| ID | 要求 | MVP目标 |
| --- | --- | --- |
| NFR-001 | 可追溯性 | 100%正式结果具备完整Resource Reference与Hash链 |
| NFR-002 | PIT正确性 | Formal策略读取100%满足`available_at <= cutoff_at` |
| NFR-003 | 确定性 | 同RunBundle重复运行核心结果Hash一致；允许差异须列入Manifest |
| NFR-004 | 可用性 | 单Provider/全球/LLM失败按契约降级，不拖垮核心数据链 |
| NFR-005 | 性能 | 常用页面首屏API P95≤2秒；大榜单分页；不在请求内全市场重算 |
| NFR-006 | 资源 | 默认4核/有限内存单机；重任务串行，内存/临时盘有硬预算 |
| NFR-007 | 安全 | 全站认证、最小挂载、非root容器、CSRF/限流/审计/Secret脱敏 |
| NFR-008 | 恢复 | RPO≤24小时，目标RTO≤4小时，至少季度恢复演练 |
| NFR-009 | 可测试性 | 每个契约有Golden成功/降级/失败/Correction Payload |
| NFR-010 | 可维护性 | 模块化单体、单向依赖、Router无业务写入、无平行事实实现 |
| NFR-011 | 可观察性 | 请求/任务/Attempt/资源ID贯通日志、指标和事件 |
| NFR-012 | 兼容性 | API破坏性变化提升主版本并经过弃用周期 |

性能目标是当前服务器的设计预算，实施阶段必须用真实数据Benchmark确认；未达标时优先使用分区、增量、预聚合和任务限流，而不是静默缩短正式回测区间。

## 7. 页面与路由清单

| 页面ID | 路由 | 主要职责 |
| --- | --- | --- |
| P-LOGIN | `/login` | 密码+Turnstile登录 |
| P-DASH | `/` | 今日状态、核心卡片、异常和快捷入口 |
| P-MARKET | `/market` | 大盘、宽度、情绪、资金和全球观察 |
| P-SECTOR | `/sectors` | 板块客观指标、异动、热门和热点股 |
| P-STOCK | `/stocks/:canonicalId` | 个股事实、题材、资金、财务、事件和研究入口 |
| P-REVIEW | `/reviews/:tradeDate?` | 收盘FactPack、AI复盘、Claim和验证 |
| P-RESEARCH | `/research/:researchId?` | L1/L2队列、角色输出、分歧、自查和报告 |
| P-STRATEGY | `/strategies/:strategyId?` | StrategySpec编辑、验证、版本和Preview |
| P-BACKTEST | `/backtests/:runId?` | 回测创建、进度、结果、交易和追溯 |
| P-DATA | `/data-quality` | Snapshot、Capability、数据集、冲突和Correction |
| P-TASKS | `/operations/tasks/:taskId?` | Task/Attempt/资源、日志、告警和重试 |
| P-SETTINGS | `/settings` | Provider、模型、调度、安全、存储和备份设置 |

页面布局和状态见[页面信息架构与低保真原型 v1](page-prototypes-and-information-architecture-v1.md)。

## 8. 功能闭环追踪矩阵

| 闭环 | 需求 | 页面 | API/命令 | 后台任务 | 关键输入 | 正式输出 | 验收证据 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 数据发布 | FR-DATA-001~008 | P-DATA/P-TASKS | `/api/v1/data-snapshots` | INGEST/NORMALIZE/CERTIFY | ProviderPolicy/Raw | Certified DataSnapshot | Golden Provider冲突与Correction测试 |
| 市场判断 | FR-MKT-001~006 | P-DASH/P-MARKET | `/api/v1/market/*` | FEATURE/OBSERVATION | Data/FeatureSnapshot | Market Observation | 指标定义、缺失和全球隔离测试 |
| 板块发现 | FR-SECTOR-001~006 | P-SECTOR/P-STOCK | `/api/v1/sectors/*` | SECTOR_OBSERVATION | Historical Membership/Feature | Sector/Hotspot Snapshot | PIT成员、榜单与事件规则测试 |
| 个股研究 | FR-STOCK-001~006 | P-STOCK/P-RESEARCH | `/api/v1/stock-research/*` | FACTPACK/RESEARCH | Stock FactPack/Evidence | Research Result | Claim Gate、取消、证据不足测试 |
| 收盘复盘 | FR-REVIEW-001~006 | P-REVIEW | `/api/v1/market-reviews/*` | REVIEW_FACTPACK/AI/VALIDATE | MarketCloseFactPack | Review/Report/Validation | 同源投影、Correction与T+1测试 |
| 策略定义 | FR-STRAT-001~004 | P-STRATEGY | `/api/v1/strategies/*` | COMPILE/PREVIEW | StrategySpec/FeatureBundle | ResolvedSpec/Preview | DSL拒绝、确定性和版本测试 |
| 权重决策 | FR-WEIGHT-001~003 | P-STRATEGY/P-BACKTEST | `/api/v1/weight-policies/*` | WEIGHT_RESOLVE | Score/Constraints | WeightSnapshot | 约束投影和研究/Formal隔离测试 |
| 正式回测 | FR-BT-001~008 | P-BACKTEST/P-TASKS | `/api/v1/backtests/*` | BACKTEST_FORMAL | RunBundle/Hikyuu Cache | Result/Prediction/Validation | 市场规则、账本、Hash和追溯测试 |
| 安全运维 | FR-PLAT/SEC/OPS | P-LOGIN/P-TASKS/P-SETTINGS | `/api/v1/auth/*`, `/operations/*` | BACKUP/SWEEPER | Config/Secret/Manifest | Audit/Backup/Restore | 登录、路径、恢复和源站隔离测试 |

矩阵中的任何一行只有“页面完成”或“API返回成功”都不算闭环；必须同时存在输入契约、后台状态、正式输出、失败/降级路径和验收证据。

## 9. 通用页面状态

所有数据型页面必须实现：

```text
LOADING
EMPTY
PROVISIONAL
PARTIAL
STALE
ERROR
SUCCESS
CORRECTION
```

- `EMPTY`说明暂无业务数据；
- `PARTIAL`列出缺失Capability/Block；
- `STALE`显示最后可用时间和刷新入口；
- `ERROR`提供稳定错误码和Task链接；
- `CORRECTION`显示当前修订版本、`revision_kind`及被替代版本；
- 页面不得用旧缓存伪装`SUCCESS`，如使用缓存必须显示Snapshot ID和新鲜度。

## 10. 关键验收场景

1. 输入`600519`在股票上下文解析为`stock:sh600519`，通用歧义输入不猜测；
2. a-stock-data核心行情失败，Financial-API按Policy生成独立替代分区和新Snapshot；
3. 公司行动冲突阻断`backtest_core`，市场页面仍可显示允许的Provisional数据；
4. 16:00链路可在Operations页完整观察，重启API不丢Task；
5. 全球观察失败时A股策略RunBundle和DSA核心复盘仍正常；
6. 板块页面不显示统一热度分，策略内的板块评分明确属于该Strategy版本；
7. 个股研究证据不足时Task可成功但Research Gate为`INSUFFICIENT_EVIDENCE`；
8. Formal Hikyuu回测遇到T+1不可卖、开盘涨跌停和最低佣金均按规则记账；
9. Prediction正确但订单未成交时，方向验证和可交易收益分别呈现；
10. Correction后旧Run和旧报告保持不变，新版本可比较差异；
11. 未登录、Turnstile失败、CSRF、Artifact路径穿越和源站直连均被拒绝；
12. 从备份恢复后可登录、读取一个快照、打开一份报告并重建一个Hikyuu缓存。

## 11. 需求变更规则

- 新功能先获得FR/NFR ID，再设计契约、页面、API和任务；
- 影响回测口径、Provider主备、指标公式、Prompt或认证的变更必须提升对应Definition/Policy/Schema版本；
- 延后项要进入明确Milestone，不能在MVP代码中以半成品开关存在；
- 删除或替代需求保留ID和决策历史，不复用编号；
- 每个实现PR更新本文件追踪矩阵或说明为什么不受影响。

## 12. 参考文档

- [Claude Code开发总指引](CLAUDE-CODE-GUIDE.md)
- [Visory架构索引](README.md)
- [Visory实现契约目录 v1](platform-implementation-contract-catalog-v1.md)
- [页面信息架构与低保真原型 v1](page-prototypes-and-information-architecture-v1.md)
- [实施路线与验收方案 v1](implementation-roadmap-and-acceptance-v1.md)
