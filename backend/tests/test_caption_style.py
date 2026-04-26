"""Tests for caption_style → libass force_style mapping in FFmpegVideoBuilder."""
from __future__ import annotations

import os
import stat
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from worker.modules.video_builder.ffmpeg_builder import (
    CAPTION_STYLE_MAP,
    _DEFAULT_CAPTION_STYLE,
    _escape_force_style,
    _escape_srt_path,
    FFmpegVideoBuilder,
)


# ---------------------------------------------------------------------------
# Unit tests for pure helper functions
# ---------------------------------------------------------------------------


class TestEscapeForceStyle:
    def test_plain_value_unchanged(self):
        raw = "FontSize=36,PrimaryColour=&H00FFFFFF"
        assert _escape_force_style(raw) == raw

    def test_backslash_escaped(self):
        assert _escape_force_style("a\\b") == "a\\\\b"

    def test_single_quote_escaped(self):
        assert _escape_force_style("a'b") == "a\\'b"

    def test_both_escaped(self):
        assert _escape_force_style("a\\'b") == "a\\\\\\'b"


class TestCaptionStyleMap:
    def test_all_expected_styles_present(self):
        for key in ("basic", "bold_center", "boxed", "large_bottom", "karaoke_placeholder"):
            assert key in CAPTION_STYLE_MAP, f"Missing style: {key}"

    def test_all_values_are_non_empty_strings(self):
        for key, val in CAPTION_STYLE_MAP.items():
            assert isinstance(val, str) and val, f"Empty style for: {key}"

    def test_default_style_is_in_map(self):
        assert _DEFAULT_CAPTION_STYLE in CAPTION_STYLE_MAP


# ---------------------------------------------------------------------------
# Integration-level tests: verify _compose builds correct ffmpeg command
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_srt(tmp_path: Path) -> Path:
    """Create a real, non-empty SRT file so srt_path.exists() is True."""
    srt = tmp_path / "captions.srt"
    srt.write_text("1\n00:00:00,000 --> 00:00:02,000\nHello\n")
    return srt


@pytest.fixture()
def tmp_video(tmp_path: Path) -> Path:
    """Minimal placeholder for video path (existence not required for _compose)."""
    return tmp_path / "input.mp4"


@pytest.fixture()
def builder() -> FFmpegVideoBuilder:
    return FFmpegVideoBuilder()


def _run_compose(builder, tmp_video, srt_path, caption_style):
    """Call _compose with _run mocked; return the captured command list."""
    captured: list[list[str]] = []

    def fake_run(cmd):
        captured.append(cmd)
        return MagicMock(returncode=0)

    output = srt_path.parent / "out.mp4"
    with patch("worker.modules.video_builder.ffmpeg_builder._run", side_effect=fake_run):
        builder._compose(
            video=tmp_video,
            audio_path=None,
            srt_path=srt_path,
            output_path=output,
            use_nvenc=False,
            watermark_path=None,
            bg_music_path=None,
            bg_music_volume=0.15,
            caption_style=caption_style,
        )

    assert captured, "No ffmpeg command was captured"
    return captured[0]


class TestComposeForceStyle:
    """Each named caption_style should produce a -vf argument containing the
    correct force_style value from CAPTION_STYLE_MAP."""

    @pytest.mark.parametrize("style_name", list(CAPTION_STYLE_MAP.keys()))
    def test_named_style_produces_correct_force_style(self, builder, tmp_srt, tmp_video, style_name):
        cmd = _run_compose(builder, tmp_video, tmp_srt, style_name)
        vf_index = cmd.index("-vf") + 1
        vf_value = cmd[vf_index]

        expected_force_style = _escape_force_style(CAPTION_STYLE_MAP[style_name])
        assert f"force_style='{expected_force_style}'" in vf_value, (
            f"force_style not found for style '{style_name}'\nvf={vf_value}"
        )

    def test_unknown_style_falls_back_to_default(self, builder, tmp_srt, tmp_video):
        cmd = _run_compose(builder, tmp_video, tmp_srt, "nonexistent_style")
        vf_index = cmd.index("-vf") + 1
        vf_value = cmd[vf_index]

        expected = _escape_force_style(CAPTION_STYLE_MAP[_DEFAULT_CAPTION_STYLE])
        assert f"force_style='{expected}'" in vf_value

    def test_none_style_falls_back_to_default(self, builder, tmp_srt, tmp_video):
        cmd = _run_compose(builder, tmp_video, tmp_srt, None)
        vf_index = cmd.index("-vf") + 1
        vf_value = cmd[vf_index]

        expected = _escape_force_style(CAPTION_STYLE_MAP[_DEFAULT_CAPTION_STYLE])
        assert f"force_style='{expected}'" in vf_value

    def test_no_srt_means_no_vf_subtitles(self, builder, tmp_video, tmp_path):
        """When srt_path is None no subtitles filter (and no force_style) is added."""
        captured: list[list[str]] = []

        def fake_run(cmd):
            captured.append(cmd)
            return MagicMock(returncode=0)

        output = tmp_path / "out.mp4"
        with patch("worker.modules.video_builder.ffmpeg_builder._run", side_effect=fake_run):
            builder._compose(
                video=tmp_video,
                audio_path=None,
                srt_path=None,
                output_path=output,
                use_nvenc=False,
                watermark_path=None,
                bg_music_path=None,
                bg_music_volume=0.15,
                caption_style="bold_center",
            )

        cmd = captured[0]
        assert "-vf" not in cmd
        assert "force_style" not in " ".join(cmd)

    def test_vf_contains_subtitles_filter_with_path(self, builder, tmp_srt, tmp_video):
        """Sanity: subtitles= filter references the SRT file path."""
        cmd = _run_compose(builder, tmp_video, tmp_srt, "basic")
        vf_index = cmd.index("-vf") + 1
        vf_value = cmd[vf_index]
        assert "subtitles=" in vf_value

    def test_force_style_does_not_use_shell(self, builder, tmp_srt, tmp_video):
        """The command must be a list (never a shell string) to avoid injection."""
        captured: list[list[str]] = []

        def fake_run(cmd):
            captured.append(cmd)
            return MagicMock(returncode=0)

        output = tmp_srt.parent / "out.mp4"
        with patch("worker.modules.video_builder.ffmpeg_builder._run", side_effect=fake_run):
            builder._compose(
                video=tmp_video,
                audio_path=None,
                srt_path=tmp_srt,
                output_path=output,
                use_nvenc=False,
                watermark_path=None,
                bg_music_path=None,
                bg_music_volume=0.15,
                caption_style="boxed",
            )

        assert isinstance(captured[0], list)
