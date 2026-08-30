from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from api.platform.request_id import REQUEST_ID_HEADER, get_transport_request_id
from src.schemas.platform.api import PlatformAPIError, PlatformErrorEnvelope


logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ErrorSpec:
    code: str
    message: str
    retryable: bool


ERROR_SPECS: dict[int, ErrorSpec] = {
    400: ErrorSpec("VALIDATION_BAD_REQUEST", "请求无效", False),
    401: ErrorSpec("AUTH_REQUIRED", "需要认证", False),
    403: ErrorSpec("AUTH_FORBIDDEN", "无权访问该资源", False),
    404: ErrorSpec("RESOURCE_NOT_FOUND", "资源不存在", False),
    409: ErrorSpec("RESOURCE_CONFLICT", "资源状态冲突", False),
    422: ErrorSpec("VALIDATION_CONTRACT_FAILED", "请求不满足业务契约", False),
    429: ErrorSpec("RATE_LIMITED", "请求过于频繁", True),
    500: ErrorSpec("INTERNAL_ERROR", "服务器内部错误", False),
    503: ErrorSpec("PROVIDER_UNAVAILABLE", "依赖服务暂不可用", True),
}


class PlatformAPIException(Exception):
    """Typed public platform error; messages always come from the stable map."""

    def __init__(
        self,
        status_code: int,
        *,
        details: dict[str, Any] | None = None,
        code: str | None = None,
        message: str | None = None,
        retryable: bool | None = None,
    ) -> None:
        if status_code not in ERROR_SPECS:
            raise ValueError(f"unsupported platform error status: {status_code}")
        self.status_code = status_code
        spec = ERROR_SPECS[status_code]
        self.code = code or spec.code
        self.message = message or spec.message
        self.retryable = spec.retryable if retryable is None else retryable
        self.details = details or {}
        super().__init__(self.code)


def platform_error(
    status_code: int,
    *,
    details: dict[str, Any] | None = None,
    code: str | None = None,
    message: str | None = None,
    retryable: bool | None = None,
) -> PlatformAPIException:
    return PlatformAPIException(
        status_code,
        details=details,
        code=code,
        message=message,
        retryable=retryable,
    )


def platform_error_response(
    request: Request,
    *,
    status_code: int,
    details: dict[str, Any] | None = None,
    code: str | None = None,
    message: str | None = None,
    retryable: bool | None = None,
) -> JSONResponse:
    spec = ERROR_SPECS.get(status_code, ERROR_SPECS[500])
    effective_status = status_code if status_code in ERROR_SPECS else 500
    request_id = get_transport_request_id(request)
    envelope = PlatformErrorEnvelope(
        error=PlatformAPIError(
            code=code or spec.code,
            message=message or spec.message,
            details=details or {},
            retryable=spec.retryable if retryable is None else retryable,
            request_id=request_id,
        )
    )
    return JSONResponse(
        status_code=effective_status,
        content=envelope.model_dump(mode="json"),
        headers={REQUEST_ID_HEADER: request_id},
    )


def validation_error_details(errors: list[dict[str, Any]]) -> dict[str, Any]:
    """Project only stable location/type pairs; never echo input values or exception context."""

    violations = []
    for error in errors:
        location = [str(part) if not isinstance(part, int) else part for part in error.get("loc", ())]
        violations.append(
            {
                "location": location,
                "type": str(error.get("type", "validation_error")),
            }
        )
    return {"violations": violations}


def log_unknown_platform_exception(request: Request, exc: Exception) -> None:
    logger.error(
        "platform_api_unhandled_exception",
        extra={
            "request_id": get_transport_request_id(request),
            "exception_type": type(exc).__name__,
            "status_code": 500,
        },
    )
