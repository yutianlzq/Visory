# WP-0303：a-stock-data Adapter Bundle 与真实 Provider 分层架构

状态：架构已收敛，真实来源接入 `NO_GO`

最后核验：2026-10-15

## 1. 决策

[`simonlin1212/a-stock-data`](https://github.com/simonlin1212/a-stock-data) 在 Visory 中定位为 **Adapter Bundle / 数据源实现参考**，不是一个可以覆盖全部端点的统一生产 Provider 身份。

本次固定参考版本：

| 项目 | 固定值 |
| --- | --- |
| Git commit | `29b07d2e37005b9fd568bca1262f6e572b5f9407` |
| 版本 | `V3.10.2` |
| Commit time | `2026-10-11T12:55:46Z` |
| License | `Apache-2.0`，只约束仓库代码，不自动授予第三方行情数据的保存、再分发或生产使用权 |
| 本地只读参考 | `E:\Personal Manager\参考项目\a-stock-data` |
| `README.md` SHA256 | `33b6f4a829571cf1fd4d3de127468cd0c59dace65ac77c8230b1b21fbaa4a9b9` |
| `SKILL.md` SHA256 | `d30aa90edb881a45168c397a6ca1ccfebc440a8d4c93b3d94d3123d27b260a1d` |

该版本声明 15 层、87 个能力入口和 34 个来源。代码实际直连腾讯、通达信官网、东方财富、巨潮、BaoStock、新浪、深交所等不同来源，并在部分函数内部执行 fallback。仓库 commit、Git blob 或函数测试只能固定实现字节，不能证明某次数据响应的历史 `available_at`、全量覆盖或修订链。

因此正式链路使用以下身份分层：

```text
a-stock-data@fixed commit
    = adapter_bundle_id + implementation fingerprint

Tencent / TDX / Eastmoney / CNINFO / BaoStock / Sina / Exchange...
    = independent provider_id

provider_id + provider_endpoint_id + endpoint_contract_version
    -> ProviderRun
    -> immutable RawObject
    -> CanonicalPartition + QualityReport + CoverageReceipt
    -> DataSnapshot
    -> DERIVED / FeatureStore / Resolver / F1 / F2
```

现有 `a_stock_data@1.0.0` Provider、Schema、Mapping、Golden 和调度引用继续保留为兼容基线及 `UNVERIFIED` 本地契约。不得原地改写其身份或 Hash。后续真实接入只能追加版本化 Provider/Endpoint 契约；在迁移完成前，新 WP-0303 正式输入不得仅以 `provider_id=a_stock_data` 或自由文本 `actual_upstream` 获得认证。

## 2. Provider、Endpoint 与实现指纹

### 2.1 Provider 身份

`provider_id` 表示对响应语义、服务端行为和数据修订负责的实际来源，例如：

- `tencent_finance`
- `tdx_official_package`
- `eastmoney_push2`
- `eastmoney_push2ex`
- `eastmoney_datacenter`
- `cninfo`
- `baostock`
- `sina_finance`
- `szse_official`

域名相同但契约、分页或修订语义不同的端点不能只靠一个模糊 Provider 能力声明。一个 Provider 可以有多个版本化 Endpoint；同一 Adapter Bundle 可以实现多个 Provider Endpoint。

### 2.2 Endpoint 契约

正式 Endpoint 至少固定：

```text
provider_endpoint_id
provider_id
endpoint_contract_version
request method / redacted origin / path family
request parameter schema and market scope
response schema and source field units
pagination / total / terminal semantics
empty / no-data / non-trading-day / error semantics
revision / cancellation / source publication semantics
rate-limit and retry policy
license / permitted retention evidence
```

`ProviderRun.actual_upstream` 继续保存脱敏 origin，但它只是运行证据，不足以代替 Provider/Endpoint 注册。运行时实际 origin 必须命中 Endpoint 的允许集合；重定向或 host 漂移要进入隔离。

### 2.3 Adapter Bundle 指纹

C-004 增量实现已将每次运行所需的实现证据版本化为 `AdapterImplementationFingerprint@1.0.0`：

```text
adapter_bundle_id = a_stock_data
adapter_bundle_version = 3.10.2
source_repository = simonlin1212/a-stock-data
source_commit = 29b07d2e...
source_file_blob / source_file_sha256
function_symbol
implementation_fingerprint
```

只写 `adapter_version=1.0.0` 或 Git commit 仍不够：必须能定位本次调用采用的函数和源文件字节，同时保留 Visory 自有 wrapper/Mapping/质量规则版本。

### 2.4 C-004 纯追加准入对象

为保护现有 `ProviderRun@1.0.0`、`RawObject@1.0.0`、Registry、Golden 和 Hash，Endpoint 身份与准入证据不原地塞入旧对象。本地实现已纯追加以下四个新 `contract_id`：

| 对象 | 最小身份和引用 | 用途 |
| --- | --- | --- |
| `ProviderEndpointDefinition@1.0.0` | `provider_endpoint_id + provider_id + endpoint_contract_version` | 固定 method、脱敏 origin/path family、请求/响应 Schema、市场范围、分页/total/终止、零行/错误、revision/cancel、发布时间和许可语义 |
| `AdapterImplementationFingerprint@1.0.0` | `adapter_implementation_fingerprint_id` | 固定 Bundle/version/repository/commit、源文件 blob/Hash、函数符号、Visory wrapper、Mapping 和质量规则版本及总 Hash |
| `SourceAdmissionReceipt@1.0.0` | `source_admission_receipt_id + endpoint + dataset/schema + requested scope` | 固定 `source-contract`、样本 Manifest、observation log、coverage、revision chain、quality 和 license 的实际证据 Hash，并声明 `CURRENT_SNAPSHOT/HISTORICAL_SERIES/VERSIONED_ARCHIVE/PIT_CERTIFIED` |
| `ProviderEndpointRunBinding@1.0.0` | `binding_id + provider_run_id + raw_object_refs` | 将旧 Run/Raw 与唯一 Endpoint/version、实现指纹和 Admission Receipt 绑定，供 Canonical/Snapshot/Formal 门禁读取 |

关系如下：

```text
ProviderEndpointDefinition
  + AdapterImplementationFingerprint
  + SourceAdmissionReceipt
  + existing ProviderRun / RawObject
  -> ProviderEndpointRunBinding
  -> Canonical / Snapshot / DERIVED / Feature
```

当前 `ContractRegistry` 以 `contract_id` 唯一；不得再注册同名 `C-004/ProviderRun@2.0.0` 来替换旧模型。无 Binding 的既有 Run 继续按旧兼容语义可读，但不能因此获得新的 Formal 来源认证。

四对象持久化于后继 Migration `0016_wp0303_provider_endpoint_admission`：Endpoint、Fingerprint、Receipt、Run Binding 和 Binding→RawObject 关联均为追加记录；一个 Run 只能绑定一个实际 Endpoint。Repository 只做精确 ID/version 读取，不提供 latest。Snapshot `backtest_core` build、Formal consumer 和 backtest current pointer 会重新核对 Run/Raw、Receipt 范围与状态、证据 Hash 和实现观察；缺 resolver、旧 Run 缺 Binding、非 `PIT_CERTIFIED` 或内部换源都拒绝。

## 3. Fallback 与运行边界

a-stock-data 中的 fallback 是实现经验，不直接成为 Visory 的生产降级语义。

1. 每个实际来源分别注册 Provider/Endpoint、Raw Schema、Mapping 和 Capability。
2. 主端点失败后切换来源，必须结束原 ProviderRun，再创建新的 ProviderRun、RawObject、分区和质量报告。
3. 禁止一个成功 ProviderRun 内部从东财切到 BaoStock 后仍只标记 `a_stock_data`。
4. 禁止把不同来源逐行拼成一个分区，除非版本化 Policy 明确允许、逐行保留来源且冲突规则已审核；WP-0303 当前不批准该模式。
5. `except Exception: return []`、HTTP 错误转空数组或 `data=null` 不得进入生产 wrapper。失败、非交易日、合法零行和分页不完整必须可区分。
6. Source fallback 与请求重试分开：同一 Endpoint 的幂等重试可属于同一次 attempt；来源、Endpoint 或响应语义变化必须产生新 attempt/run。

例如固定版本中的 `_em_zt_api()` 会在任意异常时返回空列表，`limit_up_sentiment()` 又会把空列表计算成零家数。这种行为可作为参考代码反例，不能作为 Formal 市场情绪输入。

## 4. 能力等级

每个 `provider_id + provider_endpoint_id + dataset_id` 独立评估，不按 Adapter Bundle 整体认证：

| 等级 | 含义 | 可否进入 WP-0303 Formal |
| --- | --- | --- |
| `CURRENT_SNAPSHOT` | 只能证明当前查询结果 | 否 |
| `HISTORICAL_SERIES` | 当前可下载历史数值，但没有历史版本/观察档案 | 否 |
| `VERSIONED_ARCHIVE` | 有不可变原始版本、来源时间和修订关系 | 仍需覆盖/质量门禁 |
| `PIT_CERTIFIED` | 同时满足身份、Schema、单位、覆盖、`available_at`、revision/cancel、合法零行和许可 | 是 |

本次核验没有将任何 a-stock-data 端点提升为 `PIT_CERTIFIED`。仓库测试中的实跑日期、行数和防截断校验是实现质量证据，不是 Visory 所需区间的历史 PIT 收据。

## 5. B1—B4 候选映射

| 缺口 | a-stock-data 候选入口 / 实际来源 | 可复用内容 | 仍缺且阻断 Formal 的证据 | 当前判定 |
| --- | --- | --- | --- | --- |
| B1 PIT 流通市值 | `tencent_quote()` / 腾讯；`eastmoney_stock_info()` / 东财；`baostock_valuation_history()` / BaoStock | 当前流通市值/流通股字段参考、历史换手率及价格序列参考 | 历史流通市值原始版本、口径与价格基准、沪深完整覆盖、北交所边界、首次观察/可用时间、跨 cutoff 修订 | `NO_GO` |
| B2 历史正确股本 | `eastmoney_stock_info()` / 东财；BaoStock `turn` | 当前总股本/流通股字段及历史换手率输出可用于语义对账 | A/B/H 与限售/自由流通口径、逐日生效和披露时间、历史版本、修订链；不得从换手率反推或用当前股本回填 | `NO_GO` |
| B3 公司行动与因子 | `dividend_history()` / 东财；`sina_adjust_factor()` / 新浪；`cninfo_announcements()` / 巨潮；mootdx 除权除息 | 字段候选、公告追索、因子对拍、普通行动样本 | 稳定经济事件/组件 ID、税和共同旧股基数、初版/修订/取消、全类型/全页/合法零行动、历史 `available_at`、固定前一 session P | `NO_GO` |
| B4 行情、状态、首封、基准 | `tdx_daily_package()` / 通达信官网；`baostock_valuation_history()` / BaoStock；`em_zt_pool()`/`em_zb_pool()`/东财；`ths_limit_up_pool()`/同花顺；`trading_calendar()`/深交所 | 盘后全市场日线及包内完整性检查、沪深历史 ST/停牌、首封字段、交易日历参考 | 申请区间逐日包存在性、历史冻结股票池、北交所一致边界、榜单 total/分页/失败与零行区分、首封历史观察/修订、固定基准 PRICE 的版本与 PIT | `NO_GO`；停牌 2.0.0 既有子项保留 |

通达信盘后包当前只证明部分日期可下载：参考仓库明确记录 2021 年较早日期已缺、2022-05-06 前无北交所且没有逐日验证。它可以成为 `bar_1d_raw` 候选 Endpoint，不能单独证明完整历史市场输入。

## 6. Source Admission 最小包

每个拟接入 Endpoint 独立提交以下材料，不允许用另一个来源的文档补齐：

1. 固定 `source-contract.json`：Provider/Endpoint/文档/Adapter/Mapping 版本、字段、单位、身份、空值、分页、revision/cancel 和许可。
2. 脱敏 `raw/`：成功、合法零行、缺页、限流、错误、未知类型、修订和取消的实际响应字节与 Hash。
3. `observation-log.jsonl`：请求范围、响应状态、source published、first observed、ingested、available 时钟及时区依据。
4. `coverage-manifest.json`：预期证券×交易日或事件区间、页码/total/终止、成功/失败/缺失、冻结股票池和交易日历 Hash。
5. `revision-chain.jsonl`：同一经济身份跨 cutoff 的初版、修订、取消和 supersedes 关系。
6. `quality-report.json`：Schema、唯一键、单位、正值、日期/身份对齐、跨源冲突、合法零行和未处理隔离项。

合法零行必须同时满足：请求成功、`decoded_row_count=0`、范围完整、分页结束、无错误/截断、可用时间可靠。空数组、异常 fallback、缺页、非交易日或风控失败都不是零事件证明。

## 7. 后续实施顺序

| 步骤 | 允许动作 | 停止条件 |
| --- | --- | --- |
| A：架构收敛 | 固定 Adapter Bundle、Provider/Endpoint 分层、B1—B4 候选和门禁 | `DONE`；不代表来源获准 |
| B：C-004 Endpoint Admission 契约 | 纯追加四对象、Schema、Golden、Repository、0016 与 fail-closed Formal 校验 | `DONE`（本地基础设施）；未认证具体 Endpoint |
| C：单 Endpoint admission | 先选择一个具备完整材料的 Dataset/Endpoint，追加 Raw Schema、Mapping、质量和 ProviderPolicy | 任一 PIT/coverage/revision/许可缺失则 `NO_GO` |
| D：WP-0303 输入与派生 | 合格 Binding + `PIT_CERTIFIED` Receipt 对应 Snapshot 才进入 Adjustment/Resolver/F1/F2/FeatureStore | 不得以当前历史下载、fixture 或聚合 fallback 解锁 |
| E：正式验收 | 固定 Bundle 重启消费、真实 source Correction 传播、隔离 PostgreSQL 和完整 gate | 生产认证仍需独立授权 |

完整 Goal 和阶段定义见 [WP-0303-FULL-INPUT-TO-FEATURE-CLOSEOUT Goal v2](WP-0303-FULL-INPUT-TO-FEATURE-CLOSEOUT-GOAL.md)。阶段 B 完成只表示来源准入基础设施形成，不关闭 B1—B4。

## 8. 兼容性和当前状态

- 不修改旧 14 F1、65 F2 的载荷、版本、Hash、Golden 或固定引用。
- 不修改 0014/0015、B5、N1/N2；`FixtureExecutionLineageBridge` 继续是 `FIXTURE_ONLY`。
- 不把 `a_stock_data` 的现有 `AGGREGATOR` Golden 原地改名为某个实际来源。
- 本次只新增四个 Admission Definition/Receipt/Binding 类契约及 `0016`；不注册 B1—B4 新 Dataset、Raw Schema、Mapping、Capability、Policy、Method 或指标 Definition。
- `WP-0303=IN_PROGRESS`，B1—B4 整体新增关闭项为 0；`market_breadth/market_emotion=missing`，Formal/Paper 拒绝，`NOT CERTIFIED`，`RELEASED=false`。

本文记录架构与本地 Admission 基础设施，不是 Provider/API、历史数据、生产数据库或发布认证。
