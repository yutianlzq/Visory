# Visory A 股市场情绪与资金行为架构 v1

状态：已确认（Design Approved）

最后更新：2026-08-28

## 1. 决策摘要

本模块落实架构决策 D-025，为大盘复盘、板块观察、策略环境过滤、动态仓位和 AI 日报提供统一的市场状态事实。

第一版固定以下原则：

- 市场情绪由市场宽度、涨跌停生态、风险偏好、流动性、波动与风险五个可解释维度组成；
- 资金行为由订单规模资金、杠杆资金、公开席位、大宗交易、板块资金和互联互通活跃度等证据组成，不建立无法验证的“真实主力账户”字段；
- 页面解释分与策略信号分离：页面使用固定、可审计权重，策略可以基于原始指标滚动优化，但不得改写页面历史口径；
- 每项指标必须绑定唯一 `metric_id`、公式版本、实际数据源、DataSnapshot、FeatureSnapshot、`available_at` 和质量状态；
- `a-stock-data` 是核心源，Financial-API 是补充和受控灾备；同一资金口径不得在没有版本记录的情况下跨源拼接；
- T 日盘后指标只可用于 T+1 及之后的策略决策；缺失是 `unknown`，不是零；
- 市场总览可以按能力降级，依赖缺失指标的正式策略必须阻断；
- Vibe-Research 只作为页面布局和交互参考，指标公式、历史口径和快照由平台统一管理。

本文描述目标架构，不表示当前代码已经具备相应实现。

## 2. 模块边界

### 2.1 本模块负责

- 构建 point-in-time A 股统计股票池；
- 计算大盘宽度、涨跌停、风险偏好、流动性和风险指标；
- 计算固定口径的市场情绪分和市场状态；
- 保存订单规模、融资融券、龙虎榜、大宗交易、板块资金和互联互通等资金证据；
- 计算资金方向、资金活跃度、板块资金强度及其可信度；
- 生成可供页面、DSA FactPack、Hikyuu 和策略中心消费的不可变快照；
- 提供指标贡献、来源、公式、质量、历史修订和运行诊断。

### 2.2 本模块不负责

- 识别未公开的真实机构、游资或个人账户身份；
- 把成交额、ETF成交额或北向成交总额直接解释为净流入；
- 根据 AI 文本判断覆盖或修改数值事实；
- 生成具体股票买卖建议；
- 在前端、DSA Prompt 或策略插件内重新计算同名指标；
- 建立盘中分钟级资金监控。分钟级能力待日频口径稳定后另立决策。

### 2.3 术语约束

平台统一使用以下名称：

| 名称 | 含义 | 禁止误写为 |
| --- | --- | --- |
| 订单规模资金 | Provider按成交单规模划分的超大单/大单等结果 | 已确认机构资金 |
| 公开席位资金 | 龙虎榜公开席位的买卖证据 | 全市场机构净流入 |
| 互联互通活跃度 | 官方可获得的成交总额、活跃证券和持仓披露 | 实时北向净买入 |
| 资金行为压力 | 多个有方向证据的标准化结果 | 真实资金来源 |
| 资金活跃度 | 资金证据的强度，不代表方向 | 净流入 |

## 3. 逻辑架构

```text
Certified DataSnapshot
  ├── Security/Calendar/Bar/Status
  ├── Limit Pool/Ladder/Break
  ├── Order-size Flow/Sector Flow
  ├── Margin/LHB/Block Trade
  └── Stock Connect Disclosure
                 │
                 ▼
       Point-in-time Universe Builder
                 │
      ┌──────────┴───────────┐
      ▼                      ▼
Market Sentiment Engine   Capital Evidence Engine
  ├── Breadth              ├── Transaction-size
  ├── Limit Ecology        ├── Leverage
  ├── Risk Appetite        ├── Disclosed Seats
  ├── Liquidity            ├── Block Trade
  └── Volatility/Risk      ├── Sector Allocation
                           └── Connect Activity
      │                      │
      ▼                      ▼
Metric Normalizer       Evidence Confidence/Reconciliation
      │                      │
      └──────────┬───────────┘
                 ▼
       Score + Regime + Quality Gate
                 │
                 ▼
          FeatureSnapshot / Marts
                 │
      ┌──────────┼───────────┬───────────┐
      ▼          ▼           ▼           ▼
 Market UI   DSA FactPack  Strategy   Hikyuu Backtest
```

实现保持模块化单体：Market Feature Worker 负责批量计算，PostgreSQL 保存定义、运行和快照索引，Parquet 保存时序事实，DuckDB 完成批量聚合。第一版不拆分独立微服务，也不为这些日频聚合启动第二套行情数据库。

## 4. 统计股票池与基础口径

### 4.1 股票池

第一版 `market_scope_id=cn_a_equity_v1` 与正式回测范围一致，覆盖沪深主板、创业板和科创板日线股票。

每个交易日根据当日可用事实生成以下股票池：

| 股票池 | 定义 | 用途 |
| --- | --- | --- |
| `listed_universe` | T 日已经上市且尚未退市的股票 | 覆盖率和状态检查 |
| `bar_valid_universe` | 有有效Bar或显式停牌状态 | 数据质量分母 |
| `tradable_observation_universe` | 有有效前收、当日Bar且不是停牌 | 涨跌家数和收益统计 |
| `limit_rule_universe` | 当日适用明确涨跌停规则 | 涨跌停生态 |
| `strategy_eligible_universe` | 满足正式策略市场规则的股票 | 策略和回测，不等同大盘统计池 |

ST、`*ST` 和上市未满20个交易日的股票可以进入全市场观察，但必须单独标记；它们是否进入某个指标由 MetricDefinition 固定。策略股票池继续遵循回测市场规则，不能借用更宽的情绪统计池直接交易。

### 4.2 停牌、首日与缺数

- 停牌证券计入 `listed_universe` 和覆盖率，不进入上涨/下跌分母；
- 没有有效前收的新上市证券不进入涨跌家数和收益统计；
- 涨跌停状态使用当日真实未复权价格和版本化涨跌停规则；
- MA、新高/新低和收益使用 point-in-time 复权序列，避免除权除息制造虚假跌幅；
- 股票被质量门禁隔离后，从相应计算池排除并保存原因；页面必须展示有效样本数和覆盖率；
- 同一天不同指标允许拥有不同有效样本数，但不得隐式复用一个分母。

### 4.3 板块归属

- 市场级资金汇总只使用一套 point-in-time 行业分类，避免概念板块重叠导致重复计算；
- 行业、概念、地域板块分别保存 `taxonomy_id/version`；
- 概念板块可以用于热点展示和个股题材穿透，但不得汇总成“全市场净流入”；
- 当日板块计算使用当日有效成分，禁止用当前成分回填历史。

## 5. 指标注册与计算 DAG

市场和资金指标沿用 Indicator Registry，每个定义至少包含：

```yaml
indicator_id: market.sentiment.breadth.net_advance_ratio
definition_version: 1.0.0
domain: market
frequency: 1d
market_scope_id: cn_a_equity_v1
inputs:
  - canonical.bar_1d
  - canonical.instrument_status_daily
formula: (advance_count - decline_count) / valid_return_count
formula_hash: <sha256>
lookback: 1
warmup: 0
normalization: robust_z_252_v1
direction: positive
required_capabilities: [backtest_core, market_breadth]
point_in_time: true
materialization: always
```

计算依赖如下：

```text
DataSnapshot
  → Daily Universe
  → Stock Primitives（return/MA/high-low/turnover/limit state）
  → Market Aggregates
  → Normalized Metrics
  → Dimension Scores
  → Emotion/Capital Snapshot
  → FactPack/Strategy FeatureSnapshot
```

任何公式、股票池、分母、Provider口径、标准化方法或权重变化都必须提升版本。前端只展示后端已经发布的结果，不拥有指标公式权威。

## 6. 市场情绪指标 v1

### 6.1 市场宽度

| `metric_id` 后缀 | 公式或定义 |
| --- | --- |
| `advance_count` / `decline_count` / `flat_count` | 有效收益股票按正、负、零分类 |
| `net_advance_ratio` | `(上涨家数 - 下跌家数) / 有效收益家数` |
| `advance_decline_log` | `ln((上涨家数 + 1) / (下跌家数 + 1))` |
| `median_return` | 有效股票当日收益中位数 |
| `above_ma20_ratio` | 收盘位于MA20之上的有效股票比例 |
| `above_ma60_ratio` | 收盘位于MA60之上的有效股票比例 |
| `new_high_low_spread_20` | `(20日新高数 - 20日新低数) / 有效样本数` |

上涨/下跌阈值使用精确收益方向，不用指数涨跌替代个股宽度。页面同时展示绝对家数、比例、有效样本数和覆盖率。

### 6.2 涨跌停生态

| `metric_id` 后缀 | 公式或定义 |
| --- | --- |
| `limit_up_count` / `limit_down_count` | 按当日规则收盘涨停/跌停家数 |
| `limit_up_down_spread` | `(涨停数 - 跌停数) / limit_rule_universe数量` |
| `limit_break_count` | 日内触及涨停但收盘未封住的股票数 |
| `limit_break_rate` | `炸板数 / (收盘涨停数 + 炸板数)` |
| `max_streak_height` | 当日最高连续涨停板数 |
| `streak_stock_count` | 连续涨停天数大于等于2的股票数 |
| `promotion_rate` | T-1连板候选中，T日晋级到更高板位的数量/可观察候选数 |
| `early_seal_ratio` | 有可靠封板时间时，指定时点前首次封板且收盘封住的比例 |

`promotion_rate` 必须按 T-1 已知连板股票形成候选队列，再在 T 日验证；不能用 T 日最终连板池反向构造分母。若数据源不提供可靠封板时间，`early_seal_ratio` 为 `unknown`，不根据K线猜测。

### 6.3 风险偏好

| `metric_id` 后缀 | 公式或定义 |
| --- | --- |
| `prior_limit_up_premium` | T-1收盘涨停股票在T日的等权收益 |
| `high_turnover_return_spread` | 换手率最高20%股票收益中位数减全市场收益中位数 |
| `small_large_return_spread` | 流通市值最低30%与最高30%股票的等权收益差 |
| `top_amount20_median_return` | 当日成交额前20股票收益中位数 |
| `strong_stock_survival_ratio` | T-1收益前10%股票在T日仍跑赢全市场中位数的比例 |

流通市值缺失时不得用当前市值回填历史；`small_large_return_spread` 对应能力保持不可用。

### 6.4 流动性

| `metric_id` 后缀 | 公式或定义 |
| --- | --- |
| `market_amount_cny` | 有效股票成交额之和 |
| `amount_ratio_20` | 当日成交额/此前20个交易日平均成交额 |
| `rising_amount_share` | 上涨股票成交额/有效股票总成交额 |
| `top20_amount_concentration` | 成交额前20股票成交额/有效股票总成交额 |
| `zero_or_suspended_ratio` | 零成交或停牌股票/当日上市股票 |

成交额统一为人民币元。指数成交额、ETF成交额和股票成交额分开保存，不混入 A 股股票市场分母。

### 6.5 波动与风险

| `metric_id` 后缀 | 公式或定义 |
| --- | --- |
| `median_amplitude` | 个股 `(high-low)/prev_close` 的中位数 |
| `return_dispersion_mad` | 个股收益的中位绝对偏差 |
| `benchmark_realized_vol_20` | 基准指数20日年化实现波动率 |
| `tail_loss_ratio` | 当日收益小于等于-5%的有效股票比例 |
| `market_drawdown_20` | 基准指数相对过去20日最高收盘的回撤 |

波动与风险维度转换为情绪贡献时方向取反：风险越高，情绪安全分越低。原始风险指标始终保留原方向，不能因展示需要反写事实。

## 7. 标准化、情绪分和状态机

### 7.1 时间序列标准化

不同单位的指标先按自身历史标准化。默认 `robust_z_252_v1` 使用 T 日之前最多252个交易日、最少60个有效观察：

```text
robust_z(T) = (x(T) - median(history_before_T))
              / (1.4826 * MAD(history_before_T) + epsilon)

metric_score = clip(50 + clip(direction * robust_z, -3, 3) * 100 / 6,
                    0,
                    100)
```

- `direction=positive` 表示原值越大情绪越强；
- `direction=negative` 表示原值越大风险越高；
- 历史窗口严格截止到 T-1，禁止用全区间统计量；
- 少于60个历史观察时只展示原值和 `warming_up`，不发布正式标准化分；
- 比例型指标也保留原值，标准化分只用于跨指标合成。

### 7.2 五个维度分

维度内固定权重如下：

| 维度 | 输入及权重 |
| --- | --- |
| 市场宽度 | 净上涨率30%、MA20宽度25%、MA60宽度15%、新高新低差15%、收益中位数15% |
| 涨跌停生态 | 涨跌停差30%、反向炸板率25%、最高板20%、晋级率25% |
| 风险偏好 | 昨日涨停溢价30%、高换手收益差25%、小盘/大盘收益差20%、成交额TOP20收益25% |
| 流动性 | 成交额相对20日均值60%、上涨股成交额占比40% |
| 波动与风险 | 反向尾部下跌比例40%、反向收益离散度30%、反向基准波动率30% |

`early_seal_ratio`、成交集中度、强势股存活率和市场回撤在 v1 作为解释指标，不进入综合分。进入综合分必须提升 ScoreDefinition 版本并补历史对照。

### 7.3 页面情绪分

```text
emotion_score_raw =
    breadth_score        * 0.25
  + limit_score          * 0.30
  + risk_appetite_score  * 0.20
  + liquidity_score      * 0.15
  + safety_score         * 0.10
```

规则：

- 固定权重仅用于解释和复盘，不根据最终回测收益反推；
- 必需维度缺失时不在剩余维度间重新分配权重，总分为 `partial/unknown`；
- 页面仍可展示已经认证的维度、原始指标和缺失原因；
- 策略可直接使用原始指标或独立的 `strategy_market_regime_signal`，但不得把优化权重写回 `emotion_score_raw`。

### 7.4 平滑分与市场状态

```text
emotion_score_smoothed(T) = 0.5 * raw(T) + 0.5 * smoothed(T-1)
```

状态阈值：

| 分数 | 状态代码 | 展示名称 |
| --- | --- | --- |
| `[0, 20)` | `PANIC` | 恐慌 |
| `[20, 40)` | `WEAK` | 偏弱 |
| `[40, 60)` | `RANGE` | 震荡 |
| `[60, 80)` | `ACTIVE` | 活跃 |
| `[80, 100]` | `OVERHEATED` | 过热 |

为降低临界值频繁跳变，状态改变必须满足下列任一条件：连续两个交易日进入相邻区间，或单日越过边界至少5分。每次状态迁移保存前状态、后状态、触发指标和 ScoreDefinition 版本。

## 8. 资金证据模型

### 8.1 可信度分级

| 等级 | 定义 | 示例 | 基础系数 |
| --- | --- | --- | --- |
| A | 交易所或依法公开的直接披露 | 融资融券、龙虎榜、大宗交易、互联互通官方统计 | 1.00 |
| B | Provider按明确但非账户身份的规则派生 | 超大单/大单/主力资金流 | 0.75 |
| C | 平台从价格、成交和板块联动推断 | 价格资金背离、吸筹候选 | 0.50 |
| D | AI或文本模型观点 | AI对资金意图的解释 | 0.25 |

等级由 `source + dataset + methodology_version` 决定，而不是由字段名称决定。若 a-stock-data 的实际上游是第三方派生接口，必须保存实际上游和B级口径；Financial-API作为官方服务接入也不能把其未声明为账户级事实的派生字段自动提升为A级。

单条证据可信度：

```text
evidence_confidence =
    grade_base
  * coverage_factor
  * freshness_factor
  * reconciliation_factor
```

四个因子及最终结果均落库。低可信度不把资金值缩小成零，而是与原始值并列展示，由消费者决定是否可用。

### 8.2 订单规模资金

核心输入来自 a-stock-data 对应上游的超大单、大单、中单和小单资金流。必须保存 Provider 的规模阈值、净流入定义和方法版本。

首版指标：

```text
main_net_flow = super_large_net_flow + large_net_flow
main_flow_intensity = sum(main_net_flow) / sum(stock_amount)
main_flow_breadth = count(main_net_flow > 0) / valid_flow_count
main_flow_persistence_5d = mean(sign(market_main_net_flow), last 5 days)
```

不得把大单拆分结果命名为“机构买入”。若 Provider 只有最终“主力净流入”而没有分档字段，保留其原始指标名和方法来源，不能伪造分项。

### 8.3 杠杆资金

首版保存：

- 融资余额、融资余额日变化；
- 融资买入额、融资偿还额和融资净变化；
- 融资买入额/当日股票成交额；
- 融券余额和可用时的融券卖出变化；
- 融资余额上升股票比例和行业分布。

融资融券数据必须使用实际 `published_at/available_at`。若 T 日数据在正式决策前尚不可用，T 日快照只能携带截至决策时已知的最近一期，并显式保存 `effective_trade_date` 和 `lag_trading_days`；禁止历史回测用最终补齐的 T 日值冒充当时已知数据。

### 8.4 公开席位与大宗交易

龙虎榜保存：

- 上榜原因、买卖前五席位、机构专用席位标记；
- 机构席位买入、卖出、净买入和上榜股票数；
- 席位证据占该股票当日成交额的比例；
- 同一席位的连续出现次数及其来源规则版本。

大宗交易保存成交额、成交量、买卖营业部、相对收盘价溢折价和可用时间。

这些数据只描述触发披露条件的有限样本。平台可以计算 `disclosed_institution_activity`，但不能把样本外股票视为零机构交易，也不能外推成全市场机构净流入。

### 8.5 互联互通

首版正式指标仅使用当前披露机制能够支持的事实：

- 沪股通、深股通成交总额和笔数；
- ETF成交额；
- 前十大活跃证券成交额及集中度；
- 季度披露的个股合计持仓及季度变化；
- 互联互通成交额/A股对应市场成交额。

实时买入额、卖出额和净买入额不作为官方可得事实。第三方估算可以以独立 `metric_id`、B/C等级和 `estimated=true` 保存，但默认不进入页面综合资金分、正式策略和 Formal 回测。

### 8.6 ETF资金

ETF成交额只代表交易活跃度。只有同时获得 point-in-time 基金份额、申购赎回或可靠份额变更时，才可以计算ETF净申购代理；否则不得把ETF成交额称为ETF资金净流入。ETF资金方向不属于 v1 必需能力。

## 9. 资金输出与板块资金

### 9.1 通道分数

每个有方向的资金通道先转换为 `[-100, 100]`：

```text
channel_pressure = clip(direction * robust_z_252_v1 / 3 * 100, -100, 100)
```

每个通道同时输出原值、压力分、证据等级、可信度、有效日期、滞后天数和覆盖率。

### 9.2 市场资金压力

首版只合成口径相对稳定且可连续获得的两个通道：

```text
market_capital_pressure_v1 =
    transaction_size_pressure * 0.70
  + leverage_pressure_asof     * 0.30
```

- 订单规模资金是B级派生证据，名称不得简化为机构净流入；
- 杠杆资金使用决策时点最近可用值，并显示滞后；
- 任一必需通道缺失时不动态重分权重，综合压力标记为 `partial`；
- 龙虎榜、大宗交易和互联互通不进入方向综合分，分别作为公开证据卡片展示；
- 综合分必须与 `capital_pressure_policy_version` 一起保存。

方向解释：

| 分数 | 解释 |
| --- | --- |
| `[-100, -40)` | 明显流出压力 |
| `[-40, -15)` | 偏流出 |
| `[-15, 15]` | 中性 |
| `(15, 40]` | 偏流入 |
| `(40, 100]` | 明显流入压力 |

该解释是统计证据，不是未来涨跌结论。

### 9.3 资金活跃度

资金活跃度是无方向指标，衡量当日资金证据相对历史是否异常：

```text
capital_activity_score =
    abs(transaction_size_pressure) * 0.40
  + abs(leverage_pressure_asof)     * 0.20
  + disclosed_seat_activity        * 0.20
  + block_trade_activity           * 0.10
  + connect_activity               * 0.10
```

缺失通道不重新分配权重，状态标记为 `partial`。资金活跃度高既可能是集中买入，也可能是集中卖出，必须与资金压力方向并列展示。

### 9.4 板块资金

每个行业和概念板块分别发布：

```text
sector_main_net_flow
sector_flow_intensity = sector_main_net_flow / sector_amount
sector_flow_breadth = positive_flow_stock_count / valid_flow_stock_count
sector_flow_persistence_5d / sector_flow_persistence_10d
sector_flow_rank / sector_flow_percentile
sector_return_relative_20d
price_flow_resonance_code
```

`price_flow_resonance_code` 只使用稳定枚举：

| 枚举 | 条件 | 含义 |
| --- | --- | --- |
| `PRICE_UP_FLOW_UP` | 收益和资金压力均为正 | 量价资金同向 |
| `PRICE_UP_FLOW_DOWN` | 收益为正、资金压力为负 | 上涨但资金证据背离 |
| `PRICE_DOWN_FLOW_UP` | 收益为负、资金压力为正 | 下跌但资金证据背离 |
| `PRICE_DOWN_FLOW_DOWN` | 收益和资金压力均为负 | 同向走弱 |
| `UNKNOWN` | 任一输入不可用 | 不做推断 |

“吸筹”“出货”等意图词只能出现在AI研究观点中，并带证据引用，不能成为事实枚举。

## 10. 快照、数据模型与存储

### 10.1 能力状态

FeatureSnapshot 分别认证：

```yaml
certified_capabilities:
  market_breadth: certified
  market_limit_ecology: certified
  market_emotion: certified
  capital_transaction_size: certified
  capital_leverage: provisional
  capital_disclosed_seat: unavailable
  capital_connect_activity: certified
  sector_capital: certified
```

`market_emotion` 只有五个必需维度全部通过时才能认证。单个资金通道失败不阻断其他通道；依赖综合资金压力的策略必须满足其全部必需通道。

### 10.2 核心表族

| 表族 | 主键或唯一键 | 内容 |
| --- | --- | --- |
| `market_metric_definition` | metric_id + version | 公式、股票池、分母、标准化和方向 |
| `market_metric_value_daily` | market + date + metric/version + feature_snapshot | 原始值、样本数、覆盖率和标准化分 |
| `market_sentiment_snapshot` | market + date + score_version + feature_snapshot | 五维分、原始/平滑总分、状态和贡献 |
| `market_regime_transition` | transition_id | 状态迁移及触发证据 |
| `capital_evidence_daily` | entity + date + channel + source/version + snapshot | 资金证据、等级、可信度和血缘 |
| `market_capital_snapshot` | market + date + policy_version + snapshot | 资金压力、活跃度和通道贡献 |
| `sector_capital_snapshot` | sector + taxonomy/version + date + snapshot | 板块资金、宽度、排名和共振 |
| `market_feature_run` | run_id + attempt_id | 任务、输入、状态、错误和产物Hash |

资金证据最少保存：

```text
evidence_id
entity_type / entity_id
trade_date / effective_trade_date
observed_at / published_at / available_at / computed_at
channel / metric_id / metric_version
raw_value / unit / direction
evidence_grade / estimated
coverage_factor / freshness_factor / reconciliation_factor
confidence
provider / actual_upstream / methodology_version
provider_run_id / raw_content_hash
data_snapshot_id / feature_snapshot_id
quality_status / reason_codes
```

### 10.3 文件目录

全部文件继续位于 `/data/daily_stock_analysis`：

```text
/data/daily_stock_analysis/
├── config/platform/indicators/market/
├── storage/app/features/domain=market/frequency=1d/indicator_id=<indicator_id>/definition_version=<version>/year=YYYY/
├── storage/app/features/domain=capital/frequency=1d/indicator_id=<indicator_id>/definition_version=<version>/year=YYYY/
├── storage/app/observations/domain=market_sentiment/trade_date=YYYY-MM-DD/snapshot_id=<observation_snapshot_id>/
├── storage/app/observations/domain=market_capital/trade_date=YYYY-MM-DD/snapshot_id=<observation_snapshot_id>/
├── storage/app/observations/domain=sector_capital/trade_date=YYYY-MM-DD/snapshot_id=<observation_snapshot_id>/
├── storage/app/state/duckdb/
├── storage/app/artifacts/type=market_review/year=YYYY/month=MM/
├── storage/postgres/
└── logs/market-feature-worker/
```

Parquet 保存原始指标、资金证据和板块明细；PostgreSQL 保存 Definition、Run、Snapshot、状态迁移和查询索引。页面查询优先读取日级 Mart，不对全量股票明细现场聚合。

## 11. 盘后调度与当前服务器资源

本模块服从16:00采集和19:00正式策略硬截止：

```text
16:00        a-stock-data核心采集
16:30        Provisional DataSnapshot目标
16:40        Financial-API补充判定
17:10        CERTIFIED:backtest_core目标
17:10-17:18  股票基础派生、宽度、流动性和风险
17:18-17:25  涨跌停、风险偏好、订单规模和板块资金
17:25-17:30  标准化、评分、质量门禁和核心FeatureSnapshot发布
17:30-17:44  板块独立视图、异动和热点观察发布
17:44-18:05  依赖核心A股市场状态的正式策略信号
17:44-17:50  全球观察低优先级采集，不作为策略依赖
17:50-18:20  DSA FactPack和复盘生成
18:10-18:30  龙虎榜、融资融券、大宗交易等晚到能力补充
18:30-18:50  显式依赖晚到A股资金能力的策略信号
19:00        T日正式策略硬截止
20:30        Correction审计
```

晚到能力形成新的 FeatureSnapshot 或能力版本，不覆盖17:30快照和已经生成的策略或复盘。某策略若声明依赖晚到资金能力，只能在该能力认证后运行，19:00仍未认证则当日不生成正式预测。全球观察不属于策略依赖，失败时只删减DSA背景。

当前服务器配置采用：

```yaml
market_feature_runtime:
  worker_count: 1
  max_threads: 2
  max_concurrent_metric_groups: 1
  daily_incremental_only: true
  history_backfill_window: "00:30-06:00"
  pause_heavy_backtest_during_close_pipeline: true
```

计算优先使用DuckDB批量扫描和向量化聚合；同一份股票基础特征只计算一次并由多个市场指标复用。历史回填按月份或年份分块、可续跑，不与盘后正式流水线并发。

## 12. 失败、降级和修订

### 12.1 全局阻断

以下问题阻断相关 FeatureSnapshot：

- 股票身份、资产类型或交易日历冲突；
- 关键行情覆盖率低于 DataSnapshot 门槛；
- 使用未认证或 `available_at` 晚于决策时点的数据；
- 公式Hash、股票池版本或输入Manifest不完整；
- 检测到未来函数、全区间标准化或当前板块成分回填；
- 同一输入和版本重复计算得到不同结果；
- 综合分所需必需维度缺失却被标记为完整成功。

### 12.2 能力级降级

- 涨跌停特色数据失败：宽度仍可发布，`market_emotion` 不认证；
- 订单规模资金失败：行情情绪仍可发布，资金压力不可用；
- 龙虎榜或大宗交易失败：只隐藏对应证据卡，不阻断市场情绪；
- 互联互通失败：不影响A股情绪和订单规模资金；
- 单一板块缺数：隔离该板块，市场级行业汇总重新检查覆盖门槛；
- DSA允许生成删减版复盘，但必须明确列出缺失能力和数据时间。

不得把剩余指标重新加权伪装成完整版，也不得用前一交易日数值冒充当日值。允许使用最近一期数据的指标必须在Definition中显式声明 `asof_policy` 并展示滞后。

### 12.3 数据修订

```text
DataSnapshot v1
  → FeatureSnapshot v1
  → Market/Capital Snapshot v1

Correction DataSnapshot v2
  → FeatureSnapshot v2
  → Market/Capital Snapshot v2
```

v2不覆盖v1。页面可以默认展示最新修订版，但必须能查看“当时发布版”；正式回测和Prediction继续绑定原来的不可变Snapshot。

## 13. API 与页面

### 13.1 查询 API

建议首版接口：

```text
GET /api/v1/market/state?trade_date=&snapshot_id=
GET /api/v1/market/sentiment/history?from=&to=&score_version=
GET /api/v1/market/sentiment/contributions?trade_date=
GET /api/v1/market/capital?trade_date=&snapshot_id=
GET /api/v1/market/capital/evidence?channel=&trade_date=
GET /api/v1/sectors/capital?taxonomy=&trade_date=&sort=
GET /api/v1/market/metrics/{metric_id}/lineage?trade_date=
GET /api/v1/market/feature-snapshots?trade_date=
GET /api/v1/admin/market-feature-runs/{run_id}
```

API默认返回已发布的最新快照，同时返回 `data_as_of`、`snapshot_id`、`quality_status`、`missing_capabilities` 和 `is_corrected`。调用方需要复现时必须显式传入Snapshot ID。

### 13.2 市场总览页面

页面按五层呈现：

1. 情绪总分、平滑分、状态、数据时间和质量；
2. 五维雷达及每项贡献，点击查看原始公式和历史分位；
3. 涨跌家数、涨跌停天梯、流动性和风险结构；
4. 资金行为雷达：订单规模、杠杆、公开席位、大宗和互联互通分别展示等级与可信度；
5. 板块资金热力图、持续性、排名和价资共振。

页面必须区分“事实”“Provider派生”“平台推断”和“AI观点”，并提供来源、方法版本和快照入口。禁止只展示一个没有构成解释的红绿资金数字。

### 13.3 DSA FactPack

DSA只消费结构化事实包：

```yaml
market_state:
  trade_date: 2026-08-27
  feature_snapshot_id: fs_<uuidv7>
  emotion_score_raw: 68.4
  emotion_score_smoothed: 64.7
  regime: ACTIVE
  dimensions: {}
  capital_pressure: 21.3
  capital_activity: 73.1
  evidence_summary: []
  top_sector_flows: []
  missing_capabilities: []
  lineage_uri: /api/v1/market/feature-snapshots/fs_<uuidv7>
```

AI可以解释这些事实、指出分歧和生成自然语言复盘，但不得修改分数、补造缺失资金或把推断写回事实表。

## 14. 策略与回测接入

### 14.1 决策时序

```text
T日收盘
  → Certified DataSnapshot(T)
  → FeatureSnapshot(T)
  → Market/Capital Snapshot(T)
  → Prediction(T)
  → T+1尝试执行
```

正式回测按历史决策时点读取当时可用版本。今日收盘后才能确定的涨跌停、资金和状态不能用于T日收盘前成交。

### 14.2 策略声明

StrategySpec只引用稳定指标和版本：

```yaml
environment:
  required_features:
    - market.sentiment.score_raw@1.0.0
    - market.sentiment.regime@1.0.0
    - market.capital.transaction_size_pressure@1.0.0
  rules:
    - when: market.sentiment.regime in [PANIC, WEAK]
      action: block_new_entries
```

Resolver必须检查 FeatureSnapshot、能力认证、数据时点和版本。缺失依赖时拒绝运行，不能删除环境条件后退化成另一套策略。

### 14.3 防止回测失真

- 标准化窗口严格使用 T-1 及以前的数据；
- 连板晋级率先冻结T-1候选，再使用T结果；
- 行业成分、股票状态和市值均使用point-in-time版本；
- Provider只有today-only能力时，历史未采集日期为不可用，不按零回填；
- 第三方估算北向净流入默认不进入Formal回测；
- 页面固定情绪分不得通过同一回测区间最终收益反推权重；
- 策略优化形成独立 `weight_policy_version`，必须执行滚动训练和样本外验证；
- 数据修订后生成新的运行，不覆盖原回测结果。

### 14.4 指标验证

每个可用于策略的指标至少验证：

- T+1/T+3/T+5/T+20方向、超额收益和RankIC；
- 不同牛熊、波动和流动性阶段的稳定性；
- 分组收益、换手、容量和交易成本；
- 参数敏感性和时间衰减；
- 数据缺失、Provider切换和修订对结果的影响；
- 页面固定分与策略优化分的差异归因。

指标预测有效不代表可交易。最终策略收益仍由Hikyuu按正式市场规则计算。

## 15. 可观测性

每天至少记录：

```text
universe_count / tradable_observation_count
metric_valid_count / metric_coverage_ratio
dimension_status / missing_metric_ids
emotion_score / regime / regime_transition
capital_channel_status / evidence_confidence
provider / actual_upstream / methodology_version
data_snapshot_id / feature_snapshot_id
started_at / completed_at / deadline_missed
result_hash / revision_kind / supersedes_id
```

告警分为：

- 数据告警：覆盖率、身份、Schema、单位、异常跳变；
- 任务告警：超时、重试、租约、确定性失败；
- 能力告警：某个情绪维度或资金通道不可用；
- 口径告警：Provider方法版本变化、历史分布突变；
- 业务观察事件：状态迁移、极端宽度、资金与价格背离。业务观察事件不等同买卖信号。

## 16. 实施阶段

### Phase 1：基础事实和注册表

- 建立市场股票池、MetricDefinition和FeatureSnapshot契约；
- 计算涨跌家数、收益中位数、MA20/MA60宽度、新高新低、成交额和风险指标；
- 完成历史增量回填、覆盖率和公式确定性测试。

### Phase 2：情绪分

- 接入涨跌停、炸板、连板和晋级率；
- 实现严格历史标准化、五维分、固定情绪分和状态机；
- 发布市场状态API和基础页面。

### Phase 3：资金行为

- 接入订单规模资金、融资融券、龙虎榜、大宗交易和互联互通；
- 建立证据等级、可信度、资金压力和活跃度；
- 发布行业/概念板块资金Mart和价资共振。

### Phase 4：消费与回测

- 生成DSA FactPack；
- StrategySpec和Hikyuu读取冻结FeatureSnapshot；
- 完成T/T+1/T+H验证、Provider切换和Correction对照。

### Phase 5：优化

- 积累至少120个正式交易日后评估指标冗余和固定权重；
- 策略侧执行滚动权重优化，页面固定分保持原版本；
- 达到明确价值和资源门槛后再评估分钟级情绪、ETF净申购和盘中异常资金。

## 17. 验收标准

1. 任意市场分数都能追溯到原始指标、股票池、公式、Provider和Raw Hash；
2. 情绪分缺少必需维度时不会重新分配权重或伪装完整成功；
3. 订单规模资金明确标记为Provider派生，不显示为已确认机构账户；
4. 北向成交总额不被计算为净流入，第三方估算与官方事实分开；
5. 停牌、上市首日、ST、涨跌停规则和板块历史成分处理可复现；
6. T日盘后市场状态只能用于T+1及以后执行；
7. 同一Definition、DataSnapshot和FeatureSnapshot重复计算得到相同Hash；
8. Provider切换产生新分区和新Snapshot，不静默混合；
9. Correction不覆盖旧分数、Prediction、复盘和回测；
10. 页面、DSA和Hikyuu读取同一已发布事实，不各自计算同名指标；
11. 当前服务器能在17:30目标时间前完成核心市场情绪和订单规模资金增量计算；
12. 历史缺失的today-only资金数据保持不可用，不按零回填。

## 18. 已收敛的演进与页面基线

1. v1固定情绪分至少积累120个正式交易日后才评估v2；任何公式变化创建新`definition_version`，v1历史和引用永久保留，不回写；
2. 主平台采用P-MARKET的分Tab布局，情绪分量、资金证据、质量状态和历史对照并列展示，详见[页面信息架构与低保真原型 v1](page-prototypes-and-information-architecture-v1.md)；
3. 板块和热点保持客观榜单，只有Strategy显式引用时生成策略专属评分。

## 19. 参考资料

- [a-stock-data：资金流、板块、融资融券、龙虎榜和大宗交易能力](https://github.com/simonlin1212/a-stock-data)
- [Vibe-Research：大盘、短线情绪和板块资金页面参考](https://github.com/simonlin1212/Vibe-Research)
- [Financial-API：A股涨跌停、炸板、连板和龙虎榜契约](https://github.com/HiThink-Tech/Financial-API/blob/main/docs/mcp/hithink-finance-a-share.md)
- [深交所：2024年8月19日起调整深股通交易信息披露机制](https://www.szse.cn/szhk/hkbussiness/news/t20240726_608353.html)
- [港交所：互联互通市场数据披露调整](https://www.hkex.com.hk/News/Market-Communications/2024/2404122news?sc_lang=en)
- [A 股数据平台与 Canonical Data Contract v1](data-platform-and-canonical-contract.md)
- [盘后数据采集与 Snapshot 发布 SLA v1](data-ingestion-and-snapshot-sla.md)
- [指标、预测与 Hikyuu 回测架构](backtest-and-indicator-architecture.md)
- [评分、仓位与自动权重优化架构](weight-optimization-architecture.md)
- [A 股板块异动、热门观察与策略评分边界 v1](sector-observation-and-strategy-scoring-architecture.md)
- [全球市场观察与 A 股策略隔离架构 v1](global-market-observation-boundary.md)
- [A 股 Feature Store 与指标注册中心架构 v1](feature-store-architecture.md)
- [DSA A 股收盘复盘 FactPack 架构 v1](dsa-close-review-fact-pack.md)
- [A 股分层个股研究与 StockResearchFactPack 架构 v1](stock-research-architecture.md)
- [A 股主平台模块化单体、API、任务与权限架构 v1](platform-shell-api-task-permission-architecture.md)
