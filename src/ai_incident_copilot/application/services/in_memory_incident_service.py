"""Временная in-memory реализация сервиса инцидентов для API-каркаса."""

from __future__ import annotations

from asyncio import Lock
from dataclasses import dataclass
from datetime import UTC, datetime
from math import ceil
from typing import Any
from uuid import UUID, uuid4

from ai_incident_copilot.api.schemas.incidents import (
    IncidentCreateRequest,
    IncidentFilterParams,
    IncidentResponse,
    IncidentStatus,
    IncidentSummary,
    IncidentUpdateResponse,
    PaginationParams,
)


@dataclass(slots=True)
class StoredIncident:
    """Внутреннее представление инцидента для in-memory хранилища."""

    id: UUID
    title: str
    description: str
    source: str | None
    status: IncidentStatus
    classification: str | None
    severity: str | None
    recommendation: str | None
    idempotency_key: str | None
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, Any]

    def to_response(self) -> IncidentResponse:
        """Преобразует внутреннюю запись в модель API."""

        return IncidentResponse(
            id=self.id,
            title=self.title,
            description=self.description,
            source=self.source,
            status=self.status,
            classification=self.classification,
            severity=self.severity,
            recommendation=self.recommendation,
            created_at=self.created_at,
            updated_at=self.updated_at,
            metadata=self.metadata,
        )

    def to_summary(self) -> IncidentSummary:
        """Преобразует внутреннюю запись в сокращённое представление."""

        return IncidentSummary(
            id=self.id,
            title=self.title,
            source=self.source,
            status=self.status,
            classification=self.classification,
            severity=self.severity,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )


class InMemoryIncidentService:
    """Потокобезопасный in-memory сервис для начального этапа разработки API."""

    def __init__(self) -> None:
        self._storage: dict[UUID, StoredIncident] = {}
        self._idempotency_index: dict[str, UUID] = {}
        self._lock = Lock()

    async def create(
        self,
        payload: IncidentCreateRequest,
        idempotency_key: str | None,
    ) -> IncidentResponse:
        """Создаёт инцидент или возвращает уже созданный по ключу идемпотентности."""

        async with self._lock:
            if idempotency_key and idempotency_key in self._idempotency_index:
                existing_id = self._idempotency_index[idempotency_key]
                return self._storage[existing_id].to_response()

            now = datetime.now(tz=UTC)
            incident = StoredIncident(
                id=uuid4(),
                title=payload.title,
                description=payload.description,
                source=payload.source,
                status=IncidentStatus.RECEIVED,
                classification=None,
                severity=None,
                recommendation=None,
                idempotency_key=idempotency_key,
                created_at=now,
                updated_at=now,
                metadata=payload.metadata,
            )
            self._storage[incident.id] = incident
            if idempotency_key:
                self._idempotency_index[idempotency_key] = incident.id
            return incident.to_response()

    async def get(self, incident_id: UUID) -> IncidentResponse | None:
        """Возвращает один инцидент по идентификатору."""

        incident = self._storage.get(incident_id)
        if incident is None:
            return None
        return incident.to_response()

    async def list(
        self,
        pagination: PaginationParams,
        filters: IncidentFilterParams,
    ) -> IncidentUpdateResponse:
        """Возвращает список инцидентов с пагинацией и фильтрацией."""

        incidents = list(self._storage.values())

        filtered = [
            incident
            for incident in incidents
            if self._matches_filters(incident, filters)
        ]
        filtered.sort(key=lambda item: item.created_at, reverse=True)

        total = len(filtered)
        start = (pagination.page - 1) * pagination.page_size
        end = start + pagination.page_size
        page_items = filtered[start:end]
        total_pages = ceil(total / pagination.page_size) if total else 1

        return IncidentUpdateResponse(
            items=[incident.to_summary() for incident in page_items],
            total=total,
            page=pagination.page,
            page_size=pagination.page_size,
            total_pages=total_pages,
        )

    async def request_analysis(self, incident_id: UUID) -> IncidentResponse | None:
        """Переводит инцидент в состояние ожидания анализа."""

        async with self._lock:
            incident = self._storage.get(incident_id)
            if incident is None:
                return None

            incident.status = IncidentStatus.ANALYSIS_REQUESTED
            incident.updated_at = datetime.now(tz=UTC)
            return incident.to_response()

    @staticmethod
    def _matches_filters(
        incident: StoredIncident,
        filters: IncidentFilterParams,
    ) -> bool:
        if filters.status and incident.status != filters.status:
            return False
        if filters.classification and incident.classification != filters.classification:
            return False
        if filters.severity and incident.severity != filters.severity:
            return False
        if filters.source and incident.source != filters.source:
            return False
        return True
