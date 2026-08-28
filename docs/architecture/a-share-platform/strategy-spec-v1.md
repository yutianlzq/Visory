# Visory StrategySpec v1 策略契约

状态：规则已确认，待实现
最后更新：2026-08-28

## 1. 文档目的

本文定义Visory第一版策略表达契约。目标是用同一份不可变 `ResolvedStrategySpec` 驱动策略预览、Hikyuu 回测、模拟组合和日常选股，避免页面、Python 策略、回测和推送分别维护不同逻辑。

本文描述目标架构和 Schema 草案，不表示当前代码已经完成实现。

## 2. 已确认的架构边界

策略相关配置拆成五份：

| 契约 | 负责内容 | 不负责内容 |
| --- | --- | --- |
| `StrategySpec` | 股票池、特征、筛选、评分、入场、退出、调仓语义 | 撮合细节、自动优化、多策略资金 |
| `MarketRuleProfile` | T+1、涨跌停、整手、费用、滑点、容量和成交 | 策略为什么选中股票 |
| `WeightPolicySpec` | 因子、个股、策略和敞口权重及优化 | 买卖信号定义 |
| `PortfolioSpec` | 多个 StrategyVersion 的组合及资金预算 | 单策略内部公式 |
| `BacktestRunSpec` | 数据快照、区间、资金、基准和运行模式 | 修改任何策略规则 |

一次正式运行必须同时冻结五份契约的版本和 Hash。修改市场费用不产生新的 StrategyVersion；修改筛选、评分、信号或退出规则必须产生新的 StrategyVersion。

## 3. 参考项目的复用边界

### 3.1 Sequoia-X

Sequoia-X 的均线放量、海龟突破、RPS、旗形、涨停洗盘等规则作为首批策略来源。其现有 `BaseStrategy.run()` 主要输出股票代码列表，具体策略直接在 Python 中读取行情和计算条件；平台复用业务规则，不直接把这些类作为正式回测运行时。

第一批迁移：

1. 均线放量；
2. 海龟突破；
3. RPS 突破。

复杂形态和公告事件进入第二批，优先用受控插件承载，再评估是否下沉为 DSL。

### 3.2 Fleur

吸收 Fleur 的 `pool_filters → scoring.rules → score/rank → TopN → backtest` 分层、applied/draft 分离、stale 检查和 `score_breakdown` 解释；不复用其运行栈。

### 3.3 Hikyuu

Hikyuu 提供 Environment、Condition、Signal、Stoploss/Takeprofit、MoneyManager、Slippage、Selector、AllocateFunds 和 Portfolio 等执行组件。Strategy Compiler 把平台契约映射为这些组件；Hikyuu 不成为策略配置的权威存储。

## 4. StrategySpec 顶层结构

```yaml
schema_version: 1.0.0
strategy_id: strategy_019c5f2a-8c31-7d2e-9e62-9d1147d7a41b
strategy_version: 1.0.0
name: 均线放量突破
strategy_type: cross_sectional
strategy_lifecycle_status: DRAFT

market_rule_profile_ref: cn-a-share-daily-v1@1.0.0
weight_policy_ref: score-weight-capped-v1@1.0.0

schedule: {}
universe: {}
features: []
market_environment: {}
pool_filters: {}
scoring: {}
selection: {}
entry: {}
exit: {}
risk_exit: {}
rebalance: {}
explain: {}
```

顶层最少字段：

| 字段 | 含义 |
| --- | --- |
| `schema_version` | StrategySpec Schema 版本 |
| `strategy_id` / `strategy_version` | 稳定策略标识和不可变语义版本 |
| `strategy_type` | `cross_sectional` 或 `plugin`；后续可扩展 |
| `strategy_lifecycle_status` | `DRAFT/VALIDATED/APPROVED/ACTIVE/RETIRED`；Preview是Run Mode，不是生命周期状态 |
| `market_rule_profile_ref` | 执行市场规则引用 |
| `weight_policy_ref` | 仓位与权重策略引用 |
| `schedule` | 评价和执行时间 |
| `universe` | 策略业务股票池 |
| `features` | 指标依赖和别名 |
| `pool_filters` | 候选池硬条件 |
| `scoring` | 分数和解释分解 |
| `selection` | TopN 和排名规则 |
| `entry` / `exit` | 策略买卖语义 |
| `risk_exit` | 个股风险退出规则 |
| `rebalance` | 调仓频率和空信号行为 |

## 5. 业务股票池与市场规则分离

`universe` 只描述策略希望研究的范围，例如全 A、大盘、某行业或自选集合：

```yaml
universe:
  source:
    type: named_universe
    universe_id: all_a_share_v1
  include_boards: [main, chinext, star]
  filters:
    - compare: {left: market_cap, op: gte, right: 2000000000}
```

ST、新股冷却、停牌、退市、T+1 和整手限制不在每个策略重复配置，由 `MarketRuleProfile` 统一处理。策略可以在市场规则之上进一步缩小范围，但不能放宽市场规则。

指数、行业和概念股票池必须引用 point-in-time membership 数据集及版本。

## 6. Feature 依赖

每个公式只引用已注册指标：

```yaml
features:
  - indicator_id: stock.ma
    definition_version: 1.0.0
    params: {n: 5, price: close}
    alias: ma5
  - indicator_id: stock.ma
    definition_version: 1.0.0
    params: {n: 20, price: close}
    alias: ma20
  - indicator_id: stock.volume_ma
    definition_version: 1.0.0
    params: {n: 20}
    alias: volume_ma20
```

Compiler 从 Indicator Registry 解析：输入数据、lookback、warmup、公式 Hash、point-in-time 状态和 Hikyuu 映射。未知指标、未知参数、重复别名或 `point_in_time=false` 直接拒绝正式编译。

第一版A股Formal和Paper策略禁止引用全球指数、外汇、商品、海外利率和海外事件Feature。`global.*`、`fx.*`、`commodity.*`、`overseas_index.*`和`overseas_event.*`依赖必须以`GLOBAL_FEATURE_NOT_ALLOWED_IN_A_SHARE_STRATEGY_V1`拒绝编译；全球事实只用于页面和DSA复盘背景，详见[全球市场观察与 A 股策略隔离架构 v1](global-market-observation-boundary.md)。

## 7. 安全表达式 DSL

### 7.1 禁止任意代码

YAML/JSON 中禁止：

- Python、JavaScript、SQL 或 Shell；
- `eval`、动态 import、反射和任意函数名；
- 网络、文件或数据库访问；
- 直接引用物理表名、列名或本地路径；
- 读取当前系统时间或未冻结环境变量。

DSL 解析为受控 AST，不把字符串送入语言解释器。

### 7.2 v1 节点

| 分类 | 节点 |
| --- | --- |
| 布尔 | `all`、`any`、`not` |
| 比较 | `gt`、`gte`、`lt`、`lte`、`eq`、`between` |
| 算术 | `add`、`sub`、`mul`、`div`、`min`、`max`、`abs` |
| 交叉 | `cross_above`、`cross_below` |
| 时间 | `rolling_count`、`consecutive`、`within_sessions` |
| 截面 | `rank`、`percentile`、`zscore` |
| 常量/引用 | `literal`、`feature`、`parameter` |

第二阶段再增加公告和事件节点。所有节点拥有固定输入/输出类型，布尔节点不能作为数值静默转换，除零、空值和无穷值使用显式策略。

### 7.3 AST 示例

```yaml
all:
  - cross_above:
      left: {feature: ma5}
      right: {feature: ma20}
  - compare:
      left: {feature: volume}
      op: gt
      right:
        mul:
          - {feature: volume_ma20}
          - {literal: 1.5}
```

## 8. 筛选、评分、入场和退出分离

| 层 | 回答的问题 | 输出 |
| --- | --- | --- |
| `pool_filters` | 是否进入候选池 | boolean + condition hits |
| `scoring` | 候选股得多少分 | raw score + score breakdown |
| `selection` | 哪些候选进入目标集合 | rank + selected |
| `entry` | 入选后是否产生开仓信号 | BuySignal |
| `exit` | 策略逻辑是否要求退出 | SellSignal |
| `risk_exit` | 风险条件是否强制退出 | RiskExitSignal |

同一指标可以显式参与多个层，但平台不会自动把过滤条件变成评分或卖出条件。

## 9. 评分与选择

```yaml
scoring:
  clamp: {min: 0, max: 100}
  missing_value: reject_candidate
  rules:
    - component_id: volume_strength
      expression:
        div: [{feature: volume}, {feature: volume_ma20}]
      normalization: cross_sectional_percentile
      direction: higher_better
      weight: 0.6
    - component_id: trend_strength
      expression:
        div:
          - {sub: [{feature: ma5}, {feature: ma20}]}
          - {feature: ma20}
      normalization: cross_sectional_percentile
      direction: higher_better
      weight: 0.4

selection:
  method: top_n
  top_n: 20
  minimum_score: 60
  tie_break: canonical_id_asc
```

输出必须保存 `raw_score`、clamp 后 `score`、`rank`、`score_breakdown`、原始特征值和选中原因。权重修改后旧 Preview 变为 stale，正式运行重新计算完整区间。

市场观察域不提供统一的板块热度分或热点股分。策略引用板块、资金、异动或公开榜单因素时，评分必须由当前StrategySpec显式定义并只写入Strategy/Run上下文；客观榜单和策略评分的隔离契约见[A 股板块异动、热门观察与策略评分边界 v1](sector-observation-and-strategy-scoring-architecture.md)。

## 10. 入场、退出与调仓

### 10.1 入场

v1 支持：

```yaml
entry:
  mode: selected
```

或入选后再检查额外条件：

```yaml
entry:
  mode: selected_and_condition
  condition:
    compare: {left: market_regime_score, op: gte, right: 0.5}
```

### 10.2 策略退出

```yaml
exit:
  any:
    - rank_below: 30
    - cross_below: {left: ma5, right: ma20}
```

`rank_below` 使用退出缓冲，避免刚跌出 Top20 就立即卖出、第二天又买回。

### 10.3 调仓

```yaml
rebalance:
  frequency: daily
  empty_signal_action: hold
  minimum_holding_sessions: 0
```

`frequency` 支持 daily/weekly/monthly，事件触发调仓第二阶段加入。`empty_signal_action` 必须显式填写：

- `hold`：没有新候选时不因空池清仓，退出仍由 exit/risk_exit 触发；
- `exit_all`：空池时尝试清空策略持仓。

Sequoia 首批迁移策略默认 `hold`。

## 11. 风险退出

v1 支持：

- 固定百分比止损；
- ATR 止损；
- 指标止损；
- 固定止盈；
- 跟踪止盈；
- 最大持有期；
- 跌出排名退出；
- 策略信号失效退出。

示例：

```yaml
risk_exit:
  any:
    - fixed_stop_loss: {percent: 0.08}
    - trailing_take_profit: {drawdown_from_peak: 0.12, activate_profit: 0.15}
    - max_holding_sessions: 60
```

风险退出只生成 SellIntent 原因，最终能否成交仍由 MarketRuleProfile 决定。

## 12. 决策优先级

固定优先顺序：

```text
市场不可交易约束
  → ST/退市强制退出
  → 组合级风险退出
  → 个股 risk_exit
  → 策略 exit
  → 排名/调仓卖出
  → 新买入
```

风险层可以减少或取消买入、增加退出，上游策略不能恢复已被风险层阻止的订单。

## 13. 完整示例：均线放量

```yaml
schema_version: 1.0.0
strategy_id: strategy_019c5f2a-8c31-7d2e-9e62-9d1147d7a41b
strategy_version: 1.0.0
name: 均线放量突破
strategy_type: cross_sectional
strategy_lifecycle_status: DRAFT

market_rule_profile_ref: cn-a-share-daily-v1@1.0.0
weight_policy_ref: score-weight-capped-v1@1.0.0

schedule:
  evaluate: every_trading_day_after_close
  execute: next_session_open

universe:
  source: {type: named_universe, universe_id: all_a_share_v1}

features:
  - {indicator_id: stock.ma, definition_version: 1.0.0, params: {n: 5}, alias: ma5}
  - {indicator_id: stock.ma, definition_version: 1.0.0, params: {n: 20}, alias: ma20}
  - {indicator_id: stock.volume_ma, definition_version: 1.0.0, params: {n: 20}, alias: volume_ma20}

pool_filters:
  all:
    - cross_above: {left: {feature: ma5}, right: {feature: ma20}}
    - compare:
        left: {feature: volume}
        op: gt
        right: {mul: [{feature: volume_ma20}, {literal: 1.5}]}

scoring:
  clamp: {min: 0, max: 100}
  rules:
    - component_id: volume_strength
      expression: {div: [{feature: volume}, {feature: volume_ma20}]}
      normalization: cross_sectional_percentile
      direction: higher_better
      weight: 1.0

selection:
  method: top_n
  top_n: 20
  minimum_score: 60
  tie_break: canonical_id_asc

entry: {mode: selected}

exit:
  any:
    - rank_below: 30
    - cross_below: {left: {feature: ma5}, right: {feature: ma20}}

risk_exit:
  any:
    - fixed_stop_loss: {percent: 0.08}
    - max_holding_sessions: 60

rebalance:
  frequency: daily
  empty_signal_action: hold
```

## 14. 受控插件逃生口

声明式 DSL 无法表达的复杂状态策略使用：

```yaml
strategy_type: plugin
plugin:
  plugin_id: sequoia.limit_up_shakeout
  plugin_version: 1.0.0
  parameter_schema_version: 1.0.0
  parameters: {}
```

插件必须：

1. 只读取 Compiler 注入的 FeatureSnapshot 和 StrategyState；
2. 禁止网络、文件、数据库和当前系统时间访问；
3. 禁止直接创建订单或修改持仓；
4. 只输出标准 CandidateScore/BuySignal/SellSignal；
5. 声明 lookback、warmup、输入特征和状态 Schema；
6. 保存插件版本、代码 Hash 和依赖 Hash；
7. 通过确定性、point-in-time 和资源上限测试。

AI 可以创建插件或 DSL 草稿，但只能保存为 `draft`，不能自动批准或激活。

## 15. Compiler 管线

```text
StrategySpec Draft
  → JSON Schema Validation
  → Semantic Validation
  → Feature Dependency Resolution
  → Point-in-time / Leakage Check
  → Defaults Expansion
  → ResolvedStrategySpec + Hash
  → Hikyuu CompilationPlan
  → Preview / Backtest / Paper Portfolio
```

Semantic Validation 至少检查：

- 策略、市场规则和权重引用存在且兼容；
- 指标别名和参数类型正确；
- AST 节点、输入和输出类型正确；
- lookback/warmup 可以满足回测区间；
- TopN、minimum_score、退出排名和权重合法；
- `empty_signal_action` 已显式设置；
- 条件不包含未来字段；
- plugin 权限和代码 Hash 已登记；
- 无法到达、恒真/恒假或明显矛盾条件生成警告或拒绝。

## 16. Hikyuu 映射

| StrategySpec | Hikyuu |
| --- | --- |
| `universe` | Block / StockList |
| `market_environment` | Environment |
| 策略适用条件 | Condition |
| `entry` / `exit` | Signal |
| `risk_exit.fixed/indicator` | Stoploss / Takeprofit |
| `selection/scoring` | MultiFactor / Selector |
| `weight_policy_ref` | MoneyManager / AllocateFunds Adapter |
| 市场规则滑点 | Slippage Adapter |
| 多股票运行 | Portfolio |

平台保留 StrategySpec 权威语义。某个 DSL 节点无法精确编译时必须失败，不允许静默替换成近似 Hikyuu 组件。

## 17. 版本生命周期

```text
draft → validated → previewed → approved → active → retired
```

- 修改任何策略语义都创建新版本；
- 已产生正式 BacktestRun 的版本不可覆盖；
- `previewed` 绑定 applied spec Hash，修改 draft 后旧预览 stale；
- approved/active 需要明确审批记录；
- retired 版本仍可复现历史结果；
- Preview、Backtest 和 Paper Portfolio 使用相同 ResolvedSpec 和 Compiler。

## 18. 持久化模型

| 表/产物 | 内容 |
| --- | --- |
| `strategy` | 稳定策略身份和所有者 |
| `strategy_version` | 原始 Spec、状态、父版本和说明 |
| `resolved_strategy_spec` | 展开默认值的不可变配置及 Hash |
| `strategy_compile_plan` | Feature/Hikyuu 组件依赖和编译诊断 |
| `strategy_approval` | 审批人、时间、版本和环境 |
| `strategy_preview` | applied spec、输入快照、结果摘要和 stale 状态 |
| `strategy_plugin_version` | 插件代码与依赖 Hash、权限和资源限制 |

## 19. Schema 草案要点

正式 JSON Schema 至少实施：

```text
additionalProperties = false
id/version 使用稳定正则
strategy_type 使用封闭 enum
DSL 使用 oneOf 判别联合
所有数值配置声明 min/max
所有引用使用 id@version
required 随 strategy_type 条件化
plugin 与 declarative 字段互斥
```

ResolvedSpec 不能依赖 Schema 默认值隐式补全；Resolver 必须把默认值写进产物，保证不同语言实现获得同一 Hash。

## 20. 验收测试

1. 同一 StrategySpec 解析后产生相同 ResolvedSpec 和 Hash；
2. Preview、正式回测和模拟组合对同一日期产生相同候选、分数和信号；
3. 未登记指标、任意代码和未知 AST 节点被拒绝；
4. T 日策略无法引用 T+1 事实；
5. 筛选、评分、入场和退出输出分别落地；
6. score breakdown 逐项可复算；
7. 相同分数使用稳定 tie-break；
8. `empty_signal_action=hold/exit_all` 各有明确回归；
9. 风险退出优先于策略买入；
10. 市场规则拒绝不会被策略覆盖；
11. 修改 draft 后旧 Preview 标记 stale；
12. approved/active 版本不可原地修改；
13. Plugin 无网络/文件/数据库权限且资源超限会终止；
14. Sequoia 均线放量、海龟和 RPS 的新旧规则在固定样本上生成差异报告；
15. Compiler 失败不会退化为另一套页面或 Python 计算逻辑。

## 21. 实施顺序

1. 定义 JSON Schema、AST 类型和 Resolver；
2. 实现 Indicator Registry 引用和依赖解析；
3. 实现 pool/scoring/selection/entry/exit 解释器；
4. 实现 Hikyuu Compiler 和编译诊断；
5. 迁移 Sequoia 均线放量并打通 Preview/Backtest；
6. 迁移海龟和 RPS，补齐排名退出和止损；
7. 实现受控插件接口；
8. 接入 Strategy UI、版本生命周期和审批。

## 22. 参考资料

- [Hikyuu 系统策略和组件](https://hikyuu.readthedocs.io/zh-cn/latest/trade_sys/system.html)
- [Hikyuu 止损/止盈策略](https://hikyuu.readthedocs.io/zh-cn/latest/trade_sys/stoploss.html)
- [Hikyuu 投资组合](https://hikyuu.readthedocs.io/zh-cn/latest/trade_portfolio/trade_portfolio.html)
- [Sequoia-X 项目和策略列表](https://github.com/sngyai/Sequoia-X)
- [Sequoia-X 策略基类](https://github.com/sngyai/Sequoia-X/blob/master/sequoia_x/strategy/base.py)
- [Sequoia-X 均线放量策略](https://github.com/sngyai/Sequoia-X/blob/master/sequoia_x/strategy/ma_volume.py)
- [Fleur 策略回测和 RuleVersionSpec 分层](https://github.com/WackyGem/Fleur/blob/main/docs/RFC/archive/0028-racingline-strategy-backtest-step5.md)
- [A 股回测市场规则 v1](backtest-market-rules-v1.md)
- [评分、仓位与自动权重优化架构](weight-optimization-architecture.md)
- [A 股板块异动、热门观察与策略评分边界 v1](sector-observation-and-strategy-scoring-architecture.md)
- [全球市场观察与 A 股策略隔离架构 v1](global-market-observation-boundary.md)
- [A 股 Feature Store 与指标注册中心架构 v1](feature-store-architecture.md)
