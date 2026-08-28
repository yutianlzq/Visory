# Visory A 股回测市场规则 v1

状态：规则已确认，待实现
最后更新：2026-08-28

## 1. 文档目的

本文固化Visory第一版正式回测的市场范围、历史股票池、价格与复权、T/T+1 时序、撮合、费用、容量、基准和失败语义。所有 Hikyuu 策略必须通过同一 `MarketRuleProfile` 执行，禁止每个策略自行解释涨跌停、费用或成交条件。

本文描述目标规则，不表示当前代码已经完成实现。

## 2. 已确认的 v1 默认值

| 项目 | v1 决策 |
| --- | --- |
| 市场范围 | 沪深主板、创业板、科创板 |
| 暂缓范围 | 北交所、ETF、可转债、港股、融资融券、做空、杠杆和分钟级撮合 |
| 方向 | 普通 A 股现货 Long-only |
| 新股冷却期 | 上市后前 20 个交易日不允许新买入 |
| ST 风险股票 | `ST` / `*ST` 不允许新买；存量持仓进入强制退出队列 |
| 信号时点 | T 日收盘数据稳定后生成 |
| 执行时点 | T+1 开盘尝试执行 |
| 订单顺序 | 先卖后买，卖出到账资金可用于当日后续买入 |
| 涨跌停成交 | 开盘涨停不买，开盘跌停不卖；采用保守拒绝语义 |
| 订单期限 | `DAY`，未成交部分不自动跨日 |
| 容量 | 单标的单次交易金额不超过过去 20 个有效交易日平均成交金额的 5% |
| 佣金默认 | 买卖双向万 3，单笔订单最低 5 元，可被券商配置覆盖 |
| 基础滑点 | 买卖各 5 bp，再叠加可选流动性冲击 |
| 主回测资金 | 100 万元 |
| 容量对照 | 1000 万元 |

以上默认值全部进入版本化配置，不能散落为代码常量。

## 3. 市场范围与实现边界

### 3.1 第一阶段包含

- 上海证券交易所主板 A 股；
- 深圳证券交易所主板 A 股；
- 创业板 A 股；
- 科创板 A 股；
- 上述证券的退市、暂停上市、风险警示和公司行动历史，只要相应时点事实可获得。

### 3.2 第一阶段不包含

- 北交所股票；
- ETF、LOF、可转债、债券、期权和基金；
- B 股、港股和美股；
- 融资融券、卖空、日内回转和杠杆；
- 大宗交易、盘后固定价格交易和夜市委托；
- 需要订单簿或逐笔成交才能可靠模拟的策略。

北交所最终属于平台 A 股能力范围，但其涨跌幅、申报数量和流动性特征不同。只有完成 point-in-time 数据、交易规则和 Hikyuu Adapter 验证后，才通过新的 `MarketRuleProfile` 加入，不改变 v1 结果。

## 4. Point-in-time 历史股票池

### 4.1 禁止幸存者偏差

每个交易日的可选股票池由该日已经可用的证券状态构建，不得使用当前股票列表反推历史。后来退市、改名、换板或变更风险状态的股票必须保留历史身份。

最少需要 `instrument_state_daily`：

```text
symbol / canonical_id
trade_date
exchange / board
listed_at / delisted_at
listing_sessions
security_name
risk_warning_type
trading_status
suspension_status
lot_rule_version
price_limit_rule_version
available_at
data_snapshot_id
```

证券名称中的 `ST` 文本只能作为展示或交叉验证，不能代替结构化风险状态。

### 4.2 新股规则

`listing_sessions <= 20` 时：

- 不进入新买候选池；
- 可以计算指标和观察性 Validation；
- 不创建买入 OrderIntent；
- 若未来需要新股策略，必须建立独立策略域和市场规则版本。

交易日计数以证券实际可交易的上市交易日序列为准，不用自然日近似。

### 4.3 ST、退市与停牌

| 状态 | 新买 | 已有持仓 |
| --- | --- | --- |
| `ST` / `*ST` | 禁止 | 进入 `forced_exit_pending`，下一个可交易日尝试卖出 |
| 退市风险警示/退市整理 | 禁止 | 进入强制退出队列，不假设立即成交 |
| 停牌 | 禁止 | 保留持仓和估值状态，复牌后再处理 |
| 已终止上市 | 禁止 | 使用官方结算/最终处置事实；缺失时按保守规则处理并标记不完整 |

强制退出订单如果因跌停、停牌或流动性无法成交，每个后续交易日重新评估，不能把触发风控等同于已经卖出。

若终止上市后缺少可靠结算事实，v1 默认将未处置部分减记至 0，并设置 `missing_delisting_settlement=true`。该运行可以完成，但质量状态为 `partial_data`，报告必须披露该保守减记。

### 4.4 指数与行业成分

如果策略股票池来自指数或行业，必须使用当日历史成分和当时已经公布的生效日期。当前指数成分、当前申万行业或当前概念归属不能回填到历史日期。

## 5. 价格、复权与公司行动

### 5.1 双轨价格模型

```text
指标/因子
  → point-in-time total-return adjusted series

订单/成交/持仓估值
  → 当时真实未复权 OHLC

分红/送转/配股
  → CorporateAction Ledger
```

技术指标所用复权序列只能包含决策时点已经发生且已经可用的公司行动。禁止直接使用在回测结束后统一生成、包含未来除权因子的完整前复权历史。

### 5.2 原始行情要求

正式日线回测最少需要：

```text
trade_date / symbol
open / high / low / close
volume / amount
prev_close
upper_limit / lower_limit
trading_status
available_at
source / data_snapshot_id
```

执行价格永远来自未复权行情。缺少开盘价、交易状态或价格限制等关键字段时，当日订单拒绝为 `MISSING_EXECUTION_FACT`，不能使用收盘价或邻近日期插值。

### 5.3 CorporateAction Ledger

公司行动至少支持：

- 现金分红；
- 送股、转增；
- 配股；
- 拆股/合股；
- 证券代码或身份变更；
- 退市处置和现金结算。

事件最少记录公告时间、股权登记日、除权除息日、支付日、生效数量、现金金额、来源和 Hash。现金和股份只在规则定义的生效日进入组合账本，不能因为数据后来补齐而改写旧 BacktestRun。

## 6. T/T+1 决策与订单生命周期

### 6.1 收盘策略时序

```text
T 日收盘
  → 等待数据稳定水位
  → 冻结 DataSnapshot(T)
  → 计算 FeatureSnapshot(T)
  → 生成 Prediction(T)
  → 生成 T+1 OrderIntent
  → T+1 开盘先执行卖单
  → 更新可用现金
  → T+1 开盘执行买单
  → 记录拒绝、部分成交或完全成交
  → 未成交剩余订单日终失效
```

`T+1` 始终指下一交易日。若跨节假日，使用交易日历推进。

### 6.2 OrderIntent

订单最少保存：

```text
order_intent_id / prediction_id
decision_at / planned_execution_at
symbol / side
target_weight / target_quantity
order_type = MARKET_ON_OPEN_SIM
time_in_force = DAY
price_policy_version
liquidity_policy_version
risk_rule_version
created_at
```

v1 不模拟真实交易所市价订单类型，`MARKET_ON_OPEN_SIM` 只是平台日线撮合语义：按开盘价及滑点模型计算参考成交价，并通过保守成交门禁。

### 6.3 卖出与买入顺序

同一 T+1 日：

1. 处理公司行动和开盘前持仓状态；
2. 执行强制退出和普通卖单；
3. 更新已完成卖出的可用现金；
4. 按目标权重、排名及稳定 tie-break 执行买单；
5. 保留现金残差并写入目标/实际权重偏差。

排序规则必须确定，例如：强制退出优先、普通卖出其次；买入按目标金额降序、策略 Rank、证券代码稳定排序。相同输入重复运行必须得到相同结果。

## 7. 日线撮合规则

### 7.1 参考成交价

```text
buy_price  = open(T+1) × (1 + total_slippage)
sell_price = open(T+1) × (1 - total_slippage)
```

`total_slippage` 至少包含 `base_slippage_bps`，后续可以增加随订单规模、波动和流动性变化的冲击模型。

计算后的价格若超出当日合法价格范围，订单拒绝，不截断到涨跌停价后假设成交。

### 7.2 拒绝规则

| 条件 | 买入 | 卖出 | 原因码 |
| --- | --- | --- | --- |
| 停牌/非交易日 | 拒绝 | 拒绝 | `SUSPENDED` |
| 开盘价缺失或无效 | 拒绝 | 拒绝 | `MISSING_EXECUTION_FACT` |
| 开盘价达到或高于涨停价 | 拒绝 | 允许按其他门禁评估 | `LIMIT_UP_QUEUE` |
| 开盘价达到或低于跌停价 | 允许按其他门禁评估 | 拒绝 | `LIMIT_DOWN_QUEUE` |
| 未达到上市冷却期 | 拒绝 | 允许 | `IPO_COOLDOWN` |
| ST/退市风险状态 | 拒绝 | 允许并优先 | `RISK_WARNING_ENTRY_BLOCKED` |
| 可卖数量不足 | 不适用 | 部分/拒绝 | `T1_RESTRICTION` |
| 现金不足 | 部分/拒绝 | 不适用 | `INSUFFICIENT_CASH` |
| 容量不足 | 部分/拒绝 | 部分/拒绝 | `LIQUIDITY_CAP` |

使用价格最小变动单位进行比较，不能直接用浮点相等判断涨跌停。

### 7.3 保守的涨跌停语义

即使日内后来打开涨停或跌停，v1 的开盘执行订单仍按开盘排队不确定处理：开盘涨停买单不成交、开盘跌停卖单不成交。未来只有在引入集合竞价匹配量、订单簿或分钟数据后，才能建立更精细的成交概率模型。

### 7.4 部分成交与订单失效

目标数量超过现金、可卖数量、整手或流动性上限时，可以部分成交。每个成交保存原目标、限制前数量、限制后数量和限制原因。

日终剩余数量状态为 `expired`，不自动进入下一交易日。策略如果仍希望交易，下一次决策创建新的 OrderIntent，以避免订单跨日携带导致无法解释的信号时点。

## 8. 流动性和容量

### 8.1 v1 容量上限

```text
adv20_amount(T) = mean(amount of last 20 valid sessions ending at T)
max_order_value(T+1) = adv20_amount(T) × 5%
```

容量计算只使用 T 日及以前数据，禁止用 T+1 完整日成交额决定 T+1 开盘能成交多少。

不足 20 个有效成交日时不允许新买；卖出按可用历史估计执行并标记 `liquidity_estimate_low_quality`，强制退出不因为估计缺失而从队列消失。

### 8.2 容量测试

每个正式策略至少运行：

- 主结果：初始资金 100 万元；
- 容量对照：初始资金 1000 万元。

两者使用同一信号和规则，但独立计算整手、容量、现金及实际权重。报告比较收益衰减、未成交率、冲击成本和目标仓位偏差。

## 9. A 股持仓与可卖数量

持仓账本至少区分：

```text
total_quantity
sellable_quantity
today_bought_quantity
frozen_quantity
pending_corporate_action_quantity
```

T+1 开盘前，前一交易日买入股份从 `today_bought_quantity` 转入 `sellable_quantity`。当天新买股份不能参与当天后续卖出。交易所现行规则要求投资者买入证券在交收前不得卖出，回转交易品种除外；v1 普通 A 股按此处理。

## 10. 整手和申报数量

申报数量由 `lot_rule_version` 决定，不统一硬编码为 100 股：

- 沪深主板和创业板使用对应交易规则的最低申报数量及零股卖出规则；
- 科创板使用科创板最低申报数量、递增单位和零股规则；
- 股票送转产生的零股在卖出时按适用规则处理；
- 目标权重先转为连续数量，再由 Execution Projector 投影成合法申报数量。

投影产生的未使用现金保留为现金，不能为了凑满仓而突破目标上限。

## 11. 价格限制规则版本

涨跌停不能只根据证券代码前缀推断。平台维护：

```text
TradingRuleVersion
  ├── exchange
  ├── board
  ├── security_state
  ├── effective_from / effective_to
  ├── price_limit_ratio
  ├── no_limit_conditions
  ├── tick_size
  ├── lot_rule
  └── source_document
```

当前沪深主板、科创板、创业板和北交所存在 10%、20%、30% 及新股特殊阶段等差异，且历史上规则发生过变化。实现优先级：

1. 使用数据源提供且通过交叉验证的每日 `upper_limit/lower_limit`；
2. 缺失时按当日 `TradingRuleVersion` 和前收盘价计算；
3. 两者冲突时拒绝交易并标记 `PRICE_LIMIT_CONFLICT`，不静默选择较有利结果。

## 12. 费用与滑点

### 12.1 默认券商配置

```yaml
commission:
  buy_rate: 0.0003
  sell_rate: 0.0003
  minimum_per_order: 5.00
  includes_exchange_handling: true

slippage:
  base_buy_bps: 5
  base_sell_bps: 5
  liquidity_impact: disabled
```

单个 OrderIntent 产生多个部分成交时，v1 先聚合该订单当日成交额，再计算一次最低佣金，避免对每个内部 fill 重复收取 5 元。

### 12.2 法定税费版本

费用必须按成交日选择 `FeeProfileVersion`。至少建立：

| 费用 | 适用方向 | 当前已确认锚点 |
| --- | --- | --- |
| 证券交易印花税 | 卖出单边 | 2023-08-28 起按减半后费率处理，即默认 `0.0005` |
| 股票交易过户费 | 买卖双边 | 2022-04-29 起沪深京统一为成交金额 `0.01‰`，即 `0.00001` |
| 券商佣金 | 买卖双边 | 以账户配置为准，v1 默认万 3、最低 5 元 |

回测跨越费率变更日时按每笔成交日期计算。更早历史费率必须补齐日期表；缺失时不能把当前费率静默套用到全部历史，应标记 `fee_schedule_incomplete`。

### 12.3 防止重复计费

个人券商模式默认佣金已包含交易经手等券商打包费用，平台另计印花税和过户费。只有显式切换到 `exchange_decomposed` 模式时才逐项计算经手费、监管费等，两个模式互斥。

## 13. 基准与绩效口径

### 13.1 基准选择

| 策略股票池 | 主基准 | 辅助基准 |
| --- | --- | --- |
| 全 A 宽基 | 中证全指 | 沪深 300、中证 500、中证 1000 |
| 大盘策略 | 沪深 300 | 中证全指 |
| 中盘策略 | 中证 500 | 中证全指 |
| 小盘策略 | 中证 1000 | 中证全指 |
| 行业策略 | 对应行业全收益指数 | 中证全指 |

每个 StrategyVersion 固定 `primary_benchmark_id`。回测完成后不能根据结果改选表现更差的基准。

基准优先使用全收益指数；只有价格指数可用时，报告明确标记 `benchmark_return_type=price`，不能与包含现金分红的组合收益无提示比较。

### 13.2 主绩效指标

- 总收益、年化收益、年度/月度收益；
- 主基准收益、超额收益、年化超额；
- 年化波动、Sharpe、Sortino、Calmar；
- 最大回撤、回撤持续时间和恢复时间；
- 信息比率和跟踪误差；
- 换手、佣金、税费、滑点和总交易成本；
- 未成交率、部分成交率、涨跌停拒绝率；
- 目标/实际权重偏差和平均现金占比；
- 100 万与 1000 万资金规模的容量衰减。

无风险利率由 `PerformanceMetricVersion` 配置并进入 Manifest；v1 可以使用固定值作为可复现基准，但页面必须展示该值。

## 14. 数据缺失和冲突语义

| 缺失/冲突 | 行为 |
| --- | --- |
| 证券历史身份缺失 | 从当日股票池排除，运行标记覆盖率下降 |
| 原始 OHLC 缺失 | 不交易、不插值 |
| 价格限制缺失但规则可计算 | 使用规则计算并标记降级 |
| 数据源价格限制与规则冲突 | 拒绝交易并记录冲突 |
| 公司行动缺失 | 运行不得标记 reproducible/complete |
| 历史费率缺失 | 使用显式研究 fallback 或拒绝正式发布 |
| 退市结算缺失 | 保守减记为 0，运行标记 `partial_data` |
| 基准缺失 | 策略绝对收益仍可计算，但正式比较状态不完整 |

正式结果页面必须显示数据质量状态，不能只在日志中记录。

## 15. Hikyuu Adapter 映射

```text
Canonical Bar / CorporateAction
  → Hikyuu KData / 权益处理输入

MarketRuleProfile
  → Environment / Condition / Execution Guard

Strategy Signal(T)
  → Prediction / OrderIntent(T+1)

Lot / T+1 / Cash / Capacity
  → MoneyManager + Platform Execution Projector

Commission / Tax / Transfer Fee
  → Versioned TradeCost Adapter

Base + Liquidity Slippage
  → Versioned Slippage Adapter

Order / Trade / Position / NAV
  → 平台归一结果和审计链
```

若 Hikyuu 原生组件无法表达某项日期版本化规则，由平台 Adapter 在订单进入 Hikyuu 前后执行约束，但必须保存拒绝或投影结果，不修改 Hikyuu 内核，也不能仅在报告阶段修正收益。

## 16. 配置契约示例

```yaml
market_rule_policy_id: cn-a-share-daily-v1
policy_version: 1.0.0

scope:
  exchanges: [SSE, SZSE]
  boards: [main, chinext, star]
  asset_types: [common_stock]
  long_only: true
  leverage: 1.0

universe:
  point_in_time: true
  min_listing_sessions: 20
  block_new_risk_warning_entries: true
  existing_risk_warning_action: forced_exit_next_tradable

execution:
  signal_time: close_after_data_ready
  execution_time: next_session_open
  order_sequence: sell_then_buy
  time_in_force: DAY
  buy_at_open_limit_up: reject
  sell_at_open_limit_down: reject
  missing_execution_fact: reject

liquidity:
  lookback_sessions: 20
  max_adv_amount_ratio: 0.05
  allow_partial_fill: true

cost:
  commission_buy_rate: 0.0003
  commission_sell_rate: 0.0003
  commission_min_per_order: 5.00
  stamp_duty_schedule: cn-stamp-duty-v1
  transfer_fee_schedule: cn-transfer-fee-v1
  base_buy_slippage_bps: 5
  base_sell_slippage_bps: 5

capital:
  primary: 1000000
  capacity_scenarios: [10000000]
```

运行时必须展开所有默认值，保存 resolved config 和 `market_rule_profile_hash`。

## 17. 追溯要求

每笔交易可以回答：

- 哪个 T 日信号产生订单；
- 使用哪个 T+1 交易日、开盘价和价格限制；
- 当时证券是否上市、ST、停牌或处于退市流程；
- 目标数量如何经过 T+1、现金、整手和容量投影；
- 使用哪个佣金、税费、过户费和滑点版本；
- 为什么未成交或只成交一部分；
- 公司行动如何改变现金和持股；
- 对最终收益、费用和基准超额贡献多少。

Backtest Manifest 增加：

```text
market_rule_policy_id / policy_version / definition_hash
instrument_state_snapshot_id
corporate_action_snapshot_id
price_limit_rule_set_version
lot_rule_set_version
fee_profile_version
slippage_profile_version
liquidity_policy_version
primary_benchmark_id / benchmark_snapshot_id
initial_capital / capacity_scenario_id
```

## 18. 验收测试

### 18.1 股票池

1. 使用包含后来退市股票的历史夹具，确认回测当日股票池仍包含该股票；
2. 当前股票名称和行业不能覆盖历史名称、历史行业；
3. 上市第 20 个交易日仍被阻止，第 21 个交易日起才允许新买；
4. ST 股票不新买，存量持仓产生强制退出但未必成交；
5. 停牌期间持仓保留且不产生虚假交易。

### 18.2 价格和时序

6. T 日信号无法读取 T+1 开盘及之后事实；
7. T 日信号最早只在 T+1 开盘成交；
8. 指标使用 point-in-time 复权，订单使用未复权价格；
9. 分红、送转前后持仓市值和现金账本连续；
10. 数据修正创建新快照，不覆盖旧结果。

### 18.3 撮合与持仓

11. 开盘涨停买单拒绝，开盘跌停卖单拒绝；
12. 当天买入数量不能当天卖出；
13. 卖出完成后资金可参与同日后续买单；
14. 容量按 T 日及以前 ADV20 计算，不读取 T+1 完整成交额；
15. 部分成交、失效数量和拒绝原因完整落地；
16. 科创板等不同申报数量规则使用对应版本，不统一按 100 股处理。

### 18.4 费用和绩效

17. 跨 2023-08-28 的卖出分别使用对应印花税版本；
18. 跨 2022-04-29 的交易分别使用对应过户费版本；
19. 单订单多个 fill 只应用一次最低佣金；
20. 买卖成本、滑点和现金余额逐笔可复算；
21. 主基准在运行前冻结，回测后无法改选；
22. 100 万和 1000 万场景独立执行整手、容量和费用模型。

## 19. 实施顺序

1. 建立 `instrument_state_daily`、交易日历和退市证券保留机制；
2. 建立 raw bar、每日价格限制和 CorporateAction Ledger；
3. 建立 `MarketRuleProfile`、日期版本化 PriceLimit/Lot/Fee 表；
4. 实现 T/T+1 OrderIntent、Execution Guard 和持仓可卖数量；
5. 实现佣金、印花税、过户费、滑点与容量；
6. 对接 Hikyuu TradeCost、Slippage、MoneyManager 和组合结果；
7. 完成边界夹具、确定性回归和 Manifest 复现；
8. 通过后再进入 StrategySpec 和正式策略迁移。

## 20. 延后事项

下列内容不再阻塞 v1 规则确认，但需要后续独立设计：

- 北交所 MarketRuleProfile；
- 分钟线、集合竞价、订单簿和成交概率模型；
- ETF、可转债和支持 T+0 的特殊品种；
- 融资融券、做空、借券费和保证金；
- 更复杂的非线性市场冲击模型；
- 真实券商逐笔成交回放和实盘对账。

## 21. 参考资料

- [上海证券交易所交易规则（2026 年修订）](https://www.sse.com.cn/lawandrules/sselawsrules2025/stocks/exchange/c/c_20260424_10816482.shtml)
- [深圳证券交易所交易规则（2026 年修订）](https://www.szse.cn/lawrules/rule/trade/current/t20260424_620190.html)
- [深交所创业板涨跌幅规则说明](https://www.szse.cn/www/investor/index/update/t20200729_580056.html)
- [北交所交易规则](https://www.bse.cn/jygl_list/200010919.html)
- [财政部、税务总局关于减半征收证券交易印花税的公告](https://www.mof.gov.cn/jrttts/202308/t20230828_3904235.htm)
- [新华社：中国结算下调股票交易过户费](https://www.xinhuanet.com/2022-04/28/c_1128605983.htm)
- [指标、预测与 Hikyuu 回测架构](backtest-and-indicator-architecture.md)
- [评分、仓位与自动权重优化架构](weight-optimization-architecture.md)
