"""Общие фикстуры тестового набора."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient

from ai_incident_copilot.core.config import Settings, get_settings
from ai_incident_copilot.db.session import DatabaseManager
from ai_incident_copilot.main import create_app
from alembic import command


@pytest.fixture
def sqlite_urls(tmp_path: Path) -> dict[str, str]:
    """Возвращает sync/async URL для временной SQLite-базы."""

    db_path = tmp_path / "incident-test.db"
    return {
        "path": db_path.as_posix(),
        "sync": f"sqlite:///{db_path.as_posix()}",
        "async": f"sqlite+aiosqlite:///{db_path.as_posix()}",
    }


@pytest.fixture
def migrated_settings(monkeypatch: pytest.MonkeyPatch, sqlite_urls: dict[str, str]) -> Settings:
    """Применяет Alembic-миграции и возвращает настройки приложения для интеграционных тестов."""

    get_settings.cache_clear()
    monkeypatch.setenv("DATABASE_URL_SYNC", sqlite_urls["sync"])
    config = Config("alembic.ini")
    command.upgrade(config, "head")
    settings = Settings(
        database_url_async_override=sqlite_urls["async"],
        database_url_sync_override=sqlite_urls["sync"],
        kafka_enabled=False,
        app_debug=False,
    )
    yield settings
    get_settings.cache_clear()


@pytest.fixture
def app(migrated_settings: Settings):
    """Создаёт FastAPI-приложение поверх временной БД."""

    return create_app(migrated_settings)


@pytest.fixture
def client(app) -> TestClient:
    """HTTP-клиент FastAPI для интеграционных тестов."""

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
async def unit_db_manager(sqlite_urls: dict[str, str]) -> DatabaseManager:
    """Лёгкая БД для unit-тестов через прямое создание схемы."""

    manager = DatabaseManager(sqlite_urls["async"])
    await manager.create_all()
    yield manager
    await manager.dispose()


def run_async(coro: Any) -> Any:
    """Упрощает запуск async-кода из синхронных тестов."""

    return asyncio.run(coro)
