"""Application factory for the Privacy Guardian control plane."""

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from app.backend.api.actions import router as actions_router
from app.backend.api.findings import router as findings_router
from app.backend.api.health import router as health_router
from app.backend.api.jobs import router as jobs_router
from app.backend.api.logs import router as logs_router
from app.backend.api.reports import router as reports_router
from app.backend.api.scans import router as scans_router
from app.backend.api.settings import router as settings_router
from app.backend.api.workers import router as workers_router
from app.backend.config import settings
from app.backend.database.engine import init_db
from app.backend.errors import http_exception_handler, validation_exception_handler
from app.backend.security.middleware import SecurityHeadersMiddleware


def create_app() -> FastAPI:
    app = FastAPI(
        title="Privacy Guardian",
        version="0.1.0",
        description="Local-first personal privacy/OSINT assistant control plane",
    )

    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)

    app.include_router(health_router)
    app.include_router(scans_router)
    app.include_router(findings_router)
    app.include_router(actions_router)
    app.include_router(jobs_router)
    app.include_router(workers_router)
    app.include_router(reports_router)
    app.include_router(logs_router)
    app.include_router(settings_router)
    return app


app = create_app()


@app.on_event("startup")
def _startup() -> None:
    init_db()