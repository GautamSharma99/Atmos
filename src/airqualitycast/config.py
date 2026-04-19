"""Application configuration loaded from environment variables."""
from __future__ import annotations

import logging

import structlog
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    postgres_db: str = "airquality"
    postgres_user: str = "aq_user"
    postgres_password: SecretStr = SecretStr("CHANGE_ME")
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    # API keys
    aqicn_token: SecretStr = SecretStr("")
    openaq_api_key: SecretStr = SecretStr("")
    firms_map_key: SecretStr = SecretStr("")

    # Operational
    log_level: str = Field(default="INFO")
    environment: str = Field(default="dev")

    @property
    def db_dsn(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password.get_secret_value()}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def configure_logging(level: str | None = None) -> None:
    """Configure structlog for JSON output."""
    log_level = (level or get_settings().log_level).upper()
    logging.basicConfig(format="%(message)s", level=log_level)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, log_level)),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
