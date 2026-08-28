# Visory 契约收敛总纲 v1

状态：Implementation Baseline（C-001至C-013已收敛）
最后更新：2026-08-28

## 1. 文档目的

本文件是Visory跨模块契约的唯一收敛入口。各领域架构文档继续描述业务目标、计算规则和模块边界；本文件负责统一多个模块共同使用的字段、状态、时间、版本、标识、运行和发布语义。

本文落实架构决策 **D-033**，并将 **C-001、C-002、C-003** 固化为MVP实现基线：

- `canonical_id`继续作为确定资产类型上下文中的规范市场代码；
- `entity_key=<asset_type>:<canonical_id>`作为股票、指数、ETF等资产跨域关联的全局唯一键；
- 板块、策略、指标、任务、快照和报告等非资产资源使用各自命名空间ID，不复用`canonical_id`；
- 统一交易日、事件、披露、观察、可用、截止、创建和发布时间字段；
- 时间戳必须带时区，数据库以`timestamptz`保存，A股`trade_date`按`Asia/Shanghai`解释；
- 发布状态、修订类型、质量状态、任务状态、执行阶段和研究质量门禁使用不同字段和枚举；
- `CORRECTION`从发布状态中拆出，作为`revision_kind`；修订对象仍必须单独声明是`PROVISIONAL`还是`CERTIFIED`；
- 正式对象统一携带Schema、Definition、Policy、Revision、Hash和替代关系；
- 禁止继续新增语义不明的裸`status`、`version`、`date`、`timestamp`和`hash`字段；
- C-001是后续身份、存储、数据、Snapshot、Feature、Task、Strategy、FactPack、API和部署契约的前置约束。
- C-002统一资产注册、别名、板块Taxonomy、非资产资源ID和Resolver失败语义；
- C-003统一`/data/daily_stock_analysis/storage/app`、逻辑路径、分区、挂载、原子发布和保留策略。

## 2. 契约地图

| 编号 | 契约 | 状态 | 主要产物 |
| --- | --- | --- | --- |
| C-001 | 基础语义、时间、状态、版本和Hash | 已确认 | 本文第4—9节 |
| C-002 | 实体身份与Resource Reference | 已确认 | 本文第14节Identity Schema、Resolver和Alias规则 |
| C-003 | 物理目录、URI与原子发布 | 已确认 | 本文第15节Storage Root、Mount和Artifact URI |
| C-004 | Provider、Raw与Canonical Data | 已确认 | [实现契约目录第3节](platform-implementation-contract-catalog-v1.md#3-c-004-providerraw与canonical-data) |
| C-005 | Snapshot、能力认证与Correction | 已确认 | [实现契约目录第4节](platform-implementation-contract-catalog-v1.md#4-c-005-snapshot能力认证与correction) |
| C-006 | Indicator与Feature | 已确认 | [实现契约目录第5节](platform-implementation-contract-catalog-v1.md#5-c-006-indicator与feature) |
| C-007 | Task、Run、Attempt、Phase与Artifact | 已确认 | [实现契约目录第6节](platform-implementation-contract-catalog-v1.md#6-c-007-taskrunattemptphase与artifact) |
| C-008 | Strategy、Hikyuu、Prediction与Validation | 已确认 | [实现契约目录第7节](platform-implementation-contract-catalog-v1.md#7-c-008-strategyhikyuuprediction与validation) |
| C-009 | Observation、FactPack、Claim与Evidence | 已确认 | [实现契约目录第8节](platform-implementation-contract-catalog-v1.md#8-c-009-observationfactpackclaim与evidence) |
| C-010 | API、错误、认证与事件流 | 已确认 | [实现契约目录第9节](platform-implementation-contract-catalog-v1.md#9-c-010-api错误认证与事件流) |
| C-011 | 调度、资源、优先级与Checkpoint | 已确认 | [实现契约目录第10节](platform-implementation-contract-catalog-v1.md#10-c-011-调度资源优先级与checkpoint) |
| C-012 | Docker、Secret、备份与恢复 | 已确认 | [实现契约目录第11节](platform-implementation-contract-catalog-v1.md#11-c-012-dockersecret备份与恢复) |
| C-013 | MVP范围、迁移与验收门禁 | 已确认 | [实现契约目录第12节](platform-implementation-contract-catalog-v1.md#12-c-013-mvp范围迁移与验收门禁) |

状态只允许：

```text
待讨论
讨论中
已确认
已废止
```

契约被替代时保留原编号和历史，不复用编号。

## 3. 契约优先级与覆盖规则

发生冲突时按下列顺序解释：

1. 已确认的契约收敛文档；
2. 对应领域的最新Design Approved文档；
3. 机器可校验Schema、OpenAPI和数据库约束；
4. 示例配置和示例Payload；
5. 现有兼容实现。

规则：

- 本文件不能静默改变已确认业务口径；
- 发现冲突时必须记录为契约决策，不以“实现当前就是这样”裁决；
- 机器Schema必须由已确认契约生成或审核，不能反向扩大权限与范围；
- 示例与正文冲突时以正文规范字段为准，并修复示例；
- 旧实现可以在迁移期保留Legacy Adapter，但不能成为新正式数据的第二权威；
- C-004至C-013的实现字段、对象关系和验收不变量集中维护在实现契约目录；本文件继续作为编号、优先级和基础语义入口。

## 4. C-001标识基础语义

### 4.1 `canonical_id`

`canonical_id`表示已经过Identity Resolver确认的市场规范代码，不是所有资源的通用主键。

A股股票示例：

```text
sh600519
sz000001
sz300750
sh688981
```

约束：

- 小写市场前缀；
- A股股票后接六位数字；
- 六码裸码只允许作为用户输入和显示别名；
- 进入持久化、Snapshot、Feature、FactPack、Strategy和Backtest前必须解析；
- Provider原始Symbol另存，不覆盖`canonical_id`；
- 名称、简称、拼音和数据库自增ID不能替代`canonical_id`；
- 在没有`asset_type`上下文时，不能声称`canonical_id`是跨全部资产类型的全局唯一键。

### 4.2 `asset_type`

首批值：

```text
stock
index
etf
convertible_bond
fund
future
fx
commodity
```

v1正式A股策略只允许`stock`，其他枚举存在不代表已经支持交易、回测或数据认证。

枚举规则：

- 小写snake_case；
- 不使用Provider私有类型名；
- 未支持的类型仍可以用于观察数据身份，但必须有Capability状态；
- 新增类型提升Identity Schema Version。

### 4.3 `entity_key`

资产全局唯一键：

```text
entity_key = <asset_type>:<canonical_id>
```

示例：

```text
stock:sh600519
index:sh000001
etf:sh510300
```

约束：

- `entity_key`是派生稳定键，不由Provider提供；
- 分隔符固定为半角冒号；
- 两部分均使用规范化小写；
- 不包含名称、日期、Provider、数据库环境或版本；
- 资产跨表、通用Evidence和通用Snapshot内部优先使用`entity_key`；
- 股票专属API在资源类型已由路径确定时可以继续使用`canonical_id`；
- `entity_key`不替代Security Master中的历史属性和Alias关系。

### 4.4 非资产资源ID

下列对象不使用`entity_key`：

```text
sector_id
taxonomy_id
indicator_id
strategy_id
task_id
attempt_id
data_snapshot_id
feature_snapshot_id
fact_pack_id
research_id
review_id
backtest_run_id
artifact_id
```

每类ID必须：

- 在自己的资源类型中稳定唯一；
- 对客户端视为Opaque，不从字符串位置推断业务含义；
- 不因名称修改、任务重试或Correction而复用；
- 在API中以字符串传输；
- 禁止把数据库自增整数直接暴露为跨系统长期引用；
- ID生成算法和前缀在C-002中确定。

### 4.5 `resource_ref`

跨领域引用非资产资源时使用：

```yaml
resource_ref:
  resource_type: feature_snapshot
  resource_id: fs_019c5f2a-8c34-75cd-a013-4b4ee2b25a48
```

不使用自由字符串`feature_snapshot:fs_019c5f2a-8c34-75cd-a013-4b4ee2b25a48`作为唯一机器结构。字符串表示可以用于日志和页面，但持久契约保存结构化字段。

## 5. C-001时间契约

### 5.1 时间字段

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `trade_date` | `date` | 归属的A股交易日，按Asia/Shanghai解释 |
| `session_date` | `date` | 非A股市场交易时段归属日期，可选 |
| `event_time` | `timestamptz` | 事实或事件实际发生时间 |
| `source_published_at` | `timestamptz` | 原始发布者公开披露时间 |
| `observed_at` | `timestamptz` | Provider或采集器观察到该版本的时间 |
| `ingested_at` | `timestamptz` | 平台完成Raw接收并持久化的时间 |
| `available_at` | `timestamptz` | 该事实在当前PIT契约下最早允许被消费者使用的时间 |
| `cutoff_at` | `timestamptz` | 本次计算冻结的最大可用时间 |
| `created_at` | `timestamptz` | 对象在平台控制面创建时间 |
| `published_at` | `timestamptz` | 对象通过发布门禁并对消费者可见的时间 |
| `updated_at` | `timestamptz` | 可变控制记录最后更新时间，不用于不可变业务事实 |

### 5.2 格式与存储

- PostgreSQL使用`timestamptz`；
- 文件和API使用RFC 3339且必须带`Z`或明确UTC Offset；
- 禁止无时区时间戳；
- A股业务页面默认显示`Asia/Shanghai`；
- 全球事实同时保存`market_timezone`和`session_date`；
- `trade_date`不能由UTC日期截断推导；
- 夏令时市场使用IANA Time Zone，不硬编码固定Offset；
- 排序相同时间时使用稳定ID作为tie-breaker。

示例：

```yaml
trade_date: 2026-08-27
event_time: 2026-08-27T15:00:00+08:00
source_published_at: 2026-08-27T15:35:12+08:00
observed_at: 2026-08-27T16:02:10+08:00
ingested_at: 2026-08-27T16:02:11+08:00
available_at: 2026-08-27T16:02:10+08:00
cutoff_at: 2026-08-27T19:00:00+08:00
created_at: 2026-08-27T19:00:01+08:00
published_at: 2026-08-27T19:00:05+08:00
```

### 5.3 `available_at`

防前视统一判断：

```text
available_at <= cutoff_at
```

规则：

- `available_at`不是文件mtime；
- `available_at`不是当前回填任务的`ingested_at`；
- 实时采集没有更早可靠披露时间时，默认不早于`observed_at`；
- 历史回填必须依据来源披露时间、Provider时间戳或版本化可用规则恢复PIT时间；
- 无法证明历史可用时间的数据不得进入正式历史策略；
- 财报至少区分报告期、公告日、修订公告日和平台可用时间；
- 新闻和公告不得只使用文章正文中描述的事件日期；
- Correction的`available_at`是修订内容可以被使用的时间，不能回写为原始版本时间。

### 5.4 可用时间依据

为防止历史回填伪造精度，建议相关数据对象保存：

```text
availability_basis:
  SOURCE_DISCLOSURE
  PROVIDER_TIMESTAMP
  EXCHANGE_CALENDAR_RULE
  PLATFORM_OBSERVED
  VERSIONED_ASSUMPTION
```

`VERSIONED_ASSUMPTION`必须引用`availability_policy_version`并在页面和回测Manifest披露。

## 6. C-001状态命名空间

### 6.1 禁止裸`status`

新契约不得只定义：

```yaml
status: partial
```

必须指出状态所属命名空间：

```yaml
publication_status: CERTIFIED
quality_status: PARTIAL
```

数据库旧字段可以在迁移期保留，但Adapter必须映射到明确字段。

### 6.2 发布状态

```text
publication_status:
  DRAFT
  PROVISIONAL
  CERTIFIED
  RETIRED
```

| 值 | 含义 |
| --- | --- |
| `DRAFT` | 尚未进入消费者可见范围 |
| `PROVISIONAL` | 已完成基础校验，只允许明确接受临时数据的消费者 |
| `CERTIFIED` | 对声明Capability通过正式门禁 |
| `RETIRED` | 不再作为默认当前版本，但历史引用仍有效 |

`CERTIFIED`可以只认证部分Capability，必须同时携带`certified_capabilities`，不能只看一个全局布尔值。

### 6.3 修订类型

```text
revision_kind:
  INITIAL
  CORRECTION
  REBUILD
  MIGRATION
```

| 值 | 含义 |
| --- | --- |
| `INITIAL` | 首次发布业务版本 |
| `CORRECTION` | 晚到或错误修订形成的新不可变版本 |
| `REBUILD` | 相同业务输入按相同Definition确定性重建 |
| `MIGRATION` | 因Schema或存储迁移重新封装，业务事实未被宣称改变 |

Correction示例：

```yaml
publication_status: CERTIFIED
revision_kind: CORRECTION
revision: 2
supersedes_id: ds_v1
```

这比`publication_status=CORRECTION`更明确，因为修订类型和认证资格是两个独立维度。

### 6.4 数据质量状态

```text
quality_status:
  COMPLETE
  PARTIAL
  FAILED
  UNAVAILABLE
  STALE
```

| 值 | 含义 |
| --- | --- |
| `COMPLETE` | 声明的必需字段、覆盖和规则全部满足 |
| `PARTIAL` | 核心仍可用但存在明确缺口，只允许契约声明的删减消费者 |
| `FAILED` | 数据或校验结果存在错误，禁止作为成功输入 |
| `UNAVAILABLE` | 对应Capability没有可用数据，不等于数值为零 |
| `STALE` | 数据存在但超过允许新鲜度，不自动等同失败 |

Block级状态如`MISSING`、`FALLBACK`、`ESTIMATED`和`FETCH_FAILED`应进入`block_status`或`data_flags[]`，不能扩大顶层质量枚举。

### 6.5 任务状态

```text
task_state:
  ACCEPTED
  QUEUED
  BLOCKED
  LEASED
  RUNNING
  RETRY_WAIT
  SUCCEEDED
  DEGRADED
  FAILED
  CANCELLED
```

规则：

- 只有Task使用`task_state`；
- `BLOCKED`必须保存`blocked_reason_code`和下一次检查条件；
- `DEGRADED`是契约允许的终态，不是任意异常的成功包装；
- `FAILED`和`CANCELLED`不得发布当前正式Result；
- 重试生成新Attempt，不把终态Task重置为`RUNNING`；
- 是否允许同一Task下重试或创建Retry Task由C-007确定。

### 6.6 执行阶段

通用字段：

```text
attempt_phase
phase_started_at
phase_progress
```

回测示例：

```text
VALIDATING_SNAPSHOT
COMPILING_STRATEGY
MATERIALIZING_FEATURES
RUNNING_HIKYUU
VALIDATING_RESULT
PUBLISHING_RESULT
```

规则：

- Phase不是Task State；
- Task可以保持`RUNNING`并多次切换Phase；
- `CONSISTENCY_FAILED`是`failure_code`，不是Task State；
- 研究的`SELF_REVIEW`和数据的`QUALITY_GATE`可以是各自Phase；
- Phase枚举按`task_type`或领域Schema版本管理。

### 6.7 研究质量门禁

```text
research_quality_status:
  PASSED
  QUALITY_BLOCKED
  INSUFFICIENT_EVIDENCE
```

它不代表任务运行成败：

- 一个研究Task可以技术上`SUCCEEDED`，但Research Result为`INSUFFICIENT_EVIDENCE`；
- `QUALITY_BLOCKED`表示报告未通过发布Gate，不能伪装为可用研究结论；
- LLM超时属于Task/Attempt失败或降级，不直接等于证据不足。

## 7. C-001版本与修订

### 7.1 标准字段

| 字段 | 作用 |
| --- | --- |
| `schema_version` | 字段结构、类型、必填性和枚举版本 |
| `definition_version` | 指标、规则、Prompt Profile或策略逻辑版本 |
| `policy_version` | Provider、市场规则、权重、资源或发布政策版本 |
| `revision` | 相同业务身份下的不可变修订序号，从1开始 |
| `content_hash` | 规范内容的确定性摘要 |
| `supersedes_id` | 当前对象直接替代的上一对象ID，可空 |

### 7.2 使用规则

- Schema变化不能只提升`revision`；
- 公式、阈值、Prompt逻辑和计算方向变化提升`definition_version`；
- Provider主备、交易费用、权重限制和发布资格变化提升对应`policy_version`；
- 晚到数据形成新`revision`，不改变旧对象；
- 重新执行但内容完全相同仍生成新Attempt，业务Result是否复用由C-007/C-008决定；
- `supersedes_id`只表示直接替代关系，不表示删除；
- 历史消费者绑定具体ID，不绑定可变的`latest`；
- 展示“最新”必须经过Resolver并返回实际资源ID。

### 7.3 版本格式

建议：

```text
schema_version: 1.0.0
definition_version: 1.2.0
policy_version: provider_policy_cn_a_1.0.0
revision: 2
```

- Schema和Definition使用语义化版本字符串；
- Policy可以使用`<policy_name>_<semver>`；
- `revision`使用正整数；
- 不能使用`latest`、`new`、日期字符串或Git Branch作为正式版本值；
- Git Commit、镜像Digest和依赖Lock Hash另存，不冒充业务版本。

## 8. C-001内容Hash

### 8.1 Hash字段

默认：

```text
hash_algorithm: sha256
content_hash: sha256:<lowercase_hex>
```

### 8.2 规范化

Hash输入必须由对象Schema声明，至少遵守：

- UTF-8；
- Key稳定排序；
- Decimal使用契约精度字符串，不能先转二进制浮点；
- 时间统一转换为同一Instant表示；
- 数组是否排序由字段语义决定，不能统一私自排序；
- 排除`content_hash`自身；
- 排除纯运行字段如日志路径、内存峰值和最后访问时间；
- 是否包含`created_at`、`published_at`由对象Hash Profile明确；
- 大文件保存文件Hash，Manifest保存文件Hash与相对URI；
- Hash Profile变化提升Schema或Hash Profile Version。

### 8.3 Hash分类

禁止所有摘要都叫`hash`。使用明确字段：

```text
raw_content_hash
partition_hash
manifest_hash
definition_hash
run_bundle_hash
result_hash
artifact_hash
```

每类Hash必须说明覆盖的字段集合。

## 9. C-001基础对象信封

不是所有对象都必须机械继承同一巨大Envelope，但正式资源至少可投影为：

```yaml
resource_type: data_snapshot
resource_id: ds_019c5f2a-8c35-7b16-8448-bc82c87af925
schema_version: 1.0.0
revision: 2
revision_kind: CORRECTION
supersedes_id: ds_019c5f2a-8c34-75cd-a013-4b4ee2b25a48
publication_status: CERTIFIED
quality_status: COMPLETE
trade_date: 2026-08-27
cutoff_at: 2026-08-27T19:00:00+08:00
created_at: 2026-08-27T20:32:00+08:00
published_at: 2026-08-27T20:35:00+08:00
hash_algorithm: sha256
content_hash: sha256:<hex>
lineage_refs: []
```

适用规则：

- 不适用字段可以由具体Schema省略，不能写伪造默认值；
- `quality_status`不适用于纯控制命令时不强行添加；
- Task使用`task_state`，不使用`publication_status`；
- Attempt使用`attempt_phase`和执行结果，不冒充业务Result；
- 不可变资源创建后不能修改Hash覆盖范围内字段；
- Current Pointer是独立可变控制记录，不是业务对象本身。

## 10. 跨模块示例

### 10.1 DataSnapshot Correction

```yaml
resource_type: data_snapshot
resource_id: ds_019c5f2a-8c36-79cb-9371-2e0efbb6957a
schema_version: 1.0.0
revision: 2
revision_kind: CORRECTION
supersedes_id: ds_019c5f2a-8c35-7b16-8448-bc82c87af925
publication_status: CERTIFIED
quality_status: COMPLETE
certified_capabilities:
  - backtest_core
trade_date: 2026-08-27
available_at: 2026-08-27T20:31:05+08:00
published_at: 2026-08-27T20:35:00+08:00
manifest_hash: sha256:<hex>
```

### 10.2 回测Task与Attempt

```yaml
task:
  task_id: task_019c5f2a-8c31-7d2e-9e62-9d1147d7a41b
  task_type: BACKTEST_FORMAL
  task_state: RUNNING
  active_attempt_id: attempt_019c5f2a-8c33-7ce9-882c-43a965c39b2d

attempt:
  attempt_id: attempt_019c5f2a-8c33-7ce9-882c-43a965c39b2d
  task_id: task_019c5f2a-8c31-7d2e-9e62-9d1147d7a41b
  attempt_phase: RUNNING_HIKYUU
  phase_progress: 0.63
```

`RUNNING_HIKYUU`不能写入`task_state`，`CONSISTENCY_FAILED`不能写入`attempt_phase`终态。

### 10.3 研究结果

```yaml
task_state: SUCCEEDED
research_quality_status: INSUFFICIENT_EVIDENCE
research_stance: INSUFFICIENT_EVIDENCE
```

表示研究流程正常完成，但证据不支持形成方向性研究倾向；它不是技术失败。

## 11. Legacy迁移

### 11.1 字段映射

旧对象存在`status`时必须根据资源类型迁移：

| 旧资源 | 旧字段 | 新字段 |
| --- | --- | --- |
| 数据快照 | `status=certified` | `publication_status=CERTIFIED` |
| 数据块 | `status=partial` | `quality_status=PARTIAL`或`block_status=PARTIAL` |
| 任务 | `status=processing` | `task_state=RUNNING` |
| 回测 | `status=running_hikyuu` | `task_state=RUNNING` + `attempt_phase=RUNNING_HIKYUU` |
| 研究 | `status=quality_blocked` | `research_quality_status=QUALITY_BLOCKED` |

### 11.2 兼容期

- 新写入只使用新字段；
- 旧API可以由Adapter生成Legacy `status`；
- Adapter必须按资源类型映射，不能实现一个全局字符串转换表；
- 双读期间记录新旧解析差异；
- 冲突时不自动选择“更成功”的状态；
- 正式消费者切换后再按API弃用周期移除旧字段。

### 11.3 历史时间

- 无法恢复的`available_at`保持空并标记`availability_unknown`；
- 不把数据库`created_at`批量复制为历史披露时间；
- Legacy报告可以继续显示，但不能在缺少PIT时间时升级为正式回测输入；
- 迁移脚本必须可重复运行并生成差异报告。

## 12. 机器校验要求

C-001落地后至少提供：

- 公共枚举定义；
- 时间字段Schema和时区校验；
- `entity_key`构造与解析器；
- `resource_ref`Schema；
- 状态字段互斥和组合校验；
- 版本字符串与Revision校验；
- 确定性Hash测试向量；
- Legacy字段映射测试；
- API序列化和数据库往返测试；
- Golden Payload。

必须拒绝：

1. 无时区Timestamp；
2. `entity_key`与`asset_type/canonical_id`不一致；
3. 新Schema使用裸`status`；
4. `publication_status=CORRECTION`；
5. `revision_kind=CORRECTION`但没有`supersedes_id`；
6. `revision<1`；
7. `content_hash`格式不正确；
8. Task把领域Phase写入`task_state`；
9. 历史事实用本次回填时间冒充`available_at`；
10. 字段不适用时写零、空字符串或当前时间伪装有效值。

## 13. C-001验收标准

1. 股票、指数和ETF可以使用相同`canonical_id`命名规则但通过`entity_key`全局隔离；
2. 股票专属API仍可使用现有`canonical_id`，不破坏D-022；
3. 所有正式Timestamp带时区，`trade_date`按市场日历解释；
4. 防前视统一使用`available_at <= cutoff_at`；
5. 发布、修订、质量、任务、执行阶段和研究Gate没有共用裸`status`；
6. Correction对象可以同时明确表示已认证和属于修订版本；
7. 回测领域阶段不会污染通用Task状态机；
8. 技术成功但证据不足的研究不会被标记为任务失败；
9. Schema、Definition、Policy和Revision的变化原因可区分；
10. Hash算法、规范化字段和覆盖范围可查询；
11. Legacy数据不会因迁移被伪造为具备完整PIT血缘；
12. 后续C-002至C-013全部复用本契约，不再定义冲突的同名字段。

## 14. C-002实体身份与Resource Reference

### 14.1 非资产资源ID

公开资源ID统一使用：

```text
<resource_prefix>_<uuidv7>
```

示例：

```text
task_019c5f2a-8c31-7d2e-9e62-9d1147d7a41b
attempt_019c5f2a-8c32-7485-8c0d-6e08fbfd9564
ds_019c5f2a-8c33-7ce9-882c-43a965c39b2d
fs_019c5f2a-8c34-75cd-a013-4b4ee2b25a48
```

首批前缀：

| 资源 | 前缀 |
| --- | --- |
| Task / Attempt | `task` / `attempt` |
| DataSnapshot / FeatureSnapshot / ObservationSnapshot | `ds` / `fs` / `obs` |
| FactPack / Research / Review | `fact` / `research` / `review` |
| Strategy / BacktestRun / Prediction | `strategy` / `backtest` / `prediction` |
| Artifact / Report / ProviderRun | `artifact` / `report` / `prun` |
| Sector / Taxonomy / Indicator | `sector` / `taxonomy` / `indicator` |
| RawObject / CanonicalPartition / FeaturePartition | `raw` / `cpart` / `fpart` |
| FactBlock / Claim / WatchCondition / QualityReport | `fblock` / `claim` / `watch` / `quality` |
| Request / Checkpoint / Backup / Deployment | `request` / `checkpoint` / `backup` / `deployment` |

约束：

- UUID部分使用RFC规范小写、带连字符的UUIDv7文本；
- ID由应用层公共生成器生成，数据库以字符串保存并施加唯一约束；
- ID对客户端Opaque，时间排序只允许作为运维便利，业务排序必须显式使用时间字段和ID tie-breaker；
- 重试创建新`attempt_id`，Correction创建新Snapshot ID，名称修改不更换稳定资源ID；
- 数据库内部主键可以另用UUID列，但不得向API暴露另一套长期资源ID；
- 新增前缀必须进入共享枚举和解析测试，不能由单模块私自创造。

### 14.2 资产注册

`asset_identity`是资产身份唯一注册表：

| 字段 | 要求 |
| --- | --- |
| `entity_key` | 主键，`<asset_type>:<canonical_id>` |
| `asset_type` / `canonical_id` | 必填，必须与`entity_key`一致 |
| `exchange` / `market` | 标准枚举，不使用Provider私有值 |
| `currency` / `country` | ISO标准值 |
| `valid_from` / `valid_to` | 身份有效期，右开区间，`valid_to`可空 |
| `list_date` / `delist_date` | 交易生命周期，可空但不得伪造 |
| `identity_status` | `ACTIVE/INACTIVE/DELISTED/QUARANTINED` |
| `schema_version` | 身份Schema版本 |
| `created_at` | 带时区创建时间 |

规则：

- 正式资产事实表必须保存`entity_key`；股票专属投影可冗余`canonical_id`，但两者必须一致；
- 改名、ST、停牌、行业变化不生成新资产身份；
- 退市资产永久保留，历史股票池不得只关联当前活跃证券；
- 指数、ETF等可以注册和用于观察，但`asset_type`存在不等于v1允许交易；
- 身份冲突进入隔离，不允许Last-write-wins。

### 14.3 Alias与Provider Symbol

`asset_alias`最少字段：

```text
alias_id
entity_key
alias_type
namespace
alias_value
normalized_value
valid_from / valid_to
available_at
source_provider / actual_upstream
verification_status
revision
created_at
```

`alias_type`首批包括：

```text
PROVIDER_SYMBOL
BARE_CODE
EXCHANGE_CODE
ISIN
CURRENT_NAME
HISTORICAL_NAME
PINYIN
USER_ALIAS
```

约束：

- Provider Symbol的`namespace`必须精确到Provider和市场，例如`financial_api:cn_stock`；
- 同一`namespace + normalized_value`在重叠有效期内不得映射到两个`entity_key`；
- 名称、拼音和用户别名只用于搜索候选，不直接形成正式事实关联；
- 历史名称与Provider Symbol保留有效期和`available_at`；
- 冲突记录进入Identity Quarantine，修复产生新Revision并保留原记录。

### 14.4 Resolver契约

Resolver输出：

```yaml
resolution_status: RESOLVED
input_namespace: user:stock_route
input_value: "600519"
entity_key: stock:sh600519
canonical_id: sh600519
candidates: []
reason_codes: []
resolver_version: 1.0.0
resolved_at: 2026-08-27T12:00:00+08:00
```

状态只允许：

```text
RESOLVED
AMBIGUOUS
NOT_FOUND
UNSUPPORTED
CONFLICT
INACTIVE
```

- 股票路由已经提供`asset_type=stock`上下文时，可以解析六码裸码；
- 通用搜索遇到多个候选时返回`AMBIGUOUS`和候选列表，禁止按热度或当前名称猜测；
- `CONFLICT`表示注册数据自身矛盾，必须阻断入库；
- `INACTIVE`允许历史查询，但新交易意图默认拒绝；
- Provider Adapter必须使用命名空间解析，不得复制一套代码前缀推断逻辑。

### 14.5 板块和Taxonomy身份

板块不是资产，不使用`canonical_id`：

```text
sector_id
sector_type          # industry / concept / region / style / custom
taxonomy_id
provider_sector_code
display_name
valid_from / valid_to
definition_version
```

- `sector_id`和`taxonomy_id`使用各自前缀UUIDv7；
- `taxonomy_id`代表一个明确分类体系及版本，例如“申万2021一级”；
- 不同Taxonomy中的同名板块不得自动合并；
- 板块成员关系必须按`entity_key + sector_id + valid_from/valid_to + available_at`保存；
- AI只能提出题材/板块关系候选，人工或版本化规则确认后才能进入正式Registry。

### 14.6 Resource Reference

跨域引用统一保存：

```yaml
resource_ref:
  resource_type: feature_snapshot
  resource_id: fs_019c5f2a-8c34-75cd-a013-4b4ee2b25a48
```

数据库可以拆为`resource_type/resource_id`两列。被引用对象不存在、类型不匹配或已经物理损坏时，正式发布必须失败；`RETIRED`对象仍可被历史资源引用。

## 15. C-003物理目录、逻辑URI与原子发布

### 15.1 唯一根目录

```text
VISORY_RUNTIME_ROOT=/data/daily_stock_analysis
APP_STORAGE_ROOT=/data/daily_stock_analysis/storage/app
```

上述是服务器生产值。本地开发必须显式将`VISORY_RUNTIME_ROOT`绑定到仓库外部或已忽略的本地目录，测试使用每用例临时目录。业务Schema、Manifest和`StorageRef`不因环境变化，且不保存`VISORY_RUNTIME_ROOT`的实际绝对值。

规范目录：

```text
/data/daily_stock_analysis/
├── source/daily_stock_analysis/
├── compose/
├── config/
│   ├── app/
│   ├── platform/{providers,hikyuu,strategies,indicators,sectors,global-market}/
│   ├── npm/
│   └── postgres/
├── secrets/{app,postgres,backup}/
├── storage/
│   ├── app/
│   │   ├── raw/
│   │   ├── normalized/
│   │   ├── features/
│   │   ├── observations/
│   │   ├── factpacks/
│   │   ├── results/
│   │   ├── artifacts/
│   │   ├── hikyuu/
│   │   ├── state/
│   │   ├── quarantine/
│   │   └── .staging/
│   ├── postgres/
│   └── npm/{data,letsencrypt}/
├── logs/{app,worker,scheduler,npm,backup}/
├── backups/{postgres,npm,config,manifests,restore-tests}/
└── tmp/{app,worker,export}/
```

旧`/data/daily_stock_analysis/data`、`backtests`、`reports`和`database`只能作为迁移输入，不再作为新写入路径。DuckDB数据库文件属于`storage/app/state`，Hikyuu缓存属于`storage/app/hikyuu`。

### 15.2 逻辑存储引用

PostgreSQL和Manifest不得保存宿主机绝对路径，只保存：

```yaml
storage_backend: local_fs
storage_namespace: app
relative_path: features/domain=market/frequency=1d/year=2026/part-000.parquet
content_hash: sha256:<hex>
media_type: application/vnd.apache.parquet
size_bytes: 123456
```

规则：

- `relative_path`使用`/`，不得以`/`开头，不得含空段、`.`或`..`；
- Resolver只能在配置的`storage_namespace`根内解析；
- 禁止跟随逃离根目录的Symbolic Link；
- API不接收文件路径，下载使用`artifact_id`并做鉴权；
- 迁移或恢复只需重新绑定Namespace根，不修改业务Manifest。

### 15.3 分区模板

```text
raw/provider=<provider>/dataset=<dataset>/ingest_date=YYYY-MM-DD/provider_run_id=<prun_id>/
normalized/dataset=<dataset>/trade_date=YYYY-MM-DD/revision=<n>/
features/domain=<domain>/frequency=1d/indicator_id=<indicator_id>/definition_version=<version>/year=YYYY/
observations/domain=<domain>/trade_date=YYYY-MM-DD/snapshot_id=<obs_id>/
factpacks/type=<type>/trade_date=YYYY-MM-DD/fact_pack_id=<fact_id>/
results/type=backtest/run_id=<backtest_id>/attempt_id=<attempt_id>/
results/type=review/trade_date=YYYY-MM-DD/review_id=<review_id>/
results/type=research/entity_key=<escaped_entity_key>/research_id=<research_id>/
artifacts/type=<type>/year=YYYY/month=MM/artifact_id=<artifact_id>/
hikyuu/data_snapshot_id=<ds_id>/builder_version=<version>/
```

- Provider返回的字符串必须经过白名单映射后才能进入路径段；
- `entity_key`进入路径时使用确定性安全编码，Manifest仍保存原值；
- F1/F2特征按指标/年份批量分区，禁止每股每日一个小文件；
- 正式结果目录包含`manifest.json`，数据库索引和文件Manifest必须相互引用。

### 15.4 原子发布协议

```text
Worker申请Attempt和租约
  → 在storage/app/.staging/<attempt_id>/写入
  → Schema/行数/主键/覆盖/PIT/账本校验
  → 计算文件Hash与Manifest Hash
  → fsync文件和目录
  → 同一文件系统原子rename到最终目录
  → PostgreSQL事务写入Artifact/Result索引和Current Pointer
  → 发布成功事件
```

失败语义：

- 校验失败：目录移动到`quarantine/<attempt_id>`，Task不得成功；
- Rename失败：数据库不得发布；
- Rename成功而数据库事务失败：留下Orphan，由Sweeper按Manifest识别和重试注册，消费者不可见；
- 数据库索引存在但文件缺失/Hash不符：资源标记损坏并阻断消费，禁止降级为成功；
- Correction写新目录和新ID，永不覆盖旧目录；
- `.staging`必须与最终`storage/app`处于同一文件系统。

### 15.5 容器挂载与权限

| 运行单元 | 读 | 写 |
| --- | --- | --- |
| Platform API | 已发布Artifact和State | 仅会话/小型State；不写Raw/Feature/Result |
| Scheduler | Manifest/任务元数据 | PostgreSQL控制记录；不直接写文件事实 |
| Worker | 所需输入 | `storage/app`业务目录和Staging |
| PostgreSQL | 无应用文件 | 仅`storage/postgres` |
| NPM | 无应用文件 | 仅`storage/npm` |
| Backup | 被备份目录只读 | `backups`写 |

容器使用固定非root UID/GID；不把`/data`或`VISORY_RUNTIME_ROOT`整体挂入单个容器；Secret按需只读挂载。

### 15.6 保留与清理

```text
PINNED       # 法规/审计/正式引用，禁止自动删除
AUDIT        # 按审计周期保留
REBUILDABLE  # 可由固定输入确定性重建
CACHE        # 可删除并重建
TEMP         # 短期Staging
QUARANTINE   # 失败或冲突，限期保留供诊断
```

- Raw、Snapshot Manifest、正式Strategy、Prediction、Validation、Backtest Result和Audit Event默认`PINNED`或`AUDIT`；
- 被正式资源引用的Feature、FactPack和Artifact自动提升为`PINNED`；
- Hikyuu缓存、Preview结果和F3未引用特征可以是`CACHE/REBUILDABLE`；
- 清理前计算引用闭包，先输出Dry-run清单，再由owner确认策略执行；
- Sweeper只清理过期Staging、Orphan、Cache和达到期限的Quarantine，不触碰未知目录；
- 每次清理保存任务、规则版本、目标、释放空间和失败项审计。

## 16. C-002/C-003验收标准

1. 任意正式资产事实都能通过`entity_key`唯一关联资产注册表；
2. Provider Symbol、历史名称和裸码不会绕过Namespace和有效期解析；
3. 歧义、冲突、未找到和未支持有不同机器错误语义；
4. 非资产资源ID前缀和UUIDv7格式可由共享Schema校验；
5. 板块同名不会跨Taxonomy静默合并；
6. 所有新业务文件只写`storage/app`，没有第二套正式根；
7. 数据库不保存宿主机绝对路径，恢复后Namespace可以重新绑定；
8. API不能通过用户输入路径读取任意文件；
9. Worker发布满足同文件系统Staging、校验、Hash、原子Rename和数据库事务顺序；
10. 任一步失败都不会产生可查询的半成品；
11. 容器只获得职责需要的最小挂载；
12. 清理任务不能删除任何正式引用闭包内对象。

## 17. C-004至C-013实现入口

C-004至C-013已在[平台实现契约目录 v1](platform-implementation-contract-catalog-v1.md)中收敛，覆盖Provider、Snapshot、Feature、Task、Strategy/Hikyuu、FactPack/Evidence、API/Auth、调度、部署和MVP门禁。进入编码阶段后，Schema、Migration、OpenAPI和Golden Payload必须由该目录生成或审查，不再逐模块重新发明同名字段。

## 18. 参考资料

- [Visory架构索引](README.md)
- [A 股数据平台与 Canonical Data Contract v1](data-platform-and-canonical-contract.md)
- [A 股 Feature Store 与指标注册中心架构 v1](feature-store-architecture.md)
- [Fleur-Lite 回测运行与结果一致性架构](fleur-lite-backtest-runtime.md)
- [A 股主平台模块化单体、API、任务与权限架构 v1](platform-shell-api-task-permission-architecture.md)
- [A 股分层个股研究与 StockResearchFactPack 架构 v1](stock-research-architecture.md)
- [DSA A 股收盘复盘 FactPack 架构 v1](dsa-close-review-fact-pack.md)
- [A 股平台 Docker、Cloudflare、NPM 与访问安全架构 v1](docker-cloudflare-npm-deployment-architecture.md)
- [平台实现契约目录 v1](platform-implementation-contract-catalog-v1.md)
