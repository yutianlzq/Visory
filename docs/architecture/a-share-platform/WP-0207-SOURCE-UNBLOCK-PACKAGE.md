# WP-0207 真实来源最小解阻包

日期：2026-10-15。状态：`WP-0207=IN_PROGRESS`，生产 `NOT CERTIFIED`，`RELEASED=false`。

## 1. 用途、结论与边界

本文把 `AGENTS.md` 2.2 的本地参考项目路由收敛为可直接交给 Provider maintainer、数据 owner 和历史档案 owner 的最小交付要求。它只回答“继续七阶段真实回填前必须提供什么”，不证明任何参考项目当前可用、已获授权、覆盖完整或满足生产 PIT。

- 2026-10-14 的初始参考材料轮只读检查 `E:\Personal Manager\参考项目` 中指定源码和文档；未读取 `.env`、Token、Cookie、连接字符串或其他凭据，未运行参考脚本、调用 Provider 或访问生产。2026-10-15 的授权在线窄样本另见 1.1，不能反向提升参考材料等级。
- 参考目录没有可用于本轮绑定内容的 Git 元数据；下文同时记录当前本地文件 SHA-256 和 `references/manifest.yaml` 的历史核验提交，但二者不能自动拼接成“当前文件属于该提交”的证明。
- `a-stock-data` 与 `Financial-API` 只作为 Adapter/字段契约候选；Fleur 只作设计反例；UZI 只允许 clean reimplementation；`daily_stock_analysis` 只作迁移基线。
- 当前 Registry 中的 `adapter_version=1.0.0`、Provider raw schema、mapping 和 Capability 是确定性本地契约输入；Capability 仍为 `UNVERIFIED` 且 `history_start=None`，不能替代真实上游版本、授权和历史覆盖证据。
- 任一阶段材料不满足本文 gate 时，该阶段必须保持 Blocked 或机器可见 `Unavailable`；不得用空数组、当前快照、fixture、字段名、README 自述、重新下载的今天数据或合成 `available_at` 代替证据。

### 1.1 2026-10-15 授权只读验证增量

- 使用专用只读 Key 对 `https://fuyao.aicubes.cn` 执行两轮限定验证，共 38 次 GET：首轮 30/30，追加轮 8/10；频率不超过 1 QPS，未下载 Market Dump、访问生产数据库/真实 `/data`/生产调度或调用写接口。证据不保存 Key、request ID 值或完整响应正文。
- `920799.BJ` 最近窗口日线返回 10 行，2025-01-01 至 2026-09-30 闭合窗口返回 424 行；最新估值返回 1 行并明确包含该标的。该结果证明单一 BJ 标的在限定窗口的日线与最新估值可读，不证明北交所完整 universe、退市证券、全历史或历史估值。
- 历史端点对同一闭合窗口传入 `offset=0/1/423/424/425/1000000`，均返回完全相同的 424 行和相同 item SHA-256；响应也没有 `total/has_more/next_offset/page_size`。因此在线端点实际忽略 `offset`，无法通过 offset 到达终止页，S09/G05 为明确的 `FAILED_CONTRACT`，不是已通过或仅待补测。
- 线上 `tickers/list` 的 `exchange=SZ/BJ` 与 SH 控制返回相同 SH 行；三个退市候选搜索为空，历史退市代码返回 `1002`。响应仍缺 `source_published_at/available_at/revision/cancel/supersedes`。这些反例继续阻塞 Identity/状态、行情 Coverage 和 PIT/修订 Gate。
- 固定结果位于仓库外 `C:\Users\lzq11\.codex\task-evidence\WP-0207-AUTH-API-VALIDATION-20261015-01a134a9` 与 `C:\Users\lzq11\.codex\task-evidence\WP-0207-AUTH-API-EXTENSION-20261015-01a134a9`。这些是授权窄样本和失败契约证据，因缺固定线上版本、完整 Coverage/PIT/修订档案及 package Manifest，仍不足 E3。

### 1.2 2026-10-15 `a-stock-data` 固定 Adapter 与执行门禁

- 本轮只读固定 GitHub 仓库 `https://github.com/simonlin1212/a-stock-data` 的 Release `3.10.2`、commit `29b07d2e37005b9fd568bca1262f6e572b5f9407`、tree `0207d3ec35593524a7fe9870413ac5ddaf6f282a`、`SKILL.md` blob `8e334569f7cfd334b56f3b3bd067469d175ba892` 和 Apache-2.0 `LICENSE` blob `088c0826ad3a02908696b1ff6c9e4fbd9b2823af`。这些值只固定 Adapter/toolkit 说明与许可证，不固定其背后的 BaoStock、深交所、通达信、东财、新浪、腾讯或申万数据字节。
- 新增 `ProviderSourceRouteEvidence`，把内部 Provider/Dataset/Adapter 版本、固定 Adapter commit/blob、实际 upstream、Coverage/PIT/分页/revision 状态、许可证和确定性 `source_route_hash` 绑定为不可变证据。当前为现有平台 Dataset 固定 8 条候选路由：`security_master`、`trading_calendar`、`bar_1d_raw`、`instrument_status_daily`、`listing_status_history`、`corporate_action`、`financial_statement`、`benchmark_index_1d`。
- 8 条真实候选路由全部保持 `BLOCKED`；默认 Provider Capability 仍为 `UNVERIFIED`。`valuation_daily`、`industry_membership`、`non_core_observation` 的正式 Dataset/Raw Schema/Mapping/Policy 尚未建立，继续由既有 Backfill 门禁投影为机器可见 `Unavailable`，本轮没有用参考项目字段静默创建平行契约。
- 新执行的 `ProviderRun` 保存完整 `source_route_evidence`，请求 fingerprint 追加绑定 `source_route_hash`，Provider 响应的 `actual_upstream` 必须与批准路由一致。旧 `ProviderRun` 的字段允许 `null` 仅为历史兼容，不为旧记录补造来源证据，也不能据此重放或认证历史。
- 真实 transport 的 Backfill preflight 检查 Dataset、Policy、Provider、Capability、Provider Raw Schema 和 source route；缺失、`UNVERIFIED` 或 `BLOCKED` 均 fail closed。fixture 必须声明 `fixture_only=True`，其实际 pipeline plan 的 Raw 配置在创建业务子任务前复用 Raw worker 校验 route/Schema/adapter；route 还要重新验证状态和 hash，返回当前 Provider/Dataset/Adapter/version 绑定的 `FIXTURE/FIXTURE_ONLY` 证据。普通 transport 不能借同名方法或允许 fixture 的 registry 绕过门禁。初次审查发现的父门禁反例已关闭；定向隔离 PostgreSQL 仍只证明合成路径，见[验收记录](WP-0207-END-TO-END-CLOSEOUT.md)。
- 临时 PostgreSQL/tmpfs 与临时存储上的本地对象链验证使用合成 fixture transport，只证明门禁、事务、文件发布、checkpoint 和恢复实现，不证明七阶段真实历史、2018 至今核心覆盖、两真实成功源、远程 CI/合入或生产认证。

## 2. 证据等级

| 等级 | 含义 | 本轮是否存在 |
| --- | --- | --- |
| `E3` | 固定接口版本、已授权脱敏真实样本、覆盖与 PIT 档案、逐文件 Hash 均齐全 | 否 |
| `E2` | 固定本地文档/源码字节，可作为 Adapter 或反例设计输入 | 是 |
| `E1` | README/SKILL 自述、示例、历史实测数字或当前快照能力 | 是，含授权窄样本，但只作候选/反例 |
| `E0` | 无版本、无授权、无样本、无覆盖/PIT 证据 | 七阶段真实来源当前总体状态 |

只有 `E3` 才能进入真实 Raw→Canonical→Snapshot 集成验收。`E2/E1` 不能把 Provider Capability 从 `UNVERIFIED` 提升为可认证状态。

## 3. 最小交付目录

每个 Provider 必须独立交付，不得把主源和补充源静默混成一包：

```text
wp0207-source-package/
  <provider_id>/
    package-manifest.json
    authorization-scope.md
    contracts/
      provider.json
      endpoints/*.json
      raw-schema/*.json
      canonical-mapping/*.json
    samples/
      S01-.../request.json
      S01-.../response.json|response.parquet
      S01-.../metadata.json
      ...
    coverage/
      universe.csv
      expected-intervals.csv
      observed-intervals.csv
      gaps.csv
      unavailable.csv
    pit/
      availability-events.csv
      revisions.csv
      cross-cutoff-cases.csv
    hashes.sha256
```

`package-manifest.json` 最少包含：

- `package_id`、`package_version`、`provider_id`、`generated_at`、`owner`、`contact`；
- 上游产品/API/SDK 版本、接口文档版本及 Hash、Adapter 名称/版本/代码提交或制品 Hash；
- 每个 Dataset 的 `dataset_id`、`dataset_schema_version`、Provider schema version、mapping version 和 mapping hash；
- 授权文件引用、允许的环境/端点/证券/日期/速率/保留期、明确禁止项及授权失效时间；
- 所有文件的相对路径、媒体类型、字节数和 SHA-256；
- 生成工具版本、时区、字符集、压缩和小数精度；
- `coverage_status`、`pit_status`、`revision_status`、`pagination_status`，值只能为 `PROVEN`、`PARTIAL`、`UNAVAILABLE`、`UNPROVEN`。

包内不得出现凭据值、预签名 URL、物理生产路径、原始响应正文中的敏感字段或异常堆栈。授权文件只描述范围，凭据仍通过 Visory 的 `secret://` 引用注入。

## 4. Provider 接口、字段、PIT 与分页契约

### 4.1 所有 Provider 的共同必填项

| 维度 | 必填内容 | Fail-closed 条件 |
| --- | --- | --- |
| 身份与版本 | Provider、真实 upstream、endpoint/operation、协议、SDK/API 版本、Adapter 版本与制品 Hash | 任一版本只写“latest”或无法重放 |
| 请求 | 参数名/类型/默认值/上限、日期边界是否含端点、时区、复权口径、排序、过滤与 universe | 日期/复权/交易所默认值不明确 |
| 响应 | 完整字段、类型、单位、币种、精度、枚举、Null/空字符串/零语义、主键/业务键 | 缺失值可被误补零或单位不明 |
| 身份映射 | Provider symbol、交易所、历史代码/名称/板块、上市退市区间和 Canonical `entity_key` 规则 | 当前代码表被当作历史 universe |
| 时间/PIT | `event_time`、`source_published_at`、`observed_at`、`ingested_at`、`available_at`、availability basis/policy version | 历史回填用下载时间或入库时间伪造 `available_at` |
| 修订 | 稳定对象/事件 ID、revision、supersedes、首次披露、修订、撤回/取消与生效规则 | Correction 覆盖旧对象，或无法区分更正与重复抓取 |
| 分页 | 稳定排序键、page/cursor/offset、页长、total、终止条件、重复/缺页检测和重试后连续性 | 只因短页/空页就成功但无全量保证 |
| 零行 | 成功状态、`decoded_row_count=0`、完整覆盖终点、无错误/截断和可靠 `available_at` | 失败、缺页、未知类型或权限错误返回空数组 |
| 错误/重试 | 稳定公开 code、retryable、限流、`Retry-After`、超时、最大重试和幂等键 | 把响应正文、Token、DSN、路径或堆栈写入公开错误 |
| 发布 | Raw 原始字节、Content Hash、Schema Hash、Manifest Hash、文件 Hash 和 release 标识 | 只保留临时 URL、文件名或行数 |

Visory 的 `AvailabilityMetadata` 要求历史回填不能使用 `PLATFORM_OBSERVED`，也不能令 `available_at == ingested_at`。若使用 `SOURCE_DISCLOSURE`，必须有 `source_published_at`；若使用 Provider timestamp，必须证明该时间的真实语义。

### 4.2 Financial-API 候选能力与缺口

| 数据阶段 | 本地候选接口/文件 | 当前可支持的设计事实 | 仍缺且阻塞的契约 |
| --- | --- | --- | --- |
| Identity | `/api/meta/tickers/list` | `limit/offset`；短页或空页终止；字段含 `thscode/ticker/name/exchange/asset_type/currency` | 默认仅 `SH,SZ`，必须显式包含 `BJ`；没有上市/退市、历史名称、代码迁移和完整退市 universe；没有当前线上版本/授权样本 |
| Calendar | `/api/a-share/calendar/trading-days` | 返回近一年交易日，Asia/Shanghai 日期升序 | 无范围参数，只覆盖 `[今日-1年, 今日]`；不能满足 2017 起及当前年份后一年，也不能由“未出现在 open list”单独证明闭市事实 |
| 日 K | `/api/a-share/prices/historical` | 单证券、仅 `1d`、窗口不超过 10 年；价格/量/额字段；支持 `none/forward/backward`；授权样本确认 SH/SZ 与单一 BJ 标的可读 | Visory 原始事实必须固定 `adjust=none`；在线端点对 `offset=0/1/423/424/425/1000000` 返回同一页，实际忽略 offset，且无 total/has_more/page size，不能证明或执行全量分页 |
| 日 K 批量 | `daily-k` / `daily-k-10d` dump | Parquet；字段明确；全量描述为“最近约 10 年”；未复权 | “约 10 年”不是固定起止；无 universe/退市覆盖保证；预签 URL 不是固定引用；必须补 release Manifest、实际文件 Hash、每证券 min/max/row count/gaps |
| 公司行动 | REST adjustment factors | `ex_date_ms`、税前 `dividend_per_share`、`per_share_bonus` | 不返回 `event_type/record_date/adjust_factor`，也没有稳定事件 ID、revision、cancel、披露/PIT 时间；不能满足当前 Canonical 必填字段 |
| 公司行动批量 | adjustment-factors dump | 比 REST 多 `allotment_ratio/allotment_price/currency` | REST/dump Schema 不同，禁止静默拼接；仍缺稳定身份、修订/取消、披露时间、旧股分母及完整退市覆盖 |
| 财务 | 三张报表端点 | 单证券；最近 1–20 期或 ≤10 年区间；`period_end_ms` 与 `report_date_ms` 分离；Null 不得补零 | `data.timestamp` 的 PIT 语义不清；`report_date_ms` 不能自动等于首次可用时间；缺首次披露、修订、撤回、revision 和跨 cutoff 档案 |
| 估值 | `/api/a-share/valuations/snapshot` | 最新五项估值，Null/负数语义明确；授权样本确认 `920799.BJ` 当前快照可读 | 只提供最新快照，无历史分页；单一 BJ 当前行不证明完整 BJ universe；一个聚合 `timestamp` 不代表各指标同时更新，不能满足 2018 起历史估值 |
| 非核心 | special-data 系列 | 有 `page/size`、`limit/offset`、单日、当日或近一年多种窗口 | 各端点分页模型和窗口不同；多数不支持全历史，只能在固定契约和上线日起作为观察数据，不能回填伪历史 |

参考 `rest.py` 的 ticker 自动分页、限流和 `Retry-After` 只能作为实现候选。`historical()` 未实现文档声明的 `offset`；在线验证进一步证明服务端当前忽略该参数，因此客户端不能通过补一个 offset 循环自行闭合分页。`dump.py` 的 Range resume 和原子 rename 也只作候选，而且其异常会拼接 `resp.text[:200]`、`body!r` 和传输异常，不符合 Visory 公开脱敏要求。

### 4.3 a-stock-data 候选能力与缺口

| 候选函数 | 当前可支持的设计事实 | 仍缺且阻塞的契约 |
| --- | --- | --- |
| `baostock_valuation_history` | 字段 `date/code/close/peTTM/pbMRQ/psTTM/pcfNcfTTM/turn/tradestatus/isST`；`adjustflag=3` 不复权；`turn` 为百分数，`0.31=0.31%` | 不支持北交所；SKILL 的历史行数是自述，不是本轮真实样本；需固定 baostock 版本、结果流终止、错误/零行、完整证券清单、PIT 与逐日覆盖 |
| `baostock_stock_basic` | 候选字段 `code/code_name/ipoDate/outDate/type/status` | 查询时基本信息不能证明历史名称/代码变化或完整退市全集；`outDate` 空值语义、历史快照和首次可见时间需单独证明 |
| `sw_industry_history` / `sw_industry_as_of` | 候选字段 `code/start_date/industry_code/update_date`，可形成 as-of 生效区间 | URL 指向可变 XLS；需固定文件 Hash、分类版本、名称表、完整 universe、结束区间、披露/发布时间和跨 cutoff 档案；`update_date` 未经证明不能直接成为 `available_at` |

已退市标的公司行动和北交所能力在参考材料中存在明确源侧缺口。该缺口必须进入 `unavailable.csv` 和公开 Coverage Projection，不能用其他市场当前快照或空成功填补。

### 4.4 只作反例/迁移参考的代码

- `daily_stock_analysis` 的 `BaseFetcher` 统一了 `_fetch_raw_data/_normalize_data` 和 fallback，但没有版本化 Raw Schema、历史 PIT、固定文件/Manifest 或 Durable Task 事务；`allow_empty_daily_data` 也不能单独证明合法零行。
- Fleur 固定了 Contract/Parquet/Source Schema Hash，并记录分区 metadata；但示例允许 `allow_empty=True`，部分分区失败时仍返回成功集合，只在全部失败时抛错，且错误样例包含内部错误文本、bucket/object key。年回填控制器顺序启动命令，没有 Visory 所需的父 checkpoint、跨进程固定引用复验和事务 fence。
- UZI BaoStock 示例使用 `adjustflag=2` 前复权，并把价格、量、额和换手率缺值转为 `0`；这会破坏原始事实和 Null 语义。`DimResult` 的 `missing/error` 可降级为同一个 legacy fallback 布尔值，错误仅截断 200 字符，也不能替代结构化脱敏。

## 5. 七阶段 Canonical 映射条件

| 阶段 | Visory Dataset/字段门槛 | 当前处理 |
| --- | --- | --- |
| Identity/Calendar | `security_master` 必须含稳定身份、交易所、上市日、有效区间和 PIT；`trading_calendar` 必须含 market/date/open 状态和 PIT | 候选元信息不含完整历史；日历窗口不足，Blocked |
| 行情月分区 | `bar_1d_raw` 必须含原始 OHLC、股数、金额、前收、状态、涨跌停价、PIT；复权固定 `none` | REST/dump 字段均不能直接覆盖全部必填字段与分页/覆盖证明，Blocked |
| 状态/上市退市 | `instrument_status_daily`、`listing_status_history` 必须给逐日/区间状态及 PIT | BaoStock 字段是候选，但北交所、历史名称/代码和完整退市 universe 未证明，Blocked |
| 公司行动 | 必须给 `corporate_action_id`、type、ex/record/payment date、ratio/cash/currency、revision、`published_at/available_at` | Financial-API 只覆盖部分经济字段，缺身份/修订/PIT，Blocked |
| 财务/估值 | `financial_statement` 必须给 period/type/item/value/unit/currency、revision、`published_at/available_at`；估值需单独正式 Dataset/Policy | 报表可作字段候选但 PIT/修订缺失；当前 Registry 没有正式历史估值 Dataset/Policy，估值应机器可见 Unavailable |
| 行业 | 需正式 versioned Dataset/Policy，至少含分类体系版本、成员有效区间、披露/PIT 和历史 universe | 当前 Registry 没有正式行业 Dataset/Policy；只读 XLS 候选不能直接发布，Unavailable |
| 非核心观察 | 每类数据需独立 Dataset/Policy、可靠窗口、分页、零行和 PIT | 当前缺正式契约时从平台上线日开始或 Unavailable，不回填伪历史 |

Provider owner 不能直接提交与当前 fixture 字段同名的数据就宣称匹配；必须提交 ProviderRawSchemaDefinition 和 ProviderCanonicalMappingDefinition 所需的源字段类型、目标单位、Null/时间语义、enum mapping 与确定性 mapping hash。

## 6. 历史覆盖清单

| 阶段/数据集 | 目标区间 | universe 与粒度 | 必须提交的完成证据 |
| --- | --- | --- | --- |
| Security Master/历史名称 | 来源可证明的完整历史，至少 2018-01-01 至执行 cutoff | SH/SZ/BJ，含在市、退市、代码迁移和名称变更；事件/有效区间 | universe 总数、按交易所/板块/状态统计、每证券首末有效日、缺口及原因 |
| Trading Calendar | 2017-01-01 至 2027-12-31 | CN 每个自然日的 open/closed 或可证明等价完整日历 | min/max、自然日总数、开闭市数、未来日历版本/发布依据、异常日期 |
| 日 K | 2018-01-01 至最新已完成交易日 | 每个目标证券×预期交易日；包含退市、停牌、未上市 | 每证券 min/max/row count、预期/实际 session、duplicate/gap、调整口径 `none` |
| 状态/上市退市 | 2018-01-01 至执行 cutoff；更早上市信息按来源完整历史 | 逐证券逐日状态及 listing interval | `ACTIVE/ST/SUSPENDED/DELISTED/NOT_LISTED` 计数、区间无重叠、与日 K/身份交叉校验 |
| 公司行动 | 2018-01-01 至执行 cutoff | 每证券逐事件及 revision；无事件证券也要可证明覆盖 | 事件类型/身份/修订/取消统计、日期/金额/比例质量、no-action 覆盖清单 |
| 财务 | 2017 年度报告期至执行 cutoff | 每证券、报表期、三张报表、初始披露及更正 | 各报表/期数、首次披露/修订/撤回、Null 统计、跨 cutoff PIT 对照 |
| 估值 | 2018-01-01 起或 Provider 可证明的有效起点 | 每证券逐交易日、逐指标；BSE 单列 | 指标级 min/max/row count/null、Provider 有效起点、未支持区间 Unavailable |
| 行业 | 2018-01-01 至执行 cutoff | 每证券、分类版本、有效区间 | 分类版本/名称 Hash、成员区间、重叠/空洞、退市证券、披露/PIT |
| 非核心观察 | Provider 可证明历史；否则平台上线日开始 | 每端点独立窗口/分页 | 上线日、固定接口版本、实际首日、窗口限制和历史 Unavailable |

`coverage/expected-intervals.csv` 和 `observed-intervals.csv` 最少包含：`provider_id,dataset_id,entity_key,exchange,expected_from,expected_to,observed_from,observed_to,expected_count,observed_count,duplicate_count,gap_count,coverage_status,evidence_hash`。

`gaps.csv` 最少包含：`dataset_id,entity_key,date_from,date_to,reason_code,retryable,retry_after,source_package_id`。核心区间缺口未清零时不得标记 Certified；可重试缺口必须给重试计划，不可证明区间进入 `unavailable.csv`。

合法零行必须同时满足：请求成功、`decoded_row_count=0`、分页/区间已完整到达终点、无错误/截断、身份和请求范围明确、`available_at` 有可靠依据。否则只能是 Failed、Partial、Quarantined 或 Unavailable。

## 7. 授权脱敏样本 S01-S14

每个适用 Dataset/Provider 至少提交下列样本。证券和市场数据本身可保留真实值；凭据、用户信息、内部主机、物理路径、预签参数和响应中的敏感正文必须脱敏，且脱敏前后结构/类型保持可验证。

| 编号 | 样本 | 最低要求 |
| --- | --- | --- |
| S01 | 正常非空成功 | 一次完整 request/response、状态码、headers 白名单、行数和 Hash |
| S02 | 区间起点边界 | 覆盖路线图最早日期或 Provider 可证明起点 |
| S03 | 当前终点边界 | 覆盖最近已完成日期，证明时区和包含/排除规则 |
| S04 | 退市证券 | 身份、上市退市、历史日 K/状态/公司行动的可得与缺失情况 |
| S05 | 北交所证券 | 当前代码、历史代码迁移、支持/不支持的稳定结果 |
| S06 | 停牌/ST/未上市 | 区分 Null、零值、无成交和状态枚举 |
| S07 | 合法零行/no-action | 成功 envelope、完整覆盖终点和可靠 PIT；不得用失败空数组 |
| S08 | Unsupported/Unavailable | 稳定 reason code、不可伪造的缺失区间及公开投影 |
| S09 | 分页完整性 | 第一页、中间页、最后短页/空页；排序键、cursor/offset、total 与页 Hash |
| S10 | 分页反例 | 重复页、缺页、cursor 循环或 unstable sort，Adapter 必须 fail closed |
| S11 | 修订/取消 | 同一逻辑对象至少两个 revision，含 supersedes；适用时含 cancel/withdraw |
| S12 | 跨 cutoff PIT | 同一对象在两个 cutoff 的可见性差异，绑定 source publication/observation/availability |
| S13 | 双源失败/冲突 | 主源失败+补源成功、双源冲突、schema drift/quarantine 各至少一例 |
| S14 | 批量文件与恢复 | release 标识、实际文件/Manifest Hash、Range/重启或等价恢复、覆盖统计和旧文件不变 |

每个样本 `metadata.json` 至少包含：`sample_id,provider_id,dataset_id,endpoint_version,adapter_version,request_fingerprint,observed_at,source_published_at,available_at,availability_basis,row_count,byte_count,schema_hash,content_hash,redactions,authorization_ref`。

授权范围文件至少明确：只读环境、端点、证券/universe、日期范围、最大请求/下载量、QPS、保留期、是否允许保存脱敏 Raw、是否允许生成 Canonical/质量报告、禁止生产写入/调度/部署、联系人和到期时间。文件中不得放入密钥；实际凭据由授权 owner 通过既有秘密管理通道提供。

## 8. 验收 Gate

| Gate | 通过标准 |
| --- | --- |
| G01 版本固定 | 接口文档、SDK/API、Adapter、Raw Schema、Mapping 均有不可变版本和 Hash |
| G02 授权明确 | 只读范围、数据保留/脱敏、端点、日期、universe、速率与到期时间均明确 |
| G03 字段语义 | 类型、单位、币种、精度、枚举、Null/零和时区可映射到 Canonical |
| G04 身份完整 | SH/SZ/BJ、退市、代码迁移、历史名称和 `entity_key` 规则可验证 |
| G05 分页完整 | 稳定排序、终止、重复/缺页/cursor 循环反例通过；逐页 Hash 可重放 |
| G06 合法零行 | 零行与失败/权限/截断可区分，且有覆盖终点和 PIT |
| G07 PIT | `published_at/observed_at/available_at/ingested_at` 分离；跨 cutoff 用例通过 |
| G08 修订不可变 | revision/cancel/supersedes 可重放；Correction 新增对象，旧 Raw/Snapshot/文件不变 |
| G09 历史覆盖 | 规定区间、全 universe、退市证券、逐日/逐事件 gaps 可查询；核心缺口未清零不认证 |
| G10 双源质量 | 主源、补源、冲突、quarantine、Unavailable 使用既有 Policy，禁止逐行静默混合 |
| G11 固定对象链 | ProviderRun→RawObject→CanonicalPartition→QualityReport→DataSnapshot 及文件/Manifest Hash 完整 |
| G12 恢复事务 | checkpoint、跨 attempt/进程、父 checkpoint 前崩溃、lease/cancel/publication fence 和 COMMIT/I/O 失败通过实际 PostgreSQL/files 验证 |
| G13 公开脱敏 | API、Task、P-DATA、Operations、SSE、日志和浏览器不泄露凭据、正文、DSN、路径、堆栈；保留 code/retryable/request ID |
| G14 交付绑定 | 样本、Coverage、PIT、Adapter 和验收报告 Hash 进入同一 package Manifest，旧证据不被重写 |

任何单个阶段 G01-G14 未全通过时，该阶段不能宣称“真实执行完成”。全 WP 还需七阶段按依赖顺序完成、核心缺口清零、完整 gate/前端 gate 通过、当前增量远程 CI/合入完成；生产认证另需生产数据库、真实 `/data`、调度、全历史在线执行、部署和回滚的独立授权。

## 9. 当前支持矩阵

| 项目 | 判定 | 说明 |
| --- | --- | --- |
| Financial-API ticker `limit/offset` 契约 | 线上反例且阻塞 | `exchange=SZ/BJ` 与 SH 控制返回相同 SH 行，不能构建分市场 universe；仍缺固定线上版本和完整证券清单 |
| Financial-API 历史 K 分页 | `FAILED_CONTRACT` | 在线 `offset=0/1/423/424/425/1000000` 返回同一 424 行；无 total/has_more/page size，无法到达终止页 |
| Financial-API bulk dump | 仅候选 | 有 Parquet Schema、release tag/Range/rename 思路；无固定区间/universe/PIT/文件 Manifest 证据 |
| Financial-API 公司行动 | 部分候选 | 经济字段可参考；稳定身份、修订/取消、披露/PIT 缺失，REST/dump 不同 |
| Financial-API 财务 | 部分候选 | 报告期/报告日期及 Null 语义可参考；首次披露、修订和 `available_at` 缺失 |
| Financial-API 估值 | 不满足历史回填 | 单一 `920799.BJ` 当前快照可读，但仍仅最新快照，聚合 timestamp 不能证明逐指标历史 PIT 或完整 BJ universe |
| BaoStock 估值/状态 | 部分候选 | 日频字段和不复权口径可参考；北交所不支持，版本/分页/覆盖/PIT/真实样本缺失 |
| BaoStock 基本信息 | 部分候选 | 上市/退市字段可参考；不能证明历史名称、完整退市 universe 和首次可见时间 |
| 申万行业 XLS | 部分候选 | 生效日/as-of 算法可参考；可变文件、分类版本、披露/PIT、完整覆盖未固定 |
| Fleur Contract/分区/年回填 | 设计反例 | 不作为来源或 Visory runtime；部分失败/allow-empty/错误暴露语义不满足当前 gate |
| UZI/DSA Provider 模式 | 迁移或反例 | 前复权、缺值补零、legacy fallback 和无 PIT/固定对象链不能直接复用 |
| 授权脱敏真实样本 | 缺失且阻塞 | 本轮未提供 S01-S14 或只读访问范围 |
| 历史 Coverage/PIT 档案 | 缺失且阻塞 | 无完整 universe、逐日/逐事件 gaps、revision/cancel 和 cross-cutoff evidence |

## 10. Owner 分工与继续顺序

1. **Provider maintainer**：交付固定接口/SDK/Adapter/Raw Schema/Mapping、分页/错误/限流契约及 S01-S10、S13。
2. **数据 owner**：交付 universe、规定历史区间、逐证券/逐日或逐事件 Coverage、合法零行和 Unavailable 清单及 S02-S08。
3. **历史档案 owner**：交付首次披露、revision/cancel、跨 cutoff PIT 档案和不可变原始文件/Manifest，覆盖 S11-S12、S14。
4. **Visory WP-0207**：只在前三包 Hash 固定且授权有效后，按既有 Durable Task、Provider Policy、Raw→Canonical→Snapshot、质量门禁和公开脱敏链路集成；不得新增 Queue、Publisher 或 Repository。

交付后先做离线 package 校验，再做获授权的临时 PostgreSQL/临时存储集成；生产数据库、真实 `/data`、生产调度、全历史在线回填和部署仍需单独授权。材料未到齐前可以维护 Adapter/契约校验代码，但不得创建伪数据、空成功或伪造 `available_at`。

## 11. 本轮参考文件固定 Hash

下列 SHA-256 固定的是 2026-10-14 本轮实际读取的本地字节，不等于线上版本证明，也不自动绑定 `references/manifest.yaml` 中的历史提交：

| 参考文件 | SHA-256 |
| --- | --- |
| `a-stock-data-main/SKILL.md` | `5c4572af0d4483560b7c78b5f53c34019ff6f5cf839275a2d149b37c3bdc1973` |
| `daily_stock_analysis-main/data_provider/base.py` | `8b17718dd5015315fac174c8de8e54fb96edd1883328b3e5a8bbc8026c679476` |
| `Financial-API-main/docs/api/endpoints-calendar.md` | `a6cb1ca282c57ba755b75a6b9254d5e0f3e05c1e3e8e1ae8f030d31ad2df3802` |
| `Financial-API-main/docs/api/endpoints-financials.md` | `3ef604b39e2c4ee27738026b5142faeb172a638d03cde435fd623b960c694026` |
| `Financial-API-main/docs/api/endpoints-market-dumps.md` | `a8b6230f3005bc7d858360289a8fb496724bf5b19677b2a82d2c6caa04946fcf` |
| `Financial-API-main/docs/api/endpoints-meta.md` | `754cc2f484298de9a98848e87f02229579970e43156ef4d58f2dd96ca6b78e2a` |
| `Financial-API-main/docs/api/endpoints-prices.md` | `ba5d28a3078c63c7bbc46e8c96e84befbb9be720c1d0673aa5dfefc1ed6eaff9` |
| `Financial-API-main/docs/api/endpoints-special-data.md` | `f6b51bc7669e59b7825a47eb0eca23b398b5399fa97e4be9ac414dcdaf99a197` |
| `Financial-API-main/docs/api/endpoints-valuations.md` | `2bc94c9a876ca0fcf200f6906569d78f7aaa6ee3fcd0a166ac61399a08785493` |
| `Financial-API-main/python/marketdb/providers/dump.py` | `24acf2e8ecb878241fad3ee4c64cd60e393e5d746df751325543b53b8596280e` |
| `Financial-API-main/python/marketdb/providers/rest.py` | `cbbed84f27fbe5d999829c947395dbc50deb7adabf5a8b86a3d885fcc72492ae` |
| `Fleur-main/.../baostock/backfill_controller.py` | `73a2300524216249c6841347c65a9143d72cc48efa862ddd34039aaf0d3fbc22` |
| `Fleur-main/.../contract_schemas.py` | `48a639af3930e8069c6c2272994efebb0e68c23ae81bbce8ca51046e51318a75` |
| `Fleur-main/.../http/partitioning.py` | `0db605a0f6f96bfb3e0cee5099ab7e460bf1779bc5148c5ac1ef4479ed29ca0a` |
| `UZI-SKILL-astock-master/deep-analysis/assets/data-contracts.md` | `6e4ad820e983f6996e6f9ec5660a5582a0afb5b64cc4d6d1e2507bf6390c2e3f` |
| `UZI-SKILL-astock-master/.../providers/baostock_provider.py` | `79feb1a32e7c9f71a57f21e8839f318e5cb83c21d9ee2dc196e04fd72bbbd219` |
| `UZI-SKILL-astock-master/.../pipeline/schema.py` | `b40c2faf3a165033e5aa443fb1e975c68721c45d66c40ee83dc950ffb2ede51b` |

`references/manifest.yaml` 的历史核验基线分别为：daily_stock_analysis `96bc532d...`（历史提交）、a-stock-data `f90d6785...`（当时默认分支 HEAD）、Financial-API `2ec779c9...`（历史提交）、Fleur `cecda70b...`（当时默认分支 HEAD）、UZI `d4d12ab7...`（当时默认分支 HEAD）。当前外部参考目录没有本轮可用的 Git 元数据，仓库 checkout 也没有相应受治理源码文件可做逐字节二次绑定，因此这些提交只作来源治理背景，不升级证据等级。

## 12. 当前判定

最小解阻包规范已收敛，但真实包尚未提供。当前本 Goal BLOCKER 仍是：S01-S14 授权样本、固定 Provider/Adapter 版本、完整历史 Coverage/PIT/修订档案及双真实成功源质量证据缺失；完整 gate 和全量 Web lint 仍未通过。远程 CI/合入和生产认证另受 Git 写入及生产资源授权阻塞。

本轮用固定 Python 复验 `scripts/check_ai_assets.py` 通过，`scripts/check_visory_baseline.py` 检查 633 个相对链接且 0 个破损，`git diff --check` 通过；17 个参考文件当前 SHA-256 与本文记录一致。本轮未改运行时代码，未运行后端/Web/PostgreSQL 测试，也未创建或清理 PostgreSQL 容器。

因此继续保持 `WP-0207=IN_PROGRESS / NOT CERTIFIED / RELEASED=false`。本文完成的是 owner 可执行的输入定义和验收门槛，不是七阶段真实回填、远程合入或生产认证。
