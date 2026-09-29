# Visory-G020 / WP-0207 分批 Backfill 状态
## 2026-09-29 合入后最终闭环复核

- PR #38 已按授权以普通 merge 合入：`merged=true`、状态 `closed`，base SHA `46804661dbb897433f114c25898c8da7021254a1`，实际 PR head SHA `528baa072d32f0242cfdcfa8bb7b1314de19db78`，merge commit `a1d31f9c3d16e62ea4fd78217c992bfe96dc33a8`，`merged_at=2026-09-29T04:01:18Z`；未使用 squash 或 rebase。
- 最终 PR 只读审阅结果：GitHub submitted reviews 为 0，review threads 为 0，PR conversation comments 为 0；改动边界仍限定为 WP-0207 Backfill Schema/Registry/OpenAPI/generated exports、Batch/Task Requirements/Projection、MONTH/YEAR planning、七阶段 Stage Chain、Durable Task lease/checkpoint/retry/cancel、BLOCKED/UNBLOCKED、Raw→Canonical→Snapshot 子任务链、Provider fallback/unavailable/quarantine、Correction lineage、Operations/P-DATA 只读投影、Backfill Web/API、测试/Golden/PostgreSQL integration 与 acceptance 文档。
- 合入后手动触发同一 Baseline CI 的 Run `36520276484`（`workflow_dispatch`，head branch `main`，head SHA `a1d31f9c3d16e62ea4fd78217c992bfe96dc33a8`）已完成成功：Governance and repository boundaries、Python deterministic gate、Web lint and build 三个阻断 Job 均 `completed / success`。
- `git ls-remote origin refs/heads/main` 实时返回 `a1d31f9c3d16e62ea4fd78217c992bfe96dc33a8`；本地 `origin/main` 已定向更新为同一 SHA。为遵守不覆盖其他分支约束，本地 `main` 仍为其原值 `46804661dbb897433f114c25898c8da7021254a1`，是远程 main 的祖先而非当前同值；当前分支 HEAD 仍为 PR head，且 PR head 是 `origin/main` 的祖先，可追溯至该 merge commit。
- 本节记录完成后，工作树只允许保留本状态闭环文档的有意未提交修改；未创建新的代码提交、未 push、未修改远程 PR、未连接真实 Provider/生产数据库/真实 `/data`/生产调度或生产回填。
- 状态保持：`Visory-G020 = COMPLETE`；`WP-0207 = IN_PROGRESS`；production certification = `NOT CERTIFIED`；implemented work packages = `13/45`；`RELEASED = false`；`WP-0301 = NOT_STARTED`。
- 回滚方式：如需撤销合入结果，按维护者流程对完整 merge change set 执行 revert（merge commit 为 `a1d31f9c3d16e62ea4fd78217c992bfe96dc33a8`，不得 reset 或 force-push），不涉及生产迁移或生产数据回滚。



## 2026-09-28 当前回合最新复核：实时远程基线成功

- 连续两次执行带连接超时保护的 `git ls-remote origin refs/heads/main` 均成功返回 `46804661dbb897433f114c25898c8da7021254a1`。
- 该 SHA 与本地 `HEAD`、本地 `main` 和缓存 `origin/main` 一致，`main...origin/main = 0/0`。
- 本次仅执行只读远程核验，未执行 `fetch`、`pull`、`reset`、`stash`、`commit` 或 `push`。


## 2026-09-28 当前回合复核：实时远程仍不可用

- 本回合执行 `git -c http.connectTimeout=10 -c http.lowSpeedLimit=1 -c http.lowSpeedTime=10 ls-remote origin refs/heads/main`，因 GitHub 连接低速超时失败（exit 128）；本次未取得实时远程 SHA。
- 本地 `HEAD`、本地 `main` 与缓存 `origin/main` 仍为 `46804661dbb897433f114c25898c8da7021254a1`，`main...origin/main = 0/0`；未执行 `fetch`、`pull`、`reset`、`stash`、`commit` 或 `push`。
- 实时远程基线继续记录为 `BLOCKER`；WP-0207 保持 `IN_PROGRESS / NOT CERTIFIED / 13/45`。
- 本轮最小充分验证：Backfill/API/Contract Python `188 passed, 4 warnings`；隔离 `postgres:16` integration `16 passed, 2 warnings`；Contract Registry、治理检查、受影响 Python `py_compile`、`git diff --check` 通过；Backfill Web Vitest `9 passed`，修改文件定向 ESLint、`tsc -b`、Vite build 通过。


## 2026-09-28 当前回合最终复核：实时远程阻断

- 本回合最后一次 `git ls-remote origin refs/heads/main` 因连接 `github.com:443` 失败（exit 128）；不能把缓存 `origin/main` 当作本次实时远程成功证据。失败前后本地 `HEAD`、本地 `main` 与缓存 `origin/main` 均为 `46804661dbb897433f114c25898c8da7021254a1`。
- 当前工作树仅包含 WP-0207 未提交改动；未执行 `fetch`、`pull`、`reset`、`stash`、`commit`、`push` 或 PR。WP-0206 的 `GOAL-G019-STATUS.md`、已合入代码和 Run `34581431121` 证据未被当前工作树覆盖，未发现 WP-0206 状态与实现/既有 CI 证据矛盾。
- 最新本地定向套件为 `189 passed, 15 skipped, 4 warnings`；隔离 PostgreSQL 16 Backfill integration 的既有成功证据为 `16 passed, 2 warnings`。本地 Web 修改文件 ESLint、`tsc -b`、Vite build 和 Backfill Vitest `9 passed` 通过；全量 Web ESLint 仍有 41 个未修改既有错误。
- 实时远程基线缺口记录为 `BLOCKER`；WP-0207 保持 `IN_PROGRESS / NOT CERTIFIED / 13/45`，不得标记 `VERIFIED` 或 `RELEASED`。

## 2026-09-28 当前回合补验：远程基线与 PostgreSQL integration

- 实时 `git ls-remote origin refs/heads/main` 成功返回 `46804661dbb897433f114c25898c8da7021254a1`；本地 `HEAD`、本地 `main`、缓存 `origin/main` 与远程 `main` 一致，均为该 SHA。
- 使用临时 `postgres:16`、tmpfs 数据目录和 loopback 随机端口执行 `tests/integration/platform/test_backfill_integration.py`，结果为 `16 passed, 2 warnings`；测试容器和临时密码文件已清理，未触碰现有 `minio`、`nginx`、`redis` 容器。
- 修正 BackfillWorker 的差异摘要累积：成功、失败、恢复后的 checkpoint 与最终批次 Projection 都保留分区差异摘要；新增 YEAR 12 分区成功/失败回归。相关 Python 定向套件为 `189 passed, 15 skipped, 4 warnings`。
- 仍未具备 WP-0207 远程阻断 CI、七类数据完整生产级执行/发布、真实 Provider/生产数据库/真实 `/data`/生产调度认证；状态保持 `IN_PROGRESS / NOT CERTIFIED / 13/45`。


## 2026-09-28 当前回合补充：fallback Canonical lineage 收敛

- 修正 deterministic publication fixture：provider fallback 产生的 primary/supplement `CanonicalPartition` 引用现在完整保留在不可变 publication 与 Backfill checkpoint/投影中，不再被压缩为单一伪发布引用；ProviderRun、RawObject、CanonicalPartition 数量一致性和 idempotency 约束保持不变。
- `tests/platform/test_backfill.py`：`171 passed, 3 warnings`；`tests/integration/platform/test_backfill_integration.py`：`1 passed, 15 skipped, 2 warnings`，本次未配置 PostgreSQL 连接变量，跳过项不计入 PostgreSQL 通过证据。
- 该修正不改变 `WP-0207 = IN_PROGRESS / NOT CERTIFIED / 13/45`；实时远程基线复核仍为 BLOCKER，不标记 `VERIFIED` 或 `RELEASED`。

最后更新：2026-09-28

## 2026-09-28 当前回合补充：实时远程复核间歇性阻断

- 本回合曾有一次 `git ls-remote origin refs/heads/main` 返回目标 SHA，但随后再次复核时因连接 `github.com:443` 失败（exit 128）。因此当前回合不能把实时远程基线视为稳定已验证；本地 `main`、`HEAD` 与缓存 `origin/main` 仍为 `46804661dbb897433f114c25898c8da7021254a1`。
- WP-0206 复核未发现当前未提交 WP-0207 工作树覆盖其代码、状态文档或已记录的 Run `34581431121` 证据；该历史远程证据仍只证明 WP-0206，不证明 WP-0207。
- 当前 WP-0207 定向 Python 套件为 `185 passed, 15 skipped, 3 warnings`；其中 PostgreSQL integration 在本环境未配置连接变量而跳过，既有隔离 PostgreSQL 证据仍单独保留。状态继续为 `IN_PROGRESS / NOT CERTIFIED / 13/45`。
- 当前回合未执行 `reset`、`stash`、`commit`、`push` 或 PR 操作；实时远程复核列为 `BLOCKER`，不标记 `VERIFIED` 或 `RELEASED`。

## 当前结论

- Goal-G020 已完成并已合入；WP-0207 仍为 `IN_PROGRESS`，累计完成仍为 `13/45`。
- 生产认证 `NOT CERTIFIED`；未满足 VERIFIED 条件，不得标记 RELEASED。
- 当前代码已形成第一阶段隔离安全最小闭环：MONTH 1 分区与 YEAR 12 分区通过既有 RawIngestion→CanonicalNormalization→SnapshotBuild worker、PostgreSQL 注册表和物理 Artifact/Manifest 验证；七阶段控制链已复用既有 Durable Task 创建、BLOCKED/解除阻断和前置阶段依赖语义。Provider transport 仍为隔离 deterministic fixture，不代表真实 Provider、生产数据或七类数据完整执行/发布验收。
## 2026-09-28 最新补验：批次查询一致性

- 当前基线实时复核成功：分支为 `main`；本地 `HEAD`、`refs/heads/main`、`origin/main` 与 `git ls-remote origin refs/heads/main` 均为 `46804661dbb897433f114c25898c8da7021254a1`。
- WP-0207 控制面修正 `BackfillService.get_batch` 的重复 `batch_id` 处理：发现多个 Task 记录或分页 `has_more` 时返回 `BACKFILL_BATCH_AMBIGUOUS`，不再返回任意第一条记录；新增回归通过。
- `tests/platform/test_backfill.py`：`169 passed, 2 warnings`；联合 Backfill/API/Contract 定向套件为 `183 passed, 15 skipped, 4 warnings`。受影响 Python `py_compile`、Contract Registry/generated exports、`check_ai_assets.py`、`check_visory_baseline.py` 与 `git diff --check` 均通过；修改文件定向 ESLint 与 Web build 通过，全量 Web ESLint 仍有 41 个既有未修改路径错误。状态继续为 `IN_PROGRESS / NOT CERTIFIED / 13/45`。

## 2026-09-28 当前回合复核

- 基线（历史复核记录）：当前分支为 `main`；本地 `HEAD`、本地 `main`、缓存 `origin/main` 均为 `46804661dbb897433f114c25898c8da7021254a1`。该次实时 `git ls-remote origin refs/heads/main` 曾因无法连接 GitHub `443` 失败，未执行 `fetch`、`pull`、`commit`、`push` 或 PR；后续本回合已成功实时复核同一远端 SHA，见最新补验记录。
- WP-0206 只读远程证据：PR #36 已合入，merge commit 为 `3db5057acd0029c6fb3557fe6a90ebfb2c288acd`；状态收尾 PR #37 已合入当前基线 `46804661dbb897433f114c25898c8da7021254a1`；Run `34581431121` 的 Governance、Python deterministic gate、Web lint/build 均为成功。该历史证据不等同于 WP-0207 远程 CI。
- 当前工作树未提交 WP-0207 改动仍保持 `IN_PROGRESS / NOT CERTIFIED / 13/45`。本回合 Backfill 定向 Python 为 `165 passed, 15 skipped, 2 warnings`；Contract Registry/generated exports、`check_ai_assets.py`、`check_visory_baseline.py`、受影响 Python `py_compile` 均通过；Backfill 前端定向 Vitest 为 `7 passed`，bundled Node.js `v24.19.0` 下修改文件定向 ESLint 与 Web build 通过，全量 Web ESLint 仍有 41 个既有未修改路径错误，`git diff --check` 通过。
- 完整 backend gate、完整 Web Vitest、WP-0207 远程阻断 CI、七类数据完整逐阶段执行/发布、真实 Provider/生产数据库/真实 `/data`/生产调度认证仍未完成，不得标记 `VERIFIED` 或 `RELEASED`。

## 本轮收口复核（2026-09-27）

- 重新确认当前分支为 `main`；本地 `HEAD`、`origin/main` 与实时 `git ls-remote origin refs/heads/main` 均为 `46804661dbb897433f114c25898c8da7021254a1`。WP-0206 的状态文档、已合入代码和远程 Run `34581431121` 未被当前未提交 WP-0207 工作树覆盖；该 Run 的 Governance、Python deterministic gate、Web lint/build 均为 success。
- 使用本地已有 `postgres:16` 镜像（image ID 前缀 `f1c3376c26f2`）启动 `tmpfs` 数据目录、仅绑定 `127.0.0.1` 随机端口的隔离临时容器；持久化 `pg` 容器为 `Exited (255)`，本轮未启动、未复用、未修改其卷。
- 隔离 PostgreSQL 16 上的 `tests/integration/platform/test_backfill_integration.py` 为 `16 passed, 2 warnings`，覆盖 1 个月与 1 年 pilot、dry-run/plan-only 无业务发布、checkpoint 恢复、幂等重试、取消/失败、fallback/quarantine/unavailable、Correction 不覆盖旧 Snapshot，以及依赖 Task 原子创建为 `ACCEPTED → QUEUED → BLOCKED` 且无可见队列窗口。
- 同一隔离实例上，排除两个因未安装 `markdown2` 而无法导入完整 API 应用的既有模块后，`tests/integration/platform` 为 `81 passed, 3 warnings`；完整目录收集仍有 2 个 `ModuleNotFoundError: markdown2` 错误。排除三个同源 API 模块后，`tests/platform` 为 `549 passed, 5 skipped, 4 warnings`；完整目录收集仍有 3 个同源错误。测试数据库、临时容器和密码文件已清理，未连接真实 Provider、生产数据库或真实 `/data`。
- Backfill 页面/API 定向 Vitest 为 `4 passed`，覆盖累计 skipped/failed ranges、differences summary、Provider fallback、资源用量、Canonical/Snapshot 引用和未声明内部字段不透传；bundled Node.js `v24.19.0` 直接运行项目本地 ESLint、`tsc -b`、Vite build 均通过。系统 Node.js `v16.20.2` 下的 `npm run lint/build` 受 Node/Vite 版本限制失败，未修改 Web 依赖。
- WP-0207 继续保持 `IN_PROGRESS / NOT CERTIFIED / 13/45`；远程 WP-0207 阻断 CI、七类数据完整逐阶段生产级执行/发布、真实 Provider/生产数据库/真实 `/data`/生产调度认证仍未完成，不得标记 `VERIFIED` 或 `RELEASED`。
- 随后运行完整 scripts/ci_gate.sh 的离线 backend gate，结果为 6852 passed, 82 failed, 88 skipped, 4 deselected, 572 subtests passed；失败均集中于既有 Codex transport/process、Local CLI、SQLite/Storage、screening 和 system-config 基线路径，本轮未扩大 WP-0207 范围。
- 本轮补充只读 P-DATA 阶段链下钻 `GET /api/platform/v1/data-quality/backfills/{batch_id}/stages`；服务层复用现有 Task 查询，固定路线图顺序并对缺失批次、重复阶段、错误依赖 fail-closed。Backfill/阶段链/P-DATA/generated contract 定向 Python 套件为 `173 passed, 4 warnings`；本地已有 `postgres:16` 镜像的隔离 Backfill integration 为 `16 passed, 2 warnings`。

## 本轮收口复核（2026-09-24）

- 重新确认当前分支为 main；本地 HEAD、缓存 origin/main 与实时 git ls-remote origin refs/heads/main 均为 46804661dbb897433f114c25898c8da7021254a1。工作树仍为未提交 WP-0207 改动，未执行 reset、stash、commit、push 或 PR。
- 前端 Backfill API 已收敛普通异常的脱敏边界：可信 API Envelope 仅展示公开 error.code/error.message，非 Envelope 异常统一映射为 历史回填服务不可用，不会向页面透传内部异常、凭据或绝对物理路径；platformBackfill Vitest 回归为 2 passed。
- 完整离线 pytest gate 最终为 6836 passed, 83 failed, 84 skipped, 4 deselected, 572 subtests passed。失败集中在既有 Codex transport/process、Local CLI、SQLite/Storage 等基线测试，Windows 环境还出现既有 os.killpg 不可用路径；该结果不能视为 WP-0207 通过，也未据此扩大范围修复相邻基线模块。
- 本地已有 postgres:16 镜像的 tmpfs/loopback 隔离容器证据仍有效：WP-0207 Backfill integration 12 passed, 4 warnings，完整 tests/integration/platform 79 passed, 10 warnings；临时容器、测试凭据和 shim 已清理，已有持久化 pg 容器保持 Exited (0)，未连接生产数据库、真实 Provider 或真实 /data。
- WP-0207 继续保持 IN_PROGRESS / NOT CERTIFIED / 13/45；七类数据完整逐阶段真实发布、远程阻断 CI、生产 Provider/数据库/调度认证和 VERIFIED/RELEASED 门槛仍未满足。

## 本轮验收记录（2026-09-23）

- 新增 `BackfillStageChainRequest` / `BackfillStageChainProjection`、Contract Registry/OpenAPI/generated frontend types 和 Golden fixtures；`POST /api/platform/v1/backfills/stage-chain` 按固定路线创建七个现有 `task_type=backfill` Durable Task：`IDENTITY_CALENDAR`、`PRICE_MONTH`、`LIFECYCLE_NAMES`、`CORPORATE_ACTION`、`FINANCIAL_VALUATION`、`INDUSTRY_MEMBERS`、`NON_CORE_OBSERVATION`。
- StageChain 使用既有 `input_refs`、`requirements`、`BLOCKED` 和 `unblock_task`，首阶段为 `QUEUED` / `PLANNED`，其余阶段为 `BLOCKED` / `PAUSED`；每次 reconcile 最多解除一个紧邻前置阶段，重复 idempotency key 不新增 Task 且保留稳定 Task ID。该证据证明控制链已形成，不证明七类数据已经逐阶段执行或发布。
- 本地隔离 PostgreSQL 16 临时容器中的 StageChain integration 为 `1 passed`；WP-0207 Backfill integration 为 `12 passed, 5 warnings`，覆盖七阶段线性链、MONTH 1/YEAR 12 pilot、checkpoint、幂等、恢复、取消/lease、fallback/quarantine/unavailable、Correction 不覆盖旧 Snapshot 及 Raw→Canonical→Snapshot 子 Task 顺序。Provider 仍为 deterministic fixture，未连接生产数据库、真实 Provider 或真实 `/data`。
- Backfill/Golden/Registry/generated 定向套件为 `278 passed, 3 warnings`；Backfill 单元为 `151 passed, 3 warnings`，受影响 Python `py_compile` 和 Flake8 critical checks 均通过。
- 使用本地已有 `postgres:16` 镜像、tmpfs 数据目录、loopback 随机端口和独立 fixture 数据库执行完整 `tests/integration/platform`，结果为 `77 passed, 9 warnings`；未复用已有持久化 `pg` 容器或卷。临时容器已停止并由 `--rm` 清理，测试密码文件已删除，已有持久化 `pg` 容器保持 `Exited (0)`。
- Web `npm run lint` 和 `npm run build` 使用 bundled Node.js v24.19.0 均成功；本轮实时 `git ls-remote origin refs/heads/main` 返回 `46804661dbb897433f114c25898c8da7021254a1`，与本地 `HEAD` 和缓存 `origin/main` 一致。
- P-DATA 新增只读 `GET /api/platform/v1/data-quality/backfills/{batch_id}`，复用既有 API Envelope、Backfill Projection 和脱敏错误契约；定向 API 回归为 `4 passed, 1 warning`，覆盖请求 ID、checkpoint/完成范围投影和 `retryable` 错误传播，不产生业务发布。
- P-DATA 阶段链下钻新增 `GET /api/platform/v1/data-quality/backfills/{batch_id}/stages`，只读返回已创建阶段的固定顺序投影；当前验证覆盖 API Envelope、request ID、只读调用和重复/错误链路 fail-closed，不代表完整七类数据生产级执行。

## 已有代码与本轮修正

- 公开 `BackfillBatchRequest` 现在可声明 `supersedes_id`，并按 `data_snapshot` resource ID 校验；创建批次后该字段进入既有 Durable Task requirements 和只读 Projection。Snapshot 子 Task 强制将其映射为 `correction_of_snapshot_id`，若子任务暗含或改写了不同 Correction 目标则以 `BACKFILL_CORRECTION_LINEAGE_MISMATCH` fail-closed；Operations/Backfill 页面展示 supersedes 血缘。该变更只建立不可变 Correction 控制面约束，不证明真实 Snapshot 发布事务已完成。
- 新增可选 `dependency_task_ids` 契约：依赖 Task 通过既有 `input_refs` 留痕；创建批次时重新读取依赖状态，未全部 `SUCCEEDED` 的批次进入既有 `BLOCKED` Task 状态，依赖满足后可复用既有 `unblock_task`，未新增队列、状态机或 Backfill 持久表。
  批次投影将控制面 `BLOCKED` 映射为 `PAUSED`，与 `UNAVAILABLE`、`QUARANTINED` 语义区分。
- 批次 Projection 现在同时暴露 `failure_code`、`blocked_reason_code` 和 `unblock_condition`；Operations/Backfill 页面可观察失败与依赖阻断原因，不暴露内部异常或物理路径。
- 批次 Projection 与 Operations/Backfill 页面现在同时暴露 `provider_policy_id` 和 `priority`，补齐每批 Provider policy 与优先级输入的可查询证据；Schema、Golden 与 generated frontend types 已同步。
- 公开 Backfill Request/Projection 对 `dataset` 统一执行非空与长度约束；Task `CANCELLED` 显式投影为 Backfill `CANCELLED`，不再与 `PAUSED` 混淆。两项均同步生成契约和前端类型。
- Backfill Schema、Registry、批次 API、受控 Task 类型、批次列表投影和 Operations 观察页已接入；未新增队列表或独立 Backfill 持久表。新增 `BackfillPipelineCoordinator`，分别提交 Raw/Canonical/Snapshot 既有 Durable Task；下游提交前重新读取控制面，要求前置 Task 为 SUCCEEDED 并绑定 batch、父 Task、分区幂等键、调用者、dataset 和 provider policy。此门禁只证明前置 Task 身份与状态，不等价于已验收产物归属或真实发布链；dry-run/plan-only 禁止通过协调器排入业务任务。
- 补充失败回归测试并修复：缺少 publisher 不得完成任务、Quarantine 不得调用 publisher、通用 TaskCreateRequest 必须校验 Backfill requirements；deterministic Provider/Publisher 的 lineage 与发布引用现在跨进程重建保持稳定。
- 缺少 publisher 会记录可重试失败；真实 pipeline 已补充隔离 PostgreSQL 发布 fence 与跨 attempt 崩溃恢复证据，但不代表生产 Provider、生产数据库或完整七阶段发布认证。
- YEAR 批次已扩展为确定性月分区；恢复 payload 现在要求 batch/task/stage/date/dataset/input hash、handler version、分区集合，并可绑定现有 `validate_checkpoint`；fallback、quarantine、unavailable 已有显式 deterministic fixture 分支；fallback fixture 同时保留独立 primary/supplement ProviderRun、RawObject、CanonicalPartition 引用，禁止静默混源；deterministic publisher 还验证 correction snapshot 通过新 snapshot_id 与 supersedes_id 追加发布，不覆盖旧记录；失败 checkpoint 现在保留此前已完成分区的 lineage、累计资源用量和已发布引用，重试不会丢失前序证据；批次投影和 Operations 页面现在同时展示 Canonical 与 Snapshot 发布引用。
- BackfillPipelineExecutor 现在从实际 Raw worker 结果捕获 ProviderRun，并由 BackfillWorker 合并进 checkpoint；Canonical 失败时不会继续执行 Snapshot，相关失败边界与引用回收测试已补充。
- 恢复时 lease 缺失不再直接信任 result_loader：BackfillPipelineExecutor 先从既有 Task Control Plane 重新读取子任务，要求 task_id/type 一致且状态为 SUCCEEDED；运行中、失败、取消或身份不匹配均 fail-closed，避免把未完成结果当作已发布结果。
- 本轮补充持久结果恢复：当 BackfillPipelineExecutor 未显式注入 `result_loader` 且复用现有 PostgreSQL Task Control Plane 时，默认从 ProviderRun、CanonicalQualityReport/CanonicalPartition 和 DataSnapshot 注册表按子 Task 读取已发布结果；缺失或血缘不完整时仍 fail-closed，不新增 Backfill 结果存储。
- BackfillWorker 不再修改原始 TaskRecord.requirements 保存运行进度；进度仍通过既有 Checkpoint/StorageRef 持久化，BackfillService 在读取详情和列表时校验最新 checkpoint 的大小、内容 hash、task/batch 绑定和 handler version 后叠加到只读投影。原始请求和 canonical request hash 保持不变。
- BackfillWorker 在每个分区 provider 前及业务发布前复查取消请求；取消时先保留当前已完成/已获取的 checkpoint 证据，再调用既有 `acknowledge_cancel`，不会发布下一个未完成分区。
- 父 Backfill attempt 的 lease/cancel 门禁现已作为 `publication_guard` 注入 Raw、Canonical、Snapshot 既有 registry transaction；门禁与父 Task 的 `request_cancel` 复用同一 PostgreSQL 行锁，取消先提交时子 worker 回滚注册并通过既有 Task Control Plane 取消当前 child Task，父 Task 进入 `CANCELLED`。物理 staging/orphan 仍由既有 Artifact/Raw/Canonical 恢复语义处理，不新增 Backfill 存储。
- IMPLEMENTATION-STATUS 首段漏列 WP-0206 的矛盾已修正；不将该文案修正视为新增 WP 完成。

## BLOCKER / 未完成

- Worker 已把子任务协调器和 `BackfillPipelineExecutor` 接入分区执行与结果回收路径；行情阶段 MONTH 1 分区与 YEAR 12 分区真实 worker pilot 已完成，七阶段 Durable Task 控制链也已按固定顺序创建并可增量解除阻断；但七类数据的完整逐阶段执行、发布和质量验收尚未完成。
- 恢复语义已绑定现有 `validate_checkpoint` 的 token/input hash/handler version，并校验 checkpoint 内容 hash；父 lease/cancel 的事务门禁、取消 fence、lease/reaper、真实 RawObject/CanonicalPartition/DataSnapshot 注册事务，以及子对象提交后父 checkpoint 写入前退出的跨 attempt 恢复，均已在本地隔离 PostgreSQL 16 实际执行并通过。完整七阶段链仍未完成。
- deterministic publication fixture 已在不可变发布记录中保留 ProviderRun、RawObject、CanonicalPartition 与 Snapshot lineage，并覆盖 fallback/correction；另已用隔离 transport 驱动真实 RawIngestion/CanonicalNormalization/SnapshotBuild worker 完成月/年对象链，但未连接生产 Provider，不能替代生产数据认证。
- 失败 Golden 和主要边界测试已补充；仍缺少完整脱敏矩阵和完整七阶段链。
- Operations 观察入口、批次列表 API 和 P-DATA Backfill 批次/阶段链只读下钻已实现，可查询真实 pilot 的对象引用、差异、资源使用、checkpoint 和完成范围；该入口复用现有 API Envelope 与 Backfill Projection，不新增平行存储或写入路径。它只证明控制面观察能力，不代表七阶段完整执行、发布或生产认证。
- 使用本地已有 `postgres:16` 镜像启动 tmpfs、loopback 随机端口的临时容器执行 Backfill PostgreSQL integration `16 passed, 2 warnings`：除 checkpoint/idempotency、取消 fence、lease/reaper 外，MONTH 1 分区与 YEAR 12 分区均实际写入 ProviderRun、RawObject、CanonicalPartition、DataSnapshot，并验证 Raw、Parquet 与 Snapshot Manifest；崩溃恢复案例确认 attempt 2 复用 attempt 1 已提交对象；另有七阶段 StageChain 线性依赖和依赖 Task 原子创建回归。
- 完整 `tests/integration/platform` 当前不能宣称收集通过：因既有环境缺少 `markdown2`，收集阶段有 2 个 `ModuleNotFoundError`；排除受该依赖影响的两个既有 API 模块后，隔离 PostgreSQL 实例上的结果为 `81 passed, 3 warnings`。
- 临时容器不复用已有持久化 `pg` 容器及其卷；测试数据库由 fixture 独立创建和删除。
- WP-0207 尚无远程阻断 CI；完整脱敏矩阵、P-DATA 阶段链下钻的真实 PostgreSQL/完整链路验收、七类数据完整端到端执行/发布验收，以及生产 Provider、生产数据库、真实 `/data`、生产调度/回填认证仍未完成。用户未授权 commit/push/PR，本轮未进行这些操作。

## 验证证据

### 取消与只读进度投影补验

- 新增真实 checkpoint 文件投影及 provider 内取消回归，先复现 2 failed / 106 passed：`unavailable` 被错误传入 requirements，取消 checkpoint 将未发布分区记为完成。修正字段白名单、checkpoint phase 投影及完成范围上界后，Backfill 单元与集成文件联合运行 109 passed / 3 skipped；三个 PostgreSQL 用例仍因隔离环境未配置跳过。
- PostgreSQL 用例改为断言原始 requirements/hash 不变、进度经 service 投影查询；此前未获得真实 PostgreSQL 执行证据；本轮已补充本地隔离 PostgreSQL deterministic pilot。分区安全点只是协作式取消，不是取消检查与发布之间的原子 fence；真实发布事务验收仍为 BLOCKER。
- checkpoint 读取失败现在返回脱敏的 `BACKFILL_CHECKPOINT_INVALID` 合同错误；最新 checkpoint 按 attempt number、created_at、sequence 选择，避免不同 attempt 的局部 sequence 互相覆盖。仍未完成真实发布事务的原子 fence 与跨 attempt PostgreSQL 验收。
- BackfillWorker 在已有分区安全点调用 Task Control Plane 的 `heartbeat` 续租；heartbeat 失败不被吞掉，交由既有 lease/error/reaper 语义处理。新增回归覆盖分区执行前及发布前续租调用。

### 子任务结果恢复分支补验

- 对现有 executor 测试增加无复用、复用 Raw、复用 Raw/Canonical、复用全部三类结果的参数组合；检查复用阶段不调用 worker、后续阶段仍执行、ProviderRun 引用保留。
- 新增三类子任务在 loader 缺失或返回空结果时拒绝恢复，以及 lease 身份/类型错误时不得改走 loader 的测试。以上使用 worker doubles，不证明真实持久化重试、结果归属校验或崩溃窗口安全。
- 最新 Backfill + Golden + Registry 定向运行：187 passed，2 warnings（Backfill 73 项）；覆盖新增 result_loader 分支。旧的 176 passed 是此前快照，不作为新增分支证据。
- 在上述基础上补充权威 Task 状态门禁回归：Backfill + Golden/Registry/P-DATA 定向运行 225 passed，2 warnings；Backfill 单套 105 passed，覆盖三类 child task 的所有 TaskState、结果复用、缺失结果和错误归属。
- 此前环境未配置时重跑 PostgreSQL Backfill 集成为 1 skipped；该历史结果不覆盖本轮隔离容器证据。
- PostgreSQL 集成用例已扩展为隔离 deterministic fixture 的 MONTH/YEAR pilot：当隔离环境可用时会实际创建 PostgreSQL Task、执行 1 个月与 1 年批次、持久化每个分区及最终 checkpoint，并验证发布引用数量；此前环境未配置时 2 个新增 pilot 用例与原用例均 skipped；本轮已在隔离 PostgreSQL 16 容器中重新执行并通过。
- Web 证据更正：此前 pnpm 调用意外重解析了依赖，产生的 41 个 ESLint 错误不能归因于原始基线。已从 node_modules/.ignored 恢复 37 个与 package-lock.json 一致的原依赖目录，未修改 manifest/lockfile。随后以 bundled Node.js v24.19.0 重新执行 `npm run lint` 与 `npm run build` 均 exit 0（Vite 7.3.1）；系统 Node.js v16.20.2 下仍因版本不足失败。
- 全套 API 测试导入仍缺少环境依赖 markdown2。Backfill 同名测试收集冲突已通过将新增集成文件重命名为 tests/integration/platform/test_backfill_integration.py 消除；setup.cfg 保持原始 import 模式。修正集成用例缺失的 DeterministicBackfillPublisher import、checkpoint 数量与 published_refs 字段位置；fixture writer 使用内容 hash 命名，防止同 attempt 的后续 checkpoint 覆盖历史文件。联合运行 Backfill 单元/集成文件为 106 passed、3 skipped；其中 1 个新通过项仅验证 fixture 文件不可覆盖，不是 PostgreSQL 验收。
- 排除 API 目录后运行 `tests/platform`：451 passed、21 failed、5 skipped；失败集中于既有 Canonical/Extended Canonical 测试，首个根因是环境缺少 `pyarrow`，代码按设计报 `CanonicalNormalizationError: The controlled Canonical Parquet engine is unavailable.`，未修改依赖或 Canonical 代码。WP-0207 定向套件仍为 226 passed、3 skipped。
- 重跑 ai-assets、baseline、generated exports 检查、Backfill service/test py_compile 和 git diff --check 均通过；本轮以 bundled Node.js v24.19.0 重跑 Web `npm run lint` 与 `npm run build` 均通过。
- 本次只读查询确认远端 main 仍为 `46804661dbb897433f114c25898c8da7021254a1`；G019 Run `34581431121` 及三个 Job 均 success。未产生 WP-0207 远程 CI，状态保持 IN_PROGRESS / NOT CERTIFIED。

### 本轮续租与 PostgreSQL pilot 补验

- 新增 BackfillWorker 续租拒绝回归：控制面在 Provider 前或发布安全点返回 `TASK_LEASE_LOST` 时，worker fail-closed，Provider/publisher 不继续执行。
- 首次启用隔离 PostgreSQL 16 容器执行 Backfill integration suite 时发现 checkpoint 时钟不一致：worker 使用 wall-clock 生成 expires_at，而 Task Control Plane 使用注入 clock 生成 created_at，导致 `expires_at must follow created_at`。修正为默认复用 Task Control Plane `_now`，并在修正后重新执行 4 passed。容器使用 tmpfs、loopback 随机端口和独立数据库，测试结束已删除。
- 本轮定向单元/集成/Golden/Registry/P-DATA 套件：234 passed、3 skipped、2 warnings；PostgreSQL Backfill integration：4 passed、1 warning。

### 本轮 lineage 与 Web 补验

- deterministic publication fixture 新增完整 ProviderRun→RawObject→CanonicalPartition→Snapshot lineage 记录，并补充 fallback lineage 回归；不改变生产对象或存储。
- 隔离 PostgreSQL Backfill integration 当前 5 passed，包含 parent Task 与三个 child Task 的 Raw→Canonical→Snapshot 顺序执行；child worker 仍为 deterministic fixture。
- WP-0207 定向套件当前 243 passed、4 skipped、2 warnings；使用 bundled Node.js v24.19.0 执行 Web `npm run lint` 与 `npm run build` 均 exit 0。系统 Node.js v16.20.2 下的失败仅为运行时版本限制。
- 本轮直接 `git ls-remote origin refs/heads/main` 两次均因 `Recv failure: Connection was reset` 失败；本地 `origin/main` ref 与 HEAD 相同，但本轮未取得新的远端实时 SHA 证明。

### 本轮 lineage fail-closed 修复与定向复验

- `DeterministicBackfillPublisher.publish()` 现在在非 dry-run、非 plan-only 发布前要求同时存在 `provider_run_refs`、`raw_object_refs` 和 `canonical_partition_refs`；缺失时返回脱敏的 `BACKFILL_LINEAGE_INCOMPLETE`，不会创建 Canonical/Snapshot fixture 发布记录。
- 新增不完整 lineage 边界测试由此前 `DID NOT RAISE BackfillError` 修正为通过；Backfill 阶段 pilot 与该回归共 `8 passed, 1 warning`。
- 当前定向套件为 `244 passed, 4 skipped, 2 warnings`；PostgreSQL 集成在本次默认环境未配置而跳过，前序隔离 PostgreSQL 16 的 `5 passed` 证据仍仅覆盖 deterministic child-task fixture，不等价于真实发布事务。
- `py_compile`、`export_platform_contracts.py --check`、`check_ai_assets.py`、`check_visory_baseline.py` 和 `git diff --check` 均通过。状态仍为 `IN_PROGRESS / NOT CERTIFIED`。
### 前序验证记录

- 当前工作区 HEAD、本地 main、origin/main 均为 `46804661dbb897433f114c25898c8da7021254a1`；本次 `git ls-remote origin refs/heads/main` 成功返回同一 SHA；WP-0206 Run `34581431121` 实时查询为 success，head 为 `dabded56823367816cbc992ca9dac61c0dd44e7f`，三项阻断 Job 均成功。
- 本轮 Backfill、Contract Golden/Registry 定向测试：176 passed，2 warnings，其中 Backfill 62 passed。先运行新增回归得到 15 failed / 34 passed（均因未拒绝不安全提交），修正后通过；新增前置 Task 全状态、陈旧调用方状态、错误身份/归属和 plan-only 门禁测试，并补充 BackfillWorker 委托现有 pipeline executor 后的三类产物引用回收测试。测试使用 fake Task 控制面，不代表 PostgreSQL 或真实发布闭环；前序 PostgreSQL 窄测试因隔离环境缺失 skipped，未在本轮重跑。
- `check_ai_assets.py`、`check_visory_baseline.py`、`export_platform_contracts.py --check`、Backfill service/schema 和 task schema 的 py_compile、git diff --check 通过。
- 使用 bundled Node v24.19.0 后，Web `npm run lint` 和 `npm run build` 均通过；系统 Node v16.20.2 下的失败仅记录为环境限制。
- 前序完整 backend gate 在 WSL 因 `python: command not found` 失败，未据此宣称完整后端通过。
- 没有执行生产 Provider、生产数据库、真实 /data 或生产回填认证。

## 后续验收与回滚边界

下一步收敛完整七阶段 Durable Task 链、完整脱敏矩阵和远程阻断 CI；隔离 month/year Raw→Canonical→Snapshot pilot、PostgreSQL 注册事务、跨 attempt 崩溃恢复与 Correction 不可变性已有本地证据。只推进 WP-0207，不推进 WP-0301。

当前未提交、未部署。回滚应逐文件检查并撤销仅属 WP-0207 的 diff，不得 reset 工作区或覆盖用户改动。本文为中文内部任务记录，没有对应双语文档。

### PostgreSQL 16 Docker 隔离复验（2026-09-24）

- 启动 Docker Desktop 后确认本地已有 `postgres:16` 镜像；未使用持久化 `pg` 容器或其卷，而是使用 `--rm`、`tmpfs` 数据目录、loopback 随机端口和独立测试数据库执行 `tests/integration/platform/test_backfill_integration.py`，结果为 `12 passed, 4 warnings`。
- 同一隔离 PostgreSQL 实例上执行完整 `tests/integration/platform`，结果为 `79 passed, 10 warnings`；警告仍为既有 pytest 收集、依赖弃用、Pydantic serializer 和测试缓存目录权限提示，未发现 WP-0207 测试失败。
- 测试结束已删除临时容器和测试密码文件；持久化 `pg` 容器保持 `Exited (0)`。该证据仍只证明本地隔离 deterministic fixture 和 PostgreSQL 控制面/注册表集成，不证明真实 Provider、生产数据库、真实 `/data` 或生产回填认证。

### API retryable 契约复验（2026-09-18）

- 列表、详情、创建三个 Backfill API 曾丢失 service 的 retryable，错误地改用 HTTP 状态默认值。新增六个经过现有异常处理器的 API 回归先得到 6 failed；显式传递 retryable 后定向套件为 250 passed、4 skipped、2 warnings。四个 PostgreSQL 用例因本轮未配置隔离实例而跳过，不作为集成通过证据。
- 本轮 git ls-remote 成功：远端 main、本地 HEAD 和 origin/main ref 均为 46804661dbb897433f114c25898c8da7021254a1，之前的网络阻断本次已解除。只读查询 G019 Run 34581431121 为 completed/success，head dabded56823367816cbc992ca9dac61c0dd44e7f，三个阻断 Job 全部 success；不等同于 WP-0207 CI。
- router/test py_compile 与 generated exports --check 通过。未启动生产服务、未提交或推送；目标仍 IN_PROGRESS / NOT CERTIFIED。

### 本轮 PostgreSQL 隔离验收补跑（2026-09-18）

- 使用现有本地 `pg` 容器，仅创建临时 `visory_test` 角色并在测试后删除；未连接生产数据库。`tests/integration/platform/test_backfill_integration.py` 实际执行 `5 passed, 1 warning`，覆盖 PostgreSQL Task/Checkpoint/Idempotency、MONTH/YEAR deterministic pilot，以及 Raw→Canonical→Snapshot child Task 顺序链。
- 临时测试密码文件已删除；该证据仍属于 deterministic worker fixture，不证明真实 Provider 或真实对象发布事务。WP-0207 仍为 `IN_PROGRESS / NOT CERTIFIED`。

### 当前基线与 WP-0206 复核（2026-09-18）

- 本轮重新确认 `main`、本地 `HEAD`、`origin/main` ref 与 `git ls-remote origin refs/heads/main` 均为 `46804661dbb897433f114c25898c8da7021254a1`。
- 读取 `IMPLEMENTATION-STATUS.md`、`GOAL-G019-STATUS.md` 及 WP-0206 既有 CI Run `34581431121`；未发现 WP-0206 状态、代码或远程证据被当前未提交 WP-0207 工作树覆盖的矛盾。
- 本轮未执行 reset、stash、commit、push 或 PR；WP-0207 仍保持 `IN_PROGRESS / NOT CERTIFIED`。

### 本轮 lineage cardinality fail-closed 补验（2026-09-18）

- 新增不完整 lineage cardinality 边界测试，先复现 `DID NOT RAISE BackfillError`，随后修正 `DeterministicBackfillPublisher.publish()`：非 dry-run/plan-only 发布现在同时要求三类 lineage 非空、数量一致且各自无重复引用。
- 定向 Backfill/Integration/Golden/Registry/P-DATA 套件由 `250 passed` 增至 `251 passed, 4 skipped, 2 warnings`；隔离 PostgreSQL integration 重新实际执行为 `5 passed, 1 warning`。
- 修复只约束离线 deterministic publication fixture，不宣称真实 Provider、真实 Raw/Canonical/Snapshot 事务或生产认证完成。



### Correction 公开契约收敛（2026-09-22）

- 新增 request-level Correction Golden fixture、resource ID 边界测试、API/Task/Projection 透传测试，以及 Snapshot child Task 的 lineage 注入与冲突拒绝回归。新增两项冲突测试先复现 `DID NOT RAISE BackfillError`，修正后相关 3 项通过。
- Backfill、Integration、Golden、Registry 与 generated-contract 定向套件当前为 `259 passed, 4 skipped, 2 warnings`；4 项跳过均为当前环境未配置 PostgreSQL，生成契约 `--check` 通过。该结果不作为 PostgreSQL、完整 backend gate 或远程 CI 通过证据，状态保持 `IN_PROGRESS / NOT CERTIFIED`。

### 本轮验证记录（2026-09-22）

- 重新确认当前分支为 `main`，本地 `HEAD`、本地 `origin/main` ref 与 `git ls-remote origin refs/heads/main` 均为 `46804661dbb897433f114c25898c8da7021254a1`；工作树仍为未提交 WP-0207 改动，未执行 reset、stash、commit、push 或 PR。
- 使用 bundled Node.js `v24.19.0` 执行 `apps/dsa-web` 的 `npm run lint` 与 `npm run build`，均 exit 0；构建产物包含 Backfill 页面 chunk。
- Backfill 单元/集成定向收集为 `135 passed, 4 skipped, 3 warnings`；4 项跳过源于当前环境缺少 PostgreSQL 测试配置，不作为 PostgreSQL 通过证据。
- `py_compile`、`scripts/check_ai_assets.py`、`scripts/check_visory_baseline.py`、`scripts/export_platform_contracts.py --check` 和 `git diff --check` 均通过；baseline 检查为 `imported_secrets: 0`、`broken_relative_links: 0`。
- 使用 Git Bash 调用 Windows `.venv` Python 执行完整 `scripts/ci_gate.sh`：syntax、Flake8 critical checks、generated contracts、code recognition、yfinance conversion 均通过；全量离线 pytest 最终为 `6818 passed, 82 failed, 77 skipped, 4 deselected, 572 subtests passed`，因此完整 backend gate 结论为失败。失败清单不含 Backfill 测试，主要集中在未改动的 Codex/本地 CLI/SQLite/Storage 等模块；其中多项 traceback 明确为 Windows 缺少 `os.killpg`，该本地结果不能替代 Linux 远程阻断 CI，也不据此扩大 WP-0207 范围修复无关模块。
- 此前在 Docker Desktop daemon 未启动时未能重新取得 PostgreSQL 实际执行证据；该历史环境阻塞已由下方本地 `postgres:16` tmpfs 隔离容器证据取代，仍未连接生产数据库。

### 本轮 checkpoint 完成范围与崩溃窗口收敛（2026-09-22）

- 新增失败回归先复现 dry-run 与 Unavailable 最终 checkpoint 错把整段日期写入 `completed_range`；BackfillWorker 现在只累计已完成业务发布的连续前缀，未发布范围保留在 `skipped_range`/质量事件中，并将 checkpoint handler version 升级为 `wp0207-backfill-v3`，避免恢复旧语义 checkpoint。
- 新增确定性父任务崩溃窗口回归：Raw→Canonical→Snapshot 子 Task 已成功后，模拟父 Backfill Task 在写 checkpoint 时崩溃；下一尝试通过相同子 Task 幂等键、权威 SUCCEEDED 状态和结果 loader 恢复，三个子 worker 均不重复执行。该证据使用 worker doubles，不替代 PostgreSQL、真实对象发布事务或取消原子 fence 验收。
- Backfill 单元文件当前为 `143 passed, 2 warnings`；联合 Backfill 单元/集成、Golden、Registry 与 generated-contract 定向套件为 `265 passed, 4 skipped, 2 warnings`。本轮新增 Projection 输入、公开 dataset 边界和取消终态回归均先失败后修正通过；4 项跳过均因当前环境未配置 PostgreSQL，不作为 PostgreSQL 集成通过证据；状态继续保持 `IN_PROGRESS / NOT CERTIFIED`。

### 本轮父取消与发布事务 fence 收敛（2026-09-22）

- 新增失败回归先复现两个缺口：pipeline executor 未向 child worker 传入父 attempt 发布门禁；child 发布事务拒绝后父 Backfill 未确认取消。修正后，RawObject、CanonicalPartition 和 DataSnapshot 的既有注册事务均在业务注册前锁定并校验父 Backfill attempt 的 lease、task identity、task type 与 `cancel_requested_at`。
- 父取消先提交时，当前 child Task 通过既有 `request_cancel`/`acknowledge_cancel` 收敛为 `CANCELLED`，父 Task 也返回 Backfill `CANCELLED`；若父 lease 已失效，门禁以 `TASK_LEASE_LOST` fail-closed，child/parent 留给既有 lease reaper 恢复，不把未注册结果报告为成功。
- 当前定向 Backfill/Integration/Golden/Registry/generated-contract 套件在隔离 PostgreSQL 16 上为 `274 passed, 2 warnings`；Backfill PostgreSQL integration 为 `7 passed, 1 warning`，覆盖 MONTH/YEAR pilot、checkpoint/idempotency、Durable Task child chain、父取消事务 fence 及父 lease 过期/reaper；完整 `tests/integration/platform` 为 `72 passed, 7 warnings`。另外受影响 Canonical/Snapshot 单元套件为 `55 passed, 1 warning`。
- 使用 `.venv` 的 Flake8 critical checks、受影响 Python `py_compile`、generated exports、AI assets、baseline 和 `git diff --check` 均通过；使用 bundled Node.js `v24.19.0` 执行 Web lint/build 均通过。2026-09-22 只读 GitHub 复核确认远端 `main` 仍为 `46804661dbb897433f114c25898c8da7021254a1`，与本地 `HEAD`、缓存 `origin/main` 一致；WP-0207 仍仅存在于未提交工作树，因此没有 WP-0207 远程阻断 CI。未连接生产 Provider、生产数据库、真实 `/data`、生产调度或服务器；状态保持 `IN_PROGRESS / NOT CERTIFIED`。

### 本轮 Docker PostgreSQL 实测（2026-09-22）

- 使用本地已有 `postgres:16` 镜像启动无持久卷、仅绑定 `127.0.0.1` 随机端口的临时容器；测试凭据只写入系统临时文件，未复用已有 `pg` 容器及其持久卷。
- 首次实际执行得到 `6 passed, 1 failed`：失败原因是测试只推进到原始 lease 到期时间，未计入 BackfillWorker 两个安全点 heartbeat 的续租；仅将测试时钟推进到续租后到期时间之外，生产代码未修改。
- 修正后 Backfill PostgreSQL integration 为 `7 passed, 1 warning`；WP-0207 联合定向套件为 `274 passed, 2 warnings`；完整平台 PostgreSQL integration 为 `72 passed, 7 warnings`。
- 测试结束后确认无残留 `visory_test_*` 数据库，临时容器和密码文件均已删除。该证据关闭本地 PostgreSQL fence/reaper 阻塞，但远程阻断 CI、真实对象发布事务、跨 attempt 真实发布崩溃窗口和完整七阶段链仍未完成，状态保持 `IN_PROGRESS / NOT CERTIFIED`。

### 本轮真实对象链 PostgreSQL pilot（2026-09-22）

- 在本地已有 `postgres:16` 镜像上启动 `--tmpfs /var/lib/postgresql/data`、仅绑定 `127.0.0.1` 随机端口的临时容器；已有持久化 `pg` 容器保持停止，未启动、未修改、未复用。
- 新增参数化 PostgreSQL 集成测试直接使用 `RawIngestionTaskWorker`、`CanonicalNormalizationTaskWorker`、`SnapshotBuildTaskWorker`、`BackfillPipelineCoordinator`、`BackfillPipelineExecutor` 与 `BackfillWorker`：MONTH 实际发布 1 个分区，YEAR 实际发布 12 个按月分区。
- 每个分区均验证独立 ProviderRun/RawObject/CanonicalPartition/DataSnapshot 注册记录、父 Backfill publication guard、Raw 文件、Canonical Parquet、Snapshot Manifest 及 Backfill Projection 对象引用；Trading Calendar 使用与 Snapshot trade_date 一致的独立 Canonical partition。
- 实测结果：参数化真实对象链 `2 passed, 3 warnings`；Backfill PostgreSQL integration `9 passed, 3 warnings`；完整 `tests/integration/platform` `74 passed, 9 warnings`；Backfill/Integration/Golden/Registry/generated/P-DATA 定向套件 `176 passed, 5 warnings`。警告为既有 pytest cache 权限、Pydantic serializer 及平台依赖弃用/收集提示，未据此扩大生产代码范围。
- Provider transport 为隔离 deterministic fixture；未连接真实 Provider、生产数据库、真实 `/data`、生产调度或服务器。在该次 pilot 时仍缺跨 attempt 真实对象发布崩溃窗口、完整七阶段 Durable Task 链和 WP-0207 远程阻断 CI，因此状态保持 `IN_PROGRESS / NOT CERTIFIED`。
- 测试结束前确认无残留 `visory_test_*` 数据库；临时容器已停止并因 `--rm` 删除，临时密码/env 文件已删除；已有持久化 `pg` 容器继续保持停止且未修改。

### 本轮真实对象跨 attempt 崩溃恢复（2026-09-22）

- 将真实对象链参数化 pilot 扩展为 `month-checkpoint-crash-recovery`：attempt 1 完成 RawIngestion、CanonicalNormalization、SnapshotBuild 三个 child Task 并提交 ProviderRun、RawObject、CanonicalPartition、DataSnapshot 后，以 `BaseException` 模拟父进程在写 checkpoint 前退出；父 Task 保持 `RUNNING`，随后将注入时钟推进到两次 heartbeat 后的 lease 到期时间之外，由既有 reaper/`lease_next` 创建 attempt 2。
- 首次运行得到 `1 failed, 2 passed`，暴露真实 pipeline Projection 混入 deterministic Provider 的计划 fixture ID。根因是 BackfillWorker 无条件合并 provider result 中的 fixture lineage，与“registry lineage 为 authoritative”的既有契约矛盾；修正为仅在没有 pipeline executor 时接收 fixture lineage，真实 pipeline 模式只接收 executor 从 PostgreSQL 注册表取得或恢复的引用。
- 修正后参数化 pilot 为 `3 passed, 4 warnings`：attempt 2 的三个 child Task ID 保持不变、每个 child 仅有 1 个 attempt、行情 transport fetch 次数仍为 1，且四类对象 ID 与崩溃前完全一致；Projection 不再包含伪 ProviderRun ID。
- 回归结果：Backfill PostgreSQL integration `10 passed, 4 warnings`；完整 `tests/integration/platform` `75 passed, 10 warnings`；Backfill/Integration/Golden/Registry/generated/P-DATA 定向套件 `177 passed, 6 warnings`。关键 Flake8、受影响 Python `py_compile`、generated exports、AI assets、baseline 与 `git diff --check` 均通过；bundled Node.js `v24.19.0` 下 Web lint/build 均通过。
- 该证据关闭本地隔离 PostgreSQL 的跨 attempt 真实对象恢复缺口；Provider transport 仍为 deterministic fixture，且尚无 WP-0207 远程阻断 CI、完整七阶段链或生产认证，状态保持 `IN_PROGRESS / NOT CERTIFIED / 13/45`。


### 本轮 Docker PostgreSQL StageChain 与门禁复验（2026-09-23）

- 开始前复核当前分支为 `main`；本地 `HEAD`、`origin/main` 与 `git ls-remote origin refs/heads/main` 均为 `46804661dbb897433f114c25898c8da7021254a1`。工作树仍为未提交 WP-0207 改动；未执行 reset、stash、commit、push 或 PR。
- 使用本机已有 `postgres:16` 镜像启动仅绑定 `127.0.0.1` 随机端口的临时容器，并由测试 fixture 为每个用例创建隔离 `visory_test_*` 数据库；已有持久化 `pg` 容器保持 `Exited (0)`，未启动、未复用、未修改。临时密码文件和容器均在测试结束后清理。
- 新增七阶段 `BackfillStageChainExecutor` PostgreSQL worker 验证：`1 passed, 11 deselected, 2 warnings`；完整 Backfill PostgreSQL integration：`12 passed, 5 warnings`；Backfill 单元：`151 passed, 3 warnings`；Contract/Golden/Registry/generated 定向套件：`278 passed, 3 warnings`。
- 使用 bundled Node.js `v24.19.0` 且将 bundled Node 置于子进程 `PATH` 前端，`apps/dsa-web` 的 `npm run lint` 与 `npm run build` 均 exit 0；构建产物包含 `BackfillPage` chunk。
- `check_ai_assets.py`、`check_visory_baseline.py`、`export_platform_contracts.py --check`、受影响 Python 文件 `py_compile`（21 个文件）和 `git diff --check` 均通过；`git diff --check` 仅报告既有 CRLF 转换提示，无 whitespace error。
- 本轮证据仍为隔离 deterministic provider/publisher 与本地 PostgreSQL 控制面验证，不代表真实 Provider、生产数据库、真实 `/data`、生产调度或生产回填认证。完整 `tests/integration/platform`、远程 WP-0207 阻断 CI、完整七类数据真实逐阶段发布和脱敏矩阵仍未完成；WP-0207 继续保持 `IN_PROGRESS / NOT CERTIFIED / 13/45`，不得标记 `VERIFIED` 或 `RELEASED`。
## 当前回合复验（2026-09-28）

- 相关 Python 定向套件重新执行为 `183 passed, 15 skipped, 3 warnings`；Contract Registry/generated exports、`check_ai_assets.py`、`check_visory_baseline.py`、`export_platform_contracts.py --check` 与 `git diff --check` 均通过。
- Web Backfill API/Page 定向 Vitest 为 `9 passed`；使用 bundled Node.js `v24.19.0` 直接执行 Vite production build 成功，产物包含 `BackfillPage` chunk；修改文件定向 ESLint 通过。
- 全量 Web ESLint 仍报告 `41 errors`，均位于既有未修改页面/组件及既有 Operations 页面路径；本轮未扩大 WP-0207 范围修复。系统 Node.js `v16.20.2` 运行 `npm run lint` 另受 `structuredClone` 运行时限制；这些结果均不宣称全量 Web lint 通过。
- 本轮未新增远程 WP-0207 阻断 CI，也未连接真实 Provider、生产数据库、真实 `/data`、生产调度或服务器；WP-0207 继续保持 `IN_PROGRESS / NOT CERTIFIED / 13/45`，不得标记 `VERIFIED` 或 `RELEASED`。
## 当前回合补验（2026-09-28）

- 本轮再次尝试 `git ls-remote origin refs/heads/main` 时连接被远端重置；本地 `main`、缓存 `origin/main` 与 HEAD 仍一致，最近一次成功的实时复核仍返回 `46804661dbb897433f114c25898c8da7021254a1`，未执行 fetch、pull、commit、push 或 PR。
- 本轮此前记录的 bundled Node.js v24.19.0 Web lint/build 成功结论已用直接命令复核：Vite build 成功、修改文件定向 ESLint 成功，但全量 ESLint 仍有 41 个既有未修改路径错误；Docker 可用性探测未在本轮得到可复用的新增 PostgreSQL 终态，继续引用此前隔离 postgres:16 证据。
- 随后使用临时 `postgres:16` 容器（tmpfs、loopback-only、独立数据库）实际执行 `tests/integration/platform/test_backfill_integration.py`，结果为 `16 passed, 1 warning`；容器和临时密码文件已清理，未复用持久化数据库。

- 基线复核：当前分支为 `main`，本地 `HEAD`、本地 `main`、缓存 `origin/main` 与实时 `git ls-remote origin refs/heads/main` 均为 `46804661dbb897433f114c25898c8da7021254a1`；未执行 fetch、pull、commit、push 或 PR。
- WP-0206 复核：GitHub 只读结果确认 PR #36 和状态收尾 PR #37 均已合入，PR #37 的 merge commit 为 `46804661dbb897433f114c25898c8da7021254a1`，并记录 Run `34581431121` 的 Governance、Python deterministic gate、Web lint/build 成功；没有发现当前未提交 WP-0207 工作树覆盖 WP-0206 已合入代码或状态文件的证据。
- 当前 WP-0207 相关 Python 定向套件为 `389 passed, 53 skipped, 3 warnings`；隔离 `postgres:16` tmpfs/loopback 临时容器中的 Backfill integration 为 `16 passed, 1 warning`，覆盖 MONTH 1 分区、YEAR 12 分区、dry-run/plan-only、checkpoint 恢复、幂等、取消/失败、fallback/quarantine/unavailable、Correction 不覆盖旧 Snapshot 与受控依赖 Task。
- Contract Registry/generated exports、`check_ai_assets.py`、`check_visory_baseline.py`、受影响 Python `py_compile`、`git diff --check` 均通过；Backfill 页面/API 定向 Vitest 为 `4 passed`，bundled Node.js `v24.19.0` 下 Web lint/build 均通过。
- 完整 Web Vitest 为 `1107 passed, 3 failed, 2 skipped`；3 个失败位于未被 WP-0207 修改的既有 `DecisionSignalsPage`、`AlertRuleForm`、`SettingsField` 测试路径。本轮不扩大 WP-0207 范围修复，但不把完整 Web 测试描述为通过。
- Web Backfill 错误投影新增防御性公开字段校验与敏感文本拒绝；定向 Vitest 更新为 `7 passed`，不改变后端 API Envelope 契约。
- 新增 P-DATA Backfill 与阶段链未知异常回归：内部异常、凭据、绝对路径和原始 payload 均被统一投影为公开 `INTERNAL_ERROR` Envelope；相关 Python 定向套件为 `182 passed, 15 skipped, 3 warnings`，`git diff --check` 通过。结论保持 `IN_PROGRESS / NOT CERTIFIED / 13/45`。WP-0207 仍没有远程阻断 CI；七类数据完整逐阶段生产级执行/发布、真实 Provider、生产数据库、真实 `/data`、生产调度和生产回填认证仍未完成，不得标记 `VERIFIED` 或 `RELEASED`。

## 当前回合 PostgreSQL 补验（2026-09-28）

- Docker Desktop 当前可用；使用临时 `postgres:16` 容器、`tmpfs` 数据目录、`127.0.0.1` 随机端口、独立测试数据库和临时密码文件执行 `tests/integration/platform/test_backfill_integration.py`，结果为 `16 passed, 2 warnings`。
- 覆盖 MONTH 1/YEAR 12 pilot、dry-run/plan-only、checkpoint 恢复、幂等重试、取消/失败、provider fallback、quarantine/unavailable、Correction 不覆盖旧 Snapshot、七阶段 StageChain 和受控依赖 Task。测试容器、独立数据库和临时凭据已清理，未复用持久化数据库。
- 该证据仍只证明隔离 deterministic fixture 与本地 PostgreSQL 控制面/注册表集成，不代表真实 Provider、生产数据库、真实 `/data`、生产调度或生产回填认证；WP-0207 继续为 `IN_PROGRESS / NOT CERTIFIED / 13/45`。

## 当前回合阶段链连续性边界（2026-09-28）

- 先新增失败回归，复现 `BackfillStageChainProjection` 接受跳过中间阶段的非连续 partial chain；修正后 projection 只接受路线图的连续前缀，仍保持最多七阶段、固定顺序和既有 Task 依赖校验。
- 该修正仅收紧 WP-0207 P-DATA 读投影契约，不新增队列、状态机、存储模型或生产连接；WP-0207 继续保持 `IN_PROGRESS / NOT CERTIFIED / 13/45`。

## 当前回合单日范围契约（2026-09-28）

- 新增 `trade_date` 单日 shorthand：服务端将其规范化为 `date_from == date_to`，同时继续支持现有日期范围；显式同时提供两种语义但日期不一致时 fail-closed。
- 该变更仅扩展 WP-0207 Backfill 输入/Task/Projection 契约并同步生成 Schema/OpenAPI/frontend exports，不改变既有 Task、Snapshot、Canonical 或 Provider 存储语义；WP-0207 继续保持 `IN_PROGRESS / NOT CERTIFIED / 13/45`。
- 2026-09-28 当前 Goal 续验：本地分支 `main`、`HEAD` 与缓存 `origin/main` 仍为 `46804661dbb897433f114c25898c8da7021254a1`，`main...origin/main = 0/0`；本次 `git ls-remote origin refs/heads/main` 因 GitHub 连接低速超时失败，记录为实时远程基线 `BLOCKER`，未执行 `fetch`、`pull`、`reset`、`stash`、`commit`、`push` 或 PR。定向 Python 为 `182 passed, 15 skipped, 2 warnings`；Backfill Web Vitest 为 `9 passed`；Contract/generation、治理检查、受影响 Python `py_compile`、定向 ESLint、`tsc -b`、Vite build 和 `git diff --check` 通过。全量 Web ESLint 的 41 个错误仍属于未修改路径既有问题；隔离 PostgreSQL `16 passed` 证据仍为 deterministic fixture，不代表生产认证。WP-0207 保持 `IN_PROGRESS / NOT CERTIFIED / 13/45`。
- 2026-09-28 当前 Goal 续验补充：使用临时 `postgres:16-alpine`、tmpfs、loopback-only `127.0.0.1:55439` 和临时 Secret 文件执行 `tests/integration/platform/test_backfill_integration.py`，结果 `16 passed, 2 warnings`；测试容器和凭据已清理。该结果仅证明隔离 deterministic fixture，不代表真实 Provider、生产数据库、真实 `/data` 或生产回填认证。WP-0207 仍为 `IN_PROGRESS / NOT CERTIFIED / 13/45`。
- 2026-09-28 当前 Goal 续验：实时 `git ls-remote origin refs/heads/main` 成功返回 `46804661dbb897433f114c25898c8da7021254a1`，与本地 `HEAD`、`main` 和缓存 `origin/main` 一致，`main...origin/main = 0/0`。WP-0207 定向 Python/Contract 套件为 `182 passed, 15 skipped, 2 warnings`；Contract/generated exports、`check_ai_assets.py`、`check_visory_baseline.py` 均通过；范围审计未发现 WP-0301 或相邻 Work Package 路径。WP-0207 仍保持 `IN_PROGRESS / NOT CERTIFIED / 13/45`。

## 2026-09-28 当前 checkout 与 TaskLease 脱敏复核

- 当前实际 checkout 为 `codex/wp-0207-backfill`；文档记录前代码工作树 clean，本轮当前仅有本节文档改动；HEAD 为 `b5ab2da578cbad1e34e854cc3b67a0bc957185bb`；本地 `main`、缓存 `origin/main` 与实时 `git ls-remote origin refs/heads/main` 均为 `46804661dbb897433f114c25898c8da7021254a1`，未执行 fetch、pull、reset、stash、commit 或 push。
- WP-0206 代码、`GOAL-G019-STATUS.md` 与既有 Run `34581431121` 证据未被 WP-0207 覆盖；WP-0207 仍保持 `IN_PROGRESS / NOT CERTIFIED / 13/45`，不得标记 `VERIFIED` 或 `RELEASED`。
- 只读审计确认 `TaskLease.lease_token` 仅在 worker/Task Control Plane 内部使用；公共任务详情移除 `lease_token_hash`，列表/取消/重试仅返回 `TaskRecord`，SSE 仅返回 `TaskEventRecord`，Backfill/P-DATA Projection 不包含 raw lease token。当前未发现 WP-0207 直接的 raw lease token 公共暴露；本轮不修改既有 Durable Task 脱敏契约。
- 本轮不连接真实 Provider、生产数据库、真实 `/data`、生产调度或生产回填；隔离 deterministic fixture 证据不等同于生产认证。

## 2026-09-28 当前回合续验结果

- 实时 `git ls-remote origin refs/heads/main` 成功返回 `46804661dbb897433f114c25898c8da7021254a1`；当前 checkout 为 `codex/wp-0207-backfill`，HEAD 为 `b5ab2da578cbad1e34e854cc3b67a0bc957185bb`，未执行任何 Git 写操作。
- `.venv` 定向 Python 套件 `tests/platform/test_backfill.py tests/platform/api/test_generated_contracts.py tests/integration/platform/test_data_quality_api.py` 为 `188 passed, 3 warnings`；临时 `postgres:16-alpine`、tmpfs、loopback-only 容器中的 `tests/integration/platform/test_backfill_integration.py` 为 `16 passed, 1 warning`，容器与测试凭据已清理。
- Contract Registry/generated exports、`check_ai_assets.py`、`check_visory_baseline.py`、22 个受影响 Python 文件 `py_compile`、`git diff --check`、Backfill Web Vitest `9 passed`、修改文件定向 ESLint、`tsc -b` 和 Vite build 均通过。
- 当前证据仍不包含真实 Provider、生产数据库、真实 `/data`、生产调度或生产回填认证；WP-0207 保持 `IN_PROGRESS / NOT CERTIFIED / 13/45`，不得标记 `VERIFIED` 或 `RELEASED`。

## 2026-09-28 当前回合远程阻断复核

- 本轮只读执行 `git ls-remote origin refs/heads/main` 因 GitHub 连接低速超时失败；本次未取得实时远程 SHA，记录为远程基线 `BLOCKER`。
- 本地 `main`、缓存 `origin/main` 仍为 `46804661dbb897433f114c25898c8da7021254a1`；当前 checkout 仍为 `codex/wp-0207-backfill`，未执行 fetch、pull、reset、stash、commit 或 push。
- 本地 WP-0207 验收证据保持有效。该历史记录形成时尚未完成远程复核；现已确认 PR #38 已存在，Run `36404883866` 的三项远程阻断 Job 均成功，因此本条“专用 PR 与远程阻断 CI 仍未建立”结论已被后续事实取代；状态继续为 `IN_PROGRESS / NOT CERTIFIED / 13/45`，不得标记 `VERIFIED` 或 `RELEASED`。


## 2026-09-29 当前权威复核与远程证据

- 当前 checkout 为 `codex/wp-0207-backfill`，HEAD 为 `b5ab2da578cbad1e34e854cc3b67a0bc957185bb`；本地 `main`、缓存 `origin/main` 与实时 `git ls-remote origin refs/heads/main` 均为 `46804661dbb897433f114c25898c8da7021254a1`。工作树仅保留本次两份状态文档的有意修订，未执行 reset、stash 或覆盖用户改动。
- WP-0206 仍以 `46804661dbb897433f114c25898c8da7021254a1` 为合入基线；代码、`GOAL-G019-STATUS.md` 与 Run `34581431121` 的既有证据未被 WP-0207 覆盖。
- 已确认现有 PR #38（`feat: add WP-0207 backfill control plane`）对应当前 HEAD，未创建重复 PR；Run `36404883866` 的 Governance and repository boundaries、Python deterministic gate、Web lint and build 三个阻断 Job 均 `completed / success`。
- 本地验收证据保持：定向 Python `188 passed, 3 warnings`；隔离 `postgres:16-alpine` Backfill integration `16 passed, 1 warning`；Backfill Web Vitest `9 passed`；Contract/generated exports、治理检查、受影响 Python `py_compile`、定向 ESLint、`tsc -b`、Vite build 和 `git diff --check` 通过。
- 全量 Web ESLint 的 41 个错误和完整 Web 测试的既有失败仍未被 WP-0207 修改；不将其宣称为 WP-0207 通过。未连接真实 Provider、生产数据库、真实 `/data`、生产调度或生产回填。
- WP-0207 继续保持 `IN_PROGRESS / NOT CERTIFIED / 13/45`；尚未满足七类数据完整逐阶段生产级发布、完整脱敏矩阵和生产认证等 VERIFIED 门槛，不得标记 `VERIFIED` 或 `RELEASED`。
