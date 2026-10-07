# WP-0302 实现与验收记录

## 边界与状态

- 基线：`main@6aa9fa82e31ad0ad175cc1f6650ad7db67fa0222`。
- 分支：`codex/wp-0302-feature-bundle`；隔离 worktree，未修改 WP-0207 实现。
- 仅增加 WP-0302 的类型、物化/发布边界、PostgreSQL 控制面及验证资产；不实现 WP-0303/0304/0305、Hikyuu Cache 或前端迁移。
- Worker 输入为调用方显式提供的 FeatureRow，未连接真实 Provider、生产数据库、真实 `/data` 或生产调度。
- 本分支代码/契约验收 `VERIFIED`：本地与隔离集成证据完成，实际实现提交的远程三项阻断 CI 全部成功；未合并 `main`，未部署，生产 `NOT CERTIFIED`，`RELEASED=false`。

领域契约以 [Feature Store 架构](feature-store-architecture.md) 为准；总状态见 [IMPLEMENTATION-STATUS](IMPLEMENTATION-STATUS.md)。

## 需求与可复现证据

| 验收面 | 实现与证据 |
| --- | --- |
| 分区、Schema、唯一键、质量、PIT | `src/schemas/platform/feature.py` 的 FeatureRow/FeaturePartition；`test_feature_partition_from_rows_is_deterministic_and_rejects_pit_or_duplicate_keys`、`test_quality_and_coverage_validation_fail_closed_before_formal_publication`、`test_registered_indicator_schema_is_fail_closed` |
| 不可变 Manifest / correction lineage | FeatureSnapshot；`test_snapshot_and_bundle_are_immutable_and_fix_references`、`test_correction_requires_published_lineage_and_formal_reference_pins_partition_record` |
| 固定 Bundle 引用、确定性 Hash、列投影 | FeatureBundle；`test_manifest_and_bundle_hashes_canonicalize_reference_order`、`test_bundle_requires_exact_column_coverage_by_fixed_partition_refs` |
| DependencyPlan、增量投影、warmup | `src/services/platform/feature_store.py`；`test_plan_warmup_is_required_but_not_published_and_pit_applies_to_warmup_rows`、`test_materialization_requires_exact_plan_scope_and_declared_instances` |
| 全球输入 fail-closed | Resolver 和直接 Materializer 双入口门禁；`test_resolver_never_admits_global_definitions_into_a_share_plans`、`test_resolver_rejects_global_dataset_catalog_by_default`、`test_materializer_rejects_global_definition_even_for_direct_plan` |
| correction 同字节新 lineage / 保留旧引用 | `test_unchanged_downstream_value_still_gets_new_correction_lineage`、`test_partial_correction_preserves_fixed_refs_after_formal_retention_promotion`、隔离 PostgreSQL `test_postgres_correction_same_bytes_new_lineage_and_fixed_refs_survive_pin` |
| 原子发布、并发回收、Formal pin 同事务 | `src/repositories/platform/feature.py`、migration `0013_wp0302_feature_store`；`test_feature_repository_round_trip_and_pin_is_transactional`、`test_feature_store_control_plane_rollback_removes_staged_files_and_rows`、`test_concurrent_publication_cannot_adopt_files_pending_rollback`、`test_feature_publication_lock_is_exclusive_across_processes` |
| Formal 发布时间不能绕过 | `test_feature_repository_formal_bundle_rejects_late_snapshot_but_preview_can_read_it`、`test_feature_repository_formal_bundle_rejects_late_partition_with_early_manifest` |
| Contract / Golden / generated 同步 | C-006 FeaturePartition/FeatureSnapshot/FeatureBundle；JSON Schema、OpenAPI、生成 TypeScript 与 Golden Payload；`scripts/export_platform_contracts.py --check`、`test_feature_partition_golden_hash_and_size_are_real_parquet_evidence` |
| 数据库升级/回滚 | FeatureRepository 集成测试与 PostgreSQL foundation 的空库升级、幂等、降级到 base 后重建；只在随机 `visory_test_*` 数据库执行 |

## 实现阶段验证

2026-10-07 实现阶段实际执行结果（PR 准备前的历史证据）：

| 检查 | 结果 |
| --- | --- |
| 完整 `tests/platform tests/integration/platform` | `761 passed, 5 skipped, 11 warnings`，162.60 秒；使用已有 Python 3.12.9 验证环境与独立临时 PostgreSQL 16 |
| Contract/Golden/Registry/generated 定向 | `68 passed, 1 warning` |
| `scripts/check_ai_assets.py` / `scripts/check_visory_baseline.py` | 通过；相对链接检查无断链 |
| `scripts/export_platform_contracts.py --check` | 通过；由生成器同步，不手改导出文件 |
| Python syntax / critical flake8 / deterministic gate | 通过；Git-for-Windows Bash 复用已有 `.venv`，未安装依赖 |
| Web ESLint / `tsc -b` / Vite build | 通过；复用已安装依赖，bundled Node.js 24.19.0；未重新执行 `npm ci`，未改变 lockfile |
| `git diff --check` | 通过 |
| 远程 Governance / backend / web | Run `37568286328` 三项 `completed / success`；实际实现 head `a7ba8d055b3fccc8bfd5bd14eeabb27680ab0b8a`，不是 main 的既有 CI |

首次完整平台收集因系统 Python 缺少 `markdown2`/`lxml_html_clean` 失败，临时混合依赖下 flake8 metadata 也不可用；切换已有完整 `.venv` 后以上检查实际通过。新增 migration 同时更新 foundation 测试的最新 head/table 清单；定点升级 `0012` 的断言仍保持对该固定 revision 校验。未修改 WP-0207 的实现或历史状态说明；后续 PR-PREP 收敛当前 WP-0301/WP-0302 汇总。

5 个 skipped 为既有符号链接测试（4 项，Windows 无创建权限）和 POSIX 密码文件权限测试（1 项，Windows mode bits 不权威），不是 WP-0302 的 Feature 测试；Feature Repository/Store 集成测试实际运行。警告为既有 TestClient collection 与 Pydantic 字段 alias 警告，未以静默忽略换取绿色。

隔离数据库由 fixture 创建随机库并清理；测试用容器及临时凭据在收尾清理，不保留生产连接信息。

## 实现阶段远程推送与验收闭环（历史证据）

- 实现提交：`a7ba8d055b3fccc8bfd5bd14eeabb27680ab0b8a`，基于指定基线；推送分支 `origin/codex/wp-0302-feature-bundle`，实时 `git ls-remote` 确认该分支与本地实现 HEAD 一致。
- 现有 `Visory Baseline CI` 仅由 `pull_request` / `workflow_dispatch` 触发，因此推送后对本分支显式触发既有 `ci.yml`，未创建 PR、未修改 workflow、未启用生产调度。
- Run `37568286328`，`workflow_dispatch`，head 为上述实现提交；北京时间 2026-10-07 11:46:09 创建，11:54:48 全部完成。
- Governance Job `112620936221`、Python deterministic gate Job `112620936313`、Web lint and build Job `112620936449` 均为 `completed / success`。
- 远程 Python：`7119 passed, 4 deselected, 56 warnings, 572 subtests passed`，382.97 秒；`backend-gate: all checks passed`。包含隔离 PostgreSQL service 集成，Feature 定向用例实际运行；未将 Windows 跳过的符号链接/POSIX 权限测试当作本地已验证项。
- 远程 Web 使用工作流既有 Node 20，实际执行 `npm ci` / lint / build；依赖声明和 lockfile 未改变。
- 本记录的收尾变更只更新验收文档与 WP-0302 状态，运行代码、Migration、测试和 generated contracts 与已通过远程 CI 的实现提交相同；文档收尾单独执行 Governance/baseline/generated/diff 校验。
- `VERIFIED` 只表示本次 WP-0302 的代码与契约验收，不表示已合并、已发布、M3 整体 Exit Gate 或生产认证。WP-0207 及 WP-0303/0304/0305 不变；真实数据历史全量物化、Hikyuu Cache、服务器 Benchmark 和生产恢复演练不在本次授权范围。

## 核心行执行覆盖率与最终契约复核

最终 Feature 定向测试（含真实隔离 PostgreSQL）`56 passed`。使用标准库 `sys.settrace` / `threading.settrace` 收集三个核心模块实际执行行，与 `trace._find_executable_linenos` 的可执行行集合交集计数；未安装覆盖率插件，未排除未执行失败路径以提高结果。

| 模块 | 执行行 / 可执行行 | 行执行覆盖率 |
| --- | --- | --- |
| `src/schemas/platform/feature.py` | 599 / 685 | 87.45% |
| `src/services/platform/feature_store.py` | 638 / 749 | 85.18% |
| `src/repositories/platform/feature.py` | 399 / 428 | 93.22% |
| 三模块合计 | 1636 / 1862 | 87.86% |

该指标仅是上述测试目标的行执行比例，不等同于分支覆盖率或完整生产验收。对应可复现测试命令：

```bash
python -m pytest -q -rs tests/platform/test_feature_store_contracts.py tests/platform/test_feature_partition_golden_bytes.py tests/integration/platform/test_feature_repository.py tests/integration/platform/test_feature_store_postgres.py
```

最终复核补充 `test_correction_cannot_change_logical_manifest_identity`：先实际复现 3 个 `DID NOT RAISE`，再统一内存/数据库入口的 correction 逻辑身份约束，拒绝改变 `as_of_trade_date`、`cutoff_at` 或 `dependency_plan_hash`，拒绝时不产生新文件、不改变旧 Snapshot/Bundle。该回归最终 3 项通过。

## PR-PREP 范围复核与本轮验证（2026-10-07）

- 已执行 `git fetch --all --prune`，实时远程基线和准备起点分别为 `6aa9fa82e31ad0ad175cc1f6650ad7db67fa0222` 与 `2ac0f6e6103d91c829893b4ad9da48dd3332f40c`。WP-0302 隔离分支初始干净、与远程一致；`git pull --ff-only` 返回已是最新。主 checkout 因三个既有文档改动未 pull、未切分支、未修改文件。
- 起点相对 main 为 47 个文件、两个提交：实现提交 `a7ba8d0` 与验收文档提交 `2ac0f6e`。完整文件清单只涉及 Feature Partition/Snapshot/Bundle、Feature Store、WP-0301 DependencyPlan 的必要衔接、Migration `0013`、Contract/Golden、相关测试与文档；Web 仅为 generated types，无新增 runtime API、页面、调度或真实 Provider。没有 WP-0303/0304/0305、Hikyuu Cache、相邻 WP 实现、依赖声明、lockfile 或 workflow 变更。
- 本轮状态修复只落在 WP-0302 worktree 的 `IMPLEMENTATION-STATUS.md`、本记录与 `docs/CHANGELOG.md`：WP-0301 的 PR #40 与合入后 Run `36601155597` 已实时核验；当前状态和唯一 WP 计数以 [实现状态](IMPLEMENTATION-STATUS.md) 为真源。WP-0207 历史计数不重写；WP-0302 未合入，不标记 `RELEASED`。

| 本轮检查 | 实际结果与边界 |
| --- | --- |
| 平台及真实隔离 PostgreSQL integration | `761 passed, 5 skipped, 11 warnings`，94.61 秒；已有 Python 3.12.9 / PyArrow 18.1.0，本地已有 `postgres:16` 镜像、loopback-only 动态端口、tmpfs、新建随机 `visory_test_*` 数据库；Feature 和 Migration 集成实际运行，测试容器与临时凭据已清理 |
| Governance / baseline / generated contract | `check_ai_assets.py`、`check_visory_baseline.py`、`export_platform_contracts.py --check` 通过；文档收敛后再次复验通过，606 个链接、0 broken |
| Backend gate 定向阶段 | `ci_gate.sh syntax`、`flake8`、`deterministic` 通过；本分支 20 个改动 Python 文件 `py_compile` 通过 |
| Web | bundled Node.js 24.19.0、已有依赖的 ESLint、`tsc -b`、Vite build 通过；未重新 `npm ci`、未改依赖或 lockfile |
| 完整 offline backend gate / 全量 Web Vitest | 本轮未重跑；平台模块与 Web lint/build 不能替代全仓测试结果。旧远程完整 backend 结果只属于实现提交 `a7ba8d0` |
| PR 创建前的 CI 边界 | 本节记录 PR 创建前的准备证据；Run `37568286328` 的三项绿色结果只属于 `a7ba8d0`，不能替代 `2ac0f6e` 或后续状态收敛提交/PR HEAD 的 CI。最终合入判定必须读取实际 PR 当前 HEAD 的 Governance / Python / Web 结果 |

本轮平台测试命令（仅配合 fixture 要求的隔离 `VISORY_TEST_POSTGRES_*` 环境，不读取生产连接）：

```bash
python -m pytest -q -rs -m "not network" --timeout=120 -o timeout_method=thread tests/platform tests/integration/platform
```

5 个跳过项仍为四个 Windows 符号链接权限测试和一个 POSIX mode bits 测试；没有 Feature/PostgreSQL 测试跳过。确定性脚本首次选中缺少 pandas 的 bundled Python 3.14.7，报 `ModuleNotFoundError: No module named 'pandas'`；将 Bash `python3` 固定到已有 Python 3.12.9 环境后通过，未修改脚本或安装依赖。本轮没有重测标准库行执行覆盖率，前节 `87.86%` 仅保留为实现阶段历史指标。

PR 需要单独授权后创建，描述须覆盖范围、上述实际验证、未验证项、兼容性、风险和下方完整回滚计划；只有 PR 当前 HEAD 的 Governance / Python / Web 均成功，才能报告 merge-ready。该判定不授权 merge、部署、发布或生产认证。

## 限制与回滚

- PyArrow 字节格式使用仓库既有受控 `18.1.0`；未新增或升级依赖声明。
- **兼容性**：新增 Feature 契约和 `ResourceType.FEATURE_BUNDLE`；`FeatureDependencyPlan` 扩展 date/warmup/lookback 字段并收紧非空实例、日期范围及 A 股域门禁，规范化 Hash 的字段集随之变化。本轮用 main 的旧 Golden Payload 实际复现：携带旧非空 `plan_hash` 时被当前模型拒绝，不能宣称历史序列化 Plan 无损兼容；需要重新生成新 Plan，不能静默重算或改写旧 Snapshot/Bundle 的固定引用。当前非测试调用方仅为 Schema/Registry/Resolver/Feature Store，无 runtime API 路由或前端消费方；历史消费者迁移不在本 WP 范围。
- 仅支持已验证本地文件系统的排他锁与同文件系统 rename；锁竞争报错要求调用方重试。未认证 NFS、分布式文件系统或对象存储实现。
- 未运行生产数据认证、生产端到端回测、调度或恢复演练。核心行执行覆盖率通过标准库追踪测得，不宣称分支覆盖率、全仓覆盖率或生产认证。
- Web 只同步 generated types，没有页面行为变化，不需要 UI 前后截图。当前没有对应的英文专题文档，未复制新增英文说明。
- 以下为回滚计划，不是本轮已执行操作；代码、数据库、PR 或外部状态变更均须相应单独授权。本轮未部署或连接生产，不需要也不执行生产回滚。
- **完整代码/契约/文档回滚**：若未来以普通 merge 合入，先核验 WP-0302 PR 的实际 merge SHA 及第一 parent 为合入前目标 main（不假设届时 main 仍为本轮基线），再执行 `git revert -m 1 <WP-0302-merge-sha>`；覆盖本 PR 的全部 change set，而非仅 `a7ba8d0`。不得误用 WP-0301 merge SHA `6aa9fa82...`，不得 reset、force-push、stash 或 clean。若改用逐提交 revert，必须按新到旧包含全部状态收敛提交、文档提交 `2ac0f6e6103d91c829893b4ad9da48dd3332f40c` 和实现提交 `a7ba8d055b3fccc8bfd5bd14eeabb27680ab0b8a`，不能遗漏 generated contracts 或文档。
- **状态收尾**：完整 revert 会同时撤销本 PR 对 WP-0301 状态的纠错；因此回滚 PR 中必须按仍留在 main 的 PR #40 / Run `36601155597` 证据保留 WP-0301 `VERIFIED / MERGED`，重新核对 WP-0302 当前状态与计数，不能留下 `WP-0301=NOT_STARTED` 或无当前主线实现的 `15/45`。WP-0207 与相邻 WP 不变，生产仍 `NOT CERTIFIED`、`RELEASED=false`。
- **数据库回滚独立处理**：未应用 `0013` 时无数据库动作；已应用时可保留无人使用的新增表，代码 revert 不等于自动降级。需要物理降级时，必须先停止对应消费者/Worker、备份控制面及固定 Manifest/Bundle 引用，确认没有后续 migration/消费者依赖，并在仍保留 `0013` downgrade 代码的版本中，单独授权执行降回 `0012_wp0204_benchmark_dataset_extension`。该降级删除 `feature_bundle_partition_ref`、`feature_bundle`、`feature_snapshot_partition_ref`、`feature_snapshot`、`feature_partition` 五张表；本轮只用随机隔离数据库验证降级/升级及回到 base 后重建，不授权任何真实数据库操作。
- **数据面和复验**：保留原有不可变 Parquet、旧 Snapshot/Bundle 的固定引用及持久 `.feature-publication.lock`，不自动清文件、不改绑“最新文件”。回滚后复跑 Governance、generated contract、对应模块/Migration 测试和 Web lint/build，在回滚 PR 当前 HEAD 重新获得三项阻断 CI；备份/恢复演练与生产恢复证据仍未验证。
- 正式引用和旧文件没有自动清理或变更入口；不要删除 `.feature-publication.lock` 或按目录“最新文件”重绑定引用。
