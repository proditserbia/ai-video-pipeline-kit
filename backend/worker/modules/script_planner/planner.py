from __future__ import annotations

import re
import textwrap
import uuid
from dataclasses import dataclass, field

import structlog

from app.config import settings
from worker.modules.ai_images.prompt_builder import build_image_prompt

logger = structlog.get_logger(__name__)


@dataclass
class ScriptScene:
    """A single timed scene derived from the narration script.

    Attributes:
        id:           Unique identifier for this scene (UUID string).
        index:        Zero-based position in the scene list.
        text:         The portion of the script this scene covers.
        image_prompt: Short, focused visual description for an image generator.
        search_query: Concise keyword phrase for a stock-media search.
        start_time:   Scene start in seconds relative to audio start (``None``
                      when no audio duration is available).
        end_time:     Scene end in seconds (``None`` when not timed).
        duration:     Scene length in seconds (``None`` when not timed).
    """

    id: str
    index: int
    text: str
    image_prompt: str
    search_query: str
    start_time: float | None = None
    end_time: float | None = None
    duration: float | None = None


def plan_script_scenes(
    script_text: str,
    *,
    audio_duration: float | None = None,
    min_seconds: float | None = None,
    max_seconds: float | None = None,
) -> list[ScriptScene]:
    """Convert a narration script into a list of timed :class:`ScriptScene` objects.

    The script is split into sentences and grouped into scenes whose target
    duration sits between *min_seconds* and *max_seconds*.  When
    *audio_duration* is provided, start/end times are assigned so that scenes
    cover the full audio without gaps or overlaps.  Time is distributed
    proportionally by scene text length so that longer passages receive more
    screen time.

    Args:
        script_text:    Full narration text (may be empty).
        audio_duration: Total narration audio length in seconds.  When omitted,
                        scenes are produced but left un-timed.
        min_seconds:    Minimum scene duration; falls back to
                        ``settings.VISUAL_SCENE_MIN_SECONDS``.
        max_seconds:    Maximum scene duration; falls back to
                        ``settings.VISUAL_SCENE_MAX_SECONDS``.

    Returns:
        Ordered list of :class:`ScriptScene` objects.
    """
    min_sec = min_seconds if min_seconds is not None else settings.VISUAL_SCENE_MIN_SECONDS
    max_sec = max_seconds if max_seconds is not None else settings.VISUAL_SCENE_MAX_SECONDS
    # Guard against misconfiguration.
    if min_sec <= 0:
        min_sec = 1.0
    if max_sec < min_sec:
        max_sec = min_sec

    target_sec = (min_sec + max_sec) / 2.0  # e.g. 6.5 s

    sentences = _split_sentences(script_text)
    if not sentences:
        sentences = ["abstract cinematic background"]

    # Determine scene count.
    if audio_duration and audio_duration > 0:
        raw_count = max(1, round(audio_duration / target_sec))
        # Never create so many scenes that any would be shorter than min_sec.
        max_from_duration = max(1, int(audio_duration / min_sec))
        n_scenes = min(raw_count, max_from_duration, len(sentences))
    else:
        n_scenes = len(sentences)

    # Cap to a reasonable maximum to avoid runaway generation.
    n_scenes = min(n_scenes, 20)

    chunks = _group_sentences(sentences, n_scenes)

    # Build scenes, assigning proportional timings when audio_duration is known.
    scenes = _build_scenes(chunks, audio_duration)
    logger.info(
        "script_scenes_planned",
        n_scenes=len(scenes),
        audio_duration=audio_duration,
    )
    return scenes


# ── Internal helpers ──────────────────────────────────────────────────────────

def _split_sentences(text: str) -> list[str]:
    """Split *text* into individual sentences on common terminators."""
    if not text or not text.strip():
        return []
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def _group_sentences(sentences: list[str], n_groups: int) -> list[str]:
    """Distribute *sentences* into exactly *n_groups* text chunks."""
    total = len(sentences)
    chunks: list[str] = []
    for i in range(n_groups):
        start = (i * total) // n_groups
        end = ((i + 1) * total) // n_groups
        if start < end:
            chunk = " ".join(sentences[start:end])
        else:
            chunk = sentences[i % total]
        chunks.append(chunk)
    return chunks


def _make_image_prompt(text: str) -> str:
    """Convert a scene text chunk into a focused visual image prompt.

    Delegates to :func:`~worker.modules.ai_images.prompt_builder.build_image_prompt`
    which strips conversational phrases, avoids quoting narration verbatim, and
    appends the configured negative-prompt suffix so that image models never
    render on-screen text, captions, or speech bubbles.
    """
    return build_image_prompt(text)


def _make_search_query(text: str) -> str:
    """Extract a short keyword phrase suitable for stock-media search."""
    # Take the first sentence and shorten further to a keyword-length phrase.
    first = re.split(r"[.!?,]", text)[0].strip()
    return textwrap.shorten(first, width=60, placeholder="")


def _build_scenes(
    chunks: list[str],
    audio_duration: float | None,
) -> list[ScriptScene]:
    """Construct :class:`ScriptScene` objects with optional proportional timing."""
    total_chars = sum(len(c) for c in chunks) or len(chunks)  # guard zero
    timed = audio_duration is not None and audio_duration > 0

    scenes: list[ScriptScene] = []
    cursor = 0.0
    for i, text in enumerate(chunks):
        if timed:
            if i == len(chunks) - 1:
                # Last scene gets all remaining time to avoid floating-point drift.
                end = float(audio_duration)  # type: ignore[arg-type]
            else:
                fraction = len(text) / total_chars
                end = cursor + fraction * float(audio_duration)  # type: ignore[arg-type]
            dur = end - cursor
            start: float | None = cursor
            end_t: float | None = end
            dur_t: float | None = dur
        else:
            start = end_t = dur_t = None

        scenes.append(
            ScriptScene(
                id=str(uuid.uuid4()),
                index=i,
                text=text,
                image_prompt=_make_image_prompt(text),
                search_query=_make_search_query(text),
                start_time=start,
                end_time=end_t,
                duration=dur_t,
            )
        )
        if timed:
            cursor = float(end_t)  # type: ignore[arg-type]

    return scenes
