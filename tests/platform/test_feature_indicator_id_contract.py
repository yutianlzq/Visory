from datetime import date

import pytest
from pydantic import ValidationError

from src.schemas.platform import FeaturePartition, FeaturePartitionRef, FeatureRow, compute_content_hash
from src.schemas.platform.indicator import FeatureInstance, FeatureInstanceKey, IndicatorDefinition, IndicatorDependencyRef
from src.services.platform.indicator_registry import F1_INDICATOR_DEFINITIONS, F2_INDICATOR_DEFINITIONS
from src.repositories.platform.feature import feature_partition, feature_snapshot_partition_ref, feature_bundle_partition_ref
from tests.integration.platform.test_feature_repository import _records
from tests.platform.test_feature_store_contracts import _row, _instance
from tests.platform.test_indicator_registry import _definition

LONG_IDS = (
    'market.sentiment.normalized.risk_appetite.small_large_return_spread',
    'market.sentiment.normalized.risk_appetite.top_amount20_median_return',
    'market.sentiment.normalized.risk_appetite.high_turnover_return_spread',
)


def _contracts(indicator_id):
    partition, _, _ = _records()
    return (
        (FeatureRow, _row('cn.stock:000001', date(2026, 1, 3)).model_dump()),
        (FeaturePartition, partition.model_dump()),
        (FeaturePartitionRef, FeaturePartitionRef.from_partition(partition).model_dump()),
        (FeatureInstanceKey, _instance().model_dump()),
        (FeatureInstance, {'indicator_id': indicator_id}),
        (IndicatorDependencyRef, {'indicator_id': indicator_id}),
        (IndicatorDefinition, _definition(indicator_id=indicator_id).model_dump(exclude={'definition_hash'})),
    )


@pytest.mark.parametrize('indicator_id', ['x' * 64, 'x' * 65, *LONG_IDS, 'x' * 128])
def test_indicator_id_boundaries_are_shared_by_all_contracts(indicator_id):
    for model, payload in _contracts(indicator_id):
        record = model.model_validate(payload | {'indicator_id': indicator_id})
        assert record.indicator_id == indicator_id
        assert model.model_json_schema()['properties']['indicator_id']['maxLength'] == 128


@pytest.mark.parametrize('model', [FeatureRow, FeaturePartition, FeaturePartitionRef, FeatureInstanceKey,
                                  FeatureInstance, IndicatorDependencyRef, IndicatorDefinition])
def test_feature_contracts_reject_129_character_ids(model):
    payload = next(payload for item, payload in _contracts('moving_average') if item is model)
    with pytest.raises(ValidationError):
        model.model_validate(payload | {'indicator_id': 'x' * 129})


def test_only_indicator_columns_expand_in_feature_metadata():
    for table in (feature_partition, feature_snapshot_partition_ref, feature_bundle_partition_ref):
        assert table.c.indicator_id.type.length == 128
        assert table.c.feature_partition_id.type.length == 64
        assert table.c.definition_version.type.length == 32


def test_original_f1_and_f2_definition_payloads_versions_and_hashes_are_unchanged():
    assert len(F1_INDICATOR_DEFINITIONS) == 14
    assert len(F2_INDICATOR_DEFINITIONS) == 65
    assert compute_content_hash({k: v.model_dump(mode='json') for k, v in F1_INDICATOR_DEFINITIONS.items()}) == (
        'sha256:e65941d7c70b0e490ac95526a26c2baaafb9ecdf7ce73511156b72bb3a8a1d23'
    )
    assert compute_content_hash({k: v.model_dump(mode='json') for k, v in F2_INDICATOR_DEFINITIONS.items()}) == (
        'sha256:028758764bcb833e8231027db3b9f06dd9322596a9c1c0a291d18ad2871a858b'
    )


@pytest.mark.parametrize('width', [255, 256, 386])
def test_partition_key_schema_and_metadata_share_authorized_length(width):
    partition, _, _ = _records()
    record = FeaturePartition.model_validate(partition.model_dump() | {'partition_key': 'k' * width})
    assert record.partition_key == 'k' * width
    assert FeaturePartition.model_json_schema()['properties']['partition_key']['maxLength'] == 386
    assert feature_partition.c.partition_key.type.length == 386


def test_partition_key_contract_rejects_387():
    partition, _, _ = _records()
    with pytest.raises(ValidationError):
        FeaturePartition.model_validate(partition.model_dump() | {'partition_key': 'k' * 387})
