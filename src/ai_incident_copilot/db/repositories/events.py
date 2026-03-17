"""Репозиторий событий инцидентов."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_incident_copilot.db.models import IncidentEvent
from ai_incident_copilot.domain.enums import EventProcessingStatus


class IncidentEventRepository:
    """Работает с таблицей incident_events."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, event: IncidentEvent) -> IncidentEvent:
        """Добавляет событие в текущую транзакцию."""

        self._session.add(event)
        return event

    async def get_by_idempotency_key(self, idempotency_key: str) -> IncidentEvent | None:
        """Возвращает событие по ключу идемпотентности."""

        stmt = select(IncidentEvent).where(IncidentEvent.idempotency_key == idempotency_key)
        return cast(IncidentEvent | None, await self._session.scalar(stmt))

    async def mark_consumed(self, event: IncidentEvent) -> IncidentEvent:
        """Помечает событие как обработанное."""

        event.status = EventProcessingStatus.CONSUMED
        event.processed_at = datetime.now(tz=UTC)
        event.last_error = None
        await self._session.flush()
        return event

    async def mark_failed(self, event: IncidentEvent, error_message: str) -> IncidentEvent:
        """Помечает событие как завершившееся ошибкой."""

        event.status = EventProcessingStatus.FAILED
        event.last_error = error_message
        event.retry_count += 1
        await self._session.flush()
        return event
