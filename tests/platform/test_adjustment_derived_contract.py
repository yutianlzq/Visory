from __future__ import annotations

import hashlib
import json
import subprocess
from functools import lru_cache
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.schemas.platform import (
    PLATFORM_CONTRACTS, CanonicalPartition, CanonicalQualityReport, DataSnapshot,
    ProviderRun, RawObject, SnapshotPartitionRef, compute_content_hash,
)
from src.schemas.platform.adjustment import (
    AdjustmentMethod, MethodRef, SnapshotInputRef, SourceRootRef, QualityEvidenceRef,
    AdjustmentCoverageReceipt, AdjustmentLineage, AdjustmentEventRef,
    DerivedCanonicalPartition, DerivedDataSnapshot, parse_snapshot_contract,
    parse_partition_contract, validate_adjustment_references,
)
from src.services.platform.indicator_registry import F1_INDICATOR_DEFINITIONS, F2_INDICATOR_DEFINITIONS
from src.schemas.platform.adjustment_calculation import FixtureAction, semantic_hash
from src.services.platform.adjustment_calculation import bridge_fixture_execution, verify_fixture_execution_bridge
from src.services.platform.provider_source_routes import build_fixture_provider_source_route

ROOT = Path(__file__).resolve().parents[2]
GOLDEN = ROOT / "tests/golden/platform/contracts/success"
NOW = datetime(2026, 8, 31, 8, tzinfo=timezone.utc)
H = "sha256:" + "1" * 64
ROLES = ("bar_1d_raw", "corporate_action", "security_master", "trading_calendar")
PRE_CONVERGENCE_MAIN = "efe8e9b362cba13eca183c55be57bbbbc832b60b"
REVIEWED_MAIN = "0d4d5bb6b67c391a5c6b18ff6480d61eaffedc47"


@lru_cache
def _git_bytes(revision, path):
    return subprocess.check_output(["git", "show", f"{revision}:{path}"], cwd=ROOT)


def _undo_reviewed_main_delta(old, main, current):
    if old == main:
        return current
    if isinstance(old, dict) and isinstance(main, dict):
        restored = dict(current)
        for key in old.keys() | main.keys():
            if key not in old:
                assert current[key] == main[key], key
                restored.pop(key)
            elif key not in main:
                assert key not in current, key
                restored[key] = old[key]
            else:
                restored[key] = _undo_reviewed_main_delta(old[key], main[key], current[key])
        return restored
    assert current == main
    return old


def _historical_compatibility_bytes(path, *, current=None):
    """Validate reviewed main first, then reconstruct only its already accepted delta."""
    if current is None:
        current = (ROOT / path).read_bytes()
    old = _git_bytes(PRE_CONVERGENCE_MAIN, path)
    main = _git_bytes(REVIEWED_MAIN, path)
    if path.startswith("tests/golden/"):
        assert current.replace(b"\r\n", b"\n") == main.replace(b"\r\n", b"\n")
        # 旧封存固定为 Windows CRLF；先验证 main 原文，再投影历史换行视图。
        # 这不修改 Golden 或旧 Hash，且使原生 Linux checkout 具有同一断言。
        return old.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    if old == main:
        return current
    if path == "schemas/platform/C-010.openapi.json":
        restored = _undo_reviewed_main_delta(json.loads(old), json.loads(main), json.loads(current))
        return (json.dumps(restored, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
    assert current.replace(b"\r\n", b"\n") == main.replace(b"\r\n", b"\n")
    return old


@pytest.mark.parametrize("newline", (b"\n", b"\r\n"))
def test_historical_golden_view_is_checkout_independent_and_rejects_drift(newline):
    baseline = json.loads((ROOT / "tests/golden/platform/adjustment-compatibility-baseline.json").read_text())
    for path in baseline["golden_paths"]:
        current = _git_bytes(REVIEWED_MAIN, path).replace(b"\r\n", b"\n").replace(b"\n", newline)
        historical = _historical_compatibility_bytes(path, current=current)
        assert historical == _git_bytes(PRE_CONVERGENCE_MAIN, path).replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
        with pytest.raises(AssertionError):
            _historical_compatibility_bytes(path, current=current + b" ")


def rid(prefix, number):
    return f"{prefix}_019dbd74-2a00-7000-8000-{number:012d}"


def payload(name):
    return json.loads((GOLDEN / f"{name}.json").read_text(encoding="utf-8"))["payload"]


def revalidate(model, **changes):
    data = {**model.model_dump(mode="python"), **changes}
    for key, value in changes.items():
        if key.endswith("_hash") and value == "":
            data.pop(key)
    return type(model).model_validate(data)


def method(**changes):
    return AdjustmentMethod.model_validate(changes)


def graph(action_count=0):
    """仅合成元数据对象；不生成因子、不读 Provider/数据库/真实数据。"""
    partitions, runs, raws, reports = {}, {}, {}, {}
    for i, dataset in enumerate(ROLES, 1):
        count = action_count if dataset == "corporate_action" else 1
        raw = payload("raw-object")
        raw.update(raw_object_id=rid("raw", i), provider_run_id=rid("prun", i),
                   dataset_id=dataset, row_count=count, source_published_at=NOW-timedelta(hours=2),
                   observed_at=NOW-timedelta(hours=1), ingested_at=NOW-timedelta(minutes=30))
        raw = RawObject.model_validate(raw)
        run = payload("provider-run")
        run.update(provider_run_id=rid("prun", i), dataset_id=dataset,
                   raw_object_refs=[raw.raw_object_id], row_count=count,
                   started_at=NOW-timedelta(hours=1), finished_at=NOW-timedelta(minutes=30))
        run["source_route_evidence"] = build_fixture_provider_source_route(
            provider_id=run["provider_id"], dataset_id=dataset, adapter_name="a_stock_data",
            adapter_version=run["adapter_version"], actual_upstream=run["actual_upstream"],
        ).model_dump(mode="json")
        run = ProviderRun.model_validate(run)
        partition = payload("canonical-partition")
        partition.update(canonical_partition_id=rid("cpart", i), dataset_id=dataset,
                         provider_run_refs=[run.provider_run_id], raw_object_refs=[raw.raw_object_id],
                         quality_report_id=rid("quality", i), row_count=count,
                         distinct_entity_count=0 if count == 0 else 1, max_available_at=NOW)
        partition = CanonicalPartition.model_validate(partition)
        report = payload("canonical-quality-report")
        report.update(quality_report_id=partition.quality_report_id,
                      canonical_partition_id=partition.canonical_partition_id,
                      dataset_id=dataset, dataset_schema_version="1.0.0", row_count=count,
                      provider_run_refs=partition.provider_run_refs, raw_object_refs=partition.raw_object_refs,
                      mapping_version="1.0.0", mapping_hash=H)
        report = CanonicalQualityReport.model_validate(report)
        partitions[partition.canonical_partition_id] = partition
        runs[run.provider_run_id], raws[raw.raw_object_id] = run, raw
        reports[report.quality_report_id] = report
    data = DataSnapshot.model_validate(payload("data-snapshot")).model_dump(mode="python")
    data.update(quality_status="COMPLETE", created_at=NOW, published_at=NOW, canonical_partitions=[SnapshotPartitionRef.from_partition(p, reports[p.quality_report_id]).model_dump(mode="python") for p in partitions.values()],
                security_master_ref=rid("cpart", 3), calendar_ref=rid("cpart", 4),
                quality_report_refs=[p.quality_report_id for p in partitions.values()])
    data["manifest_hash"] = DataSnapshot.build_manifest_hash(data)
    snapshot = DataSnapshot.model_validate(data)
    inputs = tuple(SnapshotInputRef.from_snapshot(snapshot, role) for role in ROLES)
    roots = tuple(SourceRootRef.from_objects(runs[r.provider_run_id], r) for r in raws.values())
    receipt = AdjustmentCoverageReceipt(
        receipt_id="fixture_complete_v1", action_snapshot_id=snapshot.snapshot_id,
        action_manifest_hash=snapshot.manifest_hash, universe_scope_hash=H,
        date_from=date(2026, 8, 28), date_to=date(2026, 8, 31), cutoff_at=NOW,
        available_at=NOW, page_raw_object_refs=(rid("raw", 2),),
        end_marker="fixture_exhaustive_end", source_row_count=action_count,
    )
    m = method()
    lineage = AdjustmentLineage(method_ref=MethodRef.from_method(m), inputs=inputs,
        source_roots=roots, quality_evidence=tuple(QualityEvidenceRef.from_report(r) for r in reports.values()),
        coverage_receipt=receipt, base_trade_date=receipt.date_from, anchor_trade_date=receipt.date_to,
        cutoff_at=NOW, available_at=NOW, universe_scope_hash=H, selected_event_refs=())
    return dict(lineage=lineage, methods={(m.method_id, m.method_version):m},
                snapshots={snapshot.snapshot_id:snapshot}, partitions=partitions,
                provider_runs=runs, raw_objects=raws, quality_reports=reports)


def validate(g):
    validate_adjustment_references(**g)


def derived(g):
    p = DerivedCanonicalPartition(canonical_partition_id=rid("cpart", 99),
        partition_key="fixture_factor_20260831", revision=1, row_count=2,
        storage_ref=next(iter(g["partitions"].values())).storage_ref,
        partition_hash=H, schema_hash=H, quality_report_id=rid("quality", 99),
        lineage=g["lineage"], created_at=NOW+timedelta(days=1), published_at=NOW+timedelta(days=1))
    s = DerivedDataSnapshot(snapshot_id=rid("ds", 99), trade_date=date(2026,8,31),
        cutoff_at=NOW, canonical_partitions=(p,), revision=1,
        created_at=NOW+timedelta(days=1), published_at=NOW+timedelta(days=1))
    return p, s


def test_registry_profiles_match_method_and_nested_input_hashes():
    contracts = ("C-004/AdjustmentMethod", "C-004/DerivedCanonicalPartition", "C-004/DerivedDataSnapshot")
    profiles = [PLATFORM_CONTRACTS.get(name).hash_profile for name in contracts]
    g = graph()
    _, snapshot = derived(g)
    manifest = snapshot.model_dump(mode="python", exclude={"manifest_hash"})
    # 注册声明必须能复算实际 manifest，不能递归忽略嵌套的固定 content_hash。
    assert compute_content_hash(manifest, profiles[2]) == snapshot.manifest_hash
    assert all(profile == profiles[0] for profile in profiles)
    assert profiles[0].profile_id == "adjustment_semantic_json_1.0.0"
    assert profiles[0].excluded_fields == frozenset()
    m = method()
    semantics = m.model_dump(mode="python", exclude={"method_contract_hash"})
    assert compute_content_hash(semantics, profiles[0]) == m.method_contract_hash
    changed = {**manifest, "content_hash": "sha256:" + "2" * 64}
    assert compute_content_hash(changed, profiles[2]) != snapshot.manifest_hash
    rows = json.loads((ROOT / "schemas/platform/contract-registry.json").read_text(encoding="utf-8"))["contracts"]
    for row in rows:
        if row["contract_id"] in contracts:
            assert row["hash_profile"] == profiles[0].model_dump(mode="json")

def test_method_hashes_roundtrip_and_policy_changes():
    m = method()
    assert method() == m == AdjustmentMethod.model_validate_json(m.model_dump_json())
    assert m.method_contract_hash != m.formula_digest
    assert method(direction="BACKWARD_FIXED_BASE").method_contract_hash != m.method_contract_hash
    assert method(direction="BACKWARD_FIXED_BASE").formula_digest != m.formula_digest
    assert method(method_version="1.0.1").method_contract_hash != m.method_contract_hash


@pytest.mark.parametrize("change", [dict(precision=True), dict(precision=38.0), dict(precision="38"),
    dict(precision=28), dict(output_scale=8), dict(rounding="ROUND_HALF_UP"),
    dict(action_whitelist=("RIGHTS",)), dict(price_source="PROVIDER_PREV_CLOSE"),
    dict(missing_input_policy="FACTOR_ONE"), dict(created_at=NOW),
    dict(method_contract_hash=H), dict(formula_digest=H)])
def test_method_rejects_unsupported_or_unhashed_policy(change):
    with pytest.raises(ValidationError):
        method(**change)


def test_method_and_nested_lineage_are_frozen():
    m = method()
    with pytest.raises(ValidationError):
        m.direction = "BACKWARD_FIXED_BASE"
    g = graph()
    with pytest.raises(ValidationError):
        g["lineage"].method_ref.method_version = "1.0.1"
    assert isinstance(g["lineage"].inputs, tuple)


def test_valid_zero_action_requires_complete_graph():
    g = graph()
    validate(g)
    assert g["lineage"].selected_event_refs == ()
    assert g["lineage"].coverage_receipt.source_row_count == 0
    p, s = derived(g)
    assert parse_partition_contract(p.model_dump(mode="json")) == p
    assert parse_snapshot_contract(s.model_dump(mode="json")) == s
    # 操作时钟不影响纯 Method/派生语义 hash，实例 manifest hash 则可不同。
    later = revalidate(p, created_at=NOW+timedelta(days=2), published_at=NOW+timedelta(days=2))
    assert later.lineage.lineage_hash == p.lineage.lineage_hash
    assert later.partition_hash == p.partition_hash
    assert g["lineage"].method_ref.method_contract_hash == method().method_contract_hash


@pytest.mark.parametrize("collection", ["methods", "snapshots", "partitions", "provider_runs", "raw_objects", "quality_reports"])
def test_missing_actual_references_are_rejected(collection):
    g = graph(); g[collection] = {}
    with pytest.raises(ValueError, match="missing"):
        validate(g)


@pytest.mark.parametrize("collection,field,value", [
    ("partitions","dataset_schema_version","9.0.0"), ("partitions","schema_hash","sha256:"+"2"*64),
    ("provider_runs","adapter_version","1.0.1"), ("raw_objects","provider_schema_version","1.0.1"),
    ("quality_reports","mapping_version","1.0.1"), ("quality_reports","mapping_hash","sha256:"+"2"*64),
])
def test_existing_but_changed_references_are_rejected(collection, field, value):
    g=graph(); key=next(iter(g[collection])); updates = {field: value}
    if collection == "provider_runs":
        run = g[collection][key]
        updates["source_route_evidence"] = build_fixture_provider_source_route(
            provider_id=run.provider_id, dataset_id=run.dataset_id, adapter_name="a_stock_data",
            adapter_version=value, actual_upstream=run.actual_upstream,
        )
    g[collection][key]=revalidate(g[collection][key], **updates)
    with pytest.raises(ValueError, match="mismatch|does not match"):
        validate(g)


def test_snapshot_hash_mismatch_is_rejected():
    g=graph(); key=next(iter(g["snapshots"])); data=g["snapshots"][key].model_dump(mode="python")
    data["content_hash"]="sha256:"+"2"*64
    data["manifest_hash"]=DataSnapshot.build_manifest_hash(data)
    g["snapshots"][key]=DataSnapshot.model_validate(data)
    with pytest.raises(ValueError, match="mismatch|does not match"):
        validate(g)


@pytest.mark.parametrize("mutation", ["missing_input", "coverage_missing_page", "coverage_scope", "coverage_interval", "coverage_late", "unknown_event", "late_event", "duplicate_input", "duplicate_root"])
def test_lineage_failure_cases(mutation):
    g=graph(); line=g["lineage"]; data=line.model_dump(mode="python")
    if mutation=="missing_input": data["inputs"]=data["inputs"][:-1]
    elif mutation=="coverage_missing_page": data["coverage_receipt"]["page_raw_object_refs"]=()
    elif mutation=="coverage_scope": data["coverage_receipt"]["universe_scope_hash"]="sha256:"+"2"*64
    elif mutation=="coverage_interval": data["coverage_receipt"]["date_from"]=date(2026,8,29)
    elif mutation=="coverage_late": data["coverage_receipt"]["available_at"]=NOW+timedelta(seconds=1)
    elif mutation in {"unknown_event","late_event"}:
        data["selected_event_refs"]=[dict(economic_event_key="fixture_event", action_group_id="fixture_group", revision=1,
            action_type="RIGHTS" if mutation=="unknown_event" else "DIVIDEND", event_hash=H,
            source_published_at=NOW-timedelta(hours=1), available_at=NOW+timedelta(seconds=1) if mutation=="late_event" else NOW,
            ex_trade_date=date(2026,8,31), raw_object_id=rid("raw",2))]
    elif mutation=="duplicate_input": data["inputs"] += data["inputs"][:1]
    else: data["source_roots"] += data["source_roots"][:1]
    data.pop("lineage_hash", None)
    data["coverage_receipt"].pop("receipt_hash", None)
    with pytest.raises(ValidationError):
        AdjustmentLineage.model_validate(data)


def test_nonempty_action_snapshot_is_not_silently_zero_actions():
    g=graph(action_count=1)
    with pytest.raises(ValueError, match="event"):
        validate(g)


def test_input_partition_cutoff_and_available_upper_bound():
    g=graph(); key=next(iter(g["partitions"]))
    data=g["lineage"].model_dump(mode="python")
    data["inputs"][0]["partitions"][0]["max_available_at"]=NOW+timedelta(seconds=1)
    with pytest.raises(ValidationError, match="cutoff"):
        AdjustmentLineage.model_validate(data)
    data=g["lineage"].model_dump(mode="python"); data["available_at"]=NOW-timedelta(seconds=1)
    with pytest.raises(ValidationError, match="available"):
        AdjustmentLineage.model_validate(data)
    assert key


def test_unknown_versions_and_legacy_consumers_refuse_derived():
    g=graph(); p,s=derived(g)
    with pytest.raises(ValidationError): DataSnapshot.model_validate(s.model_dump(mode="json"))
    with pytest.raises(ValidationError): CanonicalPartition.model_validate(p.model_dump(mode="json"))
    for value in ("0.0.0","3.0.0"):
        with pytest.raises(ValueError): parse_snapshot_contract({**s.model_dump(mode="json"),"manifest_version":value})
        with pytest.raises(ValueError): parse_partition_contract({**p.model_dump(mode="json"),"partition_contract_version":value})
    old=payload("data-snapshot"); old["manifest_version"]="9.0.0"; old["manifest_hash"]=DataSnapshot.build_manifest_hash(old)
    with pytest.raises(ValidationError, match="manifest_version"): DataSnapshot.model_validate(old)


def test_stale_semantic_hash_and_instance_hash_are_rejected():
    g=graph(); p,s=derived(g)
    for model,change in [(g["lineage"],dict(lineage_hash=H)),(s,dict(manifest_hash=H)),(s,dict(content_hash=H))]:
        with pytest.raises(ValidationError, match="hash"): revalidate(model,**change)


def test_legacy_payload_hashes_serialized_bytes_and_fixed_references_unchanged():
    base=json.loads((ROOT/"tests/golden/platform/adjustment-compatibility-baseline.json").read_text(encoding="utf-8"))
    for name,defs in [("f1",F1_INDICATOR_DEFINITIONS),("f2",F2_INDICATOR_DEFINITIONS)]:
        assert len(defs)==base[name]["count"]
        assert compute_content_hash({k:v.model_dump(mode="json") for k,v in defs.items()})==base[name]["full_payload_hash"]
    assert compute_content_hash({p:hashlib.sha256(_historical_compatibility_bytes(p)).hexdigest() for p in base["golden_paths"]})==base["golden_bytes_hash"]
    assert compute_content_hash({p:hashlib.sha256(_historical_compatibility_bytes("schemas/platform/" + p)).hexdigest() for p in base["export_names"]})==base["exports_hash"]
    rows=json.loads((ROOT/"schemas/platform/contract-registry.json").read_text(encoding="utf-8"))["contracts"]
    additive_c004 = {
        "C-004/AdapterImplementationFingerprint",
        "C-004/AdjustmentMethod",
        "C-004/DerivedCanonicalPartition",
        "C-004/DerivedDataSnapshot",
        "C-004/ProviderEndpointDefinition",
        "C-004/ProviderEndpointRunBinding",
        "C-004/SourceAdmissionReceipt",
    }
    main_rows = json.loads(_git_bytes(REVIEWED_MAIN, "schemas/platform/contract-registry.json"))["contracts"]
    assert [r for r in rows if r["contract_id"] not in additive_c004] == main_rows
    old_rows = json.loads(_git_bytes(PRE_CONVERGENCE_MAIN, "schemas/platform/contract-registry.json"))["contracts"]
    assert compute_content_hash(old_rows)==base["legacy_registrations_hash"]
    for name,entry in base["serialization"].items():
        model=PLATFORM_CONTRACTS.get(entry["contract_id"]).schema_model.model_validate(payload(name))
        assert hashlib.sha256(model.model_dump_json().encode()).hexdigest()==entry["serialized_sha256"]
        assert compute_content_hash(model)==entry["full_payload_hash"]


def test_active_and_cancelled_event_refs_are_explicit_and_pinned():
    g = graph(action_count=1)
    event = AdjustmentEventRef(economic_event_key="fixture_event", action_group_id="fixture_group",
        revision=1, action_type="DIVIDEND", event_hash=H, ex_trade_date=date(2026,8,31),
        source_published_at=NOW-timedelta(hours=1), available_at=NOW, raw_object_id=rid("raw",2))
    for state in ("ACTIVE", "CANCELLED"):
        selected = revalidate(event, event_state=state)
        g["lineage"] = revalidate(g["lineage"], selected_event_refs=(selected,), lineage_hash="")
        validate(g)


def test_reference_order_is_canonical_and_operation_clock_is_not_semantic():
    g = graph()
    line = g["lineage"]
    reordered = revalidate(line, inputs=tuple(reversed(line.inputs)),
        source_roots=tuple(reversed(line.source_roots)), quality_evidence=tuple(reversed(line.quality_evidence)), lineage_hash="")
    assert reordered.lineage_hash == line.lineage_hash
    p, s = derived(g)
    later = revalidate(s, created_at=NOW+timedelta(days=2), published_at=NOW+timedelta(days=2), manifest_hash="")
    assert later.content_hash == s.content_hash
    assert later.manifest_hash != s.manifest_hash
    assert p.lineage.lineage_hash == line.lineage_hash


@pytest.mark.parametrize("field,value", [("cash_unit", "AFTER_TAX"), ("split_unit", "NEW_SHARES_PER_SHARE"),
    ("operation_policy", "FLOAT"), ("numeric_failure_policy", "CLIP_TO_EPSILON"),
    ("return_semantics", "TOTAL_RETURN"), ("method_contract_version", "2.0.0")])
def test_method_unit_math_and_contract_version_are_closed(field,value):
    with pytest.raises(ValidationError):
        method(**{field:value})


@pytest.mark.parametrize("changed", ["method_hash", "formula_digest", "method_version", "coverage_count"])
def test_resealed_lineage_cannot_hide_reference_or_coverage_mismatch(changed):
    g = graph()
    data = g["lineage"].model_dump(mode="python")
    data.pop("lineage_hash")
    if changed == "coverage_count":
        data["coverage_receipt"].pop("receipt_hash")
        data["coverage_receipt"]["source_row_count"] = 1
    elif changed == "method_version":
        data["method_ref"]["method_version"] = "9.0.0"
    else:
        field = "method_contract_hash" if changed == "method_hash" else changed
        data["method_ref"][field] = H
    g["lineage"] = AdjustmentLineage.model_validate(data)
    with pytest.raises(ValueError, match="mismatch|missing"):
        validate(g)


@pytest.mark.parametrize("change", [dict(coverage_status="PARTIAL"), dict(end_marker=""),
    dict(event_type_coverage=("BONUS","DIVIDEND","SPLIT")), dict(source_row_count=True),
    dict(receipt_contract_version="2.0.0")])
def test_coverage_requires_positive_completeness_evidence(change):
    receipt = graph()["lineage"].coverage_receipt
    with pytest.raises(ValidationError):
        revalidate(receipt, **change, receipt_hash="")


def test_resealed_snapshot_with_future_input_cutoff_is_refused():
    g = graph()
    data = g["lineage"].model_dump(mode="python")
    data.pop("lineage_hash")
    data["inputs"][0]["snapshot_cutoff_at"] = NOW+timedelta(seconds=1)
    with pytest.raises(ValidationError, match="cutoff"):
        AdjustmentLineage.model_validate(data)


@pytest.mark.parametrize("change", [dict(published_at=NOW), dict(revision_kind="CORRECTION"),
    dict(supersedes_id=rid("ds",2)), dict(certified_capabilities=("market_breadth",)),
    dict(missing_capabilities=()), dict(publication_status="CERTIFIED")])
def test_derived_instance_time_revision_and_certification_do_not_relax(change):
    g = graph(); _, snapshot = derived(g)
    with pytest.raises(ValidationError):
        revalidate(snapshot, **change, manifest_hash="")


@pytest.mark.parametrize("field,value", [
    ("observed_schema_hash", H), ("row_count", 2), ("byte_count", 3),
    ("finished_at", NOW-timedelta(hours=1)),
    ("started_at", NOW-timedelta(minutes=45)),
])
def test_source_root_rejects_inconsistent_run_metadata(field, value):
    g = graph()
    raw = next(iter(g["raw_objects"].values()))
    run = revalidate(g["provider_runs"][raw.provider_run_id], **{field: value})
    with pytest.raises(ValueError, match="source root"):
        SourceRootRef.from_objects(run, raw)


def test_source_root_availability_includes_successful_run_completion():
    g = graph()
    raw = next(iter(g["raw_objects"].values()))
    run = revalidate(g["provider_runs"][raw.provider_run_id], finished_at=NOW+timedelta(seconds=1))
    root = SourceRootRef.from_objects(run, raw)
    assert root.available_at == run.finished_at
    roots = tuple(root if r.raw_object_id == raw.raw_object_id else r for r in g["lineage"].source_roots)
    with pytest.raises(ValidationError, match="cutoff"):
        revalidate(g["lineage"], source_roots=roots, lineage_hash="")


@pytest.mark.parametrize("collection", ["methods", "snapshots", "partitions", "provider_runs", "raw_objects", "quality_reports"])
def test_wrong_actual_object_types_are_explicitly_rejected(collection):
    g = graph()
    key = next(iter(g[collection]))
    g[collection][key] = g["lineage"]
    with pytest.raises(ValueError, match="type"):
        validate(g)



def _bridge_graph(execution, data):
    """用既有合成 graph 绑定实际 fixture，不连接 Provider/DB。"""
    g = graph(action_count=len(data['actions']))
    scope = semantic_hash(tuple(data['securities']))
    coverage = revalidate(g['lineage'].coverage_receipt,
        universe_scope_hash=scope, date_from=date.fromisoformat(data['base_trade_date']),
        date_to=date.fromisoformat(data['anchor_trade_date']),
        cutoff_at=datetime.fromisoformat(data['cutoff_at'].replace('Z', '+00:00')),
        end_marker=data['coverage']['end_marker'], receipt_hash='')
    selected = []
    for row in execution.receipt.selection_rows:
        if row.disposition not in {'SELECTED', 'CANCELLED'}:
            continue
        action = next(a for a in data['actions']
                      if a['economic_event_key'] == row.economic_event_key
                      and a['revision'] == row.revision)
        selected.append(AdjustmentEventRef(
            economic_event_key=action['economic_event_key'],
            action_group_id=action['action_group_id'], revision=action['revision'],
            action_type=action['action_type'], event_hash=semantic_hash(FixtureAction.model_validate(action)),
            ex_trade_date=date.fromisoformat(action['ex_trade_date']),
            source_published_at=max(
                datetime.fromisoformat(action['source_published_at'].replace('Z', '+00:00')),
                NOW - timedelta(hours=2),
            ),
            available_at=max(
                datetime.fromisoformat(action['available_at'].replace('Z', '+00:00')),
                NOW,
            ),
            event_state=action['event_state'],
            raw_object_id=rid('raw', 2)))
    g['lineage'] = revalidate(g['lineage'], coverage_receipt=coverage,
        base_trade_date=date.fromisoformat(data['base_trade_date']),
        anchor_trade_date=date.fromisoformat(data['anchor_trade_date']),
        cutoff_at=datetime.fromisoformat(data['cutoff_at'].replace('Z', '+00:00')),
        available_at=max(
            [NOW] + [
                datetime.fromisoformat(a['available_at'].replace('Z', '+00:00'))
                for a in data['actions']
            ]
        ),
        universe_scope_hash=scope, selected_event_refs=tuple(selected), lineage_hash='')
    validate(g)
    return g


def test_versioned_execution_receipt_bridge_binds_actual_receipt_to_formal_lineage():
    from src.services.platform.adjustment_calculation import calculate_fixture
    from tests.platform.test_adjustment_calculation import event, fixture

    data = fixture([event()])
    raw = json.dumps(data, ensure_ascii=False).encode('utf-8')
    execution = calculate_fixture(raw, materialized_at=datetime(2026, 9, 2, 8, tzinfo=timezone.utc))
    g = _bridge_graph(execution, data)
    bridge = bridge_fixture_execution(raw, execution, execution_revision=1, graph=g)
    assert bridge.bridge_contract_version == '1.0.0'
    assert bridge.receipt.execution_hash == execution.receipt.execution_hash
    assert bridge.coverage_receipt == g['lineage'].coverage_receipt
    assert bridge.quality_evidence == g['lineage'].quality_evidence
    assert bridge.selected_event_refs == g['lineage'].selected_event_refs
    assert bridge.lineage.lineage_hash == g['lineage'].lineage_hash
    assert bridge.result_bytes_hash == 'sha256:' + hashlib.sha256(execution.result.result_bytes()).hexdigest()
    verify_fixture_execution_bridge(raw, bridge, graph=g)
    assert bridge == bridge_fixture_execution(raw, execution, execution_revision=1, graph=g)


@pytest.mark.parametrize('field', [
    'receipt_contract_version', 'algorithm_version', 'method_ref', 'raw_input_hash',
    'input_semantic_hash', 'action_rows_hash', 'calendar_hash', 'identity_rows_hash',
    'price_rows_hash', 'coverage_hash', 'group_rows_hash', 'selection_hash',
])
def test_versioned_bridge_rejects_forged_receipt_fields(field):
    from src.services.platform.adjustment_calculation import calculate_fixture
    from tests.platform.test_adjustment_calculation import event, fixture

    data = fixture([event()])
    raw = json.dumps(data).encode()
    execution = calculate_fixture(raw, materialized_at=datetime(2026, 9, 2, 8, tzinfo=timezone.utc))
    g = _bridge_graph(execution, data)
    bridge = bridge_fixture_execution(raw, execution, execution_revision=1, graph=g)
    payload = bridge.model_dump(mode='python')
    if field == 'receipt_contract_version':
        payload['receipt']['execution_contract_version'] = '9.0.0'
    elif field == 'algorithm_version':
        payload['receipt']['algorithm_version'] = 'offline_fixture_factor_9.0.0'
    elif field == 'method_ref':
        payload['receipt']['method_ref']['method_version'] = '9.0.0'
    else:
        payload['receipt'][field] = H
    with pytest.raises((ValueError, ValidationError)):
        verify_fixture_execution_bridge(raw, type(bridge).model_validate(payload), graph=g)


def test_bridge_rejects_nonempty_cancelled_or_out_of_range_as_true_zero_action():
    from src.services.platform.adjustment_calculation import calculate_fixture
    from tests.platform.test_adjustment_calculation import event, fixture

    newer = event(revision=2, quantity='2', source_published_at='2026-09-01T08:00:00Z',
                  available_at='2026-09-01T08:00:00Z')
    cancelled = {**newer, 'event_state': 'CANCELLED', 'quantity': None, 'share_denominator': None}
    data = fixture([event(), cancelled]); data['cutoff_at'] = data['coverage']['cutoff_at'] = '2026-09-01T08:00:00Z'
    execution = calculate_fixture(json.dumps(data).encode(), materialized_at=datetime(2026, 9, 2, 8, tzinfo=timezone.utc))
    g = _bridge_graph(execution, data)
    with pytest.raises(ValueError, match='selection state|cancel|empty'):
        bridge_fixture_execution(json.dumps(data).encode(), execution, execution_revision=1, graph=g)


def test_bridge_rejects_revision_change_without_new_execution_revision():
    from src.services.platform.adjustment_calculation import calculate_fixture
    from tests.platform.test_adjustment_calculation import event, fixture

    data = fixture([event()])
    raw = json.dumps(data).encode()
    execution = calculate_fixture(raw, materialized_at=datetime(2026, 9, 2, 8, tzinfo=timezone.utc))
    g = _bridge_graph(execution, data)
    first = bridge_fixture_execution(raw, execution, execution_revision=1, graph=g)
    second = bridge_fixture_execution(raw, execution, execution_revision=2, graph=g)
    assert first.bridge_hash != second.bridge_hash
    assert first.bridge_lineage_hash != second.bridge_lineage_hash


@pytest.mark.parametrize('missing', [
    'lineage', 'methods', 'snapshots', 'partitions', 'provider_runs',
    'raw_objects', 'quality_reports',
])
def test_bridge_requires_complete_reference_graph(missing):
    from src.services.platform.adjustment_calculation import calculate_fixture
    from tests.platform.test_adjustment_calculation import event, fixture

    data = fixture([event()])
    raw = json.dumps(data).encode()
    execution = calculate_fixture(
        raw, materialized_at=datetime(2026, 9, 2, 8, tzinfo=timezone.utc)
    )
    g = _bridge_graph(execution, data)
    g.pop(missing)
    with pytest.raises(ValueError, match='missing bridge graph'):
        bridge_fixture_execution(raw, execution, execution_revision=1, graph=g)


def test_bridge_rejects_changed_raw_and_semantic_input_bytes():
    from src.services.platform.adjustment_calculation import calculate_fixture
    from tests.platform.test_adjustment_calculation import event, fixture

    data = fixture([event()])
    raw = json.dumps(data).encode()
    execution = calculate_fixture(
        raw, materialized_at=datetime(2026, 9, 2, 8, tzinfo=timezone.utc)
    )
    g = _bridge_graph(execution, data)
    bridge = bridge_fixture_execution(raw, execution, execution_revision=1, graph=g)
    changed = json.loads(raw)
    changed['actions'][0]['quantity'] = '2'
    changed_raw = json.dumps(changed).encode()
    with pytest.raises(ValueError, match='actual input/source'):
        verify_fixture_execution_bridge(changed_raw, bridge, graph=g)
    with pytest.raises(ValueError, match='actual input/source'):
        bridge_fixture_execution(changed_raw, execution, execution_revision=1, graph=g)


def test_bridge_rejects_result_or_implementation_forgery():
    from src.services.platform.adjustment_calculation import calculate_fixture
    from tests.platform.test_adjustment_calculation import event, fixture

    data = fixture([event()])
    raw = json.dumps(data).encode()
    execution = calculate_fixture(
        raw, materialized_at=datetime(2026, 9, 2, 8, tzinfo=timezone.utc)
    )
    g = _bridge_graph(execution, data)
    bridge = bridge_fixture_execution(raw, execution, execution_revision=1, graph=g)

    forged = bridge.model_dump(mode='python')
    forged['result']['rows'][0]['factor'] = '0.800000000000000000'
    forged['result'].pop('content_hash')
    forged['receipt']['result_content_hash'] = semantic_hash(
        {**forged['result'], 'content_hash': ''}
    )
    with pytest.raises((ValueError, ValidationError)):
        verify_fixture_execution_bridge(
            raw, type(bridge).model_validate(forged), graph=g
        )

    forged = bridge.model_dump(mode='python')
    forged['implementation_digest'] = H
    with pytest.raises((ValueError, ValidationError)):
        type(bridge).model_validate(forged)


def test_bridge_lineage_hash_excludes_materialization_clock_but_bridge_hash_binds_it():
    from src.services.platform.adjustment_calculation import calculate_fixture
    from tests.platform.test_adjustment_calculation import event, fixture

    data = fixture([event()])
    raw = json.dumps(data).encode()
    execution = calculate_fixture(
        raw, materialized_at=datetime(2026, 9, 2, 8, tzinfo=timezone.utc)
    )
    g = _bridge_graph(execution, data)
    first = bridge_fixture_execution(raw, execution, execution_revision=1, graph=g)
    later_execution = calculate_fixture(
        raw, materialized_at=datetime(2026, 9, 3, 8, tzinfo=timezone.utc)
    )
    later = bridge_fixture_execution(raw, later_execution, execution_revision=1, graph=g)
    assert later.bridge_lineage_hash == first.bridge_lineage_hash
    assert later.bridge_hash != first.bridge_hash


def test_bridge_rejects_future_materialization_and_nonempty_out_of_range():
    from src.services.platform.adjustment_calculation import calculate_fixture
    from tests.platform.test_adjustment_calculation import event, fixture

    data = fixture([event()])
    raw = json.dumps(data).encode()
    future = calculate_fixture(
        raw, materialized_at=datetime.now(timezone.utc) + timedelta(days=1)
    )
    g = _bridge_graph(future, data)
    with pytest.raises(ValueError, match='future'):
        bridge_fixture_execution(raw, future, execution_revision=1, graph=g)

    out_of_range = fixture([event(ex='2026-08-31')], end='2026-08-28')
    out_raw = json.dumps(out_of_range).encode()
    out_execution = calculate_fixture(
        out_raw, materialized_at=datetime(2026, 9, 2, 8, tzinfo=timezone.utc)
    )
    out_graph = graph(action_count=0)
    assert out_execution.receipt.selection_status == 'ALL_OUT_OF_RANGE'
    with pytest.raises(ValueError, match='not bridgeable|empty action'):
        bridge_fixture_execution(
            out_raw, out_execution, execution_revision=1, graph=out_graph
        )


def test_bridge_accepts_genuine_zero_action_with_complete_graph():
    from src.services.platform.adjustment_calculation import calculate_fixture
    from tests.platform.test_adjustment_calculation import fixture

    data = fixture()
    raw = json.dumps(data).encode()
    execution = calculate_fixture(
        raw, materialized_at=datetime(2026, 9, 2, 8, tzinfo=timezone.utc)
    )
    g = _bridge_graph(execution, data)
    bridge = bridge_fixture_execution(raw, execution, execution_revision=1, graph=g)
    assert execution.receipt.selection_status == 'TRUE_NO_ACTION'
    assert bridge.selected_event_refs == ()
    verify_fixture_execution_bridge(raw, bridge, graph=g)
