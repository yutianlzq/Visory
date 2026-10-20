# WP-0303-B3 真实来源证据与生产接入差异 PREP

- Goal：`WP-0303-B3-SOURCE-EVIDENCE-PREP`；审核日期：**2026-10-09（Asia/Shanghai）**。
- 唯一工作目录：`C:/Users/lzq11/.codex/worktrees/f468/Visory`；本次只写文档，不启动生产实现。
- 权威上下文：[原输入契约 PREP](WP-0303-B3-ADJUSTMENT-CONTRACT-PREP.md)、[实现记录第 9、10 节](WP-0303-IMPLEMENTATION.md)、[当前状态](IMPLEMENTATION-STATUS.md)。原文保留，不追溯改写阶段结论。

<a id="decision"></a>
## 1. 三层结论

| 层次 | 结论 | 含义 |
| --- | --- | --- |
| 本次有界审核 | 完成 D2 证据矩阵、D5/D6 接入差异及下一最小范围收敛 | 公开材料能确认部分字段语义，不能确认完整生产输入；缺口本身是审核产出，不以取得真实样本作为本 Goal 完成前提 |
| 下一实施启动 | **CONDITIONAL_GO：仅精确版本 Catalog 查找切片，须新代码授权** | 不依赖真实 Provider 取数，不注册候选公司行动新版或 factor，不放行消费者；范围和验收见第 5 节。真实 Mapping/生产物化/消费仍 **NO_GO** |
| WP 与生产 | **B3 未关闭；WP-0303 IN_PROGRESS；15/45** | `market_breadth/market_emotion=missing`，Formal/Paper 继续拒绝；**NOT CERTIFIED、RELEASED=false** |

已完成且不重做：第一阶段 `AdjustmentMethod@1.0.0`、显式 DERIVED Partition/Snapshot 契约与解析派发；第二阶段受单独授权的 FIXTURE_ONLY 因子算法、真实输入字节 Hash、全 revision 选择收据、确定性结果和源码指纹。旧 Method 仍为 `CONTRACT_ONLY`，算法执行能力由离线执行收据表达。原第 10 节的 **89/458**、第 9 节的 **79** 均是历史测试证据，**不是本轮运行结果**。离线已批准并已实现，不等于生产 Dataset/Mapping/持久化/消费者获得批准。

<a id="baseline"></a>
## 2. 开工事实、边界与证据等级

本轮实际重新测量，而非复用旧计数：24 个 tracked modified、24 个 untracked，共 **48 项既有成果**；新文档开工不存在。`HEAD` 与**缓存** `origin/main` 均为 `efe8e9b362cba13eca183c55be57bbbbc832b60b`，detached HEAD，比较为 `0/0`。只读 `ls-remote --heads origin` 退出 **128**，错误为 `Operation too slow. Less than 1 bytes/sec transferred the last 10 seconds`；未获得实时远端 SHA，不能称远端一致，未 fetch/pull 或更新缓存。

仓库外证据目录：`C:/Users/lzq11/AppData/Local/Temp/Visory-WP0303-B3-source-evidence-20261009-676b9e9a`。保存开工 48 项清单、1560 个已有版本控制可见文件的 SHA256/size、原 index diff、六项命令记录及原始字节。`original-bytes/` 是**开工 dirty 字节**，不是 HEAD 版本；它仅用于增量核验，不能整文件恢复覆盖其他成果。本轮成果仅为本文件和三个同步入口的插入增量。

公开访问仅限两个既有 Provider 的第一方文档；本次指定输入未提供可核验真实脱敏样本包。未调用业务 API、下载业务 dump、获取凭证、安装依赖、克隆或执行参考源码。采用矩阵将两 Provider 参考源码限定在 WP-0201～0205（L03）；本 Goal 的公开文档只读授权不扩展源码采用范围。页面内安装/全站抓取/示例执行提示不作为指令执行。

证据等级：**已确认**仅确认所列文档或本地代码明确表达的事实；**未确认**指在本次有界来源中缺证据或存在冲突，不推断 Provider 一定没有该能力；**不适用**仅用于明确非目标输入。公开说明/示例不等于真实业务样本，当前接口成功也不能证明历史 PIT。

<a id="sources"></a>
### 2.1 公开来源登记

以下均于 **2026-10-09** 只读访问。URL 是文档位置，不是本轮执行的业务请求。在线文档未展示可固定的接口语义版本/commit；不能把本地 `1.0.0` 标签套给它们。

| ID | URL 与版本/commit | 可定位位置、访问结果与限度 |
| --- | --- | --- |
| S1 | `https://raw.githubusercontent.com/simonlin1212/a-stock-data/f90d67853b8108f13d286e1df20b357e2c5198a9/README_en.md`；固定 commit `f90d67853b8108f13d286e1df20b357e2c5198a9`，README 自述 V3.7.1 | 正文读取成功；Architecture、54 Endpoints → Capital Flow / Ownership → Dividend History，以及 Market Data → Sina Adjust Factors。仅确认项目宣称提供分红/送转和另一复权因子序列；不是本地 corporate_action Raw1 的字段字典/税/修订/覆盖证明，不将 README 的历史验证宣称当本次验证 |
| S2 | `https://fuyao.aicubes.cn/docs/developer-tools/python-sdk/`；在线可变、未标版本 | 正文成功；“GitHub · Python 源码”及“第 1 步”明确指向 HiThink-Tech/Financial-API。仅用于将此官方产品文档站与既有参考项目关联；未跟随安装、源码或取数操作；不能证明网站契约对应本地固定快照 |
| S3 | `https://fuyao.aicubes.cn/docs/api-reference/corporate-actions/`；在线可变、未标版本 | 正文成功；“通用约定 / 请求参数 / 响应字段 / 字段约定差异”。端点描述为 `GET /api/a-share/corporate-actions/adjustment-factors`，单标的日期区间事件流；详细证据见第 3 节，未点在线调试 |
| S4 | `https://fuyao.aicubes.cn/docs/mcp/tools/get_a_share_corporate_actions_adjustment_factors/`；在线可变、未标版本 | 正文成功；“工具描述 / 参数 / 返回”。工具与 S3 同端点，返回仍为事件列表，不是独立交叉验证源；支持对 REST/MCP 文档一致性的有限核对 |
| S5 | `https://fuyao.aicubes.cn/docs/api-reference/market-dumps/`；在线可变、未标版本 | 正文成功；仅采纳“Parquet 文件结构 / 复权因子列”说明。`dump_id=a_share_adjustment_factors_event_none_all`，声明 FULL，主键 `(thscode,ex_date_ms)`；另列配股比例/价格和 CNY。未执行页面示例、未下载文件/Manifest；FULL 标签不证明真实范围或历史可用性 |
| S6 | `https://fuyao.aicubes.cn/docs/introduction/`；在线可变、未标版本 | 正文成功；“提供的数据”描述事件流和全市场导出。总览称显式 currency，但 S3 具体 item 表未列 currency；具体接口证据不能被总览替代 |
| X1 | `https://github.com/HiThink-Tech/Financial-API`；`https://raw.githubusercontent.com/HiThink-Tech/Financial-API/main/README.md` | web 直接打开返回 404；GitHub connector 读取固定 `2ec779c94e798ea941befb2d1c951c9420fdadd0/README.md` 也返回 404 / NOT_FOUND。只说明本次读取未成功，不能断言仓库删除；不以搜索缓存摘要证明当前字段合同 |

S1 固定 commit 和 Financial-API 的本地历史 commit 来自 L02；其 2026-08-28 快照核验不是本日远端 HEAD 核验。搜索只用于定位上述文档，第三方索引、搜索摘要、其他 Provider/交易所规则未作为字段或 PIT 证据；未扩大至全站文档合集。部分 `web.run` 调用没有返回可读正文，后续以返回正文的只读搜索连接器核对；无正文的调用不计证据成功。

<a id="d2"></a>
## 3. D2 真实来源证据矩阵

本地旧声明集中在 L04/L05；“AS”指 a_stock_data（S1），“FA”指 financial_api 对应产品文档（S2–S6）。同一格可同时包含“已确认文档语义”和“未确认生产契约”，二者不得合并为通过。

| 审核项 | 本地声明 | Provider 来源证据及状态 | 接入影响 / 缺失材料 |
| --- | --- | --- | --- |
| 字段及接口版本 | corporate_action、Raw/adapter/Mapping 均本地 1.0.0；AS 使用 action_id/ts_code 等，FA 使用 corporate_action_id/symbol/type/cash_per_share 等（L04） | AS：S1 只到能力概述，具体字段/接口版本**未确认**。FA：S3 的 thscode/ticker/item/ex_date_ms/dividend_per_share/per_share_bonus 文档字段**已确认**，与本地预期不同；对应 Raw1/版本**未确认** | 不能标记本地 Mapping 已适配。须两维护者提供固定版本字段字典、原始响应/元数据、版本变更及本地 adapter 目标版本对照；没有证据不填新版 Mapping |
| 现金单位与币种 | cash_amount 为 cny_per_share，currency 仅 CNY；转换乘数本地定义（L04） | AS：S1 宣称 per-share cash，具体币种/分母/转换未确认。FA：S3 每股原始货币，S5 导出币种 CNY **已确认于各自文档**；不能把 dump 字段补到 REST，REST 的明确币种字段未确认 | 区分 REST 与 dump 版本，保留原值/原币种/转换分母；须原币种、每股或每 10 股样本与对账，不能只据字段名默认 CNY |
| 税前现金与旧股分母 | 候选 D 为 gross cash / 一股事件前旧股（L06）；v1 未类型化税/基数 | AS：税前及旧股基数**未确认**。FA：S3/S5 明示税前**已确认**；旧股基数及多组件共用同一 pre-event 分母**未确认** | 税前“每股”不能证明同组共同旧股基数。需要含基数/除权顺序的方案级说明与真实现金、现金加送股样本；不得推导缺失分母 |
| BONUS 增量 | 候选 b 为新增股/旧股；旧 ratio 无细分（L06/L04） | AS：S1 宣称 bonus/transfer shares，但增量、单位和合并方式**未确认**。FA：S3 0.1 对应 10 送 1，普通送股增量解释**已确认**；转增是否并入、同组身份/旧股基数**未确认** | 可记录该数值说明，不可自动把所有 stock-dividend/转增或配股归为普通 BONUS。需送股、转增、现金加送转分量及重复组件反例 |
| SPLIT 总量 | 候选 s 为拆后总股/拆前股；不能当新增量（L06） | AS、FA：所审文档均无纯拆分字段/总量定义证据，**未确认**；S3 的 bonus 比例不证明 SPLIT | 不把 0.1 或 2 猜成 s；须纯拆分/并股类型与原始量纲、前后股本和精确接口版本；未补齐则不支持 |
| 经济身份与同组组件 | v1 PK=(corporate_action_id,revision)；候选 event_key/group/component/share_basis（L04/L06） | AS：**未确认**。FA：S3 不列稳定事件ID；S5 `(thscode,ex_date_ms)` 是 dump 主键**已确认**，但不能证明原经济事件、同日多个方案或组件唯一性 | 不从证券+日期臆造事件ID/分组顺序；须方案/组件ID映射、合并规则、共同基数和同日多个事件真实样本 |
| 修订、取消、迟到 | v1 revision/published_at；fixture 有 ACTIVE/CANCELLED 和全 revision 收据（L04/L08） | 两 Provider 在本次字段说明中均未给 revision/cancel 和版本可见性保证，**未确认** | 当前最新行可能抹平历史。须至少初版→更正→取消及其原载荷、源时间、采集时间/Hash；禁止默认 revision=1 或以删除代取消 |
| ex_date | v1 date；候选生效交易日，不能代替公告/支付日（L06） | AS：具体源字段/日界线**未确认**。FA：S3 ex_date_ms=Asia/Shanghai 零点毫秒戳，除权除息日文档语义**已确认** | 仍需真实样本核对到 Calendar/Identity 的映射及非交易日异常；不能直接当 UTC 日期或源可用时间 |
| published_at | v1 必填；派生中 source_published_at 与平台发布时钟分开（L04/L07） | AS：源时间含义**未确认**。FA：S3/S5 字段表没有事件披露时间，**未确认**，不是 ex_date_ms | 需要每次方案/修订公开时间及时区、公告关联和溯源。平台写文件时间不能补成源 published_at |
| available_at | AS as_of、FA available_at 本地映射；正式输入只接受 OBSERVED_INGESTION 根（L04/L07） | AS：as_of 字段及含义**未确认**。FA：所审事件字段未提供可用时刻，**未确认** | 须源可见时间与平台首次成功采集/Raw 持久化证据；保守 observed ingestion 只能从真实观察后使用，不得回填为历史 ex_date |
| 分页、终止与漏页 | Coverage 要所有 page Raw refs、end_marker、source_row_count、EXHAUSTIVE_SOURCE_MANIFEST（L07） | AS：分页规则**未确认**。FA：S3 参数仅单 thscode/from/to，文档未列游标/上限/终止；S5 声明 FULL，但实际 Manifest/文件未提供；“无分页保证”仍**未确认** | 不能以一次 item 数量/空数组确认结束。须固定版本页上限/截断/错误约定或不可截断完整导出保证、全页/文件 Hash 和终止/缺页反例 |
| 全类型发现与不支持类型 | coverage 必含 DIVIDEND/BONUS/SPLIT/RIGHTS/OTHER；Method v1 拒绝 RIGHTS/OTHER，不得过滤后当零事件（L07） | AS：全类型枚举**未确认**。FA：S3/S4 文字提配股但只给现金/送股字段且无 event_type；S5 另有配股字段。端点差异**已确认**，可靠全类型发现**未确认** | 必须说明 REST/dump 对配股、拆分、特殊事件和未知枚举的区分；缺类型不能靠两个数值为零判无行动；预计算复权价格作为本次原始行动证据**不适用** |
| 证券/区间覆盖与无行动 | 固定 universe/cutoff/base/anchor，四类 Snapshot 与 COMPLETE coverage；空引用不合法（L06/L07） | AS：范围/退市/无行动保证**未确认**。FA：S3 支持单标的区间、S5 宣称全 A 股历史是文档事实；真实目标证券清单、退市覆盖、区间端点、失败证券和合法零行证明**未确认** | 须每证券/区间完整性清单、零行动收据、错误/权限/截断区分；缺 Raw/coverage 不得产 factor=1；不得沿用旧空行 max_available_at=None 就认完整（L09） |
| 历史 PIT | 要固定截止时可得 revision，披露、可用、物化三种时间分离（L06/L07/L08） | 两 Provider均**未确认**历史版本可回放及截至当日可见性；S1 能力说明、S5 全历史事件和当前查询成功都不足 | 须带观察时钟的不可变历史响应/修订链、采集日志及 cutoff 前后对照；只有“如今知道的历史事件”不能认证历史 PIT，也不能因此认证 market 能力 |

**D2 判定：NO_GO（生产来源实施），不是所有字段都未知。** FA 可确认的税前、送股比例、除权日语义应保留；来源固定版本、旧股共同基数、完整身份/修订/时间与穷尽覆盖仍缺。a-stock-data 的仓库 README 能力声明不是本地统一事件模型的生产证据。两个源不得逐行静默拼合补齐（L05 的策略为整分区替换且冲突拒绝）。

<a id="gaps"></a>
## 4. D5/D6 接入差异：以已完成内容为起点

| 层次 | 现有实现事实 | 剩余最小差异 / 不能做的捷径 | 证据与新授权 |
| --- | --- | --- | --- |
| D5 公司行动注册/Mapping/质量 | corporate_action@1.0.0 的 ratio/cash 为泛化字段；Raw、Mapping 是本地契约。候选新版字段见原 PREP；FixtureAction 是独立私有输入（L04/L06/L08） | 候选新版**未注册**；需按 D2 确认后类型化税前旧股现金、BONUS增量/SPLIT总量、事件身份/分量/revision/cancel/时间、Source Evidence。旧 v1 不覆盖、不改 Hash；fixture 不能直接改名生产行 | Provider 版本和真实样本包先到；再单独授权 Dataset/Raw/Mapping/质量及所需生成器变更。本轮不确定尚无证据的真实字段 |
| D5 adjustment_factor 注册/行合同 | DerivedPartition 有 dataset_id=adjustment_factor、dataset_schema_version=1.0.0 的模型标签；fixture 行/结果已有（L07/L08） | 模型标签不是 DatasetDefinition；尚缺正式 Dataset/行 schema、精确字段/单位/唯一性/预期日期覆盖/正有限 Decimal 质量、结果规范与实际序列化 schema 对照。不往 corporate_action@1 塞 factor，不把 Method 当 Provider | 授权正式派生行/注册和质量；与实际计算规范对齐，并检验跨 Manifest 不覆写、漏日/重复/非正值拒绝。不新建平行 Provider 源 |
| D6 输入引用版本 | SnapshotInputRef 固定 manifest1，所有 partition.dataset_schema_version 必须1；真实引用核验只收 DataSnapshot/CanonicalPartition（L07） | 即使注册 corporate_action 新版也会被当前引用拒绝；不能放宽旧对象规则后悄悄重算旧 Hash。需另批明确版本派发/引用合同和旧新边界 | 新版来源合同确定后，授权版本化引用扩展；未知版本拒绝、旧样本载荷/Hash/固定引用不变 |
| D6 Catalog 精确版本 | ProviderRepository.get_dataset 已按 id+schema_version 读；内存投影/校验/Resolver仍以 id 单键，且 capability allowlist 未列 factor（L10） | 同名多版本会覆盖或选错；改标签不足。应精确 `(dataset_id,schema_version)` 查找，明确旧显式1.0.0兼容，不引入 latest。Catalog 共存不等于一个旧 Snapshot 可以混装两版本（L11） | 可先独立改无外部IO的查找/校验，见 N1；不注册新源/factor、不改变旧 Definition。未来 factor 能力绑定须另外明确，不用 corporate_actions_daily 冒充派生认证 |
| D6 实际执行与派生血缘 | calculate_fixture 从 bytes计算输入/结果语义Hash，收据绑定 Method、全revision选择、实际五文件Hash、runtime及materialized_at；verify_fixture_execution 重算（L08） | 正式 Lineage 无执行收据/实际结果绑定；validate_adjustment_references 仅内存元数据检查，不读文件（L07）。缺从真实固定文件→解码/行→运算→规范结果→持久字节的可验证桥接；不能把传入 Hash 声明当内容验证，也不把 FIXTURE_ONLY 改标签冒充生产收据 | 需新版本桥接授权和测试矩阵；语义Hash与Parquet/Manifest实际字节Hash分开，绑定 schema/序列化规范、执行闭包、P行、全revision选择与固定输入。复用算法，不重写公式 |
| D6 无行动与选择收据 | 离线算法保留每个 revision 的取消/范围外理由；正式 validate_adjustment_references 在非空源且无selected refs时拒绝（L07/L08） | **已确认兼容差异**：所有源行被取消/排除与真实零行不是同一种证据。需版本化桥接完整选择收据；不能删源行、伪造 source_row_count=0 或直接放宽旧Lineage。真零行还须覆盖及可靠 available_at，旧normalizer空行上界为None（L09） | 授权后用全取消、全范围外、部分选择、真零行、漏页/遗漏revision反例验收；旧契约保持拒绝，新契约仅凭完整可核验收据接受 |
| 物化/文件与控制面持久化 | DERIVED契约与parser已有；CanonicalRepository和SnapshotRepository读回旧模型，Publisher读回直接DataSnapshot.model_validate；Service/Repository中未发现新parser调用（L11） | 缺受控正式派生写入、原子文件/Manifest发布、Repository存取、重启水合、固定引用/完整Correction闭环。仅增加parser或写文件不等于接通生产；DDL需求须核对真实表后另提，不先猜迁移 | 独立授权受控临时存储及隔离DB验证；缺来源时只能显式合成/PROVISIONAL，真实DB和发布需再授权。覆盖失败回收、重启、同identity Correction/新cutoff新实例、旧字节和引用不可变 |
| Resolver / F1 / F2消费者 | 旧F1要求 corporate_action.factor且zip价格因子；F2 BLOCKED路径也要求此字段；市场发布门禁保持拒绝（L12） | factor注册或一个Catalog改动不解除消费者缺口。须新版本Definition/执行入口按证券+日期+固定Manifest对齐，检查同价基、lookback/warmup、缺日和长度，不改旧14 F1/65 F2完整载荷/Hash | 另批最窄消费者合同；使用固定派生快照、可核验执行/存储链并保持旧Golden兼容；未批准前不替换旧Definition、不解除市场Capability/Formal/Paper门禁 |

正式桥接的后续验收顺序仅描述 B3 必要边界，不是本轮实施计划：验证真实 Raw/Partition/Snapshot **实际字节和 schema** → 固定全输入/所有 revision 与 coverage → 保留已确定计算和选择收据 → 绑定规范结果Hash与真实存储字节Hash → 版本化 DERIVED lineage → 持久化读回/重启后再次核验。`source_published_at`、逻辑 `available_at` 与平台 `materialized_at/published_at` 不混用。迟到源在更晚 cutoff 产生新实例，不借 Correction 改写当时不可得信息；完整 Correction 需要同逻辑身份与前驱保护验证，现有字段结构检查不等于已完成链路。

<a id="next-scope"></a>
## 5. 下一最小范围、启动判定与授权

以下是互相隔离的候选，不捆绑成“整 WP 重做”。GO 表示本次权限内可做；CONDITIONAL_GO 表示条件满足后可启动、**不是当前已获代码授权**；NO_GO 表示关键生产证据未满足。

| 编号 / 范围 | 判定与前置证据 | 必须验证 / 所需授权与停止条件 |
| --- | --- | --- |
| N0 既有离线算法/契约 | **GO：作为已完成基线保留**；本 Goal 可完成证据文档，算法无需重新申请或重做 | 本轮只保护字节、引用历史验收；不能将“基线保留”解释为生产执行批准 |
| N1 **优先下一最小实施：精确版本 Catalog 查找与验证** | **CONDITIONAL_GO**；L10 已证明 Repository精确版本与Catalog单键差异，不依赖真实业务样本。只在既有DatasetDefinition投影、projection/definition校验、Resolver查找及直接调用方做必要兼容 | 需用户新授权实现及定向测试。以同名不同schema的**测试定义**验证共存、未知/歧义版本拒绝、投影防漂移、旧显式1.0.0查找和旧Definition/Hash/固定引用不变。不得注册生产@2或factor、扩capability、接Provider/DB、改Method/Lineage/算法或批量重写F1/F2；若必须突破这些边界，停下重新授权 |
| N2 执行收据到正式血缘的版本化桥接（与N1分开） | **CONDITIONAL_GO，仅可另授权隔离合同/合成验证**；需先明确输入引用版本和全取消/范围外/零行的兼容决策；不能照搬旧Lineage或伪造真实源 | 新授权须列明合同版本、修改/生成范围及旧版本保护；验证实际输入/输出篡改、错Method/源指纹/行集合/coverage/P/未来时间拒绝。只做收据绑定不包含持久化或生产认证；不重写已完成算法 |
| N3 真实新版公司行动与正式factor的注册/Mapping/质量接入 | **NO_GO（真实接入）**；先补第6节材料；factor行合同可与N2另行限定讨论，但不得以其替代D2 | 批准具体Provider/interface/Raw/Mapping/Dataset/quality版本及确定性脱敏回放测试后才实施；RIGHTS/OTHER发现后拒绝，未确认字段不填默认值 |
| N4 正式物化/持久化/Resolver消费者贯通 | **NO_GO（当前生产范围）**；须固定行/输入/桥接合同、质量和真实来源证据，独立资源授权 | 按第4节文件/DB/重启/Correction/消费证据单独验收；隔离合成环境只能证明技术链路。真实业务API、DB、部署/发布/认证不由N1/N2授权涵盖 |

N1 的价值是消除一个确定、独立的选错版本风险，不会让真实复权数据提前可用。生产仍受 D2 和其余 D5/D6 阻断；N1 通过也不关闭 B3。此处仅建议新授权范围，不创建分支、新 Goal、工单或执行代码修改。

<a id="requests"></a>
## 6. 缺失材料与责任边界

| 提供方 | 需要提供的可核验材料 | 最小安全访问 / 验收要求 |
| --- | --- | --- |
| 两 Provider 维护者 | 分别固定接口/文档版本或commit、Raw字段类型/单位/税/基数/空值/未知枚举；REST、MCP、dump对应关系；源级事件/组件ID、revision/cancel与发布语义；分页/截断/终止及覆盖保证 | 优先公开第一方固定文档或用户转交脱敏说明；不要求在对话粘贴Key。不能确认的能力明确标不支持/未知，不能推断性补齐 |
| 数据owner/采集负责人 | 经允许的原始响应及元数据包：纯现金、送股、转增、纯拆分、同组现金+送股、同日多方案、修订/取消/迟到、RIGHTS/OTHER、无行动证券/区间、分页缺页/截断/错误；附证券范围、请求参数、原值分母/币种和逐文件Hash | 保留脱敏前后校验说明和字段关联，去除token/身份信息；样本需足以区分“不适用”和“未知”，不以文档响应示例当真样本。没有某类样本时保留该类型NO_GO |
| 数据owner/历史归档负责人 | 至少跨cutoff的初版/修订/取消源披露与可见时间、真实首次观察/采集/入库时间及时区、不可变Raw内容/日志、导出Manifest与全页/证券覆盖/合法零行证据 | 必须可验证当时知道什么；今天下载的全历史不能重建过去的available_at。若仅有OBSERVED_INGESTION，明确最早可用时刻及历史不认证区间 |
| Visory维护者/用户 | 选定N1或N2的单独代码授权、准确写入路径、必要测试/生成器范围；接入时确认来源版本和冲突策略 | 后续如确需真实取数，另授只读API范围/证券区间/配额/脱敏输出；如需临时DB、Migration、发布或Git写入，分别授权。本轮不发外部消息、不访问账号、不产生费用 |

本 Goal 验收问题与生产阻塞分离：矩阵、来源定位、差异/判定、文档验证与保护未满足才是本 Goal 的 BLOCKER；D2样本/历史缺失和D5/D6链路则是**后续生产BLOCKER**，作为本轮FOLLOW-UP交接，不能为“完成Goal”而标已解决。没有新材料时到此停止检索，不反复改写原PREP。

<a id="local-evidence"></a>
## 7. 本地证据索引

以下绝对路径与行号基于本轮开工字节；L01–L12 均未修改。行号用于精确复查，不暗示代码测试已运行。

| ID | 绝对路径及行号 | 证明范围 |
| --- | --- | --- |
| L01 | `C:/Users/lzq11/.codex/worktrees/f468/Visory/docs/architecture/a-share-platform/WP-0303-IMPLEMENTATION.md:325-346,402-443,474-484` | 第一阶段契约/第二阶段离线算法已获批完成；生产注册、真实来源、物化/消费者缺口 |
| L02 | `C:/Users/lzq11/.codex/worktrees/f468/Visory/references/README.md:49-62`；`C:/Users/lzq11/.codex/worktrees/f468/Visory/references/manifest.yaml:59-137` | 两参考项目的固定历史快照身份，不作当前HEAD |
| L03 | `C:/Users/lzq11/.codex/worktrees/f468/Visory/docs/architecture/a-share-platform/reference-adoption-matrix.md:24-25,40-44` | 参考源码适用WP、禁止外部Schema直作Canonical、禁止逐行混源 |
| L04 | `C:/Users/lzq11/.codex/worktrees/f468/Visory/src/services/platform/extended_canonical.py:23-64,92-106` | corporate_action@1.0.0字段、单位、Raw字段、本地Mapping；无正式factor注册 |
| L05 | `C:/Users/lzq11/.codex/worktrees/f468/Visory/src/services/platform/provider_registry.py:197-204` | 能力UNVERIFIED/history_start=None；主补源、整分区替换和冲突拒绝 |
| L06 | `C:/Users/lzq11/.codex/worktrees/f468/Visory/docs/architecture/a-share-platform/WP-0303-B3-ADJUSTMENT-CONTRACT-PREP.md:84-106,163-209,268-273` | 候选新版、factor行、三时间/覆盖/Correction和D2/D5/D6，不代替最新阶段授权 |
| L07 | `C:/Users/lzq11/.codex/worktrees/f468/Visory/src/schemas/platform/adjustment.py:113-184,205-239,260-325,329-434,448-495` | 输入版本/根、覆盖/Lineage、DERIVED模型/parser、仅内存核验、非空源不得空选择 |
| L08 | `C:/Users/lzq11/.codex/worktrees/f468/Visory/src/schemas/platform/adjustment_calculation.py:83-105,145-181,208-307`；`C:/Users/lzq11/.codex/worktrees/f468/Visory/src/services/platform/adjustment_calculation.py:237-305` | 私有FIXTURE_ONLY与输入/选择/结果Hash、实际源码闭包/时钟/重算；不接生产链 |
| L09 | `C:/Users/lzq11/.codex/worktrees/f468/Visory/src/services/platform/canonical_normalization.py:390-399,464-498` | 旧日期顺序/非负/revision检查、质量报告与空行available_at上界；不能当新版完整事件质量 |
| L10 | `C:/Users/lzq11/.codex/worktrees/f468/Visory/src/repositories/platform/provider.py:174-186`；`C:/Users/lzq11/.codex/worktrees/f468/Visory/src/services/platform/feature_dependency.py:31-79,255-282` | 持久化查询复合键 vs Catalog/校验/Resolver单键、能力投影限制 |
| L11 | `C:/Users/lzq11/.codex/worktrees/f468/Visory/src/repositories/platform/canonical.py:69-102`；`C:/Users/lzq11/.codex/worktrees/f468/Visory/src/repositories/platform/snapshot.py:147-174,224`；`C:/Users/lzq11/.codex/worktrees/f468/Visory/src/services/platform/snapshot.py:64-102,918-937,1069-1078` | 旧类型读回/Publisher/消费加载及同Snapshot版本冲突；对services/platform与repositories/platform搜索新parser/引用核验符号无命中（rg退出1），不是全仓“永远无实现”断言 |
| L12 | `C:/Users/lzq11/.codex/worktrees/f468/Visory/src/services/platform/indicator_registry.py:56-65,282-293`；`C:/Users/lzq11/.codex/worktrees/f468/Visory/src/services/platform/market_sentiment.py:513-519,610-634,1020-1054` | 旧F1/F2 factor引用、zip与BLOCKED/fixture传播和市场发布/消费门禁 |

<a id="validation"></a>
## 8. 本轮验证与兼容回滚

Docs only，代码测试未运行；已执行的文档检查见命令与结果。

下列命令的执行目录均为 `C:/Users/lzq11/.codex/worktrees/f468/Visory`。实际 Python 为 `C:/Users/lzq11/AppData/Local/Programs/Python/Python312/python.exe`（3.12.9）。原始退出码、stdout/stderr 和时间分别保存在上述仓库外目录的 `validation-preliminary.json`、`validation-final.json`；保护结果见 `protection-verification.json`，本轮增量见 `goal-docs.patch`。

| 实际执行命令 | 退出码 / 结果 | 验证范围与限制 |
| --- | --- | --- |
| `python scripts/check_ai_assets.py` | 0，`[ai-assets] OK` | AI协作资产检查，不代表运行代码测试 |
| `python scripts/check_visory_baseline.py` | 0；651个相对链接、0损坏、0 imported_secrets | 8个运行路径、10个参考项目、0 tracked_external_reference_files、2项许可证通知、1个激活workflow；仅脚本定义的基线检查，不代表全仓安全认证 |
| `git diff --check` | 0，无空白错误 | 保留Git对10个既有工作文件的LF→CRLF提示，本轮未转换它们原有字节；该命令不覆盖未跟踪新文档，另做下列独立检查 |

本轮使用仓库外标准库辅助脚本执行上述命令并核验保护，实际命令如下（两者退出码均为0，不是产品代码测试）：

```powershell
python "C:\Users\lzq11\AppData\Local\Temp\Visory-WP0303-B3-source-evidence-20261009-676b9e9a\run_doc_checks.py" "C:\Users\lzq11\AppData\Local\Temp\Visory-WP0303-B3-source-evidence-20261009-676b9e9a" final
python "C:\Users\lzq11\AppData\Local\Temp\Visory-WP0303-B3-source-evidence-20261009-676b9e9a\verify_docs.py" "C:\Users\lzq11\AppData\Local\Temp\Visory-WP0303-B3-source-evidence-20261009-676b9e9a"
```

- **范围与字节保护通过**：1560个开工已有文件中1557个逐字节未变；原48项成果中45项逐字节未变，其余3份授权文档移除本轮插入后精确等于开工原字节。只新增本PREP，最终dirty为49项；HEAD、缓存origin/main、分支状态和index不变。原PREP、实现记录、代码、测试、Golden、契约、Migration及参考源码未修改。
- **新增文档独立检查通过**：UTF-8无BOM、LF、无行尾空白/冲突标记、单EOF换行；检查本轮6个相对链接及锚点、18个绝对证据位置及全部行范围。人工核对14项D2覆盖、D5/D6分层与N0–N4判定，三个入口仅插入当前摘要/链接。
- **状态检查通过**：45个WP无重复，`VERIFIED=15 / IN_PROGRESS=2 / NOT_STARTED=28 / RELEASED=0`，与开工一致；WP-0303仍IN_PROGRESS，验收15/45；Unreleased保持扁平。两市场missing、Formal/Paper拒绝及生产未认证状态未放宽。
- **保留失败与解释**：开工`ls-remote`退出128，实时远端仍未确认；L11的`rg`退出1表示指定目录无符号匹配，不是测试失败。辅助PowerShell定点读取曾因`$p:`插值出现ParserError/退出1，改为`${p}:`后读取成功，未写仓库；公开读取的404/空正文限制见X1及第2.1节。收尾写入前原始字节断言发现新增PREP初稿末尾1处CRLF，辅助脚本退出1且未写仓库；首轮文本检查有换行规范化盲点，已改为原始字节检查，并仅将本轮新文件末尾改为LF，三个原文档不转换。

未运行 pytest、全量 gate、客户端构建、数据库测试、在线业务API或生成契约导出，不安装/升级依赖。历史89/79/458不计入本轮结果。本轮无英文对应专题页，未新增/修改英文页面；原中文PREP/实现记录保留，中文索引、状态与CHANGELOG仅同步当前结论。

只有文档增量，无运行行为、公共API、Schema、旧Method/Definition/Golden/固定引用或数据库变化。回滚时以仓库外 `goal-docs.patch` 的**本轮hunk**为边界：先核对当前字节与 `final-hashes.json`，对三个原文档只反向移除本轮插入；新增文件仅在确认没有后续编辑/引用后撤销本轮内容并处理引用。有后续改动时手工合并反向hunk，不能整文件恢复开工副本/HEAD、不能删除原有untracked成果。本轮未执行回滚、commit/tag/push/PR/merge/数据库/部署/发布。

<a id="github-sample-admission"></a>
## 9. 2026-10-14 GitHub 历史数值样本的输入门禁复核

本节是 FULL-INPUT-TO-FEATURE-CLOSEOUT 的新来源证据，不追溯修改第 3 节两个既有 Provider 的语义结论。用户已授权公开 GitHub 搜索/下载及继续本 Goal；尚未授权真实 Provider 业务 API、生产数据库、真实 `/data` 或任何远端写入。

样本目录为 `E:\Personal Manager\参考项目\WP0303-GITHUB-DATA-20261014-093239`。本次独立重读该目录的 `download-manifest-final.json` 和全部 19 个源文件，重新校验实际 SHA256、Git blob 身份、8 个 CSV 的完整行集合、列数和证券/日期重复键；共 18,616 原始行，含重复和未认证行。原文件未去重、填值或转换为 Canonical。固定提交只证明仓库版本和本次取得的字节，不证明数据所有权、源接口版本或历史首次可见时间。

| 证据 ID / 固定仓库提交 | 实际文件及本次复核事实 | 本 WP 用途和拒绝原因 |
| --- | --- | --- |
| G1：AkatsukiYamisora/stock-prediction-with-DL，`2a37e5085d1f8cb00ebc338a0eea9e7700757acd` | `data/train_data/sh.600000.csv`，975 行，2015-01-05～2018-12-28；含 `circ_mv/float_share/free_share`；32 行这些资本字段为 0。`data_downloader.py:92-111` 拼接 Baostock 日线与 Tushare daily_basic，存在空白转缺失及 `fillna(0)` | B1/B2 历史数值候选；缺失填零、单位/股本口径、同价基、全市场覆盖及 PIT 未认证。不能用 `total_mv` 替代 `circ_mv`，不能向旧 security_master 注入股本 |
| G1 基准/名单 | `data/stocks/sh.000300.csv`，586 行，2019-01-02～2021-06-02，收盘正数、日期键无重复；`data/hs300_stocks.csv` 为 2021-05-31 的 300 代码名单 | B4 基准候选及成分名单案例；基准与上述浦发训练文件共同日期为 0，不能直接组合。同日历/PRICE 身份/源可用时钟未证明，当前成分名单不替代全 A 历史冻结池 |
| G2：AskyJx/xDeepLearningBook，`14fa9583875f929a4537f4ce272ce695d3b8e1da` | `data/沪深300历史数据.csv`，无表头，3442 行，2005-01-04～2019-03-05；完整保留首行和尾空列 | B4 长历史数值候选；README 的“原始数据”描述不证明原始采集归档，第 3～5 列正式语义、价格口径、完整日历和 PIT 不凭数值推定 |
| G3：ZJU-OmniAI/Data-Copilot，`31ecd6a433d4d773f6ce637aa8695da61c8ca7b6` | `data/tushare_stock_basic_20230421210721.csv`，5163 个代码；缺 `list_status/delist_date/available_at`；4 个 `list_date` 晚于文件名所指 2023-04-21 | 历史名单候选；不能判定这些是事先公告待上市项还是后补内容，也不能把文件名当观察时钟。无法证明上市/退市/更名/ST 的历史完整身份 |
| G4：elsejj/mcp-cn-a-stock，`176edb130e49e9c403b189cd1c89d73a465ecc2e` | `db/sample/stock_dividend.csv`，比亚迪 36 行/12 个 `obj+ts` 键，每键重复 3 次；2014-08-13～2026-07-31。数据库字段为 `dividend/transfer_shares/right_price/right_shares` | B3 具体数值案例；税、每股/每十股、共同旧股基数、`ts` 语义/时区、事件/组件身份、revision/cancel、全类型发现及无行动覆盖未证明。配股字段全 0 不证明不存在配股 |
| G4 股本 | `db/sample/stock_shares.csv`，114 行/38 个日期键，每键重复 3 次；2011-06-08～2025-12-31；含总股本和可交易 A/B/H 股本 | B2 股本结构案例；总可交易股本不能当 A 股分母；记录日期不自动等于生效日期，仍缺股本变更披露/观察/可用时钟和来源单位 |
| G4 价格 | `db/sample/stock_kline_1d.csv`，8000 行/2014 个日期键；2000 个键重复。2026-08-18 同键 `close=89.33/89.53`，成交量/额也不同；没有 revision 或采集时间字段 | B3 价格对照及冲突拒绝案例；同键冲突不是已认证 Provider Correction，不能任选、按位置截短或无依据去重。价格基准 P、前 session、完整交易日和复权口径未证明 |

三份 G4 CSV 无表头；列位置仅按同提交 `db/sql/create.sql:57-78` 和导出脚本检查，未据此创建正式 Mapping 或默认单位/时区。参考项目脚本未执行。G1 仓库声明 GPL-3.0，G2/G3 声明 MIT；G4 根目录未见 LICENSE，公开元数据未识别许可证。代码许可证不自动证明第三方行情数据的再利用权，各 CSV 的生产数据授权仍未确认。

当前第一方字典的补充证据：2026-10-14 读取 Tushare `daily_basic` 官方静态文档（`document/2?doc_id=32`），未调用业务 API 或使用凭据。当前字典明确 `circ_mv/total_mv` 为万元，`float_share/free_share/total_share` 为万股；`turnover_rate` 为百分数、成交量除以无限售流通股数，`turnover_rate_f` 为百分数、成交量除以自由流通股数。实际 HTML 38,380 字节、SHA256=`1ac4efa02e9c9ec0d055d056a0388d7fb6b4f78e8b961188a7db41b2251d2c19`，原始字节及获取时钟绑定在本次仓库外 `provider-current-documentation.json`。这只部分确认当前接口的字段语义；文档未固定历史接口版本，不能证明 G1 的 2015–2018 CSV 使用相同单位/映射或历史 PIT。G1 的 `turn` 来自 Baostock，不能借 Tushare 换手率解释；G4 未证明是 Tushare 来源，也不能借用这些单位放行。

首封检索的否定范围也固定：`LowellLee/kpl@f6338a0aa0c0743c0a4f696f75bec452ccbff647`、`stock-programmer/limit-up-review@0d1606d55bd8ee2181400e2d7a1bb20211ceb8a8`、`zamhown/limit-up-stock-crawler@3887d58236ddb2a2bbee59ac319d7a2dadb056ea` 的完整树中未取得所检索数据后缀的历史归档。其他命中为采集代码/字段说明；这不表示全 GitHub 不存在相关数据，也不以截图或字段名代替首封事件包。

### 9.1 具体待决语义与最小证据

| 项目 | 必须明确的决策问题 | 通过 gate 前的最小材料 |
| --- | --- | --- |
| B1 | 采用 A 股可流通市值还是自由流通调整市值？币种、单位、同价格基准和历史版本如何绑定？ | 固定版本字段字典、未填零的原始记录、对应历史股本/身份和覆盖 Manifest、跨 cutoff 可用/修订记录；不自行批准股本乘价格替代 |
| B2 | 换手率分母对应哪类 A 股可交易/流通股本？股本记录日期是生效、披露还是期末？ | 单位及分母说明、股本变更前后原载荷、经济生效/披露/首次观察/available_at 和 A/H 区分，完整 revision 与身份/日历范围 |
| B3 | G4 的现金和送转数值单位是什么？是否税前、共用事件前旧股基数？时间戳和同日组件如何识别？ | 同固定源版本的方案/组件字典、稳定 event/revision/cancel、全类型/分页终止/零行动收据、实际前 session P 及同价基、历史双时间归档 |
| B4 基准 | 代码和无表头列能否正式映射至 `index:cn:000300.SH/PRICE`？完整日历和观察时钟是什么？ | 基准身份/列字典、完整原始日线及日历/源可用证据、同证券/日期对齐清单；不临时换基准或提高旧 Definition 状态 |
| B4 首封/股票池 | 事件时间和首次可用时间能否独立证明？历史名单是否包含退市和状态变化？ | 首封原始事件及时区/覆盖/修订证据；历史证券身份、上市退市/ST/停牌记录及固定逐日 scope，而非当前名单回填 |

### 9.2 本次门禁结果与既有成果

**8 个 CSV 全部 NO_GO（正式输入），B1—B4 没有因此整体关闭。** 每个文件的实际获取时钟保留在下载 Manifest；`historical_first_observed_at/historical_available_at=null`。不能把本次取得历史数值的时刻回填为历史交易日，也不能把上传变化、重复导出或合成输入变化认证为来源修订。

实际默认 Catalog 仍为 8 个正式 Dataset；旧 `turnover_ratio/return_point_in_time_adjusted/trading_halt_state@1.0.0` 均继续报 `INDICATOR_UNREGISTERED_INPUT`。既有停牌 2.0.0 显式引用子项保留；原始 F2 仍为 EXECUTABLE=16 / BLOCKED=18 / FIXTURE_ONLY=3，另外 28 个为 DERIVED，合计 65。EXECUTABLE 不代表历史生产认证。

本次独立门禁证据：`C:\Users\lzq11\AppData\Local\Temp\Visory-WP0303-INPUT-RESUME-20261014-100626\source-admission-current.json`，同时保存下载 Manifest 的实际 Hash、源文件 Hash、完整行集合检查、旧 F1 拒绝及旧 14 F1/65 F2 完整 payload Hash 基线。这里只复核证据，不建立运行时 Source Registry、生产 Dataset/Mapping/质量旁路或 fixture 改标签桥接。当前本地技术回归及完整 Goal 验收见[实现记录第 15 节](WP-0303-IMPLEMENTATION.md#github-input-resume)；WP-0303=IN_PROGRESS，15/45，market_breadth/market_emotion=missing，Formal 拒绝，NOT CERTIFIED、RELEASED=false。

<a id="github-new-source-search"></a>
## 10. 2026-10-14 第二批 GitHub 检索：新案例与实际数值核验

用户明确授权继续通过 GitHub 查找资料。本轮新检索 7 个仓库，递归树均 `truncated=false`，合计 2,101 个文件条目；五批 20 条定向网页查询还覆盖股本观察时间、公司行动更正/取消、原公告编号/Hash 和首封归档。这里只对已检查的树和文件作结论，不声称整个 GitHub 没有历史 PIT 资料。

独立参考目录为 `E:\Personal Manager\参考项目\WP0303-GITHUB-EVIDENCE-20261014-121647`，不是完整 clone。实际下载 **154 个固定版本文件、18,969,958 bytes**，逐文件验证大小、Git blob SHA1 与 SHA256，0 下载失败、0 LFS pointer；没有运行参考代码、安装依赖或调用 Provider 业务 API。`download-manifest.json`、`download-ext-manifest.json`、`download-supplement-manifest.json` 记录全部绝对路径、来源 URL、固定 commit/tree/blob、获取时钟和实际字节 Hash。Metadata 与本轮审计产物另存，不计入 154 个来源文件。

### 10.1 新来源、获取结果与采用边界

| 来源及固定 commit | 实际取得材料 | 能支持的参考 / 正式输入缺口 |
| --- | --- | --- |
| [rootSunc/CNEquity](https://github.com/rootSunc/CNEquity/tree/c118038ea82b5bb78783c0c17a1d9251b36de71d) `c118038ea82b5bb78783c0c17a1d9251b36de71d` | 30 个契约、来源、PIT、股本/市值/行动 adapter、质量和测试文件；Apache-2.0 代码 | 区分源发布时间/观察时间/可用时间、估算市值与供应商报告值，以及每股/每十股转换。README:227 明确不附带数据湖；不能把接口/测试或代码许可当作真实历史输入与行情再利用权 |
| [injoyai/tdx](https://github.com/injoyai/tdx/tree/2a9000681f5a9896ea98e4de8bc4904f1dce78ba) `2a9000681f5a9896ea98e4de8bc4904f1dce78ba` | 6 个源码、GBBQ 说明和测试文件；MIT 代码 | 作者定义的 category=1 分红/送配为每十股，其他 category 的四字段含义不同；未取得实际 GBBQ 历史归档、源版本、全类型/零行动覆盖或 revision/观察日志 |
| [JunyaoHwang/LUEIG](https://github.com/JunyaoHwang/LUEIG/tree/673f0b30548097283cdfac0d4c51ee6562cad13a) `673f0b30548097283cdfac0d4c51ee6562cad13a` | README、处理代码和 2 个 CSV，共 4 个文件；树中未见 LICENSE | 确有涨停历史数值及封板字段案例，但取的是昨日涨停池，不是全市场当日首封/触板归档；没有历史采集时钟、终止/完整覆盖收据 |
| [que3sui/A_stock](https://github.com/que3sui/A_stock/tree/68976b0cbc830d8abd0338c0771ba77e1ca69937) `68976b0cbc830d8abd0338c0771ba77e1ca69937` | 6 个字典/代码/.gitignore 文件；树中未见 LICENSE | `DATA_README.md:117` 分开 float_share/free_share；`.gitignore:1` 明示 daily/metric/basic.csv/trade_cal.csv 在外部云盘、不入仓库，所查树没有这些原始文件。近似中证800筛选也不是既定全 A 冻结 scope |
| [wangtlover/quant-data](https://github.com/wangtlover/quant-data/tree/68958d2ccbb63e5d8201899ce0fe96e76394e454) `68958d2ccbb63e5d8201899ce0fe96e76394e454` | README 及全 50 只 A 股的 50 raw + 50 ext CSV，共 101 个文件 | 有历史价格、股本、市值、换手率和因子数值；README 明确研究样本、非全市场、禁止商业用途。实际身份/分母/日期不一致，见 10.2；未给 Provider/interface、观察/修订或历史股票池证据 |
| [zensu357/KPL-post](https://github.com/zensu357/KPL-post/tree/f44b609f92b2bf91da51aeebca6c50372911ddb4) `f44b609f92b2bf91da51aeebca6c50372911ddb4` | 4 个脱敏文档/Postman 文件；树中未见 LICENSE | 两集合分别有 66/56 个请求，**保存响应数均为 0**。可参考请求结构，不能当历史返回数据；文档限定研究用途，未发送任何集合中的请求 |
| [2131614483/free-data](https://github.com/2131614483/free-data/tree/c63cb15a9d3f71f0af45739cb8fc0802f56aeeec) `c63cb15a9d3f71f0af45739cb8fc0802f56aeeec` | README、LICENSE、数据清单，共 3 个文件；MIT 代码 | README:23 明确约 5GB CSMAR 库只在作者本机、不随仓库发布；所查树无 CSV/数据库。数据清单不是可读的原始输入，代码许可不授予 CSMAR 数据权利 |

### 10.2 实际完整行集合、身份与分母反例

本轮 102 个 CSV 共 **208,612 行**，没有用 zip 截断、删除断言、填零或重写样本：

- quant-data raw 为 **103,735 行**、ext 为 **103,751 行**，日期 2016-06-13～2026-06-11；两侧重复键均为 0。仅按 code/date 作**诊断配对**的 103,735 行全部出现 raw `country=CN`、ext `country=US`，不能视为合法 Canonical 证券身份，也不自动改标签。
- ext 多出 **16 个日期键**：603986 为 1，603993/688008/688012/688041/688072 各 3；完整键清单在 `source-admission-new.json`。没有授权交易日历/停牌记录，不能擅自解释为有效停牌行或舍弃。
- 按该仓库声明的成交量“股”、股本“亿股”和换手率“小数”，103,735 个可比较值均与 `volume / (total_shares × 1e8)` 数值一致（相对容差 1e-7，绝对下限 1e-10）；其中 **90,628 行只匹配总股本、不匹配流通股本**。例如 000063 / 2016-06-13：实际换手率 `0.0072847341487917066`，按总股本为 `0.007284734148791706959…`，按流通股本为 `0.008928494865664776977…`。这是样本数值反例，不据此替 Provider 定义口径；B2 所需分母仍未证明。
- ULSPD 为 **1,111 行、659 个代码、19 个日期**，2025-11-25～2025-12-19，代码/日期重复 0；实际列为“昨日封板时间”。`processing/processing.py:61` 调用 `stock_zt_pool_previous_em`，`:217` 基于该昨日字段生成强度。`baseline.csv` 的 **15 行**是“昨日涨停表现指数”，不是固定 `000300.SH/PRICE` 的指数 OHLC。

上述历史数值都缺不可变原始采集/修订包，`historical_first_observed_at/historical_available_at` 未被补出。Git 时间只定位仓库版本，本次 download `fetched_at` 只定位当前资料获取时间。

### 10.3 可采用的契约参考与具体决策问题

| 项目 | 新证据与边界 | 当前正式决策 |
| --- | --- | --- |
| B1 | CNEquity `domain/valuation.py:13` 区分 vendor_reported、换手率反推股本、上一年末总股本估算；`sources.md:266` 承认历史 Baostock 市值估算。quant-data 有 float_market_cap 数值但身份/覆盖/PIT 未闭合 | 继续 NO_GO；由来源 owner 确认普通无限售流通 A 股还是自由流通口径、当日价格基准及真正原始记录。不采用反推流通股、VWAP 市值、年末总股本估算或总市值替代 |
| B2 | CNEquity `sources.md:284` 用 change_date/announce_date 分离股本变动与披露；quant-data 数值按总股本而非所需流通分母匹配 | 继续 NO_GO；须明确 A/B/H、限售/自由流通与有效日期、迟到公告和观察时间。既有 security_master 不补虚构 shares_outstanding；不由换手率倒推所需历史股本 |
| B3 | CNEquity `schema.md:567` 声明税前每股，`:579` 描述源每十股转换；TDX 文档的仿射价格与本 WP 已固定 Method 不同，不能复制替换算法。其公司行动主键/测试也不能证明本 WP 需要的经济事件/组件/revision/cancel闭包 | 继续 NO_GO；来源原字段、共同旧股基数和类型/身份仍须实际材料证实。RIGHTS/OTHER 与未知行动继续拒绝，不采纳外部缺值补 1/补 0 或分类过滤 |
| B4 | 新找到昨日封板时钟及昨日涨停表现指数案例；Postman 只有请求。均未证明当日全触板 scope 或固定基准 PRICE 合同 | 首封和两基准指标继续 FIXTURE_ONLY；旧 F1 残余按版本门禁拒绝。保留既有停牌 2.0.0 子项，不修改旧 Definition/Hash |

发现一个可追索的金额对账索引：CNEquity `adapters/cninfo/reviewed_cash_corrections.py:12` 绑定 **688320.SH / 2024-06-14 / 公告号 1220289873**、PDF SHA256 `06fa22c5ffc2fee854cb2b88fc827395f6834a15055a1d43857b3293d0b86bc0` 及 old_cash/issuer_cash 条件。仓库未提供原 PDF、原始初版响应或观察日志；这是第三方代码中的窄范围对账声明，**不是已取得发行人原文或源 revision 认证**。定向搜索公告号/Hash也未返回可用归档，不能自动把金额差解释为发行人修订。另一个 `cninfo_announcements.json` 使用 `A1`、`/a1.pdf` 与 expected 行，是测试 fixture，不提升为真实材料。

### 10.4 下一步最小材料与本轮停点

| 材料包 | 最小内容 / 验收作用 |
| --- | --- |
| `source-contract.json` + 固定字典 | 来源/接口/文档版本、原字段类型/单位/币种/税、流通与自由流通分母、空值/未知类型、稳定证券/事件/组件身份、页上限/终止、revision/cancel 与许可；各源独立提供，不拼合臆造 |
| `raw/` + `observation-log.jsonl` + `revision-chain.jsonl` | 保留真实脱敏响应和逐文件Hash、请求范围/页/错误、每次源发布时间/首次观察/成功持久化时钟及时区；至少有同事件初版→更正/取消跨 cutoff 对照，及纯现金、送转、组合、未知/不支持类型和合法零行动案例。样例只校准语义，不认证全历史 |
| `coverage-manifest.json` + 冻结池/日历/历史状态 | 对目标证券×交易日/行动区间枚举预期集合、全页/终止、退市/停牌/ST/上市状态、缺页/失败/合法零行；对整个申请认证区间验收，不以 50 样本或涨停子池证明全市场。可用历史须覆盖各 Definition 的 lookback/warmup，标准化最少 60 个 T-1 有效观察，不能只提交几天样例放行五维 |
| B4 单独原始归档 | 固定 `000300.SH/PRICE` 的指数单位/身份/日历/收盘与前收/可用时间；当日首封真实时区、证券/触板事件、收盘状态、完整触板分母和分页/零行/观察证据；不使用昨日封板时间、昨日涨停指数或 OHLC 推断 |

**本轮关闭的是资料发现与拒绝依据的核验，不是 B1—B4 正式输入。** 7 个候选包均未获正式放行，没有追加 Dataset/Raw Schema/Mapping/质量/Definition、正式派生或消费者代码。实际链路停在“固定 GitHub 文件 → 字节/完整行/数值/覆盖/PIT 门禁”，尚未进入合法 Raw/Canonical/Snapshot。当前执行、验收及本轮增量回滚见[实现记录第 16 节](WP-0303-IMPLEMENTATION.md#github-new-source-resume)；此前 19 个源文件/8 CSV 和全部 B5/N1/N2 成果保留。

<a id="issuer-static-correction-evidence"></a>
## 11. 2026-10-14 由固定 GitHub 索引追溯发行人初版/更正版

本轮沿第 10.3 节固定 GitHub 索引取得两份发行人静态 PDF。资料目录为 `E:\Personal Manager\参考项目\WP0303-ISSUER-EVIDENCE-20261014-125938`；公开静态文件只作来源证据，未访问 Provider 业务 API、生产数据库或真实 `/data`，未执行参考项目代码。第 10 节“只有代码索引、未取得原 PDF”是上一轮结论，本轮新取得的事实以本节为准。

### 11.1 实际字节、日期和事件关系

| 文件 / 原文日期与身份 | 来源 URL、字节数与 SHA256 | 内容和证明边界 |
| --- | --- | --- |
| `cninfo-original-1220289873.pdf`；发行人落款 2024-06-07，证券 688320，公告 `2024-040` | `https://static.cninfo.com.cn/finalpage/2024-06-07/1220289873.PDF`；610,241 bytes；`06fa22c5ffc2fee854cb2b88fc827395f6834a15055a1d43857b3293d0b86bc0` | 5 页；第 1 页税前每股现金红利 0.11 元，第 2 页参与股数/计算基数及虚拟红利 0.10953 元，第 3–4 页税口径和日期。实际 Hash 与 GitHub 索引精确一致 |
| `cninfo-corrected-1220299514.pdf`；发行人落款 2024-06-08，证券 688320，公告 `2024-041` | `https://static.cninfo.com.cn/finalpage/2024-06-08/1220299514.PDF`；612,118 bytes；`83810793588a526467d8925e75a6d9cd7e770b55e376053bb31c9c9529f0ca2f` | 5 页；标题明确“更正版”；税前实际每股现金红利 0.11038 元；同一年度/股东大会、证券和登记/除息/支付日期，支持一个发行人更正案例。没有 Provider 机器可读 supersedes/revision/cancel 包 |

这两份公告的股权登记日均为 **2024-06-13**，除权（息）日与现金发放日均为 **2024-06-14**。日期是原文的事件日期，不能当作 Provider 观察或成功持久化时钟。更正版第 2 页明确：总股本 151,013,668 股扣除回购账户 651,191 股，参与分配为 150,362,477 股；按维持的总现金 16,596,764.36 元重新计算，实际税前现金为 **0.11038 元/参与分配旧股**。它另给除息参考价所用的**虚拟红利 0.10990 元/总股本股**，流通股份变动比例为 0。0.11（原方案/初版）、0.11038（更正版实际税前派息）、0.10990（更正版虚拟红利）和 0.09934（部分持有人税后示例）不能合并成一个无基数说明的 cash_amount。

本轮取得的是初版与标题标明的更正版；未取得第三份单独“更正说明”或取消公告。原文可以支持这一个事件的语义和版本关系，不能推广为全市场的事件身份规则、覆盖或修订完整性。

### 11.2 固定参考代码的拒绝反例与本 WP 决策

`rootSunc/CNEquity@c118038ea82b5bb78783c0c17a1d9251b36de71d` 的 `adapters/cninfo/reviewed_cash_corrections.py:12-17` 绑定初版公告号 `1220289873` 和初版 Hash，以 `old_cash=0.11038000583648681`、`issuer_cash=0.11` 为窄修正条件。`payment_notices.py:665-706` 在该谓词获准且候选唯一时可将现金写成选中公告的值。只读核验显示：该条规则能匹配一个已被次日更正版更新的旧原文，因而**不能在未证明版本选择的情况下用它把更正版金额修回 0.11**。这不是对参考项目实际运行结果的断言，也不代表其所有调用路径一定选错；本轮未执行外部代码/请求或检查其真实数据湖。

本 WP 的差异化分红语义仍须明确：`cash_amount` 绑定参与分配旧股还是除息虚拟基数，如何保留两者及回购排除，是否需要新 Method 版本。现有固定 Method 不擅自替换。不能在缺 P、缺共同基数契约及历史版本选择证据时选一个接近数值去算因子，不能把这条公告中的参与分配股本借作 B1 流通市值或 B2 换手率分母。

### 11.3 门禁结论与剩余最小材料

**B3 新增一个发行人原文/更正样本，正式输入仍 NO_GO。** 当前取得时钟和 HTTP 文件 Hash 只证明本次取得的静态内容；历史 `first_observed_at/available_at` 保持未知，不从 URL 日期、PDF 元数据、HTTP Last-Modified、Git 时间或落款回填。

尚需同固定 Provider/interface 版本的 Raw 响应和事件/组件契约、原版→更正/取消的机器可读链、真实历史观察/持久化日志、全类型/全页/终止及合法零行动覆盖 Manifest、冻结证券/日历/历史状态、实际前一 session P 和同一价格基准。两份 PDF 不解除这些门禁，也不证明修订已传播至 FeatureBundle。本次两个 SSE 静态镜像返回反爬 HTML，未绕过验证或当 PDF/修订材料使用。

B1/B2/B4 及第 10.4 节其余最小材料仍缺。没有追加正式 Dataset/Mapping/质量/Definition，也没有更改 N2 fixture 标签。实际路径是“固定 GitHub 索引 → 公开静态初版/更正版 → 实际字节/原文语义核验 → **正式来源 gate 拒绝**”；正式 Raw/Canonical/Snapshot → DERIVED → F1/F2 → FeatureBundle/真实 Correction 尚未启动。执行与回滚见[实现记录第 17 节](WP-0303-IMPLEMENTATION.md#issuer-static-evidence-resume)。
<a id="public-history-coverage-evidence"></a>
## 12. 2026-10-14 新公开历史包、股本更正与覆盖核验

本轮增量归档为 `E:\Personal Manager\参考项目\WP0303-PUBLIC-HISTORY-20261014-150613`。9 个新候选仓库的完整 Git 树共 25,055 个 blob 条目，均未截断；另两次仓库元数据访问失败不证明仓库不存在。选中并下载 201 个固定版本来源文件，原始下载共 26,336,554 bytes，全部核验 Git blob/声明大小/SHA256；1 个源码文件的公开硬编码凭证样式字面量已脱敏，原始敏感字节不保留，源 Hash 与本地脱敏 Hash 分开记录。另取得 3 份官方 PDF，共 780,575 bytes、2 个独立内容版本。权威索引为资料目录中的 `download-final-manifest.json`、`redaction-manifest.json`、`public-document-and-run-manifest.json`、`source-admission-audit.json`、`pdf-semantic-audit.json` 与 `RESEARCH-REPORT.md`。

### 12.1 固定版本与实际历史数据

| 来源 / 固定 HEAD | 本轮取得与核验 | 正式输入门禁 |
| --- | --- | --- |
| `Jiu-7131/BigDataVisualization@102c67acda5151545d54444199140bd869c49004` | 完整树中的 daily/daily_basic/adj_factor 各 5,463 文件；只下载 9 证券的三个完整系列，共 25,918 行，及 master/日历/两个指数。8,636 个行情×basic 同键配对，在所声明 Tushare 单位假设下，流通/自由流通换手率和流通市值的数值关系全部匹配舍入边界 | **NO_GO**；数值一致不证明 Provider 字段/单位契约或历史观察；未全下载约 1.91GB 数据，没有逐日 Raw/历史 revision/PIT 包，未发现 LICENSE |
| `ztangz/daily-a-share-market-report@158119d0b0944bf49e41b24fca04e049c05d90ad` | 全部 79 个日期 `market.json`，2026-06-01～2026-09-18；首封池 5,270 条、2,081 个不同代码，无缺首封值 | **NO_GO**；处理榜单截断、Raw/SQLite 被 gitignore 排除、仅收盘涨停池；generated_at 不是 Provider first_observed/available_at，未发现 LICENSE |
| `phonegapX/alphasickle@bc8bf118d41d5830bdc872af63c621dd1558f09b` | 2012-01-31、02-29、03-30 三份月频 GBK 因子 CSV，共 6,307 行，含 MKT_CAP_FLOAT | **NO_GO**；不是日频原始流通市值历史包，缺固定来源契约、逐行观察/修订/覆盖与许可 |
| Rainynitesky/kaipanla-data-parser、gmz9976/ashare-sentiment、xu-duqing/investment_data、ling-0729/KHunter、yueshushu0207/kaipanla、zxhbloomer/my_stock | 固定 HEAD/完整树与选中源码在 Manifest 中；主要是 parser、请求器、外部 MySQL 或回测结果，未取得满足本 WP 门槛的原始历史归档 | **NO_GO**；源码说明/采集能力不能替代实际保存的输入；ashare-sentiment 的审查记录还提到历史日期可能返回当日。未运行外部源码 |

Jiu 当前 master 为 5,524 行，只有 `ts_code/symbol/name/industry/list_date`，包含 316 个 BJ 身份。按 `list_date<=20251231` 得 5,463 个证券，与三个目录文件名集合完全一致；这仅证明当前 master cohort 的目录对齐，**不证明历史冻结股票池、退市/ST/停牌或沪深分母**。日历为 1,461 日/969 开市日；`000088_SZ` 的行情/basic 各 959 行、因子 969 行，10 个日期只有因子，没有行情，缺历史停牌证据，不截短或填补。全部 8,646 个因子样本为正，仍不能提升为正式因子输入。沪深300/上证50各 969 行，与日历日期集合对齐，但指数 `PRICE` 的版本契约和历史观察/修订尚未证明。

daily-report 的 `src/transform.py:205-209` 将涨停/首封榜截至 80、炸板/跌停榜截至 50；79 个文件中有 50/32/21 个日期的对应榜单少于 summary 计数。`src/fetch_market.py:119` 首封处理前还截至 120；`src/fetch_ths.py:124` 请求 `getTopicZTPool` 单页 500，未证明完整 U+炸板触板范围及终止收据。文件名与 summary.trade_date 一致也不能证明交易日身份：包含 2026-08-29（周六）。取得 GitHub 服务端 100/289 条运行元数据及一项成功运行的 jobs/artifacts，artifact count=0、日志 HTTP 403；无 Provider Raw Hash 绑定，不绕过访问限制，不将 Git/Actions 时钟回填 PIT。

### 12.2 官方 301061.SZ 初版→更正的实际字节

| 文件 / 原文身份 | 静态来源、字节与 SHA256 | 原文语义 |
| --- | --- | --- |
| `301061-original-2025-021-szse.pdf`，4 页；落款 2025-05-20、公告 2025-021 | `https://disc.static.szse.cn/download/disc/disk03/finalpage/2025-05-19/093bd5b4-baf0-428b-82f5-0acb662821af.PDF`；285,291 bytes；`21c88b5d82b63af92c096a935c989c625fb1d54e8295a51c6c39710f8a839a8a` | 每 10 旧股税前现金 5 元、转增 3 股；登记 2025-05-23、转增无限售股起始交易 2025-05-26。初版列实施前/后无限售股 42,314,676 / 55,009,078 |
| `301061-correction-2025-022-cninfo.pdf`，2 页；落款 2025-05-20、公告 2025-022 | `https://static.cninfo.com.cn/finalpage/2025-05-20/1223605477.PDF`；247,642 bytes；`b4b8b6ddbf251ac00596879dd8857896f8a46acb4951e729b03248d15e89dc2c` | 明确更正 2025-021 的实施前/后无限售股为 111,141,876 / 144,484,438；总股本 167,370,613 / 217,581,796 不变，其他内容不变 |
| `301061-correction-2025-022-szse.pdf`，2 页；同一更正镜像 | `https://disc.static.szse.cn/download/disc/disk03/finalpage/2025-05-20/9e61a77f-022d-40ea-926e-170987d108e3.PDF`；247,642 bytes；Hash 与上一行一致 | 两个下载不是两个独立更正版本 |

8 个文件页全部提取文本，5 个独立关键页面实际渲染并视觉检查；原版 URL 路径日期为 05-19，原文落款为 05-20，不能任选日期作为历史可用时间。两份独立内容的落款同日，未取得来源发布时间的时分秒或历史首次观察日志，`historical_available_at` 仍为未知。

公告里的“本次实施前/后”股数不等于公告日当天的逐日股本。Jiu 的 301061 样本 float_share 在 2025-05-20 为 7,707.1476 万股，05-23 为 11,114.1876 万股，05-26 为 14,448.4438 万股；后两值与更正表数值一致。不能据此认定 05-20 的数据错误，也不能将更正表回填全部此前交易日；仍须证明限售解禁等变动的生效时间和固定 Provider 口径。官方更正只支持发行人语义案例，**不证明 Provider 同逻辑身份 Correction 或其 FeatureBundle 传播**。定向取消检索取得的 NEEQ 提案/方案终止、募集项目暂缓、限制性股票作废或已失效规则，不是申请沪深 scope 的完整行动取消原始链；未作为取消样本接入。

### 12.3 本轮决策、最小补料与停点

| 缺口 | 尚未收敛的具体问题 / 下一最小材料 |
| --- | --- |
| B1 | 固定 Provider 的 circ_mv 是否与每日可用价格/流通股口径一致；需原始响应、单位/币种/价格基准版本、逐日首次观察/持久化时钟、历史修订与全区间覆盖/冻结池。当前 snapshot 的字段名和 close×股本数值关系不能替代 |
| B2 | float_share/free_share 的正式换手率分母及股本变动生效 session；需固定单位、量的手/股换算、限制/自由流通定义、历史生效和观察区间、修订/缺页/停牌证据。不填旧 security_master.shares_outstanding |
| B3 | Provider 经济事件/组件身份及原版→更正/取消选择规则；需全类型真实 Raw、机器可读 revision/cancel、共同旧股/税/差异化分配基数、全页/终止/合法零行动、历史观察日志，以及同价格基准前一 session 实际 P。不把第三方 adj_factor 或 PDF 直接升级为正式 Dataset/Method |
| B4 | 当日全触板首封范围、固定 000300.SH/PRICE 与各原始量的历史日期/观察契约；需未截断 Raw、分页/终止/零行/历史日历、触板事件和收盘状态，并覆盖 Definition lookback/warmup。不能用展示榜、周末生成日期或处理时间替代 |

**B1—B4 本轮新增整体关闭项 0，全部正式输入 NO_GO。** 没有追加正式 Dataset/Raw Schema/Mapping/质量/Definition，也没有进入正式派生、真实输入 FeatureStore 发布或消费。本轮只推进“固定公共来源→下载/脱敏/Hash→完整行与覆盖/修订/PIT审计”；下一步依旧由合法来源材料触发。保留 B4 停牌 2.0.0、B5/N1/N2、旧 14 F1/65 F2/Hash/Golden/固定引用及 0014/0015；实现、验证与本轮增量回滚见[第 18 节](WP-0303-IMPLEMENTATION.md#public-history-evidence-resume)。WP-0303=IN_PROGRESS、15/45，两市场 missing，Formal/Paper 拒绝，NOT CERTIFIED、RELEASED=false。

<a id="a-stock-data-adapter-evidence"></a>
## 13. 2026-10-15 a-stock-data 固定版本与 Provider 分层证据

本轮完整只读 clone 位于 `E:\Personal Manager\参考项目\a-stock-data`，工作树 clean，固定 `main@29b07d2e37005b9fd568bca1262f6e572b5f9407`（V3.10.2，commit time `2026-10-11T12:55:46Z`）。GitHub API 同日返回默认分支仍为该提交、License 为 Apache-2.0；直接 `git ls-remote` 一次因 `github.com:443` 连接失败退出 128，未把单通道失败误报为远端变更。`README.md` / `SKILL.md` 的 Git blob 分别为 `704b9b6546e00bffc6fe2bb5cd4056d0f23f3258` / `8e334569f7cfd334b56f3b3bd067469d175ba892`，实际 SHA256 分别为 `33b6f4a829571cf1fd4d3de127468cd0c59dace65ac77c8230b1b21fbaa4a9b9` / `d30aa90edb881a45168c397a6ca1ccfebc440a8d4c93b3d94d3123d27b260a1d`。

仓库声明 15 层、87 个能力入口和 34 个来源；实际函数将腾讯、通达信官网、东财、巨潮、BaoStock、新浪、同花顺和交易所等不同上游封装在一个 `SKILL.md`。因此 GitHub 仓库身份只能固定 Adapter Bundle 实现，不能充当这些上游共同的 Provider 数据身份、历史版本或 `available_at` 证明。

| B项 | 固定入口与来源 | 本次确认的实现能力 | 仍阻断正式接入的证据 |
| --- | --- | --- | --- |
| B1 | `tencent_quote`/腾讯，`eastmoney_stock_info`/东财，`baostock_valuation_history`/BaoStock | 当前流通市值/股本字段候选，日频历史换手率/价格参考 | 没有历史流通市值版本、首次观察、修订档案和全市场统一覆盖；当前值不能回填历史 |
| B2 | `eastmoney_stock_info`/东财，BaoStock `turn` | 当前总股本/流通股及历史换手率输出 | 没有正确 A 股流通分母的历史有效期、披露/PIT、revision；不能反推或填 `security_master.shares_outstanding` |
| B3 | `dividend_history`/东财，`sina_adjust_factor`/新浪，`cninfo_announcements`/巨潮，mootdx 除权除息 | 行动字段、公告追索和因子对拍候选 | 没有稳定事件/组件 ID、初版/修订/取消、全类型/全页/合法零行动、source-native available_at 与完整价格 P |
| B4 | `tdx_daily_package`/通达信官网，BaoStock 历史 ST/停牌，`em_zt_pool`/`em_zb_pool`/东财，`ths_limit_up_pool`/同花顺，`trading_calendar`/深交所 | 单日全市场包内下限/唯一键/非有限数检查、历史状态和首封字段候选 | 通达信历史保存区间不完整且未逐日验证；榜单缺 total/完整分页及历史版本；东财通用函数异常时返回空列表，无法区分错误与零事件 |

`_em_zt_api()` 捕获任意异常并返回 `[]`，`limit_up_sentiment()` 又将空集合计算为 0 家和 0% 炸板率；这与 WP-0303 的 fail-closed/分母零缺失契约冲突。正式 wrapper 必须保留成功、非交易日、合法零行、限流、缺页和错误的不同状态。a-stock-data 内部由东财切换 BaoStock 等 fallback 时，也必须拆成独立 ProviderRun/RawObject/Partition/QualityReport，不能只记录 Bundle 名称或一个自由文本 `actual_upstream`。

本次采用结果只进入 [a-stock-data Adapter Bundle 分层架构](WP-0303-A-STOCK-DATA-ADAPTER-ARCHITECTURE.md)：现有 `a_stock_data@1.0.0` 保留兼容，不原地改 Provider/Golden/Policy；后续应追加实际 Provider/Endpoint、实现指纹和 CoverageReceipt 版本。当前没有任何 Endpoint 达到 `PIT_CERTIFIED`，因此不追加 Dataset/Raw Schema/Mapping/质量/Definition/Migration，不启动正式派生或真实 Correction E2E。

**B1—B4 新增整体关闭项仍为 0。** WP-0303 继续 IN_PROGRESS、15/45；两市场 missing、Formal/Paper 拒绝、NOT CERTIFIED、RELEASED=false。参考源码未执行，未访问其数据 Provider API，也未把代码 License 当作第三方数据许可。
