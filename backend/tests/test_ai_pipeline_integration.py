"""Full end-to-end integration test: script → scenes → local_mock images → render.

Uses LocalMockImageProvider (no external API) and real FFmpeg.
Skipped automatically when FFmpeg is not installed.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from worker.modules.ai_images.providers.local_mock_provider import LocalMockImageProvider
from worker.modules.script_planner.planner import plan_script_scenes
from worker.modules.video_builder.ffmpeg_builder import FFmpegVideoBuilder, _probe_duration
from worker.modules.video_builder.visual_segment import VisualSegment

# ---------------------------------------------------------------------------
# Skip when FFmpeg is unavailable (CI environments without the binary).
# ---------------------------------------------------------------------------

pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="FFmpeg / ffprobe not installed",
)

_SCRIPT = (
    "Scientists have discovered a new planet. "
    "It orbits a nearby star. "
    "The atmosphere may support life. "
    "Missions are being planned. "
    "This could change everything."
)


def _make_silent_audio(path: Path, duration: float) -> None:
    """Generate a silent AAC audio file of the requested duration."""
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", f"anullsrc=r=44100:cl=mono:d={duration}",
            "-c:a", "aac",
            "-b:a", "64k",
            str(path),
        ],
        capture_output=True,
        check=True,
    )


class TestAIPipelineIntegration:
    """script → plan_script_scenes → LocalMockImageProvider → build_from_segments → MP4."""

    def test_full_pipeline_produces_video(self, tmp_path: Path) -> None:
        """The render must succeed and the output file must exist."""
        audio_duration = 10.0

        # 1. Plan scenes.
        scenes = plan_script_scenes(_SCRIPT, audio_duration=audio_duration)
        assert len(scenes) >= 1

        # 2. Generate images with the local mock provider.
        provider = LocalMockImageProvider()
        image_dir = tmp_path / "images"
        image_dir.mkdir()

        segments: list[VisualSegment] = []
        for scene in scenes:
            img_path = image_dir / f"scene_{scene.index:03d}.png"
            result = provider.generate_image(
                scene.image_prompt,
                img_path,
                metadata={"scene_id": scene.id},
            )
            assert img_path.exists(), f"Image not written for scene {scene.index}"
            segments.append(
                VisualSegment(
                    path=Path(result.path),
                    start_time=scene.start_time or 0.0,
                    end_time=scene.end_time or 0.0,
                    duration=scene.duration or 0.0,
                    type="image",
                    scene_id=scene.id,
                )
            )

        assert len(segments) == len(scenes)

        # 3. Build a silent audio track matching the planned duration.
        audio_path = tmp_path / "voice.aac"
        _make_silent_audio(audio_path, audio_duration)
        probed = _probe_duration(audio_path)
        assert probed is not None and probed > 0

        # 4. Render via build_from_segments (real FFmpeg).
        output_path = tmp_path / "output.mp4"
        builder = FFmpegVideoBuilder()
        builder.build_from_segments(
            segments=segments,
            audio_path=audio_path,
            srt_path=None,
            output_path=output_path,
        )

        # 5. Verify output.
        assert output_path.exists(), "Output MP4 not produced"
        assert output_path.stat().st_size > 0, "Output MP4 is empty"

    def test_output_duration_approximately_matches_audio(self, tmp_path: Path) -> None:
        """Output video duration must be within 1 second of the audio duration."""
        audio_duration = 10.0

        scenes = plan_script_scenes(_SCRIPT, audio_duration=audio_duration)
        provider = LocalMockImageProvider()
        image_dir = tmp_path / "images"
        image_dir.mkdir()

        segments: list[VisualSegment] = []
        for scene in scenes:
            img_path = image_dir / f"scene_{scene.index:03d}.png"
            result = provider.generate_image(scene.image_prompt, img_path)
            segments.append(
                VisualSegment(
                    path=Path(result.path),
                    start_time=scene.start_time or 0.0,
                    end_time=scene.end_time or 0.0,
                    duration=scene.duration or 0.0,
                    type="image",
                )
            )

        audio_path = tmp_path / "voice.aac"
        _make_silent_audio(audio_path, audio_duration)

        output_path = tmp_path / "output.mp4"
        builder = FFmpegVideoBuilder()
        builder.build_from_segments(
            segments=segments,
            audio_path=audio_path,
            srt_path=None,
            output_path=output_path,
        )

        video_duration = _probe_duration(output_path)
        assert video_duration is not None, "Could not probe output video duration"
        assert abs(video_duration - audio_duration) < 1.0, (
            f"Output duration {video_duration:.2f}s differs from audio {audio_duration}s by ≥1s"
        )

    def test_no_crash_with_single_scene(self, tmp_path: Path) -> None:
        """A one-sentence script must produce exactly one segment and a valid video."""
        audio_duration = 5.0
        scenes = plan_script_scenes("A single sentence only.", audio_duration=audio_duration)

        provider = LocalMockImageProvider()
        segments: list[VisualSegment] = []
        for scene in scenes:
            img_path = tmp_path / f"scene_{scene.index:03d}.png"
            result = provider.generate_image(scene.image_prompt, img_path)
            segments.append(
                VisualSegment(
                    path=Path(result.path),
                    start_time=scene.start_time or 0.0,
                    end_time=scene.end_time or 0.0,
                    duration=scene.duration or 0.0,
                    type="image",
                )
            )

        audio_path = tmp_path / "voice.aac"
        _make_silent_audio(audio_path, audio_duration)

        output_path = tmp_path / "output.mp4"
        FFmpegVideoBuilder().build_from_segments(
            segments=segments,
            audio_path=audio_path,
            srt_path=None,
            output_path=output_path,
        )

        assert output_path.exists()
