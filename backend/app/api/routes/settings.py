from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.api.deps import check_feature, get_current_user
from app.models.user import User

router = APIRouter(prefix="/api/settings", tags=["settings"])


class FeatureFlagUpdate(BaseModel):
    flags: dict[str, bool]


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
