"""Scene quality scoring and auto-rewrite for storyboard scenes.

Provides:
- :func:`compute_scene_similarity`       — 0-1 similarity between two scenes.
- :func:`score_scene`                    — 0-100 quality score for a scene.
- :func:`is_generic_scene`               — True when a scene is too generic.
- :func:`rewrite_scene`                  — LLM-based rewrite of a low-quality scene.
- :func:`validate_and_improve_storyboard` — Orchestrate scoring + rewrite loop
                                            over a full storyboard.

Config:
    STORYBOARD_QUALITY_ENABLED    – activates the quality pass (default False).
    STORYBOARD_QUALITY_THRESHOLD  – minimum acceptable score (default 60).
    STORYBOARD_QUALITY_MAX_RETRIES – max rewrite attempts per scene (default 2).
"""
from __future__ import annotations

import dataclasses
import json
import re
import uuid
from typing import Any

import structlog

from app.config import settings
from worker.modules.storyboard.fallback import _assemble_image_prompt
from worker.modules.storyboard.models import StoryboardScene

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Generic phrases that indicate a scene description is too vague.
_GENERIC_PHRASES: tuple[str, ...] = (
    "in nature",
    "natural habitat",
    "in its natural habitat",
    "business environment",
    "technology concept",
    "futuristic scene",
    "abstract concept",
    "generic background",
    "typical scene",
    "foraging or eating",
    "near burrow",
    "near its burrow",
    "near its home",
    "in the wild",
    "in the outdoors",
)

# Words associated with real-world, grounded context.
_CONTEXT_WORDS: frozenset[str] = frozenset(
    {
        "crowd", "people", "audience", "spectators", "fans", "festival",
        "ceremony", "event", "celebration", "gathering", "street", "square",
        "park", "stage", "venue", "outdoor", "indoor", "city", "town", "hall",
        "building", "campus", "neighborhood", "market", "stadium", "theater",
        "location", "environment", "winter", "summer", "spring", "autumn",
        "morning", "evening", "night", "rain", "snow", "sunlight",
        "landscape", "scene", "setting",
    }
)

# Words associated with human presence in the scene.
_HUMAN_WORDS: frozenset[str] = frozenset(
    {
        "people", "person", "crowd", "audience", "spectators", "fans",
        "handlers", "man", "woman", "children", "family", "interacting",
        "interaction", "visitors", "attendees", "onlookers", "bystanders",
        "performers", "musicians", "workers", "couples", "tourists",
        "residents", "students",
    }
)

# Jaccard threshold used for the binary "similar to previous" check.
_SIMILARITY_THRESHOLD: float = 0.5

# Jaccard similarity above which global diversity penalty kicks in.
_DIVERSITY_SIMILARITY_THRESHOLD: float = 0.7

# Stop-words excluded from similarity comparison.
_STOP_WORDS: frozenset[str] = frozenset(
    {
        "a", "an", "the", "of", "in", "on", "at", "and", "or", "is", "are",
        "was", "were", "with", "to", "for", "from", "by", "as", "its", "it",
    }
)

# Minimum word count to be considered "visually specific".
_MIN_SPECIFIC_WORDS: int = 10

# Minimum word count for a valid LLM rewrite response (sanity check).
_MIN_REWRITE_RESPONSE_WORDS: int = 5


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compute_scene_similarity(
    scene_a: StoryboardScene,
    scene_b: StoryboardScene,
) -> float:
    """Return a similarity score in [0, 1] between two storyboard scenes.

    Combines four signals with fixed weights:
    - Visual description word overlap (Jaccard, 50 %)
    - Shot type match                            (20 %)
    - Subject match                              (20 %)
    - Context terms overlap (Jaccard, 10 %)

    Args:
        scene_a: First scene.
        scene_b: Second scene.

    Returns:
        Float in [0, 1].  1.0 means identical, 0.0 means no overlap.
    """
    # Description overlap — highest weight.
    desc_sim = _jaccard_words(scene_a.visual_description, scene_b.visual_description)

    # Shot type match.
    shot_sim = 1.0 if scene_a.shot_type == scene_b.shot_type else 0.0

    # Subject match (case-insensitive).
    subj_sim = 1.0 if (
        scene_a.subject and scene_b.subject
        and scene_a.subject.strip().lower() == scene_b.subject.strip().lower()
    ) else 0.0

    # Context terms overlap.
    terms_a = {t.lower() for t in (scene_a.context_terms or [])}
    terms_b = {t.lower() for t in (scene_b.context_terms or [])}
    if terms_a and terms_b:
        ctx_sim = len(terms_a & terms_b) / len(terms_a | terms_b)
    else:
        ctx_sim = 0.0

    return 0.5 * desc_sim + 0.2 * shot_sim + 0.2 * subj_sim + 0.1 * ctx_sim


def score_scene(
    scene: StoryboardScene,
    previous_scene: StoryboardScene | None = None,
    accepted_scenes: list[StoryboardScene] | None = None,
) -> int:
    """Score a storyboard scene on a 0–100 scale.

    Higher scores indicate more visually specific, context-rich, and diverse
    scenes.

    Scoring bonuses:
        +30  real-world context (crowd, environment, location, activity)
        +20  human presence (people, interaction, audience, …)
        +20  uses visual_tags or context_terms
        +15  visually specific (description ≥ 10 words)
        +15  clearly different from previous scene

    Penalties:
        -40  generic phrases detected
        -20  subject isolated without context
        -15  similar to immediately preceding scene
        up to -40  global diversity penalty when similarity > 0.7 vs any
                   previously accepted scene (``similarity × 40``)

    Args:
        scene:          Scene to score.
        previous_scene: The scene immediately before this one (for variety
                        checks).  Pass ``None`` for the first scene.
        accepted_scenes: All previously accepted scenes in the storyboard.
                         Used for global diversity scoring.  Pass ``None``
                         to skip the global diversity check.

    Returns:
        Integer score clamped to [0, 100].
    """
    if scene.reuse_previous:
        # Reuse-previous is intentional; treat as passing.
        return 70

    score: int = 0
    desc_lower = scene.visual_description.lower()
    words = desc_lower.split()

    # +30 real-world context
    has_context = bool(
        any(w in _CONTEXT_WORDS for w in words)
        or scene.context_terms
    )
    if has_context:
        score += 30

    # +20 human presence
    if any(w in _HUMAN_WORDS for w in words):
        score += 20

    # +20 uses visual_tags or context_terms
    if scene.visual_tags_used or scene.context_terms:
        score += 20

    # +15 visually specific (≥ min words)
    if len(words) >= _MIN_SPECIFIC_WORDS:
        score += 15

    # +15 clearly different from previous scene
    is_similar_to_prev = previous_scene is not None and _descriptions_similar(
        scene.visual_description, previous_scene.visual_description
    )
    if not is_similar_to_prev:
        score += 15

    # Penalty: -40 generic phrases
    if any(ph in desc_lower for ph in _GENERIC_PHRASES):
        score -= 40

    # Penalty: -20 subject isolated without context
    if not has_context:
        score -= 20

    # Penalty: -15 similar to previous
    if is_similar_to_prev:
        score -= 15

    # Global diversity penalty: compare against ALL previously accepted scenes.
    if accepted_scenes:
        max_sim = max(
            (compute_scene_similarity(scene, s) for s in accepted_scenes),
            default=0.0,
        )
        if max_sim > _DIVERSITY_SIMILARITY_THRESHOLD:
            score -= int(max_sim * 40)

    return max(0, min(100, score))


def is_generic_scene(scene: StoryboardScene) -> bool:
    """Return True when a scene is too generic for quality image generation.

    A scene is considered generic when it:

    - contains a known generic phrase, **or**
    - lacks both ``context_terms`` and ``visual_tags_used``, **or**
    - has a description shorter than :data:`_MIN_SPECIFIC_WORDS` words.

    Args:
        scene: Scene to inspect.

    Returns:
        True when the scene should be rewritten.
    """
    if scene.reuse_previous:
        return False

    desc_lower = scene.visual_description.lower()

    if any(ph in desc_lower for ph in _GENERIC_PHRASES):
        return True

    if not scene.context_terms and not scene.visual_tags_used:
        return True

    if len(desc_lower.split()) < _MIN_SPECIFIC_WORDS:
        return True

    return False


def rewrite_scene(
    scene: StoryboardScene,
    topic: str,
    visual_tags: list[str],
    full_script: str,
    diversity_hint: str | None = None,
) -> StoryboardScene:
    """Attempt to improve a low-quality scene using an LLM call.

    On any error (no API key, network failure, invalid response) the original
    *scene* is returned unchanged so that the pipeline never stalls.

    Args:
        scene:          The scene to rewrite.
        topic:          Video topic.
        visual_tags:    User-supplied visual tags.
        full_script:    Full narration script (for context).
        diversity_hint: Optional instruction to make the scene visually
                        different from previously accepted scenes (e.g. when
                        global diversity similarity > threshold).

    Returns:
        A new :class:`StoryboardScene` with an improved visual description,
        or the original scene if the rewrite failed.
    """
    if not settings.OPENAI_API_KEY:
        logger.warning("scene_rewrite_skipped_no_api_key", block_index=scene.index)
        return scene

    try:
        raw = _call_rewrite_llm(scene, topic, visual_tags, full_script, diversity_hint)
    except Exception as exc:
        logger.warning(
            "scene_rewrite_llm_failed",
            block_index=scene.index,
            error=str(exc),
        )
        return scene

    new_desc = (raw.get("visual_description") or "").strip()
    if not new_desc or len(new_desc.split()) < _MIN_REWRITE_RESPONSE_WORDS:
        logger.warning(
            "scene_rewrite_invalid_response",
            block_index=scene.index,
            raw=str(raw)[:200],
        )
        return scene

    # Strip phrases that look like negative-prompt instructions accidentally
    # included by the LLM (e.g. "No text, no captions.").  These belong in the
    # separate negative_prompt field, not in the visual_description.
    new_desc = re.sub(
        r"(?i)\b(no text|no captions|no subtitles|no typography|no logos|"
        r"no signs|no labels|no speech bubbles|no readable)\b[^,;.]*[,;.]?\s*",
        "",
        new_desc,
    ).strip().rstrip(",;")

    # Ensure the subject is still present.  Append naturally only when the
    # description does not already end with punctuation.
    if scene.subject and scene.subject.lower() not in new_desc.lower():
        separator = " " if new_desc.endswith((".", "!", "?")) else ", "
        new_desc = f"{new_desc}{separator}{scene.subject}"

    new_prompt = _assemble_image_prompt(new_desc, scene.negative_prompt)
    context_terms = list(raw.get("context_terms") or scene.context_terms)
    tags_used = list(raw.get("visual_tags_used") or scene.visual_tags_used)

    return dataclasses.replace(
        scene,
        id=str(uuid.uuid4()),
        visual_description=new_desc,
        image_prompt=new_prompt,
        context_terms=context_terms,
        visual_tags_used=tags_used,
        shot_type=str(raw.get("shot_type") or scene.shot_type),
        source="llm",
    )


def validate_and_improve_storyboard(
    scenes: list[StoryboardScene],
    topic: str,
    visual_tags: list[str],
    full_script: str,
) -> list[StoryboardScene]:
    """Score every scene and rewrite low-quality or repetitive ones.

    Each scene is scored for both intrinsic quality and global diversity vs
    all previously accepted scenes.  Scenes with
    ``score < STORYBOARD_QUALITY_THRESHOLD`` or ``is_generic_scene == True``
    or ``global similarity > 0.7`` are rewritten.  Each scene receives at
    most ``STORYBOARD_QUALITY_MAX_RETRIES`` rewrite attempts.  If a scene
    still fails after all retries the best version seen is kept and a warning
    is logged.

    Scene count, timing, and ``reuse_previous`` flags are **always** preserved.

    Args:
        scenes:      Ordered list of storyboard scenes.
        topic:       Video topic.
        visual_tags: User-supplied visual tags.
        full_script: Full narration script.

    Returns:
        List of the same length as *scenes* with quality-improved scenes.
    """
    threshold: int = settings.STORYBOARD_QUALITY_THRESHOLD
    max_retries: int = settings.STORYBOARD_QUALITY_MAX_RETRIES

    improved: list[StoryboardScene] = []

    for scene in scenes:
        previous = improved[-1] if improved else None
        initial_score = score_scene(scene, previous, accepted_scenes=improved)
        generic = is_generic_scene(scene)

        # Compute max similarity vs ALL previously accepted scenes.
        max_sim_global: float = 0.0
        if improved:
            max_sim_global = max(
                compute_scene_similarity(scene, s) for s in improved
            )
        diversity_issue = max_sim_global > _DIVERSITY_SIMILARITY_THRESHOLD

        diversity_hint: str | None = None
        if diversity_issue:
            diversity_hint = (
                "Make this scene visually different from all previous scenes. "
                "Change the camera angle, environment, or subject context."
            )

        logger.info(
            "scene_quality_score",
            block_index=scene.index,
            score=initial_score,
            generic_scene_detected=generic,
            max_global_similarity=round(max_sim_global, 3),
            diversity_issue=diversity_issue,
        )

        if initial_score >= threshold and not generic and not diversity_issue:
            improved.append(scene)
            continue

        # Need rewrite — attempt up to max_retries times.
        best = scene
        best_score = initial_score
        rewritten = False
        attempts_made = 0

        for attempt in range(1, max_retries + 1):
            candidate = rewrite_scene(
                best, topic, visual_tags, full_script, diversity_hint
            )
            candidate_score = score_scene(candidate, previous, accepted_scenes=improved)

            logger.info(
                "scene_rewrite_attempt",
                block_index=scene.index,
                attempt=attempt,
                score_before=best_score,
                score_after=candidate_score,
                scene_rewritten=True,
                diversity_hint_used=diversity_hint is not None,
            )

            if candidate_score > best_score:
                best = candidate
                best_score = candidate_score
                rewritten = True

            attempts_made = attempt

            # Recompute diversity after each rewrite.
            new_max_sim: float = 0.0
            if improved:
                new_max_sim = max(
                    compute_scene_similarity(best, s) for s in improved
                )
            if (
                best_score >= threshold
                and not is_generic_scene(best)
                and new_max_sim <= _DIVERSITY_SIMILARITY_THRESHOLD
            ):
                break

        if best_score < threshold or is_generic_scene(best):
            logger.warning(
                "scene_quality_below_threshold_after_retries",
                block_index=scene.index,
                final_score=best_score,
                rewrite_attempt_count=attempts_made,
                generic=is_generic_scene(best),
            )

        logger.info(
            "scene_quality_final",
            block_index=scene.index,
            final_scene_score=best_score,
            scene_rewritten=rewritten,
            rewrite_attempt_count=attempts_made if rewritten else 0,
        )

        improved.append(best)

    return improved


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _jaccard_words(a: str, b: str) -> float:
    """Return the Jaccard similarity coefficient for the content words in *a* and *b*.

    Stop-words and very short tokens (≤ 2 chars) are excluded.

    Args:
        a: First text string.
        b: Second text string.

    Returns:
        Float in [0, 1].  Returns 1.0 when both inputs are empty.
    """
    words_a = {w for w in a.lower().split() if w not in _STOP_WORDS and len(w) > 2}
    words_b = {w for w in b.lower().split() if w not in _STOP_WORDS and len(w) > 2}
    if not words_a and not words_b:
        return 0.0
    if not words_a or not words_b:
        return 0.0
    union = words_a | words_b
    return len(words_a & words_b) / len(union)


def _descriptions_similar(a: str, b: str) -> bool:
    """Return True when *a* and *b* share a high proportion of content words.

    Uses :func:`_jaccard_words` with :data:`_SIMILARITY_THRESHOLD`.

    Args:
        a: First description.
        b: Second description.

    Returns:
        True when the Jaccard coefficient is ≥ :data:`_SIMILARITY_THRESHOLD`.
    """
    return _jaccard_words(a, b) >= _SIMILARITY_THRESHOLD


def _call_rewrite_llm(
    scene: StoryboardScene,
    topic: str,
    visual_tags: list[str],
    full_script: str,
    diversity_hint: str | None = None,
) -> dict[str, Any]:
    """Call OpenAI to produce an improved scene description.

    Args:
        scene:          The scene to rewrite.
        topic:          Video topic.
        visual_tags:    User-supplied visual tags.
        full_script:    Full narration script.
        diversity_hint: Optional extra instruction to make the rewritten scene
                        visually different from previously accepted ones.

    Returns:
        Parsed JSON dict with keys ``visual_description``, ``shot_type``,
        ``context_terms``, ``visual_tags_used``.

    Raises:
        RuntimeError: On API failure or unparseable response.
    """
    from openai import OpenAI

    model = settings.STORYBOARD_MODEL or "gpt-4o-mini"
    tags_str = ", ".join(visual_tags) if visual_tags else "none"

    system_msg = (
        "You are a storyboard rewriter for AI-generated vertical videos. "
        "Rewrite the given scene to be more specific, visually grounded, "
        "and contextually rich. "
        "Return ONLY valid JSON — no markdown, no commentary."
    )

    diversity_instruction = (
        f"\n7. IMPORTANT — DIVERSITY: {diversity_hint}"
        if diversity_hint
        else ""
    )

    user_msg = (
        f"Topic: {topic}\n"
        f"Visual tags: {tags_str}\n"
        f"Narration text: {scene.narration_text[:300]}\n\n"
        f"Current scene (needs improvement):\n"
        f"  shot_type: {scene.shot_type}\n"
        f"  visual_description: {scene.visual_description}\n\n"
        f"Rules:\n"
        f"1. Improve specificity — name a real location, activity, or moment.\n"
        f"2. Include environment, people, or interaction where the topic allows.\n"
        f"3. Remove generic phrases like 'in nature' or 'technology concept'.\n"
        f"4. Preserve the meaning of the narration block.\n"
        f"5. Do NOT include signs, text, logos, UI, or captions in the scene.\n"
        f"6. Keep visual_description under 200 characters."
        f"{diversity_instruction}\n\n"
        f"Return a JSON object:\n"
        f"{{\n"
        f'  "shot_type": "wide",\n'
        f'  "visual_description": "VERY specific improved description",\n'
        f'  "context_terms": ["festival", "crowd"],\n'
        f'  "visual_tags_used": ["festival"]\n'
        f"}}"
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
        max_tokens=500,
    )

    raw = (response.choices[0].message.content or "").strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    obj_match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not obj_match:
        raise RuntimeError(
            f"LLM rewrite returned no JSON object. Preview: {raw[:200]!r}"
        )

    return json.loads(obj_match.group())
