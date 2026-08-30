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
- 当前 Alembic head：`0001_wp0002_baseline`
- 目标 Alembic head：`0002_wp0101_asset_identity`

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
- 不直接 push `main`、不 force push、不在 owner 批准前合并 PR。

## 4. 验收 Gate

- Migration 空库 upgrade、重复 upgrade、downgrade base 后重新 upgrade；
- PostgreSQL 真实约束、事务和并发冲突测试；
- Schema、Golden、Repository、Resolver、API 和 Legacy Adapter 回归；
- OpenAPI、JSON Schema 和前端生成类型无 drift；
- Governance、Python deterministic、Web lint/build 三项 GitHub Actions 全绿；
- 证据齐全后才将 WP-0101 标记为 `VERIFIED` 并更新为 `4/45`。

## 5. 回滚

- 合并前关闭 G006 PR；
- 合并后在新分支普通 revert G006 merge commit；
- 数据库回滚使用 Alembic downgrade 至 `0001_wp0002_baseline`，只删除 WP-0101 三张新表，不触碰 Legacy SQLite；
- 生成文件通过 `python scripts/export_platform_contracts.py` 恢复，不手工编辑。
