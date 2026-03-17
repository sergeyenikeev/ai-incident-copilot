"""Сервис работы с инцидентами поверх SQLAlchemy-репозиториев."""

from __future__ import annotations

from math import ceil
from uuid import UUID, uuid4

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_incident_copilot.api.schemas.incidents import (
    IncidentCreateRequest,
    IncidentFilterParams,
    IncidentResponse,
    IncidentSummary,
    IncidentUpdateResponse,
    PaginationParams,
)
from ai_incident_copilot.core.logging import get_logger, get_request_id
from ai_incident_copilot.db.models import Incident, IncidentEvent
from ai_incident_copilot.db.repositories.audit import AuditLogRepository
from ai_incident_copilot.db.repositories.events import IncidentEventRepository
from ai_incident_copilot.db.repositories.incidents import IncidentRepository
from ai_incident_copilot.domain.enums import (
    EventProcessingStatus,
    IncidentEventType,
    IncidentStatus,
)
from ai_incident_copilot.events.kafka import EventPublisher, PublisherUnavailableError
from ai_incident_copilot.events.schemas import (
    EventMetadata,
    IncidentAnalysisRequestedPayload,
    IncidentCreatedPayload,
    IncidentEventMessage,
)


class IncidentService:
    """Прикладной сервис CRUD-операций с инцидентами."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        event_publisher: EventPublisher,
    ) -> None:
        self._session_factory = session_factory
        self._event_publisher = event_publisher
        self._logger = get_logger(__name__)

    async def create(
        self,
        payload: IncidentCreateRequest,
        idempotency_key: str | None,
    ) -> IncidentResponse:
        """Создаёт инцидент с учётом идемпотентности."""

        async with self._session_factory() as session:
            incident_repository = IncidentRepository(session)
            audit_repository = AuditLogRepository(session)
            event_repository = IncidentEventRepository(session)

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
            created_event = self._build_created_event(incident)
            event_record = self._create_event_record(
                incident=incident,
                event_type=IncidentEventType.INCIDENT_CREATED,
                kafka_topic=self._event_publisher.topic_for(IncidentEventType.INCIDENT_CREATED),
                payload=created_event.model_dump(mode="json"),
            )
            event_repository.add(event_record)
            await session.commit()
            await self._publish_event(
                session=session,
                event_record=event_record,
                event_message=created_event,
            )
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
            event_repository = IncidentEventRepository(session)
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
            analysis_requested_event = self._build_analysis_requested_event(incident)
            event_record = self._create_event_record(
                incident=incident,
                event_type=IncidentEventType.ANALYSIS_REQUESTED,
                kafka_topic=self._event_publisher.topic_for(IncidentEventType.ANALYSIS_REQUESTED),
                payload=analysis_requested_event.model_dump(mode="json"),
            )
            event_repository.add(event_record)
            await session.commit()
            await self._publish_event(
                session=session,
                event_record=event_record,
                event_message=analysis_requested_event,
            )
            await session.refresh(incident)
            return self._to_response(incident)

    async def _publish_event(
        self,
        *,
        session: AsyncSession,
        event_record: IncidentEvent,
        event_message: BaseModel,
    ) -> None:
        event_repository = IncidentEventRepository(session)
        try:
            await self._event_publisher.publish(
                topic=event_record.kafka_topic,
                key=event_record.event_key,
                message=event_message,
            )
        except PublisherUnavailableError as exc:
            self._logger.warning(
                "Kafka publisher недоступен, событие сохранено для повторной отправки",
                incident_id=str(event_record.incident_id),
                event_type=event_record.event_type.value,
                event_id=str(event_record.id),
                error=str(exc),
            )
            await event_repository.mark_failed(event_record, str(exc))
        except Exception as exc:
            self._logger.exception(
                "Не удалось опубликовать событие в Kafka",
                incident_id=str(event_record.incident_id),
                event_type=event_record.event_type.value,
                event_id=str(event_record.id),
            )
            await event_repository.mark_failed(event_record, str(exc))
        else:
            await event_repository.mark_published(event_record)
        finally:
            await session.commit()

    @staticmethod
    def _create_event_record(
        *,
        incident: Incident,
        event_type: IncidentEventType,
        kafka_topic: str,
        payload: dict[str, object],
    ) -> IncidentEvent:
        event_id = uuid4()
        return IncidentEvent(
            id=event_id,
            incident_id=incident.id,
            event_type=event_type,
            kafka_topic=kafka_topic,
            event_key=str(incident.id),
            status=EventProcessingStatus.PENDING,
            idempotency_key=str(event_id),
            payload=payload,
        )

    @staticmethod
    def _build_created_event(
        incident: Incident,
    ) -> IncidentEventMessage[IncidentCreatedPayload]:
        return IncidentEventMessage(
            metadata=EventMetadata(
                event_id=uuid4(),
                event_type=IncidentEventType.INCIDENT_CREATED,
                incident_id=incident.id,
                request_id=get_request_id(),
            ),
            payload=IncidentCreatedPayload(
                title=incident.title,
                description=incident.description,
                source=incident.source,
                status=incident.status,
                metadata=incident.payload_metadata,
            ),
        )

    @staticmethod
    def _build_analysis_requested_event(
        incident: Incident,
    ) -> IncidentEventMessage[IncidentAnalysisRequestedPayload]:
        return IncidentEventMessage(
            metadata=EventMetadata(
                event_id=uuid4(),
                event_type=IncidentEventType.ANALYSIS_REQUESTED,
                incident_id=incident.id,
                request_id=get_request_id(),
            ),
            payload=IncidentAnalysisRequestedPayload(status=incident.status),
        )

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
