# Configuration Reference

All configuration is done through environment variables. Copy `.env.example` to `.env`
and edit the values before running `docker compose up`.

## Database

| Variable | Default | Description |
|----------|---------|-------------|
| `POSTGRES_USER` | `aivideo` | PostgreSQL username |
| `POSTGRES_PASSWORD` | `aivideo_secret` | PostgreSQL password (**change in production**) |
| `POSTGRES_DB` | `aivideo` | PostgreSQL database name |

> **Internal wiring** — `docker-compose.yml` derives `DATABASE_URL` (asyncpg, used by FastAPI)
> and `SYNC_DATABASE_URL` (psycopg2, used by Celery workers and Alembic) from the three vars
> above. You do not need to set the full connection strings manually.

## Redis

Redis is provisioned automatically by Docker Compose. The URL is wired from the compose
file and does not need to be set by the user. Override if you bring your own Redis:

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_URL` | `redis://redis:6379/0` | Broker + result backend URL for Celery |

## Security

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | `change_me_…` | JWT signing secret — **must be changed in production** (≥ 32 chars). Generate with `openssl rand -hex 32` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | JWT access-token lifetime in minutes |

## Admin User (seeded on first start)

| Variable | Default | Description |
|----------|---------|-------------|
| `ADMIN_EMAIL` | `admin@example.com` | Email for the seeded admin account |
| `ADMIN_PASSWORD` | `admin123!` | Password for the seeded admin account (**change in production**) |

## Service Ports

| Variable | Default | Description |
|----------|---------|-------------|
| `BACKEND_PORT` | `8000` | Host port mapped to the FastAPI backend |
| `FRONTEND_PORT` | `3000` | Host port mapped to the Next.js frontend |

## Storage

| Variable | Default | Description |
|----------|---------|-------------|
| `STORAGE_PATH` | `/storage` | Root directory for all generated files (uploads, outputs, temp) |

### S3-Compatible Storage (optional)

Leave all S3 variables empty to use local storage (default).

| Variable | Default | Description |
|----------|---------|-------------|
| `S3_ENDPOINT_URL` | *(empty)* | S3 endpoint URL (AWS, MinIO, Cloudflare R2, etc.) |
| `S3_ACCESS_KEY` | *(empty)* | S3 access key |
| `S3_SECRET_KEY` | *(empty)* | S3 secret key |
| `S3_BUCKET` | *(empty)* | Bucket name |
| `S3_REGION` | *(empty)* | AWS region (e.g. `us-east-1`) |

## AI Script Generation

Leave `OPENAI_API_KEY` empty to use the built-in placeholder script provider (no API call,
produces a structured template script).

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | *(empty)* | OpenAI API key. Leave empty to use placeholder provider |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | Override to use compatible providers (LM Studio, Together AI, Groq) |
| `OPENAI_MODEL` | `gpt-4o-mini` | Model name passed to the completions API |
| `ANTHROPIC_API_KEY` | *(empty)* | Anthropic API key (Claude) — reserved for future integration |

## Text-to-Speech (TTS)

| Variable | Default | Description |
|----------|---------|-------------|
| `EDGE_TTS_ENABLED` | `true` | Enable Microsoft Edge TTS (free, no API key required) |
| `EDGE_TTS_DEFAULT_VOICE` | `en-US-JennyNeural` | Default voice identifier |
| `COQUI_TTS_ENABLED` | `false` | Enable Coqui TTS local server (implementation pending) |
| `COQUI_TTS_URL` | `http://coqui-tts:5002` | Coqui TTS server endpoint |

## Caption / Transcription

`faster-whisper` is an **optional** dependency.  The API server starts and all
other pipeline steps work normally without it.  When Whisper is unavailable the
caption step is skipped and `caption_status: "skipped"` / `caption_warning` are
written to `output_metadata` so the UI can surface the reason.

| Variable | Default | Description |
|----------|---------|-------------|
| `WHISPER_ENABLED` | `true` | Enable Whisper caption generation. Set to `false` to skip captions without installing `faster-whisper`. |
| `WHISPER_MODEL_SIZE` | `base` | faster-whisper model size: `tiny`, `base`, `small`, `medium`, `large-v3` |
| `WHISPER_DEVICE` | `cpu` | Compute device: `cpu` or `cuda` |

### Installing faster-whisper (optional)

```bash
pip install faster-whisper
```

`faster-whisper` requires `ctranslate2`.  A compatible CPU is sufficient for
all model sizes; a CUDA-capable GPU dramatically speeds up `medium` and above.
If the package cannot be imported at startup, a `whisper_unavailable` warning is
logged so operators know immediately that captions will be skipped.

## Stock Media

Leave API keys empty to fall back to auto-generated colour-block placeholder clips.

| Variable | Default | Description |
|----------|---------|-------------|
| `PEXELS_API_KEY` | *(empty)* | [Pexels API key](https://www.pexels.com/api/) (free tier available) |
| `PIXABAY_API_KEY` | *(empty)* | [Pixabay API key](https://pixabay.com/api/docs/) (free tier available) |

## Upload / Distribution

| Variable | Default | Description |
|----------|---------|-------------|
| `YOUTUBE_UPLOAD_ENABLED` | `false` | Enable YouTube Data API v3 upload (requires OAuth2 setup) |
| `YOUTUBE_CLIENT_SECRETS_FILE` | *(empty)* | Path to the OAuth2 client-secrets JSON file |

## Job Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `MAX_JOB_RETRIES` | `3` | Maximum number of automatic retries for a failed job |
| `DRY_RUN` | `false` | When `true`, jobs execute the full pipeline logic but skip FFmpeg rendering and uploads |
| `DEBUG_KEEP_FAILED_WORKDIR` | `false` | When `true`, the temporary work directory for **failed** jobs is preserved on disk instead of deleted. Useful for debugging FFmpeg errors. |

## Temp File Retention

During each pipeline run, a temporary work directory is created at
`$STORAGE_PATH/temp/<job_id>/`.  It holds the TTS audio, downloaded stock
clips, and the generated SRT subtitle file.

| Outcome | Default behaviour | Override |
|---------|-------------------|---------|
| **Job completed successfully** | Directory is deleted immediately after the job finishes | — |
| **Job failed** | Directory is deleted so disk space is not wasted | Set `DEBUG_KEEP_FAILED_WORKDIR=true` to keep it for debugging |
| **Directory older than 24 h** | Removed by the `cleanup_temp_dirs` Celery beat task | Adjust the beat schedule in `worker/tasks/scheduled.py` if you need a different retention window |

> **Tip** – if a completed job's output video was not uploaded to external storage,
> it lives in `$STORAGE_PATH/outputs/<job_id>.mp4` and is **not** affected by temp
> cleanup.  Only the intermediate files in `temp/` are removed.

## GPU Rendering (optional)

| Variable | Default | Description |
|----------|---------|-------------|
| `NVIDIA_VISIBLE_DEVICES` | `void` | Set to `all` to expose NVIDIA GPU to the worker container |
| `NVIDIA_NVENC_ENABLED` | `false` | Use NVENC hardware encoder in FFmpeg (`h264_nvenc`) |

## Feature Flags

Feature flags are read from individual `FEATURE_*` environment variables. All values
are `true` or `false`.

| Variable | Default | Description |
|----------|---------|-------------|
| `FEATURE_CORE_VIDEO` | `true` | FFmpeg video building |
| `FEATURE_AI_SCRIPTS` | `true` | AI-generated scripts (OpenAI / placeholder) |
| `FEATURE_TRENDS` | `true` | Trend discovery (Google Trends + RSS) |
| `FEATURE_TTS` | `true` | Text-to-speech synthesis |
| `FEATURE_CAPTIONS` | `true` | Subtitle generation via Whisper |
| `FEATURE_STOCK_MEDIA` | `true` | Stock video fetching (Pexels / Pixabay / local) |
| `FEATURE_N8N` | `true` | n8n webhook receiver |
| `FEATURE_YOUTUBE_UPLOAD` | `false` | YouTube upload (requires additional setup) |
| `FEATURE_SOCIAL_UPLOADERS` | `false` | Social platform uploaders (reserved) |
| `FEATURE_GPU_RENDERING` | `false` | GPU-accelerated rendering |
| `FEATURE_CLOUD_STORAGE` | `false` | S3-compatible cloud storage |

> Disabling a feature flag returns HTTP 403 with `{"detail": "Feature '…' is disabled"}`
> when a user attempts to use that feature via the API.
