from __future__ import annotations

from typing import Any

from worker.modules.base import ScriptResult
from worker.modules.script_generator.base import AbstractScriptProvider

PLACEHOLDER_TEMPLATE = """\
Welcome to today's video about {topic}.

{topic} is one of the most fascinating subjects you can explore right now.
In this short video, we'll cover the key points you need to know, why it
matters, and what you can do with this knowledge today.

Let's dive straight in. First, let's understand what {topic} actually means
and why so many people are talking about it. Second, we'll look at the main
benefits and challenges. Finally, we'll wrap up with actionable next steps.

Stay tuned to the end for a bonus insight that most people miss.

Thanks for watching – if you found this useful, don't forget to like and
subscribe for more content just like this.
"""


class PlaceholderScriptProvider(AbstractScriptProvider):
    """Returns a structured placeholder script when no API key is configured."""

    def generate(self, topic: str, config: dict[str, Any] | None = None) -> ScriptResult:
        text = PLACEHOLDER_TEMPLATE.format(topic=topic)
        return ScriptResult(
            text=text,
            metadata={"provider": "placeholder", "topic": topic},
        )
