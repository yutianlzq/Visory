from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
import pytest
from src.schemas.platform import ResourceType, generate_resource_id
from src.services.platform.canonical_normalization import CanonicalNormalizer
from src.services.platform.provider_registry import default_provider_canonical_mapping_records

NOW = datetime(2026, 9, 1, 8, tzinfo=timezone.utc)

def identity(value, row):
    return SimpleNamespace(entity_key="stock:sh600519", canonical_id="sh600519", resolution_status=SimpleNamespace(value="RESOLVED"))

def row_for(provider, dataset):
    if dataset == "instrument_status_daily":
        return ({"ts_code":"600519.SH","status_date":"2026-08-31","status":"ACTIVE","tradable":True,"as_of":NOW.isoformat()} if provider == "a_stock_data" else {"symbol":"600519.SH","status_date":"2026-08-31","status":"ACTIVE","is_tradable":True,"observed_at":NOW.isoformat()})
    if dataset == "listing_status_history":
        return ({"ts_code":"600519.SH","listing_status":"LISTED","effective_from":"2020-01-01","effective_to":None,"as_of":NOW.isoformat()} if provider == "a_stock_data" else {"symbol":"600519.SH","from_date":"2020-01-01","to_date":None,"status":"LISTED","observed_at":NOW.isoformat()})
    if dataset == "corporate_action":
        return ({"action_id":"ca-1","ts_code":"600519.SH","action_type":"DIV","ex_date":"2026-08-31","record_date":"2026-09-01","payment_date":None,"ratio":None,"cash_amount":1,"currency_code":"CNY","revision":1,"published_at":"2026-08-20T00:00:00Z","as_of":NOW.isoformat()} if provider == "a_stock_data" else {"corporate_action_id":"ca-1","symbol":"600519.SH","type":"DIV","ex_date":"2026-08-31","record_date":"2026-09-01","payment_date":None,"ratio":None,"cash_per_share":1,"currency":"CNY","revision":1,"published_at":"2026-08-20T00:00:00Z","available_at":NOW.isoformat()})
    return ({"ts_code":"600519.SH","report_period":"2026-06-30","statement_type":"BS","line_item":"revenue","value":1,"unit":"CNY","currency_code":"CNY","published_at":"2026-08-20T00:00:00Z","available_at":NOW.isoformat(),"revision":1} if provider == "a_stock_data" else {"symbol":"600519.SH","period_end":"2026-06-30","statement":"BS","item":"revenue","amount":1,"unit":"CNY","currency":"CNY","published_at":"2026-08-20T00:00:00Z","available_at":NOW.isoformat(),"revision":1})

@pytest.mark.parametrize("provider", ["a_stock_data", "financial_api"])
@pytest.mark.parametrize("dataset", ["instrument_status_daily", "listing_status_history", "corporate_action", "financial_statement"])
def test_extended_datasets_normalize(provider: str, dataset: str, tmp_path: Path):
    mapping = next(m for m in default_provider_canonical_mapping_records() if m.provider_id == provider and m.dataset_id == dataset)
    n = CanonicalNormalizer(tmp_path, clock=lambda: NOW)
    partition, report, content = n.normalize_rows(raw_object_id=generate_resource_id(ResourceType.RAW_OBJECT), provider_run_id=generate_resource_id(ResourceType.PROVIDER_RUN), provider_id=provider, dataset_id=dataset, dataset_schema_version="1.0.0", provider_policy_version="1.0.0", mapping=mapping, rows=[row_for(provider, dataset)], partition_key="2026", identity_resolver=identity)
    assert partition is not None and content and not report.failure_reasons
    assert report.dataset_id == dataset and report.mapping_hash == mapping.mapping_hash

def test_listing_interval_overlap_is_rejected(tmp_path: Path):
    m = next(m for m in default_provider_canonical_mapping_records() if m.provider_id == "a_stock_data" and m.dataset_id == "listing_status_history")
    n = CanonicalNormalizer(tmp_path, clock=lambda: NOW)
    first = row_for("a_stock_data", "listing_status_history")
    second = {**first, "effective_from": "2025-01-01", "effective_to": "2026-01-01"}
    _, report, _ = n.normalize_rows(raw_object_id=generate_resource_id(ResourceType.RAW_OBJECT), provider_run_id=generate_resource_id(ResourceType.PROVIDER_RUN), provider_id="a_stock_data", dataset_id="listing_status_history", dataset_schema_version="1.0.0", provider_policy_version="1.0.0", mapping=m, rows=[first, second], partition_key="2026", identity_resolver=identity)
    assert "CANONICAL_LISTING_INTERVAL_OVERLAP" in report.failure_reasons

def test_financial_unknown_unit_is_rejected(tmp_path: Path):
    m = next(m for m in default_provider_canonical_mapping_records() if m.provider_id == "a_stock_data" and m.dataset_id == "financial_statement")
    n = CanonicalNormalizer(tmp_path, clock=lambda: NOW)
    row = {**row_for("a_stock_data", "financial_statement"), "unit": "bogus"}
    _, report, _ = n.normalize_rows(raw_object_id=generate_resource_id(ResourceType.RAW_OBJECT), provider_run_id=generate_resource_id(ResourceType.PROVIDER_RUN), provider_id="a_stock_data", dataset_id="financial_statement", dataset_schema_version="1.0.0", provider_policy_version="1.0.0", mapping=m, rows=[row], partition_key="2026", identity_resolver=identity)
    assert report.failure_reasons == ("CANONICAL_UNIT_UNKNOWN",)
