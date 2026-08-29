from __future__ import annotations

import pytest

from src.schemas.platform import PLATFORM_CONTRACTS, PlatformContractModel
from src.schemas.platform.registry import validate_contract_registry


def test_registry_contains_only_wp_0001_contracts_and_required_metadata() -> None:
    registrations = PLATFORM_CONTRACTS.list()
    assert registrations
    assert {item.contract_id.split("/", 1)[0] for item in registrations} <= {
        "C-001",
        "C-002",
        "C-003",
    }

    for item in registrations:
        assert item.owner_module
        assert item.producer
        assert item.consumers
        assert item.schema_version
        assert item.business_key
        assert item.time_semantics is not None
        assert item.version_semantics is not None
        assert item.quality_semantics is not None
        assert item.storage_profile
        assert item.retention_class
        assert item.compatibility
        assert item.golden_payloads
        assert item.json_schema["additionalProperties"] is False
        assert item.hash_profile.profile_id

    validate_contract_registry(PLATFORM_CONTRACTS)


@pytest.mark.parametrize("field_name", ["status", "version", "date", "timestamp", "hash"])
def test_platform_model_rejects_ambiguous_bare_field_names(field_name: str) -> None:
    with pytest.raises(TypeError, match="ambiguous platform contract field"):
        type(
            "InvalidContract",
            (PlatformContractModel,),
            {"__annotations__": {field_name: str}, "__module__": __name__},
        )


def test_registry_lookup_is_explicit() -> None:
    contract = PLATFORM_CONTRACTS.get("C-003/StorageRef")
    assert contract.resource_id_field is None
    with pytest.raises(KeyError):
        PLATFORM_CONTRACTS.get("C-004/ProviderDefinition")
