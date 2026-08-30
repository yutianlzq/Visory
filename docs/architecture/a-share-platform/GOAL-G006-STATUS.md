# Visory-G006 / WP-0101 进度与验收记录

最后更新：2026-08-30

## 1. 当前状态

- Goal：`Visory-G006`
- Work Package：`WP-0101 Asset Identity与Alias Resolver`
- Goal 状态：`IN_PROGRESS`
- Work Package 状态：`IN_PROGRESS`
- 固定基线：`main=98ab97e9bd3cc9c24a8e16081c7ae8d89279253d`
- 工作分支：`goal/g006-wp-0101-asset-identity-resolver`
- 已验证 Work Package：`3/45`
- 实现 Alembic head：`0002_wp0101_asset_identity`
- parent：`0001_wp0002_baseline`

本 Goal 开始时，本地、`origin/main` 与 GitHub `main` 均已核验为固定基线 `98ab97e`，工作区干净。G005 已通过 PR #4 以普通 merge commit `98ab97e` 合入；WP-0001、WP-0002、WP-0003 和 M0 Exit Gate 均已验证。WP-0101 验收完成前不得更新为 `4/45`。

## 2. 实现范围

- 建立 `asset_identity`、`asset_alias`、`identity_quarantine` 和 Migration `0002_wp0101_asset_identity`；
- 实现 C-002 Identity、Alias、Resolver 输入输出 Schema、Golden 和确定性导出；
- 实现 PostgreSQL Repository、Resolver Service 和 `/api/platform/v1` API；
- Alias 保存 Namespace、有效期、`available_at`、Provider 血缘和 Revision；
- 重叠有效期冲突进入 Quarantine，不允许 Last-write-wins；
- 名称、拼音和用户 Alias 只生成候选，不直接形成正式事实关联；
- 退市资产永久保留；改名、ST、停牌不更换 `entity_key`；
- 只迁移一个低风险只读 Legacy 解析接缝，并验证输出等价；
- API 复用 C-010 Envelope、Request ID 和稳定错误码；
- 同步生成 OpenAPI 与前端 TypeScript 类型并检查 drift。

## 3. 明确不做

- 不采集或回填全量证券数据，只使用小型许可 Fixture；
- 不实现 Provider Registry、Raw Ingestion、Snapshot、Storage、Artifact、Task 或 WP-0102；
- 不修改 `upstream/`、`references/`；
- 不写生产 Secret、`/data` 或部署服务器；
- 不直接 push `main`、不 force push；只在全部验收和三项阻断 CI 全绿后按用户授权执行普通 merge commit。

## 4. 验收 Gate

- Migration 空库 upgrade、重复 upgrade、downgrade base 后重新 upgrade；
- PostgreSQL 真实约束、事务和并发冲突测试；
- Schema、Golden、Repository、Resolver、API 和 Legacy Adapter 回归；
- OpenAPI、JSON Schema 和前端生成类型无 drift；
- Governance、Python deterministic、Web lint/build 三项 GitHub Actions 全绿；
- 证据齐全后才将 WP-0101 标记为 `VERIFIED` 并更新为 `4/45`。

## 5. 当前实现与本地证据

- C-002 Schema、Contract Registry、Golden、OpenAPI 与前端类型已实现并通过确定性 drift 检查；
- Migration `0002_wp0101_asset_identity` 已登记为 Alembic head，真实 PostgreSQL DDL 仍待 GitHub PostgreSQL 16 service 验证；
- Repository 明确由调用方事务提交/回滚，联表映射按 SQLAlchemy `Column` 读取，避免同名时间列串列；
- 正式 Alias 排他约束只拒绝重叠有效期内指向不同 `entity_key` 的映射，同实体重叠 Revision 保留；
- Resolver 覆盖沪深主板、创业板、科创板、Provider namespace、名称候选、ST、退市、Quarantine 与上海时区有效日边界；
- `/api/platform/v1/asset-resolutions` 复用 C-010 Envelope、Request ID 与稳定脱敏错误；
- PostgreSQL runtime 为 opt-in：未配置时不初始化，不影响 Legacy API/SQLite；配置或 Secret 错误只记录稳定错误码；生命周期结束关闭自有连接池；
- 单一 Legacy 只读接缝通过 `LegacyAssetResolverAdapter` 复用既有 parser，未全局替换解析逻辑。

本地已完成：目标定向测试 `68 passed, 11 skipped`（skip 为本机无 PostgreSQL）、Schema/生成补充测试 `9 passed`、Web `npm ci/lint/build`、AI assets、baseline 与生成 drift 检查。Windows 全量离线测试为 `6450 passed, 82 failed, 17 skipped, 4 deselected`；失败集中于既有 Codex 进程/CLI、POSIX process-group、Docker shell、SQLite 并发和环境相关测试，目标 WP 定向测试无失败。是否阻断以 clean Ubuntu GitHub Python Job 的完整结果和 PostgreSQL 真实集成为准。

## 6. 剩余阻断项

- GitHub PostgreSQL 16 中验证 `btree_gist`、Migration upgrade/downgrade/re-upgrade、同实体 Revision、跨实体 Quarantine、并发排他、联表映射与隔离数据库清理；
- GitHub Governance、Python deterministic、Web 三项阻断 Job 全绿；
- 取得上述证据后更新为 `VERIFIED / 4/45`，再按用户授权以普通 merge commit 合入。

## 7. 回滚

- 合并前关闭 G006 PR；
- 合并后在新分支普通 revert G006 merge commit；
- 数据库回滚使用 Alembic downgrade 至 `0001_wp0002_baseline`，只删除 WP-0101 三张新表，不触碰 Legacy SQLite；
- 生成文件通过 `python scripts/export_platform_contracts.py` 恢复，不手工编辑。
