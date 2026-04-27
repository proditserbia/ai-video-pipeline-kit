from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

import httpx
import structlog

from app.config import settings
from worker.modules.ai_images.base import AIImageProvider, GeneratedImage

logger = structlog.get_logger(__name__)

# Map aspect-ratio hints to gpt-image-1 supported sizes.
# gpt-image-1 does NOT accept an "aspect_ratio" field directly.
_ASPECT_RATIO_TO_SIZE: dict[str, str] = {
    "9:16": "1024x1536",   # portrait
    "16:9": "1536x1024",   # landscape
    "1:1": "1024x1024",    # square
}
_DEFAULT_SIZE = "1024x1536"

# Pre-computed width/height for GeneratedImage provenance metadata.
_SIZE_DIMENSIONS: dict[str, tuple[int, int]] = {
    "1024x1536": (1024, 1536),
    "1536x1024": (1536, 1024),
    "1024x1024": (1024, 1024),
}


class OpenAIImageProvider(AIImageProvider):
    """Generate images via the OpenAI Image API (gpt-image-1)."""

    def __init__(self) -> None:
        if not settings.OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY is not set")

    def generate_image(
        self,
        prompt: str,
        output_path: Path,
        *,
        aspect_ratio: str = "9:16",
        metadata: dict[str, Any] | None = None,
    ) -> GeneratedImage:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        size = _ASPECT_RATIO_TO_SIZE.get(aspect_ratio, _DEFAULT_SIZE)
        logger.info("openai_image_generating", prompt=prompt, aspect_ratio=aspect_ratio, size=size)

        image_bytes = self._call_api(prompt, size=size)
        output_path.write_bytes(image_bytes)

        if not output_path.exists():
            raise RuntimeError(f"OpenAI image was not written to {output_path}")

        width, height = _SIZE_DIMENSIONS.get(size, (1024, 1536))
        logger.info("openai_image_generated", path=str(output_path), size=size)
        return GeneratedImage(
            path=output_path,
            provider="openai",
            prompt=prompt,
            scene_id=(metadata or {}).get("scene_id", ""),
            width=width,
            height=height,
            metadata={"ai_provider": "openai", **(metadata or {})},
        )

    @classmethod
    def is_available(cls) -> bool:
        return bool(settings.OPENAI_API_KEY)

    def _call_api(self, prompt: str, *, size: str = _DEFAULT_SIZE) -> bytes:
        """Call the OpenAI images/generations endpoint and return raw PNG bytes.

        Notes:
        - gpt-image-1 does NOT support the ``response_format`` parameter;
          it always returns base64-encoded image data in ``data[0]["b64_json"]``.
        - ``aspect_ratio`` must be mapped to a valid ``size`` before calling.
        """
        payload: dict[str, Any] = {
            "model": settings.OPENAI_IMAGE_MODEL,
            "prompt": prompt,
            "n": 1,
            "size": size,
        }
        try:
            with httpx.Client(timeout=120) as client:
                response = client.post(
                    f"{settings.OPENAI_BASE_URL}/images/generations",
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
                        "Content-Type": "application/json",
                    },
                )
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            body = exc.response.text[:2000] if exc.response is not None else ""
            raise RuntimeError(
                f"OpenAI image generation failed: {exc.response.status_code} {body}"
            ) from exc

        data = response.json()
        b64 = data["data"][0]["b64_json"]
        return base64.b64decode(b64)
