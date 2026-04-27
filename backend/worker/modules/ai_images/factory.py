from __future__ import annotations

import structlog

from app.config import settings
from worker.modules.ai_images.base import AIImageProvider

logger = structlog.get_logger(__name__)

# Registry maps provider name → (module path, class name).
# Adding a new provider requires only a new entry here plus a new class file.
_PROVIDER_REGISTRY: dict[str, tuple[str, str]] = {
    "openai": (
        "worker.modules.ai_images.providers.openai_provider",
        "OpenAIImageProvider",
    ),
    "stability": (
        "worker.modules.ai_images.providers.stability_provider",
        "StabilityAIProvider",
    ),
    "local_mock": (
        "worker.modules.ai_images.providers.local_mock_provider",
        "LocalMockImageProvider",
    ),
}


def get_ai_image_provider() -> AIImageProvider:
    """Return the configured :class:`AIImageProvider` instance.

    The provider is selected via the ``AI_IMAGE_PROVIDER`` setting
    (default: ``"openai"``).  The factory is the *only* place that maps
    provider names to concrete classes — no ``if provider == "openai"``
    logic should exist elsewhere in the pipeline.

    Raises:
        ValueError: If the configured provider name is unknown.
        RuntimeError: If the provider reports it is not available
            (e.g. a required API key is missing).
    """
    name = (settings.AI_IMAGE_PROVIDER or "openai").lower().strip()

    entry = _PROVIDER_REGISTRY.get(name)
    if entry is None:
        known = ", ".join(sorted(_PROVIDER_REGISTRY))
        raise ValueError(
            f"Unknown AI_IMAGE_PROVIDER: {name!r}. "
            f"Known providers: {known}."
        )

    module_path, class_name = entry

    import importlib
    module = importlib.import_module(module_path)
    provider_cls = getattr(module, class_name)
    provider: AIImageProvider = provider_cls()

    if not provider.is_available():
        raise RuntimeError(
            f"AI image provider {name!r} is not available in this environment. "
            "Check that the required API key or dependency is configured."
        )

    logger.info("ai_image_provider_selected", provider=name)
    return provider
