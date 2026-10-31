"""Configuration via environment variables (pydantic-settings).

Every value has a safe local-dev default; production values come from the
Render Blueprint (`render.yaml`). `validate_for_production` fails fast on
mis-configuration instead of silently running insecurely.
"""
from __future__ import annotations

import secrets
from functools import cached_property
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # App
    environment: Literal["development", "production", "test"] = "development"
    app_version: str = "3.0.0"
    public_base_url: str = ""  # e.g. https://care-mm.onrender.com (informational)

    # Data stores
    database_url: str = "sqlite+aiosqlite:///./care_mm.db"
    db_pool_size: int = 5
    db_max_overflow: int = 5
    redis_url: str = ""  # empty => in-process fallbacks (single instance only)

    # Auth
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    jwt_access_ttl_minutes: int = 15
    jwt_refresh_ttl_days: int = 30
    ws_ticket_ttl_seconds: int = 60
    cookie_secure: bool = True
    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)

    # Rate limits (per client IP / user, fixed 60 s window)
    auth_rate_per_minute: int = 10
    api_rate_per_minute: int = 240

    # LLM
    llm_provider: Literal["groq", "ollama", "none"] = "groq"
    llm_model: str = "llama-3.3-70b-versatile"
    groq_api_key: str = ""
    groq_base_url: str = "https://api.groq.com/openai/v1"
    ollama_host: str = "http://localhost:11434"
    enable_llm_reasoning: bool = True
    llm_cooldown_seconds: float = 30.0
    llm_timeout_seconds: float = 8.0
    llm_max_concurrency: int = 4  # per worker process

    # Streaming pipeline
    target_fps: int = 10
    max_samples_per_batch: int = 40
    max_batches_per_second: float = 6.0
    max_ws_message_bytes: int = 64 * 1024
    websocket_receive_timeout: int = 60
    max_active_streams_per_user: int = 5

    # Alerting
    pspi_mild_threshold: float = 1.5
    pspi_moderate_threshold: float = 4.0
    pspi_severe_threshold: float = 8.0
    alert_cooldown_seconds: float = 30.0
    alert_consecutive_frames: int = 5

    # rPPG
    rppg_resample_hz: float = 15.0
    rppg_window_seconds: float = 20.0
    rppg_bandpass_low_hz: float = 0.7
    rppg_bandpass_high_hz: float = 4.0

    # Privacy / retention
    consent_ttl_hours: int = 24
    metrics_retention_days: int = 30
    alerts_retention_days: int = 365
    rollup_interval_seconds: int = 60
    maintenance_interval_seconds: int = 3600

    # Observability
    log_level: str = "INFO"
    log_json: bool = False
    enable_prometheus: bool = True
    metrics_token: str = ""

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_csv(cls, v):
        if isinstance(v, str):
            return [s.strip() for s in v.split(",") if s.strip()]
        return v

    @field_validator("database_url")
    @classmethod
    def _async_driver(cls, v: str) -> str:
        # Render/Heroku style URLs -> SQLAlchemy asyncpg driver.
        for prefix in ("postgres://", "postgresql://"):
            if v.startswith(prefix):
                v = "postgresql+asyncpg://" + v[len(prefix):]
        # asyncpg understands `ssl=`, not libpq's `sslmode=`.
        return v.replace("sslmode=", "ssl=") if v.startswith("postgresql+asyncpg://") else v

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @cached_property
    def effective_jwt_secret(self) -> str:
        # Dev/test only: ephemeral secret (tokens die on restart).
        return self.jwt_secret or secrets.token_urlsafe(48)

    def validate_for_production(self) -> list[str]:
        problems = []
        if not self.is_production:
            return problems
        if len(self.jwt_secret) < 32:
            problems.append("JWT_SECRET must be set (>= 32 chars) in production")
        if self.is_sqlite:
            problems.append("DATABASE_URL must point to Postgres in production")
        if not self.cookie_secure:
            problems.append("COOKIE_SECURE must be true in production")
        if "*" in self.cors_origins:
            problems.append("CORS_ORIGINS must not contain '*' in production")
        return problems


settings = Settings()
