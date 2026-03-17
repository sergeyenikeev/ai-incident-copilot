"""Unit-тесты Kafka-компонентов без реальной Kafka."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from ai_incident_copilot.core.config import Settings
from ai_incident_copilot.domain.enums import IncidentEventType, IncidentStatus
from ai_incident_copilot.events.consumer import KafkaEventConsumer
from ai_incident_copilot.events.kafka import KafkaEventPublisher, NoOpEventPublisher
from ai_incident_copilot.events.schemas import (
    EventMetadata,
    IncidentCreatedPayload,
    IncidentEventMessage,
)


class FakeProducer:
    """Подмена aiokafka producer для unit-тестов."""

    def __init__(self, **_: object) -> None:
        self.started = False
        self.stopped = False
        self.sent: list[tuple[str, str, str]] = []

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True

    async def send_and_wait(self, topic: str, *, key: str, value: str) -> None:
        self.sent.append((topic, key, value))


class FakeConsumer:
    """Подмена aiokafka consumer для unit-тестов."""

    def __init__(self, *_: object, **__: object) -> None:
        self.started = False
        self.stopped = False
        self.committed = False
        self._yielded = False

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True

    async def commit(self) -> None:
        self.committed = True

    async def getmany(self, *, timeout_ms: int) -> dict[object, list[SimpleNamespace]]:
        return {"tp": [SimpleNamespace(value=b"payload", timeout_ms=timeout_ms)]}

    def __aiter__(self) -> FakeConsumer:
        return self

    async def __anext__(self) -> SimpleNamespace:
        if self._yielded:
            raise StopAsyncIteration
        self._yielded = True
        return SimpleNamespace(value=b"payload")


@pytest.mark.asyncio
async def test_kafka_event_publisher_start_publish_stop(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("ai_incident_copilot.events.kafka.AIOKafkaProducer", FakeProducer)
    settings = Settings(kafka_enabled=True)
    publisher = KafkaEventPublisher(settings)

    await publisher.start()
    message = IncidentEventMessage(
        metadata=EventMetadata(
            event_id=uuid4(),
            event_type=IncidentEventType.INCIDENT_CREATED,
            incident_id=uuid4(),
        ),
        payload=IncidentCreatedPayload(
            title="API down",
            description="502 from gateway",
            source="monitoring",
            status=IncidentStatus.RECEIVED,
            metadata={},
        ),
    )
    await publisher.publish(
        topic=publisher.topic_for(IncidentEventType.INCIDENT_CREATED),
        key="incident-1",
        message=message,
    )
    health = await publisher.health_status()
    await publisher.stop()

    assert health == "ok"
    assert publisher.topic_for(IncidentEventType.ANALYSIS_COMPLETED) == "incident.analysis.completed"


@pytest.mark.asyncio
async def test_noop_publisher_reports_disabled() -> None:
    publisher = NoOpEventPublisher(Settings(kafka_enabled=False))

    await publisher.start()
    status = await publisher.health_status()

    assert status == "disabled"


@pytest.mark.asyncio
async def test_kafka_event_consumer_wrapper(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("ai_incident_copilot.events.consumer.AIOKafkaConsumer", FakeConsumer)
    consumer = KafkaEventConsumer(Settings(kafka_enabled=False), "incident.analysis.requested")

    await consumer.start()
    batches = await consumer.getmany(timeout_ms=500)
    await consumer.commit()
    messages = [message async for message in consumer.messages()]
    await consumer.stop()

    assert len(batches["tp"]) == 1
    assert len(messages) == 1
