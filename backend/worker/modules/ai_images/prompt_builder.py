"""Visual image prompt builder for AI image generation.

Converts raw narration text into clean, visual-only image prompts that do
NOT cause image models to render on-screen text, captions, speech bubbles,
or other typographic elements.
"""
from __future__ import annotations

import re

from app.config import settings

# ---------------------------------------------------------------------------
# Patterns that indicate the scene text is conversational / non-visual.
# These are removed before building the visual prompt.
# ---------------------------------------------------------------------------

# Direct-address / call-to-action openers that add no visual meaning.
_CONVERSATIONAL_PHRASES: list[str] = [
    r"\bhey\s+there\b",
    r"\bhi\s+there\b",
    r"\bhello\s+there\b",
    r"\bfolks\b",
    r"\bfriends\b",
    r"\beveryone\b",
    r"\bguys\b",
    r"\blet'?s\b",
    r"\bjoin\s+me\b",
    r"\bstay\s+tuned\b",
    r"\bcome\s+with\s+me\b",
    r"\bremember\b",
    r"\bnext\s+time\b",
    r"\bhere'?s\s+the\s+(?:good\s+)?news\b",
    r"\bdid\s+you\s+know\b",
    r"\btoday\s+we\b",
    r"\btoday\s+i\b",
    r"\bin\s+this\s+video\b",
    r"\bin\s+today'?s\s+video\b",
    r"\bwelcome\s+(?:back\s+)?to\b",
    r"\bthanks?\s+for\s+watching\b",
    r"\bdon'?t\s+forget\b",
    r"\blike\s+and\s+subscribe\b",
    r"\bsmash\s+that\b",
    r"\bhit\s+that\b",
    r"\bclick\s+(?:the\s+)?(?:link|button|here)\b",
    r"\bcheck\s+(?:it\s+)?out\b",
]

_PHRASE_RE = re.compile(
    "|".join(_CONVERSATIONAL_PHRASES),
    re.IGNORECASE,
)

# Minimum character length for scene text to be considered visually meaningful.
_MIN_VISUAL_LENGTH = 20


def build_image_prompt(scene_text: str, topic: str = "") -> str:
    """Return a visual-only image prompt for *scene_text*.

    The function:
    1. Strips direct-address / call-to-action phrases.
    2. Removes quoted fragments that could cause text rendering.
    3. Falls back to a generic topic-based visual description when the
       remaining text is too short or non-visual.
    4. Wraps the result in a cinematic framing sentence.
    5. Appends the configured negative prompt suffix.

    Args:
        scene_text: Raw narration text for the scene.
        topic:      Optional topic hint used when generating a fallback
                    description (e.g. the video title or subject).

    Returns:
        A clean, visual-only prompt string ready to send to an image model.
    """
    cleaned = _strip_conversational(scene_text)

    if _is_non_visual(cleaned):
        visual_core = _fallback_description(scene_text, topic)
    else:
        visual_core = cleaned

    prompt = _wrap_cinematic(visual_core)
    return _append_negative(prompt)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _strip_conversational(text: str) -> str:
    """Remove conversational / direct-address phrases from *text*."""
    # Remove quoted strings (they reproduce spoken words verbatim).
    no_quotes = re.sub(r'"[^"]*"', "", text)
    no_quotes = re.sub(r"'[^']{0,60}'", "", no_quotes)

    # Remove matched conversational phrases.
    cleaned = _PHRASE_RE.sub("", no_quotes)

    # Collapse extra whitespace / punctuation left by removals.
    cleaned = re.sub(r"[,!?.]*\s{2,}", " ", cleaned)
    cleaned = re.sub(r"^\s*[,!?.]+\s*", "", cleaned)
    cleaned = cleaned.strip(" ,!?.")
    return cleaned


def _is_non_visual(text: str) -> bool:
    """Return True when *text* is too short or conversational to be visual."""
    return len(text.strip()) < _MIN_VISUAL_LENGTH


def _fallback_description(original_text: str, topic: str) -> str:
    """Create a generic visual description when scene text is non-visual.

    Tries to extract concrete nouns / descriptive fragments; falls back to
    the *topic* hint when nothing useful remains.
    """
    # Try a light extraction: remove filler words and keep the longest fragment.
    stripped = _strip_conversational(original_text)
    words = stripped.split()
    # Remove single-character tokens (punctuation residue).
    words = [w for w in words if len(w) > 1]
    candidate = " ".join(words).strip(" ,!?.")

    if len(candidate) >= _MIN_VISUAL_LENGTH:
        return candidate

    # Fall back to the topic string if provided.
    if topic and topic.strip():
        return topic.strip()

    # Last resort: abstract visually appealing scene.
    return "cinematic natural landscape, golden hour lighting"


def _wrap_cinematic(visual_core: str) -> str:
    """Wrap *visual_core* in a cinematic framing with style suffixes."""
    core = visual_core[0].upper() + visual_core[1:] if visual_core else visual_core
    return (
        f"{core}, dramatic cinematic lighting, photorealistic, "
        f"high detail, vertical 9:16"
    )


def _append_negative(prompt: str) -> str:
    """Append the configured negative prompt suffix to *prompt*."""
    suffix = settings.AI_IMAGE_NEGATIVE_PROMPT.strip()
    if not suffix:
        return prompt
    return f"{prompt}. {suffix}"
