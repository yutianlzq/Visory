# Visory-G007 / WP-0102 进度与验收记录

最后更新：2026-08-30

## 1. 当前状态

- Goal：`Visory-G007`
- Work Package：`WP-0102 Storage Namespace与Artifact Publisher`
- Goal 状态：`IN_PROGRESS`
- Work Package 状态：`IN_PROGRESS`
- 固定基线：`main=01e1a986418b2bdae71fed5e3176ff87a337f279`
- 工作分支：`goal/g007-wp-0102-storage-artifact-publisher`
- 已验证 Work Package：`4/45`
- 计划 Alembic head：`0003_wp0102_artifact_registry`
- parent：`0002_wp0101_asset_identity`

开始前已核验本地 `HEAD`、`origin/main` 与 GitHub `main` 均为固定基线 `01e1a986418b2bdae71fed5e3176ff87a337f279`，工作区干净。G006 已登记为 `COMPLETE / MERGED`：PR #5 于 2026-08-30 合入，merge commit 为固定基线，最终 Actions Run `33288412520` 的 Governance、Python、Web 三项阻断 Job 全绿。

本 Goal 在实现和 Exit Gate 完成前保持 `4/45`。只有本地确定性验收、真实 PostgreSQL 集成、生成链无漂移和 PR 三项阻断 CI 均有可复现证据后，WP-0102 才可标记为 `VERIFIED` 并更新为 `5/45`。

## 2. 目标范围

- 实现 `VISORY_RUNTIME_ROOT` 环境绑定下的 Storage Namespace Resolver，业务契约只保存逻辑 `StorageRef`；
- 强制规范 POSIX 相对路径、Namespace 根约束、Symlink 防逃逸和正式目标不可覆盖；
- 新增 `0003_wp0102_artifact_registry`、Artifact Registry Repository 与由 Application Service 控制的事务；
- 实现同 Namespace `.staging` 写入、内容与 Manifest Hash、fsync、同文件系统原子 rename、rename 后数据库登记；
- 实现缺失/篡改阻断消费、rename 后数据库失败留下不可见 Orphan 的稳定语义；
- 实现只读 Orphan dry-run 与幂等恢复注册，不执行删除；
- 补齐 Artifact、Manifest、发布结果和 Dry-run 结果 Schema，并接入 JSON Schema、OpenAPI 和前端类型确定性生成链。

## 3. 明确不实现

- 不创建真实 `/data`，不写服务器或生产数据；
- 不实现 Task、Attempt、Lease、WP-0103、Artifact 下载鉴权或公网文件服务；
- 不执行 Orphan 删除或自动清理；
- 不实现 Raw、Canonical、Snapshot、Provider；
- 不修改 `upstream/`、`references/`，不写生产 Secret，不部署；
- 不直接提交或 push `main`，不 force push，不合并 PR。

## 4. 当前证据

- 固定基线核验：本地 `HEAD`、`origin/main`、GitHub `main` 均为 `01e1a986418b2bdae71fed5e3176ff87a337f279`；
- G006 合入证据：PR #5 `MERGED`，merge commit `01e1a986418b2bdae71fed5e3176ff87a337f279`，最终 Run `33288412520` 三项阻断 Job `SUCCESS`；
- 实现、Migration、测试、生成链和 PR 证据：进行中。

## 5. 风险与回滚

- 文件系统原子性依赖 Staging 与正式目录位于同一 Namespace/文件系统；实现必须在 rename 前验证根、父链与目标无 Symlink 逃逸；
- rename 成功而数据库失败时保留不可见 Orphan，数据库回滚不得删除业务文件；
- Alembic downgrade 只回滚 `artifact_registry` Schema，不删除已发布文件或 Orphan；
- 合并前可关闭 G007 PR；合并后如需回滚，在新分支普通 revert 对应 merge commit，并通过新 PR 合入。
