"""Типы состояния для workflow анализа инцидента."""

from __future__ import annotations

from typing import Any, TypedDict
from uuid import UUID

from pydantic import BaseModel

from ai_incident_copilot.domain.enums import SeverityLevel


class IncidentWorkflowState(TypedDict, total=False):
    """Состояние исполнения LangGraph workflow."""

    incident_id: str
    workflow_run_id: str
    title: str
    description: str
    source: str | None
    metadata: dict[str, Any]
    classification: str | None
    severity: SeverityLevel | None
    priority_score: int | None
    recommendation: str | None
    route: str | None


class IncidentWorkflowResult(BaseModel):
    """Результат выполнения workflow анализа."""

    incident_id: UUID
    workflow_run_id: UUID
    classification: str
    severity: SeverityLevel
    priority_score: int
    recommendation: str
