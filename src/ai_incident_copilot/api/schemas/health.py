"""Схемы для проверки состояния сервиса."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class HealthStatus(StrEnum):
    """Статус healthcheck."""

    OK = "ok"
    DEGRADED = "degraded"


class HealthResponse(BaseModel):
    """Ответ эндпоинта `/health`."""

    status: HealthStatus
    service: str
    environment: str
    version: str
    checks: dict[str, str] = Field(default_factory=dict)
