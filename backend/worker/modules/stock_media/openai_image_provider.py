from __future__ import annotations

import base64
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


class OpenAIImageProvider(AbstractStockProvider):
    """Generate images via the OpenAI Image API (gpt-image-1) and convert them
    to short video clips with a Ken Burns effect.

    Images are saved under ``STORAGE_PATH/generated/`` and converted to
    1080×1920 MP4 clips in *output_dir*.
    """

    def fetch(self, query: str, count: int, output_dir: str) -> list[MediaAsset]:
        if not settings.OPENAI_API_KEY:
            logger.warning("openai_image_no_api_key", hint="Set OPENAI_API_KEY in .env")
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
        logger.info("openai_image_generating", provider="openai", prompt=prompt)
        try:
            image_bytes = self._call_api(prompt)
        except Exception as exc:
            logger.error("openai_image_api_error", error=str(exc), prompt=prompt)
            return None

        image_path = generated_dir / f"openai_{index}.png"
        image_path.write_bytes(image_bytes)

        clip_path = out_dir / f"openai_{index}.mp4"
        try:
            image_to_video(image_path, clip_path)
        except Exception as exc:
            logger.error("openai_image_to_video_error", error=str(exc), image=str(image_path))
            return None

        logger.info("ai_image_generated", provider="openai", clip=str(clip_path))
        return MediaAsset(
            path=str(clip_path),
            source="ai",
            width=1080,
            height=1920,
            duration=6.0,
            metadata={"ai_provider": "openai", "prompt": prompt},
        )

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
