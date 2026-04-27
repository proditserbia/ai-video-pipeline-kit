from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

import httpx
import structlog

from app.config import settings
from worker.modules.ai_images.base import AIImageProvider, GeneratedImage

logger = structlog.get_logger(__name__)

_STABILITY_API_URL = "https://api.stability.ai/v1/generation/{engine}/text-to-image"


class StabilityAIProvider(AIImageProvider):
    """Generate images via the Stability AI API (SDXL)."""

    def generate_image(
        self,
        prompt: str,
        output_path: Path,
        *,
        aspect_ratio: str = "9:16",
        metadata: dict[str, Any] | None = None,
    ) -> GeneratedImage:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        logger.info("stability_image_generating", prompt=prompt)

        image_bytes = self._call_api(prompt)
        output_path.write_bytes(image_bytes)

        logger.info("stability_image_generated", path=str(output_path))
        return GeneratedImage(
            path=output_path,
            provider="stability",
            prompt=prompt,
            scene_id=(metadata or {}).get("scene_id", ""),
            width=1024,
            height=1024,
            metadata={"ai_provider": "stability", **(metadata or {})},
        )

    @classmethod
    def is_available(cls) -> bool:
        return bool(settings.STABILITY_AI_API_KEY)

    def _call_api(self, prompt: str) -> bytes:
        """Call the Stability AI text-to-image endpoint and return raw PNG bytes."""
        url = _STABILITY_API_URL.format(engine=settings.STABILITY_AI_MODEL)
        payload = {
            "text_prompts": [{"text": prompt, "weight": 1.0}],
            "cfg_scale": 7,
            "height": 1024,
            "width": 1024,
            "steps": 30,
            "samples": 1,
        }
        with httpx.Client(timeout=120) as client:
            response = client.post(
                url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {settings.STABILITY_AI_API_KEY}",
                    "Accept": "application/json",
                },
            )
            response.raise_for_status()

        data = response.json()
        b64 = data["artifacts"][0]["base64"]
        return base64.b64decode(b64)
