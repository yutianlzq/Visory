# Visory-G011 / WP-0201 进度与验收记录

最后更新：2026-08-31

## 1. 当前状态

- Goal：`Visory-G011`
- Work Package：`WP-0201 Dataset Registry Contract Hardening`
- Goal 状态：`COMPLETE / MERGED`
- Work Package 状态：`VERIFIED`
- 固定基线：`main=c68739f87d1fb6e13087371b6c260120c59dd02c`
- 工作分支：`goal/g011-wp-0201-registry-contract-hardening`
- 已验证 Work Package：`8/45`（本 Goal 不增加进度）
- 目标 Migration head：`0006_wp0201_registry_contract_hardening`
- parent：`0005_wp0201_dataset_provider_registry`
- PR：[#20](https://github.com/yutianlzq/Visory/pull/20)
- 合并提交：`dbd8c271041b17323cff09ec00679f5f0ea59547`（普通 merge commit）
- 最终 CI：Run [`33373953485`](https://github.com/yutianlzq/Visory/actions/runs/33373953485)，Governance、Python、Web 三项阻断 Job 全部成功。

开始前已核验本地 `HEAD`、本地 `origin/main` 与 GitHub `main` 均为固定基线，工作区干净。合并后重新 fetch，GitHub `main`、本地 `origin/main` 与 PR merge commit 均为 `dbd8c271041b17323cff09ec00679f5f0ea59547`。本 Goal 不启动或标记 WP-0202、WP-0203。

## 2. 实现结果

### 2.1 DatasetDefinition 显式契约与版本绑定

- `security_master`、`trading_calendar`、`bar_1d_raw` 改为显式字段契约；每个声明字段逐项声明 `field_types`、`units`、`null_semantics` 和 `time_semantics`；
- `bar_1d_raw` 使用 `volume_shares`、`amount_cny`、`prev_close`、`trading_status`、涨跌停和 `available_at` 等正式字段，拒绝旧的 `volume`/`turnover` 含义；
- 允许同一 `dataset_id` 保存多个不可变 `schema_version`；Capability 与 Policy 显式绑定 DatasetDefinition 版本；
- ProviderDefinition 不再保存或展示 `actual_upstream` 占位值；实际上游留待未来 `ProviderRun.actual_upstream`。

### 2.2 Migration 与 Repository

- 新增 `0006_wp0201_registry_contract_hardening`，parent 为 `0005_wp0201_dataset_provider_registry`；
- DatasetDefinition 主键升级为 `(dataset_id, schema_version)`；Capability/Policy 增加版本字段、复合外键；策略有效区间重叠约束按数据集版本隔离；
- downgrade 在存在多版本或 Provider 记录时明确拒绝，避免重新引入虚假上游语义；
- Registry bootstrap 使用固定时间和 `ensure_*` 幂等写入：重复执行无重复，冲突显式失败；Repository 不隐式 commit。

### 2.3 契约生成与回归

- 更新 C-004 Provider/Dataset JSON Schema、C-010 OpenAPI、Contract Registry 和前端 TypeScript 生成结果；
- 新增显式 DatasetDefinition 成功/拒绝 Golden 样本及 Provider Registry 契约回归；
- Legacy API、Identity、Settings projection 与 PostgreSQL registry 集成测试保持兼容。

## 3. 验收证据

- 平台全套：`.venv\Scripts\python.exe -m pytest tests/platform --basetemp=.tmp\pytest-g011-platform-final -q`，`275 passed, 5 skipped`；
- PostgreSQL 16 一次性 Docker 集成：Migration foundation 与 Provider Registry `8 passed`，覆盖空库 upgrade、重复 upgrade、downgrade/re-upgrade、版本绑定、幂等与冲突拒绝；
- Provider/Migration 定向 `flake8` 与 Python `py_compile`：通过；
- Web Settings 定向 Vitest：`60 passed`；`npm run lint` 与 `npm run build`：通过；
- `scripts/export_platform_contracts.py --check`、`scripts/check_ai_assets.py`、`scripts/check_visory_baseline.py`、`git diff --check`：通过；
- GitHub Actions Run `33373953485`：Governance、Python deterministic gate、Web lint and build 均成功。

## 4. 环境、风险与回滚

- Python：`.venv` Python `3.12.9`；Node `v22.20.0`、npm `11.11.0`；未修改依赖清单、lockfile、Compose、服务器或生产环境变量；
- PostgreSQL：使用 `postgres:16` 一次性本地 Docker 容器、每用例隔离数据库和临时 Secret 文件；测试后已删除容器与临时密码文件，Secret 一律以 `***` 脱敏；
- 未连接真实 Provider，未写生产数据库、真实 `/data`、生产 Secret，未部署；未修改 `upstream/`、`references/`；
- Migration downgrade 只回滚数据库 Schema，不自动删除业务文件；存在多版本 DatasetDefinition 或 Provider 记录时会安全拒绝降级到 `0005`，需先进行数据处置；
- 回滚代码：revert PR #20 的 merge commit；Schema：在隔离数据库 downgrade 到 `0005_wp0201_dataset_provider_registry`，并按拒绝语义处理存在的数据。
