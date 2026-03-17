"""Unit-тесты прикладного сервиса инцидентов."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from ai_incident_copilot.api.schemas.incidents import IncidentCreateRequest
from ai_incident_copilot.application.services.incident_service import IncidentService
from ai_incident_copilot.core.config import Settings
from ai_incident_copilot.db.models import Incident, IncidentEvent
from ai_incident_copilot.events.kafka import NoOpEventPublisher


@pytest.mark.asyncio
async def test_create_incident_is_idempotent(unit_db_manager) -> None:
    publisher = NoOpEventPublisher(Settings(kafka_enabled=False))
    await publisher.start()
    service = IncidentService(unit_db_manager.session_factory, publisher)
    payload = IncidentCreateRequest(
        title="Ошибка очереди",
        description="Сообщения перестали вычитываться из Kafka и растёт backlog.",
        source="monitoring",
        metadata={"team": "platform"},
    )

    first = await service.create(payload, "same-key")
    second = await service.create(payload, "same-key")

    async with unit_db_manager.session_factory() as session:
        incidents_total = await session.scalar(select(func.count()).select_from(Incident))
        events_total = await session.scalar(select(func.count()).select_from(IncidentEvent))

    assert first.id == second.id
    assert incidents_total == 1
    assert events_total == 1


@pytest.mark.asyncio
async def test_request_analysis_creates_second_event(unit_db_manager) -> None:
    publisher = NoOpEventPublisher(Settings(kafka_enabled=False))
    await publisher.start()
    service = IncidentService(unit_db_manager.session_factory, publisher)
    payload = IncidentCreateRequest(
        title="Недоступен ingress",
        description="Пользователи получают 502 и ingress-controller отстаёт по health probes.",
        source="monitoring",
        metadata={},
    )

    created = await service.create(payload, "analysis-key")
    analyzed = await service.request_analysis(created.id)

    async with unit_db_manager.session_factory() as session:
        events_total = await session.scalar(select(func.count()).select_from(IncidentEvent))

    assert analyzed is not None
    assert analyzed.status.value == "analysis_requested"
    assert events_total == 2
