# Модули проекта

## Зачем нужен этот документ

Этот файл помогает быстро понять, как устроен код проекта, в каком порядке его
читать и за что отвечает каждый модуль.

Если начинать с самого важного, то читать код лучше сверху вниз по
runtime-потоку:

1. `src/ai_incident_copilot/main.py`
2. `src/ai_incident_copilot/api/routers/incidents.py`
3. `src/ai_incident_copilot/application/services/incident_service.py`
4. `src/ai_incident_copilot/events/kafka.py`
5. `src/ai_incident_copilot/worker_main.py`
6. `src/ai_incident_copilot/workers/incident_analysis_worker.py`
7. `src/ai_incident_copilot/application/workflows/service.py`
8. `src/ai_incident_copilot/application/workflows/rule_based.py`
9. `src/ai_incident_copilot/db/models.py`
10. `src/ai_incident_copilot/db/repositories/*.py`

Именно в этих файлах лежит основной смысл системы.

## Самое важное: сквозной поток данных

### 1. API принимает инцидент

- `main.py` собирает FastAPI-приложение и поднимает зависимости.
- `api/routers/incidents.py` принимает HTTP-запросы.
- `api/schemas/incidents.py` валидирует вход и описывает выход.

### 2. Прикладной сервис сохраняет бизнес-факт

- `application/services/incident_service.py` создаёт инцидент.
- `db/repositories/incidents.py` пишет сам объект в БД.
- `db/repositories/audit.py` пишет аудит.
- `db/repositories/events.py` пишет событие в `incident_events`.

### 3. Kafka связывает API и worker

- `events/kafka.py` публикует `incident.created` и `incident.analysis.requested`.
- `events/consumer.py` читает события на стороне worker.
- `events/schemas.py` задаёт типы сообщений.

### 4. Worker выполняет анализ

- `worker_main.py` поднимает инфраструктуру worker-процесса.
- `workers/incident_analysis_worker.py` читает Kafka-события, проверяет
  дубликаты, делает retry и запускает workflow.
- `application/workflows/service.py` оркестрирует LangGraph.
- `application/workflows/rule_based.py` даёт текущую логику анализа.

### 5. Результат возвращается в доменную модель

- `application/workflows/service.py` обновляет запись `incidents`.
- `workers/incident_analysis_worker.py` публикует `incident.analysis.completed`.
- `incident_events`, `workflow_runs`, `workflow_steps` и `audit_logs` сохраняют
  полную историю того, что произошло.

## Пакет `core`

### `core/config.py`

Нужен для централизованной загрузки конфигурации из переменных окружения.

Что делает:

- описывает `Settings`
- строит `database_url_async`
- строит `database_url_sync`
- хранит Kafka, worker и API-настройки

Почему это важно:

- конфигурация не размазана по проекту
- тесты могут подменять настройки централизованно
- Docker, CI и Kubernetes используют один и тот же контракт env-переменных

### `core/logging.py`

Нужен для структурированных JSON-логов.

Что делает:

- настраивает `structlog`
- объединяет наш логгер с логами Uvicorn и aiokafka
- поддерживает context-поля вроде `request_id`, `incident_id`, `event_id`

Почему это важно:

- без этого сложно расследовать проблемы в асинхронной и event-driven системе
- можно коррелировать HTTP-запрос, запись в БД, workflow и Kafka-событие

## Пакет `api`

### `api/routers/incidents.py`

Это транспортный вход для основной бизнес-функции проекта.

Что делает:

- принимает создание инцидента
- возвращает инцидент по id
- отдаёт список с фильтрацией и пагинацией
- ставит инцидент в очередь на анализ

Чего не делает:

- не работает напрямую с SQLAlchemy
- не знает детали Kafka
- не содержит rule-based логику

### `api/routers/health.py`

Нужен для технического healthcheck и Kubernetes probes.

Что делает:

- проверяет БД
- проверяет состояние publisher
- возвращает aggregated status

### `api/schemas/common.py`

Содержит общие модели ответа:

- `ResponseEnvelope`
- `PaginatedResponse`
- общую структуру пагинации

Почему это важно:

- все ответы API имеют одинаковую форму
- клиентам легче интегрироваться

### `api/schemas/incidents.py`

Описывает контракт API вокруг инцидентов:

- входные DTO
- фильтры
- краткое и полное представление инцидента
- структуры списка

### `api/schemas/health.py`

Описывает ответ `/health`.

### `api/dependencies.py`

Слой получения зависимостей из `app.state`.

Нужен, чтобы:

- не создавать сервисы в каждом роутере вручную
- не держать глобальные синглтоны на уровне модулей
- удобно подменять зависимости в тестах

### `api/middleware.py`

Нужен для `request_id` и контекста логирования HTTP-запросов.

### `api/errors.py`

Нужен для единообразной обработки ошибок.

Что делает:

- задаёт `ApplicationError`
- преобразует validation/runtime ошибки в структурированный JSON-ответ

## Пакет `application/services`

### `application/services/incident_service.py`

Это центральный прикладной сервис проекта.

Что делает:

- создаёт инциденты
- обеспечивает идемпотентность через `Idempotency-Key`
- пишет аудит
- создаёт outbox-подобные записи в `incident_events`
- публикует события в Kafka
- собирает DTO-ответы для API

Почему это важно:

- здесь сходятся HTTP, БД и Kafka
- именно этот слой отделяет транспорт от предметной логики

## Пакет `application/workflows`

### `application/workflows/state.py`

Описывает типизированное состояние workflow и итоговый результат анализа.

Это важно, потому что LangGraph работает со state object, и нам нужен
стабильный контракт между узлами графа.

### `application/workflows/rule_based.py`

Текущий "движок" анализа.

Что делает:

- классифицирует инцидент
- считает severity
- выбирает ветку `standard` или `escalated`
- генерирует рекомендацию

Почему он отдельный:

- его легко заменить на LLM-анализатор
- orchestration и persistence при этом останутся прежними

### `application/workflows/service.py`

Главный orchestration-модуль анализа.

Что делает:

- создаёт `workflow_run`
- строит LangGraph
- оборачивает каждый node в сохранение `workflow_steps`
- обновляет итог инцидента
- пишет ошибки и финальный результат

Почему это важно:

- именно он превращает "просто функцию анализа" в production workflow
- без него не было бы трассировки шагов и контроля статусов

## Пакет `events`

### `events/schemas.py`

Описывает формат событий Kafka.

Что в нём лежит:

- `EventMetadata`
- payload-модели для `incident.created`
- payload-модели для `incident.analysis.requested`
- payload-модели для `incident.analysis.completed`

### `events/kafka.py`

Нужен для публикации событий и скрытия деталей `aiokafka`.

Что делает:

- задаёт контракт `EventPublisher`
- реализует `KafkaEventPublisher`
- реализует `NoOpEventPublisher`
- выбирает реализацию по конфигурации

Почему `NoOpEventPublisher` важен:

- тесты и локальная разработка не требуют живого Kafka broker
- прикладной код не обрастает условными `if kafka_enabled`

### `events/consumer.py`

Нужен worker-слою для чтения событий с ручным управлением offset.

## Пакет `workers`

### `worker_main.py`

Это bootstrap фонового процесса.

Что делает:

- читает настройки
- поднимает consumer и publisher
- создаёт workflow service
- запускает `IncidentAnalysisWorker`
- поддерживает graceful shutdown
- пишет readiness-файл

### `workers/incident_analysis_worker.py`

Главный рабочий цикл обработки событий.

Что делает:

- читает `incident.analysis.requested`
- валидирует payload
- проверяет дубликаты через `incident_events`
- запускает workflow
- делает retry при временных ошибках
- публикует `incident.analysis.completed`

Почему это важно:

- здесь реализована идемпотентная обработка Kafka-сообщений
- здесь находится граница между broker и предметной логикой

## Пакет `db`

### `db/base.py`

Базовый declarative-класс и mixin'ы.

### `db/session.py`

Управляет SQLAlchemy engine и `async_sessionmaker`.

Также содержит healthcheck БД.

### `db/models.py`

Описывает основные таблицы:

- `incidents`
- `workflow_runs`
- `workflow_steps`
- `incident_events`
- `audit_logs`

Это самый важный модуль хранения данных.

### `db/repositories/incidents.py`

Инкапсулирует запросы по инцидентам:

- получение по id
- поиск по `idempotency_key`
- пагинацию и фильтрацию

### `db/repositories/events.py`

Отвечает за журнал событий и их статусы:

- `pending`
- `published`
- `failed`
- `consumed`

Это один из ключевых модулей для retry и идемпотентности.

### `db/repositories/workflows.py`

Работает с `workflow_runs` и `workflow_steps`.

### `db/repositories/audit.py`

Пишет технический и бизнес-аудит.

## Пакет `domain`

### `domain/enums.py`

Здесь лежат enum'ы предметной области:

- статусы инцидента
- типы событий
- статусы workflow
- уровни критичности

Эти enum'ы важны, потому что задают словарь состояний всей системы.

## Миграции и служебные каталоги

### `alembic/env.py`

Связывает Alembic с приложением и ORM-моделями.

Что делает:

- читает DSN из `Settings`
- подключает `Base.metadata`
- запускает online/offline миграции

### `alembic/versions/`

Здесь лежат конкретные миграции схемы БД.

Это история эволюции структуры данных проекта.

## Тестовая структура

### `tests/conftest.py`

Общий bootstrap тестов:

- временная SQLite-база
- применение миграций
- создание `TestClient`
- общие fixtures

### `tests/unit/`

Содержит быстрые тесты изолированной логики:

- workflow
- сервисы
- Kafka-обвязка
- entrypoint'ы

### `tests/integration/`

Содержит сценарии, где вместе проверяются несколько слоёв:

- HTTP API
- БД
- worker flow

Подробный разбор тестового контура: `docs/testing.md`

## Инфраструктурные файлы

### `Dockerfile.api`

Собирает runtime-образ API-сервиса.

### `Dockerfile.worker`

Собирает runtime-образ worker-сервиса.

### `docker-compose.yml`

Поднимает локальный контур из:

- PostgreSQL
- Kafka
- API
- worker

### `.github/workflows/ci.yml`

Описывает CI/CD pipeline:

- lint
- type-check
- tests
- upload coverage
- build/push Docker images

### `k8s/`

Plain Kubernetes manifests для базового деплоя.

### `helm/ai-incident-copilot/`

Helm chart для более управляемого и параметризуемого деплоя.

## Модули верхнего уровня

### `main.py`

Главная точка входа API-сервиса.

### `worker_main.py`

Главная точка входа worker-сервиса.

### `__init__.py`

Используются как package markers и для экспортов версии/пространства имён.

## В каком порядке читать код новому разработчику

Если нужно быстро войти в проект, лучше идти так:

1. `README.md`
2. `docs/architecture.md`
3. `docs/workflow.md`
4. этот файл
5. `src/ai_incident_copilot/main.py`
6. `src/ai_incident_copilot/api/routers/incidents.py`
7. `src/ai_incident_copilot/application/services/incident_service.py`
8. `src/ai_incident_copilot/workers/incident_analysis_worker.py`
9. `src/ai_incident_copilot/application/workflows/service.py`
10. `src/ai_incident_copilot/db/models.py`

Такой порядок позволяет сначала понять пользовательский сценарий, потом
инфраструктуру, и только после этого детали хранения и интеграций.
