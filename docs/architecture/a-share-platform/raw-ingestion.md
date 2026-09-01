# Raw Ingestion（WP-0202）

## 1. 范围与边界

WP-0202 为 `security_master`、`trading_calendar` 与 `bar_1d_raw` 建立可追溯的原始采集闭环：

```text
Durable Task → Controlled Provider Adapter → ProviderRun → RawObject / Quarantine
             → staging + hash + fsync + atomic rename → PostgreSQL registry
```

它只处理 Provider 的原始响应与原始 schema，不生成 CanonicalPartition、DataSnapshot、QualityReport 或调度策略；不连接生产 Provider，不使用生产 Secret，不写真实 `/data`，不替换 Legacy 内存 Task Queue。后续 Canonical Normalization 属于 WP-0203。

平台正式 `ProviderRun` 位于 `src.schemas.platform.raw_ingestion`，不得与 Legacy 的 `src.services.run_diagnostics.ProviderRun` 混用或复用。

## 2. 契约与持久化模型

- `ProviderRun`：一条 Durable Task Attempt 对 Provider 的一次受控请求。它保存 Registry 版本绑定、脱敏后的 `actual_upstream`、请求指纹、开始/结束时间、观测 schema/行/字节统计、终态与安全诊断；
- `RawObject`：成功采集的 append-only 原始内容。ID 为 `raw_` UUIDv7，`retention_class=PINNED`；StorageRef、SHA-256、媒体类型和字节数必须相等；
- `RawIngestionQuarantine`：只允许 `ADDITIVE_DRIFT`、`BREAKING_DRIFT` 或 `UNKNOWN_SCHEMA`，保存不可作为 RawObject 消费的受控证据；
- `RawIngestionTaskRequirements`：`raw_ingestion` Durable Task 的 secret-free 输入；请求内容在持久化前验证；
- `RawIngestionPublishResult`：Worker 的内部发布结果，不提供公网文件下载端点。

Migration `0007_wp0202_raw_ingestion`（parent `0006_wp0201_registry_contract_hardening`）创建 `provider_run`、`raw_object` 与 `raw_ingestion_quarantine`；G013 新增 Migration `0008_wp0202_raw_schema_hardening`，创建独立 `provider_raw_schema_definition` 与 PostgreSQL `provider_rate_limit_window`。它对 Registry、Task 与 Attempt 使用外键；`raw_object` 的 `provider_run_id` 和 `relative_path` 均唯一，保留/压缩/统计约束由数据库与契约共同限制。

Repository 只执行读写操作，不提交事务。Worker 以调用方拥有的事务同时登记 ProviderRun/RawObject 或 Quarantine，并完成或失败 Durable Task。

## 3. Provider 受控边界与脱敏

Adapter Registry 是闭集：仅 `a_stock_data` 与 `financial_api`。Worker 从 Registry 的 ProviderDefinition 取得已声明的 adapter name，再用可注入的 `ProviderTransport` 发起请求；测试使用 `FakeProviderTransport`，没有任意 import path、反射加载或真实 Provider 调用。

下列内容不能进入契约、数据库、Manifest、日志诊断或对外 API：

- Token、Cookie、Authorization、API Key、password、secret 等敏感 key 或 header；
- 带用户凭据、query 或 fragment 的 URL；
- 宿主机绝对路径和 `VISORY_RUNTIME_ROOT`；
- 看起来像 `token=...`、`authorization: ...` 等的文本值。

`actual_upstream` 必须是无凭据且无 query/fragment 的 origin 或 URI；原始请求仅保存稳定 hash fingerprint。失败信息必须短、可判定并已脱敏。

## 4. 发布、完整性与故障语义

发布器在 Storage Namespace 内的 `.staging` 写入，先验证 Hash/大小，再 fsync 内容及需要的目录，并以同文件系统原子 rename 写入严格目录：

```text
raw/provider={provider}/dataset={dataset}/year={YYYY}/month={MM}/
  provider_run={prun_uuid}/raw_object={raw_uuid}/
```

成功目录包含 payload 和 `manifest.json`。路径由现有 Namespace Resolver 解析，必须是规范 POSIX 相对路径，且拒绝路径穿越、Windows 路径、URI 式路径、根目录/父目录和任何 Symlink 逃逸。正式发布不可覆盖已存在文件或目录。

| 事件 | 结果 |
| --- | --- |
| 校验或路径安全失败 | 不发布正式 Raw；不会登记 RawObject。 |
| rename 失败 | 不登记 RawObject 或 Quarantine。 |
| rename 成功、DB 事务失败 | 目录成为不可见 Orphan；不因事务回滚删除文件。 |
| Schema matched | 原子登记 RawObject、ProviderRun `SUCCEEDED` 与 Task `SUCCEEDED`。 |
| additive drift | 保存 Quarantine；ProviderRun/Task 使用 `DEGRADED`。 |
| breaking/unknown drift | 保存 Quarantine；ProviderRun/Task 失败，不能伪装成功。 |
| Registry 已有记录但文件缺失或 Hash 不符 | Consumer 应视为损坏并阻断消费；本 WP 不自动修复。 |

Alembic downgrade 仅删除数据库 Schema；它绝不删除 Raw、Quarantine、Manifest 或 orphan 文件。

## 5. Drift、取消、租约与恢复

Schema 比较的是独立、版本化的 Provider Raw Schema（不从 Canonical DatasetDefinition 派生）：

- `MATCHED`：必需字段存在、可选字段缺失允许、已声明字段类型一致且无额外字段；
- `ADDITIVE_DRIFT`：存在额外字段但未缺少必需字段；
- `BREAKING_DRIFT`：缺少必需字段、已声明字段类型不符或 Provider Schema 版本未注册；
- `UNKNOWN_SCHEMA`：Provider 未提供可比较的 Raw schema。

漂移响应的内容和 Manifest 以 Quarantine 证据保存；其内容不会注册为消费用 RawObject。

Worker 使用 WP-0103 的单 Worker Lease：fetch 前、fetch 后/发布前都检查取消；过期或丢失 Lease 的 Worker 不能完成 Task、登记 RawObject 或把半成品发布成可见结果。Provider timeout 可映射为 retryable Raw 错误；Provider/Dataset rate limiter 只约束该受控采集路径，并通过 PostgreSQL 固定窗口行锁在 Worker 间协调；独立内存计数器仅用于离线单元测试。

`RawIngestionOrphanScanner` 是只读 Dry-run。它只扫描上述已知目录结构，跳过未知目录、Symlink 与无效 Manifest，重验 Manifest、路径、Hash、字节数和 Registry 状态，输出候选与 `RAW_REGISTRY_ENTRY_MISSING` / `PROVIDER_RUN_ENTRY_MISSING` 原因。它不删除、不自动恢复注册，也不处理未知目录。

## 6. 验证和回滚

离线纵向与 PostgreSQL 16 集成测试覆盖三个 Dataset、成功发布/读取、Hash 和 Manifest 确定性、Secret 脱敏、路径逃逸、drift、timeout、限流、取消、Lease Lost、重试/崩溃语义、rename/事务故障、orphan 识别、Migration upgrade/repeat/downgrade/re-upgrade，以及既有 Task/Artifact/Registry 回归。

回滚时以普通 `git revert` 撤销合并提交；隔离数据库可 downgrade 至 `0006_wp0201_registry_contract_hardening`。已 rename 的业务文件依然保留，必须按 Manifest、Hash 和审计要求人工处理；不得把它们作为自动清理目标。
