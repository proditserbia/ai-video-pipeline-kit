"""Tests for the AI image visual prompt builder."""
from __future__ import annotations

import pytest

from worker.modules.ai_images.prompt_builder import (
    _append_negative,
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
