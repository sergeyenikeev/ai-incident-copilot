"""Middleware FastAPI.

Здесь живёт middleware, который создаёт request-scoped logging context и
оборачивает каждый HTTP-запрос в базовый access log.
"""

from __future__ import annotations

from time import perf_counter
from uuid import uuid4

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from ai_incident_copilot.core.logging import (
    bind_logging_context,
    clear_logging_context,
    get_logger,
)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Пробрасывает request_id и пишет структурированные логи по каждому запросу.

    Это важный слой наблюдаемости: благодаря нему все нижележащие логи смогут
    автоматически включать `request_id`, а клиент получит тот же идентификатор
    в ответном заголовке `X-Request-ID`.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        logger = get_logger(__name__)
        request_id = request.headers.get("X-Request-ID", str(uuid4()))
        # Контекст очищается в начале запроса, чтобы в новый запрос случайно
        # не протекли correlation-поля от предыдущей операции.
        clear_logging_context()
        bind_logging_context(
            request_id=request_id,
            http_method=request.method,
            http_path=request.url.path,
        )

        started_at = perf_counter()
        logger.info("Получен HTTP-запрос")

        try:
            response = await call_next(request)
            duration_ms = round((perf_counter() - started_at) * 1000, 2)
            response.headers["X-Request-ID"] = request_id
            # Ответ логируется уже после получения status code и измерения
            # полной длительности запроса, что удобно для SLI/SLO-анализа.
            logger.info(
                "HTTP-запрос обработан",
                status_code=response.status_code,
                duration_ms=duration_ms,
            )
            return response
        finally:
            clear_logging_context()
