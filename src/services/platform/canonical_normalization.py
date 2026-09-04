from __future__ import annotations

import json
import os
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
import re
from typing import Any, Callable, Mapping
from uuid import uuid4

from src.artifacts.hashing import compute_bytes_hash
from src.artifacts.namespace import StorageNamespaceResolver, fsync_directory
from src.schemas.platform import (
    ArtifactPublishRequest,
    ArtifactVisibility,
    CanonicalNormalizationTaskRequirements,
    CanonicalNormalizationTaskResult,
    CanonicalPartition,
    CanonicalQualityReport,
    ProviderCanonicalMappingDefinition,
    QualityStatus,
    ResourceType,
    ResourceRef,
    RetentionClass,
    RevisionKind,
    StorageBackend,
    StorageNamespace,
    StorageRef,
    RawObject,
    AliasType,
    AliasVerificationStatus,
    AssetAlias,
    AssetIdentityRecord,
    AssetResolutionRequest,
    AssetType,
    IdentityStatus,
    build_entity_key,
    generate_resource_id,
    normalize_alias_value,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _dec(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError("numeric value is invalid") from exc


def _aware(value: Any, *, trade_date: bool = False) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware")
        return value.astimezone(timezone.utc)
    if isinstance(value, date):
        if trade_date:
            from zoneinfo import ZoneInfo
            return datetime(value.year, value.month, value.day, tzinfo=ZoneInfo("Asia/Shanghai")).astimezone(timezone.utc)
    if isinstance(value, str):
        text = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        return _aware(parsed, trade_date=trade_date)
    raise ValueError("timestamp is invalid")


def compute_schema_hash(columns: tuple[str, ...], field_types: Mapping[str, str] | None = None) -> str:
    payload: dict[str, Any] = {"columns": list(columns)}
    if field_types is not None:
        payload["field_types"] = {key: field_types[key] for key in sorted(field_types)}
    return compute_bytes_hash(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode())


def deterministic_manifest_hash(payload: Mapping[str, Any]) -> str:
    return compute_bytes_hash(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode())


def _convert_target_value(value: Any, target_type: str, *, field: str) -> Any:
    if value is None:
        return None
    try:
        if target_type == "string":
            if isinstance(value, (dict, list, tuple, set)):
                raise ValueError("structured value is not a string")
            return str(value)
        if target_type == "date":
            if isinstance(value, datetime):
                return value.date().isoformat()
            if isinstance(value, date):
                return value.isoformat()
            text = str(value)
            return date.fromisoformat(text[:10]).isoformat()
        if target_type == "timestamptz":
            return _aware(value)
        if target_type == "number":
            number = _dec(value)
            if number is None or not number.is_finite():
                raise ValueError("number is invalid")
            return format(number, "f")
        if target_type == "integer":
            if isinstance(value, bool):
                raise ValueError("boolean is not an integer")
            number = _dec(value)
            if number is None or not number.is_finite() or number != number.to_integral_value():
                raise ValueError("integer is invalid")
            return int(number)
        if target_type == "boolean":
            if isinstance(value, bool):
                return value
            if isinstance(value, (int, float)) and value in (0, 1):
                return bool(value)
            normalized = str(value).strip().casefold()
            if normalized in {"true", "1", "yes", "y", "open"}:
                return True
            if normalized in {"false", "0", "no", "n", "closed"}:
                return False
            raise ValueError("boolean is invalid")
    except (TypeError, ValueError, InvalidOperation) as exc:
        raise CanonicalNormalizationError("CANONICAL_TYPE_INVALID", "Canonical field type is invalid.", details={"field": field, "target_type": target_type}) from exc
    raise CanonicalNormalizationError("CANONICAL_TYPE_UNSUPPORTED", "Canonical field type is unsupported.", details={"field": field, "target_type": target_type})


class CanonicalNormalizationError(Exception):
    def __init__(self, code: str, message: str, *, details: Mapping[str, Any] | None = None):
        super().__init__(message)
        self.error_code = code
        self.details = dict(details or {})


def _arrow_schema(columns: tuple[str, ...], field_types: Mapping[str, str]):
    """Build the stable, explicit physical schema used by Canonical Parquet."""
    try:
        import pyarrow as pa
    except ImportError as exc:
        raise CanonicalNormalizationError(
            "CANONICAL_PARQUET_ENGINE_UNAVAILABLE",
            "The controlled Canonical Parquet engine is unavailable.",
        ) from exc
    physical_types = {
        "string": pa.string(),
        "date": pa.date32(),
        "number": pa.decimal128(38, 12),
        "integer": pa.int64(),
        "boolean": pa.bool_(),
        "timestamptz": pa.timestamp("us", tz="UTC"),
    }
    try:
        return pa.schema([pa.field(name, physical_types[field_types[name]], nullable=True) for name in columns])
    except KeyError as exc:
        raise CanonicalNormalizationError(
            "CANONICAL_SCHEMA_INCOMPLETE",
            "Canonical schema does not define every output column.",
            details={"field": str(exc)},
        ) from exc


def _parquet_content(rows: list[Mapping[str, Any]], columns: tuple[str, ...], field_types: Mapping[str, str]) -> bytes:
    """Serialize canonical rows with an explicit schema and fixed writer options."""
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise CanonicalNormalizationError(
            "CANONICAL_PARQUET_ENGINE_UNAVAILABLE",
            "The controlled Canonical Parquet engine is unavailable.",
        ) from exc

    arrow_rows: list[dict[str, Any]] = []
    for row in rows:
        converted: dict[str, Any] = {}
        for field in columns:
            value = row.get(field)
            target_type = field_types[field]
            if value is not None and target_type == "date":
                value = date.fromisoformat(value)
            elif value is not None and target_type == "number":
                value = Decimal(value)
                if value.as_tuple().exponent < -12 or len(value.as_tuple().digits) > 38:
                    raise CanonicalNormalizationError(
                        "CANONICAL_DECIMAL_SCALE_INVALID",
                        "Canonical number exceeds the fixed Parquet decimal schema.",
                        details={"field": field},
                    )
            converted[field] = value
        arrow_rows.append(converted)

    schema = _arrow_schema(columns, field_types)
    table = pa.Table.from_pylist(arrow_rows, schema=schema)
    sink = pa.BufferOutputStream()
    pq.write_table(
        table,
        sink,
        version="2.6",
        compression="zstd",
        use_dictionary=False,
        write_statistics=False,
        data_page_version="1.0",
        store_schema=False,
    )
    return sink.getvalue().to_pybytes()


class CanonicalNormalizer:
    """Normalize provider-native rows into append-only deterministic canonical partitions."""
    def __init__(
        self,
        runtime_root: Path | str,
        *,
        clock: Callable[[], datetime] = _utc_now,
        rename: Callable[[Path, Path], None] = os.rename,
    ):
        self.resolver = StorageNamespaceResolver(runtime_root)
        self.clock = clock
        self.rename = rename

    def _map_row(
        self,
        row: Mapping[str, Any],
        mapping: ProviderCanonicalMappingDefinition,
        dataset_id: str,
        *,
        identity_resolver=None,
        is_trading_day: Callable[[str, date], bool] | None = None,
        market: str = "CN",
        now: datetime | None = None,
    ) -> dict[str, Any]:
        out: dict[str, Any] = {}
        identity_cache: dict[str, Any] = {}
        if dataset_id in {"security_master", "bar_1d_raw", "instrument_status_daily", "listing_status_history", "corporate_action", "financial_statement"} and identity_resolver is None:
            raise CanonicalNormalizationError(
                "CANONICAL_IDENTITY_UNRESOLVED",
                "Canonical security data requires the registered Identity Resolver.",
            )

        def resolve_identity(source_value: Any) -> Any:
            key = str(source_value)
            if key in identity_cache:
                return identity_cache[key]
            if identity_resolver is None:
                return None
            resolved = identity_resolver(key, row)
            if isinstance(resolved, (tuple, list)):
                if len(resolved) != 1:
                    raise CanonicalNormalizationError("CANONICAL_IDENTITY_AMBIGUOUS", "Identity resolution is ambiguous.")
                resolved = resolved[0]
            status = getattr(resolved, "resolution_status", None)
            if status is not None and getattr(status, "value", status) not in {"RESOLVED", "INACTIVE"}:
                code = "CANONICAL_IDENTITY_AMBIGUOUS" if getattr(status, "value", status) == "AMBIGUOUS" else "CANONICAL_IDENTITY_UNRESOLVED"
                raise CanonicalNormalizationError(code, "Identity could not be resolved.", details={"value": key})
            entity_key = getattr(resolved, "entity_key", None)
            canonical_id = getattr(resolved, "canonical_id", None)
            if entity_key is None and canonical_id is None:
                raise CanonicalNormalizationError("CANONICAL_IDENTITY_UNRESOLVED", "Identity could not be resolved.", details={"value": key})
            value = {"entity_key": entity_key, "canonical_id": canonical_id}
            identity_cache[key] = value
            return value

        for target in mapping.target_fields:
            source = mapping.source_fields[target]
            value = row.get(source)
            if value is None and mapping.null_semantics.get(target) == "forbidden":
                raise CanonicalNormalizationError("CANONICAL_NULL_FORBIDDEN", "Required canonical field is null.", details={"field": target})
            if target in mapping.enum_mappings and value is not None:
                try:
                    value = mapping.enum_mappings[target][str(value)]
                except KeyError as exc:
                    raise CanonicalNormalizationError("CANONICAL_ENUM_UNKNOWN", "Unknown enum value.", details={"field": target}) from exc
            if target in mapping.unit_multipliers and value is not None:
                number = _dec(value)
                if number is None:
                    raise CanonicalNormalizationError("CANONICAL_TYPE_INVALID", "Canonical numeric field is invalid.", details={"field": target})
                try:
                    value = number * Decimal(mapping.unit_multipliers[target])
                except (InvalidOperation, ValueError) as exc:
                    raise CanonicalNormalizationError("CANONICAL_UNIT_INVALID", "Canonical unit multiplier is invalid.", details={"field": target}) from exc
            if target in {"entity_key", "canonical_id"} and value is not None and identity_resolver is not None:
                resolved = resolve_identity(value)
                value = resolved[target]
                if value is None:
                    raise CanonicalNormalizationError("CANONICAL_IDENTITY_UNRESOLVED", "Identity result lacks required field.", details={"field": target})
            value = _convert_target_value(value, mapping.target_field_types[target], field=target)
            if target == "available_at" and value is not None and now is not None and value > now:
                raise CanonicalNormalizationError("CANONICAL_AVAILABLE_AT_FUTURE", "available_at cannot be in the future.", details={"field": target})
            out[target] = value

        available_at = out.get("available_at")
        published_at = out.get("published_at")
        if published_at is not None and available_at is not None and published_at > available_at:
            raise CanonicalNormalizationError("CANONICAL_DISCLOSURE_AFTER_AVAILABLE", "published_at cannot be later than available_at.")
        if dataset_id == "security_master":
            if identity_resolver is not None and (out.get("entity_key") is None or out.get("canonical_id") is None):
                raise CanonicalNormalizationError("CANONICAL_IDENTITY_UNRESOLVED", "Identity result is incomplete.")
        elif dataset_id == "trading_calendar":
            is_open = out.get("is_open")
            opened = out.get("session_open_at")
            closed = out.get("session_close_at")
            if is_open and (opened is None or closed is None or closed <= opened):
                raise CanonicalNormalizationError("CANONICAL_CALENDAR_INVALID", "Open calendar sessions require ordered bounds.")
            if is_open is False and (opened is not None or closed is not None):
                raise CanonicalNormalizationError("CANONICAL_CALENDAR_INVALID", "Closed calendar sessions cannot have session bounds.")
        elif dataset_id == "bar_1d_raw":
            numeric_fields = ("open", "high", "low", "close", "prev_close", "price_limit_up", "price_limit_down", "volume_shares", "amount_cny")
            prices = [Decimal(out[key]) for key in ("open", "high", "low", "close") if out.get(key) is not None]
            if any(Decimal(out[key]) < 0 for key in numeric_fields if out.get(key) is not None):
                raise CanonicalNormalizationError("CANONICAL_NEGATIVE_VALUE", "Negative market value is invalid.")
            if len(prices) == 4 and (prices[1] < max(prices[0], prices[3]) or prices[2] > min(prices[0], prices[3])):
                raise CanonicalNormalizationError("CANONICAL_OHLC_INVALID", "OHLC relationship is invalid.")
            if is_trading_day is not None:
                trade_date = date.fromisoformat(out["trade_date"])
                if not is_trading_day(market, trade_date):
                    raise CanonicalNormalizationError(
                        "CANONICAL_NON_TRADING_DAY",
                        "Daily bars cannot be published for a closed trading day.",
                        details={"market": market, "trade_date": trade_date.isoformat()},
                    )
        elif dataset_id == "instrument_status_daily":
            if out.get("instrument_status") == "SUSPENDED" and out.get("is_tradable"):
                raise CanonicalNormalizationError("CANONICAL_STATUS_INCONSISTENT", "Suspended instruments cannot be tradable.")
            if out.get("instrument_status") == "DELISTED" and out.get("is_tradable"):
                raise CanonicalNormalizationError("CANONICAL_STATUS_INCONSISTENT", "Delisted instruments cannot be tradable.")
        elif dataset_id == "listing_status_history":
            start = date.fromisoformat(out["effective_from"])
            end = out.get("effective_to")
            if end is not None and date.fromisoformat(end) <= start:
                raise CanonicalNormalizationError("CANONICAL_LISTING_INTERVAL_INVALID", "Listing interval must have a positive duration.")
        elif dataset_id == "corporate_action":
            for later in ("record_date", "payment_date"):
                if out.get(later) is not None and date.fromisoformat(out[later]) < date.fromisoformat(out["ex_date"]):
                    raise CanonicalNormalizationError("CANONICAL_ACTION_DATES_INVALID", "Corporate action dates are out of order.")
            if out.get("ratio") is not None and Decimal(out["ratio"]) < 0:
                raise CanonicalNormalizationError("CANONICAL_ACTION_AMOUNT_INVALID", "Corporate action ratio cannot be negative.")
            if out.get("cash_amount") is not None and Decimal(out["cash_amount"]) < 0:
                raise CanonicalNormalizationError("CANONICAL_ACTION_AMOUNT_INVALID", "Corporate action cash amount cannot be negative.")
            if out.get("revision", 0) < 1:
                raise CanonicalNormalizationError("CANONICAL_REVISION_INVALID", "Revision must be positive.")
        elif dataset_id == "financial_statement":
            allowed_units = {"CNY", "RMB", "USD", "EUR", "shares", "yuan", "thousand_cny", "million_cny", "billion_cny", "percent", "ratio", "per_share"}
            if str(out.get("unit")) not in allowed_units:
                raise CanonicalNormalizationError("CANONICAL_UNIT_UNKNOWN", "Financial statement unit is unknown.")
            if out.get("revision", 0) < 1:
                raise CanonicalNormalizationError("CANONICAL_REVISION_INVALID", "Revision must be positive.")
        return out

    def normalize_rows(self, *, raw_object_id: str, provider_run_id: str, provider_id: str, dataset_id: str, dataset_schema_version: str, provider_policy_version: str, mapping: ProviderCanonicalMappingDefinition, rows: list[Mapping[str, Any]], partition_key: str, identity_resolver=None, is_trading_day: Callable[[str, date], bool] | None = None, market: str = "CN", revision: int = 1, supersedes_id: str | None = None, task_id: str | None = None, attempt_id: str | None = None) -> tuple[CanonicalPartition | None, CanonicalQualityReport, bytes]:
        now = self.clock()
        mapped: list[dict[str, Any]] = []
        failures: list[str] = []
        seen: set[tuple[Any, ...]] = set()
        duplicate = 0
        unresolved = 0
        ambiguous = 0
        for row in rows:
            try:
                item = self._map_row(
                    row,
                    mapping,
                    dataset_id,
                    identity_resolver=identity_resolver,
                    is_trading_day=is_trading_day,
                    market=market,
                    now=now,
                )
                key_fields = {
                    "security_master": ("entity_key",),
                    "trading_calendar": ("market", "trade_date"),
                    "bar_1d_raw": ("entity_key", "trade_date"),
                    "instrument_status_daily": ("entity_key", "status_date"),
                    "listing_status_history": ("entity_key", "effective_from"),
                    "corporate_action": ("corporate_action_id", "revision"),
                    "financial_statement": ("entity_key", "report_period", "statement_type", "line_item", "revision"),
                }.get(dataset_id, mapping.target_fields[:1])
                key = tuple(item.get(k) for k in key_fields)
                if key in seen:
                    duplicate += 1
                    raise CanonicalNormalizationError(
                        "CANONICAL_DUPLICATE_KEY",
                        "Duplicate canonical key.",
                    )
                seen.add(key)
                mapped.append(item)
            except CanonicalNormalizationError as exc:
                failures.append(exc.error_code)
                if exc.error_code == "CANONICAL_IDENTITY_UNRESOLVED":
                    unresolved += 1
                if exc.error_code == "CANONICAL_IDENTITY_AMBIGUOUS":
                    ambiguous += 1
        if dataset_id == "listing_status_history" and mapped:
            by_entity: dict[str, list[dict[str, Any]]] = {}
            for item in mapped:
                by_entity.setdefault(str(item["entity_key"]), []).append(item)
            for items in by_entity.values():
                items.sort(key=lambda item: item["effective_from"])
                for current, following in zip(items, items[1:]):
                    end = current.get("effective_to")
                    if end is None or following["effective_from"] < end:
                        failures.append("CANONICAL_LISTING_INTERVAL_OVERLAP")
                        break
        quality_status = QualityStatus.COMPLETE if not failures else QualityStatus.FAILED
        report = CanonicalQualityReport(
            quality_report_id=generate_resource_id(ResourceType.QUALITY_REPORT),
            quality_status=quality_status,
            rule_results={"mapping": "PASS" if not failures else "FAIL"},
            row_count=len(rows),
            rejected_row_count=len(rows) - len(mapped),
            duplicate_key_count=duplicate,
            identity_unresolved_count=unresolved,
            identity_ambiguous_count=ambiguous,
            failure_reasons=tuple(sorted(set(failures))),
            task_id=task_id,
            attempt_id=attempt_id,
            dataset_id=dataset_id,
            dataset_schema_version=dataset_schema_version,
            mapping_version=mapping.mapping_version,
            mapping_hash=mapping.mapping_hash,
            provider_run_refs=(provider_run_id,),
            raw_object_refs=(raw_object_id,),
            created_at=now,
        )
        if failures:
            return None, report, b""
        columns = tuple(mapping.target_fields)
        content = _parquet_content(mapped, columns, mapping.target_field_types)
        partition_hash = compute_bytes_hash(content)
        schema_hash = compute_schema_hash(columns, mapping.target_field_types)
        partition_id = generate_resource_id(ResourceType.CANONICAL_PARTITION)
        path = f"canonical/dataset={dataset_id}/partition={partition_key}/revision={revision}/partition={partition_id}/data.parquet"
        ref = StorageRef(storage_backend=StorageBackend.LOCAL_FS, storage_namespace=StorageNamespace.APP, relative_path=path, content_hash=partition_hash, media_type="application/vnd.apache.parquet", size_bytes=len(content))
        available_values = [item["available_at"] for item in mapped if isinstance(item.get("available_at"), datetime)]
        min_available_at = min(available_values, default=now)
        max_available_at = max(available_values, default=None)
        partition = CanonicalPartition(canonical_partition_id=partition_id, dataset_id=dataset_id, dataset_schema_version=dataset_schema_version, partition_key=partition_key, revision=revision, revision_kind=RevisionKind.CORRECTION if supersedes_id else RevisionKind.INITIAL, supersedes_id=supersedes_id, provider_policy_version=provider_policy_version, provider_run_refs=(provider_run_id,), raw_object_refs=(raw_object_id,), min_available_at=min_available_at, max_available_at=max_available_at, row_count=len(mapped), distinct_entity_count=len({item.get("entity_key") for item in mapped if item.get("entity_key")}), storage_ref=ref, partition_hash=partition_hash, schema_hash=schema_hash, quality_status=quality_status, quality_report_id=report.quality_report_id, created_at=now, published_at=now)
        report = report.model_copy(update={"canonical_partition_id": partition_id})
        return partition, report, content

    def publish_partition(self, partition: CanonicalPartition, report: CanonicalQualityReport, content: bytes) -> None:
        ref = partition.storage_ref
        if ref.media_type != "application/vnd.apache.parquet":
            raise CanonicalNormalizationError("CANONICAL_MEDIA_TYPE_INVALID", "Canonical media type is invalid.")
        if len(content) != ref.size_bytes or compute_bytes_hash(content) != ref.content_hash:
            raise CanonicalNormalizationError("CANONICAL_CONTENT_INVALID", "Canonical content integrity validation failed.")
        if report.canonical_partition_id != partition.canonical_partition_id:
            raise CanonicalNormalizationError("CANONICAL_REPORT_MISMATCH", "Quality report does not match partition.")
        target = self.resolver.resolve(ref)
        target_dir = target.parent
        if target.exists() or target_dir.exists():
            raise CanonicalNormalizationError("CANONICAL_TARGET_EXISTS", "Canonical partition target already exists.")
        staging_root = self.resolver.resolve(".staging", allow_internal=True)
        staging_root.mkdir(parents=True, exist_ok=True)
        staging = staging_root / f"{partition.canonical_partition_id}-{uuid4().hex}"
        staging.mkdir()
        payload = staging / target.name
        try:
            with payload.open("xb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            manifest_payload = {"partition": partition.model_dump(mode="json"), "quality_report": report.model_dump(mode="json")}
            manifest_payload["manifest_hash"] = deterministic_manifest_hash(manifest_payload)
            manifest = staging / "manifest.json"
            manifest.write_text(json.dumps(manifest_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8", newline="\n")
            with manifest.open("r+b") as handle:
                handle.flush()
                os.fsync(handle.fileno())
            fsync_directory(staging)
            target_dir.parent.mkdir(parents=True, exist_ok=True)
            fsync_directory(target_dir.parent)
            self.rename(staging, target_dir)
            fsync_directory(target_dir.parent)
        except CanonicalNormalizationError:
            raise
        except OSError as exc:
            raise CanonicalNormalizationError(
                "CANONICAL_ATOMIC_PUBLISH_FAILED",
                "Canonical storage publication failed.",
                details={"component": "canonical_storage"},
            ) from exc


_PROVIDER_SYMBOL = re.compile(r"^(?P<code>[0-9]{6})\.(?P<exchange>SH|SZ|BJ|SSE|SZSE|BSE)$", re.IGNORECASE)
_PROVIDER_EXCHANGES = {"SH": "SH", "SSE": "SH", "SZ": "SZ", "SZSE": "SZ", "BJ": "BJ", "BSE": "BJ"}


class CanonicalIdentityBridge:
    """Use the existing identity registry; never treat a provider symbol as an entity key."""

    def __init__(self, database, *, mapping: ProviderCanonicalMappingDefinition, raw: RawObject, clock: Callable[[], datetime]) -> None:
        from src.repositories.platform.identity import AssetIdentityRepository

        self.database = database
        self.mapping = mapping
        self.raw = raw
        self.clock = clock
        self.repository = AssetIdentityRepository()

    def _mapped_value(self, row: Mapping[str, Any], target: str) -> Any:
        source = self.mapping.source_fields[target]
        value = row.get(source)
        if value is not None and target in self.mapping.enum_mappings:
            try:
                value = self.mapping.enum_mappings[target][str(value)]
            except KeyError as exc:
                raise CanonicalNormalizationError(
                    "CANONICAL_ENUM_UNKNOWN",
                    "Unknown enum value.",
                    details={"field": target},
                ) from exc
        return value

    def _security_identity(self, value: Any, row: Mapping[str, Any]) -> AssetIdentityRecord:
        symbol = str(value)
        parsed = _PROVIDER_SYMBOL.fullmatch(symbol)
        if parsed is None:
            raise CanonicalNormalizationError(
                "CANONICAL_IDENTITY_UNRESOLVED",
                "Provider symbols must include a recognized exchange suffix.",
            )
        symbol_exchange = _PROVIDER_EXCHANGES[parsed.group("exchange").upper()]
        try:
            exchange = str(self._mapped_value(row, "exchange"))
            asset_type = AssetType(str(self._mapped_value(row, "asset_type")))
            currency = str(self._mapped_value(row, "currency"))
            list_date = date.fromisoformat(str(self._mapped_value(row, "list_date"))[:10])
            delist_value = self._mapped_value(row, "delist_date")
            delist_date = date.fromisoformat(str(delist_value)[:10]) if delist_value is not None else None
        except (KeyError, TypeError, ValueError) as exc:
            raise CanonicalNormalizationError(
                "CANONICAL_IDENTITY_UNRESOLVED",
                "Security identity fields are incomplete or invalid.",
            ) from exc
        if asset_type is not AssetType.STOCK or exchange != symbol_exchange or currency != "CNY":
            raise CanonicalNormalizationError(
                "CANONICAL_IDENTITY_CONFLICT",
                "Provider symbol, exchange, asset type, or currency is inconsistent.",
            )
        canonical_id = f"{exchange.lower()}{parsed.group('code')}"
        now = self.clock()
        return AssetIdentityRecord(
            asset_type=asset_type,
            canonical_id=canonical_id,
            entity_key=build_entity_key(asset_type, canonical_id),
            exchange=exchange,
            market="CN",
            currency=currency,
            country="CN",
            valid_from=list_date,
            valid_to=delist_date,
            list_date=list_date,
            delist_date=delist_date,
            identity_status=IdentityStatus.DELISTED if delist_date is not None else IdentityStatus.ACTIVE,
            schema_version="1.0.0",
            created_at=now,
        )

    def _upstream_label(self) -> str:
        candidate = self.raw.actual_upstream
        if re.fullmatch(r"[a-z][a-z0-9._-]{0,127}", candidate):
            return candidate
        return f"origin_{compute_bytes_hash(candidate.encode('utf-8'))[7:31]}"

    def _alias(self, identity: AssetIdentityRecord, value: Any, available_at: datetime) -> AssetAlias:
        symbol = str(value)
        alias_payload = {
            "entity_key": identity.entity_key,
            "namespace": f"{self.raw.provider_id}:cn_stock",
            "value": symbol,
            "valid_from": identity.valid_from.isoformat(),
            "valid_to": identity.valid_to.isoformat() if identity.valid_to else None,
        }
        alias_hash = compute_bytes_hash(
            json.dumps(alias_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        )
        return AssetAlias(
            alias_id=f"alias_{alias_hash[7:39]}",
            entity_key=identity.entity_key,
            alias_type=AliasType.PROVIDER_SYMBOL,
            namespace=alias_payload["namespace"],
            alias_value=symbol,
            normalized_value=normalize_alias_value(symbol),
            valid_from=identity.valid_from,
            valid_to=identity.valid_to,
            available_at=available_at,
            source_provider=self.raw.provider_id,
            actual_upstream=self._upstream_label(),
            verification_status=AliasVerificationStatus.VERIFIED,
            revision=1,
            created_at=self.clock(),
        )

    def provision_security_master(self, value: Any, row: Mapping[str, Any]):
        identity = self._security_identity(value, row)
        available_at = _aware(self._mapped_value(row, "available_at"))
        alias = self._alias(identity, value, available_at)
        with self.database.transaction() as session:
            existing = self.repository.get_identity(session, identity.entity_key)
            if existing is None:
                self.repository.add_identity(session, identity)
            elif (
                existing.asset_type is not identity.asset_type
                or existing.canonical_id != identity.canonical_id
                or existing.exchange != identity.exchange
                or existing.market != identity.market
                or existing.currency != identity.currency
            ):
                raise CanonicalNormalizationError(
                    "CANONICAL_IDENTITY_CONFLICT",
                    "Existing identity conflicts with the Security Master record.",
                )
            candidates = self.repository.find_candidates_in_session(
                session,
                namespace=alias.namespace,
                normalized_value=alias.normalized_value,
                asset_type=identity.asset_type,
                valid_on=alias.valid_from,
                available_at=available_at,
            )
            if any(candidate.identity.entity_key != identity.entity_key for candidate in candidates):
                outcome = self.repository.register_alias(session, alias)
                if not outcome.inserted:
                    raise CanonicalNormalizationError(
                        "CANONICAL_IDENTITY_CONFLICT",
                        "Provider alias conflicts with another identity.",
                    )
                raise CanonicalNormalizationError(
                    "CANONICAL_IDENTITY_CONFLICT",
                    "Provider alias resolves to another identity.",
                )
            if not candidates:
                outcome = self.repository.register_alias(session, alias)
                if not outcome.inserted:
                    raise CanonicalNormalizationError(
                        "CANONICAL_IDENTITY_CONFLICT",
                        "Provider alias conflicts with another identity.",
                    )
        return self.resolve_provider_alias(value, row)

    def resolve_provider_alias(self, value: Any, row: Mapping[str, Any]):
        from src.core.platform.identity_resolver import AssetResolverService
        from src.repositories.platform.identity import PostgresAssetResolverRepository

        return AssetResolverService(
            PostgresAssetResolverRepository(self.database),
            clock=self.clock,
        ).resolve(
            AssetResolutionRequest(
                input_namespace=f"{self.raw.provider_id}:cn_stock",
                input_value=str(value),
                asset_type=AssetType.STOCK,
            )
        )


class CanonicalTradingDayResolver:
    """Resolve a trading day exclusively from an already published Canonical calendar partition."""

    def __init__(self, database, *, storage_resolver: StorageNamespaceResolver, repository=None) -> None:
        from src.repositories.platform.canonical import CanonicalRepository

        self.database = database
        self.storage_resolver = storage_resolver
        self.repository = repository or CanonicalRepository()

    def __call__(self, market: str, trading_day: date) -> bool:
        with self.database.transaction() as session:
            partition = self.repository.get_latest_partition_for_key(
                session,
                dataset_id="trading_calendar",
                partition_key=trading_day.isoformat(),
            )
        if partition is None:
            raise CanonicalNormalizationError(
                "CANONICAL_TRADING_CALENDAR_UNAVAILABLE",
                "A published Canonical trading calendar is required for daily bars.",
            )
        try:
            path = self.storage_resolver.resolve(partition.storage_ref, require_exists=True)
            content = path.read_bytes()
        except (CanonicalNormalizationError, OSError) as exc:
            raise CanonicalNormalizationError(
                "CANONICAL_TRADING_CALENDAR_UNAVAILABLE",
                "The Canonical trading calendar cannot be read.",
            ) from exc
        if len(content) != partition.storage_ref.size_bytes or compute_bytes_hash(content) != partition.partition_hash:
            raise CanonicalNormalizationError(
                "CANONICAL_TRADING_CALENDAR_UNAVAILABLE",
                "The Canonical trading calendar failed integrity validation.",
            )
        try:
            import pyarrow.parquet as pq

            rows = pq.read_table(path, columns=["market", "trade_date", "is_open"]).to_pylist()
        except Exception as exc:
            raise CanonicalNormalizationError(
                "CANONICAL_TRADING_CALENDAR_UNAVAILABLE",
                "The Canonical trading calendar is invalid.",
            ) from exc
        for row in rows:
            row_day = row.get("trade_date")
            if isinstance(row_day, str):
                row_day = date.fromisoformat(row_day)
            if row.get("market") == market and row_day == trading_day:
                return bool(row.get("is_open"))
        raise CanonicalNormalizationError(
            "CANONICAL_TRADING_CALENDAR_UNAVAILABLE",
            "The requested market day is absent from the Canonical trading calendar.",
        )


class CanonicalNormalizationTaskWorker:
    """Durable-task adapter for the first canonical normalization slice."""
    def __init__(self, task_control, database, *, runtime_root: Path | str = ".", canonical_repository=None, raw_repository=None, artifact_publisher=None, mapping_loader=None, trading_day_resolver: Callable[[str, date], bool] | None = None, clock=_utc_now):
        from src.repositories.platform.canonical import CanonicalRepository
        from src.repositories.platform.raw_ingestion import RawIngestionRepository
        self.task_control = task_control
        self.database = database
        self.repository = canonical_repository or CanonicalRepository()
        self.raw_repository = raw_repository or RawIngestionRepository()
        self.mapping_loader = mapping_loader
        self.artifact_publisher = artifact_publisher
        self.trading_day_resolver = trading_day_resolver
        self.normalizer = CanonicalNormalizer(runtime_root, clock=clock)

    def _load_mapping_from_registry(
        self,
        requirements: CanonicalNormalizationTaskRequirements,
    ) -> ProviderCanonicalMappingDefinition | None:
        with self.database.transaction() as session:
            return self.repository.get_mapping(
                session,
                requirements.provider_id,
                requirements.dataset_id,
                requirements.dataset_schema_version,
                requirements.mapping_version,
            )

    def _cancel_if_requested(self, lease, *, code: str) -> None:
        from src.services.platform.task_control import TaskControlError

        current = self.task_control.get_task(lease.task.task_id).task
        if current.cancel_requested_at is None:
            return
        self.task_control.acknowledge_cancel(lease.attempt.attempt_id, lease.lease_token)
        raise TaskControlError("TASK_CANCEL_PENDING", "Cancelled task cannot publish canonical data.", details={"reason_code": code})

    def _record_failure(self, lease, *, failure_code: str, retryable: bool) -> None:
        from src.services.platform.task_control import TaskControlError

        try:
            self.task_control.record_failure(
                lease.attempt.attempt_id,
                lease.lease_token,
                failure_code=failure_code,
                retryable=retryable,
            )
        except TaskControlError as exc:
            if exc.error_code != "TASK_LEASE_LOST":
                raise

    def _record_input_quality_failure(self, lease, *, failure_code: str, retryable: bool) -> None:
        """Persist an auditable input-boundary failure with the task transition."""
        from src.services.platform.task_control import TaskControlError

        report = CanonicalQualityReport(
            quality_report_id=generate_resource_id(ResourceType.QUALITY_REPORT),
            quality_status=QualityStatus.FAILED,
            rule_results={"input_boundary": "FAIL"},
            row_count=0,
            rejected_row_count=0,
            duplicate_key_count=0,
            identity_unresolved_count=0,
            identity_ambiguous_count=0,
            failure_reasons=(failure_code,),
            created_at=self.normalizer.clock(),
        )
        try:
            with self.database.transaction() as session:
                self.repository.add_quality_report(session, report)
                self.task_control.record_failure_in_session(
                    session,
                    attempt_id=lease.attempt.attempt_id,
                    lease_token=lease.lease_token,
                    failure_code=failure_code,
                    retryable=retryable,
                )
        except TaskControlError as exc:
            if exc.error_code != "TASK_LEASE_LOST":
                raise

    def _load_verified_raw(self, requirements: CanonicalNormalizationTaskRequirements) -> tuple[RawObject, bytes]:
        """Validate the storage payload, raw manifest, ProviderRun, and registry as one input boundary."""
        with self.database.transaction() as session:
            raw = self.raw_repository.get_raw_object(session, requirements.raw_object_id)
            run = self.raw_repository.get_provider_run(session, requirements.provider_run_id)
        if raw is None:
            raise CanonicalNormalizationError("CANONICAL_RAW_NOT_FOUND", "Raw object is unavailable.")
        if run is None:
            raise CanonicalNormalizationError("CANONICAL_RAW_REGISTRY_MISMATCH", "Provider run is unavailable for the Raw object.")
        if (
            raw.provider_run_id != requirements.provider_run_id
            or raw.provider_id != requirements.provider_id
            or raw.dataset_id != requirements.dataset_id
            or raw.dataset_schema_version != requirements.dataset_schema_version
            or run.provider_run_id != raw.provider_run_id
            or run.provider_id != raw.provider_id
            or run.dataset_id != raw.dataset_id
            or run.dataset_schema_version != raw.dataset_schema_version
            or raw.raw_object_id not in run.raw_object_refs
        ):
            raise CanonicalNormalizationError("CANONICAL_RAW_REGISTRY_MISMATCH", "Raw registry bindings are inconsistent.")
        try:
            payload_path = self.normalizer.resolver.resolve(raw.storage_ref, require_exists=True)
            namespace_root = self.normalizer.resolver.namespace_root(raw.storage_ref.storage_namespace)
            manifest_path = payload_path.parent / "manifest.json"
            manifest_relative_path = manifest_path.relative_to(namespace_root).as_posix()
            self.normalizer.resolver.resolve(
                manifest_relative_path,
                namespace=raw.storage_ref.storage_namespace,
                require_exists=True,
            )
            manifest = RawObject.model_validate(json.loads(manifest_path.read_bytes()))
        except CanonicalNormalizationError:
            raise
        except Exception as exc:
            raise CanonicalNormalizationError("CANONICAL_RAW_MANIFEST_INVALID", "Raw object manifest is invalid.") from exc
        if manifest != raw or payload_path.parent != manifest_path.parent:
            raise CanonicalNormalizationError("CANONICAL_RAW_REGISTRY_MISMATCH", "Raw manifest does not match the registry record.")
        try:
            content = payload_path.read_bytes()
        except OSError as exc:
            raise CanonicalNormalizationError("CANONICAL_RAW_INTEGRITY_FAILED", "Raw object could not be read.") from exc
        if len(content) != raw.byte_count or compute_bytes_hash(content) != raw.raw_content_hash:
            raise CanonicalNormalizationError("CANONICAL_RAW_INTEGRITY_FAILED", "Raw object integrity validation failed.")
        return raw, content

    def execute(self, lease, *, mapping=None, identity_resolver=None) -> CanonicalNormalizationTaskResult:
        from src.services.platform.task_control import TaskControlError

        if lease.task.task_type != "canonical_normalization":
            raise TaskControlError("TASK_TYPE_UNSUPPORTED", "Worker does not support this task type.", status_code=422)
        self.task_control.start_attempt(lease.attempt.attempt_id, lease.lease_token)
        try:
            self._cancel_if_requested(lease, code="CANONICAL_CANCELLED_BEFORE_INPUT")
            requirements = CanonicalNormalizationTaskRequirements.model_validate(lease.task.requirements)
            mapping = mapping or (
                self.mapping_loader(requirements)
                if self.mapping_loader is not None
                else self._load_mapping_from_registry(requirements)
            )
            if mapping is None:
                raise CanonicalNormalizationError("CANONICAL_MAPPING_UNAVAILABLE", "Canonical mapping is unavailable.")
            if (
                mapping.provider_id != requirements.provider_id
                or mapping.dataset_id != requirements.dataset_id
                or mapping.dataset_schema_version != requirements.dataset_schema_version
                or mapping.mapping_version != requirements.mapping_version
            ):
                raise CanonicalNormalizationError("CANONICAL_MAPPING_BINDING_INVALID", "Canonical mapping does not match task requirements.")
            raw, content = self._load_verified_raw(requirements)
            if identity_resolver is None and requirements.dataset_id in {"security_master", "bar_1d_raw", "instrument_status_daily", "listing_status_history", "corporate_action", "financial_statement"}:
                identity_bridge = CanonicalIdentityBridge(
                    self.database,
                    mapping=mapping,
                    raw=raw,
                    clock=self.normalizer.clock,
                )
                identity_resolver = (
                    identity_bridge.provision_security_master
                    if requirements.dataset_id == "security_master"
                    else identity_bridge.resolve_provider_alias
                )
            try:
                payload = json.loads(content.decode("utf-8"))
                rows = payload if isinstance(payload, list) else payload.get("rows", payload)
                if isinstance(rows, dict):
                    rows = [rows]
                if not isinstance(rows, list) or not all(isinstance(item, Mapping) for item in rows):
                    raise ValueError("raw payload must contain object rows")
            except Exception as exc:
                raise CanonicalNormalizationError("CANONICAL_RAW_PAYLOAD_INVALID", "Raw object payload is invalid.") from exc
            partition, report, output = self.normalizer.normalize_rows(
                raw_object_id=raw.raw_object_id,
                provider_run_id=raw.provider_run_id,
                provider_id=requirements.provider_id,
                dataset_id=requirements.dataset_id,
                dataset_schema_version=requirements.dataset_schema_version,
                provider_policy_version=requirements.provider_policy_version,
                mapping=mapping,
                rows=list(rows),
                partition_key=requirements.partition_key,
                identity_resolver=identity_resolver,
                is_trading_day=(
                    self.trading_day_resolver
                    if self.trading_day_resolver is not None
                    else CanonicalTradingDayResolver(
                        self.database,
                        storage_resolver=self.normalizer.resolver,
                        repository=self.repository,
                    )
                    if requirements.dataset_id == "bar_1d_raw"
                    else None
                ),
                market=requirements.market,
                task_id=lease.task.task_id,
                attempt_id=lease.attempt.attempt_id,
            )
            if partition is None:
                with self.database.transaction() as session:
                    self.repository.add_quality_report(session, report)
                    self.task_control.record_failure_in_session(
                        session,
                        attempt_id=lease.attempt.attempt_id,
                        lease_token=lease.lease_token,
                        failure_code=report.failure_reasons[0] if report.failure_reasons else "CANONICAL_QUALITY_FAILED",
                        retryable=False,
                    )
                return CanonicalNormalizationTaskResult(
                    task_id=lease.task.task_id,
                    attempt_id=lease.attempt.attempt_id,
                    quality_report=report,
                    published=False,
                    failure_code=report.failure_reasons[0] if report.failure_reasons else "CANONICAL_QUALITY_FAILED",
                )
            self._cancel_if_requested(lease, code="CANONICAL_CANCELLED_BEFORE_PUBLISH")
            self.normalizer.publish_partition(partition, report, output)
            if self.artifact_publisher is not None:
                artifact_id = generate_resource_id(ResourceType.ARTIFACT)
                request = ArtifactPublishRequest(
                    artifact_id=artifact_id,
                    artifact_type="canonical_partition",
                    owner_resource_ref=ResourceRef(resource_type=ResourceType.TASK, resource_id=lease.task.task_id),
                    attempt_id=lease.attempt.attempt_id,
                    payload_filename="partition.parquet",
                    media_type="application/vnd.apache.parquet",
                    expected_size_bytes=len(output),
                    schema_version=requirements.dataset_schema_version,
                    retention_class=RetentionClass.PINNED,
                    visibility=ArtifactVisibility.OWNER,
                )

                def register(session, _record):
                    self.repository.add_quality_report(session, report)
                    self.repository.add_partition(session, partition)
                    self.task_control.complete_with_artifact_in_session(
                        session,
                        attempt_id=lease.attempt.attempt_id,
                        lease_token=lease.lease_token,
                        artifact_id=artifact_id,
                    )

                self.artifact_publisher.publish(request, output, after_register=register)
            else:
                with self.database.transaction() as session:
                    self.repository.add_quality_report(session, report)
                    self.repository.add_partition(session, partition)
                    self.task_control.complete_in_session(
                        session,
                        attempt_id=lease.attempt.attempt_id,
                        lease_token=lease.lease_token,
                    )
            return CanonicalNormalizationTaskResult(
                task_id=lease.task.task_id,
                attempt_id=lease.attempt.attempt_id,
                canonical_partition=partition,
                quality_report=report,
                published=True,
            )
        except TaskControlError:
            raise
        except CanonicalNormalizationError as exc:
            self._record_input_quality_failure(
                lease,
                failure_code=exc.error_code,
                retryable=exc.error_code in {"CANONICAL_ATOMIC_PUBLISH_FAILED"},
            )
            raise
        except Exception:
            self._record_failure(lease, failure_code="CANONICAL_NORMALIZATION_FAILED", retryable=True)
            raise


# Compatibility aliases used by the platform service export surface.
CanonicalNormalizationService = CanonicalNormalizer
ProviderCanonicalMapper = CanonicalNormalizer

__all__ = ["CanonicalNormalizationError", "CanonicalNormalizer", "CanonicalNormalizationTaskWorker", "CanonicalNormalizationService", "ProviderCanonicalMapper", "compute_schema_hash", "deterministic_manifest_hash"]
