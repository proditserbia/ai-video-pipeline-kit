from __future__ import annotations

import struct
import zlib
from pathlib import Path
from typing import Any

import structlog

from worker.modules.ai_images.base import AIImageProvider, GeneratedImage

logger = structlog.get_logger(__name__)

# Cycle through these colours per scene index so successive images are visually distinct.
_PALETTE: list[tuple[int, int, int]] = [
    (44, 62, 80),    # dark blue-grey
    (142, 68, 173),  # purple
    (22, 160, 133),  # teal
    (192, 57, 43),   # red
    (39, 174, 96),   # green
    (41, 128, 185),  # blue
]


def _write_solid_colour_png(
    path: Path,
    width: int,
    height: int,
    rgb: tuple[int, int, int],
) -> None:
    """Write a minimal valid PNG with a solid colour — no external dependencies."""

    def _chunk(name: bytes, data: bytes) -> bytes:
        payload = name + data
        crc = zlib.crc32(payload) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + payload + struct.pack(">I", crc)

    # IHDR: width, height, bit_depth=8, color_type=2 (RGB), compression, filter, interlace
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)

    # Raw image data: one filter byte (0 = None) per scanline, then RGB pixels.
    row = b"\x00" + bytes(rgb) * width
    raw = row * height
    idat_data = zlib.compress(raw)

    png = (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", ihdr)
        + _chunk(b"IDAT", idat_data)
        + _chunk(b"IEND", b"")
    )
    path.write_bytes(png)


class LocalMockImageProvider(AIImageProvider):
    """Generates solid-colour PNG placeholders without any external API calls.

    Intended for local development and testing.  Each prompt is mapped to a
    distinct colour so that successive scenes are visually distinguishable.
    """

    def generate_image(
        self,
        prompt: str,
        output_path: Path,
        *,
        aspect_ratio: str = "9:16",
        metadata: dict[str, Any] | None = None,
    ) -> GeneratedImage:
        output_path.parent.mkdir(parents=True, exist_ok=True)

        colour = _PALETTE[abs(hash(prompt)) % len(_PALETTE)]
        # Use a small size to keep test output minimal.
        _write_solid_colour_png(output_path, width=64, height=114, rgb=colour)

        scene_id = (metadata or {}).get("scene_id", "")
        logger.info("local_mock_image_generated", path=str(output_path), scene_id=scene_id)
        return GeneratedImage(
            path=output_path,
            provider="local_mock",
            prompt=prompt,
            scene_id=scene_id,
            width=64,
            height=114,
            metadata={"ai_provider": "local_mock", **(metadata or {})},
        )

    @classmethod
    def is_available(cls) -> bool:
        return True
