# Visory Feature Store 与指标注册中心架构 v1

状态：Design Approved
最后更新：2026-08-28

## 1. 决策摘要

平台采用轻量、可追溯的三级 Feature Store：

- F1 核心原子特征随 Certified DataSnapshot 每日增量物化；
- F2 市场、板块、资金、财务和事件等公共领域特征按能力物化；
- F3 策略专属参数、复合公式、截面排名和评分按需计算并缓存；
- PostgreSQL 只承担 Definition、Dependency、Run、Snapshot、Capability 和查询索引等控制面；
- Parquet 是特征值和领域 Mart 的持久数据面，DuckDB 承担批量扫描、增量计算和查询；
- Hikyuu HDF5 或内存对象只是由已冻结快照生成的可重建运行缓存，不是真源；
- FeatureSnapshot 是不可变 Manifest，引用内容寻址的特征分区，不复制整套历史数据；
- 正式预测、Paper Portfolio 或 Formal Backtest 引用过的特征分区永久固定；未引用的 F3 缓存和可重建缓存才允许按保留策略清理；
- v1 不引入 ClickHouse、在线低延迟 Feature Server、消息队列或独立 Feature Store 服务。

本决策编号为 **D-028**。

## 2. 目标

Feature Store 不是另一套行情数据库，而是 Canonical Data 之上的统一计算、认证和发布层。它必须同时满足：

1. 页面、StrategySpec、Hikyuu、DSA 和个股研究读取同一份已发布事实；
2. 每个正式指标都有唯一标识、版本、参数、公式指纹、输入快照和质量状态；
3. T 日预测、T+1 执行和 T+H 验证可以追溯至当时可用的原始数据；
4. 历史回填可以在今天执行，但不能使用历史决策时尚不可用的数据；
5. 数据修订、Provider 切换或公式升级生成新分区和新快照，不静默覆盖旧结果；
6. 公共上游特征只计算一次，由市场、板块、策略和复盘复用；
7. 当前服务器用单个 Feature Worker、DuckDB 向量化和日级增量计算即可完成盘后核心流水线；
8. 所有投入 Formal 或 Paper 的指标均可落地和复现，但不预计算无限参数组合。

## 3. 非目标与边界

v1 不负责：

- 从 Provider 直接采集数据；采集、主备、Canonical Schema 和 DataSnapshot 由数据平台负责；
- 订单撮合、持仓、费用和绩效；这些由 Hikyuu Adapter 和组合账本负责；
- 保存 AI 报告、AI 观点或自然语言置信度；它们属于 Research/Opinion 结果域；
- 为板块和热点生成平台统一热度分；观察域只发布客观特征；
- 把全球指数、外汇、商品、海外利率和海外事件注入 A 股策略；它们保存在独立 GlobalObservationSnapshot；
- 毫秒级在线推理、逐笔数据或全市场分钟指标的无限参数物化；
- 允许前端、DSA、Vibe 迁移模块或策略脚本绕过 Registry 自行定义同名指标。

资金类 Feature 仍是公开数据支持的资金行为证据，不能被命名为已确认的账户资金来源。

## 4. 总体架构

```text
a-stock-data / Financial-API
              │
              ▼
 Raw → Canonical Data → Certified DataSnapshot
                              │
                    Indicator Registry
                              │
                  Dependency Resolver / DAG
                              │
                    Feature Compute Worker
                              │
          ┌───────────────────┼───────────────────┐
          │                   │                   │
      F1 Core             F2 Domain          F3 Strategy
    always materialized  always/cache       cache/on_demand
          │                   │                   │
          └───────────────────┼───────────────────┘
                              │
                 Immutable FeatureSnapshot
                              │
          ┌──────────────┬────┴─────┬──────────────┐
          │              │          │              │
       Web/API       StrategySpec  Hikyuu       DSA/Research
                    Resolver       Adapter         FactPack
```

控制面和数据面分离：

| 平面 | 技术 | 保存内容 |
| --- | --- | --- |
| 控制面 | PostgreSQL | 指标定义、依赖、任务、Attempt、分区目录、快照、能力、消费者绑定和审计 |
| 数据面 | Parquet | F1/F2/F3 特征值、领域 Mart、质量明细和计算诊断 |
| 计算与批量查询 | DuckDB | 列投影、窗口计算、截面聚合、as-of join 和分区写入 |
| 回测缓存 | Hikyuu HDF5/内存对象 | 从指定 DataSnapshot 和 FeatureSnapshot 构建的可重建输入 |

PostgreSQL 不保存全量日线特征值。DuckDB 数据库文件只保存必要的 Catalog/View 或工作状态，权威值仍在不可变 Parquet 分区中。

## 5. 术语和对象

| 对象 | 含义 |
| --- | --- |
| `IndicatorDefinition` | 指标的稳定语义、输入、公式、参数 Schema、输出和 PIT 规则 |
| `IndicatorVersion` | 某个不可变公式或实现版本 |
| `FeatureInstance` | Definition Version 与一组规范化参数形成的实例 |
| `FeatureDependencyPlan` | Resolver 为消费者生成的依赖 DAG、列投影、时间和能力约束 |
| `FeatureRun` | 一次计算请求的逻辑任务 |
| `FeatureAttempt` | FeatureRun 的一次实际执行；重试产生新 Attempt |
| `FeaturePartition` | 内容寻址、原子发布的 Parquet 结果分区 |
| `FeatureSnapshot` | 引用分区、定义、数据快照和质量状态的不可变 Manifest |
| `FeatureView` | 面向某消费者的逻辑字段集合，不是新的事实副本 |
| `FeatureBundle` | 为 Strategy/Hikyuu 冻结的 FeatureView 投影与分区清单 |
| `Capability` | 可独立认证的特征能力，如 `stock_daily_core`、`market_emotion` |

## 6. 三级特征模型

### 6.1 F1：核心原子特征

F1 服务于绝大多数页面和策略，采用 `always` 物化，按交易日增量生成并长期保留。

首批建议包括：

- 1/5/10/20/60 日收益；
- MA5/10/20/60、成交量和成交额均线；
- RSI14、ATR14、20 日波动率；
- 振幅、换手率、量比、成交额分位和流动性；
- 新高/新低、均线上下、趋势和量价关系的原子布尔或枚举；
- 交易状态、ST、新股冷却、停牌和涨跌停状态的只读投影；
- 计算市场宽度和板块宽度所需的股票级基础列。

OHLCV、公司行动、股票状态和板块成员本身属于 Canonical Fact。F1 可以为消费便利投影这些字段，但不能制造另一套权威行情或成员数据。

### 6.2 F2：公共领域特征

F2 由多个页面、策略或研究模块共享，使用 `always` 或受控 `cache` 物化。

| 领域 | 示例 |
| --- | --- |
| 市场 | 宽度、涨跌停生态、风险偏好、流动性、五维情绪和市场状态 |
| 板块 | 收益、相对强弱、宽度、资金行为、持续性、排名和规则异动输入 |
| 资金 | 订单规模、杠杆、公开席位、大宗、互联互通活跃度和可信度 |
| 财务 | 营收、利润、现金流、ROE、估值和历史分位的 PIT 特征 |
| 事件 | 公告、新闻、题材关系、事件重要性和证据质量的结构化事实 |

板块领域只保存独立客观指标、Provider 原始排名和规则事件，不生成 `sector_heat_score` 或 `hot_stock_score`。

### 6.3 F3：策略专属特征

F3 只在激活的 StrategySpec、Preview、Research 或 Formal Run 显式声明后计算：

- 特殊窗口 MA37、RSRS 参数组合；
- StrategySpec 内复合公式；
- 特定股票池内的 rank、percentile 和 zscore；
- Sequoia 迁移策略需要的组合条件；
- 策略专属板块评分、个股评分和 score breakdown；
- 参数研究中进入正式候选验证的特征矩阵。

F3 不因“可能以后会用”而预计算。进入 Prediction、Paper 或 Formal Run 的 F3 分区会被固定；未引用的研究缓存允许过期。

## 7. Indicator Registry

### 7.1 定义契约

```yaml
indicator_id: stock.rsi
definition_version: 1.0.0
domain: stock
frequency: 1d
engine: hikyuu
inputs:
  - daily_bar.close
parameters:
  n:
    type: integer
    default: 14
    minimum: 2
    maximum: 250
lookback: 14
warmup: 30
recompute_policy:
  type: bounded
  sessions: 14
outputs:
  - name: value
    type: float64
    unit: ratio
materialization: always
point_in_time: true
null_policy: insufficient_history
```

最少注册字段：

```text
indicator_id / definition_version / publication_status
domain / frequency / engine
input_definitions[] / output_schema
parameter_schema / normalized_default_parameters
lookback / warmup / recompute_policy
adjustment_policy / universe_policy / asof_policy
materialization / capability_id
point_in_time / pit_review_version
formula_hash / implementation_hash
numeric_policy / null_policy
owner / created_at / deprecated_at
```

### 7.2 版本规则

- 指标意义、公式、复权、输入数据集、方向或输出类型变化：提升语义版本；
- 不影响数值的描述修订：允许只更新 Definition 元数据并记录审计；
- 引擎升级可能改变数值：形成新 `implementation_hash`，通过对照后决定是否提升版本；
- 旧版本不可原地替换或删除；
- Deprecated 版本禁止新 StrategySpec 引用，但已有 Run 仍可解析；
- 未通过 PIT 审查的指标只能用于探索性研究，不能进入 Formal 或 Paper。

### 7.3 参数规范化

`FeatureInstanceKey` 由以下内容确定：

```text
indicator_id
indicator_version
canonical_parameter_json
parameter_hash
frequency
universe_scope_hash（仅截面特征）
```

参数按固定键序、类型和 Decimal 精度序列化。`14`、`14.0` 和字符串 `"14"` 不得在未声明转换的情况下静默成为同一参数。

## 8. 依赖 DAG 和 ComputePlan

### 8.1 解析

Registry 保存定义级依赖，Resolver 结合参数生成实例级 DAG：

```text
StrategySpec
  → required FeatureInstances
  → transitive dependencies
  → capability and PIT checks
  → topological order
  → partition and column projection
  → FeatureDependencyPlan
```

`FeatureDependencyPlan` 至少包含：

```text
plan_id / projection_hash
consumer_type / consumer_id / consumer_version
required_instances[] / required_columns[]
dependency_edges[] / topological_order
lookback / warmup / date_range
universe_id / universe_version / universe_hash
accepted_capability_certification_statuses
point_in_time_constraints
estimated_rows / estimated_memory / resource_class
```

### 8.2 门禁

以下情况在计算前失败：

- DAG 有环；
- Definition、Version 或参数无法解析；
- Formal/Paper 依赖 `point_in_time=false` 指标；
- 股票、指数、ETF 或板块实体类型不匹配；
- StrategySpec 引用物理表、任意 SQL 或未注册列；
- 第一版 A 股策略引用全球特征域；
- 截面指标未冻结股票池和 PIT 成员版本；
- 估算资源超过当前运行级别且没有拆分计划；
- 输出列重名或别名不稳定。

### 8.3 共享计算

同一 DataSnapshot、Definition Version、参数和范围的公共上游只计算一次。多个策略引用 MA20 时共享同一个 F1 分区；策略的筛选和评分差异不会复制 MA20。

分区缓存键建议为：

```text
definition_hash
parameter_hash
input_partition_hashes
universe_hash
date_range
engine_version
numeric_policy_version
```

## 9. 物理存储模型

### 9.1 宽长表混合

#### F1 核心宽表

```text
feature_stock_daily_core
```

逻辑唯一键：

```text
canonical_id + trade_date + feature_set_version + partition_id
```

核心宽表只包含稳定、高复用、日级批量读取字段。新增核心列必须更新 `feature_set_version` 和列映射，不能在同一版本中改变语义。

#### 扩展长表

```text
feature_value
```

逻辑唯一键：

```text
entity_type
entity_id
feature_time
indicator_id
indicator_version
parameter_hash
output_name
frequency
feature_partition_id
```

长表适用于自定义参数、稀疏事件、实验特征和多输出指标。

#### 领域 Mart

```text
market_feature_daily
sector_feature_daily
fundamental_feature_pit
capital_evidence_daily
event_feature
```

页面和 DSA 优先读取 Mart；禁止 API 请求时扫描全量股票历史并现场计算市场或板块指标。

### 9.2 分区方式

日级增量按“领域＋指标组＋频率＋年份＋交易日＋修订”组织，一个指标组的全市场日数据写成少量 Parquet 文件，禁止按股票生成海量小文件。

```text
domain=stock/group=core/frequency=1d/year=2026/trade_date=2026-08-27/revision=1/
domain=market/group=sentiment/frequency=1d/year=2026/trade_date=2026-08-27/revision=1/
domain=sector/group=capital/frequency=1d/year=2026/trade_date=2026-08-27/revision=1/
domain=strategy/strategy_id=<id>/instance=<hash>/year=2026/trade_date=2026-08-27/
```

历史首次回填可以按月或年写较大分区；进入每日增量后按交易日写入。Snapshot Manifest 始终引用确切文件、行数和 Hash，不依赖目录“最新文件”语义。

### 9.3 FeaturePartition

控制面记录：

```text
feature_partition_id
domain / group / frequency
date_from / date_to / trade_date
definition_set_hash / parameter_set_hash
data_snapshot_ids[] / input_partition_ids[]
universe_hash / taxonomy_version
storage_uri / file_hash / schema_hash
row_count / min_entity_id / max_entity_id
min_available_at / max_available_at
attempt_id / created_at / published_at
quality_status / reason_codes
reference_count / retention_class
```

Worker 先写 Attempt 临时目录，完成 Schema、行数、唯一键、Hash、时间和数值检查后，在同一文件系统原子发布。控制面只在文件发布成功后提交分区记录。

## 10. 时间模型和 Point-in-time

每条特征或分区必须区分：

| 字段 | 含义 |
| --- | --- |
| `feature_time` / `trade_date` | 特征描述的业务时间 |
| `effective_from/to` | 财务、分类或状态事实的生效区间 |
| `source_max_available_at` | 所有输入事实中最晚的实际可用时间 |
| `available_at` | 按输入可用时间和 Definition 发布滞后规则推导的最早可知时间 |
| `computed_at` | 本次计算真实发生时间 |
| `published_at` | 分区或 FeatureSnapshot 被平台认证发布的时间 |

`available_at` 不因今天执行历史回填而改成今天。它表示历史上最早何时具备计算所需事实；`computed_at` 才表示本次实际计算时间。

### 10.1 三种使用模式

| 模式 | 时间门禁 |
| --- | --- |
| 当日 Formal/Paper | `available_at <= decision_at` 且 `FeatureSnapshot.published_at <= decision_at` |
| 生产历史复现 | 必须绑定当时实际发布的原 FeatureSnapshot |
| Research 历史重建 | 允许 `computed_at > decision_at`，但全部输入必须满足历史 `available_at <= decision_at` |

Research 重建不能冒充生产历史复现。运行报告必须显示 `LIVE_PUBLISHED`、`PRODUCTION_REPLAY` 或 `HISTORICAL_REBUILD`。

### 10.2 As-of join

财务、融资融券、公告、新闻和题材等稀疏数据必须按 `available_at` 做 as-of join。允许沿用最近一期的指标必须在 Definition 中声明：

```text
asof_policy
max_staleness_sessions
effective_trade_date
lag_trading_days
```

未声明时不得前向填充。历史缺失的 today-only 榜单或资金数据保持缺失，不按零回填。

## 11. FeatureSnapshot

FeatureSnapshot 是不可变 Manifest，而不是整套特征数据的副本：

```yaml
feature_snapshot_id: fs_<uuidv7>
snapshot_type: CLOSE_CORE
as_of_trade_date: 2026-08-27
decision_cutoff_at: 2026-08-27T18:00:00+08:00
published_at: 2026-08-27T17:30:00+08:00
data_snapshot_ids:
  - ds_<uuidv7>
feature_partition_ids:
  - fpart_<uuidv7>
  - fpart_<uuidv7>
  - fpart_<uuidv7>
definition_versions:
  stock.rsi: 1.0.0
  market.breadth: 1.0.0
certified_capabilities:
  stock_daily_core: certified
  market_emotion: certified
  sector_capital: certified
missing_capabilities: []
max_source_available_at: 2026-08-27T17:24:12+08:00
quality_report_id: quality_<uuidv7>
manifest_hash: sha256:...
```

Manifest Hash 覆盖规范化后的全部引用和状态。相同输入、Definition、参数和数值策略重复计算必须生成相同分区 Hash；任务时间、Attempt ID 等运行元数据不进入数值内容 Hash。

### 11.1 快照类型

| 类型 | 用途 |
| --- | --- |
| `CLOSE_CORE` | 17:30核心股票、市场、情绪和板块公共能力 |
| `LATE_A_SHARE` | 龙虎榜、融资融券、大宗等晚到A股能力 |
| `CORRECTION` | Provider或质量审计后的修订版本 |
| `HISTORICAL_REBUILD` | 版本冻结的历史回填或研究重建 |

全球观察不属于 FeatureSnapshot 类型。

### 11.2 FeatureBundle

策略 Compiler 从 FeatureSnapshot 生成消费者专属 FeatureBundle：

```text
feature_bundle_id
feature_snapshot_ids[]
dependency_plan_id / projection_hash
required_partition_ids[] / required_columns[]
date_range / decision_time_policy
universe_hash
bundle_manifest_hash
```

FeatureBundle 只做投影和冻结，不改变事实值。Hikyuu、Preview 和 Formal 必须从同一 DependencyPlan 解析，不能各自选择不同列或不同修订版。

## 12. 能力认证与失败语义

能力独立认证，`capability_certification_status`使用：

```text
CERTIFIED
PROVISIONAL
UNAVAILABLE
STALE
```

计算失败写Task/Attempt和`quality_status=FAILED`，不扩展Capability枚举。Formal和Paper默认只接受`CERTIFIED`。Preview或DSA可以显式接受`PROVISIONAL`，但输出必须展示状态和缺口。

### 12.1 阻断范围

- `stock_daily_core` 身份冲突、关键行情缺失或 PIT 失败：阻断所有依赖它的能力；
- 单个资金通道失败：只使该通道和依赖它的综合能力不可用；
- 市场情绪缺少必需维度：保留已成功的原始维度，但不认证完整版情绪分；
- 单个板块异常：隔离该板块并重新检查整体覆盖率；
- F3 策略特征失败：只阻断声明依赖它的策略；
- 全球观察失败：不影响任何 FeatureSnapshot；
- DSA 可以生成删减版 FactPack，但不能把缺失特征替换为上一日值。

缺失特征不得动态删除评分项后重新归一权重，除非 StrategySpec 和 WeightPolicy 事先声明了独立、可回测的降级版本。

### 12.2 质量检查

发布前至少检查：

- Schema、类型、单位和 Decimal 精度；
- 逻辑唯一键和稳定排序；
- 行数、股票池覆盖率和空值率；
- 极值、无穷值、除零和异常跳变；
- 输入分区 Hash 和 DataSnapshot Manifest；
- `available_at`、决策时点和未来函数；
- 截面计算股票池、行业成员和市值的 PIT 版本；
- 复权序列与未复权成交价格没有混用；
- 同一输入重算的结果 Hash 一致。

## 13. 增量、修订和历史回填

### 13.1 日常增量

每日只计算新交易日和必要 warmup 投影：

```text
Certified DataSnapshot(T)
  → resolve affected FeatureInstances
  → load warmup window
  → calculate T values
  → validate and publish partitions
  → publish FeatureSnapshot(T)
```

### 13.2 修订传播

Definition 必须声明修订传播策略：

| 类型 | 处理 |
| --- | --- |
| `same_session` | 只影响同一交易日的截面或聚合 |
| `bounded(n)` | 从修订日向后重算 n 个交易日 |
| `forward_to_latest` | EMA、状态机等递归结果重算至最新日期 |
| `effective_range` | 分类、财务或状态按生效区间重算 |

Resolver 从修订分区沿 DAG 找到受影响后代。新结果写入新 Revision 和新 FeatureSnapshot，旧 Snapshot、Prediction、FactPack 和 Backtest 保持不变。

### 13.3 历史回填

- 按月或年分块并保存 checkpoint；
- 支持续跑，不重复发布已验证分区；
- 00:30-06:00执行，不与盘后正式流水线并发；
- 默认资源等级低于当日采集、Formal Strategy 和 Paper Portfolio；
- 每块记录数据快照、定义集、范围、行数和 Hash；
- 历史股票池、板块成员、复权、财务披露和事件时间均必须 PIT；
- current-only 数据不得伪造历史。

## 14. 物化策略和落地定义

| 策略 | 含义 | 保留 |
| --- | --- | --- |
| `always` | 核心公共能力随 Certified Snapshot 自动计算 | 长期保留 |
| `cache` | 已激活策略或复用型扩展特征 | 被正式引用则固定，否则按 TTL |
| `on_demand` | 一次性研究或参数搜索中间特征 | 默认短期，正式入选前必须物化 |

“指标可以落地”在本平台中的定义是：

1. 存在已审核的 IndicatorDefinition 和不可变版本；
2. 可以解析完整输入和依赖 DAG；
3. 具有确定的输出 Schema、时间语义和质量规则；
4. 结果形成 FeaturePartition 或可重建且有 Hash 的缓存；
5. 正式消费者引用时形成 FeatureSnapshot/FeatureBundle 绑定；
6. 可以从 Run 反向追溯至 Definition、DataSnapshot、ProviderRun 和 Raw Hash。

因此不需要永久预计算所有 MA 窗口或参数组合，但任何进入正式信号、权重或回测的实际参数结果都必须落地并冻结。

## 15. 消费者协议

### 15.1 页面与 API

- 读取已发布 FeatureSnapshot 或领域 Mart；
- 默认返回最新允许状态，同时返回 Snapshot ID；
- 查看历史结果时可以选择“当时发布版”或“最新修订版”；
- 不允许页面 JavaScript 重新计算同名权威指标；
- Provisional、缺失、滞后和修订必须可见。

### 15.2 StrategySpec

- 只引用 `indicator_id + version + parameters + alias`；
- Resolver 生成 FeatureDependencyPlan；
- 未声明字段、PIT失败、缺少能力或全球特征引用直接拒绝编译；
- 截面排序绑定股票池和稳定 tie-breaker；
- F3 策略评分保存原始特征、贡献、权重版本和 score breakdown。

### 15.3 Hikyuu

- 只读取 Compiler 冻结的 FeatureBundle；
- 技术指标以 Hikyuu 为公式权威时，Registry 仍管理版本、参数、落地和血缘；
- 外部市场、板块、财务和事件特征通过 Adapter 对齐为 Hikyuu Indicator、Environment、Condition、Signal 或 Selector 输入；
- Hikyuu 缓存记录 DataSnapshot、FeatureSnapshot、Bundle、Builder 和文件 Hash；
- Hikyuu 不直接访问 Provider，也不自行选择“最新”分区；
- 缓存删除后可从冻结 Manifest 重建，不改变 RunBundle。

### 15.4 DSA 与个股研究

- DSA FactPack 只读取已发布 Mart 和 Snapshot；
- 可以接受删减能力，但必须携带 `missing_capabilities`；
- AI观点不能写回F1/F2事实或覆盖指标值；
- UZI/TradingAgents的研究结论进入Research Result域；只有结构化、已注册且通过数据治理的输入才可能在后续版本成为Feature；
- 全球观察通过独立Snapshot加入复盘背景，不与A股FeatureSnapshot合并。

## 16. 保留、引用和垃圾回收

建议 v1 保留策略：

| 产物 | 保留策略 |
| --- | --- |
| IndicatorDefinition、依赖、Manifest和Hash | 永久 |
| F1核心特征、F2公共特征 | 永久 |
| 被Prediction、Paper、Formal Backtest或正式FactPack引用的F3 | 永久固定 |
| 未被引用的F3缓存 | 30天 |
| Hikyuu可重建缓存 | 30天LRU |
| 成功Attempt临时文件 | 原子发布后清理 |
| 失败和隔离产物 | 14天 |
| 在线计算日志 | 90天，之后压缩归档 |

垃圾回收必须：

1. 先计算 Snapshot、Run、Prediction、FactPack 和报告的引用闭包；
2. 对引用数大于零或 retention class 为 `PINNED` 的分区拒绝删除；
3. 默认先生成 dry-run 清单和预计释放空间；
4. 保存清理审计；
5. 不删除 Raw、DataSnapshot 或 FeatureSnapshot Manifest；
6. Hikyuu缓存清理不影响权威特征分区。

## 17. 文件目录

所有数据、挂载和配置继续位于 `/data/daily_stock_analysis`：

```text
/data/daily_stock_analysis/
├── config/platform/indicators/
│   ├── stock/
│   ├── market/
│   ├── sector/
│   ├── fundamental/
│   └── event/
├── storage/app/features/
│   ├── domain=stock/
│   ├── domain=market/
│   ├── domain=sector/
│   ├── domain=fundamental/
│   ├── domain=event/
│   └── domain=strategy/
├── storage/app/observations/
│   ├── market/
│   ├── sector/
│   ├── stock/
│   └── review/
├── storage/app/hikyuu/
├── storage/app/quarantine/feature/
├── storage/app/.staging/
├── storage/app/state/duckdb/
├── storage/postgres/
├── logs/feature-worker/
└── backups/
```

本文只定义目标目录，不在设计阶段创建目录或配置文件。

## 18. 盘后时序和资源预算

```text
16:00        a-stock-data核心采集
17:10        CERTIFIED:backtest_core目标
17:10-17:22  F1股票核心特征增量计算
17:22-17:30  F2市场、情绪、资金和板块公共特征
17:30        CLOSE_CORE FeatureSnapshot目标发布
17:30-17:44  板块异动、热点观察和领域Mart
17:44-18:05  按StrategySpec计算必要F3并生成核心正式信号
17:50-18:20  DSA FactPack和复盘；资源冲突时让位于Formal Strategy
18:10-18:30  晚到A股资金数据和LATE_A_SHARE FeatureSnapshot
18:30-18:50  显式依赖晚到能力的策略
19:00        T日正式策略硬截止
20:30        Correction审计
00:30-06:00 历史回填、参数研究、压缩和缓存维护
```

当前服务器建议：

```yaml
feature_runtime:
  worker_count: 1
  max_threads: 2
  max_concurrent_feature_groups: 1
  daily_incremental_only_in_close_window: true
  parquet_compression: zstd
  history_backfill_window: "00:30-06:00"
  pause_backfill_during_close_pipeline: true
  pause_heavy_backtest_during_close_pipeline: true
```

同一时刻只执行一个大指标组。DuckDB按需要列投影，避免读取完整宽表；跨截面计算前按稳定键排序。DSA和全球观察属于较低资源优先级，不得挤占Formal策略硬截止。

## 19. 控制面表族

建议 PostgreSQL 表族：

| 表 | 主要职责 |
| --- | --- |
| `indicator_definition` | 指标身份、版本、Schema、公式、PIT和状态 |
| `indicator_dependency` | 定义级依赖边 |
| `feature_instance` | 规范参数和实例Hash |
| `feature_dependency_plan` | 消费者解析后的DAG和列投影 |
| `feature_run` | 逻辑任务、优先级、范围和状态 |
| `feature_attempt` | 租约、重试、资源、错误和诊断 |
| `feature_partition` | 文件、Hash、Schema、范围和质量索引 |
| `feature_snapshot` | Manifest、时间、类型和根Hash |
| `feature_snapshot_partition` | Snapshot与Partition的不可变关联 |
| `feature_capability` | 每个Snapshot的能力认证和原因 |
| `feature_consumer_binding` | Strategy、Prediction、Run、FactPack引用关系 |
| `feature_gc_audit` | 保留判定、dry-run和清理结果 |

表中ID使用平台生成的稳定资源ID；资产事实使用`entity_key`，股票专属投影可同时保存`canonical_id`（如`sh600519`），不使用六码裸码作为关联键。

## 20. API 边界

首批内部API建议：

```text
GET  /api/v1/indicators
GET  /api/v1/indicators/{indicator_id}/versions/{version}
GET  /api/v1/feature-snapshots?trade_date=&type=&publication_status=
GET  /api/v1/feature-snapshots/{snapshot_id}
GET  /api/v1/feature-snapshots/{snapshot_id}/lineage
POST /api/v1/feature-plans/resolve
POST /api/v1/feature-runs
GET  /api/v1/feature-runs/{run_id}
GET  /api/v1/features/query?view_id=&snapshot_id=&entity_id=
```

API要求：

- 查询通过注册的FeatureView或受控字段列表，不接受任意SQL和物理路径；
- 正式调用必须显式或由Resolver冻结Snapshot ID；
- “latest”只用于页面默认展示，不能写入RunBundle；
- 返回 `snapshot_id`、`data_as_of`、`available_at`、`quality_status`、`missing_capabilities` 和 `is_corrected`；
- 大范围明细通过异步导出或分区读取，不把全市场全历史塞入同步API。

## 21. 确定性、权限和运维

### 21.1 确定性

- 聚合和排名前按 `trade_date + canonical_id` 或领域稳定键排序；
- 并列排名使用明确tie-breaker；
- Decimal、NaN、Infinity、时区和空值序列化统一版本化；
- 不依赖数据库默认顺序、当前系统时间、进程随机Hash或未固定随机种子；
- 同一ComputePlan和输入重跑校验内容Hash；
- 引擎版本或数值库升级先执行golden dataset对照。

### 21.2 权限

- Provider凭据不进入IndicatorDefinition和Snapshot；
- Strategy插件无网络、文件和数据库权限，只读取Compiler注入的FeatureBundle；
- 页面/API只读访问已发布分区；
- Definition发布、Correction和垃圾回收属于受控运维权限；
- 物理路径、内部错误栈和Provider密钥不返回普通用户。

### 21.3 监控

至少监控：

```text
feature_run_duration_seconds
feature_partition_rows / bytes
feature_cache_hit_ratio
feature_snapshot_publish_lag
feature_capability_certification_status
feature_null_ratio / coverage_ratio
feature_determinism_mismatch_total
feature_correction_affected_partitions
feature_worker_memory_peak
feature_gc_reclaimable_bytes
```

告警应区分核心能力阻断、单策略失败、可删减复盘和普通缓存未命中。

## 22. 实施阶段

### FS1：Registry与快照骨架

- 建立Definition、Version、Dependency和参数规范化；
- 建立FeatureRun/Attempt、Partition和Snapshot Manifest；
- 完成DAG解析、PIT门禁、内容Hash和原子发布；
- 暂不迁移全部指标。

### FS2：F1核心股票特征

- 选择首批核心宽表字段；
- 对接Certified DataSnapshot和Hikyuu公式权威；
- 完成增量、warmup、修订传播和历史回填；
- 用固定小样本与Hikyuu结果对照。

### FS3：F2市场和板块领域

- 迁移市场宽度、情绪、资金和板块客观指标；
- 发布领域Mart与能力状态；
- 让页面和DSA改读Mart，不再重复计算。

### FS4：F3策略与Hikyuu

- StrategySpec Compiler生成DependencyPlan；
- 实现策略缓存、FeatureBundle和Hikyuu Adapter；
- Preview、Formal和Paper验证信号Hash一致；
- 固定正式消费者引用。

### FS5：修订、回填和保留治理

- 建立Correction影响传播；
- 实现夜间分块回填和checkpoint；
- 建立引用闭包、dry-run垃圾回收和备份恢复演练；
- 形成容量趋势和扩容门槛报告。

## 23. 验收标准

1. 每个正式指标可解析至唯一Definition、Version、参数和公式Hash；
2. 同一输入、Definition和数值策略重复计算得到相同Partition Hash；
3. F1/F2公共特征不会因多个消费者重复物化；
4. Formal/Paper不能读取`available_at > decision_at`或未发布快照；
5. Research历史重建不会因今天的`computed_at`错误排除当时已知事实，也不会使用未来披露；
6. Provider修订产生新Partition和FeatureSnapshot，不覆盖旧Prediction和Backtest；
7. 资产跨域关联键使用`entity_key`；股票投影中的`canonical_id`必须带市场前缀并与`asset_type/entity_key`一致；
8. 板块观察域没有平台统一热度分，策略专属评分只存在于策略上下文；
9. 全球数据不能进入FeatureDependencyPlan、FeatureBundle或Hikyuu缓存；
10. 缺失能力不会被上一日值、零值或动态重权伪装成完整成功；
11. 页面、DSA、Strategy和Hikyuu可以证明读取同一Snapshot；
12. 被正式结果引用的F3不能被垃圾回收，未引用缓存可按审计策略清理；
13. 单Worker和双线程配置能在17:30前完成日级F1/F2核心增量；
14. 历史回填可分块续跑，且不会抢占盘后正式流水线；
15. 任意Prediction或Backtest可追溯至FeatureSnapshot、DataSnapshot、ProviderRun和Raw Hash。

## 24. 已收敛的实现基线

1. 首批F1包含收益、MA、波动、ATR、成交/换手、ADV20、涨跌停/停牌/上市天数、基础估值和财务可用标志；Golden Dataset场景见实现契约目录C-013；
2. Formal Hikyuu使用固定DataSnapshot构建的HDF5缓存；内存/DataFrame只用于测试、小型Preview和构建校验；
3. PostgreSQL在M0建立，M1承载Identity/Task/Artifact，M2—M3迁移数据和Feature控制面；Legacy SQLite按读写切换保留Adapter；
4. 核心历史回填从2018-01-01开始，财务从2017报告期开始；无法证明PIT的数据显式Unavailable；
5. MVP不引入ClickHouse；只有优化DuckDB/Parquet后仍连续违反SLA且Benchmark证明必要时再立项；
6. 分钟线、北交所、ETF和其他资产均在MVP后通过新Capability接入。

实施Work Package、回填批次和Exit Gate见[实施路线与验收方案 v1](implementation-roadmap-and-acceptance-v1.md)。

## 25. 参考资料

- [指标、预测与 Hikyuu 回测架构](backtest-and-indicator-architecture.md)
- [A 股数据平台与 Canonical Data Contract v1](data-platform-and-canonical-contract.md)
- [盘后数据采集与 Snapshot 发布 SLA v1](data-ingestion-and-snapshot-sla.md)
- [StrategySpec v1 策略契约](strategy-spec-v1.md)
- [Fleur-Lite 回测运行与结果一致性架构](fleur-lite-backtest-runtime.md)
- [A 股市场情绪与资金行为架构 v1](market-sentiment-and-capital-flow-architecture.md)
- [A 股板块异动、热门观察与策略评分边界 v1](sector-observation-and-strategy-scoring-architecture.md)
- [全球市场观察与 A 股策略隔离架构 v1](global-market-observation-boundary.md)
- [Hikyuu指标文档](https://hikyuu.readthedocs.io/zh-cn/latest/indicator/overview.html)
- [Hikyuu因子管理文档](https://hikyuu.readthedocs.io/zh-cn/latest/factor.html)
- [DuckDB Parquet文档](https://duckdb.org/docs/stable/data/parquet/overview)
- [Fleur数据治理架构](https://github.com/WackyGem/Fleur/blob/main/docs/architecture/data-governance.md)
- [DSA A 股收盘复盘 FactPack 架构 v1](dsa-close-review-fact-pack.md)
- [A 股分层个股研究与 StockResearchFactPack 架构 v1](stock-research-architecture.md)
- [A 股主平台模块化单体、API、任务与权限架构 v1](platform-shell-api-task-permission-architecture.md)
- [A 股平台 Docker、Cloudflare、NPM 与访问安全架构 v1](docker-cloudflare-npm-deployment-architecture.md)
