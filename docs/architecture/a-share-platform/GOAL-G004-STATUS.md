# Visory-G004 / WP-0002 进度与验收记录

最后更新：2026-08-29

## 1. 当前状态

- Goal：`Visory-G004`
- Work Package：`WP-0002 PostgreSQL 与 Alembic 基础`
- Goal 状态：`IN_PROGRESS`
- Work Package 状态：`IN_PROGRESS`
- 基线：`origin/main=10edc2594a65a2a10674b8e83ef896414f3265dc`
- 工作分支：`goal/g004-wp-0002-postgres-alembic`
- 已验证 Work Package：`1/45`

实现与本地确定性测试已完成，真实 PostgreSQL 验收和 GitHub Governance、Python、Web 三项阻断 Job 尚待 PR CI。证据齐全前不得把 WP-0002 标记为 `VERIFIED`，也不得开始 WP-0003。

## 2. 范围

本 Goal 仅实现 WP-0002：

- 固定 SQLAlchemy `2.0.52` + psycopg `3.3.4` 同步 PostgreSQL 栈；
- PostgreSQL 配置、Secret 文件读取、QueuePool、健康检查和稳定脱敏错误；
- Alembic `1.19.1` 环境与 `0001_wp0002_baseline`；
- 显式事务边界与 Repository 不隐式提交的约束；
- 一次性隔离 PostgreSQL 测试数据库 Fixture；
- GitHub Python Job 的 PostgreSQL 16 service 验收环境。

明确不包含 Legacy 业务表或数据迁移、身份表、Artifact、任务表、采集、API/UI 页面、服务器写入、部署或 WP-0003。

## 3. 当前实现证据

- TDD RED commit：`513c1df`，平台数据库包缺失导致目标测试按预期失败；
- 导入隔离 RED/GREEN commit：`d91e8e4`，确保平台 Repository 导入不加载 Legacy Storage/Data Provider；
- 实现 GREEN commit：`b20b3fb`；
- Migration head：`0001_wp0002_baseline`，parent 为 `<base>`，不创建业务表；
- 平台数据库单元测试：35 passed、1 skipped（Windows 跳过 POSIX mode bit）；
- `src.repositories.platform` 覆盖率：89.20%；
- PostgreSQL 集成测试在本地因 Docker daemon 故障而跳过，已配置由 GitHub Linux CI 的 PostgreSQL 16 service 执行。

## 4. 待完成验收

- 空数据库 upgrade 到 head、重复 upgrade、downgrade base、重新 upgrade；
- Migration 状态可查询且可复现；
- `timestamptz` 保持同一 Instant；
- 事务提交、异常回滚；
- 不可连接错误为稳定、脱敏、retryable；
- 连接池和随机测试数据库完整清理；
- Legacy SQLite/API 回归；
- `scripts/check_ai_assets.py`、`scripts/check_visory_baseline.py`、`scripts/ci_gate.sh`；
- Web lint/build；
- PR 和 GitHub Governance、Python、Web 三项阻断 CI。

## 5. 风险与回滚

- 本地 Docker Desktop daemon 因 `dockerInference` 命名管道不可访问而未启动；没有重置 Docker、修改全局设置、创建容器或遗留测试数据库。真实 PostgreSQL 结果必须由 GitHub Linux CI 裁决。
- Migration baseline 只管理 Alembic 状态，不证明任何后续业务 Schema 已实现。
- 最小回滚为关闭未合并 PR 或普通 revert G004 commits；隔离数据库可 downgrade 到 base；移除 `VISORY_POSTGRES_*` 后 Legacy SQLite/API 保持原路径。
