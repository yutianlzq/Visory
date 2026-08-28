# Visory 评分、仓位与自动权重优化架构

状态：Design Approved（待实现）
最后更新：2026-08-28

## 1. 文档目的

本文在 Hikyuu 正式回测架构之上，定义评分、因子权重、个股仓位、策略资金和 AI 动态仓位的自动优化体系，覆盖：

1. 全区间最优权重；
2. AI 动态调整仓位；
3. 根据回测最终结果反推权重；
4. 复杂均值方差优化；
5. 多个动态权重机制按确定顺序叠加。

核心结论是：五项能力都可以实现，但必须区分“研究上界”“训练寻优”和“样本外正式回测”。全区间最优及直接用最终回测结果反推的权重含有后验信息，只能用于研究、敏感性分析或产生下一轮候选，不能把同一区间收益标成可部署业绩。

本文描述目标架构，不表示当前代码已经具备这些能力。

## 2. 从 Fleur 与 Hikyuu 吸收什么

### 2.1 Fleur 设计参考

吸收以下模式，不把 Fleur 作为运行时依赖：

- `RuleVersionSpec.scoring.rules` 对评分项和权重做版本化表达；
- `raw_score`、截断后 `score`、`rank` 和 `score_breakdown` 的可解释结果；
- applied/draft 分离，权重修改后旧预览标记 stale；
- 回测重新执行选股、评分、TopN 和建仓，不把浏览器预览当正式结果；
- `equal_weight_capped`、持仓上限、现金保留、费用和滑点等组合约束；
- 异步运行、不可变结果快照、组合账本及诊断信息。

Fleur 的价值主要在评分解释、配置冻结、结果快照和治理边界；本文不假定它已经提供 AI 仓位、均值方差或一体化自动寻优器。

### 2.2 Hikyuu 执行基础

优先复用 Hikyuu 的正式量化组件：

| 能力 | Hikyuu 组件 | 平台用途 |
| --- | --- | --- |
| 固定因子合成 | `MF_Weight` | 固定或外部优化后的因子权重 |
| 等权因子合成 | `MF_EqualWeight` | 基准组和失败降级 |
| 滚动动态因子权重 | `MF_ICWeight` / `MF_ICIRWeight` | 只使用历史窗口的样本外动态因子合成 |
| 多因子选股 | `SE_MultiFactor` / Selector | 按综合分数选择 TopN |
| 等权/固定权重分配 | `AF_EqualWeight` / `AF_FixedWeightList` | 基准组合和已求解权重落地 |
| 按系统得分分配 | `AF_MultiFactor` | 策略或子系统之间按分数配置资金 |
| 滚动系统寻优 | `SYS_WalkForward` | 训练窗口选优、下一测试窗口执行 |
| 资金管理与组合 | MoneyManager / Portfolio | 订单、仓位、资金、费用和组合模拟 |

Hikyuu 负责交易和组合仿真。平台负责运行模式、数据切分、优化目标、AI 契约、均值方差求解、版本快照和泄漏门禁。公开内建资产分配组件未覆盖本文全部约束时，通过平台优化器生成目标向量，再由自定义 `AllocateFundsBase` 适配器或 `AF_FixedWeightList` 输入 Hikyuu；不修改 Hikyuu 内核。

## 3. 权重必须分层

“权重”不能只使用一个字段。至少拆成四层：

| 层 | 名称 | 作用对象 | 主要输出 |
| --- | --- | --- | --- |
| L1 | `factor_weight` | 动量、价值、质量、情绪等因子 | 个股综合分数 |
| L2 | `position_weight` | 单只股票 | 个股目标仓位 |
| L3 | `strategy_weight` | 多个策略/子组合 | 策略资金预算 |
| L4 | `exposure_weight` | 总仓、板块、风格、现金 | 风险敞口和仓位上限 |

AI 的研究置信度单独记为 `research_confidence`，不能直接冒充任何一层资金权重。AI 只有经过 `AIAllocationOverlay`、确定性约束和版本化策略授权后，才可以影响 L2～L4。

推荐职责拆分：

```text
FactorWeightPolicy       因子合成权重
ScorePolicy              原始分、截断分、排名和解释
PositionSizingPolicy     分数到个股基础仓位
StrategyAllocationPolicy 多策略资金分配
AIAllocationOverlay      AI 受限调节量
PortfolioOptimizer       均值方差和交易成本优化
RiskConstraintPolicy     确定性风险投影
WeightComposer           叠加顺序、归一化和快照
```

## 4. 运行模式与可发布性

每次 `OptimizationRun` 必须显式声明模式：

| 模式 | 用途 | 是否允许正式回测 | 是否允许模拟/实盘 |
| --- | --- | --- | --- |
| `static` | 固定因子、等权或人工权重基准 | 是 | 是 |
| `walk_forward_ic` | 滚动 IC 权重 | 是 | 是 |
| `walk_forward_icir` | 滚动 ICIR 权重 | 是 | 是 |
| `walk_forward_tuned` | 训练窗口回测寻优，下一窗口冻结执行 | 是 | 是 |
| `ai_overlay` | 历史事实包驱动的受控 AI 调节 | 是，需离线重放 | 审批后允许 |
| `mean_variance` | 历史估计的均值方差目标仓位 | 是 | 是 |
| `stacked` | 多种机制的确定性组合 | 是 | 审批后允许 |
| `oracle_full_period` | 全区间最优、理论上界 | 否，研究结果单列 | 否 |
| `post_hoc_fit` | 用同一区间最终结果反推权重 | 否，训练结果单列 | 否 |

`oracle_full_period` 和 `post_hoc_fit` 的所有产物强制带：

```text
leakage_class = lookahead_oracle | post_hoc
deployable = false
publishable_as_oos = false
watermark = 研究上界，包含后验信息
```

平台 API、Web、Paper Portfolio 和实盘导出层必须拒绝这两种模式，不能只依赖页面提示。

## 5. 总体处理管线

动态机制不能任意相乘或互相调用。正式顺序固定为：

```text
Point-in-time Data/Feature Snapshot
                │
                ▼
       1. 静态因子基准权重
                │
       2. 滚动 IC/ICIR 调节
                │
       3. 市场状态/策略参数调节
                │
       4. AI 有界调节
                │
                ▼
       标准化因子 → 综合分数 → TopN
                │
                ▼
       5. 分数到基础个股仓位
                │
       6. 策略资金预算
                │
       7. 均值方差/成本优化
                │
       8. 确定性风险约束投影
                │
       9. A 股手数、现金和可交易性修正
                │
                ▼
     Prediction → OrderIntent → Hikyuu Execution
```

风险约束永远拥有最终优先级。AI、回测寻优和均值方差优化都无权越过单股、板块、总仓、流动性、停牌、涨跌停和 T+1 约束。

## 6. 功能一：全区间最优权重

### 6.1 定义

在指定全区间内寻找一个固定权重向量，使目标函数达到最好：

```text
w* = argmax Objective(Backtest(w, start, end))
```

可优化对象包括：

- 因子权重；
- 分数到仓位的参数；
- 策略资金权重；
- 风险厌恶、换手惩罚和现金比例等少量超参数。

### 6.2 正确用途

- 估计策略在该样本上的理论上界；
- 分析权重敏感性和参数稳定区间；
- 判断因子是否冗余或互相抵消；
- 作为下一轮样本外优化的候选起点，但不能直接作为生产权重。

### 6.3 强制隔离

全区间最优结果只能进入 `research_oracle` 命名空间。报告必须同时展示等权/固定权重基准、最优值、邻域敏感性和过拟合警告；不得把最优组合的同区间收益放进正式策略排行榜。

如果需要可部署结果，必须将数据切分为训练、验证和从未参与选参的测试区间，或改为滚动寻优：

```text
[train] 选权重 → [test] 冻结执行
       窗口前移
[  train  ] 选权重 → [test] 冻结执行
```

## 7. 功能二：AI 动态调整仓位

### 7.1 AI 的职责边界

AI 不直接输出最终订单和无限制目标仓位，只输出有界调节建议：

- 市场总仓倍率；
- 板块预算倍率；
- 个股基础仓位倍率或减仓量；
- 风险状态、置信度、原因和证据引用。

建议范围示例：

```text
gross_exposure_multiplier: [0.50, 1.10]
sector_multiplier:         [0.70, 1.20]
security_multiplier:       [0.50, 1.20]
single_decision_delta:     <= 2% NAV
```

具体上限由版本化 `AIOverlayPolicy` 配置，以上仅是默认候选，不是硬编码业务结论。

### 7.2 输入 FactPack

AI 只能读取冻结的、可重放的 `AllocationFactPack`：

```text
fact_pack_id
decision_at / execution_at
market_regime / market_breadth / liquidity
sector_strength / sector_flow_evidence
candidate_scores / current_positions
risk_budget / drawdown_state / turnover_budget
news_event_evidence_ids
data_snapshot_id / feature_snapshot_id
max_source_available_at
```

硬门禁：`max_source_available_at <= decision_at`。任何晚于决策时点的新闻、完整日线、财报或验证结果都不能进入 FactPack。

### 7.3 结构化输出

```yaml
schema_version: 1
decision: reduce_risk
gross_exposure_multiplier: 0.80
sector_multipliers:
  bank: 0.90
security_multipliers:
  600000.SH: 0.85
confidence: 0.68
reason_codes: [breadth_deterioration, sector_flow_weak]
evidence_ids: [fact:market:..., fact:sector:...]
```

必须保存模型供应商、模型名、模型版本、Prompt 版本、推理参数、FactPack Hash、原始结构化响应 Hash、解析结果和约束前后差异。模型无法重放时，历史运行仍能使用保存的输出复现组合结果，但必须标记 `model_call_replayable=false`。

### 7.4 确定性安全层

AI 输出依次经过：Schema 校验、数值截断、证据存在性检查、变化速率限制、总仓/板块/个股约束和最终风险投影。超时、JSON 无效、证据缺失或置信度不足时回退中性调节 `1.0`；严重数据质量问题时回退到降仓策略，不允许模型自行选择失败语义。

AI 动态仓位的回测有两种合规方式：

1. 使用当时真实保存的历史 AI 决策；
2. 用冻结模型/Prompt 和 point-in-time FactPack 离线逐日重放。

禁止一次性把整段未来行情交给 AI 后生成全区间仓位序列。

## 8. 功能三：根据回测结果反推权重

### 8.1 两种语义

必须把用户界面中的“反推权重”拆成：

- `post_hoc_fit`：读取同一区间最终结果寻找最好权重，只用于研究；
- `walk_forward_tuned`：仅用过去训练窗口的回测结果选权重，在下一窗口冻结验证，可进入正式回测。

二者不可共用同一个绩效标签。

### 8.2 目标函数

不建议只最大化累计收益。默认采用多目标效用：

```text
utility = annual_return
        + a * sharpe
        + b * excess_return
        - c * max_drawdown
        - d * turnover
        - e * transaction_cost
        - f * concentration
        - g * instability
```

所有系数、归一化方式和约束都要进入 `ObjectiveSpec` 版本。优化器可以是网格、随机、贝叶斯、进化或梯度可用方法；算法不是审计边界，数据切分和试验账本才是。

### 8.3 嵌套滚动验证

正式结果采用嵌套切分：

```text
Outer Train
  ├── Inner Train：搜索候选
  └── Inner Validation：选择候选和早停
Outer Test：权重冻结，只执行一次
Embargo：隔离重叠的 T+H 标签
```

外层测试结果不能再次反馈到当前外层权重。如果测试结果用于下一轮训练，必须产生新的策略版本和新的未来测试窗口。

### 8.4 试验账本

每个候选都是一个不可变 `OptimizationTrial`：搜索空间、候选权重、训练/验证区间、随机种子、回测 Run、目标分解、约束违反和淘汰原因全部保存。只保存冠军权重会丢失选择偏差和复现证据。

## 9. 功能四：复杂均值方差优化

### 9.1 目标函数

第一版采用 long-only、含成本和换手约束的凸优化形式：

```text
minimize
    0.5 * risk_aversion * w'Σw
  - expected_return_scale * μ'w
  + turnover_penalty * ||w - w_prev||₁
  + transaction_cost(w, w_prev)
  + tracking_penalty * ||w - w_base||²
```

其中：

- `μ` 是各候选股票的预期收益，不直接用未来真实收益；
- `Σ` 是只用历史窗口估计的协方差矩阵；
- `w_prev` 是当前实际持仓；
- `w_base` 是评分模型生成的基础仓位。

### 9.2 预期收益与风险估计

`μ` 优先由历史样本训练的 Score-to-Return Calibrator 生成，输入可包括多因子分数、分位数、市场状态和预测 horizon。训练标签结束时间必须早于本次决策时点。

`Σ` 支持：

- 样本协方差基准；
- EWMA；
- 收缩协方差；
- 行业/风格因子风险模型；
- 半协方差或下行风险研究模式。

需要记录估计窗口、缺失处理、异常值处理、收缩参数、正定修复和矩阵 Hash。高维小样本不允许直接使用未经收缩的样本协方差作为生产默认值。

### 9.3 A 股约束

连续优化至少包含：

```text
0 <= w_i <= single_name_cap
sum(w) <= gross_exposure_limit
cash_weight >= cash_reserve
sector_weight_s <= sector_cap_s
style_exposure within configured bounds
turnover <= turnover_budget
order_value_i <= participation_rate * ADV_i
```

执行投影还要处理：

- 100 股整手和最小交易金额；
- 停牌、涨跌停和不可成交标的；
- A 股 T+1 导致的当日不可卖持仓；
- 佣金、印花税、过户费和滑点；
- 实际成交后现金残差和权重漂移。

连续求解结果不是最终成交结果。必须分别保存 `optimized_target_weight`、`projected_target_weight`、`order_weight` 和 `realized_weight`。

### 9.4 求解失败

求解器不收敛、矩阵异常或约束不可行时，按版本化顺序降级：

```text
MVO
  → 降低复杂约束后重试
  → 风险平价/逆波动
  → score-weight capped
  → equal-weight capped
  → 保持现有仓位或现金
```

降级级别、失败原因、约束松弛量和最终使用算法必须进入诊断，不能静默换算法。

## 10. 功能五：多个动态权重机制叠加

### 10.1 两阶段叠加

为避免“所有权重都乘在一起”导致极端值和不可解释结果，分为两阶段：

**评分阶段**

```text
factor_base
  → rolling_ic_or_icir_modifier
  → regime_modifier
  → bounded_ai_factor_modifier（可选）
  → L1 归一化
  → score / rank / score_breakdown
```

因子分数可表达为：

```text
score(i,t) = Σ alpha(f,t) * z(i,f,t)
```

每一步都限制单期权重变化，并在归一化前后保存快照。

**仓位阶段**

```text
score_to_base_position
  → strategy_budget
  → market/sector/AI exposure overlay
  → mean_variance optimizer
  → risk projection
  → execution projection
```

### 10.2 组合规则

`WeightComposer` 遵循：

1. 顺序由 `CompositionPolicyVersion` 固定，运行时不可重排；
2. 每个阶段只读上一步输出并产生新快照，禁止形成环；
3. 每个 modifier 有上下限、最大日变化和缺失回退；
4. 每步后执行显式归一化或约束投影，不使用隐式除法；
5. 风控可以削减任意上游权重，上游不能恢复被风控削减的额度；
6. 同一事实不得同时以不同名字重复进入多个强相关调节层而不做共线性审查；
7. 最终结果必须给出从基础权重到实际仓位的逐步归因。

### 10.3 叠加后的解释

每只股票的决策页面至少能展示：

```text
基础评分仓位             4.00%
策略资金预算             × 0.90
市场状态调节             × 0.80
AI 个股调节              × 0.85
均值方差优化             → 2.60%
单股/板块/流动性风控      → 2.30%
整手与现金修正            → 2.25%
实际成交后仓位            → 2.18%
```

数值仅用于说明解释结构，正式结果必须来自对应快照。

## 11. Hikyuu Adapter 设计

平台不在 Hikyuu 内再造一个不可追溯的优化器，采用“平台决策、Hikyuu 执行、平台归一结果”的边界：

```text
FeatureSnapshot
  → Weight Optimization Worker
  → AllocationDecision / WeightSnapshot
  → Hikyuu Adapter
      ├── MF_* 生成/复核因子分数
      ├── Selector 选择候选
      ├── AF_* 或自定义 AF 接收目标权重
      ├── MoneyManager 处理资金和数量
      └── Portfolio 模拟成交和持仓
  → Execution/Position/NAV/Diagnostics
```

映射规则：

| 平台模式 | Hikyuu 映射 |
| --- | --- |
| 固定因子权重 | `MF_Weight` |
| 滚动 IC/ICIR | `MF_ICWeight` / `MF_ICIRWeight`，并由平台固化每日输出 |
| TopN 评分选择 | MultiFactor + Selector |
| 等权/分数权重 | `AF_EqualWeight` / `AF_MultiFactor` |
| 外部优化后的目标向量 | `AF_FixedWeightList` 或平台自定义 AF Adapter |
| 策略滚动选优 | `SYS_WalkForward`，结果仍写平台 Trial/Snapshot |
| AI/MVO/复杂叠加 | 平台先求目标权重，Hikyuu 执行交易约束和组合回测 |

对于 Hikyuu 内建动态算法，也必须抽取并保存每日 `factor_weight`、系统分数和资产分配结果，不能只保存最终净值。

## 12. 配置契约

建议新增独立 `WeightPolicySpec`，由 `StrategySpec` 引用：

```yaml
weight_policy_id: cn_equity_balanced_v1
policy_version: 1.0.0
mode: stacked

factor_weight:
  base: {momentum: 0.30, quality: 0.25, value: 0.20, sentiment: 0.25}
  dynamic:
    method: rolling_icir
    lookback_sessions: 120
    rebalance_sessions: 20
    max_factor_weight: 0.45
    max_period_delta: 0.10

position_sizing:
  method: score_weight_capped
  top_n: 20
  single_name_cap: 0.06

ai_overlay:
  enabled: true
  policy_version: ai-overlay-v1
  max_gross_multiplier: 1.10
  min_gross_multiplier: 0.50
  failure_action: neutral

optimizer:
  method: mean_variance
  estimation_sessions: 252
  covariance: shrinkage
  turnover_penalty: 0.20
  turnover_budget: 0.30

risk:
  gross_exposure_limit: 0.90
  cash_reserve: 0.10
  sector_cap: 0.25
  participation_rate: 0.05

composition:
  order: [factor_dynamic, score, base_position, strategy_budget, ai_overlay, optimizer, risk, execution]
```

配置保存的是意图；运行时要把默认值全部展开为 immutable resolved spec，并计算 `weight_policy_hash`。

## 13. 数据模型与落地

### 13.1 PostgreSQL 控制面

| 表 | 作用 |
| --- | --- |
| `weight_policy_version` | 版本化权重与叠加配置 |
| `objective_spec_version` | 反推/寻优目标函数与惩罚项 |
| `optimization_run` | 一次全区间、滚动、AI 或 MVO 优化任务 |
| `optimization_trial` | 每个候选参数和对应回测结果 |
| `weight_snapshot` | 某决策时点各层输入/输出权重索引 |
| `ai_allocation_decision` | FactPack、模型、响应和有界调节结果 |
| `allocation_decision` | 最终目标权重、约束和降级结果 |

### 13.2 Parquet 结果面

大向量和矩阵存于：

```text
/data/daily_stock_analysis/storage/app/results/type=backtest/run_id=<run_id>/attempt_id=<attempt_id>/weights/
├── factor_weights.parquet
├── score_breakdown.parquet
├── base_positions.parquet
├── overlay_components.parquet
├── optimized_targets.parquet
├── projected_targets.parquet
├── realized_weights.parquet
├── optimization_trials.parquet
├── expected_returns.parquet
└── covariance-manifest.json
```

协方差大矩阵可单独使用压缩 Parquet/Arrow 落地，PostgreSQL 只保存位置、维度、估计方法和内容 Hash。

### 13.3 WeightSnapshot 最少字段

```text
weight_snapshot_id / run_id / policy_version
decision_at / effective_at
mode / leakage_class / deployable
training_start / training_end
validation_start / validation_end
test_start / test_end
data_snapshot_id / feature_snapshot_id / fact_pack_id
input_weight_hash / output_weight_hash
component_snapshot_ids
optimizer_run_id / ai_decision_id
constraint_result / fallback_level
created_at / result_hash
```

## 14. 时间边界与防泄漏

正式运行必须同时通过：

1. `source.available_at <= decision_at`；
2. 动态权重的 `training_end < effective_at`；
3. 训练标签的 `label_end_at <= training_cutoff`；
4. T+H 标签重叠时使用 purge/embargo；
5. 当前外层测试结果不进入当前权重；
6. AI FactPack 不含事后新闻、修正版财报或未来组合结果；
7. 均值、协方差和风险状态只使用决策前数据；
8. 所有权重在 T 日决策后冻结，T+1 才尝试执行。

门禁失败时运行状态为 `rejected_leakage`，而不是自动降级为研究模式。用户若要研究模式，必须显式创建新的 run。

## 15. 回测指标与权重归因

除常规收益、Sharpe、回撤、换手和费用外，自动权重模块必须新增：

- 与等权/固定权重基准的增量收益；
- 每个权重机制的边际贡献和消融结果；
- 权重集中度、有效持仓数和板块集中度；
- 权重单期变化、稳定性和漂移；
- 预测权重、目标权重、订单权重和实际权重偏差；
- 求解器失败率、降级率和约束命中率；
- AI 接受、截断、拒绝、中性回退比例；
- 全区间最优与样本外结果的过拟合差距；
- 训练、验证和测试分段绩效及参数稳定性。

每个 stacked 策略至少自动运行以下消融：

```text
Static baseline
+ Rolling IC/ICIR
+ AI overlay
+ MVO
+ All mechanisms
```

只有全部机制优于基准且跨窗口稳定，才说明叠加有价值；最终结果好但某层长期负贡献时，应删除该层而不是继续增加复杂度。

## 16. 质量门禁与验收

1. 同一快照、策略、权重策略、模型输出和随机种子重复运行，权重与结果 Hash 一致；
2. `oracle_full_period` / `post_hoc_fit` 无法发布到模拟或实盘；
3. 正式运行的训练、验证、测试和 embargo 区间无交叉泄漏；
4. 每个动态权重时点保存完整输入、输出、原因和版本；
5. AI 无效、超时、越界和证据缺失均按固定规则回退；
6. AI 输出不能突破任何确定性风险约束；
7. MVO 输入矩阵、求解器状态、约束松弛和降级路径可追溯；
8. 权重和现金满足误差容忍范围，单股/板块/总仓不越界；
9. 100 股整手、T+1 和不可成交导致的目标偏差被显式记录；
10. 多机制叠加顺序确定，禁用其中一层可得到可比较的消融运行；
11. 回测反推的冠军权重可追溯到完整 Trial 集合而非只剩最终参数；
12. 页面明确分开展示研究上界、训练结果、样本外回测和模拟组合；
13. Hikyuu 内建动态权重也能导出逐期权重快照；
14. AI/优化器不可用时，基准策略仍能独立完成正式回测。

## 17. 分阶段实施

### Phase W0：基准与契约

- 实现四层权重模型、`WeightPolicySpec` 和 `WeightSnapshot`；
- 固定因子权重 + TopN + `equal_weight_capped` 作为可复现基准；
- 打通 Hikyuu `MF_Weight`、Selector、AF、MoneyManager 和结果归一；
- 页面完成 score breakdown 和逐层权重解释。

### Phase W1：滚动权重

- 接入 `MF_ICWeight` / `MF_ICIRWeight`；
- 固化 point-in-time IC、每日因子权重和窗口信息；
- 加入权重上限、变化率限制、缺失回退和样本外门禁。

### Phase W2：回测寻优

- 建立 OptimizationRun/Trial 和多目标 ObjectiveSpec；
- 先实现全区间 oracle 用于诊断，但与正式排行榜物理隔离；
- 实现 nested walk-forward、purge/embargo 和独立外层测试。

### Phase W3：均值方差

- 实现预期收益校准、收缩协方差、约束求解和降级链；
- 衔接 Hikyuu 订单、费用、T+1、整手和实际仓位；
- 增加容量、换手、集中度和目标/实际偏差报告。

### Phase W4：AI 与组合叠加

- 先以离线保存的 AI 决策完成可重放 PoC；
- 接入 FactPack、结构化输出、有界调节和安全回退；
- 启用 WeightComposer、全量消融和 Paper Portfolio 观察；
- 达到稳定性门槛后再申请进入模拟/实盘，不直接跳级。

## 18. 推荐的第一版生产策略

高级能力全部纳入架构，但上线顺序保持克制：

```text
固定因子权重
  + TopN
  + equal_weight_capped
  + 单股/板块/总仓/流动性约束
  → 滚动 IC/ICIR
  → walk-forward 回测寻优
  → 均值方差
  → AI overlay
  → 多机制叠加
```

`oracle_full_period` 从第一阶段就可以作为研究工具存在，但永远不转为生产模式。这样既保留用户希望的自动寻优能力，又能为每一步建立清晰基准，避免 AI、MVO 和后验寻优同时上线后无法判断收益来自哪里。

## 19. M9自动权重实现基线

这些能力属于MVP后M9，先固定研究默认值，必须通过Walk-forward与Paper门禁后才能申请发布：

1. 首批因子为20日动量/相对强度（正）、质量/盈利收益（正）、20日波动（负）和流动性（正）；每个Definition单独固定符号、去极值和缺失策略；
2. 默认Walk-forward使用504个交易日训练、126日验证、63日冻结测试、5日embargo并按月滚动；数据不足时拒绝，不缩短窗口；
3. Trial指标先在同一训练轮候选内做稳健Rank归一，再按35%超额收益、25%Sharpe、20%回撤惩罚、10%换手惩罚、10%参数不稳定惩罚合成；权重属于`objective_spec_version`；
4. 第一版AI只允许在确定性边界内调节总仓和板块上限，不调单只股票；任何输出再经过约束投影；
5. MVO优先使用CVXPY+OSQP的固定版本，求解失败降级到上一个已认证权重或等权上限策略并记录原因；新增依赖前必须完成镜像和资源Benchmark；
6. 第一版不建立完整行业/风格风险模型，使用收缩协方差、单股/板块/换手/流动性约束；风险模型作为后续独立Definition；
7. 候选Policy需要通过独立测试窗，并连续60个交易日Paper观察；回撤、换手、容量或漂移越过Policy阈值时自动停用并回滚上一版本；
8. 自动优化为单重任务，默认最多2核、服务器可用内存的50%、2小时Wall Time和受控临时盘；实际数值由版本化ResourceBudget在Benchmark后收紧。

全区间最优和同区间结果反推永久保留`RESEARCH_ONLY`标签，不能因指标优秀自动升级。

## 20. 参考资料

- [Hikyuu 多因子合成：固定、等权、滚动 IC 与滚动 ICIR](https://hikyuu.readthedocs.io/zh-cn/latest/trade_portfolio/multifactor.html)
- [Hikyuu 资产分配：固定、等权和多因子评分分配](https://hikyuu.readthedocs.io/zh-cn/latest/trade_portfolio/allocate_funds.html)
- [Hikyuu 滚动交易系统与训练/测试窗口](https://hikyuu.readthedocs.io/zh-cn/latest/trade_sys/walkforward.html)
- [Fleur 策略池预览、评分明细和 applied/draft 边界](https://github.com/WackyGem/Fleur/blob/main/docs/RFC/archive/0026-racingline-strategy-pool-preview-step3.md)
- [Fleur 回测重算评分、TopN、等权上限及组合账本](https://github.com/WackyGem/Fleur/blob/main/docs/RFC/archive/0028-racingline-strategy-backtest-step5.md)
- [指标、预测与 Hikyuu 回测架构](backtest-and-indicator-architecture.md)
