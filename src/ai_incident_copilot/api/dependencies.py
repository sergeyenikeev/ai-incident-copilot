"""Зависимости FastAPI."""

from __future__ import annotations

from typing import Annotated, cast

from fastapi import Depends, Header, Request

from ai_incident_copilot.application.services.incident_service import IncidentService
from ai_incident_copilot.core.config import Settings, get_settings
from ai_incident_copilot.db.session import DatabaseManager
from ai_incident_copilot.events.kafka import EventPublisher


def get_app_settings() -> Settings:
    """Возвращает singleton-конфигурацию приложения."""

    return get_settings()


def get_incident_service(request: Request) -> IncidentService:
    """Возвращает сервис обработки инцидентов из состояния приложения."""

    return cast(IncidentService, request.app.state.incident_service)


def get_database_manager(request: Request) -> DatabaseManager:
    """Возвращает менеджер базы данных из состояния приложения."""

    return cast(DatabaseManager, request.app.state.database_manager)


def get_event_publisher(request: Request) -> EventPublisher:
    """Возвращает publisher событий из состояния приложения."""

    return cast(EventPublisher, request.app.state.event_publisher)


def get_idempotency_key(
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> str | None:
    """Извлекает ключ идемпотентности из заголовка запроса."""

    return idempotency_key


SettingsDependency = Annotated[Settings, Depends(get_app_settings)]
IncidentServiceDependency = Annotated[
    IncidentService,
    Depends(get_incident_service),
]
DatabaseManagerDependency = Annotated[DatabaseManager, Depends(get_database_manager)]
EventPublisherDependency = Annotated[EventPublisher, Depends(get_event_publisher)]
IdempotencyKeyDependency = Annotated[str | None, Depends(get_idempotency_key)]
