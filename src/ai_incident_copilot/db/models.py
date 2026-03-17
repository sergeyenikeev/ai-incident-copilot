"""ORM-модели базы данных.

Этот модуль описывает постоянное состояние системы. Если упростить проект до
самого ядра, то именно эти таблицы отвечают за ответ на вопросы:

- какие инциденты пришли в систему
- какие workflow запускались
- какие шаги выполнились
- какие события были опубликованы или упали
- какие действия вошли в аудит
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Integer, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ai_incident_copilot.db.base import Base, TimestampMixin
from ai_incident_copilot.domain.enums import (
    EventProcessingStatus,
    IncidentEventType,
    IncidentStatus,
    SeverityLevel,
    WorkflowRunStatus,
    WorkflowStepStatus,
)

type SupportedEnum = (
    type[EventProcessingStatus]
    | type[IncidentEventType]
    | type[IncidentStatus]
    | type[SeverityLevel]
    | type[WorkflowRunStatus]
    | type[WorkflowStepStatus]
)


def enum_column(
    enum_type: SupportedEnum,
    *,
    nullable: bool = False,
    default: Any | None = None,
) -> Mapped[Any]:
    """Создаёт SQLAlchemy-колонку для enum с кросс-БД совместимостью.

    `native_enum=False` выбран осознанно: схема должна одинаково работать
    и на PostgreSQL в runtime, и на SQLite в тестах.
    """

    return mapped_column(
        Enum(
            enum_type,
            native_enum=False,
            values_callable=lambda enum_cls: [item.value for item in enum_cls],
        ),
        nullable=nullable,
        default=default,
    )


class Incident(TimestampMixin, Base):
    """Инцидент, поступивший в систему.

    Это главная бизнес-сущность проекта. Здесь хранится и исходное описание,
    и итог анализа, который будет произведён worker + workflow.
    """

    __tablename__ = "incidents"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    status: Mapped[IncidentStatus] = enum_column(IncidentStatus, default=IncidentStatus.RECEIVED)
    classification: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    severity: Mapped[SeverityLevel | None] = enum_column(SeverityLevel, nullable=True)
    priority_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    recommendation: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_analysis_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        unique=True,
        index=True,
    )
    payload_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSON,
        nullable=False,
        default=dict,
    )

    workflow_runs: Mapped[list[WorkflowRun]] = relationship(back_populates="incident")
    incident_events: Mapped[list[IncidentEvent]] = relationship(back_populates="incident")
    audit_logs: Mapped[list[AuditLog]] = relationship(back_populates="incident")


class WorkflowRun(TimestampMixin, Base):
    """Запуск анализа по инциденту.

    Один инцидент может анализироваться несколько раз, поэтому runtime анализа
    вынесен в отдельную сущность, а не хранится прямо в таблице incidents.
    """

    __tablename__ = "workflow_runs"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    incident_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("incidents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    trigger_event_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("incident_events.id", ondelete="SET NULL"),
        nullable=True,
    )
    workflow_name: Mapped[str] = mapped_column(String(128), nullable=False, default="incident-analysis")
    status: Mapped[WorkflowRunStatus] = enum_column(WorkflowRunStatus, default=WorkflowRunStatus.PENDING)
    input_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    output_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    incident: Mapped[Incident] = relationship(back_populates="workflow_runs")
    steps: Mapped[list[WorkflowStep]] = relationship(back_populates="workflow_run")
    trigger_event: Mapped[IncidentEvent | None] = relationship(
        back_populates="triggered_workflow_runs",
        foreign_keys=[trigger_event_id],
    )


class WorkflowStep(Base):
    """Детальный шаг внутри запуска workflow.

    Таблица нужна для наблюдаемости: она показывает, какой именно node
    выполнялся, с каким входом, каким выходом и на каком этапе произошла ошибка.
    """

    __tablename__ = "workflow_steps"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workflow_run_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("workflow_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    node_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    status: Mapped[WorkflowStepStatus] = enum_column(WorkflowStepStatus, default=WorkflowStepStatus.PENDING)
    input_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    output_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    workflow_run: Mapped[WorkflowRun] = relationship(back_populates="steps")


class IncidentEvent(TimestampMixin, Base):
    """Событие инцидента, прошедшее через Kafka.

    По сути это журнал событий и внутренний outbox проекта. Здесь хранятся:

    - payload доменного события
    - Kafka topic/key
    - статус обработки
    - retry_count и last_error

    Поле `idempotency_key` используется для защиты от повторной обработки.
    """

    __tablename__ = "incident_events"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    incident_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("incidents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[IncidentEventType] = enum_column(IncidentEventType)
    kafka_topic: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    event_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    status: Mapped[EventProcessingStatus] = enum_column(
        EventProcessingStatus,
        default=EventProcessingStatus.PENDING,
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    incident: Mapped[Incident] = relationship(back_populates="incident_events")
    triggered_workflow_runs: Mapped[list[WorkflowRun]] = relationship(back_populates="trigger_event")


class AuditLog(Base):
    """Запись аудита по важным действиям в системе.

    Audit log отделён от `incident_events`: события нужны для интеграции
    между сервисами, а аудит нужен для операторов, расследований и трассировки
    действий внутри самого приложения.
    """

    __tablename__ = "audit_logs"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    incident_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("incidents.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    entity_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    actor: Mapped[str] = mapped_column(String(128), nullable=False, default="system")
    request_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    incident: Mapped[Incident | None] = relationship(back_populates="audit_logs")
