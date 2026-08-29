from __future__ import annotations

import json
import logging
import re
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import Request
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient

from api.platform.boundary import PLATFORM_API_PREFIX
from api.platform.errors import platform_error
from api.platform.request_id import (
    REQUEST_ID_HEADER,
    REQUEST_ID_PATTERN,
    resolve_request_id,
)
from api.platform.responses import build_list_envelope, build_success_envelope

# This contract test does not exercise LLM providers. Avoid LiteLLM's optional
# import-time tokenizer download so the RED/GREEN target stays offline.
sys.modules.setdefault("litellm", MagicMock())

from api.app import create_app


VALID_REQUEST_ID = "req_0123456789abcdef0123456789abcdef"


def _build_app(tmp_path: Path):
    app = create_app(static_dir=tmp_path / "missing-static")

    @app.get(f"{PLATFORM_API_PREFIX}/success")
    async def success(request: Request):
        return build_success_envelope(
            request=request,
            data={"name": "example"},
            data_snapshot_id=None,
        )

    @app.get(f"{PLATFORM_API_PREFIX}/items")
    async def items(request: Request):
        return build_list_envelope(
            request=request,
            data=[{"name": "one"}],
            cursor=None,
            next_cursor=None,
            limit=50,
            has_more=False,
            data_snapshot_id=None,
        )

    @app.get(f"{PLATFORM_API_PREFIX}/errors/{{status_code}}")
    async def errors(status_code: int):
        raise platform_error(status_code)

    @app.get(f"{PLATFORM_API_PREFIX}/validate")
    async def validate(limit: int):
        return {"limit": limit}

    @app.get(f"{PLATFORM_API_PREFIX}/unknown")
    async def unknown():
        raise RuntimeError(
            "postgresql://user:super-secret@localhost/db "
            "SELECT * FROM private_table C:\\private\\config.env"
        )

    @app.get("/api/v1/legacy-stream")
    async def legacy_stream():
        async def body():
            yield "event: message\ndata: unchanged\n\n"

        return StreamingResponse(body(), media_type="text/event-stream")

    @app.get("/api/v1/legacy-validate")
    async def legacy_validate(limit: int):
        return {"limit": limit}

    return app


def _assert_c010_error(response, *, status_code: int, code: str, retryable: bool) -> dict:
    assert response.status_code == status_code
    body = response.json()
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message", "details", "retryable", "request_id"}
    assert body["error"]["code"] == code
    assert body["error"]["retryable"] is retryable
    assert body["error"]["request_id"] == response.headers[REQUEST_ID_HEADER]
    assert re.fullmatch(REQUEST_ID_PATTERN, body["error"]["request_id"])
    return body


@pytest.mark.parametrize(
    "incoming_headers",
    [
        [
            (b"x-request-id", VALID_REQUEST_ID.encode("ascii")),
            (b"x-request-id", VALID_REQUEST_ID.encode("ascii")),
        ],
        [(b"x-request-id", b"req_\xff")],
    ],
    ids=["duplicate", "non-ascii"],
)
def test_ambiguous_or_non_ascii_request_id_headers_are_replaced(incoming_headers) -> None:
    resolved = resolve_request_id({"type": "http", "headers": incoming_headers})

    assert resolved != VALID_REQUEST_ID
    assert re.fullmatch(REQUEST_ID_PATTERN, resolved)


def test_success_and_list_envelopes_share_request_id_with_response_header(tmp_path: Path) -> None:
    client = TestClient(_build_app(tmp_path))

    success = client.get(f"{PLATFORM_API_PREFIX}/success", headers={REQUEST_ID_HEADER: VALID_REQUEST_ID})
    items = client.get(f"{PLATFORM_API_PREFIX}/items")

    assert success.status_code == 200
    assert success.headers[REQUEST_ID_HEADER] == VALID_REQUEST_ID
    assert success.json()["meta"]["request_id"] == VALID_REQUEST_ID
    assert set(success.json()["meta"]) == {
        "request_id",
        "schema_version",
        "generated_at",
        "data_snapshot_id",
        "warnings",
    }
    assert items.status_code == 200
    assert items.json()["page"] == {
        "cursor": None,
        "next_cursor": None,
        "limit": 50,
        "has_more": False,
    }
    assert items.json()["meta"]["request_id"] == items.headers[REQUEST_ID_HEADER]


@pytest.mark.parametrize(
    "invalid_request_id",
    [
        "",
        "request-123",
        "req_ABCDEF0123456789abcdef0123456789",
        "req_0123456789abcdef0123456789abcde",
        "req_0123456789abcdef0123456789abcdef forged",
    ],
)
def test_invalid_client_request_id_is_replaced_not_propagated(
    tmp_path: Path,
    invalid_request_id: str,
) -> None:
    response = TestClient(_build_app(tmp_path)).get(
        f"{PLATFORM_API_PREFIX}/success",
        headers={REQUEST_ID_HEADER: invalid_request_id},
    )

    generated = response.headers[REQUEST_ID_HEADER]
    assert generated != invalid_request_id
    assert re.fullmatch(REQUEST_ID_PATTERN, generated)
    assert response.json()["meta"]["request_id"] == generated


@pytest.mark.parametrize(
    ("status_code", "code", "retryable"),
    [
        (400, "VALIDATION_BAD_REQUEST", False),
        (401, "AUTH_REQUIRED", False),
        (403, "AUTH_FORBIDDEN", False),
        (404, "RESOURCE_NOT_FOUND", False),
        (409, "RESOURCE_CONFLICT", False),
        (422, "VALIDATION_CONTRACT_FAILED", False),
        (429, "RATE_LIMITED", True),
        (503, "PROVIDER_UNAVAILABLE", True),
    ],
)
def test_platform_error_statuses_use_stable_c010_shape(
    tmp_path: Path,
    status_code: int,
    code: str,
    retryable: bool,
) -> None:
    response = TestClient(_build_app(tmp_path)).get(
        f"{PLATFORM_API_PREFIX}/errors/{status_code}",
        headers={REQUEST_ID_HEADER: VALID_REQUEST_ID},
    )

    _assert_c010_error(response, status_code=status_code, code=code, retryable=retryable)


def test_platform_fastapi_validation_is_safe_400(tmp_path: Path) -> None:
    response = TestClient(_build_app(tmp_path)).get(
        f"{PLATFORM_API_PREFIX}/validate?limit=not-an-integer"
    )

    body = _assert_c010_error(
        response,
        status_code=400,
        code="VALIDATION_BAD_REQUEST",
        retryable=False,
    )
    assert body["error"]["details"]["violations"] == [
        {"location": ["query", "limit"], "type": "int_parsing"}
    ]


def test_platform_routing_404_uses_c010_shape(tmp_path: Path) -> None:
    response = TestClient(_build_app(tmp_path)).get(f"{PLATFORM_API_PREFIX}/missing")

    _assert_c010_error(
        response,
        status_code=404,
        code="RESOURCE_NOT_FOUND",
        retryable=False,
    )


def test_platform_auth_rejection_uses_same_request_id(tmp_path: Path) -> None:
    app = _build_app(tmp_path)
    with patch("api.middlewares.auth.is_auth_enabled", return_value=True):
        response = TestClient(app).get(
            f"{PLATFORM_API_PREFIX}/success",
            headers={REQUEST_ID_HEADER: VALID_REQUEST_ID},
        )

    _assert_c010_error(response, status_code=401, code="AUTH_REQUIRED", retryable=False)
    assert response.headers[REQUEST_ID_HEADER] == VALID_REQUEST_ID


def test_unknown_exception_is_internal_error_without_sensitive_leakage(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)
    response = TestClient(
        _build_app(tmp_path),
        raise_server_exceptions=False,
    ).get(
        f"{PLATFORM_API_PREFIX}/unknown",
        headers={REQUEST_ID_HEADER: VALID_REQUEST_ID},
    )

    serialized = json.dumps(
        _assert_c010_error(
            response,
            status_code=500,
            code="INTERNAL_ERROR",
            retryable=False,
        ),
        ensure_ascii=False,
    )
    for sensitive in ("super-secret", "postgresql://", "SELECT *", "C:\\private", "Traceback"):
        assert sensitive not in serialized
        assert sensitive not in caplog.text
    request_records = [record for record in caplog.records if getattr(record, "request_id", None)]
    assert request_records
    assert {record.request_id for record in request_records} == {VALID_REQUEST_ID}


def test_legacy_health_validation_routing_and_stream_bodies_remain_unwrapped(tmp_path: Path) -> None:
    client = TestClient(_build_app(tmp_path))

    health = client.get("/api/health")
    missing = client.get("/api/v1/does-not-exist")
    invalid = client.get("/api/v1/legacy-validate?limit=bad")
    stream = client.get("/api/v1/legacy-stream")

    assert health.status_code == 200
    assert set(health.json()) == {"status", "timestamp"}
    assert "data" not in health.json()
    assert missing.status_code == 404
    assert missing.json() == {"detail": "Not Found"}
    assert invalid.status_code == 422
    assert invalid.json()["error"] == "validation_error"
    assert "meta" not in invalid.json()
    assert stream.status_code == 200
    assert stream.text == "event: message\ndata: unchanged\n\n"
    assert stream.headers["content-type"].startswith("text/event-stream")
    assert re.fullmatch(REQUEST_ID_PATTERN, stream.headers[REQUEST_ID_HEADER])
