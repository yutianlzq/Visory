# Visory-G004 / WP-0002 进度与验收记录

最后更新：2026-08-29

## 1. 最终状态

- Goal：`Visory-G004`
- Work Package：`WP-0002 PostgreSQL 与 Alembic 基础`
- Goal 状态：`COMPLETE`
- Work Package 状态：`VERIFIED`
- 固定基线：`origin/main=10edc2594a65a2a10674b8e83ef896414f3265dc`
- 工作分支：`goal/g004-wp-0002-postgres-alembic`
- PR：`#3 feat: add PostgreSQL and Alembic foundation`
- 已验证 Work Package：`2/45`
- 下一 Work Package：`WP-0003 NOT_STARTED`

实现 head `32b318a` 已通过 GitHub Actions Run `33250185521` 的 Governance、Python、Web 三项阻断 Job。WP-0002 的真实 PostgreSQL、Migration、事务、Secret、安全错误与 Legacy 回归证据齐全，达到合入条件；PR 尚未合并，未经 owner 明确批准不得合并或启动 WP-0003。

## 2. 已完成范围

本 Goal 仅实现 WP-0002：

- 固定 SQLAlchemy `2.0.52` + psycopg `3.3.4` 同步 PostgreSQL 栈，不建立同步/异步双栈；
- PostgreSQL 配置、Secret 文件读取、QueuePool、健康检查和稳定脱敏错误；
- Alembic `1.19.1` 环境与 `0001_wp0002_baseline`；
- 显式事务边界，Repository 不隐式提交；
- 一次性随机隔离 PostgreSQL 测试数据库 Fixture；
- GitHub Python Job 的 PostgreSQL 16 service 验收环境；
- `.env.example`、Migration 专题文档、实现状态、索引和 Changelog 同步。

明确未迁移 Legacy 业务表或数据，未实现身份表、Artifact、任务表、采集、API/UI 页面、服务器写入、部署或 WP-0003；未修改 `upstream/`、`references/`。

## 3. 实现与修复证据

- TDD RED：`513c1df`，先定义 PostgreSQL 基础契约；
- 导入隔离：`d91e8e4`，平台 Repository 导入不加载 Legacy Storage/Data Provider；
- 核心实现：`b20b3fb`；
- 文档：`90fa428`；
- 跨平台 Schema 导出换行确定性：`3744dd1`；
- Alembic logger 隔离修复：`32b318a`，避免 Migration 禁用应用既有 logger；
- Migration head：`0001_wp0002_baseline`，parent 为 `<base>`，不创建业务表。

首轮 Actions Run `33249823566` 的 Governance/Web 通过，Python 因 Alembic `fileConfig()` 默认禁用既有 logger 和 POSIX Secret 测试 mode 前置条件失败。修复没有弱化门禁；定向回归为 79 passed、6 skipped，随后 Run `33250185521` 三项阻断 Job 全绿。

## 4. 验收证据

GitHub Actions Run `33250185521`：

- Governance and repository boundaries：通过；
- Python deterministic gate：通过，`6487 passed, 4 deselected, 48 warnings, 572 subtests passed`；
- Web lint and build：通过。

Python Job 的 PostgreSQL 16 service 已实际通过：

- 空数据库 upgrade 到 `0001_wp0002_baseline`；
- 重复 upgrade 不产生额外变化；
- downgrade 到 base 后重新 upgrade；
- Migration current/head 状态查询；
- `timestamptz` 往返保持同一 Instant；
- 事务成功提交、异常回滚；
- 不可连接错误稳定、脱敏且 `retryable=true`；
- 连接池关闭、残留连接终止与随机测试数据库删除；
- 缺失、不可读、权限过宽和格式错误的 Secret 文件安全拒绝；
- Legacy SQLite/API 与完整离线测试门禁通过。

本地补充证据：

- 平台数据库单元/定向测试与日志回归：79 passed、6 skipped；
- `src.repositories.platform` 覆盖率：89.20%；
- `python scripts/check_ai_assets.py`、`python scripts/check_visory_baseline.py` 通过；
- Web `npm ci`、`npm run lint`、`npm run build` 通过；
- `git diff --check` 通过，固定基线差异未触及 `upstream/`、`references/`。

Windows clean-worktree 完整 `bash scripts/ci_gate.sh` 为 `6396 passed, 80 failed, 11 skipped, 4 deselected`；失败集中于 Windows 不支持的 POSIX 进程组/管道、既有 SQLite 文件锁/时序与环境相关 CLI 测试。本结果未伪装为通过，最终阻断裁决采用上述 Linux Actions 全绿结果。

## 5. 环境、风险与回滚

- 本地 Docker Desktop daemon 因 `dockerInference` 命名管道不可访问而未启动；没有重置 Docker、修改全局设置、创建容器或遗留测试数据库。
- CI Secret 仅使用 runner 临时文件引用，值为非生产占位值；文档、日志、错误和状态记录不包含密码、DSN 或 Secret 值。
- Migration baseline 只管理 Alembic 版本状态，不证明任何后续业务 Schema 已实现。
- 最小回滚：合并前关闭 PR；合并后普通 revert G004 commits，必要时对隔离 PostgreSQL downgrade 到 `base`；移除 `VISORY_POSTGRES_*` 后 Legacy SQLite/API 继续沿用原路径。
- 当前结论：达到合入条件，但必须等待 owner 明确批准。合入后可进入 WP-0003；合入前不得启动。
