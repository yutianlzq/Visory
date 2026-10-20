# WP-0303-PREP：市场宽度与情绪 F2 输入、契约与验收清单

最后核验：2026-10-08

## 1. 结论

**WP-0303-IMPLEMENTATION 判定：`CONDITIONAL_GO`。** 可以启动一个受限实现 Goal，范围只包括已经收敛的 C-006 Definition、受控 Builtin、依赖 DAG、隔离 fixture 物化、PIT/Hash/缺失/warming-up/状态迁移和 Correction 回归；不得把该启动判定解释为完整五维评分已具备正式数据输入或生产认证。

**`market_breadth` 与完整 `market_emotion` Formal 能力当前均为 `NO_GO`**，剩余四个 `BLOCKER`：

1. 当前 Dataset Catalog 和正式 `DatasetDefinition` 均没有 PIT 流通市值输入，`small_large_return_spread` 无法正式计算；
2. `turnover_ratio@1.0.0` 与 `DEFAULT_DATASET_CATALOG` 引用了 `security_master.shares_outstanding`，但实际 `security_master@1.0.0` `DatasetDefinition`、Provider Raw Schema 和 Mapping 均未声明该字段，`high_turnover_return_spread` 的上游契约未闭合；
3. `return_point_in_time_adjusted@1.0.0` 与 Resolver Catalog 要求 `corporate_action.factor`，实际 `corporate_action@1.0.0` 只有 `ratio/cash_amount/action_type`，没有可直接消费的 PIT adjustment factor，也没有从公司行动推导 factor 的已认证方法版本；所有要求 PIT 调整收益/价格序列的市场宽度和情绪输入不能正式执行；
4. Resolver `DEFAULT_DATASET_CATALOG` 与实际 DatasetDefinition 还存在 `instrument_status_daily` 字段名（`trade_date/trading_status` 对 `status_date/instrument_status/is_tradable`）以及 `benchmark_index_1d.return_type` 投影缺失；实现前必须同步并增加一致性测试，不能让 Resolver 的“可解析”替代真实 Dataset 契约。

在四个 BLOCKER 关闭前，只能发布契约已闭合的审计、涨跌停和部分流动性原始指标；依赖 PIT 调整序列的市场宽度/风险输入、风险偏好维度、总分、平滑分和状态必须保持缺失，FeatureSnapshot 不得认证 `market_breadth` 或 `market_emotion`。本 PREP 不增加已验收 WP 数量；WP-0303 继续为 `NOT_STARTED`，不得标记 `VERIFIED` 或 `RELEASED`。

## 2. 目标、非目标与基线

### 2.1 目标

- 在已合入的 WP-0301 Indicator Registry/DAG 和 WP-0302 Feature Store 上收敛 F2，不建立第二套 Registry、Store、Mart 或发布链；
- 固定市场聚合身份、冻结股票池、Definition/输出/Hash/PIT/保留/Correction、标准化、五维合成、平滑和状态迁移契约；
- 给出可直接转成实现测试的输入矩阵、反例和验证顺序；
- 将“契约可执行”“仅能 fixture 验证”“上游阻断”和“生产认证”分开记录。

### 2.2 非目标

- 不实现 WP-0207、WP-0304、WP-0305、市场页面、资金引擎、Hikyuu Cache、API/桌面端消费或生产调度；
- 不连接真实 Provider、生产数据库、真实 `/data` 或部署环境，不伪造历史 `available_at`、流通市值、首封时间或认证能力；
- 不改动全球市场观察边界；全球 Dataset/Definition 不得进入 A 股 FeatureDependencyPlan；
- 不修改 manifest、lockfile、生成文件或依赖声明。

### 2.3 当前实现与远程证据

- 指定起点、当前 `HEAD` 和实时 fetch 后 `origin/main` 均为 `efe8e9b362cba13eca183c55be57bbbbc832b60b`，差异 `0 behind / 0 ahead`，工作树初始干净；
- PR [#41](https://github.com/yutianlzq/Visory/pull/41) 已普通合并：head `1892b7a687e342ad7b0a698a2ca8054717ae6255`，base `6aa9fa82e31ad0ad175cc1f6650ad7db67fa0222`，merge SHA `efe8e9b362cba13eca183c55be57bbbbc832b60b`，`merged_at=2026-10-07T15:38:31Z`；
- 合入后 Run [37645716721](https://github.com/yutianlzq/Visory/actions/runs/37645716721) 为 `workflow_dispatch / main / efe8e9b... / completed / success`；Governance `112875831265`、Python deterministic gate `112875830855`、Web lint and build `112875831010` 均成功；
- `default_indicator_registry()` 当前只装载 `F1_INDICATOR_DEFINITIONS`；Resolver 和直接 Materializer 均强制 `domain=a_share`，并拒绝全球 Dataset Catalog；
- `FeatureRow` 只有一个 `value`，唯一键为 `entity_key + trade_date + indicator_id + definition_version`；当前 FeatureStore 只接受单输出且 alias 为 `value`；
- `FeatureSnapshot` 已固定 Definition/Partition 引用、Capability、Manifest Hash、revision/correction/supersedes lineage；同一逻辑 Manifest 的 Correction 不得改变 `as_of_trade_date`、`cutoff_at` 或 `dependency_plan_hash`。

权威路由：[实施路线](implementation-roadmap-and-acceptance-v1.md)、[C-006](platform-implementation-contract-catalog-v1.md#5-c-006-indicator与feature)、[Feature Store 架构](feature-store-architecture.md)、[市场情绪与资金行为架构](market-sentiment-and-capital-flow-architecture.md)、[Canonical Data Contract](data-platform-and-canonical-contract.md)、[DataSnapshot 与 Capability](data-snapshot-and-capability.md)。

## 3. 固定股票池、聚合身份与分母

### 3.1 适用域和聚合身份

- Definition 的 `domain` 固定为 `a_share`。架构文档中的旧示例 `domain: market` 仅表达业务语义，不能复制到当前 Resolver；
- `market_scope_id` 固定为 `cn_a_equity_v1`，只覆盖沪深主板、创业板、科创板日线股票；北交所、ETF、指数和全球输入默认不进入该 scope；范围变化必须提升股票池 policy/Definition 版本；
- C-006 允许 Feature 逻辑行使用 `entity_key or aggregate_key`。当前 `FeatureRow` 字段名仍为 `entity_key`，市场行在该字段保存稳定逻辑 `aggregate_key=aggregate:cn_a_equity_v1`；该值不是资产身份，不进入 Asset Identity Registry，不得传给 `parse_entity_key()`；
- 所有原始指标、标准化分、维度分、总分、平滑分和状态均使用同一聚合键。不同市场范围不得共享该键。

### 3.2 冻结股票池

每日生成一个 `market_scope_manifest@1.0.0`，至少包含：

```text
market_scope_id / policy_version / trade_date
sorted listed entity_keys
per-entity listed/bar_valid/tradable_observation/limit_rule flags
ST/new_listing/suspended/excluded reason codes
source DataSnapshot/Partition refs
```

对 canonical JSON 计算 `universe_scope_hash`。所有 WP-0303 Definition 使用 `universe_policy=FROZEN_REQUIRED`，同一交易日的派生子池均来自该 Manifest；不同 Hash 必须形成不同 FeatureInstance/Partition identity，禁止同一 Partition 混合股票池。

固定子池与分母：

| 名称 | 成员 | 用途 |
| --- | --- | --- |
| `listed_universe` | T 日已上市且未退市 | `listed_count`、停牌/零成交比例和 DataSnapshot 覆盖率分母 |
| `bar_valid_universe` | 有有效 Bar 或显式停牌状态 | `bar_valid_count` 和核心行情覆盖率 |
| `tradable_observation_universe` | 有有效 `prev_close` 和当日 Bar，且非停牌 | 收益、振幅、成交额、宽度和风险偏好默认分母 |
| `limit_rule_universe` | 当日 `price_limit_up/down` 完整且规则可判定 | 涨跌停生态分母 |
| 指标专属 eligible set | 由该指标 Definition 的历史、字段和候选条件确定 | 必须发布独立 `valid_count`/`denominator_count`，不得复用其他指标分母 |

质量基线沿用 DataSnapshot SLA：`bar_or_suspended_status_coverage >= 0.998`、`max_excluded_instrument_ratio <= 0.002`、`max_excluded_instrument_count <= 10`。任一指标分母为零、关键字段/PIT/单位/Hash 不合格时，该指标值为空并写明确 reason code；不把分母零转换为零值。

## 4. 输入状态定义

| 状态 | 含义 |
| --- | --- |
| `EXECUTABLE` | 当前正式 Dataset/F1 契约足以编写受控 Builtin 并做隔离 fixture 验收；不代表真实历史数据或生产能力已认证 |
| `FIXTURE_ONLY` | 可用合成 fixture 验证算法边界，但缺少可用于正式物化的上游字段/方法契约；不得进入 Capability 认证 |
| `BLOCKED` | 缺少综合分必需的正式上游契约；可以注册为不可用 Definition/反例，但不得以替代字段、补零或前向填充绕过 |

所有 Definition 初始 `definition_version=1.0.0`、`frequency=1d`、`materialization=F2_LONG_TERM`、`point_in_time=true`、单输出 `value`。`definition_hash` 必须覆盖公式引用、受控 Builtin 实现版本、输入 Definition/Dataset、参数、方向、股票池/分母、lookback/warmup、null/normalization policy；任何数值语义变化提升版本，旧版本不可原地改写。

## 5. 指标输入矩阵

### 5.1 审计分母与覆盖率

| Definition `@1.0.0` | 公式/输出 | 输入 | 股票池/分母 | PIT、warmup、质量与缺失 | 状态 |
| --- | --- | --- | --- | --- | --- |
| `market.sentiment.audit.listed_count` | `count(listed_universe)`，integer | `security_master`、`listing_status_history`、`instrument_status_daily` | frozen `listed_universe` | `available_at<=cutoff_at`；0 日；身份/上市区间冲突即缺失 | EXECUTABLE |
| `market.sentiment.audit.bar_valid_count` | `count(bar_valid_universe)`，integer | 上述 + `bar_1d_raw.trading_status` | `listed_count` | 0 日；同时发布 `bar_valid_count/listed_count` | EXECUTABLE |
| `market.sentiment.audit.valid_return_count` | 可计算 PIT 日收益的股票数 | `return_point_in_time_adjusted`、停牌状态 | `tradable_observation_universe` | 1 日；当前 `corporate_action.factor` 契约未闭合 | BLOCKED |
| `market.sentiment.audit.limit_rule_count` | `count(limit_rule_universe)` | `bar_1d_raw.price_limit_up/down` | `listed_universe` | 0 日；规则未知不猜测 | EXECUTABLE |

每个下表比例/中位数/分位组指标还必须有同名诊断 `valid_count` 和 `coverage_ratio=valid_count/denominator_count`；它们作为独立单值 Definition 或确定性质量报告字段实现，不把多个输出塞入一条 FeatureRow。

### 5.2 市场宽度

| Definition `@1.0.0` | 公式 | 输入 Dataset/F1 字段 | 股票池/分母 | PIT、lookback/warmup、质量与缺失 | 状态 |
| --- | --- | --- | --- | --- | --- |
| `market.sentiment.breadth.advance_count` / `decline_count` / `flat_count` | PIT 调整收益按 `>0/<0/=0` 计数 | `return_point_in_time_adjusted.value` | `tradable_observation_universe` / `valid_return_count` | 当前 adjustment factor/method 未进入实际 DatasetDefinition | BLOCKED |
| `market.sentiment.breadth.net_advance_ratio` | `(advance-decline)/valid_return_count` | 上述计数 | `valid_return_count` | 1/0 日；分母 0 为缺失 | BLOCKED |
| `market.sentiment.breadth.advance_decline_log` | `ln((advance+1)/(decline+1))` | 上述计数 | `valid_return_count` | 1/0 日；计数必须来自同一冻结池 | BLOCKED |
| `market.sentiment.breadth.median_return` | PIT 调整收益中位数 | `return_point_in_time_adjusted.value` | `valid_return_count` | 1/0 日；Decimal 稳定排序 | BLOCKED |
| `market.sentiment.breadth.above_ma20_ratio` | `close_adjusted(T)>MA20_adjusted(T)` 比例 | PIT adjustment factor/method、`bar_1d_raw.close` | 具备 20 日 PIT 调整序列的 `tradable_observation_universe` | 20/20 日；当前 `moving_average@1.0.0` 使用未调整 close，且实际 corporate_action 无 `factor` | BLOCKED |
| `market.sentiment.breadth.above_ma60_ratio` | 同上，窗口 60 | 同上 | 具备 60 日历史的 eligible set | 60/60 日；不足历史排除并记录覆盖率 | BLOCKED |
| `market.sentiment.breadth.new_high_low_spread_20` | `(20日新高数-20日新低数)/eligible_count` | PIT 调整 high/low/close 序列 | 具备 20 日历史的 eligible set | 20/20 日；不能用未认证 factor 或当前复权因子回填历史 | BLOCKED |

### 5.3 涨跌停生态

| Definition `@1.0.0` | 公式 | 输入 | 股票池/分母 | PIT、lookback/warmup、质量与缺失 | 状态 |
| --- | --- | --- | --- | --- | --- |
| `market.sentiment.limit.limit_up_count` / `limit_down_count` | `close>=price_limit_up` / `close<=price_limit_down` 计数 | `bar_1d_raw.close/price_limit_up/price_limit_down`、`price_limit_state` | `limit_rule_universe` | 1/0 日；价格/规则未知即排除 | EXECUTABLE |
| `market.sentiment.limit.limit_up_down_spread` | `(up-down)/limit_rule_count` | 上述计数 | `limit_rule_count` | 1/0 日；分母 0 为缺失 | EXECUTABLE |
| `market.sentiment.limit.limit_break_count` | `high>=price_limit_up && close<price_limit_up` | `bar_1d_raw.high/close/price_limit_up` | `limit_rule_universe` | 1/0 日；仅定义日线炸板，不推断首封时刻 | EXECUTABLE |
| `market.sentiment.limit.limit_break_rate` | `break_count/(limit_up_count+break_count)` | 上述 | 实际触板股票 | 1/0 日；分母 0 为缺失，不为 0 | EXECUTABLE |
| `market.sentiment.limit.max_streak_height` | 当日收盘涨停股票连续涨停交易日最大值 | 版本化 `price_limit_state` 历史、`trading_calendar` | 当日涨停股票 | 至少回看至连续序列起点；无涨停时值 0，规则缺口导致未知 | EXECUTABLE |
| `market.sentiment.limit.streak_stock_count` | 连续涨停天数 `>=2` 的股票数 | 同上 | 当日涨停股票 | 2/2 日起；规则历史不完整的个股排除 | EXECUTABLE |
| `market.sentiment.limit.promotion_rate` | T-1 连板候选在 T 日晋级数 / T 日可观察候选数 | T-1 streak、T 日 limit state/status | T-1 已冻结候选队列 | 2/2 日；禁止用 T 日最终连板池反构分母 | EXECUTABLE |
| `market.sentiment.limit.early_seal_ratio` | 指定时点前首次封板且收盘封住比例 | 可靠 first-seal timestamp | 有首封时间的触板股票 | 当前无上游字段；输出缺失 + `SOURCE_UNAVAILABLE`，且不进入 v1 总分 | FIXTURE_ONLY |

### 5.4 风险偏好

| Definition `@1.0.0` | 公式 | 输入 | 股票池/分母 | PIT、lookback/warmup、质量与缺失 | 状态 |
| --- | --- | --- | --- | --- | --- |
| `market.sentiment.risk_appetite.prior_limit_up_premium` | T-1 收盘涨停股票 T 日 PIT 调整等权收益 | T-1 `price_limit_state`、T `return_point_in_time_adjusted` | T-1 涨停且 T 可观察股票 | 2/2 日；候选在 T-1 冻结；adjustment contract 缺失 | BLOCKED |
| `market.sentiment.risk_appetite.high_turnover_return_spread` | T 日换手率最高 20%股票收益中位数 - 全市场收益中位数 | `volume_shares`、PIT `shares_outstanding`、PIT 调整收益 | 可计算换手率的 `tradable_observation_universe` | 1/0 日；分位边界使用稳定 `entity_key` 次序；`security_master` 正式契约缺字段 | BLOCKED |
| `market.sentiment.risk_appetite.small_large_return_spread` | PIT 流通市值最低 30%与最高 30%股票的等权收益差 | PIT free-float market cap、PIT 调整收益 | 同日有效流通市值股票 | 1/0 日；禁止总市值/当前市值/未来回填替代 | BLOCKED |
| `market.sentiment.risk_appetite.top_amount20_median_return` | `amount_cny` 前 20 股票的 PIT 调整收益中位数 | `bar_1d_raw.amount_cny`、PIT 调整收益 | `tradable_observation_universe` | 1/0 日；并列按 `amount desc, entity_key asc` 固定 | BLOCKED |
| `market.sentiment.risk_appetite.strong_stock_survival_ratio` | T-1 收益前 10%股票中，T 日收益高于 T 日市场中位数的比例 | T-1/T PIT 调整收益 | T-1 冻结候选且 T 可观察 | 2/2 日；解释指标，不进入 v1 总分 | BLOCKED |

### 5.5 流动性

| Definition `@1.0.0` | 公式 | 输入 | 股票池/分母 | PIT、lookback/warmup、质量与缺失 | 状态 |
| --- | --- | --- | --- | --- | --- |
| `market.sentiment.liquidity.market_amount_cny` | `sum(amount_cny)` | `bar_1d_raw.amount_cny` | 有有效金额的 `bar_valid_universe` | 1/0 日；只含 A 股股票，金额单位 CNY | EXECUTABLE |
| `market.sentiment.liquidity.amount_ratio_20` | T 日市场成交额 / T-1 前 20 个有效交易日均值 | 上述 F2 历史、`trading_calendar` | 同一 scope 历史 | 21/20 日；分母窗口严格截止 T-1 | EXECUTABLE |
| `market.sentiment.liquidity.rising_amount_share` | 上涨股票成交额 / 有效股票总成交额 | PIT 调整收益、`amount_cny` | 有收益且金额有效的股票 | 1/0 日；总额 0 为缺失 | BLOCKED |
| `market.sentiment.liquidity.top20_amount_concentration` | 成交额前 20 / 总成交额 | `amount_cny` | 有效金额股票 | 1/0 日；稳定 tie-break；解释指标 | EXECUTABLE |
| `market.sentiment.liquidity.zero_or_suspended_ratio` | 零成交或停牌股票 / `listed_count` | `volume_shares`、`trading_status`、instrument status | `listed_universe` | 1/0 日；状态缺失不是停牌 | EXECUTABLE |

### 5.6 波动与风险

| Definition `@1.0.0` | 公式 | 输入 | 股票池/分母 | PIT、lookback/warmup、质量与缺失 | 状态 |
| --- | --- | --- | --- | --- | --- |
| `market.sentiment.risk.median_amplitude` | median(`(high-low)/prev_close`) | `bar_1d_raw.high/low/prev_close` | `tradable_observation_universe` | 1/0 日；`prev_close<=0` 排除；解释指标 | EXECUTABLE |
| `market.sentiment.risk.return_dispersion_mad` | PIT 调整收益的 MAD | PIT 调整收益 | `valid_return_count` | 1/0 日；无有效样本为缺失 | BLOCKED |
| `market.sentiment.risk.benchmark_realized_vol_20` | 固定基准日收益 20 日样本标准差 × `sqrt(252)` | `benchmark_index_1d` 的固定 `benchmark_id=index:cn:000300.SH`、`return_type=PRICE`、`close` | 单一基准序列 | 21/20 日；实际 Dataset 有 `return_type`，Resolver Catalog 尚未投影 | FIXTURE_ONLY |
| `market.sentiment.risk.tail_loss_ratio` | PIT 调整收益 `<=-0.05` 数 / `valid_return_count` | PIT 调整收益 | `tradable_observation_universe` | 1/0 日；阈值包含 -5% | BLOCKED |
| `market.sentiment.risk.market_drawdown_20` | `close(T)/max(close[T-19..T])-1` | 同一固定基准 `close` | 单一基准序列 | 20/20 日；解释指标；需先同步 benchmark Catalog 口径 | FIXTURE_ONLY |

基准从当前 backtest_core fixture 和契约示例固定为 `index:cn:000300.SH / PRICE`。若产品要求更换基准或使用 TOTAL_RETURN，必须提升相关 Definition/ScoreDefinition 版本，不可在同版本运行时切换。

## 6. 标准化、维度、总分与输出

### 6.1 标准化

每个进入维度分的原始指标都有独立 `market.sentiment.normalized.<metric>@1.0.0` Definition：

```text
history = 最多 252 个、严格截止 T-1 的历史有效原始值
robust_z = (x(T) - median(history)) / (1.4826 * MAD(history) + epsilon)
metric_score = clip(50 + clip(direction * robust_z, -3, 3) * 100 / 6, 0, 100)
```

- `epsilon` 固定为 Decimal `1e-12`，只防止 MAD 为零，不替代缺失输入；
- 历史有效观察少于 60 条时：原始指标正常发布，标准化 FeatureRow `value=null`、`data_flags=[WARMING_UP]`；不得发布维度分、总分、平滑分或状态；
- 标准化窗口不能包含 T 值，不能使用全样本统计量；Correction 只能读取该 revision 在相应 cutoff 可见的历史；
- 风险维度相关指标使用 `direction=negative`；`limit_break_rate` 也取反。原始事实值不反写。

### 6.2 固定维度权重

| 维度 Definition `@1.0.0` | 必需标准化输入及权重 |
| --- | --- |
| `market.sentiment.score.breadth` | `net_advance_ratio 30% + above_ma20_ratio 25% + above_ma60_ratio 15% + new_high_low_spread_20 15% + median_return 15%` |
| `market.sentiment.score.limit` | `limit_up_down_spread 30% + reverse(limit_break_rate) 25% + max_streak_height 20% + promotion_rate 25%` |
| `market.sentiment.score.risk_appetite` | `prior_limit_up_premium 30% + high_turnover_return_spread 25% + small_large_return_spread 20% + top_amount20_median_return 25%` |
| `market.sentiment.score.liquidity` | `amount_ratio_20 60% + rising_amount_share 40%` |
| `market.sentiment.score.safety` | `reverse(tail_loss_ratio) 40% + reverse(return_dispersion_mad) 30% + reverse(benchmark_realized_vol_20) 30%` |

任一必需输入缺失或 warming up 时，对应维度 `value=null` 并保存缺失指标 ID；不补零、不沿用昨日值、不对剩余指标重新加权。

### 6.3 总分、平滑和状态 Definition

| Definition `@1.0.0` | 输出/公式 | 缺失语义 |
| --- | --- | --- |
| `market.sentiment.score.emotion_raw` | `breadth*0.25 + limit*0.30 + risk_appetite*0.20 + liquidity*0.15 + safety*0.10`，decimal score | 任一维度缺失则 null |
| `market.sentiment.score.emotion_smoothed` | 首个完整日或缺失断点后的首个完整日 `smoothed(T)=raw(T)`；其他连续完整日 `0.5*raw(T)+0.5*smoothed(T-1)` | 不跨缺失/warming-up 日延用旧值 |
| `market.sentiment.regime.state` | `PANIC/WEAK/RANGE/ACTIVE/OVERHEATED`，string | raw/smoothed 缺失则 null |
| `market.sentiment.regime.transition_from` | 发生迁移时的前状态，否则 null | 缺失日 null |
| `market.sentiment.regime.transition_trigger` | `INITIALIZED/TWO_DAY_CONFIRM/BOUNDARY_JUMP_GE_5/NONE` | 缺失日 null |

每个对象仍是一条独立单输出 FeatureRow；Definition input refs 和 Hash 固定 ScoreDefinition 版本，不创建多字段“情绪行”。F2 分区默认长期保留；被 Formal Bundle 引用后由现有 FeatureStore 提升为 `PINNED`。

### 6.4 状态迁移确定算法

基础区间固定为 `[0,20) PANIC`、`[20,40) WEAK`、`[40,60) RANGE`、`[60,80) ACTIVE`、`[80,100] OVERHEATED`。

1. 首个完整有效平滑分，或任何缺失/warming-up 断点后的首个完整有效平滑分，直接初始化为其所在状态，trigger=`INITIALIZED`；
2. 候选区间与当前状态相同：保持状态并清空待确认计数；
3. 候选区间不同，若向上时 `score-current_upper_boundary >= 5`，或向下时 `current_lower_boundary-score >= 5`，在当日直接迁移到候选区间；恰好 5 分满足条件，允许跨多级，trigger=`BOUNDARY_JUMP_GE_5`；
4. 未达到 5 分的变化只可能在相邻区间；同一相邻候选必须连续两个开放交易日出现，第二日迁移，trigger=`TWO_DAY_CONFIRM`；方向或候选区间变化重置计数；
5. 缺失、warming-up、非开放日不生成有效候选；缺失/warming-up 打断连续计数和递归平滑链，禁止沿用上一状态。非开放日不占交易日序列；
6. Correction 从最早受影响交易日起重算所有后续 `emotion_smoothed`、pending transition 和 state，直到序列末端或值与旧 revision 的递归状态完全收敛；始终发布新 Partition/Snapshot revision，不覆盖旧引用。

## 7. Capability 与正式消费门禁

当前 `IndicatorDefinition.capability_id` 是输入解析门禁，不是“该 Definition 产出的能力”。F2 Definition 的 prerequisite 使用现有 `backtest_core`（以及实际所需 Dataset capability）；输出能力由 FeatureSnapshot 在全部质量检查后认证：

### `market_breadth`

仅在以下条件同时满足时加入 `certified_capabilities`：冻结 `market_scope_manifest` 与 Hash 完整；`backtest_core`、身份、日历、状态和行情 PIT 通过；DataSnapshot 覆盖率达到 SLA；第 5.2 节全部必需宽度指标及其分母/coverage 非空、Definition/Partition Hash 一致。当前 B3 未关闭，因此 `market_breadth` 必须在 `missing_capabilities`；已成功原始行可保留为 PROVISIONAL/诊断证据。

### `market_emotion`

仅在五个维度、raw、smoothed、state 全部非空且非 warming-up，输入 Capability/PIT/质量/Hash/冻结股票池全部通过时认证。任何必需指标或维度缺失时：

- 保留已成功的原始指标、标准化分和完整维度；
- `market_emotion` 放入 `missing_capabilities`，总分/平滑/状态为空；
- Formal/Paper ConsumerRequirement 和 FeatureBundle 必须要求 `CERTIFIED market_emotion`、完整且已发布的 Snapshot/Partition；拒绝未认证、晚于 cutoff、PARTIAL/UNAVAILABLE 或动态“最新”引用；
- Preview 可显式接受 PROVISIONAL，但必须显示缺失 ID 和状态，不得退化为补零、昨日值或动态重加权。

## 8. 预期实现范围

允许的最小范围：

- 在现有 `src/services/platform/indicator_registry.py`/同模块受控拆分中注册 F2 Builtin 和 Definition；扩展现有 Registry，不建立 MarketMetricRegistry；
- 使用现有 `FeatureDependencyResolver`、`FeatureStore`、`FeatureRepository`、FeatureSnapshot/Bundle；如需市场聚合辅助类型，只能是 C-006 内部确定性计算对象，不建平行发布链；
- 增加 Definition/DAG、输入字段、冻结股票池、PIT、分母、标准化、权重、缺失、状态机、Correction 和 Hash 的平台测试/Golden；
- 必要时同步 C-006/Feature Store/市场情绪专题和 `docs/CHANGELOG.md`；无用户可见页面，不要求 UI 截图。

默认不需要 Migration、API、Web、Desktop、调度或 Provider 连接。关闭四个上游 BLOCKER 必须另行授权 Data Platform 契约扩展；不得夹带到受限 WP-0303 实现中。

## 9. 回归反例与验收顺序

### 9.1 必须失败或保持缺失的反例

1. `domain=market/global` Definition、全球 Dataset 或扩大 `allowed_domains` 进入 A 股 plan；
2. 缺 `universe_scope_hash`、同一计划/分区混用两个冻结股票池、T 日用当前股票池回算历史；
3. 比例分母为零却输出 0，或多个指标隐式共用分母；
4. 用未调整 close 冒充 PIT MA/新高新低，用 T 日最终连板池反构 `promotion_rate`；
5. 用当前/总市值替代历史流通市值，或在 `security_master` 未声明 `shares_outstanding` 时放行换手率；
6. 用 OHLC 推断首封时间；
7. 标准化窗口包含 T 或未来值、历史有效观察少于 60 却发布 score；
8. 缺一维时补零、昨日值或重新加权后发布总分/状态；
9. 临界值单日不足 5 分立即迁移、恰好 5 分未迁移、缺失日仍累计“两日确认”；
10. Correction 覆盖旧分区、改变逻辑 Manifest identity，或只重算当日不传播到后续平滑/状态；
11. 未认证 `market_emotion` 被 Formal Bundle 消费，或查询“最新”绕过固定 Snapshot/Partition 引用。

### 9.2 实现 Goal 验证顺序

1. Registry/Builtin/Definition Hash、字段存在性、`domain=a_share`、FROZEN_REQUIRED 和全球 fail-closed 单元测试；
2. 每个原始指标的 deterministic fixture、分母、边界、PIT、lookback/warmup 和缺失测试；
3. 严格 T-1 标准化、固定权重、缺失传播、平滑初值/断点和状态边界参数化测试；
4. FeaturePartition 唯一键/Schema/coverage/Hash、Snapshot Capability、Bundle Formal 阻断和 Correction 尾部传播；
5. 现有 Feature Store/PostgreSQL 回归，Contract/Golden/generated `--check`；
6. `python scripts/check_ai_assets.py`、`python scripts/check_visory_baseline.py`、`./scripts/ci_gate.sh`、Web lint/build（仅在 generated/API 联动时）和 `git diff --check`；
7. PR 当前 HEAD 的 Governance/Python/Web 三项阻断 CI。fixture 通过不等于真实 Provider、历史物化或生产认证。

## 10. 兼容性、回滚与问题分级

### 10.1 兼容性

- 仅追加 F2 Definition/Partition；F1、现有 Snapshot/Bundle 和旧 Definition 引用不改写；
- `aggregate:cn_a_equity_v1` 是 C-006 aggregate key 在当前 `FeatureRow.entity_key` 字段中的兼容表示，不扩展 `AssetType`；未来若 Schema 增加显式 `aggregate_key`，需新 schema/迁移和双读计划，不能原地重解释历史 Hash；
- 公式、基准、股票池、分母、方向、epsilon、标准化、权重或状态边界变化均提升版本；
- 当前没有 runtime API/Web/Desktop 消费方，PREP 不承诺其兼容迁移。

### 10.2 回滚

- PREP 为文档变更，回滚只需撤销本文件、索引、状态和 CHANGELOG 的对应文档差异，不修改数据库或数据面；
- 未来实现回滚必须 revert 完整 WP-0303 change set，保留 WP-0301/0302 和旧不可变 F2 revision；不得 reset、force-push、删除固定 Parquet 或把 Bundle 重绑“最新”；
- 若未来新增 Migration，必须在实现 Goal 中另写独立备份/降级方案，本 PREP 不授权执行。

### 10.3 问题分级

**BLOCKER**

- B1：缺少 PIT 流通市值 Dataset/字段、Provider Schema/Mapping、质量与 `available_at` 契约；阻断 `small_large_return_spread`、风险偏好维度和完整 `market_emotion`；
- B2：`shares_outstanding` 只存在于 Resolver Catalog/F1 引用，未进入实际 `security_master@1.0.0` DatasetDefinition/Raw Schema/Mapping；阻断 `high_turnover_return_spread`、风险偏好维度和完整 `market_emotion`；
- B3：`corporate_action.factor` 只存在于 Resolver Catalog/F1 引用，实际 DatasetDefinition 只有 action `ratio/cash_amount`；在受控 adjustment factor/method 契约形成前，阻断 PIT 调整收益/价格序列、`market_breadth` 和完整 `market_emotion`；
- B4：Resolver Catalog 与实际 `instrument_status_daily` 字段及 `benchmark_index_1d.return_type` 不一致；实现 Goal 必须先做单一 Catalog 来源或一致性校验，未同步前相关 Definition 只可 fixture 验证。

**FOLLOW-UP**

- F1：若要正式启用 `early_seal_ratio`，需另行授权可靠逐笔/事件级首封时间 Dataset；当前保持 unknown 且不进入 v1 总分；
- F2：未来显式 `aggregate_key` Schema 可消除当前字段名兼容表示，但不得为 WP-0303 建第二套 FeatureRow；
- F3：真实 Provider 历史覆盖、生产物化、调度、性能和运行观察属于后续认证，不由 fixture 替代。

**NOTE**

- N1：`early_seal_ratio`、`top20_amount_concentration`、`strong_stock_survival_ratio`、`market_drawdown_20`、`median_amplitude` 为解释指标，不进入 v1 综合分；
- N2：WP-0302 已合入 main 且验收计数为 `15/45`；WP-0207 仍 `IN_PROGRESS`，生产仍 `NOT CERTIFIED`、`RELEASED=false`；本 PREP 不改变这些状态。

## 11. 2026-10-15 Goal 重排：Endpoint Admission 先于真实输入接入

基于固定的 `a-stock-data` 参考实现，WP-0303 的完整完成定义不变，但剩余工作必须先补 C-004 来源准入层，再逐 Endpoint 审核真实材料。完整阶段、对象关系和下一 Goal 见 [WP-0303-FULL-INPUT-TO-FEATURE-CLOSEOUT Goal v2](WP-0303-FULL-INPUT-TO-FEATURE-CLOSEOUT-GOAL.md)。

原第 8 节“默认不需要 Migration”只约束最初受限 F2 实现，不覆盖独立的 `WP-0303-C004-PROVIDER-ENDPOINT-ADMISSION-CONTRACT`。该 Goal 已追加 0015 的单一后继 `0016_wp0303_provider_endpoint_admission`，持久化四类新对象及 Binding→RawObject 关联；历史 Migration 和旧 `ProviderRun`/`RawObject` 未原地扩展。

阶段 B 已在本地累计工作树完成以下来源准入基础设施：

- `ProviderEndpointDefinition`；
- `AdapterImplementationFingerprint`；
- `SourceAdmissionReceipt`；
- `ProviderEndpointRunBinding`；
- Contract Registry、JSON Schema、成功/拒绝 Golden、PostgreSQL Repository 和同事务包发布；
- Snapshot build、Formal consumer 与 current pointer 对缺 Binding、非 `PIT_CERTIFIED`、Endpoint/范围/Dataset/schema/Hash 不一致、证据/实现漂移、Raw 遗漏和换源复用 Run 的 fail-closed 校验。

阶段 B 的隔离 PostgreSQL 和合成证据只证明准入基础设施可执行，不接入或认证真实 Endpoint，不注册 B1—B4 新 Dataset/Raw Schema/Mapping/Definition，不执行正式 DERIVED/F1/F2/FeatureBundle 发布。下一阶段 C 仍须逐 Endpoint 提交真实 Source Admission 材料；当前 B1—B4 继续 `NO_GO`，两市场能力仍 missing，WP-0303 仍 `IN_PROGRESS`、15/45，生产仍 `NOT CERTIFIED`、`RELEASED=false`。
