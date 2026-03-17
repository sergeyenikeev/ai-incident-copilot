"""Точка входа worker-сервиса."""

from __future__ import annotations

import asyncio
import signal

from ai_incident_copilot.application.workflows.service import IncidentWorkflowService
from ai_incident_copilot.core.config import get_settings
from ai_incident_copilot.core.logging import configure_logging, get_logger
from ai_incident_copilot.db.session import DatabaseManager
from ai_incident_copilot.events.consumer import KafkaEventConsumer
from ai_incident_copilot.events.kafka import build_event_publisher
from ai_incident_copilot.workers.incident_analysis_worker import IncidentAnalysisWorker


async def run_worker() -> None:
    """Запускает цикл обработки Kafka-сообщений."""

    settings = get_settings()
    configure_logging(settings.app_log_level)
    logger = get_logger(__name__)
    stop_event = asyncio.Event()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            logger.warning("Обработчик сигналов недоступен в текущем окружении", signal=sig.name)

    database_manager = DatabaseManager(settings.database_url_async)
    event_publisher = build_event_publisher(settings)
    consumer = KafkaEventConsumer(settings, settings.kafka_topic_analysis_requested)
    workflow_service = IncidentWorkflowService(database_manager.session_factory)
    worker = IncidentAnalysisWorker(
        settings=settings,
        session_factory=database_manager.session_factory,
        consumer=consumer,
        event_publisher=event_publisher,
        workflow_service=workflow_service,
    )

    await event_publisher.start()
    await consumer.start()
    logger.info("Worker-сервис запущен")
    try:
        await worker.run(stop_event)
    finally:
        await consumer.stop()
        await event_publisher.stop()
        await database_manager.dispose()
        logger.info("Worker-сервис остановлен")


def main() -> None:
    """Синхронная обёртка для запуска worker-процесса."""

    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
