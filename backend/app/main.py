from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import chat, courses, health, ingestion
from app.container import Container
from app.core.config import get_settings
from app.core.errors import register_handlers
from app.core.logging import setup_logging


def create_app(container: Container | None = None) -> FastAPI:
    setup_logging()
    settings = container.settings if container else get_settings()
    app = FastAPI(title=settings.app_name, version=settings.app_version)
    app.state.container = container  # built lazily on first request when None
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
                       allow_headers=["Content-Type", "X-Admin-Key", "Authorization"])
    register_handlers(app)
    for r in (health.router, chat.router, courses.router, ingestion.router):
        app.include_router(r)
    return app


app = create_app()
