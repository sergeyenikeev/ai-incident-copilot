"""Конфигурация приложения."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Глобальные настройки, загружаемые из переменных окружения."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
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

    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_consumer_group: str = "ai-incident-worker"
    kafka_topic_incident_created: str = "incident.created"
    kafka_topic_analysis_requested: str = "incident.analysis.requested"
    kafka_topic_analysis_completed: str = "incident.analysis.completed"
    kafka_max_retries: int = 3

    @property
    def database_url_async(self) -> str:
        """Возвращает DSN для асинхронного подключения к PostgreSQL."""

        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def database_url_sync(self) -> str:
        """Возвращает DSN для синхронного подключения Alembic."""

        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Возвращает кэшированный экземпляр настроек."""

    return Settings()
