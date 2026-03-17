"""Сервис работы с инцидентами поверх SQLAlchemy-репозиториев."""

from __future__ import annotations

from math import ceil
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_incident_copilot.api.schemas.incidents import (
    IncidentCreateRequest,
    IncidentFilterParams,
    IncidentResponse,
    IncidentSummary,
    IncidentUpdateResponse,
    PaginationParams,
)
from ai_incident_copilot.core.logging import get_request_id
from ai_incident_copilot.db.models import Incident
from ai_incident_copilot.db.repositories.audit import AuditLogRepository
from ai_incident_copilot.db.repositories.incidents import IncidentRepository
from ai_incident_copilot.domain.enums import IncidentStatus


class IncidentService:
    """Прикладной сервис CRUD-операций с инцидентами."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def create(
        self,
        payload: IncidentCreateRequest,
        idempotency_key: str | None,
    ) -> IncidentResponse:
        """Создаёт инцидент с учётом идемпотентности."""

        async with self._session_factory() as session:
            incident_repository = IncidentRepository(session)
            audit_repository = AuditLogRepository(session)

            if idempotency_key:
                existing = await incident_repository.get_by_idempotency_key(idempotency_key)
                if existing is not None:
                    return self._to_response(existing)

            incident = Incident(
                title=payload.title,
                description=payload.description,
                source=payload.source,
                status=IncidentStatus.RECEIVED,
                idempotency_key=idempotency_key,
                payload_metadata=payload.metadata,
            )
            incident_repository.add(incident)
            await session.flush()

            audit_repository.create(
                incident_id=incident.id,
                entity_type="incident",
                entity_id=incident.id,
                action="incident.created",
                actor="api",
                request_id=get_request_id(),
                payload={
                    "title": incident.title,
                    "source": incident.source,
                    "idempotency_key": idempotency_key,
                },
            )
            await session.commit()
            await session.refresh(incident)
            return self._to_response(incident)

    async def get(self, incident_id: UUID) -> IncidentResponse | None:
        """Возвращает инцидент по идентификатору."""

        async with self._session_factory() as session:
            incident = await IncidentRepository(session).get_by_id(incident_id)
            if incident is None:
                return None
            return self._to_response(incident)

    async def list(
        self,
        pagination: PaginationParams,
        filters: IncidentFilterParams,
    ) -> IncidentUpdateResponse:
        """Возвращает страницу инцидентов."""

        async with self._session_factory() as session:
            incidents, total = await IncidentRepository(session).list_paginated(pagination, filters)
            total_pages = ceil(total / pagination.page_size) if total else 1
            return IncidentUpdateResponse(
                items=[self._to_summary(item) for item in incidents],
                total=total,
                page=pagination.page,
                page_size=pagination.page_size,
                total_pages=total_pages,
            )

    async def request_analysis(self, incident_id: UUID) -> IncidentResponse | None:
        """Переводит инцидент в состояние ожидания анализа."""

        async with self._session_factory() as session:
            incident_repository = IncidentRepository(session)
            audit_repository = AuditLogRepository(session)
            incident = await incident_repository.get_by_id(incident_id)
            if incident is None:
                return None

            incident.status = IncidentStatus.ANALYSIS_REQUESTED
            await session.flush()

            audit_repository.create(
                incident_id=incident.id,
                entity_type="incident",
                entity_id=incident.id,
                action="incident.analysis_requested",
                actor="api",
                request_id=get_request_id(),
                payload={"status": incident.status.value},
            )
            await session.commit()
            await session.refresh(incident)
            return self._to_response(incident)

    @staticmethod
    def _to_response(incident: Incident) -> IncidentResponse:
        return IncidentResponse(
            id=incident.id,
            title=incident.title,
            description=incident.description,
            source=incident.source,
            status=incident.status,
            classification=incident.classification,
            severity=incident.severity,
            recommendation=incident.recommendation,
            created_at=incident.created_at,
            updated_at=incident.updated_at,
            metadata=incident.payload_metadata,
        )

    @staticmethod
    def _to_summary(incident: Incident) -> IncidentSummary:
        return IncidentSummary(
            id=incident.id,
            title=incident.title,
            source=incident.source,
            status=incident.status,
            classification=incident.classification,
            severity=incident.severity,
            created_at=incident.created_at,
            updated_at=incident.updated_at,
        )
