from datetime import date
import json
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from pydantic import ValidationError
import pytest

from api.middlewares.error_handler import add_error_handlers
from api.platform.errors import platform_error
from api.platform.responses import build_list_envelope, build_success_envelope
from api.platform.router import router
from src.services.platform.backfill import BackfillError
from src.schemas.platform import PLATFORM_CONTRACTS, TaskDetails, TaskEventRecord
from src.utils.sanitize import sanitize_platform_public_payload


PRIVATE_TEXTS = (
    "token=fixture-secret", "lease=fixture-secret",
    "postgresql+psycopg://user:fixture-secret@localhost/database",
    'response_body: {"token":"fixture-secret"}',
    r"C:\private\fixture-secret.json", "/mnt/private/fixture-secret.json",
    "Traceback (most recent call last): fixture-secret",
    "https://user:fixture-secret@example.invalid/",
    "eyJfixture.payload.signature",
    "api_key=fixture-secret", "api-key: fixture-secret", "apiKey = fixture-secret",
    '{"api_key":"fixture-secret"}', "{'api-key': 'fixture-secret'}",
    '{"apiKey" : "fixture-secret"}',
    "API Key: fixture-secret",
)


ROOT = Path(__file__).resolve().parents[3]
TEXT_CASES = json.loads((ROOT / "tests/fixtures/platform_public_text.json").read_text(encoding="utf-8"))
PRIVATE_TEXTS += tuple(case["text"] for case in TEXT_CASES["private"])


@pytest.mark.parametrize("case", TEXT_CASES["private"], ids=lambda case: case["id"])
def test_public_sanitizer_rejects_serialized_diagnostics_in_values_and_keys(case):
    assert sanitize_platform_public_payload(case["text"]) == "[REDACTED]"
    assert sanitize_platform_public_payload({case["text"]: "private diagnostic"}) == {}
    if "key" in case:
        assert sanitize_platform_public_payload({case["key"]: "fixture-secret"}) == {}


@pytest.mark.parametrize("case", TEXT_CASES["safe"], ids=lambda case: case["id"])
def test_public_sanitizer_keeps_safe_text_byte_for_byte(case):
    assert sanitize_platform_public_payload(case["text"]) == case["text"]


@pytest.mark.parametrize("case", TEXT_CASES["private"] + TEXT_CASES["safe"], ids=lambda case: case["id"])
def test_real_http_warning_and_error_envelopes_share_public_diagnostic_policy(case):
    text = case["text"]
    expected = "[REDACTED]" if case in TEXT_CASES["private"] else text
    data = {"diagnostic": text, **({case["key"]: "fixture-secret"} if "key" in case else {})}
    app = FastAPI()
    add_error_handlers(app)

    @app.get("/api/platform/v1/fixture/warnings")
    def warnings(request: Request, listed: bool = False):
        if listed:
            return build_list_envelope(
                request=request, data=[data], warnings=(text,), data_snapshot_id=None,
                cursor=None, next_cursor=None, limit=10, has_more=False,
            )
        return build_success_envelope(request=request, data=data, warnings=(text,), data_snapshot_id=None)

    @app.get("/api/platform/v1/fixture/error")
    def fail_request():
        raise platform_error(503, code="BACKFILL_SOURCE_UNAVAILABLE", message=text, retryable=True, details=data)

    with TestClient(app) as client:
        for listed in (False, True):
            response = client.get("/api/platform/v1/fixture/warnings", params={"listed": str(listed).lower()})
            assert response.status_code == 200
            payload = response.json()
            assert payload["meta"]["warnings"] == [expected]
            assert (payload["data"][0] if listed else payload["data"]) == {"diagnostic": expected}
        response = client.get("/api/platform/v1/fixture/error")
    assert response.status_code == 503
    error = response.json()["error"]
    assert error["details"] == {"diagnostic": expected}
    assert error["code"] == "BACKFILL_SOURCE_UNAVAILABLE" and error["retryable"] is True
    assert error["request_id"].startswith("req_")
    if expected == text:
        assert error["message"] == text
    else:
        assert error["message"] != text


def _golden(name):
    path = ROOT / "tests/golden/platform/contracts/success" / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8"))["payload"]


@pytest.mark.parametrize("private_text", PRIVATE_TEXTS)
def test_real_http_task_details_and_sse_match_public_contract(private_text):
    payload = _golden("task-details")
    payload["task"]["requirements"]["diagnostic"] = private_text
    payload["attempts"] = [_golden("task-attempt-record")]
    payload["checkpoints"] = [_golden("task-checkpoint-record")]
    details = TaskDetails.model_validate(payload)
    event_payload = _golden("task-event-record")
    event_payload["payload"]["actor_ref"] = private_text
    event = TaskEventRecord.model_validate(event_payload)
    app = FastAPI()
    app.include_router(router, prefix="/api")
    add_error_handlers(app)
    app.state.task_control_service = SimpleNamespace(
        get_task=lambda task_id: details,
        list_event_records=lambda **kwargs: (event,),
    )
    with TestClient(app) as client:
        response = client.get(f"/api/platform/v1/tasks/{details.task.task_id}")
        stream = client.get(f"/api/platform/v1/tasks/{details.task.task_id}/events")
    assert response.status_code == stream.status_code == 200
    assert "fixture-secret" not in response.text + stream.text
    data = response.json()["data"]
    assert "lease_token_hash" not in data["attempts"][0]
    assert "resume_token_hash" not in data["checkpoints"][0]
    assert data["checkpoints"][0]["storage_ref"] == payload["checkpoints"][0]["storage_ref"]
    assert details.attempts[0].lease_token_hash
    assert details.checkpoints[0].resume_token_hash
    public = PLATFORM_CONTRACTS.get("C-010/TaskDetails").schema_model
    public.model_validate(data)
    schema = json.loads((ROOT / "schemas/platform/C-010.TaskDetails.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(data)
    for spec in (app.openapi(), json.loads((ROOT / "schemas/platform/C-010.openapi.json").read_text(encoding="utf-8"))):
        response_schema = spec["paths"]["/api/platform/v1/tasks/{task_id}"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
        assert response_schema["$ref"] == "#/components/schemas/PublicTaskDetailsResponse"
        Draft202012Validator({**spec, **response_schema}).validate(response.json())


@pytest.mark.parametrize("contract,name,secret", (
    ("C-007/TaskAttemptRecord", "task-attempt-record", "lease_token_hash"),
    ("C-011/TaskCheckpointRecord", "task-checkpoint-record", "resume_token_hash"),
))
def test_internal_worker_verifiers_remain_required(contract, name, secret):
    payload = _golden(name)
    model = PLATFORM_CONTRACTS.get(contract).schema_model
    assert secret in model.model_json_schema()["required"]
    del payload[secret]
    with pytest.raises(ValidationError) as error:
        model.model_validate(payload)
    assert (secret,) in {item["loc"] for item in error.value.errors()}


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
