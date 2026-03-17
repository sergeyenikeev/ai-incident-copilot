"""Схемы для проверки состояния сервиса.

Health endpoint намеренно отделён в собственные схемы, потому что его задача
отличается от бизнес-API: он нужен не клиентскому продукту, а эксплуатации.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class HealthStatus(StrEnum):
    """Статус healthcheck.

    Сейчас модель минималистична: `ok` и `degraded`. Этого достаточно, чтобы
    отличать штатную работу от частичной деградации зависимостей.
    """

    OK = "ok"
    DEGRADED = "degraded"


class HealthResponse(BaseModel):
    """Ответ эндпоинта `/health`."""

    status: HealthStatus
    service: str
    environment: str
    version: str
    checks: dict[str, str] = Field(default_factory=dict)
