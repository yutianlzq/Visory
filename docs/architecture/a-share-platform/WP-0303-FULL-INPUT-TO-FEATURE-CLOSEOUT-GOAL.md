# WP-0303-FULL-INPUT-TO-FEATURE-CLOSEOUT Goal v2

状态：`PARTIAL / BLOCKED`

最后调整：2026-10-15

## 1. Goal 不变，执行阶段重排

本 Goal 的完成定义仍是：关闭 B1—B4 合法输入缺口，并完成固定 Raw/Canonical/Snapshot 输入到 DERIVED、Resolver/F1/F2、FeatureStore、固定 FeatureBundle、进程重启消费和真实来源 Correction 传播的完整链路。基于固定的 `a-stock-data@29b07d2e37005b9fd568bca1262f6e572b5f9407` 参考实现，执行架构调整为“Adapter Bundle、实际 Provider Endpoint、来源准入证据和运行绑定”四层；这不会缩小或替换原验收。

当前仍保持：

- `WP-0303=IN_PROGRESS`、已验收计数 `15/45`；
- B1—B4 整体新增关闭项为 0，真实输入继续 `NO_GO`；
- `market_breadth`、`market_emotion` 保持 missing，Formal/Paper 消费继续拒绝；
- 生产 `NOT CERTIFIED`、`RELEASED=false`；
- 不推进 WP-0304、WP-0305、Hikyuu、市场页面、Paper Portfolio 或其他相邻 WP。

## 2. 不变量与兼容边界

1. 现有 `ProviderRun@1.0.0`、`RawObject@1.0.0`、Provider/Raw/Canonical 契约、Golden、Hash 和持久化语义不原地修改。
2. 旧 14 F1、65 F2 的 payload、版本、Definition Hash、Golden 和固定引用不变；变化通过追加版本表达。
3. 0014/0015、B5、N1/N2 全部保留；`FixtureExecutionLineageBridge` 继续标记 `FIXTURE_ONLY`，不得改名或提升为生产证据。
4. `a-stock-data` 固定 commit 只是 Adapter Bundle 实现指纹；腾讯、通达信、东财、巨潮、BaoStock、新浪、同花顺及交易所端点分别认证。
5. 当前 `ContractRegistry` 以 `contract_id` 唯一注册；不得通过注册第二个同名 `C-004/ProviderRun` 来隐式替换旧 Schema。下一阶段使用新的 `contract_id` 纯追加对象。
6. 没有真实 Endpoint 的来源版本、实际脱敏字节、单位/身份、完整覆盖、历史 `available_at`、revision/cancel 和许可证据时，Receipt 不得标记 `PIT_CERTIFIED`。

## 3. 目标对象关系

```text
ProviderDefinition@1.0.0                         (existing, unchanged)
  └── ProviderEndpointDefinition@1.0.0           (new)
        ├── AdapterImplementationFingerprint@1.0.0 (new)
        └── SourceAdmissionReceipt@1.0.0          (new)

ProviderRun@1.0.0 + RawObject@1.0.0              (existing, unchanged)
  └── ProviderEndpointRunBinding@1.0.0            (new)
        ├── exact Provider Endpoint/version
        ├── exact implementation fingerprint
        ├── exact admission receipt/hash
        └── exact Dataset/schema and Raw refs

ProviderEndpointRunBinding
  -> CanonicalPartition + QualityReport + Coverage evidence
  -> DataSnapshot
  -> DERIVED Adjustment/market inputs
  -> Resolver/F1/F2
  -> fixed FeatureSnapshot/FeatureBundle
```

四个新对象的职责：

| 对象 | 业务身份 | 核心职责 |
| --- | --- | --- |
| `ProviderEndpointDefinition` | `provider_endpoint_id + provider_id + endpoint_contract_version` | 固定请求、响应、分页、空值/零行、修订/取消、发布时间、许可和适用 Dataset |
| `AdapterImplementationFingerprint` | `adapter_implementation_fingerprint_id` | 固定 Bundle commit、源文件字节、函数符号、Visory wrapper、Mapping 和质量规则实现 |
| `SourceAdmissionReceipt` | `source_admission_receipt_id` | 对固定 Endpoint/Dataset/申请区间保存来源契约、样本、观察时钟、覆盖、revision/cancel、质量及许可证据 Hash，并给出准入等级 |
| `ProviderEndpointRunBinding` | `provider_endpoint_run_binding_id` | 将一次旧 `ProviderRun`/`RawObject` 与唯一 Endpoint、实现指纹及 Receipt 绑定，禁止换源后复用原 Run 身份 |

Formal 路径必须同时满足：Binding 存在且 Hash 有效；Endpoint、Dataset/schema、实际 origin、ProviderRun 和 RawObject 一致；Receipt 为相同范围的 `PIT_CERTIFIED`；证据字节未漂移。任一条件不满足即 fail closed。

## 4. 分阶段执行

| 阶段 | 内容 | 当前状态 | 退出条件 |
| --- | --- | --- | --- |
| A | 固定 Adapter Bundle 与实际 Provider/Endpoint 分层，记录 B1—B4 候选和门禁 | `DONE`（架构文档） | 不代表任何真实 Endpoint 获准 |
| B | C-004 Endpoint Admission 纯追加契约、Registry、Schema、Golden、Repository、持久化和 fail-closed 校验 | `DONE`（本地基础设施） | 只证明准入基础设施，不认证 Endpoint、不关闭 B1—B4 |
| C | 按单个 Endpoint 提交并审核真实 Source Admission 最小包，追加对应 Dataset/Raw Schema/Mapping/质量/Policy | `BLOCKED` | 任一 PIT、覆盖、修订、零行或许可证据不足即 `NO_GO` |
| D | 合格固定输入进入复权、37 原始指标、五维情绪、DERIVED、FeatureStore 和固定消费 | `BLOCKED` | 禁止 fixture、当前历史重下载、latest、补零、因子补 1 或跨源静默 fallback |
| E | 独立 PostgreSQL 原子发布、失败回收、进程重启、真实 Source Correction 传播和完整 gate | `BLOCKED` | 本地、远程合入、部署和生产认证分别验收 |

阶段 B 已在本地累计工作树完成；下一阶段 C 仍因缺少逐 Endpoint 真实来源材料而 `BLOCKED/NO_GO`。阶段 B 没有捎带具体 Provider Adapter、真实数据下载、B1—B4 Definition 修订、正式 DERIVED/F1/F2/Bundle 发布或市场能力认证。

## 5. B1—B4 当前输入判定

| 缺口 | 当前可复用 | 未满足门禁 | 判定 |
| --- | --- | --- | --- |
| B1 PIT 流通市值 | 当前字段、历史数值和口径对账样本 | 逐日历史版本、正确流通口径/价格基准、全市场覆盖、首次观察/可用时间、跨 cutoff 修订 | `NO_GO` |
| B2 正确历史股本 | 当前总/流通股字段、历史换手率反例 | A/B/H、限售/自由流通口径、逐日生效与披露时钟、历史版本和修订链 | `NO_GO` |
| B3 公司行动/复权 | 现有 Method、DERIVED 契约、FIXTURE_ONLY 算法及发行人样本 | Provider 原始事件身份、全类型/全页/合法零行动、revision/cancel、历史可用时钟、固定前一 session P | `NO_GO` |
| B4 旧 F1 与原始指标 | `trading_halt_state@2.0.0` 子项、行情/首封/基准候选 | 历史冻结池、逐日包完整性、榜单 total/分页/零行语义、首封观察时钟、固定 PRICE 版本/PIT | `NO_GO` |

## 6. C-004 阶段 B 的完成结果

`WP-0303-C004-PROVIDER-ENDPOINT-ADMISSION-CONTRACT` 已按以下边界完成本地基础设施：

1. 四个纯追加对象进入模型、Contract Registry、JSON Schema、Golden 和兼容导出，不改变旧 C-004 Schema/Golden 字节。
2. 如四类对象需要 PostgreSQL 持久化，只追加 0015 之后的单一后继 Migration；升级、事务失败回收、重启读回和危险 downgrade 拒绝均有隔离 PostgreSQL 证据。
3. Formal 校验拒绝：缺 Binding、Endpoint 不匹配、Receipt 非 `PIT_CERTIFIED`、Receipt 范围不覆盖请求、证据 Hash 漂移、Dataset/schema 不匹配、Raw 不属于 Run、换源仍复用同一 Run。
4. Preview/历史兼容读取不会把无 Binding 的旧 Run 提升为 Formal；旧固定引用继续可读。
5. Contract/Golden/generated、治理、Python 编译/lint、定向测试、隔离 PostgreSQL、`bash scripts/ci_gate.sh all` 和 `git diff --check` 均按实际结果报告，不以 skip/mock/修改旧 Golden 掩盖失败。
6. 完成后仍保持 B1—B4 `NO_GO`、两市场能力 missing、`WP-0303=IN_PROGRESS`、`NOT CERTIFIED`、`RELEASED=false`。

## 7. 停止条件与授权边界

- 若实现要求原地修改 `ProviderRun`/`RawObject`、旧 `contract_id`、旧 Golden/Hash 或 0014/0015，立即停止并重新设计。
- 若发现四对象不能在不扩展 API/客户端的情况下持久化，只完成后端契约和 Repository，不捎带 Web/Desktop。
- 若 PostgreSQL Migration 不是实际持久化所需，不为流程形式新增空迁移。
- 不访问真实 Provider API、生产数据库或真实 `/data`；不执行生产调度、部署、发布、commit、tag、push、PR 或 merge。
- 阶段 B 完成不等于来源准入、WP-0303 完成或生产认证；阶段 C 必须针对每个 Endpoint 重新取得真实材料。

## 8. 回滚

本次 Goal 重排和 C-004 实现可按本轮 allowlist 逐 hunk 回滚；不得整文件 restore、reset、clean 或 stash，也不得删除/覆盖开工前成果。代码回滚只撤销四对象、Repository/Service、Snapshot Formal 接线、0016、生成契约和本轮测试/文档；数据库仅在五张新表为空时降级到 0015，存在任何 Admission 记录时必须先保留数据并停止降级。旧对象、0014/0015 与固定引用始终保留。

## 9. 2026-10-15 C-004 Endpoint Admission 本地实现结果

- 新增四个 `1.0.0` 对象、确定性 Hash、严格字段校验、四份 JSON Schema 及成功/拒绝 Golden；旧 `ProviderRun@1.0.0`、`RawObject@1.0.0` 和旧 C-004 对象未原地改版。
- 新增 PostgreSQL 后继 `0016_wp0303_provider_endpoint_admission`，持久化四对象及 Binding→RawObject 关联；Repository 只支持精确 ID/version 读取，不提供 latest 或模糊 Endpoint 选择。
- Binding 写入在同一事务中校验 Run、全部 Raw、Provider/Endpoint、Dataset/schema、market、request/schema Hash、实际 origin、Fingerprint 和 Receipt；发布中途失败全部回滚。逐字段相同的不可变前置对象可被多个 Run 复用，同一包可幂等重放，并发首次发布被事务锁序列化；同身份漂移和 Endpoint 路径点段越界均拒绝。
- Snapshot `backtest_core` build、Formal consumer 与 backtest current pointer 现在都要求有效 Binding、有效 `PIT_CERTIFIED` Receipt、未漂移的来源证据和实现观察；缺 resolver 也 fail closed。
- 隔离 PostgreSQL 已覆盖 upgrade、四对象重启读回、唯一/FK/Raw 完整性、原子失败回收、Snapshot Formal 成功与 12 类拒绝、安全 downgrade 拒绝及空表 downgrade/re-upgrade。该证据全部使用合成材料，不认证任何真实 Endpoint。
- 阶段 C 开始前还必须批准不可变 `ACCEPTED` Receipt 的后续撤销模型；当前 `REVOKED` 只表示 Binding 直接引用 Receipt 的自身状态，不得将无 supersession/status-event 关联的新 Receipt 当成撤销传播。
- 阶段 C 仍需逐 Endpoint 的真实脱敏响应、完整覆盖、历史可用时钟、revision/cancel、单位/身份和许可证据；B1—B4 继续 `NO_GO`，`market_breadth/market_emotion=missing`，Formal/Paper 的真实来源路径继续拒绝，`WP-0303=IN_PROGRESS`、15/45、`NOT CERTIFIED`、`RELEASED=false`。

## 10. 2026-10-19 候选收敛与本 Goal 的区别

`WP-0303-MAINLINE-CONVERGENCE-AND-PR-READINESS` 只把 f468 累计成果收敛为基于新 main 的可审查、可回滚候选；其当前验证和最终 gate 判定统一记录于[实现记录第 22 节](WP-0303-IMPLEMENTATION.md#mainline-convergence)。三起点迁移、SourceRoute/Admission 联合门禁、固定消费与合成 Correction 的本地证据不替代本 Goal 阶段 C–E 的真实来源、历史 PIT、完整覆盖或真实修订认证。

本完整输入 Goal 仍 `BLOCKED/NO_GO`，完成条件未改变。真实 Endpoint 准入前还必须独立批准并验证 Receipt 撤销生命周期；当前直接引用 `REVOKED` 状态的检查不是既有 ACCEPTED Receipt/Binding 的完整撤销传播。本轮不新增该生命周期能力。

本次 mainline convergence 的本地候选已达到 PR-ready：完整 gate 为 8178 passed、0 failed、0 skipped（标准 network marker 排除 4 项），定向及真实 PostgreSQL 另有本轮证据。该有界候选结论不关闭本文的完整真实输入 Goal，不改变阶段 C–E 或 WP-0303 的状态。
