# Структура Python-кода

## Зачем этот документ

Если нужно быстро понять, какие пакеты есть в `src/ai_incident_copilot` и как они связаны,
этот файл рассказывает об основных папках и их назначении.

## Основные пакеты

- `api/` — FastAPI слой: routers, schemas, middleware, exception handling.
- `application/` — прикладные сервисы и workflow orchestration, не зависящие от HTTP.
- `events/` — Kafka publisher/consumer и описания event схем.
- `db/` — модели, базовая инфраструктура, репозитории и сессии.
- `core/` — конфигурация, логирование и общие helper’ы.
- `workers/` — worker entrypoint и orchestration для анализатора.
- `tests/` — набор unit/integration тестов и fixtures.

## Как модули взаимодействуют

1. `api.main` собирает FastAPI приложение и прокидывает зависимости в `app.state`.
2. `api` роутеры вызывают `application.services` для бизнес-логики.
3. `application.services` работает через `db.repositories` и `events` publisher.
4. `events.consumer` и worker читают Kafka и вызывают `application.workflows`.
5. `db.models` описывает schema, а `db.repositories` инкапсулируют SQL-запросы.
6. `core.config` и `core.logging` доступны всем слоям.

## Где добавлять новый код

1. Новая бизнес-функция → `application/services` → новые репозитории и схемы.
2. Новый event → `events.schemas`, `incident_events`, worker логика.
3. Новый workflow node → `application/workflows` с соответствующим тестом.
4. Новые API endpoint → в `api/routers`, используя `IncidentService`.

## Дополнительные ресурсы

- [docs/modules.md](docs/modules.md) — комплексный гид по каждому пакету.
- [README.md](README.md) — обзор всего проекта.
