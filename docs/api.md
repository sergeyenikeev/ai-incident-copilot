# API

## Общие принципы

- все бизнес-endpoint'ы находятся под `/api/v1`
- ответы заворачиваются в структурированный JSON
- ошибки возвращаются в формате `error`
- пагинация передаётся через query params

## Endpoint'ы

### `POST /api/v1/incidents`

Создаёт инцидент.

#### Заголовки

- `Idempotency-Key` — опционально, для защиты от повторного создания

#### Тело запроса

```json
{
  "title": "Недоступен API gateway",
  "description": "Пользователи получают 502 и не могут завершить операции.",
  "source": "monitoring",
  "metadata": {
    "service": "gateway",
    "environment": "prod"
  }
}
```

#### Ответ

```json
{
  "data": {
    "id": "2dce0991-f970-47d1-a657-8478f40dcd96",
    "title": "Недоступен API gateway",
    "description": "Пользователи получают 502 и не могут завершить операции.",
    "source": "monitoring",
    "status": "received",
    "classification": null,
    "severity": null,
    "recommendation": null,
    "created_at": "2026-03-17T07:00:00Z",
    "updated_at": "2026-03-17T07:00:00Z",
    "metadata": {
      "service": "gateway",
      "environment": "prod"
    }
  }
}
```

### `GET /api/v1/incidents/{id}`

Возвращает один инцидент.

### `GET /api/v1/incidents`

Возвращает список инцидентов.

#### Query params

- `page`
- `page_size`
- `status`
- `classification`
- `severity`
- `source`

#### Пример

```bash
curl "http://localhost:8080/api/v1/incidents?page=1&page_size=10&status=analysis_requested"
```

#### Ответ

```json
{
  "data": {
    "items": [
      {
        "id": "2dce0991-f970-47d1-a657-8478f40dcd96",
        "title": "Недоступен API gateway",
        "source": "monitoring",
        "status": "analysis_requested",
        "classification": null,
        "severity": null,
        "created_at": "2026-03-17T07:00:00Z",
        "updated_at": "2026-03-17T07:05:00Z"
      }
    ]
  },
  "pagination": {
    "page": 1,
    "page_size": 10,
    "total": 1,
    "total_pages": 1
  }
}
```

### `POST /api/v1/incidents/{id}/analyze`

Переводит инцидент в состояние `analysis_requested` и публикует событие для worker.

### `GET /health`

Возвращает техническое состояние сервиса.

Пример:

```json
{
  "data": {
    "status": "ok",
    "service": "ai-incident-copilot",
    "environment": "local",
    "version": "0.1.0",
    "checks": {
      "api": "ok",
      "database": "ok",
      "kafka": "disabled"
    }
  }
}
```

### `GET /metrics`

Возвращает Prometheus-метрики.

## Ошибки

### Формат ошибки

```json
{
  "error": {
    "code": "validation_error",
    "message": "Запрос не прошёл валидацию",
    "request_id": "8bceb540-2c5f-4f83-9a03-63efdd8dfd88",
    "details": {
      "errors": []
    }
  }
}
```

### Основные коды

- `validation_error`
- `incident_not_found`
- `http_error`
- `internal_error`

## Статусы инцидента

- `received`
- `analysis_requested`
- `analyzing`
- `analyzed`
- `failed`

## Практические примеры

### Создание и повтор с тем же idempotency key

Если отправить повторный `POST /api/v1/incidents` с тем же `Idempotency-Key`, будет возвращён уже существующий инцидент.

### Фильтрация по severity

```bash
curl "http://localhost:8080/api/v1/incidents?severity=high"
```

### Получение результатов анализа

После обработки worker'ом `GET /api/v1/incidents/{id}` вернёт:

- `classification`
- `severity`
- `recommendation`

## Технические детали

- схемы описаны в `src/ai_incident_copilot/api/schemas`
- middleware добавляет `X-Request-ID`
- `/metrics` не включён в OpenAPI schema
