# Storage Namespace 与 Artifact 发布（WP-0102）

最后更新：2026-08-30

## 1. 范围与边界

WP-0102 建立本地文件系统 `local_fs` 的单一逻辑 Namespace、Artifact Registry、原子 Publisher、完整性消费门禁，以及 Orphan 的只读 Dry-run 与恢复注册。它不创建 Task/Attempt/Lease 表，不实现 Artifact 下载端点、鉴权、文件公网服务、Orphan 删除、Raw/Canonical/Snapshot/Provider，也不迁移 Legacy SQLite、既有报告或历史数据目录。

业务对象、PostgreSQL、Manifest、OpenAPI 和前端类型只保存逻辑 `StorageRef`：

```yaml
storage_backend: local_fs
storage_namespace: app
relative_path: artifacts/type=report/year=2026/month=08/artifact_id=<artifact_id>/payload.json
content_hash: sha256:<64 lowercase hex>
media_type: application/json
size_bytes: 123
```

宿主机绝对路径只由 `VISORY_RUNTIME_ROOT` 提供，不能进入上述契约、数据库、Manifest、API、日志或公开错误。测试使用 pytest `tmp_path`，每个用例独立；本 WP 不创建真实 `/data`。

## 2. 环境绑定与目录

`StorageRuntimeSettings.from_environment()` 只接受显式绝对路径：

```bash
export VISORY_RUNTIME_ROOT=/absolute/path/to/visory-runtime
```

逻辑 Namespace `app` 绑定到：

```text
<VISORY_RUNTIME_ROOT>/storage/app/
├── .staging/<artifact_id>-<invocation_uuid>/
├── quarantine/<artifact_id>-<invocation_uuid>/diagnostic.json
└── artifacts/type=<artifact_type>/year=YYYY/month=MM/artifact_id=<artifact_id>/
    ├── <payload_filename>
    └── manifest.json
```

`.staging`、`quarantine` 与正式 `artifacts` 位于同一 Namespace/文件系统。调用方只提供经过 Schema 校验的单段 `payload_filename`；Publisher 根据 Artifact 类型、发布时间和 `artifact_id` 构造正式路径，调用方不能指定宿主机路径或绕过 Namespace 根。

## 3. 路径安全

`StorageRef.relative_path` 与 Resolver 均要求规范 POSIX 相对路径，并拒绝：

- 绝对路径、Windows 盘符、UNC/反斜杠和 URI 式路径；
- 空段、`.`、`..`、控制字符和 DEL；
- 直接使用内部 `.staging`/`quarantine` 作为业务目标；
- Runtime Root、Namespace Root、中间目录或目标上的 Symlink；
- 已存在的正式文件或目录。

正式路径包含新的 `artifact_id`；Correction 或重新发布必须生成新 ID 和新目录，旧 Artifact 不覆盖、不原地修改。

## 4. 原子发布顺序

`ArtifactPublisherService` 的顺序固定为：

1. 校验 Artifact/owner/可空 Attempt ID、文件名、媒体类型和声明 Hash/大小；
2. 计算 payload SHA-256 与最终逻辑 `StorageRef`；
3. 在同 Namespace 的唯一 `.staging` 目录以 exclusive create 写 payload；
4. fsync payload，生成确定性 `manifest.json` 和 `manifest_hash`，再 fsync Manifest 与 Staging 目录；
5. 重新验证正式父链无 Symlink、目标不存在；
6. 使用同文件系统 `os.rename` 原子发布目录并 fsync 正式父目录；
7. rename 成功后，由 Application Service 打开的 PostgreSQL 事务调用 `ArtifactRepository.add_published_artifact()`；Repository 不调用 commit；
8. 事务提交后才返回 `ArtifactPublishResult`，消费者只查询 `publication_state=PUBLISHED` 且 `integrity_state=VERIFIED` 的记录。

Manifest Hash 使用固定 `artifact_manifest_1.0.0` 规范化配置，覆盖 Manifest 除 `manifest_hash` 自身以外的全部字段。Manifest 不包含 Runtime Root、Staging UUID、DSN 或 Secret。

## 5. 故障与完整性语义

| 故障 | 稳定结果 |
| --- | --- |
| 内容、Hash、大小或输入校验失败 | 不发布、不登记；在受控 `quarantine` 留下只含稳定错误码的诊断 |
| Staging 写入失败 | 不 rename、不登记；返回 `ARTIFACT_WRITE_FAILED` |
| 原子 rename 失败 | 不登记；返回 `ARTIFACT_RENAME_FAILED` 或 `ARTIFACT_TARGET_EXISTS` |
| rename 成功、数据库事务失败 | 不删除正式目录；返回 `ARTIFACT_REGISTRY_WRITE_FAILED`，留下消费者不可见 Orphan |
| Registry 有记录但 payload 缺失 | 标记 `MISSING`，返回 `ARTIFACT_FILE_MISSING` 并阻断消费 |
| Registry 有记录但大小/Hash 不符 | 标记 `SIZE_MISMATCH`/`HASH_MISMATCH` 并阻断消费 |
| Manifest 缺失、格式错误、Hash 错误或与 Registry 不一致 | 标记 `MANIFEST_INVALID` 并阻断消费 |

公开错误不包含宿主机路径、底层 OSError/SQL、DSN 或 Secret。数据库回滚不能删除 rename 已成功的目录。

## 6. Artifact Registry 与 Migration

Alembic head 为 `0003_wp0102_artifact_registry`，parent 为 `0002_wp0101_asset_identity`。表 `artifact_registry` 保存：

- `artifact_id`、`artifact_type`、拆分后的 `owner_resource_ref`、可空 `attempt_id`；
- 展开的逻辑 StorageRef：`storage_backend`、`storage_namespace`、`relative_path`、`content_hash`；
- `media_type`、`size_bytes`、`artifact_hash`、`manifest_hash`、`schema_version`；
- `created_at`、`published_at`、`retention_class`、`visibility`；
- 明确的 `publication_state`、`integrity_state`、`integrity_checked_at`、`integrity_failure_code`。

表中没有 Runtime Root、绝对路径、裸 `status` 或 Task/Attempt 外键。`attempt_id` 只做平台资源 ID 格式约束。

```bash
python -m alembic upgrade head
python -m alembic current
python -m alembic downgrade 0002_wp0101_asset_identity
python -m alembic upgrade head
```

Downgrade 只删除数据库 Schema，不扫描或删除任何业务文件。

## 7. Orphan Dry-run 与恢复

`ArtifactOrphanSweeper` 只枚举以下已知、固定深度的正式目录：

```text
artifacts/type=*/year=*/month=*/artifact_id=*/manifest.json
```

未知目录、`.staging`、`quarantine` 和没有有效平台 Manifest 的目录不会作为可恢复候选。Dry-run 对每个候选重新校验目录结构、逻辑路径、Manifest Schema/Hash、payload Hash/大小，并输出 Artifact ID、原因、预计字节数和唯一动作 `RECOVER_REGISTRATION`；`deletion_performed` 永远为 `false`。

恢复注册在写数据库前再次校验全部证据，使用主键冲突安全的幂等 insert。重复恢复返回 `already_registered=true`。WP-0102 没有 delete 动作，因此不会触碰 `PINNED`/`AUDIT` 引用闭包。

## 8. 契约与 API 边界

以下 C-003 Schema 已纳入 Contract Registry、JSON Schema、C-010 OpenAPI components 和前端 TypeScript 生成：

- `ArtifactRecord`
- `ArtifactManifest`
- `ArtifactPublishResult`
- `ArtifactRecoveryResult`
- `OrphanDryRunResult`

运行：

```bash
python scripts/export_platform_contracts.py
python scripts/export_platform_contracts.py --check
```

本 WP 不新增 Artifact HTTP 路由。未来 API 只能接收 `artifact_id` 并执行鉴权，不能接收任意路径。

## 9. 回滚

- 合并前：关闭 G007 PR；
- 数据库：downgrade 至 `0002_wp0101_asset_identity`，只删除 `artifact_registry`；
- 代码：在新分支普通 revert G007 提交并通过新 PR 合入；
- 文件：Migration 和数据库回滚均不自动删除正式目录、Orphan、Quarantine 或 Staging，避免把已成功 rename 的证据误删；任何未来删除能力必须是独立 WP、先 Dry-run 并获得 owner 明确确认；
- 配置：移除 `VISORY_RUNTIME_ROOT` 即停止使用新 Artifact 文件根，Legacy SQLite/API 保持原行为。
