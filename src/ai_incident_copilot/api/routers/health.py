"""Маршруты healthcheck."""

from __future__ import annotations

from fastapi import APIRouter

from ai_incident_copilot.api.dependencies import SettingsDependency
from ai_incident_copilot.api.schemas.common import ResponseEnvelope
from ai_incident_copilot.api.schemas.health import HealthResponse, HealthStatus

router = APIRouter(tags=["health"])


@router.get("/health", response_model=ResponseEnvelope[HealthResponse])
async def healthcheck(settings: SettingsDependency) -> ResponseEnvelope[HealthResponse]:
    """Возвращает базовый статус приложения."""

    return ResponseEnvelope(
        data=HealthResponse(
            status=HealthStatus.OK,
            service=settings.app_name,
            environment=settings.app_env,
            version=settings.app_version,
            checks={"api": "ok"},
        )
    )
