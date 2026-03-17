"""Общие схемы API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ResponseEnvelope[PayloadT](BaseModel):
    """Унифицированный ответ с полезной нагрузкой."""

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
    """Описание ошибки API."""

    code: str
    message: str
    request_id: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorEnvelope(BaseModel):
    """Конверт ответа с ошибкой."""

    error: ErrorInfo
