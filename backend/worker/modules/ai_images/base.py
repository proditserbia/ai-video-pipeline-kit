from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class GeneratedImage:
    """Result of a single AI image generation call."""

    path: Path
    provider: str
    prompt: str
    scene_id: str
    width: int
    height: int
    metadata: dict[str, Any] = field(default_factory=dict)


class AIImageProvider(ABC):
    """Provider-agnostic interface for AI image generation.

    Concrete implementations live in the ``providers/`` sub-package and are
    instantiated exclusively through :func:`~factory.get_ai_image_provider`.
    No provider-specific logic should leak into calling code.
    """

    @abstractmethod
    def generate_image(
        self,
        prompt: str,
        output_path: Path,
        *,
        aspect_ratio: str = "9:16",
        metadata: dict[str, Any] | None = None,
    ) -> GeneratedImage:
        """Generate a single image for *prompt* and save it to *output_path*.

        Args:
            prompt:       Short, focused visual description.
            output_path:  Destination file (parent directory is created if needed).
            aspect_ratio: Target aspect ratio hint, e.g. ``"9:16"``.
            metadata:     Optional key/value pairs forwarded to the provider
                          (e.g. ``{"scene_id": "abc123"}``).

        Returns:
            :class:`GeneratedImage` with the resolved path and provenance info.

        Raises:
            RuntimeError: If generation fails unrecoverably.
        """

    @classmethod
    def is_available(cls) -> bool:
        """Return ``True`` if this provider can run in the current environment."""
        return True
