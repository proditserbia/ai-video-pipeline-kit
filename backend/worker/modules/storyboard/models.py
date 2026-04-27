"""Data model for the storyboard planning layer.

A :class:`StoryboardScene` represents a single visual segment of the video,
corresponding to one (possibly merged) narration block.  It is the source of
truth from which the final image prompt is built via
:func:`~worker.modules.storyboard.planner.build_prompt_from_storyboard_scene`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class StoryboardScene:
    """A single storyboard scene corresponding to one narration block.

    Attributes:
        id:                Unique identifier (UUID string).
        index:             Zero-based position in the storyboard.
        narration_block_id: ID of the :class:`NarrationBlock` this scene maps to.
        narration_text:    The narration text covered by this scene.
        shot_type:         Composition type — e.g. ``"establishing"``,
                           ``"medium"``, ``"crowd_reaction"``, ``"detail"``,
                           ``"closing"``.
        visual_description: Concrete visual description of this scene (no raw
                            narration text, no negative-prompt instructions).
        image_prompt:      Final prompt string ready to send to an image model
                           (visual_description + style suffix + negative prompt).
        negative_prompt:   Negative-prompt string (populated from config).
        subject:           Resolved visual subject (e.g. ``"groundhog"``).
        category:          Detected visual category (e.g. ``"animal"``).
        context_terms:     Concrete context terms extracted from script/tags
                           (e.g. ``["festival", "Punxsutawney", "winter"]``).
        visual_tags_used:  Visual tags that influenced this scene's description.
        start_time:        Scene start in seconds (``None`` until TTS timing).
        end_time:          Scene end in seconds.
        duration:          Scene duration in seconds.
        source:            Whether this scene was produced by the LLM or the
                           deterministic fallback planner.
        reuse_previous:    When ``True``, no new image is generated; the
                           previous visual segment is extended instead.
    """

    id: str
    index: int
    narration_block_id: str
    narration_text: str
    shot_type: str
    visual_description: str
    image_prompt: str
    negative_prompt: str
    subject: str
    category: str
    context_terms: list[str] = field(default_factory=list)
    visual_tags_used: list[str] = field(default_factory=list)
    start_time: float | None = None
    end_time: float | None = None
    duration: float | None = None
    source: Literal["llm", "fallback"] = "fallback"
    reuse_previous: bool = False
