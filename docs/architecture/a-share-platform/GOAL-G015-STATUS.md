# Visory-G015 / WP-0203 Extended Canonical Datasets

## 状态

- Goal: `COMPLETE / MERGED`
- Work Package: `WP-0203`（在 G014 Core Canonical Normalization 基础上扩展）
- 目标分支：`goal/g015-wp-0203-extended-canonical-datasets`
- 基线：`main@9bcd2f3ef414e1f4eedec04b4aa04f45423ea70c`
- Migration：`0010_wp0203_extended_canonical_datasets`，父版本 `0009_wp0203_core_canonical_normalization`
- 进度：`10/45`

## 本次交付

1. 注册 `instrument_status_daily`、`listing_status_history`、`corporate_action`、`financial_statement` 四个 Canonical 数据集。
2. 为 `a_stock_data` 与 `financial_api` 建立 provider raw schema 与 canonical mapping，显式声明字段类型、单位、Null 语义与时间语义。
3. 扩展 Canonical Normalizer：身份解析、`published_at <= available_at`、历史区间重叠、公司行动日期/金额、财务单位与 revision 门禁。
4. `CanonicalQualityReport` 增加 Task/Attempt、Dataset、Mapping 与 ProviderRun/RawObject 可回溯字段。
5. 新 Migration 仅扩展质量报告元数据，不迁移 Legacy 业务表或数据；downgrade 不删除业务文件。

## 验收证据

- 扩展数据集单元测试：`tests/platform` 共 `323 passed, 5 skipped`。
- PostgreSQL 真实集成：`tests/integration/platform` 共 `55 passed`，使用一次性 `postgres:16-alpine` 容器、每用例隔离数据库和文件临时目录。
- Alembic 空库升级、重复升级、降级与重新升级在集成测试中通过；`0010_wp0203_extended_canonical_datasets` 为当前 head。
- `scripts/export_platform_contracts.py --check` 通过，生成契约与前端类型字节稳定。
- `scripts/check_ai_assets.py`、`scripts/check_visory_baseline.py`、关键 Flake8 检查、变更文件 `py_compile` 和 `git diff --check` 通过。
- Web `npm ci`、`npm run lint`、`npm run build` 通过。
- GitHub Actions Run `33850545423` 的 Governance、Python、Web 三项阻断 Job 全部成功。
- PR #28 已按普通 merge commit 合入 main：head `7e813208c710cd9ae3d43be541935e46085174e1`，merge commit `76554416853314d6b3fe950f9d81a2c896320c27`。
- 与本次改动直接相关的 Canonical、Provider、Migration、PostgreSQL 和 Legacy 回归均已通过；全仓离线套件中仅有与本次改动无关的环境敏感 Codex transport 测试未纳入通过声明。

## 风险与回滚

- 现有 Registry 默认记录数量由 6 扩展为 14；既有三核心数据集 Mapping 内容保持不变。
- 回滚使用 `git revert` 目标提交并执行 Alembic downgrade；不会自动删除已发布业务文件。
- WP-0203 已满足验收并标记 `VERIFIED`；下一目标为 G016 / WP-0204 DataSnapshot & Capability Gate，尚未启动。
