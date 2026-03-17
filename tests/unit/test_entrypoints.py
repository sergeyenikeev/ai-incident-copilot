"""Unit-тесты entrypoint-модулей API и worker."""

from __future__ import annotations

import signal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from ai_incident_copilot import main as api_main_module
from ai_incident_copilot import worker_main
from ai_incident_copilot.core.config import Settings
from ai_incident_copilot.main import main as api_main


def test_api_main_starts_uvicorn_with_runtime_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """API entrypoint должен передавать настройки в Uvicorn."""

    settings = Settings(app_host="127.0.0.1", app_port=9090, app_debug=True)
    uvicorn_run = Mock()

    monkeypatch.setattr(api_main_module, "get_settings", lambda: settings)
    monkeypatch.setattr(api_main_module.uvicorn, "run", uvicorn_run)

    api_main()

    uvicorn_run.assert_called_once_with(
        "ai_incident_copilot.main:app",
        host="127.0.0.1",
        port=9090,
        reload=True,
        factory=False,
    )


@pytest.mark.asyncio
async def test_run_worker_manages_component_lifecycle(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Worker entrypoint должен поднимать зависимости, создавать readiness-файл и чисто завершаться."""

    ready_file = tmp_path / "worker" / "ready.flag"
    settings = Settings(
        kafka_enabled=False,
        worker_ready_file=ready_file.as_posix(),
        database_url_async_override="sqlite+aiosqlite:///worker-test.db",
    )
    logger = SimpleNamespace(info=Mock(), warning=Mock())
    publisher = SimpleNamespace(start=AsyncMock(), stop=AsyncMock())
    consumer = SimpleNamespace(start=AsyncMock(), stop=AsyncMock())
    database_manager = SimpleNamespace(session_factory=object(), dispose=AsyncMock())
    workflow_service = object()
    captured: dict[str, object] = {}

    class FakeLoop:
        def __init__(self) -> None:
            self.signals: list[signal.Signals] = []

        def add_signal_handler(self, sig: signal.Signals, callback) -> None:
            self.signals.append(sig)

    class FakeWorker:
        def __init__(
            self,
            *,
            settings: Settings,
            session_factory,
            consumer,
            event_publisher,
            workflow_service,
        ) -> None:
            captured["settings"] = settings
            captured["session_factory"] = session_factory
            captured["consumer"] = consumer
            captured["event_publisher"] = event_publisher
            captured["workflow_service"] = workflow_service

        async def run(self, stop_event) -> None:
            assert ready_file.exists()
            stop_event.set()

    fake_loop = FakeLoop()

    monkeypatch.setattr(worker_main, "get_settings", lambda: settings)
    monkeypatch.setattr(worker_main, "configure_logging", Mock())
    monkeypatch.setattr(worker_main, "get_logger", lambda _: logger)
    monkeypatch.setattr(worker_main.asyncio, "get_running_loop", lambda: fake_loop)
    monkeypatch.setattr(worker_main, "DatabaseManager", lambda _: database_manager)
    monkeypatch.setattr(worker_main, "build_event_publisher", lambda _: publisher)
    monkeypatch.setattr(worker_main, "KafkaEventConsumer", lambda *_: consumer)
    monkeypatch.setattr(worker_main, "IncidentWorkflowService", lambda _: workflow_service)
    monkeypatch.setattr(worker_main, "IncidentAnalysisWorker", FakeWorker)

    await worker_main.run_worker()

    assert captured["settings"] is settings
    assert captured["session_factory"] is database_manager.session_factory
    assert captured["consumer"] is consumer
    assert captured["event_publisher"] is publisher
    assert captured["workflow_service"] is workflow_service
    assert fake_loop.signals == [signal.SIGINT, signal.SIGTERM]
    publisher.start.assert_awaited_once()
    publisher.stop.assert_awaited_once()
    consumer.start.assert_awaited_once()
    consumer.stop.assert_awaited_once()
    database_manager.dispose.assert_awaited_once()
    assert not ready_file.exists()


def test_worker_main_delegates_to_asyncio_run(monkeypatch: pytest.MonkeyPatch) -> None:
    """Синхронный wrapper worker должен запускать корутину через asyncio.run."""

    called: dict[str, str] = {}

    def fake_asyncio_run(coro) -> None:
        called["name"] = coro.cr_code.co_name
        coro.close()

    monkeypatch.setattr(worker_main.asyncio, "run", fake_asyncio_run)

    worker_main.main()

    assert called["name"] == "run_worker"
