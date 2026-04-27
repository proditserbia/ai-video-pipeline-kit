from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal


@dataclass
class VisualSegment:
    """A single timed visual segment in the video timeline.

    Attributes:
        path:       Path to the source media file (image or video).
        start_time: Segment start in seconds relative to the beginning of
                    the final video.
        end_time:   Segment end in seconds.
        duration:   Segment length in seconds (``end_time - start_time``).
        type:       ``"image"`` for still images, ``"video"`` for video clips.
        scene_id:   Optional reference to the originating :class:`ScriptScene`
                    id for traceability.
    """

    path: Path
    start_time: float
    end_time: float
    duration: float
    type: Literal["image", "video"]
    scene_id: str = ""
