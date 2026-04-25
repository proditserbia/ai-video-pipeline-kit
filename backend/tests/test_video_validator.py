from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from worker.modules.video_builder.validator import ValidationResult, VideoValidator


def _has_ffmpeg() -> bool:
    try:
        result = subprocess.run(["ffprobe", "-version"], capture_output=True)
        return result.returncode == 0
    except FileNotFoundError:
        return False


def _create_test_video(path: Path) -> bool:
    """Create a tiny 1080x1920 video using ffmpeg for testing."""
    try:
        result = subprocess.run(
            [
                "ffmpeg", "-y",
                "-f", "lavfi",
                "-i", "color=c=blue:size=1080x1920:rate=1:duration=2",
                "-f", "lavfi",
                "-i", "sine=frequency=440:duration=2",
                "-c:v", "libx264",
                "-c:a", "aac",
                "-pix_fmt", "yuv420p",
                str(path),
            ],
            capture_output=True,
            timeout=30,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


class TestVideoValidator:
    def test_missing_file(self):
        v = VideoValidator()
        result = v.validate("/nonexistent/file.mp4")
        assert result.passed is False
        assert any("not found" in e for e in result.errors)

    def test_empty_file(self, tmp_path):
        p = tmp_path / "empty.mp4"
        p.write_bytes(b"")
        v = VideoValidator()
        result = v.validate(str(p))
        assert result.passed is False
        assert any("empty" in e.lower() for e in result.errors)

    def test_validation_result_to_dict(self):
        r = ValidationResult(
            passed=True,
            width=1080,
            height=1920,
            duration=30.0,
            has_audio=True,
            video_codec="h264",
            audio_codec="aac",
            file_size_bytes=1024,
        )
        d = r.to_dict()
        assert d["passed"] is True
        assert d["width"] == 1080
        assert d["height"] == 1920
        assert d["has_audio"] is True

    @pytest.mark.skipif(not _has_ffmpeg(), reason="ffmpeg/ffprobe not available")
    def test_valid_video(self, tmp_path):
        video = tmp_path / "test.mp4"
        created = _create_test_video(video)
        if not created:
            pytest.skip("Could not create test video with ffmpeg")

        v = VideoValidator()
        result = v.validate(str(video))
        assert result.duration > 0
        assert result.video_codec != ""
        assert result.file_size_bytes > 0
        # Resolution matches our test video
        assert result.width == 1080
        assert result.height == 1920

    def test_ffprobe_returns_none_on_invalid_file(self, tmp_path):
        bad_file = tmp_path / "not_a_video.mp4"
        bad_file.write_bytes(b"not a real video file")
        v = VideoValidator()
        # Should not raise, just return failed result
        result = v.validate(str(bad_file))
        assert isinstance(result, ValidationResult)
        assert result.passed is False
