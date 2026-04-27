"""Tests for the storyboard planning layer.

Tests cover:
1.  LLM JSON parsing → StoryboardScene conversion
2.  Invalid JSON triggers deterministic fallback
3.  Missing subject triggers validation failure → fallback
4.  Generic visual_description triggers validation failure when tags exist
5.  Groundhog + festival/crowd/winter/punxsutawney tags → context-specific scenes
6.  Jazz music → club/stage/instrument/audience variety
7.  AI smart home → home/family/devices, no generic sci-fi-only
8.  Ultra-short outro block → reuse_previous=True OR merged into previous
9.  Final image prompts include negative no-text suffix
10. STORYBOARD_PLANNER_ENABLED=False preserves old prompt_builder path
11. Stock mode unchanged (storyboard skipped in stock mode)
12. Cache key changes when script changes
"""
from __future__ import annotations

import hashlib
import unittest.mock as mock

import pytest

from worker.modules.storyboard.models import StoryboardScene
from worker.modules.storyboard.planner import (
    _STORYBOARD_CACHE,
    _call_openai,
    _convert_llm_output,
    _is_generic_description,
    _make_cache_key,
    _validate_llm_output,
    build_prompt_from_storyboard_scene,
    plan_storyboard,
)
from worker.modules.storyboard.fallback import build_fallback_storyboard


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_block(index: int, text: str, block_id: str | None = None):
    """Build a lightweight NarrationBlock-like object."""
    import uuid
    from types import SimpleNamespace

    return SimpleNamespace(
        id=block_id or str(uuid.uuid4()),
        index=index,
        text=text,
        image_prompt="",
        audio_path=None,
        image_path=None,
        start_time=None,
        end_time=None,
        duration=None,
    )


_GROUNDHOG_SCRIPT = (
    "Every year on February 2nd, people gather in Punxsutawney for one of "
    "America's most beloved traditions — Groundhog Day.\n\n"
    "Thousands of bundled-up spectators crowd Gobbler's Knob, waiting for "
    "Punxsutawney Phil to emerge from his burrow and predict the weather.\n\n"
    "The crowd erupts in cheers as handlers lift Phil from his stump and "
    "check for his shadow during the ceremony.\n\n"
    "If Phil sees his shadow, it means six more weeks of winter; "
    "if not, spring is coming early.\n\n"
    "Happy Groundhog Day, everyone!"
)

_GROUNDHOG_PARAGRAPHS = [
    p.strip() for p in _GROUNDHOG_SCRIPT.split("\n\n") if p.strip()
]

_GROUNDHOG_BLOCKS = [
    _make_block(i, t) for i, t in enumerate(_GROUNDHOG_PARAGRAPHS)
]

_JAZZ_SCRIPT = (
    "Jazz originated in New Orleans in the early twentieth century.\n\n"
    "Saxophone players improvise melodies over chord changes in smoky clubs.\n\n"
    "Concert venues fill with the sound of brass instruments.\n\n"
    "Jazz musicians developed a unique musical language.\n\n"
    "Audiences gather to hear live jazz performances on stage."
)

_SMART_HOME_SCRIPT = (
    "Smart home technology makes daily life more convenient and efficient.\n\n"
    "Voice assistants control lights, locks, and appliances at home.\n\n"
    "Families use smart devices to automate their morning routines.\n\n"
    "Smart thermostats and cameras keep homes comfortable and secure.\n\n"
    "The future of home automation is already here."
)


# ---------------------------------------------------------------------------
# 1. LLM JSON parsing → StoryboardScene conversion
# ---------------------------------------------------------------------------


class TestLLMJsonParsing:
    """_convert_llm_output must correctly convert LLM JSON to StoryboardScene."""

    def test_valid_json_produces_storyboard_scenes(self):
        raw = [
            {
                "block_index": 0,
                "shot_type": "establishing",
                "visual_description": "Wide shot of Groundhog Day festival in Punxsutawney, crowd gathered",
                "context_terms": ["festival", "crowd"],
                "visual_tags_used": ["festival"],
                "subject": "groundhog",
                "reuse_previous": False,
            }
        ]
        block = _make_block(0, "People gather in Punxsutawney for Groundhog Day.")
        scenes = _convert_llm_output(raw, [block], "groundhog", "animal", "No text.")
        assert len(scenes) == 1
        s = scenes[0]
        assert isinstance(s, StoryboardScene)
        assert s.index == 0
        assert s.shot_type == "establishing"
        assert "groundhog" in s.visual_description.lower() or "groundhog" in s.subject.lower()
        assert s.source == "llm"
        assert s.reuse_previous is False

    def test_all_fields_populated(self):
        raw = [
            {
                "block_index": 0,
                "shot_type": "medium",
                "visual_description": "Medium shot of Punxsutawney Phil being lifted by handlers",
                "context_terms": ["festival", "ceremony"],
                "visual_tags_used": ["festival"],
                "subject": "groundhog",
                "reuse_previous": False,
            }
        ]
        block = _make_block(0, "Handlers lift Phil from the burrow.")
        scenes = _convert_llm_output(raw, [block], "groundhog", "animal", "No text.")
        s = scenes[0]
        assert s.narration_block_id == block.id
        assert s.narration_text == block.text
        assert "festival" in s.context_terms
        assert "festival" in s.visual_tags_used
        assert s.negative_prompt == "No text."
        assert s.category == "animal"
        assert s.subject == "groundhog"
        assert s.image_prompt != ""

    def test_reuse_previous_true_gives_empty_image_prompt(self):
        raw = [{"block_index": 0, "reuse_previous": True, "shot_type": "closing"}]
        block = _make_block(0, "Happy Groundhog Day!")
        scenes = _convert_llm_output(raw, [block], "groundhog", "animal", "No text.")
        assert len(scenes) == 1
        assert scenes[0].reuse_previous is True
        assert scenes[0].image_prompt == ""

    def test_negative_instructions_stripped_from_visual_description(self):
        """LLM-leaked 'No text...' prefix must be stripped from visual_description."""
        raw = [
            {
                "block_index": 0,
                "shot_type": "establishing",
                "visual_description": (
                    "No text, no captions. "
                    "Wide shot of Groundhog Day festival in Punxsutawney"
                ),
                "context_terms": [],
                "visual_tags_used": [],
                "subject": "groundhog",
                "reuse_previous": False,
            }
        ]
        block = _make_block(0, "People gather.")
        scenes = _convert_llm_output(raw, [block], "groundhog", "animal", "No text.")
        desc = scenes[0].visual_description
        assert not desc.lower().startswith("no text"), (
            f"Negative instructions leaked into visual_description: {desc!r}"
        )

    def test_missing_block_id_gets_uuid(self):
        raw = [
            {
                "block_index": 99,  # No matching block
                "shot_type": "establishing",
                "visual_description": "Wide shot of groundhog ceremony",
                "context_terms": [],
                "visual_tags_used": [],
                "subject": "groundhog",
                "reuse_previous": False,
            }
        ]
        block = _make_block(0, "Some text.")
        # block_index=99 has no matching block → should still produce a scene
        scenes = _convert_llm_output(raw, [block], "groundhog", "animal", "No text.")
        assert len(scenes) == 1
        assert scenes[0].narration_block_id  # not empty


# ---------------------------------------------------------------------------
# 2. Invalid JSON triggers deterministic fallback
# ---------------------------------------------------------------------------


class TestInvalidJsonTriggersFallback:
    """When LLM returns bad JSON, plan_storyboard must use the fallback."""

    def _plan_with_bad_llm(self, bad_response: str, blocks: list) -> list[StoryboardScene]:
        """Run plan_storyboard with a mocked LLM that returns *bad_response*."""
        from app import config as cfg

        with mock.patch.object(cfg.settings, "STORYBOARD_PLANNER_ENABLED", True):
            with mock.patch.object(cfg.settings, "STORYBOARD_PLANNER_PROVIDER", "openai"):
                with mock.patch.object(cfg.settings, "OPENAI_API_KEY", "fake-key"):
                    with mock.patch.object(cfg.settings, "STORYBOARD_CACHE_ENABLED", False):
                        with mock.patch(
                            "worker.modules.storyboard.planner._call_openai",
                            side_effect=RuntimeError(
                                f"LLM returned no JSON array. Preview: {bad_response!r}"
                            ),
                        ):
                            return plan_storyboard(
                                "groundhog",
                                ["festival"],
                                _GROUNDHOG_SCRIPT,
                                blocks,
                            )

    def test_bad_json_falls_back_to_deterministic(self):
        blocks = _GROUNDHOG_BLOCKS[:3]
        scenes = self._plan_with_bad_llm("this is not json at all", blocks)
        assert len(scenes) > 0
        assert all(s.source == "fallback" for s in scenes)

    def test_empty_string_response_falls_back(self):
        blocks = _GROUNDHOG_BLOCKS[:3]
        scenes = self._plan_with_bad_llm("", blocks)
        assert len(scenes) > 0
        assert all(s.source == "fallback" for s in scenes)

    def test_fallback_scenes_have_valid_image_prompts(self):
        blocks = _GROUNDHOG_BLOCKS[:3]
        scenes = self._plan_with_bad_llm("not valid", blocks)
        for s in scenes:
            assert s.image_prompt.strip(), (
                f"Scene {s.index} has empty image_prompt after fallback"
            )

    def test_fallback_scenes_have_no_text_suffix(self):
        blocks = _GROUNDHOG_BLOCKS[:3]
        scenes = self._plan_with_bad_llm("bad json", blocks)
        for s in scenes:
            assert "No text" in s.image_prompt, (
                f"No-text suffix missing from fallback scene {s.index}: {s.image_prompt!r}"
            )


# ---------------------------------------------------------------------------
# 3. Missing subject triggers validation failure
# ---------------------------------------------------------------------------


class TestMissingSubjectValidation:
    """Scenes without the resolved subject cause validation failure → fallback."""

    def test_missing_subject_is_caught(self):
        """_validate_llm_output returns errors when subject is absent from description."""
        raw = [
            {
                "block_index": 0,
                "shot_type": "establishing",
                "visual_description": "Wide shot of a winter festival crowd",
                "context_terms": ["festival"],
                "visual_tags_used": ["festival"],
                "subject": "groundhog",
                "reuse_previous": False,
            }
        ]
        block = _make_block(0, "People gather for the ceremony.")
        errors = _validate_llm_output(raw, [block], "groundhog", ["festival"])
        # "groundhog" missing from description → error
        assert any("subject" in e.lower() or "groundhog" in e.lower() for e in errors), (
            f"Expected subject-missing error, got: {errors}"
        )

    def test_subject_present_no_error(self):
        raw = [
            {
                "block_index": 0,
                "shot_type": "establishing",
                "visual_description": "Wide shot of groundhog ceremony in Punxsutawney",
                "context_terms": ["festival"],
                "visual_tags_used": ["festival"],
                "subject": "groundhog",
                "reuse_previous": False,
            }
        ]
        block = _make_block(0, "People gather.")
        errors = _validate_llm_output(raw, [block], "groundhog", ["festival"])
        assert not errors, f"Unexpected errors: {errors}"

    def test_generic_subject_not_flagged(self):
        """When subject is 'abstract cinematic scene', missing-subject check is skipped."""
        raw = [
            {
                "block_index": 0,
                "shot_type": "establishing",
                "visual_description": "A sweeping landscape shot at sunrise",
                "context_terms": [],
                "visual_tags_used": [],
                "subject": "abstract cinematic scene",
                "reuse_previous": False,
            }
        ]
        block = _make_block(0, "Some text.")
        errors = _validate_llm_output(raw, [block], "abstract cinematic scene", [])
        assert not errors, f"Unexpected errors: {errors}"


# ---------------------------------------------------------------------------
# 4. Generic visual_description triggers validation failure when tags exist
# ---------------------------------------------------------------------------


class TestGenericDescriptionValidation:
    """_is_generic_description and _validate_llm_output must catch generic prompts."""

    def test_natural_habitat_is_generic_with_tags(self):
        assert _is_generic_description(
            "animal in its natural habitat", ["festival", "crowd"]
        )

    def test_natural_habitat_not_flagged_without_tags(self):
        # Without tags there's no context to require specificity.
        assert not _is_generic_description("animal in its natural habitat", [])

    def test_festival_crowd_not_generic(self):
        assert not _is_generic_description(
            "Groundhog Day festival crowd in Punxsutawney",
            ["festival", "crowd"],
        )

    def test_foraging_is_generic_with_event_tags(self):
        assert _is_generic_description("groundhog foraging or eating", ["festival"])

    def test_business_environment_is_generic(self):
        assert _is_generic_description("business environment shot", ["startup", "office"])

    def test_technology_concept_is_generic(self):
        assert _is_generic_description("technology concept illustration", ["smart home"])

    def test_validate_flags_generic_with_tags(self):
        raw = [
            {
                "block_index": 0,
                "shot_type": "establishing",
                "visual_description": "groundhog in its natural habitat",
                "context_terms": [],
                "visual_tags_used": [],
                "subject": "groundhog",
                "reuse_previous": False,
            }
        ]
        block = _make_block(0, "People gather for Groundhog Day ceremony.")
        errors = _validate_llm_output(raw, [block], "groundhog", ["festival", "crowd"])
        assert any("generic" in e.lower() for e in errors), (
            f"Expected generic-description error, got: {errors}"
        )


# ---------------------------------------------------------------------------
# 5. Groundhog + festival/crowd/winter/punxsutawney tags
# ---------------------------------------------------------------------------


class TestGroundhogFestivalScenario:
    """Groundhog Day + festival/crowd/winter/punxsutawney tags must produce
    context-specific, non-generic storyboard scenes."""

    _TOPIC = "groundhog"
    _TAGS = ["festival", "crowd", "winter", "punxsutawney"]

    def _build_scenes(self) -> list[StoryboardScene]:
        blocks = [_make_block(i, t) for i, t in enumerate(_GROUNDHOG_PARAGRAPHS[:4])]
        return build_fallback_storyboard(
            self._TOPIC, self._TAGS, _GROUNDHOG_SCRIPT, blocks
        )

    def test_all_scenes_produced(self):
        scenes = self._build_scenes()
        assert len(scenes) == 4

    def test_groundhog_subject_in_all_scenes(self):
        scenes = self._build_scenes()
        for s in scenes:
            assert "groundhog" in s.subject.lower() or "groundhog" in s.visual_description.lower(), (
                f"Scene {s.index} missing subject: {s.visual_description!r}"
            )

    def test_festival_context_in_at_least_one_scene(self):
        scenes = self._build_scenes()
        festival_words = {"festival", "ceremony", "event", "celebration", "gathering"}
        found = any(
            any(w in s.visual_description.lower() for w in festival_words)
            for s in scenes
        )
        assert found, (
            "festival tag not reflected in any scene description:\n"
            + "\n".join(f"  [{s.index}] {s.visual_description}" for s in scenes)
        )

    def test_no_generic_habitat_prompts_with_festival_tags(self):
        scenes = self._build_scenes()
        generic = ["in natural habitat", "foraging or eating"]
        bad = [
            s for s in scenes
            if any(g in s.visual_description.lower() for g in generic)
        ]
        # Allow at most one generic fallback in 4 scenes.
        assert len(bad) <= 1, (
            f"{len(bad)}/4 scenes are generic habitat descriptions despite festival tags:\n"
            + "\n".join(f"  [{s.index}] {s.visual_description}" for s in bad)
        )

    def test_winter_or_crowd_context_present(self):
        scenes = self._build_scenes()
        context_words = {"winter", "crowd", "bundled", "cold", "february", "snow"}
        found = any(
            any(w in s.visual_description.lower() for w in context_words)
            or any(w in ct.lower() for ct in s.context_terms for w in context_words)
            for s in scenes
        )
        assert found, (
            "No winter/crowd context found in any scene"
        )

    def test_all_prompts_have_no_text_suffix(self):
        scenes = self._build_scenes()
        for s in scenes:
            assert "No text" in s.image_prompt, (
                f"Scene {s.index} missing no-text suffix: {s.image_prompt!r}"
            )

    def test_prompts_do_not_start_with_no_text(self):
        scenes = self._build_scenes()
        for s in scenes:
            assert not s.image_prompt.startswith("No text"), (
                f"Scene {s.index} prompt starts with 'No text': {s.image_prompt!r}"
            )

    def test_shot_types_vary(self):
        """Different blocks should have different shot types for visual variety."""
        scenes = self._build_scenes()
        shot_types = {s.shot_type for s in scenes}
        assert len(shot_types) >= 2, (
            f"All scenes have the same shot type: {shot_types}"
        )

    def test_source_is_fallback(self):
        scenes = self._build_scenes()
        assert all(s.source == "fallback" for s in scenes)

    def test_storyboard_disabled_falls_back_to_prompt_builder(self):
        """When STORYBOARD_PLANNER_ENABLED=False, plan_storyboard uses fallback."""
        from app import config as cfg

        with mock.patch.object(cfg.settings, "STORYBOARD_PLANNER_ENABLED", False):
            blocks = [_make_block(i, t) for i, t in enumerate(_GROUNDHOG_PARAGRAPHS[:3])]
            scenes = plan_storyboard("groundhog", self._TAGS, _GROUNDHOG_SCRIPT, blocks)
        assert len(scenes) == 3
        # When disabled, uses fallback → source is "fallback"
        assert all(s.source == "fallback" for s in scenes)


# ---------------------------------------------------------------------------
# 6. Jazz music scenario
# ---------------------------------------------------------------------------


class TestJazzMusicScenario:
    _TOPIC = "jazz music"
    _TAGS = ["jazz", "saxophone", "concert", "stage"]
    _PARAGRAPHS = [p.strip() for p in _JAZZ_SCRIPT.split("\n\n") if p.strip()]

    def _build_scenes(self) -> list[StoryboardScene]:
        blocks = [_make_block(i, t) for i, t in enumerate(self._PARAGRAPHS[:4])]
        return build_fallback_storyboard(
            self._TOPIC, self._TAGS, _JAZZ_SCRIPT, blocks
        )

    def test_jazz_subject_in_scenes(self):
        scenes = self._build_scenes()
        for s in scenes:
            has_jazz = (
                "jazz" in s.visual_description.lower()
                or "saxophone" in s.visual_description.lower()
                or "jazz" in s.subject.lower()
            )
            assert has_jazz, (
                f"Scene {s.index}: no jazz/saxophone reference: {s.visual_description!r}"
            )

    def test_concert_or_stage_context_present(self):
        scenes = self._build_scenes()
        music_words = {"concert", "stage", "club", "venue", "music", "audience", "performance"}
        found = any(
            any(w in s.visual_description.lower() for w in music_words)
            or any(w in ct.lower() for ct in s.context_terms for w in music_words)
            for s in scenes
        )
        assert found, (
            "No concert/stage context in any jazz scene:\n"
            + "\n".join(f"  [{s.index}] {s.visual_description}" for s in scenes)
        )

    def test_all_scenes_have_image_prompts(self):
        scenes = self._build_scenes()
        for s in scenes:
            assert s.image_prompt.strip()

    def test_no_text_suffix_in_all_prompts(self):
        scenes = self._build_scenes()
        for s in scenes:
            assert "No text" in s.image_prompt


# ---------------------------------------------------------------------------
# 7. AI smart home scenario
# ---------------------------------------------------------------------------


class TestSmartHomeScenario:
    _TOPIC = "smart home"
    _TAGS = ["smart home", "voice assistant", "family", "devices"]
    _PARAGRAPHS = [p.strip() for p in _SMART_HOME_SCRIPT.split("\n\n") if p.strip()]

    def _build_scenes(self) -> list[StoryboardScene]:
        blocks = [_make_block(i, t) for i, t in enumerate(self._PARAGRAPHS[:4])]
        return build_fallback_storyboard(
            self._TOPIC, self._TAGS, _SMART_HOME_SCRIPT, blocks
        )

    def test_smart_home_subject_in_scenes(self):
        scenes = self._build_scenes()
        for s in scenes:
            # subject must contain "smart home" or be a specific element
            assert (
                "smart" in s.subject.lower()
                or "home" in s.subject.lower()
                or "assistant" in s.subject.lower()
            ), f"Scene {s.index}: unexpected subject: {s.subject!r}"

    def test_no_generic_sci_fi_prompts(self):
        """Smart home prompts must not be abstract sci-fi only."""
        scenes = self._build_scenes()
        sci_fi_phrases = ["floating screens", "generic technology", "technology concept"]
        bad = [
            s for s in scenes
            if any(ph in s.visual_description.lower() for ph in sci_fi_phrases)
        ]
        assert not bad, (
            "Generic sci-fi descriptions found:\n"
            + "\n".join(f"  [{s.index}] {s.visual_description}" for s in bad)
        )

    def test_scenes_have_image_prompts(self):
        scenes = self._build_scenes()
        for s in scenes:
            assert s.image_prompt.strip()


# ---------------------------------------------------------------------------
# 8. Ultra-short outro block → reuse_previous or merged
# ---------------------------------------------------------------------------


class TestUltraShortOutroBlock:
    """Ultra-short blocks must not receive their own image slot."""

    _MAIN_BLOCKS = [
        _make_block(0, "People gather in Punxsutawney every February for Groundhog Day."),
        _make_block(1, "Thousands of bundled-up fans wait for Punxsutawney Phil to emerge."),
        _make_block(2, "The crowd erupts when the groundhog is lifted by his handlers."),
    ]
    _SHORT_OUTRO_BLOCK = _make_block(3, "Happy Groundhog Day!")

    def test_reuse_previous_in_validate_for_short_outro(self):
        """LLM-supplied reuse_previous=True for short block must pass validation."""
        raw = [
            {
                "block_index": 0,
                "shot_type": "establishing",
                "visual_description": "Wide shot of groundhog festival in Punxsutawney",
                "context_terms": ["festival"],
                "visual_tags_used": ["festival"],
                "subject": "groundhog",
                "reuse_previous": False,
            },
            {
                "block_index": 1,
                "shot_type": "medium",
                "visual_description": "Medium shot of groundhog being lifted during ceremony",
                "context_terms": ["ceremony"],
                "visual_tags_used": ["ceremony"],
                "subject": "groundhog",
                "reuse_previous": False,
            },
            {
                "block_index": 2,
                "shot_type": "crowd_reaction",
                "visual_description": "Crowd reaction shot of bundled-up fans cheering as groundhog is revealed",
                "context_terms": ["crowd"],
                "visual_tags_used": ["crowd"],
                "subject": "groundhog",
                "reuse_previous": False,
            },
            {
                "block_index": 3,
                "shot_type": "closing",
                "reuse_previous": True,  # No new image for the short outro
            },
        ]
        all_blocks = self._MAIN_BLOCKS + [self._SHORT_OUTRO_BLOCK]
        errors = _validate_llm_output(raw, all_blocks, "groundhog", ["festival"])
        assert not errors, f"Unexpected errors for valid reuse_previous: {errors}"

    def test_reuse_previous_scene_has_empty_image_prompt(self):
        raw = [
            {
                "block_index": 3,
                "shot_type": "closing",
                "reuse_previous": True,
            }
        ]
        scenes = _convert_llm_output(
            raw, [self._SHORT_OUTRO_BLOCK], "groundhog", "animal", "No text."
        )
        assert len(scenes) == 1
        assert scenes[0].reuse_previous is True
        assert scenes[0].image_prompt == ""

    def test_fallback_does_not_reuse_for_normal_blocks(self):
        """Fallback storyboard should not reuse_previous for adequate-length blocks."""
        scenes = build_fallback_storyboard(
            "groundhog", ["festival"], _GROUNDHOG_SCRIPT, self._MAIN_BLOCKS
        )
        assert not any(s.reuse_previous for s in scenes), (
            "Fallback storyboard set reuse_previous=True for non-short blocks"
        )


# ---------------------------------------------------------------------------
# 9. Final image prompts include negative no-text suffix
# ---------------------------------------------------------------------------


class TestNoTextSuffix:
    """build_prompt_from_storyboard_scene must always include the negative suffix."""

    def _make_scene(self, visual_description: str) -> StoryboardScene:
        return StoryboardScene(
            id="test-id",
            index=0,
            narration_block_id="block-0",
            narration_text="Test narration.",
            shot_type="establishing",
            visual_description=visual_description,
            image_prompt="",
            negative_prompt="No text, no captions, no subtitles.",
            subject="groundhog",
            category="animal",
        )

    def test_negative_suffix_present(self):
        scene = self._make_scene(
            "Wide shot of groundhog festival in Punxsutawney, winter morning"
        )
        prompt = build_prompt_from_storyboard_scene(scene)
        assert "No text" in prompt, f"Negative suffix missing: {prompt!r}"

    def test_prompt_does_not_start_with_no_text(self):
        scene = self._make_scene("Wide shot of groundhog ceremony")
        prompt = build_prompt_from_storyboard_scene(scene)
        assert not prompt.startswith("No text"), (
            f"Prompt starts with 'No text': {prompt!r}"
        )

    def test_style_suffix_present(self):
        scene = self._make_scene("Wide shot of Groundhog Day festival")
        prompt = build_prompt_from_storyboard_scene(scene)
        assert "vertical 9:16" in prompt or "photorealistic" in prompt, (
            f"Style suffix missing from prompt: {prompt!r}"
        )

    def test_prompt_does_not_contain_raw_narration(self):
        """build_prompt_from_storyboard_scene must NOT include raw narration text."""
        narration = "Hey everyone, welcome back to the channel!"
        scene = StoryboardScene(
            id="test-id",
            index=0,
            narration_block_id="block-0",
            narration_text=narration,
            shot_type="establishing",
            visual_description="Wide shot of jazz club at night",
            image_prompt="",
            negative_prompt="No text.",
            subject="jazz",
            category="music",
        )
        prompt = build_prompt_from_storyboard_scene(scene)
        # Raw narration must not appear in the output.
        assert "welcome back to the channel" not in prompt.lower(), (
            f"Raw narration leaked into prompt: {prompt!r}"
        )

    def test_various_topics_all_have_suffix(self):
        topics = [
            ("Wide shot of groundhog festival", "groundhog"),
            ("Saxophone player on stage", "jazz"),
            ("Family using smart home devices", "smart home"),
        ]
        from app.config import settings

        negative = settings.AI_IMAGE_NEGATIVE_PROMPT
        for desc, subject in topics:
            scene = self._make_scene(desc)
            scene.subject = subject
            scene.negative_prompt = negative
            prompt = build_prompt_from_storyboard_scene(scene)
            assert "No text" in prompt, (
                f"Topic={subject!r}: 'No text' missing from prompt: {prompt!r}"
            )


# ---------------------------------------------------------------------------
# 10. STORYBOARD_PLANNER_ENABLED=False preserves old prompt_builder path
# ---------------------------------------------------------------------------


class TestStoryboardDisabledBehavior:
    """When STORYBOARD_PLANNER_ENABLED=False, plan_storyboard returns fallback scenes
    built with the existing prompt_builder (no LLM call)."""

    def test_disabled_returns_fallback_scenes(self):
        from app import config as cfg

        with mock.patch.object(cfg.settings, "STORYBOARD_PLANNER_ENABLED", False):
            blocks = [_make_block(i, t) for i, t in enumerate(_GROUNDHOG_PARAGRAPHS[:3])]
            scenes = plan_storyboard("groundhog", ["festival"], _GROUNDHOG_SCRIPT, blocks)
        assert len(scenes) == 3

    def test_disabled_never_calls_openai(self):
        from app import config as cfg

        with mock.patch.object(cfg.settings, "STORYBOARD_PLANNER_ENABLED", False):
            with mock.patch(
                "worker.modules.storyboard.planner._call_openai"
            ) as mock_call:
                blocks = [_make_block(0, "Some text here.")]
                plan_storyboard("groundhog", [], "Some script.", blocks)
                mock_call.assert_not_called()

    def test_disabled_produces_prompt_builder_style_prompt(self):
        """Fallback prompts should include style suffix and negative prompt."""
        from app import config as cfg

        with mock.patch.object(cfg.settings, "STORYBOARD_PLANNER_ENABLED", False):
            blocks = [_make_block(0, "People gather for the Groundhog Day festival.")]
            scenes = plan_storyboard("groundhog", ["festival"], _GROUNDHOG_SCRIPT, blocks)
        assert scenes
        assert "No text" in scenes[0].image_prompt
        assert "9:16" in scenes[0].image_prompt or "photorealistic" in scenes[0].image_prompt


# ---------------------------------------------------------------------------
# 11. Stock mode unchanged
# ---------------------------------------------------------------------------


class TestStockModeUnchanged:
    """Storyboard planner must not affect the stock-media path."""

    def test_storyboard_not_involved_in_stock_build(self):
        """Importing storyboard module does not alter any stock-media behaviour."""
        # The storyboard module's presence should not affect plan_script_scenes
        # or any stock-mode function.
        from worker.modules.script_planner.planner import plan_script_scenes

        scenes = plan_script_scenes(
            "Honeybees are fascinating insects that build complex hives.",
            audio_duration=30.0,
            topic="beekeeping",
        )
        # Should produce scenes as before — storyboard layer is not involved.
        assert len(scenes) >= 1
        for s in scenes:
            assert s.image_prompt.strip()
            assert "No text" in s.image_prompt

    def test_plan_storyboard_called_directly_does_not_break_stock_scenes(self):
        """Calling plan_storyboard in stock mode must not crash."""
        from app import config as cfg

        with mock.patch.object(cfg.settings, "STORYBOARD_PLANNER_ENABLED", False):
            blocks = [_make_block(0, "Bees are important pollinators.")]
            scenes = plan_storyboard("beekeeping", ["bees", "hive"], "Bees are important.", blocks)
        # Should run without error and return fallback scenes.
        assert len(scenes) == 1


# ---------------------------------------------------------------------------
# 12. Cache key changes when inputs change
# ---------------------------------------------------------------------------


class TestCacheKey:
    """_make_cache_key must change when any input changes."""

    def _key(self, **kwargs) -> str:
        defaults = dict(
            topic="groundhog",
            visual_tags=["festival"],
            script_text="Some script text.",
            blocks=[_make_block(0, "Block text.")],
            model="gpt-4o-mini",
        )
        defaults.update(kwargs)
        return _make_cache_key(**defaults)

    def test_key_is_deterministic(self):
        k1 = self._key()
        k2 = self._key()
        assert k1 == k2

    def test_key_changes_with_topic(self):
        assert self._key(topic="groundhog") != self._key(topic="jazz")

    def test_key_changes_with_tags(self):
        assert self._key(visual_tags=["festival"]) != self._key(visual_tags=["concert"])

    def test_key_changes_with_script(self):
        assert (
            self._key(script_text="Script A about groundhog day.")
            != self._key(script_text="Script B about jazz music.")
        )

    def test_key_changes_with_block_text(self):
        assert (
            self._key(blocks=[_make_block(0, "Block A text.")])
            != self._key(blocks=[_make_block(0, "Block B text.")])
        )

    def test_key_changes_with_model(self):
        assert self._key(model="gpt-4o-mini") != self._key(model="gpt-4o")

    def test_key_is_sha256_hex(self):
        key = self._key()
        assert len(key) == 64  # SHA-256 hex is 64 characters
        assert all(c in "0123456789abcdef" for c in key)

    def test_tags_order_does_not_matter(self):
        """Tags are sorted before hashing so order doesn't affect the key."""
        k1 = self._key(visual_tags=["festival", "crowd"])
        k2 = self._key(visual_tags=["crowd", "festival"])
        assert k1 == k2


# ---------------------------------------------------------------------------
# 13. build_prompt_from_storyboard_scene round-trip
# ---------------------------------------------------------------------------


class TestBuildPromptFromScene:
    """build_prompt_from_storyboard_scene must produce a complete prompt."""

    def test_basic_round_trip(self):
        scene = StoryboardScene(
            id="x",
            index=0,
            narration_block_id="b0",
            narration_text="People gather for Groundhog Day.",
            shot_type="establishing",
            visual_description=(
                "Wide shot of Groundhog Day festival in Punxsutawney, "
                "bundled-up crowd near ceremony stage, winter morning"
            ),
            image_prompt="",
            negative_prompt="No text, no captions, no subtitles.",
            subject="groundhog",
            category="animal",
        )
        prompt = build_prompt_from_storyboard_scene(scene)
        assert "Groundhog Day festival" in prompt
        assert "Punxsutawney" in prompt
        assert "No text" in prompt
        assert "9:16" in prompt or "photorealistic" in prompt

    def test_subject_injected_when_missing_from_description(self):
        """If subject not in visual_description, the fallback must add it."""
        blocks = [_make_block(0, "People gather at the festival.")]
        # Use the fallback which handles subject injection.
        scenes = build_fallback_storyboard(
            "groundhog", ["festival"], _GROUNDHOG_SCRIPT, blocks
        )
        s = scenes[0]
        assert "groundhog" in s.visual_description.lower() or "groundhog" in s.subject.lower(), (
            f"Subject missing from description: {s.visual_description!r}"
        )

    def test_empty_blocks_returns_empty_list(self):
        scenes = plan_storyboard("groundhog", ["festival"], "Some script.", [])
        assert scenes == []


# ---------------------------------------------------------------------------
# 14. plan_storyboard raises ValueError for 0 scenes when blocks non-empty
# ---------------------------------------------------------------------------


class TestZeroScenesError:
    """When both LLM and fallback produce 0 scenes, a clear error is raised."""

    def test_raises_on_zero_scenes(self):
        """Patching fallback to return [] should trigger ValueError."""
        from app import config as cfg

        with mock.patch.object(cfg.settings, "STORYBOARD_PLANNER_ENABLED", False):
            with mock.patch(
                "worker.modules.storyboard.planner.build_fallback_storyboard",
                return_value=[],
            ):
                blocks = [_make_block(0, "Some non-empty text.")]
                with pytest.raises(ValueError, match="0 scenes"):
                    plan_storyboard("topic", [], "script", blocks)


# ---------------------------------------------------------------------------
# 15. StoryboardScene model fields
# ---------------------------------------------------------------------------


class TestStoryboardSceneModel:
    def test_default_source_is_fallback(self):
        s = StoryboardScene(
            id="x",
            index=0,
            narration_block_id="b",
            narration_text="text",
            shot_type="establishing",
            visual_description="desc",
            image_prompt="prompt",
            negative_prompt="neg",
            subject="subj",
            category="cat",
        )
        assert s.source == "fallback"
        assert s.reuse_previous is False
        assert s.context_terms == []
        assert s.visual_tags_used == []
        assert s.start_time is None

    def test_source_can_be_llm(self):
        s = StoryboardScene(
            id="x",
            index=0,
            narration_block_id="b",
            narration_text="text",
            shot_type="establishing",
            visual_description="desc",
            image_prompt="prompt",
            negative_prompt="neg",
            subject="subj",
            category="cat",
            source="llm",
        )
        assert s.source == "llm"

    def test_reuse_previous_can_be_set(self):
        s = StoryboardScene(
            id="x",
            index=0,
            narration_block_id="b",
            narration_text="outro",
            shot_type="closing",
            visual_description="",
            image_prompt="",
            negative_prompt="neg",
            subject="subj",
            category="cat",
            reuse_previous=True,
        )
        assert s.reuse_previous is True
        assert s.image_prompt == ""
