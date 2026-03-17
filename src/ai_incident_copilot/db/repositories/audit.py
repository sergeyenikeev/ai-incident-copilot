"""Репозиторий audit-логов."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from ai_incident_copilot.db.models import AuditLog


class AuditLogRepository:
    """Работает с таблицей audit_logs."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def create(
        self,
        *,
        entity_type: str,
        entity_id: UUID,
        action: str,
        actor: str,
        payload: dict[str, Any],
        incident_id: UUID | None = None,
        request_id: str | None = None,
    ) -> AuditLog:
        """Создаёт запись аудита и добавляет её в текущую транзакцию."""

        log_entry = AuditLog(
            incident_id=incident_id,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            actor=actor,
            request_id=request_id,
            payload=payload,
        )
        self._session.add(log_entry)
        return log_entry
