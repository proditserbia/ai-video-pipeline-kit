from __future__ import annotations

from typing import Any

import httpx

from app.config import settings
from worker.modules.base import ScriptResult
from worker.modules.script_generator.base import AbstractScriptProvider

DEFAULT_SYSTEM_PROMPT = (
    "You are a professional short-form video scriptwriter. "
    "Write an engaging 60-second narration script for the given topic. "
    "Use a conversational tone. No scene directions, only spoken text."
)


class OpenAIScriptProvider(AbstractScriptProvider):
    def generate(self, topic: str, settings: dict[str, Any] | None = None) -> ScriptResult:
        cfg = settings or {}
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

        with httpx.Client(timeout=60) as client:
            response = client.post(
                f"{settings.OPENAI_BASE_URL}/chat/completions",
                json=payload,
                headers={
                    "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
                    "Content-Type": "application/json",
                },
            )
            response.raise_for_status()
            data = response.json()

        text = data["choices"][0]["message"]["content"].strip()
        return ScriptResult(
            text=text,
            metadata={"model": model, "usage": data.get("usage", {})},
        )
