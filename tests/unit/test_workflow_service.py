"""Unit-тесты LangGraph workflow-сервиса."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from ai_incident_copilot.api.schemas.incidents import IncidentCreateRequest
from ai_incident_copilot.application.services.incident_service import IncidentService
from ai_incident_copilot.application.workflows.service import IncidentWorkflowService
from ai_incident_copilot.core.config import Settings
from ai_incident_copilot.db.models import Incident, WorkflowRun, WorkflowStep
from ai_incident_copilot.events.kafka import NoOpEventPublisher


@pytest.mark.asyncio
async def test_workflow_service_persists_run_and_steps(unit_db_manager) -> None:
    publisher = NoOpEventPublisher(Settings(kafka_enabled=False))
    await publisher.start()
    incident_service = IncidentService(unit_db_manager.session_factory, publisher)
    created = await incident_service.create(
        IncidentCreateRequest(
            title="Security breach in prod",
            description="Unauthorized access detected by SIEM and multiple failed logins are present.",
            source="siem",
            metadata={"environment": "prod"},
        ),
        "workflow-key",
    )

    workflow_service = IncidentWorkflowService(unit_db_manager.session_factory)
    result = await workflow_service.run(incident_id=created.id)

    async with unit_db_manager.session_factory() as session:
        incident_status = await session.scalar(select(Incident.status).where(Incident.id == created.id))
        runs_total = await session.scalar(select(func.count()).select_from(WorkflowRun))
        steps_total = await session.scalar(select(func.count()).select_from(WorkflowStep))

    assert result.classification == "security"
    assert result.severity.value in {"high", "critical"}
    assert incident_status is not None
    assert incident_status.value == "analyzed"
    assert runs_total == 1
    assert steps_total == 3
