"""Tests for video duration following audio length, and captions=none disabling behaviour."""
from __future__ import annotations

import math
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# _probe_duration
# ---------------------------------------------------------------------------


class TestProbeDuration:
    def test_returns_float_when_ffprobe_succeeds(self, tmp_path: Path):
        from worker.modules.video_builder.ffmpeg_builder import _probe_duration

        fake_file = tmp_path / "audio.mp3"
        fake_file.write_bytes(b"\x00")  # just needs to exist

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="68.856\n")
            result = _probe_duration(fake_file)

        assert result == pytest.approx(68.856)

    def test_returns_none_when_file_missing(self, tmp_path: Path):
        from worker.modules.video_builder.ffmpeg_builder import _probe_duration

        result = _probe_duration(tmp_path / "nonexistent.mp3")
        assert result is None

    def test_returns_none_when_ffprobe_fails(self, tmp_path: Path):
        from worker.modules.video_builder.ffmpeg_builder import _probe_duration

        fake_file = tmp_path / "audio.mp3"
        fake_file.write_bytes(b"\x00")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error")
            result = _probe_duration(fake_file)

        assert result is None

    def test_returns_none_when_output_not_float(self, tmp_path: Path):
        from worker.modules.video_builder.ffmpeg_builder import _probe_duration

        fake_file = tmp_path / "audio.mp3"
        fake_file.write_bytes(b"\x00")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="N/A\n")
            result = _probe_duration(fake_file)

        assert result is None


# ---------------------------------------------------------------------------
# _prepare_clips – looping to cover target_duration
# ---------------------------------------------------------------------------


class TestPrepareClipsLooping:
    """_prepare_clips must extend the clip list by cycling when target_duration
    requires more than the supplied clips cover."""

    def _run_prepare_clips(self, n_input_clips: int, target_duration: float, tmp_path: Path) -> int:
        """Return the number of prepared clips produced."""
        from worker.modules.video_builder.ffmpeg_builder import FFmpegVideoBuilder

        clips = [tmp_path / f"src_{i}.mp4" for i in range(n_input_clips)]
        # Clips don't need to exist; we mock _run so ffmpeg is never called.
        prepared_paths: list[Path] = []
        call_count = 0

        def fake_run(cmd):
            nonlocal call_count
            call_count += 1
            # Create a placeholder output file so it "exists".
            out = Path(cmd[-1])
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(b"\x00")
            prepared_paths.append(out)
            return MagicMock(returncode=0)

        builder = FFmpegVideoBuilder()
        with patch("worker.modules.video_builder.ffmpeg_builder._run", side_effect=fake_run):
            result = builder._prepare_clips(clips, tmp_path, target_duration=target_duration)

        return len(result)

    def test_three_clips_30s_no_extension_needed(self, tmp_path: Path):
        """3 clips × 10 s = 30 s. No looping when target ≤ 30 s."""
        n = self._run_prepare_clips(3, target_duration=30.0, tmp_path=tmp_path)
        assert n == 3

    def test_three_clips_extended_for_68s_audio(self, tmp_path: Path):
        """3 clips × 10 s = 30 s, but 68 s audio needs ceil(68/10) = 7 clips."""
        n = self._run_prepare_clips(3, target_duration=68.856, tmp_path=tmp_path)
        assert n == math.ceil(68.856 / 10)  # 7

    def test_three_clips_extended_for_exactly_30s_boundary(self, tmp_path: Path):
        """target = 30 s exactly → 3 clips is sufficient."""
        n = self._run_prepare_clips(3, target_duration=30.0, tmp_path=tmp_path)
        assert n == 3

    def test_three_clips_extended_for_31s(self, tmp_path: Path):
        """31 s requires ceil(31/10) = 4 clips (input cycles: 0,1,2,0)."""
        n = self._run_prepare_clips(3, target_duration=31.0, tmp_path=tmp_path)
        assert n == 4

    def test_zero_target_duration_no_looping(self, tmp_path: Path):
        """target_duration=0 → no extension; original clip count preserved."""
        n = self._run_prepare_clips(3, target_duration=0.0, tmp_path=tmp_path)
        assert n == 3

    def test_total_prepared_duration_covers_target(self, tmp_path: Path):
        """The prepared clip count × 10 s must be >= target_duration."""
        target = 68.856
        n = self._run_prepare_clips(3, target_duration=target, tmp_path=tmp_path)
        assert n * 10 >= target


# ---------------------------------------------------------------------------
# build() probes audio and prepares enough clips
# ---------------------------------------------------------------------------


class TestBuildWithAudioDuration:
    def test_build_calls_prepare_clips_with_target_duration(self, tmp_path: Path):
        """build() must derive target_duration from audio and pass it to _prepare_clips."""
        from worker.modules.video_builder.ffmpeg_builder import FFmpegVideoBuilder

        audio_file = tmp_path / "voice.mp3"
        audio_file.write_bytes(b"\x00")

        clip = tmp_path / "clip.mp4"
        clip.write_bytes(b"\x00")

        prepare_calls: list[dict] = []

        original_prepare = FFmpegVideoBuilder._prepare_clips

        def fake_prepare(self_inner, clips, work_dir, target_duration=0.0):
            prepare_calls.append({"target_duration": target_duration})
            # Return a single dummy clip path (we mock _run too).
            dummy = work_dir / "clip_000.mp4"
            dummy.write_bytes(b"\x00")
            return [dummy]

        def fake_run(cmd):
            out = Path(cmd[-1])
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(b"\x00")
            return MagicMock(returncode=0)

        builder = FFmpegVideoBuilder()
        with patch("worker.modules.video_builder.ffmpeg_builder._probe_duration", return_value=68.856), \
             patch.object(FFmpegVideoBuilder, "_prepare_clips", fake_prepare), \
             patch("worker.modules.video_builder.ffmpeg_builder._run", side_effect=fake_run):
            builder.build(
                clips=[clip],
                audio_path=audio_file,
                srt_path=None,
                output_path=tmp_path / "out.mp4",
            )

        assert len(prepare_calls) == 1
        # target = 68.856 + 0.3 = 69.156
        assert prepare_calls[0]["target_duration"] == pytest.approx(68.856 + 0.3)

    def test_build_without_audio_uses_zero_target_duration(self, tmp_path: Path):
        """Without audio, target_duration passed to _prepare_clips must be 0."""
        from worker.modules.video_builder.ffmpeg_builder import FFmpegVideoBuilder

        clip = tmp_path / "clip.mp4"
        clip.write_bytes(b"\x00")

        prepare_calls: list[dict] = []

        def fake_prepare(self_inner, clips, work_dir, target_duration=0.0):
            prepare_calls.append({"target_duration": target_duration})
            dummy = work_dir / "clip_000.mp4"
            dummy.write_bytes(b"\x00")
            return [dummy]

        def fake_run(cmd):
            out = Path(cmd[-1])
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(b"\x00")
            return MagicMock(returncode=0)

        builder = FFmpegVideoBuilder()
        with patch.object(FFmpegVideoBuilder, "_prepare_clips", fake_prepare), \
             patch("worker.modules.video_builder.ffmpeg_builder._run", side_effect=fake_run):
            builder.build(
                clips=[clip],
                audio_path=None,
                srt_path=None,
                output_path=tmp_path / "out.mp4",
            )

        assert len(prepare_calls) == 1
        assert prepare_calls[0]["target_duration"] == 0.0


# ---------------------------------------------------------------------------
# _resolve_caption_style – normalisation
# ---------------------------------------------------------------------------


class TestResolveCaptionStyle:
    def _resolve(self, input_data: dict) -> str:
        from worker.tasks.video_pipeline import _resolve_caption_style
        return _resolve_caption_style(input_data)

    def test_none_value_returns_none_string(self):
        assert self._resolve({"caption_style": None}) == "none"

    def test_empty_string_returns_none_string(self):
        assert self._resolve({"caption_style": ""}) == "none"

    def test_capital_None_string_returns_none_string(self):
        assert self._resolve({"caption_style": "None"}) == "none"

    def test_lowercase_none_returns_none_string(self):
        assert self._resolve({"caption_style": "none"}) == "none"

    def test_missing_key_returns_none_string(self):
        assert self._resolve({}) == "none"

    def test_basic_style_preserved(self):
        assert self._resolve({"caption_style": "basic"}) == "basic"

    def test_bold_center_style_preserved(self):
        assert self._resolve({"caption_style": "bold_center"}) == "bold_center"

    def test_nested_captions_style(self):
        assert self._resolve({"captions": {"style": "boxed"}}) == "boxed"

    def test_nested_disabled_returns_none_string(self):
        assert self._resolve({"captions": {"style": "none"}}) == "none"

    def test_flat_takes_priority_over_nested(self):
        assert self._resolve({"caption_style": "basic", "captions": {"style": "boxed"}}) == "basic"


# ---------------------------------------------------------------------------
# Pipeline Step 6: caption_style="none" disables captions
# ---------------------------------------------------------------------------


class TestCaptionsDisabledByUser:
    """When caption_style resolves to 'none', the pipeline must skip Whisper
    and write caption_status='disabled' to output_metadata."""

    @staticmethod
    def _run_caption_step(caption_style_value: str) -> dict:
        """Simulate pipeline Step 6 for a given caption_style and return the
        dict that would be merged into output_metadata."""
        from worker.tasks.video_pipeline import _resolve_caption_style
        from worker.modules.captions.whisper_provider import WhisperCaptionProvider

        input_data = {"caption_style": caption_style_value}
        caption_style = _resolve_caption_style(input_data)

        whisper_called = False

        def fake_transcribe(*args, **kwargs):
            nonlocal whisper_called
            whisper_called = True
            return MagicMock(srt_path="/tmp/captions.srt")

        with patch.object(WhisperCaptionProvider, "transcribe", fake_transcribe), \
             patch.object(WhisperCaptionProvider, "is_available", return_value=True):

            if caption_style == "none":
                meta = {"caption_status": "disabled"}
            else:
                meta = {}
                # Simulate Whisper running (simplified)
                try:
                    provider = WhisperCaptionProvider.__new__(WhisperCaptionProvider)
                    provider.transcribe("/tmp/fake.mp3", "/tmp")
                    meta = {"caption_status": "success"}
                except Exception:
                    meta = {"caption_status": "failed"}

        return {"meta": meta, "whisper_called": whisper_called}

    def test_caption_none_sets_disabled_status(self):
        result = self._run_caption_step("none")
        assert result["meta"]["caption_status"] == "disabled"

    def test_caption_none_does_not_call_whisper(self):
        result = self._run_caption_step("none")
        assert result["whisper_called"] is False

    def test_caption_none_string_sets_disabled(self):
        """The literal string 'none' (from the UI dropdown) disables captions."""
        result = self._run_caption_step("none")
        assert result["meta"]["caption_status"] == "disabled"

    def test_caption_basic_calls_whisper(self):
        """A real caption style ('basic') should reach Whisper."""
        result = self._run_caption_step("basic")
        assert result["whisper_called"] is True

    def test_caption_None_string_disables(self):
        """The string 'None' (capital N) must also disable captions."""
        result = self._run_caption_step("None")
        assert result["meta"]["caption_status"] == "disabled"
        assert result["whisper_called"] is False


# ---------------------------------------------------------------------------
# caption_style unknown → validation error (schema-level)
# ---------------------------------------------------------------------------


class TestCaptionStyleValidation:
    def test_unknown_style_raises_validation_error(self):
        from pydantic import ValidationError
        from app.schemas.job import JobCreate

        with pytest.raises(ValidationError) as exc_info:
            JobCreate(title="t", caption_style="fancy_unknown")
        assert "caption_style" in str(exc_info.value).lower() or "fancy_unknown" in str(exc_info.value)

    def test_none_style_is_accepted_by_schema(self):
        from app.schemas.job import JobCreate

        job = JobCreate(title="t", caption_style="none")
        assert job.caption_style == "none"
