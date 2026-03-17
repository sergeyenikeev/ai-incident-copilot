"""Worker обработки событий анализа инцидентов.

Модуль реализует фоновый контур, который связывает Kafka и workflow:

- читает `incident.analysis.requested`
- проверяет дубликаты
- запускает workflow анализа
- фиксирует retry и ошибки
- публикует `incident.analysis.completed`

Это ключевая точка event-driven обработки проекта.
"""

from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

from aiokafka import ConsumerRecord
from pydantic import TypeAdapter
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_incident_copilot.application.workflows.service import IncidentWorkflowService
from ai_incident_copilot.application.workflows.state import IncidentWorkflowResult
from ai_incident_copilot.core.config import Settings
from ai_incident_copilot.core.logging import bind_logging_context, clear_logging_context, get_logger
from ai_incident_copilot.db.models import IncidentEvent
from ai_incident_copilot.db.repositories.events import IncidentEventRepository
from ai_incident_copilot.domain.enums import (
    EventProcessingStatus,
    IncidentEventType,
    IncidentStatus,
)
from ai_incident_copilot.events.consumer import KafkaEventConsumer
from ai_incident_copilot.events.kafka import EventPublisher, PublisherUnavailableError
from ai_incident_copilot.events.schemas import (
    EventMetadata,
    IncidentAnalysisCompletedPayload,
    IncidentAnalysisRequestedPayload,
    IncidentEventMessage,
)

AnalysisRequestedEventAdapter = TypeAdapter(IncidentEventMessage[IncidentAnalysisRequestedPayload])


class IncidentAnalysisWorker:
    """Потребляет `incident.analysis.requested` и выполняет workflow анализа.

    Worker намеренно отделён от API, чтобы длительный анализ не блокировал
    клиентские HTTP-запросы и мог масштабироваться независимо.
    """

    def __init__(
        self,
        *,
        settings: Settings,
        session_factory: async_sessionmaker[AsyncSession],
        consumer: KafkaEventConsumer,
        event_publisher: EventPublisher,
        workflow_service: IncidentWorkflowService,
    ) -> None:
        self._settings = settings
        self._session_factory = session_factory
        self._consumer = consumer
        self._event_publisher = event_publisher
        self._workflow_service = workflow_service
        self._logger = get_logger(__name__)

    async def run(self, stop_event: asyncio.Event) -> None:
        """Запускает polling-loop worker-процесса.

        Offset подтверждается вручную, только после завершения локальной
        обработки записи. Это даёт нам больше контроля над retry-поведением.
        """

        while not stop_event.is_set():
            batches = await self._consumer.getmany(timeout_ms=self._settings.worker_poll_timeout_ms)
            for records in batches.values():
                for record in records:
                    await self._process_record(record)
                    # Даже если сообщение закончилось ошибкой после всех локальных
                    # retry, offset всё равно коммитится: иначе "ядовитое" сообщение
                    # заблокирует партицию навсегда. Детали ошибки уже лежат в БД.
                    await self._consumer.commit()

    async def _process_record(self, record: ConsumerRecord) -> None:
        """Обрабатывает одно Kafka-сообщение с запросом анализа.

        Метод собирает вокруг одного сообщения полный цикл:

        - валидация payload
        - привязка logging context
        - проверка идемпотентности
        - локальные retry workflow
        - финализация успешного результата
        """

        event = AnalysisRequestedEventAdapter.validate_json(record.value.decode("utf-8"))
        source_key = str(event.metadata.event_id)
        incident_id = event.metadata.incident_id

        # Контекст логирования очищается и заполняется заново на каждое сообщение,
        # чтобы логи разных инцидентов не смешивались между собой.
        clear_logging_context()
        bind_logging_context(incident_id=str(incident_id), event_id=source_key)

        if await self._is_duplicate(source_key):
            self._logger.info(
                "Повторное сообщение пропущено как уже обработанное",
                incident_id=str(incident_id),
                event_id=source_key,
            )
            clear_logging_context()
            return

        try:
            # Несколько локальных попыток полезны против кратковременных
            # ошибок БД/сети и не требуют немедленного повторного чтения из Kafka.
            for attempt in range(1, self._settings.kafka_max_retries + 1):
                try:
                    result = await self._workflow_service.run(
                        incident_id=incident_id,
                        trigger_event_id=await self._get_source_event_id(source_key),
                    )
                except Exception as exc:
                    await self._record_retry(source_key, str(exc))
                    if attempt == self._settings.kafka_max_retries:
                        self._logger.exception(
                            "Не удалось обработать событие анализа после всех попыток",
                            incident_id=str(incident_id),
                            event_id=source_key,
                            attempt=attempt,
                        )
                        return

                    self._logger.warning(
                        "Ошибка обработки события, будет выполнен повтор",
                        incident_id=str(incident_id),
                        event_id=source_key,
                        attempt=attempt,
                        error=str(exc),
                    )
                    await asyncio.sleep(self._settings.worker_retry_backoff_seconds * attempt)
                    continue

                await self._finalize_success(source_key, result)
                return
        finally:
            clear_logging_context()

    async def _is_duplicate(self, source_key: str) -> bool:
        """Проверяет, было ли исходное событие уже доведено до статуса consumed."""

        async with self._session_factory() as session:
            repository = IncidentEventRepository(session)
            source_event = await repository.get_by_idempotency_key(source_key)
            return source_event is not None and source_event.status == EventProcessingStatus.CONSUMED

    async def _get_source_event_id(self, source_key: str) -> UUID | None:
        """Возвращает первичный ключ исходного события для связи с workflow_run."""

        async with self._session_factory() as session:
            repository = IncidentEventRepository(session)
            source_event = await repository.get_by_idempotency_key(source_key)
            if source_event is None:
                return None
            return source_event.id

    async def _record_retry(self, source_key: str, error_message: str) -> None:
        """Фиксирует неуспешную попытку обработки в журнале событий БД."""

        async with self._session_factory() as session:
            repository = IncidentEventRepository(session)
            source_event = await repository.get_by_idempotency_key(source_key)
            if source_event is None:
                return
            await repository.mark_failed(source_event, error_message)
            await session.commit()

    async def _finalize_success(
        self,
        source_key: str,
        result: IncidentWorkflowResult,
    ) -> None:
        """Завершает успешную обработку сообщения.

        Здесь происходит два независимых, но связанных действия:

        - исходное `analysis.requested` отмечается как `consumed`
        - создаётся и публикуется новое событие `analysis.completed`
        """

        async with self._session_factory() as session:
            repository = IncidentEventRepository(session)
            source_event = await repository.get_by_idempotency_key(source_key)
            if source_event is not None:
                await repository.mark_consumed(source_event)

            # Новое доменное событие также сначала сохраняется в БД, и лишь потом
            # уходит в Kafka. Это тот же outbox-подобный принцип, что и в API.
            completed_event = self._build_completed_event(result)
            event_record = self._create_completed_event_record(completed_event)
            repository.add(event_record)
            await session.commit()

            try:
                await self._event_publisher.publish(
                    topic=event_record.kafka_topic,
                    key=event_record.event_key,
                    message=completed_event,
                )
            except PublisherUnavailableError as exc:
                self._logger.warning(
                    "Kafka publisher недоступен для события завершения анализа",
                    incident_id=str(result.incident_id),
                    workflow_run_id=str(result.workflow_run_id),
                    event_id=str(completed_event.metadata.event_id),
                    error=str(exc),
                )
                await repository.mark_failed(event_record, str(exc))
            except Exception as exc:
                self._logger.exception(
                    "Не удалось опубликовать событие завершения анализа",
                    incident_id=str(result.incident_id),
                    workflow_run_id=str(result.workflow_run_id),
                    event_id=str(completed_event.metadata.event_id),
                )
                await repository.mark_failed(event_record, str(exc))
            else:
                await repository.mark_published(event_record)

            await session.commit()

    def _build_completed_event(
        self,
        result: IncidentWorkflowResult,
    ) -> IncidentEventMessage[IncidentAnalysisCompletedPayload]:
        """Собирает доменное сообщение об успешно завершённом анализе."""

        return IncidentEventMessage(
            metadata=EventMetadata(
                event_id=uuid4(),
                event_type=IncidentEventType.ANALYSIS_COMPLETED,
                incident_id=result.incident_id,
                workflow_run_id=result.workflow_run_id,
            ),
            payload=IncidentAnalysisCompletedPayload(
                status=IncidentStatus.ANALYZED,
                classification=result.classification,
                severity=result.severity,
                recommendation=result.recommendation,
            ),
        )

    def _create_completed_event_record(
        self,
        event: IncidentEventMessage[IncidentAnalysisCompletedPayload],
    ) -> IncidentEvent:
        """Создаёт ORM-запись для `incident.analysis.completed`."""

        return IncidentEvent(
            id=event.metadata.event_id,
            incident_id=event.metadata.incident_id,
            event_type=IncidentEventType.ANALYSIS_COMPLETED,
            kafka_topic=self._event_publisher.topic_for(IncidentEventType.ANALYSIS_COMPLETED),
            event_key=str(event.metadata.incident_id),
            status=EventProcessingStatus.PENDING,
            idempotency_key=str(event.metadata.event_id),
            payload=event.model_dump(mode="json"),
        )
