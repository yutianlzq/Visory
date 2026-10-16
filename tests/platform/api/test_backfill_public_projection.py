from datetime import date
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from api.middlewares.error_handler import add_error_handlers
from api.platform.router import router, _public_task_details, _sse_response
from src.services.platform.backfill import BackfillError
from src.utils.sanitize import sanitize_platform_public_payload


PRIVATE_TEXTS = (
    "token=fixture-secret", "lease=fixture-secret",
    "postgresql+psycopg://user:fixture-secret@localhost/database",
    'response_body: {"token":"fixture-secret"}',
    r"C:\private\fixture-secret.json", "/mnt/private/fixture-secret.json",
    "Traceback (most recent call last): fixture-secret",
    "https://user:fixture-secret@example.invalid/",
    "eyJfixture.payload.signature",
)


@pytest.mark.parametrize("private_text", PRIVATE_TEXTS)
def test_task_details_and_sse_remove_private_diagnostics(private_text):
    payload = {
        "task": {"requirements": {"diagnostic": private_text}, "failure_code": "BACKFILL_WORKER_ERROR"},
        "attempts": [{"lease_token_hash": "fixture-secret"}],
        "checkpoints": [{"resume_token_hash": "fixture-secret"}],
        "event_id": "tevent_public", "event_type": "task_state_changed",
    }
    details = SimpleNamespace(model_dump=lambda **kwargs: payload)
    projected = _public_task_details(details)
    assert "lease_token_hash" not in projected["attempts"][0]
    assert "resume_token_hash" not in projected["checkpoints"][0]
    assert projected["task"]["failure_code"] == "BACKFILL_WORKER_ERROR"
    assert "fixture-secret" not in str(projected)
    response = _sse_response((payload,))
    import asyncio
    async def read():
        return "".join([value async for value in response.body_iterator])
    body = asyncio.run(read())
    assert "fixture-secret" not in body
    assert "BACKFILL_WORKER_ERROR" in body


@pytest.mark.parametrize("private_text", PRIVATE_TEXTS)
@pytest.mark.parametrize("path", (
    "/api/platform/v1/backfills/backfill_test",
    "/api/platform/v1/data-quality/backfills/backfill_test",
    "/api/platform/v1/backfills/coverage?dataset=bar_1d_raw&date_from=2018-01-01&date_to=2026-10-13",
))
def test_backfill_error_keeps_code_retryability_and_request_id_without_private_text(private_text, path):
    class Service:
        def fail(self, *args):
            raise BackfillError("BACKFILL_SOURCE_UNAVAILABLE", private_text, status_code=503, retryable=True)
        get_batch = fail
        get_coverage = fail
    app = FastAPI()
    app.include_router(router, prefix="/api")
    add_error_handlers(app)
    app.state.backfill_service = Service()
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get(path)
    assert response.status_code == 503
    error = response.json()["error"]
    assert "fixture-secret" not in response.text
    assert error["code"] == "BACKFILL_SOURCE_UNAVAILABLE"
    assert error["retryable"] is True
    assert error["request_id"].startswith("req_")


def test_projection_preserves_logical_storage_references_and_version_hashes():
    payload = {
        "storage_ref": {"relative_path": "canonical/dataset=bar_1d_raw/data.parquet", "content_hash": "sha256:" + "1" * 64},
        "mapping_hash": "sha256:" + "2" * 64,
        "date_from": date(2018, 1, 1), "response_body": "fixture-secret",
    }
    result = sanitize_platform_public_payload(payload)
    assert result["storage_ref"] == payload["storage_ref"]
    assert result["mapping_hash"] == payload["mapping_hash"]
    assert "response_body" not in result
