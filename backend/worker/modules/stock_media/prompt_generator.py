from __future__ import annotations

import re
import textwrap


def generate_scene_prompts(script_text: str, count: int) -> list[str]:
    """Convert a narration script into *count* cinematic image prompts.

    The script is split into roughly equal text chunks; each chunk is
    turned into a short visual description suitable for an AI image
    generator.  A cinematic framing prefix and quality suffix are added
    so that generated images work well as video backgrounds.

    Args:
        script_text: Full narration script (may be empty).
        count: Number of distinct prompts to generate.

    Returns:
        A list of exactly *count* prompt strings.
    """
    if not script_text or not script_text.strip():
        return [_cinematic("abstract cinematic background, dramatic lighting")] * count

    # Split into sentences on common terminators.
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", script_text.strip()) if s.strip()]

    if not sentences:
        return [_cinematic(script_text.strip())] * count

    # Distribute sentences across slots.
    prompts: list[str] = []
    total = len(sentences)
    for i in range(count):
        start = (i * total) // count
        end = ((i + 1) * total) // count
        chunk = " ".join(sentences[start:end]) if start < end else sentences[i % total]
        # Summarise long chunks to keep prompts focused.
        if len(chunk) > 120:
            chunk = textwrap.shorten(chunk, width=120, placeholder="...")
        prompts.append(_cinematic(chunk))

    return prompts


def _cinematic(description: str) -> str:
    """Wrap a description in a cinematic image-generation style prompt."""
    return (
        f"A cinematic scene of {description}, "
        "dramatic lighting, photorealistic, high detail, wide shot, 16:9"
    )
