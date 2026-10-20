"""Regression shields for the WP-0303 delta on the reviewed main baseline."""

from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

from tests.platform._provider_admission_support import synthetic_source_route
from src.services.platform.provider_admission import ProviderAdmissionGateError
from tests.platform.test_provider_endpoint_admission import NOW, RUN_ID, _package, _verifier


ROOT = Path(__file__).resolve().parents[2]
MERGED_HEAD = "0017_wp0303_mainline_merge"


def test_mainline_migration_has_one_additive_merge_head():
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    scripts = ScriptDirectory.from_config(config)
    assert scripts.get_heads() == [MERGED_HEAD]
    assert set(scripts.get_revision(MERGED_HEAD).down_revision) == {
        "0014_wp0207_source_binding",
        "0016_wp0303_provider_endpoint_admission",
    }


@pytest.mark.parametrize("scenario", ("missing", "blocked", "unavailable", "fixture", "drift", "identity"))
def test_pit_receipt_cannot_bypass_source_route_gate(scenario):
    verifier = _verifier(*_package())
    run = verifier.raw_repository.run
    route = synthetic_source_route(run)
    if scenario in {"blocked", "unavailable"}:
        route = synthetic_source_route(run, state=scenario.upper())
    elif scenario == "fixture":
        route = synthetic_source_route(run, state="FIXTURE_ONLY", kind="FIXTURE")
    elif scenario == "drift":
        route = route.model_copy(update={"source_route_hash": "sha256:" + "0" * 64})
    elif scenario == "identity":
        route = synthetic_source_route(run, dataset_id="security_master")
    run.source_route_evidence = None if scenario == "missing" else route

    with pytest.raises(ProviderAdmissionGateError) as captured:
        verifier.verify_formal_run(None, RUN_ID, target_market="CN", target_date=NOW.date(), cutoff_at=NOW)
    assert captured.value.error_code.startswith("SOURCE_ADMISSION_SOURCE_ROUTE_")


def test_source_route_and_endpoint_admission_both_required():
    verifier = _verifier(*_package())
    verifier.raw_repository.run.source_route_evidence = synthetic_source_route(verifier.raw_repository.run)
    assert verifier.verify_formal_run(
        None, RUN_ID, target_market="CN", target_date=NOW.date(), cutoff_at=NOW
    ).provider_run_id == RUN_ID
    verifier.repository.binding = None
    with pytest.raises(ProviderAdmissionGateError, match="ProviderEndpointRunBinding"):
        verifier.verify_formal_run(None, RUN_ID, target_market="CN", target_date=NOW.date(), cutoff_at=NOW)
