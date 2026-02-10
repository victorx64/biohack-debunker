from __future__ import annotations

import os
from dataclasses import dataclass


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    app_env: str = os.getenv("APP_ENV", "development")
    app_debug: bool = _env_bool("APP_DEBUG", True)

    database_url: str | None = os.getenv("DATABASE_URL")
    postgres_host: str = os.getenv("POSTGRES_HOST", "postgres")
    postgres_port: int = _env_int("POSTGRES_PORT", 5432)
    postgres_db: str = os.getenv("POSTGRES_DB", "biohack_debunker")
    postgres_user: str = os.getenv("POSTGRES_USER", "app")
    postgres_password: str = os.getenv("POSTGRES_PASSWORD", "secure-password")

    redis_url: str = os.getenv("REDIS_URL", "redis://redis:6379/0")

    transcription_service_url: str = os.getenv(
        "TRANSCRIPTION_SERVICE_URL", "http://transcription-service:8001"
    )
    analysis_service_url: str = os.getenv(
        "ANALYSIS_SERVICE_URL", "http://analysis-service:8002"
    )

    rate_limit_requests: int = _env_int("RATE_LIMIT_REQUESTS", 120)
    rate_limit_window: int = _env_int("RATE_LIMIT_WINDOW", 60)

    transcription_read_timeout: int = _env_int("TRANSCRIPTION_READ_TIMEOUT", 120)
    analysis_read_timeout: int = _env_int("ANALYSIS_READ_TIMEOUT", 600)

    enable_public_feed: bool = _env_bool("ENABLE_PUBLIC_FEED", True)
    enable_billing: bool = _env_bool("ENABLE_BILLING", False)
    free_tier_credits: int = _env_int("FREE_TIER_CREDITS", 3)

    @property
    def database_dsn(self) -> str:
        if self.database_url:
            return self.database_url
        return (
            "postgresql://{user}:{password}@{host}:{port}/{db}".format(
                user=self.postgres_user,
                password=self.postgres_password,
                host=self.postgres_host,
                port=self.postgres_port,
                db=self.postgres_db,
            )
        )
