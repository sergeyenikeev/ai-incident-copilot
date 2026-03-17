"""Инициализация SQLAlchemy и управление сессиями.

Модуль концентрирует всё, что связано с жизненным циклом подключения к БД:

- создание async engine
- создание session factory
- healthcheck
- корректное закрытие ресурсов

Это позволяет остальным модулям не знать деталей настройки SQLAlchemy.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from ai_incident_copilot.db.base import Base


class DatabaseManager:
    """Управляет async engine и фабрикой сессий.

    Объект создаётся один раз на процесс и затем переиспользуется API или
    worker-слоем. Это дешевле и надёжнее, чем создавать engine по месту.
    """

    def __init__(self, database_url: str) -> None:
        self._engine: AsyncEngine = create_async_engine(
            database_url,
            echo=False,
            pool_pre_ping=True,
        )
        self._session_factory = async_sessionmaker(
            bind=self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    @property
    def engine(self) -> AsyncEngine:
        """Возвращает SQLAlchemy engine."""

        return self._engine

    @property
    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        """Возвращает фабрику асинхронных сессий."""

        return self._session_factory

    async def check_health(self) -> None:
        """Проверяет доступность базы данных.

        Вызывается из `/health` и intentionally выполняет самый дешёвый
        возможный запрос, чтобы не нагружать БД лишней логикой.
        """

        async with self._session_factory() as session:
            await session.execute(text("SELECT 1"))

    async def create_all(self) -> None:
        """Создаёт все таблицы. Используется в тестах и локальном smoke-режиме."""

        async with self._engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    async def dispose(self) -> None:
        """Корректно закрывает engine."""

        await self._engine.dispose()
