from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic.json_schema import models_json_schema

from .artifact import (
    ArtifactManifest,
    ArtifactPublishResult,
    ArtifactRecord,
    ArtifactRecoveryResult,
    OrphanDryRunResult,
)
from .asset_identity import AssetResolutionCandidate, AssetResolutionRequest, AssetResolutionResult
from .task import (
    TaskAttemptRecord,
    TaskCancelRequest,
    TaskCheckpointRecord,
    TaskCreateRequest,
    TaskDetails,
    TaskEventRecord,
    TaskLease,
    TaskListQuery,
    TaskRecord,
    TaskRetryRequest,
    TaskStateEventRecord,
)
from .provider import DatasetDefinition, ProviderCapability, ProviderDefinition, ProviderPolicy, ProviderSettingsProjection
from .raw_ingestion import ProviderRun, RawIngestionPublishResult, RawIngestionQuarantine, RawIngestionTaskRequirements, RawObject
from .api import (
    PLATFORM_API_SCHEMA_VERSION,
    PlatformAPIError,
    PlatformErrorEnvelope,
    PlatformListEnvelope,
    PlatformPage,
    PlatformResponseMeta,
    PlatformSuccessEnvelope,
)


REPO_ROOT = Path(__file__).resolve().parents[3]
FRONTEND_TYPE_EXPORT = REPO_ROOT / "apps" / "dsa-web" / "src" / "types" / "generated" / "platform-api.ts"
_API_MODELS = (
    DatasetDefinition,
    ProviderCapability,
    ProviderDefinition,
    ProviderPolicy,
    ProviderSettingsProjection,
    ProviderRun,
    RawObject,
    RawIngestionQuarantine,
    RawIngestionTaskRequirements,
    RawIngestionPublishResult,
    ArtifactManifest,
    ArtifactPublishResult,
    ArtifactRecord,
    ArtifactRecoveryResult,
    OrphanDryRunResult,
    AssetResolutionCandidate,
    AssetResolutionRequest,
    AssetResolutionResult,
    TaskAttemptRecord,
    TaskCancelRequest,
    TaskCheckpointRecord,
    TaskCreateRequest,
    TaskDetails,
    TaskEventRecord,
    TaskLease,
    TaskListQuery,
    TaskRecord,
    TaskRetryRequest,
    TaskStateEventRecord,
    PlatformAPIError,
    PlatformErrorEnvelope,
    PlatformListEnvelope,
    PlatformPage,
    PlatformResponseMeta,
    PlatformSuccessEnvelope,
)


def _json_text(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def render_platform_openapi() -> dict[str, Any]:
    """Render the C-010 component catalog without inventing runtime endpoints."""

    _, combined = models_json_schema(
        [(model, "validation") for model in _API_MODELS],
        ref_template="#/components/schemas/{model}",
    )
    schemas = combined.get("$defs", {})
    return {
        "components": {"schemas": dict(sorted(schemas.items()))},
        "info": {
            "description": (
                "C-002/C-003/C-007/C-010/C-011 public platform components. Only explicitly implemented "
                "runtime resources appear under /api/platform/v1; Legacy /api/v1 responses are not wrapped."
            ),
            "title": "Visory Platform API Contracts",
            "version": PLATFORM_API_SCHEMA_VERSION,
        },
        "openapi": "3.1.0",
        "paths": {
            "/api/platform/v1/provider-registry": {"get": {"operationId": "getProviderRegistry", "responses": {"200": {"description": "Dataset and provider registry projection", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/PlatformSuccessEnvelope"}}}}}, "summary": "Read dataset and provider registry"}},
            "/api/platform/v1/providers": {"get": {"operationId": "listProviders", "responses": {"200": {"description": "Registered providers", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/PlatformSuccessEnvelope"}}}}}, "summary": "List registered providers"}},
            "/api/platform/v1/datasets": {"get": {"operationId": "listDatasets", "responses": {"200": {"description": "Registered datasets", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/PlatformSuccessEnvelope"}}}}}, "summary": "List registered datasets"}},
            "/api/platform/v1/asset-resolutions": {
                "post": {
                    "operationId": "resolveAssetIdentity",
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/AssetResolutionRequest"}
                            }
                        },
                        "required": True,
                    },
                    "responses": {
                        "200": {
                            "description": "C-002 resolution result wrapped by C-010",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/PlatformSuccessEnvelope"}
                                }
                            },
                        },
                        "400": {
                            "description": "Invalid request",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/PlatformErrorEnvelope"}
                                }
                            },
                        },
                        "503": {
                            "description": "Identity repository unavailable",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/PlatformErrorEnvelope"}
                                }
                            },
                        },
                    },
                    "summary": "Resolve an asset identity without guessing",
                }
            },
            "/api/platform/v1/tasks": {
                "get": {
                    "operationId": "listTasks",
                    "parameters": [
                        {"name": "tab", "in": "query", "schema": {"type": "string", "enum": ["active", "blocked", "failed", "history"]}},
                        {"name": "task_state", "in": "query", "schema": {"$ref": "#/components/schemas/TaskState"}},
                        {"name": "task_type", "in": "query", "schema": {"type": "string"}},
                        {"name": "priority_class", "in": "query", "schema": {"$ref": "#/components/schemas/PriorityClass"}},
                        {"name": "requested_by", "in": "query", "schema": {"type": "string"}},
                        {"name": "created_from", "in": "query", "schema": {"type": "string", "format": "date-time"}},
                        {"name": "created_to", "in": "query", "schema": {"type": "string", "format": "date-time"}},
                        {"name": "resource_id", "in": "query", "schema": {"type": "string"}},
                        {"name": "cursor", "in": "query", "schema": {"type": "string"}},
                        {"name": "limit", "in": "query", "schema": {"type": "integer", "minimum": 1, "maximum": 100, "default": 50}},
                    ],
                    "responses": {"200": {"description": "Task list", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/PlatformListEnvelope"}}}}},
                    "summary": "List durable platform tasks",
                },
                "post": {
                    "operationId": "createTask",
                    "requestBody": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/TaskCreateRequest"}}}, "required": True},
                    "parameters": [{"name": "Idempotency-Key", "in": "header", "required": True, "schema": {"type": "string"}}],
                    "responses": {
                        "200": {"description": "Task created or idempotently replayed", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/PlatformSuccessEnvelope"}}}},
                        "400": {"description": "Missing or invalid idempotency key", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/PlatformErrorEnvelope"}}}},
                        "409": {"description": "Idempotency conflict", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/PlatformErrorEnvelope"}}}},
                    },
                    "summary": "Create a durable platform task",
                }
            },
            "/api/platform/v1/tasks/events": {
                "get": {
                    "operationId": "streamTaskEvents",
                    "parameters": [{"name": "after_event_id", "in": "query", "schema": {"type": "string"}}, {"name": "Last-Event-ID", "in": "header", "schema": {"type": "string"}}],
                    "responses": {"200": {"description": "Resumable task event stream", "content": {"text/event-stream": {"schema": {"type": "string"}}}}},
                    "summary": "Stream task state events",
                }
            },
            "/api/platform/v1/tasks/{task_id}/events": {
                "get": {
                    "operationId": "streamTaskEventsForTask",
                    "parameters": [{"name": "task_id", "in": "path", "required": True, "schema": {"type": "string"}}, {"name": "after_event_id", "in": "query", "schema": {"type": "string"}}, {"name": "Last-Event-ID", "in": "header", "schema": {"type": "string"}}],
                    "responses": {"200": {"description": "Resumable task event stream", "content": {"text/event-stream": {"schema": {"type": "string"}}}}},
                    "summary": "Stream state events for one task",
                }
            },
            "/api/platform/v1/tasks/{task_id}": {
                "get": {
                    "operationId": "getTask",
                    "parameters": [{"name": "task_id", "in": "path", "required": True, "schema": {"type": "string"}}],
                    "responses": {"200": {"description": "Task details", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/PlatformSuccessEnvelope"}}}}, "404": {"description": "Task not found", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/PlatformErrorEnvelope"}}}}},
                    "summary": "Get a durable platform task",
                }
            },
            "/api/platform/v1/tasks/{task_id}/cancellations": {
                "post": {
                    "operationId": "requestTaskCancellation",
                    "parameters": [{"name": "task_id", "in": "path", "required": True, "schema": {"type": "string"}}],
                    "requestBody": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/TaskCancelRequest"}}}, "required": True},
                    "responses": {"200": {"description": "Cancellation requested", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/PlatformSuccessEnvelope"}}}}, "409": {"description": "Cancellation rejected", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/PlatformErrorEnvelope"}}}}},
                    "summary": "Request task cancellation",
                }
            },
            "/api/platform/v1/tasks/{task_id}/retries": {
                "post": {
                    "operationId": "requestTaskRetry",
                    "parameters": [{"name": "task_id", "in": "path", "required": True, "schema": {"type": "string"}}],
                    "requestBody": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/TaskRetryRequest"}}}, "required": True},
                    "responses": {"200": {"description": "Retry requested", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/PlatformSuccessEnvelope"}}}}, "409": {"description": "Retry rejected", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/PlatformErrorEnvelope"}}}}},
                    "summary": "Request task retry",
                }
            },
        },
    }


def render_platform_openapi_json() -> str:
    return _json_text(render_platform_openapi())


def _ts_literal(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, (int, float)):
        return str(value)
    return "unknown"


def _ts_type(schema: dict[str, Any]) -> str:
    reference = schema.get("$ref")
    if isinstance(reference, str):
        return reference.rsplit("/", 1)[-1]

    if "const" in schema:
        return _ts_literal(schema["const"])

    enum_values = schema.get("enum")
    if isinstance(enum_values, list) and enum_values:
        return " | ".join(_ts_literal(value) for value in enum_values)

    alternatives = schema.get("anyOf")
    if isinstance(alternatives, list):
        rendered = []
        for option in alternatives:
            option_type = _ts_type(option)
            if option_type not in rendered:
                rendered.append(option_type)
        return " | ".join(rendered)

    schema_type = schema.get("type")
    if schema_type == "string":
        return "string"
    if schema_type in {"integer", "number"}:
        return "number"
    if schema_type == "boolean":
        return "boolean"
    if schema_type == "null":
        return "null"
    if schema_type == "array":
        item_type = _ts_type(schema.get("items", {}))
        return f"ReadonlyArray<{item_type}>"
    if schema_type == "object":
        properties = schema.get("properties")
        if isinstance(properties, dict) and properties:
            required = set(schema.get("required", []))
            rows = ["{"]
            for name in sorted(properties):
                optional = "" if name in required else "?"
                rows.append(f"  readonly {name}{optional}: {_ts_type(properties[name])};")
            rows.append("}")
            return "\n".join(rows)
        if schema.get("additionalProperties") is True or isinstance(schema.get("additionalProperties"), dict):
            value_type = (
                _ts_type(schema["additionalProperties"])
                if isinstance(schema.get("additionalProperties"), dict)
                else "unknown"
            )
            return f"Readonly<Record<string, {value_type}>>"
        return "Readonly<Record<string, never>>"
    return "unknown"


def render_frontend_types() -> str:
    """Generate strict TypeScript declarations from the rendered OpenAPI components."""

    schemas = render_platform_openapi()["components"]["schemas"]
    lines = [
        "// Generated by scripts/export_platform_contracts.py. DO NOT EDIT.",
        "// Source: src/schemas/platform public C-002/C-003/C-010 models (version 1.0.0).",
        "",
    ]
    for name in sorted(schemas):
        schema = schemas[name]
        description = str(schema.get("description", "")).strip()
        if description:
            lines.append(f"/** {description} */")
        if schema.get("type") == "object" and isinstance(schema.get("properties"), dict):
            required = set(schema.get("required", []))
            lines.append(f"export interface {name} {{")
            for property_name in sorted(schema["properties"]):
                optional = "" if property_name in required else "?"
                property_type = _ts_type(schema["properties"][property_name])
                lines.append(f"  readonly {property_name}{optional}: {property_type};")
            lines.append("}")
        else:
            lines.append(f"export type {name} = {_ts_type(schema)};")
        lines.append("")
    return "\n".join(lines)


def write_frontend_type_export(path: Path = FRONTEND_TYPE_EXPORT) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_frontend_types(), encoding="utf-8", newline="\n")
    return path


def check_frontend_type_export(path: Path = FRONTEND_TYPE_EXPORT) -> bool:
    return not path.is_file() or path.read_bytes() != render_frontend_types().encode("utf-8")
