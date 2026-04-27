"""Storyboard planner orchestrator.

Provides:
- :func:`plan_storyboard` — main entry point; calls LLM planner with
  deterministic fallback.
- :func:`build_prompt_from_storyboard_scene` — converts a
  :class:`StoryboardScene` into a final image prompt string.

LLM planner flow:
    1. Build cache key from topic + tags + script hash + block hash.
    2. Check in-memory cache (when STORYBOARD_CACHE_ENABLED=True).
    3. On cache miss: call OpenAI with structured JSON schema prompt.
    4. Validate LLM output.
    5. On validation failure: log and use deterministic fallback.
    6. Store result in cache.

Config:
    STORYBOARD_PLANNER_ENABLED  – True activates this layer (default False).
    STORYBOARD_PLANNER_PROVIDER – "openai" | "none" (default "openai").
    STORYBOARD_MODEL            – model name (default "gpt-4o-mini").
    STORYBOARD_CACHE_ENABLED    – True enables in-memory cache (default True).
    STORYBOARD_MIN_BLOCK_SECONDS – merge threshold (default 3.0).
"""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from typing import Any

import structlog

from app.config import settings
from worker.modules.ai_images.prompt_builder import (
    detect_visual_category,
    resolve_visual_subject,
)
from worker.modules.storyboard.fallback import (
    _assemble_image_prompt,
    build_fallback_storyboard,
)
from worker.modules.storyboard.models import StoryboardScene

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# In-memory cache (per-process; cleared on worker restart).
# ---------------------------------------------------------------------------

_STORYBOARD_CACHE: dict[str, list[StoryboardScene]] = {}


def _make_cache_key(
    topic: str,
    visual_tags: list[str],
    script_text: str,
    blocks: list,
    model: str,
) -> str:
    """Build a deterministic cache key that changes when any input changes.

    Args:
        topic:       Video topic.
        visual_tags: Normalised visual tags.
        script_text: Full narration script.
        blocks:      Narration blocks (text used only).
        model:       Storyboard model name / version.

    Returns:
        Hex digest string suitable for use as a dict key.
    """
    block_texts = "|".join(getattr(b, "text", str(b)) for b in blocks)
    raw = f"{topic}|{','.join(sorted(visual_tags))}|{script_text}|{block_texts}|{model}"
    return hashlib.sha256(raw.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def plan_storyboard(
    topic: str,
    visual_tags: list[str],
    script_text: str,
    blocks: list,
) -> list[StoryboardScene]:
    """Build a storyboard for a list of narration blocks.

    When :setting:`STORYBOARD_PLANNER_ENABLED` is ``False`` (the default),
    returns the deterministic fallback storyboard built from
    :func:`~worker.modules.storyboard.fallback.build_fallback_storyboard`.

    When enabled, attempts to call the configured LLM provider.  On any
    failure (API error, invalid JSON, validation failure) the deterministic
    fallback is used so the pipeline never stalls.

    Args:
        topic:       Video topic / title.
        visual_tags: User-supplied visual tags (already normalised to
                     lowercase list).
        script_text: Full narration script text.
        blocks:      Ordered list of :class:`NarrationBlock` objects.

    Returns:
        Ordered list of :class:`StoryboardScene` objects.  Always non-empty
        when *blocks* is non-empty.

    Raises:
        ValueError: When *blocks* is non-empty but the planner produces zero
                    scenes (both LLM and fallback returned empty).
    """
    if not blocks:
        return []

    logger.info(
        "storyboard_planner_start",
        topic=topic,
        visual_tags=visual_tags,
        n_blocks=len(blocks),
        provider=settings.STORYBOARD_PLANNER_PROVIDER,
        enabled=settings.STORYBOARD_PLANNER_ENABLED,
    )

    if not settings.STORYBOARD_PLANNER_ENABLED:
        logger.debug("storyboard_planner_disabled_using_fallback")
        scenes = build_fallback_storyboard(topic, visual_tags, script_text, blocks)
        _check_non_empty(scenes, blocks)
        return scenes

    provider = (settings.STORYBOARD_PLANNER_PROVIDER or "openai").lower()
    logger.info("storyboard_planner_provider", provider=provider)

    if provider == "none":
        logger.info("storyboard_planner_provider_none_using_fallback")
        scenes = build_fallback_storyboard(topic, visual_tags, script_text, blocks)
        _check_non_empty(scenes, blocks)
        return scenes

    if provider == "openai":
        scenes = _plan_with_openai_or_fallback(
            topic, visual_tags, script_text, blocks
        )
        _check_non_empty(scenes, blocks)
        return scenes

    logger.warning(
        "storyboard_planner_unknown_provider",
        provider=provider,
        fallback="deterministic",
    )
    scenes = build_fallback_storyboard(topic, visual_tags, script_text, blocks)
    _check_non_empty(scenes, blocks)
    return scenes


def build_prompt_from_storyboard_scene(scene: StoryboardScene) -> str:
    """Build the final image prompt from a :class:`StoryboardScene`.

    Combines:
    - ``scene.visual_description``
    - Style suffix: *"photorealistic, cinematic lighting, vertical 9:16"*
    - ``scene.negative_prompt``
    - Anti-repetition suffix

    Raw narration text is never appended.

    Args:
        scene: A :class:`StoryboardScene` with a populated
               ``visual_description`` field.

    Returns:
        Complete image prompt string.
    """
    return _assemble_image_prompt(scene.visual_description, scene.negative_prompt)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _check_non_empty(scenes: list[StoryboardScene], blocks: list) -> None:
    """Raise if *blocks* is non-empty but *scenes* is empty."""
    if blocks and not scenes:
        raise ValueError("Storyboard planner produced 0 scenes")


def _plan_with_openai_or_fallback(
    topic: str,
    visual_tags: list[str],
    script_text: str,
    blocks: list,
) -> list[StoryboardScene]:
    """Attempt LLM storyboard generation; fall back on any error."""
    model = settings.STORYBOARD_MODEL or "gpt-4o-mini"

    # --- Cache check ---
    cache_key = _make_cache_key(topic, visual_tags, script_text, blocks, model)
    if settings.STORYBOARD_CACHE_ENABLED and cache_key in _STORYBOARD_CACHE:
        cached = _STORYBOARD_CACHE[cache_key]
        logger.info(
            "storyboard_cache_hit",
            cache_key=cache_key[:16],
            n_scenes=len(cached),
        )
        return cached

    logger.info("storyboard_cache_miss", cache_key=cache_key[:16])

    # --- LLM call ---
    if not settings.OPENAI_API_KEY:
        logger.warning("storyboard_planner_no_api_key_using_fallback")
        return build_fallback_storyboard(topic, visual_tags, script_text, blocks)

    try:
        raw_scenes = _call_openai(topic, visual_tags, script_text, blocks, model)
    except Exception as exc:
        logger.warning(
            "storyboard_llm_call_failed",
            error=str(exc),
            fallback="deterministic",
            exc_info=True,
        )
        logger.info("storyboard_fallback_used", reason="llm_call_failed")
        return build_fallback_storyboard(topic, visual_tags, script_text, blocks)

    # --- Validation ---
    subject, _ = resolve_visual_subject(topic, visual_tags=visual_tags)
    category = detect_visual_category(topic, visual_tags=visual_tags)
    validation_errors = _validate_llm_output(
        raw_scenes, blocks, subject, visual_tags
    )
    if validation_errors:
        logger.warning(
            "storyboard_validation_failed",
            errors=validation_errors,
            n_raw_scenes=len(raw_scenes),
            n_blocks=len(blocks),
        )
        logger.info("storyboard_fallback_used", reason="validation_failed")
        return build_fallback_storyboard(topic, visual_tags, script_text, blocks)

    logger.info(
        "storyboard_llm_response_valid",
        n_scenes=len(raw_scenes),
        model=model,
    )

    # --- Convert to StoryboardScene objects ---
    negative = settings.AI_IMAGE_NEGATIVE_PROMPT
    scenes = _convert_llm_output(
        raw_scenes, blocks, subject, category, negative
    )

    # --- Cache store ---
    if settings.STORYBOARD_CACHE_ENABLED:
        _STORYBOARD_CACHE[cache_key] = scenes

    return scenes


def _call_openai(
    topic: str,
    visual_tags: list[str],
    script_text: str,
    blocks: list,
    model: str,
) -> list[dict[str, Any]]:
    """Call OpenAI Chat API and return parsed JSON array.

    Raises:
        RuntimeError: On API failure or unparseable response.
    """
    from openai import OpenAI

    tags_str = ", ".join(visual_tags) if visual_tags else "none"
    blocks_summary = "\n".join(
        f"Block {getattr(b, 'index', i)}: {getattr(b, 'text', str(b))[:300]}"
        for i, b in enumerate(blocks)
    )
    subject, _ = resolve_visual_subject(topic, visual_tags=visual_tags)

    system_msg = (
        "You are a professional storyboard artist for short-form vertical social videos. "
        "Your job is to create a concrete, story-specific visual storyboard from a "
        "narration script. "
        "Each scene must describe a SPECIFIC visual moment that matches the narration "
        "block — never a generic category description. "
        "Use the topic, visual_tags, and script to produce scene descriptions that are "
        "visually concrete, varied in composition, and story-specific. "
        "Respond ONLY with a valid JSON array — no markdown, no commentary."
    )

    word_count = len(script_text.split())
    short_block_hint = (
        "If a block is very short (outro only, e.g. 'Happy Groundhog Day!'), "
        "set \"reuse_previous\": true and omit visual_description. "
    )

    user_msg = (
        f"Create a visual storyboard for a short vertical video.\n\n"
        f"Topic: {topic}\n"
        f"Resolved subject: {subject}\n"
        f"Visual tags (hard constraints): {tags_str}\n\n"
        f"Full script ({word_count} words):\n{script_text[:1500]}\n\n"
        f"Narration blocks:\n{blocks_summary}\n\n"
        f"Respond with a JSON array — one object per block:\n"
        f"[\n"
        f"  {{\n"
        f'    "block_index": 0,\n'
        f'    "shot_type": "establishing",\n'
        f'    "visual_description": "Wide establishing shot of a Groundhog Day festival '
        f'in Punxsutawney, bundled-up crowd near a ceremony stage, winter morning",\n'
        f'    "context_terms": ["festival", "crowd", "winter"],\n'
        f'    "visual_tags_used": ["festival", "crowd"],\n'
        f'    "subject": "{subject}",\n'
        f'    "reuse_previous": false\n'
        f"  }}\n"
        f"]\n\n"
        f"Rules:\n"
        f"1. Every visual_description MUST be concrete and scene-specific.\n"
        f"2. Use different shot_type values across scenes for visual variety.\n"
        f"   Valid values: establishing, medium, crowd_reaction, detail, closing, "
        f"action, wide, portrait.\n"
        f"3. The subject '{subject}' must appear in EVERY visual_description.\n"
        f"4. Use ALL visual_tags ({tags_str}) as hard visual constraints — include "
        f"them in scene descriptions.\n"
        f"5. Do NOT write generic descriptions like 'animal in nature', "
        f"'business environment', 'technology concept'.\n"
        f"6. Do NOT include 'No text', 'no captions', or any negative-prompt "
        f"instructions in visual_description — those are NOT your job.\n"
        f"7. Do NOT copy raw narration text verbatim into visual_description.\n"
        f"8. {short_block_hint}\n"
        f"9. Keep visual_description under 200 characters, concrete and visual.\n"
    )

    client = OpenAI(
        api_key=settings.OPENAI_API_KEY,
        base_url=settings.OPENAI_BASE_URL,
    )

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.7,
        max_tokens=2500,
    )

    raw = (response.choices[0].message.content or "").strip()

    # Strip markdown code fences if present.
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    json_match = re.search(r"\[.*\]", raw, re.DOTALL)
    if not json_match:
        raise RuntimeError(
            f"LLM returned no JSON array. Preview: {raw[:200]!r}"
        )

    return json.loads(json_match.group())


# Generic phrases that indicate a scene description is too vague.
_GENERIC_PHRASES: list[str] = [
    "animal in nature",
    "animal in its natural habitat",
    "in natural habitat",
    "in its natural habitat",
    "natural habitat",
    "business environment",
    "technology concept",
    "science concept",
    "abstract concept",
    "generic background",
    "typical scene",
    "standard shot",
    "foraging or eating",
    "near burrow",
    "near its burrow",
    "near its home",
]


def _is_generic_description(desc: str, visual_tags: list[str]) -> bool:
    """Return True when *desc* is too generic given available context.

    A description is considered too generic when it matches a known generic
    phrase AND there are visual tags / context available that should have
    produced something more specific.

    Args:
        desc:        Visual description string.
        visual_tags: Available visual tags (if any, the description should
                     reflect them).

    Returns:
        True when the description is too generic to accept.
    """
    if not visual_tags:
        # Without tags there is no context to require specificity.
        return False
    desc_lower = desc.lower()
    return any(ph in desc_lower for ph in _GENERIC_PHRASES)


def _validate_llm_output(
    raw_scenes: list[dict[str, Any]],
    blocks: list,
    subject: str,
    visual_tags: list[str],
) -> list[str]:
    """Validate LLM output; return list of error strings (empty = valid).

    Validation rules:
    1. Must parse to a non-empty list.
    2. Length must match number of usable blocks (± reuse_previous).
    3. Every scene (not reuse_previous) must include the subject when specific.
    4. No scene may use a generic description when context/tags exist.
    5. Every scene must have a non-empty visual_description (unless
       reuse_previous=True).

    Args:
        raw_scenes:  Parsed JSON list from LLM.
        blocks:      Narration blocks.
        subject:     Resolved visual subject.
        visual_tags: Available visual tags.

    Returns:
        List of human-readable error messages; empty list means valid.
    """
    errors: list[str] = []

    if not raw_scenes:
        errors.append("LLM returned empty scene list")
        return errors

    # Allow ± 1 scene compared to blocks (LLM may merge or split one block).
    n_usable = sum(
        1 for s in raw_scenes if not s.get("reuse_previous", False)
    )
    n_total = len(raw_scenes)
    n_blocks = len(blocks)
    if abs(n_total - n_blocks) > max(1, n_blocks // 3):
        errors.append(
            f"Scene count mismatch: {n_total} scenes for {n_blocks} blocks "
            f"(tolerance ± {max(1, n_blocks // 3)})"
        )

    subject_lower = subject.lower() if subject else ""
    _generic_subjects = {"abstract cinematic scene", "scene"}

    for item in raw_scenes:
        if item.get("reuse_previous", False):
            continue
        desc = (item.get("visual_description") or "").strip()
        if not desc:
            errors.append(
                f"Block {item.get('block_index')}: empty visual_description"
            )
            continue

        # Subject check — skip for fully generic subjects.
        if (
            subject_lower
            and subject_lower not in _generic_subjects
            and subject_lower not in desc.lower()
        ):
            errors.append(
                f"Block {item.get('block_index')}: subject '{subject}' "
                f"missing from visual_description: {desc[:80]!r}"
            )

        # Generic description check.
        if _is_generic_description(desc, visual_tags):
            errors.append(
                f"Block {item.get('block_index')}: generic description detected "
                f"despite context tags {visual_tags}: {desc[:80]!r}"
            )

    return errors


def _convert_llm_output(
    raw_scenes: list[dict[str, Any]],
    blocks: list,
    subject: str,
    category: str,
    negative: str,
) -> list[StoryboardScene]:
    """Convert validated LLM JSON items to :class:`StoryboardScene` objects.

    Aligns each LLM item to its corresponding narration block by
    ``block_index``.  When a block is missing from the LLM output (e.g.
    the LLM merged two blocks), it is silently skipped (the fallback will
    have been invoked by the validator in that case).

    Args:
        raw_scenes: Validated parsed JSON from LLM.
        blocks:     Narration blocks.
        subject:    Resolved visual subject.
        category:   Detected visual category.
        negative:   Negative-prompt string.

    Returns:
        Ordered list of :class:`StoryboardScene` objects.
    """
    # Build a map from block.index to block for fast look-up.
    block_map = {getattr(b, "index", i): b for i, b in enumerate(blocks)}

    scenes: list[StoryboardScene] = []
    for item in raw_scenes:
        idx = int(item.get("block_index", 0))
        block = block_map.get(idx)
        narration_text = getattr(block, "text", "") if block else ""
        block_id = getattr(block, "id", str(uuid.uuid4())) if block else str(uuid.uuid4())

        reuse = bool(item.get("reuse_previous", False))

        if reuse:
            # No new image — reuse previous segment.
            image_prompt = ""
            visual_description = ""
        else:
            visual_description = (item.get("visual_description") or "").strip()
            # Safety: strip any negative-prompt instructions if LLM leaked them.
            visual_description = re.sub(
                r"(?i)(no text|no captions|no subtitles|no typography|no logos|"
                r"no signs|no labels|no speech bubbles|no readable)[^.]*\.?\s*",
                "",
                visual_description,
            ).strip()

            # Ensure subject is present.
            if subject and subject.lower() not in visual_description.lower():
                visual_description = f"{visual_description}, {subject}"

            image_prompt = _assemble_image_prompt(visual_description, negative)

        context_terms = list(item.get("context_terms") or [])
        tags_used = list(item.get("visual_tags_used") or [])

        scene = StoryboardScene(
            id=str(uuid.uuid4()),
            index=idx,
            narration_block_id=block_id,
            narration_text=narration_text,
            shot_type=str(item.get("shot_type", "establishing")),
            visual_description=visual_description,
            image_prompt=image_prompt,
            negative_prompt=negative,
            subject=subject,
            category=category,
            context_terms=context_terms,
            visual_tags_used=tags_used,
            start_time=getattr(block, "start_time", None) if block else None,
            end_time=getattr(block, "end_time", None) if block else None,
            duration=getattr(block, "duration", None) if block else None,
            source="llm",
            reuse_previous=reuse,
        )
        scenes.append(scene)

        logger.info(
            "storyboard_scene_created",
            block_index=idx,
            shot_type=scene.shot_type,
            subject=subject,
            category=category,
            visual_tags_used=tags_used,
            context_terms=context_terms,
            source="llm",
            visual_description=visual_description[:150],
            final_image_prompt=image_prompt[:150],
            reuse_previous=reuse,
        )

    return scenes
