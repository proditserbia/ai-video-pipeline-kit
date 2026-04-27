from __future__ import annotations

import subprocess
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)

# Output format: vertical 1080x1920 (9:16)
WIDTH = 1080
HEIGHT = 1920

# Ken Burns clip length bounds (seconds).
_MIN_DURATION = 5
_MAX_DURATION = 8
_DEFAULT_DURATION = 6


def image_to_video(
    image_path: Path,
    output_path: Path,
    duration: int = _DEFAULT_DURATION,
) -> Path:
    """Convert a still image to a short video clip with a Ken Burns effect.

    The zoompan filter produces a gentle zoom-in with a slight pan,
    creating the Ken Burns effect.  Output is a 1080x1920 (9:16) MP4
    at 25 fps.

    Args:
        image_path: Source image (any format supported by FFmpeg).
        output_path: Destination MP4 path.
        duration: Clip length in seconds (clamped to 5–8 s).

    Returns:
        *output_path* on success.

    Raises:
        RuntimeError: If FFmpeg exits with a non-zero code.
    """
    duration = max(_MIN_DURATION, min(_MAX_DURATION, duration))
    output_path.parent.mkdir(parents=True, exist_ok=True)

    frames = duration * 25  # 25 fps

    # zoompan: start at 1× zoom, reach 1.2× by the last frame.
    # x/y centres the crop window and shifts it slightly rightward/downward.
    zoompan = (
        f"zoompan="
        f"z='min(zoom+0.0008,1.2)':"
        f"x='iw/2-(iw/zoom/2)':"
        f"y='ih/2-(ih/zoom/2)':"
        f"d={frames}:"
        f"s={WIDTH}x{HEIGHT}:"
        f"fps=25"
    )

    cmd = [
        "ffmpeg", "-y",
        "-loop", "1",
        "-i", str(image_path),
        "-vf", zoompan,
        "-t", str(duration),
        "-c:v", "libx264",
        "-crf", "23",
        "-preset", "fast",
        "-pix_fmt", "yuv420p",
        "-an",
        str(output_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"image_to_video failed for {image_path}: {result.stderr[:400]}"
        )

    logger.info("image_to_video_done", image=str(image_path), output=str(output_path), duration=duration)
    return output_path
