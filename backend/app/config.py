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
    # When True, preserve the temp work directory for failed jobs (useful for debugging).
    DEBUG_KEEP_FAILED_WORKDIR: bool = False

    # OpenAI / LLM
    OPENAI_API_KEY: str | None = None
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"

    # TTS
    EDGE_TTS_ENABLED: bool = False
    ELEVENLABS_API_KEY: str | None = None
    OPENAI_TTS_MODEL: str = "tts-1"
    COQUI_TTS_ENABLED: bool = False
    COQUI_TTS_URL: str = "http://coqui-tts:5002"

    # Stock media
    PEXELS_API_KEY: str | None = None
    PIXABAY_API_KEY: str | None = None
    # Maximum parallel workers for stock-media downloads and clip preparation.
    PIPELINE_MAX_WORKERS: int = 4

    # AI image generation
    # MEDIA_MODE controls which media sources are used:
    #   "stock"  – use Pexels/local only (default)
    #   "ai"     – use AI image providers only
    #   "hybrid" – try stock first, fall back to AI
    MEDIA_MODE: str = "stock"
    OPENAI_IMAGE_MODEL: str = "gpt-image-1"
    STABILITY_AI_API_KEY: str | None = None
    STABILITY_AI_MODEL: str = "stable-diffusion-xl-1024-v1-0"

    # Provider-agnostic AI image generation (new timeline-aware path).
    # Set AI_IMAGE_ENABLED=true together with MEDIA_MODE=ai to activate the
    # script-scene-image-timeline pipeline.  Defaults to False so that
    # existing MEDIA_MODE=ai deployments continue using StockMediaSelector.
    AI_IMAGE_PROVIDER: str = "openai"       # openai | stability | local_mock
    AI_IMAGE_ASPECT_RATIO: str = "9:16"
    AI_IMAGE_ENABLED: bool = False
    # Negative prompt suffix appended to every AI image prompt to suppress
    # text, captions, and UI elements from appearing in generated images.
    AI_IMAGE_NEGATIVE_PROMPT: str = (
        "No text, no captions, no subtitles, no typography, no logos, "
        "no signs, no labels, no speech bubbles."
    )
    # When True, use the shot-plan system to produce visually varied prompts
    # across blocks (different framing, composition, and shot type per block).
    # Defaults to True for AI image mode.
    VISUAL_SHOT_PLAN_ENABLED: bool = True

    # Script-to-scene planner (used when AI_IMAGE_ENABLED=true).
    VISUAL_SCENE_MIN_SECONDS: float = 5.0
    VISUAL_SCENE_MAX_SECONDS: float = 8.0

    # Minimum visual block duration in seconds.  Narration blocks whose text
    # is too short to fill this duration are merged into the previous block
    # during planning so that no expensive image slot is wasted on a brief
    # outro phrase like "Happy Groundhog Day, everyone!".
    MIN_VISUAL_BLOCK_SECONDS: float = 3.0

    # Optional LLM-based visual prompt planner.
    # When AI_VISUAL_PLANNER_ENABLED=True and AI_VISUAL_PLANNER_PROVIDER=openai,
    # a single lightweight LLM call generates context-aware visual briefs for all
    # narration blocks before image generation begins.  This is NOT image
    # generation – it only produces better image prompts.
    # Default: False for backward compatibility.
    AI_VISUAL_PLANNER_ENABLED: bool = False
    # "openai" | "none"
    AI_VISUAL_PLANNER_PROVIDER: str = "openai"

    # ---------------------------------------------------------------------------
    # Storyboard planning layer
    # ---------------------------------------------------------------------------
    # When STORYBOARD_PLANNER_ENABLED=True the pipeline uses a storyboard
    # layer as the single source of truth for visual generation in AI mode:
    #   narration blocks → storyboard scenes → image prompts → AI images
    #
    # When False the previous prompt_builder path is preserved unchanged.
    # Default: False for backward compatibility.  Set True to activate.
    STORYBOARD_PLANNER_ENABLED: bool = False

    # LLM provider used to generate the storyboard.
    # "openai" uses gpt-4o-mini (or STORYBOARD_MODEL if set).
    # "none"   disables the LLM call and uses the deterministic fallback only.
    STORYBOARD_PLANNER_PROVIDER: str = "openai"

    # Model used for storyboard generation (must be a fast, cheap text model).
    # Defaults to gpt-4o-mini which is the same model used by AI_VISUAL_PLANNER.
    STORYBOARD_MODEL: str = "gpt-4o-mini"

    # Minimum block duration (seconds) below which a block is merged into the
    # previous storyboard scene rather than receiving its own image slot.
    STORYBOARD_MIN_BLOCK_SECONDS: float = 3.0

    # Enable in-memory storyboard caching within a single pipeline run.
    # This prevents redundant LLM calls when the same script+tags are processed
    # multiple times (e.g. retries).
    STORYBOARD_CACHE_ENABLED: bool = True

    # ---------------------------------------------------------------------------
    # Storyboard quality scoring and auto-rewrite
    # ---------------------------------------------------------------------------
    # When STORYBOARD_QUALITY_ENABLED=True each storyboard scene is scored
    # (0-100) after planning.  Scenes below STORYBOARD_QUALITY_THRESHOLD or
    # detected as generic are rewritten via LLM before image generation.
    # Default: False for backward compatibility.
    STORYBOARD_QUALITY_ENABLED: bool = False

    # Minimum acceptable scene quality score (0-100).  Scenes below this value
    # are rewritten.  60 is recommended; lower values reduce LLM calls at the
    # cost of accepting weaker descriptions.
    STORYBOARD_QUALITY_THRESHOLD: int = 60

    # Maximum rewrite attempts per scene before accepting the best version seen.
    STORYBOARD_QUALITY_MAX_RETRIES: int = 2

    # ---------------------------------------------------------------------------
    # Multi-image generation and selection
    # ---------------------------------------------------------------------------
    # When AI_IMAGE_VARIATIONS > 1, the pipeline generates that many candidate
    # images per scene and automatically picks the best one.
    # Keeping N ≤ 3 avoids excessive API cost and latency.
    # Default: 1 (no multi-generation, preserves original behaviour).
    AI_IMAGE_VARIATIONS: int = 1

    # Strategy for picking the best image when AI_IMAGE_VARIATIONS > 1.
    # "score"  — use score_image() heuristic (file size, dimensions, …).
    # "random" — pick a random candidate.
    AI_IMAGE_PICK_STRATEGY: str = "score"

    # When True, discarded image variants are kept on disk for debugging.
    # When False (default), they are removed after the best one is selected.
    AI_IMAGE_KEEP_VARIATIONS: bool = False

    # Cloud storage (S3-compatible)
    S3_ENDPOINT_URL: str | None = None
    S3_ACCESS_KEY: str | None = None
    S3_SECRET_KEY: str | None = None
    S3_BUCKET: str | None = None

    # Caption / Transcription
    WHISPER_ENABLED: bool = True
    WHISPER_MODEL_SIZE: str = "base"
    WHISPER_DEVICE: str = "cpu"

    # CORS
    # Space-separated or JSON-array list of allowed origins.
    # Production default: only the deployed frontend.
    # Development: override via .env, e.g.
    #   CORS_ALLOWED_ORIGINS=["https://avpk.prodit.rs","http://localhost:3000","http://localhost:8000"]
    CORS_ALLOWED_ORIGINS: list[str] = ["https://avpk.prodit.rs"]

    # GPU
    NVIDIA_NVENC_ENABLED: bool = False
    FEATURE_FLAGS: dict[str, Any] = {
        "core_video": True,
        "ai_scripts": True,
        "trends": True,
        "tts": True,
        "captions": True,
        "stock_media": True,
        "n8n": True,
        "social_uploaders": False,
        "gpu_rendering": False,
        "cloud_storage": False,
    }

    @field_validator("CORS_ALLOWED_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            import json
            return json.loads(v)
        return v

    @field_validator("FEATURE_FLAGS", mode="before")
    @classmethod
    def parse_feature_flags(cls, v: Any) -> dict[str, Any]:
        if isinstance(v, str):
            import json
            return json.loads(v)
        return v


settings = Settings()
