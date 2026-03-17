"""Маршруты healthcheck.

Это не бизнес-API, а эксплуатационный endpoint. Его основная задача —
дать Kubernetes, мониторингу и инженерам быстрый ответ, жив ли сервис и
в каком состоянии его ключевые зависимости.
"""

from __future__ import annotations

from fastapi import APIRouter

from ai_incident_copilot.api.dependencies import (
    DatabaseManagerDependency,
    EventPublisherDependency,
    SettingsDependency,
)
from ai_incident_copilot.api.schemas.common import ResponseEnvelope
from ai_incident_copilot.api.schemas.health import HealthResponse, HealthStatus
from ai_incident_copilot.core.logging import get_logger

router = APIRouter(tags=["health"])


@router.get("/health", response_model=ResponseEnvelope[HealthResponse])
async def healthcheck(
    settings: SettingsDependency,
    database_manager: DatabaseManagerDependency,
    event_publisher: EventPublisherDependency,
) -> ResponseEnvelope[HealthResponse]:
    """Возвращает агрегированный статус приложения и зависимостей.

    Endpoint специально не падает с `500`, если одна из зависимостей недоступна.
    Вместо этого он возвращает `degraded`, чтобы оркестратор и операторы видели
    частичную деградацию, а не только факт полного отказа процесса.
    """

    logger = get_logger(__name__)
    status_value = HealthStatus.OK
    checks = {"api": "ok"}

    try:
        await database_manager.check_health()
        checks["database"] = "ok"
    except Exception as exc:
        # Ошибка БД не ломает сам health endpoint, а переводит статус сервиса
        # в degraded и сохраняет причину в логах.
        status_value = HealthStatus.DEGRADED
        checks["database"] = "error"
        logger.warning("Проверка базы данных завершилась ошибкой", error=str(exc))

    kafka_status = await event_publisher.health_status()
    checks["kafka"] = kafka_status
    # Kafka publisher может быть в `disabled`, `starting`, `ok` или `error`.
    # Критичным для health считаем только явный `error`.
    if kafka_status == "error":
        status_value = HealthStatus.DEGRADED

    return ResponseEnvelope(
        data=HealthResponse(
            status=status_value,
            service=settings.app_name,
            environment=settings.app_env,
            version=settings.app_version,
            checks=checks,
        )
    )
