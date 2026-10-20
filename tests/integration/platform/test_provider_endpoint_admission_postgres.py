from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from threading import Barrier, BrokenBarrierError

import pytest
from sqlalchemy import event, inspect, select, text, update

from src.repositories.platform import (
    PlatformDatabaseError,
    PostgresDatabase,
    ProviderAdmissionRepository,
    downgrade_database,
    get_migration_status,
    upgrade_database,
)
from src.repositories.platform.provider_admission import (
    provider_endpoint_run_binding,
    provider_endpoint_run_binding_raw_object,
)
from src.repositories.platform.raw_ingestion import provider_run, raw_object
from src.repositories.platform.provider import provider_capability
from src.schemas.platform import (
    EndpointDatasetBinding,
    RawCompression,
    TaskCreateRequest,
    build_adapter_implementation_fingerprint,
    build_provider_endpoint_definition,
    build_provider_endpoint_run_binding,
    build_source_admission_receipt,
    compute_content_hash,
)
from src.services.platform.provider_admission import (
    AdapterImplementationObservation,
    ProviderAdmissionGateError,
    ProviderAdmissionService,
    ProviderEndpointAdmissionVerifier,
)
from src.services.platform.provider_registry import (
    ProviderRegistryService,
    default_provider_raw_schema_records,
)
from src.services.platform.raw_ingestion import (
    ProviderFetchResponse,
    RawIngestionTaskWorker,
    RawObjectPublisher,
)
from src.services.platform.task_control import TaskControlService


NOW = datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc)
LATEST = "0017_wp0303_mainline_merge"
PREVIOUS = "0015_wp0303_partition_key"


from tests.platform._provider_admission_support import synthetic_source_route
from src.services.platform.provider_source_routes import ProviderSourceRouteRegistry


def _hash(label: str) -> str:
    return compute_content_hash({"evidence": label})


def _create_run(database, tmp_path, *, run_suffix: str = "v1"):
    with database.transaction() as session:
        existing = session.execute(select(provider_capability.c.provider_id).limit(1)).first()
    # 多次 Run 复用同一合成准入状态，不用默认 BLOCKED 记录覆盖它。
    if existing is None:
        ProviderRegistryService(database).bootstrap_defaults()
    # 仅隔离库中的合成 Endpoint；默认真实 capability 和 route 继续拒绝执行。
    with database.transaction() as session:
        session.execute(update(provider_capability).where(
            provider_capability.c.provider_id == "a_stock_data",
            provider_capability.c.dataset_id == "security_master",
            provider_capability.c.dataset_schema_version == "1.0.0",
            provider_capability.c.market == "CN",
            provider_capability.c.frequency == "event",
        ).values(provider_capability_status="AVAILABLE", checked_at=NOW))
    task_control = TaskControlService(database, clock=lambda: NOW, runtime_root=tmp_path)
    task = task_control.create_task(
        TaskCreateRequest(
            task_type="raw_ingestion",
            requested_by=f"owner:provider-admission-test-{run_suffix}",
            request_source="integration_test",
            requirements={
                "provider_id": "a_stock_data",
                "dataset_id": "security_master",
                "dataset_schema_version": "1.0.0",
                "provider_policy_id": "security_master_v1",
                "market": "CN",
                "request": {"as_of": "2026-08-31"},
                "timeout_seconds": 5,
            },
        ),
        idempotency_key=f"provider-admission-run-{run_suffix}",
    )
    lease = task_control.lease_next(
        worker_id=f"provider-admission-worker-{run_suffix}",
        worker_capabilities=("raw_ingestion",),
    )
    assert lease is not None and lease.task.task_id == task.task_id
    schema = next(
        item
        for item in default_provider_raw_schema_records()
        if item.provider_id == "a_stock_data" and item.dataset_id == "security_master"
    )
    content = json.dumps(
        [{field: None for field in schema.required_fields}], sort_keys=True
    ).encode("utf-8")
    response = ProviderFetchResponse(
        content=content,
        media_type="application/json",
        compression=RawCompression.NONE,
        actual_upstream="fixture.a_stock_data",
        observed_at=NOW - timedelta(minutes=5),
        source_published_at=NOW - timedelta(minutes=10),
        raw_schema_fields=schema.required_fields,
        raw_schema_field_types=schema.field_types,
        row_count=1,
    )
    from types import SimpleNamespace

    class SyntheticEndpointTransport:
        def fetch(self, adapter_name, request, *, timeout_seconds):
            assert adapter_name == "a_stock_data"
            assert timeout_seconds == 5
            return response

    route = synthetic_source_route(SimpleNamespace(
        provider_id="a_stock_data", dataset_id="security_master", adapter_version="1.0.0",
        actual_upstream=response.actual_upstream, capability_market="CN",
    ))
    worker = RawIngestionTaskWorker(
        task_control,
        database,
        RawObjectPublisher(tmp_path, database.transaction, clock=lambda: NOW),
        SyntheticEndpointTransport(),
        source_route_registry=ProviderSourceRouteRegistry((route,)),
        clock=lambda: NOW,
    )
    result = worker.execute(lease)
    assert result.raw_object is not None
    return result.provider_run, result.raw_object


def _package(run, raw, *, suffix: str = "v1", admission_level: str = "PIT_CERTIFIED"):
    endpoint = build_provider_endpoint_definition(
        provider_endpoint_id=f"a_stock_data_security_master_{suffix}",
        provider_id=run.provider_id,
        endpoint_contract_version="1.0.0",
        request_method="GET",
        redacted_origin_allowlist=("fixture.a_stock_data",),
        path_family="/",
        request_schema_hash=_hash(f"request-schema-{suffix}"),
        response_schema_hash=_hash(f"response-schema-{suffix}"),
        dataset_bindings=(
            EndpointDatasetBinding(
                dataset_id=run.dataset_id,
                dataset_schema_version=run.dataset_schema_version,
                market_scope=(run.capability_market,),
            ),
        ),
        market_scope=(run.capability_market,),
        pagination_semantics="single terminal response",
        total_semantics="row count is authoritative",
        terminal_semantics="one response terminates",
        valid_zero_row_semantics="zero rows require explicit successful response evidence",
        no_data_semantics="no data remains distinct from provider failure",
        error_semantics="provider and transport errors are explicit",
        revision_semantics="source identity and revision chain are fixed",
        cancellation_semantics="cancelled facts remain explicit",
        source_publication_semantics="source publication time is preserved",
        rate_limit_semantics="fixed provider request window",
        retry_semantics="bounded retryable errors only",
        license_semantics="pinned license evidence controls use",
        license_evidence_hash=_hash("license"),
        effective_from=NOW - timedelta(days=30),
    )
    fingerprint = build_adapter_implementation_fingerprint(
        adapter_implementation_fingerprint_id=f"a_stock_data_security_master_impl_{suffix}",
        provider_endpoint_id=endpoint.provider_endpoint_id,
        provider_id=endpoint.provider_id,
        endpoint_contract_version=endpoint.endpoint_contract_version,
        adapter_bundle_id="a_stock_data_bundle",
        adapter_bundle_version="1.0.0",
        source_repository="https://github.com/example/a-stock-data.git",
        source_commit="a" * 40,
        source_file_path="src/security_master.py",
        source_file_blob_sha256=_hash(f"blob-{suffix}"),
        source_file_sha256=_hash(f"file-{suffix}"),
        function_symbol="security_master.fetch",
        visory_wrapper_version="1.0.0",
        visory_wrapper_hash=_hash(f"wrapper-{suffix}"),
        mapping_version="1.0.0",
        mapping_hash=_hash(f"mapping-{suffix}"),
        quality_rule_versions=("1.0.0",),
        quality_rule_hashes=(_hash(f"quality-{suffix}"),),
        created_at=NOW,
    )
    receipt = build_source_admission_receipt(
        source_admission_receipt_id=f"security_master_receipt_{suffix}",
        provider_endpoint_id=endpoint.provider_endpoint_id,
        provider_id=endpoint.provider_id,
        endpoint_contract_version=endpoint.endpoint_contract_version,
        dataset_id=run.dataset_id,
        dataset_schema_version=run.dataset_schema_version,
        requested_market_scope=(run.capability_market,),
        requested_date_from=date(2026, 1, 1),
        requested_date_to=date(2026, 12, 31),
        source_contract_hash=_hash(f"source-contract-{suffix}"),
        sample_manifest_hash=_hash(f"sample-manifest-{suffix}"),
        observation_log_hash=_hash(f"observation-log-{suffix}"),
        coverage_manifest_hash=_hash(f"coverage-manifest-{suffix}"),
        revision_chain_hash=_hash(f"revision-chain-{suffix}"),
        quality_report_hash=_hash(f"quality-report-{suffix}"),
        license_evidence_hash=_hash("license"),
        expected_unit_and_identity_hash=_hash(f"unit-identity-{suffix}"),
        coverage_summary={"complete": True, "terminal_pages_verified": True},
        admission_level=admission_level,
        admission_status="ACCEPTED",
        issued_at=NOW - timedelta(days=2),
        valid_from=NOW - timedelta(days=1),
    )
    binding = build_provider_endpoint_run_binding(
        provider_endpoint_run_binding_id=f"security_master_binding_{suffix}",
        provider_run_id=run.provider_run_id,
        raw_object_refs=(raw.raw_object_id,),
        provider_id=run.provider_id,
        provider_endpoint_id=endpoint.provider_endpoint_id,
        endpoint_contract_version=endpoint.endpoint_contract_version,
        adapter_implementation_fingerprint_id=fingerprint.adapter_implementation_fingerprint_id,
        implementation_fingerprint=fingerprint.implementation_fingerprint,
        source_admission_receipt_id=receipt.source_admission_receipt_id,
        receipt_hash=receipt.receipt_hash,
        dataset_id=run.dataset_id,
        dataset_schema_version=run.dataset_schema_version,
        market=run.capability_market,
        request_fingerprint=run.request_fingerprint,
        observed_schema_hash=run.observed_schema_hash,
        actual_origin_redacted=run.actual_upstream,
        created_at=NOW,
    )
    return endpoint, fingerprint, receipt, binding


def _counts(database):
    names = (
        "provider_endpoint_definition",
        "adapter_implementation_fingerprint",
        "source_admission_receipt",
        "provider_endpoint_run_binding",
        "provider_endpoint_run_binding_raw_object",
    )
    with database.engine.connect() as connection:
        return {
            name: connection.execute(text(f"SELECT count(*) FROM {name}")).scalar_one()
            for name in names
        }


def _verifier():
    return ProviderEndpointAdmissionVerifier(
        evidence_hash_resolver=lambda receipt: receipt.evidence_hashes(),
        implementation_observation_resolver=AdapterImplementationObservation.from_fingerprint,
    )


def test_migration_repository_restart_and_formal_verifier_round_trip(
    isolated_postgres_database, tmp_path
):
    database = isolated_postgres_database
    upgrade_database(database.engine, LATEST)
    run, raw = _create_run(database, tmp_path)
    endpoint, fingerprint, receipt, binding = _package(run, raw)
    ProviderAdmissionService(database).publish_package(
        endpoint, fingerprint, receipt, binding
    )

    fresh = PostgresDatabase.from_settings(database.settings)
    try:
        with fresh.transaction() as session:
            repository = ProviderAdmissionRepository()
            assert repository.get_endpoint(
                session,
                endpoint.provider_endpoint_id,
                endpoint.provider_id,
                endpoint.endpoint_contract_version,
            ) == endpoint
            assert repository.get_fingerprint(
                session, fingerprint.adapter_implementation_fingerprint_id
            ) == fingerprint
            assert repository.get_receipt(
                session, receipt.source_admission_receipt_id
            ) == receipt
            assert repository.get_binding_by_run(session, run.provider_run_id) == binding
            assert _verifier().verify_formal_run(
                session,
                run.provider_run_id,
                target_market="CN",
                target_date=date(2026, 8, 31),
                cutoff_at=NOW,
            ) == binding
    finally:
        fresh.close()
    assert get_migration_status(database.engine).current_revision == LATEST


def test_atomic_package_failure_rolls_back_endpoint_receipt_binding_and_join(
    isolated_postgres_database, tmp_path
):
    database = isolated_postgres_database
    upgrade_database(database.engine, LATEST)
    run, raw = _create_run(database, tmp_path)
    endpoint, fingerprint, receipt, binding = _package(run, raw)

    class FailingRepository(ProviderAdmissionRepository):
        @classmethod
        def add_binding(cls, session, record):
            super().add_binding(session, record)
            raise RuntimeError("binding commit probe")

    with pytest.raises(RuntimeError, match="binding commit probe"):
        ProviderAdmissionService(database, FailingRepository()).publish_package(
            endpoint, fingerprint, receipt, binding
        )
    assert _counts(database) == {
        "provider_endpoint_definition": 0,
        "adapter_implementation_fingerprint": 0,
        "source_admission_receipt": 0,
        "provider_endpoint_run_binding": 0,
        "provider_endpoint_run_binding_raw_object": 0,
    }


def test_package_publication_reuses_exact_immutable_prerequisites_for_multiple_runs(
    isolated_postgres_database, tmp_path
):
    database = isolated_postgres_database
    upgrade_database(database.engine, LATEST)
    first_run, first_raw = _create_run(database, tmp_path, run_suffix="first")
    endpoint, fingerprint, receipt, first_binding = _package(first_run, first_raw)
    service = ProviderAdmissionService(database)
    assert service.publish_package(
        endpoint, fingerprint, receipt, first_binding
    ) == first_binding
    assert service.publish_package(
        endpoint, fingerprint, receipt, first_binding
    ) == first_binding

    second_run, second_raw = _create_run(database, tmp_path, run_suffix="second")
    second_binding = build_provider_endpoint_run_binding(
        **(
            first_binding.model_dump(mode="python", exclude={"binding_hash"})
            | {
                "provider_endpoint_run_binding_id": "security_master_binding_v2",
                "provider_run_id": second_run.provider_run_id,
                "raw_object_refs": (second_raw.raw_object_id,),
                "request_fingerprint": second_run.request_fingerprint,
                "observed_schema_hash": second_run.observed_schema_hash,
                "actual_origin_redacted": second_run.actual_upstream,
            }
        )
    )
    assert service.publish_package(
        endpoint, fingerprint, receipt, second_binding
    ) == second_binding
    assert _counts(database) == {
        "provider_endpoint_definition": 1,
        "adapter_implementation_fingerprint": 1,
        "source_admission_receipt": 1,
        "provider_endpoint_run_binding": 2,
        "provider_endpoint_run_binding_raw_object": 2,
    }
    with database.transaction() as session:
        assert ProviderAdmissionRepository.get_binding_by_run(
            session, second_run.provider_run_id
        ) == second_binding

    concurrent_run_a, concurrent_raw_a = _create_run(
        database, tmp_path, run_suffix="concurrent-a"
    )
    concurrent_endpoint, concurrent_fingerprint, concurrent_receipt, concurrent_binding_a = (
        _package(concurrent_run_a, concurrent_raw_a, suffix="concurrent")
    )
    concurrent_run_b, concurrent_raw_b = _create_run(
        database, tmp_path, run_suffix="concurrent-b"
    )
    concurrent_binding_b = build_provider_endpoint_run_binding(
        **(
            concurrent_binding_a.model_dump(mode="python", exclude={"binding_hash"})
            | {
                "provider_endpoint_run_binding_id": "security_master_binding_concurrent_b",
                "provider_run_id": concurrent_run_b.provider_run_id,
                "raw_object_refs": (concurrent_raw_b.raw_object_id,),
                "request_fingerprint": concurrent_run_b.request_fingerprint,
                "observed_schema_hash": concurrent_run_b.observed_schema_hash,
                "actual_origin_redacted": concurrent_run_b.actual_upstream,
            }
        )
    )
    insert_barrier = Barrier(2)

    class RacingRepository(ProviderAdmissionRepository):
        @staticmethod
        def add_endpoint(session, record):
            try:
                insert_barrier.wait(timeout=0.25)
            except BrokenBarrierError:
                pass
            ProviderAdmissionRepository.add_endpoint(session, record)

    concurrent_packages = (
        (
            concurrent_endpoint,
            concurrent_fingerprint,
            concurrent_receipt,
            concurrent_binding_a,
        ),
        (
            concurrent_endpoint,
            concurrent_fingerprint,
            concurrent_receipt,
            concurrent_binding_b,
        ),
    )
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(
                ProviderAdmissionService(database, RacingRepository()).publish_package,
                *package,
            )
            for package in concurrent_packages
        ]
        assert {future.result(timeout=10) for future in futures} == {
            concurrent_binding_a,
            concurrent_binding_b,
        }
    assert _counts(database) == {
        "provider_endpoint_definition": 2,
        "adapter_implementation_fingerprint": 2,
        "source_admission_receipt": 2,
        "provider_endpoint_run_binding": 4,
        "provider_endpoint_run_binding_raw_object": 4,
    }

    conflicting_endpoint = build_provider_endpoint_definition(
        **(
            endpoint.model_dump(mode="python", exclude={"definition_hash"})
            | {"retry_semantics": "conflicting immutable retry semantics"}
        )
    )
    with pytest.raises(ValueError, match="EndpointDefinition identity conflicts"):
        service.publish_package(
            conflicting_endpoint, fingerprint, receipt, second_binding
        )
    assert _counts(database) == {
        "provider_endpoint_definition": 2,
        "adapter_implementation_fingerprint": 2,
        "source_admission_receipt": 2,
        "provider_endpoint_run_binding": 4,
        "provider_endpoint_run_binding_raw_object": 4,
    }


def test_repository_and_database_constraints_reject_mismatched_or_duplicate_lineage(
    isolated_postgres_database, tmp_path
):
    database = isolated_postgres_database
    upgrade_database(database.engine, LATEST)
    run, raw = _create_run(database, tmp_path)
    endpoint, fingerprint, receipt, binding = _package(run, raw)
    ProviderAdmissionService(database).publish_package(endpoint, fingerprint, receipt, binding)
    before = _counts(database)

    duplicate = build_provider_endpoint_run_binding(
        **(
            binding.model_dump(mode="python", exclude={"binding_hash"})
            | {"provider_endpoint_run_binding_id": "security_master_binding_duplicate"}
        )
    )
    with pytest.raises(PlatformDatabaseError):
        with database.transaction() as session:
            ProviderAdmissionRepository.add_binding(session, duplicate)
    assert _counts(database) == before

    missing_raw = build_provider_endpoint_run_binding(
        **(
            binding.model_dump(mode="python", exclude={"binding_hash"})
            | {"raw_object_refs": ("raw_019dbd74-2a00-7000-8000-999999999999",)}
        )
    )
    with pytest.raises(ValueError, match="every ProviderRun RawObject"):
        with database.transaction() as session:
            ProviderAdmissionRepository.add_binding(session, missing_raw)
    assert _counts(database) == before

    with pytest.raises(PlatformDatabaseError):
        with database.transaction() as session:
            session.execute(
                provider_endpoint_run_binding_raw_object.insert().values(
                    provider_endpoint_run_binding_id=binding.provider_endpoint_run_binding_id,
                    raw_object_id="raw_019dbd74-2a00-7000-8000-999999999999",
                    raw_order=1,
                )
            )
    assert _counts(database) == before


def test_real_repository_formal_gate_rejects_missing_and_non_pit_receipt(
    isolated_postgres_database, tmp_path
):
    database = isolated_postgres_database
    upgrade_database(database.engine, LATEST)
    run, raw = _create_run(database, tmp_path)
    with database.transaction() as session:
        with pytest.raises(ProviderAdmissionGateError) as captured:
            _verifier().verify_formal_run(
                session,
                run.provider_run_id,
                target_market="CN",
                target_date=date(2026, 8, 31),
                cutoff_at=NOW,
            )
    assert captured.value.error_code == "SOURCE_ADMISSION_BINDING_MISSING"

    endpoint, fingerprint, receipt, binding = _package(
        run, raw, admission_level="VERSIONED_ARCHIVE"
    )
    ProviderAdmissionService(database).publish_package(endpoint, fingerprint, receipt, binding)
    with database.transaction() as session:
        with pytest.raises(ProviderAdmissionGateError) as captured:
            _verifier().verify_formal_run(
                session,
                run.provider_run_id,
                target_market="CN",
                target_date=date(2026, 8, 31),
                cutoff_at=NOW,
            )
    assert captured.value.error_code == "SOURCE_ADMISSION_RECEIPT_NOT_PIT_CERTIFIED"


def test_formal_gate_rejects_implementation_and_internal_source_switch_drift(
    isolated_postgres_database, tmp_path
):
    database = isolated_postgres_database
    upgrade_database(database.engine, LATEST)
    run, raw = _create_run(database, tmp_path)
    endpoint, fingerprint, receipt, binding = _package(run, raw)
    ProviderAdmissionService(database).publish_package(endpoint, fingerprint, receipt, binding)

    changed_observation = replace(
        AdapterImplementationObservation.from_fingerprint(fingerprint),
        source_file_sha256=_hash("changed-file"),
    )
    verifier = ProviderEndpointAdmissionVerifier(
        evidence_hash_resolver=lambda current: current.evidence_hashes(),
        implementation_observation_resolver=lambda _current: changed_observation,
    )
    with database.transaction() as session:
        with pytest.raises(ProviderAdmissionGateError) as captured:
            verifier.verify_formal_run(
                session,
                run.provider_run_id,
                target_market="CN",
                target_date=date(2026, 8, 31),
                cutoff_at=NOW,
            )
    assert captured.value.error_code == "SOURCE_ADMISSION_IMPLEMENTATION_MISMATCH"

    with database.engine.begin() as connection:
        connection.execute(
            update(provider_run)
            .where(provider_run.c.provider_run_id == run.provider_run_id)
            .values(
                actual_upstream="fixture.financial_api",
                source_route_evidence=synthetic_source_route(
                    run.model_copy(update={"actual_upstream": "fixture.financial_api"})
                ).model_dump(mode="json"),
            )
        )
        connection.execute(
            update(raw_object)
            .where(raw_object.c.raw_object_id == raw.raw_object_id)
            .values(actual_upstream="fixture.financial_api")
        )
    with database.transaction() as session:
        with pytest.raises(ProviderAdmissionGateError) as captured:
            _verifier().verify_formal_run(
                session,
                run.provider_run_id,
                target_market="CN",
                target_date=date(2026, 8, 31),
                cutoff_at=NOW,
            )
    assert captured.value.error_code == "SOURCE_ADMISSION_ENDPOINT_MISMATCH"


def test_real_repository_formal_gate_rejects_source_evidence_hash_drift(
    isolated_postgres_database, tmp_path
):
    database = isolated_postgres_database
    upgrade_database(database.engine, LATEST)
    run, raw = _create_run(database, tmp_path)
    endpoint, fingerprint, receipt, binding = _package(run, raw)
    ProviderAdmissionService(database).publish_package(endpoint, fingerprint, receipt, binding)
    drifted = ProviderEndpointAdmissionVerifier(
        evidence_hash_resolver=lambda current: current.evidence_hashes()
        | {"coverage_manifest_hash": _hash("drifted-coverage")},
        implementation_observation_resolver=AdapterImplementationObservation.from_fingerprint,
    )
    with database.transaction() as session:
        with pytest.raises(ProviderAdmissionGateError) as captured:
            drifted.verify_formal_run(
                session,
                run.provider_run_id,
                target_market="CN",
                target_date=date(2026, 8, 31),
                cutoff_at=NOW,
            )
    assert captured.value.error_code == "SOURCE_ADMISSION_EVIDENCE_HASH_MISMATCH"


def test_downgrade_refuses_records_before_drop_and_empty_database_is_reversible(
    isolated_postgres_database, tmp_path
):
    database = isolated_postgres_database
    upgrade_database(database.engine, LATEST)
    run, raw = _create_run(database, tmp_path)
    ProviderAdmissionService(database).publish_package(*_package(run, raw))
    before = _counts(database)
    statements: list[str] = []

    def record_statement(_connection, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement)

    event.listen(database.engine, "before_cursor_execute", record_statement)
    try:
        with pytest.raises(PlatformDatabaseError) as captured:
            downgrade_database(database.engine, PREVIOUS)
    finally:
        event.remove(database.engine, "before_cursor_execute", record_statement)
    assert "immutable admission records exist" in str(captured.value.__cause__)
    assert not any(
        token in statement.upper() for statement in statements for token in ("DROP TABLE", "ALTER TABLE")
    )
    assert get_migration_status(database.engine).current_revision == LATEST
    assert _counts(database) == before

    with database.engine.begin() as connection:
        connection.execute(provider_endpoint_run_binding_raw_object.delete())
        connection.execute(provider_endpoint_run_binding.delete())
        connection.execute(text("DELETE FROM source_admission_receipt"))
        connection.execute(text("DELETE FROM adapter_implementation_fingerprint"))
        connection.execute(text("DELETE FROM provider_endpoint_definition"))
    downgrade_database(database.engine, PREVIOUS)
    from alembic.runtime.migration import MigrationContext
    with database.engine.connect() as connection:
        assert set(MigrationContext.configure(connection).get_current_heads()) == {
            "0014_wp0207_source_binding", PREVIOUS,
        }
    # 只回退 WP-0303 分支的空 Admission 表，不删除 main 的来源列和证据。
    assert "source_route_evidence" in {
        column["name"] for column in inspect(database.engine).get_columns("provider_run")
    }
    assert "provider_endpoint_definition" not in inspect(database.engine).get_table_names()
    upgrade_database(database.engine, LATEST)
    assert get_migration_status(database.engine).current_revision == LATEST
