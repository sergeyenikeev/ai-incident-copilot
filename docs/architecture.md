# Архитектура

## Цели системы

`ai-incident-copilot` решает три основные задачи:

1. надёжно принимать и хранить инциденты
2. запускать анализ асинхронно и безопасно для повторов
3. сохранять полный след обработки для эксплуатации и аудита

## Компоненты

### API service

Отвечает за:

- приём REST-запросов
- валидацию входных данных
- запись инцидентов в PostgreSQL
- запись доменных событий в `incident_events`
- публикацию событий в Kafka
- отдачу состояния инцидентов и результатов анализа

### PostgreSQL

Используется как основное состояние системы.

Таблицы:

- `incidents`
- `workflow_runs`
- `workflow_steps`
- `incident_events`
- `audit_logs`

### Kafka

Используется для развязки синхронного API и тяжёлой аналитики.

Topics:

- `incident.created`
- `incident.analysis.requested`
- `incident.analysis.completed`

### Worker service

Отвечает за:

- чтение `incident.analysis.requested`
- retry-safe обработку сообщений
- запуск LangGraph workflow
- обновление БД
- публикацию `incident.analysis.completed`

### LangGraph workflow

Отвечает за прикладной анализ:

- классификация инцидента
- вычисление критичности
- выбор ветки обработки
- генерация рекомендации

## Поток данных

### Создание инцидента

1. Клиент вызывает `POST /api/v1/incidents`.
2. API валидирует payload.
3. API создаёт запись в `incidents`.
4. API пишет audit log.
5. API создаёт outbox-событие в `incident_events`.
6. API публикует `incident.created`.

### Запрос анализа

1. Клиент вызывает `POST /api/v1/incidents/{id}/analyze`.
2. Инцидент переводится в `analysis_requested`.
3. API создаёт запись `incident.analysis.requested`.
4. Worker получает событие.
5. Worker выполняет LangGraph workflow.
6. Worker обновляет инцидент до `analyzed` или `failed`.
7. Worker публикует `incident.analysis.completed`.

## Модель хранения

### incidents

Содержит:

- базовые поля инцидента
- текущий статус
- классификацию
- критичность
- рекомендацию
- `idempotency_key`

### workflow_runs

Содержит:

- один запуск workflow на один проход анализа
- статус запуска
- input/output payload
- ссылку на триггерное событие

### workflow_steps

Содержит:

- каждый node execution
- вход и выход шага
- статус шага
- ошибку при наличии

### incident_events

Содержит:

- доменное событие
- Kafka topic и event key
- payload сообщения
- статус доставки/обработки
- retry count
- idempotency key

### audit_logs

Содержит:

- важные прикладные действия
- actor
- request_id
- payload изменений

## Идемпотентность

### На уровне API

- повторный `POST /api/v1/incidents` с тем же `Idempotency-Key` вернёт уже созданный инцидент

### На уровне событий

- `incident_events.idempotency_key` совпадает с `metadata.event_id`
- worker пропускает события со статусом `consumed`

### На уровне retry

- ошибки обработки не приводят к дублированию финального результата
- worker делает ограниченное число повторов и пишет ошибку в БД

## Наблюдаемость

### Логи

JSON-логи содержат:

- `request_id`
- `incident_id`
- `workflow_run_id`
- `event_id`
- `timestamp`

### Health

`/health` возвращает:

- статус API
- доступность БД
- состояние Kafka publisher

### Metrics

`/metrics` отдаёт Prometheus-совместимые метрики через `prometheus-fastapi-instrumentator`

## Развёртывание

### Локально

- `uv sync`
- `uv run alembic upgrade head`
- `uv run ai-incident-api`
- `uv run ai-incident-worker`

### Контейнеры

- `docker compose up --build`

### Kubernetes

Есть два варианта:

- plain manifests в `k8s/`
- Helm chart в `helm/ai-incident-copilot/`

Для Kubernetes миграции вынесены в отдельный Job:

- plain manifests: `k8s/migration-job.yaml`
- Helm: hook Job `pre-install,pre-upgrade`

Это позволяет не выполнять `alembic upgrade head` при каждом рестарте API-pod и упрощает rollout.

Дополнительно:

- подробная модель хранения: `docs/data-model.md`
- ключевые архитектурные решения: `docs/decisions.md`
