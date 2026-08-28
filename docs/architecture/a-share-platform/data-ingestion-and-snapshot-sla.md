# Visory 盘后数据采集与 Snapshot 发布 SLA v1

状态：已确认（Design Approved）

最后更新：2026-08-28

## 1. 决策摘要

平台不在15:00收盘后立即抓取正式数据，盘后采集统一从交易日16:00开始，在保留一小时数据稳定窗口的同时，为Feature Store、市场/板块指标和正式策略计算留出更充分时间。

第一版SLA固定为：

- 15:50只做进程、网络、磁盘、凭据和Provider能力预检，不读取当日正式业务数据；
- 16:00启动a-stock-data核心采集；
- 16:30目标发布`PROVISIONAL`快照；
- 16:40核心源失败或质量不合格时启用Financial-API补充；
- 17:10目标发布`CERTIFIED:backtest_core`；
- 17:30目标发布市场、板块和复盘能力认证；
- 19:00为T日正式策略硬截止；
- 20:30执行晚到数据和修订检查，需要时创建新的`CORRECTION`快照。

所有时间均为`Asia/Shanghai`。上述时间是目标契约，不代表当前仓库已经提供相应调度配置；进入实现阶段时再同步到`.env.example`、Docker和任务调度文档。

## 2. 为什么从16:00开始

- a-stock-data的部分盘后能力明确提示在15:30后调用，16:00仍为上游更新保留至少30分钟缓冲；
- 平台使用日线T日收盘事实生成T+1计划，不要求15:00后立即成交；
- 晚一小时不会产生T+1交易时序损失，同时比17:00启动多出一小时用于指标和策略计算；
- 当前服务器只有四核，错开上游更新高峰也有利于降低重复请求和补数压力。

16:00开始不等于数据天然正确。身份、单位、完整性、双源差异和`available_at`门禁仍必须全部执行。

## 3. Snapshot 类型

| 类型 | 定义 | 允许用途 | 禁止用途 |
| --- | --- | --- | --- |
| `PROVISIONAL` | 核心源已完成基础Schema和身份检查，尚未完成全部认证 | 页面、数据检查、策略Preview | 正式预测、Formal回测、Paper Portfolio |
| `CERTIFIED` | 指定能力通过完整质量门禁 | 对应能力的正式计算 | 使用未认证能力 |
| `CORRECTION` | 晚到或修订数据形成的新不可变快照 | 新运行、差异分析 | 覆盖旧Snapshot和旧Run |
| `REJECTED` | 核心门禁失败 | 诊断和修复 | 所有业务消费 |

Snapshot状态只能按状态机推进，不能把失败记录删除后重新伪装成同一次成功运行。

## 4. 每日时间线

```text
15:50  preflight
  │
16:00  a-stock-data core ingestion
  │
16:20  first normalization and quality pass
  │
16:30  provisional target
  │
16:40  fallback decision / Financial-API bulk supplement
  │
17:10  certified:backtest_core target
  │
17:30  market/sector/review capability target
  │
19:00  T-day formal signal hard deadline
  │
20:30  late-data and correction audit
```

### 4.1 15:50 Preflight

只检查：

- 数据盘剩余空间和可写性；
- PostgreSQL、DuckDB和任务表可用性；
- Provider Adapter版本和能力声明；
- a-stock-data实际上游连通性；
- Financial-API凭据是否存在及其非敏感能力信息；
- 上一交易日任务是否存在未终止租约；
- 当日是否为交易日。

Preflight不生成DataSnapshot，也不把实时行情保存为当日正式日K。

### 4.2 16:00 核心采集

优先顺序：

1. Security Master变更和Provider Symbol Map；
2. Trading Calendar；
3. 未复权日K、停牌、ST、涨跌停和成交状态；
4. 公司行动和复权依赖；
5. 基准指数；
6. 板块、资金、涨跌停池、热点和公告；
7. 财务和估值修订。

每个数据集单独生成ProviderRun。a-stock-data内部若从主上游切换到备用上游，必须保存`actual_upstream`和降级原因。

### 4.3 16:30 Provisional

满足下列条件才可发布：

- Schema和身份检查通过；
- 当日分区存在；
- 基本OHLC关系通过；
- 行数和日期没有明显异常；
- 无Provider Symbol冲突。

Provisional只用于Web快速查看和Preview。页面必须显示“数据未完成正式认证”。

### 4.4 16:40 补充源决策

出现以下任一条件时启用Financial-API：

- a-stock-data核心任务失败两次；
- 核心行情覆盖率未达到门槛；
- Security、Calendar、Bar、Status或CorporateAction质量门禁失败；
- 上游Schema变化导致Adapter无法确认字段；
- 双源抽检计划要求当日执行完整交叉校验。

行情补充优先使用Financial-API全市场增量文件或Market Dump，不逐只股票发起数千次请求。

## 5. 按能力认证

Snapshot保存独立能力状态：

```yaml
certified_capabilities:
  backtest_core: certified
  market_breadth: certified
  sector_flow: unavailable
  hotspot_review: certified
  financial_factor: provisional
```

依赖规则：

| 消费方 | 必需认证 |
| --- | --- |
| 纯价格/技术策略 | `backtest_core` |
| 市场宽度策略 | `backtest_core + market_breadth` |
| 板块轮动策略 | `backtest_core + sector_flow` |
| 财务因子策略 | `backtest_core + financial_factor` |
| DSA收盘复盘 | 已认证市场能力；缺失部分必须披露 |
| Paper Portfolio | 策略全部依赖均认证 |

一个非关键新闻源失败不会阻止纯价格策略，但使用新闻因子的策略必须拒绝运行，不能退化成另一套策略。

## 6. backtest_core 认证门禁

必须同时满足：

- Security Master、Provider Symbol和资产类型无冲突；
- 交易日历一致；
- 当日每只活跃证券存在有效Bar或显式停牌状态；
- OHLC、成交量、成交额和单位校验通过；
- 基准指数数据完整；
- ST、停牌、上市、退市和涨跌停规则可用；
- 公司行动足以解释除权日价格关系；
- 所有正式输入满足`available_at <= decision_at`；
- Snapshot Manifest、分区Hash和质量报告完整。

推荐初始阈值：

```yaml
snapshot_quality:
  bar_or_suspended_status_coverage: 0.998
  max_excluded_instrument_ratio: 0.002
  max_excluded_instrument_count: 10
  price_difference_tolerance_ticks: 1
```

阈值必须版本化。历史统计形成前不得自动放宽。

## 7. 隔离、阻断与降级

### 7.1 阻断整个 backtest_core

- 交易日历冲突；
- 股票身份或资产类型批量冲突；
- 未复权和复权口径无法区分；
- 基准指数缺失；
- 数据覆盖低于阈值；
- 双源存在大面积无法解释的OHLC差异；
- Snapshot Hash或Manifest不完整。

### 7.2 隔离少量证券

少量证券异常且未超过阈值时可以进入`excluded_instruments`：

- 当日禁止新买；
- 从候选池和TopN中排除；
- 保存排除原因和数据证据；
- 已被Paper Portfolio持有时，阻断对应组合调仓，不能假设成交；
- 回测RunBundle必须保存排除清单Hash。

排除会改变策略股票池，因此不能隐藏为普通数据警告。

### 7.3 能力级降级

板块资金、热点、新闻、龙虎榜等失败时，只把对应能力标记为`unavailable`。DSA可以生成删减版复盘，但必须明确指出缺少哪些事实；依赖这些能力的策略不能运行。

## 8. 19:00 硬截止

若19:00仍未取得策略全部必需认证：

- T日不生成新的正式策略预测；
- 不使用T-1信号冒充T日信号；
- 不使用Provisional数据创建Formal回测；
- Paper Portfolio不执行新的策略买入计划；
- 保存失败原因并发送数据质量告警；
- 风险退出是否使用独立安全数据链，留待Paper Portfolio运行规则单独确定。

历史研究任务不受每日硬截止约束，但只能使用已经Certified的历史Snapshot。

## 9. 20:30 修订检查

晚到数据与已认证快照不一致时：

```text
certified snapshot v1
  → difference report
  → corrected partitions
  → correction snapshot v2
```

- v1保持不变；
- v2记录`revision_kind=CORRECTION`和`supersedes_id=v1`；
- 已生成Prediction、Run和报告不自动改写；
- 平台可以安排重算，但新结果必须使用新ID；
- 重大差异触发告警和Provider质量扣分。

## 10. 当前服务器资源策略

```yaml
ingestion_runtime:
  timezone: Asia/Shanghai
  preflight_time: "15:50"
  start_time: "16:00"
  provisional_target: "16:30"
  supplemental_source_time: "16:40"
  core_certified_target: "17:10"
  review_certified_target: "17:30"
  hard_deadline: "19:00"
  correction_audit_time: "20:30"
  max_concurrent_provider_jobs: 2
  max_primary_attempts: 2
  retry_interval_minutes: 5
```

执行优先级：

```text
数据认证
  > Paper Portfolio结算
  > 正式策略预测
  > DSA收盘复盘
  > Hikyuu历史回测
  > 参数优化和深度AI研究
```

16:00至核心认证完成前暂停重型Hikyuu历史回测和参数搜索，避免四核CPU、内存和磁盘争用。

## 11. 可观测性与SLA指标

每天记录：

```text
preflight_status
primary_started_at / primary_completed_at
fallback_triggered / fallback_reason
provisional_published_at
capability_certified_at
hard_deadline_missed
coverage_ratio / excluded_count
cross_source_mismatch_count
provider_attempt_count
correction_snapshot_count
```

首月只统计SLA，不因偶发延迟自动调整时间。积累至少20个交易日后，再决定是否移动16:00起始时间或认证截止时间。

## 12. 验收标准

1. 16:00前不会把当日数据发布为正式盘后快照；
2. Preflight失败不会创建空Snapshot；
3. Provisional不能进入正式策略、回测和Paper接口；
4. Financial-API补充产生独立ProviderRun、分区版本和血缘；
5. 能力认证缺失只影响依赖它的消费者；
6. 19:00未认证时不使用旧信号或临时数据冒充；
7. 少量证券排除进入RunBundle和结果诊断；
8. 已持仓证券缺数时对应Paper组合不会继续调仓；
9. Correction生成新Snapshot，不覆盖旧预测和回测；
10. 当前服务器同时最多执行两个Provider任务，核心认证期间暂停重型研究任务。

## 13. 已收敛的下游契约

市场情绪和资金行为的计算输入、能力认证、17:30目标发布及失败语义已在[A 股市场情绪与资金行为架构 v1](market-sentiment-and-capital-flow-architecture.md)中确定。Feature Store三级物化、缓存保留、依赖DAG、PIT时间门禁和历史回填物理模型已在[A 股 Feature Store 与指标注册中心架构 v1](feature-store-architecture.md)中确定。

DSA在17:50后只消费已经发布的Feature/Observation Snapshot并构建不可变收盘FactPack，不在复盘生成阶段直接补抓权威行情或板块数据，详细契约见[DSA A 股收盘复盘 FactPack 架构 v1](dsa-close-review-fact-pack.md)。

历史回填固定从2018-01-01开始分批执行，任务顺序、资源门禁和阶段Exit Gate见[实施路线与验收方案 v1](implementation-roadmap-and-acceptance-v1.md)。

## 14. 参考资料

- [a-stock-data：盘后数据更新时间、数据源优先级和降级策略](https://github.com/simonlin1212/a-stock-data)
- [Financial-API：全市场日K与复权事件数据导出](https://github.com/HiThink-Tech/Financial-API/blob/main/docs/api/capability-map.md)
- [Financial-API marketdb：全量/增量同步与数据校验](https://github.com/HiThink-Tech/Financial-API/blob/main/python/toolkit/marketdb/README.md)
- [A 股数据平台与 Canonical Data Contract v1](data-platform-and-canonical-contract.md)
- [Fleur-Lite 回测运行与结果一致性架构](fleur-lite-backtest-runtime.md)
- [A 股市场情绪与资金行为架构 v1](market-sentiment-and-capital-flow-architecture.md)
