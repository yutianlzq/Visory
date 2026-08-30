from __future__ import annotations

from enum import Enum


class PlatformStringEnum(str, Enum):
    """String enum with stable JSON values."""


class AssetType(PlatformStringEnum):
    STOCK = "stock"
    INDEX = "index"
    ETF = "etf"
    CONVERTIBLE_BOND = "convertible_bond"
    FUND = "fund"
    FUTURE = "future"
    FX = "fx"
    COMMODITY = "commodity"


class IdentityStatus(PlatformStringEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    DELISTED = "DELISTED"
    QUARANTINED = "QUARANTINED"


class AliasType(PlatformStringEnum):
    PROVIDER_SYMBOL = "PROVIDER_SYMBOL"
    BARE_CODE = "BARE_CODE"
    EXCHANGE_CODE = "EXCHANGE_CODE"
    ISIN = "ISIN"
    CURRENT_NAME = "CURRENT_NAME"
    HISTORICAL_NAME = "HISTORICAL_NAME"
    PINYIN = "PINYIN"
    USER_ALIAS = "USER_ALIAS"


class AliasVerificationStatus(PlatformStringEnum):
    VERIFIED = "VERIFIED"
    CANDIDATE = "CANDIDATE"
    REJECTED = "REJECTED"


class ResolutionStatus(PlatformStringEnum):
    RESOLVED = "RESOLVED"
    AMBIGUOUS = "AMBIGUOUS"
    NOT_FOUND = "NOT_FOUND"
    UNSUPPORTED = "UNSUPPORTED"
    CONFLICT = "CONFLICT"
    INACTIVE = "INACTIVE"


class QuarantineStatus(PlatformStringEnum):
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"
    REJECTED = "REJECTED"


class PublicationStatus(PlatformStringEnum):
    DRAFT = "DRAFT"
    PROVISIONAL = "PROVISIONAL"
    CERTIFIED = "CERTIFIED"
    RETIRED = "RETIRED"


class RevisionKind(PlatformStringEnum):
    INITIAL = "INITIAL"
    CORRECTION = "CORRECTION"
    REBUILD = "REBUILD"
    MIGRATION = "MIGRATION"


class QualityStatus(PlatformStringEnum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    UNAVAILABLE = "UNAVAILABLE"
    STALE = "STALE"


class TaskState(PlatformStringEnum):
    ACCEPTED = "ACCEPTED"
    QUEUED = "QUEUED"
    BLOCKED = "BLOCKED"
    LEASED = "LEASED"
    RUNNING = "RUNNING"
    RETRY_WAIT = "RETRY_WAIT"
    SUCCEEDED = "SUCCEEDED"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ResearchQualityStatus(PlatformStringEnum):
    PASSED = "PASSED"
    QUALITY_BLOCKED = "QUALITY_BLOCKED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class AvailabilityBasis(PlatformStringEnum):
    SOURCE_DISCLOSURE = "SOURCE_DISCLOSURE"
    PROVIDER_TIMESTAMP = "PROVIDER_TIMESTAMP"
    EXCHANGE_CALENDAR_RULE = "EXCHANGE_CALENDAR_RULE"
    PLATFORM_OBSERVED = "PLATFORM_OBSERVED"
    VERSIONED_ASSUMPTION = "VERSIONED_ASSUMPTION"


class ResourceType(PlatformStringEnum):
    TASK = "task"
    ATTEMPT = "attempt"
    DATA_SNAPSHOT = "data_snapshot"
    FEATURE_SNAPSHOT = "feature_snapshot"
    OBSERVATION_SNAPSHOT = "observation_snapshot"
    FACT_PACK = "fact_pack"
    RESEARCH = "research"
    REVIEW = "review"
    STRATEGY = "strategy"
    BACKTEST_RUN = "backtest_run"
    PREDICTION = "prediction"
    ARTIFACT = "artifact"
    REPORT = "report"
    PROVIDER_RUN = "provider_run"
    SECTOR = "sector"
    TAXONOMY = "taxonomy"
    INDICATOR = "indicator"
    RAW_OBJECT = "raw_object"
    CANONICAL_PARTITION = "canonical_partition"
    FEATURE_PARTITION = "feature_partition"
    FACT_BLOCK = "fact_block"
    CLAIM = "claim"
    WATCH_CONDITION = "watch_condition"
    QUALITY_REPORT = "quality_report"
    REQUEST = "request"
    CHECKPOINT = "checkpoint"
    BACKUP = "backup"
    DEPLOYMENT = "deployment"


class RetentionClass(PlatformStringEnum):
    PINNED = "PINNED"
    AUDIT = "AUDIT"
    REBUILDABLE = "REBUILDABLE"
    CACHE = "CACHE"
    TEMP = "TEMP"
    QUARANTINE = "QUARANTINE"


class StorageBackend(PlatformStringEnum):
    LOCAL_FS = "local_fs"


class StorageNamespace(PlatformStringEnum):
    APP = "app"
