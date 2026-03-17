"""Маршруты healthcheck."""

from __future__ import annotations

from fastapi import APIRouter

from ai_incident_copilot.api.dependencies import DatabaseManagerDependency, SettingsDependency
from ai_incident_copilot.api.schemas.common import ResponseEnvelope
from ai_incident_copilot.api.schemas.health import HealthResponse, HealthStatus
from ai_incident_copilot.core.logging import get_logger

router = APIRouter(tags=["health"])


@router.get("/health", response_model=ResponseEnvelope[HealthResponse])
async def healthcheck(
    settings: SettingsDependency,
    database_manager: DatabaseManagerDependency,
) -> ResponseEnvelope[HealthResponse]:
    """Возвращает базовый статус приложения."""

    logger = get_logger(__name__)
    status_value = HealthStatus.OK
    checks = {"api": "ok"}

    try:
        await database_manager.check_health()
        checks["database"] = "ok"
    except Exception as exc:
        status_value = HealthStatus.DEGRADED
        checks["database"] = "error"
        logger.warning("Проверка базы данных завершилась ошибкой", error=str(exc))

    return ResponseEnvelope(
        data=HealthResponse(
            status=status_value,
            service=settings.app_name,
            environment=settings.app_env,
            version=settings.app_version,
            checks=checks,
        )
    )
