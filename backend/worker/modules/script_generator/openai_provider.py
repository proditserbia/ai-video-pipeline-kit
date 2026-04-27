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

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Topic: {topic}"},
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
