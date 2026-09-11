from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.platform.router import router
from api.platform.request_id import REQUEST_ID_HEADER
from src.schemas.platform import DataSnapshot
from src.services.platform.data_quality import DataQualityActionResult, DataQualityQueryResult


REQUEST_ID = "req_0123456789abcdef0123456789abcdef"
SNAPSHOT_ID = "ds_019dbd74-2a00-7000-8000-000000000007"


class FakeDataQualityService:
    def __init__(self):
        self.query = None
        self.action = None

    def get_projection(self, query):
        self.query = query
        return DataQualityQueryResult(
            trade_date=date(2026, 8, 31),
            data_as_of="2026-08-31T08:00:00Z",
            snapshot_id=SNAPSHOT_ID,
            publication_status="PROVISIONAL",
            quality_status="PARTIAL",
            cutoff_at="2026-08-31T08:00:00Z",
            revision=1,
            revision_kind="INITIAL",
            supersedes_id=None,
            missing_capabilities=("backtest_core",),
            capabilities=(),
            datasets=(),
            timeline=(),
            current_pointers=(),
            task_ids=(),
            warnings=("QUALITY_PARTIAL",),
        )

    def compare_snapshots(self, snapshot_id, base_snapshot_id=None):
        return {"target_snapshot_id": snapshot_id, "base_snapshot_id": base_snapshot_id}

    def create_action(self, action, *, idempotency_key):
        self.action = action
        return DataQualityActionResult(task_id="task_019dbd74-2a00-7000-8000-000000000777", action=action.action)


def test_data_quality_api_is_enveloped_and_filters_are_forwarded():
    app = FastAPI()
    app.include_router(router, prefix="/api")
    service = FakeDataQualityService()
    app.state.data_quality_service = service
    with TestClient(app) as client:
        response = client.get(
            "/api/platform/v1/data-quality?trade_date=2026-08-31&capability=backtest_core&dataset=bar_1d_raw&provider=a_stock_data&status=PARTIAL",
            headers={REQUEST_ID_HEADER: REQUEST_ID},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["meta"]["request_id"] == REQUEST_ID
    assert payload["data"]["snapshot_id"] == SNAPSHOT_ID
    assert payload["data"]["missing_capabilities"] == ["backtest_core"]
    assert service.query.capability == "backtest_core"
    assert service.query.dataset == "bar_1d_raw"
    assert service.query.provider == "a_stock_data"
    assert service.query.status == "PARTIAL"


def test_data_quality_action_endpoint_requires_idempotency_and_returns_task_id():
    app = FastAPI()
    app.include_router(router, prefix="/api")
    service = FakeDataQualityService()
    app.state.data_quality_service = service
    with TestClient(app) as client:
        response = client.post(
            "/api/platform/v1/data-quality/actions",
            headers={REQUEST_ID_HEADER: REQUEST_ID, "Idempotency-Key": "dq-action-1"},
            json={
                "action": "rebuild",
                "snapshot_id": SNAPSHOT_ID,
                "trade_date": "2026-08-31",
                "reason_code": "QUALITY_RECHECK_REQUESTED",
                "requested_by": "owner:quality",
            },
        )

    assert response.status_code == 200
    assert response.json()["data"]["task_id"].startswith("task_")
    assert service.action.action == "rebuild"
