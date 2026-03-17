"""Типизированные схемы событий Kafka."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from ai_incident_copilot.domain.enums import IncidentEventType, IncidentStatus, SeverityLevel


class EventMetadata(BaseModel):
    """Метаданные Kafka-сообщения."""

    event_id: UUID
    event_type: IncidentEventType
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
    incident_id: UUID
    request_id: str | None = None
    workflow_run_id: UUID | None = None
    retry_count: int = 0


class IncidentCreatedPayload(BaseModel):
    """Полезная нагрузка события о создании инцидента."""

    title: str
    description: str
    source: str | None
    status: IncidentStatus
    metadata: dict[str, Any]


class IncidentAnalysisRequestedPayload(BaseModel):
    """Полезная нагрузка запроса на анализ."""

    status: IncidentStatus


class IncidentAnalysisCompletedPayload(BaseModel):
    """Полезная нагрузка завершённого анализа."""

    status: IncidentStatus
    classification: str | None = None
    severity: SeverityLevel | None = None
    recommendation: str | None = None


class IncidentEventMessage[PayloadT](BaseModel):
    """Типизированное доменное событие инцидента."""

    metadata: EventMetadata
    payload: PayloadT
