"""Настройка структурированного логирования.

Логирование в проекте задумано как единый источник операционной правды.
Модуль конфигурирует JSON-логи для:

- нашего приложения
- Uvicorn
- aiokafka

Дополнительно здесь живут helpers для контекста (`request_id`, `incident_id`,
`workflow_run_id` и других связующих полей).
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable, Mapping, MutableMapping
from typing import Any, cast

import orjson
import structlog
from structlog.contextvars import bind_contextvars, clear_contextvars, get_contextvars
from structlog.stdlib import BoundLogger

_LOGGER_CONFIGURED = False
EventDict = MutableMapping[str, Any]
Processor = Callable[
    [Any, str, EventDict],
    Mapping[str, Any] | str | bytes | bytearray | tuple[Any, ...],
]


def configure_logging(level_name: str) -> None:
    """Инициализирует JSON-логирование для приложения и сторонних библиотек.

    Конфигурация выполняется один раз на процесс. Это защищает от ситуации,
    когда тесты или повторный bootstrap навешивают несколько handler'ов и
    начинают дублировать каждую запись в stdout.
    """

    global _LOGGER_CONFIGURED
    if _LOGGER_CONFIGURED:
        return

    level = getattr(logging, level_name.upper(), logging.INFO)
    # Эти processors применяются и к нашим логам, и к логам сторонних
    # библиотек, чтобы выход был единообразным по формату и ключам.
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True, key="timestamp"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            cast(Processor, structlog.stdlib.ProcessorFormatter.remove_processors_meta),
            structlog.processors.JSONRenderer(serializer=_json_dumps),
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(level)

    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access", "aiokafka"):
        third_party_logger = logging.getLogger(logger_name)
        third_party_logger.handlers.clear()
        third_party_logger.addHandler(handler)
        third_party_logger.setLevel(level)
        third_party_logger.propagate = False

    structlog.configure(
        processors=[
            *shared_processors,
            cast(Processor, structlog.stdlib.ProcessorFormatter.wrap_for_formatter),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=BoundLogger,
        cache_logger_on_first_use=True,
    )

    _LOGGER_CONFIGURED = True


def get_logger(name: str) -> BoundLogger:
    """Возвращает именованный logger."""

    return cast(BoundLogger, structlog.get_logger(name))


def bind_logging_context(**kwargs: Any) -> None:
    """Привязывает ключи к текущему logging context.

    Используется, чтобы в логах автоматически появлялись корреляционные поля
    вроде `request_id`, `incident_id` и `event_id` без ручной прокладки в
    каждый `logger.info(...)`.
    """

    cleaned = {key: value for key, value in kwargs.items() if value is not None}
    if cleaned:
        bind_contextvars(**cleaned)


def clear_logging_context() -> None:
    """Очищает текущий logging context."""

    clear_contextvars()


def get_request_id() -> str | None:
    """Возвращает request_id из текущего контекста, если он задан."""

    context = get_contextvars()
    request_id = context.get("request_id")
    return str(request_id) if request_id is not None else None


def _json_dumps(value: Any, **_: Any) -> str:
    """Сериализует структуру лога в JSON через быстрый `orjson`."""

    return orjson.dumps(value).decode("utf-8")
