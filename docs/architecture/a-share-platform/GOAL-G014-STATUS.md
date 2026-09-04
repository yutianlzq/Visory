# Visory-G014 / WP-0203 Core Canonical Normalization

Last updated: 2026-09-04

## Status

- Goal: `Visory-G014`
- Work Package: `WP-0203 Core Canonical Normalization`
- Status: `IN_PROGRESS`
- Fixed baseline: `71328fd512400a0cc0a2c38c128fead14a9a57d4`
- Working branch: `goal/g014-wp-0203-core-canonical-normalization`
- Progress: `9/45` (WP-0203 increments only after verification)
- Target migration: `0009_wp0203_core_canonical_normalization`, parent `0008_wp0202_raw_schema_hardening`

## Scope delivered

- Canonical mapping, partition, quality-report, task requirements and task-result contracts.
- PostgreSQL registry tables and provider/raw lineage.
- Deterministic normalization service with Decimal conversion, explicit UTC time handling, quality rejection, append-only Parquet publication, Registry-backed Mapping loading, Provider Alias identity provisioning/resolution, and optional Artifact Publisher registration in the same caller-owned transaction.
- Contract registry/OpenAPI/JSON Schema/frontend generation inputs.

## Explicit non-goals

No DataSnapshot, certification pointers, production providers, real `/data`, WP-0204/WP-0205, Legacy storage migration, or public download API.

## Verification

Focused Canonical tests cover all six Provider×Dataset mappings, deterministic Parquet schema/order/hash, raw-boundary rejection with persisted QualityReport evidence, identity provisioning/resolution, missing-calendar rejection, cancel, Registry-transaction Orphan behavior, and lease-loss recovery with a new Attempt. PostgreSQL 16 integration covers all three datasets in a single Raw→Canonical chain plus migration isolation; the combined foundation/provider/canonical suite is 16 passed. The controlled engine is only `pyarrow==18.1.0`; missing the engine is a blocking `CANONICAL_PARQUET_ENGINE_UNAVAILABLE` error, never a JSONL fallback. Platform tests are 313 passed, 5 skipped; contract export, governance, baseline, Web lint/build, and `git diff --check` pass. GitHub Actions Run `33835586388` has Governance, Python, and Web all successful. Goal/WP remain `IN_PROGRESS` at `9/45`; WP-0203 is intentionally not VERIFIED until G015 expands datasets.

## Rollback

Use ordinary `git revert`; in an isolated database run `alembic downgrade 0008_wp0202_raw_schema_hardening`. Downgrade does not delete canonical files.
