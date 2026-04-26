from __future__ import annotations

import asyncio
import traceback
from datetime import datetime, timezone
from pathlib import Path

import structlog

from worker.celery_app import celery_app

logger = structlog.get_logger(__name__)


def _run_async(coro):
    """Execute an async coroutine safely from a synchronous Celery task."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()
        asyncio.set_event_loop(None)


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


def _resolve_caption_style(input_data: dict) -> str | None:
    style = input_data.get("caption_style")
    if style:
        return style
    # Headless API may nest it inside a captions config dict
    captions_cfg = input_data.get("captions", {})
    if isinstance(captions_cfg, dict):
        return captions_cfg.get("style")
    return None


def _resolve_brand_assets(db, input_data: dict, job) -> tuple:
    """Resolve watermark and background music file paths from asset IDs.

    Priority for each asset:
      1. job ``input_data`` override (flat key or nested under ``"brand"``)
      2. project-level ``watermark_asset_id`` / ``background_music_asset_id``

    Returns ``(watermark_asset_id, watermark_path, bg_music_asset_id, bg_music_path)``.
    Paths are ``Path | None``; IDs are ``int | None``.
    Paths are returned regardless of whether the file currently exists on
    disk; ``FFmpegVideoBuilder._compose`` skips missing files gracefully.
    """
    from pathlib import Path as _Path

    from app.models.asset import Asset
    from app.models.project import Project

    def _asset_path(asset_id) -> _Path | None:
        if asset_id is None:
            return None
        try:
            asset_id = int(asset_id)
        except (TypeError, ValueError):
            return None
        asset = db.query(Asset).filter(Asset.id == asset_id).first()
        if asset and asset.file_path:
            return _Path(asset.file_path)
        return None

    # Resolve IDs — input_data overrides project settings.
    brand_cfg = input_data.get("brand") or {}
    if not isinstance(brand_cfg, dict):
        brand_cfg = {}

    watermark_id = input_data.get("watermark_asset_id") or brand_cfg.get("watermark_asset_id")
    bg_music_id = (
        input_data.get("bg_music_asset_id")
        or brand_cfg.get("bg_music_asset_id")
    )

    # Fall back to project-level brand settings.
    if (not watermark_id or not bg_music_id) and job.project_id:
        project = db.query(Project).filter(Project.id == job.project_id).first()
        if project:
            if not watermark_id:
                watermark_id = project.watermark_asset_id
            if not bg_music_id:
                bg_music_id = project.background_music_asset_id

    # Normalise IDs to int or None.
    try:
        watermark_id = int(watermark_id) if watermark_id is not None else None
    except (TypeError, ValueError):
        watermark_id = None
    try:
        bg_music_id = int(bg_music_id) if bg_music_id is not None else None
    except (TypeError, ValueError):
        bg_music_id = None

    return watermark_id, _asset_path(watermark_id), bg_music_id, _asset_path(bg_music_id)


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

        # Accumulated warnings for result_quality classification at Step 10.
        _warnings: list[str] = []

        # ── Step 4: TTS ────────────────────────────────────────────────
        audio_path: Path | None = None
        if flags.is_enabled("tts"):
            _append_log(db, job, "Synthesising TTS audio")
            voice = _resolve_voice(input_data)
            audio_out = work_dir / "voice.mp3"
            if not job.dry_run:
                from worker.modules.tts.selector import get_tts_provider
                tts_provider = get_tts_provider()
                if tts_provider is not None:
                    try:
                        _run_async(tts_provider.synthesize(script_text, voice, str(audio_out)))
                        audio_path = audio_out
                        _append_log(db, job, f"TTS audio: {audio_path}")
                        job.output_metadata = {
                            **(job.output_metadata or {}),
                            "tts_status": "success",
                        }
                        db.commit()
                    except Exception as tts_exc:
                        tts_error = f"TTS provider {type(tts_provider).__name__} failed: {tts_exc}"
                        _append_log(db, job, f"TTS warning: {tts_error} – continuing without audio")
                        log.warning("tts_failed", provider=type(tts_provider).__name__, error=str(tts_exc))
                        _warnings.append(tts_error)
                        job.output_metadata = {
                            **(job.output_metadata or {}),
                            "tts_status": "failed",
                            "tts_warning": tts_error,
                        }
                        db.commit()
                else:
                    _append_log(db, job, "TTS skipped: no provider configured")
                    log.warning("tts_skipped", reason="no_provider_configured")
                    _tts_skip_msg = "TTS was skipped. No provider is configured. Video will render without voiceover."
                    _warnings.append(_tts_skip_msg)
                    job.output_metadata = {
                        **(job.output_metadata or {}),
                        "tts_status": "skipped",
                        "tts_warning": _tts_skip_msg,
                    }
                    db.commit()
            else:
                audio_path = audio_out
                _append_log(db, job, f"TTS audio (dry run): {audio_path}")

        # ── Step 5: Stock media ────────────────────────────────────────
        media_clips: list[Path] = []
        if flags.is_enabled("stock_media"):
            _append_log(db, job, "Fetching stock media")
            if not job.dry_run:
                media_dir = work_dir / "media"
                media_dir.mkdir(exist_ok=True)
                from worker.modules.stock_media.selector import StockMediaSelector

                # Build search query from script text → topic → job title
                search_query = (
                    script_text
                    or _resolve_topic(input_data)
                    or job.title
                )
                selector = StockMediaSelector()
                assets, stock_provider = selector.fetch(
                    query=search_query,
                    count=3,
                    output_dir=str(media_dir),
                )
                media_clips = [Path(a.path) for a in assets]
                _append_log(db, job, f"Stock media: {len(media_clips)} clips from {stock_provider}")
                if stock_provider == "placeholder":
                    _stock_warn = "Stock media: no real clips available. Placeholder visuals were used."
                    _warnings.append(_stock_warn)
                job.output_metadata = {
                    **(job.output_metadata or {}),
                    "stock_provider": stock_provider,
                    "clip_sources": [a.source for a in assets],
                }
                db.commit()
            else:
                _append_log(db, job, "Stock media skipped (dry run)")

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
                _cap_warn = f"Captions were skipped: {exc}"
                _append_log(db, job, f"Captions skipped: {exc}")
                _warnings.append(_cap_warn)

        # ── Step 7: Build video ────────────────────────────────────────
        output_path: Path | None = None
        caption_style = _resolve_caption_style(input_data)
        watermark_asset_id, watermark_path, bg_music_asset_id, bg_music_path = (
            _resolve_brand_assets(db, input_data, job)
        )
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
                    caption_style=caption_style,
                    watermark_path=watermark_path,
                    bg_music_path=bg_music_path,
                )
                job.output_metadata = {
                    **(job.output_metadata or {}),
                    "caption_style": caption_style,
                    "watermark_asset_id": watermark_asset_id,
                    "bg_music_asset_id": bg_music_asset_id,
                }
                db.commit()
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
        # Classify result quality from accumulated warnings and metadata.
        # partial  → TTS or captions were missing (content gap)
        # fallback → only placeholder stock visuals were used
        # complete → no warnings
        _partial_prefixes = ("TTS", "Captions")
        _is_partial = any(
            any(w.startswith(prefix) for prefix in _partial_prefixes) for w in _warnings
        )
        _current_meta = job.output_metadata or {}
        _is_fallback = _current_meta.get("stock_provider") == "placeholder"
        if _is_partial:
            _result_quality = "partial"
        elif _is_fallback:
            _result_quality = "fallback"
        else:
            _result_quality = "complete"

        job.status = JobStatus.completed
        job.completed_at = datetime.now(timezone.utc)
        if output_path:
            job.output_path = str(output_path)
        job.output_metadata = {
            **(job.output_metadata or {}),
            "upload_url": upload_url,
            "result_quality": _result_quality,
            "warnings": _warnings,
        }
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
