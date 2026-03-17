"""Конфигурация приложения."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Глобальные настройки, загружаемые из переменных окружения."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    app_name: str = "ai-incident-copilot"
    app_version: str = "0.1.0"
    app_env: str = "local"
    app_debug: bool = False
    app_host: str = "0.0.0.0"
    app_port: int = 8080
    app_log_level: str = "INFO"
    api_prefix: str = "/api/v1"

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "ai_incident_copilot"
    postgres_user: str = "incident"
    postgres_password: str = "incident"
    database_url_async_override: str | None = Field(default=None, validation_alias="DATABASE_URL_ASYNC")
    database_url_sync_override: str | None = Field(default=None, validation_alias="DATABASE_URL_SYNC")

    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_consumer_group: str = "ai-incident-worker"
    kafka_enabled: bool = True
    kafka_fail_fast: bool = False
    kafka_client_id: str = "ai-incident-api"
    kafka_request_timeout_ms: int = 10_000
    kafka_topic_incident_created: str = "incident.created"
    kafka_topic_analysis_requested: str = "incident.analysis.requested"
    kafka_topic_analysis_completed: str = "incident.analysis.completed"
    kafka_max_retries: int = 3
    worker_poll_timeout_ms: int = 1_000
    worker_retry_backoff_seconds: float = 1.5

    @property
    def database_url_async(self) -> str:
        """Возвращает DSN для асинхронного подключения к PostgreSQL."""

        if self.database_url_async_override:
            return self.database_url_async_override
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def database_url_sync(self) -> str:
        """Возвращает DSN для синхронного подключения Alembic."""

        if self.database_url_sync_override:
            return self.database_url_sync_override
        if self.database_url_async_override:
            return (
                self.database_url_async_override.replace("+asyncpg", "+psycopg")
                .replace("+aiosqlite", "")
            )
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Возвращает кэшированный экземпляр настроек."""

    return Settings()
