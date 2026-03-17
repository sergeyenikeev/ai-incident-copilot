"""Точка входа worker-сервиса.

Модуль выполняет bootstrap фонового процесса:

- читает конфигурацию
- настраивает логирование
- создаёт Kafka consumer и publisher
- собирает workflow service и worker orchestration
- поддерживает readiness-файл для Kubernetes probes

В отличие от `workers.incident_analysis_worker`, здесь почти нет бизнес-логики:
это слой запуска и корректного завершения процесса.
"""

from __future__ import annotations

import asyncio
import signal
from pathlib import Path

from ai_incident_copilot.application.workflows.service import IncidentWorkflowService
from ai_incident_copilot.core.config import get_settings
from ai_incident_copilot.core.logging import configure_logging, get_logger
from ai_incident_copilot.db.session import DatabaseManager
from ai_incident_copilot.events.consumer import KafkaEventConsumer
from ai_incident_copilot.events.kafka import build_event_publisher
from ai_incident_copilot.workers.incident_analysis_worker import IncidentAnalysisWorker


async def run_worker() -> None:
    """Запускает цикл обработки Kafka-сообщений.

    Функция отвечает за полный жизненный цикл worker-процесса, включая
    регистрацию signal handler'ов и освобождение ресурсов при shutdown.
    """

    settings = get_settings()
    configure_logging(settings.app_log_level)
    logger = get_logger(__name__)
    stop_event = asyncio.Event()
    ready_file = Path(settings.worker_ready_file)

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
    # Readiness-файл используется probes'ами в Kubernetes. Он появляется только
    # после успешного старта зависимостей и удаляется при остановке процесса.
    await asyncio.to_thread(ready_file.parent.mkdir, parents=True, exist_ok=True)
    await asyncio.to_thread(ready_file.write_text, "ready", encoding="utf-8")
    logger.info("Worker-сервис запущен")
    try:
        await worker.run(stop_event)
    finally:
        if await asyncio.to_thread(ready_file.exists):
            await asyncio.to_thread(ready_file.unlink)
        await consumer.stop()
        await event_publisher.stop()
        await database_manager.dispose()
        logger.info("Worker-сервис остановлен")


def main() -> None:
    """Синхронная обёртка для запуска worker-процесса."""

    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
