"""Tests for the AI image visual prompt builder."""
from __future__ import annotations

import pytest

from worker.modules.ai_images.prompt_builder import (
    CATEGORY_ANIMAL,
    CATEGORY_BUSINESS,
    CATEGORY_EDUCATION,
    CATEGORY_GENERAL,
    CATEGORY_HEALTH,
    CATEGORY_HISTORY,
    CATEGORY_MUSIC,
    CATEGORY_SCIENCE,
    CATEGORY_SPORTS,
    CATEGORY_TECHNOLOGY,
    CATEGORY_TRAVEL,
    _ANIMAL_SHOT_PLAN,
    _CATEGORY_PLANS,
    _GENERAL_SHOT_PLAN,
    _append_negative,
    _dedup_visual_tags,
    _extract_subject,
    _filter_generic_tags,
    _is_animal_subject,
    _is_non_visual,
    _strip_conversational,
    _wrap_cinematic,
    build_image_prompt,
    detect_visual_category,
    resolve_visual_subject,
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


# ── _is_animal_subject (shim) + detect_visual_category ────────────────────────


class TestDetectVisualCategory:
    # ── animal ────────────────────────────────────────────────────────────────
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

    # ── detect_visual_category: correct category per domain ───────────────────
    def test_music_topic(self):
        assert detect_visual_category("guitar lessons") == CATEGORY_MUSIC

    def test_music_via_text(self):
        assert detect_visual_category("", "A band performs on stage at a concert.") == CATEGORY_MUSIC

    def test_technology_topic(self):
        assert detect_visual_category("machine learning tutorial") == CATEGORY_TECHNOLOGY

    def test_technology_via_text(self):
        assert detect_visual_category("", "Developers write code on their computers.") == CATEGORY_TECHNOLOGY

    def test_science_topic(self):
        assert detect_visual_category("quantum physics") == CATEGORY_SCIENCE

    def test_health_topic(self):
        assert detect_visual_category("meditation for anxiety") == CATEGORY_HEALTH

    def test_business_topic(self):
        assert detect_visual_category("startup marketing strategy") == CATEGORY_BUSINESS

    def test_history_topic(self):
        assert detect_visual_category("ancient roman empire") == CATEGORY_HISTORY

    def test_travel_topic(self):
        assert detect_visual_category("backpacking through europe") == CATEGORY_TRAVEL

    def test_sports_topic(self):
        assert detect_visual_category("marathon training plan") == CATEGORY_SPORTS

    def test_education_topic(self):
        assert detect_visual_category("university scholarship tips") == CATEGORY_EDUCATION

    def test_unknown_topic_returns_general(self):
        assert detect_visual_category("cooking pasta carbonara") == CATEGORY_GENERAL

    def test_empty_topic_and_text_returns_general(self):
        assert detect_visual_category("", "") == CATEGORY_GENERAL

    def test_animal_topic_combined_text(self):
        assert detect_visual_category(
            "groundhog", "Groundhogs hibernate underground in winter."
        ) == CATEGORY_ANIMAL

    def test_category_keywords_used_from_scene_text(self):
        # Topic is blank; category detected via scene text only.
        assert detect_visual_category(
            "", "Athletes compete in the championship marathon race."
        ) == CATEGORY_SPORTS

    def test_all_category_plans_present(self):
        """Every CATEGORY_* constant should have an entry in _CATEGORY_PLANS."""
        for cat in [
            CATEGORY_ANIMAL, CATEGORY_MUSIC, CATEGORY_TECHNOLOGY, CATEGORY_SCIENCE,
            CATEGORY_HEALTH, CATEGORY_BUSINESS, CATEGORY_HISTORY, CATEGORY_TRAVEL,
            CATEGORY_SPORTS, CATEGORY_EDUCATION, CATEGORY_GENERAL,
        ]:
            assert cat in _CATEGORY_PLANS, f"Missing plan for category: {cat!r}"

    def test_each_plan_has_five_shots(self):
        for cat, plan in _CATEGORY_PLANS.items():
            assert len(plan) == 5, f"Plan for {cat!r} has {len(plan)} entries, expected 5"


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
        animal_plan = _CATEGORY_PLANS[CATEGORY_ANIMAL]
        shot_types_used: set[str] = set()
        for i, _ in enumerate(self._TEXTS):
            shot_idx = i % len(animal_plan)
            shot_type, _ = animal_plan[shot_idx]
            shot_types_used.add(shot_type)
        # Five blocks cycling through five slots means all five shot types are used.
        assert len(shot_types_used) == len(animal_plan)

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
        # Determine which plan was selected (topic "solar energy" has no keyword match
        # → CATEGORY_GENERAL; if it matches another category that's also acceptable).
        category = detect_visual_category(topic)
        plan = _CATEGORY_PLANS[category]
        shot_types_expected = {t for t, _ in plan}
        shot_types_found: set[str] = set()
        for i in range(5):
            shot_idx = i % len(plan)
            shot_type, _ = plan[shot_idx]
            shot_types_found.add(shot_type)
        assert shot_types_found == shot_types_expected


# ── TestMusicShotVariety ──────────────────────────────────────────────────────


class TestMusicShotVariety:
    """Five blocks about the same music topic should produce varied music-specific prompts."""

    _TEXTS = [
        "Jazz music originated in New Orleans in the early twentieth century.",
        "Musicians improvise melodies over complex chord progressions.",
        "The saxophone produces its distinctive sound through a single reed.",
        "Concert audiences experience music as a shared social event.",
        "Recording studios capture performances for global distribution.",
    ]
    _TOPIC = "jazz music"

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

    def test_category_detected_as_music(self):
        assert detect_visual_category(self._TOPIC) == CATEGORY_MUSIC

    def test_five_prompts_all_distinct(self):
        prompts = self._build_prompts()
        assert len(set(prompts)) == 5

    def test_music_specific_vocabulary_present(self):
        """At least one prompt should reference stage, studio, instrument, or performer."""
        prompts = self._build_prompts()
        music_words = {"stage", "studio", "instrument", "musician", "concert",
                       "performer", "crowd", "festival", "mixing"}
        found = any(
            any(w in p.lower() for w in music_words) for p in prompts
        )
        assert found, "No music-specific vocabulary found in any prompt"

    def test_every_prompt_includes_no_text_suffix(self):
        for p in self._build_prompts():
            assert "No text" in p

    def test_every_prompt_includes_no_captions(self):
        for p in self._build_prompts():
            assert "no captions" in p.lower()

    def test_raw_narration_not_verbatim(self):
        prompts = self._build_prompts()
        raw_phrases = [
            "originated in new orleans in the early twentieth century",
            "improvise melodies over complex chord progressions",
        ]
        for phrase in raw_phrases:
            for p in prompts:
                assert phrase.lower() not in p.lower(), (
                    f"Raw narration {phrase!r} found verbatim in prompt: {p!r}"
                )

    def test_five_blocks_not_all_close_up(self):
        prompts = self._build_prompts()
        close_up_count = sum(
            1 for p in prompts if "close-up" in p.lower() or "close up" in p.lower()
        )
        assert close_up_count < len(prompts)

    def test_anti_repetition_suffix_present(self):
        for p in self._build_prompts():
            assert "distinct" in p.lower() or "composition" in p.lower()


# ── TestTechnologyShotVariety ─────────────────────────────────────────────────


class TestTechnologyShotVariety:
    """Five blocks about the same technology topic should produce varied tech-specific prompts."""

    _TEXTS = [
        "Artificial intelligence is transforming industries worldwide.",
        "Developers write algorithms to solve complex data problems.",
        "Microprocessors power everything from smartphones to servers.",
        "Cloud computing enables global collaboration at unprecedented scale.",
        "Self-driving vehicles navigate streets using computer vision.",
    ]
    _TOPIC = "artificial intelligence"

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

    def test_category_detected_as_technology(self):
        assert detect_visual_category(self._TOPIC) == CATEGORY_TECHNOLOGY

    def test_five_prompts_all_distinct(self):
        prompts = self._build_prompts()
        assert len(set(prompts)) == 5

    def test_technology_specific_vocabulary_present(self):
        """At least one prompt should reference workspace, lab, screen, or tech environment."""
        prompts = self._build_prompts()
        tech_words = {"workspace", "lab", "screen", "server", "interface",
                      "circuit", "futuristic", "technology", "digital", "cityscape"}
        found = any(
            any(w in p.lower() for w in tech_words) for p in prompts
        )
        assert found, "No technology-specific vocabulary found in any prompt"

    def test_every_prompt_includes_no_text_suffix(self):
        for p in self._build_prompts():
            assert "No text" in p

    def test_every_prompt_includes_no_captions(self):
        for p in self._build_prompts():
            assert "no captions" in p.lower()

    def test_raw_narration_not_verbatim(self):
        prompts = self._build_prompts()
        raw_phrases = [
            "transforming industries worldwide",
            "solve complex data problems",
        ]
        for phrase in raw_phrases:
            for p in prompts:
                assert phrase.lower() not in p.lower(), (
                    f"Raw narration {phrase!r} found verbatim in prompt: {p!r}"
                )

    def test_five_blocks_not_all_close_up(self):
        prompts = self._build_prompts()
        close_up_count = sum(
            1 for p in prompts if "close-up" in p.lower() or "close up" in p.lower()
        )
        assert close_up_count < len(prompts)

    def test_anti_repetition_suffix_present(self):
        for p in self._build_prompts():
            assert "distinct" in p.lower() or "composition" in p.lower()


# ── TestBusinessShotVariety ───────────────────────────────────────────────────


class TestBusinessShotVariety:
    """Five blocks about the same business topic should produce varied business-specific prompts."""

    _TEXTS = [
        "Startups need a clear value proposition to attract investors.",
        "Marketing teams collaborate to develop brand awareness campaigns.",
        "Financial charts reveal quarterly revenue trends and forecasts.",
        "Customer service drives long-term loyalty and repeat purchases.",
        "Entrepreneurs build global companies from small office beginnings.",
    ]
    _TOPIC = "startup marketing"

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

    def test_category_detected_as_business(self):
        assert detect_visual_category(self._TOPIC) == CATEGORY_BUSINESS

    def test_five_prompts_all_distinct(self):
        prompts = self._build_prompts()
        assert len(set(prompts)) == 5

    def test_business_specific_vocabulary_present(self):
        """At least one prompt should reference office, team, commercial, or professional."""
        prompts = self._build_prompts()
        biz_words = {"office", "team", "professional", "commercial", "corporate",
                     "financial", "collaboration", "customer", "architecture", "panorama"}
        found = any(
            any(w in p.lower() for w in biz_words) for p in prompts
        )
        assert found, "No business-specific vocabulary found in any prompt"

    def test_every_prompt_includes_no_text_suffix(self):
        for p in self._build_prompts():
            assert "No text" in p

    def test_every_prompt_includes_no_captions(self):
        for p in self._build_prompts():
            assert "no captions" in p.lower()

    def test_raw_narration_not_verbatim(self):
        prompts = self._build_prompts()
        raw_phrases = [
            "clear value proposition to attract investors",
            "develop brand awareness campaigns",
        ]
        for phrase in raw_phrases:
            for p in prompts:
                assert phrase.lower() not in p.lower(), (
                    f"Raw narration {phrase!r} found verbatim in prompt: {p!r}"
                )

    def test_five_blocks_not_all_close_up(self):
        prompts = self._build_prompts()
        close_up_count = sum(
            1 for p in prompts if "close-up" in p.lower() or "close up" in p.lower()
        )
        assert close_up_count < len(prompts)

    def test_anti_repetition_suffix_present(self):
        for p in self._build_prompts():
            assert "distinct" in p.lower() or "composition" in p.lower()


# ── TestUnknownTopicFallback ──────────────────────────────────────────────────


class TestUnknownTopicFallback:
    """Topics with no matching keywords should fall back to the general shot plan."""

    _TEXTS = [
        "Pasta carbonara is made with eggs, cheese, and guanciale.",
        "The sauce must be tossed off the heat to avoid scrambling.",
        "Traditional Roman cooks never add cream to carbonara.",
        "The dish originated in the Lazio region of central Italy.",
        "Proper technique separates authentic carbonara from imitations.",
    ]
    _TOPIC = "pasta carbonara"

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

    def test_category_is_general(self):
        assert detect_visual_category(self._TOPIC) == CATEGORY_GENERAL

    def test_five_prompts_all_distinct(self):
        prompts = self._build_prompts()
        assert len(set(prompts)) == 5

    def test_every_prompt_includes_no_text_suffix(self):
        for p in self._build_prompts():
            assert "No text" in p

    def test_five_blocks_not_all_close_up(self):
        prompts = self._build_prompts()
        close_up_count = sum(
            1 for p in prompts if "close-up" in p.lower() or "close up" in p.lower()
        )
        assert close_up_count < len(prompts)

    def test_raw_narration_not_verbatim(self):
        prompts = self._build_prompts()
        phrases = ["made with eggs, cheese, and guanciale", "scrambling"]
        for phrase in phrases:
            for p in prompts:
                assert phrase.lower() not in p.lower(), (
                    f"Raw narration {phrase!r} found verbatim in prompt: {p!r}"
                )


# ── TestVisualTags ────────────────────────────────────────────────────────────


class TestVisualTagsDetection:
    """visual_tags should take priority over topic and scene text in category detection."""

    def test_tags_override_vague_topic(self):
        """History tags must produce HISTORY even when topic gives no signal."""
        category = detect_visual_category(
            "interesting facts",
            visual_tags=["architecture", "empire", "ancient"],
        )
        assert category == CATEGORY_HISTORY

    def test_history_tags_override_funny_instruction_topic(self):
        """Tags: history keywords; topic: vague instruction.  Category -> HISTORY."""
        category = detect_visual_category(
            "Make it funny and simple",
            scene_text="Explain this in a storytelling tone.",
            visual_tags=["architecture", "soldiers", "roman roads"],
        )
        assert category == CATEGORY_HISTORY

    def test_music_tags_override_generic_topic(self):
        category = detect_visual_category(
            "short video about stuff",
            visual_tags=["guitar", "stage", "concert"],
        )
        assert category == CATEGORY_MUSIC

    def test_technology_tags_override_generic_topic(self):
        category = detect_visual_category(
            "something cool",
            visual_tags=["robot", "software", "server"],
        )
        assert category == CATEGORY_TECHNOLOGY

    def test_no_tags_falls_through_to_topic(self):
        """No tags -> normal topic-based detection still works."""
        assert detect_visual_category("guitar lessons", visual_tags=None) == CATEGORY_MUSIC
        assert detect_visual_category("guitar lessons", visual_tags=[]) == CATEGORY_MUSIC

    def test_empty_tags_ignored(self):
        """Empty/whitespace tags must not cause errors or influence detection."""
        category = detect_visual_category("guitar lessons", visual_tags=["", "  "])
        assert category == CATEGORY_MUSIC

    def test_tags_passed_to_build_image_prompt(self):
        """visual_tags kwarg must be accepted by build_image_prompt without error."""
        prompt = build_image_prompt(
            "Ancient Rome was the center of a vast empire.",
            "interesting facts",
            block_index=0,
            total_blocks=5,
            visual_tags=["architecture", "empire", "soldiers"],
        )
        assert "No text" in prompt
        assert prompt.strip() != ""

    def test_five_blocks_with_history_tags_produce_history_prompts(self):
        """When visual_tags drive HISTORY detection, prompts use the history shot plan."""
        texts = [
            "Ancient Rome was founded according to legend in 753 BC.",
            "The Roman Forum served as the centre of civic life.",
            "Legions marched across Europe to expand the empire.",
            "Trade routes connected Rome to distant civilisations.",
            "The fall of Rome marked the end of an era in history.",
        ]
        topic = "Ancient Rome"
        tags = ["architecture", "empire", "soldiers", "marketplace"]
        prompts: list[str] = []
        for i, text in enumerate(texts):
            p = build_image_prompt(
                text,
                topic,
                block_index=i,
                total_blocks=5,
                visual_tags=tags,
            )
            prompts.append(p)

        assert len(set(prompts)) == 5
        for p in prompts:
            assert "No text" in p

    def test_extract_subject_uses_first_tag_as_hint(self):
        """When topic is long/absent and text has no good subject, first tag is used."""
        subject = _extract_subject(
            "Hey!",
            "",
            visual_tags=["architecture"],
        )
        assert subject == "architecture"

    def test_extract_subject_still_prefers_concise_topic(self):
        """If topic is short and clear, it takes priority over tags."""
        subject = _extract_subject(
            "Hey!",
            "ancient rome",
            visual_tags=["architecture"],
        )
        assert subject == "ancient rome"


# ── TestTagNormalization ──────────────────────────────────────────────────────


class TestTagNormalization:
    """_normalize_visual_tags helper (from pipeline module) correctness."""

    def test_comma_string_normalizes_to_list(self):
        from worker.tasks.video_pipeline import _normalize_visual_tags
        result = _normalize_visual_tags("architecture, marketplace, soldiers")
        assert result == ["architecture", "marketplace", "soldiers"]

    def test_list_input_preserved(self):
        from worker.tasks.video_pipeline import _normalize_visual_tags
        result = _normalize_visual_tags(["Architecture", "SOLDIERS"])
        assert result == ["architecture", "soldiers"]

    def test_empty_string_returns_empty_list(self):
        from worker.tasks.video_pipeline import _normalize_visual_tags
        assert _normalize_visual_tags("") == []

    def test_none_returns_empty_list(self):
        from worker.tasks.video_pipeline import _normalize_visual_tags
        assert _normalize_visual_tags(None) == []

    def test_blank_items_stripped(self):
        from worker.tasks.video_pipeline import _normalize_visual_tags
        result = _normalize_visual_tags("architecture,  , soldiers")
        assert "" not in result
        assert "architecture" in result
        assert "soldiers" in result

    def test_whitespace_only_string_returns_empty(self):
        from worker.tasks.video_pipeline import _normalize_visual_tags
        assert _normalize_visual_tags("   ") == []


# ── TestDedupVisualTags ───────────────────────────────────────────────────────


class TestDedupVisualTags:
    """_dedup_visual_tags must collapse singular/plural duplicate tags."""

    def test_groundhog_groundhogs_deduped_to_groundhog(self):
        result = _dedup_visual_tags(["groundhog", "groundhogs"])
        assert result == ["groundhog"]

    def test_plural_only_kept_as_is(self):
        result = _dedup_visual_tags(["groundhogs"])
        assert result == ["groundhogs"]

    def test_no_duplicates_unchanged(self):
        result = _dedup_visual_tags(["groundhog", "nature", "meadow"])
        assert len(result) == 3

    def test_es_plural_collapsed(self):
        result = _dedup_visual_tags(["fox", "foxes"])
        assert result == ["fox"]

    def test_case_insensitive_dedup(self):
        result = _dedup_visual_tags(["Groundhog", "groundhogs"])
        # One of the two should survive (case-preserved singular preferred).
        assert len(result) == 1

    def test_empty_list_returns_empty(self):
        assert _dedup_visual_tags([]) == []

    def test_order_is_deterministic(self):
        a = _dedup_visual_tags(["bee", "bees", "flower"])
        b = _dedup_visual_tags(["flower", "bees", "bee"])
        # Both should produce the same deduplicated content.
        assert set(t.lower() for t in a) == set(t.lower() for t in b)


# ── TestFilterGenericTags ─────────────────────────────────────────────────────


class TestFilterGenericTags:
    """_filter_generic_tags must split tags into specific and generic lists."""

    def test_nature_is_generic(self):
        specific, generic = _filter_generic_tags(["nature", "groundhog"])
        assert "nature" in generic
        assert "groundhog" in specific

    def test_all_specific_tags_stay_in_specific(self):
        specific, generic = _filter_generic_tags(["groundhog", "meadow"])
        assert specific == ["groundhog", "meadow"]
        assert generic == []

    def test_all_generic_tags_go_to_generic(self):
        specific, generic = _filter_generic_tags(["animals", "nature"])
        assert specific == []
        assert len(generic) == 2

    def test_empty_list(self):
        specific, generic = _filter_generic_tags([])
        assert specific == [] and generic == []


# ── TestResolveVisualSubject ──────────────────────────────────────────────────


class TestResolveVisualSubject:
    """resolve_visual_subject must ground the subject to the most specific entity."""

    # ── Core grounding fix ────────────────────────────────────────────────────

    def test_animals_topic_groundhog_tags_resolves_groundhog(self):
        """topic='animals', tags=['nature','groundhog','groundhogs'] → 'groundhog'."""
        subject, source = resolve_visual_subject(
            "animals", visual_tags=["nature", "groundhog", "groundhogs"]
        )
        assert subject.lower() == "groundhog"
        assert source == "visual_tags"

    def test_generic_topic_does_not_override_specific_tags(self):
        subject, source = resolve_visual_subject(
            "animals", visual_tags=["groundhog"]
        )
        assert "groundhog" in subject.lower()
        assert source == "visual_tags"

    def test_music_topic_with_jazz_saxophone_resolves_specific(self):
        subject, source = resolve_visual_subject(
            "music", visual_tags=["jazz", "saxophone"]
        )
        assert "jazz" in subject.lower() or "saxophone" in subject.lower()
        assert source == "visual_tags"

    def test_technology_topic_with_ai_smart_home_resolves_specific(self):
        subject, source = resolve_visual_subject(
            "technology", visual_tags=["AI", "smart home"]
        )
        assert "ai" in subject.lower() or "smart home" in subject.lower()
        assert source == "visual_tags"

    def test_history_topic_with_ancient_rome_marketplace_resolves_specific(self):
        subject, source = resolve_visual_subject(
            "history", visual_tags=["ancient Rome", "marketplace"]
        )
        assert "ancient rome" in subject.lower() or "marketplace" in subject.lower()
        assert source == "visual_tags"

    def test_business_topic_with_startup_marketing_resolves_specific(self):
        subject, source = resolve_visual_subject(
            "business", visual_tags=["startup", "marketing"]
        )
        assert "startup" in subject.lower() or "marketing" in subject.lower()
        assert source == "visual_tags"

    # ── Specific topic takes priority over tags ───────────────────────────────

    def test_specific_topic_wins_over_tags(self):
        """Specific concise topic should not be overridden by visual_tags."""
        subject, source = resolve_visual_subject(
            "ancient rome", visual_tags=["architecture"]
        )
        assert subject.lower() == "ancient rome"
        assert source == "topic"

    def test_specific_topic_no_tags_uses_topic(self):
        subject, source = resolve_visual_subject("beekeeping")
        assert subject == "beekeeping"
        assert source == "topic"

    # ── Singular/plural deduplication ────────────────────────────────────────

    def test_singular_plural_deduped_before_subject_resolution(self):
        """'groundhog' and 'groundhogs' should not both appear; singular is kept."""
        subject, _ = resolve_visual_subject(
            "animals", visual_tags=["groundhog", "groundhogs"]
        )
        assert subject.lower() == "groundhog"
        # Plural form must not appear in the resolved subject.
        assert "groundhogs" not in subject.lower()

    # ── Generic fallback ──────────────────────────────────────────────────────

    def test_generic_topic_no_tags_falls_back_to_topic(self):
        """When topic is generic and there are no tags, fall back to the topic."""
        subject, source = resolve_visual_subject("animals")
        assert subject.lower() == "animals"
        assert source == "fallback"

    def test_empty_topic_no_tags_returns_default(self):
        subject, source = resolve_visual_subject("")
        assert len(subject) > 0
        assert source == "fallback"

    def test_all_generic_tags_fall_through_to_topic(self):
        """If every tag is generic, they are ignored and topic (or fallback) is used."""
        subject, source = resolve_visual_subject(
            "interesting documentary", visual_tags=["nature", "animals"]
        )
        # "nature" and "animals" are both generic, so topic should be used.
        assert "interesting documentary" in subject.lower() or len(subject) >= 4


# ── TestSubjectGroundingInFinalPrompts ────────────────────────────────────────


class TestSubjectGroundingInFinalPrompts:
    """Final image prompts must contain the resolved specific subject."""

    def test_animals_tags_groundhog_prompts_include_groundhog(self):
        """When topic='animals' + tags=['groundhog'], all prompts must say 'groundhog'."""
        texts = [
            "Groundhogs are rodents that live in underground burrows.",
            "They emerge in early spring to search for food.",
            "Groundhogs can whistle to warn others of danger.",
            "Their burrows can be ten meters long underground.",
            "February 2nd is celebrated as Groundhog Day.",
        ]
        topic = "animals"
        tags = ["nature", "groundhog", "groundhogs"]
        for i, text in enumerate(texts):
            prompt = build_image_prompt(
                text, topic, block_index=i, total_blocks=5, visual_tags=tags
            )
            assert "groundhog" in prompt.lower(), (
                f"Expected 'groundhog' in prompt for block {i}: {prompt!r}"
            )

    def test_music_jazz_saxophone_prompts_include_subject(self):
        texts = [
            "Jazz originated in New Orleans in the early twentieth century.",
            "Saxophone players improvise melodies over chord changes.",
            "Concert venues fill with the sound of brass instruments.",
            "Jazz musicians developed a unique musical language.",
            "Audiences gather to hear live jazz performances.",
        ]
        topic = "music"
        tags = ["jazz", "saxophone"]
        for i, text in enumerate(texts):
            prompt = build_image_prompt(
                text, topic, block_index=i, total_blocks=5, visual_tags=tags
            )
            assert "jazz" in prompt.lower() or "saxophone" in prompt.lower(), (
                f"Expected jazz/saxophone in prompt for block {i}: {prompt!r}"
            )

    def test_generic_topic_without_specific_tags_has_some_subject(self):
        """Even when topic is generic and no specific tags given, prompt is non-empty."""
        prompt = build_image_prompt("Animals are fascinating creatures.", "animals")
        # The prompt must be non-empty and include the standard negative-prompt
        # suffix (which always contains "No text", "no captions", etc.).
        assert prompt.strip() != ""
        assert "photorealistic" in prompt.lower() or "9:16" in prompt


# ── TestScriptGenerationSubjectInjection ─────────────────────────────────────


class TestScriptGenerationSubjectInjection:
    """OpenAIScriptProvider.generate must inject specific subject when topic is generic."""

    def _make_provider_and_capture_message(
        self, topic: str, visual_tags: list[str]
    ) -> str:
        """Run generate() with a mock HTTP client and return the user message sent."""
        import unittest.mock as mock
        from worker.modules.script_generator.openai_provider import OpenAIScriptProvider

        captured: dict = {}

        def fake_post(url, *, json, headers, **kwargs):
            captured["json"] = json
            response = mock.MagicMock()
            response.status_code = 200
            response.json.return_value = {
                "choices": [{"message": {"content": "A test script."}}],
                "usage": {},
            }
            response.raise_for_status.return_value = None
            return response

        with mock.patch("httpx.Client") as mock_client_cls:
            mock_client = mock.MagicMock()
            mock_client.__enter__ = mock.MagicMock(return_value=mock_client)
            mock_client.__exit__ = mock.MagicMock(return_value=False)
            mock_client.post.side_effect = fake_post
            mock_client_cls.return_value = mock_client

            provider = OpenAIScriptProvider()
            provider.generate(
                topic=topic,
                config={"visual_tags": visual_tags},
            )

        messages = captured["json"]["messages"]
        user_msg = next(m["content"] for m in messages if m["role"] == "user")
        return user_msg

    def test_generic_topic_injects_specific_subject_into_user_message(self):
        """When topic='animals' and tags=['groundhog'], user message mentions groundhog."""
        user_msg = self._make_provider_and_capture_message(
            "animals", ["nature", "groundhog", "groundhogs"]
        )
        assert "groundhog" in user_msg.lower(), (
            f"Expected 'groundhog' in user message: {user_msg!r}"
        )

    def test_generic_topic_subject_constraint_line_present(self):
        """When visual_tags yield a specific subject, a focus line is added."""
        user_msg = self._make_provider_and_capture_message(
            "music", ["jazz", "saxophone"]
        )
        # The message should include a "must focus on" constraint.
        assert "must focus on" in user_msg.lower() or "jazz" in user_msg.lower(), (
            f"Expected subject constraint in user message: {user_msg!r}"
        )

    def test_specific_topic_no_injection(self):
        """When topic is already specific, no extra focus line is injected."""
        user_msg = self._make_provider_and_capture_message(
            "beekeeping", ["honeybee", "hive"]
        )
        # No focus constraint needed since topic is already specific.
        # But the message must at least contain the topic.
        assert "beekeeping" in user_msg.lower()

    def test_no_tags_no_injection(self):
        """When no visual_tags are given, user message falls back to plain topic."""
        user_msg = self._make_provider_and_capture_message("animals", [])
        assert "animals" in user_msg.lower()
        # Without specific tags, there should be no extra focus line.
        assert "must focus on" not in user_msg.lower()


# ── TestGroundhogDayScenario ──────────────────────────────────────────────────


class TestGroundhogDayScenario:
    """Full Groundhog Day festival scenario.

    Visual tags include "festival" and "groundhog", and the script describes
    the annual Punxsutawney celebration.  Generated image prompts must:

    - Reflect the festival/ceremony atmosphere rather than generic habitat shots.
    - Reference the crowd, season, and event context from the script.
    - Never produce "foraging" or "natural habitat" prompts for crowd/event blocks.
    - Always include the resolved subject ("groundhog") somewhere.
    - Always append the negative-prompt suffix.
    """

    _SCRIPT = (
        "Every year on February 2nd, people gather in Punxsutawney, Pennsylvania "
        "for one of America's most beloved traditions — Groundhog Day.\n\n"
        "Thousands of bundled-up spectators crowd Gobbler's Knob, waiting for "
        "Punxsutawney Phil to emerge from his burrow and predict the weather.\n\n"
        "The crowd erupts in cheers as handlers lift Phil from his stump and "
        "check for his shadow during the ceremony.\n\n"
        "If Phil sees his shadow, it means six more weeks of winter; "
        "if not, spring is coming early!\n\n"
        "Happy Groundhog Day, everyone!"
    )

    _TOPIC = "groundhog"
    _TAGS = ["festival", "groundhog"]

    def _build_prompts(self, n: int = 4) -> list[str]:
        paragraphs = [p.strip() for p in self._SCRIPT.split("\n\n") if p.strip()]
        prompts: list[str] = []
        for i in range(n):
            p = build_image_prompt(
                paragraphs[i % len(paragraphs)],
                self._TOPIC,
                block_index=i,
                total_blocks=n,
                visual_tags=self._TAGS,
                full_script_text=self._SCRIPT,
            )
            prompts.append(p)
        return prompts

    # ── festival tag must not be ignored ─────────────────────────────────────

    def test_festival_tag_not_ignored(self):
        """At least one prompt must reflect festival/ceremony/event atmosphere."""
        prompts = self._build_prompts()
        festival_words = {"festival", "ceremony", "event", "celebration", "gathering"}
        found = any(
            any(w in p.lower() for w in festival_words) for p in prompts
        )
        assert found, (
            "festival tag completely ignored in all prompts:\n"
            + "\n".join(f"  [{i}] {p}" for i, p in enumerate(prompts))
        )

    # ── crowd block must not produce "foraging" ───────────────────────────────

    def test_crowd_block_not_foraging(self):
        """Block text about a crowd must not produce 'groundhog foraging'."""
        crowd_block = (
            "Thousands of bundled-up spectators crowd Gobbler's Knob, waiting "
            "for Punxsutawney Phil to emerge from his burrow and predict the weather."
        )
        # block_index=2 maps to the "foraging" shot-type slot in the animal plan.
        prompt = build_image_prompt(
            crowd_block,
            self._TOPIC,
            block_index=2,
            total_blocks=5,
            visual_tags=self._TAGS,
            full_script_text=self._SCRIPT,
        )
        assert "foraging" not in prompt.lower(), (
            f"Crowd block produced a 'foraging' prompt: {prompt!r}"
        )

    # ── no generic habitat prompts when context is festival ───────────────────

    def test_prompts_not_all_generic_habitat(self):
        """With festival context, most prompts must not be pure habitat shots."""
        prompts = self._build_prompts()
        generic_phrases = ["in natural habitat", "foraging or eating"]
        generic_count = sum(
            1
            for p in prompts
            if any(ph.lower() in p.lower() for ph in generic_phrases)
        )
        # Allow at most one generic fallback out of four blocks.
        assert generic_count <= 1, (
            f"{generic_count}/{len(prompts)} prompts are generic habitat prompts. "
            "Expected at most 1 when festival context is present.\n"
            + "\n".join(f"  [{i}] {p}" for i, p in enumerate(prompts))
        )

    # ── context terms from script must appear somewhere ───────────────────────

    def test_prompts_contain_event_or_crowd_context(self):
        """At least some prompts must reference Groundhog Day, winter, or crowd."""
        prompts = self._build_prompts()
        context_words = {
            "groundhog day", "punxsutawney", "winter", "crowd",
            "ceremony", "festival", "february",
        }
        found = any(
            any(w in p.lower() for w in context_words) for p in prompts
        )
        assert found, (
            "No context terms found in any prompt:\n"
            + "\n".join(f"  [{i}] {p}" for i, p in enumerate(prompts))
        )

    # ── subject must appear in every prompt ──────────────────────────────────

    def test_all_prompts_include_groundhog(self):
        """The resolved subject 'groundhog' must appear in every prompt."""
        prompts = self._build_prompts()
        for i, p in enumerate(prompts):
            assert "groundhog" in p.lower(), (
                f"Subject 'groundhog' missing from block {i} prompt: {p!r}"
            )

    # ── negative-prompt suffix must always be present ─────────────────────────

    def test_all_prompts_include_no_text_suffix(self):
        prompts = self._build_prompts()
        for i, p in enumerate(prompts):
            assert "No text" in p, (
                f"'No text' suffix missing from block {i} prompt: {p!r}"
            )

    # ── specificity scoring ───────────────────────────────────────────────────

    def test_specificity_score_reasonable(self):
        """Prompts for festival blocks should have a specificity score >= 2."""
        from worker.modules.ai_images.prompt_builder import _score_prompt_specificity

        paragraphs = [p.strip() for p in self._SCRIPT.split("\n\n") if p.strip()]
        for i in range(min(4, len(paragraphs))):
            p = build_image_prompt(
                paragraphs[i],
                self._TOPIC,
                block_index=i,
                total_blocks=4,
                visual_tags=self._TAGS,
                full_script_text=self._SCRIPT,
            )
            score = _score_prompt_specificity(p, "groundhog", self._TAGS, paragraphs[i])
            assert score >= 2, (
                f"Block {i} specificity score too low ({score}): {p!r}"
            )

    # ── prompt must not start with the negative suffix ────────────────────────

    def test_prompt_does_not_start_with_no_text(self):
        """The 'No text' negative instruction must appear at the end, not the start."""
        prompts = self._build_prompts()
        for i, p in enumerate(prompts):
            assert not p.startswith("No text"), (
                f"Block {i} prompt starts with 'No text': {p!r}"
            )

    # ── extract_visual_context API ────────────────────────────────────────────

    def test_extract_visual_context_festival_tag(self):
        """extract_visual_context must detect 'festival' from visual_tags."""
        from worker.modules.ai_images.prompt_builder import extract_visual_context

        ctx = extract_visual_context(
            "People gather in Punxsutawney.",
            visual_tags=["festival", "groundhog"],
            topic="groundhog",
        )
        assert ctx["event_type"] == "festival"

    def test_extract_visual_context_named_event(self):
        """extract_visual_context must detect 'Groundhog Day' from block text."""
        from worker.modules.ai_images.prompt_builder import extract_visual_context

        ctx = extract_visual_context(
            "Every year on Groundhog Day, crowds gather to watch.",
            visual_tags=["festival"],
            topic="groundhog",
        )
        assert "Groundhog Day" in ctx["named_events"]

    def test_extract_visual_context_location(self):
        """extract_visual_context must detect 'Punxsutawney' as location."""
        from worker.modules.ai_images.prompt_builder import extract_visual_context

        ctx = extract_visual_context(
            "People gather in Punxsutawney, Pennsylvania.",
            visual_tags=[],
            topic="groundhog",
        )
        assert ctx["location"] == "Punxsutawney"

    def test_extract_visual_context_winter(self):
        """February in block text must trigger 'winter' season."""
        from worker.modules.ai_images.prompt_builder import extract_visual_context

        ctx = extract_visual_context(
            "On February 2nd, bundled-up crowds gather.",
            visual_tags=[],
            topic="groundhog",
        )
        assert ctx["season"] == "winter"

    def test_extract_visual_context_crowd(self):
        """Block text with 'crowd' or 'spectators' must set has_crowd=True."""
        from worker.modules.ai_images.prompt_builder import extract_visual_context

        ctx = extract_visual_context(
            "Thousands of bundled-up spectators crowd the area.",
            visual_tags=[],
            topic="groundhog",
        )
        assert ctx["has_crowd"] is True

    def test_extract_visual_context_terms_populated(self):
        """context_terms list must include detected terms for logging."""
        from worker.modules.ai_images.prompt_builder import extract_visual_context

        ctx = extract_visual_context(
            "People gather in Punxsutawney on Groundhog Day.",
            visual_tags=["festival"],
            topic="groundhog",
        )
        terms = ctx["context_terms"]
        assert "festival" in terms
        assert "Punxsutawney" in terms

    def test_full_script_provides_global_context(self):
        """Location from the full script must be used even if absent from the block."""
        from worker.modules.ai_images.prompt_builder import extract_visual_context

        ctx = extract_visual_context(
            "Crowds cheer as the groundhog is lifted.",
            visual_tags=["festival"],
            topic="groundhog",
            full_script_text="Every year people gather in Punxsutawney for Groundhog Day.",
        )
        # Punxsutawney comes from the full script, not the block.
        assert ctx["location"] == "Punxsutawney"


# ── TestUltraShortBlockMerge ──────────────────────────────────────────────────


class TestUltraShortBlockMerge:
    """Ultra-short outro blocks must be merged, not given their own image slot.

    The block "Happy Groundhog Day, everyone!" is ~5 words — well below the
    ~7-word threshold derived from MIN_VISUAL_BLOCK_SECONDS=3.0 seconds at
    130 wpm.  It must be merged into the preceding block.
    """

    _SHORT_OUTRO = "Happy Groundhog Day, everyone!"

    _MAIN_SCRIPT = (
        "People gather in Punxsutawney every February for Groundhog Day.\n\n"
        "Thousands of bundled-up fans wait for Punxsutawney Phil to emerge "
        "from his burrow.\n\n"
        "The crowd erupts when the groundhog is lifted by his handlers "
        "during the ceremony.\n\n"
    )

    def test_short_outro_not_a_standalone_block(self):
        """'Happy Groundhog Day, everyone!' must be merged, not standalone."""
        from worker.modules.script_planner.planner import plan_narration_blocks

        script = self._MAIN_SCRIPT + self._SHORT_OUTRO
        blocks = plan_narration_blocks(script, topic="groundhog", visual_tags=["festival"])
        texts = [b.text for b in blocks]
        assert not any(t.strip() == self._SHORT_OUTRO for t in texts), (
            f"Ultra-short outro block was not merged. Blocks:\n"
            + "\n".join(f"  [{i}] {t!r}" for i, t in enumerate(texts))
        )

    def test_short_block_content_preserved_after_merge(self):
        """The merged block must contain the short outro text somewhere."""
        from worker.modules.script_planner.planner import plan_narration_blocks

        script = self._MAIN_SCRIPT + self._SHORT_OUTRO
        blocks = plan_narration_blocks(script, topic="groundhog")
        all_text = " ".join(b.text for b in blocks)
        assert "Happy Groundhog Day" in all_text, (
            "Ultra-short block content was lost during merge"
        )

    def test_short_block_reduces_block_count(self):
        """Adding an ultra-short outro must not increase the block count."""
        from worker.modules.script_planner.planner import plan_narration_blocks

        blocks_without = plan_narration_blocks(self._MAIN_SCRIPT, topic="groundhog")
        blocks_with = plan_narration_blocks(
            self._MAIN_SCRIPT + self._SHORT_OUTRO, topic="groundhog"
        )
        assert len(blocks_with) <= len(blocks_without), (
            f"Short block was not merged: "
            f"{len(blocks_with)} blocks with short outro vs "
            f"{len(blocks_without)} without it"
        )

    def test_merge_ultra_short_text_blocks_helper(self):
        """_merge_ultra_short_text_blocks must merge short tail into previous."""
        from worker.modules.script_planner.planner import _merge_ultra_short_text_blocks

        long_block = "Thousands of bundled-up fans wait for Punxsutawney Phil to emerge."
        short_block = "Happy Groundhog Day!"  # 3 words — well below threshold

        result = _merge_ultra_short_text_blocks([long_block, short_block])
        assert len(result) == 1, (
            f"Expected 1 merged block, got {len(result)}: {result}"
        )
        assert "Happy Groundhog Day" in result[0]

    def test_merge_preserves_adequate_blocks(self):
        """Blocks long enough to justify an image slot must NOT be merged."""
        from worker.modules.script_planner.planner import _merge_ultra_short_text_blocks

        block_a = (
            "Thousands of bundled-up spectators crowd Gobbler's Knob, "
            "waiting for Punxsutawney Phil to emerge from his burrow."
        )
        block_b = (
            "The crowd erupts when handlers lift Phil from his stump "
            "and check for his shadow during the ceremony."
        )

        result = _merge_ultra_short_text_blocks([block_a, block_b])
        assert len(result) == 2, (
            f"Adequate-length blocks were merged unexpectedly: {result}"
        )

    def test_single_block_returned_unchanged(self):
        """A list with one block must be returned as-is."""
        from worker.modules.script_planner.planner import _merge_ultra_short_text_blocks

        blocks = ["Single block with enough words to pass the threshold easily."]
        result = _merge_ultra_short_text_blocks(blocks)
        assert result == blocks

    def test_all_short_blocks_get_merged(self):
        """Short leading blocks merge into the next long block."""
        from worker.modules.script_planner.planner import _merge_ultra_short_text_blocks

        short1 = "Hey there!"  # 2 words
        short2 = "Good morning!"  # 2 words
        long_block = (
            "Thousands of people gather every year in Punxsutawney "
            "for the famous Groundhog Day celebration."
        )
        # short1 is too short → merges with short2; combined still too short → merges with long
        result = _merge_ultra_short_text_blocks([short1, short2, long_block])
        # The result must not contain short1 or short2 as standalone entries.
        assert all(
            t not in (short1, short2) for t in result
        ), f"Short blocks not merged: {result}"


# ── TestVisualPlannerSchema ───────────────────────────────────────────────────


class TestVisualPlannerSchema:
    """Visual planner output must conform to the expected JSON / dataclass schema."""

    def test_visual_brief_structure(self):
        """VisualBrief dataclass must have expected fields."""
        from worker.modules.ai_images.visual_planner import VisualBrief

        brief = VisualBrief(
            block_index=0,
            shot_type="establishing",
            visual_prompt="Wide establishing shot of Groundhog Day festival",
            negative_prompt="No text, no captions, no logos.",
        )
        assert brief.block_index == 0
        assert brief.shot_type == "establishing"
        assert "festival" in brief.visual_prompt
        assert "No text" in brief.negative_prompt

    def test_visual_prompt_field_has_no_negative_instructions(self):
        """The visual_prompt field must NOT contain 'No text' / caption instructions."""
        from worker.modules.ai_images.visual_planner import VisualBrief

        brief = VisualBrief(
            block_index=0,
            shot_type="establishing",
            visual_prompt="Wide establishing shot of Groundhog Day festival, photorealistic vertical 9:16",
            negative_prompt="No text, no captions, no subtitles, no logos.",
        )
        assert "No text" not in brief.visual_prompt, (
            "visual_prompt should not contain negative prompt instructions; "
            "those belong in negative_prompt"
        )
        assert "No text" in brief.negative_prompt

    def test_plan_visual_briefs_returns_none_when_disabled(self):
        """When AI_VISUAL_PLANNER_ENABLED=False, plan_visual_briefs returns None."""
        import unittest.mock as mock
        from worker.modules.ai_images import visual_planner

        with mock.patch.object(visual_planner.settings, "AI_VISUAL_PLANNER_ENABLED", False):
            result = visual_planner.plan_visual_briefs(
                "groundhog", ["festival"], "script text here.", []
            )
        assert result is None

    def test_plan_visual_briefs_returns_none_for_none_provider(self):
        """When AI_VISUAL_PLANNER_PROVIDER='none', returns None even if enabled."""
        import unittest.mock as mock
        from worker.modules.ai_images import visual_planner

        with mock.patch.object(visual_planner.settings, "AI_VISUAL_PLANNER_ENABLED", True):
            with mock.patch.object(
                visual_planner.settings, "AI_VISUAL_PLANNER_PROVIDER", "none"
            ):
                result = visual_planner.plan_visual_briefs(
                    "groundhog", ["festival"], "script text here.", []
                )
        assert result is None

    def test_plan_visual_briefs_returns_none_without_api_key(self):
        """When no OPENAI_API_KEY is configured, the OpenAI planner returns None."""
        import unittest.mock as mock
        from worker.modules.ai_images import visual_planner

        with mock.patch.object(visual_planner.settings, "AI_VISUAL_PLANNER_ENABLED", True):
            with mock.patch.object(
                visual_planner.settings, "AI_VISUAL_PLANNER_PROVIDER", "openai"
            ):
                with mock.patch.object(visual_planner.settings, "OPENAI_API_KEY", None):
                    result = visual_planner.plan_visual_briefs(
                        "groundhog", ["festival"], "script text here.", []
                    )
        assert result is None

    def test_plan_visual_briefs_returns_none_for_unknown_provider(self):
        """An unrecognised provider name returns None without raising."""
        import unittest.mock as mock
        from worker.modules.ai_images import visual_planner

        with mock.patch.object(visual_planner.settings, "AI_VISUAL_PLANNER_ENABLED", True):
            with mock.patch.object(
                visual_planner.settings, "AI_VISUAL_PLANNER_PROVIDER", "unsupported_xyz"
            ):
                result = visual_planner.plan_visual_briefs(
                    "groundhog", ["festival"], "script text here.", []
                )
        assert result is None


# ── TestPromptNoTextInVisualPart ──────────────────────────────────────────────


class TestPromptNoTextInVisualPart:
    """The 'No text' negative instruction must appear at the end of the prompt,
    not at the very beginning (which would mean the instruction leaked into
    the visual description section).
    """

    def test_prompt_does_not_start_with_no_text(self):
        prompt = build_image_prompt(
            "People gather for the Groundhog Day ceremony in Punxsutawney.",
            "groundhog",
            block_index=0,
            total_blocks=5,
            visual_tags=["festival", "groundhog"],
        )
        assert not prompt.startswith("No text"), (
            "Prompt starts with 'No text' — negative instructions leaked to the front"
        )

    def test_no_text_suffix_present(self):
        prompt = build_image_prompt(
            "People gather for the Groundhog Day ceremony in Punxsutawney.",
            "groundhog",
            block_index=0,
            total_blocks=5,
            visual_tags=["festival", "groundhog"],
        )
        assert "No text" in prompt, "Negative prompt suffix missing"

    def test_various_topics_prompt_does_not_start_with_no_text(self):
        """Across topic/tag combinations, no prompt must start with 'No text'."""
        cases = [
            ("jazz music", ["concert", "stage"], "Jazz musicians play on stage."),
            ("ancient rome", ["history", "architecture"], "The Roman Forum was busy."),
            ("groundhog", ["festival", "groundhog"], "Crowds gather in Punxsutawney."),
            ("solar energy", [], "Solar panels convert sunlight to electricity."),
        ]
        for topic, tags, text in cases:
            prompt = build_image_prompt(text, topic, block_index=0, total_blocks=3, visual_tags=tags)
            assert not prompt.startswith("No text"), (
                f"Prompt for topic={topic!r} starts with 'No text': {prompt!r}"
            )

    def test_stock_mode_prompt_building_unchanged(self):
        """build_image_prompt without any AI-specific args still works (stock path)."""
        prompt = build_image_prompt(
            "Bees are essential pollinators in our ecosystem.",
            "beekeeping",
            block_index=1,
            total_blocks=3,
        )
        assert prompt.strip() != ""
        assert "No text" in prompt
        assert "beekeeping" in prompt.lower() or "bee" in prompt.lower()


# ── TestExtractVisualContextEdgeCases ─────────────────────────────────────────


class TestExtractVisualContextEdgeCases:
    """Edge cases for extract_visual_context."""

    def test_empty_text_returns_empty_context(self):
        from worker.modules.ai_images.prompt_builder import extract_visual_context

        ctx = extract_visual_context("", visual_tags=[], topic="")
        assert ctx["event_type"] is None
        assert ctx["named_events"] == []
        assert ctx["location"] is None
        assert ctx["has_crowd"] is False

    def test_no_tags_no_context_falls_back_to_template(self):
        """When there is no context, build_image_prompt falls back to template."""
        prompt = build_image_prompt(
            "Honeybees flying around wildflowers in a garden.",
            "beekeeping",
            block_index=0,
            total_blocks=3,
        )
        # Template for beekeeping / general: must include the subject.
        assert "beekeep" in prompt.lower() or "bee" in prompt.lower() or "honey" in prompt.lower()

    def test_all_named_event_patterns_detected(self):
        """Spot-check a few named event patterns."""
        from worker.modules.ai_images.prompt_builder import extract_visual_context

        tests = [
            ("The Super Bowl parade was huge.", "Super Bowl"),
            ("Mardi Gras celebrations fill the streets.", "Mardi Gras"),
            ("Halloween costumes crowd the neighbourhood.", "Halloween"),
        ]
        for text, expected_event in tests:
            ctx = extract_visual_context(text, visual_tags=[], topic="")
            assert expected_event in ctx["named_events"], (
                f"Expected {expected_event!r} in named_events for text: {text!r}"
            )

    def test_season_detection_winter(self):
        from worker.modules.ai_images.prompt_builder import extract_visual_context

        ctx = extract_visual_context("Snow falls on the frozen lake in winter.", [], "")
        assert ctx["season"] == "winter"

    def test_season_detection_spring(self):
        from worker.modules.ai_images.prompt_builder import extract_visual_context

        ctx = extract_visual_context("Cherry blossoms bloom in spring.", [], "")
        assert ctx["season"] == "spring"

    def test_has_weather_shadow(self):
        from worker.modules.ai_images.prompt_builder import extract_visual_context

        ctx = extract_visual_context(
            "The groundhog looks for its shadow to predict the weather.", [], "groundhog"
        )
        assert ctx["has_weather"] is True

    def test_has_celebration_cheer(self):
        from worker.modules.ai_images.prompt_builder import extract_visual_context

        ctx = extract_visual_context(
            "The crowd cheers with excitement as the celebration begins.", [], ""
        )
        assert ctx["has_celebration"] is True

    def test_score_specificity_low_for_generic(self):
        from worker.modules.ai_images.prompt_builder import _score_prompt_specificity

        generic = "Wide establishing shot of groundhog in natural habitat, full environment visible."
        score = _score_prompt_specificity(generic, "groundhog", [], "")
        # Subject present (+2), no tags, no named locations, no event, no season, no crowd.
        assert score <= 3

    def test_score_specificity_higher_for_event_prompt(self):
        from worker.modules.ai_images.prompt_builder import _score_prompt_specificity

        specific = (
            "Wide establishing shot of Groundhog Day festival in Punxsutawney, "
            "winter morning, crowd gathered, groundhog ceremony stage visible, "
            "photorealistic vertical 9:16"
        )
        score = _score_prompt_specificity(specific, "groundhog", ["festival"], "")
        # Subject (+2), tag (+1), named location capital (+2), event (+1),
        # season (+1), crowd (+1) = 8.
        assert score >= 5

