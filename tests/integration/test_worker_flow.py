"""Интеграционный тест worker-потока на mock Kafka payload.

Тест покрывает самый важный асинхронный сценарий проекта без реального Kafka:

- API создаёт инцидент
- API ставит инцидент в анализ
- из таблицы `incident_events` берётся payload исходного события
- worker обрабатывает его напрямую
- в БД появляются workflow-артефакты и итоговое событие завершения анализа
"""

from __future__ import annotations

import asyncio
import sqlite3
from types import SimpleNamespace

from ai_incident_copilot.application.workflows.service import IncidentWorkflowService
from ai_incident_copilot.core.config import Settings
from ai_incident_copilot.db.session import DatabaseManager
from ai_incident_copilot.events.kafka import build_event_publisher
from ai_incident_copilot.workers.incident_analysis_worker import IncidentAnalysisWorker


class DummyConsumer:
    """Минимальная заглушка consumer для прямого вызова worker.

    В этом тесте consumer как объект worker'у не нужен, потому что мы вызываем
    `_process_record` напрямую и не запускаем полноценный polling-loop.
    """


def test_worker_processes_analysis_requested_event(
    client,
    migrated_settings: Settings,
    sqlite_urls: dict[str, str],
) -> None:
    """Проверяет сквозной worker-flow от события запроса анализа до результата."""

    created = client.post(
        "/api/v1/incidents",
        json={
            "title": "Массовые ошибки входа",
            "description": "SIEM фиксирует множественные неуспешные логины и нестандартный access pattern в prod.",
            "source": "siem",
            "metadata": {"environment": "prod"},
        },
    )
    incident_id = created.json()["data"]["id"]
    analyze = client.post(f"/api/v1/incidents/{incident_id}/analyze")

    assert analyze.status_code == 200

    # Забираем из БД фактический payload события, который API сгенерировал для
    # Kafka. Это даёт более реалистичный интеграционный сценарий, чем ручная
    # сборка event JSON внутри теста.
    connection = sqlite3.connect(sqlite_urls["path"])
    cursor = connection.cursor()
    cursor.execute(
        "select payload from incident_events "
        "where event_type = 'incident.analysis.requested' "
        "order by created_at desc limit 1"
    )
    payload = cursor.fetchone()[0]
    connection.close()

    async def run_once() -> None:
        """Локально поднимает зависимости worker и обрабатывает одно сообщение."""

        db_manager = DatabaseManager(migrated_settings.database_url_async)
        publisher = build_event_publisher(migrated_settings)
        await publisher.start()
        worker = IncidentAnalysisWorker(
            settings=migrated_settings,
            session_factory=db_manager.session_factory,
            consumer=DummyConsumer(),  # type: ignore[arg-type]
            event_publisher=publisher,
            workflow_service=IncidentWorkflowService(db_manager.session_factory),
        )
        await worker._process_record(SimpleNamespace(value=payload.encode("utf-8")))
        await publisher.stop()
        await db_manager.dispose()

    asyncio.run(run_once())

    # Проверяем не только состояние инцидента, но и то, что появились записи
    # о запуске workflow, шагах и completed-событии.
    connection = sqlite3.connect(sqlite_urls["path"])
    cursor = connection.cursor()
    cursor.execute("select status, classification, severity from incidents order by created_at desc limit 1")
    incident_row = cursor.fetchone()
    cursor.execute("select count(*) from workflow_runs")
    runs_total = cursor.fetchone()[0]
    cursor.execute("select count(*) from workflow_steps")
    steps_total = cursor.fetchone()[0]
    cursor.execute(
        "select status from incident_events "
        "where event_type = 'incident.analysis.requested' "
        "order by created_at desc limit 1"
    )
    source_status = cursor.fetchone()[0]
    cursor.execute("select count(*) from incident_events where event_type = 'incident.analysis.completed'")
    completed_total = cursor.fetchone()[0]
    connection.close()

    assert incident_row == ("analyzed", "security", "high")
    assert runs_total == 1
    assert steps_total == 3
    assert source_status == "consumed"
    assert completed_total == 1
