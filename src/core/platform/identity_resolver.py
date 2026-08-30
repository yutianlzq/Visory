from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from src.repositories.platform.identity import AssetResolverRepositoryPort
from src.schemas.platform import (
    AliasType,
    AliasVerificationStatus,
    AssetResolutionCandidate,
    AssetResolutionRequest,
    AssetResolutionResult,
    IdentityStatus,
    ResolutionStatus,
    build_entity_key,
    normalize_alias_value,
)


RESOLVER_VERSION = "1.0.0"
_A_SHARE_TIMEZONE = ZoneInfo("Asia/Shanghai")
_CANDIDATE_ONLY_TYPES = frozenset(
    {AliasType.CURRENT_NAME, AliasType.HISTORICAL_NAME, AliasType.PINYIN, AliasType.USER_ALIAS}
)


class AssetResolverService:
    def __init__(self, repository: AssetResolverRepositoryPort, *, clock: Callable[[], datetime] | None = None) -> None:
        self.repository = repository
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    @staticmethod
    def _candidate(row) -> AssetResolutionCandidate:
        return AssetResolutionCandidate(
            asset_type=row.identity.asset_type,
            canonical_id=row.identity.canonical_id,
            entity_key=row.identity.entity_key,
            alias_type=row.alias.alias_type,
            namespace=row.alias.namespace,
            matched_value=row.alias.alias_value,
            identity_status=row.identity.identity_status,
        )

    @staticmethod
    def _result(*, status: ResolutionStatus, resolved_at: datetime, row=None, candidates=(), reason_codes=()) -> AssetResolutionResult:
        return AssetResolutionResult(
            asset_type=row.identity.asset_type if row is not None else None,
            canonical_id=row.identity.canonical_id if row is not None else None,
            entity_key=row.identity.entity_key if row is not None else None,
            resolution_status=status,
            candidates=tuple(candidates),
            reason_codes=tuple(reason_codes),
            resolver_version=RESOLVER_VERSION,
            resolved_at=resolved_at,
        )

    def resolve(self, request: AssetResolutionRequest) -> AssetResolutionResult:
        resolved_at = self.clock()
        if resolved_at.tzinfo is None or resolved_at.utcoffset() is None:
            raise ValueError("resolver clock must return a timezone-aware datetime")
        normalized_value = normalize_alias_value(request.input_value)
        valid_on = resolved_at.astimezone(_A_SHARE_TIMEZONE).date()

        if self.repository.has_open_conflict(namespace=request.input_namespace, normalized_value=normalized_value):
            rows = self.repository.find_candidates(
                namespace=request.input_namespace,
                normalized_value=normalized_value,
                asset_type=request.asset_type,
                valid_on=valid_on,
                available_at=resolved_at,
            )
            return self._result(
                status=ResolutionStatus.CONFLICT,
                resolved_at=resolved_at,
                candidates=(self._candidate(row) for row in rows),
                reason_codes=("IDENTITY_QUARANTINE_OPEN",),
            )

        rows = self.repository.find_candidates(
            namespace=request.input_namespace,
            normalized_value=normalized_value,
            asset_type=request.asset_type,
            valid_on=valid_on,
            available_at=resolved_at,
        )
        if not rows and request.asset_type is not None and request.input_namespace == "user:stock_route":
            try:
                entity_key = build_entity_key(request.asset_type, normalized_value)
            except ValueError:
                entity_key = ""
            identity = self.repository.get_identity(entity_key) if entity_key else None
            if identity is not None:
                direct_alias = type(
                    "DirectAlias",
                    (),
                    {
                        "alias_type": AliasType.EXCHANGE_CODE,
                        "namespace": request.input_namespace,
                        "alias_value": request.input_value,
                        "verification_status": AliasVerificationStatus.VERIFIED,
                    },
                )()
                direct_row = type("DirectRow", (), {"identity": identity, "alias": direct_alias})()
                rows = (direct_row,)

        if not rows:
            return self._result(
                status=ResolutionStatus.NOT_FOUND,
                resolved_at=resolved_at,
                reason_codes=("ALIAS_NOT_FOUND",),
            )

        unique_rows = []
        seen_entities: set[str] = set()
        for row in rows:
            if row.identity.entity_key not in seen_entities:
                seen_entities.add(row.identity.entity_key)
                unique_rows.append(row)
        candidates = tuple(self._candidate(row) for row in unique_rows)
        if len(unique_rows) > 1:
            return self._result(
                status=ResolutionStatus.AMBIGUOUS,
                resolved_at=resolved_at,
                candidates=candidates,
                reason_codes=("MULTIPLE_CANDIDATES",),
            )

        row = unique_rows[0]
        candidate_only = (
            row.alias.alias_type in _CANDIDATE_ONLY_TYPES
            or row.alias.verification_status is not AliasVerificationStatus.VERIFIED
            or request.input_namespace == "user:general_search"
        )
        if candidate_only:
            return self._result(
                status=ResolutionStatus.AMBIGUOUS,
                resolved_at=resolved_at,
                candidates=candidates,
                reason_codes=("CANDIDATE_ALIAS_REQUIRES_CONFIRMATION",),
            )
        if row.identity.identity_status is IdentityStatus.QUARANTINED:
            return self._result(
                status=ResolutionStatus.CONFLICT,
                resolved_at=resolved_at,
                candidates=candidates,
                reason_codes=("IDENTITY_QUARANTINED",),
            )
        if row.identity.identity_status in {IdentityStatus.INACTIVE, IdentityStatus.DELISTED}:
            return self._result(
                status=ResolutionStatus.INACTIVE,
                resolved_at=resolved_at,
                row=row,
                reason_codes=("INACTIVE_ASSET",),
            )
        return self._result(status=ResolutionStatus.RESOLVED, resolved_at=resolved_at, row=row)
