"""Application factory for the Privacy Guardian control plane."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.backend.api.health import router as health_router
from app.backend.config import settings


def create_app() -> FastAPI:
    app = FastAPI(
        title="Privacy Guardian",
        version="0.1.0",
        description="Local-first personal privacy/OSINT assistant control plane",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health_router)
    return app


app = create_app()