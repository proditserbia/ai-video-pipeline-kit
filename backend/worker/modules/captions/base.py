from __future__ import annotations

from abc import abstractmethod

from worker.modules.base import BaseCaptionProvider, CaptionResult


class AbstractCaptionProvider(BaseCaptionProvider):
    @abstractmethod
    def transcribe(self, audio_path: str, output_dir: str) -> CaptionResult: ...
