from __future__ import annotations

import time
from typing import Any

import httpx
import structlog

from app.config import settings
from worker.modules.base import ScriptResult
from worker.modules.script_generator.base import AbstractScriptProvider

logger = structlog.get_logger(__name__)

DEFAULT_SYSTEM_PROMPT = (
    "You are a professional short-form video scriptwriter. "
    "Write an engaging 60-second narration script for the given topic. "
    "Use a conversational tone. No scene directions, only spoken text."
)

MAX_ATTEMPTS = 3
BASE_BACKOFF = 2.0  # seconds


class OpenAIRateLimitedError(Exception):
    """Raised when OpenAI returns 429 on all retry attempts."""


class OpenAIScriptProvider(AbstractScriptProvider):
    def generate(self, topic: str, config: dict[str, Any] | None = None) -> ScriptResult:
        cfg = config or {}
        system_prompt = cfg.get("system_prompt", DEFAULT_SYSTEM_PROMPT)
        model = cfg.get("model", "gpt-4o-mini")
        max_tokens = int(cfg.get("max_tokens", 512))

        # Resolve the specific visual subject so the script focuses on the
        # right concrete entity even when the topic is a generic category.
        from worker.modules.ai_images.prompt_builder import (
            resolve_visual_subject,
        )
        visual_tags: list[str] | None = cfg.get("visual_tags") or None
        if isinstance(visual_tags, str):
            visual_tags = [t.strip() for t in visual_tags.split(",") if t.strip()]
        resolved_subject, subject_source = resolve_visual_subject(
            topic, visual_tags=visual_tags
        )
        subject_is_specific = subject_source == "visual_tags"

        # Build user message: always include topic; append instructions when
        # present; inject visual subject constraint when tags provide a more
        # specific entity than the topic.
        instructions = cfg.get("instructions", "").strip()
        parts: list[str] = [f"Topic: {topic}"]
        if subject_is_specific:
            parts.append(f"The video must focus on: {resolved_subject}.")
        if instructions:
            parts.append(f"Instructions: {instructions}")
        parts.append("Generate a short narration script for a vertical social video.")
        user_message = "\n\n".join(parts)

        logger.info(
            "script_generation_subject",
            topic=topic,
            resolved_visual_subject=resolved_subject,
            subject_source=subject_source,
            subject_injected=subject_is_specific,
        )

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "max_tokens": max_tokens,
        }

        last_exc: Exception | None = None
        with httpx.Client(timeout=60) as client:
            for attempt in range(1, MAX_ATTEMPTS + 1):
                response = client.post(
                    f"{settings.OPENAI_BASE_URL}/chat/completions",
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
                        "Content-Type": "application/json",
                    },
                )

                if response.status_code == 429:
                    retry_after = response.headers.get("Retry-After")
                    if retry_after is not None:
                        try:
                            wait = float(retry_after)
                        except ValueError:
                            wait = BASE_BACKOFF * (2 ** (attempt - 1))
                    else:
                        wait = BASE_BACKOFF * (2 ** (attempt - 1))

                    last_exc = httpx.HTTPStatusError(
                        f"429 Too Many Requests (attempt {attempt}/{MAX_ATTEMPTS})",
                        request=response.request,
                        response=response,
                    )
                    if attempt < MAX_ATTEMPTS:
                        logger.warning(
                            "openai_rate_limited_retry",
                            attempt=attempt,
                            wait_seconds=wait,
                        )
                        time.sleep(wait)
                        continue
                    break

                response.raise_for_status()
                data = response.json()
                text = data["choices"][0]["message"]["content"].strip()
                return ScriptResult(
                    text=text,
                    metadata={"model": model, "usage": data.get("usage", {})},
                )

        raise OpenAIRateLimitedError(
            f"OpenAI returned 429 after {MAX_ATTEMPTS} attempts"
        ) from last_exc

