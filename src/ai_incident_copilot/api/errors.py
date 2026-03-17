"""Обработчики ошибок API."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import ORJSONResponse
from structlog.stdlib import BoundLogger

from ai_incident_copilot.api.schemas.common import ErrorEnvelope, ErrorInfo
from ai_incident_copilot.core.logging import get_logger, get_request_id


class ApplicationError(Exception):
    """Прикладная ошибка с управляемым HTTP-ответом."""

    def __init__(
        self,
        message: str,
        *,
        error_code: str,
        status_code: int,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.status_code = status_code
        self.details = details or {}


def register_exception_handlers(app: FastAPI) -> None:
    """Регистрирует глобальные обработчики исключений."""

    logger = get_logger(__name__)

    @app.exception_handler(ApplicationError)
    async def handle_application_error(
        request: Request,
        exc: ApplicationError,
    ) -> ORJSONResponse:
        _log_failure(
            logger,
            request=request,
            message="Прикладная ошибка",
            error_code=exc.error_code,
            status_code=exc.status_code,
            details=exc.details,
        )
        return _build_error_response(
            message=exc.message,
            error_code=exc.error_code,
            status_code=exc.status_code,
            details=exc.details,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request,
        exc: RequestValidationError,
    ) -> ORJSONResponse:
        details = {"errors": exc.errors()}
        _log_failure(
            logger,
            request=request,
            message="Ошибка валидации запроса",
            error_code="validation_error",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details=details,
        )
        return _build_error_response(
            message="Запрос не прошёл валидацию",
            error_code="validation_error",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details=details,
        )

    @app.exception_handler(HTTPException)
    async def handle_http_exception(
        request: Request,
        exc: HTTPException,
    ) -> ORJSONResponse:
        details = exc.detail if isinstance(exc.detail, dict) else {"detail": exc.detail}
        _log_failure(
            logger,
            request=request,
            message="HTTP ошибка",
            error_code="http_error",
            status_code=exc.status_code,
            details=details,
        )
        return _build_error_response(
            message="Ошибка обработки запроса",
            error_code="http_error",
            status_code=exc.status_code,
            details=details,
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(
        request: Request,
        exc: Exception,
    ) -> ORJSONResponse:
        _log_failure(
            logger,
            request=request,
            message="Непредвиденная ошибка",
            error_code="internal_error",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            details={},
            exc=exc,
        )
        return _build_error_response(
            message="Внутренняя ошибка сервиса",
            error_code="internal_error",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            details={},
        )


def _build_error_response(
    *,
    message: str,
    error_code: str,
    status_code: int,
    details: dict[str, Any],
) -> ORJSONResponse:
    payload = ErrorEnvelope(
        error=ErrorInfo(
            code=error_code,
            message=message,
            request_id=get_request_id(),
            details=details,
        )
    )
    return ORJSONResponse(status_code=status_code, content=payload.model_dump(mode="json"))


def _log_failure(
    logger: BoundLogger,
    *,
    request: Request,
    message: str,
    error_code: str,
    status_code: int,
    details: dict[str, Any],
    exc: Exception | None = None,
) -> None:
    log = logger.bind(
        path=request.url.path,
        method=request.method,
        error_code=error_code,
        status_code=status_code,
        details=details,
    )
    if exc is None:
        log.warning(message)
    else:
        log.exception(message, exc_info=exc)
