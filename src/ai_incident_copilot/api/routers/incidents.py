"""Маршруты работы с инцидентами."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Query, status

from ai_incident_copilot.api.dependencies import (
    IdempotencyKeyDependency,
    IncidentServiceDependency,
)
from ai_incident_copilot.api.errors import ApplicationError
from ai_incident_copilot.api.schemas.common import PaginatedResponse, ResponseEnvelope
from ai_incident_copilot.api.schemas.incidents import (
    IncidentCreateRequest,
    IncidentFilterParams,
    IncidentListResponse,
    IncidentResponse,
    IncidentStatus,
    PaginationMeta,
    PaginationParams,
)

router = APIRouter(prefix="/api/v1/incidents", tags=["incidents"])


@router.post(
    "",
    response_model=ResponseEnvelope[IncidentResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_incident(
    payload: IncidentCreateRequest,
    service: IncidentServiceDependency,
    idempotency_key: IdempotencyKeyDependency,
) -> ResponseEnvelope[IncidentResponse]:
    """Создаёт новый инцидент."""

    incident = await service.create(payload, idempotency_key)
    return ResponseEnvelope(data=incident)


@router.get("/{incident_id}", response_model=ResponseEnvelope[IncidentResponse])
async def get_incident(
    incident_id: UUID,
    service: IncidentServiceDependency,
) -> ResponseEnvelope[IncidentResponse]:
    """Возвращает один инцидент по идентификатору."""

    incident = await service.get(incident_id)
    if incident is None:
        raise ApplicationError(
            "Инцидент не найден",
            error_code="incident_not_found",
            status_code=status.HTTP_404_NOT_FOUND,
            details={"incident_id": str(incident_id)},
        )
    return ResponseEnvelope(data=incident)


@router.get("", response_model=PaginatedResponse[IncidentListResponse])
async def list_incidents(
    service: IncidentServiceDependency,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status_filter: IncidentStatus | None = Query(default=None, alias="status"),
    classification: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    source: str | None = Query(default=None),
) -> PaginatedResponse[IncidentListResponse]:
    """Возвращает список инцидентов с пагинацией и фильтрацией."""

    filters = IncidentFilterParams(
        status=status_filter,
        classification=classification,
        severity=severity,
        source=source,
    )
    result = await service.list(
        pagination=PaginationParams(page=page, page_size=page_size),
        filters=filters,
    )
    return PaginatedResponse(
        data=IncidentListResponse(items=result.items),
        pagination=PaginationMeta(
            page=result.page,
            page_size=result.page_size,
            total=result.total,
            total_pages=result.total_pages,
        ),
    )


@router.post(
    "/{incident_id}/analyze",
    response_model=ResponseEnvelope[IncidentResponse],
)
async def analyze_incident(
    incident_id: UUID,
    service: IncidentServiceDependency,
) -> ResponseEnvelope[IncidentResponse]:
    """Переводит инцидент в очередь на анализ."""

    incident = await service.request_analysis(incident_id)
    if incident is None:
        raise ApplicationError(
            "Инцидент не найден",
            error_code="incident_not_found",
            status_code=status.HTTP_404_NOT_FOUND,
            details={"incident_id": str(incident_id)},
        )
    return ResponseEnvelope(data=incident)
