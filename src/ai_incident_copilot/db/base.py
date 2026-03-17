"""Базовые сущности SQLAlchemy.

Модуль содержит минимальный фундамент ORM-слоя:

- общий `DeclarativeBase`
- naming convention для ограничений и индексов
- mixin с временными метками

Эти вещи редко меняются, но влияют почти на все модели проекта.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Базовый declarative-класс с единым naming convention.

    Единый naming convention особенно полезен для Alembic: имена индексов
    и constraint'ов получаются предсказуемыми и стабильными между окружениями.
    """

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class TimestampMixin:
    """Примесь с временными метками создания и обновления.

    Используется там, где сущность должна автоматически хранить время создания
    и последнего обновления без ручного заполнения в каждом сервисе.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
