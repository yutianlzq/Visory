# Visory A 股板块异动、热门观察与策略评分边界 v1

状态：已确认（Design Approved）

最后更新：2026-08-28

## 1. 决策摘要

本模块落实架构决策 D-026，定义板块异动、热门板块观察、热点股展示以及策略使用这些因素时的评分边界。

第一版固定以下原则：

- 市场观察域只保存和展示客观指标、独立榜单、Provider公开排名、规则触发事件和证据，不建立平台统一的板块热度分或热点股综合分；
- 行业、概念和地域板块分开管理、分开排行，禁止把重叠概念板块资金合计成全市场资金；
- “异动”是由版本化规则触发的事件，不计算严重度分；
- “热门板块”是多个独立客观榜单的页面集合，不形成唯一综合榜；
- “热点股”按涨幅贡献、成交贡献、资金、涨停、龙虎榜、Provider热榜等来源分开展示，不形成平台统一总分；
- AI只解释事实、证据和数据缺口，不生成或回写隐藏热度分；
- 当某个StrategySpec明确引用板块或热点因素时，策略域可以创建专属的`strategy_sector_score`或`strategy_stock_score`；
- 策略评分必须绑定策略版本、指标版本、权重版本、FeatureSnapshot、训练窗口和样本内/样本外状态，并由Hikyuu验证；
- 页面事实与策略评价分表、分API、分权限保存，策略结果不得写回市场事实层；
- T日盘后观察事实和策略评分只能用于T+1及之后的执行。

本文描述目标架构，不表示当前代码已经具备相应实现。

## 2. 为什么不建立平台统一评分

同一板块事实对不同策略的意义并不相同：

- 短线策略可能重视涨停密度、连板和成交异动；
- 趋势策略可能重视5日/20日相对强度和市场宽度；
- 轮动策略可能重视行业资金持续性和排名变化；
- 低波动策略可能回避成交过热、炸板和高度集中的板块；
- 事件策略可能只关心公告、政策和题材催化的可用时间。

若平台预先合成一个热度分，就会把特定策略偏好伪装成通用市场事实，也会导致页面、AI和回测共享一个未经验证的主观权重。第一版因此不提供：

```text
sector_heat_score
hot_sector_score
hot_stock_score
anomaly_severity_score
sector_lifecycle_score
```

允许保留的排名只有：

- 单个客观指标在同类板块中的排序；
- Provider返回的原始榜单和原始排名；
- 某个具体StrategyVersion内部的候选评分和排序。

三者必须使用不同字段和数据模型。

## 3. 逻辑架构

```text
Certified DataSnapshot / FeatureSnapshot
  ├── Point-in-time Sector Membership
  ├── Sector Price/Breadth/Liquidity
  ├── Sector/Stock Capital Evidence
  ├── Limit/Ladder/Break/LHB
  ├── Provider Hot/Anomaly Lists
  └── News/Announcement/Topic Evidence
                       │
                       ▼
              Sector Observation Engine
  ┌────────────────────┼────────────────────┐
  ▼                    ▼                    ▼
Objective Views   Rule-triggered Events   Provider Lists
  │                    │                    │
  ├── Price            ├── Breakout         ├── Hot Stock
  ├── Capital          ├── Volume Spike     ├── Skyrocket
  ├── Breadth          ├── Flow Surge       ├── Limit Pool
  ├── Liquidity        ├── Divergence       └── LHB/Anomaly
  ├── Limit Ecology    └── Cooling
  └── Persistence
                       │
                       ▼
             ObservationSnapshot / FactPack
                       │
          ┌────────────┴────────────┐
          ▼                         ▼
    Market UI / DSA            Strategy Resolver
   facts only, no score              │
                                     ▼
                         Strategy-specific Scoring
                                     │
                                     ▼
                               Hikyuu Backtest
```

市场观察域和策略域共享同一FeatureSnapshot，但输出隔离：

```text
ObservationSnapshot ≠ StrategyScoreSnapshot
```

页面不能用策略评分替代客观榜单；策略也不能从页面展示顺序推断输入。

## 4. 板块身份与历史成员

### 4.1 板块分类

板块注册表至少区分：

| `sector_type` | 说明 | 能否汇总为全市场 |
| --- | --- | --- |
| `industry` | 行业分类，使用明确taxonomy/version | 可以，但同一taxonomy内成员应互斥 |
| `concept` | 题材、概念和产业主题 | 不可以，成员允许重叠 |
| `region` | 地域板块 | 不进入默认市场汇总 |
| `provider_custom` | Provider自定义板块 | 仅在其原始语境展示 |

行业、概念、地域不能进入同一个排行榜。相同名称来自不同Provider时也不能只按名称合并。

### 4.2 Sector Registry

```text
sector_id
sector_type
taxonomy_id / taxonomy_version
canonical_name
valid_from / valid_to
registry_status
created_at / updated_at
```

Provider映射独立保存：

```text
sector_id
provider / actual_upstream
provider_sector_id
provider_sector_name
valid_from / valid_to
mapping_source / mapping_version
verified_at / verification_status
```

概念别名可以由AI或规则提出候选，但只有人工或确定性数据契约确认后才能合并。名称相似不代表板块语义相同。

### 4.3 成员历史

```text
sector_id
canonical_id
valid_from / valid_to
announced_at / available_at
source / actual_upstream
membership_version
data_snapshot_id
```

- 当日页面可以显示Provider当前成员，但必须标明成员快照时间；
- 正式历史回测只能使用有生效日期和`available_at`的point-in-time成员；
- 当前成员不得回填覆盖历史；
- 概念历史成员无法获得时，从平台上线日起每日归档，历史缺口保持不可用；
- 股票跨多个概念时分别保存成员关系，不复制股票行情事实。

## 5. 客观板块指标

板块指标进入Feature Store，但不合成平台评分。

### 5.1 价格与相对强度

```text
sector_return_1d
sector_return_5d
sector_return_20d
sector_relative_return_1d
sector_relative_return_5d
sector_relative_strength_20d
sector_drawdown_20d
```

每个指标保存原值、同类板块分位数和单指标排名。行业只与相同taxonomy的行业比较，概念只与相同Provider/taxonomy的概念比较。

### 5.2 市场宽度

```text
advance_count / decline_count / flat_count
advance_ratio
above_ma20_ratio / above_ma60_ratio
new_high_20_count / new_low_20_count
new_high_20_ratio / new_low_20_ratio
median_stock_return
```

停牌、首日和缺数处理沿用市场情绪架构。每个结果携带成员总数、有效样本数和覆盖率。

### 5.3 成交与流动性

```text
sector_amount_cny
sector_amount_ratio_20
sector_turnover_median
rising_stock_amount_share
top1_amount_contribution
top3_amount_contribution
top10_amount_contribution
```

贡献度用于判断板块表现由少数股票还是较多成员驱动，但平台不据此给出“健康”或“虚假热点”评分。

### 5.4 资金行为

```text
sector_main_net_flow
sector_flow_intensity
positive_flow_stock_count
positive_flow_stock_ratio
sector_flow_persistence_5d
sector_flow_persistence_10d
top_flow_contributors[]
```

订单规模资金继续标记为Provider派生证据，不能写成已确认机构资金。行业可以在单一互斥taxonomy内汇总，概念只显示各自板块值，不合计。

### 5.5 涨跌停与龙头事实

```text
limit_up_count / limit_down_count / limit_break_count
limit_up_density / limit_break_rate
max_streak_height
streak_stock_count
prior_limit_up_premium
top_return_contributors[]
top_amount_contributors[]
limit_leaders[]
```

“龙头”仅作为由明确字段排序得到的观察列表，例如最高连板、涨幅贡献或成交贡献。平台不生成一个跨维度龙头分。

### 5.6 持续性事实

```text
consecutive_top10_return_days
consecutive_top10_flow_days
consecutive_above_ma20_breadth_days
return_rank_change_1d / return_rank_change_5d
flow_rank_change_1d / flow_rank_change_5d
```

持续性直接展示连续天数和排名变化，不转换为“萌芽、加速、共识、退潮”等生命周期评分。AI可以在复盘中描述可能阶段，但必须引用客观历史序列并标记为观点。

## 6. 独立观察榜单

### 6.1 页面固定视图

第一版提供以下独立视图：

| `view_id` | 默认排序 | 页面名称 |
| --- | --- | --- |
| `sector_return_1d` | 1日收益降序 | 今日领涨 |
| `sector_return_5d` | 5日收益降序 | 五日强势 |
| `sector_relative_strength_20d` | 20日相对强度降序 | 中期强度 |
| `sector_main_flow_1d` | 当日资金强度降序 | 当日资金流入 |
| `sector_main_flow_5d` | 5日资金持续性降序 | 连续资金流入 |
| `sector_breadth` | 上涨比例降序 | 宽度扩散 |
| `sector_amount_spike` | 成交额相对20日均值降序 | 放量板块 |
| `sector_limit_cluster` | 涨停密度降序 | 涨停聚集 |
| `sector_return_flow_divergence` | 背离规则触发时间降序 | 价资背离 |
| `sector_provider_hot` | Provider原始排名 | 外部热门榜 |

每个视图只按一个已声明字段或一组用于稳定排序的同义字段排序。并列时使用`sector_id`作为确定性tie-breaker，不引入隐藏综合权重。

### 6.2 排名语义

平台生成的单指标排名至少保存：

```text
view_id
sort_metric_id / metric_version
sector_type / taxonomy_id / taxonomy_version
trade_date / available_at
rank / total_count
raw_value / percentile
observation_snapshot_id
```

Provider榜单另外保存：

```text
provider_list_id
provider / actual_upstream
provider_rank
provider_score_raw
list_period / observed_at / available_at
is_complete / pagination_state
raw_content_hash
```

`provider_score_raw`只用于忠实保存外部返回，不映射为平台分数。Provider列表未完整翻页时必须标记`is_complete=false`，不能声称覆盖全市场。

## 7. 板块异动事件

### 7.1 事件而不是分数

异动由明确规则触发，每条事件保存规则、阈值和触发事实：

```text
event_id
event_type
sector_id / sector_type / taxonomy_version
trade_date / detected_at / available_at
rule_id / rule_version / rule_hash
trigger_metric_values[]
thresholds[]
observation_snapshot_id
data_snapshot_id / feature_snapshot_id
event_lifecycle_status
revision / revision_kind / supersedes_id
```

事件不保存数值严重度，不按多个事件数量合成热度分。

### 7.2 v1规则

| `event_type` | 触发规则 |
| --- | --- |
| `PRICE_BREAKOUT` | 1日收益相对自身前120日`robust_z>=2`，且同类板块收益分位数不低于95% |
| `VOLUME_SPIKE` | 成交额达到此前20日均值1.8倍，且相对自身历史`robust_z>=2` |
| `FLOW_SURGE` | 资金强度相对自身历史`robust_z>=2`，且资金为正成员比例不低于60% |
| `BREADTH_EXPANSION` | 上涨成员比例不低于75%，且MA20宽度较前一日提升至少15个百分点 |
| `LIMIT_CLUSTER` | 涨停股票不少于3只，且涨停密度位于同类板块前5% |
| `ROTATION_ENTRY` | 1日收益排名较前一日提升不少于15位，同时成交额比不低于1.5 |
| `PRICE_UP_FLOW_DOWN` | 收益位于同类板块前20%，资金强度位于后20% |
| `PRICE_DOWN_FLOW_UP` | 收益位于同类板块后20%，资金强度位于前20% |
| `COOLING` | 此前3日平均收益分位不低于80%，当日收益和资金均为负且上涨成员比例低于40% |

规则阈值是显示和告警契约，不代表交易有效。修改阈值必须提升`rule_version`，历史事件继续绑定旧版本。

### 7.3 触发门禁

- 有效成员少于10只的板块默认不触发正式异动；
- 所需指标覆盖率低于90%时事件为`insufficient_data`而不是未触发；
- 缺少资金数据时不能触发资金类事件，但价格和成交事件可以继续；
- 同一板块、交易日、事件类型和规则版本保持幂等；
- Correction使用新事件ID、`revision_kind=CORRECTION`和`supersedes_id`，不覆盖旧事件。

## 8. 热点股客观列表

### 8.1 列表类型

热点股页面由多个列表组成：

```text
provider_hot_stock
provider_skyrocket
sector_return_contributor
sector_amount_contributor
sector_flow_contributor
limit_up_stock
streak_stock
limit_break_stock
dragon_tiger_stock
institution_seat_active
turnover_anomaly_stock
news_or_announcement_stock
exchange_monitoring_stock
severe_anomaly_stock
```

每个列表保留自己的来源、排序字段和数据时间。平台不创建跨列表总分，也不把列表出现次数合成热度。

### 8.2 去重与原因保留

全局展示以`canonical_id`去重，但保留全部入榜原因：

```yaml
canonical_id: sz300750
trade_date: 2026-08-27
observed_lists:
  - list_type: sector_amount_contributor
    sector_id: <sector_id>
    rank: 1
    metric_id: stock.amount_contribution
  - list_type: provider_hot_stock
    provider: financial_api
    provider_rank: 8
related_sectors:
  - sector_id: <sector_id>
    relation_type: provider_membership
risk_flags: []
observation_snapshot_id: obs_<uuidv7>
```

全局去重页面默认按列表分组或时间展示，不生成跨列表综合顺序。若用户主动选择某一字段排序，API必须回传`sort_by`。

### 8.3 题材归因

股票与题材的关联证据分开保存：

```text
relation_id
canonical_id
sector_id / topic_id
relation_type
source / actual_upstream
evidence_uri / raw_content_hash
published_at / available_at
verification_status
valid_from / valid_to
```

`relation_type`建议包括：

```text
provider_membership
limit_up_reason
company_announcement
official_business_description
news_mention
ai_candidate
manual_verified
manual_rejected
```

AI只能创建`ai_candidate`，不能自动改成`manual_verified`，也不计算题材关联分。页面按证据类型和时间展示关联理由。

### 8.4 风险标签

热点股页面同时展示：

```text
ST / STAR_ST
LISTED_LESS_THAN_20_DAYS
SUSPENDED
LIMIT_UP_UNBUYABLE
LIMIT_DOWN_UNSELLABLE
EXCHANGE_MONITORING
SEVERE_ANOMALY
UNLOCK_UPCOMING
INSTITUTION_SEAT_NET_SELL
INSUFFICIENT_LIQUIDITY
MISSING_MARKET_RULE
```

风险标签是事实或规则结果，不从列表中静默删除股票。策略是否排除由StrategySpec和市场规则决定。

## 9. AI与DSA边界

DSA只消费结构化观察事实：

```yaml
sector_observation:
  trade_date: 2026-08-27
  observation_snapshot_id: obs_<uuidv7>
  views:
    return_1d: []
    flow_1d: []
    breadth: []
    amount_spike: []
    limit_cluster: []
  anomaly_events: []
  stock_lists: []
  missing_capabilities: []
```

AI可以描述：

- 哪些板块在价格、资金、宽度或成交维度领先；
- 同一板块是否同时出现在多个独立榜单；
- 板块是否由少数股票贡献；
- 价格和资金是否出现背离；
- 公告、新闻和涨停原因是否能解释观察事实；
- 哪些结论因成员历史或数据缺失无法确认。

AI输出属于Review/Research，不得：

- 创建隐藏热度分；
- 修改榜单排名；
- 把“吸筹、出货、主线、退潮”等观点写回事实字段；
- 把没有证据的题材关联标记为已验证；
- 给热点股生成平台级买入优先级。

## 10. 策略专属评分

### 10.1 评分只属于策略域

当策略明确引用板块或热点因素时，StrategySpec可以定义：

```yaml
sector_model:
  universe:
    sector_type: industry
    taxonomy_id: <taxonomy_id>
  required_features:
    - sector.return_percentile_5d@1.0.0
    - sector.flow_percentile_5d@1.0.0
    - sector.advance_ratio@1.0.0
    - sector.amount_ratio_20@1.0.0
    - sector.limit_up_density@1.0.0
  score:
    output: strategy_sector_score
    method: weighted_sum
    weights:
      sector.return_percentile_5d: 0.25
      sector.flow_percentile_5d: 0.25
      sector.advance_ratio: 0.20
      sector.amount_ratio_20: 0.15
      sector.limit_up_density: 0.15
  select:
    top_n: 5
```

这只是示例，不是平台默认权重。不同策略可以使用不同特征、方向、过滤器和权重。

### 10.2 输出契约

```text
strategy_score_id
strategy_id / strategy_version / strategy_hash
entity_type / entity_id
signal_date / generated_at / available_at
score_name / raw_score / rank
feature_contributions[]
weight_policy_version / weight_policy_hash
optimization_run_id
data_snapshot_id / feature_snapshot_id
observation_snapshot_id
training_window / validation_window
leakage_class
run_id
```

策略评分写入策略运行域或策略专用Feature缓存，不写入`sector_metric_daily`、`sector_observation_snapshot`或市场页面Mart。

### 10.3 权重机制

策略可以选择：

- 固定权重；
- 研究用途的全区间最优权重；
- 正式运行的滚动训练、冻结执行权重；
- 样本外反推和约束优化；
- AI有界Overlay；
- 多机制叠加。

正式业绩继续遵循权重优化架构：全区间最优和同区间最终结果反推只能作为研究上界；Paper Portfolio和Formal回测必须使用决策时点已经冻结的WeightSnapshot。

### 10.4 硬条件可以不评分

策略不一定使用加权分，也可以直接声明：

```yaml
sector_filter:
  all:
    - sector.advance_ratio >= 0.60
    - sector.amount_ratio_20 >= 1.50
    - sector.flow_intensity > 0
    - not event(PRICE_UP_FLOW_DOWN)
```

这些条件仍属于具体策略，不改变市场页面对同一板块的客观展示。

## 11. 策略与Hikyuu回测

### 11.1 时序

```text
T日收盘
  → Certified DataSnapshot(T)
  → FeatureSnapshot(T)
  → ObservationSnapshot(T)
  → Strategy-specific Score/Filter(T)
  → Prediction(T)
  → T+1尝试执行
```

观察榜单不是交易结果。T日涨停、Provider热榜或板块异动不能按T日收盘价假设成交。

### 11.2 防未来函数

- 板块成员、股票状态、市值、涨跌停规则使用point-in-time版本；
- 排名和历史分位只使用T日决策时点可用数据；
- today-only热榜和异动在未归档日期保持不可用；
- Provider当前概念成员不能回填历史策略；
- T日盘后生成的榜单只能进入T+1信号；
- 新闻、公告和题材使用实际`published_at/available_at`；
- 历史数据修订生成新Snapshot和新BacktestRun；
- 策略评分权重不得用同一测试区间最终收益反向污染。

### 11.3 验证维度

策略使用板块或热点因素时至少验证：

- T+1/T+3/T+5/T+10/T+20收益和超额收益；
- 板块选择命中率、持有期和换手；
- 板块内选股相对板块收益；
- 涨停不可买、停牌、容量和滑点后的可交易收益；
- 行业与概念结果分别统计；
- 不同市场情绪状态下的稳定性；
- Provider榜单缺失、成员缺失和数据修订敏感性；
- 固定权重与滚动样本外权重差异。

正式收益由Hikyuu计算，不能用榜单后验涨幅替代组合回测。

## 12. 数据表与快照

### 12.1 核心表族

| 表族 | 主键或唯一键 | 内容 |
| --- | --- | --- |
| `sector_registry` | sector_id | 板块规范身份和taxonomy |
| `sector_provider_map` | sector + provider + valid_from | Provider映射 |
| `sector_membership_history` | sector + stock + valid_from | point-in-time成员 |
| `sector_metric_daily` | sector + date + metric/version + feature_snapshot | 客观指标和单指标排名 |
| `sector_observation_view` | view_id + version | 排序字段、taxonomy和展示契约 |
| `sector_observation_snapshot` | market + date + snapshot | 所有视图和能力Manifest |
| `sector_anomaly_event` | event_id | 规则触发事件和证据 |
| `provider_observation_list` | provider_list_id + observation | 外部榜单原始记录 |
| `stock_observation_list_item` | list + stock + date + snapshot | 热点股独立列表项 |
| `stock_sector_relation` | relation_id | 题材和板块关联证据 |
| `stock_observation_risk_flag` | stock + date + flag/version | 风险标签 |
| `strategy_entity_score` | strategy + entity + signal_date + run | 策略专属评分和贡献 |

### 12.2 快照Manifest

```text
observation_snapshot_id
trade_date / created_at / available_at
data_snapshot_id / feature_snapshot_id
sector_registry_version
membership_snapshot_ids[]
metric_versions[]
view_versions[]
anomaly_rule_versions[]
provider_list_manifests[]
capability_certifications{}
missing_capabilities[]
row_counts{}
manifest_hash / content_hash
publication_status / quality_status
revision / revision_kind / supersedes_id
```

ObservationSnapshot只能引用已经发布的FeatureSnapshot。Provider榜单晚到时可以生成新ObservationSnapshot，不覆盖旧版本。

### 12.3 文件目录

```text
/data/daily_stock_analysis/
├── config/platform/sectors/
│   ├── taxonomies/
│   ├── observation-views/
│   └── anomaly-rules/
├── storage/app/features/domain=sector/frequency=1d/indicator_id=<indicator_id>/definition_version=<version>/year=YYYY/
├── storage/app/observations/domain=sector/trade_date=YYYY-MM-DD/snapshot_id=<observation_snapshot_id>/
├── storage/app/observations/domain=stock_hotspot/trade_date=YYYY-MM-DD/snapshot_id=<observation_snapshot_id>/
├── storage/app/results/type=backtest/run_id=<run_id>/
├── storage/app/artifacts/type=market_review/year=YYYY/month=MM/
└── logs/sector-observation-worker/
```

配置目录只保存无密钥定义。Provider凭据继续由受控配置管理，不进入Snapshot和页面返回。

## 13. 能力认证与失败语义

### 13.1 能力拆分

```yaml
certified_capabilities:
  sector_registry: certified
  sector_membership_industry: certified
  sector_membership_concept: provisional
  sector_price: certified
  sector_breadth: certified
  sector_liquidity: certified
  sector_capital: unavailable
  sector_limit_ecology: certified
  sector_anomaly_price: certified
  sector_anomaly_flow: unavailable
  provider_hot_stock: certified
  topic_attribution: partial
```

页面按能力展示，不因一个Provider榜单失败而隐藏所有板块事实。

### 13.2 降级规则

- 资金能力缺失：资金榜和资金异动不可用，价格、宽度和成交榜继续；
- 涨跌停池缺失：涨停聚集榜不可用，其他榜单继续；
- Provider热榜失败：外部热榜不可用，平台客观榜单继续；
- 新闻或公告失败：催化证据减少，不影响行情榜单；
- 概念成员只有当前快照：允许当前页面显示，禁止对应Formal历史回测；
- 某板块有效成员少于10只：展示基础事实并标记样本小，不触发正式异动；
- Provider分页不完整：榜单标记不完整，不推断未出现股票排名；
- 缺失数据为`unknown`，不能当作零或未触发。

策略依赖的能力缺失时必须阻断策略运行，不能删除评分项或重新分配权重。

## 14. API与页面

### 14.1 查询API

```text
GET /api/v1/sectors/views
GET /api/v1/sectors/observations?view_id=&sector_type=&trade_date=&sort_by=
GET /api/v1/sectors/{sector_id}/facts?trade_date=&snapshot_id=
GET /api/v1/sectors/{sector_id}/members?as_of=&membership_version=
GET /api/v1/sectors/anomalies?event_type=&trade_date=
GET /api/v1/stocks/observation-lists?list_type=&trade_date=
GET /api/v1/stocks/{canonical_id}/sector-relations?as_of=
GET /api/v1/sector-observation-snapshots?trade_date=
GET /api/v1/sector-observation-snapshots/{snapshot_id}/lineage
GET /api/v1/strategies/{strategy_id}/entity-scores?run_id=
```

市场API不返回`sector_heat_score`或`hot_stock_score`字段。策略评分API必须位于策略命名空间并要求明确的Strategy/Run上下文。

### 14.2 页面

建议页面分为：

1. 行业、概念、地域三个独立标签页；
2. 今日领涨、资金流、宽度、放量、涨停聚集、持续性和背离等客观视图；
3. 板块详情中的价格、成员宽度、成交、资金、涨跌停和历史排名曲线；
4. 异动事件时间线，展示触发规则和原始指标；
5. 热点股多榜页，按列表来源分组并展示风险标签；
6. 题材证据页，区分Provider标签、公告、新闻、AI候选和人工验证；
7. 数据时间、能力缺口、Provider来源和Snapshot追溯入口。

页面不提供默认综合热度颜色。颜色只表达单个字段的正负、分位或状态，并在图例中明确含义。

## 15. 调度与资源

本模块复用D-025在17:30前发布的板块基础指标，不重复扫描全市场行情：

```text
17:10-17:30  市场和板块基础FeatureSnapshot
17:30-17:36  独立视图排序和持续性事实
17:36-17:40  异动规则检测
17:40-17:44  热点股列表归一、去重和风险标签
17:44        ObservationSnapshot目标发布
17:44-18:05  A股核心正式策略信号，优先级高于复盘
17:44-17:50  全球观察低优先级采集，不作为策略依赖
17:50-18:20  DSA读取有界FactPack生成复盘
18:10-18:30  晚到龙虎榜、融资融券和Provider榜单补充
18:30-18:50  显式依赖晚到A股能力的策略信号
19:00        正式策略硬截止
20:30        Correction审计
```

当前服务器采用单Observation Worker和最多2线程。排序、规则检测和列表归一使用DuckDB批量执行，不逐板块启动独立进程。DSA每个客观视图最多读取前10项并按`sector_id/canonical_id`去重，避免把全市场明细发送给模型。

晚到Provider榜单形成新ObservationSnapshot；依赖该榜单的策略只能绑定晚到快照并在19:00前完成，否则当日不生成正式预测。全球观察失败不改变任何A股策略的运行资格。

## 16. 实施阶段

### Phase 1：板块身份和客观视图

- 建立Sector Registry、Provider Map和成员历史；
- 发布价格、宽度、成交、资金和涨跌停客观指标；
- 实现按单指标排序的行业/概念/地域独立视图。

### Phase 2：异动和热点股列表

- 实现版本化异动规则；
- 接入Provider热榜、涨停池、龙虎榜和异常波动；
- 建立热点股多榜、去重、题材证据和风险标签。

### Phase 3：页面与DSA

- 发布Observation API和页面；
- 生成不含综合分的Sector FactPack；
- AI只基于有来源的事实生成复盘。

### Phase 4：策略接入

- StrategySpec引用板块和热点事实；
- 保存策略专属评分、权重和贡献；
- Hikyuu执行T+1、成本、容量和样本外验证。

### Phase 5：数据积累

- 每日归档today-only榜单和概念成员；
- 评估Provider规则漂移和历史覆盖；
- 只有具体策略提出需求时才扩充特征或评分，不为页面建设通用评分。

## 17. 验收标准

1. 市场事实表、API和页面不存在平台统一板块热度分或热点股综合分；
2. 行业、概念、地域和Provider自定义板块分开排行；
3. 每个榜单都能说明唯一排序字段、同类比较范围、数据时间和Snapshot；
4. Provider原始排名与平台单指标排名分字段保存；
5. 异动事件可追溯到规则版本、阈值和触发指标，且没有严重度分；
6. 热点股按列表来源展示，去重后仍保留全部入榜原因；
7. AI题材归因候选不会自动升级为已验证事实；
8. current-only概念成员不会进入Formal历史回测；
9. today-only榜单历史缺口不会按零或未上榜回填；
10. 策略评分只存在于Strategy/Run上下文，并保存指标贡献和权重版本；
11. 缺失策略依赖时阻断运行，不删除评分项或动态重分权重；
12. T日观察和策略评分只能用于T+1及以后执行；
13. 页面、DSA和策略读取同一Feature/Observation Snapshot；
14. 17:44前可以在当前服务器完成日级增量视图、异动和列表发布。

## 18. 页面实现基线

主平台板块页面采用独立指标列排序、Taxonomy/板块类型筛选、板块详情与热点股双栏下钻；移动端转换为关键字段列表但保留Snapshot与质量状态。完整布局见[页面信息架构与低保真原型 v1](page-prototypes-and-information-architecture-v1.md)的P-SECTOR。

## 19. 参考资料

- [a-stock-data：行业排名、板块资金、题材、涨停、热榜和异动能力](https://github.com/simonlin1212/a-stock-data)
- [Vibe-Research：板块中心和客观榜单页面参考](https://github.com/simonlin1212/Vibe-Research)
- [vibe-astock：连板、晋级率、龙虎榜和板块资金复盘参考](https://github.com/simonlin1212/vibe-astock)
- [Financial-API：涨跌停、异动、热榜和龙虎榜工具契约](https://github.com/HiThink-Tech/Financial-API/blob/main/docs/mcp/hithink-finance-a-share.md)
- [A 股市场情绪与资金行为架构 v1](market-sentiment-and-capital-flow-architecture.md)
- [StrategySpec v1 策略契约](strategy-spec-v1.md)
- [评分、仓位与自动权重优化架构](weight-optimization-architecture.md)
- [A 股回测市场规则 v1](backtest-market-rules-v1.md)
- [全球市场观察与 A 股策略隔离架构 v1](global-market-observation-boundary.md)
- [A 股 Feature Store 与指标注册中心架构 v1](feature-store-architecture.md)
- [DSA A 股收盘复盘 FactPack 架构 v1](dsa-close-review-fact-pack.md)
- [A 股分层个股研究与 StockResearchFactPack 架构 v1](stock-research-architecture.md)
- [A 股主平台模块化单体、API、任务与权限架构 v1](platform-shell-api-task-permission-architecture.md)
