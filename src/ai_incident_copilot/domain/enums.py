"""Перечисления доменной области."""

from __future__ import annotations

from enum import StrEnum


class IncidentStatus(StrEnum):
    """Состояния жизненного цикла инцидента."""

    RECEIVED = "received"
    ANALYSIS_REQUESTED = "analysis_requested"
    ANALYZING = "analyzing"
    ANALYZED = "analyzed"
    FAILED = "failed"


class SeverityLevel(StrEnum):
    """Уровень критичности инцидента."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class WorkflowRunStatus(StrEnum):
    """Статусы запуска workflow."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class WorkflowStepStatus(StrEnum):
    """Статусы отдельных шагов workflow."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class EventProcessingStatus(StrEnum):
    """Статусы обработки событий в event-driven контуре."""

    PENDING = "pending"
    PUBLISHED = "published"
    CONSUMED = "consumed"
    FAILED = "failed"


class IncidentEventType(StrEnum):
    """Типы доменных событий инцидента."""

    INCIDENT_CREATED = "incident.created"
    ANALYSIS_REQUESTED = "incident.analysis.requested"
    ANALYSIS_COMPLETED = "incident.analysis.completed"
