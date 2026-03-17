# ai-incident-copilot

`ai-incident-copilot` — production-style backend-платформа для приёма, анализа и сопровождения инцидентов.

Сервис принимает инциденты через FastAPI, сохраняет их в PostgreSQL, публикует события в Kafka, обрабатывает запросы анализа через отдельный worker и LangGraph workflow, сохраняет результаты анализа и отдаёт их обратно через API.

## Основные возможности

- REST API с versioning: `/api/v1`
- хранение инцидентов, запусков workflow, шагов, событий и audit trail в PostgreSQL
- event-driven архитектура на Kafka
- отдельный worker-сервис для анализа инцидентов
- LangGraph pipeline с типизированным состоянием и ветвлением
- JSON-логирование с `request_id`, `incident_id`, `workflow_run_id`
- метрики через `/metrics`
- миграции Alembic
- контейнеризация через Docker и `docker-compose`
- Kubernetes manifests и Helm chart
- CI/CD в GitHub Actions
- unit + integration тесты, coverage > 80%

## Архитектура

```text
                    +----------------------+
                    |      REST Client     |
                    +----------+-----------+
                               |
                               v
                     +---------+---------+
                     |  FastAPI API      |
                     |  /incidents       |
                     |  /health          |
                     |  /metrics         |
                     +----+---------+----+
                          |         |
                          |         |
                          v         v
                +---------+--+   +--+------------------+
                | PostgreSQL |   | Kafka Topics        |
                | incidents  |   | incident.created    |
                | workflow_* |   | incident.analysis.* |
                | events     |   +----------+----------+
                | audit_logs |              |
                +------+-----+              |
                       ^                    v
                       |          +---------+---------+
                       |          | Worker Service    |
                       |          | Kafka Consumer    |
                       |          | LangGraph Runner  |
                       |          +---------+---------+
                       |                    |
                       +--------------------+
```

Подробности:

- архитектура: [`docs/architecture.md`](docs/architecture.md)
- API: [`docs/api.md`](docs/api.md)
- workflow: [`docs/workflow.md`](docs/workflow.md)

## Технологический стек

- Python 3.11+
- FastAPI
- Uvicorn
- PostgreSQL + SQLAlchemy 2.x
- Kafka + `aiokafka`
- LangGraph
- Alembic
- `uv` + `requirements.txt`
- Docker / Docker Compose
- Kubernetes + Helm
- GitHub Actions
- Pytest, Ruff, Mypy

## Структура проекта

```text
.
├── src/ai_incident_copilot/
│   ├── api/                 # FastAPI маршруты, middleware, схемы
│   ├── application/         # сервисы и workflow
│   ├── core/                # конфигурация и логирование
│   ├── db/                  # SQLAlchemy модели, репозитории, сессии
│   ├── domain/              # доменные enum'ы
│   ├── events/              # Kafka producer/consumer и event schema
│   ├── workers/             # worker orchestration
│   ├── main.py              # API entrypoint
│   └── worker_main.py       # worker entrypoint
├── alembic/                 # миграции
├── tests/                   # unit и integration тесты
├── k8s/                     # plain Kubernetes manifests
├── helm/ai-incident-copilot # Helm chart
├── Dockerfile.api
├── Dockerfile.worker
└── docker-compose.yml
```

## Быстрый старт локально

### 1. Подготовка окружения

```bash
cp .env.example .env
```

Если у вас уже есть PostgreSQL и Kafka локально, поправьте `.env`.

### 2. Установка зависимостей

```bash
uv sync --all-groups
```

### 3. Применение миграций

```bash
uv run alembic upgrade head
```

### 4. Запуск API

```bash
uv run ai-incident-api
```

### 5. Запуск worker

Во втором терминале:

```bash
uv run ai-incident-worker
```

## Полный запуск через Docker Compose

```bash
docker compose up --build
```

После запуска будут доступны:

- API: `http://localhost:8080`
- Healthcheck: `http://localhost:8080/health`
- Metrics: `http://localhost:8080/metrics`
- PostgreSQL: `localhost:5432`
- Kafka: `localhost:9092`

## Основные команды разработки

### Линтер и типы

```bash
uv run ruff check src alembic tests
uv run mypy src
```

### Тесты

```bash
uv run pytest
```

На текущем состоянии проекта тесты проходят с покрытием выше 80%.

### Экспорт pip-совместимого файла

```bash
uv export --format requirements-txt --all-groups --no-hashes -o requirements.txt
```

## REST API

### Создать инцидент

```bash
curl -X POST http://localhost:8080/api/v1/incidents \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: incident-001" \
  -d '{
    "title": "Недоступен payment gateway",
    "description": "Сервис оплаты отвечает 502 и не завершает транзакции в production.",
    "source": "monitoring",
    "metadata": {
      "service": "payments",
      "environment": "prod"
    }
  }'
```

### Получить инцидент

```bash
curl http://localhost:8080/api/v1/incidents/<incident_id>
```

### Получить список инцидентов

```bash
curl "http://localhost:8080/api/v1/incidents?page=1&page_size=20&status=analysis_requested"
```

### Запросить анализ

```bash
curl -X POST http://localhost:8080/api/v1/incidents/<incident_id>/analyze
```

### Health и Metrics

```bash
curl http://localhost:8080/health
curl http://localhost:8080/metrics
```

Подробная спецификация и примеры ответов: [`docs/api.md`](docs/api.md)

## Как работает Kafka flow

### При создании инцидента

1. API сохраняет инцидент в PostgreSQL.
2. API создаёт запись в `incident_events`.
3. API публикует событие `incident.created` в Kafka.
4. Статус outbox-события помечается как `published`.

### При запросе анализа

1. API обновляет статус инцидента на `analysis_requested`.
2. API пишет событие `incident.analysis.requested`.
3. Worker читает событие из Kafka.
4. Worker выполняет LangGraph workflow.
5. Worker обновляет инцидент в БД и публикует `incident.analysis.completed`.

## Как работает LangGraph workflow

Текущий pipeline состоит из шагов:

1. `classify_incident`
2. `determine_severity`
3. decision node: выбор `standard` или `escalated`
4. `generate_standard_recommendation` или `generate_escalated_recommendation`

Для каждого запуска сохраняются:

- запись в `workflow_runs`
- шаги в `workflow_steps`
- итоговая классификация
- критичность
- `priority_score`
- рекомендация

Сейчас workflow использует rule-based анализатор, но код подготовлен к подмене узлов на LLM-логику.

Подробности: [`docs/workflow.md`](docs/workflow.md)

## Идемпотентность и retry

- `Idempotency-Key` на `POST /api/v1/incidents` предотвращает повторное создание инцидента.
- `incident_events.idempotency_key` связан с `event_id` Kafka-сообщения.
- worker пропускает уже `consumed` события.
- retry worker'а управляется `KAFKA_MAX_RETRIES` и `WORKER_RETRY_BACKOFF_SECONDS`.

## Логирование и наблюдаемость

Система пишет JSON-логи.

Ключевые поля:

- `request_id`
- `incident_id`
- `workflow_run_id`
- `timestamp`
- `level`

Логируются:

- HTTP-запросы
- ошибки API
- публикация и обработка Kafka-событий
- каждый шаг workflow
- запуск и остановка worker

## CI/CD

Workflow GitHub Actions расположен в:

- `.github/workflows/ci.yml`

Pipeline выполняет:

- `uv sync`
- Ruff
- Mypy
- Pytest + coverage
- сборку Docker-образов
- push образов в GHCR при push в `main`

## Kubernetes и Helm

### Plain manifests

Файлы находятся в каталоге `k8s/`.

Пример применения:

```bash
kubectl apply -f k8s/secret.yaml
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/api-deployment.yaml
kubectl apply -f k8s/worker-deployment.yaml
kubectl apply -f k8s/service.yaml
kubectl apply -f k8s/ingress.yaml
kubectl apply -f k8s/hpa-api.yaml
```

### Helm chart

```bash
helm upgrade --install ai-incident-copilot ./helm/ai-incident-copilot
```

Перед деплоем обязательно переопределите:

- `secret.postgresPassword`
- image tags
- ingress host
- адреса PostgreSQL и Kafka

## Важные замечания

- В текущей реализации Kafka-события записываются в БД до публикации, что даёт outbox-подобную модель и поддерживает retry-safe обработку.
- Тестовый контур использует SQLite для изоляции и скорости, а runtime-код ориентирован на PostgreSQL.
- В рамках этой среды Docker/Kubernetes не запускались фактически, но артефакты сборки, compose, manifests и Helm chart подготовлены.
