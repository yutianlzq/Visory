from __future__ import annotations

from starlette.requests import Request


PLATFORM_API_PREFIX = "/api/platform/v1"


def is_platform_path(path: str) -> bool:
    """Return whether a request path belongs to the new C-010 platform boundary."""

    normalized = path.rstrip("/") or "/"
    return normalized == PLATFORM_API_PREFIX or normalized.startswith(f"{PLATFORM_API_PREFIX}/")


def is_platform_request(request: Request) -> bool:
    return is_platform_path(request.url.path)
