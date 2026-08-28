# Visory A 股数据平台与 Canonical Data Contract v1

状态：已确认（Design Approved）

最后更新：2026-08-28

## 1. 决策摘要

平台第一版数据策略固定为：

- a-stock-data 是 A 股核心数据源和主要数据能力参考；
- Financial-API 是补充源、交叉校验源和核心源不可用时的受控灾备；
- 平台不直接把外部项目的数据结构当成内部事实，所有数据必须经过 Provider Adapter、身份解析、Canonical Schema、质量门禁和不可变 DataSnapshot；
- A股股票在`asset_type=stock`上下文中以带交易所前缀的`canonical_id`作为唯一规范代码，例如`sh600519`、`sz000001`；跨资产类型和跨域关联使用`entity_key=stock:<canonical_id>`；
- 六位裸代码只用于输入、搜索和显示，不作为跨表唯一键；
- `asset_type`、交易所和 Provider 原始代码必须保留，用于防止股票、指数、ETF或不同市场串桶；
- Raw 与 Canonical Parquet 是权威事实，PostgreSQL 保存注册表和快照 Manifest，DuckDB 负责查询，Hikyuu HDF5 仅是指定快照的可重建缓存。

“保证数据不出错”在工程上解释为：已知歧义、单位错误、跨市场串桶、无来源覆盖、时间穿越和静默降级必须被系统阻断；外部源本身出现错误时，通过双源校验、隔离、修订和快照追溯将影响限制在可发现、可回滚范围内，而不是承诺任何外部数据绝对零错误。

## 2. 数据源职责

### 2.1 a-stock-data 核心源

a-stock-data 聚合多个公开数据源，覆盖行情、财务、估值、ST/停牌、上市退市、行业变迁、资金流、板块、龙虎榜、题材、公告、新闻和宏观数据。平台复用其数据源选择、接口适配和降级经验，但生产实现必须：

1. 把需要的能力迁移到平台 Provider Adapter；
2. 固定代码或契约版本，不在运行时执行远端可变 Skill 文本；
3. 保存实际上游来源，例如 `mootdx`、`tencent`、`eastmoney`、`baostock`，不能只保存聚合项目名；
4. 为每个数据集单独声明主源和备源，禁止一个全局优先级覆盖所有数据；
5. 外部接口结构变化时先进入隔离区，不能直接写入 Canonical 层。

### 2.2 Financial-API 补充源

Financial-API 用于：

- 补充股票目录、交易日历、日K、公司行动、复权、财务、指数和板块数据；
- 对核心行情、公司行动、交易日历和财务字段进行交叉校验；
- a-stock-data 对应能力不可用或质量不合格时，按数据集策略执行受控灾备；
- 利用全市场文件或本地数据库能力完成批量补数，但输出仍须转换为平台 Canonical Schema。

Financial-API 的凭据、权限和调用额度属于 Provider 配置，不进入策略、回测 Manifest 或普通诊断页面；Manifest 只保存非敏感 Provider、能力和版本信息。

### 2.3 主备不是静默逐行拼接

一个数据分区可以由主源或受控备源生成，但不能在没有记录的情况下逐行混合。发生降级时必须：

```text
primary provider run failed/invalid
  → record failure and quality report
  → start supplemental provider run
  → normalize and validate independently
  → publish a new partition version
  → create a new DataSnapshot
```

旧 DataSnapshot 永远保留原输入。回测运行期间不允许因 Provider 恢复而切换数据。

## 3. 规范股票身份

### 3.1 唯一键

第一版 A 股股票的唯一业务键为：

```text
canonical_id = <exchange_prefix><six_digit_code>

sh600519  贵州茅台 / 上交所股票
sz000001  平安银行 / 深交所股票
sz300750  宁德时代 / 深交所股票
sh688981  中芯国际 / 上交所股票
```

平台已有 `parse_analysis_target()` 和 `canonical_id` 前缀格式，数据平台沿用该契约，不另建点分格式或数字ID作为业务真源。

### 3.2 为什么不能只用六位数字

`000001` 等裸码在股票、指数或交易所语境中可能指向不同对象。以下字段必须分开：

| 字段 | 示例 | 用途 |
| --- | --- | --- |
| `canonical_id` | `sz000001` | 股票上下文规范代码与股票专属API键 |
| `entity_key` | `stock:sz000001` | 资产事实跨表、跨域唯一关联键 |
| `code` | `000001` | 用户输入与显示 |
| `exchange` | `XSHE` | 标准交易所身份 |
| `asset_type` | `stock` | 股票、指数、ETF等分类 |
| `provider_symbol` | `000001.SZ` | 某Provider请求参数 |
| `provider` | `financial_api` | Provider身份 |

不得用股票名称、当前简称、拼音或数据库自增ID替代`entity_key/canonical_id`进行事实关联。

### 3.3 裸码解析

- 用户输入裸代码时，可以通过平台权威 Security Master 解析为股票；
- 数据采集时 Provider 若没有返回交易所，必须查询 Security Master；
- 匹配结果为零个或多个时拒绝入库，禁止猜测；
- 显式指数身份只能通过 Index Registry 解析，不能把裸股票代码自动提升为指数；
- `canonical_id` 一旦生成，Provider Adapter、缓存、回测和报告不得重新推断交易所。

### 3.4 Provider映射

`provider_symbol_map` 至少保存：

```text
entity_key / canonical_id
provider
provider_symbol
provider_exchange
valid_from / valid_to
mapping_source
mapping_version
verified_at
verification_status
```

一条 Provider Symbol 在同一有效期只能映射到一个 `canonical_id`；冲突时两条映射都进入隔离状态，不能使用“最后写入覆盖”。

## 4. 数据集主备矩阵

| Canonical 数据集 | 核心源 | 补充/校验源 | 正式回测要求 |
| --- | --- | --- | --- |
| `security_master` | a-stock-data目录能力 | Financial-API标的目录 | 身份冲突阻断 |
| `trading_calendar` | a-stock-data对应上游 | Financial-API交易日历 | 差异阻断 |
| `bar_1d_raw` | a-stock-data行情链 | Financial-API日K/全市场文件 | OHLCV门禁通过 |
| `instrument_status_daily` | a-stock-data ST/停牌能力 | Financial-API可用字段 | 缺失时不得买入 |
| `listing_status_history` | a-stock-data上市退市能力 | Financial-API目录 | 必须point-in-time |
| `corporate_action` | a-stock-data分红送转/复权链 | Financial-API公司行动 | 双源差异隔离 |
| `adjustment_factor` | 从已发布公司行动生成；a-stock-data因子校验 | Financial-API复权结果校验 | 不直接信任最终复权价 |
| `financial_statement` | a-stock-data财务能力 | Financial-API财务报表 | 保存披露/可用时间 |
| `valuation_daily` | a-stock-data估值历史 | Financial-API估值快照 | 标明快照/历史口径 |
| `industry_membership` | a-stock-data申万历史变迁 | Financial-API板块目录 | 当前成分不能覆盖历史 |
| `sector_market_daily` | a-stock-data板块/资金能力 | Financial-API板块行情 | 只作派生市场事实 |
| `limit_pool/event_hotspot` | a-stock-data涨跌停、异动、题材 | Financial-API特色数据 | 保存来源和抓取时间 |
| `news_announcement` | a-stock-data公告/新闻能力 | 其他已批准Provider | 不进入价格真源 |

矩阵是第一版默认。每次修改主备、字段口径或允许的降级路径都必须提升 `ProviderPolicy` 版本，不能只修改配置顺序。

## 5. 物理分层

```text
Provider
  → RawObject
  → Normalization
  → Identity Resolution
  → Canonical Partition
  → Quality Gate
  → DataSnapshot
  → DuckDB / Feature Store / Hikyuu cache
```

### 5.1 Raw

Raw 保存可重放证据：

```text
provider_run_id
provider / actual_upstream
capability / request_fingerprint
requested_at / received_at
http_status / provider_status
adapter_version / schema_observed
content_hash
raw_object_uri
```

Raw 追加写入，不修改、不去掉源字段，也不包含明文凭据。

### 5.2 Normalized / Canonical

Canonical 层只发布通过契约校验的数据，统一：

- 股票身份和交易所；
- 日期、时区和交易日；
- 价格单位、成交量单位和成交额单位；
- 未复权价格与公司行动；
- 空值、枚举和错误码；
- `observed_at`、`published_at`、`available_at`、`ingested_at`；
- Provider、上游来源、Raw Hash和Adapter版本。

### 5.3 Snapshots

DataSnapshot 是回测和正式指标计算的唯一数据入口：

```text
data_snapshot_id
trade_date / cutoff_at / created_at
provider_policy_version
security_master_version
calendar_version
partition_manifest[]
quality_report_id
row_count / min_date / max_date
schema_hash / manifest_hash / content_hash
publication_status / quality_status
certified_capabilities[]
revision / revision_kind / supersedes_id
```

只有`publication_status=CERTIFIED`且`backtest_core=CERTIFIED`的快照可以进入Formal Hikyuu回测。

## 6. Canonical Schema v1

### 6.1 Security Master

```text
canonical_id
code
exchange
asset_type
name / name_effective_from / name_effective_to
list_date / delist_date
board
currency
lot_size
valid_from / valid_to
available_at
source_lineage
```

证券简称允许变化，但不能生成新的 `canonical_id`。

### 6.2 日K真源

```text
canonical_id
trade_date
open / high / low / close
volume_shares
amount_cny
prev_close
trading_status
price_limit_up / price_limit_down
available_at
provider_run_id / raw_content_hash
```

唯一约束为 `(canonical_id, trade_date, snapshot_partition_version)`。价格真源保存未复权数据；前后复权序列是由公司行动快照生成的派生数据。

### 6.3 证券状态

```text
canonical_id
trade_date
is_listed / is_suspended
is_st / is_star_st
board
limit_rule_id
available_at
source_lineage
```

当前状态不能回填覆盖历史状态。

### 6.4 公司行动与复权

```text
corporate_action_id
canonical_id
action_type
announcement_date / record_date / ex_date / pay_date
cash_per_share / stock_ratio / split_ratio
published_at / available_at
source_lineage
```

Adjustment Factor 记录生成算法、输入公司行动Snapshot和公式Hash。回测指标使用时点可用复权序列，成交使用未复权价格，公司行动独立进入组合账本。

### 6.5 财务和事件

所有财务、公告、新闻、题材和资金类事实必须同时保存业务时间与可用时间。只有报告期、没有披露或抓取时间的数据不得进入 Formal point-in-time 因子。

## 7. 质量门禁

### 7.1 身份门禁

- `canonical_id` 必须通过统一Parser和Security Master；
- 代码、交易所和资产类型不可冲突；
- Provider Symbol必须存在有效映射；
- 同一自然键重复且值不同进入隔离；
- 股票行不能写入指数或ETF分区。

### 7.2 行情门禁

- `low <= open/close <= high`；
- 价格、成交量和成交额非负且单位可确认；
- 交易日必须存在于对应交易所日历；
- 停牌、零成交和缺失行情按不同状态表达；
- 涨跌停价与日期版本化规则相符；
- 相邻日、公司行动和复权关系可解释；
- 双源价格超过一个最小报价单位或成交量/额超过版本化容差时隔离，禁止取平均。

### 7.3 时间门禁

- `available_at` 不得早于源实际发布或抓取时间；
- 财报修订生成新版本，不能覆盖首次披露；
- 新闻、公告和题材不能按事件发生日期假定当时已知；
- 回测读取必须满足 `available_at <= decision_at`。

### 7.4 完整性门禁

每个分区检查：证券覆盖率、交易日覆盖率、重复率、缺失率、异常跳变、跨源一致率和历史修订量。核心表未达门槛时状态为 `quarantined`，不得创建 Certified Snapshot。

## 8. 冲突裁决

冲突时不采用平均值或“最近一次写入”：

1. 先校验身份、复权口径、币种、单位和时间范围；
2. 若属于格式/单位差异，由Adapter规范化后重新比较；
3. 若仍不一致，按数据集 ProviderPolicy 选择权威源，同时保留另一来源；
4. 交易日历、股票身份、公司行动和未复权OHLC关键字段无法解释的差异阻断发布；
5. 资金流、热度和题材属于Provider口径，允许并存但必须使用不同 `metric_id/source`，不伪装成同一事实；
6. 人工修正生成 `manual_correction` 和新Snapshot，禁止直接改Parquet文件。

## 9. 存储与分区

所有目录位于 `/data/daily_stock_analysis`：

```text
storage/app/
├── raw/provider=<provider>/dataset=<dataset>/ingest_date=YYYY-MM-DD/
├── normalized/dataset=<dataset>/trade_date=YYYY-MM-DD/revision=<revision>/
├── observations/domain=data_snapshot/trade_date=YYYY-MM-DD/snapshot_id=<data_snapshot_id>/
├── quarantine/<provider_run_id>/
├── hikyuu/data_snapshot_id=<data_snapshot_id>/builder_version=<version>/
└── state/duckdb/

storage/postgres/
```

Parquet 使用稳定Schema、ZSTD压缩和确定性列顺序。小文件先写staging，质量通过后合并为目标分区；合并不改变已有Snapshot引用的对象Hash。

## 10. Hikyuu 输入缓存

```text
Certified DataSnapshot
  → verify manifest and hashes
  → build Hikyuu HDF5 in temporary directory
  → validate row counts/date ranges/samples
  → atomic publish cache
  → cache_manifest(snapshot_id, builder_version, hash)
```

- HDF5不是数据真源；
- 缓存键至少包含DataSnapshot、Builder版本和数据口径；
- 缓存缺失或损坏时从Parquet重建；
- Hikyuu Worker禁止直接调用a-stock-data、Financial-API或其上游接口；
- 同一个Formal Run运行期间只能绑定一个缓存Manifest。

## 11. 采集时序

交易日盘后16:00开始核心采集，19:00为正式策略硬截止；Provisional、按能力认证、补充源启用、Correction和资源优先级的完整时间契约见[盘后数据采集与 Snapshot 发布 SLA v1](data-ingestion-and-snapshot-sla.md)。日线流程为：

```text
交易日收盘
  → 等待至16:00
  → a-stock-data核心采集
  → 身份/Schema/质量校验
  → Financial-API抽样或全量交叉校验
  → 差异隔离与重试
  → 发布Certified DataSnapshot(T)
  → 计算FeatureSnapshot(T)
  → 策略预测与复盘
```

快照发布截止时间必须配置并记录。截止后到达的更正进入下一Snapshot，不回写已用于预测或回测的快照。

## 12. 失败语义

稳定错误码至少包括：

```text
IDENTITY_UNRESOLVED
IDENTITY_CONFLICT
PROVIDER_UNAVAILABLE
PROVIDER_SCHEMA_CHANGED
PROVIDER_SYMBOL_CONFLICT
UNIT_UNKNOWN
CALENDAR_MISMATCH
BAR_INVARIANT_FAILED
CROSS_SOURCE_MISMATCH
AVAILABLE_AT_MISSING
SNAPSHOT_INCOMPLETE
SNAPSHOT_HASH_MISMATCH
HIKYUU_CACHE_BUILD_FAILED
```

正式数据任务失败后保留ProviderRun、RawObject、质量报告和隔离产物。降级成功也不能把原失败隐藏为成功，DataSnapshot Manifest必须记录降级原因。

## 13. 追溯链

```text
BacktestRun
  → DataSnapshot
  → Canonical Partition + SchemaHash
  → ProviderRun + AdapterVersion
  → RawObject + ContentHash
  → actual upstream + request fingerprint
```

任何一根K线、一个财务字段或一个状态值都必须能够回答：属于哪只证券、来自哪个实际上游、何时获取、何时可用、经过哪个Adapter、是否发生降级、为何被选为Canonical事实。

## 14. 验收标准

1. `sh600519`和`sz000001`能稳定映射到唯一股票；
2. 裸`000001`不会被数据采集链误写入`sh000001`指数桶；
3. 股票、指数和ETF不能共享同一Canonical事实分区；
4. Provider Symbol冲突时任务失败而非最后写入覆盖；
5. a-stock-data内部实际使用的上游可以追溯；
6. Financial-API补数创建新分区和新Snapshot；
7. 双源关键字段冲突不取平均且不能发布Certified Snapshot；
8. 未复权价格、公司行动和复权派生结果可以逐日复算；
9. ST、停牌、上市、退市和行业成分均按历史日期查询；
10. 缺少`available_at`的财务或事件数据不能进入Formal因子；
11. 同一Snapshot Manifest重复构建产生相同Canonical Hash；
12. HDF5损坏后可从同一Snapshot重建并产生相同缓存Hash；
13. Provider恢复或历史修订不改变旧回测输入；
14. 所有质量失败具有稳定原因码和隔离证据。

## 15. 实施顺序

当前仓库仍处于 `canonical_id` 扩展迁移阶段：旧 `stock_daily` 允许 `canonical_id` 为空，主要读取路径仍兼容裸 `code`，其普通索引也不是本文目标表的唯一约束。因此本文描述的是新平台目标契约，不能据此宣称现有历史表已经完全消除串桶风险。迁移必须采用 Expand-Contract：先回填和审计，再双读对照，最后将正式量化读路径切换到新的Canonical表；禁止直接修改旧唯一约束破坏现有分析功能。

### Phase D0：身份注册表

- 复用现有AnalysisTarget Parser和Index Registry；
- 建立Security Master与Provider Symbol Map；
- 清点历史裸码、市场前缀和资产类型冲突。
- 输出旧`code`与新`canonical_id`双读差异，在冲突清零前不切换正式量化读路径。

### Phase D1：核心日线事实

- 实现a-stock-data核心Adapter；
- 建立Security、Calendar、Bar、Status和RawObject Schema；
- 接入Financial-API交叉校验；
- 生成首个Certified DataSnapshot。

### Phase D2：复权与公司行动

- 统一未复权行情、公司行动和Adjustment Factor；
- 建立双轨价格对照夹具；
- 实现Hikyuu HDF5缓存构建器。

### Phase D3：财务、行业与市场事实

- 接入财务披露时间、估值历史和行业变迁；
- 接入板块、资金、涨跌停、题材和热点；
- 建立Market/Sector Snapshot。

### Phase D4：修订和运维

- 增量、回填、差异报告和隔离修复；
- Snapshot保留、备份和恢复；
- Provider质量评分和告警。

## 16. 后续设计衔接

Feature Store的F1/F2/F3三级物化、宽长表混合、依赖DAG、不可变Manifest、能力认证、缓存保留和消费者协议已经在[A 股 Feature Store 与指标注册中心架构 v1](feature-store-architecture.md)中确定。数据平台实现时应先发布Certified DataSnapshot，再由Feature Worker计算和发布独立FeatureSnapshot，两个层级不得合并或互相覆盖。

## 17. 参考资料

- [a-stock-data：数据层、上游来源和降级策略](https://github.com/simonlin1212/a-stock-data)
- [Financial-API：日K、公司行动、交易日历、财务、指数板块与本地数据库](https://github.com/HiThink-Tech/Financial-API)
- [指标、预测与 Hikyuu 回测架构](backtest-and-indicator-architecture.md)
- [A 股回测市场规则 v1](backtest-market-rules-v1.md)
- [Fleur-Lite 回测运行与结果一致性架构](fleur-lite-backtest-runtime.md)
- [盘后数据采集与 Snapshot 发布 SLA v1](data-ingestion-and-snapshot-sla.md)
- [A 股 Feature Store 与指标注册中心架构 v1](feature-store-architecture.md)
