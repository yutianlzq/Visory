from __future__ import annotations

from src.repositories.platform import ProviderRegistryRepository, upgrade_database
from src.services.platform.provider_registry import default_registry_records


def test_provider_registry_round_trip_and_controlled_adapter(isolated_postgres_database):
    database = isolated_postgres_database
    upgrade_database(database.engine)
    providers, datasets, capabilities, policies = default_registry_records()
    with database.transaction() as session:
        repo = ProviderRegistryRepository()
        for record in providers:
            repo.add_provider(session, record)
        for record in datasets:
            repo.add_dataset(session, record)
        for record in capabilities:
            repo.add_capability(session, record)
        for record in policies:
            repo.add_policy(session, record)
        projection = repo.settings_projection(session)
    assert [item.provider_id for item in projection.providers] == ["a_stock_data", "financial_api"]
    assert [item.dataset_id for item in projection.datasets] == ["bar_1d_raw", "security_master", "trading_calendar"]
    assert projection.policies[0].primary_provider_id == "a_stock_data"
