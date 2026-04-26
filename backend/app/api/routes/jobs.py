from __future__ import annotations

import uuid
from pathlib import Path
from typing import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.job import Job, JobStatus
from app.models.user import User
from app.schemas.job import JobCreate, JobListResponse, JobResponse, JobStats

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/stats", response_model=JobStats)
async def job_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> JobStats:
    """Return aggregate job counts for the dashboard stats cards."""
    counts: dict[str, int] = {}
    for s in JobStatus:
        result = await db.execute(
            select(func.count(Job.id)).where(
                Job.user_id == current_user.id, Job.status == s
            )
        )
        counts[s.value] = result.scalar_one()
    total = sum(counts.values())
    return JobStats(
        total=total,
        completed=counts.get("completed", 0),
        failed=counts.get("failed", 0),
        processing=counts.get("processing", 0) + counts.get("rendering", 0) + counts.get("uploading", 0),
        pending=counts.get("pending", 0),
    )


@router.get("", response_model=JobListResponse)
async def list_jobs(
    status: JobStatus | None = None,
    project_id: int | None = None,
    page: int = 1,
    size: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> JobListResponse:
    query = select(Job).where(Job.user_id == current_user.id)
    count_query = select(func.count(Job.id)).where(Job.user_id == current_user.id)

    if status:
        query = query.where(Job.status == status)
        count_query = count_query.where(Job.status == status)
    if project_id:
        query = query.where(Job.project_id == project_id)
        count_query = count_query.where(Job.project_id == project_id)

    total = (await db.execute(count_query)).scalar_one()
    jobs_result = await db.execute(query.offset((page - 1) * size).limit(size))
    jobs = jobs_result.scalars().all()

    return JobListResponse(
        items=[JobResponse.model_validate(j) for j in jobs],
        total=total,
        page=page,
        size=size,
        pages=max(1, -(-total // size)),  # ceiling division
    )


@router.post("", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
async def create_job(
    body: JobCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> JobResponse:
    from app.config import settings as app_settings

    # Build input_data from convenience fields when the caller (dashboard form)
    # sends script/topic/voice_name/caption_style instead of a raw input_data blob.
    if body.input_data is None:
        input_data: dict = {
            "script_text": body.script or "",
            "topic": body.topic or "",
            "voice": body.voice_name,
            "caption_style": body.caption_style,
        }
    else:
        input_data = body.input_data

    job = Job(
        id=str(uuid.uuid4()),
        user_id=current_user.id,
        project_id=body.project_id,
        title=body.title,
        job_type=body.job_type,
        input_data=input_data,
        dry_run=body.dry_run,
        max_retries=body.max_retries,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    # Queue Celery task
    try:
        from worker.celery_app import celery_app
        from worker.tasks.video_pipeline import run_video_pipeline

        task = run_video_pipeline.apply_async(args=[job.id])
        job.celery_task_id = task.id
        await db.commit()
        await db.refresh(job)
    except Exception:
        # Worker may not be available in test/dry-run scenarios
        pass

    return JobResponse.model_validate(job)


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> JobResponse:
    job = await _get_job_or_404(job_id, current_user.id, db)
    return JobResponse.model_validate(job)


@router.post("/{job_id}/cancel", response_model=JobResponse)
async def cancel_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> JobResponse:
    job = await _get_job_or_404(job_id, current_user.id, db)

    if job.status in (JobStatus.completed, JobStatus.failed, JobStatus.cancelled):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel job in '{job.status}' state",
        )

    if job.celery_task_id:
        try:
            from worker.celery_app import celery_app

            celery_app.control.revoke(job.celery_task_id, terminate=True)
        except Exception:
            pass

    job.status = JobStatus.cancelled
    await db.commit()
    await db.refresh(job)
    return JobResponse.model_validate(job)


@router.post("/{job_id}/retry", response_model=JobResponse)
async def retry_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> JobResponse:
    job = await _get_job_or_404(job_id, current_user.id, db)

    if job.status != JobStatus.failed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only failed jobs can be retried",
        )

    if job.retry_count >= job.max_retries:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum retries exceeded",
        )

    job.status = JobStatus.pending
    job.retry_count += 1
    job.error_message = None
    await db.commit()
    await db.refresh(job)

    try:
        from worker.tasks.video_pipeline import run_video_pipeline

        task = run_video_pipeline.apply_async(args=[job.id])
        job.celery_task_id = task.id
        await db.commit()
        await db.refresh(job)
    except Exception:
        pass

    return JobResponse.model_validate(job)


@router.get("/{job_id}/logs")
async def stream_logs(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    job = await _get_job_or_404(job_id, current_user.id, db)

    async def log_generator() -> AsyncIterator[str]:
        yield job.logs or ""

    return StreamingResponse(log_generator(), media_type="text/plain")


@router.get("/{job_id}/download")
async def download_job_output(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FileResponse:
    from app.config import settings as app_settings

    job = await _get_job_or_404(job_id, current_user.id, db)

    if not job.output_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No output file available for this job",
        )

    storage_root = Path(app_settings.STORAGE_PATH).resolve()
    file_path = Path(job.output_path).resolve()

    # Ensure the resolved path stays within the configured storage root
    try:
        file_path.relative_to(storage_root)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    if not file_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Output file not found on disk",
        )

    filename = file_path.name or f"{job.title}.mp4"
    return FileResponse(
        path=str(file_path),
        media_type="video/mp4",
        filename=filename,
    )


async def _get_job_or_404(job_id: str, user_id: int, db: AsyncSession) -> Job:
    result = await db.execute(
        select(Job).where(Job.id == job_id, Job.user_id == user_id)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job
