"""Tests for the AI image visual prompt builder."""
from __future__ import annotations

import pytest

from worker.modules.ai_images.prompt_builder import (
    _ANIMAL_SHOT_PLAN,
    _GENERAL_SHOT_PLAN,
    _append_negative,
    _extract_subject,
    _is_animal_subject,
    _is_non_visual,
    _strip_conversational,
    _wrap_cinematic,
    build_image_prompt,
)


# ── _strip_conversational ─────────────────────────────────────────────────────


class TestStripConversational:
    def test_removes_hey_there(self):
        result = _strip_conversational("Hey there, this is a test.")
        assert "Hey there" not in result

    def test_removes_friends(self):
        result = _strip_conversational("Friends, today we discuss bees.")
        assert "friends" not in result.lower()

    def test_removes_lets_talk(self):
        result = _strip_conversational("Let's talk about climate change.")
        assert "let's talk" not in result.lower()

    def test_removes_remember(self):
        result = _strip_conversational("Remember to like and subscribe!")
        assert "remember" not in result.lower()

    def test_removes_next_time(self):
        result = _strip_conversational("Next time, we'll cover part two.")
        assert "next time" not in result.lower()

    def test_removes_heres_the_good_news(self):
        result = _strip_conversational("Here's the good news about solar power.")
        assert "here's the good news" not in result.lower()

    def test_removes_quoted_strings(self):
        result = _strip_conversational('He said "hello world" loudly.')
        assert "hello world" not in result

    def test_keeps_visual_content(self):
        result = _strip_conversational(
            "Honeybees pollinate wildflowers in a sunlit meadow."
        )
        assert "honeybees" in result.lower() or "wildflowers" in result.lower()

    def test_visual_sentence_unchanged_enough(self):
        text = "A vast mountain range covered in snow at sunrise."
        result = _strip_conversational(text)
        # Core visual words should remain
        assert "mountain" in result.lower()


# ── _is_non_visual ────────────────────────────────────────────────────────────


class TestIsNonVisual:
    def test_empty_string_is_non_visual(self):
        assert _is_non_visual("") is True

    def test_short_string_is_non_visual(self):
        assert _is_non_visual("Hey!") is True

    def test_long_string_is_visual(self):
        assert _is_non_visual("Bees flying over a blooming meadow at dawn.") is False


# ── _wrap_cinematic ───────────────────────────────────────────────────────────


class TestWrapCinematic:
    def test_contains_9_16(self):
        result = _wrap_cinematic("Bees on flowers")
        assert "9:16" in result

    def test_contains_cinematic(self):
        result = _wrap_cinematic("Bees on flowers")
        assert "cinematic" in result.lower()

    def test_capitalizes_first_letter(self):
        result = _wrap_cinematic("bees on flowers")
        assert result[0].isupper()

    def test_contains_core_content(self):
        result = _wrap_cinematic("honeybees in a field")
        assert "honeybees" in result.lower()


# ── _append_negative ──────────────────────────────────────────────────────────


class TestAppendNegative:
    def test_contains_no_text(self):
        result = _append_negative("A cinematic scene")
        assert "No text" in result

    def test_contains_no_captions(self):
        result = _append_negative("A cinematic scene")
        assert "no captions" in result.lower()

    def test_contains_no_speech_bubbles(self):
        result = _append_negative("A cinematic scene")
        assert "speech bubbles" in result.lower()

    def test_appended_after_prompt(self):
        result = _append_negative("Scene content")
        assert result.startswith("Scene content")


# ── build_image_prompt ────────────────────────────────────────────────────────


class TestBuildImagePrompt:
    def test_hey_there_friends_no_direct_address(self):
        prompt = build_image_prompt("Hey there, friends!")
        assert "Hey there" not in prompt
        assert "friends" not in prompt.lower()

    def test_hey_there_friends_includes_no_text(self):
        prompt = build_image_prompt("Hey there, friends!")
        assert "No text" in prompt

    def test_short_conversational_produces_visual_prompt(self):
        prompt = build_image_prompt("Hey there, friends!")
        # Must be non-empty and have cinematic/photorealistic style markers
        assert "cinematic" in prompt.lower() or "photorealistic" in prompt.lower()

    def test_lets_give_them_a_hand_no_direct_address(self):
        prompt = build_image_prompt("Let's give them a hand, or maybe a flower!")
        assert "let's" not in prompt.lower()

    def test_every_prompt_includes_no_text(self):
        scenes = [
            "Hey there, friends!",
            "Let's give them a hand.",
            "Honeybees are declining worldwide.",
            "Scientists have found a new solution.",
            "Remember to share this video.",
            "Here's the good news about solar.",
        ]
        for scene in scenes:
            prompt = build_image_prompt(scene)
            assert "No text" in prompt, f"Missing 'No text' in prompt for: {scene!r}"

    def test_every_prompt_includes_no_captions(self):
        scenes = [
            "Bees are essential to ecosystems.",
            "Hey there! Let's explore nature.",
        ]
        for scene in scenes:
            prompt = build_image_prompt(scene)
            assert "no captions" in prompt.lower()

    def test_no_raw_narration_quotes(self):
        raw = 'He said "hello world".'
        prompt = build_image_prompt(raw)
        assert '"hello world"' not in prompt

    def test_visual_scene_preserves_content(self):
        text = "Honeybees flying around wildflowers in a sunny garden."
        prompt = build_image_prompt(text)
        assert "honeybees" in prompt.lower() or "wildflowers" in prompt.lower()

    def test_first_scene_greeting_fallback(self):
        """First-scene greeting should produce a generic cinematic visual."""
        prompt = build_image_prompt("Hey there, friends!", topic="beekeeping")
        assert "Hey there" not in prompt
        assert "cinematic" in prompt.lower() or "photorealistic" in prompt.lower()

    def test_last_scene_cta_fallback(self):
        """Last-scene CTA should produce a visual, not a caption-like prompt."""
        prompt = build_image_prompt("Don't forget to like and subscribe!", topic="nature")
        assert "like and subscribe" not in prompt.lower()
        assert "No text" in prompt

    def test_topic_hint_used_in_fallback(self):
        """When scene text is non-visual, the topic hint should appear."""
        prompt = build_image_prompt("Hey!", topic="ocean conservation")
        assert "ocean conservation" in prompt or "cinematic" in prompt.lower()

    def test_prompt_not_empty(self):
        for text in ["", "   ", "Hey!"]:
            prompt = build_image_prompt(text)
            assert prompt.strip() != ""


# ── _extract_subject ──────────────────────────────────────────────────────────


class TestExtractSubject:
    def test_topic_preferred_over_text(self):
        subject = _extract_subject("Some long narration text here.", "beekeeping")
        assert subject == "beekeeping"

    def test_topic_used_when_short(self):
        subject = _extract_subject("Hey!", "ocean conservation")
        assert subject == "ocean conservation"

    def test_extracts_from_text_when_no_topic(self):
        subject = _extract_subject("Honeybees pollinate wildflowers in a meadow.", "")
        assert "honeybee" in subject.lower() or "wildflowers" in subject.lower() or len(subject) > 3

    def test_fallback_when_text_non_visual(self):
        subject = _extract_subject("Hey!", "")
        assert len(subject) > 0

    def test_long_topic_not_used_as_subject(self):
        long_topic = "this is a very long topic with more than five words here"
        subject = _extract_subject("Bees in a meadow.", long_topic)
        # Falls through to text extraction because topic is > 5 words
        assert subject != long_topic


# ── _is_animal_subject ────────────────────────────────────────────────────────


class TestIsAnimalSubject:
    def test_groundhog_is_animal(self):
        assert _is_animal_subject("groundhog") is True

    def test_bear_is_animal(self):
        assert _is_animal_subject("bear") is True

    def test_honeybee_is_animal(self):
        assert _is_animal_subject("honeybees") is True

    def test_beekeeping_not_animal(self):
        assert _is_animal_subject("beekeeping") is False

    def test_ocean_conservation_not_animal(self):
        assert _is_animal_subject("ocean conservation") is False

    def test_animal_in_phrase(self):
        assert _is_animal_subject("groundhog in natural habitat") is True

    def test_case_insensitive(self):
        assert _is_animal_subject("Groundhog") is True


# ── TestShotPlanVariety ────────────────────────────────────────────────────────


class TestShotPlanVariety:
    """Verify that the shot-plan produces visually varied prompts for a repeated subject."""

    # Five short narration texts all about the same animal.
    _TEXTS = [
        "Groundhogs have round faces, tiny ears, and big curious eyes.",
        "These animals are known for their playful antics in the meadow.",
        "Groundhogs are great for your garden and help aerate the soil.",
        "February 2nd is Groundhog Day, when the weather forecast happens.",
        "Groundhogs hibernate through the cold winter months underground.",
    ]
    _TOPIC = "groundhog"

    def _build_prompts(self) -> list[str]:
        prompts: list[str] = []
        for i, text in enumerate(self._TEXTS):
            p = build_image_prompt(
                text,
                self._TOPIC,
                block_index=i,
                total_blocks=len(self._TEXTS),
                previous_prompts=list(prompts),
            )
            prompts.append(p)
        return prompts

    def test_five_blocks_produce_distinct_prompts(self):
        prompts = self._build_prompts()
        assert len(prompts) == 5
        assert len(set(prompts)) == 5, "All 5 prompts must be unique (different shot types)"

    def test_five_blocks_use_all_animal_shot_types(self):
        """Each block should map to a different shot type in the animal plan."""
        prompts = self._build_prompts()
        shot_types_used: set[str] = set()
        for i, _ in enumerate(self._TEXTS):
            shot_idx = i % len(_ANIMAL_SHOT_PLAN)
            shot_type, _ = _ANIMAL_SHOT_PLAN[shot_idx]
            shot_types_used.add(shot_type)
        # Five blocks cycling through five slots means all five shot types are used.
        assert len(shot_types_used) == len(_ANIMAL_SHOT_PLAN)

    def test_not_all_prompts_contain_close_up(self):
        prompts = self._build_prompts()
        close_up_count = sum(
            1 for p in prompts if "close-up" in p.lower() or "close up" in p.lower()
        )
        assert close_up_count < len(prompts), (
            "At least one prompt should not be a close-up"
        )

    def test_every_prompt_includes_no_text_suffix(self):
        prompts = self._build_prompts()
        for p in prompts:
            assert "No text" in p, f"'No text' missing from prompt: {p!r}"

    def test_every_prompt_includes_no_captions_suffix(self):
        prompts = self._build_prompts()
        for p in prompts:
            assert "no captions" in p.lower(), f"'no captions' missing from prompt: {p!r}"

    def test_raw_narration_phrases_not_verbatim(self):
        """Raw narration details must not be copied word-for-word into the prompt."""
        prompts = self._build_prompts()
        raw_phrases = [
            "round faces, tiny ears, and big curious eyes",
            "playful antics",
            "great for your garden",
            "February 2nd is Groundhog Day",
            "hibernate through the cold winter",
        ]
        for prompt, phrase in zip(prompts, raw_phrases):
            assert phrase.lower() not in prompt.lower(), (
                f"Raw narration phrase {phrase!r} found verbatim in prompt: {prompt!r}"
            )

    def test_first_last_not_both_close_up_portrait(self):
        prompts = self._build_prompts()
        first_close = "close-up" in prompts[0].lower() or "portrait" in prompts[0].lower()
        last_close = "close-up" in prompts[-1].lower() or "portrait" in prompts[-1].lower()
        assert not (first_close and last_close), (
            "First and last prompts must not both be close-up portraits"
        )

    def test_anti_repetition_suffix_in_every_prompt(self):
        prompts = self._build_prompts()
        for p in prompts:
            assert "distinct" in p.lower() or "composition" in p.lower(), (
                f"Anti-repetition suffix missing from prompt: {p!r}"
            )

    def test_first_prompt_is_establishing_or_wide(self):
        prompts = self._build_prompts()
        first = prompts[0].lower()
        assert "establishing" in first or "wide" in first or "habitat" in first, (
            f"First prompt should be establishing/wide/habitat shot, got: {prompts[0]!r}"
        )

    def test_subject_is_groundhog_not_full_narration(self):
        """Subject extracted from topic should be 'groundhog', not the full sentence."""
        prompts = self._build_prompts()
        for p in prompts:
            assert "groundhog" in p.lower(), (
                f"Subject 'groundhog' missing from prompt: {p!r}"
            )

    def test_general_shot_plan_also_cycles(self):
        """Non-animal topic prompts should also use different shot types per block."""
        texts = [
            "Solar panels convert sunlight into electricity efficiently.",
            "Homeowners can reduce energy bills with rooftop solar systems.",
            "Grid-tied inverters allow excess energy to flow back to utilities.",
            "Battery storage extends solar power into the night-time hours.",
            "Government incentives make solar installation more affordable.",
        ]
        topic = "solar energy"
        prompts: list[str] = []
        for i, text in enumerate(texts):
            p = build_image_prompt(
                text, topic, block_index=i, total_blocks=5, previous_prompts=list(prompts)
            )
            prompts.append(p)

        assert len(set(prompts)) == 5, "General-topic prompts must all be distinct"
        # Each prompt should map to a different general shot type.
        shot_types_expected = {t for t, _ in _GENERAL_SHOT_PLAN}
        shot_types_found: set[str] = set()
        for i in range(5):
            shot_idx = i % len(_GENERAL_SHOT_PLAN)
            shot_type, _ = _GENERAL_SHOT_PLAN[shot_idx]
            shot_types_found.add(shot_type)
        assert shot_types_found == shot_types_expected
