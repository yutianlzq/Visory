# Visory-G011 / WP-0201 进度与验收记录

最后更新：2026-08-31

## 1. 当前状态

- Goal：`Visory-G011`
- Work Package：`WP-0201 Registry Contract Hardening`
- Goal 状态：`IN_PROGRESS`
- Work Package 状态：`IN_PROGRESS`
- 固定基线：`main=c68739f87d1fb6e13087371b6c260120c59dd02c`
- 工作分支：`goal/g011-wp-0201-registry-contract-hardening`
- 开始进度：`8/45`（本 Goal 完成前保持不变）
- 目标 Migration head：`0006_wp0201_registry_contract_hardening`
- parent：`0005_wp0201_dataset_provider_registry`

开始前已核验本地 `HEAD`、本地 `origin/main` 与 GitHub `main` 均为固定基线，工作区干净。G010 已完成并保持 `8/45`。本 Goal 不启动 WP-0202 或 WP-0203。

## 2. 实现结果

### 2.1 DatasetDefinition 显式契约与版本绑定

- `security_master`、`trading_calendar`、`bar_1d_raw` 改为显式字段契约；每个声明字段必须逐项声明 `field_types`、`units`、`null_semantics` 和 `time_semantics`；
- `bar_1d_raw` 使用 `volume_shares`、`amount_cny`、`prev_close`、`trading_status`、涨跌停和 `available_at` 等正式字段，拒绝旧的 `volume`/`turnover` 含义；
- 同一 `dataset_id` 支持多个不可变 `schema_version`；Capability 与 Policy 显式绑定 DatasetDefinition 版本；
- ProviderDefinition 不再保存或展示 `actual_upstream` 占位值；实际上游留待未来 `ProviderRun.actual_upstream`。

### 2.2 Migration 与 Repository

- 新增 `0006_wp0201_registry_contract_hardening`，parent 为 `0005_wp0201_dataset_provider_registry`；
- DatasetDefinition 主键升级为 `(dataset_id, schema_version)`；Capability/Policy 增加复合外键和版本字段；策略有效区间重叠约束按数据集版本隔离；
- downgrade 在存在多版本或 Provider 记录时明确拒绝，避免重新引入虚假上游语义；
- Registry bootstrap 使用固定时间和 `ensure_*` 幂等初始化，相同内容跳过，冲突显式失败；Repository 不隐式 commit。

### 2.3 契约生成与回归

- 更新 C-004 Provider/Dataset JSON Schema、C-010 OpenAPI、Contract Registry 和前端 TypeScript 生成结果；
- 新增显式 DatasetDefinition 成功/拒绝 Golden 样本及 Provider Registry 契约回归；
- Legacy API、Identity、Settings projection 与 PostgreSQL registry 集成测试保持兼容。

## 3. 本地验收证据

- `tests/platform/test_provider_registry_contract_hardening.py`、Provider API、Golden：`64 passed, 1 warning`；
- 契约与 Registry Golden 回归：`76 passed`；
- 全部平台测试：`269 passed, 5 skipped`；
- PostgreSQL 16 一次性 Docker 集成：Migration 基础 `5 passed`，Provider Registry `3 passed`；
- 修改 Python 文件 `py_compile`：退出码 `0`；
- Web Settings 定向测试：`60 passed`；Web lint/build：通过；
- `scripts/export_platform_contracts.py --check`：通过，无 drift；
- `scripts/check_ai_assets.py`、`scripts/check_visory_baseline.py`、`git diff --check`：通过。

## 4. 未完成与风险

- 仍待完成本地完整门禁、提交、推送、PR 与 GitHub 三项阻断 Job；在这些证据齐全前不得标记 `VERIFIED` 或更新进度；
- 全部变更仅涉及 Registry 契约、Migration、测试、生成物和文档；不连接真实 Provider、不写生产数据库、Secret 或真实 `/data`；
- Migration downgrade 只回滚数据库 Schema，不自动删除业务文件；
- 版本绑定会要求未来新增 Provider capability/policy 时显式指定 DatasetDefinition schema version。

## 5. 回滚

- 代码回滚：revert 本 Goal 分支提交；
- Schema 回滚：在隔离数据库执行 `alembic downgrade 0005_wp0201_dataset_provider_registry`；若存在多版本 DatasetDefinition 或 Provider 记录，Migration 会安全拒绝并要求先处理数据；
- 不执行真实 Provider、生产数据库、生产 Secret、部署或 `/data` 写入。
