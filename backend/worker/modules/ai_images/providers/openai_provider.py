from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

import httpx
import structlog

from app.config import settings
from worker.modules.ai_images.base import AIImageProvider, GeneratedImage

logger = structlog.get_logger(__name__)


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
        logger.info("openai_image_generating", prompt=prompt)

        image_bytes = self._call_api(prompt)
        output_path.write_bytes(image_bytes)

        logger.info("openai_image_generated", path=str(output_path))
        return GeneratedImage(
            path=output_path,
            provider="openai",
            prompt=prompt,
            scene_id=(metadata or {}).get("scene_id", ""),
            width=1024,
            height=1024,
            metadata={"ai_provider": "openai", **(metadata or {})},
        )

    @classmethod
    def is_available(cls) -> bool:
        return bool(settings.OPENAI_API_KEY)

    def _call_api(self, prompt: str) -> bytes:
        """Call the OpenAI images/generations endpoint and return raw PNG bytes."""
        payload = {
            "model": settings.OPENAI_IMAGE_MODEL,
            "prompt": prompt,
            "n": 1,
            "size": "1024x1024",
            "response_format": "b64_json",
        }
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

        data = response.json()
        b64 = data["data"][0]["b64_json"]
        return base64.b64decode(b64)
