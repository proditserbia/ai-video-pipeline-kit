from __future__ import annotations

import enum
import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class JobStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    rendering = "rendering"
    uploading = "uploading"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class JobType(str, enum.Enum):
    manual = "manual"
    scheduled = "scheduled"


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(
        sa.String(36), primary_key=True, default=lambda: str(uuid.uuid4()), index=True
    )
    project_id: Mapped[int | None] = mapped_column(
        sa.Integer, sa.ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )
    user_id: Mapped[int] = mapped_column(
        sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(sa.String(512), nullable=False)
    status: Mapped[JobStatus] = mapped_column(
        sa.Enum(JobStatus), default=JobStatus.pending, nullable=False
    )
    job_type: Mapped[JobType] = mapped_column(
        sa.Enum(JobType), default=JobType.manual, nullable=False
    )
    input_data: Mapped[dict | None] = mapped_column(sa.JSON, nullable=True)
    output_path: Mapped[str | None] = mapped_column(sa.String(1024), nullable=True)
    output_metadata: Mapped[dict | None] = mapped_column(sa.JSON, nullable=True)
    logs: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(sa.Integer, default=0, nullable=False)
    max_retries: Mapped[int] = mapped_column(sa.Integer, default=3, nullable=False)
    celery_task_id: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    dry_run: Mapped[bool] = mapped_column(sa.Boolean, default=False, nullable=False)
    validation_result: Mapped[dict | None] = mapped_column(sa.JSON, nullable=True)
    created_at: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )
    updated_at: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
        nullable=False,
    )
    started_at: Mapped[sa.DateTime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    completed_at: Mapped[sa.DateTime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
