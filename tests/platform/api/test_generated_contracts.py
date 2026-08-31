from __future__ import annotations

import json
from pathlib import Path

from src.schemas.platform.api_export import (
    FRONTEND_TYPE_EXPORT,
    check_frontend_type_export,
    render_frontend_types,
    render_platform_openapi,
    render_platform_openapi_json,
    write_frontend_type_export,
)
from src.schemas.platform.export import check_exported_contracts, render_contract_exports


REPO_ROOT = Path(__file__).resolve().parents[3]
SCHEMA_EXPORT_ROOT = REPO_ROOT / "schemas" / "platform"


def test_c010_openapi_contains_examples_and_stable_components() -> None:
    spec = render_platform_openapi()

    assert spec["openapi"] == "3.1.0"
    assert spec["info"]["version"] == "1.0.0"
    assert set(spec["paths"]) == {
        "/api/platform/v1/asset-resolutions",
        "/api/platform/v1/provider-registry",
        "/api/platform/v1/providers",
        "/api/platform/v1/datasets",
        "/api/platform/v1/tasks",
        "/api/platform/v1/tasks/events",
        "/api/platform/v1/tasks/{task_id}",
        "/api/platform/v1/tasks/{task_id}/events",
        "/api/platform/v1/tasks/{task_id}/cancellations",
        "/api/platform/v1/tasks/{task_id}/retries",
    }
    schemas = spec["components"]["schemas"]
    assert set(schemas) == {
        "AliasType",
        "ArtifactIntegrityState",
        "ArtifactManifest",
        "ArtifactPublicationState",
        "ArtifactPublishResult",
        "ArtifactRecord",
        "ArtifactRecoveryResult",
        "ArtifactVisibility",
        "AssetResolutionCandidate",
        "AttemptOutcome",
        "AssetResolutionRequest",
        "AssetResolutionResult",
        "AssetType",
        "IdentityStatus",
        "OrphanAction",
        "OrphanCandidate",
        "OrphanDryRunResult",
        "ProviderCapability",
        "ProviderCapabilityStatus",
        "ProviderDefinition",
        "ProviderKind",
        "ProviderMergeMode",
        "ProviderPolicy",
        "ProviderRun",
        "ProviderRunOutcome",
        "QuarantineStatus",
        "RawCompression",
        "RawIngestionPublishResult",
        "RawIngestionQuarantine",
        "RawIngestionTaskRequirements",
        "RawObject",
        "RawSchemaDriftClassification",
        "ProviderSettingsProjection",
        "ProviderSettingsProvider",
        "DatasetDefinition",
        "PlatformAPIError",
        "PlatformErrorEnvelope",
        "PlatformListEnvelope",
        "PlatformPage",
        "PlatformResponseMeta",
        "PlatformSuccessEnvelope",
        "ResolutionStatus",
        "ResourceRef",
        "ResourceType",
        "RetentionClass",
        "StorageBackend",
        "StorageNamespace",
        "StorageRef",
        "PriorityClass",
        "TaskAttemptRecord",
        "TaskCancelRequest",
        "TaskCheckpointRecord",
        "TaskCreateRequest",
        "TaskDetails",
        "TaskEventRecord",
        "TaskListQuery",
        "TaskLease",
        "TaskRecord",
        "TaskRetryRequest",
        "TaskState",
        "TaskStateEventRecord",
    }
    assert schemas["PlatformSuccessEnvelope"]["examples"]
    assert schemas["PlatformErrorEnvelope"]["examples"]
    assert schemas["PlatformListEnvelope"]["examples"]


def test_openapi_and_frontend_types_are_byte_deterministic() -> None:
    openapi_json = render_platform_openapi_json()
    frontend_types = render_frontend_types()

    assert openapi_json == render_platform_openapi_json()
    assert frontend_types == render_frontend_types()
    assert openapi_json.endswith("\n")
    assert frontend_types.endswith("\n")
    assert "VISORY_RUNTIME_ROOT" not in openapi_json
    assert "runtime_root" not in openapi_json
    assert "VISORY_RUNTIME_ROOT" not in frontend_types
    assert "runtime_root" not in frontend_types


def test_checked_in_c010_openapi_and_frontend_types_match_source_models() -> None:
    assert "C-010.openapi.json" in render_contract_exports()
    assert check_exported_contracts(SCHEMA_EXPORT_ROOT) == []
    assert check_frontend_type_export(FRONTEND_TYPE_EXPORT) is False


def test_frontend_type_drift_is_detected(tmp_path: Path) -> None:
    target = tmp_path / "platform-api.ts"
    write_frontend_type_export(target)
    assert check_frontend_type_export(target) is False

    target.write_text(target.read_text(encoding="utf-8") + "// manual drift\n", encoding="utf-8")
    assert check_frontend_type_export(target) is True


def test_generated_frontend_types_are_strict_and_cover_c010_fields() -> None:
    generated = render_frontend_types()

    assert "DO NOT EDIT" in generated
    assert "export interface PlatformResponseMeta" in generated
    assert "readonly request_id: string;" in generated
    assert 'readonly schema_version: "1.0.0";' in generated
    assert "readonly generated_at: string;" in generated
    assert "readonly data_snapshot_id: string | null;" in generated
    assert "readonly warnings: ReadonlyArray<string>;" in generated
    assert "export interface PlatformPage" in generated
    assert "export interface PlatformErrorEnvelope" in generated
    assert "export interface ArtifactRecord" in generated
    assert "export interface ArtifactManifest" in generated
    assert "export interface ArtifactPublishResult" in generated
    assert "export interface ArtifactRecoveryResult" in generated
    assert "export interface OrphanDryRunResult" in generated
    assert "export interface ProviderRun" in generated
    assert "export interface RawObject" in generated
    assert "export interface RawIngestionQuarantine" in generated
    assert "export interface TaskRecord" in generated
    assert "export interface TaskAttemptRecord" in generated
    assert "export interface TaskCheckpointRecord" in generated
    assert ": any" not in generated
    assert "<any>" not in generated


def test_exported_openapi_json_matches_rendered_structure() -> None:
    exported = json.loads((SCHEMA_EXPORT_ROOT / "C-010.openapi.json").read_text(encoding="utf-8"))
    assert exported == render_platform_openapi()
