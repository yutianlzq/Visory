# Visory 分层个股研究与 StockResearchFactPack 架构 v1

状态：Design Approved
最后更新：2026-08-28

## 1. 决策摘要

本模块落实架构决策 **D-030**：

- DSA现有Agent、ResearchAgent、LLM路由、任务、历史和报告能力作为统一个股研究运行时；
- 个股研究分为L0客观事实卡、L1快速研究和L2深度研究；
- UZI-Skill主要参考快速扫描、覆盖矩阵、证据阶梯、研究方法和机械自查门禁；
- TradingAgents-astock主要参考七类A股分析师、多空辩论、三视角风险审查、Research Manager和断点续跑；
- 不把两个外部项目的Provider、缓存、CLI、Web和完整Agent运行栈直接部署进主平台；
- L1和L2共用不可变`StockResearchFactPack`，Agent不各自重复抓取同一份事实；
- 默认`CERTIFIED_ONLY`研究模式只读取平台已经发布的数据；用户显式允许开放研究时，外部资料必须先形成可追溯`ExternalEvidenceSupplement`；
- 研究结果进入独立Research Result域，不写回Feature Store，不自动成为StrategySignal、个股评分、资金权重或Hikyuu输入；
- UZI的命名投资人评审团和统一总分不作为平台权威能力；只吸收通用投资流派、机构研究方法和数据质量门禁；
- TradingAgents中的Trader和Portfolio Manager执行语义不迁入核心研究域；深度研究不输出建仓价、止损价、目标价和账户仓位；
- v1深度研究默认只生成候选并由用户确认执行，当前服务器每天最多运行一个深度研究任务。

## 2. 目标

个股研究模块的目标是让用户对重点股票得到结构化、可验证、可复现的研究，而不是让多个Agent自由上网后给出无法追溯的一致“结论”。

v1必须满足：

1. 股票专属输入只使用带市场前缀的`canonical_id`并校验`asset_type=stock`，跨域事实关联使用`entity_key`；
2. 快速和深度研究读取同一套行情、财务、估值、资金、事件、题材和市场事实；
3. 所有重要观点能够引用Fact ID或独立外部证据ID；
4. 数据不足时输出`INSUFFICIENT_EVIDENCE`，不使用模型知识填补当日事实；
5. 多Agent研究保留分歧、反方证据和未解决问题；
6. 研究倾向和置信度不能自动映射成策略、仓位或权重；
7. 研究触发、资源预算、超时、取消和断点恢复可审计；
8. 相同FactPack、研究Profile和问题可以安全复用已完成结果；
9. 当前服务器不批量运行全市场或全自选的深度多Agent分析；
10. 外部项目的有价值设计通过受控模块迁入，不形成第二套数据真源和第二套主平台。

## 3. 非目标与边界

v1不负责：

- 为全A股每天自动生成AI研究报告；
- 用AI研究结果直接选股、下单或改变组合仓位；
- 把多个模拟投资人分数平均为平台统一个股分；
- 让Agent通过任意Shell、文件、数据库或网络访问自行找数据；
- 让七个Agent分别调用a-stock-data或Financial-API造成重复请求和口径冲突；
- 把Research Manager结论作为无条件事实；
- 用T+1收益训练或反向修改已经发布的研究文本；
- 把全球市场因素加入A股研究评级或策略解释；
- 直接复用TradingAgents的交易执行、Portfolio Manager仓位和可执行价位语义；
- 在没有披露时间的情况下使用财务、公告、解禁或政策信息；
- 把策略评分或模拟盘收益包装成AI研究能力。

平台可以展示StrategySignal与ResearchResult之间的差异，但两者始终是独立输出。

## 4. 项目参考与复用边界

### 4.1 daily_stock_analysis

复用或演进：

- `AnalysisContextPack`的块状态、质量限制和低敏投影思想；
- `ResearchAgent`拆题、逐题研究、综合和token/超时预算；
- Technical、Intel、Risk、Decision和Skill Agent协议；
- LLM后端、Tool Surface、工具超时、取消和运行诊断；
- 结构化观点、无效观点隔离、分歧汇总和历史持久化；
- API/Bot `/research`兼容入口和Web任务进度。

需要收敛：

- 当前ResearchAgent可以自由调用搜索、行情和历史工具，目标平台正式模式必须改读StockResearchFactPack；
- 当前Agent使用`buy/hold/sell`和通用`sentiment_score`，研究域改用非交易`research_stance`；
- 当前多个Agent可能各自补取数据，目标平台改为一次组包、多Agent只读；
- 当前自由文本findings需要升级为Claim、Evidence和Data Limitation契约。

### 4.2 UZI-Skill

参考：

- `quick-scan`、标准分析和深度研究的分档思路；
- 多维数据覆盖矩阵和缺失维度展示；
- DCF、可比公司、财报、催化日历、陷阱检测等专项研究方法；
- 证据阶梯、供应链层级、罚分因子和研究报告自查；
- 关键问题未修复时阻止报告发布的机械Gate；
- 数据抓取与报告渲染分阶段、失败维度可见。

不迁入：

- 以现实投资人姓名模拟“本人观点”；
- 66位评审团和统一平均分作为平台结论；
- 独立22路Provider抓取和本地缓存作为平台数据源；
- UZI自己的HTML、CLI、自动更新和插件运行时；
- 对所有标的默认执行完整22维和全部机构方法。

平台可以定义价值、成长、质量、趋势、事件驱动、短线、逆向和风险等通用`ResearchLens`，但必须标注为AI方法视角，不冒充真实人物意见。

### 4.3 TradingAgents-astock

参考：

- 市场/技术、情绪、新闻、基本面、政策、资金行为和解禁七类A股分析师；
- Bull/Bear研究辩论；
- Aggressive/Conservative/Neutral三视角风险审查；
- Research Manager综合分歧和证据；
- quick/deep模型分层、结构化输出、checkpoint和运行历史；
- A股T+1、涨跌停、交易日和ST等研究语境。

不迁入：

- mootdx、东财、新浪、同花顺等直连链路作为研究真源；
- 完整LangGraph、Streamlit、SQLite缓存和CLI形成第二运行栈；
- Trader、Portfolio Manager和交易方向直接进入平台策略；
- 30至50次无上限LLM调用；
- Agent自由选择未冻结的数据窗口或“最新”数据；
- 研究记忆反向改写历史报告。

若直接迁移外部源代码，必须保留UZI-Skill的MIT许可和TradingAgents-astock的Apache-2.0 NOTICE要求；只参考设计时仍应记录来源。

## 5. 分层研究模型

| 层级 | 名称 | AI | 主要用途 | 目标时延 |
| --- | --- | --- | --- | --- |
| L0 | `STOCK_FACT_CARD` | 无 | 页面快速查看、触发前检查 | 秒级 |
| L1 | `QUICK_RESEARCH` | 单Agent/单综合调用 | 自选、热点、策略候选的快速梳理 | 30～90秒 |
| L2 | `DEEP_RESEARCH` | 多Agent、辩论和风险审查 | 用户确认的重点标的 | 10～30分钟 |

### 5.1 L0客观事实卡

展示：

- 股票身份、上市状态、板块和题材；
- 收盘、涨跌幅、量能、流动性和技术结构；
- 财务、估值、资金和事件摘要；
- 解禁、减持、质押、监管和交易风险；
- FeatureSnapshot、cutoff和数据缺口。

L0由页面直接读取StockResearchFactPack，不调用LLM。

### 5.2 L1快速研究

一次结构化LLM调用，从九个研究方向给出证据化摘要。它不是UZI完整22维分析，也不启动多Agent辩论。

### 5.3 L2深度研究

七个分析角色读取同一FactPack，经过多空辩论、风险审查和Research Manager综合，最后通过机械自查门禁。默认只运行一个辩论轮次和一个风险轮次。

## 6. 总体架构

```text
User / Watchlist / Event / Strategy Candidate
                       │
                       ▼
                ResearchRequest
                       │
             Trigger / Budget / Dedup
                       │
                       ▼
            StockResearchFactPack Builder
                       │
        ┌──────────────┴──────────────┐
        │                             │
  L1 QuickResearch              L2 DeepResearch
  single synthesis          7 Analysts / Debate / Risk
        │                             │
        └──────────────┬──────────────┘
                       ▼
             Research Self-Review Gate
                       │
                       ▼
        ResearchResult / Report / History
                       │
              Human review only
                       │
       optional manual promotion proposal
                       │
            Indicator / StrategySpec
```

ResearchResult不能直接沿箭头写入Strategy。任何“promotion proposal”只生成待人工审查的指标或策略需求，不携带自动批准权限。

## 7. StockResearchFactPack

### 7.1 Envelope

```yaml
fact_pack_id: fact_<uuidv7>
schema_version: 1.0.0
pack_type: A_SHARE_STOCK_RESEARCH
canonical_id: sh600519
asset_type: stock
entity_key: stock:sh600519
trade_date: 2026-08-27
cutoff_at: 2026-08-27T19:00:00+08:00
created_at: 2026-08-27T19:05:00+08:00
published_at: 2026-08-27T19:06:00+08:00
publication_status: CERTIFIED
quality_status: COMPLETE
revision: 1
revision_kind: INITIAL
data_snapshot_ids:
  - ds_<uuidv7>
feature_snapshot_ids:
  - fs_<uuidv7>
market_close_fact_pack_id: fact_<uuidv7>
sector_observation_snapshot_id: obs_<uuidv7>
block_ids: []
max_source_available_at: 2026-08-27T18:58:32+08:00
missing_capabilities: []
builder_version: 1.0.0
manifest_hash: sha256:...
```

### 7.2 顶层规则

- 股票专属上下文使用`canonical_id`，跨域正式关联使用`entity_key=stock:sh600519`；
- 资产类型不是stock时拒绝使用本契约；
- 全部事实满足`available_at <= cutoff_at`；
- 财务、公告、事件、板块成员和股票状态使用PIT版本；
- FactPack只引用已发布Data/Feature/Observation/MarketClose Snapshot；
- 全球观察不进入StockResearchFactPack；
- ResearchRequest、用户问题、策略候选和持仓身份属于控制面触发上下文，不写进公共事实块；
- Pack发布后不可变；新财报、公告、资金或Correction形成新Pack；
- 同一Pack可以被多个ResearchProfile复用。

### 7.3 Pack质量状态

```text
COMPLETE
PARTIAL
FAILED
```

核心身份、行情或交易日失败时为`FAILED`。财务、估值、资金或事件部分缺失时可以`PARTIAL`，但对应研究结论必须降低证据等级。

## 8. FactPack事实块

每个Block复用`AVAILABLE/PARTIAL/MISSING/NOT_SUPPORTED/FALLBACK/STALE/ESTIMATED/FETCH_FAILED`状态，并保存Fact ID、来源快照、覆盖率、警告和Block Hash。

### 8.1 `IDENTITY_AND_STATUS`

- 名称、交易所、板块、上市/退市、ST和停牌状态；
- 上市日期、新股冷却、流通股本和总股本；
- 当日涨跌停规则、交易状态和公司行动；
- 行业、概念和题材的PIT归属；
- 证券身份冲突和Provider原始代码。

### 8.2 `PRICE_TECHNICAL_LIQUIDITY`

- 未复权成交价格和PIT复权指标；
- 收益、趋势、MA、MACD、RSI、KDJ、ATR、波动率；
- 成交额、换手、量比、流动性和ADV；
- 新高新低、支撑阻力的客观计算输入；
- 涨跌停、停牌和不可交易状态；
- 相对指数和同行业表现。

技术指标来自Feature Store/Hikyuu公式权威，研究Agent不重新计算。

### 8.3 `MARKET_SECTOR_THEME_POSITION`

- 当日A股市场情绪、宽度和市场状态；
- 所属行业/概念的收益、宽度、资金和持续性；
- 股票在板块中的收益、成交额、市值和公开排名；
- 热点榜、异动、连板梯队和全部入榜原因；
- 题材关系、证据等级和current-only限制；
- 个股是领涨、跟随或边缘角色的客观输入。

本块不生成平台统一热点分或个股分。

### 8.4 `CAPITAL_BEHAVIOR`

- Provider订单规模资金证据和可信度；
- 龙虎榜席位、上榜原因和披露时间；
- 融资融券余额、变化和滞后交易日；
- 大宗交易、股东户数和公开持仓变化；
- 互联互通活跃度等可用证据；
- 资金数据缺失、估算、来源冲突和历史限制。

只能描述公开资金行为，不确认“庄家、主力、机构正在吸筹或出货”。

### 8.5 `FUNDAMENTAL_QUALITY`

- 营收、利润、现金流和同比/环比；
- 毛利率、净利率、ROE、ROIC和杜邦拆分；
- 资产负债、偿债、营运、存货和应收；
- 盈利质量、自由现金流和分红；
- 财报报告期、公告日、修订和审计状态；
- 一致预期仅在来源、发布时间和覆盖明确时使用。

### 8.6 `VALUATION`

- PE、PB、PS、EV/EBITDA、股息率等适用指标；
- 自身历史分位和同行可比；
- 盈利为负、周期和金融行业的适用性限制；
- DCF/可比估值所需输入覆盖；
- 估值模型版本、假设和敏感性结果。

DCF不作为L1默认步骤。只有输入覆盖通过时，L2专项方法才运行；缺少关键输入时输出`NOT_APPLICABLE`或`INSUFFICIENT_EVIDENCE`，不能用任意假设填满模型。

### 8.7 `EVENTS_NEWS_POLICY`

- 公告、财报、监管、处罚和问询；
- 公司、行业和政策事件；
- 新闻、研报摘要、来源、URL和发布时间；
- 事件实体、题材关系、重要性和证据级别；
- 相互冲突的消息和未经验证线索；
- 催化日历和未来已公告时间点。

本块不保存未经许可的完整新闻或研报正文。

### 8.8 `OWNERSHIP_SUPPLY_RISK`

- 限售解禁数量、占比、日期和持有人；
- 股东、高管减持/增持计划及执行；
- 股权质押、担保、诉讼和监管风险；
- 大股东、实际控制人和治理变化；
- 可转债、再融资、配股等潜在供给；
- 退市、风险警示和交易异常。

### 8.9 `PEER_COMPARISON`

- point-in-time同行集合和Taxonomy版本；
- 市值、成长、盈利、估值、流动性和相对收益；
- 同行中位数、分位和样本数；
- 业务不可比、分类重叠和样本不足；
- 不生成平台总排名或荐股排序。

### 8.10 `DATA_GAPS`

- 缺失、Fallback、Stale、Estimated和Provider冲突；
- 不可用维度、滞后交易日和覆盖率；
- current-only事实及历史不可用说明；
- 对L1/L2角色和研究方法的影响；
- 外部证据补充是否被允许。

本块始终存在。

## 9. ExternalEvidenceSupplement

### 9.1 研究模式

| 模式 | 网络 | 用途 |
| --- | --- | --- |
| `CERTIFIED_ONLY` | 禁止Agent自由网络 | 默认自动和正式平台研究 |
| `OPEN_RESEARCH` | 允许受控Evidence Gateway | 用户显式发起的开放资料研究 |

### 9.2 外部证据流程

```text
Agent提出EvidenceRequest
  → Evidence Gateway校验域名、类型、预算和股票范围
  → 抓取/读取公开资料
  → 保存来源、发布时间、抓取时间、内容Hash和许可状态
  → 生成ExternalEvidenceSupplement
  → 新ResearchProjection提供给后续Agent
```

Agent不能直接把自由搜索结果写入结论。外部证据至少保存：

```text
external_evidence_id
canonical_id / entity_ids[]
evidence_type / title / source / url
published_at / available_at / retrieved_at
summary / content_hash
license_status / retention_policy
quality_status / contradiction_group
requesting_agent / request_reason
```

付费墙、登录态、Cookie、个人账户内容和不明转载默认不进入平台持久证据。外部资料缺失不会触发Agent绕过安全边界。

## 10. ResearchRequest与触发

### 10.1 ResearchRequest

```yaml
research_request_id: request_<uuidv7>
canonical_id: sh600519
requested_level: QUICK_RESEARCH
research_profile_id: quick-default-1.0.0
research_mode: CERTIFIED_ONLY
question: null
trigger_type: STRATEGY_CANDIDATE
trigger_ref: prediction_<uuidv7>
requested_by: system
priority: normal
created_at: ...
fact_pack_id: null
```

`trigger_ref`用于解释为何研究，不进入事实证据链。账户持仓等私有触发只保存在受权限保护的控制面。

### 10.2 L1允许触发

- 用户手动请求；
- 自选股出现重大公告、监管、解禁或财报；
- 股票进入热点、成交额或涨停/异动榜；
- 股票进入某个正式Strategy的候选TopN；
- 持仓股票出现高等级风险事件；
- 上一次FactPack后发生足以改变关键Block的事实。

自动L1只生成研究结果，不回写触发它的Strategy或Paper Portfolio。

### 10.3 L2候选

v1以下条件只生成`DeepResearchCandidate`：

- 两个及以上已激活策略同时选择同一股票；
- QuickResearch与StrategySignal、基本面和事件证据明显冲突；
- 高等级财报、监管、重组、解禁或政策事件；
- 重点持仓出现重大风险；
- 用户标记为重点研究；
- 已有深度研究过期且FactPack发生实质变化。

DeepResearchCandidate包含原因、FactPack状态、预计调用数、token、耗时和截止时间。用户确认后才创建L2 ResearchRun。

### 10.4 去重和复用

复用键：

```text
canonical_id
stock_fact_pack_hash
research_level
research_profile_hash
normalized_question_hash
research_mode
external_evidence_bundle_hash
```

相同键的成功结果直接复用。用户选择重新分析时产生新ResearchRun和Analysis版本，不覆盖旧结果。

## 11. L1 QuickResearch

### 11.1 九方向模板

1. 公司身份和交易状态；
2. 价格、技术和流动性；
3. 市场、板块、题材和个股角色；
4. 公开资金行为；
5. 财务质量；
6. 估值和同行比较；
7. 公告、新闻、政策和催化；
8. 解禁、减持、质押和治理风险；
9. 数据缺口和待验证事项。

### 11.2 QuickResearchResult

```yaml
quick_research_id: research_<uuidv7>
research_run_id: research_<uuidv7>
fact_pack_id: fact_<uuidv7>
profile_version: quick-default-1.0.0
research_stance: NEUTRAL
evidence_strength: MIXED
core_thesis: ...
positive_claims: []
risk_claims: []
catalysts: []
invalidation_conditions: []
open_questions: []
data_limitations: []
generated_at: ...
model_identity: ...
prompt_version: ...
raw_response_hash: ...
result_hash: ...
```

`research_stance`：

```text
POSITIVE
NEUTRAL
CAUTIOUS
INSUFFICIENT_EVIDENCE
```

它是AI研究观点，不是交易方向。`evidence_strength`使用`STRONG/MIXED/WEAK/INSUFFICIENT`，不输出0～100平台个股总分。

## 12. L2 DeepResearch

### 12.1 七类分析角色

| 角色 | 重点 | 主要Block |
| --- | --- | --- |
| MarketTechnicalAnalyst | 趋势、量价、流动性、相对强弱 | Price/Technical |
| AttentionSentimentAnalyst | 热度、榜单、短线生态和公开讨论证据 | Market/Sector、Events |
| NewsEventAnalyst | 公告、新闻、财报事件和矛盾信息 | Events/News |
| FundamentalValuationAnalyst | 财务质量、估值、同行和模型适用性 | Fundamental、Valuation、Peer |
| PolicyIndustryAnalyst | 政策、行业景气、产业链和题材证据 | Events、Market/Sector |
| CapitalBehaviorAnalyst | 资金证据、龙虎榜、两融和大宗 | Capital |
| SupplyRiskAnalyst | 解禁、减持、质押、治理和供给冲击 | Ownership/Supply/Risk |

“情绪分析师”只有获得公开、可追溯的关注度或讨论数据时才能评价情绪；缺少社交数据时不得凭新闻标题推断散户情绪。

### 12.2 AgentResearchMemo

每个角色输出统一Schema：

```text
agent_memo_id / role / research_run_id
stance / evidence_strength
claims[] / counter_evidence[]
key_facts[] / evidence_refs[]
uncertainties[] / data_limitations[]
requested_external_evidence[]
model / prompt / token_usage / duration
memo_hash
```

角色不能输出最终平台策略或账户动作。

### 12.3 多空辩论

```text
7 AgentResearchMemo
  → Bull Researcher构建最强支持论证
  → Bear Researcher构建最强反对论证
  → 一轮交叉反驳
  → DisagreementMap
```

双方必须引用已有证据，不能通过新增未经登记事实赢得辩论。输出：

```text
agreements
material_disagreements
assumption_conflicts
evidence_conflicts
missing_evidence
conditions_that_would_change_each_side
```

默认只运行一轮。增加轮次需要用户选择新的ResearchProfile和更高预算。

### 12.4 风险三视角

| 视角 | 职责 |
| --- | --- |
| Aggressive | 在承认风险的前提下检验上行情景是否有充分证据 |
| Conservative | 寻找永久损失、流动性、事件、治理和供给风险 |
| Neutral | 检查两端遗漏、证据质量、概率不对称和无法判断项 |

风险角色只形成研究风险图，不生成仓位比例和止损价。

### 12.5 Research Manager

Research Manager输出：

- 核心研究命题；
- 已验证事实；
- 支持与反对证据；
- 真正分歧；
- 催化、风险和失效条件；
- 证据强度和数据缺口；
- 后续研究清单；
- `research_stance`。

Manager不能删除少数派分歧，不能把Agent投票数当成事实强度，也不能把7个角色的意见平均成平台分数。

## 13. Claim与Evidence契约

```yaml
research_claim_id: claim_<uuidv7>
claim_type: INFERENCE
text: 公司盈利增长较快，但经营现金流覆盖不足。
evidence_refs:
  - stock.sh600519.net_profit_yoy
  - stock.sh600519.ocf_to_net_profit
support_status: SUPPORTED
source_roles:
  - FundamentalValuationAnalyst
counter_evidence_refs: []
limitations: []
```

`claim_type`：

```text
FACT_SUMMARY
INFERENCE
SCENARIO
RISK
DATA_LIMITATION
OPEN_QUESTION
```

`support_status`：

```text
SUPPORTED
PARTIAL
UNSUPPORTED
CONTRADICTED
```

重要Claim缺少有效Evidence时不得进入正式报告。`UNSUPPORTED`和`CONTRADICTED`保留在诊断和分歧图中。

## 14. 研究流派和专项方法

### 14.1 ResearchLens

平台可配置通用视角：

```text
VALUE
GROWTH
QUALITY
MOMENTUM
EVENT_DRIVEN
SHORT_TERM
CONTRARIAN
RISK_FIRST
```

Lens只改变问题重点和FactPack投影，不改变事实。报告显示“价值视角”等通用名称，不显示为真实投资人本人意见。

### 14.2 专项方法

| 方法 | 启用条件 |
| --- | --- |
| DCF | 财务预测、资本成本和现金流输入覆盖通过 |
| 可比公司 | PIT同行集合、样本数和可比指标完整 |
| 财报分析 | 新财报已披露且核心三表通过质量门禁 |
| 催化日历 | 公告/事件日期和来源可验证 |
| Thesis Tracker | 已有历史研究命题和当前新FactPack |
| Trap Detection | 治理、质押、股东、异常交易和事件覆盖可用 |
| Sector Overview | 行业成员和板块FactPack可用 |

方法输出是ResearchAttachment，不直接修改主ResearchResult。专项方法不满足输入条件时拒绝运行，不使用LLM虚构估值参数。

## 15. 研究与策略硬隔离

```text
StockResearchFactPack ───────→ ResearchResult
          │
          └─────────────────→ StrategySpec/Hikyuu（只读原始事实）

ResearchResult ──X──→ StrategySignal
ResearchStance ──X──→ WeightPolicy
ResearchConfidence ─X──→ Position Size
```

- 策略和研究可以引用相同FeatureSnapshot；
- StrategySpec不能引用`research_stance`、Research Manager文本或Agent投票；
- Paper Portfolio和Formal Backtest不读取ResearchResult；
- AI动态仓位只能通过已确认的AIAllocationOverlay契约读取独立AllocationFactPack，不能复用个股研究倾向；
- 若用户希望把研究条件策略化，系统只生成`StrategyPromotionProposal`草稿；
- 草稿必须转为IndicatorDefinition/StrategySpec、通过PIT审核和Hikyuu样本外验证后才能启用。

## 16. 机械自查门禁

吸收UZI自查思想，正式发布前运行确定性检查。

### 16.1 Critical Gate

以下任一问题阻止发布：

1. `canonical_id`、股票名称、交易日或Snapshot不一致；
2. 数值Claim没有有效Fact ID或外部证据ID；
3. 使用`available_at > cutoff_at`的事实；
4. 使用当前板块成员、最终财报或修订数据回填历史研究；
5. 多Agent读取了不同未声明Snapshot；
6. 把资金证据写成确认的主力/机构账户意图；
7. 把ResearchResult写成StrategySignal、仓位或可执行价位；
8. Critical反面证据从最终报告消失；
9. 数据不足却输出强证据或高确定性；
10. Research Manager隐去Material Disagreement；
11. 引用不存在、被裁剪或不允许持久化的外部内容；
12. 输出Schema、Hash或模型诊断不完整。

### 16.2 Warning Gate

- Block为Partial/Fallback/Stale；
- 同行样本过少；
- 估值方法适用性有限；
- 事件只有单一来源；
- Agent结论高度集中但证据重复；
- 问题超出FactPack覆盖；
- LLM或Agent阶段发生降级。

Warning不一定阻止发布，但必须进入Data Limitations。

### 16.3 Repair

结构错误、缺少Evidence Ref或遗漏限制可以允许一次受控修复调用。修复只读取原FactPack和诊断，不新增事实；修复后重新执行全部Gate。Critical仍存在则状态为`QUALITY_BLOCKED`。

## 17. 资源预算

### 17.1 L1

```yaml
quick_research_runtime:
  max_concurrency: 1
  max_daily_auto_candidates: 5
  llm_call_budget: 1
  token_budget: 8000
  timeout_seconds: 90
  evidence_mode: CERTIFIED_ONLY
```

### 17.2 L2

```yaml
deep_research_runtime:
  max_concurrency: 1
  auto_execute: false
  max_daily_runs: 1
  analyst_concurrency: 2
  analyst_count: 7
  debate_rounds: 1
  risk_rounds: 1
  llm_call_budget: 14
  token_budget: 60000
  timeout_seconds: 1800
  checkpoint_enabled: true
  evidence_mode: CERTIFIED_ONLY
```

默认调用预算：7个Analyst、Bull/Bear、3个风险视角、Research Manager以及最多一次修复，共13至14次。超过预算时不能静默继续。

只有Research Manager使用`deep_think`模型；Analyst、Bull/Bear和Risk默认使用`quick_think`模型。模型身份和Prompt版本逐阶段保存。

## 18. 盘后调度

```text
19:00        T日Formal Strategy硬截止
19:05-19:15  生成ResearchRequest和DeepResearchCandidate
19:15-20:00  最多5只L1 QuickResearch，单并发
20:30        Correction审计优先
20:40-23:30 用户确认的L2 DeepResearch，最多1只
00:30以后   不继续启动新L2；为数据回填和维护让出资源
T+1以后     新FactPack触发研究stale检查，不覆盖旧报告
```

用户盘中手动请求L1/L2时，如果与16:00至19:00核心收盘流水线冲突，任务进入队列并显示预计开始时间。手动请求不拥有抢占Certified Data和Formal Strategy的权限。

## 19. 运行状态、取消和恢复

```text
queued
  → resolving_fact_pack
  → validating_inputs
  → running_analysts
  → debating
  → risk_review
  → synthesizing
  → self_review
  → publishing
  → succeeded / partial / quality_blocked / failed

任意可取消阶段 → cancelling → cancelled
```

- L1跳过不适用的多Agent阶段；
- L2每个Agent和辩论阶段完成后写Checkpoint；
- 恢复必须绑定同一FactPack、Profile、Prompt和模型路由；
- FactPack发生变化时旧Checkpoint不能续跑，创建新Run；
- 取消后保留已完成Memo和诊断，但不发布不完整正式报告；
- 超时不会让后台Agent继续写结果；
- 重试生成新Attempt，不覆盖旧Attempt。

## 20. 失败和降级

### 20.1 FactPack

- 身份/核心行情失败：不运行研究；
- 财务或估值缺失：允许Partial，相关角色输出不足；
- 事件/新闻失败：禁止模型凭知识补写今日事件；
- 资金能力缺失：Capital Analyst输出Data Limitation；
- 全球观察缺失：无影响，因为不在Pack中；
- 外部证据Gateway失败：回到已认证事实，不能绕过。

### 20.2 L1

- LLM失败：L0事实卡仍可用；
- Schema失败：允许一次修复；
- 超时：保存失败诊断，不发布空QuickResult；
- FactPack Partial：Result必须显示相同缺口。

### 20.3 L2

- 单个Analyst失败：保留其他Memo并标记Partial；
- 少于5个有效Analyst：不进入正式综合；
- Bull或Bear缺失：不称为完成的多空辩论；
- Risk三视角少于2个：不发布正式风险审查；
- Research Manager失败：已完成Memo只作为诊断，不发布最终报告；
- Self-Review Critical未清零：`QUALITY_BLOCKED`；
- 任何降级不能通过重新加权Agent票数伪装完整成功。

## 21. ResearchResult和报告

### 21.1 DeepResearchResult

```text
deep_research_id
research_run_id / fact_pack_id
research_profile_id / research_mode
research_stance / evidence_strength
core_thesis
verified_facts[]
positive_claims[] / risk_claims[]
material_disagreements[]
catalysts[] / invalidation_conditions[]
open_questions[] / data_limitations[]
agent_memo_ids[]
debate_id / risk_review_id
external_evidence_bundle_id
model_manifest / prompt_manifest
created_at / result_hash
```

### 21.2 页面

```text
股票身份 / Pack日期 / 截止时间 / 状态 / stale标记
L0客观事实卡
核心研究命题
正反证据
七角色报告
多空辩论与分歧图
三视角风险审查
催化、失效条件和待验证清单
数据缺口和外部证据
运行诊断 / Snapshot Lineage
```

默认先展示事实和分歧，再展示长篇Agent文本。Research Stance显示为“AI研究倾向”，不能与平台StrategySignal使用相同颜色、图标和术语。

## 22. 数据模型和存储

### 22.1 PostgreSQL控制面

| 表族 | 职责 |
| --- | --- |
| `research_request` | 用户/系统触发、层级、问题、权限和优先级 |
| `deep_research_candidate` | 触发原因、预算估算、确认和过期 |
| `stock_research_fact_pack` | Pack Envelope、状态、Snapshot和Hash |
| `stock_research_fact_block` | Block目录、覆盖、存储和Hash |
| `external_evidence_supplement` | 外部证据Bundle、来源和许可状态 |
| `research_run` | 逻辑任务、Profile、FactPack和状态 |
| `research_attempt` | 租约、超时、取消、错误和资源使用 |
| `agent_research_memo` | 七角色结构化Memo和Hash |
| `research_debate` | Bull/Bear论证和分歧图 |
| `research_risk_review` | 三视角风险输出 |
| `research_result` | L1/L2最终结构化结果 |
| `research_claim` | Claim、Evidence和支持状态 |
| `research_self_review` | Critical/Warning和修复记录 |
| `research_report` | Web/Markdown/历史和导出索引 |
| `strategy_promotion_proposal` | 人工审查的指标/策略草稿，不自动启用 |

### 22.2 文件目录

```text
/data/daily_stock_analysis/
├── storage/app/factpacks/type=stock_research/trade_date=YYYY-MM-DD/fact_pack_id=<pack_id>/
├── storage/app/artifacts/type=external_evidence/year=YYYY/month=MM/artifact_id=<supplement_id>/
├── storage/app/results/type=research/entity_key=<escaped_entity_key>/research_id=<research_run_id>/
├── storage/app/artifacts/type=stock_research/year=YYYY/month=MM/artifact_id=<research_result_id>/
├── storage/app/quarantine/research/<attempt_id>/
├── storage/app/state/research-checkpoints/<research_run_id>/
├── storage/postgres/
└── logs/research-worker/
```

本文只定义目标目录，不在设计阶段创建目录或配置。

## 23. API和权限

```text
POST /api/v1/stock-research/requests
GET  /api/v1/stock-research/requests/{request_id}
GET  /api/v1/stock-research/fact-packs/{pack_id}
GET  /api/v1/stock-research/fact-packs/{pack_id}/lineage
GET  /api/v1/stock-research/candidates
POST /api/v1/stock-research/candidates/{candidate_id}/confirm
POST /api/v1/stock-research/runs/{run_id}/cancel
GET  /api/v1/stock-research/runs/{run_id}
GET  /api/v1/stock-research/results/{result_id}
GET  /api/v1/stock-research/results/{result_id}/claims
GET  /api/v1/stock-research/results/{result_id}/disagreements
POST /api/v1/stock-research/results/{result_id}/promotion-proposals
```

权限：

- L0和已发布公共研究可按平台可见性读取；
- 用户问题、自选、持仓和Trigger Ref按用户隔离；
- OPEN_RESEARCH必须由用户显式授权；
- 自动任务不能代表用户开启外部网络研究；
- 普通用户不能发布ResearchProfile、绕过Self-Review或直接启用Promotion Proposal；
- API不暴露完整Prompt、密钥、Cookie、内部文件路径和受版权保护全文；
- Research Agent的工具只读指定FactPack和批准的Evidence Gateway。

## 24. 与当前DSA迁移

### SR1：Schema与适配

- 新建StockResearchFactPack、ResearchRequest和Result Schema；
- 保留现有`/research`和Bot入口；
- 现有ResearchAgent输出通过Legacy Adapter进入新历史页面；
- 旧报告标记`LEGACY_UNTRACED`。

### SR2：L1快速研究

- 实现FactPack Builder和Quick Profile；
- 将现有单股AnalysisContextPack的可用事实迁入统一Pack；
- 引入Claim/Evidence和Research Stance；
- 不改现有Strategy和Backtest。

### SR3：L2角色迁移

- 把现有Technical/Intel/Risk Agent改为FactPack只读；
- 新增Fundamental/Valuation、Policy/Industry、Capital和Supply Risk角色；
- 实现AgentResearchMemo和Checkpoint；
- 不引入TradingAgents完整LangGraph运行时。

### SR4：辩论和Self-Review

- 加入Bull/Bear、风险三视角和Research Manager；
- 复用DSA已有分歧和无效观点隔离思想；
- 实现Critical/Warning Gate和一次修复；
- 建立DeepResearchCandidate确认。

### SR5：页面、权限和Promotion

- 上线事实、证据、分歧和Lineage页面；
- 建立OPEN_RESEARCH授权和外部证据Gateway；
- 只生成StrategyPromotionProposal草稿；
- 完成资源、取消、恢复和备份演练。

## 25. 验收标准

1. L0/L1/L2对同一研究日期使用同一StockResearchFactPack；
2. Stock FactPack同时保存规范`canonical_id`和`entity_key`并拒绝非stock资产串桶；
3. 自动和默认研究模式下Agent不直接访问外部Provider或任意网络；
4. 同一事实不会被七个Agent重复抓取和形成不同口径；
5. 重要研究Claim均有有效Fact ID或External Evidence ID；
6. 财务、公告、解禁、板块成员和事件满足PIT时间门禁；
7. 缺失维度不会被模型知识或默认值填充；
8. UZI命名投资人评分不作为平台事实、总分或决策；
9. ResearchResult只使用Research Stance，不冒充StrategySignal；
10. Research Confidence不直接映射资金权重或仓位；
11. TradingAgents式辩论保留多空分歧和少数派证据；
12. Risk Review不输出仓位、止损价、目标价或账户动作；
13. Critical Self-Review问题未清零时报告为QUALITY_BLOCKED；
14. L2默认必须用户确认，自动任务不能绕过每日预算；
15. L1每天自动候选不超过5只，L2每天不超过1只且单并发；
16. 盘后19:00前不抢占Certified Data和Formal Strategy资源；
17. 取消后没有后台Agent继续发布结果，Checkpoint只在同一RunBundle下恢复；
18. Strategy Promotion只生成草稿，必须经Indicator/StrategySpec/Hikyuu流程；
19. 旧DSA Research报告保持可读并标记缺少Snapshot血缘；
20. 任意正式ResearchResult可追溯至Stock FactPack、FeatureSnapshot、DataSnapshot、ProviderRun和Raw Hash。

## 26. MVP研究实现基线

1. L1九方向直接投影第8节十类FactBlock：身份状态、技术流动性、市场/板块/题材、资金、基本面、估值、事件政策、股本供给风险、同行和数据缺口；
2. Prompt由角色Profile版本化；L1总预算和L2七角色预算写ResourcePolicy，超限按事实优先级裁剪，不能丢Critical Risk和Data Gap；
3. `OPEN_RESEARCH`首批只允许交易所/监管机构/公司公告与定期报告、已批准新闻Provider和owner白名单来源；只保存定位、Hash和必要短摘录，不复制全文；
4. L2候选“重大变化”首批规则为：单日绝对涨跌≥7%、成交≥ADV20的2倍、板块排名变化≥20位、高影响公告/业绩预告或核心质量状态改变；规则版本化且只产生候选；
5. 用户持仓自动触发在MVP禁用，L1/L2由owner或确定性候选确认触发；
6. Legacy `buy/hold/sell`只作历史展示映射为`BULLISH/NEUTRAL/BEARISH`并标记Legacy，不能自动生成策略信号；
7. MVP L1包含财报、催化和陷阱检查；DCF仅在现金流、预测假设和估值数据完整时生成场景研究，否则标记Unavailable；
8. L2在MVP二期交付，默认仅允许owner人工单只触发；自动候选、批量运行和多Worker弹性属于MVP后。

实施顺序见`WP-0701`至`WP-0704`。

## 27. 参考资料

- [UZI-Skill](https://github.com/wbh604/UZI-Skill)
- [TradingAgents-astock](https://github.com/simonlin1212/TradingAgents-astock)
- [TradingAgents论文](https://arxiv.org/abs/2412.20138)
- [daily_stock_analysis当前ResearchAgent](https://github.com/ZhuLinsen/daily_stock_analysis/blob/main/src/agent/research.py)
- [daily_stock_analysis AnalysisContextPack设计](https://github.com/ZhuLinsen/daily_stock_analysis/blob/96bc532dfcb21e3a7d0fdbdfa87d764b9b61d2ee/docs/analysis-context-pack.md)
- [A 股 Feature Store 与指标注册中心架构 v1](feature-store-architecture.md)
- [DSA A 股收盘复盘 FactPack 架构 v1](dsa-close-review-fact-pack.md)
- [StrategySpec v1 策略契约](strategy-spec-v1.md)
- [评分、仓位与自动权重优化架构](weight-optimization-architecture.md)
- [A 股市场情绪与资金行为架构 v1](market-sentiment-and-capital-flow-architecture.md)
- [A 股板块异动、热门观察与策略评分边界 v1](sector-observation-and-strategy-scoring-architecture.md)
- [全球市场观察与 A 股策略隔离架构 v1](global-market-observation-boundary.md)
- [A 股主平台模块化单体、API、任务与权限架构 v1](platform-shell-api-task-permission-architecture.md)
- [A 股平台 Docker、Cloudflare、NPM 与访问安全架构 v1](docker-cloudflare-npm-deployment-architecture.md)
