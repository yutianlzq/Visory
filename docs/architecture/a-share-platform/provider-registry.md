# WP-0201 Dataset/Provider Registry

Migration `0005_wp0201_dataset_provider_registry` extends `0004_wp0103_durable_task_control_plane` with four control-plane tables:

- `provider_definition`: controlled adapter identity and `secret://` credential references only;
- `dataset_definition`: versioned field, key, unit, null and partition contract;
- `provider_capability`: provider/dataset/market/frequency observations;
- `provider_policy`: dataset-scoped primary/supplemental policy and effective interval.

The first registry fixture declares `a_stock_data` as the core aggregator and `financial_api` as the supplemental provider for `security_master`, `trading_calendar` and `bar_1d_raw`. No network probe or production seed runs automatically. Applications may call `ProviderRegistryService.bootstrap_defaults()` inside an explicit PostgreSQL transaction when a local control-plane database is intentionally initialized.

`adapter_name` is validated against the controlled registry (`a_stock_data`, `financial_api`); policy merge modes are limited to `REPLACE_PARTITION`, `APPEND_DISJOINT`, `ENRICH_FIELDS` and `COMPARE_ONLY`. Repository methods never commit; `PostgresDatabase.transaction()` owns commit/rollback.

Read-only projections are exposed at `/api/platform/v1/provider-registry`, `/api/platform/v1/providers` and `/api/platform/v1/datasets` using the existing C-010 envelope. No provider mutation or arbitrary file/path endpoint is added.
