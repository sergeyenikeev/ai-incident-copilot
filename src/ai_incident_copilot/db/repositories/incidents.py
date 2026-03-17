"""Репозиторий инцидентов."""

from __future__ import annotations

from collections.abc import Sequence
from typing import cast
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_incident_copilot.api.schemas.incidents import IncidentFilterParams, PaginationParams
from ai_incident_copilot.db.models import Incident


class IncidentRepository:
    """Работает с таблицей incidents."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, incident: Incident) -> Incident:
        """Добавляет инцидент в текущую транзакцию."""

        self._session.add(incident)
        return incident

    async def get_by_id(self, incident_id: UUID) -> Incident | None:
        """Возвращает инцидент по первичному ключу."""

        return await self._session.get(Incident, incident_id)

    async def get_by_idempotency_key(self, idempotency_key: str) -> Incident | None:
        """Возвращает инцидент по ключу идемпотентности."""

        stmt = select(Incident).where(Incident.idempotency_key == idempotency_key)
        return cast(Incident | None, await self._session.scalar(stmt))

    async def list_paginated(
        self,
        pagination: PaginationParams,
        filters: IncidentFilterParams,
    ) -> tuple[Sequence[Incident], int]:
        """Возвращает страницу инцидентов и их общее количество."""

        base_stmt = self._apply_filters(select(Incident), filters)
        count_stmt = select(func.count()).select_from(base_stmt.subquery())
        total = cast(int, await self._session.scalar(count_stmt) or 0)

        stmt = (
            base_stmt.order_by(Incident.created_at.desc())
            .offset((pagination.page - 1) * pagination.page_size)
            .limit(pagination.page_size)
        )
        result = await self._session.scalars(stmt)
        return result.all(), total

    @staticmethod
    def _apply_filters(
        stmt: Select[tuple[Incident]],
        filters: IncidentFilterParams,
    ) -> Select[tuple[Incident]]:
        if filters.status:
            stmt = stmt.where(Incident.status == filters.status)
        if filters.classification:
            stmt = stmt.where(Incident.classification == filters.classification)
        if filters.severity:
            stmt = stmt.where(Incident.severity == filters.severity)
        if filters.source:
            stmt = stmt.where(Incident.source == filters.source)
        return stmt
