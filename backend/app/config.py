from __future__ import annotations

from typing import Any
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/videofactory"
    SYNC_DATABASE_URL: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/videofactory"

    # Redis / Celery
    REDIS_URL: str = "redis://localhost:6379/0"

    # Security
    SECRET_KEY: str = "changeme-secret-key-at-least-32-chars-long"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    ALGORITHM: str = "HS256"

    # Admin seed
    ADMIN_EMAIL: str = "admin@example.com"
    ADMIN_PASSWORD: str = "changeme"

    # Storage
    STORAGE_PATH: str = "/storage"

    # Job settings
    MAX_JOB_RETRIES: int = 3
    DRY_RUN: bool = False

    # OpenAI / LLM
    OPENAI_API_KEY: str | None = None
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    ANTHROPIC_API_KEY: str | None = None

    # TTS
    EDGE_TTS_ENABLED: bool = False
    ELEVENLABS_API_KEY: str | None = None
    OPENAI_TTS_MODEL: str = "tts-1"
    COQUI_TTS_ENABLED: bool = False
    COQUI_TTS_URL: str = "http://coqui-tts:5002"

    # Stock media
    PEXELS_API_KEY: str | None = None
    PIXABAY_API_KEY: str | None = None

    # YouTube
    YOUTUBE_CLIENT_SECRETS_FILE: str | None = None

    # Cloud storage (S3-compatible)
    S3_ENDPOINT_URL: str | None = None
    S3_ACCESS_KEY: str | None = None
    S3_SECRET_KEY: str | None = None
    S3_BUCKET: str | None = None

    # GPU
    NVIDIA_NVENC_ENABLED: bool = False

    # Feature flags (JSON string or dict)
    FEATURE_FLAGS: dict[str, Any] = {
        "core_video": True,
        "ai_scripts": True,
        "trends": True,
        "tts": True,
        "captions": True,
        "stock_media": True,
        "n8n": True,
        "youtube_upload": False,
        "social_uploaders": False,
        "gpu_rendering": False,
        "cloud_storage": False,
    }

    @field_validator("FEATURE_FLAGS", mode="before")
    @classmethod
    def parse_feature_flags(cls, v: Any) -> dict[str, Any]:
        if isinstance(v, str):
            import json
            return json.loads(v)
        return v


settings = Settings()
