"""Временная точка входа worker-сервиса."""

from __future__ import annotations

from ai_incident_copilot.core.config import get_settings
from ai_incident_copilot.core.logging import configure_logging, get_logger


def main() -> None:
    """Логирует запуск заготовки worker-процесса."""

    settings = get_settings()
    configure_logging(settings.app_log_level)
    logger = get_logger(__name__)
    logger.warning("Worker-сервис пока не реализован")


if __name__ == "__main__":
    main()
