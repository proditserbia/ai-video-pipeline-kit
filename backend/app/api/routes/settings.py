from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import get_current_user
from app.models.user import User

router = APIRouter(prefix="/settings", tags=["settings"])


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
        "youtube": bool(settings.YOUTUBE_CLIENT_SECRETS_FILE),
    }
