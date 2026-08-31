from __future__ import annotations

import pytest

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


def test_provider_policy_effective_intervals_cannot_overlap(isolated_postgres_database):
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
        repo.add_policy(session, policies[0])

    from datetime import timedelta
    from src.repositories.platform import PlatformDatabaseError

    overlapping = policies[0].model_copy(update={
        "provider_policy_id": f"{policies[0].dataset_id}_v2",
        "policy_version": "2.0.0",
        "effective_from": policies[0].effective_from + timedelta(minutes=1),
    })
    with pytest.raises(PlatformDatabaseError) as captured:
        with database.transaction() as session:
            ProviderRegistryRepository.add_policy(session, overlapping)
    assert captured.value.error_code == "DATABASE_OPERATION_FAILED"
    assert captured.value.retryable is False
