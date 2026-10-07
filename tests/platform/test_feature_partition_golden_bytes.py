from __future__ import annotations

import json
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.schemas.platform import (
    FeatureMaterializationError,
    FeaturePartition,
    FeatureRow,
    ResourceType,
    StorageBackend,
    StorageNamespace,
    StorageRef,
    generate_resource_id,
)

UTC = timezone.utc
GOLDEN = Path(__file__).resolve().parents[1] / "golden" / "platform" / "contracts" / "success"


def test_feature_partition_golden_hash_and_size_are_real_parquet_evidence() -> None:
    payload = json.loads((GOLDEN / "feature-partition.json").read_text(encoding="utf-8"))["payload"]
    row = FeatureRow(
        entity_key="cn.stock:000001",
        trade_date=date(2026, 1, 3),
        indicator_id="moving_average",
        definition_version="1.0.0",
        value=Decimal("1.20"),
        value_type="decimal",
        unit="cny_per_share",
        available_at=datetime(2026, 1, 3, 17, 30, tzinfo=UTC),
        data_snapshot_id=payload["data_snapshot_ids"][0],
        calculation_run_id="golden-run",
    )
    bytes_one = FeaturePartition.parquet_bytes((row,))
    bytes_two = FeaturePartition.parquet_bytes((row,))
    assert bytes_one == bytes_two
    assert len(bytes_one) == payload["storage_ref"]["size_bytes"]
    assert FeaturePartition.compute_hash((row,)) == payload["partition_hash"]
    assert payload["storage_ref"]["content_hash"] == payload["partition_hash"]


def test_feature_partition_parquet_serializer_rejects_duplicate_keys() -> None:
    row = FeatureRow(
        entity_key="cn.stock:000001",
        trade_date=date(2026, 1, 3),
        indicator_id="moving_average",
        definition_version="1.0.0",
        value=Decimal("1.20"),
        value_type="decimal",
        unit="cny_per_share",
        available_at=datetime(2026, 1, 3, 17, 30, tzinfo=UTC),
        data_snapshot_id=generate_resource_id(
            ResourceType.DATA_SNAPSHOT,
            timestamp_ms=1_700_000_000_000,
            random_bits=1,
        ),
        calculation_run_id="golden-run",
    )
    with pytest.raises(FeatureMaterializationError, match="duplicate"):
        FeaturePartition.parquet_bytes((row, row))


def test_feature_partition_contract_rejects_untyped_snapshot_ids_and_invalid_quality_threshold() -> None:
    payload = json.loads((GOLDEN / "feature-partition.json").read_text(encoding="utf-8"))["payload"]
    with pytest.raises(ValidationError, match="data_snapshot_ids"):
        FeaturePartition.model_validate(payload | {"data_snapshot_ids": ("not-a-data-snapshot",)})

    row = FeatureRow(
        entity_key="cn.stock:000001",
        trade_date=date(2026, 1, 3),
        indicator_id="moving_average",
        definition_version="1.0.0",
        value=Decimal("1.20"),
        value_type="decimal",
        unit="cny_per_share",
        available_at=datetime(2026, 1, 3, 17, 30, tzinfo=UTC),
        data_snapshot_id=payload["data_snapshot_ids"][0],
        calculation_run_id="golden-run",
    )
    with pytest.raises(FeatureMaterializationError, match="min_coverage_ratio"):
        FeaturePartition.build_from_rows(
            (row,),
            partition_id=generate_resource_id(ResourceType.FEATURE_PARTITION, timestamp_ms=1_700_000_000_000, random_bits=22),
            data_snapshot_ids=(payload["data_snapshot_ids"][0],),
            partition_key="2026-01-03",
            storage_ref=StorageRef(
                storage_backend=StorageBackend.LOCAL_FS,
                storage_namespace=StorageNamespace.APP,
                relative_path="features/threshold.parquet",
                content_hash=FeaturePartition.compute_hash((row,)),
                media_type="application/vnd.apache.parquet",
                size_bytes=len(FeaturePartition.parquet_bytes((row,))),
            ),
            quality_report_id=generate_resource_id(ResourceType.QUALITY_REPORT, timestamp_ms=1_700_000_000_000, random_bits=23),
            cutoff_at=datetime(2026, 1, 3, 18, 0, tzinfo=UTC),
            created_at=datetime(2026, 1, 3, 18, 0, tzinfo=UTC),
            min_coverage_ratio=Decimal("1.1"),
        )
