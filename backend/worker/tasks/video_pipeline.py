from __future__ import annotations

import traceback
from datetime import datetime, timezone
from pathlib import Path

import structlog

from worker.celery_app import celery_app

logger = structlog.get_logger(__name__)


def _append_log(db, job, line: str) -> None:
    from sqlalchemy.exc import SQLAlchemyError

    job.logs = (job.logs or "") + f"[{datetime.now(timezone.utc).isoformat()}] {line}\n"
    try:
        db.commit()
    except SQLAlchemyError as exc:
        logger.warning("append_log_commit_failed_retrying", error=str(exc))
        db.rollback()
        db.commit()


def _resolve_script_text(input_data: dict) -> str:
    """Extract script text from either flat (jobs API) or nested (headless API) input_data."""
    flat = input_data.get("script_text", "")
    if flat:
        return flat
    script_cfg = input_data.get("script", {})
    if isinstance(script_cfg, dict):
        return script_cfg.get("text", "")
    return ""


def _resolve_topic(input_data: dict) -> str:
    """Extract topic from either flat or nested input_data."""
    flat = input_data.get("topic", "")
    if flat:
        return flat
    script_cfg = input_data.get("script", {})
    if isinstance(script_cfg, dict):
        return script_cfg.get("topic", "")
    return ""


def _resolve_voice(input_data: dict) -> str:
    """Extract voice ID from either flat or nested input_data."""
    voice = input_data.get("voice", "en-US-AriaNeural")
    if isinstance(voice, dict):
        # Headless API stores voice as {"provider": "...", "voice_id": "..."}
        return voice.get("voice_id", "en-US-AriaNeural")
    return voice or "en-US-AriaNeural"


@celery_app.task(bind=True, name="worker.tasks.video_pipeline.run_video_pipeline")
def run_video_pipeline(self, job_id: str) -> dict:
    """
    Orchestrates the full video production pipeline:
    1.  Load job from DB
    2.  Update status → processing
    3.  Generate / use script     (ai_scripts flag)
    4.  Generate TTS audio        (tts flag)
    5.  Fetch stock media         (stock_media flag)
    6.  Generate captions         (captions flag)
    7.  Build video with FFmpeg   (core_video flag)
    8.  Validate output           (ffprobe)
    9.  Upload / export           (uploader)
    10. Update status → completed
    """
    from app.config import settings
    from app.core.feature_flags import FeatureFlags
    from app.database import SyncSessionLocal
    import app.models  # noqa: F401 – ensure all models are registered in Base metadata
    from app.models.job import Job, JobStatus

    flags = FeatureFlags()
    db = SyncSessionLocal()()
    job: Job | None = None

    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            logger.error("job_not_found", job_id=job_id)
            return {"error": "job_not_found"}

        log = logger.bind(job_id=job_id)
        job.status = JobStatus.processing
        job.started_at = datetime.now(timezone.utc)
        _append_log(db, job, "Pipeline started")

        input_data: dict = job.input_data or {}
        work_dir = Path(settings.STORAGE_PATH) / "temp" / job_id
        work_dir.mkdir(parents=True, exist_ok=True)

        # ── Step 3: Script ─────────────────────────────────────────────
        script_text: str = _resolve_script_text(input_data)
        if not script_text and flags.is_enabled("ai_scripts"):
            _append_log(db, job, "Generating script via AI")
            from worker.modules.script_generator.openai_provider import OpenAIScriptProvider
            from worker.modules.script_generator.placeholder_provider import PlaceholderScriptProvider

            topic = _resolve_topic(input_data) or job.title
            if settings.OPENAI_API_KEY:
                provider = OpenAIScriptProvider()
            else:
                provider = PlaceholderScriptProvider()
            result = provider.generate(topic=topic, config=input_data.get("script_settings", {}))
            script_text = result.text
            _append_log(db, job, f"Script generated ({len(script_text)} chars)")
        elif not script_text:
            script_text = job.title  # fallback

        # ── Step 4: TTS ────────────────────────────────────────────────
        audio_path: Path | None = None
        if flags.is_enabled("tts"):
            _append_log(db, job, "Synthesising TTS audio")
            voice = _resolve_voice(input_data)
            audio_out = work_dir / "voice.mp3"
            if not job.dry_run:
                if settings.EDGE_TTS_ENABLED:
                    from worker.modules.tts.edge_tts_provider import EdgeTTSProvider
                    import asyncio
                    tts = EdgeTTSProvider()
                    asyncio.run(tts.synthesize(script_text, voice, str(audio_out)))
                    audio_path = audio_out
            else:
                audio_path = audio_out
            _append_log(db, job, f"TTS audio: {audio_path}")

        # ── Step 5: Stock media ────────────────────────────────────────
        media_clips: list[Path] = []
        if flags.is_enabled("stock_media"):
            _append_log(db, job, "Fetching stock media")
            if not job.dry_run:
                media_dir = work_dir / "media"
                media_dir.mkdir(exist_ok=True)
                from worker.modules.stock_media.local_provider import LocalMediaProvider
                provider = LocalMediaProvider()
                assets = provider.fetch(query=job.title, count=3, output_dir=str(media_dir))
                media_clips = [Path(a.path) for a in assets]
            _append_log(db, job, f"Stock media clips: {len(media_clips)}")

        # ── Step 6: Captions ───────────────────────────────────────────
        srt_path: Path | None = None
        if flags.is_enabled("captions") and audio_path and not job.dry_run:
            _append_log(db, job, "Generating captions with Whisper")
            try:
                from worker.modules.captions.whisper_provider import WhisperCaptionProvider
                caption_provider = WhisperCaptionProvider()
                caption_result = caption_provider.transcribe(str(audio_path), str(work_dir))
                srt_path = Path(caption_result.srt_path) if caption_result.srt_path else None
                _append_log(db, job, f"Captions: {srt_path}")
            except Exception as exc:
                _append_log(db, job, f"Captions skipped: {exc}")

        # ── Step 7: Build video ────────────────────────────────────────
        output_path: Path | None = None
        if flags.is_enabled("core_video"):
            _append_log(db, job, "Building video with FFmpeg")
            job.status = JobStatus.rendering
            db.commit()

            output_dir = Path(settings.STORAGE_PATH) / "outputs"
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = output_dir / f"{job_id}.mp4"

            if not job.dry_run:
                from worker.modules.video_builder.ffmpeg_builder import FFmpegVideoBuilder
                builder = FFmpegVideoBuilder()
                builder.build(
                    clips=media_clips,
                    audio_path=audio_path,
                    srt_path=srt_path,
                    output_path=output_path,
                    use_nvenc=settings.NVIDIA_NVENC_ENABLED,
                )
            _append_log(db, job, f"Video built: {output_path}")

        # ── Step 8: Validate ───────────────────────────────────────────
        if output_path and output_path.exists() and not job.dry_run:
            _append_log(db, job, "Validating output")
            from worker.modules.video_builder.validator import VideoValidator
            validator = VideoValidator()
            validation = validator.validate(str(output_path))
            job.validation_result = validation.to_dict()
            db.commit()
            _append_log(db, job, f"Validation: passed={validation.passed}")

        # ── Step 9: Upload ─────────────────────────────────────────────
        upload_url: str | None = None
        if output_path and not job.dry_run:
            _append_log(db, job, "Exporting / uploading")
            job.status = JobStatus.uploading
            db.commit()

            from worker.modules.uploader.local_exporter import LocalExporter
            exporter = LocalExporter()
            upload_result = exporter.upload(str(output_path), {"title": job.title})
            upload_url = upload_result.url
            _append_log(db, job, f"Export URL: {upload_url}")

        # ── Step 10: Done ──────────────────────────────────────────────
        job.status = JobStatus.completed
        job.completed_at = datetime.now(timezone.utc)
        if output_path:
            job.output_path = str(output_path)
        job.output_metadata = {"upload_url": upload_url}
        _append_log(db, job, "Pipeline completed")
        db.commit()
        log.info("pipeline_completed")
        return {"status": "completed", "job_id": job_id}

    except Exception as exc:
        tb = traceback.format_exc()
        if job:
            job.status = JobStatus.failed
            job.error_message = str(exc)
            _append_log(db, job, f"ERROR: {exc}\n{tb}")
            db.commit()
        logger.exception("pipeline_failed", job_id=job_id, error=str(exc))
        # Only retry on transient infrastructure errors (network / OS / DB IO).
        # Logic errors (missing binary, bad config, invalid script) should not
        # be retried automatically – they will fail again immediately.
        _RETRY_COUNTDOWN_SECONDS = 60
        if isinstance(exc, (OSError, ConnectionError, TimeoutError)):
            raise self.retry(exc=exc, countdown=_RETRY_COUNTDOWN_SECONDS)
        raise

    finally:
        db.close()
