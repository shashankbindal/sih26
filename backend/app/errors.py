"""Uniform error envelope: {"error": {"code", "message", "details"}}."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("loksutra")

STATUS_CODES = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    422: "VALIDATION_ERROR",
    429: "RATE_LIMITED",
}


class ApiError(HTTPException):
    """Raise from routers/services: ApiError(404, "NOT_FOUND", "Case not found")."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(status_code=status_code, detail=message, headers=headers)
        self.code = code
        self.message = message
        self.details = details or {}


def envelope(code: str, message: str, details: Any = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details or {}}}


def _rid(request: Request) -> dict[str, str]:
    rid = getattr(request.state, "request_id", None)
    return {"X-Request-ID": rid} if rid else {}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def http_exc(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        if isinstance(exc, ApiError):
            code, message, details = exc.code, exc.message, exc.details
        else:
            code = STATUS_CODES.get(exc.status_code, "ERROR")
            message = exc.detail if isinstance(exc.detail, str) else "Request failed"
            details = {} if isinstance(exc.detail, str) else {"detail": exc.detail}
        headers = {**(exc.headers or {}), **_rid(request)}
        return JSONResponse(envelope(code, message, details), status_code=exc.status_code, headers=headers)

    @app.exception_handler(RequestValidationError)
    async def validation_exc(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [
            {"loc": [str(p) for p in e.get("loc", ())], "msg": e.get("msg"), "type": e.get("type")}
            for e in exc.errors()
        ]
        return JSONResponse(
            envelope("VALIDATION_ERROR", "Request validation failed", {"errors": errors}),
            status_code=422,
            headers=_rid(request),
        )

    @app.exception_handler(Exception)
    async def unhandled_exc(request: Request, exc: Exception) -> JSONResponse:
        # Log type and path only: exception text can contain row data (PII).
        log.error("unhandled %s on %s %s", type(exc).__name__, request.method, request.url.path)
        return JSONResponse(
            envelope("INTERNAL_ERROR", "Internal server error"),
            status_code=500,
            headers=_rid(request),
        )
