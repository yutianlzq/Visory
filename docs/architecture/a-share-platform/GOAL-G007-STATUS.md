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
- 当前实现提交：`a5712077ad3113b43655cab22aadb96ba4f17af2`
- Alembic head：`0003_wp0102_artifact_registry`
- parent：`0002_wp0101_asset_identity`

开始前已核验本地 `HEAD`、`origin/main` 与 GitHub `main` 均为固定基线 `01e1a986418b2bdae71fed5e3176ff87a337f279`，工作区干净。G006 已登记为 `COMPLETE / MERGED`：PR #5 于 2026-08-30 合入，merge commit 为固定基线，最终 Actions Run `33288412520` 的 Governance、Python、Web 三项阻断 Job 全绿。

WP-0102 实现、本地定向验收和 PostgreSQL 16 真实集成已完成；PR 与 GitHub 三项阻断 CI 尚未建立，因此本 Goal 仍保持 `IN_PROGRESS / 4/45`。只有 clean Ubuntu GitHub CI 提供完整生成链、POSIX Symlink、文件权限、PostgreSQL 和 Legacy 回归证据后，才可标记为 `VERIFIED / 5/45`。

## 2. 实现结果

### 2.1 Storage Namespace 与路径安全

- `VISORY_RUNTIME_ROOT` 仅作为环境绑定；数据库、Manifest、OpenAPI 和前端类型只保存逻辑 `StorageRef`，不包含 runtime root、宿主机绝对路径或 DSN；
- `StorageRef` 固定包含 `backend`、`namespace`、`relative_path`、`content_hash`、`media_type`、`size_bytes`；
- `relative_path` 必须是规范 POSIX 相对路径；拒绝绝对路径、Windows 盘符、UNC、反斜杠、URI、空段、`.`、`..`、控制字符和保留路径段；
- Resolver 拒绝 Runtime Root、Namespace、父目录、目标目录或 Manifest 的 Symlink；正式发布目标已存在时失败，不覆盖已有文件或目录；
- 所有测试使用每用例临时 Runtime Root，未创建或写入真实 `/data`。

### 2.2 Artifact Registry 与发布事务

- 新增 Migration `0003_wp0102_artifact_registry`，parent 为 `0002_wp0101_asset_identity`；
- `artifact_registry` 保存 `artifact_id`、`artifact_type`、`owner_resource_ref`、可空 `attempt_id`、逻辑 Storage Ref、媒体类型、大小、Artifact Hash、Schema 版本、创建/发布时间、Retention、Visibility、发布状态和完整性状态；未使用含义不明的裸 `status`，未创建 Task/Attempt 表或外键；
- Repository 不隐式 commit，由 Artifact Application Service 控制 PostgreSQL 事务；
- Publisher 在同一 Namespace 的 `.staging` 写入 payload 和确定性 Manifest，校验内容、大小、媒体类型和目标路径，执行文件与必要目录 fsync，再使用同文件系统 `os.rename` 原子发布；
- rename 成功后才登记 Registry；Registry 提交成功后消费者才可读取；Correction 或重新发布必须使用新 `artifact_id` 和新路径；
- rename 失败不写 Registry；rename 成功而数据库事务失败时保留不可见 Orphan，回滚不删除已发布文件；
- Registry 文件缺失、大小不符、Hash 不符或 Manifest 异常时降级完整性状态并阻断消费。

### 2.3 Orphan Sweeper

- 仅实现 Dry-run 和恢复注册，不执行删除；
- 使用逐层 `os.scandir(..., follow_symlinks=False)`，只识别严格匹配 `type=* / year=YYYY / month=MM / artifact_id=artifact_<uuid> / manifest.json` 且带有效平台 Manifest 的已知目录；
- 不进入 Symlink 目录，不处理 Symlink Manifest 或未知目录；
- 恢复前重新校验逻辑路径、Manifest、Schema、Hash、大小和媒体类型；恢复注册幂等；
- Dry-run 输出候选、原因、预计影响和可恢复动作；不实现或触碰 `PINNED` / `AUDIT` 引用闭包清理。

### 2.4 契约与生成链

新增并纳入 Contract Registry、JSON Schema、C-010 OpenAPI components 与前端 TypeScript 确定性导出：

- `ArtifactRecord`
- `ArtifactManifest`
- `ArtifactPublishResult`
- `ArtifactRecoveryResult`
- `OrphanDryRunResult`

没有新增 Artifact 下载路由；现有公开平台路径仍只有 `/api/platform/v1/asset-resolutions`。未来 API 只能通过 `artifact_id` 访问 Artifact，不接受任意路径。

## 3. 本地验收证据

### 3.1 定向与平台测试

- Artifact、契约和平台生成测试：`43 passed, 4 skipped`；
- 全部平台测试：`218 passed, 5 skipped`；
- Windows skip 为 4 个本机无 Symlink 创建权限的测试和 1 个 POSIX 文件权限测试；这些用例必须由 GitHub Ubuntu Job 实际执行；
- 修改 Python 文件 `py_compile` 与 scoped critical flake8：通过；
- `python scripts/export_platform_contracts.py --check`：通过，生成结果无漂移；
- `python scripts/check_ai_assets.py`：通过；
- `python scripts/check_visory_baseline.py`：暂时将 ignored `.venv` 移入仓库内被排除的 `build/` 后通过，结果为 8 个 runtime path、10 个 reference、0 imported secret、582 个链接、0 broken link；`.venv` 已原样恢复，临时目录无遗留；
- Web：`npm ci`、`npm run lint`、`npm run build` 通过；构建未产生工作树改动；
- `git diff --check`：实现提交时通过，PR 前将再次执行。

### 3.2 PostgreSQL 16 真实集成

使用本地 Docker `postgres:16`、`127.0.0.1` 随机端口、`--rm`、随机临时密码文件引用和每用例隔离测试数据库执行 `tests/integration/platform`：`15 passed`。

已验证：

- 空数据库 upgrade 到 `0003_wp0102_artifact_registry`；
- 重复 upgrade 不产生额外变化；
- downgrade 到 base 后重新 upgrade；
- `0003 -> 0002` 只回滚数据库 Schema，不删除测试 Artifact 文件；
- Migration 状态可查询且可复现；
- `timestamptz` 往返保持同一 Instant；
- PostgreSQL 事务成功提交、异常回滚，Artifact/Identity Repository 均不隐式提交；
- 正常发布和内容读取；
- rename 成功后 Registry 事务失败留下 Orphan；
- Orphan 恢复注册和重复恢复幂等；
- Pool checked-out 连接归零；
- Registry 不包含 `runtime_root`、`absolute_path` 或 `host_path` 字段。

测试后确认临时数据库目录和 Docker 容器遗留均为 `0`。密码、DSN 和 Secret 值仅通过文件引用使用并统一记为 `***`。

### 3.3 Windows 全量离线回归

Windows 全量 `pytest -m "not network"` 结果为：

```text
6484 passed, 82 failed, 25 skipped, 4 deselected, 63 warnings,
572 subtests passed
```

失败集中于既有 native Windows 与 clean Ubuntu CI 的平台差异：POSIX process group/pipe/shell、Codex App Server fail-closed 环境、Windows 打开 SQLite 句柄无法删除临时数据库，以及 5ms Screening deadline 递减断言受本机约 15.6ms 单调时钟粒度影响。相关实现和测试文件均不在本 Goal diff 中。本地 WSL 运行 `ci_gate.sh` 还会扫描仅本机存在、被 Git 忽略的 `references/repos/` 外部源码，因此不能替代 clean checkout CI，也不据此宣称 Python Gate 通过。

## 4. 待完成 Exit Gate

- 普通 push 工作分支并创建 PR；
- GitHub `Governance and repository boundaries` 全绿；
- GitHub `Python deterministic gate` 全绿，并确认 PostgreSQL 15 项集成、Linux Symlink/权限测试和完整 Legacy 回归实际执行而非 skip；
- GitHub `Web lint and build` 全绿；
- 更新最终实现 head、PR、Actions Run/Jobs 和测试总数；
- 三项阻断 Job 全绿后才更新为 `COMPLETE / VERIFIED / 5/45`，并再次等待状态提交触发的最终 CI。

## 5. 明确未实现

- 未创建真实 `/data`，未写服务器或生产数据；
- 未实现 Task、Attempt、Lease、WP-0103、Artifact 下载鉴权或公网文件服务；
- 未执行 Orphan 删除或自动清理；
- 未实现 Raw、Canonical、Snapshot、Provider；
- 未修改 `upstream/`、`references/`，未写生产 Secret，未部署；
- 未直接提交或 push `main`，未 force push，未合并 PR。

## 6. 风险与回滚

- 文件系统原子性依赖 Staging 与正式目录位于同一 Namespace/文件系统；跨文件系统部署配置会被拒绝；
- Windows 本机无法执行的 Symlink/权限用例必须由 Ubuntu CI 关闭风险；
- rename 成功而数据库失败会留下设计内不可见 Orphan，当前只提供 Dry-run 与恢复，不自动删除；
- Alembic downgrade 只删除 `artifact_registry` Schema，不删除已发布文件或 Orphan；
- 合并前可关闭 G007 PR；合并后如需回滚，在新分支普通 revert 对应 merge commit，并通过新 PR 合入；数据库 downgrade 至 `0002_wp0101_asset_identity`，业务文件需按运维清单独立处置；
- 移除 `VISORY_RUNTIME_ROOT` 和 PostgreSQL opt-in 配置后，新 Artifact runtime 不启用，Legacy SQLite/API 行为保持不变。
