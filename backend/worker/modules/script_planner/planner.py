from __future__ import annotations

import re
import textwrap
import uuid
from dataclasses import dataclass, field
from pathlib import Path

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


@dataclass
class NarrationBlock:
    """A semantic narration block that pairs exactly one TTS audio file with one AI image.

    Audio and image paths, along with timing fields, are populated by the
    pipeline during processing and are ``None`` until assigned.

    Attributes:
        id:           Unique identifier (UUID string).
        index:        Zero-based position in the block list.
        text:         The narration text covered by this block.
        image_prompt: Short visual description for the AI image generator.
        audio_path:   Path to the per-block TTS MP3 (set after TTS generation).
        image_path:   Path to the generated image (set after image generation).
        start_time:   Block start in seconds relative to the video start.
        end_time:     Block end in seconds.
        duration:     Exact block length derived from the per-block audio file.
    """

    id: str
    index: int
    text: str
    image_prompt: str
    audio_path: Path | None = field(default=None)
    image_path: Path | None = field(default=None)
    start_time: float | None = field(default=None)
    end_time: float | None = field(default=None)
    duration: float | None = field(default=None)


def plan_script_scenes(
    script_text: str,
    *,
    audio_duration: float | None = None,
    min_seconds: float | None = None,
    max_seconds: float | None = None,
    topic: str = "",
    visual_tags: list[str] | None = None,
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
    scenes = _build_scenes(
        chunks, audio_duration,
        topic=topic, visual_tags=visual_tags,
        full_script_text=script_text,
    )
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


def _make_image_prompt(
    text: str,
    topic: str = "",
    *,
    block_index: int = 0,
    total_blocks: int = 1,
    previous_prompts: list[str] | None = None,
    visual_tags: list[str] | None = None,
    full_script_text: str | None = None,
) -> str:
    """Convert a scene text chunk into a focused visual image prompt.

    Delegates to :func:`~worker.modules.ai_images.prompt_builder.build_image_prompt`
    which strips conversational phrases, avoids quoting narration verbatim, and
    appends the configured negative-prompt suffix so that image models never
    render on-screen text, captions, or speech bubbles.
    """
    return build_image_prompt(
        text,
        topic,
        block_index=block_index,
        total_blocks=total_blocks,
        previous_prompts=previous_prompts,
        visual_tags=visual_tags,
        full_script_text=full_script_text,
    )


def _make_search_query(text: str) -> str:
    """Extract a short keyword phrase suitable for stock-media search."""
    # Take the first sentence and shorten further to a keyword-length phrase.
    first = re.split(r"[.!?,]", text)[0].strip()
    return textwrap.shorten(first, width=60, placeholder="")


def _build_scenes(
    chunks: list[str],
    audio_duration: float | None,
    topic: str = "",
    visual_tags: list[str] | None = None,
    full_script_text: str | None = None,
) -> list[ScriptScene]:
    """Construct :class:`ScriptScene` objects with optional proportional timing."""
    total_chars = sum(len(c) for c in chunks) or len(chunks)  # guard zero
    timed = audio_duration is not None and audio_duration > 0

    total = len(chunks)
    previous_prompts: list[str] = []
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

        prompt = _make_image_prompt(
            text,
            topic,
            block_index=i,
            total_blocks=total,
            previous_prompts=previous_prompts,
            visual_tags=visual_tags,
            full_script_text=full_script_text,
        )
        previous_prompts.append(prompt)

        scenes.append(
            ScriptScene(
                id=str(uuid.uuid4()),
                index=i,
                text=text,
                image_prompt=prompt,
                search_query=_make_search_query(text),
                start_time=start,
                end_time=end_t,
                duration=dur_t,
            )
        )
        if timed:
            cursor = float(end_t)  # type: ignore[arg-type]

    return scenes


# ── NarrationBlock helpers ────────────────────────────────────────────────────

# First words (lowercased) that signal a short conversational opener.
_CONVERSATIONAL_OPENERS: frozenset[str] = frozenset({
    "hey", "hi", "hello", "well", "now", "so", "alright", "okay", "ok",
    "great", "good", "right", "sure", "yes", "no", "wait", "listen",
    "look", "see", "think", "remember", "note", "here", "there",
    "let", "let's", "here's",
})

# Blocks shorter than this many characters are candidates for merging.
_MIN_BLOCK_CHARS: int = 60

# Maximum word count for a block to still be considered a conversational opener.
_MAX_CONVERSATIONAL_WORDS: int = 8

# Placeholder text used when no script content is available.
_DEFAULT_NARRATION_TEXT: str = "abstract cinematic background"


def _split_paragraphs(text: str) -> list[str]:
    """Split *text* on one or more blank lines into paragraphs."""
    if not text or not text.strip():
        return []
    parts = re.split(r"\n\s*\n", text.strip())
    return [p.strip() for p in parts if p.strip()]


def _is_short_conversational(text: str) -> bool:
    """Return ``True`` when *text* is a short conversational filler.

    A block qualifies when it is below ``_MIN_BLOCK_CHARS`` characters *and*
    its first word is a known conversational opener with at most
    ``_MAX_CONVERSATIONAL_WORDS`` words total.
    """
    stripped = text.strip().rstrip(".!?,;")
    if len(stripped) >= _MIN_BLOCK_CHARS:
        return False
    words = stripped.lower().split()
    if not words:
        return True
    return words[0] in _CONVERSATIONAL_OPENERS and len(words) <= _MAX_CONVERSATIONAL_WORDS


def _merge_short_blocks(blocks: list[str]) -> list[str]:
    """Merge short conversational opener blocks into the following block.

    When a block is detected as a short conversational filler it is held as
    *pending* and prepended to the next block.  If the last block is also a
    short filler it is appended to the preceding result (or kept solo when
    there is no preceding result).
    """
    if len(blocks) <= 1:
        return list(blocks)

    result: list[str] = []
    pending: str = ""
    for block in blocks:
        if pending:
            # Pending opener: merge unconditionally and emit without re-check.
            result.append(pending + " " + block)
            pending = ""
        elif _is_short_conversational(block):
            pending = block
        else:
            result.append(block)

    # Dangling short opener at the end.
    if pending:
        if result:
            result[-1] = result[-1] + " " + pending
        else:
            result.append(pending)

    return result


# Absolute minimum word count per block regardless of speaking rate.
# Prevents over-merging when speech is slower than average (130 wpm).
_MIN_BLOCK_WORDS_FLOOR: int = 5


def _compute_min_block_words() -> int:
    """Derive the minimum word count per block from ``MIN_VISUAL_BLOCK_SECONDS``.

    Assumes an average speaking rate of ~130 words per minute.  A block with
    fewer words than this threshold is too short to justify its own image slot.
    """
    # 130 wpm → ~2.17 words/sec.
    words_per_second = 130.0 / 60.0
    return max(_MIN_BLOCK_WORDS_FLOOR, int(settings.MIN_VISUAL_BLOCK_SECONDS * words_per_second))


def _merge_ultra_short_text_blocks(blocks: list[str]) -> list[str]:
    """Merge any block whose word count falls below the minimum threshold.

    This catches outro-style blocks like *"Happy Groundhog Day, everyone!"*
    that are too short to generate useful TTS audio or a meaningful AI image.
    Short blocks are merged into the **preceding** block.  If the first block
    is too short it is prepended to the next block instead.

    The minimum word threshold is derived from
    :func:`_compute_min_block_words` and ultimately from
    ``settings.MIN_VISUAL_BLOCK_SECONDS``.

    Args:
        blocks: List of raw paragraph strings.

    Returns:
        New list with ultra-short blocks merged into their neighbours.
    """
    if len(blocks) <= 1:
        return list(blocks)

    min_words = _compute_min_block_words()
    result: list[str] = []

    for block in blocks:
        words = block.strip().split()
        if result and len(words) < min_words:
            # Merge with preceding block.
            result[-1] = result[-1] + " " + block
            logger.debug(
                "ultra_short_block_merged",
                merged_text=block[:60],
                min_words=min_words,
                actual_words=len(words),
            )
        else:
            result.append(block)

    # Edge case: first block too short and no preceding block.
    # Re-check: if result[0] is still short and there's a following one, merge.
    if len(result) >= 2 and len(result[0].strip().split()) < min_words:
        result[1] = result[0] + " " + result[1]
        result.pop(0)

    return result


def plan_narration_blocks(
    script_text: str,
    topic: str = "",
    visual_tags: list[str] | None = None,
) -> list[NarrationBlock]:
    """Split *script_text* into semantic :class:`NarrationBlock` objects.

    **Splitting strategy**:

    1. Prefer blank-line-separated paragraphs.  These map naturally to
       semantic breaks the author already chose.
    2. Fall back to grouping sentences into pairs (~5–10 s @ 130 wpm) when
       the script has no paragraph breaks.
    3. Merge short conversational opener blocks (e.g. *"Hey there, friends!"*)
       into the following block so no block is too short to generate meaningful
       TTS audio or a useful AI image.
    4. Merge any remaining ultra-short blocks (word count below the threshold
       derived from ``MIN_VISUAL_BLOCK_SECONDS``) into the preceding block to
       avoid wasting an expensive image generation slot on a brief outro phrase
       like *"Happy Groundhog Day, everyone!"*.

    Args:
        script_text:  Full narration text (may be empty).
        topic:        Optional global topic / title used by the shot-plan
                      system to build visually varied prompts.
        visual_tags:  Optional list of explicit visual tags supplied by the
                      user (e.g. ``["architecture", "soldiers"]``).  Passed
                      through to :func:`build_image_prompt` for category
                      detection and subject extraction.

    Returns:
        Ordered list of :class:`NarrationBlock` objects (at least one).
    """
    paragraphs = _split_paragraphs(script_text)

    # Fall back to sentence-based grouping when there are no paragraph breaks.
    if len(paragraphs) <= 1:
        sentences = _split_sentences(script_text)
        if not sentences:
            sentences = [_DEFAULT_NARRATION_TEXT]
        # Target ~2 sentences per block (≈5–10 s at an average speaking rate).
        n_blocks = max(1, len(sentences) // 2)
        paragraphs = _group_sentences(sentences, n_blocks)

    # Merge short conversational fillers into their following block.
    paragraphs = _merge_short_blocks(paragraphs)

    # Merge any remaining blocks that are too short for a meaningful image slot.
    paragraphs = _merge_ultra_short_text_blocks(paragraphs)

    if not paragraphs:
        paragraphs = [_DEFAULT_NARRATION_TEXT]

    total = len(paragraphs)
    previous_prompts: list[str] = []
    blocks: list[NarrationBlock] = []
    for i, text in enumerate(paragraphs):
        prompt = _make_image_prompt(
            text,
            topic,
            block_index=i,
            total_blocks=total,
            previous_prompts=previous_prompts,
            visual_tags=visual_tags,
            full_script_text=script_text,
        )
        previous_prompts.append(prompt)
        blocks.append(
            NarrationBlock(
                id=str(uuid.uuid4()),
                index=i,
                text=text,
                image_prompt=prompt,
            )
        )

    logger.info("narration_blocks_planned", n_blocks=len(blocks))
    return blocks
