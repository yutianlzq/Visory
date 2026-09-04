# Visory-G013 / WP-0202 Provider Raw Schema Hardening

Last updated: 2026-09-01

## Current status

- Goal: `Visory-G013`
- Work Package: `WP-0202 Provider Raw Schema Hardening`
- Goal status: `COMPLETE / VERIFIED`
- Work Package status: `COMPLETE / VERIFIED`
- Fixed baseline: `main=42b3cf20c97459e4f4eb85644adaf03f56aa5dac`
- Working branch: `goal/g013-wp-0202-provider-raw-schema-hardening`
- Start progress: `9/45`
- Target migration: `0008_wp0202_raw_schema_hardening`, parent `0007_wp0202_raw_ingestion`

This Goal only hardens Provider Raw Schema and PostgreSQL coordinated rate limiting. It does not implement field mapping, Canonical Normalization, Snapshot, or WP-0203; it does not connect production Providers, write real `/data`, or use production Secrets.

## Implementation record

- Added independent `ProviderRawSchemaDefinition`; Raw Schema is not derived from canonical `DatasetDefinition` and covers two controlled Providers and three Datasets.
- Added Migration `0008_wp0202_raw_schema_hardening` with `provider_raw_schema_definition`, `provider_rate_limit_window`, and indexes.
- Worker drift classification now uses Provider Raw Schema and optional field types; Provider response bytes remain unchanged.
- Default Worker uses PostgreSQL row-locked fixed-window rate limiting; the in-memory limiter remains only for offline unit tests.
- Provider Raw Schema is included in Contract Registry, JSON Schema, C-010 OpenAPI, and generated frontend types.

## Acceptance evidence

Offline Raw Schema contract, Golden, export drift, platform regression (288 passed, 5 skipped), migration unit tests (8 passed), and real PostgreSQL integration (47 passed) are complete. Web lint and production build, governance/baseline checks, compile, and Flake8 also pass. GitHub Actions final Run `33578007314` is green for Governance, Python, and Web on head `766476d60bc3a1539dc8589fa2d830ed754b7117`; PR #25 is merged as `71328fd512400a0cc0a2c38c128fead14a9a57d4`. The broad repository offline suite was not used as a gate because it is blocked by unrelated environment-sensitive Codex transport tests. This Goal/WP is `VERIFIED`; WP-0203 remains not started.

## Risks and rollback

- Risk: real Provider responses may omit type declarations; field-level classification remains available, while explicit type mismatches are blocking.
- Delivery: head `766476d60bc3a1539dc8589fa2d830ed754b7117`, PR #25, CI Run `33531064869` (Governance/Python/Web all successful).
- Rollback: use ordinary `git revert`; in an isolated database downgrade to `0007_wp0202_raw_ingestion`. Business files are never removed by downgrade.
