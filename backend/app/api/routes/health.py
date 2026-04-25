from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.feature_flags import feature_flags
from app.models.job import Job, JobStatus

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    timestamp: str
    features: dict[str, bool]


class MetricsResponse(BaseModel):
    total_jobs: int
    by_status: dict[str, int]


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        timestamp=datetime.now(timezone.utc).isoformat(),
        features=feature_flags.get_all(),
    )


@router.get("/api/metrics", response_model=MetricsResponse)
async def metrics(db: AsyncSession = Depends(get_db)) -> MetricsResponse:
    total_result = await db.execute(select(func.count(Job.id)))
    total = total_result.scalar_one()

    by_status: dict[str, int] = {}
    for s in JobStatus:
        count_result = await db.execute(
            select(func.count(Job.id)).where(Job.status == s)
        )
        by_status[s.value] = count_result.scalar_one()

    return MetricsResponse(total_jobs=total, by_status=by_status)
