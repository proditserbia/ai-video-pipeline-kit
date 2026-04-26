from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, computed_field, field_validator

from app.models.job import JobStatus, JobType


class JobBase(BaseModel):
    title: str
    job_type: JobType = JobType.manual
    input_data: dict[str, Any] | None = None
    dry_run: bool = False
    max_retries: int = 3


class JobCreate(JobBase):
    project_id: int | None = None
    # Convenience fields accepted from the dashboard form.
    # If input_data is not provided, these are mapped into input_data automatically
    # by the create_job endpoint so the worker can read them.
    script: str | None = None
    topic: str | None = None
    voice_name: str = "en-US-AriaNeural"
    caption_style: str = "basic"


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
    # logs is stored as a newline-delimited TEXT in the DB; the API always
    # returns a list of non-empty lines so the frontend log viewer just works.
    logs: list[str]
    error_message: str | None
    retry_count: int
    celery_task_id: str | None
    validation_result: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    completed_at: datetime | None

    model_config = {"from_attributes": True}

    @field_validator("logs", mode="before")
    @classmethod
    def _coerce_logs(cls, v: Any) -> list[str]:
        """Convert the raw TEXT blob into a list of non-empty log lines."""
        if v is None:
            return []
        if isinstance(v, str):
            return [line for line in v.splitlines() if line.strip()]
        if isinstance(v, list):
            return v
        return []

    # ---------- computed fields exposed to the frontend ----------

    @computed_field  # type: ignore[misc]
    @property
    def voice_name(self) -> str | None:
        v = (self.input_data or {}).get("voice")
        if isinstance(v, dict):
            # Headless API stores voice as {"provider": "...", "voice_id": "..."}
            return v.get("voice_id")
        return v or None

    @computed_field  # type: ignore[misc]
    @property
    def caption_style(self) -> str | None:
        return (self.input_data or {}).get("caption_style")

    @computed_field  # type: ignore[misc]
    @property
    def script(self) -> str | None:
        d = self.input_data or {}
        text = d.get("script_text", "")
        if not text:
            script_cfg = d.get("script", {})
            if isinstance(script_cfg, dict):
                text = script_cfg.get("text", "")
        return text or None

    @computed_field  # type: ignore[misc]
    @property
    def topic(self) -> str | None:
        d = self.input_data or {}
        t = d.get("topic", "")
        if not t:
            script_cfg = d.get("script", {})
            if isinstance(script_cfg, dict):
                t = script_cfg.get("topic", "")
        return t or None

    @computed_field  # type: ignore[misc]
    @property
    def output_url(self) -> str | None:
        """Return the authenticated download URL for the job output."""
        if not self.output_path:
            return None
        return f"/api/v1/jobs/{self.id}/download"

    @computed_field  # type: ignore[misc]
    @property
    def tts_status(self) -> str | None:
        """TTS outcome: 'success', 'skipped', or 'failed'."""
        return (self.output_metadata or {}).get("tts_status")

    @computed_field  # type: ignore[misc]
    @property
    def tts_warning(self) -> str | None:
        """Human-readable TTS warning when status is 'skipped' or 'failed'."""
        return (self.output_metadata or {}).get("tts_warning")

    @computed_field  # type: ignore[misc]
    @property
    def result_quality(self) -> str | None:
        """Overall quality of this job's output: 'complete', 'partial', or 'fallback'."""
        return (self.output_metadata or {}).get("result_quality")

    @computed_field  # type: ignore[misc]
    @property
    def warnings(self) -> list[str]:
        """List of human-readable warnings accumulated during the pipeline run."""
        v = (self.output_metadata or {}).get("warnings")
        if isinstance(v, list):
            return v
        return []


class JobListResponse(BaseModel):
    items: list[JobResponse]
    total: int
    page: int
    size: int
    pages: int = 1


class JobStats(BaseModel):
    total: int
    completed: int
    failed: int
    processing: int
    pending: int
