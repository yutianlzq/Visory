"""Independent process consumption of isolated synthetic WP-0303 publications."""

from dataclasses import asdict, replace
from datetime import date
from decimal import Decimal
import json
from pathlib import Path
import re
import subprocess
import sys

from src.repositories.platform import upgrade_database
from src.services.platform.feature_store import FeatureStore
from src.services.platform.market_sentiment import PREFIX, evaluate_market_days
from tests.platform.test_market_sentiment import (
    complete_score_fixture, market_day, publish_market,
)


_RESTART = r'''
import hashlib, io, json, os, pathlib, re, sys
import pyarrow.parquet as pq
from src.repositories.platform import PostgresDatabase, PostgresSettings
from src.schemas.platform import ConsumerRequirement, FeatureBundle, FeatureSnapshot
from src.services.platform.feature_store import FeatureStore, FeaturePublicationError

context = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
assert os.getpid() != context["parent_pid"]
settings = context["settings"]
assert settings["host"] == "127.0.0.1"
assert re.fullmatch(r"visory_test_[0-9a-f]{20}", settings["database"])
settings["password_file"] = pathlib.Path(settings["password_file"])
db = PostgresDatabase.from_settings(PostgresSettings(**settings))
try:
    store = FeatureStore(context["root"], database=db, fixture_only=context["fixture_only"])
    preview = ConsumerRequirement(
        consumer_id="independent_process_preview", consumer_kind="PREVIEW",
        required_capabilities=("market_emotion",), allow_provisional=True,
        accepted_publication_statuses=("PROVISIONAL",), min_quality_status="PARTIAL",
    )
    verified = 0
    for item in context["publications"]:
        expected_bundle = FeatureBundle.model_validate(item["bundle"])
        expected_snapshot = FeatureSnapshot.model_validate(item["snapshot"])
        assert store.consume_bundle(expected_bundle.feature_bundle_id, preview) == expected_bundle
        assert store.published_snapshot(expected_snapshot.feature_snapshot_id) == expected_snapshot
        assert expected_snapshot.certified_capabilities == ()
        assert expected_snapshot.missing_capabilities == ("market_breadth", "market_emotion")
        for ref in expected_bundle.required_partition_refs:
            payload = store.read_partition_payload(ref.feature_partition_id)
            assert "sha256:" + hashlib.sha256(payload).hexdigest() == ref.partition_hash
            # 同步读取并关闭单个 Parquet 文件，避免 Dataset 后台线程越过进程退出。
            with pq.ParquetFile(io.BytesIO(payload)) as parquet:
                table = parquet.read()
            assert table.num_rows == store.published_partition(ref.feature_partition_id).row_count
            verified += 1
        for consumer in ("formal", "paper"):
            formal = ConsumerRequirement(
                consumer_id=consumer, consumer_kind="FORMAL_BACKTEST",
                required_capabilities=("backtest_core", "market_emotion"),
                accepted_publication_statuses=("CERTIFIED",),
            )
            try:
                store.consume_bundle(expected_bundle.feature_bundle_id, formal)
            except FeaturePublicationError as exc:
                assert "capability" in str(exc)
            else:
                raise AssertionError("synthetic market publication unlocked Formal/Paper")
    print(json.dumps({"pid": os.getpid(), "verified_partition_reads": verified}))
finally:
    db.close()
'''


def _independent_restart(db, root, publications, *, fixture_only):
    import os

    assert db.settings.host == "127.0.0.1"
    assert re.fullmatch(r"visory_test_[0-9a-f]{20}", db.settings.database)
    settings = asdict(db.settings)
    settings["password_file"] = str(settings["password_file"])
    context = root.parent / (root.name + "-restart.json")
    context.write_text(json.dumps({
        "parent_pid": os.getpid(), "settings": settings, "root": str(root),
        "fixture_only": fixture_only,
        "publications": [
            {"snapshot": snapshot.model_dump(mode="json"), "bundle": bundle.model_dump(mode="json")}
            for snapshot, bundle in publications
        ],
    }), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "-c", _RESTART, str(context)],
        cwd=Path(__file__).resolve().parents[3], capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    output = json.loads(result.stdout)
    assert output["pid"] != os.getpid()
    assert output["verified_partition_reads"] == sum(
        len(bundle.required_partition_refs) for _, bundle in publications
    )


def test_restricted_calculation_fixed_publication_correction_survives_process_exit(
    isolated_postgres_database, tmp_path,
):
    db = isolated_postgres_database
    upgrade_database(db.engine)
    day = market_day()
    batch = evaluate_market_days((day,))[0]
    root = tmp_path / "restricted-synthetic-input"
    store = FeatureStore(root, database=db, clock=lambda: day.cutoff_at)
    roots = (PREFIX + "limit.limit_up_down_spread", PREFIX + "audit.listed_count")
    plan, old, old_bundle = publish_market(store, batch, roots)
    _independent_restart(db, root, ((old, old_bundle),), fixture_only=False)
    old_bytes = {ref.feature_partition_id: store.read_partition_payload(ref.feature_partition_id)
                 for ref in old.feature_partition_refs}
    datasets = {name: [dict(row) for row in rows] for name, rows in day.datasets.items()}
    datasets["bar_1d_raw"][0]["close"] = Decimal(9)
    corrected = evaluate_market_days((replace(day, datasets=datasets),))[0]
    predecessors = {instance: next(ref.feature_partition_id for ref in old.feature_partition_refs
                                  if ref.indicator_id == instance.indicator_id)
                    for instance in plan.ordered_instances}
    _, new, new_bundle = publish_market(
        store, corrected, roots, correction_of_snapshot_id=old.feature_snapshot_id,
        correction_of_partition_ids=predecessors,
    )
    assert new.revision == 2 and new.supersedes_id == old.feature_snapshot_id
    _independent_restart(db, root, ((old, old_bundle), (new, new_bundle)), fixture_only=False)
    assert all(store.read_partition_payload(key) == payload for key, payload in old_bytes.items())


def test_complete_score_fixture_tail_correction_survives_independent_process(
    isolated_postgres_database, tmp_path,
):
    db = isolated_postgres_database
    upgrade_database(db.engine)
    plan, rows, original, source = complete_score_fixture()
    _, revised_rows, revised, _ = complete_score_fixture(correction=True)
    assert original[:60] == revised[:60]
    assert all(original[index].smoothed != revised[index].smoothed for index in range(60, 65))
    assert original[60].state != revised[60].state
    root = tmp_path / "complete-score-fixture-only"
    store = FeatureStore(root, database=db, fixture_only=True, clock=lambda: plan.cutoff_at)
    args = dict(data_snapshot_ids=(source,), cutoff_at=plan.cutoff_at,
                as_of_trade_date=date(2026, 3, 6), consumer_ref="synthetic_closeout")
    old, old_bundle = store.materialize_and_publish(plan, rows, **args)
    _independent_restart(db, root, ((old, old_bundle),), fixture_only=True)
    old_bytes = {ref.feature_partition_id: store.read_partition_payload(ref.feature_partition_id)
                 for ref in old.feature_partition_refs}
    predecessors = {instance: next(ref.feature_partition_id for ref in old.feature_partition_refs
                                  if ref.indicator_id == instance.indicator_id)
                    for instance in plan.ordered_instances}
    new, new_bundle = store.materialize_and_publish(
        plan, revised_rows, correction_of_snapshot_id=old.feature_snapshot_id,
        correction_of_partition_ids=predecessors, **args,
    )
    assert new.revision == 2 and new.supersedes_id == old.feature_snapshot_id
    _independent_restart(db, root, ((old, old_bundle), (new, new_bundle)), fixture_only=True)
    assert all(store.read_partition_payload(key) == payload for key, payload in old_bytes.items())
