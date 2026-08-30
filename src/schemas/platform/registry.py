from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .asset_identity import (
    AssetAlias,
    AssetIdentityRecord,
    AssetResolutionResult,
    IdentityQuarantineRecord,
)
from .base import PlatformContractModel
from .hashing import DEFAULT_HASH_PROFILE, HashProfile
from .identity import EntityIdentity
from .resources import ResourceRef
from .storage import StorageRef
from .temporal import AvailabilityMetadata, PointInTimeWindow
from .versioning import PublicationMetadata, RevisionMetadata, TaskStateMetadata
from .hashing import ContentHashValue


_FORBIDDEN_PROPERTY_NAMES = frozenset({"status", "version", "date", "timestamp", "hash"})


@dataclass(frozen=True, slots=True)
class ContractRegistration:
    contract_id: str
    owner_module: str
    producer: str
    consumers: tuple[str, ...]
    schema_model: type[PlatformContractModel]
    schema_version: str
    business_key: str
    resource_id_field: str | None
    time_semantics: tuple[str, ...]
    version_semantics: tuple[str, ...]
    quality_semantics: tuple[str, ...]
    lineage_fields: tuple[str, ...]
    storage_profile: str
    retention_class: str
    compatibility: str
    golden_payloads: tuple[str, ...]
    hash_profile: HashProfile = DEFAULT_HASH_PROFILE

    @property
    def json_schema(self) -> dict[str, object]:
        return self.schema_model.model_json_schema()


class ContractRegistry:
    def __init__(self, registrations: Iterable[ContractRegistration]) -> None:
        items = tuple(registrations)
        self._registrations = {item.contract_id: item for item in items}
        if len(self._registrations) != len(items):
            raise ValueError("contract_id values must be unique")

    def get(self, contract_id: str) -> ContractRegistration:
        return self._registrations[contract_id]

    def list(self) -> tuple[ContractRegistration, ...]:
        return tuple(self._registrations[key] for key in sorted(self._registrations))


def _golden(*paths: str) -> tuple[str, ...]:
    return tuple(f"tests/golden/platform/contracts/{path}" for path in paths)


PLATFORM_CONTRACTS = ContractRegistry(
    (
        ContractRegistration(
            contract_id="C-001/EntityIdentity",
            owner_module="src.schemas.platform.identity",
            producer="Identity Resolver",
            consumers=("all asset modules",),
            schema_model=EntityIdentity,
            schema_version="1.0.0",
            business_key="entity_key",
            resource_id_field=None,
            time_semantics=(),
            version_semantics=("identity schema_version",),
            quality_semantics=("identity conflicts are rejected",),
            lineage_fields=(),
            storage_profile="control-plane projection; no physical path",
            retention_class="PINNED",
            compatibility="additive fields require optional defaults; breaking identity changes require a major schema version",
            golden_payloads=_golden("success/entity-identity.json", "rejected/entity-key-mismatch.json"),
        ),
        ContractRegistration(
            contract_id="C-001/PointInTimeWindow",
            owner_module="src.schemas.platform.temporal",
            producer="platform computation boundary",
            consumers=("snapshot", "feature", "review", "research", "backtest"),
            schema_model=PointInTimeWindow,
            schema_version="1.0.0",
            business_key="available_at + cutoff_at",
            resource_id_field=None,
            time_semantics=("available_at", "cutoff_at"),
            version_semantics=(),
            quality_semantics=("available_at must not exceed cutoff_at",),
            lineage_fields=(),
            storage_profile="embedded JSON object",
            retention_class="AUDIT",
            compatibility="timestamps remain RFC 3339 timezone-aware values",
            golden_payloads=_golden("success/point-in-time-window.json", "rejected/naive-timestamp.json"),
        ),
        ContractRegistration(
            contract_id="C-001/AvailabilityMetadata",
            owner_module="src.schemas.platform.temporal",
            producer="provider and normalization workers",
            consumers=("snapshot builder", "PIT consumers"),
            schema_model=AvailabilityMetadata,
            schema_version="1.0.0",
            business_key="source fact identity + available_at",
            resource_id_field=None,
            time_semantics=("event_time", "source_published_at", "observed_at", "ingested_at", "available_at"),
            version_semantics=("availability_policy_version",),
            quality_semantics=("historical backfill must preserve provable PIT availability",),
            lineage_fields=("availability_basis",),
            storage_profile="embedded control metadata",
            retention_class="PINNED",
            compatibility="new availability bases require a schema minor or major version and explicit policy",
            golden_payloads=_golden(
                "success/availability-metadata.json",
                "rejected/historical-backfill-fake-availability.json",
            ),
        ),
        ContractRegistration(
            contract_id="C-001/RevisionMetadata",
            owner_module="src.schemas.platform.versioning",
            producer="resource owner module",
            consumers=("all immutable resource consumers",),
            schema_model=RevisionMetadata,
            schema_version="1.0.0",
            business_key="resource business identity + revision",
            resource_id_field=None,
            time_semantics=(),
            version_semantics=("schema_version", "definition_version", "policy_version", "revision", "revision_kind"),
            quality_semantics=("Correction requires a direct supersedes relationship",),
            lineage_fields=("supersedes_id",),
            storage_profile="embedded control metadata",
            retention_class="PINNED",
            compatibility="old revisions remain immutable and addressable",
            golden_payloads=_golden(
                "success/revision-metadata.json",
                "correction/revision-correction.json",
                "rejected/correction-without-supersedes.json",
                "rejected/empty-not-applicable-field.json",
                "rejected/revision-zero.json",
            ),
        ),
        ContractRegistration(
            contract_id="C-001/PublicationMetadata",
            owner_module="src.schemas.platform.versioning",
            producer="resource publication gate",
            consumers=("published resource consumers",),
            schema_model=PublicationMetadata,
            schema_version="1.0.0",
            business_key="published resource id",
            resource_id_field=None,
            time_semantics=(),
            version_semantics=(),
            quality_semantics=("publication_status", "quality_status", "certified_capabilities"),
            lineage_fields=(),
            storage_profile="embedded control metadata",
            retention_class="AUDIT",
            compatibility="CORRECTION is represented only by revision_kind",
            golden_payloads=_golden("success/publication-metadata.json", "rejected/publication-correction.json"),
        ),
        ContractRegistration(
            contract_id="C-001/TaskStateMetadata",
            owner_module="src.schemas.platform.versioning",
            producer="task control plane",
            consumers=("scheduler", "worker", "operations"),
            schema_model=TaskStateMetadata,
            schema_version="1.0.0",
            business_key="task_id",
            resource_id_field=None,
            time_semantics=(),
            version_semantics=(),
            quality_semantics=("task_state", "blocked_reason_code", "failure_code"),
            lineage_fields=(),
            storage_profile="embedded task control metadata",
            retention_class="AUDIT",
            compatibility="domain phases remain separate from task_state",
            golden_payloads=_golden(
                "success/task-state-metadata.json",
                "rejected/task-phase-as-state.json",
                "rejected/failed-task-without-code.json",
            ),
        ),
        ContractRegistration(
            contract_id="C-001/ContentHashValue",
            owner_module="src.schemas.platform.hashing",
            producer="all immutable resource producers",
            consumers=("contract validators", "artifact integrity checks"),
            schema_model=ContentHashValue,
            schema_version="1.0.0",
            business_key="content_hash",
            resource_id_field=None,
            time_semantics=(),
            version_semantics=("hash_profile.profile_id",),
            quality_semantics=("sha256 lowercase canonical digest",),
            lineage_fields=("content_hash",),
            storage_profile="embedded JSON value",
            retention_class="PINNED",
            compatibility="hash profile changes require a versioned profile and schema review",
            golden_payloads=_golden("success/content-hash-value.json", "rejected/invalid-content-hash.json"),
        ),
        ContractRegistration(
            contract_id="C-002/AssetIdentityRecord",
            owner_module="src.schemas.platform.asset_identity",
            producer="Identity Registry",
            consumers=("all asset modules",),
            schema_model=AssetIdentityRecord,
            schema_version="1.0.0",
            business_key="entity_key",
            resource_id_field=None,
            time_semantics=("valid_from", "valid_to", "list_date", "delist_date", "created_at"),
            version_semantics=("schema_version",),
            quality_semantics=("identity_status", "identity conflicts enter quarantine"),
            lineage_fields=("entity_key",),
            storage_profile="PostgreSQL asset_identity",
            retention_class="PINNED",
            compatibility="renames, ST and suspension never replace entity_key; delisted identities remain addressable",
            golden_payloads=_golden(
                "success/asset-identity-record.json",
                "rejected/asset-identity-mismatch.json",
            ),
        ),
        ContractRegistration(
            contract_id="C-002/AssetAlias",
            owner_module="src.schemas.platform.asset_identity",
            producer="Identity Import and Resolver",
            consumers=("provider adapters", "search", "stock routes"),
            schema_model=AssetAlias,
            schema_version="1.0.0",
            business_key="namespace + normalized_value + validity + revision",
            resource_id_field=None,
            time_semantics=("valid_from", "valid_to", "available_at", "created_at"),
            version_semantics=("revision",),
            quality_semantics=("verification_status", "overlapping verified aliases are quarantined"),
            lineage_fields=("source_provider", "actual_upstream"),
            storage_profile="PostgreSQL asset_alias",
            retention_class="PINNED",
            compatibility="provider namespaces and right-open validity remain mandatory",
            golden_payloads=_golden("success/asset-alias.json"),
        ),
        ContractRegistration(
            contract_id="C-002/AssetResolutionResult",
            owner_module="src.schemas.platform.asset_identity",
            producer="Asset Resolver",
            consumers=("platform API", "legacy adapters", "provider adapters"),
            schema_model=AssetResolutionResult,
            schema_version="1.0.0",
            business_key="input namespace + normalized input + resolver version",
            resource_id_field=None,
            time_semantics=("resolved_at",),
            version_semantics=("resolver_version",),
            quality_semantics=("resolution_status", "reason_codes"),
            lineage_fields=("candidates",),
            storage_profile="response object; not persisted as a second identity source",
            retention_class="AUDIT",
            compatibility="resolution statuses are closed and machine-readable",
            golden_payloads=_golden("success/asset-resolution-result.json"),
        ),
        ContractRegistration(
            contract_id="C-002/IdentityQuarantineRecord",
            owner_module="src.schemas.platform.asset_identity",
            producer="Identity Registry",
            consumers=("identity operations",),
            schema_model=IdentityQuarantineRecord,
            schema_version="1.0.0",
            business_key="quarantine_id",
            resource_id_field=None,
            time_semantics=("created_at",),
            version_semantics=("revision",),
            quality_semantics=("quarantine_status", "reason_code"),
            lineage_fields=("source_provider", "actual_upstream", "conflicting_entity_keys"),
            storage_profile="PostgreSQL identity_quarantine",
            retention_class="QUARANTINE",
            compatibility="conflict records are append-only evidence",
            golden_payloads=_golden("success/identity-quarantine-record.json"),
        ),
        ContractRegistration(
            contract_id="C-002/ResourceRef",
            owner_module="src.schemas.platform.resources",
            producer="shared resource ID generator",
            consumers=("all cross-domain references",),
            schema_model=ResourceRef,
            schema_version="1.0.0",
            business_key="resource_type + resource_id",
            resource_id_field="resource_id",
            time_semantics=(),
            version_semantics=("resource prefix registry",),
            quality_semantics=("resource type and prefix must agree",),
            lineage_fields=("resource_id",),
            storage_profile="structured reference; no free-form combined string",
            retention_class="PINNED",
            compatibility="new resource prefixes are additive only after shared registry and parser tests",
            golden_payloads=_golden(
                "success/resource-ref.json",
                "rejected/resource-id-not-uuidv7.json",
                "rejected/resource-id-unknown-prefix.json",
                "rejected/resource-id-uppercase.json",
                "rejected/resource-ref-prefix-mismatch.json",
            ),
        ),
        ContractRegistration(
            contract_id="C-003/StorageRef",
            owner_module="src.schemas.platform.storage",
            producer="artifact and durable workers",
            consumers=("API", "backup", "result modules"),
            schema_model=StorageRef,
            schema_version="1.0.0",
            business_key="storage_backend + storage_namespace + relative_path",
            resource_id_field=None,
            time_semantics=(),
            version_semantics=("storage namespace binding policy",),
            quality_semantics=("path containment and content integrity",),
            lineage_fields=("content_hash",),
            storage_profile="local_fs namespace app with logical relative POSIX paths",
            retention_class="REBUILDABLE",
            compatibility="namespace roots may be rebound without changing stored references",
            golden_payloads=_golden(
                "success/storage-ref.json",
                "rejected/storage-absolute-path.json",
                "rejected/storage-backslash-path.json",
                "rejected/storage-empty-segment.json",
                "rejected/storage-invalid-backend.json",
                "rejected/storage-invalid-media-type.json",
                "rejected/storage-invalid-namespace.json",
                "rejected/storage-negative-size.json",
                "rejected/storage-path-traversal.json",
                "rejected/storage-windows-drive.json",
            ),
        ),
    )
)


def _validate_schema_properties(schema: object, location: str) -> None:
    if isinstance(schema, dict):
        properties = schema.get("properties")
        if isinstance(properties, dict):
            ambiguous = _FORBIDDEN_PROPERTY_NAMES.intersection(properties)
            if ambiguous:
                fields = ", ".join(sorted(ambiguous))
                raise ValueError(f"{location} contains ambiguous properties: {fields}")
        for key, child in schema.items():
            _validate_schema_properties(child, f"{location}.{key}")
    elif isinstance(schema, list):
        for index, child in enumerate(schema):
            _validate_schema_properties(child, f"{location}[{index}]")


def validate_contract_registry(registry: ContractRegistry) -> None:
    registrations = registry.list()
    if not registrations:
        raise ValueError("platform contract registry cannot be empty")
    model_types: set[type[PlatformContractModel]] = set()
    for registration in registrations:
        if not registration.contract_id.startswith(("C-001/", "C-002/", "C-003/")):
            raise ValueError(f"WP-0001 cannot register {registration.contract_id}")
        if registration.schema_model in model_types:
            raise ValueError(f"schema model registered more than once: {registration.schema_model.__name__}")
        model_types.add(registration.schema_model)
        if not registration.consumers or not registration.golden_payloads:
            raise ValueError(f"incomplete registry metadata for {registration.contract_id}")
        schema = registration.json_schema
        if schema.get("additionalProperties") is not False:
            raise ValueError(f"{registration.contract_id} must forbid additional properties")
        _validate_schema_properties(schema, registration.contract_id)


validate_contract_registry(PLATFORM_CONTRACTS)
