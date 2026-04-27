"""Tests for scene quality scoring and auto-rewrite.

Covers:
1.  Generic scene gets low score
2.  Good scene gets high score
3.  Rewrite improves score (mocked LLM)
4.  Max retry stops at 2
5.  Rewritten scene is different from original
6.  Scenes keep valid StoryboardScene structure after rewrite
7.  Pipeline continues even if rewrite fails (LLM error)
"""
from __future__ import annotations

import dataclasses
import unittest.mock as mock

import pytest

from worker.modules.storyboard.models import StoryboardScene
from worker.modules.storyboard.quality import (
    _descriptions_similar,
    is_generic_scene,
    rewrite_scene,
    score_scene,
    validate_and_improve_storyboard,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_scene(
    *,
    index: int = 0,
    visual_description: str = "",
    context_terms: list[str] | None = None,
    visual_tags_used: list[str] | None = None,
    shot_type: str = "establishing",
    subject: str = "groundhog",
    reuse_previous: bool = False,
    narration_text: str = "Some narration.",
) -> StoryboardScene:
    return StoryboardScene(
        id=f"scene-{index}",
        index=index,
        narration_block_id=f"block-{index}",
        narration_text=narration_text,
        shot_type=shot_type,
        visual_description=visual_description,
        image_prompt=f"Prompt for {visual_description[:40]}",
        negative_prompt="No text, no captions.",
        subject=subject,
        category="animal",
        context_terms=context_terms or [],
        visual_tags_used=visual_tags_used or [],
        reuse_previous=reuse_previous,
    )


_GOOD_DESC = (
    "Crowd gathered at a winter festival in a small town square, "
    "people wearing coats and holding hot drinks, morning light, "
    "groundhog ceremony on a wooden stage"
)

_GENERIC_DESC = "groundhog in natural habitat"


# ---------------------------------------------------------------------------
# 1. Generic scene gets low score
# ---------------------------------------------------------------------------


class TestGenericSceneGetsLowScore:
    def test_natural_habitat_is_low(self):
        scene = _make_scene(visual_description=_GENERIC_DESC)
        assert score_scene(scene) < 60

    def test_technology_concept_is_low(self):
        scene = _make_scene(
            visual_description="technology concept for smart devices",
            subject="smart device",
        )
        assert score_scene(scene) < 60

    def test_business_environment_is_low(self):
        scene = _make_scene(
            visual_description="business environment with charts",
            subject="startup",
        )
        assert score_scene(scene) < 60

    def test_futuristic_scene_is_low(self):
        scene = _make_scene(visual_description="futuristic scene with robots")
        assert score_scene(scene) < 60

    def test_very_short_desc_is_low(self):
        scene = _make_scene(visual_description="a groundhog")
        assert score_scene(scene) < 60


# ---------------------------------------------------------------------------
# 2. Good scene gets high score
# ---------------------------------------------------------------------------


class TestGoodSceneGetsHighScore:
    def test_specific_festival_scene_scores_high(self):
        scene = _make_scene(
            visual_description=_GOOD_DESC,
            context_terms=["festival", "crowd", "winter"],
            visual_tags_used=["festival", "crowd"],
        )
        assert score_scene(scene) >= 60

    def test_scene_with_people_and_context_scores_high(self):
        scene = _make_scene(
            visual_description=(
                "Close-up of a groundhog being held by handlers on stage "
                "at Groundhog Day ceremony, crowd visible in background"
            ),
            context_terms=["ceremony", "crowd"],
            visual_tags_used=["crowd"],
        )
        assert score_scene(scene) >= 60

    def test_reuse_previous_gets_neutral_score(self):
        scene = _make_scene(reuse_previous=True)
        assert score_scene(scene) == 70

    def test_different_from_previous_adds_bonus(self):
        prev = _make_scene(
            index=0,
            visual_description=(
                "Wide shot of festival square with crowd cheering at winter event, "
                "groundhog visible on stage"
            ),
            context_terms=["festival", "crowd"],
            visual_tags_used=["festival"],
        )
        # A scene clearly different from prev — equally rich but varied.
        different = _make_scene(
            index=1,
            visual_description=(
                "Medium shot of handlers lifting groundhog at ceremony stage, "
                "audience gathered around in winter clothes"
            ),
            context_terms=["ceremony", "crowd"],
            visual_tags_used=["ceremony"],
        )
        # A scene that is nearly identical to prev — same richness, no variety.
        similar = _make_scene(
            index=1,
            visual_description=(
                "Wide shot of festival square with crowd cheering at winter event, "
                "groundhog visible on stage"
            ),
            context_terms=["festival", "crowd"],
            visual_tags_used=["festival"],
        )
        score_different = score_scene(different, previous_scene=prev)
        score_similar = score_scene(similar, previous_scene=prev)
        # The different scene should score higher than the similar one because
        # it receives the +15 variety bonus while the similar one gets the -15
        # repetition penalty.
        assert score_different > score_similar, (
            f"Expected different scene ({score_different}) to outscore "
            f"similar scene ({score_similar})"
        )


# ---------------------------------------------------------------------------
# 3. Rewrite improves score (mocked LLM)
# ---------------------------------------------------------------------------


class TestRewriteImprovesScore:
    _IMPROVED_DESC = (
        "Crowd of spectators in winter coats gathering around the groundhog "
        "stage at dawn in a snowy town square, festival atmosphere"
    )

    def _mock_rewrite(self, scene: StoryboardScene, *args, **kwargs) -> StoryboardScene:
        """Simulate a successful LLM rewrite by returning an improved scene."""
        return dataclasses.replace(
            scene,
            visual_description=self._IMPROVED_DESC,
            context_terms=["festival", "crowd", "winter"],
            visual_tags_used=["festival", "crowd"],
            source="llm",
        )

    def test_rewrite_raises_score(self):
        bad_scene = _make_scene(visual_description=_GENERIC_DESC)
        good_scene = self._mock_rewrite(bad_scene)
        assert score_scene(good_scene) > score_scene(bad_scene)

    def test_validate_calls_rewrite_for_low_score(self):
        bad_scene = _make_scene(visual_description=_GENERIC_DESC)

        with mock.patch(
            "worker.modules.storyboard.quality.rewrite_scene",
            side_effect=self._mock_rewrite,
        ) as mock_rewrite:
            with mock.patch("app.config.settings.STORYBOARD_QUALITY_THRESHOLD", 60):
                with mock.patch("app.config.settings.STORYBOARD_QUALITY_MAX_RETRIES", 2):
                    result = validate_and_improve_storyboard(
                        [bad_scene], "groundhog", ["festival"], "script text"
                    )

        assert mock_rewrite.called
        assert len(result) == 1
        assert result[0].visual_description == self._IMPROVED_DESC

    def test_validate_skips_rewrite_for_high_score(self):
        good_scene = _make_scene(
            visual_description=_GOOD_DESC,
            context_terms=["festival", "crowd", "winter"],
            visual_tags_used=["festival", "crowd"],
        )

        with mock.patch(
            "worker.modules.storyboard.quality.rewrite_scene",
        ) as mock_rewrite:
            result = validate_and_improve_storyboard(
                [good_scene], "groundhog", ["festival"], "script"
            )

        mock_rewrite.assert_not_called()
        assert len(result) == 1


# ---------------------------------------------------------------------------
# 4. Max retry stops at 2
# ---------------------------------------------------------------------------


class TestMaxRetryStopsAtTwo:
    def test_max_two_rewrite_calls(self):
        """validate_and_improve_storyboard must call rewrite_scene at most
        STORYBOARD_QUALITY_MAX_RETRIES times per scene."""
        bad_scene = _make_scene(visual_description=_GENERIC_DESC)
        call_count = {"n": 0}

        def _still_bad(scene, *a, **kw):
            call_count["n"] += 1
            # Return a scene that is still slightly improved but still below
            # threshold so the loop keeps trying.
            return dataclasses.replace(
                scene, visual_description="groundhog in nature near pond"
            )

        with mock.patch(
            "worker.modules.storyboard.quality.rewrite_scene",
            side_effect=_still_bad,
        ):
            with mock.patch("app.config.settings.STORYBOARD_QUALITY_THRESHOLD", 60):
                with mock.patch("app.config.settings.STORYBOARD_QUALITY_MAX_RETRIES", 2):
                    validate_and_improve_storyboard(
                        [bad_scene], "groundhog", [], "script"
                    )

        assert call_count["n"] <= 2, (
            f"Expected at most 2 rewrite calls, got {call_count['n']}"
        )

    def test_accepts_best_version_after_max_retries(self):
        """After exhausting retries the best version should be returned."""
        bad_scene = _make_scene(visual_description=_GENERIC_DESC)
        attempt_descs = [
            "groundhog near burrow in forest",  # still bad
            "groundhog at festival crowd ceremony stage winter",  # better
        ]
        attempt_iter = iter(attempt_descs)

        def _improving_rewrite(scene, *a, **kw):
            desc = next(attempt_iter, attempt_descs[-1])
            return dataclasses.replace(
                scene,
                visual_description=desc,
                context_terms=["ceremony"] if "ceremony" in desc else [],
            )

        with mock.patch(
            "worker.modules.storyboard.quality.rewrite_scene",
            side_effect=_improving_rewrite,
        ):
            with mock.patch("app.config.settings.STORYBOARD_QUALITY_THRESHOLD", 60):
                with mock.patch("app.config.settings.STORYBOARD_QUALITY_MAX_RETRIES", 2):
                    result = validate_and_improve_storyboard(
                        [bad_scene], "groundhog", [], "script"
                    )

        # The best description seen across all attempts should be selected.
        assert result[0].visual_description != _GENERIC_DESC


# ---------------------------------------------------------------------------
# 5. Rewritten scene is different from original
# ---------------------------------------------------------------------------


class TestRewrittenSceneIsDifferent:
    def test_rewrite_changes_visual_description(self):
        bad_scene = _make_scene(visual_description=_GENERIC_DESC)
        improved_desc = (
            "Wide shot of Groundhog Day ceremony in Punxsutawney, crowd of "
            "bundled-up spectators on a snowy hillside, groundhog on stage"
        )

        def _mock_llm(scene, *a, **kw):
            return dataclasses.replace(
                scene,
                visual_description=improved_desc,
                context_terms=["festival", "crowd"],
                visual_tags_used=["festival"],
            )

        with mock.patch(
            "worker.modules.storyboard.quality.rewrite_scene",
            side_effect=_mock_llm,
        ):
            result = validate_and_improve_storyboard(
                [bad_scene], "groundhog", ["festival"], "script"
            )

        assert result[0].visual_description != _GENERIC_DESC

    def test_descriptions_similar_detects_copy(self):
        a = "groundhog in natural habitat near its burrow"
        assert _descriptions_similar(a, a)

    def test_descriptions_similar_detects_difference(self):
        a = "wide shot of groundhog ceremony crowd Punxsutawney festival winter"
        b = "close-up saxophone musician performing smoky jazz club stage"
        assert not _descriptions_similar(a, b)


# ---------------------------------------------------------------------------
# 6. Scenes keep valid StoryboardScene structure after rewrite
# ---------------------------------------------------------------------------


class TestSceneStructurePreserved:
    def test_rewrite_preserves_required_fields(self):
        """After rewrite, timing, narration_block_id, index, subject must be intact."""
        original = _make_scene(
            index=2,
            visual_description=_GENERIC_DESC,
            narration_text="Phil emerges from his burrow.",
        )
        original = dataclasses.replace(
            original,
            start_time=10.0,
            end_time=15.0,
            duration=5.0,
        )
        improved_desc = (
            "Handlers lift groundhog from burrow stage at winter ceremony, "
            "crowd cheering in snowy town square"
        )

        def _mock_llm(scene, *a, **kw):
            return dataclasses.replace(
                scene,
                visual_description=improved_desc,
                context_terms=["ceremony"],
                visual_tags_used=[],
            )

        with mock.patch(
            "worker.modules.storyboard.quality.rewrite_scene",
            side_effect=_mock_llm,
        ):
            result = validate_and_improve_storyboard(
                [original], "groundhog", [], "script"
            )

        s = result[0]
        assert isinstance(s, StoryboardScene)
        assert s.index == original.index
        assert s.narration_block_id == original.narration_block_id
        assert s.narration_text == original.narration_text
        assert s.subject == original.subject
        assert s.start_time == original.start_time
        assert s.end_time == original.end_time
        assert s.duration == original.duration
        assert s.reuse_previous is False

    def test_validate_preserves_scene_count(self):
        scenes = [
            _make_scene(index=i, visual_description=_GENERIC_DESC) for i in range(4)
        ]
        with mock.patch(
            "worker.modules.storyboard.quality.rewrite_scene",
            side_effect=lambda s, *a, **kw: dataclasses.replace(
                s, visual_description="groundhog at festival stage ceremony crowd winter"
            ),
        ):
            result = validate_and_improve_storyboard(scenes, "groundhog", [], "script")
        assert len(result) == len(scenes)

    def test_reuse_previous_scenes_pass_through_unchanged(self):
        reuse = _make_scene(index=3, reuse_previous=True)
        with mock.patch(
            "worker.modules.storyboard.quality.rewrite_scene"
        ) as mock_rw:
            result = validate_and_improve_storyboard(
                [reuse], "groundhog", [], "script"
            )
        mock_rw.assert_not_called()
        assert result[0].reuse_previous is True


# ---------------------------------------------------------------------------
# 7. Pipeline continues even if rewrite fails
# ---------------------------------------------------------------------------


class TestPipelineContinuesOnRewriteFailure:
    def test_llm_error_returns_original_scene(self):
        """rewrite_scene must return the original when LLM raises an exception."""
        bad_scene = _make_scene(visual_description=_GENERIC_DESC)

        with mock.patch(
            "worker.modules.storyboard.quality._call_rewrite_llm",
            side_effect=RuntimeError("LLM unavailable"),
        ):
            result = rewrite_scene(bad_scene, "groundhog", ["festival"], "script")

        assert result is bad_scene

    def test_no_api_key_returns_original_scene(self):
        """rewrite_scene must return the original when no API key is configured."""
        bad_scene = _make_scene(visual_description=_GENERIC_DESC)

        with mock.patch("app.config.settings.OPENAI_API_KEY", None):
            result = rewrite_scene(bad_scene, "groundhog", ["festival"], "script")

        assert result is bad_scene

    def test_validate_pipeline_continues_when_rewrite_always_fails(self):
        """validate_and_improve_storyboard must still return all scenes even if
        every rewrite_scene call returns the original unchanged."""
        scenes = [
            _make_scene(index=i, visual_description=_GENERIC_DESC) for i in range(3)
        ]
        # rewrite_scene returns input unchanged every time
        with mock.patch(
            "worker.modules.storyboard.quality.rewrite_scene",
            side_effect=lambda scene, *a, **kw: scene,
        ):
            with mock.patch("app.config.settings.STORYBOARD_QUALITY_THRESHOLD", 60):
                with mock.patch("app.config.settings.STORYBOARD_QUALITY_MAX_RETRIES", 2):
                    result = validate_and_improve_storyboard(
                        scenes, "groundhog", [], "script"
                    )

        assert len(result) == len(scenes)
        # Original descriptions preserved when rewrite always fails.
        for i, s in enumerate(result):
            assert s.visual_description == _GENERIC_DESC
            assert s.index == i

    def test_validate_skips_quality_for_disabled_reuse_previous(self):
        """Scenes with reuse_previous=True must never be sent to rewrite."""
        scenes = [
            _make_scene(index=0, visual_description=_GOOD_DESC,
                        context_terms=["festival"], visual_tags_used=["festival"]),
            _make_scene(index=1, reuse_previous=True),
        ]
        with mock.patch(
            "worker.modules.storyboard.quality.rewrite_scene"
        ) as mock_rw:
            result = validate_and_improve_storyboard(
                scenes, "groundhog", [], "script"
            )

        mock_rw.assert_not_called()
        assert result[1].reuse_previous is True


# ---------------------------------------------------------------------------
# Acceptance criteria: bad → good transformation
# ---------------------------------------------------------------------------


class TestAcceptanceCriteria:
    """Verify the canonical acceptance example from the spec."""

    def test_bad_groundhog_scene_is_generic(self):
        scene = _make_scene(
            visual_description="groundhog in natural habitat",
            context_terms=[],
            visual_tags_used=[],
        )
        assert is_generic_scene(scene)

    def test_bad_groundhog_scene_scores_low(self):
        scene = _make_scene(
            visual_description="groundhog in natural habitat",
            context_terms=[],
            visual_tags_used=[],
        )
        assert score_scene(scene) < 60

    def test_good_groundhog_scene_scores_high(self):
        scene = _make_scene(
            visual_description=(
                "crowd gathered at winter festival in small town with groundhog ceremony"
            ),
            context_terms=["festival", "crowd", "winter"],
            visual_tags_used=["festival", "crowd"],
        )
        assert score_scene(scene) >= 60
        assert not is_generic_scene(scene)

    def test_score_increases_after_rewrite_mock(self):
        bad_scene = _make_scene(
            visual_description="groundhog in natural habitat",
            context_terms=[],
            visual_tags_used=[],
        )
        good_desc = (
            "crowd gathered at winter festival in small town with groundhog ceremony"
        )
        improved = dataclasses.replace(
            bad_scene,
            visual_description=good_desc,
            context_terms=["festival", "crowd", "winter"],
            visual_tags_used=["festival", "crowd"],
        )
        assert score_scene(improved) > score_scene(bad_scene)
