"""Lok Sutra API entrypoint."""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api import admin as admin_api
from app.api import auth, cases, health, institutions, passport, search
from app.api import cases_write as cases_write_api
from app.api import clearances as clearances_api
from app.api import dashboard as dashboard_api
from app.api import evaluation as evaluation_api
from app.api import imports as imports_api
from app.api import institution_write as institution_write_api
from app.api import intake as intake_api
from app.api import links as links_api
from app.api import notifications as notifications_api
from app.api import preaction as preaction_api
from app.api import reports as reports_api
from app.api import review as review_api
from app.api import risk as risk_api
from app.config import get_settings
from app.errors import install_error_handlers
from app.scheduler import start_scheduler, stop_scheduler

API_PREFIX = "/api/v1"


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key in ("request_id", "method", "path", "status", "ms"):
            if hasattr(record, key):
                data[key] = getattr(record, key)
        return json.dumps(data)


def redact_query(path: str) -> str:
    """'/api/v1/search?q=Asha' -> '/api/v1/search?[redacted]' (query strings can carry PII)."""
    base, sep, _query = path.partition("?")
    return f"{base}?[redacted]" if sep else path


class RedactQueryFilter(logging.Filter):
    """Strips query strings from uvicorn access-log records (client, method, path, http, status)."""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple) and len(args) >= 3 and isinstance(args[2], str):
            record.args = (*args[:2], redact_query(args[2]), *args[3:])
        elif isinstance(record.msg, str) and "?" in record.msg and not args:
            record.msg = re.sub(r"\?\S*", "?[redacted]", record.msg)
        return True


def install_access_log_redaction() -> None:
    access = logging.getLogger("uvicorn.access")
    if not any(isinstance(f, RedactQueryFilter) for f in access.filters):
        access.addFilter(RedactQueryFilter())


def _configure_logging() -> None:
    logger = logging.getLogger("loksutra")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    _configure_logging()
    # Scheduler / model warm-up are registered here (scheduler.py).
    start_scheduler()
    yield
    stop_scheduler()


def create_app() -> FastAPI:
    settings = get_settings()
    install_access_log_redaction()
    app = FastAPI(
        title="Lok Sutra API",
        version=settings.app_version,
        openapi_url="/openapi.json",
        docs_url="/docs",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        request.state.request_id = rid
        started = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        # path only: query strings can carry names (PII)
        logging.getLogger("loksutra").info(
            "request",
            extra={
                "request_id": rid,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "ms": round((time.perf_counter() - started) * 1000, 1),
            },
        )
        return response

    install_error_handlers(app)

    # --- routers: add one include_router line per module ---
    app.include_router(health.router, prefix=API_PREFIX)
    app.include_router(auth.router, prefix=API_PREFIX)
    app.include_router(search.router, prefix=API_PREFIX)
    app.include_router(institutions.router, prefix=API_PREFIX)
    app.include_router(cases.router, prefix=API_PREFIX)
    app.include_router(passport.router, prefix=API_PREFIX)
    app.include_router(dashboard_api.router, prefix=API_PREFIX)
    app.include_router(reports_api.router, prefix=API_PREFIX)
    app.include_router(admin_api.router, prefix=API_PREFIX)
    app.include_router(admin_api.config_router, prefix=API_PREFIX)
    app.include_router(imports_api.router, prefix=API_PREFIX)
    app.include_router(evaluation_api.router, prefix=API_PREFIX)
    app.include_router(risk_api.router, prefix=API_PREFIX)
    app.include_router(cases_write_api.router, prefix=API_PREFIX)
    app.include_router(institution_write_api.router, prefix=API_PREFIX)
    app.include_router(intake_api.router, prefix=API_PREFIX)
    app.include_router(review_api.router, prefix=API_PREFIX)
    app.include_router(links_api.router, prefix=API_PREFIX)
    app.include_router(preaction_api.router, prefix=API_PREFIX)
    app.include_router(clearances_api.router, prefix=API_PREFIX)
    app.include_router(notifications_api.router, prefix=API_PREFIX)
    # --- end routers ---
    return app


app = create_app()
