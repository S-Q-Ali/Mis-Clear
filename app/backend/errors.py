"""Consistent API error shape.

Every error response: {"error": {"code": str, "message": str, "details": ...}}.
Status map: 400 bad request · 404 not found · 409 conflict ·
422 validation · 500 internal (never leak internals).
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


def api_error(status_code: int, code: str, message: str, details: Any = None) -> HTTPException:
    body = {"error": {"code": code, "message": message}}
    if details is not None:
        body["error"]["details"] = details
    return HTTPException(status_code=status_code, detail=body)


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Invalid request data",
                "details": jsonable_encoder(exc.errors()),
            }
        },
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    if isinstance(exc.detail, dict):
        detail = exc.detail
    else:
        detail = {
            "error": {"code": f"HTTP_{exc.status_code}", "message": str(exc.detail)}
        }
    return JSONResponse(status_code=exc.status_code, content=detail)