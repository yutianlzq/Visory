from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from src.schemas.platform import (
    BenchmarkIndexBar,
    CapabilityCertification,
    DataSnapshot,
    SnapshotCapabilityStatus,
    SnapshotPublicationStatus,
    compute_snapshot_manifest_hash,
)
from src.services.platform.snapshot import SnapshotCapabilityEngine


GOLDEN = Path(__file__).resolve().parents[1] / "golden" / "platform" / "contracts" / "success" / "data-snapshot.json"
CORE_DATASETS = ("security_master", "trading_calendar", "bar_1d_raw", "benchmark_index_1d")
NOW = datetime(2026, 8, 31, 9, tzinfo=timezone.utc)


def _load_snapshot() -> DataSnapshot:
    return DataSnapshot.model_validate(json.loads(GOLDEN.read_text(encoding="utf-8"))["payload"])


def _core_snapshot() -> DataSnapshot:
    source = _load_snapshot()
    base = source.canonical_partitions[0]
    partitions = tuple(
        base.model_copy(
            update={
                "canonical_partition_id": f"cpart_019dbd74-2a00-7000-8000-{105 + index:012d}",
                "quality_report_id": f"quality_019dbd74-2a00-7000-8000-{105 + index:012d}",
                "dataset_id": dataset_id,
                "partition_key": f"{dataset_id}:2026-08-31",
            }
        )
        for index, dataset_id in enumerate(CORE_DATASETS)
    )
    by_dataset = {item.dataset_id: item for item in partitions}
    draft = source.model_copy(
        update={
            "canonical_partitions": partitions,
            "security_master_ref": by_dataset["security_master"].canonical_partition_id,
            "calendar_ref": by_dataset["trading_calendar"].canonical_partition_id,
            "quality_report_refs": tuple(item.quality_report_id for item in partitions),
            "publication_status": SnapshotPublicationStatus.CERTIFIED,
            "published_at": source.created_at,
            "certified_capabilities": (),
            "missing_capabilities": (),
        }
    )
    return DataSnapshot.model_validate({**draft.model_dump(mode="python"), "manifest_hash": compute_snapshot_manifest_hash(draft)})


def _valid_rows(snapshot: DataSnapshot) -> dict[str, list[dict[str, object]]]:
    trade_date = snapshot.trade_date
    available_at = snapshot.cutoff_at
    return {
        "security_master": [{"trade_date": trade_date, "available_at": available_at}],
        "trading_calendar": [{"trade_date": trade_date, "is_open": True, "available_at": available_at}],
        "bar_1d_raw": [
            {
                "entity_key": "stock:cn:600519.SH",
                "trade_date": trade_date,
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.5,
                "available_at": available_at,
            }
        ],
        "benchmark_index_1d": [
            {
                "benchmark_id": "index:cn:000300.SH",
                "asset_type": "index",
                "trade_date": trade_date,
                "open": 3900.0,
                "high": 3950.0,
                "low": 3880.0,
                "close": 3940.0,
                "return_type": "TOTAL_RETURN",
                "total_return_close": 3980.0,
                "available_at": available_at,
            }
        ],
    }


def _backtest_certification(snapshot: DataSnapshot, rows: dict[str, list[dict[str, object]]]):
    return next(
        item
        for item in SnapshotCapabilityEngine.certify(snapshot, now=NOW, partition_rows=rows)
        if item.capability_id == "backtest_core"
    )


def test_complete_benchmark_contract_allows_backtest_core_certification() -> None:
    snapshot = _core_snapshot()

    certification = _backtest_certification(snapshot, _valid_rows(snapshot))

    assert certification.capability_status is SnapshotCapabilityStatus.CERTIFIED
    assert certification.snapshot_id == snapshot.snapshot_id


def test_backtest_core_rejects_stock_shaped_benchmark_rows() -> None:
    snapshot = _core_snapshot()
    rows = _valid_rows(snapshot)
    rows["benchmark_index_1d"][0]["asset_type"] = "stock"

    certification = _backtest_certification(snapshot, rows)

    assert certification.capability_status is SnapshotCapabilityStatus.UNAVAILABLE
    assert certification.reason_code == "SNAPSHOT_BENCHMARK_CONTRACT_INVALID"


def test_backtest_core_rejects_total_return_benchmark_without_total_return_close() -> None:
    snapshot = _core_snapshot()
    rows = _valid_rows(snapshot)
    rows["benchmark_index_1d"][0].pop("total_return_close")

    certification = _backtest_certification(snapshot, rows)

    assert certification.capability_status is SnapshotCapabilityStatus.UNAVAILABLE
    assert certification.reason_code == "SNAPSHOT_BENCHMARK_CONTRACT_INVALID"


def test_backtest_core_requires_open_calendar_dates_to_match_price_and_benchmark_dates() -> None:
    snapshot = _core_snapshot()
    rows = _valid_rows(snapshot)
    rows["trading_calendar"][0]["trade_date"] = date(2026, 8, 28)

    certification = _backtest_certification(snapshot, rows)

    assert certification.capability_status is SnapshotCapabilityStatus.UNAVAILABLE
    assert certification.reason_code == "SNAPSHOT_DATE_RANGE_CONFLICT"


def test_backtest_core_rejects_multiple_benchmark_ids_or_return_modes() -> None:
    snapshot = _core_snapshot()
    rows = _valid_rows(snapshot)
    rows["benchmark_index_1d"].append(
        {
            **rows["benchmark_index_1d"][0],
            "benchmark_id": "index:cn:000905.SH",
            "return_type": "PRICE",
            "total_return_close": None,
        }
    )

    certification = _backtest_certification(snapshot, rows)

    assert certification.capability_status is SnapshotCapabilityStatus.UNAVAILABLE
    assert certification.reason_code == "SNAPSHOT_BENCHMARK_CONTRACT_CONFLICT"


def test_capability_certification_must_be_bound_to_a_snapshot() -> None:
    with pytest.raises(ValueError, match="snapshot_id"):
        CapabilityCertification(
            capability_id="backtest_core",
            capability_status=SnapshotCapabilityStatus.CERTIFIED,
            evidence_refs=("quality_019dbd74-2a00-7000-8000-000000000006",),
            certified_at=NOW,
        )


def test_snapshot_references_must_point_to_its_partitions_and_quality_reports() -> None:
    snapshot = _core_snapshot()
    broken = snapshot.model_copy(
        update={
            "security_master_ref": "cpart_019dbd74-2a00-7000-8000-999999999999",
        }
    )

    with pytest.raises(ValueError, match="security_master_ref"):
        DataSnapshot.model_validate({**broken.model_dump(mode="python"), "manifest_hash": compute_snapshot_manifest_hash(broken)})

    broken_quality = snapshot.model_copy(
        update={
            "quality_report_refs": ("quality_019dbd74-2a00-7000-8000-999999999999",),
        }
    )
    with pytest.raises(ValueError, match="quality_report_refs"):
        DataSnapshot.model_validate(
            {**broken_quality.model_dump(mode="python"), "manifest_hash": compute_snapshot_manifest_hash(broken_quality)}
        )


def test_benchmark_contract_requires_explicit_asset_type_field() -> None:
    row = _valid_rows(_core_snapshot())["benchmark_index_1d"][0]
    row.pop("asset_type")

    with pytest.raises(ValueError, match="asset_type"):
        BenchmarkIndexBar.model_validate(row)
