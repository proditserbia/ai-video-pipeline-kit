from __future__ import annotations

import asyncio
import subprocess
import traceback
from datetime import datetime, timezone
from pathlib import Path

import structlog

from worker.celery_app import celery_app

logger = structlog.get_logger(__name__)

# Caption style values that mean "disabled" (no captions, no Whisper).
_DISABLED_CAPTION_STYLES: frozenset = frozenset({None, "", "None", "none"})


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


def _resolve_prompt(input_data: dict) -> str:
    """Extract script generation instructions / prompt from input_data.

    The ``prompt`` key holds additional guidance (tone, audience, angle) that
    is passed to the script generator.  It is intentionally separate from
    ``topic`` so that visual planning always uses the topic, not the instructions.
    """
    return input_data.get("prompt", "") or ""


def _normalize_visual_tags(raw) -> list[str]:
    """Return a clean list of lowercase visual tag strings.

    Accepts:
    - A comma-separated string: ``"architecture, soldiers, market"``
    - A list of strings: ``["architecture", "soldiers"]``
    - ``None`` / empty → ``[]``
    """
    if not raw:
        return []
    if isinstance(raw, str):
        raw = raw.split(",")
    return [t.strip().lower() for t in raw if str(t).strip()]


def _resolve_visual_tags(input_data: dict) -> list[str]:
    """Extract and normalise visual_tags from input_data."""
    return _normalize_visual_tags(input_data.get("visual_tags"))


def _resolve_voice(input_data: dict) -> str:
    """Extract voice ID from either flat or nested input_data."""
    voice = input_data.get("voice", "en-US-AriaNeural")
    if isinstance(voice, dict):
        # Headless API stores voice as {"provider": "...", "voice_id": "..."}
        return voice.get("voice_id", "en-US-AriaNeural")
    return voice or "en-US-AriaNeural"


def _resolve_caption_style(input_data: dict) -> str:
    """Return the requested caption style.

    "none" (or any disabled signal: None, empty string, the literal string
    "None") is normalised to the canonical value ``"none"``.
    """
    style = input_data.get("caption_style")
    if style not in _DISABLED_CAPTION_STYLES:
        return str(style)

    # Headless API may nest it inside a captions config dict.
    captions_cfg = input_data.get("captions", {})
    if isinstance(captions_cfg, dict):
        nested = captions_cfg.get("style")
        if nested not in _DISABLED_CAPTION_STYLES:
            return str(nested)

    return "none"


def _cleanup_work_dir(work_dir: Path, job_id: str, *, keep: bool = False) -> None:
    """Remove the temporary job work directory.

    Args:
        work_dir: Path to the directory to remove.
        job_id:   Used only for log context.
        keep:     When *True* the directory is not deleted (debug mode).
    """
    import shutil

    if keep:
        logger.info("workdir_kept", job_id=job_id, path=str(work_dir))
        return
    if not work_dir.exists():
        return
    try:
        shutil.rmtree(work_dir)
        logger.info("workdir_cleaned", job_id=job_id, path=str(work_dir))
    except Exception as exc:  # noqa: BLE001
        logger.warning("workdir_cleanup_failed", job_id=job_id, path=str(work_dir), error=str(exc))


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


def _concat_audio_files(parts: list[Path], output: Path) -> None:
    """Concatenate *parts* audio files into *output* using the FFmpeg concat demuxer.

    All inputs must share the same codec (e.g. MP3→MP3) for stream-copy to
    work correctly.  The output file is overwritten if it already exists.

    Args:
        parts:  Ordered list of source audio paths.
        output: Destination path for the concatenated audio.

    Raises:
        RuntimeError: If the FFmpeg command exits with a non-zero return code.
    """
    import uuid as _uuid

    list_file = output.parent / f"_concat_{output.stem}_{_uuid.uuid4().hex}.txt"
    list_file.write_text(
        "\n".join(f"file '{str(p)}'" for p in parts),
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(list_file),
            "-c", "copy",
            str(output),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        try:
            list_file.unlink(missing_ok=True)
        except OSError:
            pass
    if result.returncode != 0:
        raise RuntimeError(f"Audio concatenation failed: {result.stderr[:500]}")


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
    work_dir: Path | None = None

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

        # Resolve the structured input fields once and log them.
        _topic: str = _resolve_topic(input_data) or job.title or ""
        _prompt_instructions: str = _resolve_prompt(input_data)
        _visual_tags: list[str] = _resolve_visual_tags(input_data)

        if not _topic:
            log.warning("pipeline_topic_empty", job_id=job_id)

        log.info(
            "pipeline_inputs_resolved",
            topic_resolved=_topic,
            prompt_instructions_present=bool(_prompt_instructions),
            visual_tags_resolved=_visual_tags,
        )
        _append_log(
            db, job,
            f"Inputs: topic={_topic!r} "
            f"prompt_present={bool(_prompt_instructions)} "
            f"visual_tags={_visual_tags}",
        )

        # ── Step 3: Script ─────────────────────────────────────────────
        script_text: str = _resolve_script_text(input_data)
        if not script_text and flags.is_enabled("ai_scripts"):
            _append_log(db, job, "Generating script via AI")
            from worker.modules.script_generator.openai_provider import (
                OpenAIRateLimitedError,
                OpenAIScriptProvider,
            )
            from worker.modules.script_generator.placeholder_provider import PlaceholderScriptProvider

            topic = _topic
            # Merge prompt/instructions into script_settings so providers can use them.
            _script_cfg: dict = {**input_data.get("script_settings", {})}
            if _prompt_instructions:
                _script_cfg["instructions"] = _prompt_instructions
            # Pass visual_tags so the script provider can inject subject constraints.
            if _visual_tags:
                _script_cfg["visual_tags"] = _visual_tags
            if settings.OPENAI_API_KEY:
                try:
                    result = OpenAIScriptProvider().generate(
                        topic=topic, config=_script_cfg
                    )
                except OpenAIRateLimitedError:
                    script_warning = "OpenAI rate limited, fallback script used"
                    log.warning("openai_script_rate_limited", topic=topic)
                    logger.warning(
                        "OpenAI script generation rate limited, using fallback",
                        topic=topic,
                    )
                    _append_log(db, job, "OpenAI script generation rate limited, using fallback")
                    result = PlaceholderScriptProvider().generate(
                        topic=topic, config=_script_cfg
                    )
                    job.output_metadata = {
                        **(job.output_metadata or {}),
                        "script_warning": script_warning,
                    }
                    db.commit()
            else:
                result = PlaceholderScriptProvider().generate(
                    topic=topic, config=_script_cfg
                )
            script_text = result.text
            _append_log(db, job, f"Script generated ({len(script_text)} chars)")
        elif not script_text:
            script_text = job.title  # fallback

        # Accumulated warnings for result_quality classification at Step 10.
        _warnings: list[str] = []

        # Determine early whether the AI paragraph-sync path will be used so
        # that Step 4 can skip generating a wasteful full-script TTS file.
        _ai_paragraph_sync: bool = (
            flags.is_enabled("stock_media")
            and (settings.MEDIA_MODE or "stock").lower() == "ai"
            and settings.AI_IMAGE_ENABLED
        )

        # ── Step 4: TTS ────────────────────────────────────────────────
        audio_path: Path | None = None
        if flags.is_enabled("tts"):
            audio_out = work_dir / "voice.mp3"
            if _ai_paragraph_sync and not job.dry_run:
                # Per-block TTS will be generated in Step 5 (AI paragraph-sync
                # mode).  Generating a full-script file here would be redundant.
                _append_log(
                    db, job,
                    "TTS deferred: per-block TTS will run in AI paragraph-sync mode",
                )
                log.info("tts_deferred_paragraph_sync")
            else:
                _append_log(db, job, "Synthesising TTS audio")
                voice = _resolve_voice(input_data)
                if not job.dry_run:
                    from worker.modules.tts.selector import get_tts_provider, get_tts_provider_name
                    tts_provider = get_tts_provider()
                    _append_log(db, job, f"TTS provider selected: {get_tts_provider_name(tts_provider)}")
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

        # ── Step 5: Media (stock path or AI-image-timeline path) ───────
        media_clips: list[Path] = []
        # visual_segments is populated only when the new AI-image-timeline
        # path is used (MEDIA_MODE=ai + AI_IMAGE_ENABLED=True).
        visual_segments: list | None = None

        if flags.is_enabled("stock_media"):
            _append_log(db, job, "Fetching media")
            if not job.dry_run:
                media_dir = work_dir / "media"
                media_dir.mkdir(exist_ok=True)

                media_mode = (settings.MEDIA_MODE or "stock").lower()

                log.info(
                    "media_mode_resolved",
                    media_mode=media_mode,
                    ai_image_enabled=settings.AI_IMAGE_ENABLED,
                    ai_image_provider=settings.AI_IMAGE_PROVIDER,
                )
                _append_log(
                    db,
                    job,
                    f"media_mode_resolved: mode={media_mode!r} "
                    f"ai_image_enabled={settings.AI_IMAGE_ENABLED} "
                    f"ai_image_provider={settings.AI_IMAGE_PROVIDER!r}",
                )

                if media_mode == "ai" and settings.AI_IMAGE_ENABLED:
                    # ── Paragraph-level audio/image sync path ─────────────
                    _append_log(db, job, f"AI image pipeline enabled (provider={settings.AI_IMAGE_PROVIDER})")
                    log.info("ai_image_pipeline_start", provider=settings.AI_IMAGE_PROVIDER)

                    from worker.modules.ai_images.factory import get_ai_image_provider
                    from worker.modules.script_planner.planner import plan_narration_blocks
                    from worker.modules.video_builder.ffmpeg_builder import _probe_duration
                    from worker.modules.video_builder.visual_segment import VisualSegment

                    # Split script into semantic blocks (one TTS + one image each).
                    # Use the already-resolved _topic and _visual_tags.
                    blocks = plan_narration_blocks(
                        script_text, topic=_topic, visual_tags=_visual_tags
                    )
                    _append_log(db, job, f"Narration blocks planned: {len(blocks)}")

                    # ── Storyboard planning layer ──────────────────────────
                    # When STORYBOARD_PLANNER_ENABLED=True this is the main
                    # source of truth for visual generation.  It replaces the
                    # AI_VISUAL_PLANNER path and the per-block prompt_builder
                    # prompts with a richer, story-aware storyboard.
                    _storyboard_scenes = None
                    if settings.STORYBOARD_PLANNER_ENABLED:
                        try:
                            from worker.modules.storyboard import plan_storyboard
                            _storyboard_scenes = plan_storyboard(
                                _topic,
                                _visual_tags or [],
                                script_text,
                                blocks,
                            )
                            # Apply storyboard image prompts back onto the blocks
                            # so that the rest of the pipeline (TTS + image gen)
                            # uses the storyboard-generated prompts.
                            scenes_by_block = {
                                s.narration_block_id: s
                                for s in _storyboard_scenes
                            }
                            for block in blocks:
                                scene = scenes_by_block.get(block.id)
                                if scene and not scene.reuse_previous and scene.image_prompt:
                                    block.image_prompt = scene.image_prompt
                            _append_log(
                                db, job,
                                f"Storyboard planned: {len(_storyboard_scenes)} scenes"
                                f" (provider={settings.STORYBOARD_PLANNER_PROVIDER})",
                            )
                            log.info(
                                "storyboard_applied",
                                n_scenes=len(_storyboard_scenes),
                                provider=settings.STORYBOARD_PLANNER_PROVIDER,
                            )
                        except Exception as sb_exc:
                            log.warning(
                                "storyboard_planner_error",
                                error=str(sb_exc),
                            )
                            _append_log(
                                db, job,
                                f"Storyboard planner error (non-fatal, using block prompts): {sb_exc}",
                            )
                            _storyboard_scenes = None
                    elif settings.AI_VISUAL_PLANNER_ENABLED:
                        # Legacy: override block image prompts with AI-generated
                        # visual briefs when AI_VISUAL_PLANNER_ENABLED=True.
                        try:
                            from worker.modules.ai_images.visual_planner import (
                                plan_visual_briefs,
                            )
                            briefs = plan_visual_briefs(
                                _topic,
                                _visual_tags or [],
                                script_text,
                                blocks,
                            )
                            if briefs:
                                briefs_by_index = {b.block_index: b for b in briefs}
                                for block in blocks:
                                    brief = briefs_by_index.get(block.index)
                                    if brief and brief.visual_prompt:
                                        block.image_prompt = brief.visual_prompt
                                        log.info(
                                            "ai_visual_planner_prompt_applied",
                                            block=block.index,
                                            prompt_preview=brief.visual_prompt[:120],
                                        )
                                _append_log(
                                    db, job,
                                    f"AI visual planner applied {len(briefs)} visual briefs",
                                )
                        except Exception as vp_exc:
                            log.warning(
                                "ai_visual_planner_error",
                                error=str(vp_exc),
                            )
                            _append_log(db, job, f"AI visual planner error (non-fatal): {vp_exc}")

                    # Instantiate the configured AI image provider once.
                    try:
                        ai_provider = get_ai_image_provider()
                        ai_provider_name = type(ai_provider).__name__
                    except Exception as prov_exc:
                        _warnings.append(f"AI image provider unavailable: {prov_exc}")
                        log.warning("ai_image_provider_unavailable", error=str(prov_exc))
                        ai_provider = None
                        ai_provider_name = "none"

                    image_dir = media_dir / "ai_images"
                    image_dir.mkdir(exist_ok=True)

                    # Default block duration (seconds) used when no TTS audio
                    # is available to measure the actual duration.
                    _DEFAULT_BLOCK_DURATION_SECONDS: float = 5.0

                    # Resolve per-block TTS provider (same priority chain as Step 4).
                    _block_voice = _resolve_voice(input_data)
                    _block_tts = None
                    if flags.is_enabled("tts"):
                        from worker.modules.tts.selector import get_tts_provider as _get_tts
                        _block_tts = _get_tts()

                    _scene_logs: list[dict] = []
                    _segments: list[VisualSegment] = []
                    _voice_parts: list[Path] = []
                    _cursor: float = 0.0

                    if ai_provider is not None:
                        # Build storyboard-scene index for reuse_previous checks.
                        _storyboard_by_block_id: dict = {}
                        if _storyboard_scenes:
                            _storyboard_by_block_id = {
                                s.narration_block_id: s
                                for s in _storyboard_scenes
                            }

                        _last_image_path: Path | None = None

                        for block in blocks:
                            # ── Per-block TTS ─────────────────────────────
                            block_audio = work_dir / f"voice_{block.index:03d}.mp3"
                            block_dur: float | None = None
                            if _block_tts is not None:
                                try:
                                    _run_async(
                                        _block_tts.synthesize(
                                            block.text, _block_voice, str(block_audio)
                                        )
                                    )
                                    block_dur = _probe_duration(block_audio)
                                    block.audio_path = block_audio
                                    _voice_parts.append(block_audio)
                                except Exception as blk_tts_exc:
                                    _warn = (
                                        f"Per-block TTS failed for block "
                                        f"{block.index}: {blk_tts_exc}"
                                    )
                                    _warnings.append(_warn)
                                    log.warning(
                                        "per_block_tts_failed",
                                        block=block.index,
                                        error=str(blk_tts_exc),
                                    )
                                    _append_log(db, job, _warn)

                            dur = block_dur if block_dur is not None else _DEFAULT_BLOCK_DURATION_SECONDS

                            # ── Check reuse_previous flag ──────────────────
                            _sb_scene = _storyboard_by_block_id.get(block.id)
                            _reuse = (
                                _sb_scene is not None
                                and _sb_scene.reuse_previous
                                and _last_image_path is not None
                            )

                            if _reuse:
                                # Extend the previous visual segment's duration
                                # rather than generating a new image.
                                reuse_path = _last_image_path
                                block.start_time = _cursor
                                block.end_time = _cursor + dur
                                block.duration = dur
                                block.image_path = reuse_path
                                _cursor += dur
                                if _segments:
                                    # Extend the last segment's duration.
                                    prev = _segments[-1]
                                    _segments[-1] = VisualSegment(
                                        path=prev.path,
                                        start_time=prev.start_time,
                                        end_time=prev.end_time + dur,
                                        duration=prev.duration + dur,
                                        type=prev.type,
                                        scene_id=prev.scene_id,
                                    )
                                else:
                                    seg = VisualSegment(
                                        path=reuse_path,
                                        start_time=block.start_time,
                                        end_time=block.end_time,
                                        duration=dur,
                                        type="image",
                                        scene_id=block.id,
                                    )
                                    _segments.append(seg)
                                log.info(
                                    "ai_image_block_reused",
                                    index=block.index,
                                    reused_path=str(reuse_path),
                                    duration=dur,
                                )
                                continue

                            # ── Per-block AI image ─────────────────────────
                            img_path = image_dir / f"scene_{block.index:03d}.png"
                            try:
                                generated = ai_provider.generate_image(
                                    block.image_prompt,
                                    img_path,
                                    aspect_ratio=settings.AI_IMAGE_ASPECT_RATIO,
                                    metadata={"block_id": block.id},
                                )
                                block.start_time = _cursor
                                block.end_time = _cursor + dur
                                block.duration = dur
                                block.image_path = Path(generated.path)
                                _last_image_path = block.image_path
                                _cursor += dur
                                seg = VisualSegment(
                                    path=Path(generated.path),
                                    start_time=block.start_time,
                                    end_time=block.end_time,
                                    duration=dur,
                                    type="image",
                                    scene_id=block.id,
                                )
                                _segments.append(seg)
                                _scene_logs.append({
                                    "index": block.index,
                                    "text": block.text,
                                    "prompt": block.image_prompt,
                                    "provider": generated.provider,
                                    "image_path": str(generated.path),
                                    "start_time": block.start_time,
                                    "end_time": block.end_time,
                                    "duration": dur,
                                    "block_audio": (
                                        str(block_audio)
                                        if block_dur is not None
                                        else None
                                    ),
                                })
                                log.info(
                                    "ai_image_block_generated",
                                    index=block.index,
                                    text=block.text[:120],
                                    provider=generated.provider,
                                    duration=dur,
                                )
                            except Exception as img_exc:
                                _warn = f"AI image failed for block {block.index}: {img_exc}"
                                _warnings.append(_warn)
                                log.warning(
                                    "ai_image_block_failed",
                                    block=block.index,
                                    error=str(img_exc),
                                )
                                _append_log(db, job, _warn)

                    # Concatenate per-block audio into voice.mp3, replacing any
                    # full-script audio that may have been set in Step 4.
                    if _voice_parts:
                        concat_audio_path = work_dir / "voice.mp3"
                        try:
                            _concat_audio_files(_voice_parts, concat_audio_path)
                            audio_path = concat_audio_path
                            _append_log(
                                db, job,
                                f"Concatenated {len(_voice_parts)} block audio files"
                                f" → {concat_audio_path}",
                            )
                            job.output_metadata = {
                                **(job.output_metadata or {}),
                                "tts_status": "success",
                                "tts_block_count": len(_voice_parts),
                            }
                            db.commit()
                        except Exception as concat_exc:
                            _warn = f"Audio concatenation failed: {concat_exc}"
                            _warnings.append(_warn)
                            log.warning("audio_concat_failed", error=str(concat_exc))
                            _append_log(db, job, _warn)

                    if _segments:
                        visual_segments = _segments
                    else:
                        raise RuntimeError("AI image pipeline produced 0 visual segments")

                    job.output_metadata = {
                        **(job.output_metadata or {}),
                        "media_source": "ai",
                        "ai_provider": ai_provider_name,
                        "ai_image_provider": settings.AI_IMAGE_PROVIDER,
                        "scenes": _scene_logs,
                        "n_scenes": len(_scene_logs),
                        "paragraph_sync": True,
                        "storyboard_enabled": settings.STORYBOARD_PLANNER_ENABLED,
                        "storyboard_provider": (
                            settings.STORYBOARD_PLANNER_PROVIDER
                            if settings.STORYBOARD_PLANNER_ENABLED
                            else None
                        ),
                    }
                    db.commit()
                    _append_log(db, job, f"AI images: {len(_segments)} segments generated")

                else:
                    # ── Existing: stock / hybrid / local path ──────────
                    from worker.modules.stock_media.selector import StockMediaSelector

                    # Build search query from script text → topic → job title
                    search_query = (
                        script_text
                        or _resolve_topic(input_data)
                        or job.title
                    )
                    log.info("stock_media_query", query=search_query, media_mode=settings.MEDIA_MODE)
                    _append_log(db, job, f"Stock media search query: {search_query!r} (mode={settings.MEDIA_MODE})")
                    selector = StockMediaSelector()
                    assets, stock_provider = selector.fetch(
                        query=search_query,
                        count=3,
                        output_dir=str(media_dir),
                    )
                    media_clips = [Path(a.path) for a in assets]
                    clip_paths = [str(p) for p in media_clips]
                    log.info(
                        "stock_media_selected",
                        provider=stock_provider,
                        query=search_query,
                        clips=len(clip_paths),
                        paths=clip_paths,
                    )
                    _append_log(db, job, f"Stock media: {len(media_clips)} clips from {stock_provider!r}")
                    if clip_paths:
                        _append_log(db, job, f"Downloaded clips: {', '.join(clip_paths)}")

                    # Classify media_source for metadata.
                    _ai_providers = {"openai", "stability"}
                    if stock_provider in _ai_providers:
                        _media_source = "ai"
                    elif stock_provider == "placeholder":
                        _media_source = "placeholder"
                    else:
                        _media_source = "stock"

                    # Collect AI-specific metadata (prompts used, provider).
                    _prompts_used = [
                        a.metadata.get("prompt")
                        for a in assets
                        if a.metadata.get("prompt")
                    ]
                    _ai_provider = (
                        assets[0].metadata.get("ai_provider")
                        if assets and assets[0].metadata.get("ai_provider")
                        else None
                    )

                    # Determine warning: Pexels was tried but returned nothing, or only placeholders
                    _stock_warn: str | None = None
                    if settings.PEXELS_API_KEY and stock_provider not in {"pexels"} | _ai_providers:
                        _stock_warn = (
                            f"Pexels key is set but Pexels returned no clips; "
                            f"fell back to {stock_provider!r}."
                        )
                        log.warning("stock_media_pexels_fallback", fallback_provider=stock_provider)
                    elif stock_provider == "placeholder":
                        _stock_warn = "Stock media: no real clips available. Placeholder visuals were used."
                    if _stock_warn:
                        _warnings.append(_stock_warn)

                    _stock_meta: dict = {
                        "stock_provider": stock_provider,
                        "media_source": _media_source,
                        "stock_query": search_query,
                        "stock_clips": clip_paths,
                        "clip_sources": [a.source for a in assets],
                    }
                    if _ai_provider:
                        _stock_meta["ai_provider"] = _ai_provider
                    if _prompts_used:
                        _stock_meta["prompts_used"] = _prompts_used
                    if _stock_warn:
                        _stock_meta["stock_warning"] = _stock_warn
                    job.output_metadata = {**(job.output_metadata or {}), **_stock_meta}
                    db.commit()
            else:
                _append_log(db, job, "Stock media skipped (dry run)")

        # ── Step 6: Captions ───────────────────────────────────────────
        srt_path: Path | None = None
        caption_style = _resolve_caption_style(input_data)

        if caption_style == "none":
            # User explicitly disabled captions – skip Whisper entirely.
            _append_log(db, job, "Captions disabled by user")
            log.info("captions_disabled_by_user")
            job.output_metadata = {
                **(job.output_metadata or {}),
                "caption_status": "disabled",
            }
            db.commit()
        elif flags.is_enabled("captions") and audio_path and not job.dry_run:
            from worker.modules.captions.whisper_provider import WhisperCaptionProvider

            _cap_skip_reason: str | None = None
            if not settings.WHISPER_ENABLED:
                _cap_skip_reason = "Captions skipped: WHISPER_ENABLED=false"
            elif not WhisperCaptionProvider.is_available():
                _cap_skip_reason = (
                    "Captions skipped: faster-whisper is not installed. "
                    "Install it with: pip install faster-whisper"
                )

            if _cap_skip_reason:
                _append_log(db, job, _cap_skip_reason)
                _warnings.append(_cap_skip_reason)
                job.output_metadata = {
                    **(job.output_metadata or {}),
                    "caption_status": "skipped",
                    "caption_warning": _cap_skip_reason,
                }
                db.commit()
            else:
                _append_log(db, job, "Generating captions with Whisper")
                try:
                    caption_provider = WhisperCaptionProvider(
                        model_size=settings.WHISPER_MODEL_SIZE,
                        device=settings.WHISPER_DEVICE,
                    )
                    caption_result = caption_provider.transcribe(str(audio_path), str(work_dir))
                    srt_path = Path(caption_result.srt_path) if caption_result.srt_path else None
                    _append_log(db, job, f"Captions: {srt_path}")
                    job.output_metadata = {
                        **(job.output_metadata or {}),
                        "caption_status": "success",
                    }
                    db.commit()
                except Exception as exc:
                    _cap_warn = f"Captions were skipped: {exc}"
                    _append_log(db, job, f"Captions skipped: {exc}")
                    _warnings.append(_cap_warn)
                    job.output_metadata = {
                        **(job.output_metadata or {}),
                        "caption_status": "failed",
                        "caption_warning": _cap_warn,
                    }
                    db.commit()

        # ── Step 7: Build video ────────────────────────────────────────
        output_path: Path | None = None
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
                _build_kwargs = dict(
                    audio_path=audio_path,
                    srt_path=srt_path,
                    output_path=output_path,
                    use_nvenc=settings.NVIDIA_NVENC_ENABLED,
                    caption_style=caption_style,
                    watermark_path=watermark_path,
                    bg_music_path=bg_music_path,
                )
                if visual_segments is not None:
                    builder.build_from_segments(
                        segments=visual_segments,
                        **_build_kwargs,
                    )
                else:
                    builder.build(
                        clips=media_clips,
                        **_build_kwargs,
                    )
                job.output_metadata = {
                    **(job.output_metadata or {}),
                    "caption_style": caption_style,
                    "watermark_asset_id": watermark_asset_id,
                    "bg_music_asset_id": bg_music_asset_id,
                }
                db.commit()

                # Extract thumbnail from the built video.
                thumbnail_path = output_dir / f"{job_id}_thumb.jpg"
                try:
                    builder.extract_thumbnail(output_path, thumbnail_path)
                    job.output_metadata = {
                        **(job.output_metadata or {}),
                        "thumbnail_path": str(thumbnail_path),
                    }
                    db.commit()
                    _append_log(db, job, f"Thumbnail: {thumbnail_path}")
                except Exception as thumb_exc:
                    _append_log(db, job, f"Thumbnail generation skipped: {thumb_exc}")
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
        _cleanup_work_dir(work_dir, job_id)
        return {"status": "completed", "job_id": job_id}

    except Exception as exc:
        tb = traceback.format_exc()
        if job:
            job.status = JobStatus.failed
            job.error_message = str(exc)
            _append_log(db, job, f"ERROR: {exc}\n{tb}")
            db.commit()
        logger.exception("pipeline_failed", job_id=job_id, error=str(exc))
        # Clean up the work directory unless the operator wants to keep it for debugging.
        if work_dir is not None:
            _cleanup_work_dir(
                work_dir,
                job_id,
                keep=settings.DEBUG_KEEP_FAILED_WORKDIR,
            )
        # Only retry on transient infrastructure errors (network / OS / DB IO).
        # Logic errors (missing binary, bad config, invalid script) should not
        # be retried automatically – they will fail again immediately.
        _RETRY_COUNTDOWN_SECONDS = 60
        if isinstance(exc, (OSError, ConnectionError, TimeoutError)):
            raise self.retry(exc=exc, countdown=_RETRY_COUNTDOWN_SECONDS)
        raise

    finally:
        db.close()
