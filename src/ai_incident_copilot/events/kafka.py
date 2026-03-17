"""Kafka producer и общие интерфейсы публикации событий."""

from __future__ import annotations

from typing import Protocol

from aiokafka import AIOKafkaProducer
from pydantic import BaseModel

from ai_incident_copilot.core.config import Settings
from ai_incident_copilot.core.logging import get_logger
from ai_incident_copilot.domain.enums import IncidentEventType


class PublisherUnavailableError(RuntimeError):
    """Исключение при недоступности Kafka publisher."""


class EventPublisher(Protocol):
    """Контракт издателя событий."""

    async def start(self) -> None:
        """Инициализирует publisher."""

    async def stop(self) -> None:
        """Останавливает publisher."""

    async def publish(self, *, topic: str, key: str, message: BaseModel) -> None:
        """Публикует событие в Kafka."""

    async def health_status(self) -> str:
        """Возвращает состояние publisher для healthcheck."""

    def topic_for(self, event_type: IncidentEventType) -> str:
        """Возвращает Kafka topic для типа события."""


class KafkaEventPublisher:
    """Асинхронный publisher событий в Kafka."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._logger = get_logger(__name__)
        self._producer: AIOKafkaProducer | None = None
        self._start_error: str | None = None

    async def start(self) -> None:
        """Поднимает соединение с Kafka."""

        if self._producer is not None:
            return

        producer = AIOKafkaProducer(
            bootstrap_servers=self._settings.kafka_bootstrap_servers.split(","),
            client_id=self._settings.kafka_client_id,
            request_timeout_ms=self._settings.kafka_request_timeout_ms,
            key_serializer=lambda value: value.encode("utf-8"),
            value_serializer=lambda value: value.encode("utf-8"),
        )
        try:
            await producer.start()
        except Exception as exc:
            self._start_error = str(exc)
            self._logger.exception("Не удалось подключиться к Kafka producer")
            if self._settings.kafka_fail_fast:
                raise
            return

        self._producer = producer
        self._start_error = None
        self._logger.info("Kafka producer подключён")

    async def stop(self) -> None:
        """Корректно завершает работу producer."""

        if self._producer is not None:
            await self._producer.stop()
            self._logger.info("Kafka producer остановлен")
        self._producer = None

    async def publish(self, *, topic: str, key: str, message: BaseModel) -> None:
        """Публикует событие в Kafka."""

        if self._producer is None:
            raise PublisherUnavailableError(self._start_error or "Kafka producer не инициализирован")

        payload = message.model_dump_json()
        await self._producer.send_and_wait(topic, key=key, value=payload)
        self._logger.info(
            "Событие опубликовано в Kafka",
            topic=topic,
            event_key=key,
        )

    async def health_status(self) -> str:
        """Возвращает состояние producer."""

        if self._producer is not None and self._start_error is None:
            return "ok"
        if self._start_error:
            return "error"
        return "starting"

    def topic_for(self, event_type: IncidentEventType) -> str:
        """Возвращает topic по типу доменного события."""

        topics = {
            IncidentEventType.INCIDENT_CREATED: self._settings.kafka_topic_incident_created,
            IncidentEventType.ANALYSIS_REQUESTED: self._settings.kafka_topic_analysis_requested,
            IncidentEventType.ANALYSIS_COMPLETED: self._settings.kafka_topic_analysis_completed,
        }
        return topics[event_type]


class NoOpEventPublisher:
    """Заглушка publisher для локального режима и тестов без Kafka."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._logger = get_logger(__name__)

    async def start(self) -> None:
        """Логирует, что Kafka-издатель отключён."""

        self._logger.warning("Kafka publisher отключён настройкой kafka_enabled=false")

    async def stop(self) -> None:
        """Останавливает заглушку."""

    async def publish(self, *, topic: str, key: str, message: BaseModel) -> None:
        """Имитирует успешную публикацию события."""

        self._logger.info(
            "Событие пропущено NoOp publisher",
            topic=topic,
            event_key=key,
            payload=message.model_dump(mode="json"),
        )

    async def health_status(self) -> str:
        """Возвращает статус disabled для healthcheck."""

        return "disabled"

    def topic_for(self, event_type: IncidentEventType) -> str:
        """Возвращает topic по типу доменного события."""

        topics = {
            IncidentEventType.INCIDENT_CREATED: self._settings.kafka_topic_incident_created,
            IncidentEventType.ANALYSIS_REQUESTED: self._settings.kafka_topic_analysis_requested,
            IncidentEventType.ANALYSIS_COMPLETED: self._settings.kafka_topic_analysis_completed,
        }
        return topics[event_type]


def build_event_publisher(settings: Settings) -> EventPublisher:
    """Создаёт подходящий publisher в зависимости от конфигурации."""

    if settings.kafka_enabled:
        return KafkaEventPublisher(settings)
    return NoOpEventPublisher(settings)
