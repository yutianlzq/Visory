from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Iterator, Mapping, Sequence

from src.schemas.platform.hashing import canonical_json_bytes, compute_content_hash
from src.schemas.platform.indicator import (
    FeatureDependencyEdge,
    FeatureDependencyPlan,
    FeatureInstance,
    FeatureInstanceKey,
    IndicatorDefinition,
    IndicatorDependencyRef,
)

from .indicator_registry import IndicatorRegistry, IndicatorResolutionError, normalize_parameters

if TYPE_CHECKING:
    from src.schemas.platform.provider import DatasetDefinition


@dataclass(frozen=True, slots=True)
class DatasetContractView:
    dataset_id: str
    schema_version: str
    fields: Mapping[str, str]
    frequency: str
    domain: str
    point_in_time: bool
    capability_id: str | None


# 唯一字段来源是现有 DatasetDefinition；number 在计算层显式投影为 Decimal。
DatasetCatalogKey = tuple[str, str]


_DATASET_CAPABILITIES = MappingProxyType(
    {
        "bar_1d_raw": "market_bars_daily",
        "security_master": "security_master_daily",
        "trading_calendar": "trading_calendar",
        "instrument_status_daily": "instrument_status_daily",
        "listing_status_history": "listing_status_history",
        "corporate_action": "corporate_actions_daily",
        "financial_statement": "financial_statement_available_at",
        "benchmark_index_1d": "benchmark_index_daily",
    }
)


class DatasetCatalog:
    """Read-only DatasetDefinition projection with mandatory exact-version lookup."""

    __slots__ = ("_entries",)

    def __init__(self, entries: Mapping[DatasetCatalogKey, DatasetContractView]) -> None:
        self._entries = MappingProxyType(dict(entries))

    def get(self, dataset_id: str, schema_version: str) -> DatasetContractView | None:
        return self._entries.get((dataset_id, schema_version))

    def __getitem__(self, key: DatasetCatalogKey) -> DatasetContractView:
        return self._entries[key]

    def __iter__(self) -> Iterator[DatasetCatalogKey]:
        return iter(self._entries)

    def __len__(self) -> int:
        return len(self._entries)

    def keys(self):
        return self._entries.keys()

    def items(self):
        return self._entries.items()

    def values(self):
        return self._entries.values()


DatasetCatalogLike = DatasetCatalog | Mapping[DatasetCatalogKey, DatasetContractView]


def _catalog_get(
    catalog: DatasetCatalogLike,
    dataset_id: str,
    schema_version: str,
) -> DatasetContractView | None:
    if isinstance(catalog, DatasetCatalog):
        return catalog.get(dataset_id, schema_version)
    return catalog.get((dataset_id, schema_version))


def _project_dataset_catalog(
    definitions: Sequence["DatasetDefinition"] | None = None,
) -> DatasetCatalog:
    if definitions is None:
        from .provider_registry import _dataset_contracts

        definitions = _dataset_contracts()

    entries: dict[DatasetCatalogKey, DatasetContractView] = {}
    for item in definitions:
        if item.dataset_id not in _DATASET_CAPABILITIES:
            continue
        key = (item.dataset_id, item.schema_version)
        if key in entries:
            raise IndicatorResolutionError(
                "INDICATOR_CATALOG_DRIFT",
                "Dataset Catalog contains a duplicate exact-version projection",
                details={"dataset_id": item.dataset_id, "schema_version": item.schema_version},
            )
        entries[key] = DatasetContractView(
            dataset_id=item.dataset_id,
            schema_version=item.schema_version,
            fields=MappingProxyType(
                {key: "decimal" if value == "number" else value for key, value in item.field_types.items()}
            ),
            frequency="1d" if item.frequency == "daily" else item.frequency,
            domain=item.entity_scope,
            point_in_time="available_at" in item.required_fields,
            capability_id=_DATASET_CAPABILITIES[item.dataset_id],
        )
    return DatasetCatalog(entries)


DEFAULT_DATASET_CATALOG = _project_dataset_catalog()


def validate_dataset_projection(
    view: DatasetContractView,
    *,
    dataset_catalog: DatasetCatalogLike | None = None,
) -> None:
    reference_catalog = dataset_catalog if isinstance(dataset_catalog, DatasetCatalog) else DEFAULT_DATASET_CATALOG
    actual = _catalog_get(reference_catalog, view.dataset_id, view.schema_version)
    if actual is None or view != actual:
        raise IndicatorResolutionError(
            "INDICATOR_CATALOG_DRIFT",
            "Resolver Catalog must match the real DatasetDefinition projection",
            details={"dataset_id": view.dataset_id, "schema_version": view.schema_version},
        )


def validate_definition_inputs(
    definition: IndicatorDefinition,
    *,
    dataset_catalog: DatasetCatalogLike | None = None,
) -> None:
    catalog = DEFAULT_DATASET_CATALOG if dataset_catalog is None else dataset_catalog
    for ref in definition.input_dataset_refs:
        actual = _catalog_get(catalog, ref.dataset_id, ref.schema_version)
        if actual is None:
            raise IndicatorResolutionError(
                "INDICATOR_UNREGISTERED_INPUT",
                "definition requires an unavailable Dataset version",
                details={
                    "dataset_id": ref.dataset_id,
                    "schema_version": ref.schema_version,
                    "fields": ref.required_fields,
                },
            )
        validate_dataset_projection(actual, dataset_catalog=catalog)
        missing_fields = sorted(set(ref.required_fields) - set(actual.fields))
        if missing_fields:
            raise IndicatorResolutionError(
                "INDICATOR_UNREGISTERED_INPUT",
                "definition requires unavailable Dataset fields",
                details={
                    "dataset_id": ref.dataset_id,
                    "schema_version": ref.schema_version,
                    "fields": missing_fields,
                },
            )


class FeatureDependencyResolver:
    def __init__(
        self,
        registry: IndicatorRegistry,
        *,
        dataset_catalog: DatasetCatalogLike | None = None,
    ) -> None:
        self.registry = registry
        if dataset_catalog is None:
            self.dataset_catalog: DatasetCatalogLike = DEFAULT_DATASET_CATALOG
            self._projection_catalog = DEFAULT_DATASET_CATALOG
        elif isinstance(dataset_catalog, DatasetCatalog):
            self.dataset_catalog = dataset_catalog
            self._projection_catalog = dataset_catalog
        else:
            self.dataset_catalog = MappingProxyType(dict(dataset_catalog))
            self._projection_catalog = DEFAULT_DATASET_CATALOG

    def resolve(
        self,
        required_instances: Sequence[str | FeatureInstance | Mapping[str, Any]],
        *,
        cutoff_at: datetime | None = None,
        consumer_kind: str = "PREVIEW",
        available_capabilities: set[str] | frozenset[str] | None = None,
        dataset_available_at: Mapping[str, datetime] | None = None,
        universe_scope_hash: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        allowed_domains: set[str] | frozenset[str] | None = None,
        allow_retired: bool = False,
        allow_unavailable: bool = False,
    ) -> FeatureDependencyPlan:
        self._validate_cutoff(cutoff_at)
        if date_to is not None and date_from is None:
            raise IndicatorResolutionError("INDICATOR_PARAMETER_INVALID", "date_to requires date_from")
        if date_from is not None and date_to is not None and date_to < date_from:
            raise IndicatorResolutionError("INDICATOR_PARAMETER_INVALID", "date_to must not precede date_from")
        if consumer_kind not in {"PREVIEW", "FORMAL"}:
            raise IndicatorResolutionError("INDICATOR_PARAMETER_INVALID", "consumer_kind must be PREVIEW or FORMAL")
        if allow_unavailable and consumer_kind != "PREVIEW":
            raise IndicatorResolutionError("INDICATOR_CAPABILITY_MISSING", "unavailable diagnostic plans are preview-only")
        roots = [self._coerce_instance(item, universe_scope_hash) for item in required_instances]
        if not roots:
            raise IndicatorResolutionError("INDICATOR_PARAMETER_INVALID", "at least one required indicator is needed")
        root_universe_hashes = {item.universe_scope_hash for item in roots if item.universe_scope_hash is not None}
        if universe_scope_hash is not None and any(item != universe_scope_hash for item in root_universe_hashes):
            raise IndicatorResolutionError("INDICATOR_UNIVERSE_MISMATCH", "required indicators use different universe scopes")
        if len(root_universe_hashes) > 1:
            raise IndicatorResolutionError("INDICATOR_UNIVERSE_MISMATCH", "required indicators use different universe scopes")

        nodes: dict[tuple[str, str, str, str], tuple[FeatureInstanceKey, IndicatorDefinition]] = {}
        dependencies: dict[tuple[str, str, str, str], set[tuple[str, str, str, str]]] = {}
        edges: list[FeatureDependencyEdge] = []
        visiting: list[tuple[str, str, str, str]] = []

        def visit(instance: FeatureInstance, *, is_dependency: bool) -> FeatureInstanceKey:
            definition = self._get_definition(instance, is_dependency=is_dependency)
            effective_universe = instance.universe_scope_hash or universe_scope_hash
            current = FeatureInstance(
                indicator_id=instance.indicator_id,
                definition_version=definition.definition_version,
                parameters=normalize_parameters(definition, instance.parameters),
                universe_scope_hash=effective_universe,
            )
            self._validate_definition_use(
                definition,
                current,
                cutoff_at=cutoff_at,
                consumer_kind=consumer_kind,
                available_capabilities=available_capabilities,
                dataset_available_at=dataset_available_at,
                allowed_domains=allowed_domains,
                allow_retired=allow_retired,
                allow_unavailable=allow_unavailable,
            )
            key = self._key_for(current, definition)
            key_tuple = key.sort_key
            if key_tuple in visiting:
                cycle_start = visiting.index(key_tuple)
                cycle = [item[0] for item in visiting[cycle_start:]] + [key.indicator_id]
                raise IndicatorResolutionError("INDICATOR_DEPENDENCY_CYCLE", "indicator dependency cycle detected", details={"cycle": cycle})
            if key_tuple in nodes:
                return key
            nodes[key_tuple] = (key, definition)
            dependencies.setdefault(key_tuple, set())
            visiting.append(key_tuple)
            for dependency in definition.input_indicator_refs:
                dependency_instance = self._dependency_instance(dependency, current)
                try:
                    dependency_key = visit(dependency_instance, is_dependency=True)
                except IndicatorResolutionError as exc:
                    if exc.code in {"INDICATOR_UNKNOWN", "INDICATOR_VERSION_UNKNOWN"}:
                        raise IndicatorResolutionError("INDICATOR_DEPENDENCY_UNKNOWN", "indicator dependency is not registered", details={"indicator_id": dependency.indicator_id}) from exc
                    raise
                dependencies[key_tuple].add(dependency_key.sort_key)
                edges.append(FeatureDependencyEdge(dependency=dependency_key, consumer=key))
            visiting.pop()
            return key

        root_keys = [visit(instance, is_dependency=False) for instance in roots]
        ordered_keys = self._topological_order(nodes, dependencies)
        ordered_instances = tuple(nodes[key][0] for key in ordered_keys)
        all_definitions = [nodes[key][1] for key in ordered_keys]
        dataset_refs, capability_ids = self._collect_dataset_and_capability_refs(all_definitions)
        columns: list[str] = []
        for definition in all_definitions:
            for output in definition.output_schema:
                column = f"{definition.indicator_id}.{output.alias}"
                if column in columns:
                    raise IndicatorResolutionError("INDICATOR_OUTPUT_ALIAS_CONFLICT", "feature output alias collides in dependency plan", details={"column": column})
                columns.append(column)
        return FeatureDependencyPlan(
            required_instances=tuple(sorted(root_keys, key=lambda item: item.sort_key)),
            ordered_instances=ordered_instances,
            dependency_edges=tuple(sorted(edges, key=lambda item: (item.dependency.sort_key, item.consumer.sort_key))),
            required_columns=tuple(columns),
            dataset_refs=tuple(dataset_refs),
            capability_ids=tuple(capability_ids),
            cutoff_at=cutoff_at,
            date_from=date_from,
            date_to=date_to,
            lookback_requirement=max((definition.lookback_requirement for definition in all_definitions), default=0),
            warmup_requirement=max((definition.warmup_requirement for definition in all_definitions), default=0),
            universe_scope_hash=universe_scope_hash or next((item.universe_scope_hash for item in root_keys if item.universe_scope_hash), None),
        )

    def _coerce_instance(self, value: str | FeatureInstance | Mapping[str, Any], universe_scope_hash: str | None) -> FeatureInstance:
        if isinstance(value, str):
            return FeatureInstance(indicator_id=value, universe_scope_hash=universe_scope_hash)
        if isinstance(value, FeatureInstance):
            return value
        try:
            return FeatureInstance.model_validate(value)
        except Exception as exc:
            raise IndicatorResolutionError("INDICATOR_PARAMETER_INVALID", "required feature instance is invalid") from exc

    def _get_definition(self, instance: FeatureInstance, *, is_dependency: bool) -> IndicatorDefinition:
        try:
            return self.registry.get(instance.indicator_id, instance.definition_version)
        except IndicatorResolutionError:
            if is_dependency:
                raise
            raise

    @staticmethod
    def _dependency_instance(dependency: IndicatorDependencyRef, parent: FeatureInstance) -> FeatureInstance:
        return FeatureInstance(
            indicator_id=dependency.indicator_id,
            definition_version=dependency.definition_version,
            parameters=dependency.parameter_bindings,
            universe_scope_hash=parent.universe_scope_hash,
        )

    @staticmethod
    def _key_for(instance: FeatureInstance, definition: IndicatorDefinition) -> FeatureInstanceKey:
        canonical_parameters = canonical_json_bytes(instance.parameters).decode("utf-8")
        return FeatureInstanceKey(
            indicator_id=definition.indicator_id,
            definition_version=definition.definition_version,
            canonical_parameter_json=canonical_parameters,
            parameter_hash=compute_content_hash(instance.parameters),
            frequency=definition.frequency,
            universe_scope_hash=instance.universe_scope_hash,
        )

    def _validate_definition_use(
        self,
        definition: IndicatorDefinition,
        instance: FeatureInstance,
        *,
        cutoff_at: datetime | None,
        consumer_kind: str,
        available_capabilities: set[str] | frozenset[str] | None,
        dataset_available_at: Mapping[str, datetime] | None,
        allowed_domains: set[str] | frozenset[str] | None,
        allow_retired: bool,
        allow_unavailable: bool,
    ) -> None:
        if definition.publication_status.value == "DRAFT" or (definition.publication_status.value == "RETIRED" and not allow_retired):
            raise IndicatorResolutionError("INDICATOR_DEFINITION_NOT_PUBLISHED", "indicator definition is not published")
        if consumer_kind == "FORMAL" and not definition.point_in_time:
            raise IndicatorResolutionError("INDICATOR_PIT_NOT_ALLOWED", "formal consumers require point-in-time definitions")
        if definition.domain != "a_share" or (allowed_domains is not None and definition.domain not in allowed_domains):
            raise IndicatorResolutionError("INDICATOR_GLOBAL_DOMAIN_NOT_ALLOWED", "indicator domain is outside the consumer domain")
        if definition.universe_policy == "FROZEN_REQUIRED" and instance.universe_scope_hash is None:
            raise IndicatorResolutionError("INDICATOR_UNIVERSE_NOT_FROZEN", "cross-sectional indicator requires a frozen universe scope")
        if available_capabilities is not None and definition.capability_id and definition.capability_id not in available_capabilities:
            raise IndicatorResolutionError("INDICATOR_CAPABILITY_MISSING", "required indicator capability is unavailable", details={"capability_id": definition.capability_id})
        if definition.indicator_id.startswith("market.sentiment."):
            from .market_sentiment import validate_market_definition
            validate_market_definition(definition)
        for dataset_ref in definition.input_dataset_refs:
            catalog = _catalog_get(
                self.dataset_catalog,
                dataset_ref.dataset_id,
                dataset_ref.schema_version,
            )
            if catalog is None:
                raise IndicatorResolutionError(
                    "INDICATOR_UNREGISTERED_INPUT",
                    "input dataset exact version is not registered",
                    details={
                        "dataset_id": dataset_ref.dataset_id,
                        "schema_version": dataset_ref.schema_version,
                    },
                )
            validate_dataset_projection(catalog, dataset_catalog=self._projection_catalog)
            if catalog.domain != "a_share":
                raise IndicatorResolutionError(
                    "INDICATOR_GLOBAL_DOMAIN_NOT_ALLOWED",
                    "input dataset domain is outside A-share feature scope",
                )
            missing_fields = sorted(set(dataset_ref.required_fields) - set(catalog.fields))
            if missing_fields and not (allow_unavailable and definition.indicator_id.startswith("market.sentiment.")):
                raise IndicatorResolutionError(
                    "INDICATOR_UNREGISTERED_INPUT",
                    "input dataset fields are not registered",
                    details={
                        "dataset_id": dataset_ref.dataset_id,
                        "schema_version": dataset_ref.schema_version,
                        "fields": missing_fields,
                    },
                )
            if consumer_kind == "FORMAL" and not catalog.point_in_time:
                raise IndicatorResolutionError("INDICATOR_PIT_NOT_ALLOWED", "formal consumers cannot use a non-PIT dataset")
            if available_capabilities is not None and catalog.capability_id and catalog.capability_id not in available_capabilities:
                raise IndicatorResolutionError("INDICATOR_CAPABILITY_MISSING", "required input dataset capability is unavailable", details={"capability_id": catalog.capability_id})
            if cutoff_at is not None:
                if consumer_kind == "FORMAL" and (dataset_available_at is None or dataset_ref.dataset_id not in dataset_available_at):
                    raise IndicatorResolutionError(
                        "INDICATOR_AVAILABLE_AT_MISSING",
                        "formal consumers require available_at evidence for every input dataset",
                        details={"dataset_id": dataset_ref.dataset_id},
                    )
                if dataset_available_at is not None and dataset_ref.dataset_id in dataset_available_at:
                    available_at = dataset_available_at[dataset_ref.dataset_id]
                    self._validate_cutoff(available_at)
                    if available_at > cutoff_at:
                        raise IndicatorResolutionError("INDICATOR_AVAILABLE_AFTER_CUTOFF", "input data becomes available after cutoff_at", details={"dataset_id": dataset_ref.dataset_id})

    @staticmethod
    def _validate_cutoff(value: datetime | None) -> None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise IndicatorResolutionError("INDICATOR_PARAMETER_INVALID", "cutoff_at must include a timezone")

    def _collect_dataset_and_capability_refs(
        self,
        definitions: Sequence[IndicatorDefinition],
    ) -> tuple[list[str], list[str]]:
        dataset_refs: set[str] = set()
        capability_ids: set[str] = set()
        for definition in definitions:
            if definition.capability_id:
                capability_ids.add(definition.capability_id)
            for dataset_ref in definition.input_dataset_refs:
                dataset_refs.add(f"{dataset_ref.dataset_id}@{dataset_ref.schema_version}")
                catalog = _catalog_get(
                    self.dataset_catalog,
                    dataset_ref.dataset_id,
                    dataset_ref.schema_version,
                )
                if catalog is None:
                    raise IndicatorResolutionError(
                        "INDICATOR_UNREGISTERED_INPUT",
                        "input dataset exact version is not registered",
                        details={
                            "dataset_id": dataset_ref.dataset_id,
                            "schema_version": dataset_ref.schema_version,
                        },
                    )
                if catalog.capability_id:
                    capability_ids.add(catalog.capability_id)
        return sorted(dataset_refs), sorted(capability_ids)

    @staticmethod
    def _topological_order(
        nodes: Mapping[tuple[str, str, str, str], tuple[FeatureInstanceKey, IndicatorDefinition]],
        dependencies: Mapping[tuple[str, str, str, str], set[tuple[str, str, str, str]]],
    ) -> list[tuple[str, str, str, str]]:
        remaining = {key: set(value) for key, value in dependencies.items()}
        for key in nodes:
            remaining.setdefault(key, set())
        ordered: list[tuple[str, str, str, str]] = []
        while remaining:
            ready = sorted((key for key, parents in remaining.items() if not parents), key=lambda item: item)
            if not ready:
                raise IndicatorResolutionError("INDICATOR_DEPENDENCY_CYCLE", "indicator dependency cycle detected")
            for key in ready:
                ordered.append(key)
                remaining.pop(key)
            ready_set = set(ready)
            for parents in remaining.values():
                parents.difference_update(ready_set)
        return ordered


__all__ = [
    "DEFAULT_DATASET_CATALOG",
    "DatasetCatalog",
    "DatasetCatalogKey",
    "DatasetContractView",
    "FeatureDependencyPlan",
    "FeatureDependencyResolver",
    "FeatureInstance",
    "FeatureInstanceKey",
    "IndicatorResolutionError",
]
