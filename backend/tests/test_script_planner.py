"""Tests for the script planner module."""
from __future__ import annotations

import pytest

from worker.modules.script_planner.planner import (
    ScriptScene,
    _group_sentences,
    _make_image_prompt,
    _make_search_query,
    _split_sentences,
    plan_script_scenes,
)


# ── _split_sentences ──────────────────────────────────────────────────────────


class TestSplitSentences:
    def test_basic_split_on_period(self):
        result = _split_sentences("Hello world. Goodbye world.")
        assert result == ["Hello world.", "Goodbye world."]

    def test_split_on_exclamation(self):
        result = _split_sentences("Wow! Amazing! Great!")
        assert len(result) == 3

    def test_split_on_question(self):
        result = _split_sentences("What? Really? Yes.")
        assert len(result) == 3

    def test_empty_string_returns_empty(self):
        assert _split_sentences("") == []

    def test_whitespace_only_returns_empty(self):
        assert _split_sentences("   ") == []

    def test_single_sentence(self):
        result = _split_sentences("Just one sentence.")
        assert result == ["Just one sentence."]

    def test_strips_whitespace_from_parts(self):
        result = _split_sentences("First.   Second.   Third.")
        assert all(not s.startswith(" ") for s in result)


# ── _group_sentences ──────────────────────────────────────────────────────────


class TestGroupSentences:
    def test_groups_into_requested_count(self):
        sentences = ["A.", "B.", "C.", "D.", "E.", "F."]
        groups = _group_sentences(sentences, 3)
        assert len(groups) == 3

    def test_groups_single(self):
        groups = _group_sentences(["Only one."], 1)
        assert len(groups) == 1
        assert "Only one." in groups[0]

    def test_more_groups_than_sentences_cycles(self):
        groups = _group_sentences(["A.", "B."], 4)
        assert len(groups) == 4

    def test_all_sentences_covered(self):
        sentences = ["A.", "B.", "C."]
        groups = _group_sentences(sentences, 2)
        combined = " ".join(groups)
        for s in sentences:
            assert s in combined


# ── _make_image_prompt ────────────────────────────────────────────────────────


class TestMakeImagePrompt:
    def test_contains_no_text(self):
        prompt = _make_image_prompt("Scientists discover a new planet.")
        assert "No text" in prompt

    def test_contains_no_captions(self):
        prompt = _make_image_prompt("Ocean waves crash on shore.")
        assert "no captions" in prompt.lower()

    def test_long_text_is_acceptable_length(self):
        long_text = "word " * 100
        prompt = _make_image_prompt(long_text)
        # Prompt should be present and not absurdly long
        assert len(prompt) > 0
        assert len(prompt) < 800

    def test_includes_style_suffix(self):
        prompt = _make_image_prompt("A quiet forest.")
        assert "9:16" in prompt or "cinematic" in prompt

    def test_conversational_opener_stripped(self):
        prompt = _make_image_prompt("Hey there, friends! Let's talk about bees today.")
        assert "Hey there" not in prompt
        assert "friends" not in prompt

    def test_prompt_not_just_raw_narration(self):
        raw = "Hey there, friends!"
        prompt = _make_image_prompt(raw)
        assert raw not in prompt


# ── _make_search_query ────────────────────────────────────────────────────────


class TestMakeSearchQuery:
    def test_returns_short_phrase(self):
        query = _make_search_query("Scientists have discovered a new planet orbiting a distant star.")
        assert len(query) <= 60

    def test_stops_at_comma(self):
        query = _make_search_query("Ocean waves, beautiful sunset, horizon.")
        assert "," not in query

    def test_non_empty_for_normal_input(self):
        query = _make_search_query("A beautiful forest.")
        assert query.strip() != ""


# ── plan_script_scenes ────────────────────────────────────────────────────────


class TestPlanScriptScenes:
    def test_returns_list_of_script_scenes(self):
        scenes = plan_script_scenes("Hello world. Goodbye world.")
        assert all(isinstance(s, ScriptScene) for s in scenes)

    def test_scenes_have_unique_ids(self):
        scenes = plan_script_scenes("A. B. C. D. E.")
        ids = [s.id for s in scenes]
        assert len(ids) == len(set(ids))

    def test_empty_script_returns_one_scene(self):
        scenes = plan_script_scenes("")
        assert len(scenes) >= 1

    def test_scenes_have_image_prompts(self):
        scenes = plan_script_scenes("The forest glows at dawn.")
        for scene in scenes:
            assert "No text" in scene.image_prompt

    def test_scenes_have_search_queries(self):
        scenes = plan_script_scenes("Scientists found water on Mars.")
        for scene in scenes:
            assert scene.search_query.strip() != ""

    def test_indices_are_sequential(self):
        scenes = plan_script_scenes("A. B. C.")
        assert [s.index for s in scenes] == list(range(len(scenes)))

    def test_no_audio_duration_leaves_times_as_none(self):
        scenes = plan_script_scenes("Hello world. Goodbye world.")
        for scene in scenes:
            assert scene.start_time is None
            assert scene.end_time is None
            assert scene.duration is None

    def test_with_audio_duration_all_times_set(self):
        scenes = plan_script_scenes(
            "Scene one text here. Scene two text here. Scene three here.",
            audio_duration=30.0,
        )
        for scene in scenes:
            assert scene.start_time is not None
            assert scene.end_time is not None
            assert scene.duration is not None

    def test_scenes_cover_full_audio_duration(self):
        audio_dur = 32.0
        scenes = plan_script_scenes(
            "Scientists have discovered a new planet. "
            "It orbits a nearby star. "
            "The atmosphere may support life.",
            audio_duration=audio_dur,
        )
        assert scenes[0].start_time == pytest.approx(0.0)
        assert scenes[-1].end_time == pytest.approx(audio_dur)

    def test_no_gaps_between_scenes(self):
        scenes = plan_script_scenes(
            "First sentence. Second sentence. Third sentence.",
            audio_duration=20.0,
        )
        for i in range(len(scenes) - 1):
            assert scenes[i].end_time == pytest.approx(scenes[i + 1].start_time)

    def test_no_overlaps_between_scenes(self):
        scenes = plan_script_scenes(
            "First. Second. Third. Fourth. Fifth.",
            audio_duration=25.0,
        )
        for i in range(len(scenes) - 1):
            assert scenes[i].end_time <= scenes[i + 1].start_time + 1e-9

    def test_all_durations_positive(self):
        scenes = plan_script_scenes(
            "Alpha. Beta. Gamma. Delta.",
            audio_duration=20.0,
        )
        for scene in scenes:
            assert scene.duration > 0

    def test_scene_count_scales_with_audio_duration(self):
        short = plan_script_scenes("A. B. C. D. E. F. G. H.", audio_duration=10.0)
        long = plan_script_scenes("A. B. C. D. E. F. G. H.", audio_duration=60.0)
        assert len(long) >= len(short)

    def test_scene_count_capped_at_20(self):
        # 50 sentences, long audio — scene count must not exceed 20.
        script = " ".join(f"Sentence {i}." for i in range(50))
        scenes = plan_script_scenes(script, audio_duration=300.0)
        assert len(scenes) <= 20

    def test_custom_min_max_respected_for_count(self):
        # With min=10s, max=20s and audio=30s: ceil(30/15)=2 scenes.
        scenes = plan_script_scenes(
            "A. B. C. D. E.",
            audio_duration=30.0,
            min_seconds=10.0,
            max_seconds=20.0,
        )
        assert len(scenes) <= 3  # 30/10 = 3 max scenes

    def test_sum_of_durations_equals_audio_duration(self):
        audio_dur = 45.0
        scenes = plan_script_scenes(
            "One. Two. Three. Four. Five.",
            audio_duration=audio_dur,
        )
        total = sum(s.duration for s in scenes)
        assert total == pytest.approx(audio_dur)
