# Visory-G014 / WP-0203 Canonical Normalization



WP-0203 introduces provider-to-canonical mappings for `a_stock_data` and `financial_api` across `security_master`, `trading_calendar`, and `bar_1d_raw`. Raw objects remain immutable; normalization emits append-only canonical partitions with deterministic schema/content hashes, quality reports, and explicit ProviderRun/RawObject lineage.



Canonical outputs are written under the configured `VISORY_RUNTIME_ROOT` through `StorageRef` only. Publication uses the single locked `pyarrow==18.1.0` engine, fixed Parquet schema/column order, ZSTD, staging, fsync, and same-filesystem atomic rename; PostgreSQL stores registry, quality, and lineage metadata. Missing `pyarrow` is a blocking error and never falls back to a different format. Failed quality gates never publish consumable partitions.

Input-boundary failures (including invalid Raw manifests, Raw hash/size mismatches, and registry binding mismatches) are recorded as failed CanonicalQualityReport rows in the same transaction as the Durable Task failure. If a lease expires after atomic rename, the Registry transaction rejects the stale worker, leaves the renamed file as an invisible Orphan, and the next lease creates a new Attempt without overwriting the prior path.



The implementation intentionally does not create DataSnapshot, certified pointers, production provider connections, or real `/data` writes. Migration `0009_wp0203_core_canonical_normalization` is schema-only on downgrade and never deletes business files.





## 事务与 Artifact 注册



Canonical partition 文件先在同一 Storage Namespace 的 staging 目录完成校验、fsync 和原子 rename；配置了 `ArtifactPublisherService` 的任务 Worker 随后在同一个数据库事务回调中登记 Artifact、CanonicalQualityReport、CanonicalPartition 并完成 Task。数据库失败不会回删已 rename 的文件，该文件保持不可见 Orphan，后续由受控扫描恢复注册。


## Identity, Mapping, and Calendar Gates

`CanonicalNormalizationTaskWorker` loads the exact versioned Mapping from `canonical_mapping_definition` unless a test supplies an explicit loader. It never evaluates expressions or imports arbitrary mapping code.

For `security_master`, the worker derives a Canonical stock identity only from a Provider symbol with an explicit exchange suffix and an agreeing mapped exchange; it creates or validates the existing `AssetIdentityRecord` and a verified Provider alias in `<provider_id>:cn_stock`. Bare six-digit values, unknown assets, multi-match aliases, or provider/exchange conflicts become deterministic Canonical quality failures. `bar_1d_raw` can only resolve through that existing Provider alias.

For `bar_1d_raw`, a caller-supplied test resolver may be used, but the default runtime resolver reads the already published, integrity-checked Canonical `trading_calendar` partition for the requested market and date. A missing, corrupt, incomplete, or closed calendar rejects the bar; it is never treated as an implicit trading day.