from __future__ import annotations

import logging
import re
import time
import uuid
from contextvars import ContextVar
from typing import Any

from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from src.schemas.platform.api import REQUEST_ID_PATTERN

from .boundary import is_platform_path


REQUEST_ID_HEADER = "X-Request-ID"
_REQUEST_ID_HEADER_BYTES = REQUEST_ID_HEADER.lower().encode("ascii")
_REQUEST_ID_RE = re.compile(REQUEST_ID_PATTERN, flags=re.ASCII)
_STATE_KEY = "platform_request_id"
_transport_request_id: ContextVar[str | None] = ContextVar(
    "platform_transport_request_id",
    default=None,
)
logger = logging.getLogger(__name__)


def is_valid_request_id(value: str | None) -> bool:
    return bool(value is not None and _REQUEST_ID_RE.fullmatch(value))


def generate_request_id() -> str:
    return f"req_{uuid.uuid4().hex}"


def _incoming_request_ids(scope: Scope) -> tuple[str, ...]:
    values: list[str] = []
    for name, raw_value in scope.get("headers", ()):  # type: ignore[assignment]
        if name.lower() != _REQUEST_ID_HEADER_BYTES:
            continue
        try:
            values.append(raw_value.decode("ascii"))
        except UnicodeDecodeError:
            values.append("")
    return tuple(values)


def resolve_request_id(scope: Scope) -> str:
    incoming = _incoming_request_ids(scope)
    if len(incoming) == 1 and is_valid_request_id(incoming[0]):
        return incoming[0]
    return generate_request_id()


def current_transport_request_id() -> str | None:
    return _transport_request_id.get()


def get_transport_request_id(request: Request) -> str:
    """Read the HTTP correlation ID without touching Agent Chat business IDs."""

    request_id = getattr(request.state, _STATE_KEY, None)
    if is_valid_request_id(request_id):
        return request_id
    current = current_transport_request_id()
    if is_valid_request_id(current):
        setattr(request.state, _STATE_KEY, current)
        return current
    generated = generate_request_id()
    setattr(request.state, _STATE_KEY, generated)
    return generated


class RequestIDMiddleware:
    """Resolve one safe request ID and propagate it through HTTP responses and logs."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = resolve_request_id(scope)
        state = scope.setdefault("state", {})
        state[_STATE_KEY] = request_id
        token = _transport_request_id.set(request_id)
        started_at = time.perf_counter()
        status_code = 500

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
                headers = [
                    (name, value)
                    for name, value in message.get("headers", [])
                    if name.lower() != _REQUEST_ID_HEADER_BYTES
                ]
                headers.append((_REQUEST_ID_HEADER_BYTES, request_id.encode("ascii")))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        except Exception:
            log_context = {
                "request_id": request_id,
                "status_code": 500,
                "duration_ms": round((time.perf_counter() - started_at) * 1000, 3),
            }
            if not is_platform_path(str(scope.get("path", ""))):
                log_context.update(
                    {
                        "http_method": scope.get("method", ""),
                        "http_path": scope.get("path", ""),
                    }
                )
            logger.error("api_request_failed", extra=log_context)
            raise
        else:
            logger.info(
                "api_request_completed",
                extra={
                    "request_id": request_id,
                    "http_method": scope.get("method", ""),
                    "http_path": scope.get("path", ""),
                    "status_code": status_code,
                    "duration_ms": round((time.perf_counter() - started_at) * 1000, 3),
                },
            )
        finally:
            _transport_request_id.reset(token)


def add_request_id_middleware(app: Any) -> None:
    app.add_middleware(RequestIDMiddleware)
