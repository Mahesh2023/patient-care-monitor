"""Configuration via environment variables (pydantic-settings)."""
from __future__ import annotations
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Paths
    project_root: Path = Field(default_factory=lambda: Path(__file__).resolve().parents[2])
    data_dir: Path = Field(default_factory=lambda: Path(__file__).resolve().parents[2] / "data")
    model_dir: Path = Field(default_factory=lambda: Path(__file__).resolve().parents[2] / "models")
    log_dir: Path = Field(default_factory=lambda: Path(__file__).resolve().parents[2] / "logs")

    # LLM
    llm_provider: Literal["groq", "ollama", "none"] = "groq"
    llm_model: str = "llama-3.3-70b-versatile"
    groq_api_key: str = ""
    ollama_host: str = "http://localhost:11434"
    enable_llm_reasoning: bool = True
    llm_cooldown_seconds: float = 3.0

    # Pipeline
    target_fps: int = 10
    max_fps_per_session: int = 15
    session_timeout_seconds: int = 300
    websocket_receive_timeout: int = 30

    # Alerting
    pspi_mild_threshold: float = 1.5
    pspi_moderate_threshold: float = 4.0
    pspi_severe_threshold: float = 8.0
    alert_cooldown_seconds: float = 30.0
    alert_consecutive_frames: int = 5

    # rPPG
    rppg_fps: float = 30.0
    rppg_buffer_frames: int = 300
    rppg_bandpass_low_hz: float = 0.7
    rppg_bandpass_high_hz: float = 4.0

    # Privacy
    consent_ttl_hours: int = 24
    store_raw_frames: bool = False

    # Observability
    log_level: str = "INFO"
    enable_prometheus: bool = True

    def ensure_dirs(self) -> None:
        for p in (self.data_dir, self.model_dir, self.log_dir):
            p.mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.ensure_dirs()
