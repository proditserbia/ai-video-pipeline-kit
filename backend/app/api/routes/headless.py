from __future__ import annotations

"""
Headless API Mode routes.

Endpoints:
  POST /api/v1/headless/jobs                 — create a job from structured JSON
  POST /api/v1/headless/jobs/from-template   — create a job from a named template + props
  GET  /api/v1/headless/templates            — list available templates
  GET  /api/v1/headless/templates/{id}       — get a single template
  GET  /api/v1/headless/examples             — return example payloads for every mode
"""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.api.templates import get_template, list_templates, render_template
from app.models.job import Job, JobType
from app.models.user import User
from app.schemas.headless import (
    HeadlessJobCreate,
    HeadlessJobResponse,
    TemplateInfo,
    TemplateJobCreate,
)

router = APIRouter(prefix="/api/v1/headless", tags=["headless"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_headless_response(job: Job, request: Request) -> HeadlessJobResponse:
    base = str(request.base_url).rstrip("/")
    return HeadlessJobResponse(
        job_id=job.id,
        status=job.status.value,
        mode=job.input_data.get("mode", "unknown") if job.input_data else "unknown",
        title=job.title,
        dry_run=job.dry_run,
        poll_url=f"{base}/api/jobs/{job.id}",
        logs_url=f"{base}/api/jobs/{job.id}/logs",
    )


async def _create_and_queue_job(
    *,
    title: str,
    project_id: int | None,
    input_data: dict[str, Any],
    dry_run: bool,
    max_retries: int,
    user: User,
    db: AsyncSession,
) -> Job:
    """Shared helper: persist a Job row and enqueue the Celery pipeline task."""
    job = Job(
        id=str(uuid.uuid4()),
        user_id=user.id,
        project_id=project_id,
        title=title,
        job_type=JobType.manual,
        input_data=input_data,
        dry_run=dry_run,
        max_retries=max_retries,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    try:
        from worker.tasks.video_pipeline import run_video_pipeline

        task = run_video_pipeline.apply_async(args=[job.id])
        job.celery_task_id = task.id
        await db.commit()
        await db.refresh(job)
    except Exception:
        # Worker unavailable in test / dry-run environments — job stays queued
        pass

    return job


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post(
    "/jobs",
    response_model=HeadlessJobResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a headless video job",
    description=(
        "Submit a structured JSON payload to create and queue a video generation job.\n\n"
        "**Modes**\n"
        "- `auto` — only `script.topic` required; pipeline handles everything.\n"
        "- `semi_auto` — topic/script + selective overrides.\n"
        "- `full_control` — explicit configuration for every pipeline stage.\n\n"
        "See `GET /api/v1/headless/examples` for ready-to-use payload examples."
    ),
)
async def create_headless_job(
    body: HeadlessJobCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> HeadlessJobResponse:
    job = await _create_and_queue_job(
        title=body.title,
        project_id=body.project_id,
        input_data=body.to_input_data(),
        dry_run=body.dry_run,
        max_retries=body.max_retries,
        user=current_user,
        db=db,
    )
    return _build_headless_response(job, request)


@router.post(
    "/jobs/from-template",
    response_model=HeadlessJobResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a job from a template",
    description=(
        "Render a named template by supplying `props` that fill `{{placeholder}}` values, "
        "then create and queue the resulting video job.\n\n"
        "See `GET /api/v1/headless/templates` for available templates and required props."
    ),
)
async def create_job_from_template(
    body: TemplateJobCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> HeadlessJobResponse:
    try:
        rendered = render_template(body.template_id, body.props)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    # Apply caller overrides on top of the rendered template
    rendered["voice"] = body.voice.model_dump()
    rendered["upload"] = body.upload.model_dump()
    rendered["dry_run"] = body.dry_run
    rendered["headless"] = True
    rendered["template_id"] = body.template_id
    rendered["props"] = body.props

    title = rendered.get("title", f"Template: {body.template_id}")

    job = await _create_and_queue_job(
        title=title,
        project_id=body.project_id,
        input_data=rendered,
        dry_run=body.dry_run,
        max_retries=body.max_retries,
        user=current_user,
        db=db,
    )
    return _build_headless_response(job, request)


@router.get(
    "/templates",
    response_model=list[TemplateInfo],
    summary="List available job templates",
)
async def get_templates(
    _current_user: User = Depends(get_current_user),
) -> list[TemplateInfo]:
    return [TemplateInfo(**t) for t in list_templates()]


@router.get(
    "/templates/{template_id}",
    response_model=TemplateInfo,
    summary="Get a single template by ID",
)
async def get_single_template(
    template_id: str,
    _current_user: User = Depends(get_current_user),
) -> TemplateInfo:
    tmpl = get_template(template_id)
    if tmpl is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    return TemplateInfo(
        id=tmpl["id"],
        name=tmpl["name"],
        description=tmpl["description"],
        required_props=tmpl["required_props"],
        optional_props=tmpl["optional_props"],
        example_props=tmpl["example_props"],
    )


@router.get(
    "/examples",
    summary="Get example payloads for all headless modes",
    description="Returns ready-to-use JSON payloads demonstrating each input mode.",
)
async def get_examples(
    _current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    return {
        "auto": {
            "_comment": "Minimal payload — only topic required. Pipeline handles everything.",
            "mode": "auto",
            "title": "Quick Auto Video",
            "script": {
                "topic": "5 productivity tips for remote workers",
                "tone": "motivational",
                "duration_seconds": 60,
                "target_platform": "tiktok",
            },
        },
        "semi_auto": {
            "_comment": "Topic + selective overrides for voice and captions.",
            "mode": "semi_auto",
            "title": "Semi-Auto Product Video",
            "script": {
                "topic": "Why you need a standing desk",
                "tone": "conversational",
                "duration_seconds": 45,
                "target_platform": "instagram",
            },
            "voice": {
                "provider": "edge_tts",
                "voice_id": "en-US-GuyNeural",
                "rate": "+8%",
            },
            "caption": {
                "enabled": True,
                "style": "bold",
            },
        },
        "full_control": {
            "_comment": "Every pipeline stage explicitly configured.",
            "mode": "full_control",
            "title": "Full Control Tutorial",
            "project_id": None,
            "script": {
                "text": "Welcome back. Today I will show you exactly how to set up Docker in five minutes. Step one: install Docker Desktop. Step two: verify with docker dash dash version. Step three: run your first container. That is it. Follow for more dev tips.",
                "duration_seconds": 90,
                "target_platform": "youtube",
            },
            "voice": {
                "provider": "edge_tts",
                "voice_id": "en-US-JennyNeural",
                "rate": "+0%",
                "pitch": "+0Hz",
                "volume": "+0%",
            },
            "caption": {
                "enabled": True,
                "style": "basic",
                "max_line_width": 40,
            },
            "video": {
                "resolution": "1080x1920",
                "background_music": True,
                "background_music_volume": 0.1,
                "watermark": False,
                "stock_query": "programming laptop desk",
                "thumbnail": True,
                "fps": 30,
            },
            "upload": {
                "destinations": ["local"],
                "tags": ["docker", "devtips", "programming"],
                "privacy": "private",
                "dry_run": False,
            },
            "dry_run": False,
            "max_retries": 3,
        },
        "template": {
            "_comment": "Template mode — use a pre-built template + props.",
            "template_id": "quick_explainer",
            "props": {
                "topic": "How blockchain works in plain English",
                "tone": "educational",
                "voice_id": "en-US-JennyNeural",
                "target_platform": "youtube",
            },
        },
        "dry_run": {
            "_comment": "Dry-run mode — pipeline runs but does not write final output.",
            "mode": "auto",
            "title": "Dry Run Test",
            "script": {
                "topic": "Test topic for dry run",
                "duration_seconds": 30,
            },
            "dry_run": True,
        },
    }
