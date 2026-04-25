from __future__ import annotations

from abc import abstractmethod
from typing import Any

from worker.modules.base import BaseUploader, UploadResult


class AbstractUploader(BaseUploader):
    @abstractmethod
    def upload(self, video_path: str, metadata: dict[str, Any]) -> UploadResult: ...
