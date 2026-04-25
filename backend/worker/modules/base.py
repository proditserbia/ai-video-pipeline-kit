from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ScriptResult:
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AudioResult:
    path: str
    duration_seconds: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class CaptionResult:
    srt_path: str | None
    vtt_path: str | None
    json_path: str | None
    segments: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class MediaAsset:
    path: str
    source: str
    width: int = 0
    height: int = 0
    duration: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class UploadResult:
    url: str
    platform: str
    metadata: dict[str, Any] = field(default_factory=dict)
    skipped: bool = False
    skip_reason: str = ""


@dataclass
class TrendItem:
    title: str
    source: str
    description: str | None = None
    score: float | None = None
    keywords: list[str] = field(default_factory=list)


class BaseScriptProvider(ABC):
    @abstractmethod
    def generate(self, topic: str, config: dict[str, Any] | None = None) -> ScriptResult: ...


class BaseTTSProvider(ABC):
    @abstractmethod
    async def synthesize(self, text: str, voice: str, output_path: str) -> AudioResult: ...


class BaseCaptionProvider(ABC):
    @abstractmethod
    def transcribe(self, audio_path: str, output_dir: str) -> CaptionResult: ...


class BaseVideoBuilder(ABC):
    @abstractmethod
    def build(
        self,
        clips: list[Path],
        audio_path: Path | None,
        srt_path: Path | None,
        output_path: Path,
        use_nvenc: bool = False,
    ) -> None: ...


class BaseStockProvider(ABC):
    @abstractmethod
    def fetch(self, query: str, count: int, output_dir: str) -> list[MediaAsset]: ...


class BaseUploader(ABC):
    @abstractmethod
    def upload(self, video_path: str, metadata: dict[str, Any]) -> UploadResult: ...


class BaseTrendProvider(ABC):
    @abstractmethod
    def fetch(self, keyword: str | None, limit: int) -> list[TrendItem]: ...


class ModuleNotAvailableError(RuntimeError):
    """Raised when an optional module dependency is not installed."""
