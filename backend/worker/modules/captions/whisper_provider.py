from __future__ import annotations

import json
from pathlib import Path

from worker.modules.base import CaptionResult, ModuleNotAvailableError
from worker.modules.captions.base import AbstractCaptionProvider


def _format_timestamp(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds - int(seconds)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _check_faster_whisper() -> str | None:
    """Return an error message string if faster-whisper cannot be imported, else None."""
    try:
        import faster_whisper  # noqa: F401
        return None
    except Exception as exc:
        return (
            "faster-whisper is not installed or failed to load "
            f"({exc}). "
            "Install it with: pip install faster-whisper\n"
            "Note: faster-whisper requires ctranslate2 which needs a compatible CPU/GPU."
        )


class WhisperCaptionProvider(AbstractCaptionProvider):
    """Transcription using faster-whisper. Produces SRT, VTT, and JSON outputs."""

    @classmethod
    def is_available(cls) -> bool:
        """Return True if the faster-whisper package can be imported successfully."""
        return _check_faster_whisper() is None

    def __init__(self, model_size: str = "base", device: str = "cpu") -> None:
        error = _check_faster_whisper()
        if error:
            raise ModuleNotAvailableError(error)
        from faster_whisper import WhisperModel
        # Load once; model loading is expensive
        self._model = WhisperModel(model_size, device=device, compute_type="int8")

    def transcribe(self, audio_path: str, output_dir: str) -> CaptionResult:
        segments_iter, info = self._model.transcribe(audio_path, beam_size=5)
        segments = list(segments_iter)

        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        srt_path = str(out / "captions.srt")
        vtt_path = str(out / "captions.vtt")
        json_path = str(out / "captions.json")
        segment_dicts: list[dict] = []

        srt_lines: list[str] = []
        vtt_lines: list[str] = ["WEBVTT\n"]

        for i, seg in enumerate(segments, start=1):
            d = {
                "id": i,
                "start": seg.start,
                "end": seg.end,
                "text": seg.text.strip(),
            }
            segment_dicts.append(d)

            start_ts = _format_timestamp(seg.start)
            end_ts = _format_timestamp(seg.end)
            srt_lines += [str(i), f"{start_ts} --> {end_ts}", seg.text.strip(), ""]

            vtt_start = start_ts.replace(",", ".")
            vtt_end = end_ts.replace(",", ".")
            vtt_lines += [f"{vtt_start} --> {vtt_end}", seg.text.strip(), ""]

        Path(srt_path).write_text("\n".join(srt_lines))
        Path(vtt_path).write_text("\n".join(vtt_lines))
        Path(json_path).write_text(json.dumps(segment_dicts, ensure_ascii=False, indent=2))

        return CaptionResult(
            srt_path=srt_path,
            vtt_path=vtt_path,
            json_path=json_path,
            segments=segment_dicts,
        )


    def transcribe(self, audio_path: str, output_dir: str) -> CaptionResult:
        segments_iter, info = self._model.transcribe(audio_path, beam_size=5)
        segments = list(segments_iter)

        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        srt_path = str(out / "captions.srt")
        vtt_path = str(out / "captions.vtt")
        json_path = str(out / "captions.json")
        segment_dicts: list[dict] = []

        srt_lines: list[str] = []
        vtt_lines: list[str] = ["WEBVTT\n"]

        for i, seg in enumerate(segments, start=1):
            d = {
                "id": i,
                "start": seg.start,
                "end": seg.end,
                "text": seg.text.strip(),
            }
            segment_dicts.append(d)

            start_ts = _format_timestamp(seg.start)
            end_ts = _format_timestamp(seg.end)
            srt_lines += [str(i), f"{start_ts} --> {end_ts}", seg.text.strip(), ""]

            vtt_start = start_ts.replace(",", ".")
            vtt_end = end_ts.replace(",", ".")
            vtt_lines += [f"{vtt_start} --> {vtt_end}", seg.text.strip(), ""]

        Path(srt_path).write_text("\n".join(srt_lines))
        Path(vtt_path).write_text("\n".join(vtt_lines))
        Path(json_path).write_text(json.dumps(segment_dicts, ensure_ascii=False, indent=2))

        return CaptionResult(
            srt_path=srt_path,
            vtt_path=vtt_path,
            json_path=json_path,
            segments=segment_dicts,
        )
