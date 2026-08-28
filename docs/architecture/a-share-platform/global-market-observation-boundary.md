# Visory 全球市场观察与 A 股策略隔离架构 v1

状态：已确认（Design Approved）

最后更新：2026-08-28

## 1. 决策摘要

本模块落实架构决策 D-027。全球指数、汇率、利率、商品和海外事件仅用于页面观察与DSA收盘复盘背景，不进入A股策略、权重、Prediction、Paper Portfolio或Hikyuu正式回测。

第一版固定以下原则：

- 正式回测只使用A股市场、板块、个股、财务、资金和A股事件事实；
- StrategySpec不得声明`domain=global`的Feature依赖；
- 不建立盘前全球市场Overlay，不因隔夜美股、汇率或商品变化自动加减A股仓位；
- 全球市场不建立平台综合风险分，也不建立策略专属全球评分；
- 全球数据只形成独立的GlobalObservationSnapshot，不能进入FeatureSnapshot的Formal策略依赖集合；
- 全球数据失败、延迟或缺失不阻断A股DataSnapshot、市场情绪、板块观察、正式策略和回测；
- DSA可以把全球事实写入复盘背景，但必须区分事实、数据时间和AI观点，不能把观点回写为A股策略信号；
- 全球事实仍需保存市场时区、交易时段、`available_at`、Provider和快照，避免复盘错配交易日；
- Financial-API当前不承担海外市场数据源职责，全球数据使用独立ProviderPolicy。

本文描述目标架构，不表示当前代码已经具备相应实现。

## 2. 模块边界

### 2.1 本模块负责

- 展示最近已完成交易时段的全球主要指数；
- 展示汇率、利率和商品的最近可用事实；
- 保存海外市场休市、延迟、盘中和完整收盘状态；
- 为DSA提供有来源、有时间戳的全球市场背景；
- 保存全球事件和A股复盘文本之间的引用关系；
- 为页面历史查询和报告复现保存不可变观察快照。

### 2.2 本模块不负责

- 生成A股候选股、买卖信号或目标仓位；
- 调整A股策略权重、总仓或板块敞口；
- 为Hikyuu提供全球Feature；
- 计算全球风险偏好、Risk-on/Risk-off或海外压力综合分；
- 将海外新闻自动映射成A股交易条件；
- 在A股开盘前重新计算或覆盖T日策略计划；
- 为海外市场建立交易回测、模拟组合或交易执行。

### 2.3 与其他模块的关系

```text
Global Provider Adapters
          │
          ▼
Global Normalized Facts
          │
          ▼
GlobalObservationSnapshot
          │
    ┌─────┴─────┐
    ▼           ▼
Market UI    DSA FactPack
display       narrative context

A-share Data/FeatureSnapshot
          │
          ▼
StrategySpec → Hikyuu

禁止连接：GlobalObservationSnapshot ─X→ Strategy/Hikyuu
```

## 3. 全球观察范围

### 3.1 v1核心观察组

| 组 | 建议观察项 | 用途 |
| --- | --- | --- |
| 美国股票市场 | 标普500、纳斯达克、道琼斯 | 展示上一完整美股交易时段 |
| 港股市场 | 恒生指数、恒生科技、恒生国企 | 展示与A股同日的港股表现 |
| 亚洲市场 | 日经225、TOPIX、KOSPI | 展示主要亚洲市场表现 |
| 欧洲市场 | 欧洲斯托克50、德国DAX | 展示最近完整欧洲交易时段 |
| 外汇 | USD/CNH、美元指数DXY | 展示人民币离岸汇率和美元变化 |
| 利率 | 美国2年期、10年期国债收益率及期限利差 | 展示最近可用利率事实 |
| 商品 | 黄金、WTI或Brent原油、铜 | 展示主要商品价格变化 |

资产是否上线取决于已批准Provider、历史可用性和使用条款。没有可靠来源时对应能力为`unavailable`，不能用静态样例填充。

### 3.2 可选观察组

- 费城半导体指数；
- VIX；
- 中概股指数或代表性ETF；
- 富时中国A50期货；
- 铁矿石、大豆等产业相关商品；
- CFTC持仓、美国重要经济数据和央行日历。

这些观察项不属于v1必需能力。即使接入，也只能进入页面和复盘，不改变策略隔离边界。

### 3.3 不承诺的能力

- 海外全市场宽度和涨跌家数；
- 海外行业、板块和资金流全覆盖；
- 交易所级实时行情；
- 海外指数、期货和商品的商业再分发权；
- 海外市场策略和组合回测；
- 全球事实对A股涨跌的因果解释。

## 4. 时间与交易日对齐

### 4.1 不用自然日期强行对齐

全球市场必须按交易时段而不是同名日期关联：

```text
china_trade_date
global_market_timezone
global_session_date
session_open_at
session_close_at
observed_at
available_at
session_status
```

例如，T日17:44生成A股复盘时，T日晚间的美股交易尚未发生。复盘只能引用截至当时已经结束的最近一场美股交易，不能以后来结束的美股行情回填T日报告。

### 4.2 v1只生成收盘观察快照

取消策略盘前双快照和08:45 Overlay。第一版只在A股盘后生成：

```text
GLOBAL_REVIEW_CONTEXT(T)
```

建议目标时间为17:50，内容包括：

- T日已经完成的港股、日股和韩股交易时段；
- 截至T日17:50最近已经完成的美股和欧洲交易时段；
- 外汇、利率和商品截至抓取时点的最近可用值；
- 每个观察项的时区、时段状态和数据时间。

连续交易或尚未收盘的资产必须标记`INTRADAY`，不能伪装成完整日线。DSA默认优先引用`COMPLETE`记录；引用盘中记录时必须在文本中明确“截至何时”。

### 4.3 时段状态

```text
COMPLETE
INTRADAY
DELAYED
HOLIDAY
MISSING
ESTIMATED
```

- `COMPLETE`：Provider明确给出已经完成的交易时段；
- `INTRADAY`：对应市场仍在交易；
- `DELAYED`：数据存在明确延迟；
- `HOLIDAY`：该市场休市，不等同缺数；
- `MISSING`：预期有数据但获取失败；
- `ESTIMATED`：Provider或平台估算，只允许页面展示并明确标记。

所有时区使用IANA名称，例如`America/New_York`，禁止写死与北京时间的固定偏移，避免夏令时错误。

## 5. 全球资产身份

### 5.1 Global Asset Registry

```text
global_asset_id
asset_type
canonical_name
exchange / venue
market_timezone
currency
session_calendar_id
valid_from / valid_to
identity_status
```

`asset_type`至少区分：

```text
equity_index
fx_pair
interest_rate
commodity_spot
commodity_future
volatility_index
economic_series
```

Provider代码映射独立保存：

```text
global_asset_id
provider
provider_symbol
provider_exchange
valid_from / valid_to
mapping_version
verified_at / verification_status
```

同一简称可能对应指数、ETF或期货，不能只按名称或Ticker合并。例如指数、跟踪ETF和期货合约必须使用不同`global_asset_id`。

### 5.2 商品期货连续合约

若页面使用连续期货序列，必须保存：

```text
contract_series_type
roll_rule_version
active_contract
roll_date
adjustment_method
```

现货、主力连续和具体期货合约不得并存为同一指标名。由于全球数据不进入策略，v1可以只展示Provider明确提供的序列，但页面必须披露其口径。

## 6. 数据源与ProviderPolicy

### 6.1 独立于A股主备矩阵

`a-stock-data核心源 + Financial-API补充源`只适用于A股数据平台。全球观察建立独立的数据集策略：

| 数据集 | 优先考虑 | 补充/降级 |
| --- | --- | --- |
| 全球指数快照 | 中国网络可达的东财/腾讯/新浪适配能力 | DSA现有YFinance/Finnhub/AlphaVantage适配器 |
| 全球指数历史 | 已批准的历史行情Provider | YFinance等个人研究来源，标注使用限制 |
| 美国国债收益率 | US Treasury官方数据 | 其他已批准宏观Provider |
| 外汇和商品 | 独立、已批准的FX/Commodity Provider | 无可靠源时不可用 |
| 全球事件 | DSA资讯源和investment-news适配 | 其他已批准公开源 |

每个数据集单独声明ProviderPolicy，不建立一个覆盖所有全球资产的全局优先级。

### 6.2 复用方式

- 复用Vibe-Research全球市场页面组织方式；
- 复用global-stock-data的数据源分层、限流和合规等级思想；
- 复用当前DSA的多市场身份、交易日历、YFinance/Finnhub/AlphaVantage路由和fail-open能力；
- 不在生产运行时执行远端可变Skill文本；
- 需要的能力迁移为固定版本Global Provider Adapter；
- 保存实际Provider、上游、请求时间、内容Hash和使用限制等级。

### 6.3 使用条款

全球行情源的个人使用、商业使用和再分发条款可能不同。每个Provider能力至少登记：

```text
license_tier
personal_use_allowed
commercial_use_allowed
redistribution_allowed
terms_checked_at
terms_uri
```

本平台当前定位为个人研究可以使用符合个人使用条件的数据源；若未来对外提供商业服务，必须重新审查并替换不允许商业使用或再分发的来源。

## 7. Canonical Global Fact

### 7.1 行情事实

```text
global_asset_id
session_date
session_open_at / session_close_at
open / high / low / close
previous_close
change / change_pct
volume / amount
currency
session_status
observed_at / available_at / ingested_at
provider / actual_upstream
provider_run_id / raw_content_hash
```

Provider没有成交量或成交额时保持空值，不能根据价格推算。

### 7.2 利率和经济序列

```text
global_asset_id
observation_date
value / unit
period
release_at / available_at
revision_kind / revision
provider / raw_content_hash
```

经济数据修订生成新版本，不覆盖复盘当时看到的原始值。

### 7.3 页面派生指标

允许计算只用于展示的客观派生值：

```text
return_1d / return_5d / return_20d
change_bp
high_low_range
realized_volatility_20d
drawdown_20d
```

这些结果存入Global Observation Mart，不注册为Formal Strategy Feature，也不计算跨资产综合分。

## 8. GlobalObservationSnapshot

```text
global_observation_snapshot_id
china_trade_date
created_at / available_at
asset_manifest[]
event_manifest[]
provider_policy_version
calendar_versions[]
quality_report_id
missing_capabilities[]
row_counts{}
manifest_hash / content_hash
publication_status / quality_status
revision / revision_kind / supersedes_id
```

发布和质量组合遵循C-001：

```text
DRAFT + COMPLETE|PARTIAL
PROVISIONAL + COMPLETE|PARTIAL
CERTIFIED + COMPLETE|PARTIAL
RETIRED + COMPLETE|PARTIAL
```

构建中和失败属于Task State/Attempt Phase，不写入Snapshot发布状态；Correction使用`revision_kind=CORRECTION`并指向`supersedes_id`。

GlobalObservationSnapshot不是A股DataSnapshot或FeatureSnapshot的组成部分。A股正式RunBundle不得把它列为策略输入。

## 9. 存储

```text
/data/daily_stock_analysis/
├── config/platform/global-market/
│   ├── asset-registry/
│   ├── provider-policies/
│   └── review-views/
├── storage/app/raw/provider=<provider>/dataset=global_*/
├── storage/app/normalized/dataset=global_market/trade_date=YYYY-MM-DD/
├── storage/app/observations/domain=global_market/trade_date=YYYY-MM-DD/snapshot_id=<global_observation_snapshot_id>/
├── storage/app/artifacts/type=market_review/year=YYYY/month=MM/
└── logs/global-observation-worker/
```

全球Raw、Normalized和Mart与A股事实分区隔离。PostgreSQL保存Asset Registry、ProviderPolicy、Run和Snapshot索引，Parquet保存行情与历史观察明细。

## 10. 调度和资源

全球观察低于A股核心流水线优先级：

```text
17:10-17:30  A股市场与板块FeatureSnapshot
17:30-17:44  板块ObservationSnapshot
17:44-17:50  全球观察增量采集
17:50        GlobalObservationSnapshot目标发布
17:44-18:05  A股核心正式策略并行运行，优先级高于全球观察
17:50-18:20  DSA组装FactPack和复盘；全球缺失时生成删减版
18:30-18:50  显式依赖晚到A股能力的策略信号
19:00        A股正式策略硬截止；与全球观察无依赖
20:30        全球和A股Correction审计分别执行
```

资源策略：

```yaml
global_observation_runtime:
  worker_count: 1
  max_threads: 2
  max_provider_concurrency: 2
  required_for_a_share_strategy: false
  required_for_market_review: false
  failure_mode: partial_review
```

若A股正式信号接近19:00硬截止，全球采集和AI复盘必须让出CPU、内存、磁盘和网络资源。

## 11. 页面与DSA

### 11.1 页面

全球市场页面按事实类型分组：

1. 美国、港股、亚洲和欧洲主要指数；
2. 汇率；
3. 利率；
4. 商品；
5. 全球事件时间线；
6. 每项数据的市场时段、状态、Provider和更新时间。

页面不展示：

```text
global_risk_score
risk_on_off_score
overseas_pressure_score
global_strategy_signal
```

颜色只表示单个资产涨跌或数据状态，不表示对A股的正负影响。

### 11.2 DSA FactPack

```yaml
global_observation:
  snapshot_id: obs_<uuidv7>
  china_trade_date: 2026-08-27
  groups:
    us_indices: []
    hk_indices: []
    asia_indices: []
    europe_indices: []
    fx: []
    rates: []
    commodities: []
  events: []
  missing_capabilities: []
```

DSA可以说明“最近完整美股交易时段纳斯达克下跌”等事实，也可以讨论可能的A股情绪背景，但必须：

- 明确市场时段和数据日期；
- 把影响判断标记为AI观点；
- 不修改A股市场情绪分；
- 不生成或修改StrategySignal；
- 不调整Paper Portfolio；
- 全球数据缺失时如实披露并继续生成A股复盘。

GlobalObservation在DSA中的可选Block、证据引用和失败语义以[DSA A 股收盘复盘 FactPack 架构 v1](dsa-close-review-fact-pack.md)为准；它不计入A股核心FactPack完整性。

## 12. 策略和回测硬隔离

### 12.1 StrategySpec门禁

第一版Formal和Paper策略允许的Feature Domain：

```text
stock
sector
market_cn
fundamental_cn
event_cn
```

以下依赖直接拒绝编译：

```text
global.*
fx.*
commodity.*
overseas_index.*
overseas_event.*
```

错误码建议：

```text
GLOBAL_FEATURE_NOT_ALLOWED_IN_A_SHARE_STRATEGY_V1
```

### 12.2 Hikyuu边界

- Hikyuu Adapter不读取GlobalObservationSnapshot；
- Hikyuu缓存不写入全球指数、汇率、利率和商品特征；
- BacktestRun Manifest不包含全球快照ID；
- Prediction、OrderIntent、WeightSnapshot和Execution不引用全球数据；
- 全球采集失败不改变回测状态和结果Hash；
- 不实现盘前Overlay、隔夜减仓或全球风险仓位因子。

### 12.3 研究分析

页面可以在回测结果旁并排展示同期全球市场走势，帮助人工观察，但必须标记为`post_hoc_context`：

- 不进入回测输入；
- 不参与绩效、归因或风险计算；
- 不声称证明因果关系；
- 不因页面选择区间改变正式回测结果。

## 13. API

```text
GET /api/v1/global-market/assets
GET /api/v1/global-market/latest?group=&snapshot_id=
GET /api/v1/global-market/history/{global_asset_id}?from=&to=
GET /api/v1/global-market/events?from=&to=
GET /api/v1/global-market/snapshots?china_trade_date=
GET /api/v1/global-market/snapshots/{snapshot_id}/lineage
GET /api/v1/admin/global-market/runs/{run_id}
```

全球API位于独立命名空间。Strategy API、Hikyuu Adapter和权重服务不调用这些接口。

## 14. 失败与修订

- 单个海外指数失败：跳过该项并展示缺失，不影响其他资产；
- 一个资产组全部失败：标记对应能力不可用，全球快照可以`PARTIAL`发布；
- 全球全部失败：DSA生成不含全球背景的A股复盘；
- Provider返回盘中值：标记`INTRADAY`，不伪装完整收盘；
- 休市：标记`HOLIDAY`，不复制前一日数据冒充当日；
- Provider切换：生成独立ProviderRun和新分区；
- 晚到或修订：生成`revision_kind=CORRECTION`的新快照并引用`supersedes_id`，不覆盖已经发布的复盘；
- 全球失败永不触发A股19:00策略硬截止失败。

## 15. 实施阶段

### Phase 1：指数观察

- 建立Global Asset Registry和Provider Map；
- 复用DSA现有美、港、日、韩市场身份和行情适配；
- 发布全球主要指数GlobalObservationSnapshot。

### Phase 2：汇率、利率和商品

- 接入已批准的USD/CNH、DXY、美国国债和商品Provider；
- 保存单位、时区、连续合约和数据状态；
- 缺少合规稳定来源的资产保持不可用。

### Phase 3：页面和DSA

- 发布全球市场API和观察页面；
- DSA消费结构化Global FactPack；
- 增加时段、数据状态、来源和缺口披露。

### Phase 4：稳定性

- 建立Provider质量、限流和Correction机制；
- 检查个人使用与商业使用条款；
- 优化中国服务器网络失败时的受控降级。

不安排全球策略、盘前Overlay和Hikyuu全球回测阶段。

## 16. 验收标准

1. 全球数据只进入页面、GlobalObservationSnapshot和DSA复盘背景；
2. StrategySpec引用全球、外汇或商品Feature时Formal编译失败；
3. Hikyuu输入、缓存、Run Manifest和结果Hash不包含全球数据；
4. 全球数据失败不阻断A股DataSnapshot、FeatureSnapshot、Prediction和回测；
5. 不存在全球综合风险分、A股盘前Overlay或全球策略评分；
6. 每条全球事实保存市场时区、时段日期、状态、Provider和`available_at`；
7. 17:50复盘不会引用当时尚未发生的美股交易时段；
8. 休市、盘中、延迟和缺失状态不会混淆；
9. DSA影响判断明确标记为AI观点，不写回A股事实和信号；
10. 页面并排展示的全球历史标记为后验背景，不参与回测归因；
11. Provider使用条款和个人/商业边界可查询；
12. Correction生成新快照，不覆盖旧复盘。

## 17. 实施入口

全球观察在M4的`WP-0405`以低优先级只读页面能力实现；策略类型和RunBundle Schema必须从结构上拒绝全球输入。阶段验收见[实施路线与验收方案 v1](implementation-roadmap-and-acceptance-v1.md)。

## 18. 参考资料

- [Vibe-Research：全球指数和每日复盘页面参考](https://github.com/simonlin1212/Vibe-Research)
- [global-stock-data：美港行情、宏观数据和数据源使用等级](https://github.com/simonlin1212/global-stock-data)
- [Financial-API：当前不提供海外市场行情和宏观数据](https://github.com/HiThink-Tech/Financial-API/blob/main/README.md)
- [daily_stock_analysis市场支持边界](https://github.com/ZhuLinsen/daily_stock_analysis/blob/96bc532dfcb21e3a7d0fdbdfa87d764b9b61d2ee/docs/market-support.md)
- [指标、预测与 Hikyuu 回测架构](backtest-and-indicator-architecture.md)
- [StrategySpec v1 策略契约](strategy-spec-v1.md)
- [A 股板块异动、热门观察与策略评分边界 v1](sector-observation-and-strategy-scoring-architecture.md)
- [A 股 Feature Store 与指标注册中心架构 v1](feature-store-architecture.md)
- [DSA A 股收盘复盘 FactPack 架构 v1](dsa-close-review-fact-pack.md)
- [A 股分层个股研究与 StockResearchFactPack 架构 v1](stock-research-architecture.md)
- [A 股主平台模块化单体、API、任务与权限架构 v1](platform-shell-api-task-permission-architecture.md)
- [A 股平台 Docker、Cloudflare、NPM 与访问安全架构 v1](docker-cloudflare-npm-deployment-architecture.md)
