from __future__ import annotations

import subprocess
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)

# Target format: vertical 1080x1920 (9:16)
WIDTH = 1080
HEIGHT = 1920


def _escape_srt_path(path: str) -> str:
    """
    Escape a file path for use in FFmpeg's subtitles= filter.
    Characters that must be escaped: backslash, colon, single-quote,
    brackets, and other special chars interpreted by the filter.
    """
    # On all platforms, forward-slashes are safe for FFmpeg
    path = path.replace("\\", "/")
    # Escape characters that libavfilter treats as special
    for ch in (":", "'", "[", "]", ";", ","):
        path = path.replace(ch, "\\" + ch)
    return path
    """Run an FFmpeg/ffprobe command. Never uses shell=True."""
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error("ffmpeg_error", cmd=cmd, stderr=result.stderr)
        raise RuntimeError(f"FFmpeg command failed: {result.stderr[:500]}")
    return result


class FFmpegVideoBuilder:
    """Builds a 1080x1920 vertical MP4 from clips + audio + optional SRT."""

    def build(
        self,
        clips: list[Path],
        audio_path: Path | None,
        srt_path: Path | None,
        output_path: Path,
        use_nvenc: bool = False,
        watermark_path: Path | None = None,
        bg_music_path: Path | None = None,
        bg_music_volume: float = 0.15,
    ) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if not clips:
            clips = self._generate_placeholder_clip(output_path.parent)

        prepared = self._prepare_clips(clips, output_path.parent)
        concat_video = self._concatenate_clips(prepared, output_path.parent)
        final = self._compose(
            video=concat_video,
            audio_path=audio_path,
            srt_path=srt_path,
            output_path=output_path,
            use_nvenc=use_nvenc,
            watermark_path=watermark_path,
            bg_music_path=bg_music_path,
            bg_music_volume=bg_music_volume,
        )
        logger.info("video_built", output=str(output_path))

    # ── Internal helpers ──────────────────────────────────────────────

    def _generate_placeholder_clip(self, work_dir: Path) -> list[Path]:
        """Generate a 10-second solid-colour placeholder clip."""
        clip_path = work_dir / "placeholder.mp4"
        _run([
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", f"color=c=0x1a1a2e:size={WIDTH}x{HEIGHT}:rate=30:duration=10",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            str(clip_path),
        ])
        return [clip_path]

    def _prepare_clips(self, clips: list[Path], work_dir: Path) -> list[Path]:
        """Scale/crop each clip to 1080x1920 and trim/loop to ~10 s."""
        prepared: list[Path] = []
        for i, clip in enumerate(clips):
            out = work_dir / f"clip_{i:03d}.mp4"
            # Scale with crop to maintain aspect ratio for 9:16
            vf = (
                f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
                f"crop={WIDTH}:{HEIGHT}"
            )
            _run([
                "ffmpeg", "-y",
                "-stream_loop", "-1",
                "-i", str(clip),
                "-t", "10",
                "-vf", vf,
                "-c:v", "libx264",
                "-crf", "23",
                "-preset", "fast",
                "-pix_fmt", "yuv420p",
                "-an",
                str(out),
            ])
            prepared.append(out)
        return prepared

    def _concatenate_clips(self, clips: list[Path], work_dir: Path) -> Path:
        """Concatenate clips using the concat demuxer."""
        list_file = work_dir / "concat_list.txt"
        list_file.write_text("\n".join(f"file '{str(c)}'" for c in clips))
        concat_path = work_dir / "concat.mp4"
        _run([
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(list_file),
            "-c", "copy",
            str(concat_path),
        ])
        return concat_path

    def _compose(
        self,
        video: Path,
        audio_path: Path | None,
        srt_path: Path | None,
        output_path: Path,
        use_nvenc: bool,
        watermark_path: Path | None,
        bg_music_path: Path | None,
        bg_music_volume: float,
    ) -> Path:
        cmd: list[str] = ["ffmpeg", "-y", "-i", str(video)]

        audio_index: int | None = None
        if audio_path and audio_path.exists():
            cmd += ["-i", str(audio_path)]
            audio_index = 1
            if bg_music_path and bg_music_path.exists():
                cmd += ["-i", str(bg_music_path)]

        # Video filter chain
        vf_parts: list[str] = []

        if srt_path and srt_path.exists():
            srt_escaped = _escape_srt_path(str(srt_path))
            vf_parts.append(f"subtitles='{srt_escaped}'")

        if watermark_path and watermark_path.exists():
            cmd += ["-i", str(watermark_path)]
            # Overlay watermark at bottom-right with 10px margin
            vf_parts.append(
                f"[0:v][{2 if audio_index else 1}:v]overlay=W-w-10:H-h-10[v]"
            )

        video_codec = ["libx264", "-crf", "23", "-preset", "fast"]
        if use_nvenc:
            video_codec = ["h264_nvenc", "-preset", "p4", "-rc", "vbr", "-cq", "24"]

        if vf_parts:
            cmd += ["-vf", ",".join(vf_parts)]

        cmd += ["-c:v"] + video_codec + ["-pix_fmt", "yuv420p"]

        if audio_index is not None:
            if bg_music_path and bg_music_path.exists():
                # Mix voice + background music
                cmd += [
                    "-filter_complex",
                    f"[{audio_index}:a]volume=1.0[voice];"
                    f"[2:a]volume={bg_music_volume}[bg];"
                    "[voice][bg]amix=inputs=2:duration=first[aout]",
                    "-map", "0:v",
                    "-map", "[aout]",
                ]
            else:
                cmd += [
                    "-map", "0:v",
                    "-map", f"{audio_index}:a",
                ]
            cmd += ["-c:a", "aac", "-b:a", "128k", "-shortest"]
        else:
            cmd += ["-an"]

        cmd.append(str(output_path))
        _run(cmd)
        return output_path

    def extract_thumbnail(self, video_path: Path, output_path: Path, timestamp: str = "00:00:01") -> Path:
        """Extract a single frame as thumbnail."""
        _run([
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-ss", timestamp,
            "-frames:v", "1",
            str(output_path),
        ])
        return output_path
