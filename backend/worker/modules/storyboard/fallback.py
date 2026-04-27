"""Deterministic fallback storyboard planner.

Used when:
- STORYBOARD_PLANNER_PROVIDER is "none"
- The LLM call fails or returns invalid JSON
- LLM output fails validation

Generates storyboard scenes using:
- :func:`~worker.modules.ai_images.prompt_builder.extract_visual_context`
  for context extraction from block text + visual tags + script
- :func:`~worker.modules.ai_images.prompt_builder.resolve_visual_subject`
  for subject grounding
- :func:`~worker.modules.ai_images.prompt_builder.detect_visual_category`
  for category-aware shot plans
- :func:`~worker.modules.ai_images.prompt_builder._build_context_aware_prompt`
  for context-enriched visual descriptions when event/crowd/location context
  is present, falling back to the category-plan template when not

The fallback never returns generic prompts if visual_tags or context exist.
"""
from __future__ import annotations

import uuid

import structlog

from app.config import settings
from worker.modules.ai_images.prompt_builder import (
    _CATEGORY_PLANS,
    _build_context_aware_prompt,
    _build_shot_plan_prompt,
    detect_visual_category,
    extract_visual_context,
    resolve_visual_subject,
)
from worker.modules.storyboard.models import StoryboardScene

logger = structlog.get_logger(__name__)

# Style suffix appended to every visual_description to produce the final prompt.
_STYLE_SUFFIX = "photorealistic, cinematic lighting, vertical 9:16"

# Anti-repetition suffix.
_ANTI_REPETITION = (
    "Use a distinct framing and composition from previous images in this set."
)


def build_fallback_storyboard(
    topic: str,
    visual_tags: list[str],
    script_text: str,
    blocks: list,
) -> list[StoryboardScene]:
    """Build a deterministic storyboard from narration blocks.

    Produces one :class:`StoryboardScene` per block.  Context-enriched
    descriptions are generated when event/crowd/location context is detected;
    otherwise the category-plan template is used.

    Args:
        topic:       Video topic / title.
        visual_tags: User-supplied visual tags (already normalised).
        script_text: Full narration script for global context.
        blocks:      List of :class:`NarrationBlock` objects.

    Returns:
        Ordered list of :class:`StoryboardScene` objects.
    """
    if not blocks:
        return []

    negative = settings.AI_IMAGE_NEGATIVE_PROMPT
    subject, _ = resolve_visual_subject(topic, visual_tags=visual_tags)
    category = detect_visual_category(topic, visual_tags=visual_tags)
    plan = _CATEGORY_PLANS.get(category, _CATEGORY_PLANS["general"])
    total = len(blocks)

    scenes: list[StoryboardScene] = []
    for block in blocks:
        shot_idx = block.index % len(plan)
        shot_type, template = plan[shot_idx]

        # Extract context for this specific block.
        ctx = extract_visual_context(
            block.text,
            visual_tags,
            topic,
            full_script_text=script_text,
        )
        context_terms: list[str] = ctx.get("context_terms", [])

        # Determine which visual_tags were actually relevant for this block.
        tags_lower_set = {t.lower() for t in visual_tags}
        block_lower = block.text.lower()
        ctx_term_lower = {t.lower() for t in context_terms}
        tags_used = [
            t for t in visual_tags
            if t.lower() in ctx_term_lower
            or t.lower() in block_lower
        ]

        # Try context-enriched description first; fall back to template.
        enriched = _build_context_aware_prompt(shot_type, subject, ctx)
        if enriched is not None:
            visual_description = enriched
        else:
            visual_description = template.format(subject=subject)

        # Ensure subject appears in the description.
        if subject and subject.lower() not in visual_description.lower():
            visual_description = f"{visual_description}, {subject} visible"

        image_prompt = _assemble_image_prompt(visual_description, negative)

        scene = StoryboardScene(
            id=str(uuid.uuid4()),
            index=block.index,
            narration_block_id=block.id,
            narration_text=block.text,
            shot_type=shot_type,
            visual_description=visual_description,
            image_prompt=image_prompt,
            negative_prompt=negative,
            subject=subject,
            category=category,
            context_terms=context_terms,
            visual_tags_used=tags_used,
            start_time=getattr(block, "start_time", None),
            end_time=getattr(block, "end_time", None),
            duration=getattr(block, "duration", None),
            source="fallback",
            reuse_previous=False,
        )
        scenes.append(scene)

        logger.info(
            "storyboard_scene_created",
            block_index=block.index,
            shot_type=shot_type,
            subject=subject,
            category=category,
            visual_tags_used=tags_used,
            context_terms=context_terms,
            source="fallback",
            visual_description=visual_description[:150],
            final_image_prompt=image_prompt[:150],
            reuse_previous=False,
        )

    return scenes


def _assemble_image_prompt(visual_description: str, negative_prompt: str) -> str:
    """Combine visual description, style suffix, negative prompt, and anti-repetition.

    Args:
        visual_description: The concrete visual scene description (no negative
                             instructions).
        negative_prompt:    The negative-prompt string.

    Returns:
        Complete image prompt ready for the image model.
    """
    # Capitalise first letter of the description.
    desc = visual_description[:1].upper() + visual_description[1:]
    return (
        f"{desc}, {_STYLE_SUFFIX}. "
        f"{negative_prompt} "
        f"{_ANTI_REPETITION}"
    )
