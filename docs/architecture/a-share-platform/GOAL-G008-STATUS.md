# Visory-G008 / WP-0103 进度与验收记录

最后更新：2026-08-30

## 1. 当前状态

- Goal：`Visory-G008`
- Work Package：`WP-0103 Durable Task Control Plane`
- Goal 状态：`COMPLETE / PR OPEN`
- Work Package 状态：`VERIFIED`
- 固定基线：`main=a9a640b9c5910f839c036a94c85baec376ca7395`
- 工作分支：`goal/g008-wp-0103-durable-task-control-plane`
- 已验证 Work Package：`6/45`
- 目标 Alembic head：`0004_wp0103_durable_task_control_plane`
- parent：`0003_wp0102_artifact_registry`

开始前已核验本地 `HEAD`、本地 `origin/main` 与 GitHub `main` 均为固定基线 `a9a640b9c5910f839c036a94c85baec376ca7395`，工作区干净。G007 已登记为 `COMPLETE / MERGED`：PR #6 通过普通 merge commit `a9a640b9c5910f839c036a94c85baec376ca7395` 合入，最终 GitHub Actions Run `33299476674` 的 Governance、Python、Web 三项阻断 Job 全绿。

WP-0103 开始时进度保持 `5/45`。Migration、真实 PostgreSQL 并发/故障测试、纵向 Artifact 闭环、契约生成、Legacy 回归和 GitHub 三项阻断 Job 的证据现已齐全，WP-0103 标记为 `VERIFIED`，已验证进度更新为 `6/45`。

## 2. 实现结果

### 2.1 PostgreSQL Task Control Schema

- 新增 Migration `0004_wp0103_durable_task_control_plane`，parent 为 `0003_wp0102_artifact_registry`；
- 新建 `platform_task`、`task_attempt`、`task_state_event`、`task_checkpoint`、`task_command_idempotency`；
- Task、Attempt、状态事件和幂等命令使用 PostgreSQL 约束、唯一索引、可延期外键和 `timestamptz`；
- Repository 不隐式 commit，状态转换、Attempt 创建和 Event 追加均由 Application Service 事务控制；
- 由于完整 revision 名超过 Alembic 默认 `VARCHAR(32)`，`0004` upgrade 将 `alembic_version.version_num` 扩为 `VARCHAR(64)`。

### 2.2 状态机、Lease 与幂等

- Task State 仅允许已确认的 `ACCEPTED / QUEUED / BLOCKED / LEASED / RUNNING / RETRY_WAIT / SUCCEEDED / DEGRADED / FAILED / CANCELLED` 转换；所有转换追加 `task_state_event`，非法转换在事务内拒绝；
- Task State 与 Attempt Phase 分离；Retry 创建新 Attempt，旧 Attempt 保持不可变；
- Worker 领取使用 PostgreSQL 行锁与 `FOR UPDATE SKIP LOCKED`，固定按 `priority_class + priority_value + queued_at + task_id` 排序；
- Worker 写入统一按 `Task → Attempt` 顺序加锁，并验证 `attempt_id + lease_token + lease未过期`；数据库只保存 Lease/Resume Token SHA-256 Hash，原始 Token 只返回 Worker；
- 支持心跳续租、Lease Lost、服务重启恢复、最大 Attempt 限制、协作式 Cancel、Retry、Blocked 原因/恢复条件和 Checkpoint 完整性验证；
- Command 使用 Owner、端点、`Idempotency-Key` 和规范 Payload Hash 幂等；相同 Key 不同 Payload 返回稳定 `TASK_IDEMPOTENCY_CONFLICT`，Force 生成新 Task Key 并保存 lineage/reason。

### 2.3 首个纵向维护任务

- `artifact_orphan_dry_run` 完成 `Scheduler入队 → Worker领取 → 执行Dry-run → G007 Artifact Publisher → Task终态` 闭环；
- Artifact Registry insert、Attempt 完成、Task 终态和 `result_artifact_id` 在同一 PostgreSQL 事务提交；
- rename 失败不写 Registry；rename 成功而 Task/Registry 事务失败时留下不可见 Orphan；Lease Lost、取消竞态或发布失败均不得产生可见结果 Artifact；
- 任务只生成 JSON Dry-run Artifact，不执行删除，不扫描未知目录，不触碰 `PINNED / AUDIT` 引用闭包。

### 2.4 最小 C-010 API 与生成链

新增：

- `POST /api/platform/v1/tasks`
- `GET /api/platform/v1/tasks/{task_id}`
- `POST /api/platform/v1/tasks/{task_id}/cancellations`
- `POST /api/platform/v1/tasks/{task_id}/retries`

创建命令必须提供 `Idempotency-Key`。响应使用 C-010 Envelope、Request ID 和稳定 `TASK_*` 错误码，不回显路径、SQL、Token、DSN 或 Secret。未新增页面、SSE、Artifact 下载、任意路径访问或未经认证的文件服务。

Task、Attempt、StateEvent、Checkpoint、Lease、创建/取消/重试请求和查询结果已纳入 Contract Registry、JSON Schema、C-010 OpenAPI components 与前端 TypeScript 确定性生成链。

## 3. 本地验收证据

### 3.1 定向、平台与 Legacy 回归

- `python -m pytest tests/platform -q`：`257 passed, 5 skipped`；Windows skip 为本机 Symlink/权限差异用例；
- `python -m pytest tests/test_task_service.py tests/test_task_queue_config_sync.py tests/test_analysis_api_contract.py -q`：`106 passed`，Legacy 内存 Task Queue 与现有分析 API 行为未变；
- 修改 Python 文件 `py_compile`：通过；
- 修改 Python 文件完整 flake8：通过；
- `python scripts/export_platform_contracts.py --check`：通过，生成链无漂移；
- `python scripts/check_ai_assets.py`：通过；
- `python scripts/check_visory_baseline.py`：通过，8 个 runtime path、10 个 reference、0 imported secret、583 个相对链接、0 broken link；检查期间仅将 ignored `.venv` 临时移动到仓库 `build/` 排除目录，执行后原样恢复；
- `git diff --check`：通过。

全量离线 pytest 本机结果为 `6521 passed, 37 skipped, 83 failed, 4 deselected`。失败集中于本机 Codex 子进程/命名管道、Windows 无 Bash、SQLite 并发/文件权限和本机 CLI 探测等既有环境路径；WP-0103 平台、PostgreSQL、Legacy Task Queue/API 定向回归均独立全绿。最终 Python 阻断结论以 clean GitHub Ubuntu Job 为准。

### 3.2 PostgreSQL 16 真实集成

使用本地 Docker `postgres:16`、`127.0.0.1` 随机端口、随机临时密码文件引用和每用例隔离数据库执行 `tests/integration/platform`：`30 passed`。

已验证：

- 空库 upgrade、重复 upgrade、downgrade base、重新 upgrade 与 Migration 状态；
- 并发幂等 Command 只创建一个 Task；
- 并发 Worker 只能一个领取；
- 心跳、Lease 过期、Lease Lost、旧 Worker 写入/发布拒绝和服务重启恢复；
- Retry 新 Attempt、Cancel、Blocked/恢复、max attempts；
- Checkpoint Token/Input/Handler/Hash/StorageRef 校验；
- Artifact rename 失败、Registry/Task 事务失败、取消竞态和不可见 Orphan；
- `artifact_orphan_dry_run` 完整纵向闭环；
- PostgreSQL 连接归还和隔离测试数据库清理。

测试容器、临时 Secret 文件和隔离数据库均在命令结束后删除；原有 `nginx`、`redis` 容器未调整。

### 3.3 Web

在 `apps/dsa-web` 执行：

- `npm run lint`：通过；
- `npm run build`：通过。

## 4. 验收结论

- 契约提交：`77e5ca6`（`test: define durable task control contracts`）；
- 实现 head：`826aacfa2965c98efff8a8795a46dc9f72edec5f`（`feat: add durable task control plane`）；
- PR：[#7](https://github.com/yutianlzq/Visory/pull/7)，当前保持 open、未合并；
- GitHub Actions Run：[`33314470672`](https://github.com/yutianlzq/Visory/actions/runs/33314470672)，Governance、Python、Web 三项阻断 Job 全部成功；
- WP-0103 状态为 `VERIFIED`，已验证 Work Package 进度为 `6/45`；
- 未经 owner 明确批准不得合并，且本 Goal 不启动 WP-0104。

## 5. 环境、风险与回滚

- Python：`.venv` Python `3.12.9`，未新增或升级依赖；
- Docker：Server `29.2.1`，测试镜像 `postgres:16`；未修改 Compose、生产容器或网络；
- Secret：测试密码仅存在于一次性临时文件，所有报告统一显示为 `***`；未使用生产 Secret；
- Storage：所有 Artifact/Checkpoint 测试使用每用例临时目录；未创建或写入真实 `/data`；
- 部署：未部署、未写服务器、未修改 `upstream/` 或 `references/`；
- 已知风险：本地全量 pytest 的 83 个环境性失败已由 clean GitHub Python Job 的成功结果完成阻断核验；Checkpoint 物理文件不由 Alembic downgrade 删除，符合 Storage/DB 分离契约；
- Schema 回滚：在隔离数据库 downgrade 至 `0003_wp0102_artifact_registry`，删除 WP-0103 五张表；不会自动删除 Artifact、Checkpoint 或 Orphan 文件；
- 代码回滚：revert G008 实现 commits；移除 `VISORY_POSTGRES_*` 后 Legacy SQLite、Legacy Task Queue 和现有 API 继续按原行为运行。
