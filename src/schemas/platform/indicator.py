from __future__ import annotations

import json
import re
from datetime import date
from typing import Any

from pydantic import AwareDatetime, Field, field_validator, model_validator

from .base import PlatformContractModel
from .enums import PlatformStringEnum, PublicationStatus
from .hashing import canonical_json_bytes, compute_content_hash


_SEMVER = re.compile(r"^(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$")
_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
_FREQUENCY = re.compile(r"^[a-z0-9][a-z0-9_./-]{0,31}$")
_HASH = re.compile(r"^sha256:[0-9a-f]{64}$")


def _identifier(value: str, field_name: str) -> str:
    if not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"{field_name} must be a normalized lowercase identifier")
    return value


def _semver(value: str, field_name: str) -> str:
    if not _SEMVER.fullmatch(value):
        raise ValueError(f"{field_name} must be a semantic version")
    return value


def _reject_floats(value: Any, field_name: str = "value") -> None:
    if isinstance(value, float):
        raise ValueError(f"{field_name} cannot contain implicit float values")
    if isinstance(value, dict):
        for key, item in value.items():
            _reject_floats(item, f"{field_name}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _reject_floats(item, f"{field_name}[{index}]")


class FormulaType(PlatformStringEnum):
    SQL = "SQL"
    PYTHON_BUILTIN = "PYTHON_BUILTIN"
    HIKYUU_BUILTIN = "HIKYUU_BUILTIN"
    COMPOSITE = "COMPOSITE"


class IndicatorOutputDefinition(PlatformContractModel):
    alias: str
    value_type: str
    unit: str
    precision: int | None = Field(default=None, ge=0, le=18)
    nullable: bool = True

    @field_validator("alias", "unit")
    @classmethod
    def validate_identifiers(cls, value: str, info: object) -> str:
        return _identifier(value, getattr(info, "field_name", "field"))

    @field_validator("value_type")
    @classmethod
    def validate_value_type(cls, value: str) -> str:
        allowed = {"boolean", "decimal", "integer", "string", "date"}
        if value not in allowed:
            raise ValueError("value_type is not supported")
        return value


class ParameterDefinition(PlatformContractModel):
    name: str
    value_type: str
    required: bool = False
    allowed_values: tuple[str, ...] = ()

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return _identifier(value, "parameter name")

    @field_validator("value_type")
    @classmethod
    def validate_value_type(cls, value: str) -> str:
        allowed = {"boolean", "decimal", "integer", "string", "enum"}
        if value not in allowed:
            raise ValueError("parameter value_type is not supported")
        return value

    @field_validator("allowed_values")
    @classmethod
    def validate_allowed_values(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)) or any(not item.strip() for item in value):
            raise ValueError("allowed_values must contain unique non-blank values")
        return value

    @model_validator(mode="after")
    def validate_enum_values(self) -> "ParameterDefinition":
        if self.value_type == "enum" and not self.allowed_values:
            raise ValueError("enum parameters require allowed_values")
        if self.value_type != "enum" and self.allowed_values:
            raise ValueError("allowed_values only applies to enum parameters")
        return self


class DatasetInputRef(PlatformContractModel):
    dataset_id: str
    schema_version: str = "1.0.0"
    required_fields: tuple[str, ...] = ()

    @field_validator("dataset_id")
    @classmethod
    def validate_dataset_id(cls, value: str) -> str:
        return _identifier(value, "dataset_id")

    @field_validator("schema_version")
    @classmethod
    def validate_schema_version(cls, value: str) -> str:
        return _semver(value, "schema_version")

    @field_validator("required_fields")
    @classmethod
    def validate_required_fields(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)) or any(not _IDENTIFIER.fullmatch(item) for item in value):
            raise ValueError("required_fields must contain unique normalized identifiers")
        return value


class IndicatorDependencyRef(PlatformContractModel):
    indicator_id: str
    definition_version: str | None = None
    parameter_bindings: dict[str, Any] = Field(default_factory=dict)

    @field_validator("indicator_id")
    @classmethod
    def validate_indicator_id(cls, value: str) -> str:
        return _identifier(value, "indicator_id")

    @field_validator("definition_version")
    @classmethod
    def validate_definition_version(cls, value: str | None) -> str | None:
        return None if value is None else _semver(value, "definition_version")

    @field_validator("parameter_bindings")
    @classmethod
    def validate_bindings(cls, value: dict[str, Any]) -> dict[str, Any]:
        _reject_floats(value, "parameter_bindings")
        return dict(value)


class IndicatorDefinition(PlatformContractModel):
    """Immutable semantic contract for one versioned indicator definition."""

    indicator_id: str
    name: str
    domain: str
    frequency: str
    schema_version: str
    definition_version: str
    formula_type: FormulaType
    formula_ref: str
    implementation_version: str = "1.0.0"
    input_dataset_refs: tuple[DatasetInputRef, ...] = ()
    input_indicator_refs: tuple[IndicatorDependencyRef, ...] = ()
    lookback_requirement: int = Field(default=0, ge=0)
    warmup_requirement: int = Field(default=0, ge=0)
    output_schema: tuple[IndicatorOutputDefinition, ...]
    parameter_schema: tuple[ParameterDefinition, ...] = ()
    normalized_default_parameters: dict[str, Any] = Field(default_factory=dict)
    recompute_policy: str
    adjustment_policy: str
    universe_policy: str
    asof_policy: str
    materialization: str
    capability_id: str | None = None
    point_in_time: bool = True
    pit_review_version: str | None = None
    definition_hash: str = ""
    formula_hash: str = ""
    implementation_hash: str = ""
    numeric_policy: str
    null_policy: str
    owner: str
    publication_status: PublicationStatus
    created_at: AwareDatetime
    deprecated_at: AwareDatetime | None = None

    @field_validator("indicator_id")
    @classmethod
    def validate_indicator_id(cls, value: str) -> str:
        return _identifier(value, "indicator_id")

    @field_validator("owner")
    @classmethod
    def validate_owner(cls, value: str) -> str:
        if not value.strip() or any(char.isspace() for char in value):
            raise ValueError("owner cannot be blank or contain whitespace")
        return value

    @field_validator("domain", "recompute_policy", "adjustment_policy", "universe_policy", "asof_policy", "materialization", "numeric_policy", "null_policy")
    @classmethod
    def validate_policy_names(cls, value: str, info: object) -> str:
        if not value.strip() or any(char.isspace() for char in value):
            raise ValueError(f"{getattr(info, 'field_name', 'policy')} cannot be blank or contain whitespace")
        return value

    @field_validator("frequency")
    @classmethod
    def validate_frequency(cls, value: str) -> str:
        if not _FREQUENCY.fullmatch(value):
            raise ValueError("frequency must be a normalized frequency identifier")
        return value

    @field_validator("schema_version", "definition_version", "implementation_version")
    @classmethod
    def validate_versions(cls, value: str, info: object) -> str:
        return _semver(value, getattr(info, "field_name", "version"))

    @field_validator("formula_ref")
    @classmethod
    def validate_formula_ref(cls, value: str) -> str:
        if not _IDENTIFIER.fullmatch(value):
            raise ValueError("formula_ref must be a controlled builtin identifier")
        return value

    @field_validator("capability_id")
    @classmethod
    def validate_capability_id(cls, value: str | None) -> str | None:
        return None if value is None else _identifier(value, "capability_id")

    @field_validator("pit_review_version")
    @classmethod
    def validate_pit_review_version(cls, value: str | None) -> str | None:
        return None if value is None else _semver(value, "pit_review_version")

    @field_validator("normalized_default_parameters")
    @classmethod
    def validate_parameter_values(cls, value: dict[str, Any]) -> dict[str, Any]:
        _reject_floats(value, "normalized_default_parameters")
        return dict(value)

    @field_validator("input_dataset_refs", mode="before")
    @classmethod
    def normalize_dataset_refs(cls, value: Any) -> tuple[DatasetInputRef, ...]:
        if value is None:
            return ()
        normalized: list[DatasetInputRef] = []
        for item in value:
            if isinstance(item, str):
                normalized.append(DatasetInputRef(dataset_id=item))
            else:
                normalized.append(item if isinstance(item, DatasetInputRef) else DatasetInputRef.model_validate(item))
        return tuple(normalized)

    @field_validator("input_indicator_refs", mode="before")
    @classmethod
    def normalize_indicator_refs(cls, value: Any) -> tuple[IndicatorDependencyRef, ...]:
        if value is None:
            return ()
        normalized: list[IndicatorDependencyRef] = []
        for item in value:
            if isinstance(item, str):
                if "@" in item:
                    indicator_id, definition_version = item.split("@", 1)
                    normalized.append(IndicatorDependencyRef(indicator_id=indicator_id, definition_version=definition_version))
                else:
                    normalized.append(IndicatorDependencyRef(indicator_id=item))
            else:
                normalized.append(item if isinstance(item, IndicatorDependencyRef) else IndicatorDependencyRef.model_validate(item))
        return tuple(normalized)

    @model_validator(mode="after")
    def validate_definition(self) -> "IndicatorDefinition":
        if self.lookback_requirement < self.warmup_requirement:
            raise ValueError("lookback_requirement must be greater than or equal to warmup_requirement")
        output_aliases = [item.alias for item in self.output_schema]
        if not output_aliases or len(output_aliases) != len(set(output_aliases)):
            raise ValueError("output aliases must be unique and non-empty")
        parameter_names = [item.name for item in self.parameter_schema]
        if len(parameter_names) != len(set(parameter_names)):
            raise ValueError("parameter names must be unique")
        defaults = set(self.normalized_default_parameters)
        declared = set(parameter_names)
        if not defaults <= declared:
            raise ValueError("normalized_default_parameters contains an undeclared parameter")
        required = {item.name for item in self.parameter_schema if item.required}
        if required & defaults:
            raise ValueError("required parameters cannot appear in normalized_default_parameters")
        optional_without_defaults = {item.name for item in self.parameter_schema if not item.required} - defaults
        if optional_without_defaults:
            raise ValueError("optional parameters require normalized defaults")
        dataset_ids = [item.dataset_id for item in self.input_dataset_refs]
        if len(dataset_ids) != len(set(dataset_ids)):
            raise ValueError("input_dataset_refs must not contain duplicate datasets")
        dependency_keys = [
            (item.indicator_id, item.definition_version, compute_content_hash(item.parameter_bindings))
            for item in self.input_indicator_refs
        ]
        if len(dependency_keys) != len(set(dependency_keys)):
            raise ValueError("input_indicator_refs must not contain duplicate dependencies")
        if self.point_in_time and self.pit_review_version is None:
            raise ValueError("point_in_time definitions require pit_review_version")
        if not self.point_in_time and self.pit_review_version is not None:
            raise ValueError("non-point-in-time definitions cannot declare pit_review_version")
        if self.publication_status is PublicationStatus.RETIRED and self.deprecated_at is None:
            raise ValueError("RETIRED definitions require deprecated_at")
        if self.publication_status is not PublicationStatus.RETIRED and self.deprecated_at is not None:
            raise ValueError("deprecated_at is only valid for RETIRED definitions")
        if self.deprecated_at is not None and self.deprecated_at < self.created_at:
            raise ValueError("deprecated_at must not precede created_at")
        semantic_payload = self._semantic_payload()
        expected_definition_hash = compute_content_hash(semantic_payload)
        expected_formula_hash = compute_content_hash({"formula_type": self.formula_type.value, "formula_ref": self.formula_ref})
        expected_implementation_hash = compute_content_hash(
            {"builtin_id": self.formula_ref, "implementation_version": self.implementation_version}
        )
        for field_name, expected in (
            ("definition_hash", expected_definition_hash),
            ("formula_hash", expected_formula_hash),
            ("implementation_hash", expected_implementation_hash),
        ):
            supplied = getattr(self, field_name)
            if supplied and supplied != expected:
                raise ValueError(f"{field_name} does not match canonical definition content")
            object.__setattr__(self, field_name, expected)
        return self

    def _semantic_payload(self) -> dict[str, Any]:
        return self.model_dump(
            mode="python",
            exclude={"definition_hash", "formula_hash", "implementation_hash", "created_at", "deprecated_at"},
        )


class FeatureInstanceKey(PlatformContractModel):
    indicator_id: str
    definition_version: str
    canonical_parameter_json: str
    parameter_hash: str
    frequency: str
    universe_scope_hash: str | None = None

    @field_validator("indicator_id")
    @classmethod
    def validate_indicator_id(cls, value: str) -> str:
        return _identifier(value, "indicator_id")

    @field_validator("definition_version")
    @classmethod
    def validate_definition_version(cls, value: str) -> str:
        return _semver(value, "definition_version")

    @field_validator("frequency")
    @classmethod
    def validate_frequency(cls, value: str) -> str:
        if not _FREQUENCY.fullmatch(value):
            raise ValueError("frequency must be a normalized frequency identifier")
        return value

    @field_validator("parameter_hash", "universe_scope_hash")
    @classmethod
    def validate_hashes(cls, value: str | None) -> str | None:
        if value is not None and not _HASH.fullmatch(value):
            raise ValueError("parameter hashes must use sha256 format")
        return value

    @model_validator(mode="after")
    def validate_parameter_identity(self) -> "FeatureInstanceKey":
        try:
            parsed = json.loads(self.canonical_parameter_json)
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError("canonical_parameter_json must be valid JSON") from exc
        if not isinstance(parsed, dict):
            raise ValueError("canonical_parameter_json must encode an object")
        if canonical_json_bytes(parsed).decode("utf-8") != self.canonical_parameter_json:
            raise ValueError("canonical_parameter_json is not canonical")
        if compute_content_hash(parsed) != self.parameter_hash:
            raise ValueError("parameter_hash does not match canonical_parameter_json")
        return self

    @property
    def sort_key(self) -> tuple[str, str, str, str]:
        return (self.indicator_id, self.definition_version, self.parameter_hash, self.universe_scope_hash or "")


class FeatureInstance(PlatformContractModel):
    indicator_id: str
    definition_version: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    universe_scope_hash: str | None = None

    @field_validator("indicator_id")
    @classmethod
    def validate_indicator_id(cls, value: str) -> str:
        return _identifier(value, "indicator_id")

    @field_validator("definition_version")
    @classmethod
    def validate_definition_version(cls, value: str | None) -> str | None:
        return None if value is None else _semver(value, "definition_version")

    @field_validator("parameters")
    @classmethod
    def validate_parameters(cls, value: dict[str, Any]) -> dict[str, Any]:
        _reject_floats(value, "parameters")
        return dict(value)

    @field_validator("universe_scope_hash")
    @classmethod
    def validate_universe_hash(cls, value: str | None) -> str | None:
        if value is not None and not _HASH.fullmatch(value):
            raise ValueError("universe_scope_hash must use sha256 format")
        return value

    @property
    def canonical_parameter_json(self) -> str:
        return canonical_json_bytes(self.parameters).decode("utf-8")

    @property
    def parameter_hash(self) -> str:
        return compute_content_hash(self.parameters)


class FeatureDependencyEdge(PlatformContractModel):
    dependency: FeatureInstanceKey
    consumer: FeatureInstanceKey


class FeatureDependencyPlan(PlatformContractModel):
    required_instances: tuple[FeatureInstanceKey, ...] = Field(min_length=1)
    ordered_instances: tuple[FeatureInstanceKey, ...] = Field(min_length=1)
    dependency_edges: tuple[FeatureDependencyEdge, ...] = ()
    required_columns: tuple[str, ...] = ()
    dataset_refs: tuple[str, ...] = ()
    capability_ids: tuple[str, ...] = ()
    cutoff_at: AwareDatetime | None = None
    date_from: date | None = None
    date_to: date | None = None
    lookback_requirement: int = Field(default=0, ge=0)
    warmup_requirement: int = Field(default=0, ge=0)
    universe_scope_hash: str | None = None
    plan_hash: str = ""

    @field_validator("dataset_refs", "capability_ids")
    @classmethod
    def validate_ref_lists(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)) or any(not item.strip() for item in value):
            raise ValueError("reference lists must contain unique non-blank values")
        return value

    @field_validator("required_columns")
    @classmethod
    def validate_columns(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)) or any(not item.strip() for item in value):
            raise ValueError("required_columns must contain unique non-blank values")
        return value

    @model_validator(mode="after")
    def validate_plan(self) -> "FeatureDependencyPlan":
        if not self.required_instances or not self.ordered_instances:
            raise ValueError("FeatureDependencyPlan requires non-empty required_instances and ordered_instances")
        required = set(self.required_instances)
        ordered = set(self.ordered_instances)
        if len(required) != len(self.required_instances):
            raise ValueError("required_instances must not contain duplicates")
        if len(ordered) != len(self.ordered_instances):
            raise ValueError("ordered_instances must not contain duplicates")
        if not required <= ordered:
            raise ValueError("ordered_instances must contain all required_instances")
        if self.universe_scope_hash is not None and not _HASH.fullmatch(self.universe_scope_hash):
            raise ValueError("universe_scope_hash must use sha256 format")
        if self.date_to is not None and self.date_from is None:
            raise ValueError("date_to requires date_from")
        if self.date_from is not None and self.date_to is not None and self.date_to < self.date_from:
            raise ValueError("date_to must not precede date_from")
        edge_keys = {(edge.dependency, edge.consumer) for edge in self.dependency_edges}
        if len(edge_keys) != len(self.dependency_edges):
            raise ValueError("dependency_edges must not contain duplicates")
        for edge in self.dependency_edges:
            if edge.dependency not in ordered or edge.consumer not in ordered:
                raise ValueError("dependency_edges must reference ordered_instances")
        order_index = {instance: index for index, instance in enumerate(self.ordered_instances)}
        if any(order_index[edge.dependency] >= order_index[edge.consumer] for edge in self.dependency_edges):
            raise ValueError("ordered_instances must place dependencies before consumers")
        expected = compute_content_hash(
            self.model_dump(mode="python", exclude={"plan_hash"})
        )
        if self.plan_hash and self.plan_hash != expected:
            raise ValueError("plan_hash does not match canonical plan content")
        object.__setattr__(self, "plan_hash", expected)
        return self


__all__ = [
    "DatasetInputRef",
    "FeatureDependencyEdge",
    "FeatureDependencyPlan",
    "FeatureInstance",
    "FeatureInstanceKey",
    "FormulaType",
    "IndicatorDefinition",
    "IndicatorDependencyRef",
    "IndicatorOutputDefinition",
    "ParameterDefinition",
    "PublicationStatus",
]
