from __future__ import annotations

from datetime import datetime, timezone

from src.repositories.platform import PostgresDatabase, ProviderRegistryRepository
from src.schemas.platform import (
    DatasetDefinition, ProviderCapability, ProviderDefinition, ProviderKind,
    ProviderCapabilityStatus, ProviderMergeMode, ProviderPolicy,
)

ADAPTER_REGISTRY: dict[str, str] = {
    "a_stock_data": "a-stock-data controlled adapter",
    "financial_api": "Financial-API controlled adapter",
}


def default_registry_records(now: datetime | None = None):
    now = now or datetime.now(timezone.utc)
    providers = (
        ProviderDefinition(provider_id="a_stock_data", display_name="a-stock-data", adapter_name="a_stock_data", adapter_version="1.0.0", provider_kind=ProviderKind.AGGREGATOR, credential_ref=None, actual_upstream="declared_by_adapter", created_at=now, updated_at=now),
        ProviderDefinition(provider_id="financial_api", display_name="Financial-API", adapter_name="financial_api", adapter_version="1.0.0", provider_kind=ProviderKind.DIRECT, credential_ref="secret://financial_api", actual_upstream=None, created_at=now, updated_at=now),
    )
    datasets = tuple(
        DatasetDefinition(
            dataset_id=dataset_id, schema_version="1.0.0", entity_scope="a_share", frequency=frequency,
            primary_key_fields=keys, required_fields=fields, optional_fields=optional,
            field_types={field: ("string" if field == "entity_key" else "date" if field == "trade_date" else "number") for field in (*fields, *optional)},
            units={field: "unit" for field in (*fields, *optional)}, enum_domains={}, time_semantics={"available_at": "timestamptz"},
            null_semantics={field: "forbidden" for field in fields}, partition_template=f"{dataset_id}/{{date}}", quality_rule_ids=("identity_resolved",), owner_module="data_platform",
        )
        for dataset_id, frequency, keys, fields, optional in (
            ("security_master", "event", ("entity_key",), ("entity_key", "canonical_id"), ("name",)),
            ("trading_calendar", "daily", ("market", "trade_date"), ("market", "trade_date", "is_open"), ()),
            ("bar_1d_raw", "daily", ("entity_key", "trade_date"), ("entity_key", "trade_date", "open", "high", "low", "close", "volume"), ("turnover",)),
        )
    )
    capabilities = tuple(
        ProviderCapability(provider_id=provider_id, dataset_id=dataset.dataset_id, market="CN", frequency=dataset.frequency, supported_fields=dataset.required_fields, history_start=None, freshness_sla_seconds=86400, rate_limit_profile={"requests_per_minute": 60}, provider_capability_status=ProviderCapabilityStatus.UNVERIFIED, checked_at=now)
        for provider_id in ("a_stock_data", "financial_api") for dataset in datasets
    )
    policies = tuple(
        ProviderPolicy(provider_policy_id=f"{dataset.dataset_id}_v1", dataset_id=dataset.dataset_id, policy_version="1.0.0", primary_provider_id="a_stock_data", supplemental_provider_ids=("financial_api",), allowed_merge_mode=ProviderMergeMode.REPLACE_PARTITION, fallback_triggers=("PRIMARY_UNAVAILABLE", "QUALITY_FAILED"), field_authority_map={field: "a_stock_data" for field in dataset.required_fields}, conflict_tolerance={"mode": "reject"}, freshness_sla_seconds=86400, required_quality_rules=("identity_resolved",), effective_from=now)
        for dataset in datasets
    )
    return providers, datasets, capabilities, policies


class ProviderRegistryService:
    def __init__(self, database: PostgresDatabase, repository: ProviderRegistryRepository | None = None):
        self.database = database
        self.repository = repository or ProviderRegistryRepository()

    def settings_projection(self):
        with self.database.transaction() as session:
            return self.repository.settings_projection(session)

    def bootstrap_defaults(self) -> None:
        with self.database.transaction() as session:
            providers, datasets, capabilities, policies = default_registry_records()
            for record in providers:
                self.repository.add_provider(session, record)
            for record in datasets:
                self.repository.add_dataset(session, record)
            for record in capabilities:
                self.repository.add_capability(session, record)
            for record in policies:
                self.repository.add_policy(session, record)


__all__ = ["ADAPTER_REGISTRY", "ProviderRegistryService", "default_registry_records"]
