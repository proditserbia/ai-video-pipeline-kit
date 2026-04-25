from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.models.job import JobStatus, JobType


class JobBase(BaseModel):
    title: str
    job_type: JobType = JobType.manual
    input_data: dict[str, Any] | None = None
    dry_run: bool = False
    max_retries: int = 3


class JobCreate(JobBase):
    project_id: int | None = None


class JobUpdate(BaseModel):
    title: str | None = None
    status: JobStatus | None = None
    output_path: str | None = None
    output_metadata: dict[str, Any] | None = None
    logs: str | None = None
    error_message: str | None = None


class JobResponse(JobBase):
    id: str
    project_id: int | None
    user_id: int
    status: JobStatus
    output_path: str | None
    output_metadata: dict[str, Any] | None
    logs: str | None
    error_message: str | None
    retry_count: int
    celery_task_id: str | None
    validation_result: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class JobListResponse(BaseModel):
    items: list[JobResponse]
    total: int
    page: int
    size: int
