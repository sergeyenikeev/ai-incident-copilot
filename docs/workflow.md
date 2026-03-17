# Workflow

## Назначение

LangGraph workflow отвечает за анализ инцидента после получения события `incident.analysis.requested`.

Цель:

- классифицировать инцидент
- вычислить критичность
- выбрать ветку реакции
- сформировать практическую рекомендацию
- сохранить историю выполнения по шагам

## Типизированное состояние

Workflow использует `IncidentWorkflowState`.

Ключевые поля:

- `incident_id`
- `workflow_run_id`
- `title`
- `description`
- `source`
- `metadata`
- `classification`
- `severity`
- `priority_score`
- `recommendation`
- `route`

## Узлы графа

### 1. `classify_incident`

Определяет категорию инцидента.

Текущие классы:

- `security`
- `data`
- `network`
- `infrastructure`
- `application`

### 2. `determine_severity`

Вычисляет:

- `severity`
- `priority_score`
- `route`

Severity:

- `low`
- `medium`
- `high`
- `critical`

### 3. Decision node

На основе classification и severity выбирает:

- `standard`
- `escalated`

### 4. `generate_standard_recommendation`

Формирует обычную рекомендацию для стандартного сценария.

### 5. `generate_escalated_recommendation`

Формирует усиленную рекомендацию для тяжёлого или security-кейса.

## Правила ветвления

### Standard

Используется, когда:

- классификация не `security`
- severity не `critical`

### Escalated

Используется, когда:

- классификация `security`
- или severity = `critical`

## Persistence model

### workflow_runs

На каждый запуск создаётся запись:

- `incident_id`
- `trigger_event_id`
- `workflow_name`
- `status`
- `input_payload`
- `output_payload`

### workflow_steps

На каждый node execution создаётся шаг:

- `node_name`
- `status`
- `input_payload`
- `output_payload`
- `error_message`

Это позволяет:

- восстанавливать историю анализа
- диагностировать падения
- строить аудит и операционные отчёты

## Жизненный цикл анализа

1. worker получает `incident.analysis.requested`
2. инцидент переводится в `analyzing`
3. создаётся `workflow_run`
4. выполняются шаги графа
5. результаты записываются в `incidents`
6. инцидент переводится в `analyzed`
7. публикуется `incident.analysis.completed`

Если шаг падает:

1. шаг получает `failed`
2. `workflow_run` получает `failed`
3. инцидент получает `failed`
4. worker фиксирует retry/ошибку в `incident_events`

## Эвристики текущей версии

Rule-based анализатор смотрит на:

- ключевые слова в заголовке
- ключевые слова в описании
- метаданные инцидента
- маркеры production / outage / security

Примеры:

- `SIEM`, `несанкционирован`, `unauthorized` -> `security`
- `postgres`, `replication`, `backup` -> `data`
- `502`, `timeout`, `queue`, `kubernetes` -> `infrastructure`

## Как расширить workflow LLM-моделью

Текущая реализация специально разделена на:

- state model
- analyzer
- orchestration service

Чтобы заменить rule-based анализ на LLM:

1. создать новый analyzer-класс
2. заменить реализацию `classify`, `determine_severity`, `choose_route`, `recommendation`
3. оставить прежний контракт workflow state
4. не менять storage-модель `workflow_runs` / `workflow_steps`

Это позволит перейти к LLM без переделки API, worker и репозиториев.

## Эксплуатационные детали

- workflow логирует каждый шаг
- worker пробрасывает `incident_id` и `event_id` в logging context
- `workflow_run_id` сохраняется в БД и логах
- worker готов к повторной обработке сообщений без дублирования финального результата
