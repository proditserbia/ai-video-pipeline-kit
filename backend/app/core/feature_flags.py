from __future__ import annotations

from app.config import settings


class FeatureFlags:
    def __init__(self) -> None:
        self._flags: dict[str, bool] = {
            k: bool(v) for k, v in settings.FEATURE_FLAGS.items()
        }

    def is_enabled(self, flag_name: str) -> bool:
        return self._flags.get(flag_name, False)

    def get_all(self) -> dict[str, bool]:
        return dict(self._flags)


feature_flags = FeatureFlags()
