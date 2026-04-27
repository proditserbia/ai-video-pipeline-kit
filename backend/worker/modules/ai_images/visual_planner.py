"""Optional LLM-based visual prompt planner.

When ``AI_VISUAL_PLANNER_ENABLED=True`` and
``AI_VISUAL_PLANNER_PROVIDER=openai``, this module generates context-aware
visual briefs for *all* narration blocks in a **single LLM call** before
image generation begins.

This is **NOT** image generation — it only produces better image prompts.

Configuration:
    AI_VISUAL_PLANNER_ENABLED  – True | False (default False).
    AI_VISUAL_PLANNER_PROVIDER – "openai" | "none" (default "openai").

The planner is disabled by default for backward compatibility.  Set
``AI_VISUAL_PLANNER_ENABLED=true`` to activate AI-assisted visual planning.

Output schema per block:
    {
      "block_index": 0,
      "shot_type": "establishing",
      "visual_prompt": "...",
      "negative_prompt": "No text, ..."
    }
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

import structlog

from app.config import settings

logger = structlog.get_logger(__name__)


@dataclass
class VisualBrief:
    """AI-generated visual brief for a single narration block.

    Attributes:
        block_index:     Zero-based block position.
        shot_type:       Composition hint (e.g. ``"establishing"``,
                         ``"medium"``, ``"crowd_reaction"``).
        visual_prompt:   The visual scene description to send to the image
                         model.  Must NOT contain "No text" / caption /
                         negative instructions — those belong in
                         ``negative_prompt``.
        negative_prompt: Negative-prompt string to suppress text, logos, and
                         UI elements in the generated image.
    """

    block_index: int
    shot_type: str
    visual_prompt: str
    negative_prompt: str


def plan_visual_briefs(
    topic: str,
    visual_tags: list[str],
    script_text: str,
    blocks: list,
) -> list[VisualBrief] | None:
    """Generate context-aware visual briefs for all narration blocks.

    When the visual planner is disabled (``AI_VISUAL_PLANNER_ENABLED=False``)
    or the provider is ``"none"``, returns ``None`` immediately and the
    caller falls back to the deterministic prompt builder.

    Args:
        topic:       Video topic / title.
        visual_tags: User-supplied visual tags.
        script_text: Full narration script.
        blocks:      List of ``NarrationBlock`` objects (must have ``.index``
                     and ``.text`` attributes).

    Returns:
        Ordered list of :class:`VisualBrief` objects, or ``None`` on
        disabled/error.
    """
    if not settings.AI_VISUAL_PLANNER_ENABLED:
        logger.debug("ai_visual_planner_disabled")
        return None

    provider = (settings.AI_VISUAL_PLANNER_PROVIDER or "openai").lower()
    if provider == "none":
        logger.debug("ai_visual_planner_provider_none")
        return None

    if provider == "openai":
        return _plan_with_openai(topic, visual_tags, script_text, blocks)

    logger.warning(
        "ai_visual_planner_unknown_provider",
        provider=provider,
    )
    return None


def _plan_with_openai(
    topic: str,
    visual_tags: list[str],
    script_text: str,
    blocks: list,
) -> list[VisualBrief] | None:
    """Call the OpenAI Chat API to generate visual briefs.

    Uses ``gpt-4o-mini`` by default for cost efficiency.  Returns ``None``
    if the API key is missing or the call fails.
    """
    if not settings.OPENAI_API_KEY:
        logger.warning("ai_visual_planner_no_api_key")
        return None

    negative = settings.AI_IMAGE_NEGATIVE_PROMPT
    tags_str = ", ".join(visual_tags) if visual_tags else "none"
    blocks_summary = "\n".join(
        f"Block {b.index}: {b.text[:300]}" for b in blocks
    )

    system_msg = (
        "You are a visual prompt engineer for AI video generation. "
        "Your job is to write specific, story-aware image prompts for each "
        "narration block. Use the script context, visual tags, and block text "
        "to create scene-specific descriptions. "
        "Do NOT use generic habitat descriptions when the context is an event "
        "or festival. "
        "Vary shot types across blocks for visual diversity. "
        "Respond ONLY with a valid JSON array — no markdown, no commentary."
    )

    user_msg = (
        f"Generate visual image prompts for a short vertical social video.\n\n"
        f"Topic: {topic}\n"
        f"Visual tags: {tags_str}\n\n"
        f"Full script (up to 1000 chars):\n{script_text[:1000]}\n\n"
        f"Narration blocks:\n{blocks_summary}\n\n"
        f'Respond with a JSON array. One object per block:\n'
        f'[\n'
        f'  {{\n'
        f'    "block_index": 0,\n'
        f'    "shot_type": "establishing",\n'
        f'    "visual_prompt": "...",\n'
        f'    "negative_prompt": "{negative}"\n'
        f'  }}\n'
        f']\n\n'
        f"Rules:\n"
        f"- Use event/ceremony context if visual_tags include festival/ceremony/event\n"
        f"- Include named locations and specific entities from the script\n"
        f"- Vary shot types: establishing, medium, crowd_reaction, detail, closing\n"
        f"- Every prompt must be specific to the actual story, NOT generic\n"
        f"- The visual_prompt field must NOT contain 'No text' or negative instructions\n"
        f"- 'No text' / negative instructions belong ONLY in negative_prompt\n"
        f"- All prompts must specify vertical 9:16 format\n"
        f"- Add 'photorealistic vertical 9:16' at the end of every visual_prompt\n"
    )

    try:
        from openai import OpenAI

        client = OpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_BASE_URL,
        )

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.7,
            max_tokens=2000,
        )

        raw = response.choices[0].message.content or ""
        raw = raw.strip()

        # Strip markdown code fences if present.
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)

        json_match = re.search(r"\[.*\]", raw, re.DOTALL)
        if not json_match:
            logger.warning(
                "ai_visual_planner_no_json",
                raw_preview=raw[:200],
            )
            return None

        data = json.loads(json_match.group())

        briefs: list[VisualBrief] = []
        for item in data:
            visual_prompt = item.get("visual_prompt", "").strip()
            # Safety: strip negative-prompt phrases from the visual_prompt
            # field if the LLM accidentally included them there.
            if visual_prompt.lower().startswith("no text"):
                logger.warning(
                    "ai_visual_planner_negative_in_visual_prompt",
                    block_index=item.get("block_index"),
                    visual_prompt_preview=visual_prompt[:80],
                )
                visual_prompt = re.sub(
                    r"^(no text[^.]*\.\s*)+",
                    "",
                    visual_prompt,
                    flags=re.IGNORECASE,
                ).strip()

            briefs.append(
                VisualBrief(
                    block_index=int(item.get("block_index", 0)),
                    shot_type=str(item.get("shot_type", "establishing")),
                    visual_prompt=visual_prompt,
                    negative_prompt=str(item.get("negative_prompt", negative)),
                )
            )

        logger.info(
            "ai_visual_planner_success",
            n_briefs=len(briefs),
            topic=topic,
            provider="openai",
        )
        return briefs

    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "ai_visual_planner_failed",
            error=str(exc),
            provider="openai",
        )
        return None
