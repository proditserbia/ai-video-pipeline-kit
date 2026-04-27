"""Visual image prompt builder for AI image generation.

Converts raw narration text into clean, visual-only image prompts that do
NOT cause image models to render on-screen text, captions, speech bubbles,
or other typographic elements.

When ``settings.VISUAL_SHOT_PLAN_ENABLED`` is ``True`` (the default), each
block receives a distinct shot type drawn from a rotating plan so that a
multi-block video about the same subject never produces five identical
close-up portraits.
"""
from __future__ import annotations

import re

import structlog

from app.config import settings

logger = structlog.get_logger(__name__)

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

# Maximum character length for single-quoted strings to be considered inline
# quotes (not multi-sentence blocks).  Longer single-quoted spans are left
# intact because they are likely chapter titles or proper names.
_MAX_SINGLE_QUOTE_LENGTH = 60

# Maximum number of words taken from scene text when building a subject hint.
_SUBJECT_MAX_WORDS = 10

# ---------------------------------------------------------------------------
# Animal keyword set – triggers the animal-specific shot plan.
# ---------------------------------------------------------------------------

_ANIMAL_KEYWORDS: frozenset[str] = frozenset({
    # Rodents / burrowing
    "groundhog", "groundhogs", "marmot", "marmots",
    "squirrel", "squirrels", "chipmunk", "chipmunks",
    "beaver", "beavers", "mole", "moles", "vole", "voles",
    "rabbit", "rabbits", "hare", "hares",
    # Canines / felines / bears
    "fox", "foxes", "wolf", "wolves", "coyote", "coyotes",
    "bear", "bears", "panda", "pandas",
    "cat", "cats", "kitten", "kittens", "lion", "lions", "tiger", "tigers",
    "leopard", "cheetah", "jaguar",
    "dog", "dogs", "puppy", "puppies",
    # Ungulates
    "deer", "elk", "moose", "bison", "buffalo",
    "horse", "horses", "pony", "donkey",
    "cow", "cows", "goat", "goats", "sheep", "lamb",
    # Primates
    "monkey", "monkeys", "gorilla", "chimpanzee", "orangutan", "baboon",
    # Birds
    "bird", "birds", "eagle", "hawk", "owl", "sparrow", "robin", "crow",
    "parrot", "penguin", "flamingo", "heron", "duck", "goose",
    # Reptiles / amphibians
    "snake", "snakes", "lizard", "gecko", "iguana",
    "frog", "frogs", "toad", "turtle", "tortoise", "crocodile", "alligator",
    # Marine
    "fish", "whale", "dolphin", "shark", "seal", "otter", "walrus",
    "octopus", "jellyfish",
    # Insects
    "bee", "bees", "honeybee", "honeybees", "butterfly", "butterflies",
    "ant", "ants", "dragonfly", "firefly",
    # Other
    "raccoon", "raccoons", "badger", "skunk", "opossum", "armadillo",
    "elephant", "elephants", "giraffe", "hippo", "rhino", "zebra",
    "kangaroo", "koala", "wombat",
})

# ---------------------------------------------------------------------------
# Shot plans – each entry is (shot_type_label, prompt_template).
# The template receives a single ``{subject}`` substitution.
# ---------------------------------------------------------------------------

#: General shot plan (cycling based on block_index) used for non-animal topics.
_GENERAL_SHOT_PLAN: list[tuple[str, str]] = [
    (
        "establishing",
        "Wide establishing shot featuring {subject}, full environment clearly "
        "visible, natural setting, golden hour lighting, photorealistic vertical 9:16",
    ),
    (
        "medium",
        "Medium shot of {subject}, full body and surrounding context visible, "
        "natural lighting, photorealistic vertical 9:16",
    ),
    (
        "action",
        "Dynamic action shot of {subject} in motion or engaged in activity, "
        "energetic composition, photorealistic vertical 9:16",
    ),
    (
        "detail",
        "Contextual detail shot of {subject} within their ecosystem, environment "
        "and surroundings prominent, photorealistic vertical 9:16",
    ),
    (
        "wide_closing",
        "Wide panoramic shot with {subject} visible in a broader landscape, "
        "emphasizing scale and natural surroundings, photorealistic vertical 9:16",
    ),
]

#: Animal-specific shot plan that rotates through habitat / behaviour /
#: ecosystem compositions to avoid repeated close-up portraits.
_ANIMAL_SHOT_PLAN: list[tuple[str, str]] = [
    (
        "animal_establishing",
        "Wide establishing shot of {subject} in natural habitat, full environment "
        "visible, lush surroundings, animal present in scene, "
        "photorealistic vertical 9:16",
    ),
    (
        "animal_medium_fullbody",
        "Medium full-body shot of {subject} near its burrow or home, full body "
        "and paws visible, natural daylight, photorealistic vertical 9:16",
    ),
    (
        "animal_foraging",
        "Dynamic shot of {subject} foraging or eating, natural behaviour and "
        "movement clearly visible, photorealistic vertical 9:16",
    ),
    (
        "animal_habitat_detail",
        "Ground-level detail shot of {subject} burrow, nest, or den entrance, "
        "habitat texture and environment context visible, "
        "photorealistic vertical 9:16",
    ),
    (
        "animal_ecosystem_wide",
        "Wide ecosystem shot with {subject} small in frame, surrounded by "
        "plants, flowers, and natural landscape, environmental context, "
        "photorealistic vertical 9:16",
    ),
]

# Suffix appended to every shot-plan prompt to discourage the image model
# from repeating the same composition across a batch of images.
_ANTI_REPETITION_SUFFIX = (
    "Use a distinct framing and composition from previous images in this set."
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_image_prompt(
    scene_text: str,
    topic: str = "",
    *,
    block_index: int = 0,
    total_blocks: int = 1,
    previous_prompts: list[str] | None = None,
) -> str:
    """Return a visual-only image prompt for *scene_text*.

    When ``settings.VISUAL_SHOT_PLAN_ENABLED`` is ``True`` (the default) the
    function selects a shot type from a rotating plan based on *block_index*,
    uses the *topic* (or a brief subject extracted from *scene_text*) to fill
    the template, and appends an anti-repetition constraint so that an image
    model never produces five identical close-up portraits for the same topic.

    When ``VISUAL_SHOT_PLAN_ENABLED`` is ``False`` the legacy behaviour is
    preserved: raw narration is cleaned of conversational phrases and wrapped
    in a generic cinematic framing sentence.

    Args:
        scene_text:       Raw narration text for the scene.
        topic:            Global topic / title hint (e.g. the video title).
        block_index:      Zero-based position of this block in the sequence.
        total_blocks:     Total number of blocks in the video.
        previous_prompts: Prompts already generated for preceding blocks
                          (reserved for future similarity checks).

    Returns:
        A clean, visual-only prompt string ready to send to an image model.
    """
    if settings.VISUAL_SHOT_PLAN_ENABLED:
        return _build_shot_plan_prompt(
            scene_text,
            topic,
            block_index=block_index,
            total_blocks=total_blocks,
            previous_prompts=previous_prompts,
        )

    # ── Legacy path ──────────────────────────────────────────────────────────
    cleaned = _strip_conversational(scene_text)
    if _is_non_visual(cleaned):
        visual_core = _fallback_description(scene_text, topic)
    else:
        visual_core = cleaned
    prompt = _wrap_cinematic(visual_core)
    return _append_negative(prompt)


# ---------------------------------------------------------------------------
# Shot-plan helpers
# ---------------------------------------------------------------------------


def _build_shot_plan_prompt(
    scene_text: str,
    topic: str,
    *,
    block_index: int,
    total_blocks: int,
    previous_prompts: list[str] | None,
) -> str:
    """Build a shot-plan prompt for *scene_text* at position *block_index*."""
    subject = _extract_subject(scene_text, topic)
    is_animal = _is_animal_subject(subject)
    plan = _ANIMAL_SHOT_PLAN if is_animal else _GENERAL_SHOT_PLAN
    shot_idx = block_index % len(plan)
    shot_type, template = plan[shot_idx]

    visual_core = template.format(subject=subject)

    logger.info(
        "visual_prompt_built",
        block_index=block_index,
        total_blocks=total_blocks,
        shot_type=shot_type,
        subject=subject,
        is_animal=is_animal,
        final_visual_prompt=visual_core,
    )

    prompt = _append_negative(visual_core)
    return f"{prompt} {_ANTI_REPETITION_SUFFIX}"


def _extract_subject(scene_text: str, topic: str) -> str:
    """Return the visual subject to use in a shot-plan template.

    Priority:
    1. *topic* hint when it is a concise phrase (≤ 5 words).
    2. A brief noun phrase extracted from the cleaned scene text.
    3. *topic* (any length) as a fallback when the text is too short to use.
    4. ``"abstract cinematic scene"`` as a last resort.
    """
    if topic and len(topic.strip().split()) <= 5 and len(topic.strip()) > 1:
        return topic.strip()

    # Extract a subject from the scene text regardless of its raw length.
    cleaned = _strip_conversational(scene_text)
    first_sentence = re.split(r"[.!?]", cleaned)[0].strip()
    words = first_sentence.split()[:_SUBJECT_MAX_WORDS]
    subject = " ".join(words).strip(".,!?")

    if len(subject) > 3:
        return subject

    # Nothing useful extracted from the text; fall back to topic or default.
    if topic and topic.strip():
        return topic.strip()
    return "abstract cinematic scene"


def _is_animal_subject(subject: str) -> bool:
    """Return ``True`` when *subject* contains a known animal keyword."""
    words = re.findall(r"\b\w+\b", subject.lower())
    return bool(_ANIMAL_KEYWORDS.intersection(words))


# ---------------------------------------------------------------------------
# Legacy helpers (also used by the legacy path in build_image_prompt)
# ---------------------------------------------------------------------------


def _strip_conversational(text: str) -> str:
    """Remove conversational / direct-address phrases from *text*."""
    # Remove quoted strings (they reproduce spoken words verbatim).
    no_quotes = re.sub(r'"[^"]*"', "", text)
    no_quotes = re.sub(rf"'[^']{{0,{_MAX_SINGLE_QUOTE_LENGTH}}}'", "", no_quotes)

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
    core = visual_core[:1].upper() + visual_core[1:] if visual_core else visual_core
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
