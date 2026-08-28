# Visory 实现契约目录 v1

状态：Implementation Baseline

最后更新：2026-08-28

## 1. 目的与适用范围

本文是Claude Code或Codex实施Visory时使用的跨模块字段目录，承接[Visory契约收敛总纲 v1](platform-contract-convergence-v1.md)的C-004至C-013。业务公式、页面交互和算法细节仍以对应领域文档为准；跨模块对象、字段、状态、引用、失败语义和验收门禁以本文为准。

本文定义的是目标契约，不表示当前代码已经实现。实现时必须先建立共享Schema与Golden Payload，再迁移现有SQLite、内存任务和兼容API。

## 2. 契约登记模板

每个可持久化或跨进程对象必须在代码的Contract Registry中登记：

| 元素 | 必填内容 |
| --- | --- |
| `contract_id` | `C-xxx/ObjectName` |
| `owner_module` | 唯一写入责任模块 |
| `producer` | 允许创建对象的服务/Worker |
| `consumers` | 允许读取的模块 |
| `schema_version` | 字段与类型版本 |
| `business_key` | 同一业务对象的唯一键 |
| `resource_id_field` | 对外Opaque ID |
| `time_semantics` | trade/event/available/cutoff等适用字段 |
| `version_semantics` | definition/policy/revision适用字段 |
| `quality_semantics` | 质量状态、能力和失败门禁 |
| `lineage_fields` | 上游对象引用与Hash |
| `storage_profile` | PostgreSQL/Parquet/JSON及逻辑路径 |
| `retention_class` | PINNED/AUDIT/REBUILDABLE/CACHE等 |
| `compatibility` | 向后兼容和弃用策略 |
| `golden_payloads` | 最少成功、降级、失败、Correction样例 |

公共约束来自C-001至C-003：

- 资产关系使用`entity_key`；
- 资源ID使用`<prefix>_<uuidv7>`；
- 时间戳使用带时区RFC 3339/PostgreSQL `timestamptz`；
- 防前视统一为`available_at <= cutoff_at`；
- 禁止裸`status/version/date/timestamp/hash`；
- 文件引用使用`storage_backend + storage_namespace + relative_path`；
- 正式资源不可变，Correction发布新Revision和新资源ID。

### 2.1 契约族责任矩阵

| 契约 | Owner Module | Producer | 正式消费者 | PostgreSQL控制面 | 文件数据面 | 默认保留 |
| --- | --- | --- | --- | --- | --- | --- |
| C-002 Identity | Identity | Identity Import/Resolver | 全部资产模块 | Identity/Alias/Taxonomy | 导入差异Artifact | PINNED |
| C-003 Storage/Artifact | Artifact | Durable Worker | API/Backup/全部结果模块 | Artifact/Storage Namespace | `storage/app` | 按Retention Class |
| C-004 Provider/Canonical | Data Platform | Provider/Normalization Worker | Snapshot Builder | Registry/Run/Partition索引 | Raw/Normalized Parquet | Raw PINNED |
| C-005 DataSnapshot | Data Platform | Certification Worker | Feature/Review/Research/Backtest | Snapshot/Capability/Pointer | Manifest | PINNED |
| C-006 Feature | Feature | Feature Worker | Observation/FactPack/Strategy | Definition/Run/Snapshot索引 | Feature Parquet/Manifest | F1/F2 PINNED或AUDIT |
| C-007 Task/Attempt | Task | API/Scheduler/Worker | Operations/各领域模块 | Task/Attempt/Lease/Event | Checkpoint/Diagnostic Artifact | AUDIT |
| C-008 Strategy/Backtest | Strategy/Backtest | Compiler/Hikyuu Worker | 页面/Review/Validation | Spec/Run/Prediction索引 | Run Result/Manifest | Formal PINNED |
| C-009 Observation/Fact | Observation/Review/Research | Observation/AI Worker | 页面/Strategy（仅显式Feature） | Snapshot/Claim/Evidence索引 | FactPack/Report | 正式引用PINNED |
| C-010 API/Auth/SSE | Platform/Auth | Platform API | React/CLI/Bot | Session/Idempotency/Event | 导出Artifact | Session按安全Policy |
| C-011 Schedule/Resource | Task/Ops | Scheduler/Worker | Operations | Schedule/Budget/Checkpoint索引 | Checkpoint | AUDIT或TEMP |
| C-012 Deploy/Backup | Operations | Deploy/Backup Worker | owner/恢复流程 | Deployment/Backup索引 | Backup/Restore Manifest | AUDIT/PINNED |
| C-013 MVP Gate | Architecture/QA | CI/验收流程 | owner/Release | 验收证据索引 | Golden/Benchmark/Restore Artifact | AUDIT |

跨模块对象只能由Owner Module写入。消费者需要新的派生字段时，应请求Owner扩展契约或创建自己的派生对象，不能直接更新上游表。

## 3. C-004 Provider、Raw与Canonical Data

### 3.1 对象关系

```text
ProviderDefinition
  └── ProviderCapability
        └── ProviderPolicy(dataset级)
              └── ProviderRun
                    └── RawObject
                          └── CanonicalPartition
```

### 3.2 ProviderDefinition

| 字段 | 类型 | 要求 |
| --- | --- | --- |
| `provider_id` | string | 稳定小写ID，如`a_stock_data`、`financial_api` |
| `display_name` | string | 仅展示 |
| `adapter_name` | string | 受控Adapter注册名，禁止任意Import Path |
| `adapter_version` | semver | 必填 |
| `provider_kind` | enum | `AGGREGATOR/DIRECT/FILE/INTERNAL` |
| `enabled` | bool | 控制面状态，不进入事实Hash |
| `credential_ref` | string/null | Secret引用，不保存密钥值 |
| `created_at/updated_at` | timestamptz | 控制面时间 |

聚合源必须保存`actual_upstream`。页面可以展示Provider名称，但任何Canonical事实都必须追溯到实际原始上游和Raw Hash。

### 3.3 ProviderCapability与ProviderPolicy

`ProviderCapability`最少字段：

```text
provider_id
dataset_id
market
frequency
supported_fields[]
history_start
freshness_sla_seconds
rate_limit_profile
provider_capability_status
checked_at
```

`provider_capability_status`：`AVAILABLE/DEGRADED/UNAVAILABLE/UNVERIFIED`。

`ProviderPolicy`是数据集级策略：

```text
provider_policy_id
dataset_id
policy_version
primary_provider_id
supplemental_provider_ids[]
allowed_merge_mode
fallback_triggers[]
field_authority_map{}
conflict_tolerance{}
freshness_sla_seconds
required_quality_rules[]
effective_from / effective_to
```

主备优先级必须按`dataset_id`配置，不能存在全平台通用主源顺序。首版合并模式仅允许：

| 模式 | 语义 |
| --- | --- |
| `REPLACE_PARTITION` | 主源分区失败后，由补充源独立生成新分区 |
| `APPEND_DISJOINT` | 两来源负责不重叠的实体/日期，并保存边界 |
| `ENRICH_FIELDS` | 只补充Policy声明的非权威字段，不覆盖权威字段 |
| `COMPARE_ONLY` | 仅交叉校验，不进入Canonical值 |

禁止未声明的逐行混合、平均冲突值和Last-write-wins。

### 3.4 ProviderRun

```text
provider_run_id
provider_id / actual_upstream
dataset_id / capability
request_fingerprint
provider_policy_version
task_id / attempt_id
started_at / finished_at
observed_schema_hash
row_count / byte_count
run_outcome
failure_code / failure_detail_redacted
raw_object_refs[]
```

`run_outcome`只允许`SUCCEEDED/DEGRADED/FAILED/CANCELLED`，不替代Task State。`request_fingerprint`不能包含Token、Cookie或个人配置明文。

### 3.5 RawObject

```text
raw_object_id
provider_run_id
provider_id / actual_upstream
dataset_id
request_fingerprint
observed_at / ingested_at
source_published_at
media_type / compression
storage_ref
raw_content_hash
byte_count
provider_schema_version
retention_class=PINNED
```

Raw只追加、不改写、不删源字段、不保存请求密钥。HTTP失败正文可以保存到受控诊断Artifact，但必须脱敏。

### 3.6 DatasetDefinition与CanonicalPartition

`DatasetDefinition`：

```text
dataset_id
schema_version
entity_scope
frequency
primary_key_fields[]
required_fields[]
optional_fields[]
field_types{}
units{}
enum_domains{}
time_semantics{}
null_semantics{}
partition_template
quality_rule_ids[]
owner_module
```

`CanonicalPartition`：

```text
canonical_partition_id
dataset_id / schema_version
partition_key{}
revision / revision_kind / supersedes_id
provider_policy_version
provider_run_refs[] / raw_object_refs[]
min_available_at / max_available_at
row_count / distinct_entity_count
storage_ref
partition_hash / schema_hash
quality_status / quality_report_id
created_at / published_at
```

Canonical行情、身份、日历、公司行动、财务和状态数据的字段定义见[A股数据平台与Canonical Data Contract v1](data-platform-and-canonical-contract.md)。`entity_key + trade_date`等业务主键必须由`DatasetDefinition`明确，不能由Parquet文件顺序暗示。

### 3.7 C-004门禁

必须拒绝：身份未解析、单位未知、主键重复、时区丢失、权威字段被补充源覆盖、Raw缺失、Hash不符、Provider实际来源未知、历史数据`available_at`无依据却进入正式策略。

## 4. C-005 Snapshot、能力认证与Correction

### 4.1 DataSnapshot

```text
data_snapshot_id
schema_version
trade_date
cutoff_at
provider_policy_version
security_master_ref
trading_calendar_ref
partition_refs[]
quality_report_id
publication_status
quality_status
certified_capabilities[]
missing_capabilities[]
revision / revision_kind / supersedes_id
available_at / created_at / published_at
manifest_hash / content_hash
```

`partition_refs[]`每项必须含`dataset_id`、`canonical_partition_id`、`partition_hash`、日期范围、行数和Storage Reference。Snapshot只引用已发布、Hash验证成功的Canonical Partition。

### 4.2 Capability认证

首批能力：

```text
identity_core
calendar_core
backtest_core
market_observation
sector_observation
capital_observation
financial_research
news_research
global_observation
```

每项认证记录：

```text
capability_id
capability_certification_status  # CERTIFIED/PROVISIONAL/UNAVAILABLE/STALE
required_datasets[]
quality_rule_results[]
coverage{}
freshness{}
reason_codes[]
certified_at
```

顶层`publication_status=CERTIFIED`只表示至少一个声明能力通过，消费者仍必须检查所需Capability。

### 4.3 ConsumerRequirement

每个正式消费者注册：

```text
consumer_id
consumer_version
required_capabilities[]
optional_capabilities[]
accepted_publication_statuses[]
accepted_quality_statuses[]
max_staleness{}
missing_data_policy
```

Formal Backtest默认只接受`publication_status=CERTIFIED`且`backtest_core=CERTIFIED`。页面可以显式接受Provisional，但必须展示状态和缺口。

### 4.4 Current Pointer与Correction

`snapshot_current_pointer`是唯一可变映射：

```text
pointer_scope
trade_date
capability_id
data_snapshot_id
updated_at
updated_by_task_id
previous_snapshot_id
```

发布顺序：创建不可变Correction → 完成全部Gate → 原子更新Pointer。历史Run始终绑定具体Snapshot ID，不随Pointer变化。Correction的`available_at`不能回写到原版本时间。

### 4.5 Snapshot状态组合

合法示例：

```text
PROVISIONAL + PARTIAL + market_observation:PROVISIONAL
CERTIFIED   + COMPLETE + backtest_core:CERTIFIED
CERTIFIED   + PARTIAL  + backtest_core:CERTIFIED, news_research:UNAVAILABLE
RETIRED     + COMPLETE + 历史仍可引用
```

`FAILED`对象不得发布，`PARTIAL`不能自动解释为不可用，必须由Capability和ConsumerRequirement共同裁决。

## 5. C-006 Indicator与Feature

### 5.1 IndicatorDefinition

```text
indicator_id
name / domain / frequency
schema_version / definition_version
formula_type                 # SQL/PYTHON_BUILTIN/HIKYUU_BUILTIN/COMPOSITE
formula_ref / parameters_schema
input_dataset_refs[]
input_indicator_refs[]
lookback_requirement
warmup_requirement
output_type / unit / precision
null_policy / winsorize_policy / normalization_policy
availability_rule
owner_module
definition_hash
publication_status
```

禁止把任意Python源码、网络调用或动态Import写入Definition。复杂实现必须注册为受控Builtin并固定代码版本。

### 5.2 FeatureRow与FeaturePartition

Feature逻辑行最少字段：

```text
entity_key or aggregate_key
trade_date
indicator_id / definition_version
value
value_type / unit
available_at
data_snapshot_id
calculation_run_id
quality_status / data_flags[]
```

FeaturePartition：

```text
feature_partition_id
indicator_id / definition_version
domain / frequency
partition_key{}
data_snapshot_id
cutoff_at
row_count / null_count / coverage
min_date / max_date
storage_ref
partition_hash / schema_hash
quality_status
revision / supersedes_id
```

### 5.3 FeatureSnapshot与FeatureBundle

```text
feature_snapshot_id
data_snapshot_id
cutoff_at
indicator_definition_refs[]
feature_partition_refs[]
dependency_dag_hash
publication_status / quality_status
certified_capabilities[]
revision / revision_kind / supersedes_id
manifest_hash
```

`FeatureBundle`是消费者最小固定输入：

```text
feature_bundle_id
feature_snapshot_id
required_indicator_refs[]
resolved_partition_refs[]
consumer_ref
cutoff_at
bundle_hash
```

正式策略和FactPack引用Bundle或具体Snapshot，不查询“最新指标”。F1/F2长期物化，F3按需缓存；任何正式引用都会把相应分区提升为`PINNED`。

### 5.4 PIT和修订传播

- Feature计算只能读`available_at <= cutoff_at`的数据；
- 修订由依赖DAG计算影响范围，生成新Partition和FeatureSnapshot；
- 原正式Run不重写，可显式创建Rebuild/Compare Run；
- 横截面指标必须保存当日股票池Snapshot，禁止用当前股票池回算历史。

## 6. C-007 Task、Run、Attempt、Phase与Artifact

### 6.1 Task

```text
task_id
task_type / task_schema_version
task_state
priority_class / priority_value
idempotency_key
requested_by / request_source
input_refs[]
requirements{}
active_attempt_id
blocked_reason_code / unblock_condition
created_at / queued_at / terminal_at
cancel_requested_at
failure_code
```

唯一约束：`task_type + idempotency_key + active_window`。重复命令返回已有Task；显式Force必须生成新的Idempotency Key并记录原因。

### 6.2 TaskAttempt与Lease

```text
attempt_id
task_id
attempt_number
attempt_phase / phase_progress
worker_id / worker_capabilities[]
lease_token_hash
leased_at / lease_expires_at / heartbeat_at
started_at / finished_at
checkpoint_ref
resource_usage{}
attempt_outcome
failure_code / retryable
diagnostic_artifact_refs[]
```

- 重试创建新Attempt，旧Attempt不可变；
- Worker写入必须同时验证`attempt_id + lease_token + lease未过期`；
- 租约丢失后旧Worker不得发布；
- Task State与Attempt Phase按C-001分离；
- 取消是协作式的，Worker在安全点检查并保存可恢复Checkpoint。

### 6.3 Task State转换

```text
ACCEPTED → QUEUED → LEASED → RUNNING → SUCCEEDED|DEGRADED|FAILED|CANCELLED
                    ↑            └── RETRY_WAIT → QUEUED
QUEUED|RUNNING → BLOCKED → QUEUED
```

所有状态转换写`task_state_event`：原状态、新状态、原因、操作者/Worker、时间、关联Attempt。非法转换在数据库事务内拒绝。

### 6.4 Artifact

```text
artifact_id
artifact_type
owner_resource_ref
attempt_id
storage_ref
media_type / size_bytes
artifact_hash
schema_version
created_at / published_at
retention_class
visibility                  # PRIVATE/OWNER/INTERNAL
```

日志、诊断、导出、报告和Parquet结果都通过Artifact注册；API只能凭`artifact_id`访问。

## 7. C-008 Strategy、Hikyuu、Prediction与Validation

### 7.1 对象图

```text
StrategySpec → ResolvedStrategySpec → RunBundle → BacktestRun/Attempt
                                        ├── Prediction
                                        ├── OrderIntent → ExecutionResult
                                        └── ValidationResult
```

### 7.2 StrategySpec与ResolvedStrategySpec

StrategySpec字段以[StrategySpec v1](strategy-spec-v1.md)为准，顶层至少含：

```text
strategy_id / strategy_version
schema_version / definition_version
universe_spec
feature_requirements[]
filter_expression
score_expression
selection_policy
entry_policy / exit_policy
risk_rule_refs[]
weight_policy_ref
market_rule_policy_ref
validation_policy_ref
publication_status
definition_hash
```

Resolved版本额外固定：实际Universe Snapshot、FeatureBundle、所有Policy版本、插件代码Hash和Compiler版本。相同输入必须得到相同`resolved_spec_hash`。

### 7.3 RunBundle与BacktestRun

```text
run_bundle_id / run_bundle_hash
run_mode                       # PREVIEW/RESEARCH/FORMAL/PAPER
resolved_strategy_ref
data_snapshot_id / feature_bundle_id
market_rule_policy_version
weight_policy_version
cost_policy_version
hikyuu_adapter_version
hikyuu_version / image_digest / code_commit
random_seed
period_start / period_end
cutoff_policy
resource_budget
```

`BacktestRun`保存逻辑请求和最终发布Attempt：

```text
backtest_run_id
task_id
run_bundle_id / run_bundle_hash
published_attempt_id
result_artifact_refs[]
result_hash
publication_status / quality_status
created_at / published_at
```

Formal Run禁止包含GlobalObservationSnapshot，也禁止Hikyuu Worker联网补数。

### 7.4 Prediction、Execution与Validation

`Prediction`：

```text
prediction_id
backtest_run_id / strategy_ref
entity_key
decision_trade_date
decision_at / cutoff_at
direction / score / rank
target_horizons[]
feature_bundle_id / data_snapshot_id
explanation_components[]
created_at
```

`OrderIntent`：订单生成日期、目标实体、方向、目标数量/权重、原因、有效期和市场规则版本。

`ExecutionResult`：T+1尝试时间、实际价格/数量/费用、未成交数量、状态和拒绝原因。未成交不得伪造成零收益持仓。

`ValidationResult`：

```text
validation_id
prediction_id
validation_kind             # DIRECTION/TRADEABLE_RETURN/RISK/CALIBRATION
horizon
validation_trade_date
validation_data_snapshot_id
realized_value
expected_value
outcome
methodology_version
available_at / created_at
```

T日预测、T+1执行、T+H验证必须分别持久化，可由Validation反查到Prediction、RunBundle、Feature、Data和Raw。

### 7.5 Hikyuu结果门禁

必须校验：现金账本平衡、持仓数量、T+1可卖、涨跌停拒绝、费用只计一次、NAV连续、交易/持仓一致、日期范围、基准口径、结果Hash、同Bundle确定性。Preview近似结果不得冒充Formal。

## 8. C-009 Observation、FactPack、Claim与Evidence

### 8.1 分层

```text
Canonical/Feature事实
  → ObservationSnapshot（客观观察）
  → FactPack（面向场景的事实包）
  → AI Analysis（观点）
  → Claim ↔ Evidence（可核验结论）
  → Report（投影）
```

### 8.2 ObservationSnapshot

```text
observation_snapshot_id
observation_domain
trade_date / cutoff_at
data_snapshot_id / feature_snapshot_id
view_definition_refs[]
event_rule_refs[]
provider_list_refs[]
block_manifest[]
publication_status / quality_status
capability_certifications{}
revision / supersedes_id
manifest_hash
```

市场/板块页面只展示客观指标、独立榜单和规则事件，不生成平台统一热度评分。Strategy显式引用后才在策略域产生可回测分数。

### 8.3 FactPack与FactBlock

```text
fact_pack_id
fact_pack_type                 # MARKET_CLOSE/STOCK_RESEARCH
subject_ref                    # trade_date或entity_key
trade_date / cutoff_at
data_snapshot_id / feature_snapshot_id
observation_snapshot_refs[]
block_refs[]
publication_status / quality_status
missing_blocks[]
revision / supersedes_id
manifest_hash
```

FactBlock：

```text
block_id / block_type
fact_pack_id
schema_version / definition_version
storage_ref
row_count / coverage
quality_status / data_flags[]
lineage_refs[]
content_hash
```

缺失必须显式表达，不能用0、空数组或LLM猜测填补事实。

### 8.4 Claim与Evidence

```text
claim_id
analysis_resource_ref
claim_type
claim_text
stance / confidence
evidence_refs[]
support_status                 # SUPPORTED/PARTIAL/CONTRADICTED/UNSUPPORTED
as_of / cutoff_at
created_at
```

Evidence Reference：

```text
evidence_id
evidence_type                  # FACT_BLOCK/RAW_OBJECT/ANNOUNCEMENT/NEWS/EXTERNAL
resource_ref
locator                       # row key、字段、页码或片段定位
content_hash
source_published_at / available_at
provider / actual_upstream
```

外部证据必须保存URL、获取时间、发布者、标题、内容Hash和引用定位；报告只呈现短摘录，不把网页全文复制为平台事实。

### 8.5 AI Result

AI结果必须固定`fact_pack_id`、Prompt Profile/版本、模型提供方/模型标识、参数、输入Hash、输出Hash、Claim列表、自查结果和研究质量状态。模型失败不改变FactPack；重新生成创建新Attempt和新Result。

## 9. C-010 API、错误、认证与事件流

### 9.1 成功响应

```json
{
  "data": {},
  "meta": {
    "request_id": "req_...",
    "schema_version": "1.0.0",
    "generated_at": "2026-08-27T12:00:00+08:00",
    "data_snapshot_id": null,
    "warnings": []
  }
}
```

列表额外使用：

```json
{"page":{"cursor":null,"next_cursor":null,"limit":50,"has_more":false}}
```

游标必须签名或Opaque，不能把内部SQL位置暴露给客户端。时间序列排序字段和tie-breaker固定。

### 9.2 错误响应

```json
{
  "error": {
    "code": "SNAPSHOT_CAPABILITY_MISSING",
    "message": "当前快照不满足正式回测能力",
    "details": {},
    "retryable": false,
    "request_id": "req_..."
  }
}
```

稳定错误域：

```text
AUTH_* / IDENTITY_* / VALIDATION_* / PROVIDER_* / SNAPSHOT_*
FEATURE_* / TASK_* / STRATEGY_* / BACKTEST_* / RESEARCH_*
ARTIFACT_* / RATE_LIMITED / INTERNAL_ERROR
```

HTTP映射：400语法/字段，401未认证，403无权限，404资源不存在，409状态/幂等冲突，422业务契约不满足，429限流，503依赖暂不可用。响应不得包含堆栈、路径、SQL或Secret。

### 9.3 Command幂等

创建Task的POST请求支持`Idempotency-Key`。同Owner、端点和规范请求Hash在有效期内：相同Payload返回原Task，不同Payload返回409。禁止由前端轮询重复创建任务。

### 9.4 Auth Session与Turnstile

```text
session_id
owner_id
session_token_hash
created_at / expires_at / last_seen_at
ip_hash / user_agent_hash
revoked_at / revoke_reason
```

- 公网v1只有唯一owner密码；密码只保存Argon2id Hash；
- 登录必须先服务端调用Cloudflare Turnstile Siteverify，再校验密码；
- Turnstile Token一次性、短时有效，并校验hostname和action；
- Cookie为`HttpOnly + Secure + SameSite=Lax/Strict`，登录/登出/敏感Command使用CSRF防护；
- API不得信任客户端传入的“Turnstile已通过”布尔值；
- 登录失败统一文案，按IP/会话指纹限流并写安全审计。

### 9.5 SSE事件

```text
event_id
event_type
resource_ref
task_id / attempt_id
sequence
occurred_at
payload_schema_version
payload
```

事件类型至少包括`task.state_changed`、`task.phase_progress`、`snapshot.published`、`result.published`、`alert.raised`。客户端通过`Last-Event-ID`恢复；事件只作通知，最终状态以查询API为准。

## 10. C-011 调度、资源、优先级与Checkpoint

### 10.1 ScheduleDefinition

```text
schedule_id
schedule_version
task_type
calendar_id
timezone=Asia/Shanghai
trigger_rule
trade_day_only
input_resolver
priority_class
resource_budget_id
misfire_policy
enabled
```

盘后主链固定从交易日16:00开始，细节见[盘后数据采集与Snapshot发布SLA v1](data-ingestion-and-snapshot-sla.md)。不得用UTC Cron直接表达A股业务时间而不声明时区和交易日历。

### 10.2 优先级

```text
P0_DATA_CERTIFICATION
P1_FORMAL_SIGNAL
P2_MARKET_REVIEW
P3_USER_INTERACTIVE
P4_RESEARCH
P5_PREVIEW_AND_MAINTENANCE
```

同级再按`priority_value + queued_at + task_id`排序。单重Worker起步；资源门禁不能只靠队列顺序，还要检查Memory/CPU/Disk预算和互斥标签。

### 10.3 ResourceBudget

```text
resource_budget_id / policy_version
max_cpu_cores
max_memory_mb
max_wall_seconds
max_temp_bytes
max_output_bytes
max_provider_calls
max_llm_calls / max_llm_tokens
checkpoint_interval_seconds
```

超预算必须产生稳定失败码或契约允许的降级结果，禁止静默删减Formal回测区间。

### 10.4 Checkpoint

```text
checkpoint_id
task_id / attempt_id
phase
sequence
resume_token_hash
input_hash
storage_ref
checkpoint_hash
created_at
expires_at
```

恢复前必须验证任务输入、代码/Definition版本和Checkpoint Hash。Hikyuu引擎不能安全续跑时，应从确定的阶段边界重启Attempt，不伪装精确续跑。

## 11. C-012 Docker、Secret、备份与恢复

### 11.1 配置分类

| 类别 | 位置 | 规则 |
| --- | --- | --- |
| 无密钥模板 | 仓库`.env.example`和Compose模板 | 可版本控制 |
| 运行配置 | 生产`/data/daily_stock_analysis/config`；本地`${VISORY_RUNTIME_ROOT}/config` | 不包含凭据 |
| Secret | 生产`/data/daily_stock_analysis/secrets`；本地`${VISORY_RUNTIME_ROOT}/secrets` | 0600、按容器只读挂载；本地禁止复制生产Secret |
| 业务数据 | `storage/app` | 按C-003原子发布 |
| 控制数据库 | `storage/postgres` | 仅PostgreSQL容器访问 |
| NPM状态 | `storage/npm` | 与应用隔离 |

环境变量只保存Secret文件路径或非敏感开关；日志、诊断、Compose Inspect和备份清单不得输出Secret值。

### 11.2 DeploymentManifest

```text
deployment_id
deployed_at
git_commit
image_digests{}
compose_hashes{}
config_hashes{}
schema_migration_version
contract_catalog_version
host_profile_redacted
preflight_result_ref
deployed_by
```

上线必须使用镜像Digest或固定版本，执行数据库迁移、目录权限、健康检查、Cloudflare/NPM链路、Turnstile、源站直连拒绝和备份预检。

### 11.3 BackupManifest

```text
backup_id
started_at / completed_at
backup_scope
postgres_dump_ref
app_manifest_refs[]
config_archive_ref
npm_archive_ref
encryption_profile
file_hashes[]
source_deployment_id
result
```

RPO/RTO基线：PostgreSQL每日全备并在重要迁移前额外备份；正式业务对象按Manifest增量备份；目标RPO 24小时、RTO 4小时。若个人平台需要更严格指标，提升BackupPolicy版本。

### 11.4 RestoreManifest

恢复必须在隔离目录或恢复测试环境执行：验证Hash → 恢复PostgreSQL → 绑定Storage Namespace → 校验引用闭包 → 抽样读取Parquet → 重建一个Hikyuu Cache → 登录和API Smoke。RestoreManifest保存每步结果、缺失对象和最终判定。仅“备份命令退出0”不算恢复成功。

## 12. C-013 MVP范围、迁移与验收门禁

### 12.1 MVP包含

1. 股票身份、Alias、交易日历和Canonical核心数据；
2. 16:00采集、Provisional/Certified/Correction和质量页面；
3. F1/F2核心Feature；
4. 大盘结构、市场宽度、情绪、资金证据、板块和热点客观展示；
5. DSA收盘FactPack、AI复盘和T+1观察验证；
6. 个股L0事实卡和L1快速研究；
7. 最小StrategySpec、固定权重、Hikyuu日线Formal回测；
8. Prediction/Order/Execution/Validation全链路；
9. PostgreSQL持久任务、单重Worker和Operations页面；
10. Cloudflare + NPM + owner密码 + Turnstile + 备份恢复演练；
11. MVP二期的单只、owner人工触发L2深度研究，含分歧、Checkpoint和资源上限。

### 12.2 MVP延后

- AI动态仓位、复杂MVO和多机制自动叠加生产化；
- L2多Agent深度研究的自动候选、批量运行和多Worker弹性；
- 全球市场进入任何A股策略、权重或回测；
- 分钟/Tick、北交所、ETF、可转债、融资融券、做空和杠杆；
- 多租户、细粒度团队RBAC、微服务、消息总线和分布式Hikyuu Worker；
- Fleur运行时和其完整基础设施。

### 12.3 MVP两期与Local Release Gate

```text
MVP一期 = M0—M6 + WP-0701—WP-0703
             = 本地核心功能闭环

MVP二期 = WP-0704 + M8
             = 本地生产预演 + 服务器发布
```

一期及二期的代码、Migration、Compose、备份和恢复均先在本地/隔离环境验证。服务器部署是二期的最后发布步骤，不是开发环境。Local Release Gate至少要求：

- 必需WP有`VERIFIED`证据；
- 生产等价Compose、Migration、恢复、PIT、Hikyuu Golden和安全反例在本地通过；
- 没有未处理的高危问题或破坏性数据迁移；
- 服务器Preflight、备份点、回滚方案和owner部署批准齐全。

### 12.4 Golden Dataset

测试集必须包含：

| 类别 | 最少场景 |
| --- | --- |
| 身份 | 沪/深主板、创业板、科创板、退市、改名、ST、歧义裸码 |
| 日历 | 正常交易日、周末、法定假期、临时停市 |
| 行情 | 停牌、涨停、跌停、零成交、复权事件、缺失K线 |
| 公司行动 | 分红、送转、除权、Correction |
| 股票池 | 新股、退市、历史成分变更 |
| Provider | 主源成功、补充替代、字段补充、双源冲突、超时 |
| Feature | Warmup不足、缺失、横截面股票池、修订传播 |
| 回测 | T+1不可卖、整手、最低佣金、容量、未成交、基准 |
| AI/证据 | 支持、矛盾、证据不足、模型超时、外部证据晚到 |
| 安全 | Turnstile失败、密码错误、Session过期、CSRF、路径穿越 |

Golden Dataset必须小到CI可运行，同时提供覆盖至少一个完整交易月的集成Fixture。大规模历史性能测试使用独立Benchmark Dataset。

### 12.5 实现Exit Gate

每个Milestone必须同时满足：

1. Schema、数据库Migration、Golden Payload和错误码已登记；
2. Unit/Contract/Integration测试通过；
3. PIT、幂等、重试、Correction和权限反例有测试；
4. 页面有Loading/Empty/Partial/Stale/Error/Success状态；
5. API与页面只消费已发布契约，不读Worker临时目录；
6. 日志含`request_id/task_id/attempt_id/resource_id`且不泄密；
7. 文档、`.env.example`、OpenAPI和Changelog同步；
8. 回滚步骤和数据兼容路径明确；
9. 关键性能预算通过；
10. Product Requirement到测试证据的追踪矩阵无空项。

## 13. 跨契约不变量

以下任一违反都阻断合入：

1. 页面、策略、回测或AI绕过DataSnapshot/FeatureSnapshot读取Provider；
2. 正式对象引用`latest`而不是具体资源ID；
3. 历史回填以本次`ingested_at`冒充`available_at`；
4. Correction覆盖旧文件或旧数据库业务记录；
5. Task重试覆盖旧Attempt；
6. Preview/Research结果标记为Formal；
7. 全球观察进入A股RunBundle；
8. AI输出直接改写事实、策略或资金权重；
9. API通过用户路径读取文件；
10. Secret出现在配置模板、日志、Artifact或Manifest；
11. `PARTIAL`或`DEGRADED`不带原因和缺口；
12. 数据、Definition、Policy、代码或镜像版本缺失导致结果不可复现。

## 14. Claude Code落地顺序

每实现一个对象，按顺序执行：

1. 在`src/schemas`或目标共享契约包定义枚举、Pydantic Schema和JSON Schema导出；
2. 写Golden Payload和拒绝样例；
3. 建立PostgreSQL模型、约束和Alembic Migration；
4. 建Repository接口与事务测试；
5. 实现领域Service和状态机，不让Router直接写表；
6. 实现API/OpenAPI及前端TypeScript类型生成；
7. 实现Worker/Artifact原子发布；
8. 加Contract、Integration和故障注入测试；
9. 更新契约登记、追踪矩阵和Changelog；
10. 运行对应质量门禁后再进入下一对象。

任何实现任务若发现本文与领域文档冲突，应停止扩大代码Diff，先记录契约差异并修改唯一权威文档；不得在Adapter、Router或前端写隐式兼容逻辑掩盖冲突。

## 15. 参考文档

- [Visory契约收敛总纲 v1](platform-contract-convergence-v1.md)
- [A股数据平台与Canonical Data Contract v1](data-platform-and-canonical-contract.md)
- [A股Feature Store与指标注册中心架构 v1](feature-store-architecture.md)
- [StrategySpec v1策略契约](strategy-spec-v1.md)
- [指标、预测与Hikyuu回测架构](backtest-and-indicator-architecture.md)
- [A股主平台模块化单体、API、任务与权限架构 v1](platform-shell-api-task-permission-architecture.md)
- [Visory Docker、Cloudflare、NPM与访问安全架构 v1](docker-cloudflare-npm-deployment-architecture.md)
