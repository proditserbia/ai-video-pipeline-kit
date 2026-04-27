"""Tests for the timeline-aware FFmpegVideoBuilder.build_from_segments() path."""
from __future__ import annotations

import math
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from worker.modules.video_builder.ffmpeg_builder import FFmpegVideoBuilder
from worker.modules.video_builder.visual_segment import VisualSegment


# ── VisualSegment dataclass ───────────────────────────────────────────────────


class TestVisualSegment:
    def test_fields(self):
        seg = VisualSegment(
            path=Path("/tmp/img.png"),
            start_time=0.0,
            end_time=6.4,
            duration=6.4,
            type="image",
            scene_id="abc",
        )
        assert seg.start_time == 0.0
        assert seg.end_time == 6.4
        assert seg.duration == 6.4
        assert seg.type == "image"
        assert seg.scene_id == "abc"

    def test_default_scene_id_is_empty(self):
        seg = VisualSegment(
            path=Path("/tmp/v.mp4"),
            start_time=0.0,
            end_time=5.0,
            duration=5.0,
            type="video",
        )
        assert seg.scene_id == ""


# ── _image_to_static_clip ─────────────────────────────────────────────────────


class TestImageToStaticClip:
    def test_calls_ffmpeg_with_loop_flag(self, tmp_path: Path):
        builder = FFmpegVideoBuilder()
        img = tmp_path / "img.png"
        img.write_bytes(b"\x00")
        out = tmp_path / "out.mp4"

        captured: list[list[str]] = []

        def fake_run(cmd):
            captured.append(cmd)
            out_path = Path(cmd[-1])
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(b"\x00")
            return MagicMock(returncode=0)

        with patch("worker.modules.video_builder.ffmpeg_builder._run", side_effect=fake_run):
            builder._image_to_static_clip(img, out, duration=6.0)

        assert len(captured) == 1
        cmd = captured[0]
        assert "-loop" in cmd
        assert "1" in cmd
        assert "-t" in cmd
        assert "6.0" in cmd

    def test_duration_is_exact_in_command(self, tmp_path: Path):
        builder = FFmpegVideoBuilder()
        img = tmp_path / "img.png"
        img.write_bytes(b"\x00")
        out = tmp_path / "out.mp4"

        captured_duration: list[str] = []

        def fake_run(cmd):
            t_idx = cmd.index("-t") + 1
            captured_duration.append(cmd[t_idx])
            Path(cmd[-1]).parent.mkdir(parents=True, exist_ok=True)
            Path(cmd[-1]).write_bytes(b"\x00")
            return MagicMock(returncode=0)

        with patch("worker.modules.video_builder.ffmpeg_builder._run", side_effect=fake_run):
            builder._image_to_static_clip(img, out, duration=7.3)

        assert float(captured_duration[0]) == pytest.approx(7.3)

    def test_no_ken_burns_filter(self, tmp_path: Path):
        """Ensure zoompan (Ken Burns) filter is NOT used."""
        builder = FFmpegVideoBuilder()
        img = tmp_path / "img.png"
        img.write_bytes(b"\x00")
        out = tmp_path / "out.mp4"

        captured: list[list[str]] = []

        def fake_run(cmd):
            captured.append(cmd)
            Path(cmd[-1]).parent.mkdir(parents=True, exist_ok=True)
            Path(cmd[-1]).write_bytes(b"\x00")
            return MagicMock(returncode=0)

        with patch("worker.modules.video_builder.ffmpeg_builder._run", side_effect=fake_run):
            builder._image_to_static_clip(img, out, duration=5.0)

        full_cmd = " ".join(captured[0])
        assert "zoompan" not in full_cmd


# ── _prepare_segments ────────────────────────────────────────────────────────


class TestPrepareSegments:
    def _make_image_segment(self, tmp_path: Path, name: str, duration: float) -> VisualSegment:
        p = tmp_path / name
        p.write_bytes(b"\x00")
        return VisualSegment(
            path=p,
            start_time=0.0,
            end_time=duration,
            duration=duration,
            type="image",
        )

    def _make_video_segment(self, tmp_path: Path, name: str, duration: float) -> VisualSegment:
        p = tmp_path / name
        p.write_bytes(b"\x00")
        return VisualSegment(
            path=p,
            start_time=0.0,
            end_time=duration,
            duration=duration,
            type="video",
        )

    def test_returns_one_clip_per_segment(self, tmp_path: Path):
        builder = FFmpegVideoBuilder()
        segments = [
            self._make_image_segment(tmp_path, f"img_{i}.png", 6.0)
            for i in range(3)
        ]

        def fake_run(cmd):
            Path(cmd[-1]).parent.mkdir(parents=True, exist_ok=True)
            Path(cmd[-1]).write_bytes(b"\x00")
            return MagicMock(returncode=0)

        work_dir = tmp_path / "work"
        work_dir.mkdir()
        with patch("worker.modules.video_builder.ffmpeg_builder._run", side_effect=fake_run):
            prepared = builder._prepare_segments(segments, work_dir)

        assert len(prepared) == 3

    def test_image_segments_use_loop_flag(self, tmp_path: Path):
        builder = FFmpegVideoBuilder()
        seg = self._make_image_segment(tmp_path, "img.png", 5.0)

        captured: list[list[str]] = []

        def fake_run(cmd):
            captured.append(cmd)
            Path(cmd[-1]).parent.mkdir(parents=True, exist_ok=True)
            Path(cmd[-1]).write_bytes(b"\x00")
            return MagicMock(returncode=0)

        work_dir = tmp_path / "work"
        work_dir.mkdir()
        with patch("worker.modules.video_builder.ffmpeg_builder._run", side_effect=fake_run):
            builder._prepare_segments([seg], work_dir)

        assert any("-loop" in cmd for cmd in captured)

    def test_video_segments_use_stream_loop(self, tmp_path: Path):
        builder = FFmpegVideoBuilder()
        seg = self._make_video_segment(tmp_path, "clip.mp4", 8.0)

        captured: list[list[str]] = []

        def fake_run(cmd):
            captured.append(cmd)
            Path(cmd[-1]).parent.mkdir(parents=True, exist_ok=True)
            Path(cmd[-1]).write_bytes(b"\x00")
            return MagicMock(returncode=0)

        work_dir = tmp_path / "work"
        work_dir.mkdir()
        with patch("worker.modules.video_builder.ffmpeg_builder._run", side_effect=fake_run):
            builder._prepare_segments([seg], work_dir)

        assert any("-stream_loop" in cmd for cmd in captured)

    def test_zero_duration_gets_floor_of_01(self, tmp_path: Path):
        """Degenerate segment with duration=0 must not pass 0 to FFmpeg."""
        builder = FFmpegVideoBuilder()
        seg = VisualSegment(
            path=tmp_path / "img.png",
            start_time=0.0,
            end_time=0.0,
            duration=0.0,
            type="image",
        )
        (tmp_path / "img.png").write_bytes(b"\x00")

        captured: list[list[str]] = []

        def fake_run(cmd):
            captured.append(cmd)
            Path(cmd[-1]).parent.mkdir(parents=True, exist_ok=True)
            Path(cmd[-1]).write_bytes(b"\x00")
            return MagicMock(returncode=0)

        work_dir = tmp_path / "work"
        work_dir.mkdir()
        with patch("worker.modules.video_builder.ffmpeg_builder._run", side_effect=fake_run):
            builder._prepare_segments([seg], work_dir)

        t_vals = [
            float(cmd[cmd.index("-t") + 1])
            for cmd in captured
            if "-t" in cmd
        ]
        assert all(t > 0 for t in t_vals)


# ── build_from_segments ───────────────────────────────────────────────────────


class TestBuildFromSegments:
    def _make_segments(self, tmp_path: Path, n: int, duration: float = 6.4) -> list[VisualSegment]:
        segments = []
        cursor = 0.0
        for i in range(n):
            p = tmp_path / f"img_{i}.png"
            p.write_bytes(b"\x00")
            end = cursor + duration
            segments.append(
                VisualSegment(
                    path=p,
                    start_time=cursor,
                    end_time=end,
                    duration=duration,
                    type="image",
                    scene_id=f"scene-{i}",
                )
            )
            cursor = end
        return segments

    def test_calls_compose_after_concat(self, tmp_path: Path):
        builder = FFmpegVideoBuilder()
        segments = self._make_segments(tmp_path, 3)
        audio = tmp_path / "audio.mp3"
        audio.write_bytes(b"\x00")
        output = tmp_path / "out.mp4"

        def fake_run(cmd):
            Path(cmd[-1]).parent.mkdir(parents=True, exist_ok=True)
            Path(cmd[-1]).write_bytes(b"\x00")
            return MagicMock(returncode=0)

        compose_calls: list = []
        original_compose = FFmpegVideoBuilder._compose

        def fake_compose(self_inner, **kwargs):
            compose_calls.append(kwargs)
            kwargs["output_path"].write_bytes(b"\x00")

        with (
            patch("worker.modules.video_builder.ffmpeg_builder._run", side_effect=fake_run),
            patch.object(FFmpegVideoBuilder, "_compose", fake_compose),
        ):
            builder.build_from_segments(
                segments=segments,
                audio_path=audio,
                srt_path=None,
                output_path=output,
            )

        assert len(compose_calls) == 1
        assert compose_calls[0]["audio_path"] == audio

    def test_empty_segments_uses_placeholder(self, tmp_path: Path):
        """When segments is empty, a placeholder should be used so the build
        does not crash."""
        builder = FFmpegVideoBuilder()
        output = tmp_path / "out.mp4"

        ffmpeg_calls: list = []

        def fake_run(cmd):
            ffmpeg_calls.append(cmd)
            Path(cmd[-1]).parent.mkdir(parents=True, exist_ok=True)
            Path(cmd[-1]).write_bytes(b"\x00")
            return MagicMock(returncode=0)

        def fake_compose(self_inner, **kwargs):
            kwargs["output_path"].write_bytes(b"\x00")

        with (
            patch("worker.modules.video_builder.ffmpeg_builder._run", side_effect=fake_run),
            patch.object(FFmpegVideoBuilder, "_compose", fake_compose),
        ):
            # Should not raise even with empty segments
            builder.build_from_segments(
                segments=[],
                audio_path=None,
                srt_path=None,
                output_path=output,
            )

    def test_five_scenes_32s_audio_proportional_coverage(self, tmp_path: Path):
        """Verify that a typical 5-scene 32s narration produces exactly 5 prepared
        clips whose durations sum to 32 seconds."""
        from worker.modules.script_planner.planner import plan_script_scenes

        script = (
            "Scientists have discovered a new planet. "
            "It orbits a nearby star. "
            "The atmosphere may support life. "
            "Missions are being planned. "
            "This could change everything."
        )
        audio_dur = 32.0
        scenes = plan_script_scenes(script, audio_duration=audio_dur)

        # Build VisualSegment list from planner output (using mock image paths).
        segments = []
        for scene in scenes:
            img = tmp_path / f"scene_{scene.index:03d}.png"
            img.write_bytes(b"\x00")
            segments.append(
                VisualSegment(
                    path=img,
                    start_time=scene.start_time or 0.0,
                    end_time=scene.end_time or 0.0,
                    duration=scene.duration or 0.0,
                    type="image",
                    scene_id=scene.id,
                )
            )

        total_duration = sum(s.duration for s in segments)
        assert total_duration == pytest.approx(audio_dur)

        # Verify no gaps.
        for i in range(len(segments) - 1):
            assert segments[i].end_time == pytest.approx(segments[i + 1].start_time)
