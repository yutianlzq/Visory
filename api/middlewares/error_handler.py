# -*- coding: utf-8 -*-
"""
===================================
全局异常处理中间件
===================================

职责：
1. 捕获未处理的异常
2. 统一错误响应格式
3. 记录错误日志
"""

import logging
import traceback
from typing import Callable

from fastapi import HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from api.platform.boundary import is_platform_request
from api.platform.errors import (
    PlatformAPIException,
    log_unknown_platform_exception,
    platform_error_response,
    validation_error_details,
)

logger = logging.getLogger(__name__)


class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    """
    全局异常处理中间件
    
    捕获所有未处理的异常，返回统一格式的错误响应
    """
    
    async def dispatch(
        self, 
        request: Request, 
        call_next: Callable
    ) -> Response:
        """
        处理请求，捕获异常
        
        Args:
            request: 请求对象
            call_next: 下一个处理器
            
        Returns:
            Response: 响应对象
        """
        try:
            response = await call_next(request)
            return response
            
        except Exception as e:
            # 记录错误日志
            logger.error(
                f"未处理的异常: {e}\n"
                f"请求路径: {request.url.path}\n"
                f"请求方法: {request.method}\n"
                f"堆栈: {traceback.format_exc()}"
            )
            
            # 返回统一格式的错误响应
            return JSONResponse(
                status_code=500,
                content={
                    "error": "internal_error",
                    "message": "服务器内部错误，请稍后重试",
                    "detail": str(e) if logger.isEnabledFor(logging.DEBUG) else None
                }
            )


def add_error_handlers(app) -> None:
    """Register platform adapters while preserving Legacy response bodies."""

    @app.exception_handler(PlatformAPIException)
    async def platform_exception_handler(request: Request, exc: PlatformAPIException):
        return platform_error_response(
            request,
            status_code=exc.status_code,
            details=exc.details,
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        """Handle endpoint-raised HTTP errors."""
        if is_platform_request(request):
            return platform_error_response(request, status_code=exc.status_code)
        if isinstance(exc.detail, dict) and "error" in exc.detail and "message" in exc.detail:
            return JSONResponse(status_code=exc.status_code, content=exc.detail)
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": "http_error",
                "message": str(exc.detail) if exc.detail else "HTTP Error",
                "detail": None,
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def routing_exception_handler(request: Request, exc: StarletteHTTPException):
        """Adapt platform routing errors without changing Legacy 404 bodies."""
        if is_platform_request(request):
            return platform_error_response(request, status_code=exc.status_code)
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        """Map platform request syntax errors to safe 400 responses."""
        if is_platform_request(request):
            return platform_error_response(
                request,
                status_code=400,
                details=validation_error_details(exc.errors()),
            )
        return JSONResponse(
            status_code=422,
            content={
                "error": "validation_error",
                "message": "请求参数验证失败",
                "detail": exc.errors(),
            },
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        """Keep unknown platform failures stable and free of sensitive context."""
        if is_platform_request(request):
            log_unknown_platform_exception(request, exc)
            return platform_error_response(request, status_code=500)
        logger.error(
            f"未处理的异常: {exc}\n"
            f"请求路径: {request.url.path}\n"
            f"堆栈: {traceback.format_exc()}"
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": "internal_error",
                "message": "服务器内部错误",
                "detail": None,
            },
        )
