from __future__ import annotations

from pathlib import Path

import httpx
import structlog

from app.config import settings
from worker.modules.base import MediaAsset
from worker.modules.stock_media.base import AbstractStockProvider
from worker.modules.stock_media.image_to_video import image_to_video
from worker.modules.stock_media.prompt_generator import generate_scene_prompts

logger = structlog.get_logger(__name__)

_GENERATED_DIR = "generated"

# Stability AI REST API endpoint for SDXL text-to-image.
_STABILITY_API_URL = "https://api.stability.ai/v1/generation/{engine}/text-to-image"


class StabilityAIProvider(AbstractStockProvider):
    """Generate images via the Stability AI API (SDXL) and convert them to
    short video clips with a Ken Burns effect.

    Images are saved under ``STORAGE_PATH/generated/`` and converted to
    1080×1920 MP4 clips in *output_dir*.
    """

    def fetch(self, query: str, count: int, output_dir: str) -> list[MediaAsset]:
        if not settings.STABILITY_AI_API_KEY:
            logger.warning("stability_ai_no_api_key", hint="Set STABILITY_AI_API_KEY in .env")
            return []

        prompts = generate_scene_prompts(query, count)
        generated_dir = Path(settings.STORAGE_PATH) / _GENERATED_DIR
        generated_dir.mkdir(parents=True, exist_ok=True)
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        assets: list[MediaAsset] = []
        for i, prompt in enumerate(prompts):
            asset = self._generate_one(prompt, i, generated_dir, out_dir)
            if asset:
                assets.append(asset)

        return assets

    def _generate_one(
        self,
        prompt: str,
        index: int,
        generated_dir: Path,
        out_dir: Path,
    ) -> MediaAsset | None:
        logger.info("stability_ai_image_generating", provider="stability", prompt=prompt)
        try:
            image_bytes = self._call_api(prompt)
        except Exception as exc:
            logger.error("stability_ai_api_error", error=str(exc), prompt=prompt)
            return None

        image_path = generated_dir / f"stability_{index}.png"
        image_path.write_bytes(image_bytes)

        clip_path = out_dir / f"stability_{index}.mp4"
        try:
            image_to_video(image_path, clip_path)
        except Exception as exc:
            logger.error("stability_ai_image_to_video_error", error=str(exc), image=str(image_path))
            return None

        logger.info("ai_image_generated", provider="stability", clip=str(clip_path))
        return MediaAsset(
            path=str(clip_path),
            source="ai",
            width=1080,
            height=1920,
            duration=6.0,
            metadata={"ai_provider": "stability", "prompt": prompt},
        )

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
        import base64
        b64 = data["artifacts"][0]["base64"]
        return base64.b64decode(b64)
