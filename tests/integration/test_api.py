"""Интеграционные тесты HTTP API."""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4


def test_health_endpoint_returns_dependency_checks(client) -> None:
    response = client.get("/health")
    payload = response.json()

    assert response.status_code == 200
    assert payload["data"]["checks"]["api"] == "ok"
    assert payload["data"]["checks"]["database"] == "ok"
    assert payload["data"]["checks"]["kafka"] == "disabled"


def test_health_endpoint_returns_degraded_when_dependency_fails(client) -> None:
    client.app.state.database_manager.check_health = AsyncMock(side_effect=RuntimeError("db unavailable"))
    client.app.state.event_publisher.health_status = AsyncMock(return_value="error")

    response = client.get("/health")
    payload = response.json()

    assert response.status_code == 200
    assert payload["data"]["status"] == "degraded"
    assert payload["data"]["checks"]["database"] == "error"
    assert payload["data"]["checks"]["kafka"] == "error"


def test_incident_crud_and_filters(client) -> None:
    first = client.post(
        "/api/v1/incidents",
        headers={"Idempotency-Key": "incident-1"},
        json={
            "title": "Недоступен checkout",
            "description": "Пользователи получают ошибки оплаты и checkout перестал завершать заказ.",
            "source": "monitoring",
            "metadata": {"service": "checkout"},
        },
    )
    second = client.post(
        "/api/v1/incidents",
        json={
            "title": "Проблема с очередью задач",
            "description": "Worker не успевает разгребать очередь и время реакции растёт выше SLA.",
            "source": "monitoring",
            "metadata": {"service": "worker"},
        },
    )
    incident_id = first.json()["data"]["id"]
    analyze = client.post(f"/api/v1/incidents/{incident_id}/analyze")
    get_one = client.get(f"/api/v1/incidents/{incident_id}")
    filtered = client.get("/api/v1/incidents", params={"status": "analysis_requested"})

    assert first.status_code == 201
    assert second.status_code == 201
    assert analyze.status_code == 200
    assert get_one.json()["data"]["status"] == "analysis_requested"
    assert filtered.json()["pagination"]["total"] == 1
    assert filtered.json()["data"]["items"][0]["id"] == incident_id


def test_validation_and_not_found_errors_are_structured(client) -> None:
    invalid = client.post(
        "/api/v1/incidents",
        json={
            "title": "x",
            "description": "коротко",
        },
    )
    missing = client.get(f"/api/v1/incidents/{uuid4()}")

    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "validation_error"
    assert invalid.json()["error"]["request_id"]
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "incident_not_found"
