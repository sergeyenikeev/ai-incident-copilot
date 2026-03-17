"""Репозитории workflow-сущностей.

Модуль разделяет две близкие, но разные сущности:

- `WorkflowRun`: один запуск анализа целиком
- `WorkflowStep`: отдельный шаг внутри запуска
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_incident_copilot.db.models import WorkflowRun, WorkflowStep
from ai_incident_copilot.domain.enums import WorkflowRunStatus, WorkflowStepStatus


class WorkflowRunRepository:
    """Работает с workflow_runs.

    Репозиторий описывает жизненный цикл запуска workflow на уровне всего run,
    без детализации по node execution.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, workflow_run: WorkflowRun) -> WorkflowRun:
        """Добавляет запуск workflow в транзакцию."""

        self._session.add(workflow_run)
        return workflow_run

    async def get_by_id(self, workflow_run_id: UUID) -> WorkflowRun | None:
        """Возвращает запуск workflow по идентификатору."""

        stmt = select(WorkflowRun).where(WorkflowRun.id == workflow_run_id)
        return cast(WorkflowRun | None, await self._session.scalar(stmt))

    async def mark_running(self, workflow_run: WorkflowRun) -> WorkflowRun:
        """Помечает запуск как выполняющийся."""

        workflow_run.status = WorkflowRunStatus.RUNNING
        workflow_run.started_at = datetime.now(tz=UTC)
        await self._session.flush()
        return workflow_run

    async def mark_completed(
        self,
        workflow_run: WorkflowRun,
        output_payload: dict[str, Any],
    ) -> WorkflowRun:
        """Помечает запуск как завершённый."""

        workflow_run.status = WorkflowRunStatus.COMPLETED
        workflow_run.output_payload = output_payload
        workflow_run.finished_at = datetime.now(tz=UTC)
        workflow_run.error_message = None
        await self._session.flush()
        return workflow_run

    async def mark_failed(self, workflow_run: WorkflowRun, error_message: str) -> WorkflowRun:
        """Помечает запуск как завершившийся ошибкой."""

        workflow_run.status = WorkflowRunStatus.FAILED
        workflow_run.error_message = error_message
        workflow_run.finished_at = datetime.now(tz=UTC)
        await self._session.flush()
        return workflow_run


class WorkflowStepRepository:
    """Работает с workflow_steps.

    Нужен для поузловой трассировки выполнения LangGraph и последующего
    расследования инцидентов на уровне конкретного шага.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, workflow_step: WorkflowStep) -> WorkflowStep:
        """Добавляет шаг в транзакцию."""

        self._session.add(workflow_step)
        return workflow_step

    async def mark_running(self, workflow_step: WorkflowStep) -> WorkflowStep:
        """Помечает шаг как выполняющийся."""

        workflow_step.status = WorkflowStepStatus.RUNNING
        workflow_step.started_at = datetime.now(tz=UTC)
        await self._session.flush()
        return workflow_step

    async def mark_completed(
        self,
        workflow_step: WorkflowStep,
        output_payload: dict[str, Any],
    ) -> WorkflowStep:
        """Помечает шаг как выполненный."""

        workflow_step.status = WorkflowStepStatus.COMPLETED
        workflow_step.output_payload = output_payload
        workflow_step.finished_at = datetime.now(tz=UTC)
        workflow_step.error_message = None
        await self._session.flush()
        return workflow_step

    async def mark_failed(self, workflow_step: WorkflowStep, error_message: str) -> WorkflowStep:
        """Помечает шаг как ошибочный."""

        workflow_step.status = WorkflowStepStatus.FAILED
        workflow_step.error_message = error_message
        workflow_step.finished_at = datetime.now(tz=UTC)
        await self._session.flush()
        return workflow_step
