"""Зависимости FastAPI."""

from __future__ import annotations

from typing import Annotated, cast

from fastapi import Depends, Header, Request

from ai_incident_copilot.application.services.in_memory_incident_service import (
    InMemoryIncidentService,
)
from ai_incident_copilot.core.config import Settings, get_settings


def get_app_settings() -> Settings:
    """Возвращает singleton-конфигурацию приложения."""

    return get_settings()


def get_incident_service(request: Request) -> InMemoryIncidentService:
    """Возвращает сервис обработки инцидентов из состояния приложения."""

    return cast(InMemoryIncidentService, request.app.state.incident_service)


def get_idempotency_key(
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> str | None:
    """Извлекает ключ идемпотентности из заголовка запроса."""

    return idempotency_key


SettingsDependency = Annotated[Settings, Depends(get_app_settings)]
IncidentServiceDependency = Annotated[
    InMemoryIncidentService,
    Depends(get_incident_service),
]
IdempotencyKeyDependency = Annotated[str | None, Depends(get_idempotency_key)]
