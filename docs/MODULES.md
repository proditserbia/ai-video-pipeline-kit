# Pipeline Modules

The AI Video Pipeline Kit is composed of independent modules, each handling one stage of
the production pipeline. Modules are guarded by feature flags — disabled modules are
gracefully skipped rather than failing the job.

## Pipeline execution order

```
Job created (API)
│
├── 1. Script      → generate or use provided text
├── 2. TTS         → synthesise voice-over audio
├── 3. Stock media → fetch or generate video clips
├── 4. Captions    → transcribe audio → SRT/VTT/JSON
├── 5. Video build → FFmpeg assemble final MP4
├── 6. Validate    → ffprobe quality gate
└── 7. Upload/export → local copy or remote platform
```

---

## 1. Script Generator (`worker/modules/script_generator/`)

Generates or passes through the narration script for the video.

### PlaceholderScriptProvider *(default — no API key required)*

Produces a structured template script when no `OPENAI_API_KEY` is set.
- Always available, zero latency, no network call.
- Output is predictable and suitable for testing dry-run pipelines.

### OpenAIScriptProvider

Calls the OpenAI Chat Completions API (or any compatible endpoint) with a system prompt
that instructs the model to write a 60-second short-form narration.

**Required env vars:** `OPENAI_API_KEY`  
**Optional env vars:** `OPENAI_BASE_URL`, `OPENAI_MODEL`  
**Feature flag:** `FEATURE_AI_SCRIPTS`

Per-job overrides (passed in `input_data.script_settings`):

| Key | Default | Description |
|-----|---------|-------------|
| `system_prompt` | built-in prompt | Override the system prompt |
| `model` | `gpt-4o-mini` | Model name |
| `max_tokens` | `512` | Maximum completion length |

---

## 2. Text-to-Speech (`worker/modules/tts/`)

Synthesises the narration script into an MP3 audio file.

### EdgeTTSProvider *(default — free, no API key)*

Uses the `edge-tts` library to call Microsoft Azure's Text-to-Speech endpoint through
the Edge browser protocol.

**Required env vars:** *(none)*  
**Feature flag:** `FEATURE_TTS`

Per-job voice selection: pass `voice` in `input_data` (e.g. `"en-US-JennyNeural"`).

Popular voices:
- `en-US-JennyNeural` — female, US English
- `en-US-AriaNeural` — female, US English
- `en-US-GuyNeural` — male, US English
- `en-GB-SoniaNeural` — female, British English

### CoquiTTSProvider *(not yet implemented)*

Placeholder for a local [Coqui TTS](https://github.com/coqui-ai/TTS) server.
Jobs will fail with `NotImplementedError` if `COQUI_TTS_ENABLED=true` and the
CoquiTTSProvider is selected. Use EdgeTTS instead.

**Status:** `COQUI_TTS_ENABLED=false` (disabled by default)

---

## 3. Stock Media (`worker/modules/stock_media/`)

Fetches or generates video clips to use as b-roll footage.

### LocalMediaProvider *(default — no API key)*

Scans `$STORAGE_PATH/assets/` for `.mp4`, `.mov`, `.avi`, `.mkv`, `.webm` files.
Falls back to generating solid-colour placeholder clips via FFmpeg when no local
assets are available.

**Feature flag:** `FEATURE_STOCK_MEDIA`

Upload your own clips to the assets library via the UI (Assets → Upload) or the
`POST /api/assets/upload` endpoint.

### PexelsProvider

Searches and downloads portrait-orientation videos from [Pexels](https://www.pexels.com/).

**Required env vars:** `PEXELS_API_KEY`  
**Feature flag:** `FEATURE_STOCK_MEDIA`

Returns empty list with a warning log when `PEXELS_API_KEY` is not set.

### PixabayProvider

Searches and downloads videos from [Pixabay](https://pixabay.com/).

**Required env vars:** `PIXABAY_API_KEY`  
**Feature flag:** `FEATURE_STOCK_MEDIA`

Returns empty list with a warning log when `PIXABAY_API_KEY` is not set.

> **Provider selection** — the pipeline currently always uses `LocalMediaProvider`.
> Pexels/Pixabay integration is available but requires explicitly wiring the provider
> in `video_pipeline.py` with valid API keys.

---

## 4. Captions (`worker/modules/captions/`)

Generates subtitles from the synthesised audio using speech-to-text.

### WhisperCaptionProvider

Transcribes audio using [faster-whisper](https://github.com/SYSTRAN/faster-whisper)
(a CTranslate2-optimised version of OpenAI Whisper).

Produces three output files per job:
- `captions.srt` — SubRip format (used by FFmpeg `subtitles=` filter)
- `captions.vtt` — WebVTT format
- `captions.json` — raw segments with timestamps

**Required env vars:** *(none — model downloads automatically on first use)*  
**Tuning env vars:** `WHISPER_MODEL_SIZE`, `WHISPER_DEVICE`  
**Feature flag:** `FEATURE_CAPTIONS`

> Whisper caption generation is skipped gracefully (with a log entry) when
> `faster-whisper` raises an exception (e.g. model download failure, OOM).
> The video is still produced without embedded captions.

---

## 5. Video Builder (`worker/modules/video_builder/`)

Assembles all assets into the final MP4 using FFmpeg.

### FFmpegVideoBuilder

Pipeline:
1. **Scale & crop** each clip to `1080×1920` (9:16 vertical, 30 fps).
2. **Concatenate** clips using the FFmpeg concat demuxer.
3. **Compose** final video with optional voice audio, background music, SRT subtitles,
   and watermark overlay.

**Output format:** `libx264`, CRF 23, `yuv420p`, AAC 128 kbps audio, vertical 1080×1920.  
**GPU encoding:** enabled when `NVIDIA_NVENC_ENABLED=true` → uses `h264_nvenc`.  
**Feature flag:** `FEATURE_CORE_VIDEO`

When no clips are provided (stock media step returned empty), the builder generates a
`10-second solid-colour placeholder clip` automatically so the pipeline always produces
a valid output.

### VideoValidator

Runs `ffprobe` on the output file to verify:
- File exists and is non-empty
- Duration is within `[1 s, 3600 s]`
- A video stream is present
- Resolution is `1080×1920` (warning only — does not fail the job)
- Audio stream is present (warning only — does not fail the job)

Validation result is stored as JSON in `job.validation_result`.

---

## 6. Uploader (`worker/modules/uploader/`)

Exports or uploads the finished video.

### LocalExporter *(default)*

Copies the output file to `$STORAGE_PATH/outputs/` and returns a `file://` URI.
Always available — no configuration required.

### YouTubeUploader *(not yet implemented)*

Returns a skipped result with a clear reason if `YOUTUBE_CLIENT_SECRETS_FILE` is not
configured.

The full OAuth2 + Data API v3 upload flow is marked as TODO; the class raises
`NotImplementedError` if invoked with a valid secrets file.

**Status:** `YOUTUBE_UPLOAD_ENABLED=false` (disabled by default)  
**Feature flag:** `FEATURE_YOUTUBE_UPLOAD`

---

## 7. Trend Discovery (`worker/modules/trends/`)

Discovers trending topics and stores them for job scheduling.

### GoogleTrendsProvider

Uses `pytrends` to fetch top trending searches from Google.

**Status:** optional — skipped gracefully if `pytrends` raises an exception.

### RSSProvider

Parses RSS feeds (BBC, CNN, Reuters by default) using `feedparser`.

**Status:** optional — skipped gracefully if `feedparser` raises an exception.

**Feature flag:** `FEATURE_TRENDS`

Both providers are called by the `discover_trends` Celery beat task (runs every hour).
Topics appear in the **Topics** section of the dashboard for manual approval before
being used as job inputs.

---

## Disabling / Skipping Modules

Set the corresponding feature flag to `false` in `.env`:

```env
FEATURE_CAPTIONS=false    # skip Whisper transcription
FEATURE_STOCK_MEDIA=false # skip stock media fetch (video uses placeholder clip)
FEATURE_TRENDS=false      # skip trend discovery task
```

Optional modules that are not fully implemented return a clear skip/error message
rather than silently producing wrong output:

| Module | Behaviour when unavailable |
|--------|---------------------------|
| `CoquiTTSProvider` | `NotImplementedError` with setup instructions |
| `YouTubeUploader` (no secrets) | `UploadResult(skipped=True, skip_reason="…")` |
| `YouTubeUploader` (with secrets) | `NotImplementedError` with TODO note |
| Whisper (exception) | Logged, captions step skipped, video continues |
