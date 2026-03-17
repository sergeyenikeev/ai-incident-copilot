"""Общие схемы API.

Модуль задаёт универсальный формат успешных и ошибочных ответов. Это позволяет
всем endpoint'ам возвращать предсказуемую структуру независимо от payload.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ResponseEnvelope[PayloadT](BaseModel):
    """Унифицированный ответ с полезной нагрузкой.

    Обёртка `data` делает контракт API стабильнее: в ответ всегда можно
    добавить метаданные рядом, не ломая форму полезной нагрузки.
    """

    model_config = ConfigDict(from_attributes=True)

    data: PayloadT


class PaginationMeta(BaseModel):
    """Метаданные пагинации."""

    page: int
    page_size: int
    total: int
    total_pages: int


class PaginatedResponse[PayloadT](BaseModel):
    """Ответ со списком и метаданными пагинации."""

    model_config = ConfigDict(from_attributes=True)

    data: PayloadT
    pagination: PaginationMeta


class ErrorInfo(BaseModel):
    """Описание ошибки API.

    Здесь лежит всё, что нужно клиенту для машинной и человеческой обработки:

    - код ошибки
    - сообщение
    - request_id
    - дополнительные детали
    """

    code: str
    message: str
    request_id: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorEnvelope(BaseModel):
    """Конверт ответа с ошибкой."""

    error: ErrorInfo
