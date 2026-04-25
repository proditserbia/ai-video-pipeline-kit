from __future__ import annotations

"""
Headless API Mode schemas.

Supports three input modes:
- auto:         Provide only a topic; the pipeline decides everything else.
- semi_auto:    Provide a topic/script plus selective overrides.
- full_control: Explicitly configure every pipeline stage.

Template mode: provide a template_id + props dict to render a pre-defined template.
"""

import enum
from typing import Any

from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class HeadlessMode(str, enum.Enum):
    auto = "auto"
    semi_auto = "semi_auto"
    full_control = "full_control"


class TTSProvider(str, enum.Enum):
    edge_tts = "edge_tts"
    coqui = "coqui"


class CaptionStyle(str, enum.Enum):
    none = "none"
    basic = "basic"
    bold = "bold"
    karaoke = "karaoke"
    boxed = "boxed"


class UploadDestination(str, enum.Enum):
    local = "local"
    youtube = "youtube"
    tiktok = "tiktok"
    instagram = "instagram"
    facebook = "facebook"
    twitter = "twitter"


class VideoResolution(str, enum.Enum):
    vertical_1080 = "1080x1920"
    square_1080 = "1080x1080"
    landscape_1080 = "1920x1080"


# ---------------------------------------------------------------------------
# Sub-schemas
# ---------------------------------------------------------------------------


class ScriptConfig(BaseModel):
    """Script source configuration.

    In *auto* mode only ``topic`` is required.
    In *semi_auto* / *full_control* modes ``text`` may be supplied directly.
    """

    # AI-generated path
    topic: str | None = Field(None, description="Topic for AI script generation (auto / semi_auto)")
    category: str | None = Field(None, description="Content category (e.g. 'tech', 'finance')")
    tone: str = Field("professional", description="Desired tone of the script")
    duration_seconds: int = Field(60, ge=5, le=600, description="Target video duration in seconds")
    target_platform: str = Field("tiktok", description="Target platform (affects script style)")
    language: str = Field("en", description="ISO 639-1 language code")

    # Manual path
    text: str | None = Field(None, description="Full script text (skips AI generation)")

    @model_validator(mode="after")
    def _require_topic_or_text(self) -> "ScriptConfig":
        if not self.topic and not self.text:
            raise ValueError("Either 'topic' or 'text' must be provided in script config")
        return self


class VoiceConfig(BaseModel):
    """TTS / voice configuration."""

    provider: TTSProvider = Field(TTSProvider.edge_tts, description="TTS provider to use")
    voice_id: str = Field("en-US-JennyNeural", description="Voice identifier for the provider")
    rate: str = Field("+0%", description="Speech rate adjustment (e.g. '+10%', '-5%')")
    pitch: str = Field("+0Hz", description="Pitch adjustment (e.g. '+5Hz', '-10Hz')")
    volume: str = Field("+0%", description="Volume adjustment")


class CaptionConfig(BaseModel):
    """Caption / subtitle configuration."""

    enabled: bool = Field(True, description="Whether to generate and burn captions")
    style: CaptionStyle = Field(CaptionStyle.basic, description="Caption rendering style")
    provider: str = Field("whisper", description="Transcription provider (whisper)")
    language: str | None = Field(None, description="Force transcription language (ISO 639-1)")
    max_line_width: int = Field(40, ge=10, le=120, description="Max characters per caption line")


class VideoConfig(BaseModel):
    """Video assembly configuration."""

    resolution: VideoResolution = Field(
        VideoResolution.vertical_1080, description="Output video resolution"
    )
    background_music: bool = Field(False, description="Add background music track")
    background_music_volume: float = Field(
        0.15, ge=0.0, le=1.0, description="Background music volume (0.0–1.0)"
    )
    watermark: bool = Field(False, description="Overlay project watermark")
    stock_query: str | None = Field(
        None, description="Search query for stock media (defaults to topic)"
    )
    stock_provider: str | None = Field(
        None, description="Stock media provider override (pexels, pixabay, local)"
    )
    thumbnail: bool = Field(True, description="Extract thumbnail from output video")
    codec: str = Field("h264", description="Video codec (h264 or nvenc_h264)")
    fps: int = Field(30, ge=15, le=60, description="Frames per second")


class UploadConfig(BaseModel):
    """Upload / publish configuration."""

    destinations: list[UploadDestination] = Field(
        [UploadDestination.local], description="Upload destinations"
    )
    title_override: str | None = Field(None, description="Override video title for platforms")
    description_override: str | None = Field(None, description="Override description for platforms")
    tags: list[str] = Field(default_factory=list, description="Tags / hashtags")
    privacy: str = Field("private", description="Privacy setting (public, private, unlisted)")
    dry_run: bool = Field(False, description="Simulate upload without actually publishing")


# ---------------------------------------------------------------------------
# Primary request schemas
# ---------------------------------------------------------------------------


class HeadlessJobCreate(BaseModel):
    """
    Structured JSON payload for headless video job creation.

    Modes:
    - **auto**: Provide only ``script.topic``; all other settings use smart defaults.
    - **semi_auto**: Provide topic/script plus selective ``voice``, ``caption``, or ``video`` overrides.
    - **full_control**: Explicitly configure every stage of the pipeline.
    """

    mode: HeadlessMode = Field(..., description="Input mode: auto | semi_auto | full_control")
    title: str = Field(..., min_length=1, max_length=512, description="Human-readable job title")
    project_id: int | None = Field(None, description="Optional project association")

    # Pipeline stage configs
    script: ScriptConfig = Field(..., description="Script source configuration")
    voice: VoiceConfig = Field(default_factory=VoiceConfig, description="TTS configuration")
    caption: CaptionConfig = Field(default_factory=CaptionConfig, description="Caption configuration")
    video: VideoConfig = Field(default_factory=VideoConfig, description="Video assembly configuration")
    upload: UploadConfig = Field(default_factory=UploadConfig, description="Upload configuration")

    # Job-level settings
    dry_run: bool = Field(False, description="Run pipeline without writing final output")
    max_retries: int = Field(3, ge=0, le=10, description="Maximum retry attempts on failure")
    priority: int = Field(5, ge=1, le=10, description="Job priority (1=lowest, 10=highest)")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Arbitrary key/value metadata stored with the job"
    )

    @model_validator(mode="after")
    def _validate_mode_requirements(self) -> "HeadlessJobCreate":
        """Enforce per-mode field requirements."""
        if self.mode == HeadlessMode.auto:
            if not self.script.topic:
                raise ValueError("'script.topic' is required in 'auto' mode")
        elif self.mode == HeadlessMode.full_control:
            if not self.script.text and not self.script.topic:
                raise ValueError(
                    "'script.text' or 'script.topic' is required in 'full_control' mode"
                )
        return self

    def to_input_data(self) -> dict[str, Any]:
        """Serialize to the ``input_data`` JSON column stored on the Job model."""
        return {
            "headless": True,
            "mode": self.mode.value,
            "script": self.script.model_dump(),
            "voice": self.voice.model_dump(),
            "caption": self.caption.model_dump(),
            "video": self.video.model_dump(),
            "upload": self.upload.model_dump(),
            "priority": self.priority,
            "metadata": self.metadata,
        }


# ---------------------------------------------------------------------------
# Template-based creation
# ---------------------------------------------------------------------------


class TemplateJobCreate(BaseModel):
    """
    Create a job by rendering a named template with supplied props.

    Built-in templates: quick_explainer, product_review, news_summary, tutorial, story_hook.
    Props replace ``{{key}}`` placeholders in the template's script text or topic.
    """

    template_id: str = Field(..., description="Template identifier (e.g. 'quick_explainer')")
    props: dict[str, Any] = Field(
        default_factory=dict,
        description="Key/value pairs that fill template placeholders",
    )
    project_id: int | None = Field(None, description="Optional project association")
    voice: VoiceConfig = Field(default_factory=VoiceConfig, description="TTS override")
    upload: UploadConfig = Field(default_factory=UploadConfig, description="Upload override")
    dry_run: bool = Field(False, description="Simulate without writing final output")
    max_retries: int = Field(3, ge=0, le=10)


# ---------------------------------------------------------------------------
# Response helpers
# ---------------------------------------------------------------------------


class HeadlessJobResponse(BaseModel):
    """Slim response for headless job creation — includes only actionable fields."""

    job_id: str
    status: str
    mode: str
    title: str
    dry_run: bool
    poll_url: str = Field(description="URL to poll for job status")
    logs_url: str = Field(description="URL to stream job logs")


class TemplateInfo(BaseModel):
    """Metadata about a built-in template."""

    id: str
    name: str
    description: str
    required_props: list[str]
    optional_props: list[str]
    example_props: dict[str, Any]
