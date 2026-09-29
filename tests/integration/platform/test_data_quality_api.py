from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.middlewares.error_handler import add_error_handlers
from api.platform.router import router
from api.platform.request_id import REQUEST_ID_HEADER
from src.schemas.platform import BackfillBatchProjection, BackfillStageChainProjection, DataSnapshot
from src.services.platform.backfill import BackfillError
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

BACKFILL_BATCH_ID = "backfill_019dbd74-2a00-7000-8000-000000000009"
BACKFILL_TASK_ID = "task_019dbd74-2a00-7000-8000-000000000010"


class FakeBackfillPDataService:
    def __init__(self):
        self.batch_id = None
        self.stage_chain_batch_id = None

    @staticmethod
    def _projection(stage, task_id, state, dependency_task_ids=()):
        return BackfillBatchProjection(
            batch_id=BACKFILL_BATCH_ID,
            task_id=task_id,
            batch_state=state,
            batch_type="MONTH",
            stage=stage,
            date_from=date(2026, 8, 1),
            date_to=date(2026, 8, 31),
            dataset="bar_1d_raw",
            provider_policy_id="default",
            priority=100,
            dry_run=False,
            plan_only=False,
            checkpoint_phase="PARTITION_0",
            completed_range=(date(2026, 8, 1), date(2026, 8, 10)),
            dependency_task_ids=dependency_task_ids,
            resource_usage={"partitions": 1.0},
        )

    def get_batch(self, batch_id):
        self.batch_id = batch_id
        return self._projection("PRICE_MONTH", BACKFILL_TASK_ID, "RUNNING")

    def get_stage_chain(self, batch_id):
        self.stage_chain_batch_id = batch_id
        identity_task_id = "task_019dbd74-2a00-7000-8000-000000000012"
        return BackfillStageChainProjection(
            batches=(
                self._projection("IDENTITY_CALENDAR", identity_task_id, "COMPLETED"),
                self._projection(
                    "PRICE_MONTH",
                    "task_019dbd74-2a00-7000-8000-000000000011",
                    "RUNNING",
                    dependency_task_ids=(identity_task_id,),
                ),
            )
        )


def test_data_quality_backfill_projection_is_read_only_and_enveloped():
    app = FastAPI()
    app.include_router(router, prefix="/api")
    service = FakeBackfillPDataService()
    app.state.backfill_service = service
    with TestClient(app) as client:
        response = client.get(
            f"/api/platform/v1/data-quality/backfills/{BACKFILL_BATCH_ID}",
            headers={REQUEST_ID_HEADER: REQUEST_ID},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["meta"]["request_id"] == REQUEST_ID
    assert payload["data"]["batch_id"] == BACKFILL_BATCH_ID
    assert payload["data"]["checkpoint_phase"] == "PARTITION_0"
    assert payload["data"]["completed_range"] == ["2026-08-01", "2026-08-10"]
    assert service.batch_id == BACKFILL_BATCH_ID
class FailingBackfillPDataService:
    def get_batch(self, batch_id):
        raise BackfillError(
            "BACKFILL_CHECKPOINT_INVALID",
            "Backfill checkpoint cannot be read.",
            status_code=409,
            retryable=True,
        )


class FailingStageChainBackfillPDataService:
    def get_stage_chain(self, batch_id):
        raise BackfillError(
            "BACKFILL_STAGE_CHAIN_INVALID",
            "Backfill stage chain is not in the required order.",
            status_code=409,
            retryable=False,
        )


def test_data_quality_backfill_stage_chain_projection_is_read_only_and_ordered():
    app = FastAPI()
    app.include_router(router, prefix="/api")
    service = FakeBackfillPDataService()
    app.state.backfill_service = service
    with TestClient(app) as client:
        response = client.get(
            f"/api/platform/v1/data-quality/backfills/{BACKFILL_BATCH_ID}/stages",
            headers={REQUEST_ID_HEADER: REQUEST_ID},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["meta"]["request_id"] == REQUEST_ID
    assert [item["stage"] for item in payload["data"]["batches"]] == ["IDENTITY_CALENDAR", "PRICE_MONTH"]
    assert service.stage_chain_batch_id == BACKFILL_BATCH_ID


def test_data_quality_backfill_projection_preserves_safe_error_contract():
    app = FastAPI()
    app.include_router(router, prefix="/api")
    add_error_handlers(app)
    app.state.backfill_service = FailingBackfillPDataService()
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get(
            f"/api/platform/v1/data-quality/backfills/{BACKFILL_BATCH_ID}",
            headers={REQUEST_ID_HEADER: REQUEST_ID},
        )

    assert response.status_code == 409
    payload = response.json()
    assert payload["error"]["code"] == "BACKFILL_CHECKPOINT_INVALID"
    assert payload["error"]["retryable"] is True
    assert payload["error"]["request_id"] == REQUEST_ID
    assert payload["error"]["details"] == {}



def test_data_quality_backfill_stage_chain_preserves_safe_error_contract():
    app = FastAPI()
    app.include_router(router, prefix="/api")
    add_error_handlers(app)
    app.state.backfill_service = FailingStageChainBackfillPDataService()
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get(
            f"/api/platform/v1/data-quality/backfills/{BACKFILL_BATCH_ID}/stages",
            headers={REQUEST_ID_HEADER: REQUEST_ID},
        )

    assert response.status_code == 409
    payload = response.json()
    assert payload["error"]["code"] == "BACKFILL_STAGE_CHAIN_INVALID"
    assert payload["error"]["retryable"] is False
    assert payload["error"]["request_id"] == REQUEST_ID
    assert payload["error"]["details"] == {}


class ExplodingBackfillPDataService:
    def get_batch(self, batch_id):
        raise RuntimeError("database password=fixture-secret at C:\\private\\raw_payload.json")

    def get_stage_chain(self, batch_id):
        raise RuntimeError("Authorization: Bearer fixture-secret")


def test_data_quality_backfill_unknown_failures_use_safe_platform_envelope():
    app = FastAPI()
    app.include_router(router, prefix="/api")
    add_error_handlers(app)
    app.state.backfill_service = ExplodingBackfillPDataService()

    with TestClient(app, raise_server_exceptions=False) as client:
        projection = client.get(
            f"/api/platform/v1/data-quality/backfills/{BACKFILL_BATCH_ID}",
            headers={REQUEST_ID_HEADER: REQUEST_ID},
        )
        stage_chain = client.get(
            f"/api/platform/v1/data-quality/backfills/{BACKFILL_BATCH_ID}/stages",
            headers={REQUEST_ID_HEADER: REQUEST_ID},
        )

    for response in (projection, stage_chain):
        assert response.status_code == 500
        payload = response.json()
        assert payload["error"] == {
            "code": "INTERNAL_ERROR",
            "message": "服务器内部错误",
            "details": {},
            "retryable": False,
            "request_id": REQUEST_ID,
        }
        assert "fixture-secret" not in response.text
        assert "raw_payload" not in response.text
