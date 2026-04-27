"""Multi-image generation and best-image selection for AI image pipeline.

Provides:
- :func:`score_image`                  — 0-100 heuristic quality score for a
                                         generated image file.
- :func:`generate_and_select_best_image` — Generate N candidate images and
                                           return the best one.

Config:
    AI_IMAGE_VARIATIONS      – number of candidates to generate (default 1).
    AI_IMAGE_PICK_STRATEGY   – "score" or "random" (default "score").
    AI_IMAGE_KEEP_VARIATIONS – keep discarded candidates on disk (default False).
"""
from __future__ import annotations

import random
import shutil
from pathlib import Path
from typing import Any

import structlog

from worker.modules.ai_images.base import AIImageProvider, GeneratedImage

logger = structlog.get_logger(__name__)

# Minimum file size (bytes) for an image to be considered non-blank / non-corrupt.
_MIN_ACCEPTABLE_FILE_SIZE: int = 5_000   # 5 KB

# A "reasonable" minimum for a real AI-generated image.
_GOOD_FILE_SIZE_THRESHOLD: int = 50_000  # 50 KB


def score_image(
    image_path: Path,
    scene: Any = None,  # StoryboardScene — typed loosely to avoid circular import
) -> int:
    """Return a 0–100 quality score for a generated image file.

    Scoring is intentionally lightweight (no heavy ML):

    +20  file exists and is readable
    +20  file size ≥ ``_MIN_ACCEPTABLE_FILE_SIZE`` (not blank/corrupt)
    +20  file size ≥ ``_GOOD_FILE_SIZE_THRESHOLD`` (real AI content)
    +20  valid image dimensions detected (requires Pillow, otherwise +10)
    +20  aspect ratio close to 9:16 (±10 %)

    Args:
        image_path: Path to the image file to score.
        scene:      Optional storyboard scene (reserved for future use, e.g.
                    subject presence check with a vision model).

    Returns:
        Integer score in [0, 100].
    """
    if not image_path.exists():
        return 0

    score: int = 20  # file exists

    try:
        file_size = image_path.stat().st_size
    except OSError:
        return 0

    if file_size >= _MIN_ACCEPTABLE_FILE_SIZE:
        score += 20
    if file_size >= _GOOD_FILE_SIZE_THRESHOLD:
        score += 20

    try:
        from PIL import Image

        with Image.open(image_path) as img:
            width, height = img.size

        if width > 64 and height > 64:
            score += 20

        # Aspect ratio check: 9:16 ≈ 0.5625
        if height > 0:
            ratio = width / height
            expected = 9 / 16
            if abs(ratio - expected) <= 0.1:
                score += 20
    except Exception:
        # PIL not available or file is not a recognised image format.
        # Give a partial score so the file isn't unfairly penalised.
        score += 10

    return min(100, score)


def generate_and_select_best_image(
    provider: AIImageProvider,
    prompt: str,
    output_path: Path,
    *,
    n_variations: int = 1,
    pick_strategy: str = "score",
    aspect_ratio: str = "9:16",
    metadata: dict[str, Any] | None = None,
    keep_variations: bool = False,
    scene: Any = None,
) -> GeneratedImage:
    """Generate *n_variations* images and return the best one.

    When *n_variations* == 1 this is a transparent pass-through: the provider
    is called exactly once and its result is returned unchanged, so existing
    callers pay zero overhead.

    For *n_variations* > 1:
    - Image 0 uses the original *prompt* unchanged.
    - Images 1..N use the prompt with ", slightly different composition"
      appended to elicit natural diversity without changing the subject.
    - The best candidate is determined by *pick_strategy* (``"score"`` or
      ``"random"``).
    - The winner is copied to *output_path*; discarded variants are deleted
      unless *keep_variations* is True.

    Args:
        provider:        Configured :class:`AIImageProvider` instance.
        prompt:          Image prompt.
        output_path:     Canonical destination path for the selected image.
        n_variations:    Number of images to generate.  Clamped to [1, 10].
        pick_strategy:   ``"score"`` (default) or ``"random"``.
        aspect_ratio:    Aspect ratio hint forwarded to the provider.
        metadata:        Optional metadata forwarded to each provider call.
        keep_variations: When True, discarded variation files are kept on disk
                         (useful for debugging).
        scene:           Optional storyboard scene passed to :func:`score_image`.

    Returns:
        :class:`GeneratedImage` with ``path`` set to *output_path*.

    Raises:
        RuntimeError: When all generation attempts fail.
    """
    n_variations = max(1, min(10, n_variations))

    # Fast path — no overhead for the default case.
    if n_variations == 1:
        return provider.generate_image(
            prompt,
            output_path,
            aspect_ratio=aspect_ratio,
            metadata=metadata,
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)

    candidates: list[GeneratedImage] = []
    variation_paths: list[Path] = []

    for i in range(n_variations):
        var_path = output_path.parent / f"{output_path.stem}_var{i}{output_path.suffix}"
        variation_prompt = (
            prompt if i == 0 else f"{prompt}, slightly different composition"
        )
        try:
            gen = provider.generate_image(
                variation_prompt,
                var_path,
                aspect_ratio=aspect_ratio,
                metadata=metadata,
            )
            candidates.append(gen)
            variation_paths.append(var_path)
            logger.info(
                "image_variation_generated",
                variation=i,
                path=str(var_path),
                total_variations=n_variations,
            )
        except Exception as exc:
            logger.warning(
                "image_variation_failed",
                variation=i,
                error=str(exc),
            )

    if not candidates:
        raise RuntimeError(
            f"All {n_variations} image generation attempts failed for prompt: "
            f"{prompt[:120]!r}"
        )

    # Select the best candidate.
    if pick_strategy == "random":
        best_idx = random.randrange(len(candidates))
        scores = [0] * len(candidates)
    else:
        scores = [score_image(Path(c.path), scene) for c in candidates]
        best_idx = scores.index(max(scores))

    best = candidates[best_idx]

    logger.info(
        "image_variation_selected",
        selected_index=best_idx,
        image_scores=scores,
        best_score=scores[best_idx],
        image_variations_generated=len(candidates),
        pick_strategy=pick_strategy,
    )

    # Copy winner to the canonical output path (avoid rename so variation file
    # can be kept intact when keep_variations=True).
    if Path(best.path) != output_path:
        shutil.copy2(best.path, output_path)

    # Discard variation files unless keep_variations is requested.
    # All variation files (including the winning one) can be removed because
    # the winner has already been copied to the canonical output_path.
    if not keep_variations:
        for vpath in variation_paths:
            if vpath.exists() and vpath != output_path:
                try:
                    vpath.unlink()
                except OSError:
                    pass

    # Return a GeneratedImage pointing at the canonical output_path.
    return GeneratedImage(
        path=output_path,
        provider=best.provider,
        prompt=best.prompt,
        scene_id=best.scene_id,
        width=best.width,
        height=best.height,
        metadata={
            **(best.metadata or {}),
            "variations_generated": len(candidates),
            "selected_variation_index": best_idx,
            "image_scores": scores,
        },
    )
