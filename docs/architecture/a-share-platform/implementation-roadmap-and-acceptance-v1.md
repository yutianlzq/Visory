# Visory 实施路线与验收方案 v1

状态：Execution Baseline

最后更新：2026-08-28

## 1. 目标

本文把Visory的产品、架构和契约拆成Claude Code或Codex可以逐个实现、验证和回滚的Work Package。每个Package必须形成可运行的纵向切片，不能只创建大量空目录、占位接口或无法消费的数据表。

实施原则：契约先行、身份/时间先行、数据先于AI、Hikyuu先固定规则后做优化、纵向闭环优先、Legacy渐进迁移、每阶段都可独立验收。所有开发、Migration、Compose、备份和恢复先在本地或隔离环境验证，未过Local Release Gate不得部署服务器。

### 1.1 项目与环境基线

- 产品名为`Visory`，新Compose Project、Docker网络和新资源前缀为`visory`；
- 本地运行根使用`VISORY_RUNTIME_ROOT`，测试使用临时目录；
- 服务器物理根保留`/data/daily_stock_analysis`，不因品牌更名做数据迁移；
- 目标服务器、Cloudflare、NPM和真实Secret只在MVP二期Local Release Gate通过后进入操作范围。

## 2. 当前基线与目标差距

当前仓库已有React/Vite、FastAPI、数据源Fetcher、股票分析、市场复盘、LLM、报告、通知、SQLite Repository、内存Task Queue和简单Backtest Service，可复用界面壳、分析流程和兼容入口。

目标平台尚需实现：

| 能力 | 当前基线 | 目标 |
| --- | --- | --- |
| 资产身份 | 多种code规范并存，canonical迁移中 | `entity_key`+Alias有效期+Resolver |
| 数据库 | SQLite与UTC-naive时间 | PostgreSQL控制面+timestamptz+Migration |
| 文件数据 | 应用缓存/文件分散 | Parquet/DuckDB+Manifest+`storage/app` |
| 数据任务 | Fetcher直接服务分析 | ProviderRun→Raw→Canonical→Snapshot |
| 任务 | 进程内Queue/ThreadPool | Task/Attempt/Lease/Checkpoint持久控制面 |
| 指标 | 多处计算/有限持久化 | Indicator Registry+FeatureSnapshot |
| 市场页面 | 现有大盘/复盘局部能力 | 统一Market/Sector Observation |
| 复盘 | 可生成分析与报告 | FactPack→AI→Claim/Evidence→Validation |
| 回测 | 简单后验评估 | Hikyuu唯一Formal内核+完整账本/追溯 |
| 研究 | DSA/Agent能力 | L0/L1/L2分层+Evidence Gate |
| 安全 | 现有管理认证 | owner密码+Turnstile+Cloudflare/NPM |
| 部署 | 当前Docker能力 | 双Compose/最小挂载/备份恢复Manifest |

因此不得直接在现有`src/storage.py`继续添加目标平台全部表，也不得扩展内存Task Queue为正式回测任务中心。

## 3. 里程碑总览

```text
M0 契约与工程底座
  → M1 身份、存储与持久任务
    → M2 数据采集、Canonical与Snapshot
      → M3 Feature Store
        ├→ M4 市场/板块/数据质量页面
        ├→ M5 DSA收盘复盘
        └→ M6 StrategySpec + Hikyuu正式回测
              → M7 个股研究
                → M8 安全、部署、备份与MVP发布
                  → M9 自动权重/L2批量自动化/高级能力（MVP后）
```

M4、M5、M6在M3完成后可以按资源并行开发，但单个PR仍只实现一个Work Package。

### 3.1 MVP一期：本地核心功能版

范围：`M0—M6 + WP-0701—WP-0703`，共39个WP。

一期必须交付统一契约和任务底座、数据/Snapshot/Feature、大盘与板块、消息证据、复盘、L0/L1个股研究、StrategySpec、固定/等权和Hikyuu Formal回测。验收环境仅为本机回环、CI或隔离开发网络；不写服务器正式数据根，不改Cloudflare。

### 3.2 MVP二期：生产化与服务器版

范围：`WP-0704 + M8`，共6个WP。

二期完成单只人工L2深度研究、owner认证与Turnstile、Visory双Compose、备份/恢复、安全反例和Release Candidate。代码与部署产物仍先在本地完成生产等价预演，通过本文的Local Release Gate后，才由owner提供Secret/域名并授权服务器发布。

### 3.3 Local Release Gate

- 一期必需WP全部`VERIFIED`，二期待部署代码/模板本地验证通过；
- 生产等价Compose可Build/Up/Healthcheck/Down，不依赖生产Secret；
- 空库Migration、兼容回滚、备份恢复和Hikyuu缓存重建通过；
- 契约、PIT、确定性、市场规则、安全和E2E证据完整；
- 无高危未解决问题，服务器Preflight和回滚/备份点已确认；
- owner显式批准部署窗口与服务器写操作。

## 4. M0 契约与工程底座

### WP-0001 Contract Registry与公共Schema

范围：

- 建`src/schemas/platform`；
- 实现C-001枚举、ID/ResourceRef、时间、版本、Hash和StorageRef；
- 导出JSON Schema；
- 建`tests/golden/platform/contracts`成功/失败Payload；
- CI校验确定性Hash和Schema兼容。

验收：C-001至C-003的拒绝清单全部有测试；现有API不受影响。

### WP-0002 PostgreSQL与Alembic基础

范围：

- 引入PostgreSQL连接配置、连接池、健康检查和Alembic；
- 建Migration基线、事务工具和测试数据库Fixture；
- 配置只保存Secret文件引用；
- 不迁移Legacy业务表。

验收：空库升级、重复升级、回滚测试、时区往返、连接失败错误码通过。

### WP-0003 API Envelope、Error与生成类型

范围：统一成功/错误Envelope、Request ID、中间件、OpenAPI示例和前端生成类型；为Legacy响应保留Adapter。

验收：401/403/404/409/422/429/503和未知异常均符合C-010，不泄露堆栈。

### M0 Exit Gate

- Contract Registry、JSON Schema、OpenAPI和前端类型有单一生成链；
- PostgreSQL Migration可复现；
- Legacy Smoke通过；
- 尚未改写现有生产数据。

## 5. M1 身份、存储与持久任务

### WP-0101 Asset Identity与Alias Resolver

实现`asset_identity`、`asset_alias`、Identity Quarantine、Resolver Service/API和Legacy code Adapter。首批覆盖沪深主板、创业板、科创板及历史退市标的。

验收：名称变更、ST、退市、Provider Symbol、六码输入、歧义和冲突Golden测试；正式输出都有`entity_key`。

### WP-0102 Storage Namespace与Artifact Publisher

实现StorageRef、Namespace Resolver、路径安全、Staging/Hash/Atomic Rename、Artifact Registry、Orphan Sweeper Dry-run。测试使用临时根，不创建真实`/data`目录。

验收：路径穿越/Symlink逃逸、校验失败、Rename失败、数据库失败和恢复注册测试通过。

### WP-0103 Durable Task Control Plane

实现Task、Attempt、Lease、State Event、Artifact、Idempotency、Scheduler入队和Worker领取。先迁移一个低风险维护任务验证框架，不立即替换全部分析队列。

验收：服务重启、重复Command、Lease Lost、Worker崩溃、Retry、Cancel和Blocked恢复测试。

### WP-0104 Operations最小页面

实现P-TASKS的任务表、Attempt时间线、错误码、Artifact和取消/重试；SSE断线可恢复，最终状态以查询API为准。

### M1 Exit Gate

- Identity、Artifact和Task成为新平台对象的唯一目标实现；
- Storage/API安全反例通过；
- 单个持久任务可跨进程完成并原子发布Artifact；
- Legacy Task Queue仍可运行但标记为迁移路径。

## 6. M2 数据采集、Canonical与Snapshot

### 6.1 历史回填范围

MVP固定：

| 数据集 | 回填范围 |
| --- | --- |
| Security Master/上市退市/历史名称 | 来源可证明的完整历史，至少覆盖2018-01-01至今 |
| 交易日历 | 2017-01-01至当前年份后一个自然年 |
| 日K/状态/公司行动/复权依据 | 2018-01-01至今，包含退市证券 |
| 财务报表/披露时间 | 2017年度报告期至今，用于2018年后PIT消费 |
| 行业成员 | 2018-01-01至今；无法证明的历史区间标记Unavailable |
| 估值 | 2018-01-01至今或Provider可证明的有效起点 |
| 资金/涨跌停/题材/榜单 | Provider有可靠历史则回填；否则从平台上线日开始，不伪造 |
| 新闻/外部证据 | 不做全量历史回填，从上线日增量采集 |

正式策略可用回测起点由最长指标Warmup、股票池和Capability共同确定，不能简单等于数据起点。2018年前研究若后续需要，以新Backfill Policy版本单独执行。

### WP-0201 Dataset/Provider Registry

实现ProviderDefinition、Capability、数据集级ProviderPolicy、DatasetDefinition和设置页只读投影。首批核心源a-stock-data，补充源Financial-API。

### WP-0202 Raw Ingestion

选择`security_master`、`trading_calendar`、`bar_1d_raw`三类纵向切片，实现ProviderRun、RawObject、速率/超时/Schema Drift/脱敏和Quarantine。

### WP-0203 Canonical Normalization

实现身份映射、单位/时间/Null转换、Canonical Partition和质量报告；扩展到状态、上市退市、公司行动和财务。

### WP-0204 DataSnapshot与Capability Gate

实现Provisional/Certified/Correction、Partition Manifest、ConsumerRequirement和Current Pointer。Formal Consumer只接受`backtest_core`。

### WP-0205 16:00 Scheduler与补充源

按SLA建立幂等Schedule：Preflight→Core→Provisional→Supplement Decision→Certified→Correction Audit。失败/降级可在Task页面观察。

### WP-0206 P-DATA数据质量页面

实现Capability、Dataset、ProviderRun、Partition、冲突、Quarantine和Correction下钻，不提供直接编辑Canonical值。

### WP-0207 分批Backfill

顺序：Identity/Calendar → 行情月分区 → 状态/上市退市 → 公司行动 → 财务/估值 → 行业 → 非核心观察。每批保存Task、检查点、差异和资源使用；先1个月、1年试跑再全区间。

### M2 Exit Gate

- 最近一个交易日可自动发布`backtest_core=CERTIFIED`；
- 主源失败可受控补充且血缘完整；
- Correction不改变旧Snapshot；
- 2018至今核心回填完成或所有缺口机器可见；
- 双源关键字段抽样和全量质量规则通过。

## 7. M3 Feature Store

### WP-0301 Indicator Registry与DAG

实现IndicatorDefinition、受控Builtin Registry、依赖DAG、Hash和版本生命周期。迁移首批公式，不复制现有同名指标。

首批F1：未复权/时点复权收益、MA、波动、ATR、成交/换手、ADV20、涨跌停/停牌/上市天数、基础估值和财务可用标志。

### WP-0302 Feature Partition/Snapshot/Bundle

实现增量分区、Warmup、质量、Manifest、修订传播、F1/F2/F3保留和消费者Bundle。

### WP-0303 市场宽度与情绪F2

实现上涨/下跌、新高/新低、涨跌停生态、量价/风险偏好、五维情绪和市场状态；固定Definition版本和解释分量。

### WP-0304 板块与资金F2

实现历史成员PIT聚合、相对强度、宽度、流动性、资金证据和异常规则输入。

### WP-0305 Hikyuu Cache Builder

从Certified Snapshot构建缓存、Hash校验、样本对比和原子发布；缓存损坏可重建。

### M3 Exit Gate

- 2018至今首批F1/F2增量物化；
- 当前服务器Benchmark记录耗时、峰值内存、临时盘和产物大小；
- 相同输入重复计算Hash一致；
- Data Correction能正确计算受影响分区；
- Hikyuu Worker无需联网即可加载固定缓存。

## 8. M4 市场、板块与总览

### WP-0401 Market Observation

发布大盘结构、宽度、情绪、资金和规则事件ObservationSnapshot，构建查询Projection。

### WP-0402 Sector Registry与Observation

实现Taxonomy、历史成员、独立指标榜单、板块异动和热点股客观列表；不实现平台统一热度分。

### WP-0403 P-MARKET/P-SECTOR

按原型实现Tab、指标表、图表、EvidenceDrawer、Snapshot状态、版本对比和移动端。

### WP-0404 P-DASH

总览只组合已发布Projection；任何卡片失败独立降级，显示上个交易日时必须显式标注。

### WP-0405 全球观察隔离

实现低优先级GlobalObservation和页面Tab；增加结构/测试保证其类型不能进入Strategy/RunBundle。

### M4 Exit Gate

- 页面所有指标来自同一Snapshot链；
- 客观榜单无隐藏综合分；
- Global失败不影响A股核心；
- 常用API P95达到预算；
- 页面通用九类状态和关键E2E通过。

## 9. M5 DSA收盘复盘

### WP-0501 MarketCloseFactPack

实现八类FactBlock、缺口、Manifest、Correction和Artifact；只消费发布Snapshot/Observation。

### WP-0502 Review AI与Claim/Evidence

迁移DSA现有LLM、Prompt、报告能力到固定FactPack输入，结构化输出Claim、Evidence、观察条件和质量门禁。

### WP-0503 Review Projection与通知

Web/Markdown/通知/分享图共享同一ReviewResult，通知失败不拖垮Result。

### WP-0504 T+1/T+H Review Validation

观察条件使用后续FeatureSnapshot验证，结果与Strategy Prediction隔离。

### WP-0505 P-REVIEW

实现FactBlock、AI观点、Claim/Evidence、Correction、Validation和投影历史。

### M5 Exit Gate

- 一个交易日从FactPack自动生成复盘和至少一个投影；
- 核心Claim 100%有Evidence或明确Unsupported；
- LLM不可用时事实页面和删减模板仍可用；
- Correction不覆盖旧报告；
- T+1验证可追溯到原Review。

## 10. M6 StrategySpec与Hikyuu正式回测

### WP-0601 StrategySpec Schema与安全DSL

实现Registry、AST、Validator、版本、审计和最小均线/放量策略Fixture。禁止`eval/exec`。

### WP-0602 Resolver/Compiler/Preview

固定Universe、FeatureBundle、市场规则、权重和插件Hash；输出候选、分数、排除原因和信号Hash。

### WP-0603 A股市场规则与Hikyuu Adapter

实现历史股票池、双轨价格、T+1、涨跌停、整手、费用、容量、公司行动和基准。先用Golden Dataset逐条对照，再运行长区间。

### WP-0604 Backtest Task与原子结果

实现RunBundle、Preview/Research/Formal门禁、Hikyuu子进程、资源限制、Attempt、完整结果文件、账本验证和原子发布。

### WP-0605 Prediction/Execution/Validation

分别保存T日Prediction、T+1Order/Execution和T+HValidation，未成交/不可交易和方向错误分离。

### WP-0606 P-STRATEGY/P-BACKTEST

实现策略版本、编辑/验证、Preview、回测提交、进度、净值/回撤/交易/持仓/验证/Manifest和版本对比。

### WP-0607 固定权重MVP

实现等权、固定因子权重、个股上限、板块/总仓约束和投影归因。高级自动权重只保留契约，不进入MVP发布路径。

### M6 Exit Gate

- Hikyuu是唯一Formal结果生成器；
- 两个代表性策略在2018至今区间完成Formal回测；
- 同RunBundle重复运行核心Hash一致；
- Golden市场规则、账本和PIT反例全通过；
- Run可追溯到Raw；
- 当前服务器完成Benchmark且不静默缩短区间。

## 11. M7 个股研究

### WP-0701 StockResearchFactPack/L0

统一身份、行情技术、板块题材、资金、财务、估值、事件、股本风险、同行和缺口。

### WP-0702 L1 Quick Research

迁移UZI覆盖矩阵、自查和DSA运行能力；限定调用/Token/时间预算，输出Claim/Evidence。

### WP-0703 P-STOCK/P-RESEARCH

实现L0事实卡、L1任务、研究历史、Evidence、自查和Promotion Proposal。

### WP-0704 L2 Deep Research

作为MVP二期交付，只允许owner对单只标的人工触发，迁移TradingAgents七角色、多空辩论和风险三视角；不自动全市场运行。

### M7 Exit Gate

- L0/L1使用固定FactPack；
- 证据不足有正确质量状态；
- 研究不能自动发布Strategy；
- L2取消、Checkpoint和资源上限通过。

## 12. M8 安全、部署与MVP发布

### WP-0801 Owner Auth与Turnstile

实现Argon2id密码、服务端Siteverify、Session、CSRF、限流、安全审计和全路由默认保护。

### WP-0802 目标Compose与目录

生成Edge/Platform Compose模板、非root UID/GID、最小挂载、健康检查、资源限制和配置/Secret模板；不把Secret写入仓库。

### WP-0803 Cloudflare与NPM上线

按部署文档配置橙云、Full Strict、DNS-01、源站限制、真实IP、WebSocket/SSE和安全Header。由owner填写域名、Token和密码。

### WP-0804 Backup/Restore

实现加密备份、Manifest、保留、定时任务和隔离恢复演练。证明PostgreSQL、Storage Namespace、报告、登录和Hikyuu缓存重建。

### WP-0805 Release Candidate验收

执行本文件第15节全链路验收，修复阻断问题，冻结Schema/Policy/镜像和部署Manifest。

### M8 Exit Gate

- 公网唯一入口通过Cloudflare/NPM；源站直连被拒绝；
- 未登录不能访问页面/API/Artifact/SSE；
- 16:00链路和一个Formal回测连续多个交易日稳定；
- 恢复演练满足RPO/RTO；
- 所有MVP FR/NFR有测试或运行证据。

## 13. M9 MVP后能力

按顺序：

1. Walk-Forward自动权重和嵌套验证；
2. 复杂均值方差与约束求解；
3. AI有界仓位Overlay与多机制叠加归因；
4. L2深度研究批量化、自动候选与资源弹性；
5. Paper Portfolio；
6. 更多资产/频率；
7. 明确性能需求后再评估多Worker或拆服务。

全区间最优、同区间结果反推和AI动态仓位首先只能作为Research，必须通过样本外门禁才能成为可发布Policy。

## 14. Claude Code Work Package模板

每次任务使用以下模板：

```markdown
# WP-xxxx 标题

## 目标
- 对应FR：
- 对应Contract：
- 对应Milestone：

## 当前证据
- 现有实现：
- 现有测试：
- 已知Legacy兼容：

## 范围
- 允许修改：
- 明确不修改：

## 输入/输出
- 输入Schema/版本：
- 输出Schema/版本：
- 数据库/Artifact：

## 行为
- 成功：
- Partial/Degraded：
- Retry/Cancel：
- Correction/兼容：
- 安全/PIT/幂等：

## 验收
- Golden/反例：
- 测试命令：
- 性能预算：
- 页面/可视证据：

## 迁移与回滚
- Migration：
- 回填：
- 回滚：
- 监控：

## 文档同步
- Contract Registry：
- OpenAPI/.env.example：
- 追踪矩阵/Changelog：
```

若一个任务无法在此模板中清晰描述，说明Package过大或契约未收敛，应先拆分/补文档。

## 15. MVP全链路验收

### 15.1 确定性验收

固定Golden Snapshot和RunBundle，重复运行两次：候选、信号、交易、NAV关键值、Prediction和Result Hash一致。允许的环境元数据差异不进入业务Hash。

### 15.2 PIT验收

注入T日收盘后才披露的财务/Correction，确认T日Prediction不可见；在正确`available_at`后才可被新Run消费。

### 15.3 数据降级验收

模拟a-stock-data超时、Financial-API成功；验证新分区、新Snapshot、Provider血缘、Capability和页面状态。模拟双源公司行动冲突，Formal被阻断。

### 15.4 市场规则验收

覆盖停牌、新股、ST、退市、开盘涨跌停、T+1不可卖、整手、最低佣金、印花税版本、容量和公司行动。

### 15.5 研究复盘验收

同一FactPack生成Review和L1 Research；Claim有Evidence，证据不足不生成虚假结论；Correction生成新版本。

### 15.6 故障恢复验收

在Provider、Feature、Hikyuu、LLM和Artifact发布阶段分别终止Worker；验证Lease、Retry/Checkpoint、无半成品和可诊断。

### 15.7 安全验收

未登录、错误密码、Turnstile伪造/重放、CSRF、路径穿越、恶意Markdown、源站直连、伪造Proxy Header和Artifact越权全部拒绝。

### 15.8 备份恢复验收

从独立备份恢复到空目录：登录→查看DataSnapshot→打开复盘→查询一个个股→读取Formal回测→重建Hikyuu缓存，生成Restore Manifest。

### 15.9 资源验收

记录一个交易日全链路和2018至今代表性回测的Wall Time、峰值内存、CPU、读写和磁盘。若超预算：先优化分区/增量/预聚合，或排队非核心任务；不得减少正式区间却保留同一Result标签。

## 16. 发布与回滚

### 16.1 发布

1. 冻结Contract/Schema/Policy版本；
2. 备份并验证Manifest；
3. 构建固定Digest镜像；
4. 运行Migration Preflight；
5. 部署PostgreSQL/Worker/API；
6. 健康、登录、Snapshot、Task、Artifact Smoke；
7. Cloudflare/NPM外网与源站隔离测试；
8. 运行一个只读查询和小型Preview；
9. 观察错误率/资源/任务积压；
10. 保存Deployment Manifest。

### 16.2 回滚

- 应用回滚到上一镜像Digest；
- 数据库只在明确支持降级时执行Down Migration，否则保持Expand兼容并切旧应用；
- Current Pointer可回指上一Certified Snapshot，但不删除Correction；
- Artifact和Run不可覆盖；
- 配置恢复使用版本化归档；
- 回滚原因、范围和后续数据处理写Audit。

## 17. 进度治理

维护一个实现状态表，每个WP只使用：`NOT_STARTED/IN_PROGRESS/BLOCKED/VERIFIED/RELEASED`。`VERIFIED`必须附代码、Migration、测试命令和证据；只有部署并通过运行观察才是`RELEASED`。

任何Milestone不得因为文档存在而标记完成。状态以代码、数据库、运行结果和验收证据为准。

## 18. 参考文档

- [Claude Code开发总指引](CLAUDE-CODE-GUIDE.md)
- [需求与功能闭环 v1](product-requirements-and-feature-closure-v1.md)
- [平台实现契约目录 v1](platform-implementation-contract-catalog-v1.md)
- [工程与编码规范 v1](engineering-and-coding-standards-v1.md)
- [页面信息架构与低保真原型 v1](page-prototypes-and-information-architecture-v1.md)
- [部署安全架构 v1](docker-cloudflare-npm-deployment-architecture.md)
