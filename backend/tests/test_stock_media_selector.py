from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from worker.modules.base import MediaAsset
from worker.modules.stock_media.selector import StockMediaSelector


def _asset(source: str, path: str = "/tmp/clip.mp4") -> MediaAsset:
    return MediaAsset(path=path, source=source)


class TestStockMediaSelectorProviderSelection:
    """Verify the priority chain: Pexels → Pixabay → Local → Placeholder."""

    def test_pexels_used_when_key_set_and_returns_assets(self, tmp_path):
        pexels_assets = [_asset("pexels")]
        with (
            patch("app.config.settings.PEXELS_API_KEY", "fake-pexels-key"),
            patch(
                "worker.modules.stock_media.pexels_provider.PexelsProvider.fetch",
                return_value=pexels_assets,
            ),
        ):
            selector = StockMediaSelector()
            assets, provider = selector.fetch("nature", 1, str(tmp_path))

        assert provider == "pexels"
        assert assets == pexels_assets

    def test_falls_back_to_pixabay_when_pexels_empty(self, tmp_path):
        pixabay_assets = [_asset("pixabay")]
        with (
            patch("app.config.settings.PEXELS_API_KEY", "fake-pexels-key"),
            patch("app.config.settings.PIXABAY_API_KEY", "fake-pixabay-key"),
            patch(
                "worker.modules.stock_media.pexels_provider.PexelsProvider.fetch",
                return_value=[],
            ),
            patch(
                "worker.modules.stock_media.pixabay_provider.PixabayProvider.fetch",
                return_value=pixabay_assets,
            ),
        ):
            selector = StockMediaSelector()
            assets, provider = selector.fetch("nature", 1, str(tmp_path))

        assert provider == "pixabay"
        assert assets == pixabay_assets

    def test_falls_back_to_local_when_no_api_keys_and_local_files_exist(self, tmp_path):
        local_assets = [_asset("local")]
        with (
            patch("app.config.settings.PEXELS_API_KEY", None),
            patch("app.config.settings.PIXABAY_API_KEY", None),
            patch(
                "worker.modules.stock_media.local_provider.LocalMediaProvider.fetch",
                return_value=local_assets,
            ),
        ):
            selector = StockMediaSelector()
            assets, provider = selector.fetch("nature", 1, str(tmp_path))

        assert provider == "local"
        assert assets == local_assets

    def test_placeholder_provider_when_no_api_keys_and_no_local_files(self, tmp_path):
        placeholder_assets = [_asset("local_placeholder")]
        with (
            patch("app.config.settings.PEXELS_API_KEY", None),
            patch("app.config.settings.PIXABAY_API_KEY", None),
            patch(
                "worker.modules.stock_media.local_provider.LocalMediaProvider.fetch",
                return_value=placeholder_assets,
            ),
        ):
            selector = StockMediaSelector()
            assets, provider = selector.fetch("nature", 1, str(tmp_path))

        assert provider == "placeholder"
        assert assets == placeholder_assets

    def test_pixabay_not_tried_when_pexels_succeeds(self, tmp_path):
        pexels_assets = [_asset("pexels")]
        pixabay_mock = MagicMock(return_value=[_asset("pixabay")])
        with (
            patch("app.config.settings.PEXELS_API_KEY", "fake-pexels-key"),
            patch("app.config.settings.PIXABAY_API_KEY", "fake-pixabay-key"),
            patch(
                "worker.modules.stock_media.pexels_provider.PexelsProvider.fetch",
                return_value=pexels_assets,
            ),
            patch(
                "worker.modules.stock_media.pixabay_provider.PixabayProvider.fetch",
                pixabay_mock,
            ),
        ):
            selector = StockMediaSelector()
            _, provider = selector.fetch("nature", 1, str(tmp_path))

        assert provider == "pexels"
        pixabay_mock.assert_not_called()

    def test_falls_back_to_local_when_both_api_providers_empty(self, tmp_path):
        local_assets = [_asset("local")]
        with (
            patch("app.config.settings.PEXELS_API_KEY", "fake-pexels-key"),
            patch("app.config.settings.PIXABAY_API_KEY", "fake-pixabay-key"),
            patch(
                "worker.modules.stock_media.pexels_provider.PexelsProvider.fetch",
                return_value=[],
            ),
            patch(
                "worker.modules.stock_media.pixabay_provider.PixabayProvider.fetch",
                return_value=[],
            ),
            patch(
                "worker.modules.stock_media.local_provider.LocalMediaProvider.fetch",
                return_value=local_assets,
            ),
        ):
            selector = StockMediaSelector()
            assets, provider = selector.fetch("nature", 1, str(tmp_path))

        assert provider == "local"
        assert assets == local_assets

    def test_provider_name_is_local_when_mix_of_local_and_placeholder(self, tmp_path):
        mixed_assets = [_asset("local"), _asset("local_placeholder")]
        with (
            patch("app.config.settings.PEXELS_API_KEY", None),
            patch("app.config.settings.PIXABAY_API_KEY", None),
            patch(
                "worker.modules.stock_media.local_provider.LocalMediaProvider.fetch",
                return_value=mixed_assets,
            ),
        ):
            selector = StockMediaSelector()
            _, provider = selector.fetch("nature", 2, str(tmp_path))

        assert provider == "local"
