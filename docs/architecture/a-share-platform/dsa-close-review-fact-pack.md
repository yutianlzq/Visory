# Visory A 股收盘复盘 FactPack 架构 v1

状态：Design Approved
最后更新：2026-08-28

## 1. 决策摘要

本模块落实架构决策 **D-029**：

- `daily_stock_analysis`（DSA）作为收盘复盘的任务编排、LLM生成、结构化输出、Markdown渲染、历史、通知和Web展示底座；
- DSA不再为Visory自行抓取权威行情、市场宽度、板块、资金和热点事实，只消费平台发布的不可变FactPack；
- 收盘复盘拆分为 `MarketCloseFactPack → ReviewAnalysis → ReviewReport` 三层；
- Vibe-Research主要参考每日复盘页面的客观信息模块和信息密度；
- vibe-astock主要参考赚钱效应、晋级率、连板溢价、梯队断层、情绪周期和次日验证条件；
- 外部项目的独立数据后端、AI运行栈和完整应用不直接拼入平台，能力通过Canonical Data、Feature Store和适配器迁入；
- AI的重要判断必须引用FactPack中的稳定证据ID，事实、推断和情景假设明确分开；
- 次日观察条件支持T+1自动验证，但不计算策略收益、不产生仓位、不自动升级为StrategySignal；
- 核心市场复盘不包含个股买卖点、目标价、账户仓位或策略资金分配；策略与组合晚报属于后续独立消费者；
- 全球市场只作为可选复盘背景，不能改变A股情绪事实、策略、权重或Hikyuu回测。

## 2. 目标

收盘复盘要回答“今天客观发生了什么、哪些结构值得关注、明天观察什么”，而不是让LLM重新抓数据或生成不可验证的市场故事。

v1必须做到：

1. 指数、宽度、情绪、资金、板块、热点和消息来自同一套已发布事实；
2. AI只解释FactPack，不修改事实值、不补写缺失数据；
3. 页面、Markdown、通知和历史回放由同一ReviewAnalysis渲染；
4. 每项关键观点可回到证据、FeatureSnapshot、DataSnapshot、ProviderRun和Raw Hash；
5. 数据缺失、Provider降级、滞后和Correction对用户可见；
6. LLM失败时仍可发布客观复盘看板和模板摘要；
7. 当时发布版和最新修订版均可查看，旧报告不被静默覆盖；
8. 盘后核心复盘不阻塞Formal Strategy、Paper Portfolio和Hikyuu任务；
9. 当前服务器可在17:50至18:20的低优先级窗口完成核心FactPack和AI复盘；
10. T+1观察条件可自动对账，并与正式策略验证严格隔离。

## 3. 非目标与边界

v1不负责：

- 作为第二套数据采集系统直接访问a-stock-data、Financial-API或页面接口；
- 替代Feature Store计算市场情绪、市场宽度、板块资金或短线派生指标；
- 为板块、热点股生成平台统一评分；
- 把AI复盘观点写回F1/F2特征或作为Hikyuu输入；
- 自动生成StrategySignal、订单、目标权重或账户仓位；
- 用T+1观察条件的命中率冒充策略收益或回测结果；
- 在主报告中等待所有晚到龙虎榜、融资融券和大宗交易数据；
- 保存或再分发未经许可的完整新闻、研报或公告正文；
- 把全球市场后验走势当作A股决策时已经可用的输入。

具体策略可以直接引用Feature Store中的相同A股事实，但不能引用AI生成的ReviewAnalysis。若某条复盘观察逻辑需要进入交易体系，必须另行注册指标、定义StrategySpec并由Hikyuu验证。

## 4. 项目参考与复用边界

### 4.1 daily_stock_analysis

Visory复用或演进：

- `run_market_review`任务入口、锁、API后台任务和运行诊断；
- LLM后端、fallback、usage和模型诊断；
- 结构化`market_review_payload`、Markdown渲染和通知链路；
- `report_type=market_review`历史、查询、分享图和Web详情；
- 市场复盘多语言和兼容输出能力；
- AnalysisContextPack已有的块状态、低敏overview和运行流程可见性思想。

不沿用为权威语义：

- `MarketAnalyzer`运行中自行抓取的行情、板块和搜索结果；
- 事实、AI章节和Markdown混合在同一个Payload中的v1结构；
- 历史持久化时固定写入的`sentiment_score=50`兼容占位；
- Market Light与平台五维情绪并存为两个权威评分；
- LLM Prompt中的通用“明日交易计划、仓位区间”要求。

### 4.2 Vibe-Research

参考：

- 指数、市场宽度、短线情绪、成交额榜、板块资金、资金轮动和AI复盘的一屏组织；
- 页面先展示客观信息、再把同一组数据交给AI的交互方式；
- 数据工具为模型裁剪字段和条数，而不是把整库转储进Prompt；
- 客观公开榜单与AI观点分离。

不复用：

- Vibe自己的运行时Provider选择和本地缓存作为平台真源；
- 全球市场卡片对A股策略产生影响的任何扩展；
- 完整复制其FastAPI/React应用形成第二套平台。

### 4.3 vibe-astock

参考：

- 昨日涨停股今日均值、中位数、翻红率和再涨停率；
- 1进2、2进3和高板晋级率；
- 连板溢价、梯队高度、梯队断层和封板质量；
- 赚钱效应与亏钱效应对照；
- 近5/10日情绪轨迹和次日验证条件；
- 硬指标纯计算，AI只负责叙述和证据串联。

这些指标必须先注册进Indicator Registry并通过平台数据口径计算，不能直接读取外部项目的当前页面结果作为正式事实。

## 5. 三层对象模型

```text
Certified FeatureSnapshot
Sector/Hotspot ObservationSnapshot
Event Features
Optional GlobalObservationSnapshot
                  │
                  ▼
        MarketCloseFactPack
        纯事实、不可变Manifest
                  │
                  ▼
          ReviewAnalysis
     AI观点、情景、证据引用和数据限制
                  │
                  ▼
           ReviewReport
 Web / Markdown / Notification / History
```

| 层 | 权威内容 | 是否允许AI修改 |
| --- | --- | --- |
| `MarketCloseFactPack` | 快照引用、客观指标、榜单、事件、缺失状态 | 否 |
| `ReviewAnalysis` | AI摘要、解释、推断、情景和观察条件 | 仅生成新版本，不覆盖FactPack |
| `ReviewReport` | 页面/Markdown/通知的展示结构 | 只渲染，不另算指标 |

FactPack中不保存Markdown；ReviewAnalysis中不复制全量原始数据；ReviewReport中不新增FactPack未提供的数值。

## 6. MarketCloseFactPack Envelope

```yaml
fact_pack_id: fact_<uuidv7>
schema_version: 1.0.0
pack_type: A_SHARE_CLOSE_CORE
market: cn
trade_date: 2026-08-27
cutoff_at: 2026-08-27T17:50:00+08:00
created_at: 2026-08-27T17:52:00+08:00
published_at: 2026-08-27T17:53:00+08:00
publication_status: CERTIFIED
quality_status: COMPLETE
revision: 1
revision_kind: INITIAL
data_snapshot_ids:
  - ds_<uuidv7>
feature_snapshot_ids:
  - fs_<uuidv7>
observation_snapshot_id: obs_<uuidv7>
global_observation_snapshot_id: obs_<uuidv7>
block_ids:
  - fblock_<uuidv7>
  - fblock_<uuidv7>
max_source_available_at: 2026-08-27T17:49:32+08:00
missing_capabilities: []
quality_report_id: quality_<uuidv7>
builder_version: 1.0.0
manifest_hash: sha256:...
```

### 6.1 顶层规则

- `market=cn`固定表示本架构的A股复盘；
- 所有A股输入必须满足`available_at <= cutoff_at`；
- 引用的Feature/Observation Snapshot必须已经发布；
- `max_source_available_at`是所有纳入事实的最大可用时间；
- 全球快照是可选引用，不计入A股核心完整性；
- `manifest_hash`覆盖规范化后的Envelope、Block Hash和全部Snapshot引用；
- Pack发布后不可修改；Correction、补充或重生成产生新ID；
- “latest”仅用于页面默认选择，Report和历史必须绑定具体FactPack ID。

### 6.2 Pack质量状态

```text
COMPLETE
PARTIAL
FAILED
```

| `quality_status` | 语义 |
| --- | --- |
| `COMPLETE` | 全部核心块可用，允许生成完整AI复盘 |
| `PARTIAL` | 核心行情可用但部分块缺失，允许删减复盘 |
| `FAILED` | 身份、交易日、核心行情或Manifest失败，不生成AI完整复盘 |

没有单一FactPack质量分。质量通过块状态、覆盖率、缺失原因和来源状态表达，避免一个分数掩盖关键缺口。

## 7. 通用Block契约

```yaml
block_id: fblock_<uuidv7>
block_type: MARKET_BREADTH
schema_version: 1.0.0
block_status: AVAILABLE
as_of_trade_date: 2026-08-27
available_at: 2026-08-27T17:23:00+08:00
source_snapshot_ids:
  - fs_<uuidv7>
facts: []
coverage:
  expected: 5300
  valid: 5278
  ratio: 0.9958
warnings: []
missing_reasons: []
block_hash: sha256:...
```

Block状态复用DSA已有Context Pack的质量词，便于Web和运行诊断统一：

```text
AVAILABLE
PARTIAL
MISSING
NOT_SUPPORTED
FALLBACK
STALE
ESTIMATED
FETCH_FAILED
```

每个事实项建议至少保存：

```text
fact_id
metric_id / metric_version
entity_type / entity_id
feature_time / available_at
value / value_type / unit
quality_status / reason_codes
feature_snapshot_id / feature_partition_id
source_provider / actual_upstream
evidence_grade
```

`fact_id`在一个FactPack内唯一且稳定，作为AI证据引用目标。

## 8. 核心事实块

### 8.1 `MARKET_INDICES_STRUCTURE`

包含：

- 上证、深证成指、创业板指、科创50、沪深300、中证500/1000等已配置主要指数；
- 收盘、涨跌幅、开高低、振幅、成交额和相对量能；
- 指数20/60日位置、均线结构、相对强弱和风格差异；
- 大盘/小盘、价值/成长、主板/双创的结构比较；
- 所有指数使用规范`canonical_id`并保存`asset_type=index`。

技术结构指标引用Feature Store，不由DSA重新计算。

### 8.2 `MARKET_BREADTH`

包含：

- 上涨、下跌、平盘、停牌和有效股票数；
- 上涨占比、下跌占比、涨跌比；
- 各涨跌幅区间分布；
- MA20/MA60上方占比；
- 20/60/120日新高和新低；
- 行业上涨占比和中位数收益；
- 宽度与主要指数的背离枚举。

股票池、上市状态、ST、新股、停牌和复权口径沿用D-014与市场情绪设计。

### 8.3 `MARKET_EMOTION_LIMIT_ECOLOGY`

包含：

- D-025五维情绪原始值、维度分、总分、平滑分和市场状态；
- 涨停、跌停、炸板、封板率和触板数；
- 首板、二板、三板及以上梯队；
- 最高连板、梯队断层和断板分布；
- 昨日涨停股今日均值、中位数、翻红率、再涨停率；
- 1进2、2进3、高板晋级率；
- 昨日连板股收益与高标承接；
- 赚钱效应和亏钱效应的独立原始指标。

DSA现有Market Light只能作为兼容显示Adapter。新页面的情绪事实必须引用D-025权威市场情绪快照，不能保留第二套同名评分。

### 8.4 `LIQUIDITY_CAPITAL_BEHAVIOR`

包含：

- 全市场成交额、相对5/20日变化和放量/缩量；
- 沪深市场成交额结构和成交集中度；
- 成交额Top20及其公开榜单来源；
- 订单规模资金证据、市场/板块资金压力和可信度；
- 融资融券、龙虎榜、大宗、互联互通等已在cutoff前认证的能力；
- 缺失、估算、滞后交易日和Provider差异。

资金块只能使用“资金行为证据”语言，禁止从成交额或Provider派生值确认机构、主力账户意图。

### 8.5 `SECTOR_ROTATION`

包含：

- 行业和概念涨跌榜；
- 板块相对收益、宽度、成交额、资金行为、持续性和历史分位；
- 板块领涨/领跌数量和扩散/收缩；
- 板块资金趋势、价格资金共振枚举；
- 规则异动、连续上榜和新进入榜单；
- point-in-time板块成员和Taxonomy版本。

本块不包含平台统一`sector_heat_score`。排名、资金、宽度和异动作为相互独立的客观序列展示。

### 8.6 `HOTSPOT_AND_LEADERBOARDS`

包含：

- 涨停池、连板梯队、高度板、首板池；
- 成交额榜、换手榜、Provider人气榜和公开热榜；
- 热点股与题材/板块关联；
- 每个标的的全部入榜原因、榜单来源、榜单原始排名和更新时间；
- 规则异动、重点监控、龙虎榜等已经认证的客观标签；
- 今日核心标的只作为列表事实，不生成平台荐股排序。

相同股票以`canonical_id`去重，但必须保留多个`list_membership_reason`。AI可以描述“多榜共振”，不能把它升级成已验证买入信号。

### 8.7 `EVENTS_AND_NEWS`

包含：

- 截止时间前已发布的重要公告、政策、监管和行业事件；
- 结构化新闻标题、摘要、来源、URL、发布时间和事件实体；
- 事件重要性、题材关联和证据质量等已注册结构化特征；
- 相互矛盾的来源、未经验证消息和缺失情况；
- 与板块、指数和热点事实的可验证关联。

FactPack不保存受版权保护的完整正文。DSA不在生成阶段临时Search后把无血缘内容当作权威事实；搜索和资讯采集应在上游事件管道完成。

### 8.8 `DATA_GAPS_AND_CORRECTIONS`

包含：

- 缺失和未认证能力；
- Provisional、Fallback、Estimated和Stale数据；
- Provider切换、双源差异和被隔离实体；
- 与上一个已发布Pack相比的修订说明；
- 对哪些复盘章节产生影响。

本块永远存在，即使没有缺口也显式为`AVAILABLE`且列表为空。

### 8.9 `GLOBAL_REVIEW_CONTEXT`（可选）

只引用D-027的GlobalObservationSnapshot，包含：

- 截止17:50已经发生或已经收盘的全球指数、汇率、利率和商品事实；
- 市场时段状态、交易日、时区、延迟和缺失；
- 全球重要事件背景。

AI输出必须标注“复盘背景”。本块缺失不降低A股FactPack的核心状态，不能用于A股策略解释、业绩归因或回测。

## 9. FactPack构建

### 9.1 Zero-fetch Builder

FactPack Builder只做：

1. 解析指定Snapshot；
2. 读取已发布Feature/Observation Mart；
3. 校验时间、身份、状态和能力；
4. 投影和裁剪字段；
5. 生成Block Hash和Manifest；
6. 原子发布FactPack。

Builder禁止：

- 调用Provider或SearchService补数；
- 现场重新计算市场情绪、板块排名或赚钱效应；
- 读取数据库“最新值”替代Manifest引用；
- 用上一日事实冒充当日值；
- 把Correction分区混进当时发布的原Pack。

### 9.2 Compact AI Projection

完整FactPack可以包含大榜单和明细，但LLM只接收`ReviewPromptProjection`：

```text
fact_pack_id / manifest_hash
trade_date / cutoff_at / quality_status
block_status and limitations
core scalar facts
bounded top/bottom lists
selected event summaries
stable fact_ids
```

每个Block声明Prompt条数和字符预算。裁剪规则必须确定性、版本化，并保留被裁剪条数；禁止按LLM临时偏好改变事实选择后仍使用同一Projection版本。

## 10. ReviewAnalysis

### 10.1 Envelope

```yaml
review_analysis_id: review_<uuidv7>
schema_version: 1.0.0
fact_pack_id: fact_<uuidv7>
fact_pack_hash: sha256:...
projection_version: 1.0.0
prompt_version: close-review-1.0.0
model_provider: provider_x
model_name: model_x
model_version: model_x_revision
temperature: 0.2
generated_at: ...
publication_status: CERTIFIED
quality_status: COMPLETE
sections: []
watch_conditions: []
data_limitations: []
raw_response_hash: sha256:...
analysis_hash: sha256:...
```

保存模型、Prompt、参数、FactPack和原始结构化响应Hash。模型调用未必可重新生成逐字相同文本，因此历史复现使用已经持久化的结构化ReviewAnalysis；不能用重新调用模型覆盖旧分析。

### 10.2 固定章节

```text
1. 今日核心结论
2. 指数与大盘结构
3. 市场宽度与赚钱效应
4. 情绪周期与涨跌停生态
5. 资金行为与成交结构
6. 板块轮动与题材脉络
7. 热点股客观梳理
8. 消息催化与事件风险
9. 下个交易日观察条件
10. 数据缺口与风险提示
```

缺少对应Block时删除该事实章节或输出数据限制，不能让模型凭常识补齐。

### 10.3 Claim契约

```yaml
claim_id: claim_<uuidv7>
section: sector_rotation
claim_type: INFERENCE
text: 半导体板块表现出价格与资金同向增强，但扩散仍有限。
evidence_refs:
  - sector.semiconductor.return_rank
  - sector.semiconductor.flow_resonance
  - sector.semiconductor.advance_ratio
support_status: SUPPORTED
limitations:
  - 概念板块成员存在重叠
```

`claim_type`：

| 类型 | 说明 |
| --- | --- |
| `FACT_SUMMARY` | 对FactPack事实的无方向改写 |
| `INFERENCE` | 基于多个事实的AI解释，必须标明推断 |
| `SCENARIO` | 对下一交易日的条件情景，不是预测事实 |
| `DATA_LIMITATION` | 数据缺口、降级和无法判断 |

`support_status`使用`SUPPORTED/PARTIAL/CONTRADICTED/UNSUPPORTED`。发布门禁拒绝没有有效`evidence_refs`的重要事实和推断；`UNSUPPORTED`只进入诊断，不进入正式报告。

### 10.4 禁止输出

核心市场ReviewAnalysis禁止：

- 具体个股买入、卖出、目标价、止损价；
- 用户账户仓位或资金比例建议；
- 把公开榜单描述成平台推荐；
- 把资金证据描述成确认的机构/主力账户意图；
- 引用FactPack以外的即时网页信息；
- 修改或重新计算情绪、板块排名和指标值；
- 把全球后验事实作为A股策略结论依据；
- 把T+1观察条件称为已验证策略。

“进攻/均衡/防守”等词若保留，只能描述市场环境枚举，不能自动映射到用户账户仓位。

## 11. T+1观察条件与验证

### 11.1 ReviewWatchCondition

```yaml
watch_condition_id: watch_<uuidv7>
review_analysis_id: review_<uuidv7>
trade_date: 2026-08-27
horizon: T+1
statement: 市场宽度是否继续修复
metric_id: market.advance_ratio
metric_version: 1.0.0
baseline_value: 0.54
operator: gte
threshold: 0.60
target_session: 2026-08-28
evidence_refs:
  - market.advance_ratio
condition_hash: sha256:...
```

条件必须可机器验证：指标、版本、运算符、阈值、目标交易日和基准值完整。纯自然语言愿望不进入自动验证集合。

### 11.2 ReviewValidation

T+1收盘后由FeatureSnapshot验证：

```text
MET
NOT_MET
INDETERMINATE
```

保存：

```text
review_validation_id
watch_condition_id
validation_trade_date
validation_feature_snapshot_id
observed_value / comparison_result
validated_at / validator_version
reason_codes / result_hash
```

### 11.3 与策略回测隔离

- ReviewValidation不计算收益、胜率、最大回撤或仓位；
- 命中率只能评价“观察条件是否发生”，不能评价投资绩效；
- ReviewAnalysis不能直接进入Feature Store或StrategySpec；
- 若某个条件被选为策略因素，必须注册新的IndicatorDefinition和StrategySpec版本；
- 新策略使用原始市场事实，不使用AI当晚的自然语言结论；
- Hikyuu从头执行独立样本内/样本外验证。

## 12. ReviewReport

### 12.1 同源多输出

同一个ReviewAnalysis渲染：

| 输出 | 重点 |
| --- | --- |
| Web详情 | 客观卡片、AI章节、证据抽屉、缺口、版本和T+1验证 |
| Markdown | 完整章节、表格、证据脚注和风险声明 |
| 通知摘要 | 核心结论、关键数字、三条观察条件和缺口 |
| 分享图 | 指数、宽度、情绪、板块和风险的高密度摘要 |
| 历史 | 当时发布版、修订提示、运行诊断和关联验证 |

Renderer只读取FactPack和ReviewAnalysis，不重新计算指标或让第二次LLM总结。

### 12.2 页面结构

建议页面顺序：

```text
标题 / 日期 / Pack状态 / 截止时间 / 修订标识
核心客观卡片：指数、成交额、宽度、情绪、涨跌停
短线生态：赚钱效应、晋级率、梯队、封板质量
板块与资金：独立榜单、资金证据、轮动
热点与事件：客观列表、入榜原因、消息时间
AI复盘：按固定章节展示Claim与证据
明日观察条件：基准、阈值、T+1验证状态
数据缺口与来源
运行诊断 / Snapshot Lineage
```

客观数据优先于AI长文。用户即使关闭LLM，也能使用完整事实看板。

## 13. 盘后时序

```text
17:10        A股核心DataSnapshot认证目标
17:10-17:30  F1/F2核心FeatureSnapshot
17:30-17:44  板块、异动和热点ObservationSnapshot
17:44-17:50  全球观察低优先级任务
17:50-17:55  构建A_SHARE_CLOSE_CORE FactPack
17:55-18:20  DSA生成ReviewAnalysis和主ReviewReport
18:10-18:30  龙虎榜、融资融券、大宗等晚到A股能力
18:30-18:40  可选ReviewSupplement，资源冲突时让位于Formal Strategy
19:00        Formal Strategy硬截止
20:30        Correction审计；不静默重生成当时主报告
T+1收盘后    验证ReviewWatchCondition
```

主报告不等待全部晚到资金能力。晚到事实形成独立`A_SHARE_CLOSE_SUPPLEMENT` FactPack和补充报告，不覆盖主报告。

核心优先级：

```text
Certified Data
  > Paper Portfolio
  > Formal Strategy
  > Core FactPack
  > DSA AI Review
  > Review Supplement
  > Global Background
  > Heavy Backfill/Research
```

## 14. 失败与降级

### 14.1 FactPack失败

- Canonical身份、交易日或核心行情冲突：`FAILED`，不生成AI完整复盘；
- 市场宽度失败但指数可用：`PARTIAL`，发布指数和数据缺口；
- 情绪五维不完整：展示成功原始维度，不展示完整版情绪总分；
- 板块或热点失败：删除对应章节，不让AI推测主线；
- 新闻事件失败：明确“消息面数据不可用”，不能从模型知识补写今日消息；
- 全球失败：忽略可选块，不影响A股Pack状态；
- 晚到资金失败：主报告不受影响，补充报告不发布。

### 14.2 LLM失败

- FactPack和客观Web页面正常发布；
- 使用确定性模板生成摘要；
- ReviewAnalysis状态为`FALLBACK_TEMPLATE`；
- 保存模型失败诊断，不伪装AI成功；
- 通知明确“AI复盘未生成，以下为客观数据摘要”；
- 不自动换一个事实范围重新生成。

### 14.3 Renderer或通知失败

- ReviewAnalysis成功不因单一输出渠道失败而回滚；
- 每个Renderer和通知渠道单独记录Attempt；
- Web/Markdown/通知可以重试，但必须绑定原FactPack和ReviewAnalysis；
- 重试不重新调用LLM，除非用户显式创建新的ReviewAnalysis版本。

## 15. 修订和版本

```text
FeatureSnapshot v1
  → MarketCloseFactPack v1
  → ReviewAnalysis v1
  → ReviewReport v1

Correction FeatureSnapshot v2
  → MarketCloseFactPack v2
  → 可选ReviewAnalysis v2
  → ReviewReport v2
```

- v2不覆盖v1；
- 页面默认可以展示最新修订版，但必须提供“当时发布版”；
- v2若不重新调用LLM，可以只更新客观卡片并标记旧AI分析绑定v1；
- 若重新生成AI，必须形成新的ReviewAnalysis ID和Prompt/模型记录；
- T+1验证绑定WatchCondition原始Pack和指定验证Snapshot；
- 任何修订不得改写已经完成的ReviewValidation。

## 16. 数据模型和存储

### 16.1 PostgreSQL控制面

| 表族 | 主要职责 |
| --- | --- |
| `market_close_fact_pack` | Envelope、状态、Snapshot引用和Manifest Hash |
| `market_close_fact_block` | Block目录、状态、存储位置、覆盖和Hash |
| `review_run` | 逻辑生成任务、FactPack、优先级和状态 |
| `review_attempt` | LLM/模板Attempt、租约、诊断和错误 |
| `review_analysis` | 结构化AI输出、模型、Prompt和Hash |
| `review_claim` | Claim、类型、证据引用和支持状态 |
| `review_watch_condition` | T+1可机器验证条件 |
| `review_validation` | T+1验证结果和FeatureSnapshot |
| `review_report` | Web/Markdown/通知/分享图的版本和索引 |
| `review_consumer_binding` | 历史、通知、单股上下文和其他消费者引用 |

大块事实和榜单保存在Parquet/JSON产物；PostgreSQL保存控制、查询索引和小型结构化结果。

### 16.2 文件目录

```text
/data/daily_stock_analysis/
├── storage/app/factpacks/type=market_close/trade_date=YYYY-MM-DD/fact_pack_id=<fact_pack_id>/
│   ├── manifest.json
│   ├── indices.parquet
│   ├── breadth.parquet
│   ├── emotion-limit.parquet
│   ├── capital.parquet
│   ├── sectors.parquet
│   ├── hotspots.parquet
│   ├── events.parquet
│   └── data-gaps.json
├── storage/app/results/type=review/trade_date=YYYY-MM-DD/review_id=<review_analysis_id>/
├── storage/app/artifacts/type=market_review/year=YYYY/month=MM/artifact_id=<review_report_id>/
├── storage/app/quarantine/review/
├── storage/postgres/
├── logs/review-worker/
└── backups/
```

本文只定义目标目录，不在设计阶段创建目录或配置。

## 17. API边界

```text
GET  /api/v1/market-close-fact-packs?trade_date=&publication_status=&quality_status=
GET  /api/v1/market-close-fact-packs/{fact_pack_id}
GET  /api/v1/market-close-fact-packs/{fact_pack_id}/blocks/{block_type}
GET  /api/v1/market-close-fact-packs/{fact_pack_id}/lineage
POST /api/v1/market-reviews
GET  /api/v1/market-reviews/{review_analysis_id}
GET  /api/v1/market-reviews/{review_analysis_id}/claims
GET  /api/v1/market-reviews/{review_analysis_id}/watch-conditions
GET  /api/v1/market-reviews/{review_analysis_id}/validations
GET  /api/v1/market-review-reports/{review_report_id}
```

兼容入口`POST /api/v1/analysis/market-review`可以继续存在，由Adapter创建新ReviewRun并返回既有task状态格式。

API要求：

- 默认响应包含FactPack ID、cutoff、状态、缺口和修订标识；
- 大榜单分页或按Block读取；
- 普通用户只读已发布Pack和Report；
- 不暴露完整Prompt、密钥、内部错误栈和受版权保护的全文；
- 证据链接通过`fact_id`解析受控字段，不允许任意文件路径或SQL；
- 历史详情返回实际市场情绪分或空值，不再把固定50展示为权威事实。

## 18. 与当前DSA的迁移

### MR1：兼容Adapter

- 保留现有`MarketReviewRunResult`、任务状态、历史类型和Web入口；
- 新增FactPack/ReviewAnalysis对象，不立即删除v1 Payload；
- 从新ReviewReport生成兼容`market_review_payload.version=1`；
- 标记兼容字段和新权威字段的映射。

### MR2：事实来源切换

- `MarketAnalyzer`在平台模式不再直接抓市场、板块和搜索事实；
- 引入FactPack Builder和Prompt Projection；
- SearchService移到上游Event/Intelligence采集；
- 旧直抓模式只保留为独立DSA兼容运行，不允许产出平台正式FactPack。

### MR3：情绪和结构统一

- 新Payload引用D-025市场情绪快照；
- Market Light降为兼容视图，不再作为第二公式权威；
- 固定`sentiment_score=50`从用户可见权威字段移除；
- 若旧表暂时不可为空，则50仅保存在legacy字段并显式标记`legacy_placeholder=true`。

### MR4：Web和历史升级

- 客观卡片读取FactPack Block；
- AI章节读取ReviewAnalysis；
- 增加证据抽屉、数据缺口、版本、修订和T+1验证；
- 旧历史没有FactPack时继续使用v1 Payload并标记`LEGACY_UNTRACED`。

### MR5：通知和单股上下文

- 通知由同一ReviewReport渲染；
- 单股分析只消费低敏DailyMarketContext投影，不获得完整FactPack和原始新闻；
- 核心A股市场环境可以影响单股AI文字护栏，但不能绕过StrategySpec和WeightPolicy修改正式仓位。

## 19. 安全、确定性和审计

- FactPack Builder无Provider凭据和外部网络访问；
- LLM只接收低敏、裁剪后的Prompt Projection；
- Prompt不得包含通知配置、账户隐私、数据库路径或Provider密钥；
- 新闻只传标题、短摘要、来源、时间和URL；
- AI输出Schema校验、证据引用校验和长度限制失败时拒绝正式发布；
- FactPack构建是确定性的，相同Manifest重复构建得到相同Hash；
- LLM文本不要求重跑逐字确定，但持久化输出、Hash和模型诊断支持历史复现；
- Renderer对同一FactPack和ReviewAnalysis应生成相同规范化Markdown Hash；
- 运行日志记录Pack、Analysis、Report和Attempt ID，不记录完整敏感Prompt；
- 所有Correction、重新生成和手工触发保存审计来源。

## 20. 资源预算

```yaml
close_review_runtime:
  fact_pack_worker_count: 1
  review_worker_count: 1
  max_parallel_llm_runs: 1
  fact_pack_max_threads: 2
  prompt_projection_max_bytes: 120000
  main_review_deadline: "18:20"
  late_supplement_enabled: true
  pause_on_formal_strategy_pressure: true
```

- FactPack组装主要读取已聚合Mart，禁止现场全市场重算；
- LLM同时只运行一个主复盘；
- Formal Strategy资源压力出现时暂停DSA AI，不暂停已发布客观Pack；
- 分享图按需生成，不占盘后核心窗口；
- T+1验证是少量确定性比较，随次日FeatureSnapshot增量运行。

## 21. 实施阶段

### RC1：Schema和Builder

- 定义FactPack Envelope、Block、状态和证据ID；
- 对接Feature/Observation/Global Snapshot；
- 完成Zero-fetch Builder、Manifest Hash和质量门禁；
- 用固定交易日构造golden FactPack。

### RC2：DSA ReviewAnalysis

- 定义Prompt Projection和ReviewAnalysis Schema；
- 改造Prompt为固定章节和证据引用；
- 实现Claim支持校验、模板fallback和运行诊断；
- 保留现有LLM后端与通知兼容。

### RC3：Web和Report

- 客观卡片改读Block；
- 增加证据、缺口、修订和Lineage；
- 同源渲染Markdown、通知和分享图；
- 兼容旧历史Payload。

### RC4：短线指标和T+1验证

- 注册赚钱效应、晋级率、连板溢价和梯队断层指标；
- 纳入FeatureSnapshot和FactPack；
- 实现WatchCondition和ReviewValidation；
- 明确其不进入策略域。

### RC5：晚到补充与迁移收尾

- 接入晚到A股资金补充Pack；
- 移除平台模式下MarketAnalyzer直接抓取；
- 收敛Market Light和固定50兼容字段；
- 完成备份、恢复和修订回放演练。

## 22. 验收标准

1. Visory复盘模式生成复盘时不直接调用外部行情、板块或搜索Provider；
2. FactPack绑定不可变Feature/Observation Snapshot并满足时间门禁；
3. 同一Snapshot和Builder版本重复构建得到相同Manifest Hash；
4. 页面、Markdown、通知和历史引用同一FactPack和ReviewAnalysis；
5. 重要AI Claim均有有效证据ID，无法支持的Claim不会进入正式报告；
6. 情绪事实来自D-025，固定50不再作为用户可见权威情绪分；
7. 板块和热点只展示独立客观指标、榜单和原因，不生成平台统一评分；
8. 资金行为不会被表述为确认的主力或机构账户来源；
9. 全球背景失败不会降低A股FactPack核心状态，也不进入策略或回测；
10. LLM失败时客观看板和模板摘要仍可发布；
11. 新闻缺失时AI不会补写FactPack外的今日消息；
12. Correction和晚到补充不会覆盖当时主FactPack与报告；
13. T+1观察条件保存指标、版本、阈值、基准和验证Snapshot；
14. ReviewValidation只输出命中状态，不计算或展示策略收益；
15. 若观察逻辑进入Strategy，必须新建Indicator/StrategySpec并由Hikyuu独立验证；
16. 当前服务器在18:20前完成核心FactPack和主复盘，资源压力时Formal Strategy优先；
17. 旧DSA市场复盘历史仍可展示并明确标记Legacy；
18. 任意ReviewReport可追溯至FactPack、FeatureSnapshot、DataSnapshot、ProviderRun和Raw Hash。

## 23. MVP实现基线

1. 首批指数固定为上证综指、沪深300、深证成指、创业板指和中证500；事实字段来自已发布F1/F2，不在Review中重新计算；
2. Prompt裁剪由版本化Prompt/Resource Policy管理：板块最多20条、热点股最多30条、事件最多20条，关键缺口全部保留；总Token预算由模型能力配置且超限按确定性优先级裁剪；
3. 晚到资金Correction默认只更新页面和版本提示，不再次主动通知；owner可在通知Policy中显式启用；
4. Legacy `sentiment_score`按Expand方式改为可空并双读验证，缺失不回填固定50；
5. MVP正式Review仅生成`zh-CN`结构化结果；旧多语言能力继续兼容，目标多语言在后续采用固定结构化结果的版本化翻译投影；
6. 首批WatchCondition只允许指数收益/区间、市场宽度、涨跌停、成交、板块相对强度和版本化规则事件；禁止自由文本条件直接执行。

实现顺序为`WP-0501`至`WP-0505`，详见[实施路线与验收方案 v1](implementation-roadmap-and-acceptance-v1.md)。

## 24. 参考资料

- [daily_stock_analysis当前大盘复盘实现](https://github.com/ZhuLinsen/daily_stock_analysis/blob/main/src/core/market_review.py)
- [daily_stock_analysis当前MarketAnalyzer](https://github.com/ZhuLinsen/daily_stock_analysis/blob/main/src/market_analyzer.py)
- [daily_stock_analysis AnalysisContextPack设计](https://github.com/ZhuLinsen/daily_stock_analysis/blob/96bc532dfcb21e3a7d0fdbdfa87d764b9b61d2ee/docs/analysis-context-pack.md)
- [Vibe-Research每日复盘与数据看板](https://github.com/simonlin1212/Vibe-Research)
- [vibe-astock短线复盘和派生情绪指标](https://github.com/simonlin1212/vibe-astock)
- [A 股 Feature Store 与指标注册中心架构 v1](feature-store-architecture.md)
- [A 股市场情绪与资金行为架构 v1](market-sentiment-and-capital-flow-architecture.md)
- [A 股板块异动、热门观察与策略评分边界 v1](sector-observation-and-strategy-scoring-architecture.md)
- [全球市场观察与 A 股策略隔离架构 v1](global-market-observation-boundary.md)
- [StrategySpec v1 策略契约](strategy-spec-v1.md)
- [A 股分层个股研究与 StockResearchFactPack 架构 v1](stock-research-architecture.md)
- [A 股主平台模块化单体、API、任务与权限架构 v1](platform-shell-api-task-permission-architecture.md)
- [A 股平台 Docker、Cloudflare、NPM 与访问安全架构 v1](docker-cloudflare-npm-deployment-architecture.md)
