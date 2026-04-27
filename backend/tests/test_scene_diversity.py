"""Tests for global scene diversity enforcement and multi-image selection.

Covers:
1.  Repeated scenes trigger diversity penalty
2.  Rewrite produces different scene when diversity hint is used
3.  compute_scene_similarity score works correctly
4.  generate_and_select_best_image generates N images
5.  Best image is selected by score_image
6.  Pipeline still completes (generate_and_select_best_image with n=1)
7.  Performance acceptable (multi-gen with mock provider is fast)
"""
from __future__ import annotations

import dataclasses
import time
import unittest.mock as mock
from pathlib import Path

import pytest

from worker.modules.storyboard.models import StoryboardScene
from worker.modules.storyboard.quality import (
    _DIVERSITY_SIMILARITY_THRESHOLD,
    compute_scene_similarity,
    score_scene,
    validate_and_improve_storyboard,
)
from worker.modules.ai_images.base import GeneratedImage
from worker.modules.ai_images.image_selector import (
    generate_and_select_best_image,
    score_image,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_scene(
    *,
    index: int = 0,
    visual_description: str = "festival crowd winter groundhog ceremony stage",
    context_terms: list[str] | None = None,
    visual_tags_used: list[str] | None = None,
    shot_type: str = "wide",
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
        context_terms=context_terms or ["festival", "crowd"],
        visual_tags_used=visual_tags_used or ["festival"],
        reuse_previous=reuse_previous,
    )


def _make_generated_image(path: Path, provider: str = "mock") -> GeneratedImage:
    return GeneratedImage(
        path=path,
        provider=provider,
        prompt="test prompt",
        scene_id="scene-0",
        width=576,
        height=1024,
        metadata={},
    )


def _write_solid_png(path: Path, width: int = 576, height: int = 1024) -> None:
    """Write a minimal valid solid-colour PNG using Pillow."""
    import struct
    import zlib

    def _chunk(name: bytes, data: bytes) -> bytes:
        payload = name + data
        crc = zlib.crc32(payload) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + payload + struct.pack(">I", crc)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    row = b"\x00" + b"\x80\x80\x80" * width
    raw = row * height
    idat_data = zlib.compress(raw)
    png = (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", ihdr)
        + _chunk(b"IDAT", idat_data)
        + _chunk(b"IEND", b"")
    )
    path.write_bytes(png)


# ---------------------------------------------------------------------------
# 1. Repeated scenes trigger diversity penalty
# ---------------------------------------------------------------------------


class TestDiversityPenalty:
    def test_identical_scene_triggers_penalty(self):
        """A scene identical to an accepted scene should score lower due to
        the global diversity penalty."""
        desc = (
            "Wide shot of groundhog ceremony stage at winter festival, "
            "crowd gathered in front"
        )
        accepted = _make_scene(
            index=0,
            visual_description=desc,
            shot_type="wide",
            subject="groundhog",
            context_terms=["festival", "crowd"],
        )
        scene_dup = _make_scene(
            index=1,
            visual_description=desc,
            shot_type="wide",
            subject="groundhog",
            context_terms=["festival", "crowd"],
        )
        score_no_history = score_scene(scene_dup, accepted_scenes=None)
        score_with_history = score_scene(scene_dup, accepted_scenes=[accepted])
        assert score_with_history < score_no_history, (
            f"Expected diversity penalty: "
            f"score_no_history={score_no_history}, "
            f"score_with_history={score_with_history}"
        )

    def test_high_similarity_triggers_penalty(self):
        """Two scenes with nearly identical descriptions should trigger the
        diversity penalty (similarity > 0.7)."""
        desc_a = (
            "Wide festival groundhog ceremony stage crowd winter snow morning"
        )
        desc_b = (
            "Wide festival groundhog ceremony stage crowd winter snow dawn"
        )
        scene_a = _make_scene(index=0, visual_description=desc_a, shot_type="wide")
        scene_b = _make_scene(index=1, visual_description=desc_b, shot_type="wide")

        sim = compute_scene_similarity(scene_a, scene_b)
        if sim > _DIVERSITY_SIMILARITY_THRESHOLD:
            score_without = score_scene(scene_b, accepted_scenes=None)
            score_with = score_scene(scene_b, accepted_scenes=[scene_a])
            assert score_with < score_without

    def test_low_similarity_no_penalty(self):
        """Scenes with clearly different descriptions should NOT trigger the
        diversity penalty."""
        scene_a = _make_scene(
            index=0,
            visual_description=(
                "Wide shot winter festival groundhog ceremony stage crowd snow"
            ),
            shot_type="wide",
        )
        scene_b = _make_scene(
            index=1,
            visual_description=(
                "Close-up saxophone player performing on stage in smoky jazz club"
            ),
            shot_type="close",
            subject="musician",
            context_terms=["concert", "jazz"],
        )
        sim = compute_scene_similarity(scene_a, scene_b)
        assert sim <= _DIVERSITY_SIMILARITY_THRESHOLD
        # Penalty should not apply.
        score_without = score_scene(scene_b, accepted_scenes=None)
        score_with = score_scene(scene_b, accepted_scenes=[scene_a])
        assert score_with == score_without

    def test_diversity_penalty_compares_all_accepted_not_just_previous(self):
        """The global diversity penalty must consider ALL accepted scenes, not
        just the immediately preceding one."""
        desc_repeated = (
            "Wide shot winter festival groundhog ceremony stage crowd snow"
        )
        scene_0 = _make_scene(index=0, visual_description=desc_repeated)
        scene_1 = _make_scene(
            index=1,
            visual_description=(
                "Close-up of groundhog peeking over stage with handler"
            ),
        )
        scene_2 = _make_scene(index=2, visual_description=desc_repeated)

        accepted = [scene_0, scene_1]
        score_without = score_scene(scene_2, accepted_scenes=None)
        score_with = score_scene(scene_2, accepted_scenes=accepted)
        assert score_with < score_without


# ---------------------------------------------------------------------------
# 2. Rewrite produces different scene (diversity hint used)
# ---------------------------------------------------------------------------


class TestDiversityRewrite:
    def test_diversity_hint_passed_to_rewrite_when_similar(self):
        """When a scene is globally similar to accepted scenes,
        validate_and_improve_storyboard passes a diversity_hint to rewrite_scene."""
        desc = (
            "Wide shot winter festival groundhog ceremony stage crowd snow morning"
        )
        accepted_scene = _make_scene(index=0, visual_description=desc, shot_type="wide")

        # Scene 1 is very similar — should trigger diversity rewrite.
        scene_to_improve = _make_scene(
            index=1, visual_description=desc, shot_type="wide"
        )

        rewrite_calls: list[dict] = []

        def _mock_rewrite(scene, topic, tags, script, diversity_hint=None):
            rewrite_calls.append({"diversity_hint": diversity_hint})
            # Return a scene with a clearly different description so it passes.
            return dataclasses.replace(
                scene,
                visual_description=(
                    "Aerial view of concert hall interior with audience in evening wear"
                ),
                shot_type="aerial",
                context_terms=["concert", "audience"],
                visual_tags_used=["concert"],
            )

        with mock.patch(
            "worker.modules.storyboard.quality.rewrite_scene",
            side_effect=_mock_rewrite,
        ):
            with mock.patch("app.config.settings.STORYBOARD_QUALITY_THRESHOLD", 0):
                with mock.patch("app.config.settings.STORYBOARD_QUALITY_MAX_RETRIES", 1):
                    # Pass accepted_scene as the existing first scene so that
                    # scene_to_improve is scored against it.
                    result = validate_and_improve_storyboard(
                        [accepted_scene, scene_to_improve],
                        "groundhog",
                        ["festival"],
                        "script",
                    )

        # At least one call should have received a diversity_hint.
        hints = [c["diversity_hint"] for c in rewrite_calls if c["diversity_hint"]]
        assert hints, (
            "Expected at least one rewrite call with a diversity_hint "
            f"but got calls: {rewrite_calls}"
        )

    def test_rewrite_result_differs_from_original(self):
        """The mock-rewritten scene must have a different description."""
        original = _make_scene(
            index=0,
            visual_description="groundhog near burrow in woods",
            context_terms=[],
            visual_tags_used=[],
        )
        improved_desc = (
            "Close-up of groundhog emerging from burrow at ceremony stage, "
            "handlers and crowd visible in background"
        )

        with mock.patch(
            "worker.modules.storyboard.quality.rewrite_scene",
            side_effect=lambda s, *a, **kw: dataclasses.replace(
                s,
                visual_description=improved_desc,
                context_terms=["ceremony"],
                visual_tags_used=["festival"],
            ),
        ):
            result = validate_and_improve_storyboard(
                [original], "groundhog", ["festival"], "script"
            )

        assert result[0].visual_description != original.visual_description


# ---------------------------------------------------------------------------
# 3. compute_scene_similarity score works correctly
# ---------------------------------------------------------------------------


class TestComputeSceneSimilarity:
    def test_identical_scenes_have_high_similarity(self):
        desc = "wide shot winter festival groundhog ceremony crowd stage"
        scene_a = _make_scene(
            index=0,
            visual_description=desc,
            shot_type="wide",
            subject="groundhog",
            context_terms=["festival"],
        )
        scene_b = _make_scene(
            index=1,
            visual_description=desc,
            shot_type="wide",
            subject="groundhog",
            context_terms=["festival"],
        )
        sim = compute_scene_similarity(scene_a, scene_b)
        assert sim > 0.7, f"Expected high similarity, got {sim}"

    def test_different_scenes_have_low_similarity(self):
        scene_a = _make_scene(
            index=0,
            visual_description=(
                "Wide winter festival groundhog ceremony stage crowd snow"
            ),
            shot_type="wide",
            subject="groundhog",
        )
        scene_b = _make_scene(
            index=1,
            visual_description=(
                "Close-up saxophone musician jazz club dim stage spotlight"
            ),
            shot_type="close",
            subject="musician",
            context_terms=["concert"],
            visual_tags_used=["music"],
        )
        sim = compute_scene_similarity(scene_a, scene_b)
        assert sim < 0.4, f"Expected low similarity, got {sim}"

    def test_similarity_is_symmetric(self):
        scene_a = _make_scene(index=0, visual_description="crowd winter festival stage")
        scene_b = _make_scene(index=1, visual_description="festival crowd winter ceremony")
        sim_ab = compute_scene_similarity(scene_a, scene_b)
        sim_ba = compute_scene_similarity(scene_b, scene_a)
        assert abs(sim_ab - sim_ba) < 1e-9

    def test_similarity_in_range_zero_to_one(self):
        scene_a = _make_scene(index=0)
        scene_b = _make_scene(index=1, visual_description="completely different topic rock concert")
        sim = compute_scene_similarity(scene_a, scene_b)
        assert 0.0 <= sim <= 1.0

    def test_different_shot_types_reduce_similarity(self):
        desc = "winter festival groundhog ceremony stage crowd"
        scene_wide = _make_scene(index=0, visual_description=desc, shot_type="wide")
        scene_close = _make_scene(index=1, visual_description=desc, shot_type="close")
        sim_same_shot = compute_scene_similarity(scene_wide, scene_wide)
        sim_diff_shot = compute_scene_similarity(scene_wide, scene_close)
        assert sim_same_shot >= sim_diff_shot


# ---------------------------------------------------------------------------
# 4. generate_and_select_best_image generates N images
# ---------------------------------------------------------------------------


class TestMultiImageGeneration:
    def _make_provider(self, tmp_path: Path) -> mock.MagicMock:
        """Return a mock provider that writes a tiny PNG on generate_image."""
        provider = mock.MagicMock()

        call_count = {"n": 0}

        def _fake_generate(prompt, output_path, *, aspect_ratio="9:16", metadata=None):
            _write_solid_png(output_path, width=64, height=114)
            call_count["n"] += 1
            return GeneratedImage(
                path=output_path,
                provider="mock",
                prompt=prompt,
                scene_id="test",
                width=64,
                height=114,
                metadata={},
            )

        provider.generate_image.side_effect = _fake_generate
        provider._call_count = call_count
        return provider

    def test_n_variations_calls_provider_n_times(self, tmp_path):
        provider = self._make_provider(tmp_path)
        output = tmp_path / "scene_000.png"
        result = generate_and_select_best_image(
            provider,
            "groundhog festival crowd",
            output,
            n_variations=3,
        )
        assert provider.generate_image.call_count == 3
        assert result.metadata["variations_generated"] == 3

    def test_n_equals_one_calls_provider_once(self, tmp_path):
        provider = self._make_provider(tmp_path)
        output = tmp_path / "scene_000.png"
        result = generate_and_select_best_image(
            provider,
            "groundhog festival",
            output,
            n_variations=1,
        )
        assert provider.generate_image.call_count == 1
        # Fast-path: no variation metadata
        assert "variations_generated" not in result.metadata

    def test_variation_one_uses_original_prompt(self, tmp_path):
        prompts = []
        provider = mock.MagicMock()

        def _fake(prompt, output_path, *, aspect_ratio="9:16", metadata=None):
            _write_solid_png(output_path, width=64, height=114)
            prompts.append(prompt)
            return GeneratedImage(
                path=output_path, provider="mock", prompt=prompt,
                scene_id="", width=64, height=114, metadata={},
            )

        provider.generate_image.side_effect = _fake
        original_prompt = "exact original prompt"
        generate_and_select_best_image(
            provider, original_prompt, tmp_path / "out.png", n_variations=2
        )
        assert prompts[0] == original_prompt
        assert prompts[1] != original_prompt  # variation suffix appended

    def test_result_path_is_canonical_output_path(self, tmp_path):
        provider = self._make_provider(tmp_path)
        output = tmp_path / "scene_007.png"
        result = generate_and_select_best_image(
            provider, "test", output, n_variations=2
        )
        assert result.path == output

    def test_variation_files_cleaned_up_by_default(self, tmp_path):
        provider = self._make_provider(tmp_path)
        output = tmp_path / "scene_000.png"
        generate_and_select_best_image(
            provider, "test", output, n_variations=2, keep_variations=False
        )
        # Only the canonical output file should remain.
        leftover = [
            p for p in tmp_path.iterdir()
            if p.suffix == ".png" and p != output
        ]
        assert leftover == [], f"Unexpected leftover files: {leftover}"

    def test_variation_files_kept_when_flag_set(self, tmp_path):
        provider = self._make_provider(tmp_path)
        output = tmp_path / "scene_000.png"
        generate_and_select_best_image(
            provider, "test", output, n_variations=2, keep_variations=True
        )
        all_pngs = list(tmp_path.glob("*.png"))
        # Output + at least 1 variation should exist.
        assert len(all_pngs) >= 2


# ---------------------------------------------------------------------------
# 5. Best image is selected by score_image
# ---------------------------------------------------------------------------


class TestImageSelection:
    def test_score_image_nonexistent_returns_zero(self, tmp_path):
        assert score_image(tmp_path / "missing.png") == 0

    def test_score_image_empty_file_returns_low(self, tmp_path):
        empty = tmp_path / "empty.png"
        empty.write_bytes(b"")
        assert score_image(empty) < 40

    def test_score_image_valid_png_returns_high(self, tmp_path):
        img = tmp_path / "valid.png"
        _write_solid_png(img, width=576, height=1024)
        s = score_image(img)
        assert s >= 40, f"Expected ≥40 for a valid PNG, got {s}"

    def test_best_image_selected_from_candidates(self, tmp_path):
        """generate_and_select_best_image should pick the image with the
        highest score_image score (highest file size → highest score here)."""
        call_idx = {"n": 0}

        def _fake_generate(prompt, output_path, *, aspect_ratio="9:16", metadata=None):
            i = call_idx["n"]
            call_idx["n"] += 1
            # Variation 0 → tiny (low score), Variation 1 → large (high score).
            if i == 0:
                _write_solid_png(output_path, width=4, height=4)
            else:
                _write_solid_png(output_path, width=576, height=1024)
            return GeneratedImage(
                path=output_path, provider="mock", prompt=prompt,
                scene_id="", width=576 if i == 1 else 4,
                height=1024 if i == 1 else 4, metadata={},
            )

        provider = mock.MagicMock()
        provider.generate_image.side_effect = _fake_generate

        output = tmp_path / "scene_000.png"
        result = generate_and_select_best_image(
            provider, "test", output, n_variations=2, pick_strategy="score"
        )
        # The larger (higher-score) image should win.
        assert result.metadata["selected_variation_index"] == 1

    def test_random_strategy_still_returns_a_result(self, tmp_path):
        provider = mock.MagicMock()

        def _fake(prompt, output_path, *, aspect_ratio="9:16", metadata=None):
            _write_solid_png(output_path, width=64, height=114)
            return GeneratedImage(
                path=output_path, provider="mock", prompt=prompt,
                scene_id="", width=64, height=114, metadata={},
            )

        provider.generate_image.side_effect = _fake
        output = tmp_path / "out.png"
        result = generate_and_select_best_image(
            provider, "test", output, n_variations=3, pick_strategy="random"
        )
        assert result.path == output
        assert result.metadata["variations_generated"] == 3


# ---------------------------------------------------------------------------
# 6. Pipeline still completes (n=1 fast path)
# ---------------------------------------------------------------------------


class TestPipelineCompletesWithSingleVariation:
    def test_n1_returns_original_generatedimage_unchanged(self, tmp_path):
        output = tmp_path / "scene_000.png"
        expected = GeneratedImage(
            path=output, provider="mock", prompt="p", scene_id="s",
            width=100, height=200, metadata={"x": 1},
        )
        provider = mock.MagicMock()
        provider.generate_image.return_value = expected

        result = generate_and_select_best_image(
            provider, "p", output, n_variations=1
        )
        assert result is expected

    def test_all_variations_fail_raises_runtime_error(self, tmp_path):
        provider = mock.MagicMock()
        provider.generate_image.side_effect = RuntimeError("API error")

        with pytest.raises(RuntimeError, match="All .* image generation attempts failed"):
            generate_and_select_best_image(
                provider, "test", tmp_path / "out.png", n_variations=2
            )

    def test_partial_failure_still_returns_successful_candidate(self, tmp_path):
        """When some variations fail but at least one succeeds, the winner
        must be returned without error."""
        call_idx = {"n": 0}

        def _selective_fail(prompt, output_path, *, aspect_ratio="9:16", metadata=None):
            i = call_idx["n"]
            call_idx["n"] += 1
            if i == 0:
                raise RuntimeError("variation 0 failed")
            _write_solid_png(output_path, width=64, height=114)
            return GeneratedImage(
                path=output_path, provider="mock", prompt=prompt,
                scene_id="", width=64, height=114, metadata={},
            )

        provider = mock.MagicMock()
        provider.generate_image.side_effect = _selective_fail
        output = tmp_path / "out.png"
        result = generate_and_select_best_image(
            provider, "test", output, n_variations=2
        )
        assert result.path == output


# ---------------------------------------------------------------------------
# 7. Performance acceptable (multi-gen with mock provider is fast)
# ---------------------------------------------------------------------------


class TestPerformance:
    def test_multi_gen_finishes_within_one_second(self, tmp_path):
        """Generating 3 variations with a mock provider should complete well
        within 1 second — confirms no accidental sleeps or blocking calls."""

        def _fast_generate(prompt, output_path, *, aspect_ratio="9:16", metadata=None):
            _write_solid_png(output_path, width=64, height=114)
            return GeneratedImage(
                path=output_path, provider="mock", prompt=prompt,
                scene_id="", width=64, height=114, metadata={},
            )

        provider = mock.MagicMock()
        provider.generate_image.side_effect = _fast_generate

        start = time.monotonic()
        generate_and_select_best_image(
            provider, "test", tmp_path / "out.png", n_variations=3
        )
        elapsed = time.monotonic() - start
        assert elapsed < 1.0, f"Multi-image selection took {elapsed:.2f}s — too slow"

    def test_similarity_computation_is_fast_for_ten_scenes(self):
        """compute_scene_similarity over 10 scenes should complete in < 0.1 s."""
        scenes = [
            _make_scene(
                index=i,
                visual_description=f"scene {i} with unique words about topic event location",
                shot_type="wide" if i % 2 == 0 else "close",
            )
            for i in range(10)
        ]
        start = time.monotonic()
        for a in scenes:
            for b in scenes:
                compute_scene_similarity(a, b)
        elapsed = time.monotonic() - start
        assert elapsed < 0.1, f"Similarity computation took {elapsed:.3f}s"
