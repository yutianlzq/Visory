from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol
from uuid import uuid4

from sqlalchemy import (
    BigInteger,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    insert,
    or_,
    select,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.schemas.platform import (
    AliasVerificationStatus,
    AssetAlias,
    AssetIdentityRecord,
    AssetType,
    normalize_alias_value,
)

from .database import PostgresDatabase


metadata = MetaData()

asset_identity = Table(
    "asset_identity",
    metadata,
    Column("entity_key", String(160), primary_key=True),
    Column("asset_type", String(32), nullable=False),
    Column("canonical_id", String(128), nullable=False),
    Column("exchange", String(16), nullable=False),
    Column("market", String(16), nullable=False),
    Column("currency", String(3), nullable=False),
    Column("country", String(2), nullable=False),
    Column("valid_from", Date, nullable=False),
    Column("valid_to", Date),
    Column("list_date", Date),
    Column("delist_date", Date),
    Column("identity_status", String(16), nullable=False),
    Column("schema_version", String(32), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

asset_alias = Table(
    "asset_alias",
    metadata,
    Column("alias_id", String(128), primary_key=True),
    Column("entity_key", String(160), ForeignKey("asset_identity.entity_key", ondelete="RESTRICT"), nullable=False),
    Column("alias_type", String(32), nullable=False),
    Column("namespace", String(128), nullable=False),
    Column("alias_value", Text, nullable=False),
    Column("normalized_value", Text, nullable=False),
    Column("valid_from", Date, nullable=False),
    Column("valid_to", Date),
    Column("available_at", DateTime(timezone=True), nullable=False),
    Column("source_provider", String(128), nullable=False),
    Column("actual_upstream", String(128), nullable=False),
    Column("verification_status", String(16), nullable=False),
    Column("revision", Integer, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

identity_quarantine = Table(
    "identity_quarantine",
    metadata,
    Column("quarantine_id", String(128), primary_key=True),
    Column("namespace", String(128), nullable=False),
    Column("normalized_value", Text, nullable=False),
    Column("candidate_entity_key", String(160), nullable=False),
    Column("conflicting_entity_keys", JSONB, nullable=False),
    Column("reason_code", String(64), nullable=False),
    Column("source_provider", String(128), nullable=False),
    Column("actual_upstream", String(128), nullable=False),
    Column("alias_payload", JSONB, nullable=False),
    Column("quarantine_status", String(16), nullable=False),
    Column("revision", BigInteger, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)


@dataclass(frozen=True, slots=True)
class AliasRegistrationOutcome:
    inserted: bool
    quarantine_id: str | None = None


@dataclass(frozen=True, slots=True)
class ResolverAliasRow:
    identity: AssetIdentityRecord
    alias: AssetAlias


class AssetResolverRepositoryPort(Protocol):
    def find_candidates(
        self,
        *,
        namespace: str,
        normalized_value: str,
        asset_type: AssetType | None,
        valid_on: date,
        available_at: datetime,
    ) -> tuple[ResolverAliasRow, ...]:
        ...

    def get_identity(self, entity_key: str) -> AssetIdentityRecord | None:
        ...

    def has_open_conflict(self, *, namespace: str, normalized_value: str) -> bool:
        ...


class AssetIdentityRepository:
    """SQLAlchemy Core persistence. Callers own commit and rollback."""

    @staticmethod
    def add_identity(session: Session, identity: AssetIdentityRecord) -> None:
        session.execute(insert(asset_identity).values(**identity.model_dump(mode="python")))

    @staticmethod
    def get_identity(session: Session, entity_key: str) -> AssetIdentityRecord | None:
        row = session.execute(select(asset_identity).where(asset_identity.c.entity_key == entity_key)).mappings().one_or_none()
        return AssetIdentityRecord.model_validate(dict(row)) if row is not None else None

    @staticmethod
    def _overlapping_entity_keys(session: Session, alias: AssetAlias) -> tuple[str, ...]:
        rows = session.execute(
            select(asset_alias.c.entity_key)
            .where(
                asset_alias.c.namespace == alias.namespace,
                asset_alias.c.normalized_value == alias.normalized_value,
                asset_alias.c.verification_status == AliasVerificationStatus.VERIFIED.value,
                asset_alias.c.entity_key != alias.entity_key,
                asset_alias.c.valid_from < (alias.valid_to or date.max),
                or_(asset_alias.c.valid_to.is_(None), asset_alias.c.valid_to > alias.valid_from),
            )
            .order_by(asset_alias.c.entity_key)
        ).scalars()
        return tuple(dict.fromkeys(rows))

    def register_alias(self, session: Session, alias: AssetAlias) -> AliasRegistrationOutcome:
        try:
            with session.begin_nested():
                session.execute(insert(asset_alias).values(**alias.model_dump(mode="python")))
            return AliasRegistrationOutcome(inserted=True)
        except IntegrityError as exc:
            constraint_name = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
            if constraint_name != "ex_asset_alias_verified_validity":
                raise

        conflicting = self._overlapping_entity_keys(session, alias)
        quarantine_id = f"identity_quarantine_{uuid4().hex}"
        session.execute(
            insert(identity_quarantine).values(
                quarantine_id=quarantine_id,
                namespace=alias.namespace,
                normalized_value=alias.normalized_value,
                candidate_entity_key=alias.entity_key,
                conflicting_entity_keys=list(conflicting),
                reason_code="ALIAS_VALIDITY_CONFLICT",
                source_provider=alias.source_provider,
                actual_upstream=alias.actual_upstream,
                alias_payload=alias.model_dump(mode="json"),
                quarantine_status="OPEN",
                revision=alias.revision,
                created_at=alias.created_at,
            )
        )
        return AliasRegistrationOutcome(inserted=False, quarantine_id=quarantine_id)

    @staticmethod
    def find_candidates_in_session(
        session: Session,
        *,
        namespace: str,
        normalized_value: str,
        asset_type: AssetType | None,
        valid_on: date,
        available_at: datetime,
    ) -> tuple[ResolverAliasRow, ...]:
        statement = (
            select(asset_identity, asset_alias)
            .join(asset_alias, asset_alias.c.entity_key == asset_identity.c.entity_key)
            .where(
                asset_alias.c.namespace == namespace,
                asset_alias.c.normalized_value == normalized_value,
                asset_alias.c.valid_from <= valid_on,
                or_(asset_alias.c.valid_to.is_(None), asset_alias.c.valid_to > valid_on),
                asset_alias.c.available_at <= available_at,
                asset_alias.c.verification_status != AliasVerificationStatus.REJECTED.value,
            )
            .order_by(asset_identity.c.entity_key, asset_alias.c.revision.desc(), asset_alias.c.alias_id)
        )
        if asset_type is not None:
            statement = statement.where(asset_identity.c.asset_type == asset_type.value)
        rows = session.execute(statement).mappings().all()
        results: list[ResolverAliasRow] = []
        seen: set[tuple[str, str]] = set()
        for row in rows:
            key = (row[asset_identity.c.entity_key], row[asset_alias.c.alias_id])
            if key in seen:
                continue
            seen.add(key)
            identity_payload = {column.name: row[column] for column in asset_identity.columns}
            alias_payload = {column.name: row[column] for column in asset_alias.columns}
            results.append(
                ResolverAliasRow(
                    identity=AssetIdentityRecord.model_validate(identity_payload),
                    alias=AssetAlias.model_validate(alias_payload),
                )
            )
        return tuple(results)

    @staticmethod
    def has_open_conflict_in_session(session: Session, *, namespace: str, normalized_value: str) -> bool:
        row = session.execute(
            select(identity_quarantine.c.quarantine_id)
            .where(
                identity_quarantine.c.namespace == namespace,
                identity_quarantine.c.normalized_value == normalized_value,
                identity_quarantine.c.quarantine_status == "OPEN",
            )
            .limit(1)
        ).first()
        return row is not None


class PostgresAssetResolverRepository:
    """Read-only resolver projection backed by the shared PostgreSQL pool."""

    def __init__(self, database: PostgresDatabase, repository: AssetIdentityRepository | None = None) -> None:
        self.database = database
        self.repository = repository or AssetIdentityRepository()

    def find_candidates(self, **kwargs) -> tuple[ResolverAliasRow, ...]:
        with self.database.transaction() as session:
            return self.repository.find_candidates_in_session(session, **kwargs)

    def get_identity(self, entity_key: str) -> AssetIdentityRecord | None:
        with self.database.transaction() as session:
            return self.repository.get_identity(session, entity_key)

    def has_open_conflict(self, *, namespace: str, normalized_value: str) -> bool:
        with self.database.transaction() as session:
            return self.repository.has_open_conflict_in_session(
                session,
                namespace=namespace,
                normalized_value=normalized_value,
            )


class InMemoryAssetIdentityRepository:
    """Deterministic fixture repository; never used as a production fallback."""

    def __init__(self, identities=(), aliases=(), conflicts=()) -> None:
        self._identities = {identity.entity_key: identity for identity in identities}
        self._aliases = tuple(aliases)
        self._conflicts = frozenset(conflicts)

    def find_candidates(
        self,
        *,
        namespace: str,
        normalized_value: str,
        asset_type: AssetType | None,
        valid_on: date,
        available_at: datetime,
    ) -> tuple[ResolverAliasRow, ...]:
        rows: list[ResolverAliasRow] = []
        for alias in self._aliases:
            identity = self._identities.get(alias.entity_key)
            if identity is None or alias.namespace != namespace or alias.normalized_value != normalized_value:
                continue
            if asset_type is not None and identity.asset_type is not asset_type:
                continue
            if alias.valid_from > valid_on or (alias.valid_to is not None and alias.valid_to <= valid_on):
                continue
            if alias.available_at > available_at or alias.verification_status is AliasVerificationStatus.REJECTED:
                continue
            rows.append(ResolverAliasRow(identity=identity, alias=alias))
        return tuple(sorted(rows, key=lambda row: (row.identity.entity_key, -row.alias.revision, row.alias.alias_id)))

    def get_identity(self, entity_key: str) -> AssetIdentityRecord | None:
        return self._identities.get(entity_key)

    def has_open_conflict(self, *, namespace: str, normalized_value: str) -> bool:
        return (namespace, normalized_value) in self._conflicts


__all__ = [
    "AliasRegistrationOutcome",
    "AssetIdentityRepository",
    "AssetResolverRepositoryPort",
    "InMemoryAssetIdentityRepository",
    "PostgresAssetResolverRepository",
    "ResolverAliasRow",
    "asset_alias",
    "asset_identity",
    "identity_quarantine",
    "normalize_alias_value",
]
