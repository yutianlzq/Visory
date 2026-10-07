# WP-0302 实现与验收记录

## 边界与状态

- 基线：`main@6aa9fa82e31ad0ad175cc1f6650ad7db67fa0222`。
- 分支：`codex/wp-0302-feature-bundle`；隔离 worktree，未修改 WP-0207 实现。
- 仅增加 WP-0302 的类型、物化/发布边界、PostgreSQL 控制面及验证资产；不实现 WP-0303/0304/0305、Hikyuu Cache 或前端迁移。
- Worker 输入为调用方显式提供的 FeatureRow，未连接真实 Provider、生产数据库、真实 `/data` 或生产调度。
- 本地实现验收不代表远程阻断 CI 通过；WP 保持 `IN_PROGRESS`，生产 `NOT CERTIFIED`，`RELEASED=false`。

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

## 当前验证

2026-10-07 当前实际执行结果：

| 检查 | 结果 |
| --- | --- |
| 完整 `tests/platform tests/integration/platform` | `761 passed, 5 skipped, 11 warnings`，162.60 秒；使用已有 Python 3.12.9 验证环境与独立临时 PostgreSQL 16 |
| Contract/Golden/Registry/generated 定向 | `68 passed, 1 warning` |
| `scripts/check_ai_assets.py` / `scripts/check_visory_baseline.py` | 通过；相对链接检查无断链 |
| `scripts/export_platform_contracts.py --check` | 通过；由生成器同步，不手改导出文件 |
| Python syntax / critical flake8 / deterministic gate | 通过；Git-for-Windows Bash 复用已有 `.venv`，未安装依赖 |
| Web ESLint / `tsc -b` / Vite build | 通过；复用已安装依赖，bundled Node.js 24.19.0；未重新执行 `npm ci`，未改变 lockfile |
| `git diff --check` | 通过 |
| 远程 Governance / backend / web | 尚待本分支推送后独立验证，不用本地结果替代 |

首次完整平台收集因系统 Python 缺少 `markdown2`/`lxml_html_clean` 失败，临时混合依赖下 flake8 metadata 也不可用；切换已有完整 `.venv` 后以上检查实际通过。新增 migration 同时更新 foundation 测试的最新 head/table 清单；定点升级 `0012` 的断言仍保持对该固定 revision 校验。未修改 WP-0207 的实现或既有状态说明。

5 个 skipped 为既有符号链接测试（4 项，Windows 无创建权限）和 POSIX 密码文件权限测试（1 项，Windows mode bits 不权威），不是 WP-0302 的 Feature 测试；Feature Repository/Store 集成测试实际运行。警告为既有 TestClient collection 与 Pydantic 字段 alias 警告，未以静默忽略换取绿色。

隔离数据库由 fixture 创建随机库并清理；测试用容器及临时凭据在收尾清理，不保留生产连接信息。

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

## 限制与回滚

- PyArrow 字节格式使用仓库既有受控 `18.1.0`；未新增或升级依赖声明。
- 仅支持已验证本地文件系统的排他锁与同文件系统 rename；锁竞争报错要求调用方重试。未认证 NFS、分布式文件系统或对象存储实现。
- 未运行生产数据认证、生产端到端回测、调度或恢复演练。核心行执行覆盖率通过标准库追踪测得，不宣称分支覆盖率、全仓覆盖率或生产认证。
- Web 只同步 generated types，没有页面行为变化，不需要 UI 前后截图。当前没有对应的英文专题文档，未复制新增英文说明。
- 回滚代码使用本分支实现提交的普通 revert；数据库只在隔离库验证从 `0013_wp0302_feature_store` 降回 `0012_wp0204_benchmark_dataset_extension`。降级会删除 Feature 控制面五张表，任何真实环境必须先备份及单独授权，不能据本记录直接执行。
- 正式引用和旧文件没有自动清理或变更入口；不要删除 `.feature-publication.lock` 或按目录“最新文件”重绑定引用。
