# WP-0201 Dataset/Provider Registry

Migration `0006_wp0201_registry_contract_hardening` extends `0004_wp0103_durable_task_control_plane` with four control-plane tables:

- `provider_definition`: controlled adapter identity and `secret://` credential references only;
- `dataset_definition`: immutable versioned field, key, unit, null, time and partition contract;
- `provider_capability`: provider/dataset/schema-version/market/frequency observations;
- `provider_policy`: dataset/schema-version-scoped primary/supplemental policy and effective interval.

The first registry fixture explicitly declares `a_stock_data` as the core aggregator and `financial_api` as the supplemental provider for `security_master`, `trading_calendar` and `bar_1d_raw`. No network probe or production seed runs automatically. The fixture is deterministic and idempotent; conflicting existing content fails explicitly. Applications may call `ProviderRegistryService.bootstrap_defaults()` inside an explicit PostgreSQL transaction when a local control-plane database is intentionally initialized.

`ProviderDefinition` contains no `actual_upstream`; actual upstream is recorded only by a future `ProviderRun`. `adapter_name` is validated against the controlled registry (`a_stock_data`, `financial_api`); policy merge modes are limited to `REPLACE_PARTITION`, `APPEND_DISJOINT`, `ENRICH_FIELDS` and `COMPARE_ONLY`. Repository methods never commit; `PostgresDatabase.transaction()` owns commit/rollback.

Read-only projections are exposed at `/api/platform/v1/provider-registry`, `/api/platform/v1/providers` and `/api/platform/v1/datasets` using the existing C-010 envelope. No provider mutation or arbitrary file/path endpoint is added.
