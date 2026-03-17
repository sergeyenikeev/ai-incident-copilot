"""Базовый Kafka consumer для worker-сервиса."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import cast

from aiokafka import AIOKafkaConsumer, ConsumerRecord

from ai_incident_copilot.core.config import Settings
from ai_incident_copilot.core.logging import get_logger


class KafkaEventConsumer:
    """Обёртка над AIOKafkaConsumer для фоновой обработки событий."""

    def __init__(self, settings: Settings, *topics: str) -> None:
        self._settings = settings
        self._topics = topics
        self._logger = get_logger(__name__)
        self._consumer = AIOKafkaConsumer(
            *topics,
            bootstrap_servers=settings.kafka_bootstrap_servers.split(","),
            group_id=settings.kafka_consumer_group,
            enable_auto_commit=False,
            auto_offset_reset="earliest",
        )

    async def start(self) -> None:
        """Подключается к Kafka."""

        await self._consumer.start()
        self._logger.info("Kafka consumer подключён", topics=list(self._topics))

    async def stop(self) -> None:
        """Останавливает consumer."""

        await self._consumer.stop()
        self._logger.info("Kafka consumer остановлен")

    async def messages(self) -> AsyncIterator[ConsumerRecord]:
        """Итерирует входящие сообщения."""

        async for message in self._consumer:
            yield message

    async def getmany(self, timeout_ms: int) -> dict[object, list[ConsumerRecord]]:
        """Возвращает пачку сообщений с таймаутом polling."""

        return cast(dict[object, list[ConsumerRecord]], await self._consumer.getmany(timeout_ms=timeout_ms))

    async def commit(self) -> None:
        """Подтверждает обработанные offset'ы."""

        await self._consumer.commit()
