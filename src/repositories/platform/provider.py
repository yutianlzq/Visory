from __future__ import annotations

from sqlalchemy import Boolean, Column, DateTime, Integer, MetaData, String, Table, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from src.schemas.platform import DatasetDefinition, ProviderCapability, ProviderDefinition, ProviderPolicy

metadata = MetaData()
CONTROLLED_ADAPTERS = {"a_stock_data", "financial_api"}
provider_definition = Table(
    "provider_definition", metadata,
    Column("provider_id", String(64), primary_key=True), Column("display_name", String(255), nullable=False),
    Column("adapter_name", String(64), nullable=False), Column("adapter_version", String(32), nullable=False),
    Column("provider_kind", String(16), nullable=False), Column("enabled", Boolean, nullable=False),
    Column("credential_ref", String(255)), Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)
dataset_definition = Table(
    "dataset_definition", metadata,
    Column("dataset_id", String(64), primary_key=True), Column("schema_version", String(32), primary_key=True),
    Column("entity_scope", String(64), nullable=False), Column("frequency", String(32), nullable=False),
    Column("primary_key_fields", JSONB, nullable=False), Column("required_fields", JSONB, nullable=False),
    Column("optional_fields", JSONB, nullable=False), Column("field_types", JSONB, nullable=False),
    Column("units", JSONB, nullable=False), Column("enum_domains", JSONB, nullable=False),
    Column("time_semantics", JSONB, nullable=False), Column("null_semantics", JSONB, nullable=False),
    Column("partition_template", String(255), nullable=False), Column("quality_rule_ids", JSONB, nullable=False),
    Column("owner_module", String(255), nullable=False),
)
provider_capability = Table(
    "provider_capability", metadata,
    Column("provider_id", String(64), primary_key=True), Column("dataset_id", String(64), primary_key=True),
    Column("dataset_schema_version", String(32), primary_key=True), Column("market", String(32), primary_key=True),
    Column("frequency", String(32), primary_key=True), Column("supported_fields", JSONB, nullable=False),
    Column("history_start", DateTime(timezone=True)), Column("freshness_sla_seconds", Integer, nullable=False),
    Column("rate_limit_profile", JSONB, nullable=False), Column("provider_capability_status", String(16), nullable=False),
    Column("checked_at", DateTime(timezone=True), nullable=False),
)
provider_policy = Table(
    "provider_policy", metadata,
    Column("provider_policy_id", String(64), primary_key=True), Column("dataset_id", String(64), nullable=False),
    Column("dataset_schema_version", String(32), nullable=False), Column("policy_version", String(32), nullable=False),
    Column("primary_provider_id", String(64), nullable=False), Column("supplemental_provider_ids", JSONB, nullable=False),
    Column("allowed_merge_mode", String(32), nullable=False), Column("fallback_triggers", JSONB, nullable=False),
    Column("field_authority_map", JSONB, nullable=False), Column("conflict_tolerance", JSONB, nullable=False),
    Column("freshness_sla_seconds", Integer, nullable=False), Column("required_quality_rules", JSONB, nullable=False),
    Column("effective_from", DateTime(timezone=True), nullable=False), Column("effective_to", DateTime(timezone=True)),
)


def _definition(row) -> ProviderDefinition:
    return ProviderDefinition.model_validate(dict(row))


def _dataset(row) -> DatasetDefinition:
    value = dict(row)
    for key in ("primary_key_fields", "required_fields", "optional_fields", "quality_rule_ids"):
        value[key] = tuple(value[key])
    value["enum_domains"] = {k: tuple(v) for k, v in value["enum_domains"].items()}
    return DatasetDefinition.model_validate(value)


def _capability(row) -> ProviderCapability:
    value = dict(row)
    value["supported_fields"] = tuple(value["supported_fields"])
    return ProviderCapability.model_validate(value)


def _policy(row) -> ProviderPolicy:
    value = dict(row)
    value["supplemental_provider_ids"] = tuple(value["supplemental_provider_ids"])
    value["fallback_triggers"] = tuple(value["fallback_triggers"])
    value["required_quality_rules"] = tuple(value["required_quality_rules"])
    return ProviderPolicy.model_validate(value)


class ProviderRegistryRepository:
    """Read/write persistence; caller owns transaction boundaries."""

    @staticmethod
    def add_provider(session: Session, record: ProviderDefinition) -> None:
        if record.adapter_name not in CONTROLLED_ADAPTERS:
            raise ValueError("adapter_name is not registered")
        session.execute(provider_definition.insert().values(**record.model_dump(mode="python")))

    @staticmethod
    def add_dataset(session: Session, record: DatasetDefinition) -> None:
        session.execute(dataset_definition.insert().values(**record.model_dump(mode="python")))

    @staticmethod
    def add_capability(session: Session, record: ProviderCapability) -> None:
        session.execute(provider_capability.insert().values(**record.model_dump(mode="python")))

    @staticmethod
    def add_policy(session: Session, record: ProviderPolicy) -> None:
        session.execute(provider_policy.insert().values(**record.model_dump(mode="python")))

    @classmethod
    def _ensure(cls, session: Session, table: Table, key_columns: tuple[str, ...], records: tuple[object, ...], add):
        for record in records:
            payload = record.model_dump(mode="python")
            key = {column: payload[column] for column in key_columns}
            row = session.execute(select(table).filter_by(**key)).mappings().first()
            if row is None:
                add(session, record)
                continue
            existing = dict(row)
            if table is dataset_definition:
                current = _dataset(existing)
            elif table is provider_definition:
                current = _definition(existing)
            elif table is provider_capability:
                current = _capability(existing)
            else:
                current = _policy(existing)
            if current != record:
                raise ValueError(f"registry bootstrap conflict for {table.name}: {key}")

    @classmethod
    def ensure_providers(cls, session: Session, records: tuple[ProviderDefinition, ...]) -> None:
        cls._ensure(session, provider_definition, ("provider_id",), records, cls.add_provider)

    @classmethod
    def ensure_datasets(cls, session: Session, records: tuple[DatasetDefinition, ...]) -> None:
        cls._ensure(session, dataset_definition, ("dataset_id", "schema_version"), records, cls.add_dataset)

    @classmethod
    def ensure_capabilities(cls, session: Session, records: tuple[ProviderCapability, ...]) -> None:
        cls._ensure(session, provider_capability, ("provider_id", "dataset_id", "dataset_schema_version", "market", "frequency"), records, cls.add_capability)

    @classmethod
    def ensure_policies(cls, session: Session, records: tuple[ProviderPolicy, ...]) -> None:
        cls._ensure(session, provider_policy, ("provider_policy_id",), records, cls.add_policy)

    @staticmethod
    def list_providers(session: Session) -> tuple[ProviderDefinition, ...]:
        return tuple(_definition(row) for row in session.execute(select(provider_definition).order_by(provider_definition.c.provider_id)).mappings())

    @staticmethod
    def list_datasets(session: Session) -> tuple[DatasetDefinition, ...]:
        return tuple(_dataset(row) for row in session.execute(select(dataset_definition).order_by(dataset_definition.c.dataset_id, dataset_definition.c.schema_version)).mappings())

    @staticmethod
    def list_capabilities(session: Session, dataset_id: str | None = None) -> tuple[ProviderCapability, ...]:
        statement = select(provider_capability).order_by(provider_capability.c.provider_id, provider_capability.c.dataset_id, provider_capability.c.dataset_schema_version, provider_capability.c.market, provider_capability.c.frequency)
        if dataset_id:
            statement = statement.where(provider_capability.c.dataset_id == dataset_id)
        return tuple(_capability(row) for row in session.execute(statement).mappings())

    @staticmethod
    def list_policies(session: Session, dataset_id: str | None = None) -> tuple[ProviderPolicy, ...]:
        statement = select(provider_policy).order_by(provider_policy.c.dataset_id, provider_policy.c.dataset_schema_version, provider_policy.c.effective_from)
        if dataset_id:
            statement = statement.where(provider_policy.c.dataset_id == dataset_id)
        return tuple(_policy(row) for row in session.execute(statement).mappings())

    @classmethod
    def settings_projection(cls, session: Session):
        from src.schemas.platform import ProviderSettingsProjection, ProviderSettingsProvider
        providers = tuple(
            ProviderSettingsProvider(provider_id=record.provider_id, display_name=record.display_name, adapter_name=record.adapter_name, adapter_version=record.adapter_version, provider_kind=record.provider_kind, enabled=record.enabled, credential_configured=record.credential_ref is not None)
            for record in cls.list_providers(session)
        )
        return ProviderSettingsProjection(providers=providers, datasets=cls.list_datasets(session), capabilities=cls.list_capabilities(session), policies=cls.list_policies(session))


__all__ = ["CONTROLLED_ADAPTERS", "ProviderRegistryRepository", "provider_definition", "dataset_definition", "provider_capability", "provider_policy"]
