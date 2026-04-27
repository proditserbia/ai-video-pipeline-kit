from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import get_current_user
from app.models.user import User

router = APIRouter(prefix="/settings", tags=["settings"])

# ---------------------------------------------------------------------------
# Response models for /settings/status
# ---------------------------------------------------------------------------

class MediaSettings(BaseModel):
    media_mode: str
    ai_image_enabled: bool
    ai_image_provider: str
    ai_image_aspect_ratio: str
    paragraph_tts_sync_enabled: bool
    visual_shot_plan_enabled: bool


class ScriptSettings(BaseModel):
    ai_script_enabled: bool
    provider: str


class TTSSettings(BaseModel):
    active_provider: str
    openai_tts_available: bool
    edge_tts_available: bool
    coqui_available: bool
    elevenlabs_available: bool
    default_voice: str | None


class CaptionSettings(BaseModel):
    model_config = {"protected_namespaces": ()}

    whisper_enabled: bool
    model_size: str
    available_styles: list[str]


class ProviderStatus(BaseModel):
    openai_api_key_present: bool
    pexels_api_key_present: bool
    pixabay_api_key_present: bool
    stability_api_key_present: bool
    elevenlabs_api_key_present: bool


class JobsSettings(BaseModel):
    max_retries: int
    dry_run: bool
    default_ordering: str


class AppSettingsStatus(BaseModel):
    app_name: str
    environment: str
    storage_path: str
    media: MediaSettings
    script: ScriptSettings
    tts: TTSSettings
    captions: CaptionSettings
    providers: ProviderStatus
    jobs: JobsSettings
    feature_flags: dict[str, bool]


def _infer_tts_provider(s: Any) -> str:
    """Infer the highest-priority configured TTS provider from settings (no network I/O)."""
    if s.ELEVENLABS_API_KEY:
        return "elevenlabs"
    if s.OPENAI_API_KEY:
        return "openai"
    if s.COQUI_TTS_ENABLED:
        return "coqui"
    if s.EDGE_TTS_ENABLED:
        return "edge"
    return "none"


def _infer_tts_default_voice(provider: str) -> str | None:
    if provider == "openai":
        return "alloy"
    if provider == "edge":
        return "en-US-JennyNeural"
    return None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/status", response_model=AppSettingsStatus, dependencies=[Depends(get_current_user)])
async def get_settings_status() -> AppSettingsStatus:
    """
    Return safe, read-only application configuration status.

    Never exposes actual API key values – only boolean ``key_present`` flags.
    """
    from app.config import settings
    from app.core.feature_flags import feature_flags
    from app.schemas.job import VALID_CAPTION_STYLES

    active_provider = _infer_tts_provider(settings)
    ai_scripts_enabled = (
        bool(settings.OPENAI_API_KEY)
        and feature_flags.is_enabled("ai_scripts")
    )

    return AppSettingsStatus(
        app_name="AI Video Pipeline Kit",
        environment="dry-run" if settings.DRY_RUN else "production",
        storage_path=settings.STORAGE_PATH,
        media=MediaSettings(
            media_mode=settings.MEDIA_MODE,
            ai_image_enabled=settings.AI_IMAGE_ENABLED,
            ai_image_provider=settings.AI_IMAGE_PROVIDER,
            ai_image_aspect_ratio=settings.AI_IMAGE_ASPECT_RATIO,
            # Paragraph-level TTS/image sync is active when the AI image pipeline is on.
            paragraph_tts_sync_enabled=settings.AI_IMAGE_ENABLED,
            visual_shot_plan_enabled=settings.VISUAL_SHOT_PLAN_ENABLED,
        ),
        script=ScriptSettings(
            ai_script_enabled=ai_scripts_enabled,
            provider="openai" if bool(settings.OPENAI_API_KEY) else "placeholder",
        ),
        tts=TTSSettings(
            active_provider=active_provider,
            openai_tts_available=bool(settings.OPENAI_API_KEY),
            edge_tts_available=settings.EDGE_TTS_ENABLED,
            coqui_available=settings.COQUI_TTS_ENABLED,
            elevenlabs_available=bool(settings.ELEVENLABS_API_KEY),
            default_voice=_infer_tts_default_voice(active_provider),
        ),
        captions=CaptionSettings(
            whisper_enabled=settings.WHISPER_ENABLED,
            model_size=settings.WHISPER_MODEL_SIZE,
            available_styles=sorted(VALID_CAPTION_STYLES),
        ),
        providers=ProviderStatus(
            openai_api_key_present=bool(settings.OPENAI_API_KEY),
            pexels_api_key_present=bool(settings.PEXELS_API_KEY),
            pixabay_api_key_present=bool(settings.PIXABAY_API_KEY),
            stability_api_key_present=bool(settings.STABILITY_AI_API_KEY),
            elevenlabs_api_key_present=bool(settings.ELEVENLABS_API_KEY),
        ),
        jobs=JobsSettings(
            max_retries=settings.MAX_JOB_RETRIES,
            dry_run=settings.DRY_RUN,
            default_ordering="newest_first",
        ),
        feature_flags=feature_flags.get_all(),
    )


@router.get("", dependencies=[Depends(get_current_user)])
async def get_settings() -> dict[str, Any]:
    from app.config import settings
    from app.core.feature_flags import feature_flags

    return {
        "feature_flags": feature_flags.get_all(),
        "storage_path": settings.STORAGE_PATH,
        "max_job_retries": settings.MAX_JOB_RETRIES,
        "dry_run": settings.DRY_RUN,
    }


@router.get("/features", dependencies=[Depends(get_current_user)])
async def get_features() -> dict[str, bool]:
    """Return the current feature-flag state."""
    from app.core.feature_flags import feature_flags

    return feature_flags.get_all()


@router.get("/credentials", dependencies=[Depends(get_current_user)])
async def get_credentials() -> dict[str, bool]:
    """Return which external API credentials are configured."""
    from app.config import settings

    return {
        "openai": bool(settings.OPENAI_API_KEY),
        "edge_tts": settings.EDGE_TTS_ENABLED,
        "pexels": bool(settings.PEXELS_API_KEY),
        "pixabay": bool(settings.PIXABAY_API_KEY),
    }
