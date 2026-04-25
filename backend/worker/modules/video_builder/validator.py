from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

MIN_DURATION = 1.0
MAX_DURATION = 3600.0
EXPECTED_WIDTH = 1080
EXPECTED_HEIGHT = 1920


@dataclass
class ValidationResult:
    passed: bool
    width: int = 0
    height: int = 0
    duration: float = 0.0
    has_audio: bool = False
    video_codec: str = ""
    audio_codec: str = ""
    file_size_bytes: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "width": self.width,
            "height": self.height,
            "duration": self.duration,
            "has_audio": self.has_audio,
            "video_codec": self.video_codec,
            "audio_codec": self.audio_codec,
            "file_size_bytes": self.file_size_bytes,
            "errors": self.errors,
            "warnings": self.warnings,
        }


class VideoValidator:
    """Validates output video using ffprobe. Never uses shell=True."""

    def validate(self, video_path: str) -> ValidationResult:
        path = Path(video_path)
        result = ValidationResult(passed=False)

        if not path.exists():
            result.errors.append(f"File not found: {video_path}")
            return result

        result.file_size_bytes = path.stat().st_size
        if result.file_size_bytes == 0:
            result.errors.append("File is empty")
            return result

        probe = self._probe(video_path)
        if probe is None:
            result.errors.append("ffprobe failed to parse the file")
            return result

        streams = probe.get("streams", [])
        fmt = probe.get("format", {})

        result.duration = float(fmt.get("duration", 0.0))

        for stream in streams:
            codec_type = stream.get("codec_type")
            if codec_type == "video":
                result.width = int(stream.get("width", 0))
                result.height = int(stream.get("height", 0))
                result.video_codec = stream.get("codec_name", "")
            elif codec_type == "audio":
                result.has_audio = True
                result.audio_codec = stream.get("codec_name", "")

        # Checks
        if result.width != EXPECTED_WIDTH or result.height != EXPECTED_HEIGHT:
            result.warnings.append(
                f"Resolution {result.width}x{result.height} != expected {EXPECTED_WIDTH}x{EXPECTED_HEIGHT}"
            )

        if not (MIN_DURATION <= result.duration <= MAX_DURATION):
            result.errors.append(
                f"Duration {result.duration:.1f}s out of range [{MIN_DURATION}, {MAX_DURATION}]"
            )

        if not result.has_audio:
            result.warnings.append("No audio stream detected")

        if not result.video_codec:
            result.errors.append("No video stream detected")

        result.passed = len(result.errors) == 0
        logger.info(
            "validation_complete",
            path=video_path,
            passed=result.passed,
            errors=result.errors,
        )
        return result

    def _probe(self, video_path: str) -> dict[str, Any] | None:
        cmd = [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            video_path,
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True)
            if proc.returncode != 0:
                logger.error("ffprobe_error", stderr=proc.stderr)
                return None
            return json.loads(proc.stdout)
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            logger.error("ffprobe_exception", error=str(exc))
            return None
