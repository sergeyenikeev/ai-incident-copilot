"""Типы состояния для workflow анализа инцидента.

Здесь описывается контракт между узлами LangGraph. Это отдельный модуль, чтобы
структура workflow-state была явно видна и не размазывалась по orchestration-коду.
"""

from __future__ import annotations

from typing import Any, TypedDict
from uuid import UUID

from pydantic import BaseModel

from ai_incident_copilot.domain.enums import SeverityLevel


class IncidentWorkflowState(TypedDict, total=False):
    """Состояние исполнения LangGraph workflow.

    `TypedDict` удобен тем, что state остаётся обычным словарём для LangGraph,
    но при этом IDE и type checker понимают ожидаемые поля.
    """

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
    """Результат выполнения workflow анализа.

    Это уже не промежуточное состояние графа, а нормализованный итог,
    который удобно возвращать worker-слою и использовать для публикации события
    `incident.analysis.completed`.
    """

    incident_id: UUID
    workflow_run_id: UUID
    classification: str
    severity: SeverityLevel
    priority_score: int
    recommendation: str
