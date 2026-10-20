from sqlalchemy import inspect, text

import pytest

from src.repositories.platform import get_migration_status, upgrade_database
from src.repositories.platform.provider_admission import ProviderAdmissionRepository
from src.services.platform.provider_registry import ProviderRegistryService
from tests.integration.platform.test_provider_endpoint_admission_postgres import _create_run
from tests.platform.test_provider_endpoint_admission import _package


HEAD = "0017_wp0303_mainline_merge"


@pytest.mark.parametrize("starting_revision", (
    "base", "0014_wp0207_source_binding", "0016_wp0303_provider_endpoint_admission",
))
def test_upgrade_from_each_existing_branch_preserves_evidence(
    isolated_postgres_database, tmp_path, starting_revision,
):
    database = isolated_postgres_database
    run = None
    endpoint = None
    before_source = None
    if starting_revision != "base":
        upgrade_database(database.engine, starting_revision)
        ProviderRegistryService(database).bootstrap_defaults()
        if starting_revision == "0014_wp0207_source_binding":
            run, _ = _create_run(database, tmp_path)
            with database.engine.connect() as connection:
                before_source = connection.execute(text(
                    "SELECT source_route_evidence FROM provider_run WHERE provider_run_id=:run_id"
                ), {"run_id": run.provider_run_id}).scalar_one()
            assert before_source is not None
        else:
            endpoint, fingerprint, receipt, _ = _package()
            with database.transaction() as session:
                repository = ProviderAdmissionRepository()
                repository.add_endpoint(session, endpoint)
                repository.add_fingerprint(session, fingerprint)
                repository.add_receipt(session, receipt)

    upgrade_database(database.engine)
    first = get_migration_status(database.engine)
    assert first.current_revision == first.head_revision == HEAD
    assert first.is_at_head
    upgrade_database(database.engine)
    assert get_migration_status(database.engine) == first

    columns = {c["name"]: c for c in inspect(database.engine).get_columns("provider_run")}
    assert "source_route_evidence" in columns
    for table in ("feature_partition", "feature_snapshot_partition_ref", "feature_bundle_partition_ref"):
        assert next(c for c in inspect(database.engine).get_columns(table) if c["name"] == "indicator_id")["type"].length == 128
    assert next(c for c in inspect(database.engine).get_columns("feature_partition") if c["name"] == "partition_key")["type"].length == 386
    if run is not None:
        with database.engine.connect() as connection:
            assert connection.execute(text(
                "SELECT source_route_evidence FROM provider_run WHERE provider_run_id=:run_id"
            ), {"run_id": run.provider_run_id}).scalar_one() == before_source
    if endpoint is not None:
        with database.transaction() as session:
            repository = ProviderAdmissionRepository()
            assert repository.get_endpoint(session, endpoint.provider_endpoint_id, endpoint.provider_id, endpoint.endpoint_contract_version) == endpoint
            assert repository.get_fingerprint(session, fingerprint.adapter_implementation_fingerprint_id) == fingerprint
            assert repository.get_receipt(session, receipt.source_admission_receipt_id) == receipt
