# Visory 指标、预测与 Hikyuu 回测架构

状态：Design Approved（待实现）
最后更新：2026-08-28

## 1. 文档目的

本文固化Visory的指标、因子验证、策略回测、结果落地与追溯设计。核心决策是：

- Hikyuu 是唯一正式策略回测和组合模拟内核；
- Fleur 只提供策略表达、数据治理、异步任务和 T+1 设计参考；
- 平台自建 Indicator Registry、Feature Store、Snapshot 和 Lineage；
- 日线策略默认遵循 T 日预测、T+1 执行、T+H 验证；
- Prediction、Execution、Validation 是三个不可混淆的数据面；
- 因子、个股仓位、策略资金和风险敞口权重分层管理，动态权重只允许 point-in-time 计算；
- v1 采用沪深主板/创业板/科创板日线现货多头和保守 T+1 开盘撮合；
- 所有运行结果必须能追溯到策略、公式、指标快照、数据快照及原始数据 Hash。

本文描述目标架构，不表示当前代码已经具备下述全部能力。

## 2. 当前实现与目标架构边界

当前仓库已有：

- `src/core/backtest_engine.py`：面向历史分析记录的 long-only 日线前向评价；
- `src/services/backtest_service.py`：历史分析候选、日线窗口和结果编排；
- `backtest_results` / `backtest_summaries`：分析建议的简单收益和方向统计；
- `decision_signal_outcomes`：DecisionSignal 的多周期后验结果；
- Skill opinion outcome：策略观点样本的前向评估。

这些能力属于**分析/信号后验评价**，不等于具备订单、成交、持仓、组合资金和 A 股交易约束的正式策略回测。目标架构保留它们的兼容读取和历史结果，不静默改写旧数据；新增的 Hikyuu 运行域使用独立的策略回测模型。

目标语义命名：

| 名称 | 含义 | 引擎 |
| --- | --- | --- |
| Analysis Outcome Evaluation | 历史分析建议/DecisionSignal 是否命中的后验评价 | 现有 evaluator |
| Factor Evaluation | 单指标或组合因子的预测能力、稳定性与衰减 | Feature/Factor Service + Hikyuu 指标能力 |
| Strategy Backtest | 含信号、仓位、成交、费用和持仓的策略回测 | Hikyuu |
| Paper Portfolio | T+1 模拟组合的持续运行与结算 | Hikyuu Adapter + Portfolio Worker |

禁止将旧的 `backtest_results` 直接解释成新的组合回测业绩。

## 3. 逻辑架构

```text
a-stock-data / Financial-API
             │
             ▼
       Canonical Data
             │
       Data Snapshot
             │
             ├──────────────┐
             ▼              ▼
    Indicator Compute   Market/Sector Compute
             │              │
             └──────┬───────┘
                    ▼
              Feature Store
                    │
              Feature Snapshot
                    │
          ┌─────────┴─────────┐
          ▼                   ▼
    Factor Evaluation    Strategy Compiler
                              │
                     StrategySpec → Hikyuu
                              │
                        Hikyuu Worker
                              │
         Prediction → Order → Execution → Position/NAV
                              │
                        T+H Validation
                              │
                     Metrics + Diagnostics
```

## 4. 指标范围

### 4.1 个股行情和技术指标

- 收益与价格：1/5/10/20/60 日收益、振幅、跳空、新高新低距离；
- 趋势：MA、EMA、MACD、DMI/ADX、BOLL、SAR、Slope、RSRS；
- 动量：RSI、KDJ、ROC、MTM、CCI、WR、相对强度；
- 波动：TR、ATR、历史波动率、下行波动率、滚动回撤；
- 量价：量比、换手、OBV、AD、MFI、VWAP 偏离、量价背离；
- 形态：突破、交叉、缺口、连阳/连阴、放量/缩量、涨跌停状态。

### 4.2 横截面因子

- 全市场/行业分位数和 ZScore；
- 行业中性或市值中性排名；
- 相对强度、质量、成长、估值、波动和流动性因子；
- 因子 IC、RankIC、ICIR、分组收益、衰减和换手。

### 4.3 市场和板块指标

- 上涨/下跌/平盘家数；
- 新高/新低和位于 MA20/MA60 之上的股票比例；
- 涨停、跌停、炸板、连板高度和晋级率；
- 全市场成交、风格强弱和情绪阶段；
- 板块收益、相对强度、宽度、成交、资金行为、涨停数量、龙头和持续性；

全球指数、汇率、商品、利率和海外事件仅用于页面与DSA复盘背景，不属于A股正式策略指标，不能进入Hikyuu、Paper Portfolio或Formal回测。详细边界见[全球市场观察与 A 股策略隔离架构 v1](global-market-observation-boundary.md)。

### 4.4 财务、资金和事件指标

- 营收、利润、现金流、ROE、毛利率、负债率、盈利质量；
- PE/PB/PS、股息率和历史估值分位；
- 龙虎榜、融资融券、大宗交易、大单、ETF/板块资金等资金行为证据；
- 新闻/公告重要性、题材关联度、事件新颖度、情绪、置信度和数据缺口。

资金类数据只能表述为公开数据支持的“资金行为证据”，不得推断为可确认的真实账户资金来源。

市场情绪五维分、资金证据等级、订单规模/杠杆/公开席位/互联互通口径、板块资金和T+1接入规则见[A 股市场情绪与资金行为架构 v1](market-sentiment-and-capital-flow-architecture.md)。

## 5. 指标注册与公式权威

### 5.1 IndicatorDefinition

每个可用于页面、策略或回测的指标必须先注册：

```yaml
indicator_id: stock.rsi
definition_version: 1.0.0
domain: stock
frequency: 1d
engine: hikyuu
inputs: [daily_bar.close]
parameters: {n: 14}
lookback: 14
warmup: 30
outputs:
  - {name: rsi14, type: float64}
materialization: always
point_in_time: true
```

最少字段：

| 字段 | 说明 |
| --- | --- |
| `indicator_id` / `version` | 稳定标识和语义版本 |
| `domain` / `frequency` | stock/sector/market/global/event；1d/1m/event 等 |
| `engine` | hikyuu/platform/external/model |
| `inputs` | 上游数据集或指标 |
| `parameters` | 参数及默认值 |
| `lookback` / `warmup` | 增量重算和有效值边界 |
| `formula_hash` | 公式或实现指纹 |
| `output_schema` | 单值或多结果集定义 |
| `materialization` | always/cache/on_demand |
| `point_in_time` | 是否通过时点可用性审查 |

公式修改必须提升指标版本或形成新的 `formula_hash`；旧回测继续绑定旧版本。

### 5.2 公式权威归属

| 指标类型 | 权威计算方 |
| --- | --- |
| MA、MACD、RSI、KDJ、ATR、RSRS 等技术指标 | Hikyuu |
| 市场宽度、情绪和市场阶段 | Platform Market Engine |
| 板块强度、宽度和资金行为 | Platform Sector Engine（迁移 Vibe 逻辑） |
| 财务、估值 | Platform Feature Engine |
| 新闻、公告、题材 | Platform Event Engine |
| 策略交易信号和组合绩效 | Hikyuu Adapter |
| AI 观点和置信度 | Research Engine，单独存储，不覆盖事实指标 |

同一指标不得由前端、Vibe、DSA 和 Hikyuu各自计算后并存为同一名字。

### 5.3 物化策略

“所有已定义且投入使用的指标都可落地”不等于预计算所有参数组合。

| 策略 | 适用范围 | 示例 |
| --- | --- | --- |
| `always` | 高频公共、计算昂贵或审计必需 | MA5/20/60、RSI14、市场宽度、板块强度 |
| `cache` | 策略专用或自定义参数 | RSRS 特殊窗口、Sequoia 专用评分 |
| `on_demand` | 一次性研究和大规模参数搜索中间值 | MA37、未入选的优化参数 |

日频核心指标优先使用宽表/宽 Parquet；扩展指标使用长表或独立指标组。分钟级指标只物化明确使用的集合，禁止无边界地展开全部指标和参数。

## 6. Feature Store 设计

Provider主备、Canonical股票身份、Raw/Normalized分层、DataSnapshot、质量门禁和Hikyuu缓存构建规则见[A 股数据平台与 Canonical Data Contract v1](data-platform-and-canonical-contract.md)。核心源固定为a-stock-data，Financial-API作为补充和受控灾备；Hikyuu只能读取Certified DataSnapshot，不能直接访问外部Provider。

### 6.1 物理分层

```text
Raw → Normalized → Features → Marts → Snapshots
```

- Raw：第三方原始响应、请求参数、抓取时间、HTTP 状态和内容 Hash；
- Normalized：统一代码、时区、单位、复权、交易日和字段语义；
- Features：指标、因子和事件特征；
- Marts：市场、板块、个股研究和策略可直接消费的事实表；
- Snapshots：不可变输入清单、版本、分区和质量报告。

### 6.2 目标表族

| 表族 | 主要键 | 内容 |
| --- | --- | --- |
| `feature_stock_daily_core` | symbol + trade_date + snapshot | 常用宽表技术指标 |
| `feature_value` | entity + time + indicator/version | 扩展/自定义指标长表 |
| `market_snapshot_daily` | market + trade_date + snapshot | 市场宽度和情绪 |
| `sector_snapshot_daily` | sector + trade_date + snapshot | 板块强度、宽度和资金行为 |
| `global_market_snapshot` | asset + event_time + available_at | 全球市场观察事实，仅供页面和复盘，不进入正式策略 |
| `fundamental_feature` | symbol + report_period + available_at | 财务和估值特征 |
| `event_feature` | event_id + entity + available_at | 新闻、公告和题材特征 |
| `strategy_signal` | strategy/version + symbol + signal_date | 预测与目标仓位 |

指标值最少携带 `indicator_id`、`indicator_version`、`trade_time`、`available_at`、`data_snapshot_id`、`formula_hash` 和 `computed_at`。

### 6.3 存储选择

- Parquet + DuckDB：大量行情、指标、快照、回测明细；
- PostgreSQL：注册表、任务、策略、预测、订单索引、运行元数据和报告索引；
- Hikyuu HDF5/内存 Stock：由指定 DataSnapshot 生成的可重建缓存，不是真源；
- 暂不引入 ClickHouse；数据量或并发达到明确门槛后另立决策。

## 7. Hikyuu Adapter

### 7.1 输入

Hikyuu 不运行自己的权威采集链路。Adapter 从指定快照读取 Canonical Data：

```text
DataSnapshot
  ├── instruments
  ├── trading_calendar
  ├── bars
  ├── adjust_factors
  ├── trading_status
  ├── sector_membership(point-in-time)
  └── external_features
```

日线可写入可重建 HDF5，也可在小样本研究中通过 DataFrame 注入临时 Stock。市场、板块、财务和事件等外部特征按日期对齐后转成 Hikyuu Indicator，供 Environment、Condition、Signal 或 Selector 使用。

### 7.2 StrategySpec 到 Hikyuu

```text
StrategySpec.universe        → Block / StockList
StrategySpec.environment     → Environment
StrategySpec.conditions      → Condition
StrategySpec.entry/exit      → Signal
StrategySpec.stop            → Stoploss / Stopprofit
StrategySpec.position_sizing → MoneyManager
StrategySpec.slippage        → Slippage
StrategySpec.cost_model      → TradeCost
StrategySpec.selection       → Selector / MultiFactor
StrategySpec.allocation      → AllocateFunds
StrategySpec.portfolio       → Portfolio
```

Sequoia-X 和 Fleur 参考策略先转换成平台 `StrategySpec`，再由 Compiler 生成 Hikyuu 组件；禁止分别维护“页面选股公式”和“回测公式”。

`StrategySpec` 只管理股票池、特征、筛选、评分、入场、退出和调仓语义；MarketRuleProfile、WeightPolicySpec、PortfolioSpec 和 BacktestRunSpec 独立版本化。声明式策略使用安全 AST，复杂状态策略走受控插件，详细契约见[StrategySpec v1 策略契约](strategy-spec-v1.md)。

### 7.3 输出

Adapter 必须把 Hikyuu 原生结果归一为平台模型：

- Prediction / StrategySignal；
- OrderIntent；
- ExecutionResult；
- PositionSnapshot；
- PortfolioNav；
- Trade；
- BacktestMetric；
- BacktestDiagnostic。

不得只保存一个收益率或净值截图。

### 7.4 自动权重边界

评分和自动权重由平台 Weight Optimization Worker 编排，Hikyuu 提供 `MF_Weight`、`MF_ICWeight`、`MF_ICIRWeight`、Selector、AllocateFunds、MoneyManager、Portfolio 和 WalkForward 等执行基础。平台负责全区间研究上界、回测滚动寻优、AI 有界调仓、均值方差、叠加顺序及不可前视门禁。

正式回测只能消费决策时点已经冻结的 `WeightSnapshot`。全区间最优和使用同一区间最终回测结果反推的权重只能作为研究结果，不能进入 Paper Portfolio 或标记为样本外业绩。详细设计见[评分、仓位与自动权重优化架构](weight-optimization-architecture.md)。

## 8. 因子评价

因子评价不模拟完整交易，先回答“指标是否具备稳定预测能力”：

- IC / RankIC / ICIR；
- 五分组/十分组收益和单调性；
- TopN、Long-Short 和基准超额收益；
- 1D/3D/5D/10D/20D 衰减；
- 覆盖率、缺失率和异常值率；
- 换手率和潜在交易成本；
- 行业/市值中性前后对比；
- 牛市、熊市、震荡期稳定性；
- 不同市值、流动性和板块样本稳定性。

推荐可交易标签以 `T+1 open` 为起点：

```text
ret_1d  = close(T+1)  / open(T+1) - 1
ret_5d  = close(T+5)  / open(T+1) - 1
ret_20d = close(T+20) / open(T+1) - 1
```

研究用途的 close-to-close 标签可以并存，但必须使用不同 `label_id/version`，不得与可交易收益混为一谈。

## 9. T/T+1/T+H 时序

### 9.1 收盘日线策略

```text
T 日收盘
  → 等待权威数据稳定
  → 冻结 DataSnapshot(T)
  → 计算并冻结 FeatureSnapshot(T)
  → 生成 Prediction(T)
  → 创建 T+1 OrderIntent
  → 下一个交易日 T+1 尝试成交
  → 更新 Execution/Position/NAV
  → T+1/T+3/T+5/T+20 形成 Validation
```

`T+1` 是下一个交易日，不是自然日。预测日、执行日和验证结束日必须显式保存。

### 9.2 盘中策略

盘中策略只能读取 `available_at <= decision_at` 的数据。若 10:30 产生信号，允许按策略定义在 10:31 或之后执行；禁止读取完整当日 K 线、真实系统未来时间或尚未发布的外部市场数据。

### 9.3 无法成交

预测存在但因一字涨停、停牌、跌停、流动性、资金或风控无法成交时：

- Prediction 保留；
- ExecutionResult 记录 `rejected` 和稳定原因码；
- 预测方向仍可生成 Validation；
- 策略组合收益不得假设成交成功。

建议原因码：`SUSPENDED`、`LIMIT_UP`、`LIMIT_DOWN`、`INSUFFICIENT_CASH`、`INSUFFICIENT_LIQUIDITY`、`T1_RESTRICTION`、`MISSING_DATA`、`RISK_REJECTED`。

### 9.4 v1 市场规则

第一版正式范围已固定为沪深主板、创业板和科创板日线现货多头。历史股票池必须保留退市证券并按当日状态生成；上市前 20 个交易日和 ST/*ST 禁止新买。指标使用 point-in-time 复权序列，成交使用真实未复权价格，公司行动单独进入组合账本。

T+1 开盘先卖后买，开盘涨停不买、开盘跌停不卖；订单当日有效，容量按 T 日及以前 20 个有效交易日平均成交金额的 5% 限制。默认佣金万 3、单订单最低 5 元、买卖基础滑点各 5 bp，法定税费按成交日期选择版本；主资金 100 万元，并运行 1000 万元容量对照。完整规则和失败语义见[A 股回测市场规则 v1](backtest-market-rules-v1.md)。

## 10. 预测、执行与验证模型

### 10.1 Prediction

```text
prediction_id
run_id
strategy_id / strategy_version
symbol
signal_date / generated_at / available_at
horizon
direction / score / rank / target_weight
reason_codes
data_snapshot_id / feature_snapshot_id
formula_hash
```

Prediction 是策略在当时事实条件下的不可变输出。更正输入后生成新 Prediction，不覆盖旧记录。

### 10.2 OrderIntent 与 ExecutionResult

OrderIntent 保存计划执行日、方向、目标数量/权重和价格政策。ExecutionResult 保存请求价、成交价、数量、费用、滑点、状态和拒绝原因。

### 10.3 ValidationResult

```text
validation_id
prediction_id
label_id / label_version
horizon
start_date / end_date
start_price / end_price
realized_return / benchmark_return / excess_return
direction_hit
max_favorable_excursion / max_adverse_excursion
validation_snapshot_id
validated_at
```

同一 Prediction 可以拥有多个 horizon 的 Validation。Validation 是预测能力评估；Execution/Trade 是可交易结果，两者必须分别汇总。

## 11. BacktestRun 与复现清单

正式回测采用 Fleur-Lite 五阶段异步运行模式，并将 `PREVIEW`、`RESEARCH` 和 `FORMAL` 三种结果严格分级。只有 Hikyuu 生成的 `FORMAL` 结果可以作为正式组合业绩；任务租约、Attempt、原子产物发布、结果一致性和当前服务器资源预算见[Fleur-Lite 回测运行与结果一致性架构](fleur-lite-backtest-runtime.md)。

每次运行保存不可变 Manifest：

```text
run_id
engine_name=hikyuu
engine_version
strategy_id / strategy_version / strategy_hash
data_snapshot_id
feature_snapshot_id
universe_hash
calendar_version
cost_model_version
execution_model_version
weight_policy_version / weight_policy_hash
weight_mode / leakage_class
optimization_run_id
ai_overlay_policy_version / ai_decision_snapshot_hash
market_rule_policy_id / policy_version / definition_hash
instrument_state_snapshot_id
corporate_action_snapshot_id
price_limit_rule_set_version / lot_rule_set_version
fee_profile_version / slippage_profile_version
liquidity_policy_version
primary_benchmark_id / benchmark_snapshot_id
code_commit
dependency_lock_hash
parameters
random_seed
started_at / completed_at
result_hash
```

同一 Manifest 重复执行必须得到相同 `result_hash`；不能复现时，运行状态不得标记为 reproducible。

## 12. 全链路追溯

预测验证链：

```text
ValidationResult
  → Prediction
  → StrategyVersion
  → FeatureSnapshot
  → IndicatorDefinition + FormulaHash
  → DataSnapshot
  → RawObject + Provider + ContentHash
```

交易链：

```text
Trade
  → ExecutionResult
  → OrderIntent
  → Prediction
  → StrategyVersion
  → FeatureSnapshot
  → DataSnapshot
```

任何页面展示的回测指标都必须能回答：使用了哪份数据、何时可用、公式和策略版本、为何选中、是否成交、为何拒绝、验证采用哪个价格窗口以及数据是否后来被修正。

## 13. 数据修正与版本

历史数据修正不覆盖旧快照：

```text
DataSnapshot v1 → BacktestRun v1
DataSnapshot v2 → BacktestRun v2
```

平台可以生成差异报告，但不得把 v2 结果写回 v1。策略、指标、标签、费用、日历和执行模型规则变化同样必须提升版本。

## 14. 持久化目录

所有持久化数据继续位于 `/data/daily_stock_analysis`：

```text
/data/daily_stock_analysis/
├── config/
│   ├── app/
│   ├── platform/
│   │   ├── providers/
│   │   ├── hikyuu/
│   │   ├── strategies/
│   │   └── indicators/
│   ├── npm/
│   └── postgres/
├── storage/app/
│   ├── raw/
│   ├── normalized/
│   ├── features/
│   ├── observations/
│   ├── factpacks/
│   ├── results/
│   ├── artifacts/
│   ├── hikyuu/
│   ├── state/
│   ├── quarantine/
│   └── .staging/
├── storage/postgres/
├── logs/
└── backups/
```

单次回测建议落地：

```text
storage/app/results/type=backtest/run_id=<run_id>/attempt_id=<attempt_id>/
├── manifest.json
├── predictions.parquet
├── orders.parquet
├── executions.parquet
├── positions.parquet
├── trades.parquet
├── nav.parquet
├── validations.parquet
├── metrics.json
└── diagnostics.json
```

PostgreSQL保存运行索引和可查询元数据，大量时序明细保存为 Parquet。

## 15. 任务状态与幂等

正式状态：

```text
queued → validating_snapshot → compiling_signals → materializing_data
       → running_hikyuu → validating_result → persisting → succeeded
       ↘ failed / cancelled / consistency_failed
```

幂等键至少包含：

```text
strategy_version
data_snapshot_id
feature_snapshot_id
date_range
universe_hash
cost_model_version
execution_model_version
parameter_hash
```

相同幂等键默认返回既有成功运行；`force` 也必须创建新的 Attempt，不能覆盖原结果。初期使用 PostgreSQL 持久任务表和单 Hikyuu Worker，不引入 NATS；完整 Run/Attempt/Task 契约见[Fleur-Lite 回测运行与结果一致性架构](fleur-lite-backtest-runtime.md)。

## 16. 质量门禁

实现前必须建立以下验收：

1. 同一策略、同一快照和同一依赖版本重复运行，结果 Hash 一致；
2. T 日预测无法读取 T+1 及之后的事实；
3. 收盘策略默认只在 T+1 或之后成交；
4. 停牌、涨跌停、T+1、费用和滑点有确定性测试；
5. 预测正确但未成交时，预测命中与组合收益严格分离；
6. 每个 Prediction 可追溯到 Feature/Data Snapshot 和原始 Hash；
7. 每个交易可追溯到 OrderIntent 和 Prediction；
8. 每个 Prediction 支持至少 1D/5D/20D 验证；
9. 数据修正创建新快照和新运行，不覆盖旧结果；
10. Hikyuu 输出完整归一到预测、订单、成交、持仓、净值、绩效和诊断模型；
11. 前复权/后复权/不复权、权息和财报披露时间口径有对照测试；
12. ARM64 环境完成 Hikyuu 编译、最小回测和批量性能 PoC 后才进入正式实现；
13. 全区间最优和同区间结果反推权重无法发布到模拟或实盘；
14. 每个动态权重可追溯到训练窗口、输入快照、调节分量、约束投影和实际仓位；
15. 历史股票池包含后来退市证券，当前证券状态不能覆盖历史状态；
16. T+1、开盘涨跌停、ST、新股冷却、整手、容量和部分成交有确定性测试；
17. 复权指标、真实成交、公司行动和日期版本化税费可以逐笔复算。
18. Preview/Research/Formal 在 API 和页面明确分级，只有 Formal 可以进入 Paper 发布检查；
19. 同范围 Preview 与正式编译的候选、评分、TopN 和信号 Hash 一致；
20. 动态列投影与全列基线的 Hikyuu 正式结果一致；
21. Worker 重试生成新 Attempt，旧结果不被覆盖且部分产物不可发布。

## 17. 分阶段实施

### Phase 0：可行性

- ARM64 编译 Hikyuu；
- 用 10 只股票、3 年日线完成最小回测；
- 验证 DataFrame/HDF5 输入、外部指标和结果导出；
- 固化 Hikyuu、Python 和依赖版本。

### Phase 1：数据与指标

- 完成 Canonical Bar、Calendar、Status、Adjustment；
- 完成历史证券状态、每日价格限制和 CorporateAction Ledger；
- 建立 MarketRuleProfile、LotRule、FeeProfile 和 point-in-time 股票池；
- 建立 Indicator Registry、Feature Snapshot 和物化任务；
- 先落地 MA、MACD、RSI、ATR、收益、波动等核心指标；
- 建立公式一致性对照测试。

### Phase 2：策略与回测

- 定义 StrategySpec；
- 迁移 2～3 个 Sequoia 策略；
- 实现 Hikyuu Compiler、Worker 和结果 Adapter；
- 完成 T+1、费用、停牌和涨跌停验证。

### Phase 3：因子与组合

- 完成 IC/RankIC/分组收益/衰减；
- 完成 TopN、四层权重、风险和组合回测；
- 分阶段接入滚动 IC/ICIR、回测滚动寻优、均值方差和 AI 有界调仓；
- 建立模拟组合和每日结算。

### Phase 4：平台集成

- 接入 Web 回测中心、运行状态和诊断；
- 接入 Vibe 市场/板块指标；
- 为 DSA、UZI 和 TradingAgents 提供只读 FactPack；
- 保留现有 Analysis Outcome 的兼容展示并明确标识引擎类型。

## 18. 已收敛的实现基线与延后项

1. Formal Hikyuu使用由固定DataSnapshot构建的HDF5缓存；内存DataFrame只用于单元测试、小型Preview或缓存构建校验，不成为第二正式输入；
2. MVP正式历史从2018-01-01开始，费用和市场规则按有效日期版本化；更早区间在规则表和数据完整前不提供Formal标签；
3. 分红送转、除权和基础退市生命周期属于MVP门禁；配股、复杂退市结算等数据不完整时隔离受影响证券/日期，不能估算后继续Formal；
4. 行业/概念成员来自版本化Provider Policy；无法证明历史有效期的概念成员只供当前观察，不进入历史策略；
5. PostgreSQL按M0—M2的Expand、Backfill、Verify、Cutover迁移，现有SQLite经Legacy Adapter保留到对应读写切换；
6. MVP不引入ClickHouse或消息队列。只有分区/增量/预聚合优化后仍连续20个交易日违反SLA或容量预算，并有Benchmark证明瓶颈时才立项；
7. 北交所、分钟线、ETF、可转债和其他资产均在MVP后按独立Market/Data/Rule Capability接入；
8. 受控策略插件在无网络、只读输入的独立子进程运行，使用ResourceBudget限制CPU、内存、时间和输出，插件失败不能污染主Worker。

具体Work Package和Exit Gate见[实施路线与验收方案 v1](implementation-roadmap-and-acceptance-v1.md)。

## 19. 参考资料

- [Hikyuu 项目与交易系统组件](https://github.com/fasiondog/hikyuu/blob/master/readme.md)
- [Hikyuu 技术指标总览](https://hikyuu.readthedocs.io/zh-cn/latest/indicator/overview.html)
- [Hikyuu 因子管理与持久化边界](https://hikyuu.readthedocs.io/zh-cn/latest/factor.html)
- [Hikyuu DataFrame 与外部指标转换](https://hikyuu.readthedocs.io/zh-cn/latest/others.html)
- [Hikyuu 事件驱动回测的未来数据约束](https://hikyuu.readthedocs.io/zh-cn/latest/vip/backtest.html)
- [Hikyuu 多因子合成与滚动 IC/ICIR 权重](https://hikyuu.readthedocs.io/zh-cn/latest/trade_portfolio/multifactor.html)
- [Hikyuu 资产分配算法](https://hikyuu.readthedocs.io/zh-cn/latest/trade_portfolio/allocate_funds.html)
- [Hikyuu 滚动交易系统](https://hikyuu.readthedocs.io/zh-cn/latest/trade_sys/walkforward.html)
- [Fleur 数据治理架构](https://github.com/WackyGem/Fleur/blob/main/docs/architecture/data-governance.md)
- [Fleur Rearview 回测与组合运行架构](https://github.com/WackyGem/Fleur/blob/main/docs/architecture/rearview.md)
- [Fleur-Lite 回测运行与结果一致性架构](fleur-lite-backtest-runtime.md)
- [A 股数据平台与 Canonical Data Contract v1](data-platform-and-canonical-contract.md)
- [A 股回测市场规则 v1](backtest-market-rules-v1.md)
- [StrategySpec v1 策略契约](strategy-spec-v1.md)
- [评分、仓位与自动权重优化架构](weight-optimization-architecture.md)
- [A 股市场情绪与资金行为架构 v1](market-sentiment-and-capital-flow-architecture.md)
- [全球市场观察与 A 股策略隔离架构 v1](global-market-observation-boundary.md)
- [A 股 Feature Store 与指标注册中心架构 v1](feature-store-architecture.md)
- [当前 DecisionSignal 与后验评估契约](https://github.com/ZhuLinsen/daily_stock_analysis/blob/96bc532dfcb21e3a7d0fdbdfa87d764b9b61d2ee/docs/decision-signals.md)
- [当前多策略契约](https://github.com/ZhuLinsen/daily_stock_analysis/blob/96bc532dfcb21e3a7d0fdbdfa87d764b9b61d2ee/docs/multi-strategy-contract.md)
