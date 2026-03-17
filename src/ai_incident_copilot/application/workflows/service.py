"""Сервис orchestration для LangGraph workflow анализа инцидента.

Это главный модуль интеллектуальной обработки. Он отвечает не только за
запуск графа, но и за полную трассировку выполнения в БД:

- создаёт `workflow_runs`
- сохраняет каждый шаг в `workflow_steps`
- обновляет итоговое состояние инцидента
- логирует ошибки и успешное завершение

Именно здесь rule-based или будущая LLM-логика превращается в управляемый,
наблюдаемый и повторяемый процесс.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from fastapi.encoders import jsonable_encoder
from langgraph.graph import END, START, StateGraph
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_incident_copilot.application.workflows.rule_based import RuleBasedIncidentAnalyzer
from ai_incident_copilot.application.workflows.state import (
    IncidentWorkflowResult,
    IncidentWorkflowState,
)
from ai_incident_copilot.core.logging import get_logger
from ai_incident_copilot.db.models import Incident, WorkflowRun, WorkflowStep
from ai_incident_copilot.db.repositories.incidents import IncidentRepository
from ai_incident_copilot.db.repositories.workflows import (
    WorkflowRunRepository,
    WorkflowStepRepository,
)
from ai_incident_copilot.domain.enums import IncidentStatus, WorkflowRunStatus, WorkflowStepStatus

type StateHandler = Callable[[IncidentWorkflowState], IncidentWorkflowState]


class IncidentWorkflowService:
    """Выполняет LangGraph workflow анализа и сохраняет шаги в БД.

    Сервис отделяет orchestration от конкретного алгоритма анализа.
    Сам анализатор можно заменить, не переписывая связку с БД и LangGraph.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        analyzer: RuleBasedIncidentAnalyzer | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._analyzer = analyzer or RuleBasedIncidentAnalyzer()
        self._logger = get_logger(__name__)

    async def run(
        self,
        *,
        incident_id: UUID,
        trigger_event_id: UUID | None = None,
    ) -> IncidentWorkflowResult:
        """Запускает workflow анализа для конкретного инцидента.

        Метод охватывает весь жизненный цикл одного workflow-run:

        1. загрузка инцидента
        2. создание записи `workflow_runs`
        3. перевод инцидента в `analyzing`
        4. выполнение LangGraph
        5. запись итогов обратно в `incidents`
        """

        async with self._session_factory() as session:
            incident_repository = IncidentRepository(session)
            workflow_run_repository = WorkflowRunRepository(session)
            workflow_step_repository = WorkflowStepRepository(session)

            incident = await incident_repository.get_by_id(incident_id)
            if incident is None:
                raise ValueError(f"Инцидент {incident_id} не найден")

            # `workflow_run` создаётся до фактического старта графа, чтобы у нас
            # сразу появился идентификатор запуска для логов, шагов и аудита.
            workflow_run = WorkflowRun(
                incident_id=incident.id,
                trigger_event_id=trigger_event_id,
                workflow_name="incident-analysis",
                status=WorkflowRunStatus.PENDING,
                input_payload=self._incident_payload(incident),
            )
            workflow_run_repository.add(workflow_run)
            await session.flush()

            # Статус `analyzing` позволяет API и операторам видеть, что работа
            # действительно началась, а не просто стоит в очереди.
            incident.status = IncidentStatus.ANALYZING
            await workflow_run_repository.mark_running(workflow_run)
            await session.commit()

            # Граф строится динамически, но на основе типизированного состояния
            # и стабильного набора узлов. Это облегчает будущую замену узлов.
            graph = self._build_graph(
                session=session,
                workflow_run=workflow_run,
                workflow_step_repository=workflow_step_repository,
            )
            initial_state: IncidentWorkflowState = {
                "incident_id": str(incident.id),
                "workflow_run_id": str(workflow_run.id),
                "title": incident.title,
                "description": incident.description,
                "source": incident.source,
                "metadata": incident.payload_metadata,
            }

            try:
                final_state = cast(IncidentWorkflowState, await graph.ainvoke(initial_state))
            except Exception as exc:
                # Ошибка на любом шаге должна быть отражена и в БД, и в логах;
                # иначе инцидент зависнет в промежуточном состоянии.
                incident.status = IncidentStatus.FAILED
                await workflow_run_repository.mark_failed(workflow_run, str(exc))
                await session.commit()
                self._logger.exception(
                    "Workflow анализа завершился ошибкой",
                    incident_id=str(incident.id),
                    workflow_run_id=str(workflow_run.id),
                )
                raise

            # Ниже выполняется "сведение" workflow-state обратно в доменную
            # модель инцидента, которую увидят API-клиенты и downstream-системы.
            incident.classification = final_state["classification"]
            incident.severity = final_state["severity"]
            incident.priority_score = final_state["priority_score"]
            incident.recommendation = final_state["recommendation"]
            incident.status = IncidentStatus.ANALYZED
            incident.last_analysis_at = datetime.now(tz=UTC)

            await workflow_run_repository.mark_completed(
                workflow_run,
                output_payload=jsonable_encoder(final_state),
            )
            await session.commit()

            self._logger.info(
                "Workflow анализа завершён",
                incident_id=str(incident.id),
                workflow_run_id=str(workflow_run.id),
                classification=incident.classification,
                severity=incident.severity.value if incident.severity else None,
            )
            return IncidentWorkflowResult(
                incident_id=incident.id,
                workflow_run_id=workflow_run.id,
                classification=final_state["classification"],
                severity=final_state["severity"],
                priority_score=final_state["priority_score"],
                recommendation=final_state["recommendation"],
            )

    def _build_graph(
        self,
        *,
        session: AsyncSession,
        workflow_run: WorkflowRun,
        workflow_step_repository: WorkflowStepRepository,
    ) -> Any:
        """Собирает LangGraph из типизированных node-функций.

        Каждый node оборачивается через `_run_step`, чтобы любой этап
        автоматически попадал в таблицу `workflow_steps`.
        """

        graph = StateGraph(IncidentWorkflowState)

        async def classify_node(state: IncidentWorkflowState) -> IncidentWorkflowState:
            return await self._run_step(
                session=session,
                workflow_run=workflow_run,
                workflow_step_repository=workflow_step_repository,
                node_name="classify_incident",
                state=state,
                handler=self._classify_incident,
            )

        async def severity_node(state: IncidentWorkflowState) -> IncidentWorkflowState:
            return await self._run_step(
                session=session,
                workflow_run=workflow_run,
                workflow_step_repository=workflow_step_repository,
                node_name="determine_severity",
                state=state,
                handler=self._determine_severity,
            )

        async def standard_recommendation_node(state: IncidentWorkflowState) -> IncidentWorkflowState:
            return await self._run_step(
                session=session,
                workflow_run=workflow_run,
                workflow_step_repository=workflow_step_repository,
                node_name="generate_standard_recommendation",
                state=state,
                handler=self._generate_standard_recommendation,
            )

        async def escalated_recommendation_node(state: IncidentWorkflowState) -> IncidentWorkflowState:
            return await self._run_step(
                session=session,
                workflow_run=workflow_run,
                workflow_step_repository=workflow_step_repository,
                node_name="generate_escalated_recommendation",
                state=state,
                handler=self._generate_escalated_recommendation,
            )

        graph.add_node("classify_incident", classify_node)
        graph.add_node("determine_severity", severity_node)
        graph.add_node("generate_standard_recommendation", standard_recommendation_node)
        graph.add_node("generate_escalated_recommendation", escalated_recommendation_node)

        # Последовательность узлов задаёт основной pipeline анализа:
        # классификация -> оценка тяжести -> выбор ветки рекомендации.
        graph.add_edge(START, "classify_incident")
        graph.add_edge("classify_incident", "determine_severity")
        graph.add_conditional_edges(
            "determine_severity",
            self._choose_recommendation_route,
            {
                "standard": "generate_standard_recommendation",
                "escalated": "generate_escalated_recommendation",
            },
        )
        graph.add_edge("generate_standard_recommendation", END)
        graph.add_edge("generate_escalated_recommendation", END)
        return graph.compile()

    async def _run_step(
        self,
        *,
        session: AsyncSession,
        workflow_run: WorkflowRun,
        workflow_step_repository: WorkflowStepRepository,
        node_name: str,
        state: IncidentWorkflowState,
        handler: StateHandler,
    ) -> IncidentWorkflowState:
        """Выполняет один шаг workflow и синхронизирует его с БД.

        Этот helper обеспечивает единый паттерн для всех узлов:

        - создать `workflow_steps` со статусом `pending`
        - перевести шаг в `running`
        - выполнить handler
        - сохранить `completed` или `failed`
        """

        step = WorkflowStep(
            workflow_run_id=workflow_run.id,
            node_name=node_name,
            status=WorkflowStepStatus.PENDING,
            input_payload=jsonable_encoder(state),
            output_payload={},
        )
        workflow_step_repository.add(step)
        await session.flush()
        await workflow_step_repository.mark_running(step)
        await session.commit()

        try:
            updates = handler(state)
        except Exception as exc:
            await workflow_step_repository.mark_failed(step, str(exc))
            await session.commit()
            self._logger.exception(
                "Ошибка шага workflow",
                workflow_run_id=str(workflow_run.id),
                node_name=node_name,
            )
            raise

        await workflow_step_repository.mark_completed(step, jsonable_encoder(updates))
        await session.commit()
        self._logger.info(
            "Шаг workflow выполнен",
            workflow_run_id=str(workflow_run.id),
            node_name=node_name,
        )
        return updates

    def _classify_incident(self, state: IncidentWorkflowState) -> IncidentWorkflowState:
        """Определяет категорию инцидента и дополняет workflow-state."""

        classification = self._analyzer.classify(
            title=state["title"],
            description=state["description"],
            metadata=state["metadata"],
        )
        return {
            **state,
            "classification": classification,
        }

    def _determine_severity(self, state: IncidentWorkflowState) -> IncidentWorkflowState:
        """Вычисляет severity, priority_score и ветку дальнейшей реакции."""

        assessment = self._analyzer.determine_severity(
            title=state["title"],
            description=state["description"],
            classification=state["classification"] or "application",
            metadata=state["metadata"],
        )
        route = self._analyzer.choose_route(
            classification=state["classification"] or "application",
            severity=assessment.severity,
        )
        return {
            **state,
            "severity": assessment.severity,
            "priority_score": assessment.priority_score,
            "route": route,
        }

    def _generate_standard_recommendation(
        self,
        state: IncidentWorkflowState,
    ) -> IncidentWorkflowState:
        """Генерирует рекомендацию для обычного маршрута обработки."""

        severity = state["severity"]
        assert severity is not None
        recommendation = self._analyzer.standard_recommendation(
            classification=state["classification"] or "application",
            severity=severity,
        )
        return {
            **state,
            "recommendation": recommendation,
        }

    def _generate_escalated_recommendation(
        self,
        state: IncidentWorkflowState,
    ) -> IncidentWorkflowState:
        """Генерирует усиленную рекомендацию для тяжёлых кейсов."""

        severity = state["severity"]
        assert severity is not None
        recommendation = self._analyzer.escalated_recommendation(
            classification=state["classification"] or "application",
            severity=severity,
        )
        return {
            **state,
            "recommendation": recommendation,
        }

    @staticmethod
    def _choose_recommendation_route(state: IncidentWorkflowState) -> str:
        """Возвращает имя ветки LangGraph после расчёта severity."""

        return state["route"] or "standard"

    @staticmethod
    def _incident_payload(incident: Incident) -> dict[str, object]:
        """Собирает снимок инцидента для входного payload workflow-run."""

        return {
            "id": str(incident.id),
            "title": incident.title,
            "description": incident.description,
            "source": incident.source,
            "status": incident.status.value,
            "metadata": incident.payload_metadata,
        }
