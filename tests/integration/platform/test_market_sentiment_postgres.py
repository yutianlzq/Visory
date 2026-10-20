from dataclasses import replace

import pytest

from src.repositories.platform import FeatureRepository, upgrade_database
from src.schemas.platform import ConsumerRequirement, FeatureBundle
from src.services.platform.feature_store import FeatureStore, FeaturePublicationError
from src.services.platform.market_sentiment import PREFIX, evaluate_market_days
from tests.platform.test_market_sentiment import market_day, publish_market, complete_score_fixture


def test_market_restricted_database_publication_consumer_and_correction(isolated_postgres_database, tmp_path):
    db = isolated_postgres_database
    upgrade_database(db.engine)
    batch = evaluate_market_days([market_day()])[0]
    store = FeatureStore(tmp_path, database=db, clock=lambda: batch.rows[0].available_at)
    # 受限真实路径与完整隔离评分 fixture 分开验收，不认证缺失的市场能力。
    roots = [PREFIX + "limit.limit_up_down_spread", PREFIX + "audit.listed_count"]
    plan, old, bundle = publish_market(store, batch, roots)
    fresh = FeatureStore(tmp_path, database=db, clock=lambda: batch.rows[0].available_at)
    requirement = ConsumerRequirement(
        consumer_id="preview",
        consumer_kind="PREVIEW",
        required_capabilities=("market_emotion",),
        accepted_publication_statuses=("PROVISIONAL",),
        allow_provisional=True,
        min_quality_status="PARTIAL",
    )
    assert fresh.consume_bundle(bundle.feature_bundle_id, requirement) == bundle
    with db.transaction() as session:
        assert FeatureRepository.get_snapshot(session, old.feature_snapshot_id) == old
    datasets = {name: [dict(row) for row in observations] for name, observations in market_day().datasets.items()}
    from decimal import Decimal

    datasets["bar_1d_raw"][0]["close"] = Decimal(9)
    corrected_batch = evaluate_market_days([replace(market_day(), datasets=datasets)])[0]
    assert corrected_batch.manifest.universe_scope_hash == batch.manifest.universe_scope_hash
    correction_ids = {
        instance: next(
            ref.feature_partition_id for ref in old.feature_partition_refs if ref.indicator_id == instance.indicator_id
        )
        for instance in plan.ordered_instances
    }
    _, new, _ = publish_market(
        fresh,
        corrected_batch,
        roots,
        correction_of_snapshot_id=old.feature_snapshot_id,
        correction_of_partition_ids=correction_ids,
    )
    assert new.revision == 2 and new.supersedes_id == old.feature_snapshot_id
    assert fresh.published_bundle(bundle.feature_bundle_id) == bundle
    for ref in old.feature_partition_refs:
        assert fresh.read_partition_payload(ref.feature_partition_id)
    formal = ConsumerRequirement(
        consumer_id="paper",
        consumer_kind="FORMAL_BACKTEST",
        required_capabilities=("backtest_core", "market_emotion"),
        accepted_publication_statuses=("CERTIFIED",),
    )
    with pytest.raises(FeaturePublicationError, match="capability"):
        fresh.consume_bundle(bundle.feature_bundle_id, formal)


def test_repository_cannot_certify_market_or_bind_formal_bundle(isolated_postgres_database, tmp_path):
    db = isolated_postgres_database
    upgrade_database(db.engine)
    batch = evaluate_market_days([market_day()])[0]
    _, snapshot, bundle = publish_market(
        FeatureStore(tmp_path, database=db, clock=lambda: batch.rows[0].available_at), batch
    )
    forged = type(snapshot).build(
        **(
            {key: value for key, value in snapshot.model_dump().items() if key != "manifest_hash"}
            | {"certified_capabilities": ("market_emotion",), "missing_capabilities": ("market_breadth",)}
        )
    )
    with pytest.raises(ValueError, match="capability"):
        with db.transaction() as session:
            FeatureRepository.add_snapshot(session, forged)
    formal = FeatureBundle.build(
        **(
            {key: value for key, value in bundle.model_dump().items() if key != "bundle_hash"}
            | {"consumer_kind": "FORMAL_BACKTEST"}
        )
    )
    with pytest.raises(ValueError, match="capability"):
        with db.transaction() as session:
            FeatureRepository.add_bundle(session, formal)
    with db.transaction() as session:
        assert FeatureRepository.get_bundle(session, bundle.feature_bundle_id) == bundle


def test_existing_database_identifier_limit_is_fail_closed_without_migration(isolated_postgres_database, tmp_path):
    db = isolated_postgres_database
    upgrade_database(db.engine, "0013_wp0302_feature_store")
    plan, rows, _, source = complete_score_fixture()
    store = FeatureStore(tmp_path, database=db, fixture_only=True, clock=lambda: plan.cutoff_at)
    with pytest.raises(ValueError, match="existing PostgreSQL indicator_id limit"):
        store.materialize_and_publish(
            plan,
            rows,
            data_snapshot_ids=(source,),
            cutoff_at=plan.cutoff_at,
            as_of_trade_date=rows[plan.ordered_instances[0]][-1].trade_date,
            consumer_ref="fixture",
        )
    assert not list(tmp_path.rglob("*.parquet"))
