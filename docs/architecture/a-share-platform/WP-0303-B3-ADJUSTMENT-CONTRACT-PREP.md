# WP-0303-B3：PIT Adjustment Factor / Method 输入契约 PREP

## 1. 当前结论与完成边界

**2026-10-08：本记录收敛 B3 的差异、候选契约、实施决策及验收设计，不是 B3 实现验收。真实来源实施为 NO_GO；经下一 Goal 明确授权、确认本文决策后，隔离离线 fixture 实施可 CONDITIONAL_GO。没有无条件 GO，也不自动开始实现。**

- 当前实现事实以 [WP-0303-IMPLEMENTATION 第 8 节](WP-0303-IMPLEMENTATION.md#8-2026-10-08-b5-后继派生键迁移与完整数据库链路验收) 为准；该文前七节及 [WP-0303-PREP](WP-0303-PREP.md) 的旧 Catalog 描述是历史，当前 Catalog 已投影真实 DatasetDefinition，没有 `corporate_action.factor`。
- `WP-0303=IN_PROGRESS`，唯一 WP 计数 `VERIFIED=15 / IN_PROGRESS=2 / NOT_STARTED=28 / RELEASED=0`，已验收 **15/45**；B3 仍未关闭。`market_breadth/market_emotion` 仍 missing，Formal/Paper 继续拒绝，生产 **NOT CERTIFIED、RELEASED=false**。
- 本轮仅新增本文，并最小追加 INDEX、CHANGELOG、IMPLEMENTATION-STATUS 的路由/说明；不改运行代码、生成契约、manifest、lockfile、Migration 或已有 PREP/验收历史。
- 不执行依赖安装/升级/下载、真实 Provider/业务数据库/真实 `/data`、B1/B2/B4 或相邻 WP、分支/worktree/commit/tag/push/PR/merge/部署。公开交易所规则只用作只读语义反例，不是 Provider 认证。

领域约束不重复维护：数据集主备矩阵见 [数据平台契约第 4 节](data-platform-and-canonical-contract.md)，公司行动与派生复权见该文第 6.4 节；指标版本与回测复现见 [回测与指标架构](backtest-and-indicator-architecture.md)。本文是 B3 的细化设计，不覆盖它们。

## 2. 开工保护与证据口径

### 2.1 实测基线

工作目录：`C:\Users\lzq11\.codex\worktrees\f468\Visory`，不是聊天初始的 f307。适用规则已读：目标根 `AGENTS.md` 和祖先 `C:\Users\lzq11\.codex\AGENTS.md`；目标 docs/src/tests 路径未发现更深规则。

- 开工 **20 个已跟踪修改、10 个未跟踪文件，共 30 项**，detached HEAD。
- `HEAD`、本地 `origin/main`、只读 `git ls-remote origin refs/heads/main` 返回的远端 main 均为 `efe8e9b362cba13eca183c55be57bbbbc832b60b`。本轮没有 fetch/pull 或改动 refs；远端核验是当时观测，不保证此后不变。 收尾再次执行 `git ls-remote origin refs/heads/main` 返回 exit 128：`Failed to connect to github.com port 443 after 21138 ms: Couldn't connect to server`；不能声称收尾远端仍一致。收尾本地 HEAD/origin/main 未变，无自动合并。
- 开工文件逐一按原字节复制，SHA256/大小/状态保存在仓库外 `C:\Users\lzq11\AppData\Local\Temp\visory-wp0303-b3-prep-20261008-01a11ab3\opening.json`，原文件副本在同目录 `opening/`；另有开工 status/diff。以下三个同步文件原本已修改，必须相对开工副本计算本轮增量，而不是相对 HEAD 计算成果。
- 本轮 allowlist 只有本文、`docs/INDEX.md`、`docs/CHANGELOG.md`、`docs/architecture/a-share-platform/IMPLEMENTATION-STATUS.md`。其他开工 27 项须保持 SHA256 不变；三个同步文件只插入本文路由及边界说明，不删除或重排开工内容。

### 2.2 开工已有 30 项（不计为本轮成果）

| 状态 | 开工路径（相对上述工作目录） |
| --- | --- |
| 已跟踪修改 | `docs/CHANGELOG.md`、`docs/INDEX.md`、`docs/architecture/a-share-platform/IMPLEMENTATION-STATUS.md` |
| 已跟踪修改 | `docs/architecture/a-share-platform/WP-0302-IMPLEMENTATION.md`、`docs/architecture/a-share-platform/feature-store-architecture.md`、`docs/architecture/a-share-platform/market-sentiment-and-capital-flow-architecture.md` |
| 已跟踪修改 | `schemas/platform/C-006.FeatureBundle.schema.json`、`schemas/platform/C-006.FeatureDependencyPlan.schema.json`、`schemas/platform/C-006.FeaturePartition.schema.json`、`schemas/platform/C-006.FeatureSnapshot.schema.json`、`schemas/platform/C-006.IndicatorDefinition.schema.json`、`schemas/platform/C-010.openapi.json` |
| 已跟踪修改 | `src/repositories/platform/feature.py`、`src/schemas/platform/feature.py`、`src/schemas/platform/indicator.py`、`src/services/platform/feature_dependency.py`、`src/services/platform/feature_store.py`、`src/services/platform/indicator_registry.py` |
| 已跟踪修改 | `tests/integration/platform/test_postgres_foundation.py`、`tests/platform/test_indicator_registry.py` |
| 未跟踪 | `docs/architecture/a-share-platform/WP-0303-IMPLEMENTATION.md`、`docs/architecture/a-share-platform/WP-0303-PREP.md` |
| 未跟踪 | `migrations/versions/0014_wp0303_indicator_id.py`、`migrations/versions/0015_wp0303_partition_key.py`、`src/services/platform/market_sentiment.py` |
| 未跟踪 | `tests/integration/platform/test_feature_indicator_id_postgres.py`、`tests/integration/platform/test_feature_partition_key_postgres.py`、`tests/integration/platform/test_market_sentiment_postgres.py`、`tests/platform/test_feature_indicator_id_contract.py`、`tests/platform/test_market_sentiment.py` |

### 2.3 事实、目标和验证必须分开

下表 `file:line` 以本轮只读时的开工文件为准；长单行声明按符号定位。引用测试仅说明已有断言/覆盖边界，**本轮没有运行这些测试**。第 4–8 节所有新字段、Method、公式、失败码及案例均是建议契约/验收设计，当前并未实现，也未获生产批准。

## 3. B3 差异矩阵

| 当前声明或实现 | 消费者要求 | 缺失语义/反例 | 实现证据（相对仓库根） | 对 B3 的影响 |
| --- | --- | --- | --- | --- |
| `corporate_action@1.0.0`：必填 ID/entity/type/ex_date/revision/published_at/available_at；可选 record_date/payment_date/ratio/cash_amount/currency | 按证券、交易日、固定 cutoff 的 factor 序列 | 没有 factor、方向、锚点、Method、生成公式/血缘；事件行不是逐日因子行 | `src/services/platform/extended_canonical.py:23-31`，`extended_dataset_contracts` | 不能把事件 Dataset 改名当成因子 Dataset |
| `ratio:number`，unit=`ratio`，time=`action_ratio`，nullable_when_not_applicable | 无偿增股 b、拆分倍数 s 或配股 r 的明确口径 | 不知道每股/每 10 股、增量/总量、前/后股本基数；一个字段不能同时安全表达三者 | `src/services/platform/extended_canonical.py:31,60-64,92-106` | **只证明本地允许映射一个数，不能证明业务比例**；不得凭名称代入公式 |
| `cash_amount:number`，unit=`cny_per_share`，currency 仅 CNY | 税前每旧股现金 D，币种及分派基数 | 本地单位声明不证明 Provider 实际是每股、税前、均匀分派；差异化分红/每 10 股金额可能不同 | `src/services/platform/extended_canonical.py:31,46-57,92-99` | **只证明设计意图和乘数声明**；真实口径仍未核验 |
| type enum=`DIVIDEND/SPLIT/BONUS/RIGHTS/OTHER`；映射 DIV→DIVIDEND | 明确行动子类、普通/特殊公式、组合分组与取消状态 | 标签不能证明公式适用；RIGHTS 缺认购价；BONUS 可能是重整，不等于普通送转 | `src/services/platform/extended_canonical.py:31,46-57,106` | enum 接受不等于 Method 支持；OTHER/含糊行动拒绝 |
| 两个 Raw Schema/Mapping @1.0.0；ratio/cash 乘数为 1 | Provider 原始字段、版本、单位、修订、时间及覆盖证据 | a_stock_data `as_of` / financial_api `available_at` 名称不足以证明 PIT 可用时间；无线上文档/样本核验 | `src/services/platform/extended_canonical.py:37-64,92-106`；`src/services/platform/provider_registry.py:197-204` | ProviderCapability 为 UNVERIFIED、history_start=None；不能认证历史复权 |
| required/optional/type/unit/time/null 结构校验 | 类型条件必填、合法参数、PIT、完整事件集合 | 结构完整不证明业务完整，DIVIDEND 缺现金、SPLIT 缺倍数仍不能计算 | `src/schemas/platform/provider.py:147-223`；`src/services/platform/canonical_normalization.py:302-335,390-399` | 新版本需类型化输入与条件质量规则 |
| 现有公司行动日期检查要求 record_date/payment_date 不早于 ex_date | 普通 A 股登记日在除权日前，特殊情形有证据规则 | 普通登记日早于 ex_date 会被拒绝；不能把迎合现有条件的 fixture 当作语义证明 | `src/services/platform/canonical_normalization.py:390-399`；`tests/platform/test_extended_canonical.py:21-31` | 新版质量规则必须修正；旧 v1 不静默改写 |
| 去重 PK=`(corporate_action_id,revision)`，revision>=1 | 截至 cutoff 的最新已知有效修订、取消、经济事件去重 | 不同 ID 可是同一经济事件；无全局 revision 选择/同日组合协议 | `src/services/platform/canonical_normalization.py:427-445`；`src/services/platform/snapshot.py:305-326` | 不得累乘全部 revision 或重复主备记录 |
| 无质量失败可给 COMPLETE，允许 row_count=0 | 固定证券范围及时间区间的肯定完整覆盖 | 空行/成功状态不能区分无行动、缺页、缺分区、历史未覆盖 | `src/services/platform/canonical_normalization.py:484-498`；`src/schemas/platform/canonical.py:189-210` | 缺失不能 factor=1；需独立覆盖收据 |
| `bar_1d_raw.prev_close` 声明 prior_session_observation | 事件前实际未复权收盘 P | Provider 当日行情“前收盘价”可能已是除权息参考基准；本地声明不证明来源等价 | `src/services/platform/provider_registry.py:64-73`；交易所规则证据见第 3.1 节 | 优先在固定 bar Snapshot 按日历取前一 session 的 close，不盲用 prev_close |
| 当前 Catalog 从 DatasetDefinition 投影，按 dataset_id 单键保存，number→decimal | 并存公司行动 v1/v2、派生 factor 及固定 Method | 无 factor；增加 v2 时单键可能覆盖 v1；Formal 检查 available_at 不等于经济语义通过 | `src/services/platform/feature_dependency.py:31-68,255-282` | Resolver 必须按精确版本解析，禁止临时造字段解锁 |
| F1 `return_point_in_time_adjusted@1.0.0` 要 corporate_action.factor；builtin zip close/factor | 完整日期/身份 join、正 finite 因子、PIT 来源 | zip 可截短；无长度、日期、来源保证；raw MA 不是 adjusted MA | `src/services/platform/indicator_registry.py:56-65,282-304` | 保留旧载荷/Hash且继续拒绝；新增精确版本依赖 |
| BLOCKED F2 同样引用 corporate_action.factor | adjusted return、MA/20 日高低价及其下游 | 输入不存在；归一化/score/state 不能因新字段名自动认证 | `src/services/platform/market_sentiment.py:513-519,610-656,1020-1054`；`WP-0303-PREP.md:107-113` | 只设计受影响闭包；B1/B2/B4及市场认证门禁不放开 |
| formula_hash 仅 hash `{formula_type,formula_ref}`；implementation_hash 仅 builtin_id/implementation_version | 经济公式、精度、时间、组合、比例政策指纹 | 当前 formula_hash 不是完整经济公式 digest；Decimal scale 也不会自动同义归一 | `src/schemas/platform/indicator.py:320-340`；`src/schemas/platform/hashing.py:39-94` | 新 Method 单独规范并固定 Hash；不修改旧 Hash 算法 |
| CanonicalPartition 强制真实 ProviderRun/RawObject refs；DataSnapshot 无 Method refs | 派生因子的直接输入 Snapshot 与完整传递血缘 | 不应制造 ProviderRun/RawObject 或只记录源 Provider 名字 | `src/schemas/platform/canonical.py:197-233`；`src/schemas/platform/snapshot.py:248-270` | 派生 provenance 承载是实施前决策，不能只注册 Dataset 就声称闭环 |
| Feature Correction 固定 as_of/cutoff/plan/definition_refs | 修正不覆盖固定历史且下游传播 | available_at>旧 cutoff 的迟到事实不得冒充旧逻辑 Snapshot 的 Correction | `src/services/platform/feature_store.py:746-768`；`tests/platform/test_feature_store_contracts.py:1111` 起 | 新 cutoff/plan 必须新逻辑 Snapshot/Bundle；同 identity 才能 supersedes |

### 3.1 公开第一方反例与证据限度

- [深交所交易规则（2026 年修订）](https://docs.static.szse.cn/www/lawrules/rule/trade/current/W020260424690713155663.pdf)，2026-04-24 修订，PDF 第 26 页 4.4.1–4.4.3：普通除权息在登记日后一交易日；参考价依现金、配股价和股份变化计算；允许另行申请特殊公式。第 4.4.3 条说明参考价用于除权息日涨跌幅基准。本文只据此识别日期、公式适用范围及价格基准风险，不断言任何 Provider 字段的真实含义。
- [上交所 2026 年修订通知](https://www.sse.com.cn/lawandrules/sselawsrules2025/trade/universal/c/c_20260424_10816492.shtml)，发布日期 2026-04-24，通知规定 2026-07-06 生效；已核对通知及检索到的 4.3.1–4.3.3 文本。DOCX 附件读取返回 `400 Unsupported content-type`，**未声称成功读取该附件全文**。不以此缺口阻塞本 PREP，深交所官方 PDF 足以支持保守反例。
- [深交所披露的重整权益分派公告](https://disc.static.szse.cn/download/disc/disk03/finalpage/2025-12-06/3350047f-887c-4844-a383-077fbc181e86.PDF)，2025-12-06，已核对 PDF 第 4–6 页，登记日 2025-12-11、股份上市日 2025-12-12，采用重整专用参考价计算。它是“增股标签不自动等于普通送股公式”的反例，不是通用 Provider Mapping 证据。

**可确认的是本地声明和上述规则反例；不可确认的是 Provider 实际单位、事件身份、历史时间、修订/取消、完整覆盖、特殊公式标记。它们仍是实施 BLOCKER，不以网站规则代替 Provider 审核。**

## 4. 建议的最小 Dataset / Method 契约（未实现、待批准）

### 4.1 单一派生路径与版本

```text
固定 corporate_action@2.0.0 Snapshot + 原始 bar_1d_raw Snapshot
  + 固定 identity/calendar + 覆盖收据 + pit_adjustment Method@1.0.0
  -> 派生 adjustment_factor@1.0.0 / 版本化派生 Manifest
  -> 固定版本 F1 -> 受影响的 F2 新版本及固定 Feature Snapshot/Bundle
```

公司行动 `2.0.0`、因子 `1.0.0`、Method 名称/版本是建议值，不是当前注册项。保留 `corporate_action@1.0.0` 及已有 Raw/Mapping/Definition；不向旧事件行回填 factor。Method 是平台确定性派生方法，不是第三个 Provider。Provider 返回因子/复权价格只能辅助交叉核验，不能成为生成因子的真源。

### 4.2 公司行动新版条件输入

| 建议字段/约束 | 定义与必填条件 |
| --- | --- |
| ID/entity/revision、`published_at/available_at/ex_date` | 保留稳定经济事件身份与不可变 revision；新修订不能覆盖旧行；ex_date 是交易所确认的生效日，不等于公告日/支付日 |
| `action_type/action_subtype`、`reference_formula_kind` | 明确普通现金/普通无偿送转/纯拆分/配股/特殊；Method 仅接受下节白名单，特殊公式与 OTHER 不降级 |
| `event_status` | 至少 ACTIVE/CANCELLED；待定方案不作为生效行动。取消必须是可验证的新 revision，不是删除旧行 |
| `cash_per_old_share_gross`（D）与 `currency` | 普通现金行动必填，税前 CNY/一股事件前旧股；金额、基数、税前口径都需来源证据，不允许只改字段名 |
| `bonus_new_shares_per_old_share`（b） | 普通无偿送转必填，新增股数/一股事件前旧股；b=0.5 表示每旧股增加 0.5 股，不是总股数倍数 |
| `split_total_share_multiplier`（s） | 纯拆分必填，拆分后总股数/拆分前总股数；s=2 表示一股变两股，不是新增两股 |
| `rights_new_shares_per_old_share`、`subscription_price_cny` | 预留配股的关键语义审查；即使补齐，Method v1 仍不支持 RIGHTS，须另批方法版本，不能套无偿增股 |
| `economic_event_key/action_group_id/component_role`、`share_basis` | 同日组件须同一方案、共同 pre-event 基数，身份/角色唯一；不同方案同日需要明确顺序或统一公式证据，v1 拒绝含糊组合 |
| source evidence、Raw Schema/Mapping version、转换参数 | 固定原始值、每股/每 10 股等分母、增量/总量、税口径、公告/修订/取消证据及 Hash，作为可审计血缘 |

“每 10 股派 10 元、送 5 股”若来源明确为税前、事件前旧股基数，则 D=10/10=1、b=5/10=0.5；不能因 Provider 字段叫 `ratio/cash_per_share` 就默认该转换。Null 意味未知/不适用，不统一补 0。仅在已识别的行动类型和完整组件收据明确“不适用”时，公式缺省的 D 或 b 才可为 0。

### 4.3 派生 factor 的行与 Manifest

- 行唯一键建议 `(entity_key,trade_date)` **限定在同一个不可变派生 Manifest 中**；跨 Manifest 不按这个键覆写。每个预期价格观测日恰有一个正有限 `factor`，unit=`dimensionless`；必填逻辑 `available_at`，源披露时间作为明确命名的 `source_published_at`/血缘，不能和平台发布时钟混同。
- Manifest 固定 `dataset_id/schema_version`、`method_id/method_version/method_contract_hash/formula_digest`、方向、anchor/base、日期范围、cutoff、证券范围 Hash、每个输入 Snapshot ID/manifest/content Hash、Partition ID/Hash/schema_version、identity/calendar refs/Hash、ProviderPolicy/Raw Schema/Mapping/质量规则版本、覆盖收据 Hash、事件 ID/revision/group、P 的原始价格行引用、计算规范和结果 content Hash。
- 同一 Manifest 的 rows 必须共享同一 anchor/base/cutoff/Method；不可把每个历史日单独 anchor=当日的 factor=1 拼成一条历史序列。所有窗口消费者声明实际 lookback/warmup及相同价基，缺失日期不靠 zip 截短。
- 无公司行动时 `selected_event_refs=[]` 合法，但 **action Snapshot、覆盖收据和其他输入引用仍必填**；空引用不能代替零行动证明。
- 承载建议：复用 Canonical/DataSnapshot 和既有 FeatureStore，不新建平行存储；新增**显式版本化 DERIVED provenance/Method Manifest 引用**，固定直接输入 Snapshot 和传递的真实 Raw/ProviderRun 根。它不是现有 C-005/C-006 已有字段。旧 PROVIDER 模式和旧 Hash 序列化保持原样，禁止伪造 ProviderRun/RawObject、把 Method 当 Provider 或注入默认字段后重算旧 Manifest Hash。该承载的 schema/生成契约变化须由下一 Goal 显式批准（D6）。

## 5. 行动白名单、公式、方向与数值规范

### 5.1 Method v1 支持边界

| 行动 | 候选 v1 处理 | 关键输入与拒绝条件 |
| --- | --- | --- |
| 普通现金 DIVIDEND | 支持 | 已确认 D>0、CNY、均匀税前每旧股分派、非特殊公式 |
| 普通 BONUS/公积金转增 | 支持 | 已确认 b>0、无对价、共同旧股基数，不能包含重整受让/偿债股份 |
| 纯 SPLIT | 支持普通拆分 | s>1、无现金/配股/其他组件；s<=0非法，0<s<=1的合股/反向拆分不在 v1 白名单 |
| 同日普通现金+普通送转 | 条件支持一次组合 | 同一 group、共同基数、完整组件、各角色唯一；cash/bonus可分别多组件求和但必须证明不重复 |
| RIGHTS、现金+SPLIT、独立多个方案同日、合股、重整、差异化分红、特殊/未知行动 | 拒绝 | 不凭 enum 猜公式，不取 Provider 因子兜底，不默认无行动；扩大支持需新 Method 版本和反例验收 |

### 5.2 事件跳变与价格语义

令 P 是固定未复权 bar Snapshot 中**事件前一交易 session 的实际 close**（P>0，CNY/旧股）；D 为税前每旧股现金，b 为每旧股新增无偿股，s 为纯拆分后的总股倍数。

```text
现金：                 Q = P - D
普通送转：             Q = P / (1 + b)
同日普通现金 + 送转：   Q = (P - sum(D_i)) / (1 + sum(b_i))
纯拆分：               Q = P / s
事件价格跳变：         q = Q / P
```

Q 使用理论精度，不套交易报价 tick 四舍五入；它是本 Method 的连续价格参考，不承诺逐分等于交易所公布参考价。必须 Q>0、q>0且有限；D>=P、非法 b/s、来源基数含糊立即拒绝，不能裁剪到 epsilon。factor不设置无依据的 `(0,1]` 上界（后复权 factor 可大于 1）。

同日 cash/bonus 必须在共同 P 下组合一次；不能把 `(P-D)/P` 和 `1/(1+b)` 的任意逐条执行当作普遍同日协议，更不能将不同基数的多组件简单累乘。按组件拆分时现金+送转公式可能恰巧相同，但两个现金事件若各用原 P 则会给出错误积；同日组在完成语义去重后只产生一个 q。

该方法是**价格连续性复权收益**，不是 TOTAL_RETURN、税后分红收益、实际持仓收益或组合账本。原始成交、volume/amount、交易限价和公司行动账本不使用派生价替代；不通过复权顺手实现成交/账本改动。

### 5.3 固定方向和锚点

B 为显式固定 base（历史范围起点），A 为固定 anchor，B<=t<=A；只处理已知且生效 session 在 `(B,A]` 的事件。B 当日价格已经反映该日生效行动，不能再施加 B 当日 q。

```text
H(B) = 1
H(t) = product(1/q_e),  B < ex_session_e <= t    # 后复权，固定 B
F(t,A) = product(q_e),  t < ex_session_e <= A    # 前复权，固定 A；F(A,A)=1
精确算术下 F(t,A) = H(t)/H(A)
adjusted_OHLC(t) = raw_OHLC(t) * H(t) 或 * F(t,A)
R(t) = adjusted_close(t) / adjusted_close(prev_session(t)) - 1
```

实现规范以各自的直接乘积为准，不用两个已经量化的 H 再除来计算 F。每个事件在 ex_date session 开始生效；事件日自身前复权不再乘该日 q，而前一日价格要乘。未来 ex_date>A 即使已公告，也不能进入当前 anchor；未来 anchor 不允许回填旧历史回测。比较 close与MA、20日high/low等必须使用同一 Manifest/anchor/cutoff。

### 5.4 精度与确定性（建议，D3 待批准）

- 全链使用十进制字符串/Decimal，拒绝 float、NaN、Infinity；原始值/原始精度保留作证据。运算 context precision=38，`ROUND_HALF_EVEN`；除法 q及1/q和按日期/组排序的连乘使用该 context。
- 行 factor 只在输出时量化为小数点后18位；调整价格计算采用固定的该行 factor并在结果输出时量化18位，不按报价tick量化。归一化负零为正零；量化后<=0或有效数字溢出拒绝，不静默截断。
- 可计算边界固定为38位有效数字内、输出整数最多20位；超范围、因子量化为0或 InvalidOperation 拒绝。收益在同样context中从固定调整价计算，再量化18位；拒绝调整价量化后为0，不用二进制浮点容差放行。
- Decimal 的 Hash 序列使用固定18位规范字符串；Method 参数中的量/比例采用有单位的规范十进制字符串（去无意义尾零，禁止指数/locale表示，零为`0`）。原 Raw字节Hash不被这些规范化取代。
- Method 必须声明精度/舍入/每步操作/量化点/排序；与精确关系的差异容限作为测试规范，不能换算法而保持同一MethodHash。重复执行应比较内容 Hash/确定性结果字节；不能宣称带新UUID、created_at、平台published_at的实例 Manifest Hash也天然相同。

## 6. PIT、完整性、时间对齐与更正

### 6.1 三种时间不可混用

1. 公司行动 `published_at` 是该 revision 的源披露时刻；`available_at` 是系统/授权历史证据证明的可用时刻。要求 `published_at <= available_at <= C`，C是消费 cutoff（aware UTC；展示可上海时区）。首次抓取后不能只根据公告日期伪造过去可用时间；只有审核通过的历史可用证据才可用于 historical replay。
2. ex_date是经济生效日，由固定交易日历与确证公告决定；登记/支付日期不是PIT时钟。普通登记日在ex_date前；特殊日期另据白名单规则校验，不把当前v1错误的全局 `record_date>=ex_date` 迁移到v2。不得把未知/非交易日ex_date默默挪到下个交易日。
3. DataSnapshot/CanonicalPartition 的 `created_at/published_at` 是平台物化/发布时间，不是源披露。当前 DataSnapshot 要 `available_at<=cutoff_at` 且 `published_at>=created_at`（`src/schemas/platform/snapshot.py:317-345`），不得用同一个不等式混淆源时间和平台发布；离线稍后重算可保留已证明的知识cutoff，但不能把新采集的事实回填旧C。

派生行逻辑 `available_at` 取所需事件、P、日历/身份和完整覆盖收据的已证可用时间上界，不能早于任何根输入；Manifest 单列 `materialized_at`（操作审计，不进入纯内容Hash）。Method 是固定确定性变换，不借“生成在今天”偷渡未来源事实，也不把今天来源的 available_at减小到历史cutoff。下一实现须核对现有 Snapshot/Feature 数据与平台发布时间契约，而非另创旁路。

### 6.2 固定 Snapshot 与 revision 选择

- 只消费显式 pin 的已发布合格 Snapshot/Partition/Hash，校验其cutoff和每行availability；禁止 `latest`、当前Provider接口或当前全量factor回填。若Snapshot携带晚于C的行/收据，不静默丢弃来掩盖污染，应拒绝或选择另一个确实满足C的固定Snapshot。
- 在该固定输入且截至C可知的同一经济事件revision中选择最高已知版本；不能从今天目录中找最高revision。源revision编号不具单调语义时，用审计过的映射版本规则，不凭数字大小猜。
- 最高已知版本 CANCELLED：保留取消证据，事件不产生q；ACTIVE但缺值/未知类型：拒绝，不能转为无行动。重复revision、同事件冲突、主备冲突或漏组件隔离；保持原主备 `REPLACE_PARTITION` 与 reject冲突政策，不逐行拼接。
- 固定calendar/identity join `(entity_key,trade_date)`，每个预期交易观测日与factor恰好一对一；事件P的前一session没有实际close、停牌/上市边界或身份切换不明时，v1拒绝，不 ffill、跳日或用当日prev_close兜底。非观测日如何处理由现有状态/行情契约决定，不在本轮推进B1。

### 6.3 无行动不等于数据缺失

允许 factor=1 的前提：固定公司行动 Snapshot及覆盖收据能肯定证明 `(B,A]` 对目标证券/范围截至C完整，全部适用行动已识别、去重、选revision且没有生效行动。

收据至少固定：证券范围Hash、请求/历史覆盖起止、Provider/Raw/Mapping/Policy版本、完整分页/结束标志或等价来源清单、成功/截断/限流/错误状态、事件类型覆盖、源可用时间证据、空结果原因、质量报告/隔离项、收据Hash及其available_at。**需要肯定完整性证据，不只是“质量没有报错”。**

| 情形 | 结果 |
| --- | --- |
| 有完整合格覆盖收据、row_count=0，或全部确认取消且事件集合完整 | NO_ACTION，factor=1；仍保留Snapshot和证据引用 |
| 无Snapshot/缺分区/缺页/Provider UNVERIFIED历史/空值/部分事件类型不支持 | MISSING或REJECTED，禁止factor=1与认证 |
| 完整但区间内有unknown/RIGHTS/特殊公式或未解决主备冲突 | UNSUPPORTED/CONFLICT，fail-closed；不能以排除股票重算分母掩盖市场覆盖缺口 |
| 范围不匹配、coverage收据available_at>C | COVERAGE或PIT拒绝，即使文件非空也不合格 |

零行动需要完整区间证据；后复权仅承诺固定B后的序列，不假称上市以来绝对基准。使用20/60日窗口时，coverage与P覆盖必须延伸到实际lookback/warmup要求，不能只覆盖当天。

### 6.4 迟到更正与传播

- 原revision D=1截至C0可用；新revision D=2仅在C1>C0可用：旧C0始终选D=1，旧factor/Partition/Snapshot/Bundle/Hash/文件不变。C1下可生成“截至C1重述历史”产物，但它不能冒充C0当时可知的回测输入。
- **新cutoff或dependency_plan_hash/Definition变化 => 新逻辑Snapshot/Bundle**；不以Correction改旧cutoff绕过 `src/services/platform/feature_store.py:762-768`。只有同as_of、同cutoff、同plan/definitions且输入更正确实在该cutoff可用，才使用现有revision/supersedes链；仍不可覆盖旧物理对象。
- 一项事件更正的前复权影响早于ex_date到B的因子，后复权影响ex_date及其后到A；不是一律“尾部更正”。须根据方向、依赖窗口重算受影响的return、MA/high-low等，再传播至受影响F2原始量→normalized→score→smoothed→state，保留未受影响分区。
- **迟到事件**与**算术/Mapping错误修复**分开：前者新的知识时间，后者若Method或Mapping版本/plan变化同样新逻辑产物，不能保持旧MethodHash而改公式。现有B5 fixture只证明其固定manifest Correction机制，不证明本B3链路已运行。

## 7. Method / Formula Hash 与旧引用保护

建议 `method_contract_hash=SHA256(canonical Method payload)`；`formula_digest` 单独覆盖公式及数学政策，不冒充当前 IndicatorDefinition.formula_hash。其payload至少含公式白名单、D/b/s单位/基数、同日组合、P来源、ex_session/端点、方向/锚点、revision/取消、coverage/PIT/失败政策、精度/舍入/量化/排序、返回值语义、算法版本与实现版本。

- 方法payload只含确定性语义；created/materialized/平台published等操作时间单独审计。输入Manifest另固定source IDs/Hash/cutoff/coverage，改变输入不一定改变MethodHash，但必须改变对应输入/结果血缘Hash。
- 新F1/F2 Definition使用现有parameters或批准的新MethodRef明确pin `method_id/version/method_contract_hash/formula_digest`；既有formula_hash仍按旧规则计算，新完整经济digest不得通过改全局Hash函数补入旧定义。运行实现版本及代码指纹也固定，不把版本号当作实际源码Hash。
- 当前 `[dataset_id -> view]` 要升级为按 `(dataset_id,schema_version)` 的精确注册/投影/解析；仓库Dataset持久化已用该复合键（`src/repositories/platform/provider.py:178-183`），Resolver还没有。新factor必须来自真实注册Definition，不能以定制Catalog注入factor。
- `return_point_in_time_adjusted` 建议新增 `definition_version=2.0.0` 指向新factor；`moving_average@1.0.0`继续是raw语义，若增加adjusted MA要另建明确语义Definition，不能静默替代原MA。相关名称/版本仍待D5批准。
- 只给受影响F2依赖闭包增加新Definition版本，并显式pin上游版本；不全部重写65项，不使用省略版本后取最大版本。MA等B4残余的实施不在本PREP，本记录仅标明接入依赖和另行授权边界。
- 原14个F1、65个F2的完整payload/Hash，以及原Partition/Snapshot/Bundle固定引用全部保留；不修改旧ID/键、Hash算法、不反序列化后补默认字段再重发旧内容。现有aggregate Hash见当前 [第8.3节](WP-0303-IMPLEMENTATION.md#83-真实-postgresql-及完整-fixture-证据)，是历史记录，本轮未重跑其测试。

## 8. 下一 Goal 的最小实施范围与验收设计

### 8.1 实施顺序（计划，未执行）

| 步骤 | 最小改动面与停止条件 |
| --- | --- |
| 0：批准决策与护栏 | 先批准D1–D6及代码/生成契约授权，冻结旧14/65 payload/Hash和旧固定引用保护用例；B1/B2/B4隔离，市场认证硬门不变 |
| 1：输入版本 | 新版公司行动Dataset与经证据审核的Raw Schema/Mapping/质量规则；每股转换、普通登记日、未知/取消/冲突/覆盖负例。真实Provider证据不足则只允许fixture模式，保持UNVERIFIED |
| 2：派生方法 | 固定Method Manifest、Decimal算法、join/同日group/PIT/coverage；复用现有存储，补版本化派生血缘承载；不把虚构RawObject用于通过既有模型 |
| 3：Resolver/F1 | 精确Dataset/Method版本，新增F1收益Definition；缺字段、日期不齐、因子非法、旧输入漂移仍拒绝；新能力不能自动映射为两市场认证 |
| 4：消费接口与传播 | 审阅受影响F2版本闭包及新旧固定引用；与B4相交的adjusted MA等只在追加授权后接入，不借本B3实施替换旧raw MA或修其他输入 |
| 5：分层验收 | 先以下确定性用例，再Method→Resolver→FeatureStore固定发布/消费/重启/Correction；批准持久化变更后才做隔离DB验证及生成契约同步。需要Migration时重新说明范围，禁止改0013/0014/0015或开工成果 |

真实Provider核验、真实环境能力验收、数据库/生成契约/任何外部写入需各自明确授权。离线fixture实现通过不允许关闭完整WP-0303或Formal/Paper门禁；B3关闭也需要它自己的完整端到端验收，而不是本文完成。

### 8.2 可手工复算的正常案例（全为设计，未运行）

统一假设：同一测试证券、CNY、固定日历session t0<t1<t2、输入Snapshot/Hash/coverage可用时间<=C、已确认普通行动；本文数字是合成例子，不是真实Provider行情。

| ID | 输入和固定方向 | 期望数学结果/验收点 |
| --- | --- | --- |
| A01 | 完整覆盖、零行动，raw close t0=10、t1=11，B=t0/A=t1 | H=F=1；R(t1)=11/10-1=0.1；没有事件ref但Snapshot/coverage非空 |
| A02 | t1现金D=1，P=t0close=10，raw t1close=9，A=t1 | Q=9、q=0.9；F(t0)=0.9、F(t1)=1，调整价9/9、R=0；H(t1)=10/9，38位运算/18位输出按政策量化，不以实数精确0掩盖舍入差异 |
| A03 | t1同日现金D=1及b=0.5，P=10，raw t1=6 | Q=(10-1)/1.5=6、q=0.6；前复权价6/6，R=0；每10股现金10元/送5股转换后等价 |
| A04 | t1纯拆分s=2，P=10，raw t1=5 | Q=5、q=0.5；F(t0)=0.5，H(t1)=2；两方向收益0 |
| A05 | t1现金D=1/P=10/q=0.9，t1raw=9；t2纯拆分s=2/q=0.5，t2raw=4.5；A=t2 | F(t0)=0.45、F(t1)=0.5、F(t2)=1，三日价均4.5；H(t0)=1、H(t1)=10/9、H(t2)=20/9；Method所有除法/量化按固定政策 |
| A06 | 同日同group两个独立确认的现金组件D1=D2=1，P=10，raw post=8 | 一次组合Q=8、q=0.8；错误的0.9×0.9=0.81必须被反例识别；重复同一组件不得相加 |
| A07 | C前已公告但ex_date=t2>A=t1 | t1锚点不含t2事件；历史t0/t1不因未来生效而复权，未来anchor须新Manifest |
| A08 | 普通登记日在t0、ex_date=t1，P行指向t0实际close | v2接受正确日期；不能要求record>=ex，不能拿t1行情中的参考prev_close替代t0实际close |

### 8.3 失败、更正与Hash案例（全为设计，未运行）

| ID | 反例/变更 | 预期拒绝或传播结果 |
| --- | --- | --- |
| N01 | 没有公司行动Snapshot，或空分区但缺分页终止/完整区间证明 | MISSING/COVERAGE拒绝；不得factor=1或改变分母绕过 |
| N02 | 行revision或coverage available_at>C；源published_at>available_at；旧快照夹带未来数据 | PIT拒绝，结果/旧文件/固定引用不变；不只过滤污染行后宣称合格 |
| N03 | 相同group基数不一致、不同方案无顺序、相同事件跨两个ID重复/主备冲突 | AMBIGUOUS/CONFLICT拒绝；不得按输入顺序累乘 |
| N04 | OTHER、未知类型、重整BONUS、RIGHTS缺认购价、RIGHTS字段齐全但Method v1 | UNSUPPORTED拒绝；不兜底Providerfactor、不能将RIGHTS当无偿增股 |
| N05 | P<=0，D>=P，s<=0，负b，factor=0/负数/NaN/Inf；极小正数量化后0；溢出 | 数值拒绝；无裁剪/float fallback。合法后复权factor>1不被误拒绝 |
| N06 | bar/factor长度不同、日期重复/缺失、entity不齐，前一session停牌无实际close | JOIN/REFERENCE_PRICE拒绝，不能zip、ffill或默默缩短窗口 |
| N07 | 同样固定Method/输入/coverage，运行两次；重排事件输入；1.0/1.00表示同一数 | 规范化后的Method/input语义/结果content Hash及结果字节一致；Raw byte Hash仍保留差异；不同操作时间/实例UUID不纳入此承诺 |
| N08 | Method精度/组合公式、Mapping转换口径或anchor/cutoff变化 | 新方法/定义或输入Manifest Hash，禁止旧Hash别名；旧固定引用继续可复现 |
| C01 | t1现金原D=1在C0可用，新D=2在C1可用；P=10，postclose=9，A=t1 | C0仍Fpre=0.9/R=0；C1重述Fpre=0.8/R=9/8-1=0.125；生成新cutoff逻辑产物，不把C1写回C0 |
| C02 | 原行动ACTIVE在C0；取消revision在C1 | C0仍应用原q；C1完整取消证据使该事件不产生q，但旧物理对象与引用不变 |
| C03 | 同as_of/cutoff/plan/definition_refs，确实在cutoff可用的输入被更正 | 现有Correction revision+1/supersedes规则适用；input/result Hash改变，按前/后方向计算影响区间；旧Bundle固定消费不变 |
| C04 | Correction尝试更改cutoff、plan或Definition refs | 必须拒绝同逻辑Correction，改为新逻辑Snapshot；验证失败无文件/控制面残留 |
| C05 | t1行动更正，窗口含ex_date，追踪return及获授权的adjusted MA/high-low消费者 | 设计期望沿依赖边重算至F2 raw→normalized→score→smoothed→state；更改B3输入不自动关闭B4或认证；无受影响依赖的分区保持Hash |
| C06 | 新版消费后重启，再消费旧/新固定Partition/Snapshot/Bundle | 原14F1/65F2完整payload/Hash和旧引用/字节均不变；不依赖Registry最新默认版本；不能只测内存builtin后声称端到端通过 |

A02/A05的H涉及循环小数，期望应按第5.4节逐步运算再量化；数学分数只是手算基准，测试须给规范十进制Golden，并区分数学相等和量化相等。上述错误标签是设计分类，不声称现有异常码已注册。

## 9. 决策、启动判定与剩余事项

### 9.1 必要决策

| 决策 | 建议与证据缺口 | 启动要求 |
| --- | --- | --- |
| D1：行动范围/收益语义 | 只支持普通现金、普通送转、纯拆分及确证同组cash+bonus；价格连续性，不是total return；未知/配股/特殊拒绝 | 维护者确认白名单与特殊行动的拒绝政策；真实数据集不能忽略不支持事件 |
| D2：Provider语义与完整覆盖 | 当前两Provider为本地UNVERIFIED声明；需要真实字段说明、脱敏样本、每股/税/身份/revision/取消/时间/全量覆盖证据 | 可先提供离线证据；在线核验须另授权，证据不足不做真实来源实施 |
| D3：精度/锚点/参考价 | precision38、half-even、scale18；理论未tick量化Q；固定A/B；P只取前一session真实rawclose，无停牌ffill | 维护者批准数值和受限P政策；适用市场/特殊价另Method版本 |
| D4：PIT/correction | 源披露/可用与平台发布时间分离；迟到新C不得回灌旧C；同identity才Correction | 批准知识cutoff与可用证据规则；保持现有Correction guard |
| D5：版本化 | corporate_action2、adjustment_factor1、Method1、新F1/F2精确版本；旧14/65/固定引用不变 | 批准下一Goal的实际代码与必要生成契约范围；与B4交叉接入须单独授权 |
| D6：派生Manifest承载 | 复用Canonical/DataSnapshot、显式DERIVED直接输入/Method refs及传递真实根血缘；现有类型没有完整承载 | 实施前批准版本化Schema/manifest载荷与Hash兼容设计；不可伪造Raw/ProviderRun或静默改旧Manifest |

### 9.2 判定

- **NO_GO：真实Provider/PIT来源实施、能力认证与正式市场链路启动。** D2/D6未解决，当前字段、日期质量和消费者契约有实证缺口；无法用文档候选字段替代实现事实。
- **CONDITIONAL_GO：下一独立Goal的隔离离线fixture实施。** 必须明确代码/生成契约授权、批准D1/D3/D4/D5/D6，fixture输入自带明确语义/覆盖收据，保留旧契约与认证拒绝。不能把此判定理解为本轮自动开始代码。
- **PREP完成与上述NO_GO不矛盾。** 本轮完成证据、契约和检查即可交付，不等待真实Provider授权、不扩大B1/B2/B4或其他WP。

**BLOCKER（针对后续实施，不使本PREP无限扩张）：** D2真实来源口径/覆盖/历史availability未确认；D6派生血缘承载待批；D1/D3/D4/D5尚未正式批准；当前v1质量与消费者字段不闭合。未知行动、覆盖不足必须保留失败，不为GO放宽政策。

**FOLLOW-UP：** RIGHTS/特殊公式/差异化分红/合股、停牌参考价等后续Method版本；与B4相交的adjusted MA/完整F2接入；B1/B2及完整WP验收、远端CI/合入、真实环境认证由各自Goal处理。本轮不提供这些能力已实现的结论。

**未验证：** 任何新Method、因子、HashGolden、F1/F2新版本、PIT/Correction案例、持久化/迁移、客户端、真实Provider/数据库/`/data`、远端CI、生产发布。历史第8节测试不重复累计，也不作为本轮新复权实现证据。

## 10. 本轮实际文档检查

本节只记录实际执行的本地文档治理检查，不记计划测试为通过。全部命令目录为 `C:\Users\lzq11\.codex\worktrees\f468\Visory`。

| 实际命令 | 结果/退出码 | 验证范围与限度 |
| --- | --- | --- |
| `python scripts/check_ai_assets.py` | `[ai-assets] OK`，exit 0 | AI资产治理；不是复权运行验收 |
| `python scripts/check_visory_baseline.py` | exit 0；633个相对链接、broken=0、imported_secrets=0、启用validation workflow=1 | 当前完整工作树基线/边界/许可证/链接；包含开工已有修改，不全算本Goal成果 |
| `git diff --check` | exit 0；仅既有LF→CRLF提示 | 所有tracked diff空白检查；未跟踪本文另由下项检查，不承诺运行测试 |
| `python C:\Users\lzq11\AppData\Local\Temp\visory-wp0303-b3-prep-20261008-01a11ab3\verify_goal_docs.py` | PASS，exit 0；4文件allowlist、5个本文相对链接/锚点、3个同步文件逆向还原开工字节、其余27项SHA256相同 | 标准库临时审计脚本；本文尾部换行/无trailing whitespace、索引新路由、Unreleased扁平、HEAD未移动；相对开工diff保存为同目录`goal-docs.patch` |

最终状态为20个tracked modified+11个untracked：只比开工新增本文；3个原本dirty文档只加本轮路由/说明。日志为仓库外同目录`check-ai-assets.log`、`check-visory-baseline.log`、`diff-check.log`、`validation-runs.json`、`goal-audit.json`。检查记录入文后再次执行上述检查，收尾不再改变文档内容。

Docs only, tests not run。未运行pytest/ci_gate/Web构建/数据库测试/生成器；本轮无这些实现变更。双语评估：本文是中文平台WP内部设计记录，无对应英文版；INDEX/CHANGELOG/状态只追加中文路由，无需重写README/README_EN或上游英文材料。

## 11. 兼容性、风险与仅撤销本轮增量

没有运行行为、配置、Schema注册、Migration或认证状态变化；所有建议字段/方法需未来实现，旧v1消费者仍由既有门禁拒绝，不能引用本记录解锁。主要风险是把候选字段、空集合、交易所公式、历史fixture成功或本PREP完成误读为Provider认证/B3关闭；第1/3/9节分别明确否定。

本轮新增文档未与正式合同同步生成，属有意范围边界，不是假称实现完成。三个索引/状态/变更记录文件的开工内容完整保留。若要回滚：只删除新增本文并撤销这三个文件中标注本记录的新增行/段，或在确认无后续重叠编辑后使用仓库外保存的**相对开工增量patch**反向应用；不以HEAD整文件覆盖，不使用reset/checkout/stash/clean，不删除开工两个WP-0303文档或任何27项其他成果。开工副本只作核对，不在存在后续编辑时直接整文件恢复。
