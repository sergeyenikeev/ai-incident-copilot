# Инфраструктура и эксплуатационные файлы

## Зачем нужен этот документ

Этот файл объясняет, для чего нужны контейнерные, CI/CD и deployment-артефакты
проекта. Если в `docs/modules.md` больше внимания уделено Python-коду, то здесь
фокус именно на operational-слое.

## Самое важное

Если смотреть на инфраструктуру сверху вниз, то порядок такой:

1. локальный запуск: `docker-compose.yml`
2. runtime-образы: `Dockerfile.api`, `Dockerfile.worker`
3. контроль качества: `.github/workflows/ci.yml`
4. миграции: `alembic/`
5. базовый деплой: `k8s/`
6. параметризуемый деплой: `helm/ai-incident-copilot/`

## Docker

### `Dockerfile.api`

Нужен для сборки образа API-сервиса.

Что делает:

- берёт `python:3.12-slim`
- ставит системные пакеты для сборки зависимостей
- ставит `uv`
- копирует проект
- выполняет `uv sync --frozen --no-dev`
- запускает `alembic upgrade head && ai-incident-api`

Почему так:

- один образ содержит весь runtime API
- миграции в Compose можно выполнить прямо перед стартом сервиса
- образ воспроизводим за счёт `uv.lock`

### `Dockerfile.worker`

Нужен для сборки образа worker-сервиса.

Что делает:

- использует тот же базовый слой, что и API
- устанавливает тот же код и зависимости
- запускает `ai-incident-worker`

Почему это важно:

- API и worker используют общий код приложения
- меньше риск расхождения версий зависимостей

## Docker Compose

### `docker-compose.yml`

Нужен для локального полного запуска проекта одной командой.

Что поднимает:

- `postgres`
- `kafka`
- `api`
- `worker`

Почему это важно:

- можно быстро воспроизвести почти полный runtime-контур
- удобно для локальной проверки интеграции между сервисами

### Почему Kafka в KRaft-режиме

В локальном контуре выбран single-node Kafka без отдельного ZooKeeper.

Причина:

- проще локальный запуск
- меньше контейнеров
- достаточно для dev/demo окружения

## Миграции

### `alembic/env.py`

Это связующий слой между Alembic и приложением.

Что делает:

- подтягивает DSN из `Settings`
- импортирует metadata SQLAlchemy-моделей
- запускает offline/online миграции

### `alembic/versions/`

Здесь лежат файлы миграций, которые изменяют структуру БД по шагам.

Почему это важно:

- схема БД воспроизводима
- изменения структуры можно отслеживать и катить контролируемо

## GitHub Actions

### `.github/workflows/ci.yml`

Это автоматический pipeline контроля качества и доставки.

### Job `quality`

Проверяет:

- `ruff`
- `mypy`
- `pytest`
- формирование `coverage.xml`

Почему это важно:

- код не должен попадать в основную ветку без базовой верификации

### Job `docker`

Выполняется только для `push` в `main` и только после `quality`.

Что делает:

- логинится в GHCR
- собирает API-образ
- собирает worker-образ
- публикует теги `sha` и `latest`

Почему это важно:

- артефакты доставки появляются только после зелёных проверок

## Kubernetes manifests

### Каталог `k8s/`

Содержит plain manifests:

- `configmap.yaml`
- `secret.yaml`
- `migration-job.yaml`
- `api-deployment.yaml`
- `worker-deployment.yaml`
- `service.yaml`
- `ingress.yaml`
- `hpa-api.yaml`

### Что здесь важно

#### `migration-job.yaml`

Отдельный Job для `alembic upgrade head`.

Зачем:

- не выполнять миграции при каждом старте API-pod
- отделить rollout приложения от изменения схемы БД

#### `api-deployment.yaml`

Описывает запуск API-подов.

Содержит:

- env через `ConfigMap` и `Secret`
- probes
- ресурсы
- команду запуска API

#### `worker-deployment.yaml`

Описывает запуск worker-подов.

Особенность:

- worker не имеет HTTP health endpoint
- readiness и liveness построены через readiness-файл

## Helm chart

### Каталог `helm/ai-incident-copilot/`

Нужен для более гибкого деплоя по сравнению с plain manifests.

Что даёт Helm:

- параметризацию image tags
- переопределение env и секретов
- hook Job для миграций
- удобный upgrade/install сценарий

### Почему миграции сделаны hook Job

Потому что Helm должен иметь возможность:

- применить миграции до rollout workload'ов
- не держать миграции внутри жизненного цикла API deployment

## Как читать инфраструктуру новому инженеру

Если задача понять, как проект запускать и деплоить, лучше идти так:

1. `README.md`
2. этот документ
3. `docker-compose.yml`
4. `.github/workflows/ci.yml`
5. `k8s/`
6. `helm/ai-incident-copilot/`
7. `alembic/env.py`

Так быстрее складывается полная operational-картина проекта.

Для operational-действий после деплоя также полезно открыть `docs/runbook.md`.
