"""Точка входа API-приложения."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator

from ai_incident_copilot.api.errors import register_exception_handlers
from ai_incident_copilot.api.middleware import RequestContextMiddleware
from ai_incident_copilot.api.routers.health import router as health_router
from ai_incident_copilot.api.routers.incidents import router as incidents_router
from ai_incident_copilot.application.services.incident_service import IncidentService
from ai_incident_copilot.core.config import Settings, get_settings
from ai_incident_copilot.core.logging import clear_logging_context, configure_logging, get_logger
from ai_incident_copilot.db.session import DatabaseManager


def create_app(settings: Settings | None = None) -> FastAPI:
    """Создаёт и настраивает экземпляр FastAPI."""

    app_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        """Жизненный цикл FastAPI-приложения."""

        configure_logging(app_settings.app_log_level)
        logger = get_logger(__name__)
        database_manager = DatabaseManager(app_settings.database_url_async)

        app.state.settings = app_settings
        app.state.database_manager = database_manager
        app.state.incident_service = IncidentService(database_manager.session_factory)

        logger.info(
            "API-сервис запускается",
            service=app_settings.app_name,
            environment=app_settings.app_env,
            version=app_settings.app_version,
        )
        yield
        clear_logging_context()
        await database_manager.dispose()
        logger.info("API-сервис остановлен")

    app = FastAPI(
        title="AI Incident Copilot",
        version=app_settings.app_version,
        debug=app_settings.app_debug,
        lifespan=lifespan,
    )

    app.add_middleware(RequestContextMiddleware)
    app.include_router(health_router)
    app.include_router(incidents_router)
    register_exception_handlers(app)

    instrumentator = Instrumentator(excluded_handlers=["/metrics"])
    instrumentator.instrument(app).expose(app, include_in_schema=False, endpoint="/metrics")

    return app


app = create_app()


def main() -> None:
    """Запускает HTTP API через Uvicorn."""

    settings = get_settings()
    uvicorn.run(
        "ai_incident_copilot.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.app_debug,
        factory=False,
    )


if __name__ == "__main__":
    main()
