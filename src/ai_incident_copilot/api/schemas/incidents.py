"""Схемы запросов и ответов для инцидентов."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from ai_incident_copilot.api.schemas.common import PaginationMeta


class IncidentStatus(StrEnum):
    """Состояния жизненного цикла инцидента."""

    RECEIVED = "received"
    ANALYSIS_REQUESTED = "analysis_requested"
    ANALYZING = "analyzing"
    ANALYZED = "analyzed"
    FAILED = "failed"


class IncidentCreateRequest(BaseModel):
    """Запрос на создание инцидента."""

    title: str = Field(min_length=3, max_length=255)
    description: str = Field(min_length=10, max_length=10_000)
    source: str | None = Field(default=None, max_length=128)
    metadata: dict[str, Any] = Field(default_factory=dict)


class IncidentResponse(BaseModel):
    """Полное представление инцидента."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    description: str
    source: str | None = None
    status: IncidentStatus
    classification: str | None = None
    severity: str | None = None
    recommendation: str | None = None
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class IncidentSummary(BaseModel):
    """Краткое представление инцидента в списках."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    source: str | None = None
    status: IncidentStatus
    classification: str | None = None
    severity: str | None = None
    created_at: datetime
    updated_at: datetime


class IncidentListResponse(BaseModel):
    """Набор инцидентов для ответа списка."""

    items: list[IncidentSummary]


class PaginationParams(BaseModel):
    """Параметры пагинации на входе сервисного слоя."""

    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class IncidentFilterParams(BaseModel):
    """Фильтры списка инцидентов."""

    status: IncidentStatus | None = None
    classification: str | None = None
    severity: str | None = None
    source: str | None = None


class IncidentUpdateResponse(BaseModel):
    """Внутреннее представление результатов пагинации."""

    items: list[IncidentSummary]
    total: int
    page: int
    page_size: int
    total_pages: int


__all__ = [
    "IncidentCreateRequest",
    "IncidentFilterParams",
    "IncidentListResponse",
    "IncidentResponse",
    "IncidentStatus",
    "IncidentSummary",
    "IncidentUpdateResponse",
    "PaginationMeta",
    "PaginationParams",
]
