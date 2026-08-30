# Visory-G006 / WP-0101 进度与验收记录

最后更新：2026-08-30

## 1. 当前状态

- Goal：`Visory-G006`
- Work Package：`WP-0101 Asset Identity与Alias Resolver`
- Goal 状态：`READY_TO_MERGE`
- Work Package 状态：`VERIFIED`
- 固定基线：`main=98ab97e9bd3cc9c24a8e16081c7ae8d89279253d`
- 工作分支：`goal/g006-wp-0101-asset-identity-resolver`
- 已验证 Work Package：`4/45`
- 实现 Alembic head：`0002_wp0101_asset_identity`
- parent：`0001_wp0002_baseline`

本 Goal 开始时，本地、`origin/main` 与 GitHub `main` 均已核验为固定基线 `98ab97e`，工作区干净。实现提交 `a272b25`、CI 隔离修复提交 `0a300f6`、本地验收和 PR #5 GitHub Actions Run `33288021328` 的三项阻断 Job 均已通过，因此 WP-0101 标记为 `VERIFIED`，implemented work packages 更新为 `4/45`。owner 已批准在本状态提交触发的最终 CI 全绿后以普通 merge commit 合入。

## 2. 实现结果

- 建立 `asset_identity`、`asset_alias`、`identity_quarantine` 和 Migration `0002_wp0101_asset_identity`；
- 使用 `btree_gist` 与右开 `daterange(valid_from, valid_to, '[)')` 排他约束，拒绝同一 `namespace + normalized_value` 在重叠有效期内指向不同 `entity_key`，同一实体的重叠 Revision 允许保留；
- 实现 C-002 Identity、Alias、Resolution、Quarantine Schema、Contract Registry、Golden、JSON Schema、C-010 OpenAPI 与前端 TypeScript 确定性导出；
- 实现 PostgreSQL Repository、Resolver Service 和 `POST /api/platform/v1/asset-resolutions`；Repository 不隐式 commit，由调用方事务控制提交和回滚；
- Provider Namespace 精确隔离；名称、历史名称、拼音和用户 Alias 只生成候选；改名、ST、停牌保持同一 `entity_key`，退市返回 `INACTIVE`；
- Alias 有效日按 `Asia/Shanghai` 计算，正式结果包含 C-002 规定的身份、状态、候选、原因、Resolver 版本和解析时间字段；
- PostgreSQL runtime 为 opt-in；未配置任何 `VISORY_POSTGRES_*` 时不初始化，配置或 Secret 错误只记录稳定错误码，生命周期结束关闭自有连接池；
- 只将 CSI 解析的一个低风险只读接缝迁移至 `LegacyAssetResolverAdapter`，未全局替换 Legacy parser；现有 Legacy SQLite 与 API 行为保持不变。

## 3. 明确未实现

- 未采集或回填全量证券数据，只使用小型许可 Fixture；
- 未实现 Provider Registry、Raw Ingestion、Snapshot、Storage、Artifact、Task 或 WP-0102；
- 未修改 `upstream/`、`references/`，未写生产 Secret、`/data` 或部署服务器；
- 未直接 push `main`、未 force push、未改写历史。

## 4. 本地验收证据

- WP-0101 定向测试：`68 passed, 11 skipped`；11 项 skip 仅因本机未运行 PostgreSQL，真实集成由 GitHub PostgreSQL Job 覆盖；
- Legacy 解析回归：`297 passed`；
- 修改 Python 文件 `py_compile` 与 scoped critical flake8：通过；
- `python scripts/export_platform_contracts.py --check`、`python scripts/check_ai_assets.py`、`git diff --check`：通过；
- `python scripts/check_visory_baseline.py`：暂时将 ignored `.venv` 移至系统临时目录后通过，结果为 8 个 runtime path、10 个 reference、0 imported secret、580 个链接、0 broken link；`.venv` 已恢复，临时目录无遗留；
- Web：`npm ci`、`npm run lint`、`npm run build` 通过；
- Alembic head 为 `0002_wp0101_asset_identity`，parent 为 `0001_wp0002_baseline`；
- Windows 全量离线测试为 `6450 passed, 82 failed, 17 skipped, 4 deselected`。失败集中于既有 native Windows/Codex App Server fail-closed、POSIX process group、Docker shell、SQLite 并发和环境测试；不将其伪装为全绿，最终阻断裁决由 clean Ubuntu GitHub Python Job 给出。

## 5. GitHub 验收证据

- 首轮 Run `33287567588`：Governance 与 Web 通过；Python 发现 3 个测试隔离问题，没有弱化约束或门禁；
- 修复 Run `33288021328`：Governance、Python deterministic、Web lint/build 三项阻断 Job 全绿；
- Python Job：`6549 passed, 4 deselected, 50 warnings, 572 subtests passed`，`scripts/ci_gate.sh` 完整通过；
- PostgreSQL 16 service 中，以下真实集成测试均实际执行且为 `PASSED`：
  - 空数据库 upgrade、重复 upgrade、downgrade base、重新 upgrade；
  - `timestamptz` Instant 往返；
  - 事务成功提交和异常回滚；
  - Repository 不隐式提交及联表同名时间列映射；
  - Alias 右开有效期、同实体 Revision、跨实体 Quarantine；
  - 并发写入不能绕过排他约束；
  - 不可连接错误的稳定、脱敏、retryable 语义；
  - 连接池关闭及 function-scope 隔离测试数据库清理；
- Runtime 的 POSIX Secret 文件权限与连接池 ownership/close 测试通过；日志和公开错误未暴露密码、DSN 或 Secret 值。

最终结论：WP-0101 已达到 `VERIFIED`，进度更新为 `4/45`。PR #5 已达到合入条件；按 owner 授权，在本状态提交触发的最终三项 CI 全绿后使用普通 merge commit 合入。

## 6. 回滚

- 合并前关闭 PR #5；
- 合并后在新分支普通 revert PR #5 的 merge commit，并通过新 PR 合入；
- 数据库回滚使用 Alembic downgrade 至 `0001_wp0002_baseline`，只删除 WP-0101 三张新表，不触碰 Legacy SQLite；
- 移除 `VISORY_POSTGRES_*` 后 Identity runtime 保持关闭；
- 生成文件必须通过 `python scripts/export_platform_contracts.py` 恢复，不手工编辑。
