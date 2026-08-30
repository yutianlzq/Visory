# Visory-G008 / WP-0103 进度与验收记录

最后更新：2026-08-30

## 1. 当前状态

- Goal：`Visory-G008`
- Work Package：`WP-0103 Durable Task Control Plane`
- Goal 状态：`IN_PROGRESS`
- Work Package 状态：`IN_PROGRESS`
- 固定基线：`main=a9a640b9c5910f839c036a94c85baec376ca7395`
- 工作分支：`goal/g008-wp-0103-durable-task-control-plane`
- 已验证 Work Package：`5/45`
- 目标 Alembic head：`0004_wp0103_durable_task_control_plane`
- parent：`0003_wp0102_artifact_registry`

开始前已核验本地 `HEAD`、本地 `origin/main` 与 GitHub `main` 均为固定基线 `a9a640b9c5910f839c036a94c85baec376ca7395`，工作区干净。G007 已登记为 `COMPLETE / MERGED`：PR #6 通过普通 merge commit `a9a640b9c5910f839c036a94c85baec376ca7395` 合入，最终 GitHub Actions Run `33299476674` 的 Governance、Python、Web 三项阻断 Job 全绿。

WP-0103 开始时进度保持 `5/45`。只有 Migration、真实 PostgreSQL 并发/故障测试、纵向 Artifact 闭环、契约生成、Legacy 回归和 GitHub 三项阻断 Job 的证据全部齐全后，才可将 WP-0103 标记为 `VERIFIED` 并更新为 `6/45`。

## 2. 当前实现范围

- PostgreSQL Task、TaskAttempt、TaskStateEvent、TaskCheckpoint 与 Command Idempotency；
- 严格 Task State 状态机、Lease、心跳、Lease Lost、Retry、Cancel 与 Blocked 恢复；
- Checkpoint 完整性和版本校验；
- `artifact_orphan_dry_run` 单 Worker 纵向闭环；
- C-010 最小 Task API 与生成契约。

## 3. 明确边界

- 不替换 Legacy 内存 Task Queue；
- 不实现 WP-0104、SSE、多 Worker 集群、正式调度策略或其他领域任务；
- 不创建或写入真实 `/data`，不部署，不写生产 Secret；
- 不修改 `upstream/`、`references/`；
- 不直接提交 `main`、不 force push、不合并本 Goal PR。

## 4. 验收证据

实施中，尚未标记 `VERIFIED`。
